"""
Uebersetzung in die gewaehlte Zielsprache + Zutaten-Alternativen fuer
in DE ueblichen Handel (Asia-Markt/Metro). Liefert immer nur einen
Vorschlag, nie eine automatische Ersetzung - die endgueltige
Entscheidung faellt im Review-Schritt der WebUI. Laeuft IMMER, auch
wenn Quelle und Zielsprache identisch sind, da der Alternativen-Check
davon unabhaengig ist.
"""
from . import db, providers
from .config import api_key_for_provider


def enrich_recipe(recipe: dict, target_language: str) -> dict:
    cfg = db.get_settings()
    provider = cfg["provider"]

    ingredients_txt = "\n".join(f"- {i}" for i in recipe["ingredients"])
    steps_txt = "\n".join(f"{n}. {s}" for n, s in enumerate(recipe["steps"], 1))

    prompt = (
        cfg["enrich_prompt"]
        .replace("{{TARGET_LANGUAGE}}", target_language)
        .replace("{{TITLE}}", recipe["title"])
        .replace("{{INGREDIENTS}}", ingredients_txt)
        .replace("{{STEPS}}", steps_txt)
    )

    return providers.call_llm(
        provider=provider,
        model=cfg["model"],
        api_key=api_key_for_provider(provider),
        prompt=prompt,
        schema=providers.ENRICH_SCHEMA,
        tool_name="submit_enrichment",
    )
