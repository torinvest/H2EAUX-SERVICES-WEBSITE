import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

from config import (
    DEFAULT_CONSUMPTION_L_100,
    DEFAULT_FUEL_PRICE_L,
    TARIFS,
    TVA_TAUX,
)
from database import get_conn
from geo import cout_carburant, trajet_km
from parsers import parse_cst_file, parse_pat_file, parse_trn_file
from parsers.classify import (
    AUTRE,
    COMPTEUR_GENERAL,
    LABELS,
    RADIO_DISTANCE,
    RELEVE_OK,
    STATUT_LABELS,
    VISUEL_GPA,
    VISUEL_LOGEMENT,
    categorie_pour_facturation,
    categoriser_releve,
    label_facture,
    statut_releve,
)

CAT_FILTER_LABELS = {
    VISUEL_GPA: "Visuel extérieur GPA",
    VISUEL_LOGEMENT: "Visuel logement",
    RADIO_DISTANCE: "Radio à distance",
    COMPTEUR_GENERAL: "Compteur général",
}


def _montant(categorie_facture: str, statut: str) -> float:
    if statut != RELEVE_OK:
        return 0.0
    return TARIFS.get(categorie_facture, 0.0)


def get_setting(key: str, default: str = "") -> str:
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
    )
    conn.commit()
    conn.close()


def _log_import(conn, type_import: str, fichier_count: int, detail: str):
    conn.execute(
        "INSERT INTO import_log (type_import, fichier_count, detail, created_at) VALUES (?,?,?,?)",
        (type_import, fichier_count, detail, datetime.now().isoformat()),
    )


def _pdc_lookup_from_db(conn) -> Dict[str, dict]:
    rows = conn.execute("SELECT * FROM patrimoine").fetchall()
    return {row["id_pdc"]: dict(row) for row in rows}


def _format_contacts_trn(t: dict) -> str:
    parts = []
    if t.get("client_contact"):
        parts.append(t["client_contact"])
    if t.get("client_tel"):
        parts.append(f"Tel: {t['client_tel']}")
    if t.get("client_mobile"):
        parts.append(f"Mobile: {t['client_mobile']}")
    if t.get("client_email"):
        parts.append(t["client_email"])
    return "\n".join(parts)


def _upsert_ensemble_from_pat(conn, p: dict):
    code = (p.get("code_ensemble") or "").strip()
    if not code:
        return
    conn.execute(
        """
        INSERT INTO ensembles (code_ensemble, nom_ensemble, ville, cp, updated_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        ON CONFLICT(code_ensemble) DO UPDATE SET
            nom_ensemble = COALESCE(NULLIF(excluded.nom_ensemble, ''), ensembles.nom_ensemble),
            ville = COALESCE(NULLIF(excluded.ville, ''), ensembles.ville),
            cp = COALESCE(NULLIF(excluded.cp, ''), ensembles.cp),
            updated_at = datetime('now')
        """,
        (code, p.get("nom_ensemble", ""), p.get("ville", ""), p.get("cp", "")),
    )


def _upsert_ensemble_from_trn(conn, t: dict):
    code = (t.get("code_ensemble") or "").strip()
    if not code:
        return
    contacts = _format_contacts_trn(t)
    conn.execute(
        """
        INSERT INTO ensembles
        (code_ensemble, nom_ensemble, ville, cp, adresse, client_nom, client_tel,
         client_email, contacts, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(code_ensemble) DO UPDATE SET
            nom_ensemble = COALESCE(NULLIF(excluded.nom_ensemble, ''), ensembles.nom_ensemble),
            ville = COALESCE(NULLIF(excluded.ville, ''), ensembles.ville),
            cp = COALESCE(NULLIF(excluded.cp, ''), ensembles.cp),
            adresse = COALESCE(NULLIF(excluded.adresse, ''), ensembles.adresse),
            client_nom = COALESCE(NULLIF(excluded.client_nom, ''), ensembles.client_nom),
            client_tel = COALESCE(NULLIF(excluded.client_tel, ''), ensembles.client_tel),
            client_email = COALESCE(NULLIF(excluded.client_email, ''), ensembles.client_email),
            contacts = CASE
                WHEN ensembles.contacts = '' AND excluded.contacts != '' THEN excluded.contacts
                ELSE ensembles.contacts
            END,
            updated_at = datetime('now')
        """,
        (
            code,
            t.get("nom_ensemble", ""),
            t.get("ville", ""),
            t.get("cp", ""),
            t.get("adresse1", ""),
            t.get("client_nom", ""),
            t.get("client_tel", "") or t.get("client_mobile", ""),
            t.get("client_email", ""),
            contacts,
        ),
    )


def _insert_pat_pdc(conn, p: dict):
    conn.execute(
        """
        INSERT OR REPLACE INTO patrimoine VALUES
        (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            p["id_pdc"],
            p["code_ensemble"],
            p["nom_ensemble"],
            p["ville"],
            p["cp"],
            p["id_ensemble"],
            p["id_workflow"],
            p["id_entree"],
            p["nom_entree"],
            p["id_lgt"],
            p["occupant"],
            p["etage"],
            p["porte"],
            p["fluide"],
            p["type_releve"],
            p["position"],
            p["emplacement"],
            p.get("distribution_type", ""),
            p.get("latitude", ""),
            p.get("longitude", ""),
            p["categorie"],
            int(p["a_relever"] or 0),
            p["source_file"],
            datetime.now().isoformat(),
        ),
    )
    _upsert_ensemble_from_pat(conn, p)


def _insert_releve(conn, r: dict, pat_trouve: int) -> bool:
    st = r.get("statut_releve", "NON_RELEVE")
    cat = r.get("categorie", AUTRE)
    cat_f, estime = categorie_pour_facturation(cat, st)
    mnt = _montant(cat_f, st)
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO releves
        (id_pdc, code_ensemble, nom_ensemble, ville, id_entree, id_lgt,
         occupant, etage, porte, fluide, type_releve, position, emplacement,
         distribution_type, categorie, categorie_facture, gpa_estime, pat_trouve,
         statut_releve, montant, date_releve, index_val, conso, code_obs, lib_obs,
         nature_index, nature_conso, source_file, timestamp_fichier)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            r["id_pdc"],
            r["code_ensemble"],
            r["nom_ensemble"],
            r["ville"],
            r["id_entree"],
            r["id_lgt"],
            r.get("occupant", ""),
            r.get("etage", ""),
            r.get("porte", ""),
            r["fluide"],
            r["type_releve"],
            r["position"],
            r["emplacement"],
            r.get("distribution_type", ""),
            cat,
            cat_f,
            1 if estime else 0,
            pat_trouve,
            st,
            mnt,
            r["date_releve"],
            r["index"],
            r["conso"],
            r["code_obs"],
            r["lib_obs"],
            r["nature_index"],
            r["nature_conso"],
            r["source_file"],
            r["timestamp_fichier"],
        ),
    )
    return conn.total_changes > 0


def _enrichir_releves(conn):
    conn.execute(
        """
        UPDATE releves SET
            occupant = COALESCE(NULLIF(releves.occupant,''), p.occupant),
            etage = COALESCE(NULLIF(releves.etage,''), p.etage),
            porte = COALESCE(NULLIF(releves.porte,''), p.porte),
            distribution_type = COALESCE(NULLIF(releves.distribution_type,''), p.distribution_type),
            type_releve = COALESCE(NULLIF(releves.type_releve,''), p.type_releve),
            position = COALESCE(NULLIF(releves.position,''), p.position),
            emplacement = COALESCE(NULLIF(releves.emplacement,''), p.emplacement),
            nom_ensemble = COALESCE(NULLIF(releves.nom_ensemble,''), p.nom_ensemble),
            ville = COALESCE(NULLIF(releves.ville,''), p.ville),
            code_ensemble = COALESCE(NULLIF(releves.code_ensemble,''), p.code_ensemble),
            categorie = p.categorie,
            pat_trouve = 1
        FROM patrimoine p
        WHERE p.id_pdc = releves.id_pdc
        """
    )
    conn.execute(
        """
        UPDATE releves SET pat_trouve = 0
        WHERE id_pdc NOT IN (SELECT id_pdc FROM patrimoine)
        """
    )
    rows = conn.execute(
        "SELECT id, nature_index, index_val, categorie, occupant, etage, porte, "
        "distribution_type, type_releve, position, emplacement FROM releves"
    ).fetchall()
    for row in rows:
        cat = row["categorie"]
        if not cat or cat == AUTRE:
            cat = categoriser_releve(
                row["type_releve"] or "",
                row["position"] or "",
                row["emplacement"] or "",
                row["occupant"] or "",
                row["etage"] or "",
                row["porte"] or "",
                row["distribution_type"] or "",
            )
        st = statut_releve(row["nature_index"] or "", row["index_val"] or "", cat)
        cat_f, estime = categorie_pour_facturation(cat, st)
        mnt = _montant(cat_f, st)
        conn.execute(
            """
            UPDATE releves SET categorie=?, categorie_facture=?, gpa_estime=?,
            statut_releve=?, montant=? WHERE id=?
            """,
            (cat, cat_f, 1 if estime else 0, st, mnt, row["id"]),
        )


def import_pat_only(hoc_path: Path) -> dict:
    pat_dir = hoc_path / "DBXML" / "PAT"
    conn = get_conn()
    stats = {"pat": 0, "pdcs": 0, "ensembles": 0}
    codes = set()
    if pat_dir.exists():
        for f in pat_dir.glob("PAT_*.xml"):
            data = parse_pat_file(f)
            for p in data["pdcs"]:
                _insert_pat_pdc(conn, p)
                stats["pdcs"] += 1
                if p.get("code_ensemble"):
                    codes.add(p["code_ensemble"])
            stats["pat"] += 1
    stats["ensembles"] = len(codes)
    _log_import(conn, "PAT", stats["pat"], f"{stats['pdcs']} PDC, {stats['ensembles']} ensembles")
    conn.commit()
    conn.close()
    return stats


def import_trn_only(hoc_path: Path) -> dict:
    trn_dir = hoc_path / "DBXML" / "TRN"
    conn = get_conn()
    stats = {"trn": 0, "tournees": 0}
    if trn_dir.exists():
        for f in trn_dir.glob("TRN_*.xml"):
            data = parse_trn_file(f)
            for t in data["tournees"]:
                _upsert_ensemble_from_trn(conn, t)
                recap = t.get("recap_fluides", {})
                totals = {"nb_int": 0, "nb_ext": 0, "nb_rad": 0}
                for fluide_data in recap.values():
                    totals["nb_int"] += fluide_data.get("nb_int", 0)
                    totals["nb_ext"] += fluide_data.get("nb_ext", 0)
                    totals["nb_rad"] += fluide_data.get("nb_rad", 0)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO tournees
                    (num_tournee, fichier, fichier_pat, code_ensemble, nom_ensemble,
                     ville, cp, id_ensemble, nb_pdc_cible, client_nom,
                     planning_debut, planning_fin, latitude, longitude,
                     nb_int, nb_ext, nb_rad)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        t["num_tournee"],
                        t["fichier"],
                        t["fichier_pat"],
                        t["code_ensemble"],
                        t["nom_ensemble"],
                        t["ville"],
                        t["cp"],
                        t["id_ensemble"],
                        t["nb_pdc_cible"],
                        t["client_nom"],
                        t["planning_debut"],
                        t["planning_fin"],
                        t.get("latitude", ""),
                        t.get("longitude", ""),
                        totals["nb_int"],
                        totals["nb_ext"],
                        totals["nb_rad"],
                    ),
                )
                stats["tournees"] += 1
            stats["trn"] += 1
    _log_import(conn, "TRN", stats["trn"], f"{stats['tournees']} tournées")
    conn.commit()
    conn.close()
    return stats


def import_cst_only(hoc_path: Path) -> dict:
    cst_dir = hoc_path / "DBXML" / "CST"
    conn = get_conn()
    pdc_lookup = _pdc_lookup_from_db(conn)
    stats = {"cst": 0, "releves": 0, "sans_pat": 0}
    if cst_dir.exists():
        for f in cst_dir.glob("*CST_*.csv"):
            releves = parse_cst_file(f, pdc_lookup)
            for r in releves:
                pat_trouve = 1 if r["id_pdc"] in pdc_lookup else 0
                if _insert_releve(conn, r, pat_trouve):
                    stats["releves"] += 1
            stats["cst"] += 1
    _enrichir_releves(conn)
    stats["sans_pat"] = conn.execute(
        """
        SELECT COUNT(*) FROM releves
        WHERE pat_trouve = 0 AND statut_releve = 'RELEVE_OK'
        """
    ).fetchone()[0]
    _log_import(
        conn,
        "CST",
        stats["cst"],
        f"{stats['releves']} relevés, {stats['sans_pat']} OK sans PAT",
    )
    conn.commit()
    conn.close()
    return stats


def import_hoc_folder(hoc_path: Path) -> dict:
    pat = import_pat_only(hoc_path)
    trn = import_trn_only(hoc_path)
    cst = import_cst_only(hoc_path)
    return {"pat": pat["pat"], "trn": trn["trn"], "cst": cst["cst"], "releves": cst["releves"], "sans_pat": cst["sans_pat"]}


def _filter_clause(
    categorie: Optional[str] = None,
    statut: Optional[str] = None,
    date_filter: Optional[str] = None,
    code_ensemble: Optional[str] = None,
    ok_only: bool = False,
) -> tuple:
    clauses = []
    params: list = []
    if categorie:
        clauses.append("categorie_facture = ?")
        params.append(categorie)
    if statut:
        clauses.append("statut_releve = ?")
        params.append(statut)
    if ok_only:
        clauses.append("statut_releve = 'RELEVE_OK'")
    if date_filter:
        clauses.append("date(date_releve) = date(?)")
        params.append(date_filter)
    if code_ensemble:
        clauses.append("code_ensemble = ?")
        params.append(code_ensemble)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def get_filter_meta() -> dict:
    conn = get_conn()
    dates = [
        r[0]
        for r in conn.execute(
            """
            SELECT DISTINCT date(date_releve) FROM releves
            WHERE date_releve != '' ORDER BY 1 DESC
            """
        ).fetchall()
    ]
    codes = [
        dict(r)
        for r in conn.execute(
            """
            SELECT DISTINCT r.code_ensemble,
                   COALESCE(e.nom_ensemble, r.nom_ensemble, '') AS nom_ensemble,
                   COALESCE(e.ville, r.ville, '') AS ville
            FROM releves r
            LEFT JOIN ensembles e ON e.code_ensemble = r.code_ensemble
            WHERE r.code_ensemble != ''
            UNION
            SELECT code_ensemble, nom_ensemble, ville FROM ensembles
            WHERE code_ensemble != ''
            ORDER BY code_ensemble
            """
        ).fetchall()
    ]
    conn.close()
    return {
        "dates": dates,
        "codes": codes,
        "categories": [{"key": k, "label": v} for k, v in CAT_FILTER_LABELS.items()],
    }


def get_totals(
    categorie: Optional[str] = None,
    date_filter: Optional[str] = None,
    code_ensemble: Optional[str] = None,
) -> dict:
    conn = get_conn()

    def _sum(where: str, params: list) -> dict:
        row = conn.execute(
            f"SELECT COUNT(*) AS n, COALESCE(SUM(montant), 0) AS ht FROM releves {where}",
            params,
        ).fetchone()
        ht = round(row["ht"] or 0, 2)
        tva = round(ht * TVA_TAUX, 2)
        return {"count": row["n"], "montant_ht": ht, "tva": tva, "montant_ttc": round(ht + tva, 2)}

    where_global, params_global = _filter_clause(
        date_filter=date_filter, code_ensemble=code_ensemble, ok_only=True
    )
    global_ok = _sum(where_global, params_global)

    where_filtre, params_filtre = _filter_clause(
        categorie=categorie,
        date_filter=date_filter,
        code_ensemble=code_ensemble,
        ok_only=True,
    )
    filtre_actif = _sum(where_filtre, params_filtre) if categorie else None

    par_categorie = {}
    for cat_key, cat_label in CAT_FILTER_LABELS.items():
        w, p = _filter_clause(
            categorie=cat_key,
            date_filter=date_filter,
            code_ensemble=code_ensemble,
            ok_only=True,
        )
        row = conn.execute(
            f"SELECT COUNT(*) AS n, COALESCE(SUM(montant), 0) AS ht FROM releves {w}",
            p,
        ).fetchone()
        par_categorie[cat_key] = {
            "label": cat_label,
            "count": row["n"],
            "montant_ht": round(row["ht"] or 0, 2),
        }

    sans_pat = conn.execute(
        """
        SELECT COUNT(*) FROM releves
        WHERE pat_trouve = 0 AND statut_releve = 'RELEVE_OK'
        """
    ).fetchone()[0]
    conn.close()

    return {
        "filtre_categorie": filtre_actif,
        "filtre_categorie_label": CAT_FILTER_LABELS.get(categorie, "") if categorie else "",
        "par_categorie": par_categorie,
        "global": global_ok,
        "tva_taux": TVA_TAUX,
        "sans_pat_ok": sans_pat,
    }


def get_dashboard_stats(
    date_filter: Optional[str] = None,
    categorie: Optional[str] = None,
    code_ensemble: Optional[str] = None,
) -> dict:
    conn = get_conn()
    where, params = _filter_clause(
        categorie=categorie,
        date_filter=date_filter,
        code_ensemble=code_ensemble,
    )

    finance = conn.execute(
        f"""
        SELECT categorie_facture, gpa_estime, statut_releve,
               COUNT(*) as n, SUM(montant) as total
        FROM releves {where if where else 'WHERE 1=1'}
        GROUP BY categorie_facture, gpa_estime, statut_releve
        """,
        params,
    ).fetchall()

    by_cat_ok = {}
    by_cat_ko = {}
    ca_total = 0.0
    gpa_estime_count = 0
    for row in finance:
        label = label_facture(row["categorie_facture"], bool(row["gpa_estime"]))
        if row["statut_releve"] == RELEVE_OK:
            by_cat_ok[label] = by_cat_ok.get(label, 0) + row["n"]
            ca_total += row["total"] or 0
            if row["gpa_estime"]:
                gpa_estime_count += row["n"]
        else:
            by_cat_ko[label] = by_cat_ko.get(label, 0) + row["n"]

    ok_where, ok_params = _filter_clause(
        categorie=categorie,
        date_filter=date_filter,
        code_ensemble=code_ensemble,
        statut=RELEVE_OK,
    )
    ko_where, ko_params = _filter_clause(
        categorie=categorie,
        date_filter=date_filter,
        code_ensemble=code_ensemble,
        statut="NON_RELEVE",
    )

    total_ok = conn.execute(
        f"SELECT COUNT(*) FROM releves {ok_where}", ok_params
    ).fetchone()[0]
    total_ko = conn.execute(
        f"SELECT COUNT(*) FROM releves {ko_where}", ko_params
    ).fetchone()[0]

    patrimoine = conn.execute(
        """
        SELECT categorie, COUNT(*) as total FROM patrimoine
        WHERE a_relever = 1 GROUP BY categorie
        """
    ).fetchall()

    hist_where, hist_params = _filter_clause(
        categorie=categorie,
        date_filter=date_filter,
        code_ensemble=code_ensemble,
    )
    historique = conn.execute(
        f"""
        SELECT date(date_releve) as jour, categorie_facture, statut_releve,
               COUNT(*) as n, SUM(montant) as ca
        FROM releves
        WHERE date_releve != '' {hist_where.replace('WHERE', 'AND') if hist_where else ''}
        GROUP BY jour, categorie_facture, statut_releve
        ORDER BY jour DESC LIMIT 60
        """,
        hist_params,
    ).fetchall()

    conn.close()

    ca_ht = round(ca_total, 2)
    tva = round(ca_ht * TVA_TAUX, 2)
    totals = get_totals(categorie, date_filter, code_ensemble)

    return {
        "releves_ok_par_type": by_cat_ok,
        "releves_non_ok_par_type": by_cat_ko,
        "ca_total": ca_ht,
        "ca_tva": tva,
        "ca_ttc": round(ca_ht + tva, 2),
        "tva_taux": TVA_TAUX,
        "totals": totals,
        "gpa_estime_count": gpa_estime_count,
        "regle_gpa_estime": "Autre + index OK → facturé GPA 0,70 € (PAT absent)",
        "tarifs": {LABELS.get(k, k): v for k, v in TARIFS.items()},
        "total_releves_ok": total_ok,
        "total_non_releves": total_ko,
        "patrimoine_a_relever": {
            LABELS.get(r["categorie"], r["categorie"]): r["total"] for r in patrimoine
        },
        "historique": [
            {
                "jour": r["jour"],
                "categorie": CAT_FILTER_LABELS.get(
                    r["categorie_facture"], r["categorie_facture"]
                ),
                "statut": STATUT_LABELS.get(r["statut_releve"], r["statut_releve"]),
                "n": r["n"],
                "ca": round(r["ca"] or 0, 2),
            }
            for r in historique
        ],
    }


def get_releves_list(
    categorie: Optional[str] = None,
    statut: Optional[str] = None,
    date_filter: Optional[str] = None,
    code_ensemble: Optional[str] = None,
    limit: int = 5000,
) -> List[dict]:
    conn = get_conn()
    where, params = _filter_clause(categorie, statut, date_filter, code_ensemble)
    rows = conn.execute(
        f"""
        SELECT id, id_pdc, code_ensemble, nom_ensemble, ville, fluide,
               categorie, categorie_facture, gpa_estime, pat_trouve, statut_releve, montant,
               date_releve, index_val, conso, lib_obs, nature_index, type_releve,
               emplacement, position, occupant, etage, porte, distribution_type
        FROM releves {where}
        ORDER BY date_releve DESC, code_ensemble
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()
    conn.close()
    return [
        {
            **dict(r),
            "categorie_label": label_facture(
                r["categorie_facture"] or r["categorie"],
                bool(r["gpa_estime"]),
            ),
            "statut_label": STATUT_LABELS.get(r["statut_releve"], r["statut_releve"]),
        }
        for r in rows
    ]


def get_ensembles_list() -> List[dict]:
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT e.*,
               (SELECT COUNT(*) FROM releves r
                WHERE r.code_ensemble = e.code_ensemble AND r.statut_releve = 'RELEVE_OK') AS nb_releves_ok,
               (SELECT COALESCE(SUM(montant), 0) FROM releves r
                WHERE r.code_ensemble = e.code_ensemble AND r.statut_releve = 'RELEVE_OK') AS ca_ht
        FROM ensembles e
        ORDER BY e.code_ensemble
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_ensemble(code: str) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM ensembles WHERE code_ensemble = ?", (code,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_ensemble(code: str, data: dict) -> dict:
    conn = get_conn()
    conn.execute(
        """
        UPDATE ensembles SET
            commentaires = ?,
            code_acces = ?,
            contacts = ?,
            nom_ensemble = COALESCE(?, nom_ensemble),
            ville = COALESCE(?, ville),
            updated_at = datetime('now')
        WHERE code_ensemble = ?
        """,
        (
            data.get("commentaires", ""),
            data.get("code_acces", ""),
            data.get("contacts", ""),
            data.get("nom_ensemble"),
            data.get("ville"),
            code,
        ),
    )
    if conn.total_changes == 0:
        conn.execute(
            """
            INSERT INTO ensembles (code_ensemble, commentaires, code_acces, contacts,
                                   nom_ensemble, ville, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                code,
                data.get("commentaires", ""),
                data.get("code_acces", ""),
                data.get("contacts", ""),
                data.get("nom_ensemble", ""),
                data.get("ville", ""),
            ),
        )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM ensembles WHERE code_ensemble = ?", (code,)
    ).fetchone()
    conn.close()
    return dict(row)


def get_km_stats(date_filter: Optional[str] = None) -> dict:
    conn = get_conn()
    clauses = ["latitude != ''", "longitude != ''", "planning_debut != ''"]
    params: list = []
    if date_filter:
        clauses.append("date(planning_debut) = date(?)")
        params.append(date_filter)
    where = " WHERE " + " AND ".join(clauses)
    rows = conn.execute(
        f"""
        SELECT code_ensemble, nom_ensemble, ville, planning_debut, latitude, longitude
        FROM tournees {where}
        ORDER BY planning_debut ASC
        """,
        params,
    ).fetchall()
    conn.close()

    sites = [dict(r) for r in rows]
    km_total, segments = trajet_km(sites)

    prix = float(get_setting("fuel_price_l", str(DEFAULT_FUEL_PRICE_L)))
    conso = float(get_setting("consumption_l_100", str(DEFAULT_CONSUMPTION_L_100)))
    carburant = cout_carburant(km_total, prix, conso)

    ca = get_dashboard_stats(date_filter).get("ca_total", 0)
    marge = round(ca - carburant["cout_euros"], 2)

    return {
        "km_total": km_total,
        "nb_sites": len(sites),
        "segments": segments,
        "carburant": carburant,
        "ca_jour": ca,
        "marge_apres_carburant": marge,
    }


def create_share_report(
    date_filter: Optional[str] = None,
    categorie: Optional[str] = None,
    code_ensemble: Optional[str] = None,
) -> dict:
    payload = {
        "generated_at": datetime.now().isoformat(),
        "stats": get_dashboard_stats(date_filter, categorie, code_ensemble),
        "km": get_km_stats(date_filter),
        "releves": get_releves_list(
            categorie=categorie,
            date_filter=date_filter,
            code_ensemble=code_ensemble,
            limit=500,
        ),
    }
    token = str(uuid.uuid4())[:8]
    conn = get_conn()
    conn.execute(
        "INSERT INTO share_reports (token, created_at, payload) VALUES (?,?,?)",
        (token, payload["generated_at"], json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()
    return {"token": token, "payload": payload}


def get_share_report(token: str) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT payload FROM share_reports WHERE token = ?", (token,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return json.loads(row["payload"])


def build_mailto(
    date_filter: Optional[str],
    base_url: str,
    categorie: Optional[str] = None,
    code_ensemble: Optional[str] = None,
) -> str:
    stats = get_dashboard_stats(date_filter, categorie, code_ensemble)
    km = get_km_stats(date_filter)
    share = create_share_report(date_filter, categorie, code_ensemble)
    link = f"{base_url}/share/{share['token']}"
    subject = f"Rapport OCEA relevés {date_filter or 'global'}"
    body = (
        f"Rapport OCEA — {date_filter or 'toutes dates'}\n\n"
        f"Relevés OK (facturables): {stats['total_releves_ok']}\n"
        f"Non relevés (sans index): {stats['total_non_releves']}\n"
        f"Chiffre d'affaires HT: {stats['ca_total']} €\n"
        f"TVA ({int(stats['tva_taux']*100)}%): {stats['ca_tva']} €\n"
        f"Total TTC: {stats['ca_ttc']} €\n\n"
        f"Détail par type (OK):\n"
    )
    for k, v in stats.get("releves_ok_par_type", {}).items():
        body += f"  - {k}: {v}\n"
    body += (
        f"\nKilomètres parcourus: {km['km_total']} km\n"
        f"Coût carburant estimé: {km['carburant']['cout_euros']} €\n"
        f"Marge après carburant: {km['marge_apres_carburant']} €\n\n"
        f"Rapport détaillé: {link}\n"
    )
    return f"mailto:?subject={quote(subject)}&body={quote(body)}"
