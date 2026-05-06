from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import os
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Dict, Optional, TypeVar, cast

logger = logging.getLogger("jarvis.llm")

T = TypeVar("T")


class ModelCapability(str, Enum):
    LIGHT = "light"  # Fast, cheap, for simple tasks
    BALANCED = "balanced"  # Good all-rounder
    MEDIUM = "medium"  # Strong reasoning
    HEAVY = "heavy"  # Slower, complex reasoning
    UTILITY = "utility"  # Special tasks (cleaning, formatting)
    CODING = "coding"  # Optimized for code
    VISION = "vision"  # Multi-modal support


@dataclass(frozen=True)
class ModelProfile:
    id: str
    provider: str
    capability: ModelCapability
    tier: str = "cloud"  # cloud, local
    is_billable: bool = False
    token_limit: Optional[int] = None
    endpoint: Optional[str] = None


@dataclass(frozen=True)
class LLMRequest:
    prompt: str
    capability: ModelCapability
    purpose: str = "conversation"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model_id: str
    provider: str
    capability: ModelCapability
    metadata: dict[str, Any] = field(default_factory=dict)


Provider = Callable[[LLMRequest], str | Awaitable[str]]


class LLMClient:
    """Dynamic Model Orchestrator with capability-based routing and fallback."""

    def __init__(
        self, default_capability: ModelCapability = ModelCapability.BALANCED
    ) -> None:
        self.registry: List[ModelProfile] = []
        self._providers: Dict[str, Provider] = {}
        self.default_capability = default_capability
        self.on_failure: Optional[Callable[[str], None]] = None
        self._provider_cooldowns: Dict[str, float] = {}
        self._load_registry()

    @staticmethod
    def _base_provider_name(provider: str) -> str:
        return provider.split("_")[0]

    @staticmethod
    def _is_rate_limited(error_text: str) -> bool:
        lowered = error_text.lower()
        return (
            " 429 " in lowered
            or "429" in lowered
            or "too many requests" in lowered
            or "rate limit" in lowered
        )

    @staticmethod
    def _is_transient_provider_error(error_text: str) -> bool:
        lowered = error_text.lower()
        transient_markers = (
            " 500 ",
            " 502 ",
            " 503 ",
            " 504 ",
            "500",
            "502",
            "503",
            "504",
            "bad gateway",
            "service unavailable",
            "gateway timeout",
            "readtimeout",
            "connecttimeout",
            "connecterror",
            "temporarily unavailable",
        )
        return any(marker in lowered for marker in transient_markers)

    @staticmethod
    def _cooldown_seconds() -> float:
        try:
            return float(os.getenv("JARVIS_PROVIDER_COOLDOWN_SECONDS", "90"))
        except ValueError:
            return 90.0

    @staticmethod
    def _transient_cooldown_seconds() -> float:
        try:
            return float(os.getenv("JARVIS_TRANSIENT_PROVIDER_COOLDOWN_SECONDS", "30"))
        except ValueError:
            return 30.0

    def _load_registry(self) -> None:
        """Populate the registry from environment variables."""
        # NVIDIA Models
        for m in os.getenv(
            "NVIDIA_MODELS",
            "meta/llama-3.1-405b-instruct:heavy,meta/llama-3.1-70b-instruct:medium,meta/llama-3.1-8b-instruct:light",
        ).split(","):
            if ":" in m:
                name, cap = m.rsplit(":", 1)
                self.registry.append(
                    ModelProfile(
                        name,
                        "nvidia",
                        ModelCapability[cap.upper()],
                        tier="cloud",
                        is_billable=False,
                    )
                )

        # Ollama Cloud Models
        for m in os.getenv(
            "OLLAMA_CLOUD_MODELS", "qwen3.5:397b-cloud:heavy,llama3.1:70b:medium"
        ).split(","):
            if ":" in m:
                name, cap = m.rsplit(":", 1)
                self.registry.append(
                    ModelProfile(
                        name,
                        "ollama_cloud",
                        ModelCapability[cap.upper()],
                        tier="cloud",
                        is_billable=False,
                        token_limit=8000,
                    )
                )

        # Ollama Local Models
        for m in os.getenv(
            "OLLAMA_LOCAL_MODELS",
            "qwen3:latest:balanced,gemma4:latest:heavy,qwen3:4b-instruct:light",
        ).split(","):
            if ":" in m:
                name, cap = m.rsplit(":", 1)
                self.registry.append(
                    ModelProfile(
                        name,
                        "ollama",
                        ModelCapability[cap.upper()],
                        tier="local",
                        is_billable=False,
                    )
                )

        # Gemini Models (Billable Utility)
        for m in os.getenv(
            "GEMINI_MODELS", "gemini-1.5-flash:utility,gemini-1.5-pro:heavy"
        ).split(","):
            if ":" in m:
                name, cap = m.rsplit(":", 1)
                self.registry.append(
                    ModelProfile(
                        name,
                        "gemini",
                        ModelCapability[cap.upper()],
                        tier="cloud",
                        is_billable=True,
                    )
                )

    def register_provider(self, provider_name: str, handler: Provider) -> None:
        self._providers[provider_name] = handler

    def select_model(
        self, capability: ModelCapability, purpose: str = ""
    ) -> List[ModelProfile]:
        """Selects and ranks models based on capability and purpose."""
        # Filter by capability
        candidates = [m for m in self.registry if m.capability == capability]

        # If no direct match, try adjacent capabilities
        if not candidates:
            candidates = self.registry  # Fallback to all if nothing found

        # Priority Logic:
        # 1. Non-billable Utility (if purpose is cleaning)
        # 2. Local Models (if fast response needed)
        # 3. Cloud (NVIDIA) for Heavy/Coding

        def score(m: ModelProfile) -> float:
            s = 0.0
            if m.capability == capability:
                s += 10
            if purpose == "cleaning" and m.provider == "gemini":
                s += 20
            if purpose != "cleaning" and m.is_billable:
                s -= 50  # Avoid billable models for non-utility
            if m.provider == "nvidia":
                s += 5  # Prefer NVIDIA for quality
            if m.tier == "local":
                s += 2  # Prefer local for speed
            return s

        return sorted(candidates, key=score, reverse=True)

    async def generate(
        self,
        prompt: str,
        capability: ModelCapability,
        purpose: str = "conversation",
        metadata: dict[str, Any] | None = None,
        parallel_count: int = 1,
        fallback: bool = False,
    ) -> LLMResponse:
        """Main entry point for single model generation with fallback."""
        candidates = self.select_model(capability, purpose=purpose)

        if parallel_count > 1 and len(candidates) >= parallel_count:
            return await self.brainstorm(
                prompt, candidates[:parallel_count], capability, purpose, metadata
            )

        last_error = None
        blocked_providers: set[str] = set()

        # If fallback is enabled, ensure we have the full registry as backup
        model_queue = list(candidates)
        if fallback:
            for m in self.registry:
                if m not in model_queue:
                    model_queue.append(m)

        for model in model_queue:
            base_provider = self._base_provider_name(model.provider)
            if base_provider in blocked_providers:
                continue

            cooldown_until = self._provider_cooldowns.get(base_provider, 0.0)
            now = time.monotonic()
            if cooldown_until > now:
                blocked_providers.add(base_provider)
                logger.info(
                    "Skipping provider %s due to cooldown (%.0fs remaining).",
                    base_provider,
                    cooldown_until - now,
                )
                continue

            provider = self._providers.get(model.provider)
            if not provider:
                # Try generic provider if specific not found (e.g. ollama_cloud uses ollama)
                provider = self._providers.get(base_provider)

            if not provider:
                continue

            try:
                # Use selected model's ID in metadata
                request_metadata = dict(metadata or {})
                request_metadata["model"] = model.id

                request = LLMRequest(
                    prompt=prompt,
                    capability=model.capability,
                    purpose=purpose,
                    metadata=request_metadata,
                )

                logger.info(
                    f"Brain choice: [{model.provider}] {model.id} for {purpose}"
                )
                value = provider(request)
                text = await value if inspect.isawaitable(value) else value

                return LLMResponse(
                    text=text,
                    model_id=model.id,
                    provider=model.provider,
                    capability=model.capability,
                    metadata={"tier": model.tier},
                )
            except Exception as e:
                last_error = repr(e)
                logger.warning(f"Model failure: {model.id} - {last_error}")
                is_rate_limited = self._is_rate_limited(last_error)
                is_transient = self._is_transient_provider_error(last_error)

                if is_rate_limited:
                    cooldown_seconds = self._cooldown_seconds()
                    self._provider_cooldowns[base_provider] = (
                        time.monotonic() + cooldown_seconds
                    )
                    blocked_providers.add(base_provider)
                    logger.warning(
                        "Provider %s rate limited. Cooling down for %.0f seconds.",
                        base_provider,
                        cooldown_seconds,
                    )
                elif is_transient:
                    cooldown_seconds = self._transient_cooldown_seconds()
                    self._provider_cooldowns[base_provider] = (
                        time.monotonic() + cooldown_seconds
                    )
                    blocked_providers.add(base_provider)
                    logger.warning(
                        "Provider %s transient upstream failure. Cooling down for %.0f seconds.",
                        base_provider,
                        cooldown_seconds,
                    )
                elif self.on_failure:
                    # Permanent degradation is reserved for likely persistent failures.
                    self.on_failure(base_provider)
                continue

        # Ultimate fallback
        return LLMResponse(
            text=f"[Total Brain Failure: {last_error}] Offline fallback: {prompt[:50]}...",
            model_id="offline",
            provider="system",
            capability=capability,
        )

    async def brainstorm(
        self,
        prompt: str,
        models: List[ModelProfile],
        capability: ModelCapability,
        purpose: str,
        metadata: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Parallel synthesis from multiple brains."""
        logger.info(f"Initiating Brainstorming with {len(models)} models.")

        tasks = []

        async def wrap_provider(p, r):
            val = p(r)
            if inspect.isawaitable(val):
                return await val
            return val

        for model in models:
            provider = self._providers.get(model.provider) or self._providers.get(
                model.provider.split("_")[0]
            )
            if provider:
                req = LLMRequest(
                    prompt,
                    model.capability,
                    purpose,
                    {**(metadata or {}), "model": model.id},
                )
                tasks.append(wrap_provider(provider, req))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid_texts = [r for r in results if isinstance(r, str)]

        if not valid_texts:
            raise Exception("Brainstorming failed: All models returned errors.")

        # Combined response
        combined = "\n\n---\n\n".join(valid_texts)
        return LLMResponse(
            text=combined,
            model_id="brainstorm_group",
            provider="multi",
            capability=capability,
            metadata={"model_count": len(valid_texts)},
        )


def require_capability(capability: ModelCapability):
    """Decorator to specify the required capability for an agent action."""

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Inject capability into context or task if needed
            if "context" in kwargs and kwargs["context"] is not None:
                kwargs["context"]["required_capability"] = capability
            return await func(self, *args, **kwargs)

        return wrapper

    return decorator


def orchestrate(purpose: str):
    """Decorator to automatically handle LLM orchestration for a method."""

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            # This decorator can be used to wrap logic that needs LLM
            # For now, it's a placeholder for more complex logic
            return await func(self, *args, **kwargs)

        return wrapper

    return decorator
