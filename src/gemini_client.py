"""
StockSage AI - Gemini API Client Component (Phase 8)

Handles GEMINI_API_KEY environment variable lookup, lazy initialization of the official
Google Gemini SDK client (`google.genai`), graceful missing-key handling, timeout/error
safety, and strict grounded prompt generation for natural-language answer phrasing.
"""

import os
import json
from typing import Optional, Dict, Any

# Centralized Gemini Model Identifier
GEMINI_MODEL = "gemini-2.5-flash"


def is_gemini_configured() -> bool:
    """Check if GEMINI_API_KEY environment variable is set and non-empty."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    return len(key) > 0


def get_gemini_client():
    """
    Return an initialized google.genai.Client instance if configured, or None.
    Handles imports lazily so missing dependencies do not crash app startup.
    """
    if not is_gemini_configured():
        return None

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    try:
        from google import genai
        return genai.Client(api_key=api_key)
    except Exception:
        # Fallback for deprecated google.generativeai if google.genai is missing
        try:
            import google.generativeai as genai_legacy
            genai_legacy.configure(api_key=api_key)
            return genai_legacy
        except Exception:
            return None


def generate_grounded_response(
    user_question: str,
    verified_context: Dict[str, Any],
    intent: Optional[str] = None
) -> Optional[str]:
    """
    Pass verified structured Python analytics context to Gemini API to convert into a concise,
    manager-friendly natural-language answer.
    Returns None if Gemini is unconfigured or if API execution fails.
    """
    client = get_gemini_client()
    if client is None:
        return None

    # Construct strict system grounding prompt
    system_instruction = (
        "You are StockSage AI, an expert retail sales and inventory copilot.\n"
        "Your task is to answer the store manager's question using ONLY the provided verified retail data context.\n\n"
        "STRICT GROUNDING RULES:\n"
        "1. Never invent or guess numbers, products, stores, sales, or stock levels.\n"
        "2. Do not recompute or round numbers provided in the context; use the formatted values as given.\n"
        "3. Preserve Indian Rupee currency formatting (₹) and exact units (units, days, units/day).\n"
        "4. If the context indicates cost or margin data is unavailable, state clearly that profit cannot be calculated.\n"
        "5. Do not assert root causes for sales changes unless explicitly provided in the context.\n"
        "6. Do not present assumptions as guaranteed facts.\n"
        "7. Keep your answer concise, direct, professional, and manager-friendly.\n"
        "8. If no matching products or issues exist in the context, state clearly that no records were found."
    )

    context_json = json.dumps(verified_context, indent=2, default=str)

    prompt = (
        f"{system_instruction}\n\n"
        f"USER QUESTION: {user_question}\n"
        f"INTENT: {intent or 'general'}\n\n"
        f"VERIFIED RETAIL CONTEXT (MACHINE-CHECKED DATA):\n"
        f"```json\n{context_json}\n```\n\n"
        f"Provide a clear, grounded natural-language summary for the retail manager based ONLY on the context above."
    )

    try:
        # Check if using official google.genai Client
        if hasattr(client, "models") and hasattr(client.models, "generate_content"):
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt
            )
            if response and hasattr(response, "text") and response.text:
                return response.text.strip()
        # Legacy fallback
        elif hasattr(client, "GenerativeModel"):
            model = client.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            if response and hasattr(response, "text") and response.text:
                return response.text.strip()
    except Exception:
        # Fallback to local response builder on API failure/timeout/quota error
        return None

    return None
