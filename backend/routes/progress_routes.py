from flask import Blueprint, request, jsonify
from config.db import get_db_connection
from datetime import date, datetime, timedelta

progress_routes = Blueprint('progress', __name__)

@progress_routes.route('/mark-complete', methods=['POST'])
def mark_complete():
    data = request.json
    user_id = data.get('user_id')
    task_type = data.get('task_type') # 'diet' or 'workout'
    
    if not user_id or not task_type:
        return jsonify({"error": "Missing data"}), 400
        
    today = date.today().isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
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

@progress_routes.route('/status/<int:user_id>', methods=['GET'])
def get_progress_status(user_id):
    today = date.today().isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
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
