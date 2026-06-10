from datetime import date, timedelta

from flask import Blueprint, jsonify, request

from config.db import get_db_connection
from utils.coach_engine import calculate_health_score, fetch_user_context, nutrient_analysis
from utils.nutrition import estimate_food_cost, estimate_menu_food, food_catalog
from utils.schema import ensure_app_schema

hostel_bp = Blueprint("hostel", __name__)


def round_macros(totals):
    return {
        "calories": round(totals["calories"]),
        "protein_g": round(totals["protein_g"], 1),
        "carbs_g": round(totals["carbs_g"], 1),
        "fat_g": round(totals["fat_g"], 1),
        "fiber_g": round(totals["fiber_g"], 1),
    }


def quality_score(context, totals):
    core = context["core"]
    score = 100
    meal_calorie_share = totals["calories"] / core["daily_calories"] if core["daily_calories"] else 0
    if totals["protein_g"] < core["protein_g"] * 0.2:
        score -= 25
    if totals["fiber_g"] < 5:
        score -= 15
    if meal_calorie_share > 0.45:
        score -= 20
    if totals["fat_g"] > 25:
        score -= 10
    return max(0, min(100, round(score)))


def combine_menu(menu):
    if not menu:
        return ""
    return "\n".join(
        value for value in [menu.get("breakfast"), menu.get("lunch"), menu.get("dinner")]
        if value
    )


def current_menu_analysis(context):
    menu = context.get("hostel_menu") or {}
    meals = {}
    totals = {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "fiber_g": 0}
    matched = []

    for meal in ["breakfast", "lunch", "dinner"]:
        text = menu.get(meal) or ""
        meal_totals, meal_matches = estimate_menu_food(text)
        meals[meal] = {
            "menu": text,
            "matched_foods": meal_matches,
            "macros": round_macros(meal_totals),
            "quality_score": quality_score(context, meal_totals) if text else 0,
        }
        matched.extend(meal_matches)
        for key in totals:
            totals[key] += meal_totals[key]

    score = quality_score(context, totals) if combine_menu(menu) else 0
    return {
        "meals": meals,
        "matched_foods": sorted(set(matched)),
        "macros": round_macros(totals),
        "quality_score": score,
    }


def consumed_today(context):
    metrics = context.get("today_metrics") or {}
    progress = context.get("today_progress") or {}
    core = context["core"]
    protein = metrics.get("protein_g")
    calories = metrics.get("calories")
    if progress.get("diet_completed"):
        protein = protein if protein is not None else core["protein_g"]
        calories = calories if calories is not None else core["daily_calories"]
    return {
        "protein_g": round(float(protein or 0), 1),
        "calories": round(float(calories or 0)),
    }


def protein_gap(context):
    core = context["core"]
    consumed = consumed_today(context)
    remaining = max(0, round(core["protein_g"] - consumed["protein_g"], 1))
    suggestions = []
    remaining_budget = float(context["user"].get("budget") or 0) / 30 if context["user"].get("budget") else None
    for item in food_catalog(context["user"].get("diet_type")):
        if item["protein_g"] <= 0:
            continue
        if remaining_budget is not None and item["cost"] > max(remaining_budget, 15):
            continue
        servings = 1 if remaining <= item["protein_g"] else min(3, round(remaining / item["protein_g"]))
        suggestions.append({
            **item,
            "servings": servings,
            "total_cost": estimate_food_cost(item["food"], servings),
            "total_protein_g": round(item["protein_g"] * servings, 1),
        })
        if len(suggestions) >= 5:
            break
    return {
        "target_protein_g": core["protein_g"],
        "consumed_protein_g": consumed["protein_g"],
        "remaining_protein_g": remaining,
        "suggestions": suggestions,
    }


def budget_plan(context):
    user = context["user"]
    monthly_budget = float(user.get("budget") or 0)
    daily_budget = round(monthly_budget / 30, 1) if monthly_budget else 0
    gap = protein_gap(context)
    candidates = food_catalog(user.get("diet_type"))
    selected = []
    spent = 0

    for item in candidates:
        if gap["remaining_protein_g"] <= 0 and len(selected) >= 3:
            break
        if monthly_budget and spent + item["cost"] > max(daily_budget, item["cost"]):
            continue
        selected.append(item)
        spent += item["cost"]
        if len(selected) >= 5:
            break

    return {
        "monthly_budget": round(monthly_budget, 1),
        "daily_budget": daily_budget,
        "daily_cost": round(spent, 1),
        "weekly_cost": round(spent * 7, 1),
        "monthly_cost": round(spent * 30, 1),
        "alternative_foods": selected,
        "budget_status": "Set a hostel budget in profile" if not monthly_budget else (
            "Within budget" if spent <= daily_budget else "Above daily budget"
        ),
    }


def grocery_plan(context):
    gap = protein_gap(context)
    daily_gap = gap["remaining_protein_g"] or max(15, round(context["core"]["protein_g"] * 0.25))
    weekly_need = daily_gap * 7
    weekly_budget = float(context["user"].get("budget") or 0) / 4 if context["user"].get("budget") else 0
    groceries = []
    used_budget = 0
    protein_covered = 0

    for item in food_catalog(context["user"].get("diet_type")):
        if protein_covered >= weekly_need or len(groceries) >= 6:
            break
        servings = max(1, min(14, round((weekly_need - protein_covered) / max(item["protein_g"], 1))))
        cost = estimate_food_cost(item["food"], servings)
        if weekly_budget and used_budget + cost > weekly_budget * 1.1:
            servings = max(1, int((weekly_budget - used_budget) // max(item["cost"], 1)))
            cost = estimate_food_cost(item["food"], servings)
        if servings <= 0:
            continue
        groceries.append({
            "food": item["food"],
            "quantity": servings,
            "unit": item["unit"],
            "estimated_cost": cost,
            "protein_g": round(item["protein_g"] * servings, 1),
        })
        used_budget += cost
        protein_covered += item["protein_g"] * servings

    return {
        "weekly_budget": round(weekly_budget, 1),
        "estimated_weekly_cost": round(used_budget, 1),
        "estimated_monthly_cost": round(used_budget * 4, 1),
        "target_weekly_gap_g": round(weekly_need, 1),
        "covered_protein_g": round(protein_covered, 1),
        "items": groceries,
    }


def survival_plan(context, remaining_budget=None):
    budget = float(remaining_budget) if remaining_budget not in [None, ""] else float(context["user"].get("budget") or 0) / 10
    ranked = []
    for item in food_catalog(context["user"].get("diet_type")):
        affordable_servings = int(budget // max(item["cost"], 1)) if budget else 0
        ranked.append({
            **item,
            "affordable_servings": affordable_servings,
            "protein_if_spent_g": round(affordable_servings * item["protein_g"], 1),
        })
    return {
        "budget_remaining": round(budget, 1),
        "ranked_foods": ranked[:8],
    }


def hostel_health_score(context):
    base = calculate_health_score(context)["score"]
    analysis = current_menu_analysis(context)
    budget = budget_plan(context)
    budget_score = 100 if budget["monthly_budget"] and budget["monthly_cost"] <= budget["monthly_budget"] else 60 if budget["monthly_budget"] else 40
    mess_score = analysis["quality_score"] or 50
    score = round((base * 0.7) + (budget_score * 0.15) + (mess_score * 0.15))
    if score >= 90:
        label = "Excellent"
    elif score >= 75:
        label = "Good"
    elif score >= 60:
        label = "Average"
    else:
        label = "Poor"
    return {
        "score": max(0, min(100, score)),
        "label": label,
        "components": {
            "health": base,
            "budget_discipline": budget_score,
            "mess_food_quality": mess_score,
        },
    }


def hostel_insights(conn, context):
    user_id = context["user"]["user_id"]
    start = (date.today() - timedelta(days=29)).isoformat()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT entry_date, calories, protein_g, water_ml, sleep_hours, weight_kg
        FROM user_daily_metrics
        WHERE user_id = %s AND entry_date >= %s
        ORDER BY entry_date ASC
    """, (user_id, start))
    metrics = cursor.fetchall()
    cursor.execute("""
        SELECT entry_date, meal_type, items, calories, protein_g, carbs_g, fat_g
        FROM hostel_consumption
        WHERE user_id = %s AND entry_date >= %s
        ORDER BY entry_date ASC
    """, (user_id, start))
    consumption = cursor.fetchall()
    cursor.close()

    avg_protein = round(sum(float(row.get("protein_g") or 0) for row in metrics) / len(metrics), 1) if metrics else 0
    avg_calories = round(sum(float(row.get("calories") or 0) for row in metrics) / len(metrics)) if metrics else 0
    insights = []
    if avg_protein and avg_protein < context["core"]["protein_g"]:
        insights.append(f"Average protein is {round(context['core']['protein_g'] - avg_protein, 1)}g below target.")
    if not consumption:
        insights.append("Mark mess meals as consumed to unlock mess nutrition trends.")
    if not insights:
        insights.append("Mess and nutrition tracking are active.")

    return {
        "metrics": metrics,
        "recent_mess_foods": consumption,
        "averages": {
            "protein_g": avg_protein,
            "calories": avg_calories,
            "target_protein_g": context["core"]["protein_g"],
            "target_calories": context["core"]["daily_calories"],
        },
        "budget_plan": budget_plan(context),
        "protein_gap": protein_gap(context),
        "hostel_health_score": hostel_health_score(context),
        "hostel_insights": insights,
    }


def get_hostel_context(conn, user_id):
    ensure_app_schema(conn)
    if not hostel_enabled(conn, user_id):
        return None, (jsonify({"error": "Hostel Mode is disabled for this profile"}), 403)
    context = fetch_user_context(conn, user_id)
    if not context:
        return None, (jsonify({"error": "Profile not found"}), 404)
    return context, None


def sync_mess_tables(cursor, user_id, menu_date, meals):
    cursor.execute(
        "SELECT hostel_name, hostel_type, mess_type, budget FROM profiles WHERE user_id = %s",
        (user_id,),
    )
    profile = cursor.fetchone() or {}
    hostel_id = None
    if profile.get("hostel_name"):
        cursor.execute("""
            INSERT INTO hostels (name, hostel_type, mess_type, monthly_budget)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            monthly_budget=VALUES(monthly_budget), mess_type=VALUES(mess_type)
        """, (
            profile.get("hostel_name"),
            profile.get("hostel_type"),
            profile.get("mess_type"),
            profile.get("budget"),
        ))
        cursor.execute(
            "SELECT id FROM hostels WHERE name = %s AND (hostel_type <=> %s) AND (mess_type <=> %s)",
            (profile.get("hostel_name"), profile.get("hostel_type"), profile.get("mess_type")),
        )
        hostel = cursor.fetchone()
        hostel_id = hostel.get("id") if hostel else None
        if hostel_id:
            cursor.execute("UPDATE profiles SET hostel_id = %s WHERE user_id = %s", (hostel_id, user_id))

    cursor.execute("DELETE FROM mess_food_items WHERE mess_menu_id IN (SELECT id FROM mess_menus WHERE user_id = %s AND menu_date = %s)", (user_id, menu_date))
    cursor.execute("DELETE FROM mess_menus WHERE user_id = %s AND menu_date = %s", (user_id, menu_date))

    for meal_type, menu_text in meals.items():
        if not menu_text:
            continue
        totals, matches = estimate_menu_food(menu_text)
        cursor.execute("""
            INSERT INTO mess_menus
            (hostel_id, user_id, menu_date, meal_type, menu_text, calories, protein_g, carbs_g, fat_g, quality_score)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            hostel_id, user_id, menu_date, meal_type, menu_text, round(totals["calories"]),
            totals["protein_g"], totals["carbs_g"], totals["fat_g"], 0,
        ))
        mess_menu_id = cursor.lastrowid
        for food in matches:
            food_totals, _ = estimate_menu_food(food)
            cursor.execute("""
                INSERT INTO mess_food_items
                (mess_menu_id, food_name, meal_type, calories, protein_g, carbs_g, fat_g, estimated_cost)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                mess_menu_id, food, meal_type, round(food_totals["calories"]), food_totals["protein_g"],
                food_totals["carbs_g"], food_totals["fat_g"], estimate_food_cost(food),
            ))


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
        sync_mess_tables(cursor, user_id, menu_date, {
            "breakfast": data.get("breakfast", ""),
            "lunch": data.get("lunch", ""),
            "dinner": data.get("dinner", ""),
        })
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
        analysis["nutrition_quality_score"] = quality_score(context, totals)

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


@hostel_bp.route("/assistant", methods=["GET"])
def assistant():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        context, error = get_hostel_context(conn, user_id)
        if error:
            return error
        insights = hostel_insights(conn, context)
        return jsonify({
            "mess_analysis": current_menu_analysis(context),
            "budget_plan": insights["budget_plan"],
            "protein_gap": insights["protein_gap"],
            "grocery_plan": grocery_plan(context),
            "survival_mode": survival_plan(context, request.args.get("budget_remaining")),
            "hostel_health_score": insights["hostel_health_score"],
            "insights": insights,
        }), 200
    finally:
        conn.close()


@hostel_bp.route("/budget-plan", methods=["GET"])
def get_budget_plan():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    try:
        context, error = get_hostel_context(conn, user_id)
        if error:
            return error
        return jsonify(budget_plan(context)), 200
    finally:
        conn.close()


@hostel_bp.route("/protein-gap", methods=["GET"])
def get_protein_gap():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    try:
        context, error = get_hostel_context(conn, user_id)
        if error:
            return error
        return jsonify(protein_gap(context)), 200
    finally:
        conn.close()


@hostel_bp.route("/grocery-plan", methods=["GET"])
def get_grocery_plan():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    try:
        context, error = get_hostel_context(conn, user_id)
        if error:
            return error
        return jsonify(grocery_plan(context)), 200
    finally:
        conn.close()


@hostel_bp.route("/survival", methods=["GET"])
def get_survival_plan():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    try:
        context, error = get_hostel_context(conn, user_id)
        if error:
            return error
        return jsonify(survival_plan(context, request.args.get("budget_remaining"))), 200
    finally:
        conn.close()


@hostel_bp.route("/health-score", methods=["GET"])
def get_hostel_health_score():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    try:
        context, error = get_hostel_context(conn, user_id)
        if error:
            return error
        return jsonify(hostel_health_score(context)), 200
    finally:
        conn.close()


@hostel_bp.route("/insights", methods=["GET"])
def get_insights():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    try:
        context, error = get_hostel_context(conn, user_id)
        if error:
            return error
        return jsonify(hostel_insights(conn, context)), 200
    finally:
        conn.close()
