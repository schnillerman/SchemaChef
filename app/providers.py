"""
Provider-Abstraktion: Anthropic (Claude) / OpenAI (ChatGPT) / Google
(Gemini) austauschbar ueber die Admin-Einstellungen. Alle drei liefern
strukturierte JSON-Ausgabe fuer Extraktion und Anreicherung.

Wichtig: Ein Consumer-Abo (Claude Pro/Max, ChatGPT Plus, Gemini
Advanced) ist NICHT dasselbe wie ein API-Key. Fuer den programmatischen
Zugriff hier braucht es separate, meist nutzungsbasiert abgerechnete
API-Keys:
  - Anthropic: console.anthropic.com -> API Keys
  - OpenAI:    platform.openai.com -> API Keys
  - Gemini:    aistudio.google.com/apikey
Bei seltener privater Nutzung (ein paar Rezepte im Monat) bewegen sich
die Kosten im Cent- bis niedrigen Euro-Bereich.
"""
import json

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "source_language": {
            "type": "string",
            "description": "ISO-639-1 Code der Originalsprache, z.B. 'en', 'de', 'th'",
        },
        "ingredients": {"type": "array", "items": {"type": "string"}},
        "steps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "ingredients", "steps"],
}

ENRICH_SCHEMA = {
    "type": "object",
    "properties": {
        "title_translated": {"type": "string"},
        "steps_translated": {"type": "array", "items": {"type": "string"}},
        "ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "original": {"type": "string"},
                    "name_translated": {
                        "type": "string",
                        "description": "Nur der Zutatenname in der Zielsprache, OHNE Menge/Einheit, z.B. 'Kartoffeln'",
                    },
                    "amount_translated": {
                        "type": "string",
                        "description": "Nur Menge+Einheit, z.B. '500g' oder '1 Stange' oder '' falls keine Mengenangabe vorhanden",
                    },
                    "details_translated": {
                        "type": "string",
                        "description": "Zubereitungshinweis falls vorhanden, z.B. 'gerieben', 'getrocknet', 'gehackt', 'in Scheiben' - sonst leerer String",
                    },
                    "alternative": {"type": ["string", "null"]},
                    "bezugsquelle": {"type": ["string", "null"]},
                },
                "required": ["original", "name_translated", "amount_translated"],
            },
        },
    },
    "required": ["title_translated", "steps_translated", "ingredients"],
}


def _to_gemini_schema(schema: dict) -> dict:
    """Konvertiert die (lowercase) JSON-Schema-Notation, die fuer
    Anthropic/OpenAI genutzt wird, in Googles (uppercase) Format -
    damit nicht zwei Schemata von Hand gepflegt werden muessen."""
    type_map = {"object": "OBJECT", "array": "ARRAY", "string": "STRING", "null": "NULL"}

    def conv(node: dict) -> dict:
        t = node.get("type")
        if isinstance(t, list):
            non_null = [x for x in t if x != "null"]
            out = conv({**node, "type": non_null[0]}) if non_null else {"type": "STRING"}
            out["nullable"] = "null" in t
            return out
        out = {"type": type_map.get(t, "STRING")}
        if node.get("description"):
            out["description"] = node["description"]
        if t == "object":
            out["properties"] = {k: conv(v) for k, v in node.get("properties", {}).items()}
            if "required" in node:
                out["required"] = node["required"]
        elif t == "array":
            out["items"] = conv(node["items"])
        return out

    return conv(schema)


def _anthropic_call(model: str, api_key: str, prompt: str, schema: dict, tool_name: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    tool = {"name": tool_name, "description": "Strukturierte Ausgabe.", "input_schema": schema}
    message = client.messages.create(
        model=model,
        max_tokens=3000,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool_name},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in message.content:
        if block.type == "tool_use" and block.name == tool_name:
            return block.input
    raise ValueError("Anthropic hat keine strukturierte Antwort geliefert")


def _openai_call(model: str, api_key: str, prompt: str, schema: dict, tool_name: str) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": "Strukturierte Ausgabe.",
                    "parameters": schema,
                },
            }
        ],
        tool_choice={"type": "function", "function": {"name": tool_name}},
    )
    call = response.choices[0].message.tool_calls[0]
    return json.loads(call.function.arguments)


def _gemini_call(model: str, api_key: str, prompt: str, schema: dict, tool_name: str) -> dict:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_to_gemini_schema(schema),
        ),
    )
    return json.loads(response.text)


_CALLERS = {"anthropic": _anthropic_call, "openai": _openai_call, "gemini": _gemini_call}


def call_llm(provider: str, model: str, api_key: str, prompt: str, schema: dict, tool_name: str) -> dict:
    if provider not in _CALLERS:
        raise ValueError(f"Unbekannter Provider: {provider}")
    if not api_key:
        raise ValueError(
            f"Kein API-Key fuer Provider '{provider}' konfiguriert (siehe .env / Admin-Einstellungen)"
        )
    if not model:
        raise ValueError(f"Kein Modellname fuer Provider '{provider}' konfiguriert")
    return _CALLERS[provider](model, api_key, prompt, schema, tool_name)


# Model-IDs, die zwar in der API-Modell-Liste auftauchen, aber keine
# Chat-Completion-Modelle sind (Embeddings, Audio, Bildgenerierung
# etc.) - Deny-Liste statt Allow-Liste, damit neue Chat-Modellfamilien
# nicht versehentlich mit ausgefiltert werden.
_OPENAI_NON_CHAT_HINTS = (
    "embedding", "whisper", "tts", "dall-e", "moderation",
    "davinci", "babbage", "ada", "audio",
)


def list_models(provider: str, api_key: str) -> list[str]:
    """Fragt die tatsaechlich verfuegbaren Modelle beim jeweiligen
    Anbieter ab (Model-Listing-API), damit die Admin-UI ein Dropdown
    statt eines Freitextfelds anbieten kann - verhindert Tippfehler."""
    if not api_key:
        raise ValueError(f"Kein API-Key fuer '{provider}' konfiguriert")

    if provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        return sorted((m.id for m in client.models.list()), reverse=True)

    if provider == "openai":
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        return sorted(
            m.id
            for m in client.models.list().data
            if not any(hint in m.id for hint in _OPENAI_NON_CHAT_HINTS)
        )

    if provider == "gemini":
        from google import genai

        client = genai.Client(api_key=api_key)
        return sorted(
            m.name.removeprefix("models/")
            for m in client.models.list()
            if "generateContent" in (m.supported_actions or [])
        )

    raise ValueError(f"Unbekannter Provider: {provider}")
