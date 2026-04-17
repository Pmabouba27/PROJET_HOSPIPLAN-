# HospiPlan — Système de planification du personnel soignant

> Projet Bootcamp · Hôpital fictif **Al Amal** · 3 phases progressives

---

## Présentation rapide

HospiPlan est une application web full-stack qui automatise la planification des gardes du personnel soignant d'un hôpital. Elle repose sur :

- **Backend** Django REST Framework + PostgreSQL
- **Frontend** React (Create React App)
- **Génération automatique** de planning via heuristique gloutonne + recherche tabou (Phase 3)
- **Tableau de bord** statistiques et vue calendrier

---

## Prérequis

| Outil | Version minimale |
|-------|-----------------|
| Python | 3.10 |
| Node.js | 18 |
| PostgreSQL | 14 |
| Docker + Docker Compose | 24 (optionnel) |

---

## Démarrage rapide (sans Docker)

### 1. Cloner le dépôt

```bash
git clone <url-du-repo>
cd Projet_Hospiplan
```

### 2. Base de données PostgreSQL

#### Créer la base

Connectez-vous à PostgreSQL avec le super-utilisateur (`postgres`) :

```bash
psql -U postgres
```

Puis dans le shell PostgreSQL :

```sql
CREATE DATABASE hospiplan;
-- Si vous souhaitez un utilisateur dédié :
CREATE USER hospiplan_user WITH PASSWORD 'votre_mot_de_passe';
GRANT ALL PRIVILEGES ON DATABASE hospiplan TO hospiplan_user;
\q
```

#### Accès à l'interface d'administration PostgreSQL

Vous pouvez utiliser **pgAdmin** ou **DBeaver** pour inspecter la base visuellement.

Paramètres de connexion par défaut (définis dans `hospiplan/hospiplan/settings.py`) :

| Paramètre | Valeur |
|-----------|--------|
| Host | `localhost` |
| Port | `5432` |
| Database | `hospiplan` |
| User | `postgres` |
| Password | `enfant*2` |

Pour modifier ces valeurs, éditez le bloc `DATABASES` dans `hospiplan/hospiplan/settings.py`.

### 3. Backend Django

```bash
cd hospiplan

# Créer et activer l'environnement virtuel
python -m venv ../myenv
source ../myenv/bin/activate        # Linux/macOS
# ou : ..\myenv\Scripts\activate    # Windows

# Installer les dépendances
pip install -r requirements.txt

# Appliquer les migrations (crée toutes les tables)
python manage.py migrate

# Peupler la base avec les données de démonstration (15 soignants, 5 services, shifts…)
python manage.py seed_phase3

# (optionnel) Remettre la base à zéro et repeupler
python manage.py seed_phase3 --reset

# Créer un superutilisateur pour l'admin Django
python manage.py createsuperuser

# Lancer le serveur de développement
python manage.py runserver
# → disponible sur http://localhost:8000
```

L'interface d'administration Django est accessible sur **http://localhost:8000/admin/** (superutilisateur requis). Elle permet de gérer directement toutes les tables : soignants, services, types de contrat, poids des contraintes molles, etc.

### 4. Frontend React

```bash
cd frontend

npm install
npm start
# → disponible sur http://localhost:3000
```

---

## Démarrage avec Docker Compose

```bash
# Lancer toute la stack (base + backend + frontend)
docker-compose up --build

# En arrière-plan
docker-compose up -d --build

# Appliquer les migrations dans le conteneur backend
docker-compose exec backend python manage.py migrate

# Peupler la base
docker-compose exec backend python manage.py seed_phase3

# Arrêter les services
docker-compose down

# Supprimer aussi les volumes (reset complet de la base)
docker-compose down -v
```

Les services exposés :

| Service | URL |
|---------|-----|
| Frontend React | http://localhost:3000 |
| Backend Django API | http://localhost:8000 |
| Admin Django | http://localhost:8000/admin/ |
| PostgreSQL | localhost:5432 |

---

## Structure du projet

```
Projet_Hospiplan/
├── docker-compose.yml          # Orchestration des 3 services
├── README.md                   # Ce fichier
├── CONCEPT.md                  # Documentation métier et technique
│
├── hospiplan/                  # Backend Django
│   ├── manage.py
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── hospiplan/              # Configuration Django
│   │   └── settings.py
│   └── api/                    # Application principale
│       ├── models.py           # Modèles de données
│       ├── serializers.py      # Sérialisation DRF
│       ├── views.py            # Endpoints API
│       ├── urls.py             # Routage
│       ├── planning/           # Moteur Phase 3
│       │   ├── generator.py    # Heuristique gloutonne
│       │   ├── metaheuristic.py# Recherche tabou
│       │   ├── scoring.py      # Fonction objectif (molles M1-M7)
│       │   └── feasibility.py  # Oracle contraintes dures
│       └── management/
│           └── commands/
│               └── seed_phase3.py  # Peuplement de démonstration
│
└── frontend/                   # Application React
    ├── package.json
    ├── Dockerfile
    └── src/
        ├── App.js              # Routage + navigation
        ├── App.css             # Styles globaux
        └── components/
            ├── Home.js         # Accueil
            ├── Soignants.js    # Gestion du personnel
            ├── Postes.js       # Postes de garde
            ├── Affectations.js # Affectations manuelles
            ├── Absences.js     # Gestion des absences
            ├── Preferences.js  # Préférences soignants
            ├── GeneratePlanning.js  # Génération auto (Phase 3)
            └── Statistiques.js     # Tableau de bord (Phase 3)
```

---

## Endpoints API principaux

| Méthode | URL | Description |
|---------|-----|-------------|
| GET/POST | `/api/staff/` | Liste et création de soignants |
| GET/POST | `/api/shifts/` | Postes de garde |
| GET/POST | `/api/assignments/` | Affectations (avec validation des contraintes dures) |
| GET/POST | `/api/absences/` | Absences |
| GET/POST | `/api/services/` | Services hospitaliers |
| GET/POST | `/api/preferences/` | Préférences soignants |
| POST | `/api/plannings/generate/` | Génération automatique de planning |
| GET | `/api/stats/` | Tableau de bord statistiques |

### Exemple — Générer un planning

```bash
curl -X POST http://localhost:8000/api/plannings/generate/ \
  -H "Content-Type: application/json" \
  -d '{
    "date": "2026-04-20",
    "metaheuristic": true,
    "persist": false
  }'
```

### Exemple — Statistiques sur une période

```bash
curl "http://localhost:8000/api/stats/?start_date=2026-04-01&end_date=2026-04-30"
```

---

## Contraintes appliquées

### Dures (rejet automatique de l'affectation)

- Chevauchement de créneaux pour un même soignant
- Soignant absent ou inactif
- Certifications manquantes ou expirées
- Repos obligatoire de 11 h après garde de nuit
- Quota hebdomadaire d'heures contractuelles dépassé
- Contrat n'autorisant pas les gardes de nuit
- Contraintes impératives déclarées par le soignant

### Molles (pénalisées dans la fonction objectif, Phase 3)

| Code | Description | Poids défaut |
|------|-------------|--------------|
| M1 | Nuits consécutives > N | 5.0 |
| M2 | Non-respect des préférences F-07 | 1.0 |
| M3 | Déséquilibre de charge par grade/service | 3.0 |
| M4 | Changements de service dans la semaine | 2.0 |
| M5 | Iniquité des gardes de week-end (trimestre) | 4.0 |
| M6 | Affectation sans période d'adaptation | 2.5 |
| M7 | Rupture de continuité de soins | 3.0 |

Les poids sont modifiables sans redéploiement via l'admin Django (`SoftConstraintWeight`).

---

## Lancer les tests

```bash
cd hospiplan
python manage.py test api
```

---

## Ressources

- [Django REST Framework](https://www.django-rest-framework.org/)
- [React](https://react.dev/)
- [PostgreSQL](https://www.postgresql.org/docs/)
- [Docker Compose](https://docs.docker.com/compose/)
