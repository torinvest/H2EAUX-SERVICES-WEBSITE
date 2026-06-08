"""Calcul distances GPS entre sites de tournée."""

import math
from typing import List, Optional, Tuple


def parse_coord(value: str) -> Optional[float]:
    if not value:
        return None
    try:
        return float(str(value).replace(",", ".").strip())
    except ValueError:
        return None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def trajet_km(sites: List[dict]) -> Tuple[float, List[dict]]:
    """
    sites: liste triée par heure avec latitude, longitude, code_ensemble, nom_ensemble, planning_debut
    Retourne km total + détail des segments.
    """
    segments = []
    total = 0.0
    prev = None

    for site in sites:
        lat = parse_coord(site.get("latitude", ""))
        lon = parse_coord(site.get("longitude", ""))
        if lat is None or lon is None:
            continue
        if prev:
            km = haversine_km(prev["lat"], prev["lon"], lat, lon)
            total += km
            segments.append(
                {
                    "de": prev["code_ensemble"],
                    "de_nom": prev["nom_ensemble"],
                    "de_heure": prev["planning_debut"],
                    "vers": site.get("code_ensemble", ""),
                    "vers_nom": site.get("nom_ensemble", ""),
                    "vers_heure": site.get("planning_debut", ""),
                    "km": round(km, 2),
                }
            )
        prev = {
            "lat": lat,
            "lon": lon,
            "code_ensemble": site.get("code_ensemble", ""),
            "nom_ensemble": site.get("nom_ensemble", ""),
            "planning_debut": site.get("planning_debut", ""),
        }

    return round(total, 2), segments


def cout_carburant(km: float, prix_litre: float, conso_l_100: float) -> dict:
    litres = (km / 100.0) * conso_l_100
    cout = litres * prix_litre
    return {
        "km": km,
        "litres": round(litres, 2),
        "cout_euros": round(cout, 2),
        "prix_litre": prix_litre,
        "conso_l_100": conso_l_100,
    }
