from datetime import date, datetime, timedelta

from models.recommender import recommender
from utils.nutrition import estimate_food_cost, estimate_menu_food, food_catalog
from utils.schema import ensure_app_schema
from utils.plans import get_diet_plan_details, get_weekly_plan, get_workout_plan_details


ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,
    "lightly_active": 1.375,
    "moderately_active": 1.55,
    "very_active": 1.725,
    "super_active": 1.9,
}


def hostel_menu_totals(context):
    menu = context.get("hostel_menu") or {}
    totals = {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "fiber_g": 0}
    meals = {}
    for meal in ["breakfast", "lunch", "dinner"]:
        text = menu.get(meal) or ""
        meal_totals, matches = estimate_menu_food(text)
        meals[meal] = {"menu": text, "macros": meal_totals, "matched_foods": matches}
        for key in totals:
            totals[key] += meal_totals[key]
    return totals, meals


def budget_food_suggestions(user, max_items=4):
    catalog = food_catalog(user.get("diet_type"))
    budget = float(user.get("budget") or 0)
    daily_budget = budget / 30 if budget else None
    suggestions = []
    for item in catalog:
        if daily_budget and item["cost"] > max(15, daily_budget):
            continue
        suggestions.append(item)
        if len(suggestions) >= max_items:
            break
    return suggestions or catalog[:max_items]


def protein_gap_summary(context):
    core = context["core"]
    nutrients = nutrient_analysis(context)
    suggestions = budget_food_suggestions(context["user"], 5)
    return {
        "target_protein_g": core["protein_g"],
        "consumed_protein_g": nutrients["protein"]["actual"],
        "remaining_protein_g": nutrients["protein"]["needed"],
        "budget_foods": suggestions,
    }


def hostel_mess_quality(context):
    totals, meals = hostel_menu_totals(context)
    core = context["core"]
    if not any(item["menu"] for item in meals.values()):
        return {"score": 0, "label": "No menu", "totals": totals, "meals": meals}
    score = 100
    if totals["protein_g"] < core["protein_g"] * 0.45:
        score -= 25
    if totals["fiber_g"] < core["fiber_g"] * 0.45:
        score -= 15
    if totals["calories"] > core["daily_calories"] * 1.15:
        score -= 20
    if totals["fat_g"] > 70:
        score -= 10
    score = max(0, min(100, round(score)))
    label = "Excellent" if score >= 90 else "Good" if score >= 75 else "Average" if score >= 60 else "Poor"
    return {"score": score, "label": label, "totals": totals, "meals": meals}


def ensure_ai_tables(conn):
    # Keep read-heavy endpoints fast. Write routes and explicit schema-repair
    # paths run migrations; context reads should not do DDL checks on every
    # serverless cold start.
    return


def fetch_user_context(conn, user_id):
    ensure_ai_tables(conn)
    cursor = conn.cursor()
    today = date.today()
    yesterday = today - timedelta(days=1)

    cursor.execute(
        "SELECT p.*, u.name as user_name, u.created_at FROM profiles p "
        "JOIN users u ON p.user_id = u.id WHERE p.user_id = %s",
        (user_id,),
    )
    user = cursor.fetchone()
    if not user:
        cursor.close()
        return None

    cursor.execute(
        "SELECT diet_completed, workout_completed FROM user_progress "
        "WHERE user_id = %s AND entry_date = %s",
        (user_id, today.isoformat()),
    )
    today_progress = cursor.fetchone() or {"diet_completed": False, "workout_completed": False}

    cursor.execute(
        "SELECT diet_completed, workout_completed FROM user_progress "
        "WHERE user_id = %s AND entry_date = %s",
        (user_id, yesterday.isoformat()),
    )
    yesterday_progress = cursor.fetchone() or {"diet_completed": False, "workout_completed": False}

    cursor.execute(
        "SELECT * FROM user_daily_metrics WHERE user_id = %s AND entry_date = %s",
        (user_id, today.isoformat()),
    )
    today_metrics = cursor.fetchone() or {}

    cursor.execute(
        "SELECT * FROM user_daily_metrics WHERE user_id = %s AND entry_date = %s",
        (user_id, yesterday.isoformat()),
    )
    yesterday_metrics = cursor.fetchone() or {}

    cursor.execute(
        "SELECT entry_date, diet_completed, workout_completed FROM user_progress "
        "WHERE user_id = %s ORDER BY entry_date DESC LIMIT 90",
        (user_id,),
    )
    progress_history = cursor.fetchall()

    uses_hostel = bool(user.get("uses_hostel"))
    hostel_menu = {}
    if uses_hostel:
        cursor.execute(
            "SELECT * FROM hostel_menus WHERE user_id = %s AND menu_date = %s",
            (user_id, today.isoformat()),
        )
        hostel_menu = cursor.fetchone() or {}

    start = today - timedelta(days=89)
    cursor.execute(
        "SELECT entry_date, weight_kg, calories, protein_g, fiber_g, water_ml, sleep_hours, steps "
        "FROM user_daily_metrics WHERE user_id = %s AND entry_date >= %s ORDER BY entry_date ASC",
        (user_id, start.isoformat()),
    )
    metrics_history = cursor.fetchall()
    cursor.close()

    core = calculate_core_metrics(user)
    diet_plan_id, workout_plan_id = recommender.predict(
        age=int(user["age"]),
        weight=float(user["weight"]),
        height=float(user["height"]),
        activity_level_str=user["activity_level"],
        goal_str=user["goal"],
    )
    diet_type = user.get("diet_type", "non_vegetarian")

    return {
        "user": user,
        "core": core,
        "today_progress": today_progress,
        "yesterday_progress": yesterday_progress,
        "today_metrics": today_metrics,
        "yesterday_metrics": yesterday_metrics,
        "progress_history": progress_history,
        "metrics_history": metrics_history,
        "hostel_menu": hostel_menu,
        "diet_plan": get_diet_plan_details(diet_plan_id, diet_type),
        "workout_plan": get_workout_plan_details(workout_plan_id),
        "weekly_plan": get_weekly_plan(diet_plan_id, workout_plan_id, diet_type),
    }


def calculate_core_metrics(user):
    weight_kg = float(user["weight"])
    height_cm = float(user["height"])
    age = int(user["age"])
    height_m = height_cm / 100
    bmi = round(weight_kg / (height_m ** 2), 1)

    if user["gender"] == "male":
        bmr = round(10 * weight_kg + 6.25 * height_cm - 5 * age + 5)
    else:
        bmr = round(10 * weight_kg + 6.25 * height_cm - 5 * age - 161)

    tdee = round(bmr * ACTIVITY_MULTIPLIERS.get(user["activity_level"], 1.2))
    if user["goal"] == "loss":
        daily_calories = max(1200, tdee - 500)
    elif user["goal"] == "gain":
        daily_calories = tdee + 500
    else:
        daily_calories = tdee

    protein_multiplier = 1.8 if user["goal"] == "gain" else 1.6 if user["goal"] == "loss" else 1.4
    return {
        "bmi": bmi,
        "bmr": bmr,
        "tdee": tdee,
        "daily_calories": daily_calories,
        "protein_g": round(weight_kg * protein_multiplier),
        "fiber_g": 30,
        "hydration_ml": round(weight_kg * 33),
        "sleep_hours": 8,
        "goal": user["goal"],
    }


def recommended_goal_weight(user):
    explicit = user.get("goal_weight_kg")
    if explicit:
        return round(float(explicit), 1)

    current = float(user["weight"])
    height_m = float(user["height"]) / 100
    healthy_upper = 24.9 * (height_m ** 2)
    healthy_middle = 22.5 * (height_m ** 2)

    if user["goal"] == "loss":
        return round(min(current, healthy_upper), 1)
    if user["goal"] == "gain":
        return round(max(current, healthy_middle), 1)
    return round(current, 1)


def logged_weight_points(context):
    points = []
    for row in context.get("metrics_history", []):
        if row.get("weight_kg") is None:
            continue
        entry_date = row["entry_date"]
        if isinstance(entry_date, str):
            entry_date = datetime.strptime(entry_date, "%Y-%m-%d").date()
        points.append((entry_date, float(row["weight_kg"])))
    return points


def trend_from_points(points):
    if len(points) < 2:
        return {"daily_slope": 0, "r2": 0, "confidence": 0, "sample_size": len(points)}

    start = points[0][0]
    xs = [(day - start).days for day, _ in points]
    ys = [value for _, value in points]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    variance = sum((x - x_mean) ** 2 for x in xs)
    if variance == 0:
        return {"daily_slope": 0, "r2": 0, "confidence": 0, "sample_size": len(points)}

    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / variance
    intercept = y_mean - slope * x_mean
    ss_total = sum((y - y_mean) ** 2 for y in ys)
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - (ss_res / ss_total) if ss_total else 0
    confidence = min(95, round(max(0, r2) * 60 + min(len(points), 14) / 14 * 35))
    return {
        "daily_slope": slope,
        "r2": round(max(0, r2), 3),
        "confidence": confidence,
        "sample_size": len(points),
    }


def score_ratio(actual, target):
    if actual is None or target <= 0:
        return 0
    ratio = float(actual) / float(target)
    if ratio > 1:
        ratio = max(0, 1 - ((ratio - 1) * 0.5))
    return round(max(0, min(1, ratio)) * 100)


def calculate_health_score(context, day="today"):
    core = context["core"]
    metrics = context["today_metrics"] if day == "today" else context["yesterday_metrics"]
    progress = context["today_progress"] if day == "today" else context["yesterday_progress"]

    calories_actual = metrics.get("calories")
    protein_actual = metrics.get("protein_g")
    if progress.get("diet_completed"):
        calories_actual = calories_actual if calories_actual is not None else core["daily_calories"]
        protein_actual = protein_actual if protein_actual is not None else core["protein_g"]

    components = {
        "calories": {
            "weight": 25,
            "score": score_ratio(calories_actual, core["daily_calories"]),
            "actual": calories_actual,
            "target": core["daily_calories"],
        },
        "protein": {
            "weight": 25,
            "score": score_ratio(protein_actual, core["protein_g"]),
            "actual": protein_actual,
            "target": core["protein_g"],
        },
        "workout": {
            "weight": 20,
            "score": 100 if progress.get("workout_completed") else 0,
            "actual": bool(progress.get("workout_completed")),
            "target": True,
        },
        "water": {
            "weight": 15,
            "score": score_ratio(metrics.get("water_ml"), core["hydration_ml"]),
            "actual": metrics.get("water_ml"),
            "target": core["hydration_ml"],
        },
        "sleep": {
            "weight": 15,
            "score": score_ratio(metrics.get("sleep_hours"), core["sleep_hours"]),
            "actual": metrics.get("sleep_hours"),
            "target": core["sleep_hours"],
        },
    }
    score = round(sum((item["score"] * item["weight"]) / 100 for item in components.values()))
    if score >= 90:
        label = "Excellent"
    elif score >= 75:
        label = "Good"
    elif score >= 60:
        label = "Average"
    else:
        label = "Poor"
    return {"score": score, "label": label, "components": components}


def nutrient_analysis(context):
    core = context["core"]
    metrics = context["today_metrics"]
    progress = context["today_progress"]
    user = context["user"]
    protein_actual = metrics.get("protein_g")
    fiber_actual = metrics.get("fiber_g")
    water_actual = metrics.get("water_ml")

    if progress.get("diet_completed"):
        protein_actual = protein_actual if protein_actual is not None else core["protein_g"]
        fiber_actual = fiber_actual if fiber_actual is not None else core["fiber_g"]

    is_veg = user.get("diet_type") == "vegetarian"
    protein_foods = ["paneer", "soya chunks", "dal", "curd"] if is_veg else ["eggs", "chicken", "fish", "curd"]
    fiber_foods = ["sprouts", "salad", "fruit", "dal"]

    return {
        "protein": {
            "actual": protein_actual or 0,
            "target": core["protein_g"],
            "needed": max(0, round(core["protein_g"] - (protein_actual or 0))),
            "foods": protein_foods,
        },
        "fiber": {
            "actual": fiber_actual or 0,
            "target": core["fiber_g"],
            "needed": max(0, round(core["fiber_g"] - (fiber_actual or 0))),
            "foods": fiber_foods,
        },
        "water": {
            "actual": water_actual or 0,
            "target": core["hydration_ml"],
            "needed": max(0, round(core["hydration_ml"] - (water_actual or 0))),
            "foods": ["water", "lemon water", "curd", "fruit"],
        },
    }


def weight_forecast(context):
    user = context["user"]
    core = context["core"]
    points = logged_weight_points(context)
    current = points[-1][1] if points else float(user["weight"])
    goal_weight = recommended_goal_weight(user)
    trend = trend_from_points(points)
    daily_delta = trend["daily_slope"]

    forecasts = {}
    for days in [7, 14, 30, 90, 180]:
        forecasts[str(days)] = round(current + (daily_delta * days), 1)

    moving_toward_goal = (goal_weight - current) * daily_delta > 0
    if not moving_toward_goal or daily_delta == 0:
        completion_date = None
    else:
        days_to_goal = abs((goal_weight - current) / daily_delta)
        completion_date = (date.today() + timedelta(days=round(days_to_goal))).isoformat()

    return {
        "current_weight": round(current, 1),
        "goal_weight": goal_weight,
        "predicted_weight": forecasts,
        "goal_completion_date": completion_date,
        "confidence": trend["confidence"],
        "weight_loss_rate_kg_per_week": round(daily_delta * 7, 2),
        "sample_size": trend["sample_size"],
        "basis": {
            "daily_calories": core["daily_calories"],
            "goal": user["goal"],
            "source": "logged_weight_regression" if trend["sample_size"] >= 2 else "insufficient_logged_weight_data",
        },
    }


def notifications(context):
    score = calculate_health_score(context)
    nutrients = nutrient_analysis(context)
    items = []
    if nutrients["protein"]["needed"] > 0:
        items.append({"type": "warning", "title": "Low protein", "message": f"Add {nutrients['protein']['needed']}g protein today."})
    if nutrients["water"]["needed"] > 0:
        items.append({"type": "warning", "title": "Low water", "message": f"Drink {nutrients['water']['needed']}ml more water."})
    if score["components"]["sleep"]["score"] < 75:
        items.append({"type": "warning", "title": "Sleep not logged", "message": "Log sleep hours to improve score accuracy."})
    if not context["today_progress"].get("workout_completed"):
        items.append({"type": "warning", "title": "Workout pending", "message": "Complete today's workout to protect your streak."})

    streak = current_streak(context["progress_history"])
    if streak >= 7:
        items.append({"type": "achievement", "title": "Streak achieved", "message": f"{streak} day consistency streak."})
    if score["score"] >= 80:
        items.append({"type": "motivation", "title": "Great job", "message": "Your health score is trending strong today."})
    return {"items": items, "count": len(items)}


def action_center(context):
    score = calculate_health_score(context)
    nutrients = nutrient_analysis(context)
    user = context["user"]
    actions = []
    if nutrients["water"]["needed"] > 0:
        actions.append({"action": "Drink 500ml water", "reason": "Water is the quickest score improvement."})
    if nutrients["protein"]["needed"] > 0:
        food = budget_food_suggestions(user, 1)[0]["food"] if user.get("uses_hostel") else nutrients["protein"]["foods"][0]
        actions.append({"action": f"Add {food} to your next meal", "reason": f"{nutrients['protein']['needed']}g protein still needed."})
    if user.get("uses_hostel"):
        mess_quality = hostel_mess_quality(context)
        if mess_quality["score"] and mess_quality["score"] < 70:
            actions.append({"action": "Balance today's mess plate", "reason": f"Mess quality is {mess_quality['label']} with {round(mess_quality['totals']['protein_g'])}g protein."})
        if user.get("budget"):
            budget_food = budget_food_suggestions(user, 1)[0]
            actions.append({"action": f"Use {budget_food['food']} for low-cost protein", "reason": f"{budget_food['protein_per_rupee']}g protein per rupee."})
    if not context["today_progress"].get("workout_completed"):
        actions.append({"action": "Complete today's workout", "reason": "Workout carries 20% of your health score."})
    if score["components"]["sleep"]["score"] < 75:
        actions.append({"action": "Plan sleep before 11 PM", "reason": "Sleep recovery is currently under target."})

    potential_score = score["score"]
    for key in ["water", "protein", "workout", "sleep"]:
        component = score["components"][key]
        if component["score"] < 100:
            potential_score += round(((100 - component["score"]) * component["weight"]) / 100)
            break

    return {
        "title": "What Should I Do Right Now?",
        "actions": actions[:4],
        "current_health_score": score["score"],
        "potential_health_score": min(100, potential_score),
    }


def daily_briefing(context):
    user = context["user"]
    core = context["core"]
    yesterday_score = calculate_health_score(context, day="yesterday")
    today_score = calculate_health_score(context, day="today")
    nutrients = nutrient_analysis(context)
    forecast = weight_forecast(context)
    weekday = datetime.now().strftime("%A").lower()
    diet_day = context["diet_plan"].get(weekday, context["diet_plan"]["monday"])

    summary = [
        {"label": "Workout completed", "completed": bool(context["yesterday_progress"].get("workout_completed"))},
        {"label": "Protein goal achieved", "completed": yesterday_score["components"]["protein"]["score"] >= 90},
        {"label": "Water goal achieved", "completed": yesterday_score["components"]["water"]["score"] >= 90},
    ]

    warnings = [item["message"] for item in notifications(context)["items"] if item["type"] == "warning"]
    hostel_recommendations = []
    hostel_menu_analysis = None
    if user.get("uses_hostel"):
        mess_quality = hostel_mess_quality(context)
        gap = protein_gap_summary(context)
        budget_foods = gap["budget_foods"][:2]
        hostel_menu_analysis = {
            "quality_score": mess_quality["score"],
            "quality_label": mess_quality["label"],
            "calories": round(mess_quality["totals"]["calories"]),
            "protein_g": round(mess_quality["totals"]["protein_g"], 1),
            "carbs_g": round(mess_quality["totals"]["carbs_g"], 1),
            "fat_g": round(mess_quality["totals"]["fat_g"], 1),
            "protein_gap_g": gap["remaining_protein_g"],
        }
        hostel_recommendations = [
            f"Today's mess is {mess_quality['label']} with about {round(mess_quality['totals']['protein_g'])}g protein.",
            f"Add {', '.join(item['food'] for item in budget_foods)} if protein is short.",
        ]

    return {
        "greeting": f"Good Morning {user['user_name']}",
        "today_date": datetime.now().strftime("%A, %B %d"),
        "yesterday_summary": summary,
        "today_goals": {
            "calories": core["daily_calories"],
            "protein_g": core["protein_g"],
            "water_ml": core["hydration_ml"],
            "sleep_hours": core["sleep_hours"],
        },
        "hostel_recommendations": hostel_recommendations,
        "hostel_menu_analysis": hostel_menu_analysis,
        "today_warnings": warnings,
        "weight_forecast": forecast,
        "health_score": today_score,
    }


def current_streak(progress_history):
    streak = 0
    expected = date.today()
    normalized = []
    for row in progress_history:
        entry_date = row["entry_date"]
        if isinstance(entry_date, str):
            entry_date = datetime.strptime(entry_date, "%Y-%m-%d").date()
        normalized.append((entry_date, bool(row["diet_completed"]) and bool(row["workout_completed"])))
    lookup = dict(normalized)
    while lookup.get(expected):
        streak += 1
        expected -= timedelta(days=1)
    return streak


def weekday_key(day=None):
    return (day or datetime.now()).strftime("%A").lower()


def profile_summary(context):
    user = context["user"]
    core = context["core"]
    return {
        "age": int(user["age"]),
        "gender": user["gender"],
        "weight_kg": float(user["weight"]),
        "height_cm": float(user["height"]),
        "activity_level": user["activity_level"],
        "goal": user["goal"],
        "diet_type": user.get("diet_type"),
        "budget": user.get("budget"),
        "hostel_name": user.get("hostel_name"),
        "hostel_type": user.get("hostel_type"),
        "mess_type": user.get("mess_type"),
        "uses_hostel": bool(user.get("uses_hostel")),
        "goal_weight_kg": user.get("goal_weight_kg"),
        "favorite_foods": user.get("favorite_foods"),
        "disliked_foods": user.get("disliked_foods"),
        "food_allergies": user.get("food_allergies"),
        "bmi": core["bmi"],
        "bmr": core["bmr"],
        "tdee": core["tdee"],
    }


def meal_macro_split(core):
    calories = core["daily_calories"]
    protein = core["protein_g"]
    return {
        "breakfast": {"calories": round(calories * 0.25), "protein_g": round(protein * 0.25)},
        "lunch": {"calories": round(calories * 0.35), "protein_g": round(protein * 0.35)},
        "snack": {"calories": round(calories * 0.15), "protein_g": round(protein * 0.15)},
        "dinner": {"calories": round(calories * 0.25), "protein_g": round(protein * 0.25)},
    }


def diet_recommendation(context):
    core = context["core"]
    user = context["user"]
    day_key = weekday_key()
    day_plan = context["diet_plan"].get(day_key, context["diet_plan"]["monday"])
    nutrients = nutrient_analysis(context)
    hostel_menu = context.get("hostel_menu") or {}
    budget = user.get("budget")
    preference_notes = []

    if user.get("favorite_foods"):
        preference_notes.append(f"Prioritize preferred foods when possible: {user.get('favorite_foods')}.")
    if user.get("food_allergies"):
        preference_notes.append(f"Avoid allergens: {user.get('food_allergies')}.")
    if user.get("disliked_foods"):
        preference_notes.append(f"Reduce disliked foods: {user.get('disliked_foods')}.")
    if budget:
        preference_notes.append(f"Keep choices practical for a monthly food budget near {round(float(budget))}.")

    hostel_notes = []
    if user.get("uses_hostel"):
        for meal_name in ["breakfast", "lunch", "dinner"]:
            menu_text = hostel_menu.get(meal_name)
            if menu_text:
                totals, _ = estimate_menu_food(menu_text)
                analysis = "protein support" if totals["protein_g"] >= 15 else "needs protein add-on"
                hostel_notes.append({
                    "meal": meal_name,
                    "menu": menu_text,
                    "estimated_calories": round(totals["calories"]),
                    "estimated_protein_g": round(totals["protein_g"], 1),
                    "note": analysis,
                })

    return {
        "type": "daily_diet_plan",
        "personalization": profile_summary(context),
        "targets": {
            "calories": core["daily_calories"],
            "protein_g": core["protein_g"],
            "fiber_g": core["fiber_g"],
            "water_ml": core["hydration_ml"],
            "sleep_hours": core["sleep_hours"],
        },
        "macro_split": meal_macro_split(core),
        "plan_name": context["diet_plan"]["name"],
        "today": {
            "day": day_key.title(),
            "breakfast": day_plan["breakfast"],
            "lunch": day_plan["lunch"],
            "snack": {
                "item": "Curd with fruit" if user.get("diet_type") == "vegetarian" else "Boiled eggs or curd with fruit",
                "details": "Use this only if protein or calories are short after hostel meals.",
                "image": "/assets/img/veg_breakfast.png",
            },
            "dinner": day_plan["dinner"],
        },
        "hostel_menu_analysis": hostel_notes,
        "deficiencies": nutrients,
        "personal_notes": preference_notes,
        "recommendations": [
            f"Hit {core['protein_g']}g protein before adding extra carbs.",
            f"Drink {core['hydration_ml']}ml water across the day.",
            "Adjust meals from the foods you actually log.",
        ],
    }


def exercise_library(routine, context):
    text = (routine or "").lower()
    goal = context["user"]["goal"]
    bmi = context["core"]["bmi"]

    if "rest" in text or "stretch" in text or "yoga" in text or "mobility" in text:
        exercises = [
            {"name": "Mobility Flow", "duration": "12 min", "difficulty": "Beginner", "burn_kcal": 45},
            {"name": "Hamstring and Hip Stretch", "duration": "10 min", "difficulty": "Beginner", "burn_kcal": 30},
            {"name": "Easy Walk", "duration": "20 min", "difficulty": "Beginner", "burn_kcal": 90},
        ]
    elif "cardio" in text or "hiit" in text or "sprint" in text or goal == "loss":
        exercises = [
            {"name": "Brisk Walk or Jog", "duration": "20 min", "difficulty": "Beginner" if bmi >= 28 else "Intermediate", "burn_kcal": 180},
            {"name": "Bodyweight Squats", "duration": "3 sets x 15 reps", "difficulty": "Intermediate", "burn_kcal": 90},
            {"name": "Mountain Climbers", "duration": "3 sets x 30 sec", "difficulty": "Intermediate", "burn_kcal": 80},
            {"name": "Core Plank", "duration": "3 sets x 45 sec", "difficulty": "Intermediate", "burn_kcal": 60},
        ]
    elif "lower" in text:
        exercises = [
            {"name": "Squats", "duration": "4 sets x 12 reps", "difficulty": "Intermediate", "burn_kcal": 140},
            {"name": "Reverse Lunges", "duration": "3 sets x 10 reps", "difficulty": "Intermediate", "burn_kcal": 120},
            {"name": "Glute Bridge", "duration": "3 sets x 15 reps", "difficulty": "Beginner", "burn_kcal": 70},
            {"name": "Calf Raises", "duration": "3 sets x 20 reps", "difficulty": "Beginner", "burn_kcal": 50},
        ]
    elif "upper" in text or "push" in text or "pull" in text:
        exercises = [
            {"name": "Push Ups", "duration": "3 sets x 10 reps", "difficulty": "Intermediate", "burn_kcal": 90},
            {"name": "Backpack Rows", "duration": "3 sets x 12 reps", "difficulty": "Intermediate", "burn_kcal": 85},
            {"name": "Pike Push Ups", "duration": "3 sets x 8 reps", "difficulty": "Advanced", "burn_kcal": 75},
            {"name": "Dead Bug Core", "duration": "3 sets x 12 reps", "difficulty": "Beginner", "burn_kcal": 45},
        ]
    else:
        exercises = [
            {"name": "Push Ups", "duration": "3 sets x 10 reps", "difficulty": "Intermediate", "burn_kcal": 90},
            {"name": "Squats", "duration": "3 sets x 15 reps", "difficulty": "Intermediate", "burn_kcal": 110},
            {"name": "Plank", "duration": "3 sets x 45 sec", "difficulty": "Intermediate", "burn_kcal": 60},
        ]

    if context["user"]["activity_level"] in ["sedentary", "lightly_active"]:
        for exercise in exercises:
            if exercise["difficulty"] == "Advanced":
                exercise["difficulty"] = "Intermediate"
        exercises.append({"name": "Cool-down Walk", "duration": "8 min", "difficulty": "Beginner", "burn_kcal": 35})

    return exercises


def workout_recommendation(context):
    day_key = weekday_key()
    routine = context["workout_plan"].get(day_key, context["workout_plan"]["monday"])
    exercises = exercise_library(routine, context)
    completed_count = sum(1 for row in context["progress_history"] if row.get("workout_completed"))
    total_days = len(context["progress_history"])
    consistency = round((completed_count / total_days) * 100) if total_days else 0

    return {
        "type": "daily_workout_plan",
        "personalization": profile_summary(context),
        "plan_name": context["workout_plan"]["name"],
        "plan_description": context["workout_plan"]["desc"],
        "today": {
            "day": day_key.title(),
            "routine": routine,
            "estimated_burn_kcal": sum(item["burn_kcal"] for item in exercises),
            "exercises": exercises,
        },
        "workout_history": {
            "days_tracked": total_days,
            "completed_days": completed_count,
            "consistency_percent": consistency,
            "current_streak": current_streak(context["progress_history"]),
        },
        "recommendations": [
            "Complete the full routine to count the workout toward your streak.",
            "Keep intensity conversational if sleep or water is below target.",
            "Increase reps only after two clean completions of the same routine.",
        ],
    }


def weekly_recommendation(context):
    score = calculate_health_score(context)
    forecast = weight_forecast(context)
    return {
        "type": "weekly_health_recommendations",
        "personalization": profile_summary(context),
        "weekly_plan": context["weekly_plan"],
        "health_score": score,
        "weight_forecast": {
            "7_days": forecast["predicted_weight"]["7"],
            "30_days": forecast["predicted_weight"]["30"],
            "90_days": forecast["predicted_weight"]["90"],
        },
        "recommendations": [
            f"Keep calories near {context['core']['daily_calories']} kcal on at least 5 days this week.",
            f"Average {context['core']['protein_g']}g protein daily to support your {context['user']['goal']} goal.",
            f"Maintain {context['core']['hydration_ml']}ml water and {context['core']['sleep_hours']} hours sleep targets.",
            f"Current streak is {current_streak(context['progress_history'])} days; protect it with a lighter workout on low-energy days.",
        ],
        "warnings": [item["message"] for item in notifications(context)["items"] if item["type"] == "warning"],
        "motivation": motivation_message(context),
    }


def motivation_message(context):
    score = calculate_health_score(context)
    streak = current_streak(context["progress_history"])
    name = context["user"]["user_name"]
    if streak >= 7:
        return f"{name}, your {streak}-day streak shows real consistency. Keep the next action small and repeatable."
    if score["score"] >= 75:
        return f"{name}, today's foundation is solid. One more logged habit can push the score higher."
    return f"{name}, start with water or protein now. Small logged actions move the whole day in the right direction."


def coach_reply(context, message):
    core = context["core"]
    score = calculate_health_score(context)
    nutrients = nutrient_analysis(context)
    actions = action_center(context)["actions"]
    user = context["user"]
    lower = message.lower()
    hostel_enabled = bool(user.get("uses_hostel"))

    if hostel_enabled and any(word in lower for word in ["mess", "hostel", "today", "eat"]):
        mess_quality = hostel_mess_quality(context)
        gap = protein_gap_summary(context)
        foods = ", ".join(item["food"] for item in gap["budget_foods"][:3])
        menu_note = (
            f"Today's mess estimate is {round(mess_quality['totals']['calories'])} kcal and "
            f"{round(mess_quality['totals']['protein_g'], 1)}g protein."
        ) if mess_quality["score"] else "Today's mess menu is not logged yet."
        return (
            f"{menu_note} Your goal is {user['goal']} with a {core['daily_calories']} kcal target and "
            f"{core['protein_g']}g protein target. Remaining protein is {gap['remaining_protein_g']}g. "
            f"Best budget-fit add-ons: {foods}. Avoid foods you dislike: {user.get('disliked_foods') or 'none logged'}."
        )

    if hostel_enabled and ("budget" in lower or "₹" in lower or "rs" in lower or "rupee" in lower):
        budget = float(user.get("budget") or 0)
        foods = budget_food_suggestions(user, 5)
        ranked = ", ".join(f"{item['food']} ({item['protein_per_rupee']}g/Rs)" for item in foods[:4])
        return (
            f"Your monthly food budget is {round(budget)}. Daily working budget is about "
            f"{round(budget / 30) if budget else 0}. Best protein-per-rupee options: {ranked}. "
            "Use these around the mess menu instead of replacing the whole meal."
        )

    if "water" in lower:
        return (
            f"Your water target is {core['hydration_ml']}ml today. "
            f"You have logged {nutrients['water']['actual']}ml, so {nutrients['water']['needed']}ml is still pending. "
            "Drink 500ml now, then split the rest across the day."
        )
    if "protein" in lower:
        foods = ", ".join(item["food"] for item in budget_food_suggestions(user, 3)) if hostel_enabled else ", ".join(nutrients["protein"]["foods"][:3])
        return (
            f"You need {core['protein_g']}g protein today. "
            f"Logged protein is {nutrients['protein']['actual']}g, leaving {nutrients['protein']['needed']}g. "
            f"Best fit from your diet type: {foods}."
        )
    if "weight" in lower or "forecast" in lower:
        forecast = weight_forecast(context)
        return (
            f"Current weight is {forecast['current_weight']}kg. "
            f"At your {core['daily_calories']} kcal target, the 30-day forecast is "
            f"{forecast['predicted_weight']['30']}kg and the goal weight is {forecast['goal_weight']}kg."
        )

    first_action = actions[0]["action"] if actions else "Stay consistent with today's plan"
    return (
        f"Your health score is {score['score']} ({score['label']}). "
        f"Right now: {first_action}. "
        f"Calories target is {core['daily_calories']} kcal, protein target is {core['protein_g']}g, "
        f"and water target is {core['hydration_ml']}ml."
    )
