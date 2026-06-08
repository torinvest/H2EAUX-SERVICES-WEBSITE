import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "ocea_crm.db"
SCHEMA_VERSION = 3


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def _migrate(conn):
    migrations = [
        ("patrimoine", "distribution_type", "TEXT DEFAULT ''"),
        ("patrimoine", "latitude", "TEXT DEFAULT ''"),
        ("patrimoine", "longitude", "TEXT DEFAULT ''"),
        ("tournees", "latitude", "TEXT DEFAULT ''"),
        ("tournees", "longitude", "TEXT DEFAULT ''"),
        ("releves", "occupant", "TEXT DEFAULT ''"),
        ("releves", "etage", "TEXT DEFAULT ''"),
        ("releves", "porte", "TEXT DEFAULT ''"),
        ("releves", "distribution_type", "TEXT DEFAULT ''"),
        ("releves", "statut_releve", "TEXT DEFAULT 'NON_RELEVE'"),
        ("releves", "montant", "REAL DEFAULT 0"),
        ("releves", "categorie_facture", "TEXT DEFAULT ''"),
        ("releves", "gpa_estime", "INTEGER DEFAULT 0"),
        ("releves", "pat_trouve", "INTEGER DEFAULT 0"),
        ("patrimoine", "imported_at", "TEXT DEFAULT ''"),
    ]
    for table, col, typedef in migrations:
        if not _column_exists(conn, table, col):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")


def init_db():
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS share_reports (
            token TEXT PRIMARY KEY,
            created_at TEXT,
            payload TEXT
        );

        CREATE TABLE IF NOT EXISTS ensembles (
            code_ensemble TEXT PRIMARY KEY,
            nom_ensemble TEXT DEFAULT '',
            ville TEXT DEFAULT '',
            cp TEXT DEFAULT '',
            adresse TEXT DEFAULT '',
            commentaires TEXT DEFAULT '',
            code_acces TEXT DEFAULT '',
            contacts TEXT DEFAULT '',
            client_nom TEXT DEFAULT '',
            client_tel TEXT DEFAULT '',
            client_email TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS import_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type_import TEXT,
            fichier_count INTEGER,
            detail TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS patrimoine (
            id_pdc TEXT PRIMARY KEY,
            code_ensemble TEXT,
            nom_ensemble TEXT,
            ville TEXT,
            cp TEXT,
            id_ensemble TEXT,
            id_workflow TEXT,
            id_entree TEXT,
            nom_entree TEXT,
            id_lgt TEXT,
            occupant TEXT,
            etage TEXT,
            porte TEXT,
            fluide TEXT,
            type_releve TEXT,
            position TEXT,
            emplacement TEXT,
            distribution_type TEXT DEFAULT '',
            latitude TEXT DEFAULT '',
            longitude TEXT DEFAULT '',
            categorie TEXT,
            a_relever INTEGER,
            source_file TEXT,
            imported_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS tournees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            num_tournee TEXT,
            fichier TEXT UNIQUE,
            fichier_pat TEXT,
            code_ensemble TEXT,
            nom_ensemble TEXT,
            ville TEXT,
            cp TEXT,
            id_ensemble TEXT,
            nb_pdc_cible INTEGER,
            client_nom TEXT,
            planning_debut TEXT,
            planning_fin TEXT,
            latitude TEXT DEFAULT '',
            longitude TEXT DEFAULT '',
            nb_int INTEGER DEFAULT 0,
            nb_ext INTEGER DEFAULT 0,
            nb_rad INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS releves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_pdc TEXT,
            code_ensemble TEXT,
            nom_ensemble TEXT,
            ville TEXT,
            id_entree TEXT,
            id_lgt TEXT,
            occupant TEXT DEFAULT '',
            etage TEXT DEFAULT '',
            porte TEXT DEFAULT '',
            fluide TEXT,
            type_releve TEXT,
            position TEXT,
            emplacement TEXT,
            distribution_type TEXT DEFAULT '',
            categorie TEXT,
            categorie_facture TEXT DEFAULT '',
            gpa_estime INTEGER DEFAULT 0,
            pat_trouve INTEGER DEFAULT 0,
            statut_releve TEXT DEFAULT 'NON_RELEVE',
            montant REAL DEFAULT 0,
            date_releve TEXT,
            index_val TEXT,
            conso TEXT,
            code_obs TEXT,
            lib_obs TEXT,
            nature_index TEXT,
            nature_conso TEXT,
            source_file TEXT,
            timestamp_fichier TEXT,
            UNIQUE(id_pdc, date_releve, source_file)
        );

        CREATE INDEX IF NOT EXISTS idx_releves_categorie ON releves(categorie_facture);
        CREATE INDEX IF NOT EXISTS idx_releves_statut ON releves(statut_releve);
        CREATE INDEX IF NOT EXISTS idx_releves_date ON releves(date_releve);
        CREATE INDEX IF NOT EXISTS idx_releves_code ON releves(code_ensemble);
        CREATE INDEX IF NOT EXISTS idx_patrimoine_code ON patrimoine(code_ensemble);
        """
    )
    _migrate(conn)
    conn.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()
    conn.close()
