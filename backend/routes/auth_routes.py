from flask import Blueprint, request, jsonify
import bcrypt
import pymysql
from config.db import get_db_connection
from utils.schema import ensure_app_schema

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    
    if not name or not email or not password:
        return jsonify({"error": "Missing required fields"}), 400
        
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
        
    cursor = conn.cursor()
    try:
        ensure_app_schema(conn)
        cursor.execute("INSERT INTO users (name, email, password) VALUES (%s, %s, %s)", (name, email, hashed_password))
        conn.commit()
        user_id = cursor.lastrowid
        return jsonify({"message": "Registration successful", "user_id": user_id, "name": name}), 201
    except pymysql.Error as err:
        if err.args[0] == 1062:
            return jsonify({"error": "Email already exists"}), 400
        return jsonify({"error": str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
        
    cursor = conn.cursor()
    try:
        ensure_app_schema(conn)
        cursor.execute("SELECT id, name, password FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        
        if user and bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
            cursor.execute("SELECT user_id FROM profiles WHERE user_id = %s", (user['id'],))
            profile = cursor.fetchone()
            return jsonify({
                "message": "Login successful", 
                "user_id": user['id'], 
                "name": user['name'],
                "has_profile": profile is not None
            }), 200
        else:
            return jsonify({"error": "Invalid email or password"}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()
