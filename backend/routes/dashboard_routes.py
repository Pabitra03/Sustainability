from flask import Blueprint, request, jsonify
from config.db import get_db_connection
from models.recommender import recommender
from utils.plans import get_diet_plan_details, get_workout_plan_details, get_weekly_plan
from datetime import datetime

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/', methods=['GET'])
def get_dashboard():
    user_id = request.args.get('user_id')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
        
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT p.*, u.name as user_name FROM profiles p JOIN users u ON p.user_id = u.id WHERE p.user_id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({"error": "Profile not found"}), 404
            
        # Nutritional Rule-Based Logic
        weight_kg = float(user['weight'])
        height_cm = float(user['height'])
        age = int(user['age'])
        
        # Calculate BMI
        height_m = height_cm / 100
        bmi = round(weight_kg / (height_m ** 2), 1)
        
        # Calculate BMR (Mifflin-St Jeor)
        if user['gender'] == 'male':
            bmr = round(10 * weight_kg + 6.25 * height_cm - 5 * age + 5)
        else:
            bmr = round(10 * weight_kg + 6.25 * height_cm - 5 * age - 161)
            
        # Activity Multiplier
        activity_multipliers = {
            'sedentary': 1.2,
            'lightly_active': 1.375,
            'moderately_active': 1.55,
            'very_active': 1.725,
            'super_active': 1.9
        }
        
        tdee = round(bmr * activity_multipliers.get(user['activity_level'], 1.2))
        
        # Goal adjustments
        if user['goal'] == 'loss':
            daily_calories = tdee - 500
        elif user['goal'] == 'gain':
            daily_calories = tdee + 500
        else:
            daily_calories = tdee

        # Machine Learning Predictions
        diet_plan_id, workout_plan_id = recommender.predict(
            age=age,
            weight=weight_kg,
            height=height_cm,
            activity_level_str=user['activity_level'],
            goal_str=user['goal']
        )
                 
        diet_plan = get_diet_plan_details(diet_plan_id, user.get('diet_type', 'non_vegetarian'))
        workout_plan = get_workout_plan_details(workout_plan_id)
        weekly_plan = get_weekly_plan(diet_plan_id, workout_plan_id, user.get('diet_type', 'non_vegetarian'))
        
        # Hydration logic
        hydration = round((weight_kg * 0.033) * 1000) # ml
        
        response_data = {
            "name": user['user_name'],
            "today_date": datetime.now().strftime("%A, %B %d"),
            "active_days": 0, # Initial value before fetchProgressStatus updates it
            "metrics": {
                "bmi": bmi,
                "bmr": bmr,
                "tdee": tdee,
                "daily_calories": daily_calories,
                "hydration_ml": hydration,
                "goal": user['goal']
            },
            "diet": diet_plan,
            "workout": workout_plan,
            "weekly_plan": weekly_plan
        }
        return jsonify(response_data), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()
