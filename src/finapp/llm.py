"""LLM providers: OpenRouter (many models) or Anthropic (Claude direct)."""

from __future__ import annotations

from openai import OpenAI

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

OPENROUTER = "openrouter"
ANTHROPIC = "anthropic"
PROVIDERS = (OPENROUTER, ANTHROPIC)

PROVIDER_LABELS = {
    OPENROUTER: "OpenRouter",
    ANTHROPIC: "Anthropic (Claude direct)",
}

OPENROUTER_MODELS = [
    {
        "id": "openai/gpt-5.6-luna",
        "label": "Recommended · GPT-5.6 Luna  $",
        "hint": "OpenAI's cheap tier — default for chat and categorization",
    },
    {
        "id": "deepseek/deepseek-v4-flash",
        "label": "Recommended · DeepSeek V4 Flash  $",
        "hint": "Strong open-weight agent, usually cheaper than Luna",
    },
    {
        "id": "qwen/qwen3.5-27b",
        "label": "Open · Qwen 3.5 27B  $",
        "hint": "Open-weight, solid everyday chat",
    },
    {
        "id": "meta-llama/llama-3.3-70b-instruct",
        "label": "Open · Llama 3.3 70B  $",
        "hint": "Open-weight 70B; confirm tools still work if answers look guessed",
    },
    {
        "id": "openai/gpt-5.6-terra",
        "label": "Balanced · GPT-5.6 Terra  $$",
        "hint": "OpenAI mid-tier — better reviews than Luna",
    },
    {
        "id": "anthropic/claude-sonnet-4.6",
        "label": "Balanced · Claude Sonnet 4.6 (via OpenRouter)  $$",
        "hint": "Claude through OpenRouter — uses your OpenRouter key",
    },
    {
        "id": "openai/gpt-5.6-sol",
        "label": "Strong · GPT-5.6 Sol  $$$",
        "hint": "OpenAI flagship",
    },
    {
        "id": "anthropic/claude-opus-4.6",
        "label": "Strong · Claude Opus 4.6 (via OpenRouter)  $$$",
        "hint": "Opus through OpenRouter — uses your OpenRouter key",
    },
]

ANTHROPIC_MODELS = [
    {
        "id": "claude-haiku-4-5",
        "label": "Claude Haiku 4.5  $",
        "hint": "Fast and cheap — good for categorization",
    },
    {
        "id": "claude-sonnet-4-6",
        "label": "Claude Sonnet 4.6  $$",
        "hint": "Everyday agent quality, billed on your Anthropic account",
    },
    {
        "id": "claude-opus-4-6",
        "label": "Claude Opus 4.6  $$$",
        "hint": "Previous default — best for hard reviews",
    },
]

DEFAULT_MODELS = {
    OPENROUTER: "openai/gpt-5.6-luna",
    ANTHROPIC: "claude-opus-4-6",
}
CATEGORIZE_MODELS = {
    OPENROUTER: "openai/gpt-5.6-luna",
    ANTHROPIC: "claude-haiku-4-5",
}

# Back-compat aliases used by older call sites
DEFAULT_CHAT_MODEL = DEFAULT_MODELS[OPENROUTER]
DEFAULT_CATEGORIZE_MODEL = CATEGORIZE_MODELS[OPENROUTER]


def models_for(provider: str) -> list[dict]:
    return ANTHROPIC_MODELS if provider == ANTHROPIC else OPENROUTER_MODELS


def model_ids_for(provider: str) -> list[str]:
    return [m["id"] for m in models_for(provider)]


def model_label(model_id: str, provider: str | None = None) -> str:
    catalogs = [models_for(provider)] if provider else [OPENROUTER_MODELS, ANTHROPIC_MODELS]
    for catalog in catalogs:
        for row in catalog:
            if row["id"] == model_id:
                return row["label"]
    return model_id


def model_hint(model_id: str, provider: str | None = None) -> str:
    catalogs = [models_for(provider)] if provider else [OPENROUTER_MODELS, ANTHROPIC_MODELS]
    for catalog in catalogs:
        for row in catalog:
            if row["id"] == model_id:
                return row["hint"]
    return ""


def resolve_provider(provider: str | None) -> str:
    return provider if provider in PROVIDERS else OPENROUTER


def resolve_chat_model(model_id: str | None, provider: str | None = None) -> str:
    prov = resolve_provider(provider)
    ids = model_ids_for(prov)
    if model_id and model_id in ids:
        return model_id
    return DEFAULT_MODELS[prov]


def categorize_model(provider: str | None = None) -> str:
    return CATEGORIZE_MODELS[resolve_provider(provider)]


def get_client(api_key: str) -> OpenAI:
    return OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "http://localhost:8501",
            "X-OpenRouter-Title": "Money Snap",
        },
    )


def tools_to_openai(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema") or {"type": "object", "properties": {}},
            },
        }
        for t in tools
    ]


def assistant_to_dict(message) -> dict:
    row: dict = {
        "role": "assistant",
        "content": message.content or None,
    }
    if message.tool_calls:
        row["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments or "{}",
                },
            }
            for tc in message.tool_calls
        ]
    else:
        row["content"] = message.content or ""
    return row


def complete(
    api_key: str,
    model: str,
    messages: list[dict],
    *,
    system: str | None = None,
    tools: list[dict] | None = None,
    max_tokens: int = 4096,
):
    """One OpenRouter chat.completions round. `tools` should already be OpenAI-shaped."""
    client = get_client(api_key)
    payload = list(messages)
    if system:
        payload = [{"role": "system", "content": system}, *payload]
    kwargs: dict = {
        "model": model,
        "messages": payload,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    try:
        return client.chat.completions.create(**kwargs)
    except Exception as exc:
        err = str(exc).lower()
        if "max_tokens" in err:
            kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")
            return client.chat.completions.create(**kwargs)
        raise


def complete_text(
    api_key: str,
    model: str,
    messages: list[dict],
    *,
    provider: str = OPENROUTER,
    system: str | None = None,
    max_tokens: int = 4096,
) -> str:
    """Plain-text completion (categorize, email). No tools."""
    if resolve_provider(provider) == ANTHROPIC:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if "opus" in model:
            kwargs["thinking"] = {"type": "adaptive"}
        response = client.messages.create(**kwargs)
        return next((b.text for b in response.content if b.type == "text"), "")

    response = complete(api_key, model, messages, system=system, max_tokens=max_tokens)
    return response.choices[0].message.content or ""
