# HospiPlan SaaS — Contrats d'interface (Phase 0)

> **Statut : FIGÉ v1.0 — validé le 12/11/2026** (décisions : identifiants `*_id` entre services, `Service`/`CareUnit` dans planning, jetons de service JWT pour les appels internes).
> Toute modification passe par une PR qui touche ce fichier, relue et approuvée par A **et** B.
> Règle de compatibilité : on peut **ajouter** un champ optionnel sans changer de version ; **renommer / supprimer / changer le type** d'un champ = nouvelle version (`/api/v2/...` ou `version: 2` dans le message).

Sommaire :
1. Découpage validé et propriété des données
2. Conventions communes (URL, JSON, erreurs, pagination)
3. Authentification : JWT utilisateur + appels inter-services
4. service-identite (A)
5. service-personnel (A)
6. service-planning (B)
7. Événement `planning.generated` (B → Azure Function)
8. Retry, timeouts, idempotence
9. Développement local (ports, mocks)

---

## 1. Découpage validé et propriété des données

Chaque modèle Django actuel (`hospiplan/api/models.py`) a **un seul propriétaire**. Un service ne lit **jamais** directement le schéma d'un autre : il passe par l'API. Les références entre services sont des **identifiants entiers** (pas de `ForeignKey` inter-schéma).

| Service | Schéma PostgreSQL | Modèles possédés | Responsable |
|---|---|---|---|
| **service-identite** | `identite` | `Etablissement` *(nouveau)*, `Abonnement` *(nouveau)*, `Utilisateur` *(nouveau, lié à un `staff_id` optionnel)* | A |
| **service-personnel** | `personnel` | `Staff`, `Role`, `Specialty`, `ContractType`, `Contract`, `Certification`, `StaffCertification`, `AbsenceType`, `Absence`, `Preference`, `StaffServiceAssignment`, `StaffLoan` | A |
| **service-planning** | `planning` | `Service`, `CareUnit`, `ServiceStatus`, `ShiftType`, `Shift` (+ certifications requises par id), `ShiftAssignment`, `PatientLoad`, `Rule`, `SoftConstraintWeight` | B |
| **fn-planning-events** | — (écrit éventuellement dans Blob Storage) | Rapports générés | B |

Champs qui deviennent des identifiants « externes » (plus de clé étrangère) :

| Modèle | Champ actuel | Devient | Pointe vers |
|---|---|---|---|
| `Preference` (personnel) | `target_shift_type` | `target_shift_type_id: int \| null` | planning `ShiftType` |
| `Preference` (personnel) | `target_service` | `target_service_id: int \| null` | planning `Service` |
| `StaffServiceAssignment`, `StaffLoan` (personnel) | `service`, `from_service`, `to_service` | `*_service_id: int` | planning `Service` |
| `Service` (planning) | `manager` | `manager_staff_id: int \| null` | personnel `Staff` |
| `Shift` (planning) | `required_certifications` (M2M) | `required_certification_ids: int[]` | personnel `Certification` |
| `ShiftAssignment` (planning) | `staff` | `staff_id: int` | personnel `Staff` |

**Multi-établissement (SaaS)** : *toutes* les tables métier de personnel et planning reçoivent une colonne `etablissement_id: int` (non nulle, indexée). Chaque requête est filtrée par l'`etablissement_id` du JWT — jamais par un paramètre envoyé par le client.

---

## 2. Conventions communes

| Sujet | Règle |
|---|---|
| Préfixe | `/api/v1/` pour les API publiques, `/internal/v1/` pour les API inter-services (refusées avec un JWT utilisateur) |
| Santé | `GET /health` → `200 {"status":"ok","service":"<nom>","version":"<sha git>"}` — sans authentification, utilisé par App Service et les alertes |
| Format | JSON UTF-8, `Content-Type: application/json` ; noms de champs en `snake_case` |
| Dates | `YYYY-MM-DD` ; dates-heures ISO 8601 **avec fuseau** : `2026-11-12T07:00:00+01:00` ; stockage en UTC |
| Identifiants | entiers (`id`) ; pas d'UUID côté métier sauf `event_id` / `correlation_id` |
| Pagination | listes : `?page=1&page_size=50` (max 200) → `{"count", "next", "previous", "results": [...]}` (format DRF `PageNumberPagination`) |
| Filtres | paramètres de requête simples : `?staff_id=`, `?start_date=`, `?end_date=`, `?service_id=` |
| Traçabilité | chaque requête porte `X-Correlation-ID` (UUID) ; un service le **propage** à ses appels sortants et dans l'événement ; s'il est absent, le premier service le génère. Il apparaît dans chaque ligne de log |
| CORS | seule l'origine du frontend (variable `CORS_ALLOWED_ORIGINS`) est autorisée |

### Format d'erreur (identique pour les 3 services)

```json
{
  "error": {
    "code": "RULE_ABSENCE_PRIO",
    "message": "Ce soignant est absent du 2026-11-10 au 2026-11-14.",
    "details": {"staff_id": 12, "shift_id": 340},
    "correlation_id": "6f1c2e4a-0b7d-4a51-9a7e-3c1f0d2b9e11"
  }
}
```

| HTTP | `code` (exemples) | Quand |
|---|---|---|
| 400 | `VALIDATION_ERROR`, `RULE_*` (règles métier existantes : `RULE_NO_OVERLAP`, `RULE_ABSENCE_PRIO`, `RULE_CERTIFICATION`, `RULE_CONTRACT_ELIG`, `RULE_WEEKLY_QUOTA`, `RULE_HARD_PREFERENCE`, `RULE_MIN_STAFF`, `RULE_STAFF_INACTIVE`) | données invalides / règle dure violée |
| 401 | `AUTH_REQUIRED`, `TOKEN_EXPIRED`, `TOKEN_INVALID` | JWT absent ou invalide |
| 403 | `FORBIDDEN_ROLE`, `FORBIDDEN_TENANT` | rôle insuffisant / ressource d'un autre établissement |
| 404 | `NOT_FOUND` | ressource inexistante **dans l'établissement** (on ne révèle pas qu'elle existe ailleurs) |
| 409 | `CONFLICT` | doublon (email, affectation existante) |
| 429 | `RATE_LIMITED` | trop de tentatives de login |
| 502 / 503 / 504 | `UPSTREAM_ERROR`, `UPSTREAM_UNAVAILABLE`, `UPSTREAM_TIMEOUT` | un service appelé a échoué (après retries) |
| 500 | `INTERNAL_ERROR` | bug — aucun détail technique dans `message` |

---

## 3. Authentification

### 3.1 JWT utilisateur (émis par service-identite)

- Algorithme **RS256** : service-identite signe avec sa clé **privée** ; personnel et planning vérifient avec la clé **publique** (variable `JWT_PUBLIC_KEY`, ou `GET /api/v1/auth/jwks`). Aucun service autre qu'identite ne peut fabriquer de jeton.
- Durée : access token **15 min**, refresh token **7 jours** (rotation à chaque refresh, révocable).
- En-tête : `Authorization: Bearer <access_token>`.

Contenu (claims) de l'access token :

```json
{
  "iss": "hospiplan-identite",
  "aud": "hospiplan-api",
  "sub": "42",
  "email": "cadre@chu-exemple.fr",
  "etablissement_id": 3,
  "role": "CADRE",
  "staff_id": 17,
  "type": "access",
  "iat": 1762934400,
  "exp": 1762935300,
  "jti": "b0f6c8d2-..."
}
```

| Claim | Type | Sens |
|---|---|---|
| `sub` | string | id de l'`Utilisateur` dans identite |
| `etablissement_id` | int | établissement client (tenant) — **seule** source du filtrage multi-établissement |
| `role` | enum | `SUPERADMIN`, `ADMIN`, `CADRE`, `SOIGNANT` |
| `staff_id` | int \| null | fiche soignant liée (obligatoire si `role = SOIGNANT`) |

### 3.2 Matrice des rôles

| Action | SUPERADMIN (éditeur SaaS) | ADMIN (établissement) | CADRE (cadre de santé) | SOIGNANT |
|---|---|---|---|---|
| Gérer les établissements / abonnements | ✅ | ❌ | ❌ | ❌ |
| Gérer les utilisateurs de son établissement | ✅ | ✅ | ❌ | ❌ |
| Référentiels (services, unités, types de garde, certifications, types de contrat) | ✅ | ✅ | lecture | lecture |
| Soignants, contrats, certifications des soignants | ✅ | ✅ | ✅ | lecture **de sa fiche** |
| Absences / préférences | ✅ | ✅ | ✅ | **les siennes** (création + lecture) |
| Postes, affectations manuelles | ✅ | ✅ | ✅ | lecture **des siennes** |
| Générer un planning | ✅ | ✅ | ✅ | ❌ |
| Statistiques | ✅ | ✅ | ✅ | ❌ |

### 3.3 Appels inter-services (`/internal/v1/*`)

- service-planning appelle service-personnel avec un **jeton de service** : `Authorization: Bearer <JWT service>` signé par identite via `POST /internal/v1/auth/service-token` (identifiants `SERVICE_CLIENT_ID` / `SERVICE_CLIENT_SECRET` en variables d'environnement / Key Vault), claims : `{"sub": "service-planning", "type": "service", "scope": ["personnel:read"], "aud": "hospiplan-internal"}`, durée 15 min, mis en cache.
- L'établissement concerné est passé dans l'en-tête `X-Etablissement-Id` (accepté **uniquement** avec un jeton de type `service`).
- Un JWT utilisateur sur `/internal/...` → `403 FORBIDDEN_ROLE`.

---

## 4. service-identite (A)

| Méthode | Chemin | Rôle requis | Corps / paramètres | Réponse |
|---|---|---|---|---|
| POST | `/api/v1/auth/login` | public (limité : 5 essais / min / IP) | `{"email", "password"}` | `200 {"access", "refresh", "user": {...}}` |
| POST | `/api/v1/auth/refresh` | public | `{"refresh"}` | `200 {"access", "refresh"}` |
| POST | `/api/v1/auth/logout` | connecté | `{"refresh"}` | `204` (révoque le refresh) |
| GET | `/api/v1/auth/me` | connecté | — | `200 user` |
| GET | `/api/v1/auth/jwks` | public | — | clé publique (JWKS) |
| GET / POST | `/api/v1/etablissements` | SUPERADMIN | `{"nom", "siret", "ville", "plan"}` | établissement |
| GET / PATCH | `/api/v1/etablissements/{id}` | SUPERADMIN ; ADMIN pour le sien (lecture) | — | établissement |
| GET / POST | `/api/v1/users` | ADMIN+ | `{"email", "first_name", "last_name", "role", "staff_id", "password"}` | utilisateur |
| GET / PATCH / DELETE | `/api/v1/users/{id}` | ADMIN+ | — | utilisateur (`DELETE` = désactivation) |
| POST | `/internal/v1/auth/service-token` | identifiants de service | `{"client_id", "client_secret"}` | `{"access", "expires_in"}` |

Objets :

```json
// user
{"id": 42, "email": "cadre@chu-exemple.fr", "first_name": "Awa", "last_name": "Diop",
 "role": "CADRE", "etablissement_id": 3, "staff_id": 17, "is_active": true}

// etablissement
{"id": 3, "nom": "CHU Exemple", "siret": "12345678900011", "ville": "Lyon",
 "plan": "STANDARD", "statut_abonnement": "ACTIF", "max_soignants": 300, "created_at": "..."}
```

`plan` ∈ `ESSAI`, `STANDARD`, `PREMIUM` (sert au pitch et au FinOps : prix / nb de soignants).

---

## 5. service-personnel (A)

API publique (JWT utilisateur, filtrée par `etablissement_id`) — reprend les endpoints actuels du monolithe :

| Ressource | Chemin | Méthodes | Remarques |
|---|---|---|---|
| Soignants | `/api/v1/staff` | GET, POST | filtres `?is_active=`, `?search=` |
| | `/api/v1/staff/{id}` | GET, PATCH, DELETE | `DELETE` = `is_active=false` (on garde l'historique) |
| | `/api/v1/staff/{id}/profile` | GET | fiche complète (actuel `StaffProfileView`) |
| | `/api/v1/staff/overview` | GET | liste + statut (actuel `StaffListWithStatusView`) |
| Rôles, spécialités | `/api/v1/roles`, `/api/v1/specialties` | CRUD | |
| Contrats | `/api/v1/contract-types`, `/api/v1/contracts` | CRUD | `?staff_id=` |
| Certifications | `/api/v1/certifications`, `/api/v1/staff-certifications` | CRUD | `?staff_id=`, `?expiring_before=YYYY-MM-DD` (utilisé par la Function Timer) |
| Absences | `/api/v1/absence-types`, `/api/v1/absences` | CRUD | `?staff_id=&start_date=&end_date=` |
| Préférences | `/api/v1/preferences` | CRUD | `?staff_id=` |
| Rattachements / prêts | `/api/v1/service-assignments`, `/api/v1/staff-loans` | CRUD | |

Objet `staff` (inchangé par rapport à `StaffSerializer`, + `etablissement_id`) :

```json
{"id": 17, "etablissement_id": 3, "first_name": "Awa", "last_name": "Diop",
 "email": "awa.diop@chu-exemple.fr", "phone": "0600000000", "is_active": true,
 "roles": [2], "specialties": [5], "created_at": "2026-09-01T08:00:00Z"}
```

### 5.1 API interne consommée par service-planning ⚠️ point de synchronisation

Le moteur (`feasibility.py`, `generator.py`) charge tout en mémoire en une fois : on garde ce principe avec **un seul appel groupé** (pas un appel par soignant).

`GET /internal/v1/planning-context?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`
En-têtes : `Authorization: Bearer <jeton service>`, `X-Etablissement-Id: 3`, `X-Correlation-ID`.
Le service personnel applique lui-même la marge de ±7 jours sur les absences.

```json
{
  "etablissement_id": 3,
  "start_date": "2026-11-16",
  "end_date": "2026-11-16",
  "generated_at": "2026-11-12T10:00:00Z",
  "staff": [
    {"id": 17, "first_name": "Awa", "last_name": "Diop", "is_active": true, "role_ids": [2]}
  ],
  "absences": [
    {"staff_id": 17, "start_date": "2026-11-10", "expected_end_date": "2026-11-14"}
  ],
  "certifications": [
    {"staff_id": 17, "certification_id": 4, "expiration_date": "2027-03-01"}
  ],
  "contracts": [
    {"staff_id": 17, "start_date": "2025-01-01", "end_date": null,
     "night_shift_allowed": true, "max_hours_per_week": 48, "max_consecutive_nights": 3}
  ],
  "preferences": [
    {"staff_id": 17, "kind": "avoids_day", "importance": 3, "is_hard_constraint": false,
     "description": "Pas le dimanche", "target_shift_type_id": null, "target_service_id": null,
     "target_day_of_week": 6, "start_date": null, "end_date": null}
  ],
  "service_assignments": [
    {"staff_id": 17, "service_id": 1, "start_date": "2025-01-01", "end_date": null}
  ],
  "loans": [
    {"staff_id": 17, "from_service_id": 1, "to_service_id": 2,
     "start_date": "2026-11-01", "end_date": "2026-11-30"}
  ]
}
```

Seuls les soignants **actifs** figurent dans `staff` ; les autres listes ne concernent que ces soignants. `expiration_date: null` = certification sans expiration.

`GET /internal/v1/staff/{id}/eligibility?date=YYYY-MM-DD` — utilisé pour l'**affectation manuelle** (une seule personne) :

```json
{"staff_id": 17, "is_active": true, "absent": false, "absence": null,
 "certification_ids_valid": [4, 7], "contract": {"night_shift_allowed": true, "max_hours_per_week": 48},
 "hard_preferences": [{"description": "Pas le dimanche", "target_day_of_week": 6}]}
```

`GET /internal/v1/staff?ids=17,18,19` → `[{"id", "first_name", "last_name", "email"}]` (noms pour les statistiques et l'email de notification).

---

## 6. service-planning (B)

API publique (JWT utilisateur, filtrée par `etablissement_id`) :

| Ressource | Chemin | Méthodes | Rôle |
|---|---|---|---|
| Services | `/api/v1/services` | CRUD | écriture ADMIN+ |
| Unités de soins | `/api/v1/care-units` | CRUD | écriture ADMIN+ |
| Types de garde | `/api/v1/shift-types` | CRUD | écriture ADMIN+ |
| Postes (gardes) | `/api/v1/shifts` | CRUD, `?start_date=&end_date=&care_unit_id=` | écriture CADRE+ |
| Affectations | `/api/v1/assignments` | GET, POST, DELETE | écriture CADRE+ ; SOIGNANT : GET des siennes |
| Génération | `/api/v1/plannings/generate` | POST | CADRE+ |
| Statistiques | `/api/v1/stats?start_date=&end_date=` | GET | CADRE+ |
| Poids contraintes molles | `/api/v1/soft-constraint-weights` | GET, PATCH | ADMIN+ |

### 6.1 POST `/api/v1/assignments`

Requête : `{"shift_id": 340, "staff_id": 17}` → appelle `/internal/v1/staff/17/eligibility` puis vérifie chevauchement, quota hebdo et certifications requises localement.
Réponses : `201` affectation · `400` avec `code` `RULE_*` · `503 UPSTREAM_UNAVAILABLE` si personnel est injoignable (on **n'affecte pas** sans vérification).

```json
{"id": 901, "shift_id": 340, "staff_id": 17, "assigned_at": "2026-11-12T10:03:00Z"}
```

### 6.2 POST `/api/v1/plannings/generate`

Requête (inchangée par rapport à `GeneratePlanningView`) :

```json
{"date": "2026-11-16", "service_id": 1, "metaheuristic": true, "persist": true}
```

Réponse `200` :

```json
{
  "planning_id": "a3e1b6f0-3c5d-4e7a-9f21-0d4c8b7e6a55",
  "date": "2026-11-16",
  "service_id": 1,
  "assignments": [{"shift_id": 340, "staff_id": 17, "legal": true}],
  "uncovered": [{"shift_id": 341, "missing": 1, "reason": "Aucun soignant certifié disponible"}],
  "score": {"total": 12.5, "details": {"M1": 0, "M2": 3.0, "M3": 4.5, "M4": 2.0, "M5": 0, "M6": 0, "M7": 3.0}, "weights": {"M1": 5.0}},
  "summary": {"shifts_total": 12, "covered": 11, "uncovered": 1, "staff_used": 9},
  "metaheuristic": {"iterations": 200, "improved": true},
  "persisted": 14,
  "errors": [],
  "event_published": true
}
```

Renommage `shift` → `shift_id`, `staff` → `staff_id` : **déjà appliqué** dans le monolithe (`/api/assignments/`, `/api/plannings/generate/`) et dans le frontend (`Affectations.js`, `GeneratePlanning.js`). `planning_id` est nouveau (UUID, sert d'`event_id` et de clé d'idempotence). Si personnel est injoignable → `503 UPSTREAM_UNAVAILABLE`, rien n'est persisté. Si la publication Service Bus échoue après retries → la réponse reste `200` avec `"event_published": false` (le planning est déjà enregistré ; l'erreur est journalisée et alertée).

### 6.3 GET `/api/v1/stats`

Même structure que l'actuelle `StatsView` (par soignant, par service, global). Les noms des soignants sont obtenus via `/internal/v1/staff?ids=...`.

---

## 7. Événement `planning.generated`

- Transport : **Azure Service Bus**, file (queue) `planning-events` (Basic tier suffit — un seul consommateur).
- Producteur : service-planning, **après commit** de la transaction (jamais avant).
- Consommateur : Azure Function `fn-planning-events` (trigger `ServiceBusTrigger`).
- Propriétés du message Service Bus : `MessageId = event_id` (déduplication), `CorrelationId = correlation_id`, `ContentType = application/json`, `Subject = planning.generated`.

Corps (enveloppe inspirée de CloudEvents) :

```json
{
  "event_id": "a3e1b6f0-3c5d-4e7a-9f21-0d4c8b7e6a55",
  "event_type": "planning.generated",
  "version": 1,
  "occurred_at": "2026-11-12T10:03:12Z",
  "source": "service-planning",
  "correlation_id": "6f1c2e4a-0b7d-4a51-9a7e-3c1f0d2b9e11",
  "etablissement_id": 3,
  "triggered_by": {"user_id": 42, "role": "CADRE"},
  "data": {
    "planning_id": "a3e1b6f0-3c5d-4e7a-9f21-0d4c8b7e6a55",
    "date": "2026-11-16",
    "service_id": 1,
    "service_name": "Cardiologie",
    "summary": {"shifts_total": 12, "covered": 11, "uncovered": 1, "staff_used": 9},
    "score_total": 12.5,
    "assignments": [
      {"shift_id": 340, "staff_id": 17, "start": "2026-11-16T07:00:00+01:00",
       "end": "2026-11-16T19:00:00+01:00", "shift_type": "Jour", "care_unit": "USIC"}
    ],
    "uncovered": [{"shift_id": 341, "missing": 1, "reason": "Aucun soignant certifié disponible"}]
  }
}
```

Le message ne contient **aucune donnée personnelle** au-delà des identifiants (pas de nom, pas d'email) : la Function récupère les emails via `/internal/v1/staff?ids=` avec son propre jeton de service.

Traitement par la Function :
1. Calcul des indicateurs (taux de couverture, nb de postes non couverts) → log structuré dans Application Insights.
2. Rapport JSON/CSV → Blob Storage `rapports/{etablissement_id}/{date}/{planning_id}.json`.
3. Notification aux soignants affectés (email ou log simulé pour la démo) ; alerte au cadre si `uncovered` non vide.

Fonction Timer (bonus) `fn-certifications-expiring` : chaque jour à 06:00, `GET /api/v1/staff-certifications?expiring_before=<J+30>` par établissement → notification.

---

## 8. Retry, timeouts, idempotence

| Appel | Timeout | Retry | Si échec final |
|---|---|---|---|
| planning → personnel (HTTP) | connexion 2 s, lecture 5 s (`planning-context` : 10 s) | 3 tentatives, backoff exponentiel 0,5 s → 1 s → 2 s + aléa, **uniquement** sur erreur réseau, 502, 503, 504 (jamais sur 4xx) | `503 UPSTREAM_UNAVAILABLE` / `504 UPSTREAM_TIMEOUT` au client |
| planning → Service Bus | 10 s | retry intégré au SDK (`RetryPolicy`, 3 tentatives, exponentiel) | `event_published: false` + log `ERROR` + alerte |
| Function (trigger Service Bus) | — | redélivrance Service Bus, `maxDeliveryCount = 5` | message en **dead-letter queue**, alerte Azure Monitor |
| Frontend → API | 30 s (génération), 10 s (autres) | pas de retry automatique sur POST | message d'erreur lisible (`error.message`) |

Idempotence : la Function ignore un `event_id` déjà traité (le nom du blob = `planning_id` ; s'il existe, on ne renvoie pas les notifications). `POST /plannings/generate` n'est pas rejoué automatiquement par le client.

---

## 9. Développement local

| Composant | Port local | URL dans les autres services (variable d'env) |
|---|---|---|
| frontend | 3000 | — |
| service-identite | 8001 | `IDENTITE_URL=http://localhost:8001` |
| service-personnel | 8002 | `PERSONNEL_URL=http://localhost:8002` |
| service-planning | 8003 | `PLANNING_URL=http://localhost:8003` |
| PostgreSQL | 5432 | `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` (un utilisateur PostgreSQL **par service**, droits sur son seul schéma) |
| Service Bus | — | `SERVICEBUS_CONNECTION_STRING` ; en local sans Azure : `EVENTS_BACKEND=log` (l'événement est seulement journalisé) |

Mocks pour avancer en parallèle :
- **B** développe service-planning contre un mock de `/internal/v1/planning-context` et `/eligibility` construit à partir des exemples JSON ci-dessus (`docs/contrats/exemples/`).
- **A** développe le frontend avec un JWT de test signé par une clé de dev (jamais la clé de production).
- Les exemples JSON de ce document sont la **référence** des tests : un test de contrat par service vérifie que les réponses ont bien ces champs.
