# hospiplan_auth — bibliothèque commune des microservices

Code partagé par service-identite, service-personnel et service-planning, conforme à `docs/contrats/CONTRATS.md` §2-3.

| Module | Rôle |
|---|---|
| `authentication.JWTClaimsAuthentication` | vérifie le JWT RS256 avec la clé publique, sans requête SQL. `request.user` est un `ClaimsUser` (`id`, `role`, `etablissement_id`, `staff_id`, `is_service`, `scope`) |
| `permissions` | `IsUserToken`, `HasRole(...)`, `MinRole(role, read_role=...)`, `IsServiceToken(*scopes)` |
| `tenant.TenantQuerysetMixin` | filtre les querysets par `etablissement_id` (pris dans le jeton) et l'impose à la création |
| `errors.exception_handler` / `ApiError` | format d'erreur commun `{"error": {code, message, details, correlation_id}}` |
| `correlation` | middleware `X-Correlation-ID`, filtre de logs, journal des accès |
| `pagination.StandardPagination` | `?page=&page_size=` (max 200) |
| `health.health` | vue `GET /health` |
| `db` | un schéma PostgreSQL par service (`search_path`, création automatique avant les migrations) |
| `conf.load_pem` | lit une clé PEM depuis une variable d'environnement ou un fichier |

Installation en local : `pip install -e libs/hospiplan_auth`.
Déploiement Azure : le workflow copie `libs/hospiplan_auth/hospiplan_auth/` dans le dossier du service avant le déploiement.
