"""Tarifs et paramètres OCEA."""

from parsers.classify import (
    COMPTEUR_GENERAL,
    RADIO_DISTANCE,
    VISUEL_GPA,
    VISUEL_LOGEMENT,
)

# Tarifs unitaires HT (euros) — relevé OK uniquement
TARIFS = {
    VISUEL_LOGEMENT: 0.84,
    VISUEL_GPA: 0.70,
    RADIO_DISTANCE: 0.40,
    COMPTEUR_GENERAL: 6.00,
}

# TVA France
TVA_TAUX = 0.20

# Paramètres véhicule / carburant (modifiables dans le CRM)
DEFAULT_FUEL_PRICE_L = 1.85  # €/litre
DEFAULT_CONSUMPTION_L_100 = 7.5  # litres / 100 km
