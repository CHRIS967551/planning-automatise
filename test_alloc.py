import sys
sys.path.insert(0, 'c:/Users/HP/Desktop/planning_automatise')

try:
    from app import charger_salles, charger_cours, charger_effectifs_et_accessibilite, generer_salles_automatiques, annee_path, safe_json
    print("✓ Imports OK")
    
    # Charger les données
    annee = "2025-2026"
    cours = charger_cours(annee)
    print(f"✓ {len(cours)} cours chargés")
    
    salles = charger_salles()
    print(f"✓ {len(salles)} salles chargées")
    
    effectifs, access = charger_effectifs_et_accessibilite(annee)
    print(f"✓ Effectifs et accessibilité chargés")
    
    # Lancer l'allocation
    print("\nGénération des salles...")
    generer_salles_automatiques(cours, salles, effectifs, access)
    print("✓ Allocation générée")
    
    # Vérifier le JSON
    import json
    with open(f'data/output/{annee}/cours_planifies.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"✓ {len(data)} cours dans le JSON")
    
except Exception as e:
    import traceback
    print(f"\n✗ ERREUR:")
    traceback.print_exc()
