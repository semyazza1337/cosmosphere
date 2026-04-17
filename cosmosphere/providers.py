"""LLM provider backends for cosmosphere scoring.

Each provider receives the system prompt + user message,
returns raw text from the model. JSON parsing stays in analyze.py.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)

# Default models per provider — override via env vars
DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.5-flash",
    "claude-code": "claude-sonnet-4-6",
}


class ProviderError(RuntimeError):
    """Missing package, missing API key, or call failure."""


def _call_anthropic(system_prompt: str, user_msg: str) -> str:
    try:
        from anthropic import Anthropic, APIError
    except ImportError:
        raise ProviderError("anthropic package not installed — run: uv sync")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ProviderError("ANTHROPIC_API_KEY not set")

    model = os.environ.get("COSMOSPHERE_MODEL", DEFAULT_MODELS["anthropic"])
    client = Anthropic(api_key=api_key)
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=8192,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )
    except APIError as e:
        raise ProviderError(f"Anthropic API call failed: {e}") from e

    return "".join(
        block.text for block in resp.content if getattr(block, "type", "") == "text"
    )


def _call_openai(system_prompt: str, user_msg: str) -> str:
    try:
        from openai import OpenAI, APIError
    except ImportError:
        raise ProviderError("openai package not installed — run: uv sync --extra openai")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ProviderError("OPENAI_API_KEY not set")

    model = os.environ.get("COSMOSPHERE_MODEL", DEFAULT_MODELS["openai"])
    client = OpenAI(api_key=api_key)
    try:
        resp = client.chat.completions.create(
            model=model,
            max_tokens=8192,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
        )
    except APIError as e:
        raise ProviderError(f"OpenAI API call failed: {e}") from e

    return resp.choices[0].message.content or ""


def _call_gemini(system_prompt: str, user_msg: str) -> str:
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        raise ProviderError("google-genai package not installed — run: uv sync --extra gemini")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ProviderError("GEMINI_API_KEY not set")

    model_name = os.environ.get("COSMOSPHERE_MODEL", DEFAULT_MODELS["gemini"])
    client = genai.Client(api_key=api_key)
    try:
        resp = client.models.generate_content(
            model=model_name,
            contents=user_msg,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=8192,
            ),
        )
    except Exception as e:
        raise ProviderError(f"Gemini API call failed: {e}") from e

    return resp.text or ""


def _call_claude_code(system_prompt: str, user_msg: str) -> str:
    """Use the local `claude` CLI (Claude Code) in non-interactive print mode.

    Runs under the user's Claude Max plan — no separate API key needed.
    Prompt is passed via stdin to avoid ARG_MAX limits with large paper batches.
    """
    claude_bin = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
    if not os.path.isfile(claude_bin):
        raise ProviderError(
            "claude CLI not found. Install Claude Code or set PATH correctly."
        )

    model = os.environ.get("COSMOSPHERE_MODEL", DEFAULT_MODELS["claude-code"])

    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}

    try:
        result = subprocess.run(
            [
                claude_bin,
                "--print",
                "--model", model,
                "--system-prompt", system_prompt,
                "--output-format", "text",
            ],
            input=user_msg,
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
    except subprocess.TimeoutExpired:
        raise ProviderError("claude CLI timed out (>180s)")
    except OSError as e:
        raise ProviderError(f"Failed to launch claude CLI: {e}") from e

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "(no output)").strip()
        raise ProviderError(f"claude CLI exited {result.returncode}: {detail}")

    return result.stdout.strip()


_PROVIDERS = {
    "anthropic": _call_anthropic,
    "openai": _call_openai,
    "gemini": _call_gemini,
    "claude-code": _call_claude_code,
}

AVAILABLE_PROVIDERS = list(_PROVIDERS.keys())


def call_provider(provider: str, system_prompt: str, user_msg: str) -> str:
    """Dispatch to the right LLM backend. Raises ProviderError on failure."""
    fn = _PROVIDERS.get(provider)
    if fn is None:
        raise ProviderError(f"Unknown provider {provider!r}. Choose: {AVAILABLE_PROVIDERS}")
    logger.info("Using provider: %s", provider)
    return fn(system_prompt, user_msg)
