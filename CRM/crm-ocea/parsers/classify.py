"""Classification des types de relevé OCEA / Harmonie HOC."""

VISUEL_LOGEMENT = "VISUEL_LOGEMENT"
VISUEL_GPA = "VISUEL_GPA"
RADIO_DISTANCE = "RADIO_DISTANCE"
COMPTEUR_GENERAL = "COMPTEUR_GENERAL"
AUTRE = "AUTRE"

RELEVE_OK = "RELEVE_OK"
NON_RELEVE = "NON_RELEVE"

LABELS = {
    VISUEL_LOGEMENT: "Visuel logement",
    VISUEL_GPA: "Visuel extérieur GPA",
    RADIO_DISTANCE: "Radio à distance",
    COMPTEUR_GENERAL: "Compteur général",
    AUTRE: "Autre / non classé (PAT absent)",
}

# Libellé affiché quand un « Autre » relevé OK est facturé en GPA (≈90 % des cas)
LABEL_GPA_ESTIME = "Visuel extérieur GPA (estimé, PAT absent)"

STATUT_LABELS = {
    RELEVE_OK: "Relevé (index OK — facturable)",
    NON_RELEVE: "Non relevé (sans index)",
}


def label_facture(categorie_facture: str, gpa_estime: bool) -> str:
    if gpa_estime:
        return LABEL_GPA_ESTIME
    return LABELS.get(categorie_facture, categorie_facture)


def categorie_pour_facturation(categorie: str, statut: str) -> tuple:
    """
    Règle métier OCEA : les relevés « Autre » (PAT manquant) avec index
    sont facturés en GPA à 0,70 € (~90 % des cas terrain).
    Retourne (categorie_facture, gpa_estime).
    """
    if statut == RELEVE_OK and categorie == AUTRE:
        return VISUEL_GPA, True
    return categorie, False


def est_compteur_general(
    occupant: str,
    etage: str,
    porte: str,
    distribution_type: str,
) -> bool:
    occ = (occupant or "").upper()
    dt = (distribution_type or "").lower()
    porte_u = (porte or "").upper()

    if "COMPTEUR GENERAL" in occ or "COMPTEUR GÉNÉRAL" in occ:
        return True
    if dt in ("général", "general"):
        return True
    if ":CG" in porte_u or porte_u in ("CG", "L:CG"):
        return True
    # Étage -1 / sous-sol : compteur général si libellé explicite ou porte CG
    if (etage or "").strip() == "-1" and (
        "COMPTEUR" in occ or ":CG" in porte_u or dt in ("général", "general")
    ):
        return True
    return False


def categoriser_releve(
    type_releve: str,
    position: str,
    emplacement: str,
    occupant: str = "",
    etage: str = "",
    porte: str = "",
    distribution_type: str = "",
) -> str:
    if est_compteur_general(occupant, etage, porte, distribution_type):
        return COMPTEUR_GENERAL

    tr = (type_releve or "").lower()
    pos = (position or "").lower()
    emp = (emplacement or "").strip().upper()

    if "radio" in tr or "telereleve" in tr or "uhf" in tr:
        return RADIO_DISTANCE

    if "visuel" in tr:
        if emp == "GPA" or pos == "exterieur":
            return VISUEL_GPA
        return VISUEL_LOGEMENT

    return AUTRE


def statut_releve(nature_index: str, index_val: str, categorie: str) -> str:
    """
    Relevé OK = index réel saisi (facturable).
    Non relevé = 'Pas d'index' ou passage sans valeur.
    """
    idx = (index_val or "").strip()
    nature = (nature_index or "").strip()

    if nature == "IndexReel" and idx:
        return RELEVE_OK
    if nature == "Pas d'index":
        return NON_RELEVE
    # Radio : index présent même si nature absente (import partiel)
    if categorie == RADIO_DISTANCE and idx:
        return RELEVE_OK
    if nature == "IndexReel" and not idx:
        return NON_RELEVE
    return NON_RELEVE
