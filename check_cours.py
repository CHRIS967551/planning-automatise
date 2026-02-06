import json

# Charger les cours
with open('data/output/2025-2026/cours_planifies.json', 'r', encoding='utf-8') as f:
    cours = json.load(f)

# Chercher pour 2026-02-05 le matin
jour = "2026-02-05"
formations_matin = ["ASSU 1", "BQ 2", "CJN 2", "LPMN 1"]

print("=== Cours du matin (2026-02-05) ===\n")
for form in formations_matin:
    print(f"▶ {form}:")
    for c in cours:
        if c["date"] == jour and c["formation"] == form:
            h_debut_min = int(c["heure_debut"].split("h")[0]) * 60 + int((c["heure_debut"].split("h")[1] or "0"))
            h_fin_min = int(c["heure_fin"].split("h")[0]) * 60 + int((c["heure_fin"].split("h")[1] or "0"))
            # Matin = avant 12h30
            if h_debut_min < 12*60+30 and h_fin_min > 8*60+30:
                print(f"  {c['heure_debut']}-{c['heure_fin']}: {c['matiere_nom']}")
    print()
