import xml.etree.ElementTree as ET
from pathlib import Path

from .classify import categoriser_releve


def _text(el, tag: str, default: str = "") -> str:
    node = el.find(tag)
    return (node.text or default).strip() if node is not None else default


def _distribution_type(pdc_el, find, findall) -> str:
    for compteurs in findall(pdc_el, "Compteurs"):
        for cpt in findall(compteurs, "Compteur"):
            dt = _text(cpt, "DistributionType")
            if dt:
                return dt
    return ""


def parse_pat_file(path: Path) -> dict:
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

    ensemble = find(root, "Ensembles")
    if ensemble is None:
        ensemble = root
    ensemble = find(ensemble, "Ensemble") or root

    code_ensemble = _text(ensemble, "CodeEnsemble")
    nom_ensemble = _text(ensemble, "NomEnsemble")
    ville = _text(ensemble, "Ville")
    cp = _text(ensemble, "CP")
    id_ensemble = _text(ensemble, "IDEnsemble")
    id_workflow = _text(ensemble, "IDWorkflow")
    latitude = _text(ensemble, "LatitudeGPS")
    longitude = _text(ensemble, "LongitudeGPS")

    pdcs = []
    for entrees_block in findall(ensemble, "Entrees"):
        for ent in findall(entrees_block, "Entree"):
            id_entree = _text(ent, "IDEntree")
            nom_entree = _text(ent, "NomEntree")
            for logement in findall(ent, "Logements"):
                for lgt in findall(logement, "Logement"):
                    id_lgt = _text(lgt, "IDLgt")
                    occupant = _text(lgt, "Occupant")
                    etage = _text(lgt, "Etage")
                    porte = _text(lgt, "Porte")
                    for pdc_block in findall(lgt, "PDCs"):
                        for pdc in findall(pdc_block, "PDC"):
                            type_releve = _text(pdc, "TypeReleve")
                            position = _text(pdc, "Position")
                            emplacement = _text(pdc, "Emplacement")
                            distribution_type = _distribution_type(pdc, find, findall)
                            categorie = categoriser_releve(
                                type_releve,
                                position,
                                emplacement,
                                occupant,
                                etage,
                                porte,
                                distribution_type,
                            )
                            pdcs.append(
                                {
                                    "source_file": path.name,
                                    "code_ensemble": code_ensemble,
                                    "nom_ensemble": nom_ensemble,
                                    "ville": ville,
                                    "cp": cp,
                                    "id_ensemble": id_ensemble,
                                    "id_workflow": id_workflow,
                                    "latitude": latitude,
                                    "longitude": longitude,
                                    "id_entree": id_entree,
                                    "nom_entree": nom_entree,
                                    "id_lgt": id_lgt,
                                    "occupant": occupant,
                                    "etage": etage,
                                    "porte": porte,
                                    "id_pdc": _text(pdc, "IDPdc"),
                                    "fluide": _text(pdc, "Fluide"),
                                    "type_releve": type_releve,
                                    "position": position,
                                    "emplacement": emplacement,
                                    "distribution_type": distribution_type,
                                    "a_relever": _text(pdc, "ARelever", "0"),
                                    "categorie": categorie,
                                }
                            )

    return {
        "fichier": path.name,
        "code_ensemble": code_ensemble,
        "nom_ensemble": nom_ensemble,
        "latitude": latitude,
        "longitude": longitude,
        "pdcs": pdcs,
    }
