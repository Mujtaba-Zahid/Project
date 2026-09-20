"""
services/credential_manager.py — Safe Credential Protocol & Audit Service
─────────────────────────────────────────────────────────────────────────
Implements the Safe Credentials Protocol:
  - Verifies presence and readiness of API credentials without leaking secret values
  - Generates safe user prompt commands using hidden typing (read -s)
  - Provides diagnostic audits for both system environment and per-user credentials
"""

import os
from typing import Dict, List, Optional
from flask import current_app, has_app_context


# Core external credentials recognized by FinanceFlow
SYSTEM_CREDENTIALS = [
    {
        'key': 'SECRET_KEY',
        'name': 'Flask Application Secret Key',
        'description': 'Used for session encryption and symmetric credential storage',
        'required': True,
        'doc_url': 'https://flask.palletsprojects.com/en/stable/config/#SECRET_KEY',
    },
    {
        'key': 'GROQ_API_KEY',
        'name': 'Groq LLM API Key',
        'description': 'Powers conversational AI advisor and Pakistani financial insights',
        'required': False,
        'doc_url': 'https://console.groq.com/keys',
    },
    {
        'key': 'OXR_APP_ID',
        'name': 'Open Exchange Rates App ID',
        'description': 'Powers live currency conversions between PKR, USD, EUR, etc.',
        'required': False,
        'doc_url': 'https://openexchangerates.org/signup/free',
    },
    {
        'key': 'GOOGLE_CLIENT_ID',
        'name': 'Google OAuth Client ID',
        'description': 'Enables Google One-Tap and OAuth login',
        'required': False,
        'doc_url': 'https://console.cloud.google.com/apis/credentials',
    },
    {
        'key': 'GOOGLE_CLIENT_SECRET',
        'name': 'Google OAuth Client Secret',
        'description': 'Enables Google OAuth authentication flow',
        'required': False,
        'doc_url': 'https://console.cloud.google.com/apis/credentials',
    },
]


def mask_secret(value: Optional[str]) -> str:
    """Safely mask a credential so only the first few and last few characters are visible."""
    if not value or not str(value).strip():
        return ""
    clean = str(value).strip()
    if len(clean) <= 8:
        return "••••••••"
    return clean[:4] + "••••••••" + clean[-4:]


class CredentialManager:
    """Manager providing leak-safe credential checks and prompt commands."""

    @classmethod
    def audit_system_credentials(cls) -> List[Dict]:
        """Audit all system credentials without exposing their plaintext values.

        Returns list of metadata dicts indicating:
          - key: Env variable name
          - configured: bool
          - source: 'config', 'env', or 'missing'
          - masked_value: Safely redacted preview
          - doc_url: Documentation / registration link
        """
        results = []
        for cred in SYSTEM_CREDENTIALS:
            key = cred['key']
            val = None
            source = 'missing'

            if has_app_context() and current_app.config.get(key):
                val = current_app.config.get(key)
                source = 'config'
            elif os.getenv(key):
                val = os.getenv(key)
                source = 'env'

            is_configured = bool(val and str(val).strip())

            results.append({
                'key': key,
                'name': cred['name'],
                'description': cred['description'],
                'required': cred['required'],
                'configured': is_configured,
                'source': source if is_configured else 'missing',
                'masked_value': mask_secret(val) if is_configured else "",
                'doc_url': cred['doc_url'],
            })
        return results

    @classmethod
    def generate_safe_prompt_command(cls, credential_name: str, env_file_path: str = ".env") -> str:
        """Generate safe terminal command for entering credential with hidden typing.

        Follows the Safe Credentials Protocol standard:
          printf "Enter CREDENTIAL_NAME (typing hidden): " && read -s val && echo && echo "CREDENTIAL_NAME=$val" >> "ENV_FILE" && echo "Saved."
        """
        clean_name = credential_name.strip()
        clean_path = env_file_path.strip()
        return (
            f'printf "Enter {clean_name} (typing hidden): " && '
            f'read -s val && echo && echo "{clean_name}=$val" >> "{clean_path}" && '
            f'echo "Saved."'
        )

    @classmethod
    def verify_credential_present(cls, credential_name: str) -> bool:
        """Check whether a specific system credential is populated in config or environment."""
        if has_app_context() and current_app.config.get(credential_name):
            val = current_app.config.get(credential_name)
            return bool(val and str(val).strip())
        val = os.getenv(credential_name)
        return bool(val and str(val).strip())
