"""
tests/test_api_handling.py — Enterprise API Handling & Safe Credential Tests
───────────────────────────────────────────────────────────────────────────
Tests security and resilience implementations:
  1. Symmetric Fernet encryption at rest with backward compatibility
  2. FinancialProfile model transparent encryption/decryption
  3. Resilient HTTP infrastructure (pooling, timeouts, retries, Retry-After)
  4. Credential sanitization in URLs, headers, and logs
  5. GroqMiddleware rate limit guidance & config-level resolution
  6. Currency service graceful degradation on external API failure
  7. CredentialManager safe verification protocol compliance
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

import requests

from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.financial_profile import FinancialProfile
from app.models.exchange_rate import ExchangeRate
from app.services.crypto import encrypt_credential, decrypt_credential
from app.services.http_client import (
    get_http_session,
    sanitize_url,
    sanitize_headers,
    parse_retry_after,
    DEFAULT_TIMEOUT,
    LLM_TIMEOUT,
)
from app.services.groq_middleware import GroqMiddleware
from app.services.currency import fetch_exchange_rates
from app.services.credential_manager import CredentialManager, mask_secret


class ApiHandlingTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['SECRET_KEY'] = 'test-secret-key-12345'
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Seed primary test user
        self.user = User(
            name='Crypto Test User',
            email='cryptouser@financeflow.com',
        )
        self.user.set_password('SecurePass123!')
        db.session.add(self.user)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    # ─────────────────────────────────────────────────────────────
    # 1. Symmetric Encryption & Backward Compatibility Tests
    # ─────────────────────────────────────────────────────────────

    def test_crypto_encryption_and_decryption(self):
        """Test encryption produces a Fernet token and decrypts to original plaintext."""
        raw_key = "gsk_live_abcdef1234567890XYZ"
        encrypted = encrypt_credential(raw_key)

        self.assertIsNotNone(encrypted)
        self.assertNotEqual(encrypted, raw_key)
        self.assertTrue(encrypted.startswith('gAAAAA'))

        # Decrypt
        decrypted = decrypt_credential(encrypted)
        self.assertEqual(decrypted, raw_key)

    def test_crypto_prevents_double_encryption(self):
        """Encrypting an already encrypted token should return it unmodified."""
        raw_key = "gsk_live_123456"
        encrypted_once = encrypt_credential(raw_key)
        encrypted_twice = encrypt_credential(encrypted_once)
        self.assertEqual(encrypted_once, encrypted_twice)

    def test_crypto_legacy_plaintext_backward_compatibility(self):
        """Existing unencrypted keys in DB should be returned cleanly by decrypt_credential."""
        legacy_key = "gsk_legacy_plain_text_key_12345"
        # Decrypting plaintext directly returns it without error
        result = decrypt_credential(legacy_key)
        self.assertEqual(result, legacy_key)

    def test_crypto_empty_and_corrupt_handling(self):
        """None or empty inputs return None, and corrupt tokens fall back safely."""
        self.assertIsNone(encrypt_credential(None))
        self.assertIsNone(encrypt_credential(""))
        self.assertIsNone(decrypt_credential(None))
        self.assertIsNone(decrypt_credential(""))

        # Invalid/corrupt Fernet token should gracefully return the raw token without crashing
        corrupt_token = "gAAAAABcorruptedTokenDataHere123"
        safe_fallback = decrypt_credential(corrupt_token)
        self.assertEqual(safe_fallback, corrupt_token)

    # ─────────────────────────────────────────────────────────────
    # 2. FinancialProfile Transparent Model Encryption Tests
    # ─────────────────────────────────────────────────────────────

    def test_financial_profile_groq_api_key_encryption_at_rest(self):
        """Assigning groq_api_key encrypts at rest while transparently decrypting on access."""
        profile = FinancialProfile(user_id=self.user.user_id)
        raw_api_key = "gsk_user_secret_groq_key_998877"

        profile.groq_api_key = raw_api_key
        db.session.add(profile)
        db.session.commit()

        # Check raw database value
        stored_raw = profile.raw_encrypted_key
        self.assertIsNotNone(stored_raw)
        self.assertTrue(stored_raw.startswith('gAAAAA'))
        self.assertNotEqual(stored_raw, raw_api_key)

        # Check property access
        self.assertEqual(profile.groq_api_key, raw_api_key)
        self.assertEqual(self.user.groq_api_key, raw_api_key)

        # Check masked representation
        masked = profile.masked_api_key
        self.assertTrue(masked.startswith("gsk_"))
        self.assertTrue(masked.endswith("8877"))
        self.assertIn("••••••••", masked)
        self.assertNotIn("groq_key", masked)

    def test_financial_profile_legacy_unencrypted_db_row(self):
        """Simulate an existing row created before encryption was added."""
        profile = FinancialProfile(user_id=self.user.user_id)
        # Directly set underlying column to unencrypted text as if from old database
        profile._groq_api_key = "gsk_pre_existing_raw_key_111"
        db.session.add(profile)
        db.session.commit()

        # Should still read cleanly through the transparent property
        self.assertEqual(profile.groq_api_key, "gsk_pre_existing_raw_key_111")
        self.assertTrue(profile.has_custom_api_key)

    def test_financial_profile_to_dict_never_leaks_key(self):
        """Serialization for AI context must never include raw or encrypted keys."""
        profile = FinancialProfile(user_id=self.user.user_id)
        profile.groq_api_key = "gsk_super_secret_key"
        data = profile.to_dict()

        self.assertNotIn('groq_api_key', data)
        self.assertNotIn('_groq_api_key', data)
        self.assertIn('has_custom_api_key', data)
        self.assertTrue(data['has_custom_api_key'])

    # ─────────────────────────────────────────────────────────────
    # 3. Resilient HTTP Infrastructure & Sanitization Tests
    # ─────────────────────────────────────────────────────────────

    def test_http_session_creation(self):
        """Verify HTTP session config with connection pooling and timeouts."""
        session = get_http_session()
        self.assertIsInstance(session, requests.Session)
        self.assertIn("https://", session.adapters)
        self.assertIn("http://", session.adapters)

        # Standard timeout constants
        self.assertEqual(DEFAULT_TIMEOUT, (3.05, 10.0))
        self.assertEqual(LLM_TIMEOUT, (3.05, 30.0))

    def test_sanitize_url_redacts_sensitive_params(self):
        """Query parameters like app_id, api_key, token must be redacted."""
        url = "https://openexchangerates.org/api/latest.json?app_id=secret12345&base=USD&prettyprint=false"
        sanitized = sanitize_url(url)

        self.assertNotIn("secret12345", sanitized)
        self.assertIn("app_id=%5BREDACTED%5D", sanitized)
        self.assertIn("base=USD", sanitized)

        # Test other key names
        url2 = "https://api.example.com/data?key=mykey&token=mytoken&user=john"
        sanitized2 = sanitize_url(url2)
        self.assertNotIn("mykey", sanitized2)
        self.assertNotIn("mytoken", sanitized2)
        self.assertIn("user=john", sanitized2)

    def test_sanitize_headers_masks_auth_tokens(self):
        """Authorization and API key headers must be masked."""
        headers = {
            'Authorization': 'Bearer gsk_live_token_12345',
            'X-Api-Key': 'key_abc',
            'Content-Type': 'application/json',
        }
        sanitized = sanitize_headers(headers)
        self.assertNotIn('gsk_live_token_12345', sanitized['Authorization'])
        self.assertIn('Masked', sanitized['Authorization'])
        self.assertEqual(sanitized['Content-Type'], 'application/json')

    def test_parse_retry_after_header(self):
        """Verify parsing of standard Retry-After HTTP headers."""
        resp_mock = MagicMock()
        resp_mock.headers = {'Retry-After': '14'}
        self.assertEqual(parse_retry_after(resp_mock), 14)

        resp_mock.headers = {'Retry-After': 'invalid_date_format'}
        self.assertEqual(parse_retry_after(resp_mock), 5)  # Safe default fallback

        self.assertIsNone(parse_retry_after(None))

    # ─────────────────────────────────────────────────────────────
    # 4. GroqMiddleware Config Resolution & Rate Limit Handling
    # ─────────────────────────────────────────────────────────────

    def test_groq_middleware_config_resolution_order(self):
        """Verify priority: user key > app.config['GROQ_API_KEY'] > os.environ > None."""
        # 1. Initially nothing configured
        key, source = GroqMiddleware.resolve_api_key(self.user.user_id)
        self.assertIsNone(key)
        self.assertEqual(source, 'none')

        # 2. Configured at app.config level
        self.app.config['GROQ_API_KEY'] = 'gsk_from_app_config_123'
        key, source = GroqMiddleware.resolve_api_key(self.user.user_id)
        self.assertEqual(key, 'gsk_from_app_config_123')
        self.assertEqual(source, 'env')

        # 3. User overrides with personal key
        profile = FinancialProfile(user_id=self.user.user_id)
        profile.groq_api_key = 'gsk_user_override_456'
        db.session.add(profile)
        db.session.commit()

        key, source = GroqMiddleware.resolve_api_key(self.user.user_id)
        self.assertEqual(key, 'gsk_user_override_456')
        self.assertEqual(source, 'user')

    def test_groq_middleware_chat_rate_limit_retry_after_message(self):
        """When receiving HTTP 429 with Retry-After, user is advised of wait duration."""
        profile = FinancialProfile(user_id=self.user.user_id)
        profile.groq_api_key = 'gsk_user_test_key'
        db.session.add(profile)
        db.session.commit()

        with patch('app.services.groq_middleware.requests.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 429
            mock_resp.headers = {'Retry-After': '25'}
            mock_post.return_value = mock_resp

            result = GroqMiddleware.chat(self.user.user_id, "How can I invest?")
            self.assertTrue(result['is_fallback'])
            self.assertIn("25 seconds", result['response'])

    # ─────────────────────────────────────────────────────────────
    # 5. Currency Service Resilience & Graceful Degradation
    # ─────────────────────────────────────────────────────────────

    def test_currency_graceful_fallback_to_stale_rates_on_api_error(self):
        """If remote API fails, currency service falls back to cached rates rather than failing."""
        # Seed an older rate in DB
        old_time = datetime.utcnow() - timedelta(hours=3)
        rate = ExchangeRate(
            base_currency='USD',
            target_currency='PKR',
            rate=278.50,
            fetched_at=old_time,
        )
        db.session.add(rate)
        db.session.commit()

        self.app.config['OXR_APP_ID'] = 'oxr_test_id_123'

        with patch('app.services.currency.requests.get') as mock_get:
            # Simulate external API network failure / timeout
            mock_get.side_effect = requests.exceptions.ConnectionError(
                "Failed to establish a connection to https://openexchangerates.org/api/latest.json?app_id=oxr_test_id_123"
            )

            success = fetch_exchange_rates()
            # Should gracefully return True because cached rate exists
            self.assertTrue(success)

            # Confirm rate was preserved
            pkr_rate = ExchangeRate.query.filter_by(target_currency='PKR').first()
            self.assertIsNotNone(pkr_rate)
            self.assertEqual(pkr_rate.rate, 278.50)

    # ─────────────────────────────────────────────────────────────
    # 6. Safe Credential Protocol Compliance Tests
    # ─────────────────────────────────────────────────────────────

    def test_credential_manager_audit_does_not_leak_keys(self):
        """Auditing credentials returns masked status without exposing raw values."""
        self.app.config['GROQ_API_KEY'] = 'gsk_secret_1234567890abcdef'
        self.app.config['OXR_APP_ID'] = 'oxr_secret_app_id_9999'

        audit_results = CredentialManager.audit_system_credentials()
        self.assertIsInstance(audit_results, list)

        groq_cred = next(c for c in audit_results if c['key'] == 'GROQ_API_KEY')
        self.assertTrue(groq_cred['configured'])
        self.assertNotIn('gsk_secret_1234567890abcdef', groq_cred['masked_value'])
        self.assertIn('••••••••', groq_cred['masked_value'])

    def test_credential_manager_safe_prompt_command(self):
        """Prompt command must format with hidden typing (read -s) and exact target path."""
        cmd = CredentialManager.generate_safe_prompt_command('GROQ_API_KEY', '.env')
        self.assertIn('read -s val', cmd)
        self.assertIn('GROQ_API_KEY', cmd)
        self.assertIn('>> ".env"', cmd)
        self.assertIn('(typing hidden)', cmd)


if __name__ == '__main__':
    unittest.main()
