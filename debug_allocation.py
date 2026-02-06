import json

# Charger le JSON généré
with open('data/output/2025-2026/cours_planifies.json', 'r', encoding='utf-8') as f:
    courses = json.load(f)

# Récupérer seulement 5 février matin
morning_courses = [c for c in courses if c['date'] == '2026-02-05' and int(c['heure_debut'].split('h')[0]) < 12]

# Grouper par salle
by_salle = {}
for c in morning_courses:
    salle = c.get('salle', 'NONE')
    if salle not in by_salle:
        by_salle[salle] = []
    by_salle[salle].append(c)

# Afficher par salle
print("=" * 80)
print("ALLOCATION SALLE POUR 5 FÉVRIER MATIN")
print("=" * 80)
for salle in sorted(by_salle.keys()):
    courses_in_room = by_salle[salle]
    print(f"\nSALLE {salle}:")
    for c in sorted(courses_in_room, key=lambda x: x['heure_debut']):
        print(f"  {c['heure_debut']:6} - {c['heure_fin']:6} | {c['formation']:12} | {c['matiere_nom']}")
    
    # Vérifier s'il y a un conflit (matière différente au même créneau)
    for i, c1 in enumerate(courses_in_room):
        for c2 in courses_in_room[i+1:]:
            if c1['heure_debut'] == c2['heure_debut'] and c1['matiere_nom'] != c2['matiere_nom']:
                print(f"  ⚠️  CONFLIT: {c1['formation']} ({c1['matiere_nom']}) et {c2['formation']} ({c2['matiere_nom']}) au même créneau !")

print("\n" + "=" * 80)
