# Conventions de travail — HospiPlan SaaS

Équipe : **A** (Produit & Applicatif) et **B** (Cloud & Plateforme). Voir `PLAN_TP_SAAS.md` pour la répartition et `docs/contrats/CONTRATS.md` pour les interfaces figées.

## Branches

- `main` est **protégée** : aucun push direct, merge uniquement par Pull Request approuvée par l'autre membre.
- Une branche par tâche, créée depuis un `main` à jour :

  | Préfixe | Usage | Exemple |
  |---|---|---|
  | `feat/` | nouvelle fonctionnalité | `feat/identite-login-jwt` |
  | `fix/` | correction | `fix/planning-retry-personnel` |
  | `infra/` | Azure, VM, workflows | `infra/vm-postgresql` |
  | `docs/` | livrables, README | `docs/estimation-couts` |
  | `chore/` | nettoyage, dépendances | `chore/requirements` |

- Branches courtes (≤ 2 jours) : on rebase/merge `main` régulièrement pour éviter les gros conflits.

```bash
git switch main && git pull
git switch -c feat/identite-login-jwt
# ... travail ...
git push -u origin feat/identite-login-jwt   # puis ouvrir la PR sur GitHub
```

## Commits

Format : `<type>(<portée>): <description à l'impératif>` — types `feat`, `fix`, `infra`, `docs`, `chore`, `test` ; portées `identite`, `personnel`, `planning`, `function`, `frontend`, `infra`, `docs`.

```
feat(identite): émettre un JWT avec etablissement_id et role
infra(vm): restreindre le NSG PostgreSQL aux IP sortantes App Service
```

## Pull Requests

- **Chaque PR est relue par l'autre membre** (A relit B, B relit A) avant le merge.
- Une PR = une tâche ; titre au format des commits.
- Remplir le modèle de PR (`.github/pull_request_template.md`).
- Toute modification de `docs/contrats/` doit être approuvée par **les deux** et annoncée à l'autre avant d'écrire le code.
- Merge en **squash** pour garder un historique lisible.

## Secrets — règle absolue

- **Aucun mot de passe, clé, chaîne de connexion ou profil de publication dans Git.** Ils vont dans `.env` (local, ignoré par Git), dans les **Paramètres d'application** Azure et dans les **secrets GitHub Actions**.
- `.env.example` liste les variables **sans** valeurs réelles.
- Un secret commité par erreur = **le régénérer** (le retirer du code ne suffit pas : il reste dans l'historique).

## Organisation du dépôt (cible)

```
service-identite/     # A — Django, JWT, établissements
service-personnel/    # A — Django, soignants
service-planning/     # B — Django, postes, affectations, moteur
fn-planning-events/   # B — Azure Functions (Python)
frontend/             # A — React
infra/                # B — scripts / Bicep / docs VM
docs/                 # contrats, livrables
.github/workflows/    # B — CI/CD
```

Chaque service a son `README.md`, son `requirements.txt`, son `Dockerfile` et son `.env.example`.
