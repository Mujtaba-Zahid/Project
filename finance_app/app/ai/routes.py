"""
AI Advisor routes — /ai/*
─────────────────────────
GET  /ai/advisor       → AI Financial Command Center page
POST /ai/chat          → AJAX endpoint for conversational Q&A
GET  /ai/profile       → View financial health profile
POST /ai/profile       → Update financial health profile
POST /ai/predict/train → Train ML models and get predictions
GET  /ai/api/alerts    → JSON endpoint for dashboard alert integration
"""

from flask import render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user

from . import ai_bp
from ..extensions import db
from ..models.financial_profile import FinancialProfile
from ..services.ai_alerts import detect_overspending, get_alerts_json, ALERT_META
from ..services.recommender import generate_recommendations
from ..services.groq_client import chat as groq_chat, clear_chat_history
from ..services.groq_middleware import GroqMiddleware, SUPPORTED_MODELS
from ..services.spending_predictor import train_models, predict_next_month
from ..models.ai_chat import AiChatMessage


def _ensure_profile(user_id):
    """Get or create a FinancialProfile for the user."""
    profile = FinancialProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        profile = FinancialProfile(user_id=user_id)
        profile.compute_score()
        db.session.add(profile)
        db.session.commit()
    return profile


@ai_bp.route('/advisor')
@login_required
def advisor():
    """AI Financial Command Center — unified dashboard."""
    profile = _ensure_profile(current_user.user_id)
    profile.compute_score()
    db.session.commit()

    alerts = detect_overspending(
        current_user.user_id,
        monthly_income=profile.monthly_income_pkr
    )
    recommendations = generate_recommendations(
        current_user.user_id,
        monthly_income=profile.monthly_income_pkr
    )
    predictions = predict_next_month(current_user.user_id)

    # Get recent chat messages
    recent_messages = (
        AiChatMessage.query
        .filter_by(user_id=current_user.user_id)
        .order_by(AiChatMessage.created_at.desc())
        .limit(20)
        .all()
    )
    recent_messages.reverse()

    # Format predictions for template
    prediction_data = []
    if predictions is not None:
        for _, row in predictions.iterrows():
            prediction_data.append({
                'category': row['category'],
                'predicted': round(row['predicted_next_month']),
            })

    # Groq API status
    groq_status = GroqMiddleware.get_status(current_user.user_id)

    return render_template('ai/advisor.html',
                           profile=profile,
                           alerts=alerts,
                           alert_meta=ALERT_META,
                           recommendations=recommendations,
                           predictions=prediction_data,
                           chat_messages=recent_messages,
                           groq_status=groq_status,
                           supported_models=SUPPORTED_MODELS)


@ai_bp.route('/chat', methods=['POST'])
@login_required
def chat():
    """AJAX endpoint for AI chatbot conversation."""
    data = request.get_json()
    if not data or not data.get('message', '').strip():
        return jsonify({'error': 'Message is required'}), 400

    user_message = data['message'].strip()
    requested_model = data.get('model')
    result = groq_chat(current_user.user_id, user_message, model=requested_model)

    return jsonify({
        'response': result['response'],
        'tokens_used': result['tokens_used'],
        'is_fallback': result['is_fallback'],
        'model_used': result.get('model_used', 'Default'),
        'source': result.get('source', 'none'),
    })


@ai_bp.route('/chat/clear', methods=['POST'])
@login_required
def chat_clear():
    """Clear chat history."""
    clear_chat_history(current_user.user_id)
    return jsonify({'status': 'ok'})


@ai_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """View and update the financial health profile."""
    fp = _ensure_profile(current_user.user_id)

    if request.method == 'POST':
        fp.monthly_income_pkr = request.form.get('monthly_income_pkr', type=float, default=80000)
        fp.income_type = request.form.get('income_type', 'Salary')
        fp.credit_score = request.form.get('credit_score', type=int, default=680)
        fp.debt_to_income_ratio = request.form.get('debt_to_income_ratio', type=float, default=0.35)
        fp.savings_rate = request.form.get('savings_rate', type=float, default=0.12)
        fp.financial_stress_level = request.form.get('financial_stress_level', 'Medium')
        fp.cash_flow_status = request.form.get('cash_flow_status', 'Neutral')
        fp.financial_scenario = request.form.get('financial_scenario', 'normal')
        fp.emergency_fund_pkr = request.form.get('emergency_fund_pkr', type=float, default=0)
        fp.emergency_fund_months = request.form.get('emergency_fund_months', type=float, default=1)
        fp.loan_payment_pkr = request.form.get('loan_payment_pkr', type=float, default=0)
        fp.investment_amount_pkr = request.form.get('investment_amount_pkr', type=float, default=0)
        fp.subscription_services = request.form.get('subscription_services', type=int, default=3)
        fp.savings_goal_met = request.form.get('savings_goal_met') == 'on'

        fp.compute_score()
        db.session.commit()
        flash('Financial profile updated! Your health score is now recalculated.', 'success')
        return redirect(url_for('ai.advisor'))

    return render_template('ai/profile.html', profile=fp)


@ai_bp.route('/predict/train', methods=['POST'])
@login_required
def predict_train():
    """Train ML models and return predictions."""
    results = train_models(current_user.user_id)
    if results is None:
        return jsonify({
            'error': 'Need at least 4 months of transaction data to train models.'
        }), 400

    predictions = predict_next_month(current_user.user_id)
    prediction_data = []
    if predictions is not None:
        for _, row in predictions.iterrows():
            prediction_data.append({
                'category': row['category'],
                'predicted': round(row['predicted_next_month']),
            })

    return jsonify({
        'status': 'ok',
        'metrics': results,
        'predictions': prediction_data,
    })


@ai_bp.route('/api/alerts')
@login_required
def api_alerts():
    """JSON endpoint for dashboard alert integration."""
    profile = _ensure_profile(current_user.user_id)
    alerts = get_alerts_json(
        current_user.user_id,
        monthly_income=profile.monthly_income_pkr
    )
    return jsonify({'alerts': alerts, 'count': len(alerts)})


@ai_bp.route('/api-key/save', methods=['POST'])
@login_required
def api_key_save():
    """Save or update custom Groq API key and preferred model for current user."""
    data = request.get_json() or {}
    api_key = data.get('api_key', '').strip()
    model = data.get('preferred_model', '').strip() or None

    if not api_key:
        return jsonify({'error': 'API key cannot be empty. Please enter your Groq API key.'}), 400

    # Optional pre-save connection verification
    if data.get('validate', True):
        test_result = GroqMiddleware.test_connection(api_key)
        if not test_result['success']:
            return jsonify({
                'error': test_result['error'],
                'latency_ms': test_result['latency_ms']
            }), 400

    result = GroqMiddleware.save_user_api_key(current_user.user_id, api_key, model)
    return jsonify({
        'status': 'ok',
        'message': 'Groq API key connected and verified successfully!',
        'masked_key': result['masked_key'],
        'preferred_model': result['preferred_model'],
    })


@ai_bp.route('/api-key/test', methods=['POST'])
@login_required
def api_key_test():
    """Test connection to Groq API with either supplied key or user's active key."""
    data = request.get_json() or {}
    api_key = data.get('api_key', '').strip()

    if not api_key:
        # Check if user already has an active key saved or in env
        api_key, source = GroqMiddleware.resolve_api_key(current_user.user_id)

    if not api_key:
        return jsonify({
            'success': False,
            'error': 'No API key provided or found in profile. Please enter a key to test.',
            'latency_ms': 0,
        }), 400

    result = GroqMiddleware.test_connection(api_key)
    return jsonify(result), (200 if result['success'] else 400)


@ai_bp.route('/api-key/delete', methods=['POST'])
@login_required
def api_key_delete():
    """Delete custom Groq API key from user's profile."""
    result = GroqMiddleware.delete_user_api_key(current_user.user_id)
    return jsonify({
        'status': 'ok',
        'message': 'Custom Groq API key removed. Reverted to offline fallback mode.',
        'has_fallback': result['has_fallback'],
        'source': result['source'],
    })


@ai_bp.route('/api-key/status')
@login_required
def api_key_status():
    """Return JSON with current Groq connection status and model options."""
    return jsonify(GroqMiddleware.get_status(current_user.user_id))

