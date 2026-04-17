"""
Script de peuplement via l'API REST — HospiPlan
================================================
Crée les 20 soignants avec leurs absences et préférences
directement via les endpoints HTTP, sans passer par Django.

Pré-requis :
    pip install requests

Usage :
    python seed_api.py              # peuple depuis zéro
    python seed_api.py --reset      # supprime d'abord toutes les données existantes

Le backend doit être lancé sur http://localhost:8000
"""

import sys
import random
import requests
from datetime import date, timedelta

BASE = "http://localhost:8000/api"
random.seed(42)

# ─── helpers ────────────────────────────────────────────────────────────────

def get(path):
    r = requests.get(f"{BASE}/{path}/")
    r.raise_for_status()
    return r.json()

def post(path, data):
    r = requests.post(f"{BASE}/{path}/", json=data)
    if not r.ok:
        print(f"  ⚠  POST /{path}/ — {r.status_code}: {r.text[:200]}")
        return None
    return r.json()

def delete_all(path):
    items = get(path)
    for item in items:
        requests.delete(f"{BASE}/{path}/{item['id']}/")
    print(f"  🗑  {len(items)} {path} supprimés")

def today_str(delta=0):
    return str(date.today() + timedelta(days=delta))

# ─── données de référence ────────────────────────────────────────────────────

PRENOMS = [
    'Amina',   'Bastien', 'Chloé',   'Diallo',  'Élise',
    'Fatou',   'Gabriel', 'Hana',    'Inès',    'Julien',
    'Khadija', 'Lucas',   'Marion',  'Nora',    'Omar',
    'Priya',   'Quentin', 'Rania',   'Sébastien','Tania',
]
NOMS = [
    'Traoré',   'Martin',   'Lefebvre', 'Dupont',    'Moreau',
    'Diop',     'Bernard',  'Nguyen',   'Richard',   'Petit',
    'Barry',    'Rousseau', 'Bouchard', 'Okonkwo',   'Garcia',
    'Sharma',   'Lemaire',  'Benali',   'Fontaine',  'Millet',
]

# Absences par soignant (index → liste de dict)
ABSENCES = {
    0:  [{"type": "Congés payés",    "delta_start": 2,   "delta_end": 10,  "planned": True}],
    3:  [{"type": "Formation",       "delta_start": 5,   "delta_end": 8,   "planned": True}],
    6:  [{"type": "Arrêt maladie",   "delta_start": -1,  "delta_end": 4,   "planned": False}],
    10: [{"type": "Congés payés",    "delta_start": 1,   "delta_end": 7,   "planned": True}],
    13: [{"type": "Arrêt maladie",   "delta_start": 0,   "delta_end": 3,   "planned": False}],
    # Soignants spéciaux pour les tests
    17: [{"type": "Arrêt maladie",   "delta_start": -1,  "delta_end": 10,  "planned": False}],  # RULE_ABSENCE_PRIO
    19: [{"type": "Congé maternité", "delta_start": -30, "delta_end": 60,  "planned": True}],   # RULE_ABSENCE_PRIO
}

# Préférences par soignant (index → liste de dict)
PREFERENCES = {
    0:  [{"kind": "wants_shift_type",  "importance": 3, "shift_type_name": "Jour",      "hard": False}],
    1:  [{"kind": "avoids_shift_type", "importance": 4, "shift_type_name": "Nuit",      "hard": False}],
    2:  [{"kind": "wants_service",     "importance": 2, "service_name": "Pédiatrie",    "hard": False}],
    3:  [{"kind": "avoids_day",        "importance": 3, "day": 5,                       "hard": False}],  # samedi
    4:  [{"kind": "wants_day",         "importance": 2, "day": 0,                       "hard": False}],  # lundi
    5:  [{"kind": "avoids_service",    "importance": 3, "service_name": "Réanimation",  "hard": False}],
    6:  [{"kind": "wants_shift_type",  "importance": 5, "shift_type_name": "Week-end",  "hard": False}],
    7:  [{"kind": "avoids_shift_type", "importance": 2, "shift_type_name": "Week-end",  "hard": False}],
    8:  [{"kind": "wants_service",     "importance": 4, "service_name": "Cardiologie",  "hard": False}],
    9:  [{"kind": "avoids_day",        "importance": 1, "day": 6,                       "hard": False}],  # dimanche
    11: [{"kind": "wants_day",         "importance": 3, "day": 1,                       "hard": False}],  # mardi
    12: [{"kind": "wants_service",     "importance": 2, "service_name": "Gériatrie",    "hard": False}],
    14: [{"kind": "avoids_service",    "importance": 4, "service_name": "Urgences",     "hard": False}],
    15: [{"kind": "avoids_shift_type", "importance": 5, "shift_type_name": "Nuit",      "hard": False}],
    # Contrainte DURE — Sébastien Fontaine (index 18) ne travaille jamais le vendredi
    18: [{"kind": "avoids_day",        "importance": 5, "day": 4,                       "hard": True,
          "description": "Ne peut pas travailler le vendredi (contrainte de transport)"}],
}

# ─── script principal ────────────────────────────────────────────────────────

def main():
    reset = "--reset" in sys.argv

    print("=" * 55)
    print("  HospiPlan — Seed API")
    print("=" * 55)

    # 0. Vérifier que l'API répond
    try:
        requests.get(f"{BASE}/staff/", timeout=5)
    except Exception:
        print("\n❌ Impossible de joindre http://localhost:8000")
        print("   Vérifie que le backend Django est bien lancé.\n")
        sys.exit(1)

    # 1. Reset optionnel
    if reset:
        print("\n🗑  Reset des données…")
        delete_all("preferences")
        delete_all("absences")
        # Supprime les soignants qui ont l'email @chu-alaamal.fr
        staff = get("staff")
        for s in staff:
            if "@chu-alaamal.fr" in s.get("email", ""):
                requests.delete(f"{BASE}/staff/{s['id']}/")
        print(f"  🗑  soignants @chu-alaamal.fr supprimés")

    # 2. Charger les référentiels existants
    print("\n📦 Chargement des référentiels…")
    shift_types_list = get("shift_types")
    services_list    = get("services")
    absence_types_list = get("absence_types")

    # Index par nom
    shift_type_by_name  = {st["name"]: st["id"] for st in shift_types_list}
    service_by_name     = {sv["name"]: sv["id"] for sv in services_list}
    absence_type_by_name = {at["name"]: at["id"] for at in absence_types_list}

    if not shift_types_list:
        print("\n⚠  Aucun ShiftType trouvé.")
        print("   Lance d'abord : python manage.py seed_phase3 --reset")
        print("   (une seule fois pour créer les référentiels)\n")
        sys.exit(1)

    print(f"   Types de shift  : {list(shift_type_by_name.keys())}")
    print(f"   Services        : {list(service_by_name.keys())}")
    print(f"   Types d'absence : {list(absence_type_by_name.keys())}")

    # 3. Créer les 20 soignants
    print("\n👥 Création des 20 soignants…")
    staff_ids = []
    existing_staff = {s["email"]: s["id"] for s in get("staff")}

    for i, (prenom, nom) in enumerate(zip(PRENOMS, NOMS)):
        email = f"{prenom.lower()}.{nom.lower()}@chu-alaamal.fr"
        if email in existing_staff:
            staff_ids.append(existing_staff[email])
            print(f"   [{i:02d}] {prenom} {nom} — déjà existant (id={existing_staff[email]})")
            continue

        created = post("staff", {
            "first_name": prenom,
            "last_name":  nom,
            "email":      email,
            "phone":      f"06 {i:02d} {i:02d} {i:02d} {i:02d}",
            "is_active":  True,
        })
        if created:
            staff_ids.append(created["id"])
            print(f"   [{i:02d}] {prenom} {nom} — créé (id={created['id']})")
        else:
            staff_ids.append(None)

    # 4. Créer les absences
    print(f"\n🏥 Création des absences ({len(ABSENCES)} soignants)…")
    for idx, abs_list in ABSENCES.items():
        sid = staff_ids[idx] if idx < len(staff_ids) else None
        if not sid:
            print(f"   ⚠  soignant index {idx} introuvable, skip")
            continue
        for ab in abs_list:
            type_id = absence_type_by_name.get(ab["type"])
            if not type_id:
                print(f"   ⚠  Type d'absence '{ab['type']}' introuvable, skip")
                continue
            result = post("absences", {
                "staff":             sid,
                "absence_type":      type_id,
                "start_date":        today_str(ab["delta_start"]),
                "expected_end_date": today_str(ab["delta_end"]),
                "is_planned":        ab["planned"],
            })
            if result:
                nom_s = f"{PRENOMS[idx]} {NOMS[idx]}"
                print(f"   ✔  {nom_s} → {ab['type']} "
                      f"({today_str(ab['delta_start'])} → {today_str(ab['delta_end'])})")

    # 5. Créer les préférences
    print(f"\n⚙️  Création des préférences ({len(PREFERENCES)} soignants)…")
    for idx, pref_list in PREFERENCES.items():
        sid = staff_ids[idx] if idx < len(staff_ids) else None
        if not sid:
            print(f"   ⚠  soignant index {idx} introuvable, skip")
            continue
        for pref in pref_list:
            payload = {
                "staff":             sid,
                "type":              "hard_constraint" if pref["hard"] else "user_preference",
                "kind":              pref["kind"],
                "importance":        pref["importance"],
                "is_hard_constraint": pref["hard"],
                "description":       pref.get("description", f"Auto-seed ({pref['kind']})"),
            }
            # Cible selon le kind
            if "shift_type_name" in pref:
                st_id = shift_type_by_name.get(pref["shift_type_name"])
                if not st_id:
                    print(f"   ⚠  ShiftType '{pref['shift_type_name']}' introuvable, skip")
                    continue
                payload["target_shift_type"] = st_id
            elif "service_name" in pref:
                svc_id = service_by_name.get(pref["service_name"])
                if not svc_id:
                    print(f"   ⚠  Service '{pref['service_name']}' introuvable, skip")
                    continue
                payload["target_service"] = svc_id
            elif "day" in pref:
                payload["target_day_of_week"] = pref["day"]

            result = post("preferences", payload)
            if result:
                nom_s = f"{PRENOMS[idx]} {NOMS[idx]}"
                label = "⛔ DURE" if pref["hard"] else "✔ souple"
                print(f"   {label}  {nom_s} → {pref['kind']} (importance {pref['importance']})")

    # 6. Résumé final
    total_staff   = len([x for x in staff_ids if x])
    total_abs     = len(get("absences"))
    total_prefs   = len(get("preferences"))

    print("\n" + "=" * 55)
    print("  ✅ Seed terminé !")
    print(f"     Soignants créés/vérifiés : {total_staff}")
    print(f"     Absences en base         : {total_abs}")
    print(f"     Préférences en base      : {total_prefs}")
    print()
    print("  🧪 Soignants spéciaux pour les tests :")
    print("     Rania Benali (idx 17)     → RULE_ABSENCE_PRIO (arrêt 10j)")
    print("     Tania Millet (idx 19)     → RULE_ABSENCE_PRIO (congé maternité)")
    print("     Sébastien Fontaine (idx 18) → Contrainte dure vendredi")
    print("     Priya Sharma (idx 15)     → RULE_CONTRACT_ELIG (intérimaire, pas de nuit)*")
    print("     Quentin Lemaire (idx 16)  → RULE_CERTIF_EXP (certif expirée)*")
    print()
    print("  * Ces règles nécessitent seed_phase3 pour les contrats/certifs.")
    print("=" * 55)


if __name__ == "__main__":
    main()
