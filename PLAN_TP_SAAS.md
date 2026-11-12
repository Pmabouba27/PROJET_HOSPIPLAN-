# HospiPlan SaaS — Plan de travail « Cloud Startup Challenge »

> Objectif : transformer HospiPlan en **solution SaaS** basée sur une **architecture microservices**, déployée sur **Microsoft Azure** (IaaS + PaaS + FaaS).
> Équipe : 2 personnes — **A (Produit & Applicatif)** et **B (Cloud & Plateforme)**.

---

## 1. Rappel du sujet (TP Saas.pdf)

### Exigences obligatoires
- **7 fonctionnalités minimales** : authentification, gestion des utilisateurs, fonctionnalité métier principale, tableau de bord, gestion des données, API backend, traitement automatique/événementiel.
- **≥ 3 microservices** : responsabilité métier claire, déploiement indépendant, API exposée, configuration distincte, communication par API ou événement. Une base (ou un schéma) par service encouragée.
- **IaaS** : au moins une VM Azure — justifier OS, taille, ports ouverts, stratégie d'accès, sécurisation, coût, raison du choix IaaS.
- **PaaS** : au moins un microservice sur Azure App Service — justifier le choix, le plan, la configuration, les variables d'environnement, la connexion aux autres services, les avantages vs VM.
- **FaaS** : au moins une Azure Function déclenchée par un événement concret — trigger, données d'entrée, traitement, résultat, raison du serverless.
- **Communication** : JSON, authentification inter-services, gestion des erreurs, mécanisme de retry.
- **Sécurité** : HTTPS, authentification, autorisation par rôles, protection des secrets, ports limités sur la VM, protection de la BDD, journalisation des accès, **aucun mot de passe dans GitHub**.
- **Déploiement Azure** : région, groupe de ressources, nommage, VM, App Service, Functions, paramètres d'environnement, tests post-déploiement.
- **GitHub & CI/CD** : branche `main` protégée, un dossier par microservice, README, `.gitignore`, historique de commits clair, ≥ 1 workflow GitHub Actions de déploiement.
- **FinOps** : coût mensuel (VM, stockage, App Service, Functions, BDD, réseau, logs) pour une architecture de démo et une de production + « comment réduire le coût de 30 % ? ».
- **Observabilité** : logs applicatifs, suivi des erreurs, indicateurs de disponibilité et de performance, alertes, procédure de diagnostic (Azure Monitor, Application Insights, Log Analytics).

### 14 livrables
| Concevoir | Réaliser | Justifier |
|---|---|---|
| 1. Pitch de la startup | 6. Code source | 11. Estimation des coûts |
| 2. Expression du besoin | 7. Dépôt GitHub | 12. Analyse de sécurité |
| 3. Backlog fonctionnel | 8. Prototype fonctionnel | 13. README technique |
| 4. Architecture microservices | 9. Ressources déployées sur Azure | 14. Présentation finale |
| 5. Diagramme Cloud | 10. Démo de la communication entre services | |

### Barème (/100)
| Critère | Pts | Critère | Pts |
|---|---|---|---|
| Idée et valeur du SaaS | 10 | Déploiement Azure | 10 |
| Analyse du besoin | 10 | Sécurité | 5 |
| Architecture microservices | 15 | Tarification et FinOps | 5 |
| Utilisation IaaS | 10 | GitHub et CI/CD | 5 |
| Utilisation PaaS | 10 | Démonstration | 5 |
| Utilisation FaaS | 10 | Présentation et justification | 5 |

### Démonstration finale attendue
Connexion → scénario métier principal → appel d'un microservice → lecture/écriture en BDD → exécution de l'Azure Function → ressources Azure → logs/traces. **Plan B** : captures d'écran / vidéo.

### Questions de soutenance à préparer
1. Pourquoi votre produit est-il un SaaS ?
2. Pourquoi ces microservices ?
3. Pourquoi une VM ?
4. Pourquoi App Service ?
5. Pourquoi Azure Functions ?
6. Principale faiblesse de l'architecture ?
7. Combien coûte la solution ?
8. Comment passer de 100 à 100 000 utilisateurs ?
9. Pourriez-vous supprimer entièrement l'IaaS ?
10. Que changeriez-vous pour une vraie mise en production ?

---

## 2. État actuel d'HospiPlan vs le TP

### Déjà en place
| Exigence | État |
|---|---|
| Fonctionnalité métier principale | ✅ Génération de planning (glouton + recherche tabou, `hospiplan/api/planning/`) |
| Tableau de bord | ✅ `StatsView` + `Statistiques.js` |
| Gestion des données | ✅ ~20 modèles Django, PostgreSQL |
| API backend | ✅ Django REST Framework (~15 endpoints) |
| Interface web | ✅ React |
| Conteneurisation | ✅ `docker-compose.yml` + Dockerfiles |
| Dépôt GitHub | ✅ |
| Documentation | ✅ README, CONCEPT.md |

### Manques / problèmes
| Exigence | Problème |
|---|---|
| ≥ 3 microservices | Monolithe : une seule app Django `api` |
| Authentification & rôles | Aucune — API ouverte |
| Multi-clients (SaaS) | Conçu pour un seul hôpital ; pas de notion d'établissement client ni d'abonnement |
| IaaS / PaaS / FaaS | Rien déployé, pas d'Azure Function |
| Asynchrone / événements | Aucun (`confluent-kafka` listé mais inutilisé) |
| CI/CD | Pas de `.github/workflows/` |
| Sécurité | ⚠️ `SECRET_KEY` et mot de passe PostgreSQL commités (`settings.py`, README, `docker-compose.yml`) ; `DEBUG = True`. Ils restent dans l'historique git → **à régénérer**, pas seulement à retirer |
| `requirements.txt` | Cassé (encodage UTF-16, ne contient que `confluent-kafka`) |

---

## 3. Architecture cible

### Découpage métier
| Service | Responsabilité | Données | Hébergement |
|---|---|---|---|
| **service-identite** | Comptes, établissements clients (tenants), rôles, émission JWT | Users, Etablissement, Abonnement, Rôles | App Service (PaaS) |
| **service-personnel** | Soignants, contrats, certifications, absences, préférences | Staff, Contract, Certification, Absence, Preference… | App Service (PaaS) |
| **service-planning** | Postes, types de garde, affectations, moteur de génération | Shift, ShiftType, ShiftAssignment, CareUnit, Rules… | App Service (PaaS) |
| **PostgreSQL** | Un schéma par service | — | **VM Azure (IaaS)** |
| **fn-planning-events** | Statistiques, rapport, notification des soignants | Message « planning généré » | **Azure Functions (FaaS)** |

### Dépendances
- Frontend → service-identite (login) → JWT porté sur tous les appels.
- service-planning → service-personnel (REST, synchrone) : disponibilités, absences, certifications.
- service-planning → Azure Service Bus (asynchrone) : événement `planning.generated`.
- Service Bus → Azure Function (trigger) → rapport / notification / stats.
- Bonus : Function à trigger planifié (Timer) pour signaler les certifications expirant bientôt.

### Flux de démo
```
Utilisateur ─HTTPS→ Frontend React ─JWT→ service-planning ─REST→ service-personnel
                                              │                       │
                                              └──SQL──→ PostgreSQL (VM) ←──SQL┘
                                              │
                                              └─message→ Service Bus ─trigger→ Azure Function → notification/rapport
                                                                                     │
                                                                          Application Insights (logs)
```

---

## 4. Ordre de réalisation

1. **Assainissement** (~½ j) : secrets en variables d'environnement, `.env.example`, `.gitignore`, `requirements.txt` régénéré, `DEBUG`/`ALLOWED_HOSTS` configurables, rotation des secrets.
2. **VM PostgreSQL sur Azure** (~½ j) : Ubuntu B1s/B2s, port 5432 restreint, SSH par clé uniquement.
3. **Authentification JWT + établissements** (~1 j) — à faire **avant** le découpage pour ne pas la coder trois fois.
4. **Découpage en 3 services** (~2-3 j) : un dossier par service, un schéma par service.
5. **Azure Function + Service Bus** (~1 j).
6. **CI/CD, supervision, FinOps, documents** (~1-2 j).

---

## 5. Répartition du travail

### Phase 0 — ensemble (½ journée)
- [x] Valider le découpage (section 3) → propriété de chaque modèle : `docs/contrats/CONTRATS.md` §1.
- [x] **Figer les contrats** : endpoints REST de chaque service (OpenAPI ou tableau), format JSON du message `planning.generated`, contenu du JWT (`etablissement_id`, `role`) → `docs/contrats/CONTRATS.md` + exemples JSON dans `docs/contrats/exemples/`.
- [x] Conventions Git : une branche par tâche, **chaque PR relue par l'autre** → `CONTRIBUTING.md`, `.github/pull_request_template.md`, `.gitignore`.
- [ ] Activer la protection de `main` sur GitHub (Settings → Branches → règle `main` : PR obligatoire, 1 approbation) — à faire par le propriétaire du dépôt.
- [ ] Relecture et approbation de `CONTRATS.md` par A **et** B.

Une fois les contrats figés, chacun avance en parallèle (en local via `docker-compose` en attendant la VM).

### Tâches
| Domaine | **A — Produit & Applicatif** | **B — Cloud & Plateforme** |
|---|---|---|
| Assainissement | [ ] `settings.py` en variables d'env, `.env.example`, `requirements.txt` | [ ] Rotation des secrets, nettoyage README / `docker-compose.yml` |
| Code | [ ] **service-identite** (JWT, établissements, rôles) | [ ] **service-planning** (extraction de `planning/`, affectations, postes) |
| | [ ] **service-personnel** (soignants, contrats, absences, préférences) | [ ] **Azure Function** + Service Bus (stats / rapport / notification) |
| | [ ] **Frontend** : écran de login, rôles, appels vers les nouveaux services | [ ] Publication de l'événement dans service-planning (avec retry) |
| Azure | [ ] Déploiement de ses 2 services sur App Service | [ ] **VM PostgreSQL** (NSG, sauvegardes, schémas) |
| | | [ ] Déploiement service-planning, Function App, Application Insights, alertes |
| | | [ ] **Workflow GitHub Actions** |
| Livrables | [ ] Pitch, expression du besoin, backlog fonctionnel | [ ] Diagramme Cloud, estimation des coûts (démo / prod / −30 %) |
| | [ ] Analyse de sécurité applicative (auth, rôles, validation) | [ ] Sécurité infra (ports, secrets, HTTPS), README technique |

### Équilibre sur le barème
- **A : 40 pts** — Idée (10), Besoin (10), Architecture microservices (15), Sécurité (5)
- **B : 40 pts** — IaaS (10), FaaS (10), Déploiement Azure (10), FinOps (5), CI/CD (5)
- **Commun : 20 pts** — PaaS (10, chacun déploie ses services), Démonstration (5), Présentation (5)

### Points de synchronisation (risques de blocage)
1. **La VM (B) conditionne les tests Azure de A** → B commence par la VM.
2. **Les endpoints de service-personnel (A) sont consommés par service-planning (B)** → B travaille sur un mock conforme au contrat en attendant.

### Avant la soutenance
- [ ] Session croisée d'1 h : A explique le découpage et la sécurité applicative, B explique la VM, la Function et les coûts. Les deux doivent pouvoir répondre aux 10 questions.
- [ ] Préparer le plan B de la démo (captures / vidéo).

---

## 6. Dernière étape — Déploiement CI/CD via profil de publication (compte Azure partagé)

> Le compte Azure étant partagé avec la classe, on ne connecte **pas** Azure à GitHub (Deployment Center). On utilise le **profil de publication** de chaque application, stocké comme **secret GitHub**, et un workflow GitHub Actions pousse le code vers Azure.
> ⚠️ Le fichier `.PublishSettings` contient un identifiant/mot de passe (`userName` / `userPWD`) : il ne doit **jamais** être commité dans le dépôt.

### 6.1 Récupérer les profils (portail Azure — responsable : B)
Pour **chaque** application : `service-identite`, `service-personnel`, `service-planning` (App Service) et la Function App `fn-planning-events`.
- [ ] App Service → **Configuration** → **Paramètres généraux** → activer **SCM Basic Auth Publishing Credentials** → Enregistrer (désactivé par défaut, sinon le profil ne fonctionne pas).
- [ ] **Vue d'ensemble** → **Télécharger le profil de publication** → enregistrer le fichier **hors du dépôt** (ex. `~/azure-profiles/`).
- La VM PostgreSQL (IaaS) n'est pas concernée.

### 6.2 Créer les secrets GitHub (admin du dépôt)
GitHub → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**, en collant le **contenu complet** du fichier :

| Secret | Application |
|---|---|
| `AZURE_PUBLISH_PROFILE_IDENTITE` | App Service service-identite |
| `AZURE_PUBLISH_PROFILE_PERSONNEL` | App Service service-personnel |
| `AZURE_PUBLISH_PROFILE_PLANNING` | App Service service-planning |
| `AZURE_PUBLISH_PROFILE_FUNCTION` | Function App fn-planning-events |

### 6.3 Workflows GitHub Actions (un par service, `.github/workflows/`)
Déclenchés sur `push` vers `main` uniquement si le dossier du service change :

```yaml
name: Deploy service-planning
on:
  push:
    branches: [main]
    paths: ['service-planning/**']
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -r service-planning/requirements.txt
      - uses: azure/webapps-deploy@v3
        with:
          app-name: <nom-app-service-planning>
          publish-profile: ${{ secrets.AZURE_PUBLISH_PROFILE_PLANNING }}
          package: service-planning
```
- [ ] `deploy-identite.yml`, `deploy-personnel.yml`, `deploy-planning.yml` (même modèle, `azure/webapps-deploy@v3`).
- [ ] `deploy-function.yml` avec `Azure/functions-action@v1` et `publish-profile: ${{ secrets.AZURE_PUBLISH_PROFILE_FUNCTION }}`.
- [ ] Commande de démarrage App Service (Django) : `gunicorn <projet>.wsgi --bind=0.0.0.0`.
- En attendant le découpage, un premier workflow peut déployer le monolithe actuel (`hospiplan/`).

### 6.4 Sécurité
- [ ] `.gitignore` : `*.PublishSettings`, `*.publishsettings`, `.env`.
- [ ] Les variables d'environnement (`SECRET_KEY`, identifiants PostgreSQL, Service Bus…) sont saisies dans **Configuration → Paramètres d'application** de chaque App Service, jamais dans le code ni dans le profil.
- [ ] Compte partagé : n'importe quel élève peut télécharger le profil → en cas de doute et **après la soutenance**, **Réinitialiser le profil de publication** et mettre à jour le secret GitHub.

### 6.5 Vérification post-déploiement
- [ ] Onglet **Actions** de GitHub : workflow vert.
- [ ] Appel HTTPS des endpoints de chaque service (`https://<app>.azurewebsites.net/...`).
- [ ] Logs : App Service → **Flux de journaux** / Application Insights.
- [ ] Captures d'écran pour le livrable « GitHub et CI/CD » et le plan B de la démo.
