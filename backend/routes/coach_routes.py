from flask import Blueprint, jsonify, request

from config.db import get_db_connection
from utils.coach_engine import (
    coach_reply,
    diet_recommendation,
    ensure_coach_tables,
    fetch_user_context,
    weekly_recommendation,
    workout_recommendation,
)
from utils.schema import ensure_app_schema

coach_bp = Blueprint("coach", __name__)
wellness_bp = Blueprint("wellness", __name__)


def save_message(conn, user_id, role, message):
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO coach_chat_messages (user_id, role, message) VALUES (%s, %s, %s)",
        (user_id, role, message),
    )
    conn.commit()
    cursor.close()


def build_chat_response(user_id, message):
    if not user_id or not message:
        return jsonify({"error": "User ID and message are required"}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        ensure_app_schema(conn)
        context = fetch_user_context(conn, user_id)
        if not context:
            return jsonify({"error": "Profile not found"}), 404

        reply = coach_reply(context, message)
        save_message(conn, user_id, "user", message)
        save_message(conn, user_id, "assistant", reply)

        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM coach_chat_messages WHERE user_id = %s AND id NOT IN ("
            "SELECT id FROM (SELECT id FROM coach_chat_messages WHERE user_id = %s "
            "ORDER BY created_at DESC, id DESC LIMIT 20) recent)",
            (user_id, user_id),
        )
        conn.commit()
        cursor.close()
        return jsonify({"reply": reply}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


def build_history_response(user_id):
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        ensure_coach_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role, message, created_at FROM coach_chat_messages WHERE user_id = %s "
            "ORDER BY created_at ASC, id ASC LIMIT 20",
            (user_id,),
        )
        messages = cursor.fetchall()
        cursor.close()
        return jsonify({"messages": messages}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@coach_bp.route("/chat", methods=["POST"])
def chat():
    data = request.json or {}
    return build_chat_response(data.get("user_id"), data.get("message", "").strip())


@coach_bp.route("/history", methods=["GET"])
def history():
    return build_history_response(request.args.get("user_id"))


def recommendation_response(user_id, builder):
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        ensure_app_schema(conn)
        context = fetch_user_context(conn, user_id)
        if not context:
            return jsonify({"error": "Profile not found"}), 404
        return jsonify(builder(context)), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@coach_bp.route("/diet-recommendation", methods=["GET"])
def get_diet_recommendation():
    return recommendation_response(request.args.get("user_id"), diet_recommendation)


@coach_bp.route("/workout-recommendation", methods=["GET"])
def get_workout_recommendation():
    return recommendation_response(request.args.get("user_id"), workout_recommendation)


@coach_bp.route("/weekly-recommendation", methods=["GET"])
def get_weekly_recommendation():
    return recommendation_response(request.args.get("user_id"), weekly_recommendation)


@wellness_bp.route("/coach", methods=["POST"])
def wellness_coach():
    data = request.json or {}
    return build_chat_response(data.get("user_id"), data.get("message", "").strip())


@wellness_bp.route("/coach/history", methods=["GET"])
def wellness_history():
    return build_history_response(request.args.get("user_id"))
