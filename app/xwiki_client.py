"""
XWiki-REST-Zugriff per HTTP Basic Auth (dedizierter Technical User).
Kein Keycloak-Bearer-Token: empirisch bestaetigt, dass XWikis
OIDC-Authenticator hier ausschliesslich den interaktiven Redirect-Flow
kann und Bearer-Header ignoriert - Basic Auth ist der tatsaechlich
unterstuetzte Weg fuer programmatischen REST-Zugriff.

Bewusst OHNE Groovy-Transformer: Das fertige Microdata-HTML wird hier
in Python gebaut und direkt per REST an die Zielseite geschrieben
(Struktur exakt nach der bereits gegen KitchenOwl validierten
Musterseite: {{html}}-Macro-Block, xwiki/2.1-Syntax). Der Technical
User braucht dafuer nur normale Edit/Create-Rechte auf dem konfigurierten
Zielraum - keine Programming Rights.

Base-URL, Zielraum und Zugangsdaten kommen aus Compose-Environment
bzw. Docker Secrets (config.py) - bewusst NICHT aus der DB/Admin-UI,
da sie sich selten aendern und nicht ueber die Web-UI manipulierbar
sein sollen. Nur das operative Zeug (Prompts, Zutaten-Format) bleibt
in der DB.
"""
import html
import re

import requests

from . import db
from .config import settings

UMLAUT_MAP = str.maketrans({
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
})

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")
_BRACKET_RE = re.compile(r"\[([^\[\]]*)\]")


def render_template(template: str, values: dict) -> str:
    """Ersetzt {{PLATZHALTER}} durch Werte aus 'values'. Text in
    eckigen Klammern [...] (inkl. aller darin enthaltenen Platzhalter
    und beliebigem umgebenden Text) faellt komplett weg, sobald auch
    nur einer der darin enthaltenen Platzhalter leer ist - so kann der
    Template-Autor selbst frei entscheiden, welcher Text/welches
    Trennzeichen um einen optionalen Wert steht, ohne haendisch fuer
    jede Kombination ein eigenes Template zu pflegen."""
    def render_bracket(m: re.Match) -> str:
        segment = m.group(1)
        names = _PLACEHOLDER_RE.findall(segment)
        if names and any(not values.get(n, "") for n in names):
            return ""
        return _PLACEHOLDER_RE.sub(lambda mm: values.get(mm.group(1), ""), segment)

    result = _BRACKET_RE.sub(render_bracket, template)
    return _PLACEHOLDER_RE.sub(lambda m: values.get(m.group(1), ""), result)


def slugify(title: str) -> str:
    """Transliteriert Umlaute statt sie zu verschlucken (Bug im
    urspruenglichen Groovy-Ansatz: [^A-Za-z0-9] entfernt sie komplett)."""
    s = title.translate(UMLAUT_MAP)
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")
    return s or "Rezept"


def _auth() -> tuple[str, str]:
    return (settings.XWIKI_REST_USER, settings.XWIKI_REST_PASSWORD)


def _space_segments() -> list[str]:
    return [s for s in settings.XWIKI_TARGET_SPACE.strip("/").split("/") if s]


def _page_url(slug: str) -> str:
    spaces_path = "/spaces/".join(_space_segments())
    base = settings.XWIKI_BASE.rstrip("/")
    return f"{base}/rest/wikis/xwiki/spaces/{spaces_path}/pages/{slug}"


def page_exists(slug: str) -> bool:
    resp = requests.get(_page_url(slug), auth=_auth(), timeout=10)
    return resp.status_code == 200


def fetch_page_names() -> list[str] | None:
    """Namen (nicht Titel) aller vorhandenen Seiten im Zielraum.
    Regex- statt XML-Parsing, da das exakte Antwort-Schema dieses
    Endpunkts nicht gegen eine echte Instanz verifiziert wurde -
    robuster gegen kleinere Abweichungen. Gibt None bei Fehlern zurueck
    (Unterscheidung zu einer tatsaechlich leeren Seitenliste - wichtig
    fuer den History-Abgleich, der bei einem Fehler NICHTS als
    geloescht markieren darf)."""
    try:
        spaces_path = "/spaces/".join(_space_segments())
        base = settings.XWIKI_BASE.rstrip("/")
        url = f"{base}/rest/wikis/xwiki/spaces/{spaces_path}/pages"
        resp = requests.get(url, auth=_auth(), timeout=10)
        resp.raise_for_status()
        return re.findall(r"<name>(.*?)</name>", resp.text)
    except Exception:
        return None


def list_page_names() -> list[str]:
    """Wie fetch_page_names(), aber mit leerer Liste statt None bei
    Fehlern - fuer find_free_slug(), das ohnehin auf page_exists()
    zurueckfaellt, wenn die Liste leer ist."""
    return fetch_page_names() or []


def find_free_slug(base_slug: str) -> str:
    """Findet einen im Zielraum noch freien Seitennamen, Gross-/
    Kleinschreibung egal (z.B. 'Kartoffelsalat' vs 'kartoffelsalat'
    gelten als derselbe Name). Erste Kollision -> 'Titel 2', dann
    'Titel 3' usw."""
    names = list_page_names()
    if names:
        existing_lower = {n.lower() for n in names}
    else:
        # Listing nicht verfuegbar - Fallback auf Einzel-Check
        # (case-sensitiv, aber besser als gar keine Pruefung).
        existing_lower = {base_slug.lower()} if page_exists(base_slug) else set()

    if base_slug.lower() not in existing_lower:
        return base_slug

    n = 2
    while f"{base_slug} {n}".lower() in existing_lower:
        n += 1
    return f"{base_slug} {n}"


def format_ingredient_line(name: str, amount: str, details: str, alternative: str, cfg: dict) -> str:
    """Baut die finale Zutatenzeile ueber render_template() aus einem
    admin-editierbaren Template (DB, kein Rebuild fuer
    Formatierungsaenderungen noetig). Default entspricht KitchenOwls
    manuellem Eingabeformat 'Name, Menge'."""
    values = {"NAME": name, "AMOUNT": amount, "DETAILS": details, "ALTERNATIVE": alternative}
    return render_template(cfg["ingredient_format"], values)


def _format_step(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    s = s[0].upper() + s[1:]
    if not s.endswith((".", "!", "?")):
        s += "."
    return s


def build_recipe_page_html(
    title: str, ingredient_lines: list[str], steps: list[str],
    source_url: str = "", site_name: str = "",
) -> str:
    """Baut den Seiteninhalt nach dem Muster, das bereits erfolgreich
    gegen KitchenOwl getestet wurde: reines Microdata-HTML in einem
    {{html}}-Macro-Block, xwiki/2.1-Syntax, kein JSON-LD (XWikis
    HTML-Cleaner haette ein <script>-Tag ohnehin vermutlich entfernt).

    Einzige Abweichung vom 1:1-Muster: recipeInstructions bekommt hier
    <p> pro Schritt statt eines Fliesstext-Blocks. Schema.org toleriert
    das problemlos (recipeInstructions ist Freitext/HTML), und ein
    Microdata-Parser liest bei einem <div> ohne eigenes itemscope
    ohnehin den gesamten Text-Inhalt zusammen, ob mit oder ohne
    <p>-Kinder - das ist also kein Bruch mit dem validierten Ansatz,
    nur eine naheliegende Formatierungs-Erweiterung.

    Quellenangabe (source_url/site_name) ist Pflicht, da wir fremde
    Rezeptinhalte transformieren - bewusst AUSSERHALB des Recipe-
    itemscope platziert, damit sie nicht versehentlich als Teil der
    Microdata geparst wird (z.B. als recipeInstructions-Text).
    """
    def esc(s: str) -> str:
        return html.escape(s, quote=True)

    ing_html = "\n".join(
        f'    <li itemprop="recipeIngredient">{esc(i)}</li>' for i in ingredient_lines
    )
    step_html = "\n".join(
        f"    <p>{esc(_format_step(s))}</p>" for s in steps if s.strip()
    )

    inner = (
        '<div itemscope itemtype="https://schema.org/Recipe">\n'
        f'  <h1 itemprop="name">{esc(title)}</h1>\n'
        "  <ul>\n"
        f"{ing_html}\n"
        "  </ul>\n"
        '  <div itemprop="recipeInstructions">\n'
        f"{step_html}\n"
        "  </div>\n"
        "</div>"
    )

    attribution = ""
    if source_url:
        label = esc(site_name) if site_name else esc(source_url)
        attribution = (
            '\n<p style="font-size:0.85em;color:#666;margin-top:1.5em;">\n'
            f'  Quelle: <a href="{esc(source_url)}" rel="nofollow noopener">{label}</a>\n'
            "</p>"
        )

    return "{{html}}\n" + inner + attribution + "\n{{/html}}"


def create_or_update_page(slug: str, title: str, content_html: str, force_overwrite: bool = False) -> tuple[str, str]:
    """Gibt (view_url, tatsaechlich_verwendeter_slug) zurueck. Ohne
    force_overwrite wird bei einer Kollision (Gross-/Kleinschreibung
    egal) automatisch durchnummeriert statt einen Fehler zu werfen -
    siehe find_free_slug()."""
    if not force_overwrite:
        slug = find_free_slug(slug)

    # syntax=xwiki/2.1, damit der {{html}}-Block im Content als Macro
    # interpretiert wird (nicht xhtml/1.0 - das war eine falsche
    # Annahme vor dem Abgleich mit der Musterseite).
    payload = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<page xmlns="http://www.xwiki.org">\n'
        f"  <title>{html.escape(title)}</title>\n"
        "  <syntax>xwiki/2.1</syntax>\n"
        f"  <content><![CDATA[{content_html}]]></content>\n"
        "</page>\n"
    )

    resp = requests.put(
        _page_url(slug),
        data=payload.encode("utf-8"),
        auth=_auth(),
        headers={"Content-Type": "application/xml; charset=UTF-8"},
        timeout=20,
    )
    resp.raise_for_status()

    base = settings.XWIKI_BASE.rstrip("/")
    view_url = f"{base}/bin/view/{settings.XWIKI_TARGET_SPACE}/{slug}"
    return view_url, slug
