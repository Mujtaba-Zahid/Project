"""
services/groq_client.py — Groq LLM Client for AI Financial Advisor
──────────────────────────────────────────────────────────────────
Public client layer that delegates to GroqMiddleware.
Maintains backward-compatible API functions:
  - chat(user_id, user_message)
  - clear_chat_history(user_id)
  - _fallback_response(user_message)
"""

from typing import Dict, Optional
from .groq_middleware import GroqMiddleware, DEFAULT_MODEL, SUPPORTED_MODELS


def _get_api_key(user_id: Optional[int] = None) -> Optional[str]:
    """Get active Groq API key for a user (or from environment)."""
    key, _ = GroqMiddleware.resolve_api_key(user_id)
    return key


def _fallback_response(user_message: str) -> str:
    """Generate helpful rule-based advice when Groq API is unavailable."""
    return GroqMiddleware._fallback_response(user_message)


def chat(user_id: int, user_message: str, model: Optional[str] = None) -> Dict:
    """Send a message to the Groq AI advisor and return the response."""
    return GroqMiddleware.chat(user_id, user_message, model_override=model)


def clear_chat_history(user_id: int):
    """Delete all chat messages for a user."""
    GroqMiddleware.clear_history(user_id)
