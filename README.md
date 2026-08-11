# SchemaChef

SchemaChef converts recipes from any language into schema.org Recipe objects in a selectable target language and saves them to XWiki, ready for scraping.

## Quick links
- For detailed implementation notes, configuration examples, and troubleshooting, see [DETAILS.md](https://github.com/schnillerman/SchemaChef/blob/main/DETAILS.md).

## Requirements
- Docker (container-based deployment)
- XWiki instance with admin access (can be hosted anywhere)

## Key features
- Web UI for interactive use and configuration
- Choose AI provider (Gemini, ChatGPT, Claude) and model in the Web UI
- Least-changing configuration via environment variables and secret files; runtime parameters and templates in the Web UI
- Input: any website URL containing a recipe
- Output: an XWiki page containing an embedded `{{MicroData-HTML}}` block with schema.org Recipe microdata
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
- Template example (KitchenOwl style, actual default):
  * `{{NAME}}[, {{DETAILS}}][, {{AMOUNT}}][ (or: {{ALTERNATIVE}})]` — square brackets denote an optional segment which is omitted entirely if any placeholder inside it is empty. Available variables: `NAME`, `AMOUNT` (always present), `DETAILS`, `ALTERNATIVE` (often empty).

## XWiki integration
- The app saves generated Recipe pages to XWiki.
- Authentication: basic auth.
- The page content includes an embedded `{{MicroData-HTML}}` block so the page contains scraper-friendly schema.org microdata.

### Before:
E.g., see https://griechischesmagazin.de/briam-tourlou/

### After:
```
{{html}}
<div itemscope itemtype="https://schema.org/Recipe">
  <h1 itemprop="name">Briam-Tourlou</h1>
  <ul>
    <li itemprop="recipeIngredient">Eggplants, 2-3</li>
    <li itemprop="recipeIngredient">Zucchini, 2</li>
    <li itemprop="recipeIngredient">Potatoes, 1 kg</li>
    <li itemprop="recipeIngredient">Bell peppers, red or green, 3</li>
    <li itemprop="recipeIngredient">Tomatoes, ripe, grated, 3</li>
    <li itemprop="recipeIngredient">Olive oil, 80 ml</li>
    <li itemprop="recipeIngredient">Onions, chopped, 2</li>
    <li itemprop="recipeIngredient">Garlic cloves, finely chopped, 2</li>
    <li itemprop="recipeIngredient">Parsley, finely chopped, 3-4 tbsp</li>
  </ul>
  <div itemprop="recipeInstructions">
    <p>Cut the eggplants into medium pieces, salt them, let rest for 20 minutes, rinse with cold water, and dry.</p>
    <p>Place them on a baking sheet lined with parchment paper. Brush them with oil. Season with salt and pepper. Bake at 200°C until they are light[...]</p>
    <p>Peel the zucchini and potatoes and cut into medium-sized pieces. Repeat the process for the zucchini as for the eggplants.</p>
    <p>Wash the bell peppers and cut into pieces.</p>
    <p>Place the potatoes on a baking sheet. Add 1-2 tablespoons of oil, salt, and pepper, and mix everything. Bake at 200°C until lightly browned.</p>
    <p>Add the olive oil to a pot and heat over high heat. Sauté the onions and garlic. Add the tomatoes, bell peppers, and parsley. Reduce the heat and simmer for 10 minutes.[...]</p>
    <p>Place all the vegetables and the tomato sauce on a baking sheet and mix well. Bake at 180°C for about 40 minutes.</p>
    <p>You may need to add some hot water during baking. Stir the dish carefully so as not to crush the vegetables.</p>
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
- Add automated tests and CI config, plus badges
- Implement and document structured error handling and logging (conversion failures, rate limits, XWiki errors)
- Expand supported languages and add Weblate pipeline
- Add more before/after example recipes

## Contributing
Contributions welcome — please open an issue or a pull request.

---

## Extended Documentation
A detailed, translated version of the German design notes, setup instructions, architecture decisions, and troubleshooting is available in [DETAILS.md](https://github.com/schnillerman/SchemaChef/blob/main/DETAILS.md). This file includes:

- Full explanation of the two separate language settings (target recipe language vs. UI language)
- Configuration levels (compose env, Docker secrets, DB/admin) and what requires a recreate/rebuild
- Synology / Container Manager and reverse-proxy notes
- Reasoning about APP_SECRET_KEY vs DB credentials and the choice of SQLite
- XWiki Technical User guidance and how to create/test it
- Pages/endpoints overview and admin behavior
- Multi-provider API key policy and model selection details
- Resource expectations (image size, RAM, workers)
- Open issues and next steps
- KitchenOwl ingredient format and template handling
- Schema migrations
- Duplicate handling and required attribution behavior
- Troubleshooting steps for XWiki CAPTCHA/lockouts
