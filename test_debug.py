import json, os
from app import charger_salles, safe_json, generer_salles_automatiques, to_minutes

base = os.path.join('data', 'output', '2025-2026')
cours_path = os.path.join(base, 'cours_planifies.json')

cours = safe_json(cours_path, [])
salles = charger_salles()
effectifs = safe_json(os.path.join(base, 'effectifs.json'), {})
access = safe_json(os.path.join(base, 'accessibilite.json'), {})

print(f'Cours: {len(cours)}')
print(f'Salles: {len(salles)}')
codes = [s["code"] for s in salles]
print(f'Codes: {codes}')
print(f'Capacités: {[s["capacite"] for s in salles]}')
print(f'Effectif ASSU 1: {effectifs.get("ASSU 1")}')
print(f'Effectif LGCVM: {effectifs.get("LGCVM")}')

# Test to_minutes
try:
    print(f'to_minutes("09h00") = {to_minutes("09h00")}')
except Exception as e:
    print(f'ERREUR: {e}')

# Appeler generer_salles
print("\nAppel generer_salles_automatiques...")
try:
    generer_salles_automatiques(cours, salles, effectifs, access)
    # Vérifier le 5 février
    cours_5fev = [c for c in cours if c['date'] == '2026-02-05']
    print(f"Cours du 5 fév: {len(cours_5fev)}")
    for c in cours_5fev[:5]:
        print(f"  {c['formation']} {c['heure_debut']}: {c.get('salle', 'NONE')}")
except Exception as e:
    print(f"ERREUR: {e}")
    import traceback
    traceback.print_exc()
