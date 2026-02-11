from flask import Flask, render_template, request, redirect
from datetime import date, datetime
import os, csv, json
import locale

# 🔵 Activer la locale française pour les dates
try:
    locale.setlocale(locale.LC_TIME, "fr_FR.UTF-8")
except:
    locale.setlocale(locale.LC_TIME, "French_France")

app = Flask(__name__)

# ======================
# PATHS
# ======================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
REFERENCES = os.path.join(DATA_DIR, "references")
OUTPUT = os.path.join(DATA_DIR, "output")
IMPORTS = os.path.join(DATA_DIR, "imports")

os.makedirs(IMPORTS, exist_ok=True)
os.makedirs(REFERENCES, exist_ok=True)
os.makedirs(OUTPUT, exist_ok=True)

# ======================
# ANNÉE ACTIVE
# ======================

def get_annee_active():
    path = os.path.join(OUTPUT, "annee_active.json")
    if not os.path.exists(path):
        return "2025-2026"
    return json.load(open(path, encoding="utf-8"))["annee"]

def annee_path():
    a = get_annee_active()
    p = os.path.join(OUTPUT, a)
    os.makedirs(p, exist_ok=True)

    def ensure(name, default):
        path = os.path.join(p, name)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default, f, indent=2)

    ensure("cours_planifies.json", [])
    ensure("verrou.json", {"verrouille": False})
    ensure("effectifs.json", {})
    ensure("accessibilite.json", {})

    return p

# ======================
# UTILS
# ======================

def safe_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default

def to_minutes(h):
    h = h.replace("h", ":")
    hh, mm = h.split(":")
    return int(hh) * 60 + int(mm)

def normaliser_nom_formation(nom):
    nom = nom.upper()
    nom = nom.replace("(", "").replace(")", "")
    nom = " ".join(nom.split())
    return nom

def extraire_heures_du_texte(matiere_nom):
    """
    Extrait les heures du texte du cours si elles existent.
    Formats acceptés: (9h-12h30), (9h30-12h), (09h-12h30), etc.
    Ex: "UE62 - Droit rural - J. MIR (9h-12h30)" -> ("09h", "12h30")
    Sinon retourne None
    """
    import re
    
    # Cherche pattern (XXhYY-XXhYY) avec espaces optionnels
    # Accepte: 9h, 9h30, 09h, 09h30, 9H, etc.
    match = re.search(r'\(\s*(\d{1,2})h(\d{0,2})\s*-\s*(\d{1,2})h(\d{0,2})\s*\)', matiere_nom, re.IGNORECASE)
    if match:
        h_debut_heure = match.group(1).zfill(2)
        h_debut_min = match.group(2).zfill(2) if match.group(2) else "00"
        h_fin_heure = match.group(3).zfill(2)
        h_fin_min = match.group(4).zfill(2) if match.group(4) else "00"
        
        h_debut = f"{h_debut_heure}h{h_debut_min}"
        h_fin = f"{h_fin_heure}h{h_fin_min}"
        
        return (h_debut, h_fin)
    
    return None

# ======================
# FORMATIONS
# ======================

FORMATIONS_PATH = os.path.join(REFERENCES, "formations.json")

def charger_formations():
    data = safe_json(FORMATIONS_PATH, {})
    propres = {}

    for nom, infos in data.items():
        up = nom.upper()
        if "EMPLOIS DU TEMPS" in up or "EMPLOI DU TEMPS" in up or "PLANNING" in up:
            continue

        nom_clean = normaliser_nom_formation(nom)

        if nom_clean not in propres:
            propres[nom_clean] = {"effectif": int(infos.get("effectif", 0))}
        else:
            propres[nom_clean]["effectif"] = max(
                propres[nom_clean]["effectif"],
                int(infos.get("effectif", 0))
            )

    with open(FORMATIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(propres, f, indent=2)

    return [{"nom": n, "effectif": v["effectif"]} for n, v in propres.items()]

def sauver_formations(formations):
    with open(FORMATIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {f["nom"]: {"effectif": f["effectif"]} for f in formations},
            f,
            indent=2
        )

# ======================
# SALLES
# ======================

def charger_salles():
    path = os.path.join(REFERENCES, "salles.csv")
    if not os.path.exists(path):
        return []

    try:
        with open(path, encoding="utf-8-sig") as f:
            # Détecter le délimiteur
            sample = f.read(1024)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
                delimiter = dialect.delimiter
            except:
                delimiter = "," if "," in sample else ";"
            f.seek(0)
            salles = list(csv.DictReader(f, delimiter=delimiter))
        for s in salles:
            s["capacite"] = int(s.get("capacite", 0))
            s["accessible"] = s.get("accessible", "OUI").upper()
        return sorted(salles, key=lambda x: x["capacite"])
    except (IOError, ValueError, KeyError):
        return []

# ======================
# GÉNÉRATION DES SALLES
# ======================

def generer_salles_automatiques(cours, salles, effectifs, access=None):
    """
    RÈGLE MÉTIER :
    - mêmes date + horaires + matière => salle partagée possible
    - capacité >= somme des effectifs
    - UNE SALLE = UNE SEULE FOIS PAR DEMI-JOURNÉE (MATIN / APRES-MIDI)
    """

    if not salles:
        return

    if access is None:
        access = {}

    # ----------------------
    # utilitaire demi-journée
    # ----------------------
    def periode(h_debut):
        return "MATIN" if to_minutes(h_debut) < 13 * 60 else "APRES_MIDI"

    # salles déjà utilisées par (date, période)
    salles_utilisees = {}  # {(date, periode): set(code_salle)}

    # ----------------------
    # regroupement par cours réel
    # ----------------------
    groupes = {}
    for c in cours:
        key = (
            c["date"],
            c["heure_debut"],
            c["heure_fin"],
            c["matiere_nom"]
        )
        groupes.setdefault(key, []).append(c)

    # ----------------------
    # attribution
    # ----------------------
    for groupe in groupes.values():

        date = groupe[0]["date"]
        periode_jour = periode(groupe[0]["heure_debut"])
        cle = (date, periode_jour)

        salles_utilisees.setdefault(cle, set())

        formations = {c["formation"] for c in groupe}
        total = sum(effectifs.get(f, 0) for f in formations)

        besoin_accessible = any(access.get(f, False) for f in formations)

        # 1️⃣ tentative salle commune
        salle_commune = None
        for s in salles:
            if besoin_accessible and s["accessible"] != "OUI":
                continue
            if s["capacite"] < total:
                continue
            if s["code"] in salles_utilisees[cle]:
                continue

            salle_commune = s["code"]
            break

        if salle_commune:
            for c in groupe:
                c["salle"] = salle_commune
            salles_utilisees[cle].add(salle_commune)
            continue

        # 2️⃣ sinon : une salle par formation (TOUJOURS même règle)
        for c in groupe:
            eff = effectifs.get(c["formation"], 0)
            besoin_accessible_f = access.get(c["formation"], False)

            for s in salles:
                if besoin_accessible_f and s["accessible"] != "OUI":
                    continue
                if s["capacite"] < eff:
                    continue
                if s["code"] in salles_utilisees[cle]:
                    continue

                c["salle"] = s["code"]
                salles_utilisees[cle].add(s["code"])
                break


# ======================
# CSV → COURS
# ======================

def lire_csv(path):
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            # Détecter le délimiteur automatiquement
            sample = f.read(1024)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
                delimiter = dialect.delimiter
            except:
                # Fallback: utiliser le délimiteur le plus courant
                delimiter = "," if "," in sample else ";"
            f.seek(0)
            reader = csv.reader(f, delimiter=delimiter)
            return [[c.strip() for c in row] for row in reader]
    except IOError:
        return []

MOIS = {
    "JANV.": "01", "JAN.": "01",
    "FÉV.": "02", "FEV.": "02",
    "FÉVR.": "02", "FEVR.": "02",
    "MARS": "03",
    "AVR.": "04",
    "MAI": "05",
    "JUIN": "06",
    "JUIL.": "07",
    "AOÛT": "08", "AOUT": "08",
    "SEPT.": "09", "SEPTE.": "09",
    "OCT.": "10",
    "NOV.": "11",
    "DÉC.": "12", "DEC.": "12"
}

MOIS_FR = {
    1: "Janvier",
    2: "Février",
    3: "Mars",
    4: "Avril",
    5: "Mai",
    6: "Juin",
    7: "Juillet",
    8: "Août",
    9: "Septembre",
    10: "Octobre",
    11: "Novembre",
    12: "Décembre"
}

JOURS_FR = {
    0: "Lundi",
    1: "Mardi",
    2: "Mercredi",
    3: "Jeudi",
    4: "Vendredi",
    5: "Samedi",
    6: "Dimanche"
}


def parser_csv(path, formation):
    rows = lire_csv(path)
    cours = []
    
    if not rows:
        return cours

    # 🔎 Détection de la ligne d'horaires
    # Cherche une ligne avec des horaires du format "HHhMM-HHhMM"
    header = None
    for r in rows:
        if len(r) > 4:
            horaires_candidates = [c for c in r[4:] if c and "-" in c and ("h" in c or "H" in c)]
            if len(horaires_candidates) >= 3:  # Au moins 3 horaires pour confirmer
                header = r
                break
    
    if not header:
        return cours

    horaires = [h for h in header[4:] if h and "-" in h and ("h" in h or "H" in h)]
    formation = normaliser_nom_formation(formation)

    for r in rows:
        if len(r) < 5:
            continue

        # colonne jour obligatoire
        if not r[1].isdigit():
            continue

        jour = r[1].zfill(2)
        mois_txt = (
            r[2]
            .upper()
            .strip()
            .replace("É", "E")
            .replace("È", "E")
            .replace("Ê", "E")
            .replace("Û", "U")
        )
        annee = r[3].strip()

        # 🔒 validation mois
        if mois_txt not in MOIS:
            continue

        mois = MOIS[mois_txt]

        # 🔒 validation finale de la date (anti-bug jour/mois)
        try:
            date_obj = datetime.strptime(
                f"{annee}-{mois}-{jour}", "%Y-%m-%d"
            ).date()
        except ValueError:
            continue

        date_cours = date_obj.isoformat()

        for i, h in enumerate(horaires):
            if "-" not in h:
                continue

            matiere = r[i + 4].strip()
            if not matiere:
                continue

            # filtrage événements non-cours
            matiere_normalized = matiere.upper().replace("É", "E").replace("È", "E")
            if any(x in matiere_normalized for x in ["ENTREPRISE", "REUNION", "JOURNEE"]):
                continue

            # Essayer d'extraire les heures du texte du cours (ex: "UE62 - ... (9h-12h30)")
            heures_extraites = extraire_heures_du_texte(matiere)
            if heures_extraites:
                h_debut, h_fin = heures_extraites
            else:
                # Utiliser les heures du header si pas d'heures dans le texte
                h_debut, h_fin = h.split("-")

            cours.append({
                "date": date_cours,
                "heure_debut": h_debut.strip(),
                "heure_fin": h_fin.strip(),
                "formation": formation,
                "matiere_nom": matiere,
                "salle": None
            })

    return cours


# ======================
# INDEX
# ======================

@app.route("/", methods=["GET", "POST"])
def index():
    base = annee_path()
    cours_path = os.path.join(base, "cours_planifies.json")
    cours = safe_json(cours_path, [])

    formations = charger_formations()

    effectifs_path = os.path.join(base, "effectifs.json")
    access_path = os.path.join(base, "accessibilite.json")

    effectifs = safe_json(effectifs_path, {})
    access = safe_json(access_path, {})

    for f in formations:
        effectifs.setdefault(f["nom"], f["effectif"])
        access.setdefault(f["nom"], False)

    with open(effectifs_path, "w", encoding="utf-8") as f:
        json.dump(effectifs, f, indent=2)
    with open(access_path, "w", encoding="utf-8") as f:
        json.dump(access, f, indent=2)

    formations_importees = {normaliser_nom_formation(c["formation"]) for c in cours}

    rapport = [{
        "formation": f["nom"],
        "statut": "OK" if normaliser_nom_formation(f["nom"]) in formations_importees else "Aucun cours"

    } for f in formations]

    if request.method == "POST":
        f = request.files.get("csv_file")
        if f:
            f.save(os.path.join(IMPORTS, f.filename))

            raw = f.filename.split(".")[0].upper()
            nom = raw
            for x in ["EMPLOIS DU TEMPS", "EMPLOI DU TEMPS", "PLANNING", "2025-2026", "2026-2027"]:
                nom = nom.replace(x, "")
            nom = " ".join(nom.replace("-", " ").split())

            if nom not in [x["nom"] for x in formations]:
                formations.append({"nom": nom, "effectif": 0})
                sauver_formations(formations)

            cours.extend(parser_csv(os.path.join(IMPORTS, f.filename), nom))
            with open(cours_path, "w", encoding="utf-8") as file:
                json.dump(cours, file, indent=2)

        return redirect("/")

    return render_template(
        "index.html",
        formations=formations,
        rapport=rapport,
        effectifs=effectifs,
        access=access,
        verrou=safe_json(os.path.join(base, "verrou.json"), {"verrouille": False}),
        erreur=None
    )

# ======================
# PREVIEW
# ======================

@app.route("/preview", methods=["GET", "POST"])
def preview():
    base = annee_path()
    cours_path = os.path.join(base, "cours_planifies.json")
    cours = safe_json(cours_path, [])
    today = date.today()

    salles = charger_salles()
    effectifs = safe_json(os.path.join(base, "effectifs.json"), {})
    access = safe_json(os.path.join(base, "accessibilite.json"), {})

    # Générer automatiquement les salles seulement si elles ne sont pas déjà assignées
    if any(c.get("salle") is None for c in cours):
        try:
            generer_salles_automatiques(cours, salles, effectifs, access)
            # Sauvegarder les salles générées
            with open(cours_path, "w", encoding="utf-8") as file:
                json.dump(cours, file, indent=2)
        except Exception as e:
            print(f"ERREUR generer_salles_automatiques: {e}")
            import traceback
            traceback.print_exc()

    par_date = {}
    for c in cours:
        d = datetime.strptime(c["date"], "%Y-%m-%d").date()
        par_date.setdefault(d, []).append(c)

    jours = sorted(par_date)

    # =========================
    # 📅 DATE SÉLECTIONNÉE (CALENDRIER)
    # =========================
    date_param = request.args.get("date")

    if date_param:
        try:
            jour = datetime.strptime(date_param, "%Y-%m-%d").date()
        except ValueError:
            jour = None
    else:
        # COMPORTEMENT ACTUEL (NE CHANGE RIEN)
        jour = next((d for d in jours if d > today), None)

    if jour is None or jour not in par_date:
        return "Aucun cours pour cette date"

    if request.method == "POST":
        for key, salle in request.form.items():
            try:
                d, f = key.split("|")
                for c in cours:
                    if c["date"] == d and c["formation"] == f:
                        c["salle"] = salle.strip() or None
            except ValueError:
                continue

        with open(cours_path, "w", encoding="utf-8") as file:
            json.dump(cours, file, indent=2)
        return redirect(f"/preview?date={jour.isoformat()}")

    matin, apresmidi = {}, {}

    for c in par_date.get(jour, []):
        debut = to_minutes(c["heure_debut"])
        fin = to_minutes(c["heure_fin"])
        
        # Normaliser le nom de formation pour éviter les doublons
        formation_key = normaliser_nom_formation(c["formation"])

        if debut < 12*60+30 and fin > 8*60+30:
            if formation_key not in matin:
                matin[formation_key] = c
        if debut < 17*60+30 and fin > 13*60+30:
            if formation_key not in apresmidi:
                apresmidi[formation_key] = c

    return render_template(
        "preview.html",
        date=jour.isoformat(),
        matin=list(matin.values()),
        apresmidi=list(apresmidi.values())
    )


# ======================
# TV
# ======================

@app.route("/tv")
def tv():
    base = annee_path()
    cours = safe_json(os.path.join(base, "cours_planifies.json"), [])
    today = date.today()

    salles = charger_salles()
    effectifs = safe_json(os.path.join(base, "effectifs.json"), {})
    access = safe_json(os.path.join(base, "accessibilite.json"), {})

    # regroupement par date
    par_date = {}
    for c in cours:
        try:
            d = datetime.strptime(c["date"], "%Y-%m-%d").date()
            par_date.setdefault(d, []).append(c)
        except Exception:
            continue

    jours = sorted(par_date)

    # 🔎 logique correcte :
    # - aujourd’hui s’il y a cours
    # - sinon prochain jour de cours
    jour = today if today in jours else next((d for d in jours if d > today), None)

    # 🔒 sécurité absolue (évite le crash isoformat)
    if jour is None:
        return render_template(
            "tv.html",
            date="Aucun cours",
            matin={},
            apresmidi={},
            is_today=False
        )

    matin, apresmidi = {}, {}

    for c in par_date.get(jour, []):
        debut = to_minutes(c["heure_debut"])
        fin = to_minutes(c["heure_fin"])

        if debut < 12 * 60 + 30 and fin > 8 * 60 + 30:
            matin[c["formation"]] = c["salle"] or "—"

        if debut < 17 * 60 + 30 and fin > 13 * 60 + 30:
            apresmidi[c["formation"]] = c["salle"] or "—"

    return render_template(
        "tv.html",
        date=f"{JOURS_FR[jour.weekday()]} {jour.day:02d} {MOIS_FR[jour.month]} {jour.year}",
        matin=matin,
        apresmidi=apresmidi,
        is_today=(jour == today)
    )



# ======================
# GESTION DES FORMATIONS
# ======================

@app.route("/formations/add", methods=["POST"])
def formations_add():
    base = annee_path()
    nom = request.form.get("nom", "").strip()
    effectif_str = request.form.get("effectif", "0")
    
    if not nom:
        return redirect("/")
    
    try:
        effectif = int(effectif_str)
    except ValueError:
        effectif = 0
    
    # Charger les formations
    formations = charger_formations()
    
    # Vérifier si elle existe déjà
    if not any(f["nom"].upper() == nom.upper() for f in formations):
        formations.append({"nom": nom, "effectif": effectif})
        sauver_formations(formations)
        
        # Initialiser les données pour cette formation
        effectifs_path = os.path.join(base, "effectifs.json")
        access_path = os.path.join(base, "accessibilite.json")
        
        effectifs = safe_json(effectifs_path, {})
        access = safe_json(access_path, {})
        
        effectifs[nom] = effectif
        access[nom] = False
        
        with open(effectifs_path, "w", encoding="utf-8") as f:
            json.dump(effectifs, f, indent=2)
        with open(access_path, "w", encoding="utf-8") as f:
            json.dump(access, f, indent=2)
    
    return redirect("/")

@app.route("/formations/delete", methods=["POST"])
def formations_delete():
    base = annee_path()
    nom = request.form.get("nom", "").strip()
    
    if not nom:
        return redirect("/")
    
    # Charger les formations
    formations = charger_formations()
    
    # Supprimer la formation
    formations = [f for f in formations if f["nom"].upper() != nom.upper()]
    sauver_formations(formations)
    
    # Supprimer des effectifs et accessibilité
    effectifs_path = os.path.join(base, "effectifs.json")
    access_path = os.path.join(base, "accessibilite.json")
    
    effectifs = safe_json(effectifs_path, {})
    access = safe_json(access_path, {})
    
    # Supprimer toutes les variantes du nom
    effectifs = {k: v for k, v in effectifs.items() if k.upper() != nom.upper()}
    access = {k: v for k, v in access.items() if k.upper() != nom.upper()}
    
    with open(effectifs_path, "w", encoding="utf-8") as f:
        json.dump(effectifs, f, indent=2)
    with open(access_path, "w", encoding="utf-8") as f:
        json.dump(access, f, indent=2)
    
    return redirect("/")

# ======================
# EFFECTIFS
# ======================

@app.route("/effectifs", methods=["POST"])
def effectifs():
    base = annee_path()
    effectifs_path = os.path.join(base, "effectifs.json")
    
    # Récupérer tous les effectifs du formulaire
    effectifs = {}
    for formation, effectif_str in request.form.items():
        try:
            effectif = int(effectif_str) if effectif_str.strip() else 0
            effectifs[formation] = effectif
        except ValueError:
            effectifs[formation] = 0
    
    # Sauvegarder
    with open(effectifs_path, "w", encoding="utf-8") as f:
        json.dump(effectifs, f, indent=2)
    
    return redirect("/")

# ======================
# ACCESSIBILITÉ
# ======================

@app.route("/accessibilite", methods=["POST"])
def accessibilite():
    base = annee_path()
    access_path = os.path.join(base, "accessibilite.json")
    
    # Récupérer les données du formulaire (seulement celles cochées)
    access = {}
    for formation in request.form.keys():
        access[formation] = True
    
    # Charger les formations pour avoir la liste complète
    formations = charger_formations()
    for f in formations:
        # Si la formation n'est pas dans le formulaire, elle n'est pas accessible
        if f["nom"] not in access:
            access[f["nom"]] = False
    
    # Sauvegarder
    with open(access_path, "w", encoding="utf-8") as f:
        json.dump(access, f, indent=2)
    
    return {"status": "ok"}

@app.route("/admin/reset_imports", methods=["POST"])
def reset_imports():
    base = annee_path()

    # 🔹 Vider cours_planifies.json
    cours_path = os.path.join(base, "cours_planifies.json")
    with open(cours_path, "w", encoding="utf-8") as f:
        json.dump([], f, indent=2)

    # 🔹 Supprimer les CSV du dossier imports
    for fichier in os.listdir(IMPORTS):
        if fichier.endswith(".csv"):
            os.remove(os.path.join(IMPORTS, fichier))

    return redirect("/")


# ======================
# RUN
# ======================

if __name__ == "__main__":
    app.run(debug=True)
