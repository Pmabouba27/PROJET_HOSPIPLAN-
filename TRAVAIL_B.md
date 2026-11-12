# Travail de B — Cloud & Plateforme

> Référence obligatoire : `docs/contrats/CONTRATS.md` (v1.0 validée). Règles Git : `CONTRIBUTING.md` (une branche par tâche, PR relue par A).
> Barème porté par B : IaaS (10) + FaaS (10) + Déploiement Azure (10) + FinOps (5) + CI/CD (5) = **40 pts**, plus PaaS (10, en commun), démo et présentation.

## Déjà fait

| Élément | Où |
|---|---|
| Secrets sortis du code, `.env.example`, `requirements.txt`, Dockerfile Python 3.12 + gunicorn | `hospiplan/`, `docker-compose.yml` |
| Mot de passe PostgreSQL local changé | `.env` (poste local) |
| Scripts de la VM PostgreSQL : NSG restreint, SSH par clé, SSL + scram, un schéma et un utilisateur par service, sauvegardes, arrêt automatique | `infra/vm-postgresql/` |
| Contrat de l'événement `planning.generated` + exemple JSON | `CONTRATS.md` §7, `docs/contrats/exemples/planning-generated.event.json` |

## Prérequis (15 min)

```bash
git switch main && git pull
cp .env.example .env            # renseigner DJANGO_SECRET_KEY, DB_USER, DB_PASSWORD, DB_PORT
python -m venv myenv && myenv\Scripts\activate
pip install -r hospiplan/requirements.txt
az login && az account set --subscription "<abonnement de la classe>"
ssh-keygen -t ed25519            # si vous n'avez pas encore de clé SSH
```

Convention de nommage Azure (compte partagé, donc un suffixe = vos initiales) : `rg-hospiplan-<sfx>`, `vm-hospiplan-pg`, `asp-hospiplan-<sfx>`, `app-hospiplan-planning-<sfx>`, `func-hospiplan-events-<sfx>`, `sb-hospiplan-<sfx>`, `sthospiplan<sfx>` (stockage : sans tiret), `appi-hospiplan-<sfx>`, `log-hospiplan-<sfx>`. Région : **France Central**. Tags : `projet=hospiplan`, `environnement=demo`, `proprietaire=<sfx>`.

---

## Ordre de réalisation

| # | Tâche | Branche | Durée | Dépend de | Débloque |
|---|---|---|---|---|---|
| **B1** | Créer la VM PostgreSQL (IaaS) | — (scripts existants) | ½ j | — | **A** (tests Azure), B5 |
| B2 | service-planning : extraction + appels à personnel | `feat/planning-service` | 1,5 j | mock JSON (A2 plus tard) | B3, démo |
| B3 | Service Bus + publication de l'événement avec retry | `feat/planning-events` | ½ j | B2 | B4 |
| B4 | Azure Functions : trigger Service Bus + Timer | `feat/fn-planning-events` | 1 j | B3 | démo FaaS |
| B5 | Déploiement : plan App Service, planning, Function App, supervision | `infra/deploiement-azure` | 1 j | B1, B2, B4 | démo, A4 |
| B6 | CI/CD GitHub Actions | `infra/github-actions` | ½ j | B5 (profils de publication) | livrable CI/CD |
| B7 | Livrables : diagramme Cloud, coûts, sécurité infra, README technique | `docs/livrables-b` | 1 j | — (en parallèle) | soutenance |

⚠️ **Commencer par B1** : la VM conditionne les tests Azure de A.

---

## B1 — VM PostgreSQL (IaaS)

Tout est prêt dans `infra/vm-postgresql/`, il reste à l'exécuter (détails dans son `README.md`).

- [ ] Lancer `PREFIX=hospiplan SUFFIX=<sfx> ./deploy-vm.sh` (depuis Git Bash ou WSL).
- [ ] Attendre la fin de cloud-init : `ssh hospiadmin@<IP> 'cloud-init status --wait'`.
- [ ] Lancer `ssh hospiadmin@<IP> 'sudo bash -s' < setup-postgres.sh`. Le script affiche les mots de passe **une seule fois** : les conserver dans un gestionnaire de mots de passe, **pas** dans le dépôt.
- [ ] Transmettre à A, par un canal privé et non par GitHub : l'IP, `svc_identite`, `svc_personnel` et leurs mots de passe.
- [ ] Migrer le monolithe vers la VM : `.env` avec `DB_HOST=<IP>`, `DB_USER=hospiplan_app`, `DB_SSLMODE=require`, puis `python manage.py migrate` et la commande de seed.
- [ ] Tests du README :
  - connexion avec SSL : OK ;
  - connexion sans SSL : refusée ;
  - connexion depuis une autre IP : timeout.
- [ ] Captures d'écran : vue d'ensemble de la VM, règles du NSG, arrêt automatique.
- [ ] Rédiger la justification IaaS (OS, taille, ports, accès, sécurisation, coût, pourquoi une VM), à partir du tableau de `infra/vm-postgresql/README.md`.

## B2 — service-planning (`service-planning/`)

Contrat : `CONTRATS.md` §1, §6 et §8.

- [ ] Projet Django `service-planning/` (port **8003**, schéma `planning`), avec ses propres `requirements.txt`, `Dockerfile`, `.env.example` et `README.md`.
- [ ] Déplacer les modèles `Service`, `CareUnit`, `ServiceStatus`, `ShiftType`, `Shift`, `ShiftAssignment`, `PatientLoad`, `Rule`, `SoftConstraintWeight`, ainsi que le moteur `hospiplan/api/planning/` (`feasibility.py`, `generator.py`, `metaheuristic.py`, `scoring.py`).
- [ ] Ajouter `etablissement_id` à chaque table et transformer les FK vers personnel en entiers :
  - `ShiftAssignment.staff_id` ;
  - `Service.manager_staff_id` ;
  - `Shift.required_certification_ids` (`ArrayField` PostgreSQL ou table de liaison avec un entier).
- [ ] **Client HTTP vers personnel** (`clients/personnel.py`) :
  - `requests.Session` avec `urllib3.Retry` : 3 tentatives, backoff exponentiel, uniquement sur erreur réseau, 502, 503 et 504 ;
  - timeouts : connexion 2 s, lecture 5 s (10 s pour `planning-context`) ;
  - en-têtes `Authorization: Bearer <jeton service>`, `X-Etablissement-Id`, `X-Correlation-ID` ;
  - jeton de service mis en cache jusqu'à son expiration ;
  - après échec des retries → `503 UPSTREAM_UNAVAILABLE` ou `504 UPSTREAM_TIMEOUT`, et rien n'est persisté.
- [ ] Adapter le moteur : remplacer les requêtes ORM sur les tables de personnel (dans `FeasibilityContext.build` et `generator._load_aux`) par **un seul** appel `planning-context`, qui construit les mêmes structures en mémoire. Le reste de l'algorithme ne change pas.
- [ ] Affectation manuelle `POST /api/v1/assignments` : appeler `/internal/v1/staff/{id}/eligibility`, puis vérifier localement le chevauchement, le quota hebdomadaire et les certifications. Reprendre les 7 contraintes de l'actuel `ShiftAssignmentViewSet.create`, avec les codes `RULE_*`.
- [ ] **Avant que A2 soit prêt** : une variable `PERSONNEL_MOCK=true` lit `docs/contrats/exemples/personnel-planning-context.json` et `personnel-eligibility.json`.
- [ ] Authentification : réutiliser `libs/hospiplan_auth` fourni par A (A1) : vérification du JWT, rôles, `TenantQuerysetMixin`, format d'erreur, correlation ID.
- [ ] Endpoints : `/health`, `/api/v1/services`, `care-units`, `shift-types`, `shifts`, `assignments`, `plannings/generate` (avec `planning_id` UUID), `stats`, `soft-constraint-weights`.
- [ ] Tests :
  - génération avec le mock ;
  - personnel injoignable → 503 ;
  - une règle dure violée → 400 `RULE_*` ;
  - isolation entre établissements.

## B3 — Service Bus + publication de l'événement

Contrat : `CONTRATS.md` §7 et §8.

- [ ] Créer `sb-hospiplan-<sfx>` (tier **Basic**) et la file `planning-events` : `maxDeliveryCount=5`, dead-letter activée, TTL 1 jour.
- [ ] Créer deux règles d'accès SAS distinctes, au moindre privilège : `send` pour service-planning, `listen` pour la Function.
- [ ] `events/publisher.py` dans service-planning, avec le SDK `azure-servicebus` :
  - message conforme à `planning-generated.event.json` ;
  - propriétés `message_id = event_id`, `correlation_id`, `subject = "planning.generated"`, `content_type = "application/json"` ;
  - publication **après commit** (`transaction.on_commit`) ;
  - `RetryPolicy` du SDK (3 tentatives, exponentiel) ;
  - en cas d'échec final : `event_published: false` dans la réponse + log `ERROR`.
- [ ] Variable `EVENTS_BACKEND` : `servicebus` sur Azure, `log` en local. En mode `log`, l'événement est seulement journalisé.
- [ ] Test : générer un planning, puis voir le message dans Service Bus Explorer depuis le portail.

## B4 — Azure Functions (`fn-planning-events/`)

- [ ] Function App Python 3.12 en modèle de programmation **v2** (`function_app.py`), plan **Consommation**.
- [ ] **`on_planning_generated`** (trigger `service_bus_queue_trigger` sur `planning-events`) :
  1. valider le message (`event_type`, `version`) ; un message invalide lève une exception et part en dead-letter après 5 essais ;
  2. **idempotence** : si le blob `rapports/{etablissement_id}/{date}/{planning_id}.json` existe déjà, ne rien refaire ;
  3. calculer les indicateurs (taux de couverture, nombre de postes non pourvus) et les écrire en **log structuré** dans Application Insights (`custom_dimensions`) ;
  4. écrire le rapport JSON dans Blob Storage (sortie `blob_output`) ;
  5. notifier : récupérer les emails via `/internal/v1/staff?ids=` avec le jeton de service `fn-planning-events`. Pour la démo, la notification est un log ; un vrai email (Azure Communication Services) est un bonus. Une alerte au cadre si `uncovered` n'est pas vide.
- [ ] **Bonus `certifications_expiring`** (trigger Timer `0 0 6 * * *`) : appeler `staff-certifications?expiring_before=J+30` pour chaque établissement, puis notifier.
- [ ] `local.settings.json` reste ignoré par Git (c'est déjà le cas). Fournir un `local.settings.example.json` sans valeurs.
- [ ] Tester en local avec Azure Functions Core Tools (`func start`) et une vraie file Service Bus.
- [ ] Justification FaaS : traitement **déclenché par un événement**, sporadique, sans serveur à gérer, facturé à l'exécution, et qui ne ralentit pas la réponse de la génération.

## B5 — Déploiement Azure + supervision

- [ ] **Plan App Service** `asp-hospiplan-<sfx>` : Linux, **B1**, partagé par les 3 services (identite et personnel sont déployés par A sur ce même plan).
- [ ] **App Service service-planning** :
  - Python 3.12, commande de démarrage `gunicorn planning.wsgi --bind=0.0.0.0 --timeout 60` ;
  - HTTPS Only, TLS 1.2 minimum ;
  - paramètres d'application : `DJANGO_*`, `DB_*` (utilisateur `svc_planning`, `DB_SSLMODE=require`), `PERSONNEL_URL`, `IDENTITE_URL`, `SERVICE_CLIENT_ID`, `SERVICE_CLIENT_SECRET`, `SERVICEBUS_CONNECTION_STRING` (règle `send`), `EVENTS_BACKEND=servicebus`, `JWT_PUBLIC_KEY`, `CORS_ALLOWED_ORIGINS`.
- [ ] **Function App** `func-hospiplan-events-<sfx>` et son compte de stockage. Paramètres : connexion Service Bus (règle `listen`), `PERSONNEL_URL`, identifiants du client de service.
- [ ] **NSG de la VM** : `update-nsg.sh` avec les IP sortantes des 3 App Service et de la Function App. Sur le plan Consommation, les IP sortantes sont nombreuses : soit les lister toutes (`possibleOutboundIpAddresses`), soit faire passer la lecture des emails par service-personnel. Documenter ce choix.
- [ ] **Observabilité** :
  - Log Analytics `log-hospiplan-<sfx>` + Application Insights `appi-hospiplan-<sfx>`, reliés aux 3 App Service et à la Function (variable `APPLICATIONINSIGHTS_CONNECTION_STRING` + `azure-monitor-opentelemetry` dans les services Django) ;
  - paramètres de diagnostic des App Service (logs HTTP et logs console) envoyés vers Log Analytics ;
  - **alertes** Azure Monitor : `/health` en échec (test de disponibilité Application Insights), taux de 5xx supérieur à 5 %, messages en dead-letter supérieurs à 0, CPU de la VM supérieur à 80 %, plus un budget de coût sur le groupe de ressources ;
  - requêtes KQL prêtes pour la démo : suivre un `correlation_id` de bout en bout, et lister les erreurs des dernières 24 h ;
  - procédure de diagnostic, à mettre dans le README technique : symptôme → où regarder → quelle commande lancer.
- [ ] **Tests post-déploiement** : `/health` sur les 3 services, puis le scénario complet de la démo (login → génération → message → Function → blob → logs). Captures d'écran pour le plan B.

## B6 — CI/CD GitHub Actions

Voir `PLAN_TP_SAAS.md` §6 : profils de publication stockés en secrets GitHub, car le compte Azure est partagé.

- [ ] Pour chaque app : activer **SCM Basic Auth Publishing Credentials**, télécharger le profil **hors du dépôt**, puis créer le secret GitHub `AZURE_PUBLISH_PROFILE_PLANNING`, `..._FUNCTION`. A s'occupe de `..._IDENTITE` et `..._PERSONNEL`.
- [ ] `.github/workflows/` :
  - `deploy-planning.yml`, `deploy-identite.yml`, `deploy-personnel.yml` : déclenchés sur `push` vers `main`, filtrés par `paths`, avec l'action `azure/webapps-deploy@v3` ;
  - `deploy-function.yml` : action `Azure/functions-action@v1` ;
  - `ci.yml`, sur chaque PR : `pip install`, `manage.py check`, tests de chaque service et `npm run build` du frontend. C'est ce qui donne du sens à la protection de `main`.
- [ ] Une fois `ci.yml` en place, l'exiger comme check obligatoire dans la règle de protection de `main`.
- [ ] Captures d'écran : onglet Actions en vert, et l'historique de déploiement dans le portail.

## B7 — Livrables (dossier `docs/livrables/`)

| Livrable | Contenu attendu |
|---|---|
| 5. Diagramme Cloud | ressources Azure (RG, VNet/NSG, VM, plan App Service + 3 apps, Function App, Service Bus, Storage, App Insights / Log Analytics), flux HTTPS / SQL / message, zones de confiance. Format draw.io ou Mermaid exporté en PNG |
| 9. Ressources déployées | liste avec nom, SKU et région, et captures d'écran du portail |
| 10. Démo de la communication | scénario chronométré, requêtes KQL, vidéo de secours (plan B) |
| 11. Estimation des coûts | tableau mensuel **démo** et **production** : VM, disque, plan App Service, Functions, Service Bus, stockage, Log Analytics et App Insights, réseau sortant. Prix relevés avec l'[Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/), région France Central, et **date du relevé**. Section « −30 % » : arrêt automatique de la VM, instances réservées ou plan d'économies, échantillonnage d'App Insights, rétention des logs réduite, consolidation sur un seul plan App Service, mise à l'échelle automatique |
| 12. Analyse de sécurité (partie infra) | NSG et ufw, SSH par clé, SSL PostgreSQL, un utilisateur PostgreSQL par service, secrets dans les paramètres d'application et les secrets GitHub, HTTPS Only. Risques : compte Azure partagé (profils de publication à réinitialiser après la soutenance), VM avec IP publique. En production : Private Endpoint, Key Vault, Managed Identity |
| 13. README technique | architecture, lancement en local (`docker-compose`), variables d'environnement par service, déploiement, CI/CD, supervision et procédure de diagnostic |

Préparer aussi les réponses aux questions de soutenance 3, 4, 5, 7, 9 et 10 (voir `PLAN_TP_SAAS.md`).

---

## Points de synchronisation avec A

| Quand | B fournit à A | A fournit à B |
|---|---|---|
| Fin B1 | IP de la VM + identifiants `svc_identite` / `svc_personnel` (canal privé) | — |
| Fin A1 | — | `libs/hospiplan_auth`, clé publique JWT de dev, identifiants des clients `service-planning` et `fn-planning-events` |
| Fin A2 | — | `planning-context` et `eligibility` opérationnels → désactiver `PERSONNEL_MOCK` |
| B5 | plan App Service partagé + chaîne de connexion App Insights | IP sortantes de identite et personnel |
| B6 | workflows prêts | secrets `AZURE_PUBLISH_PROFILE_IDENTITE` / `_PERSONNEL` |
| Après la soutenance | réinitialiser les profils de publication, supprimer le groupe de ressources | — |
