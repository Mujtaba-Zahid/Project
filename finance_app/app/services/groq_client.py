"""
services/groq_client.py — Groq LLM Client for AI Financial Advisor
──────────────────────────────────────────────────────────────────
Calls Groq's OpenAI-compatible API (llama-3.3-70b-versatile) with
user financial context injected as a system prompt.

Gracefully handles missing API keys, rate limits, and network errors
by falling back to helpful rule-based financial advice.
"""

import os
import json
import logging
from typing import List, Dict, Optional

import requests

from ..extensions import db
from ..models.ai_chat import AiChatMessage
from ..models.financial_profile import FinancialProfile
from .recommender import build_groq_context

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
MAX_HISTORY_MESSAGES = 20  # last N messages to include in context


def _get_api_key() -> Optional[str]:
    """Get Groq API key from environment."""
    return os.environ.get('GROQ_API_KEY', '').strip() or None


def _get_chat_history(user_id: int) -> List[Dict[str, str]]:
    """Load recent chat history from the database."""
    messages = (
        AiChatMessage.query
        .filter_by(user_id=user_id)
        .order_by(AiChatMessage.created_at.desc())
        .limit(MAX_HISTORY_MESSAGES)
        .all()
    )
    # Reverse to chronological order
    messages.reverse()
    return [{"role": m.role, "content": m.content} for m in messages]


def _save_message(user_id: int, role: str, content: str, tokens: int = 0):
    """Persist a chat message to the database."""
    msg = AiChatMessage(
        user_id=user_id,
        role=role,
        content=content,
        tokens_used=tokens,
    )
    db.session.add(msg)
    db.session.commit()


def _fallback_response(user_message: str) -> str:
    """Generate helpful rule-based advice when Groq API is unavailable."""
    message_lower = user_message.lower()

    if any(w in message_lower for w in ['save', 'saving', 'savings']):
        return (
            "💡 **Quick Savings Tips:**\n\n"
            "• **Automate it**: Set up a standing transfer on payday — PKR 5,000/month minimum\n"
            "• **NSCs**: National Savings Certificates offer 15–21% annual returns (government-backed)\n"
            "• **72-hour rule**: Wait 3 days before any purchase over PKR 3,000\n"
            "• **Meal prep**: Cook 5 portions on Sundays — saves 60–70% vs eating out\n\n"
            "🔑 *To get personalized AI advice, add your Groq API key in settings (it's free!)*"
        )
    elif any(w in message_lower for w in ['budget', 'spend', 'spending', 'expensive']):
        return (
            "💡 **Budget Control Tips:**\n\n"
            "• **Track everything**: Check your Dashboard for real-time budget status\n"
            "• **InDrive > Uber/Careem**: Save 25–35% on every ride\n"
            "• **Generic meds**: Paracetamol PKR 12 vs Panadol PKR 80 — identical chemistry\n"
            "• **Jazz weekly bundles**: Better per-GB value than monthly packs\n\n"
            "🔑 *Add your free Groq API key to unlock the full AI advisor chat*"
        )
    elif any(w in message_lower for w in ['invest', 'investment', 'return']):
        return (
            "💡 **Investment Options in Pakistan:**\n\n"
            "• **NSCs**: 15–21% p.a., government-backed, zero risk\n"
            "• **Meezan Bank**: ~13% profit, Shariah-compliant\n"
            "• **Mutual Funds**: 12–18% p.a. via Meezan or Al-Meezan\n"
            "• **PSX Index Fund**: Long-term equity growth (higher risk)\n\n"
            "🔑 *For personalized advice, configure your free Groq API key*"
        )
    else:
        return (
            "👋 I'm your AI Financial Advisor! Here's what I can help with:\n\n"
            "• **\"How can I save PKR 10,000 this month?\"**\n"
            "• **\"Cheaper alternative to Careem?\"**\n"
            "• **\"Should I invest in NSCs or mutual funds?\"**\n"
            "• **\"Why is my Food spending so high?\"**\n\n"
            "🔑 *To unlock full AI-powered conversations, add your free Groq API key "
            "via the GROQ_API_KEY environment variable or in the .env file.*"
        )


def chat(user_id: int, user_message: str) -> Dict:
    """Send a message to the Groq AI advisor and return the response.

    Returns:
        dict with keys: 'response', 'tokens_used', 'is_fallback'
    """
    # Save user message
    _save_message(user_id, 'user', user_message)

    api_key = _get_api_key()
    if not api_key:
        response = _fallback_response(user_message)
        _save_message(user_id, 'assistant', response)
        return {
            'response': response,
            'tokens_used': 0,
            'is_fallback': True,
        }

    # Build context + history
    system_prompt = build_groq_context(user_id)
    history = _get_chat_history(user_id)

    messages = [{"role": "system", "content": system_prompt}]
    # Include recent history (skip the message we just saved — it's in history)
    for msg in history:
        messages.append(msg)

    try:
        resp = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 500,
                "top_p": 0.9,
            },
            timeout=30,
        )

        if resp.status_code == 429:
            response = (
                "⏳ Rate limit reached on the Groq API. Please wait a moment and try again. "
                "Free-tier allows ~30 requests/minute."
            )
            _save_message(user_id, 'assistant', response)
            return {'response': response, 'tokens_used': 0, 'is_fallback': True}

        resp.raise_for_status()
        data = resp.json()

        assistant_content = data['choices'][0]['message']['content']
        tokens = data.get('usage', {}).get('total_tokens', 0)

        _save_message(user_id, 'assistant', assistant_content, tokens)
        return {
            'response': assistant_content,
            'tokens_used': tokens,
            'is_fallback': False,
        }

    except requests.exceptions.Timeout:
        response = "⏱️ The AI advisor took too long to respond. Please try again."
        _save_message(user_id, 'assistant', response)
        return {'response': response, 'tokens_used': 0, 'is_fallback': True}
    except requests.exceptions.RequestException as e:
        logger.error(f"Groq API error for user {user_id}: {e}")
        response = _fallback_response(user_message)
        _save_message(user_id, 'assistant', response)
        return {'response': response, 'tokens_used': 0, 'is_fallback': True}


def clear_chat_history(user_id: int):
    """Delete all chat messages for a user."""
    AiChatMessage.query.filter_by(user_id=user_id).delete()
    db.session.commit()
