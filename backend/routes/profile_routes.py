from flask import Blueprint, request, jsonify
from config.db import get_db_connection
from utils.schema import ensure_app_schema

profile_bp = Blueprint('profile', __name__)

PROFILE_MEMORY_FIELDS = [
    'favorite_foods',
    'disliked_foods',
    'food_allergies',
    'budget',
    'hostel_name',
    'hostel_type',
    'mess_type',
    'uses_hostel',
    'goal_weight_kg',
]

@profile_bp.route('/profile', methods=['GET'])
def get_profile():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400
        
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
        
    cursor = conn.cursor()
    try:
        ensure_app_schema(conn)
        cursor.execute("SELECT * FROM profiles WHERE user_id = %s", (user_id,))
        profile = cursor.fetchone()
        if profile:
            return jsonify(profile), 200
        else:
            return jsonify({"error": "Profile not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@profile_bp.route('/profile', methods=['POST'])
def save_profile():
    data = request.json
    user_id = data.get('user_id')
    
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400
        
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
        
    cursor = conn.cursor()
    try:
        ensure_app_schema(conn)
        uses_hostel = bool(data.get('uses_hostel'))
        hostel_name = data.get('hostel_name') if uses_hostel else None
        hostel_type = data.get('hostel_type') if uses_hostel else None
        mess_type = data.get('mess_type') if uses_hostel else None

        cursor.execute("""
            INSERT INTO profiles (
                user_id, age, gender, weight, height, activity_level, goal, diet_type,
                favorite_foods, disliked_foods, food_allergies, budget,
                hostel_name, hostel_type, mess_type, uses_hostel, goal_weight_kg
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            age=VALUES(age), gender=VALUES(gender), weight=VALUES(weight),
            height=VALUES(height), activity_level=VALUES(activity_level), goal=VALUES(goal),
            diet_type=VALUES(diet_type), favorite_foods=VALUES(favorite_foods),
            disliked_foods=VALUES(disliked_foods), food_allergies=VALUES(food_allergies),
            budget=VALUES(budget), hostel_name=VALUES(hostel_name),
            hostel_type=VALUES(hostel_type), mess_type=VALUES(mess_type),
            uses_hostel=VALUES(uses_hostel), goal_weight_kg=VALUES(goal_weight_kg)
        """, (
            user_id, data.get('age'), data.get('gender'), data.get('weight'), 
            data.get('height'), data.get('activity_level'), data.get('goal'),
            data.get('diet_type'), data.get('favorite_foods'), data.get('disliked_foods'),
            data.get('food_allergies'), data.get('budget') or None, hostel_name,
            hostel_type, mess_type, uses_hostel, data.get('goal_weight_kg') or None
        ))
        conn.commit()
        return jsonify({"message": "Profile saved successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()
