# Travail de A — Produit & Applicatif

> Référence obligatoire : `docs/contrats/CONTRATS.md` (v1.0 validée). Règles Git : `CONTRIBUTING.md` (une branche par tâche, PR relue par B).
> Barème porté par A : Idée (10) + Besoin (10) + Architecture microservices (15) + Sécurité (5) = **40 pts**, plus PaaS (10, en commun), démo et présentation.

## Prérequis (15 min)

```bash
git switch main && git pull
cp .env.example .env            # puis renseigner DJANGO_SECRET_KEY, DB_USER, DB_PASSWORD, DB_PORT
python -m venv myenv && myenv\Scripts\activate
pip install -r hospiplan/requirements.txt
cd hospiplan && python manage.py check && python manage.py runserver
```

---

## Ordre de réalisation

| # | Tâche | Branche | Durée | Dépend de | Débloque |
|---|---|---|---|---|---|
| A1 | service-identite : comptes, établissements, JWT | `feat/identite-jwt` | 1 j | — | A2, A3, B (vérif. JWT dans planning) |
| A2 | service-personnel : extraction + API interne | `feat/personnel-service` | 1,5 j | A1 (vérif. JWT) | **B** (remplace le mock planning-context) |
| A3 | Frontend : login, rôles, nouveaux services | `feat/frontend-auth` | 1 j | A1, A2 | démo |
| A4 | Déploiement App Service identite + personnel | `infra/appservice-identite-personnel` | ½ j | A1, A2, VM de B | démo |
| A5 | Livrables : pitch, besoin, backlog, archi, sécurité applicative | `docs/livrables-a` | 1 j | — (à faire en parallèle) | soutenance |

⚠️ **Priorité pour B** : `GET /internal/v1/planning-context` (A2) est consommé par service-planning. Le livrer tôt, même sans le reste de A2.

---

## A1 — service-identite (`service-identite/`)

Contrat : `CONTRATS.md` §3 et §4.

- [ ] Projet Django `service-identite/` avec son propre `requirements.txt`, `Dockerfile`, `.env.example` et `README.md` ; port local **8001** ; schéma PostgreSQL `identite`.
- [ ] Modèles :
  - `Etablissement` : `nom`, `siret`, `ville`, `plan` (`ESSAI`/`STANDARD`/`PREMIUM`), `statut_abonnement`, `max_soignants`, `created_at` ;
  - `Utilisateur` : modèle custom `AbstractUser` avec login par email, `role` (`SUPERADMIN`/`ADMIN`/`CADRE`/`SOIGNANT`), `etablissement` (FK), `staff_id` (int, nullable).
  - À créer **avant** la première migration, car le modèle utilisateur custom ne se change pas après.
- [ ] JWT avec `djangorestframework-simplejwt` :
  - signature RS256 (`SIGNING_KEY` = clé privée et `VERIFYING_KEY` = clé publique, lues en variables d'env) ;
  - access 15 min, refresh 7 j, rotation des refresh et blacklist ;
  - claims personnalisés `etablissement_id`, `role`, `staff_id`, `email`, `iss`, `aud`, `type` ;
  - générer la paire de clés : `openssl genpkey -algorithm RSA -out private.pem -pkeyopt rsa_keygen_bits:2048` puis `openssl rsa -in private.pem -pubout -out public.pem`. Ces fichiers **ne doivent jamais être commités** (`*.pem` est déjà dans `.gitignore`).
- [ ] Endpoints : `auth/login`, `auth/refresh`, `auth/logout`, `auth/me`, `auth/jwks`, `etablissements`, `users`, `/health`.
- [ ] Limitation du login à 5 essais / min / IP (throttling DRF) → code `429 RATE_LIMITED`.
- [ ] Jetons de service : `POST /internal/v1/auth/service-token`. Les clients autorisés (`service-planning`, `fn-planning-events`) et leurs secrets sont lus en variables d'env (`SERVICE_CLIENTS`). Le jeton porte `type: "service"`, `scope` et `aud: "hospiplan-internal"`.
- [ ] **Paquet partagé** `libs/hospiplan_auth/`, à copier ou installer dans chaque service et à réutiliser par B dans planning :
  - une classe d'authentification DRF qui vérifie le JWT avec la clé publique ;
  - des permissions `IsRole(...)`, `IsServiceToken(scope)` ;
  - un mixin `TenantQuerysetMixin`, qui filtre les requêtes par `request.user.etablissement_id` ;
  - un gestionnaire d'exceptions au format d'erreur commun (§2) ;
  - un middleware `X-Correlation-ID`.
- [ ] Commande `seed_identite` : un établissement de démo, et un utilisateur par rôle (mots de passe lus dans l'environnement, pas en dur).
- [ ] Tests :
  - login OK / KO ;
  - claims présents dans le jeton ;
  - jeton expiré → 401 ;
  - rôle insuffisant → 403 ;
  - un ADMIN ne voit pas les utilisateurs d'un autre établissement.

## A2 — service-personnel (`service-personnel/`)

Contrat : `CONTRATS.md` §1 et §5.

- [ ] Projet Django `service-personnel/` (port **8002**, schéma `personnel`). Y déplacer les modèles du monolithe : `Staff`, `Role`, `Specialty`, `ContractType`, `Contract`, `Certification`, `StaffCertification`, `AbsenceType`, `Absence`, `Preference`, `StaffServiceAssignment`, `StaffLoan`.
- [ ] Ajouter `etablissement_id` (int, indexé, non nul) à chaque table.
- [ ] Remplacer les FK vers planning par des entiers :
  - `Preference` : `target_shift_type_id`, `target_service_id` ;
  - `StaffServiceAssignment` : `service_id` ;
  - `StaffLoan` : `from_service_id`, `to_service_id`.
- [ ] Endpoints publics `/api/v1/...` (§5) avec les règles de rôles de la matrice §3.2. Un SOIGNANT ne voit que sa fiche, ses absences et ses préférences (via le claim `staff_id`).
- [ ] **Corriger le bug existant** : `staff/overview` est masqué par la route `staff/{id}`. Déclarer la route `overview` avant le routeur, ou utiliser une action `@action(detail=False)`.
- [ ] Filtre `?expiring_before=` sur `staff-certifications` (utilisé par la Function Timer de B).
- [ ] **API interne** (jeton de service obligatoire + `X-Etablissement-Id`) :
  - `GET /internal/v1/planning-context?start_date&end_date` : réponse **identique** à `docs/contrats/exemples/personnel-planning-context.json`. Inclure la marge ±7 j sur les absences, uniquement les soignants actifs, et éviter les requêtes N+1 (`select_related`, `prefetch_related`) ;
  - `GET /internal/v1/staff/{id}/eligibility?date` : conforme à `personnel-eligibility.json` ;
  - `GET /internal/v1/staff?ids=1,2,3`.
- [ ] Reprise des données : adapter `seed_phase3.py` (ou faire un script de migration depuis le monolithe) pour remplir le schéma `personnel` avec `etablissement_id = 1`.
- [ ] **Tests de contrat** : comparer les clés de la réponse `planning-context` à l'exemple JSON. C'est ce qui garantit que B ne sera pas cassé.

## A3 — Frontend (`frontend/`)

- [ ] Écran de **login**. Conserver le jeton d'accès en mémoire et le refresh token en `sessionStorage` (à justifier dans l'analyse de sécurité).
- [ ] Intercepteur axios :
  - ajoute `Authorization: Bearer` ;
  - sur une 401, appelle `/auth/refresh` une seule fois puis rejoue la requête ;
  - sinon, redirige vers le login.
- [ ] URL des API dans des variables d'environnement (`REACT_APP_IDENTITE_URL`, `REACT_APP_PERSONNEL_URL`, `REACT_APP_PLANNING_URL`) à la place de `http://localhost:8000` codé en dur dans chaque composant. Les regrouper dans un module `src/api.js`.
- [ ] Menu et boutons selon le rôle : un SOIGNANT ne voit pas Génération ni Statistiques ; la gestion des utilisateurs est réservée à l'ADMIN.
- [ ] Nouvel écran « Utilisateurs », pour l'ADMIN.
- [ ] Affichage des erreurs au nouveau format `error.message`, en gardant `detail` tant que le monolithe tourne.
- [ ] Routes au format `/api/v1/` et en kebab-case (`care-units`, `shift-types`…).
- [ ] *Déjà fait* : `shift_id`/`staff_id` dans `Affectations.js` et `GeneratePlanning.js`.

## A4 — Déploiement App Service (PaaS)

- [ ] Créer 2 App Service Linux Python 3.12 (`app-hospiplan-identite-<suffixe>`, `app-hospiplan-personnel-<suffixe>`) sur **un même plan B1**, partagé avec service-planning de B pour réduire les coûts.
- [ ] Commande de démarrage : `gunicorn <projet>.wsgi --bind=0.0.0.0`.
- [ ] Renseigner les variables dans Configuration → Paramètres d'application :
  - `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=false`, `DJANGO_ALLOWED_HOSTS` ;
  - `DB_*` avec `DB_SSLMODE=require` et l'utilisateur `svc_identite` ou `svc_personnel` fourni par `setup-postgres.sh` de B ;
  - les clés JWT et `CORS_ALLOWED_ORIGINS`.
- [ ] HTTPS Only activé et TLS minimum 1.2.
- [ ] Transmettre à B les IP sortantes (`az webapp show --query outboundIpAddresses`) pour qu'il les ajoute au NSG de la VM avec `update-nsg.sh`.
- [ ] Profil de publication → secrets GitHub `AZURE_PUBLISH_PROFILE_IDENTITE` et `AZURE_PUBLISH_PROFILE_PERSONNEL` (voir `PLAN_TP_SAAS.md` §6).
- [ ] Tests post-déploiement : `/health`, login, appel `planning-context` avec un jeton de service. Faire des captures d'écran.
- [ ] Pour le livrable PaaS : justifier le choix (pas d'OS à gérer, HTTPS et certificats fournis, scaling, slots), le plan B1, les variables, et comparer avec la VM.

## A5 — Livrables (dossier `docs/livrables/`)

| Livrable | Contenu attendu |
|---|---|
| 1. Pitch | problème (plannings hospitaliers faits à la main sous Excel, règles légales complexes), cible (cadres de santé, DRH hospitalières), proposition de valeur, modèle SaaS (abonnement par établissement / par soignant, plans ESSAI/STANDARD/PREMIUM), concurrents |
| 2. Expression du besoin | acteurs (SUPERADMIN, ADMIN, CADRE, SOIGNANT), besoins fonctionnels et non fonctionnels (disponibilité, RGPD, données de santé), contraintes légales (repos, quotas) |
| 3. Backlog fonctionnel | user stories priorisées (MoSCoW) qui couvrent les 7 fonctionnalités obligatoires, avec des critères d'acceptation |
| 4. Architecture microservices | tableau du découpage et justification (§1 du contrat), schéma des appels, choix synchrone et asynchrone. Réponse à « Pourquoi ces microservices ? » |
| 12. Analyse de sécurité (partie applicative) | JWT RS256, rôles, isolation par établissement, validation des entrées, limitation du login, CORS, secrets ; risques restants (refresh token en sessionStorage, compte Azure partagé) |

Préparer aussi les réponses aux questions de soutenance 1, 2, 6 et 8 (voir `PLAN_TP_SAAS.md`).

---

## Points de synchronisation avec B

| Quand | A fournit à B | B fournit à A |
|---|---|---|
| Fin A1 | `libs/hospiplan_auth` + clé publique JWT de dev + identifiants du client `service-planning` | — |
| Pendant A2 | `planning-context` déployé en local (port 8002) | — |
| Avant A4 | IP sortantes des App Service | IP de la VM + identifiants `svc_identite` / `svc_personnel` + plan App Service partagé |
| Avant la démo | comptes de démo par rôle | Function et Service Bus opérationnels |
