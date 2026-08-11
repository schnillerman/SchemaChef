"""
Nur noch echte Infrastruktur-Credentials landen hier (Docker Secrets,
mit Env-Var-Fallback fuer lokale Entwicklung ohne Compose). Alles
Operative (XWiki-Base-URL, Ziel-Space, Prompts, Zutaten-Format) liegt
in der DB und ist ausschliesslich ueber /admin pflegbar - siehe db.py.

API-Keys sind bewusst KEINE DB-Werte (siehe Chat-Verlauf): Damit die
Web-UI selbst manipulationssicher bleibt und niemand ueber /admin an
Zugangsdaten kommt, liegen sie wie XWiki-User/Passwort als Docker
Secrets. Preis dafuer: ein Key-Wechsel braucht einen Rebuild/Recreate,
kein Live-Edit mehr moeglich - bewusster Tradeoff.
"""
import os
from pathlib import Path


def _read_secret(env_var_name: str, secret_file_name: str, default: str | None = None) -> str:
    """Liest zuerst aus einem Docker Secret (/run/secrets/<name>),
    fallback auf Umgebungsvariable (lokale Entwicklung), fallback auf
    default falls angegeben - sonst Fehler beim Start."""
    secret_path = Path(f"/run/secrets/{secret_file_name}")
    if secret_path.exists():
        return secret_path.read_text().strip()
    value = os.environ.get(env_var_name, "")
    if value:
        return value
    if default is not None:
        return default
    raise RuntimeError(
        f"Weder /run/secrets/{secret_file_name} noch {env_var_name} gesetzt"
    )


class Settings:
    # XWiki-Verbindung: bewusst als normale Compose-Environment-Variable
    # (nicht DB/Admin-UI) - aendert sich selten, und soll nicht ueber
    # die Web-UI manipulierbar sein. Siehe compose.yaml.
    XWIKI_BASE = os.environ.get("XWIKI_BASE", "https://xwiki.example.com").rstrip("/")
    XWIKI_TARGET_SPACE = os.environ.get("XWIKI_TARGET_SPACE", "Rezepte/Strukturiert")

    # XWiki-Zugang - Docker Secret, siehe ./secrets/xwiki_user.txt / xwiki_password.txt
    XWIKI_REST_USER = _read_secret("XWIKI_REST_USER", "xwiki_user")
    XWIKI_REST_PASSWORD = _read_secret("XWIKI_REST_PASSWORD", "xwiki_password")

    # Signiert nur das Flask-Session-Cookie (Flash-Messages) gegen
    # Manipulation - kein Datenbank-Passwort. Trotzdem als Secret
    # ausgelagert, da ein Leak Cookie-Faelschung ermoeglichen wuerde.
    APP_SECRET_KEY = _read_secret("APP_SECRET_KEY", "app_secret_key", default="dev-insecure-key")

    # LLM-API-Keys - jeweils optional (nur der aktive Provider braucht
    # einen), leerer String falls Datei/Env fehlt statt Fehler beim
    # Start, damit die App auch mit nur einem konfigurierten Anbieter
    # laeuft.
    ANTHROPIC_API_KEY = _read_secret("ANTHROPIC_API_KEY", "api_key_anthropic", default="")
    OPENAI_API_KEY = _read_secret("OPENAI_API_KEY", "api_key_openai", default="")
    GEMINI_API_KEY = _read_secret("GEMINI_API_KEY", "api_key_gemini", default="")

    DB_PATH = os.environ.get("DB_PATH", "/data/recipes.db")


settings = Settings()


def api_key_for_provider(provider: str) -> str:
    return {
        "anthropic": settings.ANTHROPIC_API_KEY,
        "openai": settings.OPENAI_API_KEY,
        "gemini": settings.GEMINI_API_KEY,
    }.get(provider, "")
