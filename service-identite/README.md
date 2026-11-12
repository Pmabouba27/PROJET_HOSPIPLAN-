# service-identite

Microservice des **comptes, établissements clients (tenants), rôles et jetons JWT** de HospiPlan SaaS.
Contrat d'interface : `docs/contrats/CONTRATS.md` §3-4 · Responsable : **A**.

| | |
|---|---|
| Port local | 8001 |
| Schéma PostgreSQL | `identite` (utilisateur `svc_identite` sur la VM) |
| Hébergement | Azure App Service (PaaS), Linux, Python 3.12 |
| Démarrage | `gunicorn identite.wsgi --bind=0.0.0.0` |

## Responsabilités

- **Établissements** (`Etablissement`) : nom, SIRET, plan (`ESSAI` / `STANDARD` / `PREMIUM`), statut d'abonnement. Un établissement suspendu ou résilié ne peut plus se connecter.
- **Utilisateurs** (`Utilisateur`) :
  - connexion par email ;
  - rôle `SUPERADMIN` / `ADMIN` / `CADRE` / `SOIGNANT` ;
  - `staff_id` : lien vers la fiche soignant du service personnel. Ce n'est pas une clé étrangère, et il est obligatoire pour un SOIGNANT.
- **Jetons utilisateur** :
  - signés en RS256 avec la clé **privée**, que seul ce service détient ;
  - vérifiés par les autres services avec la clé **publique** ;
  - access token de 15 min, refresh token de 7 jours ;
  - rotation et révocation (liste noire) ;
  - les claims sont relus en base à chaque refresh.
- **Jetons de service** (`client_credentials`) pour les appels entre services : `aud = hospiplan-internal`, avec des scopes.

## Endpoints

| Méthode | Chemin | Accès |
|---|---|---|
| GET | `/health` | public |
| POST | `/api/v1/auth/login` | public, 5 essais / min / IP |
| POST | `/api/v1/auth/refresh` | public (refresh token) |
| POST | `/api/v1/auth/logout` | connecté |
| GET | `/api/v1/auth/me` | connecté |
| GET | `/api/v1/auth/jwks` | public |
| GET, POST | `/api/v1/etablissements` | lecture : SUPERADMIN et ADMIN (le sien) · écriture : SUPERADMIN |
| GET, PATCH, DELETE | `/api/v1/etablissements/{id}` | idem (`DELETE` = résiliation) |
| GET, POST | `/api/v1/users` | ADMIN (son établissement), SUPERADMIN (tous, filtre `?etablissement_id=`) |
| GET, PATCH, DELETE | `/api/v1/users/{id}` | idem (`DELETE` = désactivation + révocation des jetons) |
| POST | `/internal/v1/auth/service-token` | identifiants de service |

Toutes les erreurs suivent le format commun : `{"error": {"code", "message", "details", "correlation_id"}}`.

## Lancer en local

```bash
# depuis la racine du dépôt
myenv\Scripts\activate
pip install -r service-identite/requirements.txt
pip install -e libs/hospiplan_auth

cd service-identite
cp .env.example .env              # renseigner DB_*, DJANGO_SECRET_KEY, SERVICE_CLIENTS, SEED_PASSWORD
python manage.py generate_jwt_keys
python manage.py migrate          # crée le schéma « identite » s'il manque
python manage.py seed_identite    # CHU Démo + superadmin/admin/cadre/soignant@hospiplan.demo
python manage.py runserver 8001
python manage.py test comptes     # 38 tests
```

Exemple :

```bash
curl -X POST http://localhost:8001/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email":"cadre@hospiplan.demo","password":"<SEED_PASSWORD>"}'
```

## Utilisation par les autres services

1. Installer la bibliothèque commune : `pip install -e libs/hospiplan_auth`.
2. Dans `settings.py` :

   ```python
   from hospiplan_auth.conf import load_pem
   HOSPIPLAN_AUTH = {"PUBLIC_KEY": load_pem("JWT_PUBLIC_KEY", BASE_DIR), "SERVICE_NAME": "service-personnel"}
   REST_FRAMEWORK = {
       "DEFAULT_AUTHENTICATION_CLASSES": ["hospiplan_auth.authentication.JWTClaimsAuthentication"],
       "DEFAULT_PERMISSION_CLASSES": ["hospiplan_auth.permissions.IsUserToken"],
       "EXCEPTION_HANDLER": "hospiplan_auth.errors.exception_handler",
       "DEFAULT_PAGINATION_CLASS": "hospiplan_auth.pagination.StandardPagination",
   }
   MIDDLEWARE = ["hospiplan_auth.correlation.CorrelationIdMiddleware", ..., "hospiplan_auth.correlation.AccessLogMiddleware"]
   ```

3. Dans les vues :
   - `TenantQuerysetMixin` filtre par l'`etablissement_id` du jeton ;
   - `MinRole("CADRE", read_role="SOIGNANT")` et `HasRole(...)` contrôlent les rôles ;
   - `IsServiceToken("personnel:read")` protège les endpoints `/internal/v1/` ;
   - `ApiError(400, "RULE_NO_OVERLAP", "...")` produit une erreur métier.
4. Copier **uniquement** `keys/jwt_public.pem` (variable `JWT_PUBLIC_KEY_FILE`). La clé privée ne quitte jamais service-identite.

Pour obtenir un jeton de service (service-planning, Function) :

```bash
POST /internal/v1/auth/service-token  {"client_id": "service-planning", "client_secret": "<secret de SERVICE_CLIENTS>"}
→ {"access": "<jwt>", "token_type": "Bearer", "expires_in": 900}
```

Le jeton se réutilise jusqu'à son expiration. Chaque appel envoie `Authorization: Bearer <jwt>` et `X-Etablissement-Id`.

## Sécurité

- Mots de passe hachés en PBKDF2 (Django par défaut), longueur minimale de 10 caractères, mots de passe courants refusés.
- Même réponse pour un email inconnu et pour un mauvais mot de passe : on ne peut pas deviner quels comptes existent.
- Connexions, échecs, désactivations et refus de jeton de service sont journalisés (logger `hospiplan.security`). Les accès sont journalisés avec le correlation ID (logger `hospiplan.access`).
- Un changement de rôle ou de mot de passe, ou une désactivation, révoque tous les refresh tokens de l'utilisateur.
- Limites connues :
  - la limitation des tentatives de login utilise un cache local, donc propre à chaque instance (en production : Redis) ;
  - un access token reste valide au plus 15 min après une désactivation.
