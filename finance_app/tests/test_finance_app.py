import unittest
from datetime import date, datetime, timedelta
from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.account import Account
from app.models.category import Category
from app.models.tag import Tag
from app.models.transaction import Transaction
from app.models.budget import Budget
from app.models.savings_goal import SavingsGoal
from app.models.investment import Investment
from app.models.recurring import RecurringTransaction
from app.models.notification import Notification
from app.services.balance import get_balance
from app.services.transfer import fund_transfer
from app.services.budget import get_budget_status, check_and_alert
from app.services.savings import contribute_to_goal, get_goal_progress


class FinanceFlowTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client(use_cookies=True)

        # Create primary test user
        self.user = User(
            name='Test User',
            email='test@financeflow.com',
            phone='0300-1112233',
        )
        self.user.set_password('Secret123!')
        db.session.add(self.user)
        db.session.flush()

        # Seed categories for test user
        self.cat_salary = Category(user_id=self.user.user_id, name='Salary', type='income', icon='💰')
        self.cat_food = Category(user_id=self.user.user_id, name='Food', type='expense', icon='🍔')
        self.cat_rent = Category(user_id=self.user.user_id, name='Rent', type='expense', icon='🏠')
        db.session.add_all([self.cat_salary, self.cat_food, self.cat_rent])

        # Seed an account
        self.account = Account(
            user_id=self.user.user_id,
            account_name='Primary Checking',
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

    def login(self, email='test@financeflow.com', password='Secret123!'):
        return self.client.post('/auth/login', data={
            'email': email,
            'password': password,
        }, follow_redirects=True)

    def logout(self):
        return self.client.get('/auth/logout', follow_redirects=True)

    # -------------------------------------------------------------
    # 1. Auth & Registration Tests
    # -------------------------------------------------------------
    def test_user_password_hashing(self):
        self.assertTrue(self.user.check_password('Secret123!'))
        self.assertFalse(self.user.check_password('WrongPass'))

    def test_user_registration_flow(self):
        response = self.client.post('/auth/register', data={
            'name': 'New User',
            'email': 'newuser@financeflow.com',
            'phone': '0300-9998877',
            'password': 'SecurePassword1!',
            'confirm_password': 'SecurePassword1!',
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        # Check user exists
        new_u = User.query.filter_by(email='newuser@financeflow.com').first()
        self.assertIsNotNone(new_u)
        # Check auto-seeded categories
        cats = Category.query.filter_by(user_id=new_u.user_id).all()
        self.assertGreater(len(cats), 0)

    def test_login_and_logout(self):
        # Invalid password
        resp_fail = self.login(password='WrongPass!')
        self.assertIn(b'Invalid email or password', resp_fail.data)

        # Valid login
        resp_success = self.login()
        self.assertEqual(resp_success.status_code, 200)
        self.assertIn(b'Dashboard', resp_success.data)

        # Logout
        resp_logout = self.logout()
        self.assertIn(b'You have been logged out.', resp_logout.data)

    # -------------------------------------------------------------
    # 2. Account CRUD & Balance Tests
    # -------------------------------------------------------------
    def test_account_creation_and_soft_delete(self):
        self.login()
        # Create savings account
        resp = self.client.post('/accounts/add', data={
            'account_name': 'Emergency Fund',
            'account_type': 'wallet',
            'currency': 'PKR',
            'is_active': 'y',
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        acc = Account.query.filter_by(account_name='Emergency Fund').first()
        self.assertIsNotNone(acc)
        self.assertEqual(acc.account_type, 'wallet')
        self.assertEqual(get_balance(acc.account_id), 0.0)

        # Soft delete account
        del_resp = self.client.post(f'/accounts/delete/{acc.account_id}', follow_redirects=True)
        self.assertEqual(del_resp.status_code, 200)
        db.session.refresh(acc)
        self.assertTrue(acc.is_deleted)

    # -------------------------------------------------------------
    # 3. Transaction & Balance Calculation Tests
    # -------------------------------------------------------------
    def test_transactions_and_live_balance(self):
        self.login()

        # Add Income: 100,000 PKR Salary
        t1 = Transaction(
            user_id=self.user.user_id,
            account_id=self.account.account_id,
            category_id=self.cat_salary.category_id,
            amount=100000.00,
            transaction_type='income',
            transaction_date=date.today(),
            description='Monthly Salary',
        )
        db.session.add(t1)
        db.session.commit()

        self.assertEqual(get_balance(self.account.account_id), 100000.0)

        # Add Expense: 25,000 PKR Rent
        t2 = Transaction(
            user_id=self.user.user_id,
            account_id=self.account.account_id,
            category_id=self.cat_rent.category_id,
            amount=25000.00,
            transaction_type='expense',
            transaction_date=date.today(),
            description='House Rent',
        )
        db.session.add(t2)
        db.session.commit()

        self.assertEqual(get_balance(self.account.account_id), 75000.0)

        # Soft delete expense transaction -> balance restores to 100,000
        t2.soft_delete()
        db.session.commit()
        self.assertEqual(get_balance(self.account.account_id), 100000.0)

    # -------------------------------------------------------------
    # 4. Atomic Fund Transfer Tests
    # -------------------------------------------------------------
    def test_atomic_fund_transfer(self):
        # Create destination account
        wallet = Account(
            user_id=self.user.user_id,
            account_name='Digital Wallet',
            account_type='wallet',
            currency='PKR',
            is_active=True,
        )
        db.session.add(wallet)

        # Deposit initial 50,000 into checking
        deposit = Transaction(
            user_id=self.user.user_id,
            account_id=self.account.account_id,
            amount=50000.00,
            transaction_type='income',
            transaction_date=date.today(),
        )
        db.session.add(deposit)
        db.session.commit()

        self.assertEqual(get_balance(self.account.account_id), 50000.0)
        self.assertEqual(get_balance(wallet.account_id), 0.0)

        # Successful transfer of 15,000
        transfer = fund_transfer(
            from_account_id=self.account.account_id,
            to_account_id=wallet.account_id,
            amount=15000.00,
            user_id=self.user.user_id,
            notes='Pocket money',
        )
        self.assertIsNotNone(transfer)
        self.assertEqual(get_balance(self.account.account_id), 35000.0)
        self.assertEqual(get_balance(wallet.account_id), 15000.0)

        # Attempt transfer with insufficient funds (e.g. 50,000 when only 35,000 available)
        with self.assertRaises(ValueError):
            fund_transfer(
                from_account_id=self.account.account_id,
                to_account_id=wallet.account_id,
                amount=50000.00,
                user_id=self.user.user_id,
            )

        # Verify balances were completely unchanged due to rollback
        self.assertEqual(get_balance(self.account.account_id), 35000.0)
        self.assertEqual(get_balance(wallet.account_id), 15000.0)

    # -------------------------------------------------------------
    # 5. Budget & Threshold Alerting Tests
    # -------------------------------------------------------------
    def test_budget_monitoring_and_alerts(self):
        current_month = date.today().replace(day=1)
        # Create budget for Food: limit 20,000, threshold 0.80 (80% = 16,000)
        b = Budget(
            user_id=self.user.user_id,
            category_id=self.cat_food.category_id,
            monthly_limit=20000.00,
            month=current_month,
            alert_threshold=0.80,
            alert_sent=False,
        )
        db.session.add(b)
        db.session.commit()

        # Spend 10,000 on Food (50% of budget)
        t1 = Transaction(
            user_id=self.user.user_id,
            account_id=self.account.account_id,
            category_id=self.cat_food.category_id,
            amount=10000.00,
            transaction_type='expense',
            transaction_date=date.today(),
        )
        db.session.add(t1)
        db.session.commit()

        check_and_alert(self.user.user_id, self.cat_food.category_id, current_month)
        # No alert should be sent yet
        db.session.refresh(b)
        self.assertFalse(b.alert_sent)
        self.assertEqual(Notification.query.filter_by(user_id=self.user.user_id).count(), 0)

        # Spend additional 7,000 on Food (Total: 17,000 = 85% >= 80%)
        t2 = Transaction(
            user_id=self.user.user_id,
            account_id=self.account.account_id,
            category_id=self.cat_food.category_id,
            amount=7000.00,
            transaction_type='expense',
            transaction_date=date.today(),
        )
        db.session.add(t2)
        db.session.commit()

        check_and_alert(self.user.user_id, self.cat_food.category_id, current_month)
        db.session.refresh(b)
        self.assertTrue(b.alert_sent)
        notif = Notification.query.filter_by(user_id=self.user.user_id, type='budget_alert').first()
        self.assertIsNotNone(notif)
        self.assertIn('Food', notif.title)

    # -------------------------------------------------------------
    # 6. Savings Goals & Auto-completion Tests
    # -------------------------------------------------------------
    def test_savings_goals_contribution_and_completion(self):
        goal = SavingsGoal(
            user_id=self.user.user_id,
            goal_name='New Laptop',
            target_amount=100000.00,
            saved_amount=0.00,
            deadline=date.today() + timedelta(days=90),
            status='active',
        )
        db.session.add(goal)
        db.session.commit()

        self.assertEqual(get_goal_progress(goal.goal_id), 0.0)

        # Contribute 40,000
        contribute_to_goal(goal.goal_id, 40000.00, user_id=self.user.user_id)
        db.session.refresh(goal)
        self.assertEqual(float(goal.saved_amount), 40000.00)
        self.assertEqual(goal.status, 'active')

        # Contribute remaining 60,000 -> completes goal
        contribute_to_goal(goal.goal_id, 60000.00, user_id=self.user.user_id)
        db.session.refresh(goal)
        self.assertEqual(float(goal.saved_amount), 100000.00)
        self.assertEqual(goal.status, 'completed')

        # Check congratulations notification
        notif = Notification.query.filter_by(user_id=self.user.user_id, type='goal_completed').first()
        self.assertIsNotNone(notif)
        self.assertIn('Goal Reached', notif.title)

    # -------------------------------------------------------------
    # 7. Investment Gain/Loss Calculations
    # -------------------------------------------------------------
    def test_investment_gain_loss(self):
        # Buy 100 shares at 50 PKR (invested: 5,000 PKR). Current value: 7,500 PKR
        inv = Investment(
            user_id=self.user.user_id,
            asset_name='OGDC Stock',
            asset_type='stock',
            purchase_amount=5000.00,
            current_value=7500.00,
            purchase_date=date.today() - timedelta(days=30),
        )
        db.session.add(inv)
        db.session.commit()

        # Unrealized gain: 2,500 (+50%)
        self.assertEqual(inv.gain_loss, 2500.0)
        self.assertEqual(inv.gain_loss_pct, 50.0)

        # Sell at 8,000 PKR
        inv.sold_amount = 8000.00
        inv.sold_date = date.today()
        db.session.commit()

        # Realized gain: 3,000 (+60%)
        self.assertEqual(inv.realized_gain_loss, 3000.0)
        self.assertEqual(inv.realized_gain_loss_pct, 60.0)

    # -------------------------------------------------------------
    # 8. Recurring Transactions Processing
    # -------------------------------------------------------------
    def test_recurring_transaction_execution(self):
        due_date = date.today() - timedelta(days=1)
        rec = RecurringTransaction(
            user_id=self.user.user_id,
            account_id=self.account.account_id,
            category_id=self.cat_rent.category_id,
            amount=30000.00,
            transaction_type='expense',
            frequency='monthly',
            next_due_date=due_date,
            is_active=True,
            description='Monthly Office Rent',
        )
        db.session.add(rec)
        db.session.commit()

        self.login()
        resp = self.client.post('/recurring/process', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        # Check transaction was generated
        tx = Transaction.query.filter_by(
            user_id=self.user.user_id,
            amount=30000.00,
            transaction_type='expense',
        ).first()
        self.assertIsNotNone(tx)
        self.assertIn('[Auto]', tx.description)

        # Check next due date rolled over
        db.session.refresh(rec)
        self.assertGreater(rec.next_due_date, date.today())

    # -------------------------------------------------------------
    # 9. REST API v1 Endpoints Tests
    # -------------------------------------------------------------
    def test_rest_api_v1_endpoints(self):
        self.login()

        # Test GET /api/v1/accounts
        resp = self.client.get('/api/v1/accounts')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('accounts', data)
        self.assertEqual(len(data['accounts']), 1)
        self.assertEqual(data['accounts'][0]['name'], 'Primary Checking')

        # Test POST /api/v1/transactions
        tx_payload = {
            'account_id': self.account.account_id,
            'category_id': self.cat_salary.category_id,
            'amount': 45000.00,
            'transaction_type': 'income',
            'transaction_date': date.today().isoformat(),
            'description': 'Freelance Project Delivery',
            'currency': 'PKR',
        }
        resp_post = self.client.post('/api/v1/transactions', json=tx_payload)
        self.assertEqual(resp_post.status_code, 201)
        post_data = resp_post.get_json()
        self.assertIn('id', post_data)
        created_tx_id = post_data['id']

        # Test GET /api/v1/accounts/<id>/balance
        resp_bal = self.client.get(f'/api/v1/accounts/{self.account.account_id}/balance')
        self.assertEqual(resp_bal.status_code, 200)
        bal_data = resp_bal.get_json()
        self.assertEqual(bal_data['balance'], 45000.0)

        # Test GET /api/v1/transactions
        resp_list = self.client.get('/api/v1/transactions')
        self.assertEqual(resp_list.status_code, 200)
        list_data = resp_list.get_json()
        self.assertEqual(list_data['total'], 1)

        # Test DELETE /api/v1/transactions/<id>
        resp_del = self.client.delete(f'/api/v1/transactions/{created_tx_id}')
        self.assertEqual(resp_del.status_code, 200)
        self.assertEqual(resp_del.get_json()['message'], 'Deleted')

        # Balance after soft-delete should be 0 again
        resp_bal_after = self.client.get(f'/api/v1/accounts/{self.account.account_id}/balance')
        self.assertEqual(resp_bal_after.get_json()['balance'], 0.0)

    # -------------------------------------------------------------
    # 10. Web Pages & Charts Accessibility
    # -------------------------------------------------------------
    def test_web_routes_and_dashboard_charts(self):
        self.login()

        # Seed sample income & expense for charts
        t_inc = Transaction(
            user_id=self.user.user_id,
            account_id=self.account.account_id,
            category_id=self.cat_salary.category_id,
            amount=80000.00,
            transaction_type='income',
            transaction_date=date.today(),
        )
        t_exp = Transaction(
            user_id=self.user.user_id,
            account_id=self.account.account_id,
            category_id=self.cat_food.category_id,
            amount=12000.00,
            transaction_type='expense',
            transaction_date=date.today(),
        )
        db.session.add_all([t_inc, t_exp])
        db.session.commit()

        # Dashboard
        resp_dash = self.client.get('/dashboard/')
        self.assertEqual(resp_dash.status_code, 200)
        self.assertIn(b'FinanceFlow', resp_dash.data)

        # Charts feeds
        resp_c1 = self.client.get('/dashboard/chart/income-expense')
        self.assertEqual(resp_c1.status_code, 200)
        c1_data = resp_c1.get_json()
        self.assertIn('labels', c1_data)
        self.assertIn('income', c1_data)

        resp_c2 = self.client.get('/dashboard/chart/spending-category')
        self.assertEqual(resp_c2.status_code, 200)
        c2_data = resp_c2.get_json()
        self.assertIn('Food', c2_data['labels'])

        # Other pages
        routes = [
            '/transactions/',
            '/accounts/',
            '/budgets/',
            '/savings/',
            '/investments/',
            '/recurring/',
            '/tags/',
            '/reports/',
            '/reports/monthly',
            '/reports/category',
            '/reports/audit',
        ]
        for r in routes:
            resp = self.client.get(r)
            self.assertEqual(resp.status_code, 200, f'Route {r} returned {resp.status_code}')

        # Test CSV statement export
        resp_csv = self.client.get('/reports/export/csv')
        self.assertEqual(resp_csv.status_code, 200)
        self.assertEqual(resp_csv.headers['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn(b'Salary', resp_csv.data)


if __name__ == '__main__':
    unittest.main()
