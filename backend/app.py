from flask import Flask, jsonify
import os
import sys

# Ensure the backend directory is in the path for Vercel deployments
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from flask_cors import CORS
from config.db import init_db
from routes.auth_routes import auth_bp
from routes.profile_routes import profile_bp
from routes.progress_routes import progress_routes
from routes.dashboard_routes import dashboard_bp
from routes.coach_routes import coach_bp, wellness_bp
from routes.hostel_routes import hostel_bp
from routes.reports_routes import reports_bp
from dotenv import load_dotenv

load_dotenv(override=True)

app = Flask(__name__)
CORS(app)

# Register Blueprints
app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(profile_bp, url_prefix='/api/user')
app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')
app.register_blueprint(progress_routes, url_prefix='/api/progress')
app.register_blueprint(coach_bp, url_prefix='/api/coach')
app.register_blueprint(wellness_bp, url_prefix='/api/wellness')
app.register_blueprint(hostel_bp, url_prefix='/api/hostel')
app.register_blueprint(reports_bp, url_prefix='/api/reports')

# Only uncomment to manually init DB locally if needed
# init_db()

# Global Error Handler for Debugging Vercel Errors
@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    return jsonify({
        "error": "Internal Server Error",
        "message": str(e),
        "traceback": traceback.format_exc()
    }), 500

@app.route('/', methods=['GET'])
def home():
    return "Sustainability Backend is running!"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)
