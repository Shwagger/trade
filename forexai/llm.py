"""Optional local LLM layer (Ollama).

What the LLM is **not** allowed to do here: predict prices, choose a direction,
or size a position. Language models have no edge on tick data, and asking one
"will EURUSD go up?" produces confident nonsense.

What it is good at, and all it does in this system:

1. explain, in plain language, why the numeric stack reached its decision
2. act as a *one-way* safety valve - it may downgrade a trade to WAIT when the
   context looks dangerous, but it can never create or enlarge a trade

Runs fully offline against Ollama on ``localhost:11434``. Disabled by default;
when the daemon is not running everything degrades to a template explanation,
never to an error. On an 8 GB machine use a 3B-class model
(``ollama pull llama3.2:3b`` or ``qwen2.5:3b-instruct``).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

import pandas as pd

DEFAULT_ENDPOINT = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "llama3.2:3b"

SYSTEM_RULES = (
    "You are a risk reviewer for a rules-based FX system. You never predict "
    "prices and never choose a direction. You receive a decision that a "
    "quantitative model already made, and you answer with strict JSON: "
    '{"explanation": "<= 40 words", "concern": "none|minor|serious"}. '
    "Use concern=serious only for a clear structural risk such as extreme "
    "volatility, a signal that contradicts the dominant higher-timeframe trend, "
    "or an exhausted move."
)


@dataclass
class LLMReview:
    available: bool
    explanation: str
    concern: str = "none"

    @property
    def vetoes(self) -> bool:
        return self.concern == "serious"


def _template_explanation(context: dict) -> str:
    bits = [
        f"{context['action']} at confidence {context['confidence']:.0%}",
        f"trend {'up' if context['htf_trend'] > 0 else 'down'} on the higher timeframe",
        f"ADX {context['adx']:.0f}",
        f"RSI {context['rsi']:.0f}",
        f"ATR {context['atr_pips']:.1f} pips",
    ]
    return "; ".join(bits) + "."


def build_context(features_row: pd.Series, decision, price: float, pip_size: float) -> dict:
    return {
        "action": decision.action,
        "confidence": float(decision.confidence),
        "ml_score": round(float(decision.ml_score), 3),
        "ta_score": round(float(decision.ta_score), 3),
        "price": round(float(price), 5),
        "atr_pips": round(float(features_row.get("atr", float("nan")) / pip_size), 1),
        "adx": round(float(features_row.get("adx", float("nan"))), 1),
        "rsi": round(float(features_row.get("rsi", float("nan"))), 1),
        "htf_trend": round(float(features_row.get("htf24_trend", 0.0)), 2),
        "bb_pct_b": round(float(features_row.get("bb_pct_b", float("nan"))), 2),
        "vol_ratio": round(float(features_row.get("vol_ratio", float("nan"))), 2),
    }


def review(
    context: dict,
    model: str = DEFAULT_MODEL,
    endpoint: str = DEFAULT_ENDPOINT,
    timeout: float = 25.0,
) -> LLMReview:
    """Ask the local model for a review. Never raises."""
    prompt = (
        f"{SYSTEM_RULES}\n\nDecision context (JSON):\n{json.dumps(context, indent=2)}\n\n"
        "Answer with JSON only."
    )
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1, "num_predict": 160},
        }
    ).encode()

    try:
        req = urllib.request.Request(
            endpoint, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
        parsed = json.loads(body.get("response", "{}"))
        return LLMReview(
            available=True,
            explanation=str(parsed.get("explanation", "")).strip()
            or _template_explanation(context),
            concern=str(parsed.get("concern", "none")).strip().lower(),
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return LLMReview(available=False, explanation=_template_explanation(context))


def apply_review(direction: int, review_result: Optional[LLMReview]) -> tuple[int, str]:
    """One-way valve: the review can only ever move a decision towards WAIT."""
    if review_result is None or not review_result.available:
        return direction, "llm not consulted"
    if review_result.vetoes and direction != 0:
        return 0, f"llm veto: {review_result.explanation}"
    return direction, review_result.explanation
