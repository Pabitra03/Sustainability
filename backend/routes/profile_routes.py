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


def clean_text(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def clean_number(value, field_name, required=False):
    if value in [None, ""]:
        if required:
            raise ValueError(f"{field_name} is required")
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a number")


def clean_int(value, field_name, required=False):
    number = clean_number(value, field_name, required)
    return int(number) if number is not None else None


def clean_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ["1", "true", "yes", "on"]
    return False


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

        cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        if not user:
            return jsonify({"error": "User not found"}), 404
        return jsonify({"error": "Profile not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@profile_bp.route('/profile', methods=['POST'])
def save_profile():
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400
        
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
        
    cursor = conn.cursor()
    try:
        ensure_app_schema(conn)
        cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
        if not cursor.fetchone():
            return jsonify({"error": "User not found. Please sign in again."}), 404

        age = clean_int(data.get('age'), 'Age', required=True)
        weight = clean_number(data.get('weight'), 'Weight', required=True)
        height = clean_number(data.get('height'), 'Height', required=True)
        if age <= 0 or weight <= 0 or height <= 0:
            return jsonify({"error": "Age, weight, and height must be greater than zero"}), 400

        uses_hostel = clean_bool(data.get('uses_hostel'))
        hostel_name = clean_text(data.get('hostel_name')) if uses_hostel else None
        hostel_type = clean_text(data.get('hostel_type')) if uses_hostel else None
        mess_type = clean_text(data.get('mess_type')) if uses_hostel else None

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
            user_id, age, clean_text(data.get('gender')) or 'male', weight,
            height, clean_text(data.get('activity_level')) or 'sedentary',
            clean_text(data.get('goal')) or 'maintain',
            clean_text(data.get('diet_type')) or 'non_vegetarian',
            clean_text(data.get('favorite_foods')), clean_text(data.get('disliked_foods')),
            clean_text(data.get('food_allergies')), clean_number(data.get('budget'), 'Budget'),
            hostel_name, hostel_type, mess_type, uses_hostel,
            clean_number(data.get('goal_weight_kg'), 'Goal weight')
        ))
        conn.commit()
        return jsonify({"message": "Profile saved successfully", "uses_hostel": uses_hostel}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()
