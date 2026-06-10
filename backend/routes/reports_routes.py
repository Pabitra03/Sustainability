from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request

from config.db import get_db_connection
from utils.coach_engine import calculate_health_score, fetch_user_context, notifications, weight_forecast
from utils.nutrition import estimate_food_cost, estimate_menu_food, food_catalog
from utils.schema import ensure_app_schema

reports_bp = Blueprint("reports", __name__)


def completion_rate(progress_history, field):
    if not progress_history:
        return 0
    completed = sum(1 for row in progress_history if row.get(field))
    return round((completed / len(progress_history)) * 100)


def achievements(context):
    health = calculate_health_score(context)
    progress = context["progress_history"]
    diet_rate = completion_rate(progress, "diet_completed")
    workout_rate = completion_rate(progress, "workout_completed")
    items = []

    if health["score"] >= 75:
        items.append("Health Score Hero")
    if diet_rate >= 70:
        items.append("Diet Champion")
    if workout_rate >= 70:
        items.append("Consistency Hero")
    if health["components"]["protein"]["score"] >= 90:
        items.append("Protein Master")
    if context["user"]["goal"] in ["loss", "gain"]:
        items.append("Goal Crusher")
    return items


def report_hostel_analysis(context, consumption):
    menu = context.get("hostel_menu") or {}
    totals = {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "fiber_g": 0}
    for meal in ["breakfast", "lunch", "dinner"]:
        meal_totals, _ = estimate_menu_food(menu.get(meal) or "")
        for key in totals:
            totals[key] += meal_totals[key]
    consumed_protein = round(sum(float(row.get("protein_g") or 0) for row in consumption), 1)
    consumed_calories = round(sum(float(row.get("calories") or 0) for row in consumption))
    return {
        "today_menu": menu,
        "today_menu_estimate": {
            "calories": round(totals["calories"]),
            "protein_g": round(totals["protein_g"], 1),
            "carbs_g": round(totals["carbs_g"], 1),
            "fat_g": round(totals["fat_g"], 1),
        },
        "logged_mess_totals": {
            "calories": consumed_calories,
            "protein_g": consumed_protein,
        },
    }


def report_budget_analysis(context):
    budget = float(context["user"].get("budget") or 0)
    foods = food_catalog(context["user"].get("diet_type"))[:5]
    daily_cost = round(sum(item["cost"] for item in foods[:3]), 1)
    return {
        "monthly_budget": round(budget, 1),
        "daily_budget": round(budget / 30, 1) if budget else 0,
        "recommended_daily_cost": daily_cost,
        "recommended_weekly_cost": round(daily_cost * 7, 1),
        "recommended_monthly_cost": round(daily_cost * 30, 1),
        "best_value_foods": foods,
    }


@reports_bp.route("/summary", methods=["GET"])
def summary():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        context = fetch_user_context(conn, user_id)
        if not context:
            return jsonify({"error": "Profile not found"}), 404

        ensure_app_schema(conn)
        cursor = conn.cursor()
        start = (date.today() - timedelta(days=29)).isoformat()
        cursor.execute("""
            SELECT entry_date, calories, protein_g, fiber_g, water_ml, sleep_hours, steps
            FROM user_daily_metrics
            WHERE user_id = %s AND entry_date >= %s
            ORDER BY entry_date ASC
        """, (user_id, start))
        metrics_history = cursor.fetchall()
        consumption = []
        if context["user"].get("uses_hostel"):
            cursor.execute("""
                SELECT entry_date, meal_type, items, calories, protein_g, carbs_g, fat_g
                FROM hostel_consumption
                WHERE user_id = %s AND entry_date >= %s
                ORDER BY entry_date DESC, id DESC
                LIMIT 20
            """, (user_id, start))
            consumption = cursor.fetchall()
        cursor.close()

        health = calculate_health_score(context)
        forecast = weight_forecast(context)
        notes = notifications(context)["items"]

        return jsonify({
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "user": {
                "name": context["user"]["user_name"],
                "goal": context["user"]["goal"],
                "diet_type": context["user"].get("diet_type"),
                "budget": context["user"].get("budget"),
                "uses_hostel": bool(context["user"].get("uses_hostel")),
                "hostel_name": context["user"].get("hostel_name") if context["user"].get("uses_hostel") else None,
                "mess_type": context["user"].get("mess_type") if context["user"].get("uses_hostel") else None,
            },
            "metrics": {
                "bmi": context["core"]["bmi"],
                "bmr": context["core"]["bmr"],
                "tdee": context["core"]["tdee"],
                "daily_calories": context["core"]["daily_calories"],
                "protein_g": context["core"]["protein_g"],
                "water_ml": context["core"]["hydration_ml"],
                "current_weight": float(context["user"]["weight"]),
                "goal_weight": forecast["goal_weight"],
            },
            "health_score": health,
            "completion": {
                "workout": completion_rate(context["progress_history"], "workout_completed"),
                "diet": completion_rate(context["progress_history"], "diet_completed"),
            },
            "weight_forecast": forecast,
            "achievements": achievements(context),
            "recommendations": [item["message"] for item in notes] or [
                "Stay consistent with today's calories, protein, water, and workout targets."
            ],
            "metrics_history": metrics_history,
            "recent_foods": consumption,
            "budget_analysis": report_budget_analysis(context),
            "mess_analysis": report_hostel_analysis(context, consumption) if context["user"].get("uses_hostel") else None,
        }), 200
    finally:
        conn.close()
