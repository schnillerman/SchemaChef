"""
Schritt 2-4 des Imports: HTML holen, zuerst nach eingebettetem
Schema.org-Recipe-JSON-LD suchen (Fast Path, kein LLM noetig), sonst
per Claude strukturiert extrahieren (Fallback - zwingend, da viele
Seiten keine Standards nutzen).
"""
import json
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from . import db, providers
from .config import api_key_for_provider


def fetch_html(url: str) -> str:
    resp = requests.get(
        url,
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0 (compatible; RecipeImporter/1.0)"},
    )
    resp.raise_for_status()
    return resp.text


def extract_site_name(html: str, url: str) -> str:
    """Fuer die Quellenangabe (rechtlich/ethisch Pflicht, da wir
    fremde Rezeptinhalte transformieren): og:site_name falls vorhanden,
    sonst Domain als Fallback - immer etwas Sinnvolles."""
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("meta", property="og:site_name")
    if tag and tag.get("content", "").strip():
        return tag["content"].strip()
    return urlparse(url).netloc


# --- Fast Path: Schema.org JSON-LD ---

def find_recipe_jsonld(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", type="application/ld+json"):
        if not tag.string:
            continue
        try:
            data = json.loads(tag.string)
        except json.JSONDecodeError:
            continue

        items = data if isinstance(data, list) else [data]
        flat = []
        for item in items:
            if isinstance(item, dict) and "@graph" in item:
                flat.extend(item["@graph"])
            else:
                flat.append(item)

        for item in flat:
            if not isinstance(item, dict):
                continue
            types = item.get("@type")
            types = types if isinstance(types, list) else [types]
            if "Recipe" in types:
                return item
    return None


def _flatten_instructions(instr) -> list[str]:
    steps = []
    if isinstance(instr, str):
        steps = [s.strip() for s in instr.split("\n") if s.strip()]
    elif isinstance(instr, list):
        for step in instr:
            if isinstance(step, str):
                steps.append(step.strip())
            elif isinstance(step, dict):
                text = step.get("text") or step.get("name")
                if text:
                    steps.append(text.strip())
                if step.get("itemListElement"):
                    steps.extend(_flatten_instructions(step["itemListElement"]))
    return steps


def parse_jsonld_recipe(item: dict) -> dict:
    ingredients = item.get("recipeIngredient") or item.get("ingredients") or []
    if isinstance(ingredients, str):
        ingredients = [ingredients]

    return {
        "title": (item.get("name") or "").strip(),
        "source_language": item.get("inLanguage"),
        "ingredients": [str(i).strip() for i in ingredients if str(i).strip()],
        "steps": _flatten_instructions(item.get("recipeInstructions", [])),
    }


# --- Fallback: LLM-Extraktion ---

def clean_html_for_llm(html: str, max_chars: int = 20000) -> str:
    """Bewusst simpel gehalten (kein trafilatura/lxml) fuer geringen
    Ressourcenbedarf. Entfernt nur offensichtlichen Rauschanteil; das
    Modell kommt mit dem Rest gut zurecht."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "iframe", "noscript", "svg"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    lines = [l for l in text.splitlines() if l.strip()]
    return "\n".join(lines)[:max_chars]


def extract_with_llm(cleaned_text: str, url: str) -> dict:
    cfg = db.get_settings()
    provider = cfg["provider"]
    prompt = (
        cfg["extract_prompt"]
        .replace("{{URL}}", url)
        .replace("{{CONTENT}}", cleaned_text)
    )
    return providers.call_llm(
        provider=provider,
        model=cfg["model"],
        api_key=api_key_for_provider(provider),
        prompt=prompt,
        schema=providers.EXTRACT_SCHEMA,
        tool_name="submit_recipe",
    )


def extract_recipe(url: str) -> tuple[dict, str]:
    """Gibt (recipe_dict, source) zurueck, source ist 'jsonld' oder 'llm'.
    recipe_dict enthaelt zusaetzlich 'site_name' fuer die Pflicht-
    Quellenangabe auf der finalen Seite."""
    html = fetch_html(url)
    site_name = extract_site_name(html, url)

    jsonld = find_recipe_jsonld(html)
    if jsonld:
        recipe = parse_jsonld_recipe(jsonld)
        if recipe["title"] and recipe["ingredients"] and recipe["steps"]:
            recipe["site_name"] = site_name
            return recipe, "jsonld"
        # JSON-LD unvollstaendig -> auf LLM-Fallback zurueckfallen

    cleaned = clean_html_for_llm(html)
    recipe = extract_with_llm(cleaned, url)
    recipe["site_name"] = site_name
    return recipe, "llm"
