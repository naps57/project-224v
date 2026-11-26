"""Call the language model, saving every reply on disk so reruns are free and give the same answers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

MODEL = "gemini-3.8-flash"
TEMPERATURE = 0.0
CACHE = Path(__file__).resolve().parents[2] / "cache" / "llm"


def ask_llm(prompt: str) -> str:
    """The model's reply to `prompt`, from the cache if this exact call was made before."""
    key = hashlib.sha256(json.dumps([MODEL, TEMPERATURE, prompt]).encode()).hexdigest()
    path = CACHE / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())["reply"]
    reply = _call_gemini(prompt)
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": MODEL, "prompt": prompt, "reply": reply}, indent=1))
    return reply


def _call_gemini(prompt: str) -> str:
    from google import genai  # imported here so tests and cached runs work without the package or a key

    # Reads GEMINI_API_KEY from the environment. A call that takes over a minute is retried, up to 5 tries.
    retry = genai.types.HttpRetryOptions(attempts=5)
    client = genai.Client(http_options=genai.types.HttpOptions(timeout=60_000, retry_options=retry))
    config = genai.types.GenerateContentConfig(temperature=TEMPERATURE)
    return client.models.generate_content(model=MODEL, contents=prompt, config=config).text.strip()
