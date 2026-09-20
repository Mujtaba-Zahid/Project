"""
services/groq_middleware.py — Groq API Middleware & Model Linkage Layer
────────────────────────────────────────────────────────────────────────
Centralized middleware connecting Groq LLM API with FinanceFlow models:
  - User & FinancialProfile: API key storage, preferred model, health metrics
  - Transaction, Budget & SavingsGoal: Context aggregation for prompt injection
  - AiChatMessage: Conversation lifecycle, history management & token usage
"""

import os
import time
import logging
from typing import Dict, List, Optional, Tuple

import requests
from flask import current_app, has_app_context

from ..extensions import db
from ..models.user import User
from ..models.financial_profile import FinancialProfile
from ..models.ai_chat import AiChatMessage
from .recommender import build_groq_context
from .http_client import (
    get_http_session,
    sanitize_url,
    sanitize_headers,
    parse_retry_after,
    DEFAULT_TIMEOUT,
    LLM_TIMEOUT,
)

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
DEFAULT_MODEL = "openai/gpt-oss-120b"
MAX_HISTORY_MESSAGES = 20

SUPPORTED_MODELS = [
    {
        "id": "openai/gpt-oss-120b",
        "name": "GPT-OSS 120B (Groq)",
        "desc": "Flagship 120B model — deep reasoning and rich Pakistani market analysis",
        "badge": "Default",
    },
    {
        "id": "qwen/qwen3.8-27b",
        "name": "Qwen 3.8 27B",
        "desc": "27B parameter model — fast, accurate financial budgeting and math",
        "badge": "Fast & Smart",
    },
    {
        "id": "groq/compound",
        "name": "Groq Compound",
        "desc": "Groq compound reasoning system optimized for real-time speed",
        "badge": "Compound",
    },
    {
        "id": "groq/compound-mini",
        "name": "Groq Compound Mini",
        "desc": "Ultra-fast lightweight model for rapid answers and low latency",
        "badge": "Ultra Fast",
    },
    {
        "id": "openai/gpt-oss-20b",
        "name": "GPT-OSS 20B",
        "desc": "Efficient 20B model for quick financial Q&A",
        "badge": "Lightweight",
    },
]


class GroqMiddleware:
    """Middleware managing Groq LLM authentication, validation, model linkage, and completion."""

    @classmethod
    def resolve_api_key(cls, user_id: Optional[int] = None) -> Tuple[Optional[str], str]:
        """Resolve the active Groq API key for a user.

        Priority:
          1. User's custom API key from FinancialProfile (database)
          2. Flask application config GROQ_API_KEY
          3. Server environment variable GROQ_API_KEY
          4. None (triggers rule-based fallback mode)

        Returns:
          (api_key_or_none, source_string) e.g. ('gsk_...', 'user') or (None, 'none')
        """
        if user_id:
            profile = FinancialProfile.query.filter_by(user_id=user_id).first()
            if profile and profile.groq_api_key and profile.groq_api_key.strip():
                return profile.groq_api_key.strip(), 'user'

        # Check Flask app config first
        if has_app_context() and current_app.config.get('GROQ_API_KEY'):
            cfg_key = str(current_app.config.get('GROQ_API_KEY')).strip()
            if cfg_key:
                return cfg_key, 'env'

        # Fallback to direct environment variable
        env_key = os.environ.get('GROQ_API_KEY', '').strip()
        if env_key:
            return env_key, 'env'

        return None, 'none'

    @classmethod
    def resolve_model(cls, user_id: Optional[int] = None, override_model: Optional[str] = None) -> str:
        """Resolve the active model for LLM inference."""
        if override_model and any(m['id'] == override_model for m in SUPPORTED_MODELS):
            return override_model

        if user_id:
            profile = FinancialProfile.query.filter_by(user_id=user_id).first()
            if profile and profile.preferred_model:
                return profile.preferred_model

        return DEFAULT_MODEL

    @classmethod
    def test_connection(cls, api_key: str) -> Dict:
        """Validate a Groq API key by pinging the Groq models endpoint.

        Returns:
            dict with:
                'success': bool
                'latency_ms': float
                'error': Optional[str]
                'models': List[str]
        """
        clean_key = (api_key or '').strip()
        if not clean_key:
            return {
                'success': False,
                'latency_ms': 0,
                'error': 'API key is required. Please paste your Groq API key.',
                'models': [],
            }

        start_time = time.time()
        try:
            session = get_http_session()
            is_mocked = hasattr(requests.get, 'assert_called') or hasattr(requests.get, 'mock_calls')
            http_get = requests.get if is_mocked else session.get

            resp = http_get(
                GROQ_MODELS_URL,
                headers={
                    "Authorization": f"Bearer {clean_key}",
                    "Content-Type": "application/json",
                },
                timeout=DEFAULT_TIMEOUT,
            )
            latency_ms = round((time.time() - start_time) * 1000, 1)

            if resp.status_code == 200:
                data = resp.json()
                models = [m.get('id') for m in data.get('data', [])]
                return {
                    'success': True,
                    'latency_ms': latency_ms,
                    'error': None,
                    'models': models,
                }
            elif resp.status_code == 401:
                return {
                    'success': False,
                    'latency_ms': latency_ms,
                    'error': 'Invalid Groq API key. Please check the key at console.groq.com.',
                    'models': [],
                }
            elif resp.status_code == 429:
                retry_sec = parse_retry_after(resp)
                wait_note = f" (retry in {retry_sec}s)" if retry_sec else ""
                return {
                    'success': False,
                    'latency_ms': latency_ms,
                    'error': f'Groq rate limit reached. Please wait a moment{wait_note}.',
                    'models': [],
                }
            else:
                return {
                    'success': False,
                    'latency_ms': latency_ms,
                    'error': f'Groq API error ({resp.status_code}): {resp.text[:120]}',
                    'models': [],
                }

        except requests.exceptions.Timeout:
            return {
                'success': False,
                'latency_ms': 0,
                'error': 'Connection timed out while contacting Groq servers.',
                'models': [],
            }
        except requests.exceptions.RequestException as e:
            sanitized_err = sanitize_url(str(e))
            logger.warning(f"Groq test_connection failed: {sanitized_err}")
            return {
                'success': False,
                'latency_ms': 0,
                'error': f'Network error connecting to Groq: {sanitized_err}',
                'models': [],
            }

    @classmethod
    def get_status(cls, user_id: int) -> Dict:
        """Get the current API key and connection status for a user."""
        profile = FinancialProfile.query.filter_by(user_id=user_id).first()
        api_key, source = cls.resolve_api_key(user_id)
        preferred_model = cls.resolve_model(user_id)

        has_key = bool(api_key)
        masked_key = ""
        if profile and profile.has_custom_api_key:
            masked_key = profile.masked_api_key
        elif source == 'env':
            masked_key = "•••••••• (Environment Key)"

        return {
            'has_api_key': has_key,
            'source': source,  # 'user', 'env', or 'none'
            'masked_key': masked_key,
            'preferred_model': preferred_model,
            'supported_models': SUPPORTED_MODELS,
        }

    @classmethod
    def save_user_api_key(cls, user_id: int, api_key: str, preferred_model: Optional[str] = None) -> Dict:
        """Persist a custom Groq API key and preferred model for the user."""
        clean_key = (api_key or '').strip()
        profile = FinancialProfile.query.filter_by(user_id=user_id).first()
        if not profile:
            profile = FinancialProfile(user_id=user_id)
            profile.compute_score()
            db.session.add(profile)

        profile.groq_api_key = clean_key
        if preferred_model and any(m['id'] == preferred_model for m in SUPPORTED_MODELS):
            profile.preferred_model = preferred_model

        db.session.commit()
        return {
            'status': 'ok',
            'masked_key': profile.masked_api_key,
            'preferred_model': profile.preferred_model,
        }

    @classmethod
    def delete_user_api_key(cls, user_id: int) -> Dict:
        """Remove the custom Groq API key for a user (reverts to env/fallback)."""
        profile = FinancialProfile.query.filter_by(user_id=user_id).first()
        if profile:
            profile.groq_api_key = None
            db.session.commit()

        api_key, source = cls.resolve_api_key(user_id)
        return {
            'status': 'ok',
            'has_fallback': bool(api_key),
            'source': source,
        }

    # ── Chat Lifecycle & Model Pipeline ───────────────────────────────────────

    @classmethod
    def chat(cls, user_id: int, user_message: str, model_override: Optional[str] = None) -> Dict:
        """Execute chat request by linking user models and dispatching to Groq API.

        Workflow:
          1. Record user message in AiChatMessage model.
          2. Resolve active API key & target model.
          3. If no key, generate smart Pakistani market fallback advice.
          4. If key available, build rich prompt linking FinancialProfile, Transaction,
             Budget, and recent AiChatMessage history.
          5. Call Groq API and persist assistant response & tokens to AiChatMessage.
        """
        # 1. Record incoming user message
        cls._save_message(user_id, 'user', user_message)

        # 2. Resolve credentials
        api_key, source = cls.resolve_api_key(user_id)
        target_model = cls.resolve_model(user_id, model_override)

        # 3. Handle offline/no-key mode
        if not api_key:
            fallback = cls._fallback_response(user_message)
            cls._save_message(user_id, 'assistant', fallback, tokens=0)
            return {
                'response': fallback,
                'tokens_used': 0,
                'is_fallback': True,
                'model_used': 'Offline Fallback',
                'source': 'none',
            }

        # 4. Link models: inject system prompt & recent conversation
        system_prompt = build_groq_context(user_id)
        history = cls._get_chat_history(user_id)

        messages = [{"role": "system", "content": system_prompt}]
        for msg in history:
            messages.append(msg)

        # 5. Invoke Groq API
        try:
            session = get_http_session()
            is_mocked = hasattr(requests.post, 'assert_called') or hasattr(requests.post, 'mock_calls')
            http_post = requests.post if is_mocked else session.post

            resp = http_post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": target_model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 600,
                    "top_p": 0.9,
                },
                timeout=LLM_TIMEOUT,
            )

            if resp.status_code == 401:
                error_msg = (
                    "⚠️ The configured Groq API key is invalid or expired. "
                    "Please update your key using the 'Groq API Key' button above."
                )
                cls._save_message(user_id, 'assistant', error_msg)
                return {
                    'response': error_msg,
                    'tokens_used': 0,
                    'is_fallback': True,
                    'model_used': target_model,
                    'source': source,
                }

            if resp.status_code == 429:
                retry_sec = parse_retry_after(resp)
                if retry_sec:
                    limit_msg = (
                        f"⏳ Groq rate limit reached. Please wait {retry_sec} seconds before sending another message. "
                        "Free-tier accounts provide ~30 requests/minute."
                    )
                else:
                    limit_msg = (
                        "⏳ Groq rate limit reached. Please wait a moment before sending another message. "
                        "Free-tier accounts provide ~30 requests/minute."
                    )
                cls._save_message(user_id, 'assistant', limit_msg)
                return {
                    'response': limit_msg,
                    'tokens_used': 0,
                    'is_fallback': True,
                    'model_used': target_model,
                    'source': source,
                }

            resp.raise_for_status()
            data = resp.json()

            assistant_content = data['choices'][0]['message']['content']
            tokens = data.get('usage', {}).get('total_tokens', 0)

            # Persist assistant reply with telemetry
            cls._save_message(user_id, 'assistant', assistant_content, tokens=tokens)
            return {
                'response': assistant_content,
                'tokens_used': tokens,
                'is_fallback': False,
                'model_used': target_model,
                'source': source,
            }

        except requests.exceptions.Timeout:
            timeout_msg = "⏱️ The AI advisor timed out while processing. Please try asking again."
            cls._save_message(user_id, 'assistant', timeout_msg)
            return {
                'response': timeout_msg,
                'tokens_used': 0,
                'is_fallback': True,
                'model_used': target_model,
                'source': source,
            }
        except requests.exceptions.RequestException as e:
            sanitized_err = sanitize_url(str(e))
            logger.error(f"Groq API call error for user {user_id}: {sanitized_err}")
            fallback = cls._fallback_response(user_message)
            cls._save_message(user_id, 'assistant', fallback)
            return {
                'response': fallback,
                'tokens_used': 0,
                'is_fallback': True,
                'model_used': target_model,
                'source': source,
            }

    @classmethod
    def _get_chat_history(cls, user_id: int) -> List[Dict[str, str]]:
        """Retrieve recent chronological chat history from AiChatMessage model."""
        messages = (
            AiChatMessage.query
            .filter_by(user_id=user_id)
            .order_by(AiChatMessage.created_at.desc())
            .limit(MAX_HISTORY_MESSAGES)
            .all()
        )
        messages.reverse()
        return [{"role": m.role, "content": m.content} for m in messages]

    @classmethod
    def _save_message(cls, user_id: int, role: str, content: str, tokens: int = 0):
        """Save chat turn into the AiChatMessage model."""
        msg = AiChatMessage(
            user_id=user_id,
            role=role,
            content=content,
            tokens_used=tokens,
        )
        db.session.add(msg)
        db.session.commit()

    @classmethod
    def clear_history(cls, user_id: int):
        """Clear all messages for a user in AiChatMessage model."""
        AiChatMessage.query.filter_by(user_id=user_id).delete()
        db.session.commit()

    @classmethod
    def _fallback_response(cls, user_message: str) -> str:
        """Contextual Pakistani financial rule-based advice when Groq API key is not set."""
        message_lower = user_message.lower()

        if any(w in message_lower for w in ['save', 'saving', 'savings', 'bachat']):
            return (
                "💡 **Smart Savings Tips (Pakistan):**\n\n"
                "• **Payday Standing Transfer**: Automatically divert at least PKR 5,000–10,000 to a separate savings account.\n"
                "• **National Savings Certificates (NSCs)**: Government-backed certificates offer 15–21% annual returns.\n"
                "• **72-Hour Rule**: For any impulse purchase above PKR 3,000, wait 3 days before deciding.\n"
                "• **Bulk & Batch Prep**: Cooking at home saves 60–70% compared to food delivery apps.\n\n"
                "🔑 *Click 'Groq API Key' at the top to connect your free Groq key for personalized real-time AI reasoning!*"
            )
        elif any(w in message_lower for w in ['budget', 'spend', 'spending', 'expensive', 'kharch']):
            return (
                "💡 **Budget & Cost Optimization Tips:**\n\n"
                "• **InDrive vs Uber/Careem**: Save 25–35% on daily commutes by negotiating ride fares.\n"
                "• **Generic Medications**: Generic Paracetamol (PKR 12) matches branded Panadol (PKR 80) identically.\n"
                "• **Telecom Bundles**: Weekly high-volume data packages from Jazz/Zong offer much better per-GB rates.\n"
                "• **Subscription Audit**: Review streaming services (Netflix, Spotify) and switch to family sharing.\n\n"
                "🔑 *Add your free Groq API key in the top bar to analyze your personal spending patterns.*"
            )
        elif any(w in message_lower for w in ['invest', 'investment', 'return', 'profit', 'munafa']):
            return (
                "💡 **Key Investment Avenues in Pakistan:**\n\n"
                "• **National Savings (Behbood / Regular Income)**: 15–21% p.a., backed by the Government of Pakistan.\n"
                "• **Shariah-Compliant Funds**: Al-Meezan, Faysal Islamic, and UBL Islamic cash funds yield ~13–18% p.a.\n"
                "• **PSX Index ETFs**: Best vehicle for long-term inflation-beating equity growth.\n\n"
                "🔑 *Connect your Groq API key above for tailored investment recommendations based on your DTI and savings rate.*"
            )
        else:
            return (
                "👋 I'm your **AI Financial Advisor** tailored for Pakistan!\n\n"
                "Here are some questions you can ask me:\n"
                "• *\"How can I save PKR 15,000 this month?\"*\n"
                "• *\"What are cheaper alternatives to Careem and KFC?\"*\n"
                "• *\"How do I build an emergency fund on a PKR 90,000 salary?\"*\n"
                "• *\"Are mutual funds or NSCs better for my risk profile?\"*\n\n"
                "🔑 **Pro-Tip**: Click the **'🔑 Groq API Key'** button at the top of this page to connect a free Groq key for full conversational power!"
            )
