import unittest
from datetime import date, datetime, timedelta
from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.financial_profile import FinancialProfile
from app.models.ai_chat import AiChatMessage
from unittest.mock import patch, MagicMock
from app.services.auto_categorizer import auto_categorize, suggest_categories
from app.services.ai_alerts import detect_overspending, get_alerts_json, ALERT_META
from app.services.recommender import generate_recommendations, build_groq_context, SUBSTITUTIONS
from app.services.groq_client import chat as groq_chat, clear_chat_history, _fallback_response
from app.services.groq_middleware import GroqMiddleware, SUPPORTED_MODELS
from app.services.spending_predictor import train_models, predict_next_month


class AiAdvisorTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client(use_cookies=True)

        # Create primary test user
        self.user = User(
            name='AI Test User',
            email='ai_tester@financeflow.com',
            phone='0300-9988776',
        )
        self.user.set_password('AdvisorSecret123!')
        db.session.add(self.user)
        db.session.flush()

        # Seed categories for test user
        self.cat_salary = Category(user_id=self.user.user_id, name='Salary', type='income', icon='💰')
        self.cat_food = Category(user_id=self.user.user_id, name='Food & Dining', type='expense', icon='🍔')
        self.cat_transport = Category(user_id=self.user.user_id, name='Transport', type='expense', icon='🚗')
        self.cat_utilities = Category(user_id=self.user.user_id, name='Utilities', type='expense', icon='💡')
        db.session.add_all([self.cat_salary, self.cat_food, self.cat_transport, self.cat_utilities])

        # Seed an account
        self.account = Account(
            user_id=self.user.user_id,
            account_name='Meezan Main',
            account_type='bank',
            currency='PKR',
            is_active=True,
        )
        db.session.add(self.account)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def login(self):
        return self.client.post('/auth/login', data={
            'email': 'ai_tester@financeflow.com',
            'password': 'AdvisorSecret123!',
        }, follow_redirects=True)

    # -------------------------------------------------------------
    # 1. FinancialProfile Model Tests
    # -------------------------------------------------------------
    def test_financial_profile_creation_and_scoring(self):
        profile = FinancialProfile(user_id=self.user.user_id)
        db.session.add(profile)
        db.session.commit()

        # Initial default score calculation
        score = profile.compute_score()
        self.assertIsInstance(score, int)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

        # High financial health test
        profile.credit_score = 800
        profile.savings_rate = 0.25
        profile.debt_to_income_ratio = 0.15
        profile.emergency_fund_months = 6.0
        profile.cash_flow_status = 'Positive'
        profile.savings_goal_met = True
        high_score = profile.compute_score()
        self.assertGreater(high_score, 70)

        # Low financial health test
        profile.credit_score = 400
        profile.savings_rate = 0.02
        profile.debt_to_income_ratio = 0.55
        profile.emergency_fund_months = 0.5
        profile.cash_flow_status = 'Negative'
        profile.savings_goal_met = False
        low_score = profile.compute_score()
        self.assertLess(low_score, 45)

        # Serialization
        data = profile.to_dict()
        self.assertEqual(data['credit_score'], 400)
        self.assertEqual(data['cash_flow_status'], 'Negative')

    # -------------------------------------------------------------
    # 2. AiChatMessage Model Tests
    # -------------------------------------------------------------
    def test_ai_chat_message(self):
        msg = AiChatMessage(
            user_id=self.user.user_id,
            role='user',
            content='How can I budget better for groceries?',
            tokens_used=15
        )
        db.session.add(msg)
        db.session.commit()

        saved = db.session.get(AiChatMessage, msg.id)
        self.assertIsNotNone(saved)
        self.assertEqual(saved.role, 'user')
        self.assertIn('groceries', saved.content)
        d = saved.to_dict()
        self.assertEqual(d['role'], 'user')
        self.assertIn('groceries', d['content'])

    # -------------------------------------------------------------
    # 3. Auto-Categorizer Service Tests
    # -------------------------------------------------------------
    def test_auto_categorizer(self):
        self.assertEqual(auto_categorize("KFC Karachi Clifton"), "Food & Dining")
        self.assertEqual(auto_categorize("Uber trip to airport"), "Transport")
        self.assertEqual(auto_categorize("K-Electric bill payment"), "Utilities")
        self.assertEqual(auto_categorize("Daraz online shopping order"), "Shopping")
        self.assertIsNone(auto_categorize("Random Unrecognized Text 12345"))

        suggestions = suggest_categories("KFC and McDonald delivery")
        self.assertIn("Food & Dining", suggestions)

    # -------------------------------------------------------------
    # 4. Product Substitutions & Recommender Tests
    # -------------------------------------------------------------
    def test_recommender(self):
        self.assertIn("kfc", SUBSTITUTIONS)
        self.assertIn("uber", SUBSTITUTIONS)

        # Test context generation with no transactions
        ctx = build_groq_context(self.user.user_id)
        self.assertIn("FINANCIAL HEALTH PROFILE", ctx)
        self.assertIn("Monthly income", ctx)

        # Add transactions and verify recommendations run without error
        txn = Transaction(
            user_id=self.user.user_id,
            account_id=self.account.account_id,
            amount=2500,
            transaction_type='expense',
            transaction_date=date.today(),
            description='KFC dinner with family',
            category_id=self.cat_food.category_id,
        )
        db.session.add(txn)
        db.session.commit()

        recs = generate_recommendations(self.user.user_id, monthly_income=80000)
        self.assertIsInstance(recs, list)

    # -------------------------------------------------------------
    # 5. Overspending Alerts Service Tests
    # -------------------------------------------------------------
    def test_ai_alerts(self):
        # Empty alerts initially
        alerts = detect_overspending(self.user.user_id, monthly_income=80000)
        self.assertIsInstance(alerts, list)

        # Meta info
        self.assertIn('burn_rate', ALERT_META)
        self.assertIn('merchant_spike', ALERT_META)

        json_alerts = get_alerts_json(self.user.user_id, monthly_income=80000)
        self.assertIsInstance(json_alerts, list)

    # -------------------------------------------------------------
    # 6. Groq LLM Client & Fallback Tests
    # -------------------------------------------------------------
    def test_groq_fallback_responses(self):
        resp_savings = _fallback_response("How to save money?")
        self.assertIn("Savings Tips", resp_savings)

        resp_budget = _fallback_response("Help me reduce my spend")
        self.assertIn("Budget", resp_budget)

        resp_invest = _fallback_response("What is a good investment?")
        self.assertIn("Investment", resp_invest)

        # Test chat function executes safely without raising exceptions
        result = groq_chat(self.user.user_id, "How can I cut expenses?")
        self.assertIn('response', result)
        self.assertTrue(result['is_fallback'])  # No key set in test env

        # Verify chat history was saved
        messages = AiChatMessage.query.filter_by(user_id=self.user.user_id).all()
        self.assertGreaterEqual(len(messages), 2)  # User message + assistant reply

        # Clear chat history
        clear_chat_history(self.user.user_id)
        messages_after = AiChatMessage.query.filter_by(user_id=self.user.user_id).all()
        self.assertEqual(len(messages_after), 0)

    # -------------------------------------------------------------
    # 7. Spending Predictor ML Tests
    # -------------------------------------------------------------
    def test_spending_predictor_graceful_handling(self):
        # Insufficient data should return None safely
        res = train_models(self.user.user_id)
        self.assertIsNone(res)

        preds = predict_next_month(self.user.user_id)
        self.assertIsNone(preds)

    # -------------------------------------------------------------
    # 8. Web Routes: AI Blueprint Tests
    # -------------------------------------------------------------
    def test_ai_web_routes(self):
        # Unauthenticated redirects to login
        resp = self.client.get('/ai/advisor')
        self.assertEqual(resp.status_code, 302)

        # Authenticated
        self.login()

        # Advisor main page
        resp = self.client.get('/ai/advisor')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'AI Financial Advisor', resp.data)

        # Profile GET
        resp = self.client.get('/ai/profile')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Financial Health Profile', resp.data)

        # Profile POST
        resp = self.client.post('/ai/profile', data={
            'monthly_income_pkr': 120000,
            'income_type': 'Salary',
            'credit_score': 740,
            'debt_to_income_ratio': 0.22,
            'savings_rate': 0.18,
            'financial_stress_level': 'Low',
            'cash_flow_status': 'Positive',
            'financial_scenario': 'normal',
            'emergency_fund_pkr': 350000,
            'emergency_fund_months': 3.5,
            'loan_payment_pkr': 15000,
            'investment_amount_pkr': 50000,
            'subscription_services': 2,
            'savings_goal_met': 'on',
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        # Verify profile updated
        profile = FinancialProfile.query.filter_by(user_id=self.user.user_id).first()
        self.assertEqual(profile.monthly_income_pkr, 120000)
        self.assertEqual(profile.credit_score, 740)
        self.assertTrue(profile.savings_goal_met)

        # Chat AJAX POST
        resp = self.client.post('/ai/chat', json={'message': 'Give me money saving tips'})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('response', data)

        # Chat Clear POST
        resp = self.client.post('/ai/chat/clear')
        self.assertEqual(resp.status_code, 200)

        # API alerts JSON
        resp = self.client.get('/ai/api/alerts')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('alerts', resp.get_json())

        # Predict train with insufficient data
        resp = self.client.post('/ai/predict/train')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('error', resp.get_json())

    # -------------------------------------------------------------
    # 9. Dashboard Integration Tests
    # -------------------------------------------------------------
    def test_dashboard_with_ai_integration(self):
        self.login()
        resp = self.client.get('/dashboard/')
        self.assertEqual(resp.status_code, 200)
        # Verify AI links exist in navigation and layout
        self.assertIn(b'/ai/advisor', resp.data)

    # -------------------------------------------------------------
    # 10. Groq Middleware & Model Linkage Tests
    # -------------------------------------------------------------
    def test_groq_middleware_model_linkage(self):
        # 1. Initial resolution without key
        key, source = GroqMiddleware.resolve_api_key(self.user.user_id)
        self.assertEqual(source, 'none')
        self.assertIsNone(key)
        self.assertFalse(self.user.has_groq_key)

        # 2. Save user API key and check model linkage
        save_res = GroqMiddleware.save_user_api_key(
            self.user.user_id,
            "gsk_test1234567890abcdef",
            preferred_model="qwen/qwen3.8-27b"
        )
        self.assertEqual(save_res['status'], 'ok')
        self.assertIn('••••', save_res['masked_key'])

        # Reload user from session
        profile = FinancialProfile.query.filter_by(user_id=self.user.user_id).first()
        self.assertEqual(profile.groq_api_key, "gsk_test1234567890abcdef")
        self.assertEqual(profile.preferred_model, "qwen/qwen3.8-27b")
        self.assertTrue(profile.has_custom_api_key)
        self.assertTrue(self.user.has_groq_key)
        self.assertEqual(self.user.groq_api_key, "gsk_test1234567890abcdef")

        # Key resolution should now be 'user'
        resolved_key, resolved_source = GroqMiddleware.resolve_api_key(self.user.user_id)
        self.assertEqual(resolved_source, 'user')
        self.assertEqual(resolved_key, "gsk_test1234567890abcdef")

        # 3. Model resolution
        self.assertEqual(GroqMiddleware.resolve_model(self.user.user_id), "qwen/qwen3.8-27b")
        self.assertEqual(GroqMiddleware.resolve_model(self.user.user_id, override_model="groq/compound"), "groq/compound")

        # 4. Test connection mocking
        with patch('app.services.groq_middleware.requests.get') as mock_get:
            # Success 200
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {'data': [{'id': 'openai/gpt-oss-120b'}, {'id': 'qwen/qwen3.8-27b'}]}
            mock_get.return_value = mock_resp

            test_res = GroqMiddleware.test_connection("gsk_validkey")
            self.assertTrue(test_res['success'])
            self.assertIn('openai/gpt-oss-120b', test_res['models'])

            # Unauthorized 401
            mock_resp_401 = MagicMock()
            mock_resp_401.status_code = 401
            mock_get.return_value = mock_resp_401

            test_res_401 = GroqMiddleware.test_connection("gsk_badkey")
            self.assertFalse(test_res_401['success'])
            self.assertIn('Invalid', test_res_401['error'])

        # 5. Delete key and verify revert
        del_res = GroqMiddleware.delete_user_api_key(self.user.user_id)
        self.assertEqual(del_res['status'], 'ok')
        self.assertFalse(self.user.has_groq_key)

    # -------------------------------------------------------------
    # 11. Groq API Key Web Endpoints Tests
    # -------------------------------------------------------------
    def test_api_key_web_endpoints(self):
        self.login()

        # 1. GET status
        resp = self.client.get('/ai/api-key/status')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('has_api_key', data)
        self.assertIn('supported_models', data)
        self.assertFalse(data['has_api_key'])

        # 2. POST save without key -> 400 error
        resp = self.client.post('/ai/api-key/save', json={'api_key': ''})
        self.assertEqual(resp.status_code, 400)

        # 3. POST save with valid mock
        with patch('app.services.groq_middleware.GroqMiddleware.test_connection') as mock_test:
            mock_test.return_value = {'success': True, 'latency_ms': 120.5, 'error': None, 'models': ['openai/gpt-oss-120b']}
            resp = self.client.post('/ai/api-key/save', json={
                'api_key': 'gsk_mockedsecret12345678',
                'preferred_model': 'openai/gpt-oss-120b',
                'validate': True,
            })
            self.assertEqual(resp.status_code, 200)
            res_data = resp.get_json()
            self.assertEqual(res_data['status'], 'ok')
            self.assertIn('••••', res_data['masked_key'])

        # 4. Status reflects newly saved key
        resp = self.client.get('/ai/api-key/status')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()['has_api_key'])

        # 5. POST test connection with mock
        with patch('app.services.groq_middleware.GroqMiddleware.test_connection') as mock_test:
            mock_test.return_value = {'success': True, 'latency_ms': 95.0, 'error': None, 'models': ['llama-3.3-70b-versatile']}
            resp = self.client.post('/ai/api-key/test', json={'api_key': 'gsk_test123'})
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.get_json()['success'])

        # 6. Advisor page renders Groq API Key elements
        resp = self.client.get('/ai/advisor')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Groq API Key', resp.data)
        self.assertIn(b'apiKeyModal', resp.data)

        # 7. POST delete key
        resp = self.client.post('/ai/api-key/delete')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['status'], 'ok')


if __name__ == '__main__':
    unittest.main()
