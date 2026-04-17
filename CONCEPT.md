# HospiPlan — Document de concept et documentation technique

> Hôpital fictif **Al Amal** · Projet Bootcamp · 3 phases progressives

---

## 1. Contexte et problématique

L'hôpital Al Amal opère 24 h/24 sur plusieurs services avec plus de 80 soignants aux profils variés. Avant HospiPlan, les plannings étaient construits manuellement dans des tableurs, ce qui engendrait des erreurs fréquentes, des conflits d'horaires, des surcharges injustes et un temps RH considérable.

**HospiPlan** résout ce problème en trois étapes progressives :

1. Modéliser rigoureusement le domaine (base de données relationnelle)
2. Exposer cette base via une API et une interface web permettant la gestion manuelle sous contraintes
3. Automatiser la génération de plannings en respectant les règles légales et en optimisant l'équité

---

## 2. Architecture générale

```
┌─────────────────────────────────────┐
│           Navigateur (React)         │
│  - Gestion des soignants, postes    │
│  - Génération automatique           │
│  - Tableau de bord statistiques     │
└──────────────┬──────────────────────┘
               │ HTTP / JSON
               ▼
┌─────────────────────────────────────┐
│        Backend Django REST          │
│  - CRUD soignants, shifts, etc.     │
│  - Validation contraintes dures     │
│  - Moteur de génération (Phase 3)   │
└──────────────┬──────────────────────┘
               │ ORM Django
               ▼
┌─────────────────────────────────────┐
│         PostgreSQL 15               │
│  - Schéma normalisé 3NF             │
│  - Contraintes d'intégrité SQL      │
└─────────────────────────────────────┘
```

---

## 3. Modèle de données — entités principales

| Entité | Rôle |
|--------|------|
| `Staff` | Soignant : nom, email, rôles, spécialités, statut actif |
| `Role` | Catégorie (IDE, Aide-soignant, Médecin, Cadre) |
| `Specialty` | Spécialité médicale (hiérarchique via `parent`) |
| `ContractType` | Type de contrat : CDI, CDD, intérim, vacation |
| `Contract` | Contrat actif ou passé d'un soignant |
| `Certification` | Habilitation médicale (avec dépendances) |
| `StaffCertification` | Possession d'une certification + dates de validité |
| `Service` | Service hospitalier (Urgences, Cardiologie…) |
| `CareUnit` | Unité de soins rattachée à un service |
| `ShiftType` | Type de garde (jour, nuit, week-end) |
| `Shift` | Créneau concret : unité + type + plage horaire + min/max staff |
| `ShiftAssignment` | Affectation d'un soignant à un créneau |
| `Absence` | Absence déclarée (congés, maladie, formation…) |
| `Preference` | Préférence ou contrainte impérative d'un soignant |
| `PatientLoad` | Charge patiente journalière par unité |
| `StaffLoan` | Prêt inter-services |
| `Rule` | Règle métier configurable (legacy) |
| `SoftConstraintWeight` | Poids des contraintes molles M1–M7 (Phase 3) |

---

## 4. Phase 1 — Fondations : Base de données

### Objectifs
Concevoir un schéma relationnel normalisé (3NF minimum) qui couvre les 10 exigences fonctionnelles du cahier des charges : personnel, contrats, certifications, services, gardes, absences, préférences, charge patiente, prêts, règles légales.

### Points clés du schéma
- **Hiérarchie de spécialités** : `Specialty.parent` (autoreférence)
- **Relations temporelles** : `Contract`, `StaffCertification`, `Absence` ont toutes des dates de début/fin pour historiser les états
- **Règles configurables** : `SoftConstraintWeight` stocke les poids modifiables sans redéploiement
- **Requêtes de reporting** : 7 requêtes SQL documentées (Q-01 à Q-07) couvrant disponibilités, équité de charge, certifications expirantes, etc.

---

## 5. Phase 2 — Backend Django & Application Web

### API REST

Le backend expose des ViewSets DRF sur les ressources principales et une logique de validation fine dans `ShiftAssignmentViewSet.create()`.

### Contraintes dures implémentées

Chaque tentative d'affectation (manuelle via API ou automatique) est rejetée si l'une des règles suivantes est violée :

| Règle | Description |
|-------|-------------|
| `RULE_NO_OVERLAP` | Chevauchement de créneaux pour un même soignant |
| `RULE_ABSENCE_PRIO` | Soignant absent sur la période |
| `RULE_CERTIF_REQ` | Certification requise par le poste manquante |
| `RULE_CERTIF_EXP` | Certification présente mais expirée |
| `RULE_MIN_REST` | Repos obligatoire < 11 h après garde de nuit |
| `RULE_CONTRACT_ELIG` | Contrat n'autorisant pas les gardes de nuit |
| `RULE_WEEKLY_QUOTA` | Dépassement du quota horaire hebdomadaire contractuel |
| `RULE_HARD_PREF` | Contrainte impérative déclarée par le soignant |
| `RULE_MIN_STAFF` | Suppression qui ferait passer sous le seuil de sécurité |

La validation est implémentée à deux niveaux :
1. **`views.py`** : réponse explicite en JSON avec message d'erreur lisible
2. **`models.py / ShiftAssignment.clean()`** : filet de sécurité au niveau ORM

### Frontend React

- Navigation latérale avec sections « Espace soignant » et « Espace RH »
- CRUD soignants, postes, affectations, absences, préférences
- Messages d'erreur inline quand une contrainte dure est violée

---

## 6. Phase 3 — Contraintes molles et génération automatique

### Principe

Le générateur produit un planning **admissible** (aucune contrainte dure violée) en minimisant une **fonction objectif** qui pénalise les contraintes molles.

### Moteur de génération (`api/planning/`)

#### `generator.py` — Heuristique gloutonne (MRV)

1. **Sélection des shifts** : ordonne les créneaux par nombre décroissant de difficulté (Most Restricted Variable — le shift avec le moins de candidats légaux est traité en premier)
2. **Sélection du soignant** : pour chaque slot, choisit le soignant légal qui minimise localement le score soft ; en cas d'égalité, applique **least-loaded** (moins de gardes dans ce service sur la période) pour équilibrer la charge (répond directement à M3)
3. **Créneaux non pourvus** : si aucun soignant légal n'existe pour un slot, le créneau est laissé vide et signalé dans la réponse

#### `metaheuristic.py` — Recherche tabou

Améliore le planning glouton en explorant des **permutations d'affectations** (échange de soignants entre deux shifts) tout en maintenant les contraintes dures.

Paramètres :
- `max_iter` : 200 itérations
- `tabu_len` : 25 (taille de la liste tabou)
- `time_limit_s` : 6 secondes max

#### `scoring.py` — Fonction objectif

Score total = somme pondérée des pénalités M1 à M7 :

```
score = w_M1 × pénalité_nuits_consécutives
      + w_M2 × pénalité_préférences_non_respectées
      + w_M3 × écart_type_charge_par_grade_service
      + w_M4 × nombre_changements_de_service
      + w_M5 × écart_type_week_ends_sur_trimestre
      + w_M6 × affectations_sans_adaptation
      + w_M7 × ruptures_continuité_soins
```

Un score plus bas signifie un meilleur planning du point de vue RH.

#### `feasibility.py` — Oracle de faisabilité

Vérifie en mémoire (sans requêtes SQL pendant la génération) qu'une affectation candidate respecte toutes les contraintes dures. Charge les données nécessaires une seule fois avant la génération.

### Interface Phase 3

#### Génération automatique (`/generer`)
- **Date de début + Date de fin** : génération multi-jours en boucle
- **Service** : dropdown par nom (plus d'ID à saisir manuellement)
- **Option tabou** : active/désactive la métaheuristique
- **Option persistance** : enregistre ou non en base
- **Vue tableau** : résultats jour par jour avec score, affectations, créneaux non pourvus
- **Vue calendrier** : planning visuel avec code couleur par soignant

#### Tableau de bord (`/statistiques`)
- Filtre par période (date début / date fin)
- 5 KPIs globaux (shifts, couverture, absences…)
- Graphique en barres par type de garde
- Table de couverture par service avec barre de progression
- Table d'activité par soignant (gardes, nuits, week-ends, services)

---

## 7. Données de démonstration

La commande `python manage.py seed_phase3` peuple la base avec :

- 15 soignants avec rôles, spécialités, contrats et certifications variés
- 5 services (Urgences, Cardiologie, Pédiatrie, Réanimation, Gériatrie)
- 5 unités de soins et leurs charges patientes sur 7 jours
- Shifts (jour + nuit) sur 7 jours pour chaque unité
- 5 absences réparties aléatoirement
- 12 préférences structurées (M2)
- Poids par défaut des contraintes molles (M1–M7)

Options :
```bash
python manage.py seed_phase3           # peuple sans toucher aux données existantes
python manage.py seed_phase3 --reset   # remet la base à zéro avant de peupler
python manage.py seed_phase3 --seed 99 # change la graine aléatoire (reproductibilité)
```

---

## 8. Décisions techniques notables

| Décision | Justification |
|----------|---------------|
| PostgreSQL | Schéma relationnel complexe, transactions ACID nécessaires pour les affectations concurrentes |
| Django REST Framework | Intégration naturelle avec l'ORM Django, serializers + ViewSets réduisent la boilerplate |
| Validation à deux niveaux (vue + modèle) | La validation modèle (`clean()`) est le filet de sécurité ; la validation vue produit des messages d'erreur lisibles pour le frontend |
| Heuristique MRV + least-loaded | Approche classique des CSP ; least-loaded répond directement à M3 sans complexité supplémentaire |
| Poids des molles en base | Les règles métier évoluent avec la convention collective ; les stocker en base permet de les modifier sans redéploiement |
| Génération jour par jour | Simplifie la logique et permet d'afficher les résultats progressivement dans l'UI |

---

## 9. Pistes d'amélioration futures

- Authentification JWT avec rôles (soignant vs RH vs admin)
- Notifications push quand un créneau reste non pourvu
- Export PDF / Excel du planning généré
- Algorithme génétique comme alternative à la recherche tabou pour les longues périodes
- Tests d'intégration couvrant les scénarios de contraintes dures
- CI/CD : GitHub Actions → déploiement automatique (Vercel + Railway)
