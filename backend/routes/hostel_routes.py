from datetime import date

from flask import Blueprint, jsonify, request

from config.db import get_db_connection
from utils.ai_engine import fetch_user_context, nutrient_analysis
from utils.nutrition import estimate_menu_food
from utils.schema import ensure_app_schema

hostel_bp = Blueprint("hostel", __name__)


def recommendation_text(context, totals, items_text):
    nutrients = nutrient_analysis(context)
    core = context["core"]
    text = (items_text or "").lower()
    avoid = []
    choose = []

    if any(word in text for word in ["fried", "biryani", "pakora", "samosa", "puri", "poori", "maggi"]):
        avoid.append("large oily or fried portions")
    if totals["protein_g"] < 15:
        choose.extend(nutrients["protein"]["foods"][:2])
    if totals["fiber_g"] < 5:
        choose.extend(nutrients["fiber"]["foods"][:2])
    if totals["calories"] > core["daily_calories"] * 0.4:
        choose.append("smaller rice or paratha portion")
    if not choose:
        choose.append("the current plate with extra salad")

    protein_level = "Good" if totals["protein_g"] >= 20 else "Low"
    calorie_level = "High" if totals["calories"] > core["daily_calories"] * 0.4 else "Balanced"
    meal_share = round((totals["calories"] / core["daily_calories"]) * 100) if core["daily_calories"] else 0

    return {
        "protein_level": protein_level,
        "calorie_level": calorie_level,
        "meal_share_percent": meal_share,
        "avoid": avoid,
        "choose": list(dict.fromkeys(choose)),
        "suggestion": (
            f"This meal has about {round(totals['protein_g'])}g protein and "
            f"{round(totals['calories'])} kcal, around {meal_share}% of today's calories. "
            f"Choose {', '.join(list(dict.fromkeys(choose))[:2])} to keep the plate aligned."
        ),
    }


def hostel_enabled(conn, user_id):
    cursor = conn.cursor()
    cursor.execute("SELECT uses_hostel FROM profiles WHERE user_id = %s", (user_id,))
    profile = cursor.fetchone()
    cursor.close()
    return bool(profile and profile.get("uses_hostel"))


@hostel_bp.route("/menu", methods=["GET"])
def get_menu():
    user_id = request.args.get("user_id")
    menu_date = request.args.get("date") or date.today().isoformat()
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        ensure_app_schema(conn)
        if not hostel_enabled(conn, user_id):
            return jsonify({"error": "Hostel Mode is disabled for this profile"}), 403
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM hostel_menus WHERE user_id = %s AND menu_date = %s",
            (user_id, menu_date),
        )
        menu = cursor.fetchone()
        cursor.close()
        return jsonify(menu or {
            "user_id": int(user_id),
            "menu_date": menu_date,
            "breakfast": "",
            "lunch": "",
            "dinner": "",
        }), 200
    finally:
        conn.close()


@hostel_bp.route("/menu", methods=["POST"])
def save_menu():
    data = request.json or {}
    user_id = data.get("user_id")
    menu_date = data.get("menu_date") or date.today().isoformat()
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        ensure_app_schema(conn)
        if not hostel_enabled(conn, user_id):
            return jsonify({"error": "Hostel Mode is disabled for this profile"}), 403
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO hostel_menus (user_id, menu_date, breakfast, lunch, dinner)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            breakfast=VALUES(breakfast), lunch=VALUES(lunch), dinner=VALUES(dinner)
        """, (
            user_id,
            menu_date,
            data.get("breakfast", ""),
            data.get("lunch", ""),
            data.get("dinner", ""),
        ))
        conn.commit()
        cursor.close()
        return jsonify({"message": "Hostel menu saved", "menu_date": menu_date}), 200
    finally:
        conn.close()


@hostel_bp.route("/analyze-menu", methods=["POST"])
def analyze_menu():
    data = request.json or {}
    user_id = data.get("user_id")
    meal_type = data.get("meal_type", "meal")
    items = data.get("items", "")
    should_store = bool(data.get("mark_consumed"))

    if not user_id or not items:
        return jsonify({"error": "User ID and items are required"}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        ensure_app_schema(conn)
        if not hostel_enabled(conn, user_id):
            return jsonify({"error": "Hostel Mode is disabled for this profile"}), 403
        context = fetch_user_context(conn, user_id)
        if not context:
            return jsonify({"error": "Profile not found"}), 404

        totals, matches = estimate_menu_food(items)
        analysis = recommendation_text(context, totals, items)

        if should_store:
            cursor = conn.cursor()
            today = date.today().isoformat()
            cursor.execute("""
                INSERT INTO hostel_consumption
                (user_id, entry_date, meal_type, items, calories, protein_g, carbs_g, fat_g)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                user_id, today, meal_type, items, round(totals["calories"]),
                totals["protein_g"], totals["carbs_g"], totals["fat_g"],
            ))
            cursor.execute("""
                INSERT INTO user_daily_metrics
                (user_id, entry_date, calories, protein_g, fiber_g)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                calories=COALESCE(calories, 0) + VALUES(calories),
                protein_g=COALESCE(protein_g, 0) + VALUES(protein_g),
                fiber_g=COALESCE(fiber_g, 0) + VALUES(fiber_g)
            """, (
                user_id, today, round(totals["calories"]),
                totals["protein_g"], totals["fiber_g"],
            ))
            conn.commit()
            cursor.close()

        return jsonify({
            "meal_type": meal_type,
            "items": items,
            "matched_foods": matches,
            "macros": {
                "calories": round(totals["calories"]),
                "protein_g": round(totals["protein_g"], 1),
                "carbs_g": round(totals["carbs_g"], 1),
                "fat_g": round(totals["fat_g"], 1),
                "fiber_g": round(totals["fiber_g"], 1),
            },
            "analysis": analysis,
        }), 200
    finally:
        conn.close()
