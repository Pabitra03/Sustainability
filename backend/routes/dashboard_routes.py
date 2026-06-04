from flask import Blueprint, request, jsonify
from config.db import get_db_connection
from datetime import datetime
from utils.ai_engine import (
    action_center,
    calculate_health_score,
    daily_briefing,
    diet_recommendation,
    fetch_user_context,
    motivation_message,
    notifications,
    nutrient_analysis,
    weekly_recommendation,
    weight_forecast,
    workout_recommendation,
)

dashboard_bp = Blueprint('dashboard', __name__)

def load_context_response(user_id):
    if not user_id:
        return None, (jsonify({"error": "User ID is required"}), 400)

    conn = get_db_connection()
    if not conn:
        return None, (jsonify({"error": "Database connection failed"}), 500)

    try:
        context = fetch_user_context(conn, user_id)
        if not context:
            return None, (jsonify({"error": "Profile not found"}), 404)
        return context, None
    finally:
        conn.close()

@dashboard_bp.route('', methods=['GET'])
@dashboard_bp.route('/', methods=['GET'])
def get_dashboard():
    user_id = request.args.get('user_id')

    context, error = load_context_response(user_id)
    if error:
        return error

    try:
        core = context["core"]
        response_data = {
            "name": context["user"]['user_name'],
            "today_date": datetime.now().strftime("%A, %B %d"),
            "active_days": 0, # Initial value before fetchProgressStatus updates it
            "metrics": {
                "bmi": core["bmi"],
                "bmr": core["bmr"],
                "tdee": core["tdee"],
                "daily_calories": core["daily_calories"],
                "protein_g": core["protein_g"],
                "fiber_g": core["fiber_g"],
                "hydration_ml": core["hydration_ml"],
                "sleep_hours": core["sleep_hours"],
                "goal": core["goal"]
            },
            "uses_hostel": bool(context["user"].get("uses_hostel")),
            "diet": context["diet_plan"],
            "workout": context["workout_plan"],
            "weekly_plan": context["weekly_plan"],
            "health_score": calculate_health_score(context),
            "action_center": action_center(context),
            "nutrient_analysis": nutrient_analysis(context),
            "notifications": notifications(context),
            "daily_briefing": daily_briefing(context),
            "diet_recommendation": diet_recommendation(context),
            "workout_recommendation": workout_recommendation(context),
            "weekly_recommendation": weekly_recommendation(context),
            "today_metrics": context["today_metrics"],
            "weight_forecast": weight_forecast(context),
            "motivation": motivation_message(context)
        }
        return jsonify(response_data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@dashboard_bp.route('/daily-briefing', methods=['GET'])
def get_daily_briefing():
    context, error = load_context_response(request.args.get('user_id'))
    if error:
        return error
    return jsonify(daily_briefing(context)), 200

@dashboard_bp.route('/action-center', methods=['GET'])
def get_action_center():
    context, error = load_context_response(request.args.get('user_id'))
    if error:
        return error
    return jsonify(action_center(context)), 200

@dashboard_bp.route('/health-score', methods=['GET'])
def get_health_score():
    context, error = load_context_response(request.args.get('user_id'))
    if error:
        return error
    return jsonify(calculate_health_score(context)), 200

@dashboard_bp.route('/nutrient-analysis', methods=['GET'])
def get_nutrient_analysis():
    context, error = load_context_response(request.args.get('user_id'))
    if error:
        return error
    return jsonify(nutrient_analysis(context)), 200

@dashboard_bp.route('/notifications', methods=['GET'])
def get_notifications():
    context, error = load_context_response(request.args.get('user_id'))
    if error:
        return error
    return jsonify(notifications(context)), 200
