# HospiPlan SaaS — Rapport d'avancement des étapes

> Dernière mise à jour : 12/11/2026
> Référence : `PLAN_TP_SAAS.md` (plan général) · `docs/contrats/CONTRATS.md` (interfaces) · `CONTRIBUTING.md` (règles Git)

## Synthèse

| Étape | Contenu | Statut | Branche | Commit |
|---|---|---|---|---|
| 0 | Contrats d'interface et conventions Git | ✅ fait — en attente de relecture | `phase0/contrats-et-conventions` | `db9a49a` |
| 1 | Assainissement (secrets, config, dépendances) | ✅ code fait — ⚠️ rotation du mot de passe PostgreSQL à faire | `chore/assainissement-secrets` | `0af0627` |
| 2 | VM PostgreSQL sur Azure (IaaS) | 🟡 scripts prêts, **VM non créée** (connexion Azure requise) | `infra/vm-postgresql` | `70166c0` |
| 3 | Authentification JWT + établissements | ⏳ à faire (A) | — | — |
| 4 | Découpage en 3 microservices | ⏳ à faire (A + B) | — | — |
| 5 | Azure Function + Service Bus | ⏳ à faire (B) | — | — |
| 6 | CI/CD, supervision, FinOps, livrables | ⏳ à faire | — | — |

Les 3 branches sont **empilées** : chacune part de la précédente. Ordre de merge dans `main` : **phase0 → assainissement → vm-postgresql**. Si on merge directement la dernière, elle apporte les deux autres.

---

## Étape 0 — Contrats et conventions

**Objectif** : figer les interfaces pour que A et B puissent coder en parallèle sans se bloquer.

**Réalisé**
- `docs/contrats/CONTRATS.md` :
  - **Découpage validé** : chaque modèle Django appartient à un seul service.
    - *identite* : établissements, abonnements, utilisateurs.
    - *personnel* : soignants, contrats, certifications, absences, préférences, rattachements, prêts.
    - *planning* : services, unités, types de garde, postes, affectations, poids des contraintes.
  - **Références entre services** : les clés étrangères deviennent des identifiants (`staff_id`, `target_service_id`…). Toutes les tables métier reçoivent une colonne `etablissement_id`.
  - **JWT** : RS256, contient `etablissement_id`, `role` (SUPERADMIN / ADMIN / CADRE / SOIGNANT) et `staff_id`. Le document inclut la matrice des droits par rôle.
  - **Endpoints REST** des 3 services : `/api/v1/` pour le public, `/internal/v1/` pour les appels entre services, `/health` pour la supervision.
  - **API clé entre A et B** : `GET /internal/v1/planning-context`, un seul appel groupé qui renvoie toutes les données lues aujourd'hui par `feasibility.py` et `generator.py`.
  - **Événement `planning.generated`** : file Service Bus `planning-events`, sans données personnelles.
  - **Règles communes** : format d'erreur unique (réutilise les codes `RULE_*` existants), `X-Correlation-ID`, timeouts, retry avec backoff exponentiel, dead-letter queue.
- `docs/contrats/exemples/` : 5 exemples JSON validés, qui servent de mocks.
- `CONTRIBUTING.md` : nommage des branches, format des commits, relecture croisée obligatoire, règle sur les secrets.
- `.github/pull_request_template.md` : checklist de PR.
- `.gitignore` à la racine, qui n'existait pas : il couvre `.env`, `*.PublishSettings`, les venv et `node_modules`.
- Retrait du suivi Git de 34 fichiers `__pycache__`.

**Décisions à confirmer par A et B**
- Dans la réponse de génération, `shift`/`staff` deviennent `shift_id`/`staff_id` : le frontend doit être adapté.
- `Service` et `CareUnit` appartiennent à service-planning.
- Appels entre services : jetons de service émis par identite. Si le temps manque, une clé partagée `X-Service-Key` est possible (à signaler comme faiblesse).

---

## Étape 1 — Assainissement

**Problèmes de départ** : `SECRET_KEY` et mot de passe PostgreSQL écrits en dur dans `settings.py`, `docker-compose.yml` et le README ; `DEBUG = True` ; `ALLOWED_HOSTS` vide ; `requirements.txt` en UTF-16 avec une seule dépendance (inutilisée) ; Dockerfile en Python 3.11, incompatible avec Django 6.

**Réalisé**
- `hospiplan/hospiplan/settings.py` :
  - toute la configuration vient des variables d'environnement, chargées via `.env` en local ;
  - erreur explicite si `DJANGO_SECRET_KEY`, `DB_USER` ou `DB_PASSWORD` manquent ;
  - `DEBUG` vaut `false` par défaut ;
  - `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` et `CSRF_TRUSTED_ORIGINS` sont configurables ;
  - `DB_SSLMODE` est ajouté (vaudra `require` vers la VM) ;
  - en production : HTTPS forcé derrière le proxy App Service, cookies sécurisés, HSTS ;
  - `STATIC_ROOT` est défini.
- `.env.example` (versionné, sans valeurs) et `.env` local (ignoré par Git) avec une **nouvelle `SECRET_KEY` générée**.
- `hospiplan/requirements.txt` régénéré en UTF-8 avec des versions figées : Django 6.0.3, DRF 3.17.1, django-cors-headers 4.9.0, psycopg2-binary 2.9.11, python-dotenv 1.1.1, gunicorn 23.0.0. `confluent-kafka` est retiré car il n'est importé nulle part.
- `docker-compose.yml` : identifiants lus via `env_file: .env`.
- `hospiplan/Dockerfile` : Python 3.12, et `gunicorn` comme commande de production.
- `README.md` : mot de passe retiré, documentation des variables.

**Vérifications**
| Test | Résultat |
|---|---|
| `manage.py check` (dev) | ✅ aucun problème |
| `manage.py check --deploy` avec `DJANGO_DEBUG=false` | ✅ seuls 2 avertissements HSTS (sous-domaines / preload) restent, normaux pour `*.azurewebsites.net` |
| Démarrage sans `DJANGO_SECRET_KEY` | ✅ refusé avec un message clair |
| Connexion à la base | ⚠️ non testée : le PostgreSQL local n'était pas démarré |

**Reste à faire (B)**
- **Rotation** : l'ancien mot de passe `postgres` et l'ancienne `SECRET_KEY` restent visibles dans l'historique Git, ils sont donc compromis.
  - La `SECRET_KEY` est déjà remplacée dans `.env`.
  - Mot de passe PostgreSQL local : `ALTER USER postgres WITH PASSWORD '<nouveau>';`, puis mettre à jour `DB_PASSWORD` et `POSTGRES_PASSWORD` dans `.env`. Le `.env` local contient encore l'ancien mot de passe pour que l'application continue de fonctionner d'ici là.
  - Sur Azure, des mots de passe neufs sont générés par `setup-postgres.sh`.
- Chaque membre doit copier `.env.example` en `.env` sur son poste, puis lancer `pip install -r hospiplan/requirements.txt`.

---

## Étape 2 — VM PostgreSQL (IaaS)

**Réalisé** (`infra/vm-postgresql/`)
- `deploy-vm.sh` crée toute l'infrastructure :
  - groupe de ressources, VNet et IP publique statique ;
  - **NSG** : ports 22 et 5432 ouverts uniquement depuis l'IP de l'administrateur et les IP sortantes des App Service, tout le reste refusé ;
  - VM Ubuntu 24.04 `Standard_B1s`, accès SSH par clé uniquement ;
  - disque StandardSSD de 30 Gio ;
  - arrêt automatique à 19:00 UTC, pour le FinOps ;
  - tags `projet` / `environnement` / `proprietaire`, utiles sur un compte partagé.
- `cloud-init.yaml` : installe PostgreSQL, `ufw`, `fail2ban` et les mises à jour automatiques ; interdit le login root et l'authentification SSH par mot de passe ; programme une sauvegarde `pg_dump` quotidienne conservée 7 jours. Ce fichier ne contient aucun secret.
- `setup-postgres.sh` configure la base :
  - SSL obligatoire à distance et `scram-sha-256` ;
  - connexions et déconnexions journalisées ;
  - base `hospiplan` avec **un schéma et un utilisateur par microservice** (`svc_identite`, `svc_personnel`, `svc_planning`), plus `hospiplan_app` pour le monolithe pendant la transition ;
  - mots de passe générés **sur la VM** et affichés une seule fois. Le script peut être relancé sans danger.
- `update-nsg.sh` : ajoute les IP sortantes des App Service à la règle 5432.
- `README.md` : justification des choix (OS, taille, ports, accès, sécurité, coût, raison du choix IaaS) réutilisable dans le livrable, tests post-déploiement et commande de suppression.

**Vérifications** : syntaxe des 3 scripts validée avec `bash -n`. La VM n'a pas été créée : Azure CLI est installé mais aucun compte n'est connecté, et le compte de la classe est partagé.

**Reste à faire (B)**
```bash
az login
cd infra/vm-postgresql
PREFIX=hospiplan SUFFIX=<initiales> ./deploy-vm.sh
ssh hospiadmin@<IP> 'cloud-init status --wait'
ssh hospiadmin@<IP> 'sudo bash -s' < setup-postgres.sh
```
Ensuite, renseigner dans `.env` : `DB_HOST=<IP>`, `DB_USER=hospiplan_app`, `DB_PASSWORD=...`, `DB_SSLMODE=require`. Lancer `python manage.py migrate`, puis la commande de seed. Faire des captures d'écran du portail (VM, NSG) pour le livrable.

---

## Actions manuelles restantes (ne peuvent pas être faites depuis ici)

| # | Action | Qui |
|---|---|---|
| 1 | Ouvrir les 3 PR sur GitHub (liens ci-dessous), les relire, puis merger dans l'ordre | A + B |
| 2 | Protéger `main` : Settings → Branches → règle `main` → PR obligatoire, 1 approbation | propriétaire du dépôt |
| 3 | Relire et approuver `docs/contrats/CONTRATS.md`, en tranchant les 3 décisions de l'étape 0 | A + B |
| 4 | Changer le mot de passe PostgreSQL local et mettre à jour `.env` | chacun |
| 5 | `az login`, puis créer la VM avec les scripts | B |

Liens pour créer les PR :
- https://github.com/Pmabouba27/PROJET_HOSPIPLAN-/pull/new/phase0/contrats-et-conventions
- https://github.com/Pmabouba27/PROJET_HOSPIPLAN-/pull/new/chore/assainissement-secrets (base : `phase0/contrats-et-conventions`, ou `main` après le premier merge)
- https://github.com/Pmabouba27/PROJET_HOSPIPLAN-/pull/new/infra/vm-postgresql (base : `chore/assainissement-secrets`, ou `main` après les merges)

## Prochaines étapes

- **A — étape 3** : authentification JWT et modèle `Etablissement`, en suivant `CONTRATS.md` §3–4. Brancher ensuite le login dans le frontend.
- **B — étape 4 côté planning** : créer `service-planning/` à partir de `hospiplan/api/planning/` et le faire tourner contre le mock `docs/contrats/exemples/personnel-planning-context.json`.
- **B — étape 5** : Service Bus et `fn-planning-events`, sur la base de `docs/contrats/exemples/planning-generated.event.json`.
