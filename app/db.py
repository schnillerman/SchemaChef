"""SQLite: Import-Verlauf, Admin-Einstellungen UND Versionsverlauf der
drei Templates (Extraktions-/Anreicherungs-Prompt, Zutatenformat).
Bewusst kein eigener DB-Container, um den Ressourcenbedarf niedrig zu
halten - eine Datei im gemounteten /data-Volume reicht.

Migrationen (_run_migrations) sorgen dafuer, dass ein App-Update mit
geaenderten Settings-Keys bereits eingegebene Werte nicht verwirft -
bei jeder strukturellen Aenderung an DEFAULT_SETTINGS hier einen
Migrationsschritt ergaenzen, nicht nur den Key umbenennen.

Die drei Vorgabe-Templates liegen NICHT mehr hartkodiert im Code,
sondern als editierbare Dateien unter ./templates/ (Projekt-Root,
NICHT app/templates/ - das sind die Jinja2-HTML-Templates). Aendern
dieser Dateien setzt den "Werksdefault" fuer den "Auf Vorlage
zuruecksetzen"-Button in /admin, ohne die DB anzufassen."""
import sqlite3
from pathlib import Path

from .config import settings

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

PROMPT_KEYS = ("extract_prompt", "enrich_prompt", "ingredient_format")
_TEMPLATE_FILES = {
    "extract_prompt": "extraction_prompt.md",
    "enrich_prompt": "enrichment_prompt.md",
    "ingredient_format": "ingredients_scheme.md",
}


def read_default_template(prompt_key: str) -> str:
    """Liest den Werksdefault direkt aus der Datei - fuer den 'Auf
    Vorlage zuruecksetzen'-Button IMMER live gelesen, nicht gecacht,
    damit eine Datei-Aenderung ohne Neustart sichtbar wird (Datei ist
    ins Image gebacken, aendert sich also ohnehin nur bei Rebuild -
    aber kein Grund, unnoetig zu cachen)."""
    path = TEMPLATES_DIR / _TEMPLATE_FILES[prompt_key]
    return path.read_text(encoding="utf-8").strip()


DEFAULT_SETTINGS = {
    # XWiki-Base-URL und Zielraum liegen NICHT mehr hier, sondern als
    # normale Compose-Environment-Variablen (XWIKI_BASE,
    # XWIKI_TARGET_SPACE) - siehe compose.yaml/app/config.py. Aendern
    # sich selten und sollen nicht ueber die Web-UI manipulierbar sein.
    # XWiki-Zugangsdaten (User/Passwort) liegen als Docker Secrets.
    "provider": "gemini",
    # Zielsprache der Rezept-Uebersetzung (NICHT die UI-Sprache, die
    # ist ein Cookie - siehe Chat). Wird bei jedem Import ueber das
    # Dropdown auf der Startseite aktualisiert, hier nur der Default/
    # zuletzt gewaehlte Wert.
    "target_language": "Deutsch",
    # EIN Modell fuer den aktuell aktiven Provider (nicht pro Provider
    # gemerkt - bewusste Entscheidung: einfacher, ein Wechsel des
    # Providers erfordert ohnehin meist auch ein neues Modell).
    # Stand August 2026 - Modelllandschaft aendert sich schnell.
    "model": "gemini-3.6-flash",
    # API-Keys liegen NICHT in der DB, sondern als Docker Secrets -
    # siehe app/config.py. Damit bleibt die Web-UI selbst
    # manipulationssicher fuer Zugangsdaten.
    "extract_prompt": read_default_template("extract_prompt"),
    "enrich_prompt": read_default_template("enrich_prompt"),
    # Format der einzelnen Zutatenzeile in der finalen XWiki-Seite -
    # admin-editierbar, kein Rebuild fuer Formatierungsaenderungen
    # noetig. Default entspricht KitchenOwls manuellem Eingabeformat
    # "Name, Menge" (siehe github.com/TomBursch/kitchenowl/issues/72).
    "ingredient_format": read_default_template("ingredient_format"),
    # Zwischengespeicherte Modell-Listen (JSON-Array) PRO Provider,
    # befuellt automatisch beim Laden von /admin bzw. per "Modelle
    # laden"-Button - fuer die Dropdown-Optionen.
    "models_cache_anthropic": "",
    "models_cache_openai": "",
    "models_cache_gemini": "",
    # Zeitpunkt (ISO-String) des letzten erfolgreichen Modell-Ladens,
    # PRO Provider - fuer die "zuletzt geladen am..."-Anzeige.
    "models_loaded_at_anthropic": "",
    "models_loaded_at_openai": "",
    "models_loaded_at_gemini": "",
}


def get_db() -> sqlite3.Connection:
    Path(settings.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _run_migrations(conn: sqlite3.Connection) -> None:
    existing = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM settings")}

    # model_anthropic/model_openai/model_gemini -> ein einzelnes
    # "model", passend zum zuletzt aktiven Provider.
    if "model" not in existing:
        provider = existing.get("provider", "gemini")
        model_key = f"model_{provider}"
        if model_key in existing:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                ("model", existing[model_key]),
            )

    # Keys, die in einer frueheren Version existierten und inzwischen
    # entfernt/ersetzt wurden - Werte wurden oben ggf. migriert,
    # verwaiste Zeilen hier aufraeumen. api_key_* wandern zu Docker
    # Secrets, xwiki_base/xwiki_target_space zu Compose-Environment-
    # Variablen - der jeweilige Wert MUSS manuell in secrets/*.txt bzw.
    # compose.yaml uebertragen werden, bevor die DB-Zeile verschwindet
    # (siehe Anleitung im Chat/README).
    for stale_key in (
        "xwiki_space", "xwiki_subspace", "xwiki_user", "xwiki_password",
        "xwiki_base", "xwiki_target_space",
        "ingredient_format_alt", "model_anthropic", "model_openai", "model_gemini",
        "api_key_anthropic", "api_key_openai", "api_key_gemini",
    ):
        conn.execute("DELETE FROM settings WHERE key = ?", (stale_key,))
    conn.commit()


def init_db() -> None:
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            title TEXT,
            slug TEXT,
            status TEXT NOT NULL,
            xwiki_url TEXT,
            error TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prompt_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_key TEXT NOT NULL,
            content TEXT NOT NULL,
            note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()

    _run_migrations(conn)

    for key, value in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def get_settings() -> dict:
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    result = dict(DEFAULT_SETTINGS)
    result.update({row["key"]: row["value"] for row in rows})
    return result


def update_settings(values: dict) -> None:
    conn = get_db()
    for key, value in values.items():
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
    conn.commit()
    conn.close()


def save_prompt_version(prompt_key: str, content: str, note: str) -> None:
    conn = get_db()
    conn.execute(
        "INSERT INTO prompt_versions (prompt_key, content, note) VALUES (?, ?, ?)",
        (prompt_key, content, note.strip()),
    )
    conn.commit()
    conn.close()


def list_prompt_versions(prompt_key: str, limit: int = 30):
    conn = get_db()
    rows = conn.execute(
        "SELECT id, content, note, created_at FROM prompt_versions "
        "WHERE prompt_key = ? ORDER BY id DESC LIMIT ?",
        (prompt_key, limit),
    ).fetchall()
    conn.close()
    return rows


def log_import(url, title, slug, status, xwiki_url=None, error=None) -> None:
    conn = get_db()
    conn.execute(
        "INSERT INTO imports (url, title, slug, status, xwiki_url, error) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (url, title, slug, status, xwiki_url, error),
    )
    conn.commit()
    conn.close()


def recent_imports(limit: int = 50):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM imports ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return rows
