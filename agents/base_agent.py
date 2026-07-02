"""
Base agent class for the AI Council.

Supports 4 providers with automatic fallback:
  - google     → Google AI Studio (Gemini Flash/Pro)
  - nvidia     → NVIDIA NIM (DeepSeek R1 on GPU)
  - groq       → Groq LPU (ultra-fast Llama)
  - openrouter → OpenRouter (fallback/overflow)

Features:
  - Automatic fallback to secondary provider on failure
  - Exponential backoff retry (3 attempts per provider)
  - Response JSON parsing with Pydantic validation
  - Per-provider rate limiting
  - Disk caching (survive mid-run crashes)

ARCHITECTURAL RULE (from blueprint):
  Every number the LLMs see must come from real data sources.
  The LLMs only reason on pre-fetched, verified numbers.
  NEVER ask an LLM for a stock price, PE ratio, or earnings number.
"""

import asyncio
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, TypeVar

from pydantic import BaseModel

from config import (
    GOOGLE_AI_API_KEY,
    OPENROUTER_API_KEY,
    NVIDIA_API_KEY,
    GROQ_API_KEY,
    ANTHROPIC_API_KEY,
    NVIDIA_BASE_URL,
    GROQ_BASE_URL,
    OPENROUTER_BASE_URL,
    ANTHROPIC_BASE_URL,
    OLLAMA_BASE_URL,
    OLLAMA_TIMEOUT,
    AGENT_MODELS,
    LLM_TEMPERATURE,
    LLM_MAX_TOKENS,
    MAX_RETRIES,
    RETRY_BASE_DELAY,
    API_DELAY_GOOGLE,
    API_DELAY_OPENROUTER,
    API_DELAY_NVIDIA,
    API_DELAY_GROQ,
    API_DELAY_ANTHROPIC,
    CACHE_DIR,
)
from utils.exceptions import AgentFailureError, RateLimitExhaustedError
from utils.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

# Provider delay lookup
PROVIDER_DELAYS = {
    "google":     API_DELAY_GOOGLE,
    "openrouter": API_DELAY_OPENROUTER,
    "nvidia":     API_DELAY_NVIDIA,
    "groq":       API_DELAY_GROQ,
    "anthropic":  API_DELAY_ANTHROPIC,
}

# Provider key lookup
PROVIDER_KEYS = {
    "google":     lambda: GOOGLE_AI_API_KEY,
    "openrouter": lambda: OPENROUTER_API_KEY,
    "nvidia":     lambda: NVIDIA_API_KEY,
    "groq":       lambda: GROQ_API_KEY,
    "anthropic":  lambda: ANTHROPIC_API_KEY,
}

# Provider human-readable names for logging
PROVIDER_NAMES = {
    "google":     "Google AI Studio",
    "nvidia":     "NVIDIA NIM",
    "groq":       "Groq LPU",
    "openrouter": "OpenRouter",
    "anthropic":  "Anthropic Claude",
}


class BaseAgent(ABC):
    """
    Abstract base class for all council agents.

    Each agent:
    1. Takes pre-processed data as structured input
    2. Calls its assigned primary LLM provider
    3. If primary fails, auto-falls back to secondary provider
    4. Parses and validates JSON response
    5. Returns a typed Pydantic model
    """

    # Subclasses must set these
    agent_name: str = "base"
    output_model: type[BaseModel] = BaseModel

    def __init__(self):
        # AGENT_MODELS now has 4-tuple: (primary_provider, primary_model, fallback_provider, fallback_model)
        config = AGENT_MODELS.get(
            self.agent_name,
            ("google", "gemini-2.5-flash", "openrouter", "meta-llama/llama-4-maverick:free"),
        )
        self.provider = config[0]
        self.model_id = config[1]
        self.fallback_provider = config[2] if len(config) > 2 else "openrouter"
        self.fallback_model = config[3] if len(config) > 3 else "meta-llama/llama-4-maverick:free"
        self.fallback_model = config[3] if len(config) > 3 else "meta-llama/llama-4-maverick:free"

    @abstractmethod
    def _build_system_prompt(self) -> str:
        """Return the system prompt for this agent. Must be < 500 tokens."""
        ...

    @abstractmethod
    def _build_user_message(self, data: Any) -> str:
        """Convert input data to the user message for the LLM."""
        ...

    async def analyze(self, data: Any) -> dict:
        """
        Main entry point: analyze data and return structured output.

        Flow:
          1. Check disk cache
          2. Try primary provider (with retries)
          3. On failure, try fallback provider (with retries)
          4. On all failures, return safe fallback output
        """
        # Check disk cache
        cached = self._load_cache(data)
        if cached:
            logger.info(f"[{self.agent_name}] Using cached output")
            return cached

        system_prompt = self._build_system_prompt()
        user_message = self._build_user_message(data)

        # Try primary provider
        result = await self._try_provider(
            system_prompt, user_message, self.provider, self.model_id, data
        )
        if result:
            return result

        # Auto-fallback to secondary provider
        logger.warning(
            f"[{self.agent_name}] Primary ({PROVIDER_NAMES.get(self.provider)}) failed. "
            f"Falling back to {PROVIDER_NAMES.get(self.fallback_provider)}..."
        )
        result = await self._try_provider(
            system_prompt, user_message, self.fallback_provider, self.fallback_model, data
        )
        if result:
            return result

        # All providers failed
        logger.error(f"[{self.agent_name}] All providers failed — using safe fallback")
        return self._fallback_output(data)

    async def _try_provider(
        self,
        system_prompt: str,
        user_message: str,
        provider: str,
        model: str,
        data: Any,
    ) -> dict | None:
        """
        Try a specific provider with exponential backoff retries.
        Returns the parsed dict on success, None on all retries exhausted.
        """
        provider_name = PROVIDER_NAMES.get(provider, provider)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                await get_rate_limiter().acquire(provider)

                logger.debug(
                    f"[{self.agent_name}] {provider_name} attempt {attempt}/{MAX_RETRIES} "
                    f"using {model}"
                )

                response_text = await self._call_provider(system_prompt, user_message, provider, model)
                parsed = self._parse_json_response(response_text)
                validated = self.output_model(**parsed)
                result = validated.model_dump()

                self._save_cache(data, result)
                logger.info(
                    f"[{self.agent_name}] ✓ {provider_name} success (attempt {attempt})"
                )
                return result

            except RateLimitExhaustedError:
                logger.warning(
                    f"[{self.agent_name}] {provider_name} rate limit exhausted! "
                    f"Skipping retries and failing over immediately."
                )
                break
            except Exception as e:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    f"[{self.agent_name}] {provider_name} attempt {attempt} failed: "
                    f"{type(e).__name__}: {str(e)[:100]}. "
                    f"{'Retrying in ' + str(delay) + 's' if attempt < MAX_RETRIES else 'Giving up'}"
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(delay)

        return None

    async def _call_provider(
        self, system_prompt: str, user_message: str, provider: str, model: str
    ) -> str:
        """Route to the correct provider call method."""
        if provider == "google":
            return await self._call_google(system_prompt, user_message, model)
        elif provider == "nvidia":
            return await self._call_openai_compatible(
                system_prompt, user_message, model,
                base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY,
                provider_name="NVIDIA NIM",
            )
        elif provider == "groq":
            return await self._call_openai_compatible(
                system_prompt, user_message, model,
                base_url=GROQ_BASE_URL, api_key=GROQ_API_KEY,
                provider_name="Groq",
            )
        elif provider == "openrouter":
            return await self._call_openai_compatible(
                system_prompt, user_message, model,
                base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY,
                provider_name="OpenRouter",
            )
        elif provider == "ollama":
            return await self._call_openai_compatible(
                system_prompt, user_message, model,
                base_url=OLLAMA_BASE_URL, api_key="ollama", # api key is ignored but required by SDK
                provider_name="Ollama",
                timeout=OLLAMA_TIMEOUT,
            )
        elif provider == "anthropic":
            return await self._call_anthropic(system_prompt, user_message, model)
        else:
            raise ValueError(f"Unknown provider: {provider}")

    async def _call_anthropic(self, system_prompt: str, user_message: str, model: str) -> str:
        """Call Anthropic API directly using aiohttp."""
        import aiohttp

        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not set in .env")

        max_tok = LLM_MAX_TOKENS
        if hasattr(self, "_max_tokens"):
            max_tok = self._max_tokens

        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        payload = {
            "model": model,
            "max_tokens": max_tok,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_message}
            ],
            "temperature": LLM_TEMPERATURE
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(ANTHROPIC_BASE_URL, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    err_text = await resp.text()
                    raise RuntimeError(f"Anthropic API error {resp.status}: {err_text}")
                
                response_json = await resp.json()
                text = response_json["content"][0]["text"]
                logger.debug(f"[{self.agent_name}] Anthropic: {text[:200]}...")
                return text

    async def _call_google(self, system_prompt: str, user_message: str, model: str) -> str:
        """Call Google AI Studio (Gemini) using google-genai SDK."""
        from google import genai

        if not GOOGLE_AI_API_KEY:
            raise ValueError("GOOGLE_AI_API_KEY not set in .env")

        client = genai.Client(api_key=GOOGLE_AI_API_KEY)

        max_tok = LLM_MAX_TOKENS
        if hasattr(self, "_max_tokens"):
            max_tok = self._max_tokens

        response = client.models.generate_content(
            model=model,
            contents=user_message,
            config={
                "system_instruction": system_prompt,
                "temperature": LLM_TEMPERATURE,
                "max_output_tokens": max_tok,
                "response_mime_type": "application/json",
            },
        )

        text = response.text
        logger.debug(f"[{self.agent_name}] Google: {text[:200]}...")
        return text

    async def _call_openai_compatible(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
        base_url: str,
        api_key: str,
        provider_name: str = "API",
        timeout: float = 60.0,
    ) -> str:
        """
        Unified OpenAI-compatible call for NVIDIA NIM, Groq, OpenRouter, and Ollama.
        """
        from openai import AsyncOpenAI
        import httpx

        if not api_key and provider_name != "Ollama":
            raise ValueError(f"{provider_name} API key not set in .env")

        http_client = httpx.AsyncClient(timeout=timeout)
        client = AsyncOpenAI(base_url=base_url, api_key=api_key, http_client=http_client)

        max_tok = LLM_MAX_TOKENS
        if hasattr(self, "_max_tokens"):
            max_tok = self._max_tokens

        # Build messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        # NVIDIA NIM and Groq support json_object response format
        # OpenRouter also supports it for most models
        kwargs = dict(
            model=model,
            messages=messages,
            temperature=LLM_TEMPERATURE,
            max_tokens=max_tok,
        )

        # Add JSON response format (supported by all 3 providers)
        try:
            kwargs["response_format"] = {"type": "json_object"}
            response = await client.chat.completions.create(**kwargs)
        except Exception:
            # Some models don't support response_format — retry without it
            kwargs.pop("response_format", None)
            response = await client.chat.completions.create(**kwargs)

        text = response.choices[0].message.content
        logger.debug(f"[{self.agent_name}] {provider_name}: {text[:200]}...")
        return text

    def _parse_json_response(self, text: str) -> dict:
        """
        Extract and parse JSON from LLM response.
        Handles markdown code fences, extra text, DeepSeek's <think> tags, etc.
        """
        if not text:
            raise ValueError("Empty response from LLM")

        # Strip DeepSeek R1 thinking tags (common with reasoning models)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code block
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding first complete { ... } block (greedy from last })
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Could not parse JSON from: {text[:300]}")

    def _fallback_output(self, data: Any) -> dict:
        """Fallback when all providers fail — now fails loudly."""
        ticker = getattr(data, "ticker", "") if hasattr(data, "ticker") else ""
        if not ticker and isinstance(data, dict):
            ticker = data.get("ticker", "")
        raise AgentFailureError(self.agent_name, ticker, "All retries exhausted")

    def _cache_key(self, data: Any) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        data_str = str(data)[:100]
        safe_str = re.sub(r"[^\w]", "_", data_str)[:50]
        return f"{self.agent_name}_{safe_str}_{today}"

    def _load_cache(self, data: Any) -> dict | None:
        cache_file = CACHE_DIR / f"{self._cache_key(data)}.json"
        if cache_file.exists():
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return None

    def _save_cache(self, data: Any, result: dict) -> None:
        cache_file = CACHE_DIR / f"{self._cache_key(data)}.json"
        try:
            cache_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"[{self.agent_name}] Cache save failed: {e}")
