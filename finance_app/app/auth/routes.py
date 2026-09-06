from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from . import auth_bp
from .forms import LoginForm, RegisterForm
from ..extensions import db, oauth
from ..models.user import User
from ..models.category import Category
from ..models.tag import Tag


def _seed_defaults_for_user(user):
    """Create default account, categories and tags for a new user."""
    from ..models.account import Account
    default_account = Account(
        user_id=user.user_id,
        account_name='Primary Checking',
        account_type='bank',
        currency=user.preferred_currency or 'PKR',
        is_active=True,
    )
    db.session.add(default_account)

    default_categories = [
        ('Salary', 'income', '💰'),
        ('Freelance', 'income', '💻'),
        ('Food', 'expense', '🍔'),
        ('Transport', 'expense', '🚗'),
        ('Utilities', 'expense', '💡'),
        ('Entertainment', 'expense', '🎬'),
        ('Health', 'expense', '🏥'),
        ('Rent', 'expense', '🏠'),
        ('Shopping', 'expense', '🛍️'),
        ('Education', 'expense', '📚'),
    ]
    for name, cat_type, icon in default_categories:
        cat = Category(user_id=user.user_id, name=name, type=cat_type, icon=icon, is_default=True)
        db.session.add(cat)

    default_tags = [
        ('essential', '#10b981'),
        ('leisure', '#f59e0b'),
        ('recurring', '#6366f1'),
        ('one-time', '#22d3ee'),
    ]
    for name, color in default_tags:
        tag = Tag(user_id=user.user_id, name=name, color=color)
        db.session.add(tag)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form = LoginForm()
    if form.validate_on_submit():
        email = (form.email.data or '').strip().lower()
        password = form.password.data or ''
        user = User.query.filter(db.func.lower(User.email) == email).first()
        if user and (user.check_password(password) or user.check_password(password.strip())):
            remember = form.remember.data if hasattr(form, 'remember') else True
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            flash(f'Welcome back, {user.display_name}!', 'success')
            return redirect(next_page or url_for('dashboard.index'))
        flash('Invalid email or password. Please check your credentials or use the demo account below.', 'danger')

    return render_template('auth/login.html', form=form)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form = RegisterForm()
    if form.validate_on_submit():
        email = (form.email.data or '').strip().lower()
        existing = User.query.filter(db.func.lower(User.email) == email).first()
        if existing:
            flash('An account with this email already exists.', 'danger')
            return render_template('auth/register.html', form=form)

        user = User(
            name=form.name.data.strip(),
            email=email,
            phone=form.phone.data.strip() if form.phone.data else None,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush()  # Get user_id before seeding defaults

        _seed_defaults_for_user(user)
        db.session.commit()

        login_user(user, remember=True)
        flash('Account created successfully!', 'success')
        return redirect(url_for('dashboard.index'))

    return render_template('auth/register.html', form=form)


@auth_bp.route('/login/google')
def google_login():
    try:
        google = oauth.create_client('google')
        if google is None:
            flash('Google Sign-In is not configured. Use email login instead.', 'warning')
            return redirect(url_for('auth.login'))
        redirect_uri = url_for('auth.google_callback', _external=True)
        return google.authorize_redirect(redirect_uri)
    except Exception:
        flash('Google Sign-In is not configured. Use email login instead.', 'warning')
        return redirect(url_for('auth.login'))


@auth_bp.route('/callback')
def google_callback():
    try:
        token = oauth.google.authorize_access_token()
        user_info = token.get('userinfo')
        if not user_info:
            user_info = oauth.google.userinfo()

        # Check if user already exists (by google_id or email)
        user = User.query.filter_by(google_id=user_info['sub']).first()
        if not user:
            user = User.query.filter_by(email=user_info['email']).first()
            if user:
                # Link Google to existing account
                user.google_id = user_info['sub']
                user.avatar_url = user_info.get('picture')
            else:
                # Create new user from Google profile
                user = User(
                    name=user_info.get('name', user_info['email'].split('@')[0]),
                    email=user_info['email'],
                    google_id=user_info['sub'],
                    avatar_url=user_info.get('picture'),
                )
                db.session.add(user)
                db.session.flush()
                _seed_defaults_for_user(user)

        db.session.commit()
        login_user(user)
        flash('Signed in with Google!', 'success')
        return redirect(url_for('dashboard.index'))

    except Exception as e:
        flash(f'Google sign-in failed: {str(e)}', 'danger')
        return redirect(url_for('auth.login'))


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
