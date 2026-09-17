"""AI Advisor blueprint — /ai prefix."""
from flask import Blueprint

ai_bp = Blueprint('ai', __name__, url_prefix='/ai', template_folder='../templates')

from . import routes  # noqa: E402, F401

