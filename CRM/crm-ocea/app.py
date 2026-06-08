from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import DEFAULT_CONSUMPTION_L_100, DEFAULT_FUEL_PRICE_L
from database import get_conn, init_db
from services import (
    _enrichir_releves,
    build_mailto,
    create_share_report,
    get_dashboard_stats,
    get_ensemble,
    get_ensembles_list,
    get_filter_meta,
    get_km_stats,
    get_releves_list,
    get_setting,
    get_share_report,
    get_totals,
    import_cst_only,
    import_hoc_folder,
    import_pat_only,
    import_trn_only,
    set_setting,
    update_ensemble,
)

app = FastAPI(title="CRM H2EAUX SERVICES — OCEA", version="3.0.0")

BASE = Path(__file__).parent
HOC_DEFAULT = BASE.parent / "HOC"
STATIC = BASE / "static"

init_db()

if STATIC.exists():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")


class EnsembleUpdate(BaseModel):
    commentaires: str = ""
    code_acces: str = ""
    contacts: str = ""
    nom_ensemble: Optional[str] = None
    ville: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/api/recalculate")
def recalculate():
    conn = get_conn()
    _enrichir_releves(conn)
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/import")
def import_data(hoc_path: Optional[str] = None):
    path = Path(hoc_path) if hoc_path else HOC_DEFAULT
    if not path.exists():
        return {"ok": False, "error": f"Dossier introuvable: {path}"}
    stats = import_hoc_folder(path)
    return {"ok": True, "stats": stats, "path": str(path)}


@app.post("/api/import/pat")
def import_pat(hoc_path: Optional[str] = None):
    path = Path(hoc_path) if hoc_path else HOC_DEFAULT
    if not path.exists():
        return {"ok": False, "error": f"Dossier introuvable: {path}"}
    stats = import_pat_only(path)
    return {"ok": True, "stats": stats, "path": str(path)}


@app.post("/api/import/cst")
def import_cst(hoc_path: Optional[str] = None):
    path = Path(hoc_path) if hoc_path else HOC_DEFAULT
    if not path.exists():
        return {"ok": False, "error": f"Dossier introuvable: {path}"}
    stats = import_cst_only(path)
    return {"ok": True, "stats": stats, "path": str(path)}


@app.post("/api/import/trn")
def import_trn(hoc_path: Optional[str] = None):
    path = Path(hoc_path) if hoc_path else HOC_DEFAULT
    if not path.exists():
        return {"ok": False, "error": f"Dossier introuvable: {path}"}
    stats = import_trn_only(path)
    return {"ok": True, "stats": stats, "path": str(path)}


@app.get("/api/filters")
def filters_meta():
    return get_filter_meta()


@app.get("/api/totals")
def totals(
    categorie: Optional[str] = None,
    date: Optional[str] = None,
    code: Optional[str] = None,
):
    return get_totals(categorie, date, code)


@app.get("/api/stats")
def stats(
    date: Optional[str] = Query(None),
    categorie: Optional[str] = None,
    code: Optional[str] = None,
):
    return get_dashboard_stats(date, categorie, code)


@app.get("/api/releves")
def releves(
    categorie: Optional[str] = None,
    statut: Optional[str] = None,
    date: Optional[str] = None,
    code: Optional[str] = None,
    limit: int = 5000,
):
    return get_releves_list(categorie, statut, date, code, limit)


@app.get("/api/ensembles")
def ensembles_list():
    return get_ensembles_list()


@app.get("/api/ensembles/{code}")
def ensemble_get(code: str):
    row = get_ensemble(code)
    if not row:
        return {"ok": False, "error": "Ensemble introuvable"}
    return row


@app.put("/api/ensembles/{code}")
def ensemble_put(code: str, body: EnsembleUpdate):
    row = update_ensemble(code, body.model_dump())
    return {"ok": True, "ensemble": row}


@app.get("/api/km")
def km(date: Optional[str] = Query(None)):
    return get_km_stats(date)


@app.get("/api/settings")
def settings_get():
    return {
        "fuel_price_l": float(get_setting("fuel_price_l", str(DEFAULT_FUEL_PRICE_L))),
        "consumption_l_100": float(
            get_setting("consumption_l_100", str(DEFAULT_CONSUMPTION_L_100))
        ),
    }


@app.post("/api/settings")
def settings_post(
    fuel_price_l: float = Query(1.85),
    consumption_l_100: float = Query(7.5),
):
    set_setting("fuel_price_l", str(fuel_price_l))
    set_setting("consumption_l_100", str(consumption_l_100))
    return {"ok": True}


@app.post("/api/share")
def share(
    date: Optional[str] = Query(None),
    categorie: Optional[str] = None,
    code: Optional[str] = None,
):
    return create_share_report(date, categorie, code)


@app.get("/share/{token}", response_class=HTMLResponse)
def share_page(token: str):
    data = get_share_report(token)
    if not data:
        return HTMLResponse("<h1>Rapport introuvable</h1>", status_code=404)
    return HTMLResponse(_render_share_html(data))


@app.get("/api/mailto")
def mailto(
    request: Request,
    date: Optional[str] = Query(None),
    categorie: Optional[str] = None,
    code: Optional[str] = None,
):
    base = str(request.base_url).rstrip("/")
    return {"url": build_mailto(date, base, categorie, code)}


@app.get("/api/export/csv")
def export_csv(
    categorie: Optional[str] = None,
    statut: Optional[str] = None,
    date: Optional[str] = None,
    code: Optional[str] = None,
):
    import csv
    import io

    rows = get_releves_list(categorie, statut, date, code, limit=50000)
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys(), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=releves_ocea.csv"},
    )


def _render_share_html(data: dict) -> str:
    s = data.get("stats", {})
    k = data.get("km", {})
    rows = ""
    for r in data.get("releves", [])[:100]:
        rows += (
            f"<tr><td>{r.get('date_releve','')[:10]}</td>"
            f"<td>{r.get('categorie_label','')}</td>"
            f"<td>{r.get('statut_label','')}</td>"
            f"<td>{r.get('code_ensemble','')}</td>"
            f"<td>{r.get('montant',0):.2f} €</td></tr>"
        )
    ok_lines = "".join(
        f"<li>{label}: {n}</li>" for label, n in s.get("releves_ok_par_type", {}).items()
    )
    return f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
    <title>CRM H2EAUX SERVICES — Rapport OCEA</title>
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600&family=Outfit:wght@400;600&display=swap" rel="stylesheet">
    <style>
    body{{font-family:'Outfit',sans-serif;background:#030303;color:#f0ebe0;max-width:920px;margin:2rem auto;padding:1.5rem}}
    h1{{font-family:'Cormorant Garamond',serif;color:#d4af37;font-size:2rem}}
    h2{{color:#2ecc71;font-size:1rem;text-transform:uppercase;letter-spacing:0.1em;margin-top:1.5rem}}
    table{{border-collapse:collapse;width:100%;margin-top:0.75rem}}
    td,th{{border:1px solid rgba(212,175,55,0.2);padding:8px;font-size:0.85rem}}
    th{{background:#0f0f0f;color:#d4af37;text-align:left}}
    strong{{color:#f5d76e}}
    ul{{color:#8a8578}}
    </style></head><body>
    <h1>CRM H2EAUX SERVICES</h1>
    <p style="color:#8a8578">Comptages immobiliers &amp; maintenances · Entreprise OCEA</p>
    <p>Généré le {data.get('generated_at','')}</p>
    <h2>Financier</h2>
    <p>CA HT: <strong>{s.get('ca_total',0):.2f} €</strong></p>
    <p>TVA 20 %: {s.get('ca_tva',0):.2f} € — TTC: <strong>{s.get('ca_ttc',0):.2f} €</strong></p>
    <p>Relevés OK: {s.get('total_releves_ok',0)} | Non relevés: {s.get('total_non_releves',0)}</p>
    <ul>{ok_lines}</ul>
    <h2>Trajet</h2>
    <p>{k.get('km_total',0)} km — Carburant: {k.get('carburant',{}).get('cout_euros',0):.2f} €</p>
    <h2>Détail (100 premiers relevés)</h2>
    <table><tr><th>Date</th><th>Type</th><th>Statut</th><th>Site</th><th>Montant</th></tr>{rows}</table>
    </body></html>"""
