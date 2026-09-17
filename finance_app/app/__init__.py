import os
from flask import Flask
from .config import config_map
from .extensions import db, migrate, login_manager, csrf, mail, oauth


def create_app(config_name=None):
    """Application factory."""
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')

    app = Flask(__name__)
    app.config.from_object(config_map[config_name])

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)
    oauth.init_app(app)

    # Register Google OAuth
    if app.config.get('GOOGLE_CLIENT_ID'):
        oauth.register(
            name='google',
            client_id=app.config['GOOGLE_CLIENT_ID'],
            client_secret=app.config['GOOGLE_CLIENT_SECRET'],
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid email profile'},
        )

    # Ensure upload directory exists
    os.makedirs(app.config.get('UPLOAD_FOLDER', 'uploads'), exist_ok=True)

    # Register blueprints
    _register_blueprints(app)

    # Register user loader
    _register_user_loader()

    # Configure Flask-Login
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    # Register template context processors
    _register_context_processors(app)

    # Root route redirect
    @app.route('/')
    def index():
        from flask_login import current_user
        from flask import redirect, url_for
        if current_user.is_authenticated:
            return redirect(url_for('dashboard.index'))
        return redirect(url_for('auth.login'))

    return app


def _register_blueprints(app):
    """Register all Flask blueprints."""
    from .auth import auth_bp
    from .dashboard import dashboard_bp
    from .transactions import transactions_bp
    from .accounts import accounts_bp
    from .budgets import budgets_bp
    from .savings import savings_bp
    from .investments import investments_bp
    from .recurring import recurring_bp
    from .tags import tags_bp
    from .imports import imports_bp
    from .reports import reports_bp
    from .api import api_bp
    from .ai import ai_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(budgets_bp)
    app.register_blueprint(savings_bp)
    app.register_blueprint(investments_bp)
    app.register_blueprint(recurring_bp)
    app.register_blueprint(tags_bp)
    app.register_blueprint(imports_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(api_bp, url_prefix='/api/v1')
    app.register_blueprint(ai_bp)


def _register_user_loader():
    """Set up Flask-Login user loader."""
    from .models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))


def _register_context_processors(app):
    """Global template context variables."""
    @app.context_processor
    def inject_globals():
        return {
            'app_name': 'FinanceFlow',
        }
