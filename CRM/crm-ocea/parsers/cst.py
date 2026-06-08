import csv
import re
from pathlib import Path
from typing import Dict, List, Optional

from .classify import categoriser_releve, statut_releve

RE_ID_PDC = re.compile(r"IDPdc='(\d+)'")
RE_ID_LGT = re.compile(r"IDLgt='(\d+)'")
RE_ID_ENTREE = re.compile(r"IDEntree='(\d+)'")
RE_FILENAME = re.compile(
    r"(\d+)CST_([A-Z0-9]+)_(\d+)(?:_(\d+))?(?:_(\d+))?_(\d{14})"
)


def _parse_filename(name: str) -> dict:
    m = RE_FILENAME.search(name)
    if not m:
        return {}
    return {
        "seq": m.group(1),
        "code_ensemble": m.group(2),
        "id_entree": m.group(3),
        "id_extra1": m.group(4) or "",
        "id_extra2": m.group(5) or "",
        "timestamp": m.group(6),
    }


def parse_cst_file(path: Path, pdc_lookup: Optional[Dict[str, dict]] = None) -> List[dict]:
    pdc_lookup = pdc_lookup or {}
    meta = _parse_filename(path.name)
    releves: Dict[str, dict] = {}

    with path.open(encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f, delimiter=";")
        current_event_pdc = None
        last_nature = None

        for row in reader:
            if len(row) < 5:
                continue
            action, xpath, _node, field, value = row[0], row[1], row[2], row[3], row[4]

            id_pdc_m = RE_ID_PDC.search(xpath)
            if id_pdc_m:
                current_event_pdc = id_pdc_m.group(1)

            if not current_event_pdc:
                continue

            id_pdc = current_event_pdc
            if id_pdc not in releves:
                id_lgt_m = RE_ID_LGT.search(xpath)
                id_entree_m = RE_ID_ENTREE.search(xpath)
                base = pdc_lookup.get(id_pdc, {})
                releves[id_pdc] = {
                    "source_file": path.name,
                    "code_ensemble": meta.get("code_ensemble", base.get("code_ensemble", "")),
                    "id_entree": id_entree_m.group(1) if id_entree_m else base.get("id_entree", ""),
                    "id_lgt": id_lgt_m.group(1) if id_lgt_m else base.get("id_lgt", ""),
                    "id_pdc": id_pdc,
                    "nom_ensemble": base.get("nom_ensemble", ""),
                    "ville": base.get("ville", ""),
                    "occupant": base.get("occupant", ""),
                    "etage": base.get("etage", ""),
                    "porte": base.get("porte", ""),
                    "fluide": base.get("fluide", ""),
                    "type_releve": base.get("type_releve", ""),
                    "position": base.get("position", ""),
                    "emplacement": base.get("emplacement", ""),
                    "distribution_type": base.get("distribution_type", ""),
                    "categorie": base.get("categorie", "AUTRE"),
                    "date_releve": "",
                    "index": "",
                    "conso": "",
                    "code_obs": "",
                    "lib_obs": "",
                    "nature_index": "",
                    "nature_conso": "",
                    "timestamp_fichier": meta.get("timestamp", ""),
                }

            rec = releves[id_pdc]

            if field == "Date" and action in ("ADD", "UPDATE"):
                rec["date_releve"] = value
            elif field == "Fluide":
                rec["fluide"] = value
            elif field == "Nature":
                last_nature = value
                if value in ("IndexReel", "Pas d'index"):
                    rec["nature_index"] = value
                elif value in ("ConsoReel", "Pas de conso"):
                    rec["nature_conso"] = value
            elif field == "Val" and last_nature:
                if last_nature == "IndexReel":
                    rec["index"] = value
                elif last_nature == "ConsoReel":
                    rec["conso"] = value
            elif field == "ValeurCodeObs":
                rec["code_obs"] = value
            elif field == "LibCodeObs":
                rec["lib_obs"] = value

    results = []
    for rec in releves.values():
        if not rec.get("categorie") or rec["categorie"] == "AUTRE":
            rec["categorie"] = categoriser_releve(
                rec.get("type_releve", ""),
                rec.get("position", ""),
                rec.get("emplacement", ""),
                rec.get("occupant", ""),
                rec.get("etage", ""),
                rec.get("porte", ""),
                rec.get("distribution_type", ""),
            )
        rec["statut_releve"] = statut_releve(
            rec.get("nature_index", ""),
            rec.get("index", ""),
            rec.get("categorie", ""),
        )
        results.append(rec)

    return results
