# SchemaChef

The platform for the recipe workflow: a lean container, a web UI. Insert URL → Parse page → Check if matching Schema.org syntax is already present (Fast Path) or if AI extraction is needed (Claude/ChatGPT/Gemini, interchangeable) → Translation into a selectable target language + ingredient alternatives (Asian market/Metro) → Review in the browser → Finished, KitchenOwl-scrapable page via REST directly into XWiki, including required source citation. No Groovy, no Programming Rights required for the technical user.

**License:** MIT (see `LICENSE`) - private use without commercial interest, as few hurdles as possible for contributors (e.g., translations).

## Languages

Two separate language settings, do not confuse:

- **Target language of the recipe translation**: Dropdown with autocomplete (`<datalist>`) on the home page, selectable per import, last choice is remembered as a DB setting (Default: German).
- **UI language of the app itself** (DE/EN): Toggle in the upper right, stored as a cookie (1 year) - each person/browser can have its own UI language, independent of the target language.

UI translations are stored as GNU-gettext `.po` files under `translations/<lang>/LC_MESSAGES/messages.po` - the most common format for this, directly supported by free tools like **Poedit** or **Weblate**. `.mo` binary files are deliberately NOT committed, but are recompiled from the `.po` files on every `docker build` (`pybabel compile`) - avoids merge conflicts on binary files and keeps contributions simple: a new language only needs a new `translations/<lang>/LC_MESSAGES/messages.po` folder following the same scheme.

**Weblate integration is prepared, but deliberately not yet active** (only DE/EN are currently delivered). Once desired: register repo on Hosted Weblate (GitHub App flow, see docs.weblate.org), point component to `translations/*/LC_MESSAGES/messages.po`. Weblate will then NOT push directly to `main`, but open pull requests like any other contributor - enforceable with a protected branch. No repo-side config file needed, this runs via the Weblate web dashboard.

## Architecture in One Sentence

One container (Flask + Gunicorn + SQLite), no separate DB or auth service - access protection for the web UI (npm + oauth2-proxy + Keycloak) sits in front of the container, not inside it. The app's access to XWiki runs separately via HTTP Basic Auth with a dedicated XWiki technical user.

## Three Configuration Levels

| Level | Examples | Change takes effect... |
|---|---|---|
| `.env` (local, ignored by git) → Fallback in `compose.yaml` | `XWIKI_BASE`, `XWIKI_TARGET_SPACE` | after `docker compose up -d --force-recreate` |
| Docker Secrets (`secrets/*.txt`) | XWiki user/password, app secret key, LLM API keys | after `docker compose up -d --build --force-recreate` |
| DB (`/admin`) | Provider, model, prompts, ingredient format | immediately, no rebuild/recreate |

Principle: everything that changes rarely or should not be manipulable via the web UI is kept in `.env`/secrets - `compose.yaml` itself remains generic (Git-safe, no real instance values). Everything operational that is adjusted more frequently resides in the DB.

## Setup

```bash
mkdir -p secrets data
echo -n "recipe_importer_bot" > secrets/xwiki_user.txt
echo -n "YOUR_XWIKI_PASSWORD" > secrets/xwiki_password.txt
openssl rand -hex 32 > secrets/app_secret_key.txt
# Only populate the provider(s) actually used:
echo -n "YOUR_ANTHROPIC_KEY" > secrets/api_key_anthropic.txt
echo -n "YOUR_OPENAI_KEY" > secrets/api_key_openai.txt
echo -n "YOUR_GEMINI_KEY" > secrets/api_key_gemini.txt
# Set actual XWIKI_BASE/XWIKI_TARGET_SPACE locally here (captured
# by .gitignore) - compose.yaml itself remains generic/publicly-safe:
cat > .env << 'ENVEOF'
XWIKI_BASE=[https://xwiki.your-domain.tld](https://xwiki.your-domain.tld)
XWIKI_TARGET_SPACE=Your/TargetSpace
ENVEOF
docker compose up -d --build
```

Container then runs internally on port 5000, mapped externally to `11321` (see `compose.yaml`). Then configure the active provider at `http://<nas-ip>:11321/admin`. XWiki base URL and target space are deliberately NOT in the DB/admin UI, but as environment variables set via a local `.env` (see above, never commit) - they change rarely and should not be manipulable via the web UI. Changes there require `docker compose up -d --force-recreate` (no rebuild needed, only recreate, as there is no code/image change). API keys are also NOT editable via the web UI (see "API Keys as Docker Secrets" below). Details on all six secret files: `secrets/README.md`.

In Synology Container Manager: Import project from this folder. Create a reverse proxy host on port `11321` using npm and secure it with your existing oauth2-proxy/Keycloak setup (for the login of people opening the page - separate Keycloak client with Standard Flow, not to be confused with the XWiki technical user). The app itself does not bring its own authentication for the web UI to avoid maintaining auth twice.

## Why APP_SECRET_KEY and Not DB_PASSWORD

Two different things: `APP_SECRET_KEY` only signs the Flask session cookie (for flash messages) so that it cannot be manipulated from the browser - it has nothing to do with the database.

A `DB_PASSWORD`/`DB_USER`/`DB_ROOT` in the classical sense is deliberately not present here: SQLite is a single file (`/data/recipes.db`), not a client-server database service like Postgres/MySQL - there is no database process to log into with a username/password. Protection comes instead via normal filesystem permissions on the mounted `/data` volume. That was also the reason for choosing SQLite instead of Postgres in the first place (no additional DB container for "lightweight"). Introducing `DB_USER`/`DB_ROOT` additionally would be dead config without a real mechanism behind it - hence deliberately omitted.

## XWiki Access: Technical User Instead of Keycloak Bearer Token

**Empirically tested and discarded:** A bearer token issued via the Keycloak client credentials flow is not validated by your XWiki OIDC authenticator - a REST request with `Authorization: Bearer <token>` was answered with `302` to Keycloak's `/protocol/openid-connect/auth`, meaning the authenticator completely ignored the header and instead started the interactive login flow. The `xwiki-contrib-OIDC-Authenticator` is built for browser SSO, not as a resource server for externally issued tokens (consistent with several reports in the XWiki forum). This could only be solved with additional Java development on your XWiki - disproportionate for this purpose.

Instead: dedicated XWiki technical user with HTTP Basic Auth (providently the way actually supported by XWiki for programmatic REST access):

1. In XWiki: Users & Groups → Create new user, e.g., `recipe_importer_bot`, strong/random password.
2. On `XWIKI_TARGET_SPACE` (Default: `Rezepte/Strukturiert`) → Access Rights → Give this user Edit + Create. **No** Programming Rights, no Admin.
3. Populate `secrets/xwiki_user.txt` / `secrets/xwiki_password.txt`.
4. Test:
   ```bash
   curl -i -u recipe_importer_bot:<PASSWORD> \
     "[https://xwiki.example.com/rest/wikis/xwiki/spaces/Rezepte/spaces/Strukturiert](https://xwiki.example.com/rest/wikis/xwiki/spaces/Rezepte/spaces/Strukturiert)"
   ```
   Expected: `200` (or `404` if the space doesn't exist yet - then that's no longer an auth error, just "doesn't exist yet").

The Keycloak client `recipe-importer.example.com-xwiki-importer` (service account) is no longer needed for REST access - can be deleted or left alone, doesn't hurt.

## Pages

- `/` – Insert URL, select target language (autocomplete, last choice remembered)
- `/extract` (POST) → Review page: title, ingredients (original/translated/details/alternative), steps editable, then confirm import. Page name (slug) sits directly next to "Import into XWiki"; in case of duplicates (case-insensitive), it is automatically numbered, with an explicit note in the form
- `/history` – History of all imports. On each call, a live comparison with XWiki (one REST call, no N+1) - pages that were deleted directly in XWiki are crossed out/marked instead of showing a dead link. If XWiki is unreachable, nothing is falsely marked as deleted
- `/admin` – four independent storage areas (LLM provider & model, ingredient format, extraction prompt, enrichment prompt), each with its own "Save" button - changes take effect immediately, no rebuild needed
- `/set-language/<de|en>` (POST) – Switch UI language (cookie, 1 year)

## Multiple LLM Providers

Provider selection, model, and prompts are stored in SQLite and can be changed immediately via `/admin` without a redeploy. A single "Model" field instead of one per provider - depends on the provider selected above (JS-controlled), does not remember separate values per provider.

**API keys are deliberately NOT in the DB**, but in Docker secrets (`secrets/api_key_<provider>.txt`) - so that the web UI itself remains tamper-proof for credentials (no one can access or change keys via `/admin`). Price for this: a key change requires `docker compose up -d --build --force-recreate`, no live edit. Given your rare usage, a favorable trade-off.

Model selection via dropdown instead of free text: The list is automatically updated when opening `/admin` for the active provider (`client.models.list()`, quietly in the background, no flash spam on errors), plus manually at any time via a "Reload Model List" button - with display "last loaded on yyyy-mm-dd at hh:mm". No more typo risk, no hardcoded model directory that could become outdated.

**Important:** A Claude Pro/Max, ChatGPT Plus, or Gemini Advanced subscription is NOT the same as an API key. For programmatic access here, each desired provider requires a separate, mostly usage-billed API key (sources: see `secrets/README.md`). For your rare private use, this should remain in the cent to low euro range per month.

## Resource Requirements

- Image: python:3.12-slim base, deliberately no lxml/trafilatura → unproblematic even on ARM NAS. Three SDKs (Anthropic/OpenAI/Gemini) together approx. 110 MB additional - justifiable for "one container for everything" instead of three separate images.
- Runtime: 2 Gunicorn workers, RAM requirement typically 80-150 MB. `compose.yaml` caps at 256 MB RAM (CPU limit optional, depending on Synology Container Manager version).

## Open Items

1. ~~KitchenOwl compatibility of the output~~ - **done**, checked against sample page (`app/xwiki_client.py`, `build_recipe_page_html`).
2. ~~XWiki REST auth~~ - **done**, Basic Auth instead of bearer token (see above).
3. **Space rights**: Technical user needs Edit/Create on `XWIKI_TARGET_SPACE`, *no* Programming Rights - already successfully verified in operation.
4. **Model names** in the DB default (`gemini-3.6-flash` et al.) are as of August 2026 - now secondary, since `/admin` automatically loads the real list upon page load (see "Multiple LLM Providers").

## Ingredient Format for KitchenOwl

KitchenOwl's manual entry format is "Name, Amount" (confirmed in github.com/TomBursch/kitchenowl/issues/72). KitchenOwl's scraper does have its own parser (NLP, optionally LLM-supported since a recent release) and basically handles "Amount Name" as well - but "Name, Amount" should be parsed more reliably, closer to the actual target format.

Extraction/enrichment yields three separate fields per ingredient: `name_translated`, `amount_translated`, `details_translated` (preparation note or descriptive property like "grated", "ripe", "red or green" - always in base form, not inflected). The final line format comes from an admin-editable template (`ingredient_format`, default `{{NAME}}[, {{DETAILS}}][, {{AMOUNT}}][ (or: {{ALTERNATIVE}})]`) - see "Ingredient Format: Placeholders with optional [..] blocks" below for template logic. Changes take effect immediately, no rebuild needed.

## Schema Migrations

`db._run_migrations()` ensures that an app update with changed settings keys does not discard already entered values (API keys, target space, etc.), but adopts them into the new keys. With every structural change to `DEFAULT_SETTINGS` in `db.py`, a new migration step is added there, not just a rename - pure `INSERT OR IGNORE` would have solved this only for newly added keys, not for renames/merges.

## Ingredient Format: Placeholders with Optional [..] Blocks

Text in square brackets (including contained placeholders) is completely dropped if any of the placeholders contained within is empty - prevents double commas/empty brackets for empty fields like details or alternatives. Placeholders are raw values without built-in separators; the template author determines themselves what text/separator surrounds an optional value. Default: `{{NAME}}[, {{DETAILS}}][, {{AMOUNT}}][ (or: {{ALTERNATIVE}})]`

Implemented in `xwiki_client.render_template()` - generic mechanism, usable independently of the ingredient format.

## Prompt Templates and Version History

The three default templates (extraction prompt, enrichment prompt, ingredient format) are located as editable files under `./templates/` (project root, not to be confused with `app/templates/`, the Jinja2 HTML templates):

- `templates/extraction_prompt.md`
- `templates/enrichment_prompt.md`
- `templates/ingredients_scheme.md`

Changing these files + rebuild sets the "factory default" for the "Reset to Template" button in `/admin`. Any content change to one of the three fields is additionally stored as a new version in the DB upon saving (with an optional single-line version note) - via a dropdown per field, any previous version can be loaded again (into the text field only, not automatically saved - can be checked again before actual saving). Each of the three fields saves independently of the others (separate form, separate "Save" button) - a click affects only that exact one field, not the provider/model or the other templates.

## Duplicates and Source Citation

**Duplicates**: Before saving, it is checked (case-insensitive) whether a page with this name already exists in the target space. If so, it is automatically numbered (`Title`, `Title 2`, `Title 3`, ...) instead of showing an error. The "Overwrite existing page" checkbox in the review remains as an explicit opt-in in case an existing page really needs to be replaced (e.g., re-importing a recipe to correct errors).

**Source Citation (Mandatory)**: Every generated page gets a footnote with a link to the source URL and the website name (`og:site_name`, otherwise domain as fallback) - since third-party recipe content is transformed. Deliberately placed OUTSIDE the recipe `itemscope` so that it is not accidentally parsed as part of the microdata (e.g., as a preparation step).

## Next Meaningful Steps

1. ~~Run the first real import via the web UI~~ - done (several real recipes successfully imported).
2. Create reverse proxy host in npm, put oauth2-proxy in front.
3. Optional, as soon as the repo is public on GitHub: test suite + CI (lint/tests on every push), Docker publish workflow to ghcr.io, branch protection.
4. Optional: Enable Weblate integration as soon as further languages beyond DE/EN are desired (see "Languages" above).

## Troubleshooting: REST-PUT Returns 401 Even Though Credentials/Rights Are Correct

The cause for us was XWiki's built-in Authentication Security Module: By default, 3 failed login attempts within 5 minutes trigger a CAPTCHA requirement for the affected account. Structurally, HTTP Basic Auth cannot solve a CAPTCHA - every subsequent REST attempt then fails permanently (`401`, Tomcat error page), *even with the correct password*, until the block is manually resolved. Recognizable by `WARN nticationFailureLoggerListener - Authentication failure` in the XWiki logs, with `CaptchaException` as the cause if logging for `org.xwiki.security.authentication` is set to TRACE.

**Recovery:**
1. Incognito window → `<XWIKI_BASE>/bin/view/Main/?oidc.skipped=true`
2. Log in with the affected technical user, solve CAPTCHA
3. Block is then lifted, REST access works again

Globally configurable (no per-user exception possible) under Administration → Authentication - deliberately not disabled, as the native login form remains accessible via `?oidc.skipped=true` and this protection is also needed against real attacks.
