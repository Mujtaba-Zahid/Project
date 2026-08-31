from flask import Blueprint

recurring_bp = Blueprint('recurring', __name__, url_prefix='/recurring')

from . import routes  # noqa: E402, F401
