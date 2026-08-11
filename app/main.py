import json
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, flash, make_response, redirect, render_template, request, url_for
from flask_babel import Babel, gettext as _

from . import db, enrichment, extractor, providers, xwiki_client
from .config import api_key_for_provider, settings

app = Flask(__name__)
app.secret_key = settings.APP_SECRET_KEY

SUPPORTED_UI_LANGUAGES = ("de", "en")
UI_LANG_COOKIE = "ui_lang"

app.config["BABEL_DEFAULT_LOCALE"] = "de"
app.config["BABEL_TRANSLATION_DIRECTORIES"] = str(Path(__file__).resolve().parent.parent / "translations")


def get_locale() -> str:
    lang = request.cookies.get(UI_LANG_COOKIE, "de")
    return lang if lang in SUPPORTED_UI_LANGUAGES else "de"


babel = Babel(app, locale_selector=get_locale)
app.jinja_env.globals["get_locale"] = get_locale

db.init_db()


def _refresh_models(provider_filter=None) -> tuple[dict, bool]:
    """Holt frische Modell-Listen fuer alle Provider mit hinterlegtem
    API-Key (oder nur fuer provider_filter, falls angegeben). Gibt
    (updates_dict, hatte_fehler) zurueck - Aufrufer entscheidet ueber
    Flash-Messages (Auto-Load beim Seitenaufruf bleibt bewusst still,
    der manuelle Button meldet sich)."""
    updates = {}
    any_error = False
    providers_to_check = [provider_filter] if provider_filter else ("anthropic", "openai", "gemini")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d um %H:%M")
    for provider in providers_to_check:
        api_key = api_key_for_provider(provider)
        if not api_key:
            continue
        try:
            models = providers.list_models(provider, api_key)
            updates[f"models_cache_{provider}"] = json.dumps(models)
            updates[f"models_loaded_at_{provider}"] = now_str
        except Exception as e:
            any_error = True
            flash(_("Modelle fuer %(provider)s konnten nicht geladen werden: %(error)s", provider=provider, error=e), "error")
    if updates:
        db.update_settings(updates)
    return updates, any_error


@app.route("/set-language/<lang>", methods=["POST"])
def set_language(lang):
    resp = make_response(redirect(request.referrer or url_for("index")))
    if lang in SUPPORTED_UI_LANGUAGES:
        # 1 Jahr - reine UI-Praeferenz, kein sensibler Wert.
        resp.set_cookie(UI_LANG_COOKIE, lang, max_age=60 * 60 * 24 * 365)
    return resp


@app.route("/", methods=["GET"])
def index():
    cfg = db.get_settings()
    return render_template("index.html", target_language=cfg["target_language"])


@app.route("/extract", methods=["POST"])
def extract():
    url = request.form["url"].strip()
    target_language = request.form.get("target_language", "Deutsch").strip() or "Deutsch"
    db.update_settings({"target_language": target_language})

    try:
        recipe, source = extractor.extract_recipe(url)
        enriched = enrichment.enrich_recipe(recipe, target_language)
    except Exception as e:  # bewusst breit: alles landet als Fehlermeldung beim Nutzer
        flash(_("Extraktion fehlgeschlagen: %(error)s", error=e), "error")
        return redirect(url_for("index"))

    enriched["site_name"] = recipe.get("site_name", "")
    base_slug = xwiki_client.slugify(enriched["title_translated"])
    slug = xwiki_client.find_free_slug(base_slug)

    return render_template(
        "review.html",
        url=url,
        recipe=enriched,
        slug=slug,
        slug_is_duplicate=(slug != base_slug),
        source=source,
    )


@app.route("/confirm", methods=["POST"])
def confirm():
    url = request.form["url"]
    site_name = request.form.get("site_name", "").strip()
    title = request.form["title_translated"].strip()
    slug = request.form["slug"].strip()
    force = request.form.get("force_overwrite") == "on"

    names = request.form.getlist("ingredient_name")
    amounts = request.form.getlist("ingredient_amount")
    details_list = request.form.getlist("ingredient_details")
    alternatives = request.form.getlist("ingredient_alternative")
    steps_translated = [s for s in request.form.getlist("step_translated") if s.strip()]

    cfg = db.get_settings()
    lines = []
    for name, amount, details, alt in zip(names, amounts, details_list, alternatives):
        name = name.strip()
        amount = amount.strip()
        details = details.strip()
        alt = alt.strip()
        if not name:
            continue
        lines.append(xwiki_client.format_ingredient_line(name, amount, details, alt, cfg))

    content_html = xwiki_client.build_recipe_page_html(
        title, lines, steps_translated, source_url=url, site_name=site_name
    )

    try:
        xwiki_url, used_slug = xwiki_client.create_or_update_page(
            slug, title, content_html, force_overwrite=force
        )
    except Exception as e:
        db.log_import(url, title, slug, "error", error=str(e))
        flash(_("Import fehlgeschlagen: %(error)s", error=e), "error")
        return redirect(url_for("index"))

    db.log_import(url, title, used_slug, "ok", xwiki_url=xwiki_url)
    flash(_("Rezept '%(title)s' importiert.", title=title), "success")
    return redirect(url_for("history"))


@app.route("/history", methods=["GET"])
def history():
    imports = db.recent_imports()
    # Live-Abgleich mit XWiki: EIN REST-Call statt N Einzelchecks. Bei
    # Fehler (None) wird NICHTS als geloescht markiert - lieber
    # veraltete Anzeige als falsch-positive "geloescht"-Meldungen.
    existing_names = xwiki_client.fetch_page_names()
    existing_lower = {n.lower() for n in existing_names} if existing_names is not None else None

    rows = []
    for row in imports:
        d = dict(row)
        if d["status"] == "ok" and d["slug"] and existing_lower is not None:
            d["still_exists"] = d["slug"].lower() in existing_lower
        else:
            d["still_exists"] = None
        rows.append(d)

    return render_template("history.html", imports=rows, sync_available=(existing_lower is not None))


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        section = request.form.get("section")
        cfg_before = db.get_settings()

        if section == "llm":
            db.update_settings(
                {
                    "provider": request.form["provider"],
                    "model": request.form["model"].strip(),
                }
            )
        elif section in db.PROMPT_KEYS:
            new_value = request.form[section] if section != "ingredient_format" else request.form[section].strip()
            if new_value != cfg_before.get(section):
                note = request.form.get(f"{section}_note", "").strip()
                db.save_prompt_version(section, new_value, note)
            db.update_settings({section: new_value})

        flash(_("Einstellungen gespeichert."), "success")
        return redirect(url_for("admin"))

    cfg = db.get_settings()
    # Auto-Load: aktiven Provider beim Aufruf der Seite still
    # aktualisieren, damit das Dropdown ohne Klick aktuell ist. Fehler
    # (z.B. fehlender/ungueltiger Key) bewusst ohne Flash-Message, um
    # die Seite nicht bei jedem Aufruf mit einer Fehlermeldung zu
    # stoeren - der manuelle Button bleibt fuer explizites Feedback.
    if api_key_for_provider(cfg["provider"]):
        try:
            _refresh_models(provider_filter=cfg["provider"])
            cfg = db.get_settings()
        except Exception:
            pass

    model_choices = {}
    models_loaded_at = {}
    for provider in ("anthropic", "openai", "gemini"):
        raw = cfg.get(f"models_cache_{provider}", "")
        try:
            model_choices[provider] = json.loads(raw) if raw else []
        except json.JSONDecodeError:
            model_choices[provider] = []
        models_loaded_at[provider] = cfg.get(f"models_loaded_at_{provider}", "")

    prompt_versions = {key: db.list_prompt_versions(key) for key in db.PROMPT_KEYS}
    prompt_versions_json = json.dumps(
        {key: {str(v["id"]): v["content"] for v in versions} for key, versions in prompt_versions.items()}
    )
    default_templates = {key: db.read_default_template(key) for key in db.PROMPT_KEYS}

    return render_template(
        "admin.html",
        settings=cfg,
        xwiki_base=settings.XWIKI_BASE,
        xwiki_target_space=settings.XWIKI_TARGET_SPACE,
        model_choices=model_choices,
        model_choices_json=json.dumps(model_choices),
        models_loaded_at=models_loaded_at,
        configured_providers={
            "anthropic": bool(settings.ANTHROPIC_API_KEY),
            "openai": bool(settings.OPENAI_API_KEY),
            "gemini": bool(settings.GEMINI_API_KEY),
        },
        prompt_versions=prompt_versions,
        prompt_versions_json=prompt_versions_json,
        default_templates=default_templates,
    )


@app.route("/admin/refresh-models", methods=["POST"])
def refresh_models():
    updates, any_error = _refresh_models()
    if updates:
        flash(_("Modell-Listen aktualisiert."), "success")
    elif not any_error:
        flash(_("Kein API-Key als Secret hinterlegt - siehe secrets/README.md."), "error")
    return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
