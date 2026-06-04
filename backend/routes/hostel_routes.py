from datetime import date

from flask import Blueprint, jsonify, request

from config.db import get_db_connection
from utils.ai_engine import fetch_user_context, nutrient_analysis
from utils.schema import ensure_app_schema

hostel_bp = Blueprint("hostel", __name__)

FOOD_FACTS = {
    "egg": {"calories": 78, "protein_g": 6, "carbs_g": 1, "fat_g": 5, "fiber_g": 0},
    "chicken": {"calories": 220, "protein_g": 28, "carbs_g": 0, "fat_g": 9, "fiber_g": 0},
    "fish": {"calories": 180, "protein_g": 24, "carbs_g": 0, "fat_g": 8, "fiber_g": 0},
    "paneer": {"calories": 265, "protein_g": 18, "carbs_g": 6, "fat_g": 20, "fiber_g": 0},
    "soya": {"calories": 170, "protein_g": 26, "carbs_g": 15, "fat_g": 1, "fiber_g": 6},
    "dal": {"calories": 180, "protein_g": 12, "carbs_g": 28, "fat_g": 3, "fiber_g": 8},
    "rajma": {"calories": 220, "protein_g": 13, "carbs_g": 36, "fat_g": 2, "fiber_g": 10},
    "chana": {"calories": 230, "protein_g": 12, "carbs_g": 38, "fat_g": 4, "fiber_g": 10},
    "rice": {"calories": 210, "protein_g": 4, "carbs_g": 45, "fat_g": 1, "fiber_g": 1},
    "roti": {"calories": 110, "protein_g": 3, "carbs_g": 22, "fat_g": 1, "fiber_g": 3},
    "curd": {"calories": 100, "protein_g": 5, "carbs_g": 7, "fat_g": 5, "fiber_g": 0},
    "milk": {"calories": 150, "protein_g": 8, "carbs_g": 12, "fat_g": 8, "fiber_g": 0},
    "sprout": {"calories": 80, "protein_g": 6, "carbs_g": 13, "fat_g": 1, "fiber_g": 4},
    "salad": {"calories": 40, "protein_g": 2, "carbs_g": 8, "fat_g": 0, "fiber_g": 3},
    "poha": {"calories": 250, "protein_g": 6, "carbs_g": 45, "fat_g": 6, "fiber_g": 3},
    "idli": {"calories": 120, "protein_g": 4, "carbs_g": 24, "fat_g": 1, "fiber_g": 1},
    "fried": {"calories": 300, "protein_g": 5, "carbs_g": 35, "fat_g": 15, "fiber_g": 1},
    "biryani": {"calories": 420, "protein_g": 18, "carbs_g": 55, "fat_g": 14, "fiber_g": 3},
}


def estimate_food(items_text):
    text = (items_text or "").lower()
    totals = {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "fiber_g": 0}
    matches = []

    for key, facts in FOOD_FACTS.items():
        if key in text:
            matches.append(key)
            for metric, value in facts.items():
                totals[metric] += value

    if not matches and text.strip():
        words = [word for word in text.replace(",", " ").split() if len(word) > 2]
        portions = max(1, min(3, len(words) // 2 or 1))
        totals = {
            "calories": 180 * portions,
            "protein_g": 6 * portions,
            "carbs_g": 28 * portions,
            "fat_g": 5 * portions,
            "fiber_g": 3 * portions,
        }

    return totals, matches


def recommendation_text(context, totals, items_text):
    nutrients = nutrient_analysis(context)
    text = (items_text or "").lower()
    avoid = []
    choose = []

    if "fried" in text or "biryani" in text:
        avoid.append("fried rice or oily biryani portions")
    if totals["protein_g"] < 15:
        choose.extend(nutrients["protein"]["foods"][:2])
    if totals["fiber_g"] < 5:
        choose.extend(nutrients["fiber"]["foods"][:2])
    if not choose:
        choose.append("the current plate with extra salad")

    protein_level = "Good" if totals["protein_g"] >= 20 else "Low"
    calorie_level = "High" if totals["calories"] > context["core"]["daily_calories"] * 0.35 else "Balanced"

    return {
        "protein_level": protein_level,
        "calorie_level": calorie_level,
        "avoid": avoid,
        "choose": choose,
        "suggestion": (
            f"This meal has about {round(totals['protein_g'])}g protein and "
            f"{round(totals['calories'])} kcal. Choose {', '.join(choose[:2])} "
            "to keep your hostel meal aligned with today's goal."
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

        totals, matches = estimate_food(items)
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
