"""Model access for chat, categorization, and email summaries.

Users pick one connection: OpenRouter, Claude (Anthropic), or OpenAI.
Calls happen only when a feature asks for a completion. Nothing here runs
on a timer.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import anthropic
import streamlit as st
import toml
from openai import OpenAI

from finapp.db import get_state, set_state

PROVIDERS = ("openrouter", "anthropic", "openai")

PROVIDER_INFO = {
    "openrouter": {
        "label": "OpenRouter",
        "default_model": "qwen/qwen3.8-27b:free",
        "default_categorize_model": "z-ai/glm-5.3-flash",
        "placeholder": "sk-or-v1-...",
        "help_url": "https://openrouter.ai/keys",
        "secret_section": "openrouter",
        "blurb": "One key for many models, billed per request.",
    },
    "anthropic": {
        "label": "Claude",
        "default_model": "claude-opus-4-6",
        "default_categorize_model": "claude-haiku-4-5",
        "placeholder": "sk-ant-...",
        "help_url": "https://console.anthropic.com",
        "secret_section": "anthropic",
        "blurb": "Direct Anthropic API. Chat uses Opus, categorization uses Haiku.",
    },
    "openai": {
        "label": "OpenAI",
        "default_model": "gpt-4.1-mini",
        "default_categorize_model": "gpt-4.1-mini",
        "placeholder": "sk-...",
        "help_url": "https://platform.openai.com/api-keys",
        "secret_section": "openai",
        "blurb": "Direct OpenAI API.",
    },
}

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Tried in order when the selected free model is rate-limited. These are
# specific models, so the random free router cannot pick a safety classifier.
_OPENROUTER_FREE_FALLBACKS = (
    "nvidia/nemotron-3-super-120b-a12b:free",
    "inclusionai/ling-3.0-flash-fin:free",
    "thinkingmachines/inkling:free",
    "google/gemma-4-31b-it:free",
)


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    api_key: str
    model: str
    categorize_model: str
    zdr: bool
    key_source: str

    @property
    def ready(self) -> bool:
        return len(self.api_key) > 20


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict | None


@dataclass
class ModelTurn:
    text: str
    tool_calls: list[ToolCall]
    assistant_message: dict


def has_secret_key(provider: str) -> bool:
    return len(_secret_key(provider)) > 20


def _secret_key(provider: str) -> str:
    section = PROVIDER_INFO[provider]["secret_section"]
    try:
        block = st.secrets.get(section, {})
        value = block.get("api_key", "") if block else ""
    except Exception:
        value = ""
    return (value or "").strip()


def _infer_provider() -> str:
    saved = get_state("llm_provider") or ""
    if saved in PROVIDER_INFO:
        return saved
    if _secret_key("anthropic"):
        return "anthropic"
    if _secret_key("openrouter"):
        return "openrouter"
    if _secret_key("openai"):
        return "openai"
    return "openrouter"


def models_for(provider: str) -> tuple[str, str]:
    info = PROVIDER_INFO[provider]
    model = (get_state(f"llm_model_{provider}") or "").strip() or info["default_model"]
    categorize = (get_state(f"llm_categorize_model_{provider}") or "").strip() or info["default_categorize_model"]
    return model, categorize


def _session_keys() -> dict:
    keys = st.session_state.get("_llm_keys")
    if not isinstance(keys, dict):
        keys = {}
        st.session_state["_llm_keys"] = keys
    legacy = st.session_state.pop("_anthropic_api_key", None)
    if legacy and "anthropic" not in keys:
        keys["anthropic"] = legacy
    return keys


def get_llm_config() -> LLMConfig:
    """Resolve the saved provider. A key in this session wins over secrets.toml."""
    provider = _infer_provider()
    model, categorize_model = models_for(provider)
    zdr = get_state("llm_zdr") == "1"

    keys = _session_keys()
    if provider == "anthropic" and not keys.get("anthropic"):
        db_key = (get_state("anthropic_api_key") or "").strip()
        if len(db_key) > 20:
            keys["anthropic"] = db_key
            set_state("anthropic_api_key", "")

    session_key = (keys.get(provider) or "").strip()
    if len(session_key) > 20:
        return LLMConfig(provider, session_key, model, categorize_model, zdr, "session")

    secret = _secret_key(provider)
    if len(secret) > 20:
        return LLMConfig(provider, secret, model, categorize_model, zdr, "secrets")

    return LLMConfig(provider, "", model, categorize_model, zdr, "")


def _secrets_path() -> Path:
    """The project secrets file. Streamlit merges several paths; the last one wins."""
    try:
        candidates = [Path(path) for path in st.config.get_option("secrets.files")]
    except Exception:
        candidates = []
    existing = [path for path in candidates if path.is_file()]
    if existing:
        return existing[-1]
    return Path(".streamlit") / "secrets.toml"


def _quote_toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def upsert_secret_key(text: str, section: str, api_key: str) -> str:
    """Set api_key inside one TOML section, leaving every other line as it is."""
    quoted = _quote_toml_string(api_key)
    header = re.compile(rf"(?m)^\[{re.escape(section)}\][^\n]*$")
    match = header.search(text)
    if match is None:
        block = f"[{section}]\napi_key = {quoted}\n"
        if not text:
            return block
        if not text.endswith("\n"):
            text += "\n"
        if not text.endswith("\n\n"):
            text += "\n"
        return text + block

    rest = text[match.end():]
    next_header = re.search(r"(?m)^\[", rest)
    body_end = match.end() + (next_header.start() if next_header else len(rest))
    body = text[match.end():body_end]
    key_line = re.compile(
        r"^([ \t]*api_key[ \t]*=[ \t]*)"
        r"(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\n#]*)"
        r"([ \t]*(?:#.*)?)$",
        re.M,
    )
    found = key_line.search(body)
    if found:
        body = body[:found.start()] + f"{found.group(1)}{quoted}{found.group(2)}" + body[found.end():]
    elif body.startswith("\n"):
        body = f"\napi_key = {quoted}{body}"
    else:
        body = f"\napi_key = {quoted}\n{body}"
    return text[:match.end()] + body + text[body_end:]


def _assert_secret_edit(original: str, updated: str, section: str, api_key: str) -> None:
    """Parse before replacing the file so a bad edit cannot wipe other secrets."""
    parsed = toml.loads(updated)
    block = parsed.get(section)
    if not isinstance(block, dict) or block.get("api_key") != api_key:
        raise ValueError("Refusing to write secrets.toml because the API key did not round-trip.")
    if not original.strip():
        return
    previous = toml.loads(original)
    for name, value in previous.items():
        if name == section:
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "api_key":
                        continue
                    if block.get(key) != item:
                        raise ValueError(f"Refusing to write secrets.toml because [{section}] {key} would change.")
            continue
        if parsed.get(name) != value:
            raise ValueError(f"Refusing to write secrets.toml because [{name}] would change.")


def _write_secret_key(provider: str, api_key: str) -> None:
    if any(char in api_key for char in "\n\r"):
        raise ValueError("API key cannot contain a newline.")
    section = PROVIDER_INFO[provider]["secret_section"]
    path = _secrets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    updated = upsert_secret_key(original, section, api_key)
    _assert_secret_edit(original, updated, section, api_key)
    mode = path.stat().st_mode if path.exists() else 0o600
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(updated, encoding="utf-8")
    os.chmod(temporary, mode)
    temporary.replace(path)


def _reload_streamlit_secrets() -> bool:
    """Drop Streamlit's cached secrets so the key just written is visible."""
    try:
        st.secrets._reset()
        st.secrets._parse()
    except Exception:
        return False
    return True


def save_llm_settings(
    provider: str,
    model: str,
    categorize_model: str,
    zdr: bool,
    api_key: str = "",
) -> None:
    if provider not in PROVIDER_INFO:
        raise ValueError(f"Unknown provider: {provider}")
    info = PROVIDER_INFO[provider]
    set_state("llm_provider", provider)
    set_state(f"llm_model_{provider}", (model or "").strip() or info["default_model"])
    set_state(
        f"llm_categorize_model_{provider}",
        (categorize_model or "").strip() or info["default_categorize_model"],
    )
    set_state("llm_zdr", "1" if zdr else "0")
    pasted = (api_key or "").strip()
    if not pasted:
        return
    _write_secret_key(provider, pasted)
    if _reload_streamlit_secrets():
        _session_keys().pop(provider, None)
    else:
        _session_keys()[provider] = pasted


def forget_session_key(provider: str) -> None:
    _session_keys().pop(provider, None)


def to_openai_tools(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        }
        for tool in tools
    ]


def _public_message(message: dict) -> dict:
    return {key: value for key, value in message.items() if not str(key).startswith("_")}


def _parse_arguments(raw) -> dict | None:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _to_anthropic(messages: list[dict], system: str | None) -> tuple[str, list[dict]]:
    system_parts = [system] if system else []
    converted: list[dict] = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            if message.get("content"):
                system_parts.append(message["content"])
            continue
        if role == "user":
            converted.append({"role": "user", "content": message.get("content") or ""})
            continue
        if role == "assistant":
            raw = message.get("_anthropic_content")
            if raw:
                converted.append({"role": "assistant", "content": raw})
                continue
            blocks = []
            text = message.get("content") or ""
            if text:
                blocks.append({"type": "text", "text": text})
            for call in message.get("tool_calls") or []:
                function = call.get("function") or {}
                parsed = _parse_arguments(function.get("arguments"))
                blocks.append({
                    "type": "tool_use",
                    "id": call.get("id"),
                    "name": function.get("name"),
                    "input": parsed or {},
                })
            converted.append({"role": "assistant", "content": blocks or text})
            continue
        if role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": message.get("tool_call_id"),
                "content": message.get("content") or "",
            }
            if converted and converted[-1]["role"] == "user" and isinstance(converted[-1]["content"], list):
                converted[-1]["content"].append(block)
            else:
                converted.append({"role": "user", "content": [block]})
    return "\n".join(part for part in system_parts if part), converted


def _anthropic_turn(
    messages: list[dict],
    *,
    api_key: str,
    model: str,
    system: str | None,
    tools: list[dict] | None,
    max_tokens: int,
    thinking: bool,
) -> ModelTurn:
    client = anthropic.Anthropic(api_key=api_key)
    system_text, anthropic_messages = _to_anthropic(messages, system)
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": anthropic_messages,
    }
    if system_text:
        kwargs["system"] = system_text
    if tools:
        kwargs["tools"] = tools
    if thinking:
        kwargs["thinking"] = {"type": "adaptive"}
    response = client.messages.create(**kwargs)

    text_parts = []
    tool_calls: list[ToolCall] = []
    openai_calls = []
    for block in response.content:
        if block.type == "text" and block.text:
            text_parts.append(block.text)
        elif block.type == "tool_use":
            arguments = block.input if isinstance(block.input, dict) else _parse_arguments(block.input)
            tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=arguments))
            openai_calls.append({
                "id": block.id,
                "type": "function",
                "function": {
                    "name": block.name,
                    "arguments": json.dumps(block.input if isinstance(block.input, dict) else {}),
                },
            })

    text = "\n".join(text_parts)
    assistant: dict = {
        "role": "assistant",
        "content": text if text or not openai_calls else None,
        "_anthropic_content": response.content,
    }
    if openai_calls:
        assistant["tool_calls"] = openai_calls
    return ModelTurn(text=text, tool_calls=tool_calls, assistant_message=assistant)


def _candidate_models(provider: str, model: str) -> list[str]:
    """Free OpenRouter models fall through to the next one after a 429."""
    if provider != "openrouter":
        return [model]
    if not (model.endswith(":free") or model == "openrouter/free"):
        return [model]
    chain: list[str] = []
    if model.endswith(":free") and "content-safety" not in model:
        chain.append(model)
    for candidate in _OPENROUTER_FREE_FALLBACKS:
        if candidate not in chain:
            chain.append(candidate)
    return chain


def _rate_limited(exc: Exception) -> bool:
    return getattr(exc, "status_code", None) == 429


def _openai_client(provider: str, api_key: str) -> OpenAI:
    if provider == "openrouter":
        return OpenAI(
            api_key=api_key,
            base_url=_OPENROUTER_BASE_URL,
            default_headers={"X-OpenRouter-Title": "Money Snap"},
            timeout=120,
        )
    return OpenAI(api_key=api_key, timeout=120)


def _openai_turn(
    messages: list[dict],
    *,
    provider: str,
    api_key: str,
    model: str,
    system: str | None,
    tools: list[dict] | None,
    max_tokens: int,
    zdr: bool,
    thinking: bool,
) -> ModelTurn:
    outbound = [_public_message(message) for message in messages]
    if system:
        outbound = [{"role": "system", "content": system}, *outbound]
    kwargs = {
        "model": model,
        "messages": outbound,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = to_openai_tools(tools)
    extra_body: dict = {}
    if provider == "openrouter" and not thinking:
        # Qwen and other free reasoning models otherwise spend the token budget
        # on hidden reasoning and return an empty message.
        extra_body["reasoning"] = {"enabled": False}
    if provider == "openrouter" and zdr:
        extra_body["provider"] = {"zdr": True}
    if extra_body:
        kwargs["extra_body"] = extra_body

    client = _openai_client(provider, api_key)
    attempts = _candidate_models(provider, model)
    saw_rate_limit = False
    for index, candidate in enumerate(attempts):
        kwargs["model"] = candidate
        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as exc:
            if _rate_limited(exc) and index < len(attempts) - 1:
                saw_rate_limit = True
                continue
            if _rate_limited(exc):
                raise RuntimeError(
                    "The free models are rate-limited right now. Wait a minute and try the summary again."
                ) from exc
            raise
        if not response.choices:
            continue
        message = response.choices[0].message
        tool_calls: list[ToolCall] = []
        openai_calls = []
        for call in message.tool_calls or []:
            raw_arguments = call.function.arguments or "{}"
            tool_calls.append(ToolCall(
                id=call.id,
                name=call.function.name,
                arguments=_parse_arguments(raw_arguments),
            ))
            openai_calls.append({
                "id": call.id,
                "type": "function",
                "function": {"name": call.function.name, "arguments": raw_arguments},
            })

        text = message.content or ""
        if text.strip() or tool_calls:
            assistant: dict = {"role": "assistant", "content": text if text or not openai_calls else None}
            if openai_calls:
                assistant["tool_calls"] = openai_calls
            return ModelTurn(text=text, tool_calls=tool_calls, assistant_message=assistant)

    if saw_rate_limit:
        raise RuntimeError(
            "The free models are rate-limited right now. Wait a minute and try the summary again."
        )
    raise RuntimeError("The model returned an empty response. No email was sent.")


def complete(
    messages: list[dict],
    *,
    cfg: LLMConfig,
    model: str,
    system: str | None = None,
    tools: list[dict] | None = None,
    max_tokens: int = 4096,
    thinking: bool = False,
) -> ModelTurn:
    if not cfg.ready:
        raise RuntimeError("No model API key is set. Add one in Settings.")
    if cfg.provider == "anthropic":
        return _anthropic_turn(
            messages,
            api_key=cfg.api_key,
            model=model,
            system=system,
            tools=tools,
            max_tokens=max_tokens,
            thinking=thinking,
        )
    return _openai_turn(
        messages,
        provider=cfg.provider,
        api_key=cfg.api_key,
        model=model,
        system=system,
        tools=tools,
        max_tokens=max_tokens,
        zdr=cfg.zdr,
        thinking=thinking,
    )


def complete_text(
    prompt: str,
    *,
    cfg: LLMConfig,
    model: str,
    max_tokens: int = 4096,
    thinking: bool = False,
) -> str:
    turn = complete(
        [{"role": "user", "content": prompt}],
        cfg=cfg,
        model=model,
        max_tokens=max_tokens,
        thinking=thinking,
    )
    if not turn.text.strip():
        raise RuntimeError(
            "The model returned an empty response. No email was sent."
        )
    return turn.text
