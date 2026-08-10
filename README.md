# SchemaChef

SchemaChef converts recipes from any language into schema.org Recipe objects in a selectable target language and saves them to XWiki, ready for scraping.

## Requirements
- Docker (container-based deployment)
- XWiki instance with admin access (can be hosted anywhere)

## Key features
- Web UI for interactive use and configuration
- Choose AI provider (Gemini, ChatGPT, Claude) and model in the Web UI
- Least-changing configuration via environment variables and secret files; runtime parameters and templates in the Web UI
- Input: any website URL containing a recipe
- Output: an XWiki page containing an embedded {{MicroData-HTML}} block with schema.org Recipe microdata
- Template-driven ingredient & instruction formatting to improve scraper compatibility (example: KitchenOwl)

## How it works (high level)
1. Provide a source recipe URL.
2. The selected AI provider normalizes and maps recipe content to schema.org Recipe fields.
3. The result is rendered using the chosen language and templates.
4. The generated Recipe is posted to XWiki as a page containing an embedded MicroData-HTML block.

## Configuration
- Minimal/unchanging settings are provided via environment variables and secret files (for example: service endpoints, XWiki credentials, and other deployment-level config).
- API keys are deposited in secret files (not in the web UI).
- Dynamic settings (templates, target language, provider/model selection, and other per-job parameters) are set in the Web UI.

## Templates
- Templates are edited and managed in the Web UI and persisted in the application database.
- Template example (KitchenOwl style):
  - `{{INGREDIENT}}[, {{AMOUNT}}]` — square brackets denote an optional segment which will be omitted if the variable inside is empty. Variables (e.g., `INGREDIENT`, `AMOUNT`) are pre-filled by the AI.

## XWiki integration
- The app saves generated Recipe pages to XWiki.
- Authentication: basic auth (to be confirmed).
- The page content includes an embedded `{{MicroData-HTML}}` block so the page contains scraper-friendly schema.org microdata.

### Before:
E.g., see https://griechischesmagazin.de/briam-tourlou/

### After:
```
{{html}}
<div itemscope itemtype="https://schema.org/Recipe">
  <h1 itemprop="name">Briam-Tourlou</h1>
  <ul>
    <li itemprop="recipeIngredient">Auberginen, 2-3,  (oder )</li>
    <li itemprop="recipeIngredient">Zucchini, 2,  (oder )</li>
    <li itemprop="recipeIngredient">Kartoffeln, 1 kg,  (oder )</li>
    <li itemprop="recipeIngredient">rote oder grüne Paprikaschoten, 3,  (oder )</li>
    <li itemprop="recipeIngredient">Tomaten, 3, , reif, gerieben (oder )</li>
    <li itemprop="recipeIngredient">Olivenöl, 80 ml,  (oder )</li>
    <li itemprop="recipeIngredient">Zwiebeln, 2, , gehackt (oder )</li>
    <li itemprop="recipeIngredient">Knoblauchzehen, 2, , fein gehackt (oder )</li>
    <li itemprop="recipeIngredient">Petersilie, 3-4 EL, , fein gehackt (oder )</li>
  </ul>
  <div itemprop="recipeInstructions">
    <p>Die Auberginen in mittlere Stücke schneiden, salzen, 20 Minuten ruhen lassen, mit kaltem Wasser abspülen und trocknen.</p>
    <p>Legen Sie sie auf ein Backblech, das Sie mit Backpapier ausgelegt haben. Fetten Sie sie mit einem Pinsel mit Öl ein. Würzen Sie sie mit Salz und Pfeffer. Bei 200 °C backen, bis sie leicht gebräunt sind (ca. 20 Minuten).</p>
    <p>Zucchini und Kartoffeln schälen und in mittelgroße Stücke schneiden. Den Vorgang wie bei den Auberginen auch für die Zucchini wiederholen.</p>
    <p>Paprika waschen und in Stücke schneiden.</p>
    <p>Legen Sie die Kartoffeln auf ein Backblech. Fügen Sie 1–2 Esslöffel Öl, Salz und Pfeffer hinzu und mischen Sie alles. Bei 200 °C backen, bis sie leicht gebräunt sind.</p>
    <p>Das Olivenöl in einen Topf geben und bei starker Hitze erhitzen. Zwiebeln und Knoblauch anbraten. Tomaten, Paprika und Petersilie hinzufügen. Die Hitze senken und 10 Minuten kochen lassen. Mit Salz und Pfeffer würzen.</p>
    <p>Das gesamte Gemüse und die Tomatensauce auf ein Backblech geben und gut mischen. Bei 180 °C ca. 40 Minuten backen.</p>
    <p>Möglicherweise müssen Sie während des Backens etwas heißes Wasser hinzufügen. Rühren Sie das Gericht vorsichtig um, um das Gemüse nicht zu zerdrücken.</p>
  </div>
</div>
{{/html}}
```

## Data & privacy
- API keys are stored in secret files.
- Recipe transformation history is recorded as links to the generated XWiki pages (no full-text recipe copies are stored locally beyond those links).

## Supported languages
- English (EN) and German (DE) are supported now; Weblate integration is planned for broader localization.

## License
- MIT

## Roadmap / TODO
- Add before/after example recipes (source → resulting XWiki page / JSON-LD)
- Implement and document error handling and logging (conversion failures, rate limits, XWiki errors)
- Add automated tests and CI config, plus badges
- Confirm XWiki authentication method and provide configuration details (endpoint, page path rules)
- Document Docker run / compose instructions and recommended deployment examples
- Expand supported languages and add Weblate pipeline

## Contributing
Contributions welcome — please open an issue or a pull request.
