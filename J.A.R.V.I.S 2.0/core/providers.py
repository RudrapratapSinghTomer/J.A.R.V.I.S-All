from __future__ import annotations

import os
import asyncio
from typing import Any
import google.generativeai as genai
import logging
import httpx
import json
import subprocess
from core.llm_client import LLMRequest

logger = logging.getLogger("jarvis.providers")


async def gemini_provider(request: LLMRequest) -> str:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise Exception("GOOGLE_API_KEY not found.")

    model_name = request.metadata.get("model") or os.getenv(
        "GEMINI_DEFAULT_MODEL", "gemini-2.0-flash"
    )

    try:
        genai.configure(api_key=api_key)

        # Try the requested model
        m_name = (
            f"models/{model_name}"
            if not model_name.startswith("models/")
            else model_name
        )
        model = genai.GenerativeModel(m_name)
        response = await model.generate_content_async(request.prompt)
        return response.text
    except Exception as e:
        if "not found" in str(e).lower():
            logger.warning(
                "Gemini model %s not found. Discovering a supported fallback model.",
                model_name,
            )
            try:
                candidates = []
                for m in genai.list_models():
                    methods = getattr(m, "supported_generation_methods", []) or []
                    if "generateContent" in methods:
                        candidates.append(getattr(m, "name", ""))

                if not candidates:
                    raise Exception(
                        "No Gemini models with generateContent support were discovered."
                    )

                # Prefer modern flash models, then any available generateContent model.
                preferred = [
                    name
                    for name in candidates
                    if "flash" in name.lower() and "exp" not in name.lower()
                ]
                fallback_name = preferred[0] if preferred else candidates[0]

                logger.warning("Gemini fallback selected: %s", fallback_name)
                model = genai.GenerativeModel(fallback_name)
                response = await model.generate_content_async(request.prompt)
                return response.text
            except Exception as e2:
                raise Exception(f"Gemini Fallback discovery failed: {repr(e2)}")
        raise Exception(f"Gemini Provider failed: {repr(e)}")


async def nvidia_provider(request: LLMRequest) -> str:
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise Exception("NVIDIA_API_KEY not found.")

    base_url = os.getenv(
        "JARVIS_NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
    )
    model_name = request.metadata.get("model") or os.getenv(
        "NVIDIA_MODEL", "meta/llama-3.1-405b-instruct"
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": request.prompt}],
                    "temperature": 0.2,
                    "top_p": 0.7,
                    "max_tokens": 1024,
                    **(
                        {
                            "extra_body": {
                                "chat_template_kwargs": {"enable_thinking": True},
                                "reasoning_budget": 16384,
                            }
                        }
                        if "nemotron-3-super" in model_name
                        else {}
                    ),
                },
                timeout=120.0,  # Increased for 405B latency
            )
            if response.status_code == 429:
                logger.warning("NVIDIA API rate limited (429 Too Many Requests).")
            elif response.status_code in {500, 502, 503, 504}:
                logger.warning(
                    "NVIDIA API transient upstream error (%s).", response.status_code
                )
            elif response.status_code != 200:
                logger.error(
                    f"NVIDIA API Error: {response.status_code} - {response.text}"
                )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        raise Exception(f"NVIDIA Provider failed: {repr(e)}")


async def ollama_provider(request: LLMRequest) -> str:
    """Ollama provider for both local and cloud endpoints."""
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model_name = request.metadata.get("model") or os.getenv("OLLAMA_MODEL", "llama3.1")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{host}/api/generate",
                json={
                    "model": model_name,
                    "prompt": request.prompt,
                    "stream": False,
                },
                timeout=120.0,
            )
            response.raise_for_status()
            data = response.json()
            return data["response"]
    except Exception as e:
        raise Exception(f"Ollama Provider failed: {repr(e)}")
