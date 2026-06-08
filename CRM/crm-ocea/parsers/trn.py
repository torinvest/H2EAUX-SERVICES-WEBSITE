import xml.etree.ElementTree as ET
from pathlib import Path


def _text(el, tag: str, default: str = "") -> str:
    node = el.find(tag)
    return (node.text or default).strip() if node is not None else default


def parse_trn_file(path: Path) -> dict:
    tree = ET.parse(path)
    root = tree.getroot()
    ns = {"ns": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}

    def find(parent, tag):
        if ns:
            return parent.find(f"ns:{tag}", ns) or parent.find(tag)
        return parent.find(tag)

    def findall(parent, tag):
        if ns:
            return parent.findall(f"ns:{tag}", ns) or parent.findall(tag)
        return parent.findall(tag)

    tournees = []
    for tournee in findall(root, "Tournee"):
        ensemble = find(tournee, "Ensemble")
        client = find(tournee, "Client")
        planning = find(tournee, "Planning")
        recap = {}

        for recap_fluide in findall(tournee, "RecapFluide"):
            for fluide in findall(recap_fluide, "Fluide"):
                code = _text(fluide, "CodeFluide")
                recap[code] = {
                    "nb_int": int(_text(fluide, "NbInt", "0") or 0),
                    "nb_ext": int(_text(fluide, "NbExt", "0") or 0),
                    "nb_rad": int(_text(fluide, "NbRad", "0") or 0),
                    "nb_tot": int(_text(fluide, "NbTot", "0") or 0),
                }

        tournees.append(
            {
                "fichier": path.name,
                "num_tournee": _text(tournee, "Numtournee"),
                "fichier_pat": _text(tournee, "FichierPAT"),
                "code_ensemble": _text(ensemble, "CodeEnsemble") if ensemble else "",
                "nom_ensemble": _text(ensemble, "NomEnsemble") if ensemble else "",
                "ville": _text(ensemble, "Ville") if ensemble else "",
                "cp": _text(ensemble, "CP") if ensemble else "",
                "adresse1": _text(ensemble, "Adresse1") if ensemble else "",
                "id_ensemble": _text(ensemble, "IDEnsemble") if ensemble else "",
                "nb_pdc_cible": int(_text(ensemble, "NbPdcCible", "0") or 0),
                "latitude": _text(ensemble, "LatitudeGPS") if ensemble else "",
                "longitude": _text(ensemble, "LongitudeGPS") if ensemble else "",
                "client_nom": _text(client, "Nom") if client else "",
                "client_contact": _text(client, "NomContact") if client else "",
                "client_tel": _text(client, "Tel") if client else "",
                "client_mobile": _text(client, "Mobile") if client else "",
                "client_email": _text(client, "Email") if client else "",
                "planning_debut": _text(planning, "Debut") if planning else "",
                "planning_fin": _text(planning, "Fin") if planning else "",
                "recap_fluides": recap,
            }
        )

    return {"fichier": path.name, "tournees": tournees}
