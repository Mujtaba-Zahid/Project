from flask import Blueprint

savings_bp = Blueprint('savings', __name__, url_prefix='/savings')

from . import routes  # noqa: E402, F401
