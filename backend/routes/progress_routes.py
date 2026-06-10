from flask import Blueprint, request, jsonify
from config.db import get_db_connection
from datetime import date, datetime, timedelta
from utils.coach_engine import (
    calculate_health_score,
    fetch_user_context,
    hostel_mess_quality,
    logged_weight_points,
    recommended_goal_weight,
    score_ratio,
    trend_from_points,
    weight_forecast,
)
from utils.schema import ensure_app_schema

progress_routes = Blueprint('progress', __name__)


def parse_entry_date(value):
    if not value:
        return date.today().isoformat()
    return value


def date_key(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def day_range(days):
    start = date.today() - timedelta(days=days - 1)
    return [(start + timedelta(days=i)).isoformat() for i in range(days)]


def day_range_between(start, end):
    if isinstance(start, datetime):
        start = start.date()
    if isinstance(end, datetime):
        end = end.date()
    if isinstance(start, str):
        start = datetime.strptime(start, "%Y-%m-%d").date()
    if isinstance(end, str):
        end = datetime.strptime(end, "%Y-%m-%d").date()
    total = (end - start).days + 1
    return [(start + timedelta(days=i)).isoformat() for i in range(max(1, total))]


def metric_value(row, field):
    if not row:
        return None
    value = row.get(field)
    return value if value is not None else None


def numeric_values(values):
    return [float(value) for value in values if value is not None]


def average(values):
    numbers = numeric_values(values)
    return round(sum(numbers) / len(numbers), 1) if numbers else None


def sum_values(values):
    numbers = numeric_values(values)
    return round(sum(numbers), 1) if numbers else 0


def percent(numerator, denominator):
    return round((numerator / denominator) * 100) if denominator else 0


def last_value(values):
    return next((value for value in reversed(values) if value is not None), None)


def first_value(values):
    return next((value for value in values if value is not None), None)


def moving_average(values, window):
    result = []
    for index in range(len(values)):
        subset = numeric_values(values[max(0, index - window + 1):index + 1])
        result.append(round(sum(subset) / len(subset), 1) if subset else None)
    return result


def stddev(values):
    numbers = numeric_values(values)
    if len(numbers) < 2:
        return 0
    avg = sum(numbers) / len(numbers)
    return (sum((value - avg) ** 2 for value in numbers) / len(numbers)) ** 0.5


def goal_progress(start_weight, current_weight, goal_weight, goal):
    if start_weight is None or current_weight is None or goal_weight is None:
        return 0
    total = abs(float(start_weight) - float(goal_weight))
    if total == 0:
        return 100
    if goal == "loss":
        moved = float(start_weight) - float(current_weight)
    elif goal == "gain":
        moved = float(current_weight) - float(start_weight)
    else:
        moved = total
    return max(0, min(100, round((moved / total) * 100)))


def regression_series(labels, points):
    trend = trend_from_points(points)
    if len(points) < 2:
        return [None for _ in labels]
    base_day = points[0][0]
    base_value = points[0][1]
    return [
        round(base_value + trend["daily_slope"] * ((datetime.strptime(label, "%Y-%m-%d").date() - base_day).days), 1)
        for label in labels
    ]


def linear_metric_prediction(values, days):
    points = [(index, float(value)) for index, value in enumerate(values) if value is not None]
    if len(points) < 3:
        return {"value": last_value(values), "confidence": 0}
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    variance = sum((x - x_mean) ** 2 for x in xs)
    if variance == 0:
        return {"value": last_value(values), "confidence": 0}
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / variance
    intercept = y_mean - slope * x_mean
    ss_total = sum((y - y_mean) ** 2 for y in ys)
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - (ss_res / ss_total) if ss_total else 0
    confidence = min(95, round(max(0, r2) * 60 + min(len(points), 14) / 14 * 35))
    projected = intercept + slope * (len(values) - 1 + days)
    return {"value": round(max(0, min(100, projected))), "confidence": confidence}


def trend_indicator(values, lower_is_better=False, suffix=""):
    numbers = numeric_values(values)
    if len(numbers) < 2:
        return {"direction": "flat", "label": "Not enough data", "delta": None}
    recent = average(numbers[-7:])
    previous = average(numbers[-14:-7]) if len(numbers) >= 14 else average(numbers[:-7])
    if previous is None:
        return {"direction": "flat", "label": "Not enough data", "delta": None}
    delta = round(recent - previous, 1)
    improved = delta < 0 if lower_is_better else delta > 0
    direction = "up" if delta > 0 else "down" if delta < 0 else "flat"
    label = "Improving" if improved else "Declining" if delta != 0 else "Stable"
    return {"direction": direction, "label": label, "delta": f"{delta:+g}{suffix}"}


def calculate_day_score(core, metrics, progress):
    metrics = metrics or {}
    progress = progress or {}
    calories_actual = metrics.get("calories")
    protein_actual = metrics.get("protein_g")
    if progress.get("diet_completed"):
        calories_actual = calories_actual if calories_actual is not None else core["daily_calories"]
        protein_actual = protein_actual if protein_actual is not None else core["protein_g"]

    components = {
        "calories": {"weight": 25, "score": score_ratio(calories_actual, core["daily_calories"])},
        "protein": {"weight": 25, "score": score_ratio(protein_actual, core["protein_g"])},
        "workout": {"weight": 20, "score": 100 if progress.get("workout_completed") else 0},
        "water": {"weight": 15, "score": score_ratio(metrics.get("water_ml"), core["hydration_ml"])},
        "sleep": {"weight": 15, "score": score_ratio(metrics.get("sleep_hours"), core["sleep_hours"])},
    }
    return round(sum((item["score"] * item["weight"]) / 100 for item in components.values()))


def report_summary(labels, metric_rows, progress_rows, core):
    metric_lookup = {date_key(row["entry_date"]): row for row in metric_rows}
    progress_lookup = {date_key(row["entry_date"]): row for row in progress_rows}
    tracked_days = len([label for label in labels if label in metric_lookup or label in progress_lookup])
    workout_days = sum(1 for label in labels if (progress_lookup.get(label) or {}).get("workout_completed"))
    diet_days = sum(1 for label in labels if (progress_lookup.get(label) or {}).get("diet_completed"))
    calories = [metric_lookup[label].get("calories") for label in labels if label in metric_lookup and metric_lookup[label].get("calories") is not None]
    protein = [metric_lookup[label].get("protein_g") for label in labels if label in metric_lookup and metric_lookup[label].get("protein_g") is not None]
    water = [metric_lookup[label].get("water_ml") for label in labels if label in metric_lookup and metric_lookup[label].get("water_ml") is not None]
    sleep = [metric_lookup[label].get("sleep_hours") for label in labels if label in metric_lookup and metric_lookup[label].get("sleep_hours") is not None]

    def avg(values):
        return round(sum(values) / len(values), 1) if values else None

    return {
        "tracked_days": tracked_days,
        "workout_completion_percent": round((workout_days / len(labels)) * 100) if labels else 0,
        "diet_completion_percent": round((diet_days / len(labels)) * 100) if labels else 0,
        "avg_calories": avg(calories),
        "avg_protein_g": avg(protein),
        "avg_water_ml": avg(water),
        "avg_sleep_hours": avg(sleep),
        "targets": {
            "calories": core["daily_calories"],
            "protein_g": core["protein_g"],
            "water_ml": core["hydration_ml"],
            "sleep_hours": core["sleep_hours"],
        },
    }

@progress_routes.route('/mark-complete', methods=['POST'])
def mark_complete():
    data = request.json
    user_id = data.get('user_id')
    task_type = data.get('task_type') # 'diet' or 'workout'
    
    if not user_id or not task_type:
        return jsonify({"error": "Missing data"}), 400
        
    today = date.today().isoformat()
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    cursor = conn.cursor()
    
    try:
        ensure_app_schema(conn)
        # Check if record exists for today
        cursor.execute("SELECT * FROM user_progress WHERE user_id = %s AND entry_date = %s", (user_id, today))
        progress = cursor.fetchone()
        
        if not progress:
            # Create new record
            if task_type == 'diet':
                cursor.execute("INSERT INTO user_progress (user_id, entry_date, diet_completed) VALUES (%s, %s, %s)", (user_id, today, True))
            else:
                cursor.execute("INSERT INTO user_progress (user_id, entry_date, workout_completed) VALUES (%s, %s, %s)", (user_id, today, True))
        else:
            # Update existing record
            field = 'diet_completed' if task_type == 'diet' else 'workout_completed'
            cursor.execute(f"UPDATE user_progress SET {field} = %s WHERE user_id = %s AND entry_date = %s", (True, user_id, today))
            
        # Re-fetch for status check
        cursor.execute("SELECT diet_completed, workout_completed FROM user_progress WHERE user_id = %s AND entry_date = %s", (user_id, today))
        updated = cursor.fetchone()
        
        is_fully_done = updated['diet_completed'] and updated['workout_completed']
        
        conn.commit()
        return jsonify({
            "message": f"{task_type.capitalize()} marked as complete!",
            "fully_completed": is_fully_done
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@progress_routes.route('/metrics', methods=['POST'])
def save_daily_metrics():
    data = request.json or {}
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400

    fields = {
        "weight_kg": data.get("weight_kg"),
        "calories": data.get("calories"),
        "protein_g": data.get("protein_g"),
        "fiber_g": data.get("fiber_g"),
        "water_ml": data.get("water_ml"),
        "sleep_hours": data.get("sleep_hours"),
        "steps": data.get("steps"),
    }
    fields = {key: value for key, value in fields.items() if value not in [None, ""]}
    if not fields:
        return jsonify({"error": "At least one metric is required"}), 400

    mode = data.get("mode", "set")
    entry_date = parse_entry_date(data.get("entry_date"))
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    cursor = conn.cursor()

    try:
        ensure_app_schema(conn)
        columns = ["user_id", "entry_date"] + list(fields.keys())
        values = [user_id, entry_date] + list(fields.values())
        placeholders = ", ".join(["%s"] * len(columns))
        if mode == "add":
            updates = ", ".join(
                f"{field}=COALESCE({field}, 0) + VALUES({field})" for field in fields.keys()
            )
        else:
            updates = ", ".join(f"{field}=VALUES({field})" for field in fields.keys())
        cursor.execute(
            f"INSERT INTO user_daily_metrics ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON DUPLICATE KEY UPDATE {updates}",
            values,
        )
        conn.commit()

        cursor.execute(
            "SELECT * FROM user_daily_metrics WHERE user_id = %s AND entry_date = %s",
            (user_id, entry_date),
        )
        metrics = cursor.fetchone()
        return jsonify({"message": "Metrics saved", "metrics": metrics}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@progress_routes.route('/status/<int:user_id>', methods=['GET'])
def get_progress_status(user_id):
    today = date.today().isoformat()
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    cursor = conn.cursor()
    
    try:
        ensure_app_schema(conn)
        # Get today's status
        cursor.execute("SELECT diet_completed, workout_completed FROM user_progress WHERE user_id = %s AND entry_date = %s", (user_id, today))
        status = cursor.fetchone() or {"diet_completed": False, "workout_completed": False}
        
        # Get user info
        cursor.execute("SELECT created_at FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        # Calculate days active
        days_active = 1
        if user and user['created_at']:
            # Adjust if created_at is string or datetime
            created_dt = user['created_at']
            if isinstance(created_dt, str):
                created_dt = datetime.fromisoformat(created_dt.replace('Z', '+00:00'))
            diff = datetime.now() - created_dt
            days_active = diff.days + 1

        # Check yesterday's status
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        cursor.execute("SELECT diet_completed, workout_completed FROM user_progress WHERE user_id = %s AND entry_date = %s", (user_id, yesterday))
        yesterday_status = cursor.fetchone()
        
        # If no record exists for yesterday, we treat it as incomplete ONLY if they had the account then
        yesterday_completed = False
        if yesterday_status:
            yesterday_completed = bool(yesterday_status['diet_completed']) and bool(yesterday_status['workout_completed'])
        else:
            # If no record, check if they were already a user yesterday
            if user and user['created_at'] and user['created_at'] < datetime.combine(date.today(), datetime.min.time()):
                yesterday_completed = False # Missed it
            else:
                yesterday_completed = True # New user, don't warn
            
        # Calculate streak
        cursor.execute("SELECT entry_date, diet_completed, workout_completed FROM user_progress WHERE user_id = %s ORDER BY entry_date DESC", (user_id,))
        progress_history = cursor.fetchall()
        
        streak = 0
        current_date = date.today()
        check_date = current_date - timedelta(days=1)
        
        # Check today first
        for p in progress_history:
            # Handle both string and date objects
            p_date = p['entry_date']
            if isinstance(p_date, str):
                p_date = datetime.strptime(p_date, "%Y-%m-%d").date()
                
            if p_date == current_date:
                if p['diet_completed'] and p['workout_completed']:
                    streak += 1
                break
                
        # Now count backwards from yesterday
        for p in progress_history:
            p_date = p['entry_date']
            if isinstance(p_date, str):
                p_date = datetime.strptime(p_date, "%Y-%m-%d").date()
                
            if p_date > check_date:
                continue
            if p_date == check_date:
                if p['diet_completed'] and p['workout_completed']:
                    streak += 1
                    check_date -= timedelta(days=1)
                else:
                    break
            else:
                break
            
        return jsonify({
            "diet_completed": bool(status['diet_completed']),
            "workout_completed": bool(status['workout_completed']),
            "yesterday_completed": yesterday_completed,
            "days_planned": 30, # Target
            "days_active": days_active,
            "streak": streak
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@progress_routes.route('/analytics', methods=['GET'])
def analytics():
    user_id = request.args.get('user_id')
    period = request.args.get('period') or request.args.get('days', 30)
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

        if str(period).lower() == "all":
            cursor.execute("""
                SELECT MIN(entry_date) AS first_date
                FROM (
                    SELECT entry_date FROM user_daily_metrics WHERE user_id = %s
                    UNION ALL
                    SELECT entry_date FROM user_progress WHERE user_id = %s
                ) tracked
            """, (user_id, user_id))
            first = cursor.fetchone()
            start_date = first.get("first_date") if first and first.get("first_date") else context["user"].get("created_at")
            if isinstance(start_date, datetime):
                start_date = start_date.date()
            labels = day_range_between(start_date or date.today(), date.today())
            days = len(labels)
        else:
            try:
                days = int(period)
            except (TypeError, ValueError):
                return jsonify({"error": "Invalid analytics period"}), 400
            days = max(7, min(days, 180))
            labels = day_range(days)

        start = labels[0]
        cursor.execute("""
            SELECT entry_date, weight_kg, calories, protein_g, fiber_g, water_ml, sleep_hours, steps
            FROM user_daily_metrics
            WHERE user_id = %s AND entry_date >= %s
            ORDER BY entry_date ASC
        """, (user_id, start))
        metric_rows = cursor.fetchall()

        cursor.execute("""
            SELECT entry_date, diet_completed, workout_completed
            FROM user_progress
            WHERE user_id = %s AND entry_date >= %s
            ORDER BY entry_date ASC
        """, (user_id, start))
        progress_rows = cursor.fetchall()
        hostel_rows = []
        if context["user"].get("uses_hostel"):
            cursor.execute("""
                SELECT entry_date, SUM(calories) AS calories, SUM(protein_g) AS protein_g
                FROM hostel_consumption
                WHERE user_id = %s AND entry_date >= %s
                GROUP BY entry_date
                ORDER BY entry_date ASC
            """, (user_id, start))
            hostel_rows = cursor.fetchall()
        cursor.close()

        metric_lookup = {date_key(row["entry_date"]): row for row in metric_rows}
        progress_lookup = {date_key(row["entry_date"]): row for row in progress_rows}
        core = context["core"]
        user = context["user"]
        profile_weight = float(user["weight"])
        goal_weight = recommended_goal_weight(user)

        weight_values = []
        for label in labels:
            row = metric_lookup.get(label)
            if row and row.get("weight_kg") is not None:
                weight_values.append(float(row["weight_kg"]))
            else:
                weight_values.append(None)
        current_weight = last_value(weight_values) or profile_weight

        health_scores = [
            calculate_day_score(core, metric_lookup.get(label), progress_lookup.get(label))
            for label in labels
        ]

        calories = [metric_value(metric_lookup.get(label), "calories") for label in labels]
        protein = [metric_value(metric_lookup.get(label), "protein_g") for label in labels]
        water = [metric_value(metric_lookup.get(label), "water_ml") for label in labels]
        sleep = [metric_value(metric_lookup.get(label), "sleep_hours") for label in labels]
        workouts = [1 if (progress_lookup.get(label) or {}).get("workout_completed") else 0 for label in labels]
        diet = [1 if (progress_lookup.get(label) or {}).get("diet_completed") else 0 for label in labels]
        tracked_mask = [label in metric_lookup or label in progress_lookup for label in labels]
        hostel_lookup = {date_key(row["entry_date"]): row for row in hostel_rows}
        hostel_calories = [metric_value(hostel_lookup.get(label), "calories") for label in labels]
        hostel_protein = [metric_value(hostel_lookup.get(label), "protein_g") for label in labels]
        monthly_budget = float(user.get("budget") or 0)
        budget_daily = round(monthly_budget / 30, 1) if monthly_budget else 0
        budget_consumption = [budget_daily if (hostel_lookup.get(label) or metric_lookup.get(label)) else None for label in labels]
        mess_quality = hostel_mess_quality(context) if user.get("uses_hostel") else {"score": None, "label": None}
        tracked_days = sum(1 for item in tracked_mask if item)
        calorie_avg_7 = moving_average(calories, 7)
        calorie_avg_30 = moving_average(calories, 30)
        protein_avg = average(protein)
        water_avg = average(water)
        sleep_avg = average(sleep)
        weekly_workouts = workouts[-7:]
        monthly_workouts = workouts[-30:]
        weekly_performance = percent(sum(weekly_workouts), len(weekly_workouts))
        monthly_performance = percent(sum(monthly_workouts), len(monthly_workouts))
        weight_points = logged_weight_points({**context, "metrics_history": metric_rows})
        weight_prediction_line = regression_series(labels, weight_points)
        forecast_data = weight_forecast({**context, "metrics_history": metric_rows})
        first_weight = first_value(weight_values) or profile_weight
        weight_rate = forecast_data.get("weight_loss_rate_kg_per_week", 0)
        sleep_consistency = max(0, min(100, round(100 - (stddev(sleep) / max(core["sleep_hours"], 1) * 100))))
        sleep_deficiency = max(0, round(core["sleep_hours"] - sleep_avg, 1)) if sleep_avg is not None else None

        over_target = sum(1 for value in calories if value is not None and value > core["daily_calories"])
        under_target = sum(1 for value in calories if value is not None and value <= core["daily_calories"])

        radar = {
            "labels": ["Protein", "Calories", "Water", "Sleep", "Workout"],
            "scores": [
                score_ratio(protein_avg, core["protein_g"]),
                score_ratio(average(calories), core["daily_calories"]),
                score_ratio(water_avg, core["hydration_ml"]),
                score_ratio(sleep_avg, core["sleep_hours"]),
                percent(sum(workouts), len(workouts)),
            ],
        }

        goal_rings = [
            {
                "key": "weight",
                "label": "Weight Goal",
                "percent": goal_progress(first_weight, current_weight, goal_weight, user["goal"]),
                "value": f"{round(current_weight, 1)} / {goal_weight} kg",
            },
            {
                "key": "workout",
                "label": "Workout Goal",
                "percent": percent(sum(workouts), len(workouts)),
                "value": f"{sum(workouts)} / {len(workouts)} days",
            },
            {
                "key": "protein",
                "label": "Protein Goal",
                "percent": score_ratio(protein_avg, core["protein_g"]),
                "value": f"{protein_avg or 0} / {core['protein_g']} g avg",
            },
            {
                "key": "water",
                "label": "Water Goal",
                "percent": score_ratio(water_avg, core["hydration_ml"]),
                "value": f"{water_avg or 0} / {core['hydration_ml']} ml avg",
            },
        ]

        insights = []
        if protein_avg is not None:
            protein_early = average(protein[:max(1, len(protein) // 2)])
            protein_late = average(protein[max(1, len(protein) // 2):])
            if protein_early and protein_late:
                change = round(((protein_late - protein_early) / protein_early) * 100)
                direction = "improved" if change >= 0 else "decreased"
                insights.append(f"Your protein intake {direction} by {abs(change)}% in this range.")
            deficit = round(core["protein_g"] - protein_avg, 1)
            if deficit > 0:
                insights.append(f"Average protein is {deficit}g below target.")
            else:
                insights.append(f"Average protein is {abs(deficit)}g above target.")
        if tracked_days:
            if user["goal"] == "loss" and current_weight <= first_weight and forecast_data["goal_completion_date"]:
                insights.append("Weight loss trend is on track for the saved goal.")
            elif user["goal"] == "gain" and current_weight >= first_weight and forecast_data["goal_completion_date"]:
                insights.append("Weight gain trend is moving toward the saved goal.")
            elif len(weight_points) >= 2:
                insights.append("Weight trend needs attention based on logged entries.")
        if len(workouts) >= 14:
            previous = percent(sum(workouts[-14:-7]), len(workouts[-14:-7]))
            recent = percent(sum(workouts[-7:]), len(workouts[-7:]))
            direction = "increased" if recent >= previous else "decreased"
            insights.append(f"Workout consistency {direction} from {previous}% to {recent}%.")
        if sleep_avg is not None:
            if sleep_deficiency and sleep_deficiency > 0:
                insights.append(f"Sleep deficiency detected: average sleep is {sleep_deficiency}h under target.")
            if sleep_consistency < 70:
                insights.append("Sleep consistency is unstable across logged nights.")
        if not insights:
            insights.append("Log meals, water, sleep, workouts, and weight to unlock automatic analytics.")

        response = {
            "period_days": days,
            "period": str(period),
            "labels": labels,
            "current": {
                "weight_kg": round(current_weight, 1),
                "goal_weight_kg": goal_weight,
                "bmi": core["bmi"],
                "calories_target": core["daily_calories"],
                "protein_target_g": core["protein_g"],
                "water_target_ml": core["hydration_ml"],
                "sleep_target_hours": core["sleep_hours"],
                "health_score": calculate_health_score(context),
            },
            "series": {
                "weight": weight_values,
                "weight_prediction": weight_prediction_line,
                "weight_goal": [goal_weight for _ in labels],
                "calories": calories,
                "calorie_target": [core["daily_calories"] for _ in labels],
                "calorie_weekly_average": calorie_avg_7,
                "calorie_monthly_average": calorie_avg_30,
                "protein": protein,
                "protein_target": [core["protein_g"] for _ in labels],
                "water": water,
                "water_target": [core["hydration_ml"] for _ in labels],
                "water_weekly_average": moving_average(water, 7),
                "water_monthly_average": moving_average(water, 30),
                "sleep": sleep,
                "sleep_target": [core["sleep_hours"] for _ in labels],
                "sleep_weekly_average": moving_average(sleep, 7),
                "sleep_monthly_average": moving_average(sleep, 30),
                "workout_completion": workouts,
                "workout_missed": [0 if value else 1 for value in workouts],
                "diet_completion": diet,
                "health_score": health_scores,
                "hostel_calories": hostel_calories,
                "hostel_protein": hostel_protein,
                "budget_consumption": budget_consumption,
                "budget_target": [budget_daily for _ in labels],
            },
            "analytics": {
                "tracked_days": tracked_days,
                "weight_loss_rate_kg_per_week": weight_rate,
                "trend_indicators": {
                    "weight": trend_indicator(weight_values, lower_is_better=user["goal"] == "loss", suffix="kg"),
                    "calories": trend_indicator(calories, lower_is_better=user["goal"] == "loss", suffix=" kcal"),
                    "protein": trend_indicator(protein, suffix="g"),
                    "water": trend_indicator(water, suffix="ml"),
                    "sleep": trend_indicator(sleep, suffix="h"),
                    "health_score": trend_indicator(health_scores, suffix=" pts"),
                },
                "calories": {
                    "average": average(calories),
                    "weekly_average": average(calories[-7:]),
                    "monthly_average": average(calories[-30:]),
                    "days_over_target": over_target,
                    "days_under_target": under_target,
                },
                "protein": {
                    "target": core["protein_g"],
                    "average": protein_avg,
                    "deficit": max(0, round(core["protein_g"] - protein_avg, 1)) if protein_avg is not None else None,
                    "surplus": max(0, round(protein_avg - core["protein_g"], 1)) if protein_avg is not None else None,
                },
                "water": {
                    "achievement_percent": score_ratio(water_avg, core["hydration_ml"]),
                    "weekly_average": average(water[-7:]),
                    "monthly_average": average(water[-30:]),
                },
                "sleep": {
                    "deficiency_hours": sleep_deficiency,
                    "consistency_percent": sleep_consistency if sleep_avg is not None else None,
                    "weekly_average": average(sleep[-7:]),
                    "monthly_average": average(sleep[-30:]),
                },
                "workout": {
                    "completion_percent": percent(sum(workouts), len(workouts)),
                    "completed": sum(workouts),
                    "missed": len(workouts) - sum(workouts),
                    "weekly_performance": weekly_performance,
                    "monthly_performance": monthly_performance,
                },
                "health_score": {
                    "last_7_days": average(health_scores[-7:]),
                    "last_30_days": average(health_scores[-30:]),
                    "last_90_days": average(health_scores[-90:]),
                },
                "hostel": {
                    "mess_quality_score": mess_quality.get("score"),
                    "mess_quality_label": mess_quality.get("label"),
                    "avg_hostel_calories": average(hostel_calories),
                    "avg_hostel_protein_g": average(hostel_protein),
                    "monthly_budget": monthly_budget,
                    "daily_budget": budget_daily,
                    "budget_usage_percent": score_ratio(average(budget_consumption), budget_daily) if budget_daily else 0,
                },
                "radar": radar,
                "goal_rings": goal_rings,
                "insights": insights[:5],
            },
            "predictions": {
                "weight": {
                    "after_7_days": forecast_data["predicted_weight"]["7"],
                    "after_30_days": forecast_data["predicted_weight"]["30"],
                    "after_90_days": forecast_data["predicted_weight"]["90"],
                    "goal_completion_date": forecast_data["goal_completion_date"],
                    "confidence": forecast_data.get("confidence", 0),
                    "sample_size": forecast_data.get("sample_size", 0),
                },
                "health_score": {
                    "after_7_days": linear_metric_prediction(health_scores, 7),
                    "after_30_days": linear_metric_prediction(health_scores, 30),
                },
            },
            "reports": {
                "weekly": report_summary(labels[-7:], metric_rows, progress_rows, core),
                "monthly": report_summary(labels, metric_rows, progress_rows, core),
                "progress": {
                    "first_weight_kg": first_weight,
                    "current_weight_kg": current_weight,
                    "goal_weight_kg": goal_weight,
                    "bmi": core["bmi"],
                    "health_score_change": (
                        health_scores[-1] - next((v for v in health_scores if v is not None), health_scores[-1])
                    ),
                },
            },
        }
        return jsonify(response), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@progress_routes.route('/health-score', methods=['GET'])
def progress_health_score():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    try:
        context = fetch_user_context(conn, user_id)
        if not context:
            return jsonify({"error": "Profile not found"}), 404
        return jsonify(calculate_health_score(context)), 200
    finally:
        conn.close()


@progress_routes.route('/forecast', methods=['GET'])
def forecast():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    try:
        context = fetch_user_context(conn, user_id)
        if not context:
            return jsonify({"error": "Profile not found"}), 404
        forecast_data = weight_forecast(context)
        return jsonify({
            "current_weight": forecast_data["current_weight"],
            "goal_weight": forecast_data["goal_weight"],
            "predicted_weight": {
                "7": forecast_data["predicted_weight"]["7"],
                "30": forecast_data["predicted_weight"]["30"],
                "90": forecast_data["predicted_weight"]["90"],
            },
            "goal_completion_date": forecast_data["goal_completion_date"],
            "confidence": forecast_data.get("confidence", 0),
            "weight_loss_rate_kg_per_week": forecast_data.get("weight_loss_rate_kg_per_week", 0),
            "sample_size": forecast_data.get("sample_size", 0),
            "basis": forecast_data["basis"],
        }), 200
    finally:
        conn.close()
