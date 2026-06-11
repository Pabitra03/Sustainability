# 🌿 Sustainability

An intelligent health, nutrition, and budget assistant for college students living in hostels. The app uses profile metrics, hostel mess menus, daily progress, budget, food preferences, and logged meals to generate personalized diet, workout, mess, grocery, protein, and forecast recommendations.

---

## ✨ Features

- **🔐 Auth System** — Secure user registration & login with bcrypt password hashing
- **📋 Smart Onboarding & Profile Memory** — Collects biometrics, goal weight, diet preference, hostel details, budget, preferred foods, disliked foods, and allergies
- **🥗 Personalized Diet Plans** — AI-generated meal plans (breakfast, lunch, dinner) with exact macro breakdowns tailored to your caloric goal
- **💪 Workout Plans** — Metabolic routines built to burn fat or build muscle based on your profile
- **📊 Production Analytics** — Chart.js dashboards for weight, calories, protein, water, sleep, workouts, hostel protein, budget usage, health score trends, radar scoring, progress rings, and predictions
- **📈 Predictive Insights** — Data-driven weight and health score forecasts with confidence indicators from logged user history
- **🏠 AI Hostel Mode & Assistant** — Unified hostel dashboard featuring a mess plate builder, daily menu logs, macro analysis, nutrition quality score, protein gap detection, weekly grocery lists, survival mode ranking, and a hostel health score tracker
- **📄 PDF Reports** — Print-ready health reports with profile, BMI, BMR, TDEE, progress, budget analysis, mess analysis, health score, forecasts, and recommendations
- **🤖 AI Coach** — Multi-functional coaching chat that answers both general fitness queries (water, protein, weight forecasts, health scores) and hostel-specific questions (mess menu adjustments, budget-fit food suggestions, allergies, and dislikes)
- **🧮 Health Insights** — Auto-calculates BMI, BMR, and TDEE from your profile data
- **🌙 Dark Mode** — Fully themed light/dark UI with smooth transitions
- **☁️ Cloud Database** — Powered by TiDB Cloud Serverless (MySQL-compatible) with SSL and auto-retry on wake-up

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | HTML5, Tailwind CSS, Vanilla JavaScript, Chart.js, Feather Icons |
| **Backend** | Python 3, Flask, Flask-CORS |
| **Database** | TiDB Cloud Serverless (MySQL-compatible) via PyMySQL |
| **Auth** | bcrypt password hashing |
| **Deployment** | Vercel (backend as serverless functions) |

---

## 📁 Project Structure

```
Sustainability/
├── frontend/           # Static HTML/CSS/JS frontend
│   ├── index.html      # Landing page
│   ├── auth.html       # Login & Register
│   ├── onboarding.html # User profile setup
│   ├── dashboard.html  # Main dashboard
│   ├── diet.html       # Diet plan page
│   ├── workout.html    # Workout plan page
│   ├── progress.html   # Advanced analytics dashboard with real logged data
│   ├── hostel.html     # Mess plate builder & Hostel Assistant dashboard
│   ├── coach.html      # AI coaching chat
│   ├── reports.html    # Professional report and PDF export view
│   ├── profile.html    # Profile settings
│   ├── css/            # Stylesheets
│   └── js/app.js       # Shared JS utilities & API config
│
└── backend/            # Flask REST API
    ├── app.py          # App entry point & blueprint registration
    ├── config/db.py    # DB connection with retry logic
    ├── routes/         # API route handlers
    │   ├── auth_routes.py
    │   ├── profile_routes.py
    │   ├── dashboard_routes.py
    │   ├── progress_routes.py
    │   ├── hostel_routes.py
    │   ├── reports_routes.py
    │   └── coach_routes.py
    ├── models/         # AI/ML recommendation models
    ├── utils/          # Plan generation, coach engine, nutrition, schema helpers
    ├── setup_db.py     # DB initializer script
    ├── isrgrootx1.pem  # TiDB SSL certificate
    └── requirements.txt
```

---

## 🚀 Running Locally

### Prerequisites
- Python 3.8+
- A [TiDB Cloud](https://tidbcloud.com) Serverless cluster (free tier works)

---

### 1. Backend Setup

```bash
# Navigate to the backend folder
cd backend

# Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac/Linux

# Install dependencies
pip install -r requirements.txt
```

Create a `.env` file inside the `backend/` folder:

```env
DB_HOST=gateway01.ap-southeast-1.prod.alicloud.tidbcloud.com
DB_USER=your_tidb_user
DB_PASSWORD=your_tidb_password
DB_NAME=test
DB_PORT=4000
DB_SSL_CA=isrgrootx1.pem
```

Initialize the database tables (run once):

```bash
python setup_db.py
```

The app also runs a safe schema check from live API routes. A fresh database is created with all required tables:

- `users`
- `profiles` with goal weight, hostel opt-in, and AI memory fields
- `user_progress`
- `user_daily_metrics`
- `coach_chat_messages`
- `hostels`
- `mess_menus`
- `mess_food_items`
- `hostel_menus`
- `hostel_consumption`

Start the backend server (runs on port **5001**):

```bash
python app.py
```

---

### 2. Frontend Setup

Open a new terminal and run:

```bash
# Navigate to the frontend folder
cd frontend

# Serve with Python's built-in server (runs on port 3000)
python -m http.server 3000
```

Then open your browser and go to: **[http://localhost:3000](http://localhost:3000)**

> The frontend auto-detects `localhost` and points API calls to `http://127.0.0.1:5001/api`.

---

## ⚙️ Environment Variables

| Variable | Description |
|---|---|
| `DB_HOST` | TiDB Cloud cluster hostname |
| `DB_USER` | TiDB database username |
| `DB_PASSWORD` | TiDB database password |
| `DB_NAME` | Database name (default: `test`) |
| `DB_PORT` | TiDB port (default: `4000`) |
| `DB_SSL_CA` | Path to SSL CA certificate (`isrgrootx1.pem`) |

---

## 📝 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/register` | Register a new user |
| POST | `/api/auth/login` | Login and get session |
| POST | `/api/user/profile` | Save user profile |
| GET | `/api/user/profile?user_id=` | Get user profile |
| GET | `/api/dashboard/?user_id=` | Get personalized dashboard data |
| GET | `/api/dashboard/daily-briefing?user_id=` | Get AI daily briefing |
| GET | `/api/dashboard/action-center?user_id=` | Get right-now actions |
| GET | `/api/dashboard/health-score?user_id=` | Get health score engine output |
| GET | `/api/dashboard/nutrient-analysis?user_id=` | Get protein/fiber/water gaps |
| GET | `/api/dashboard/notifications?user_id=` | Get smart notifications |
| GET | `/api/progress/status/<user_id>` | Get progress tracking data |
| POST | `/api/progress/mark-complete` | Mark diet/workout as done |
| POST | `/api/progress/metrics` | Log daily weight, calories, protein, water, sleep, and steps |
| GET | `/api/progress/analytics?user_id=&days=30` | Get real progress analytics, trend indicators, radar scores, progress rings, and predictions |
| GET | `/api/progress/analytics?user_id=&period=all` | Get all-time analytics from the user's stored history |
| GET | `/api/progress/health-score?user_id=` | Get current health score |
| GET | `/api/progress/forecast?user_id=` | Get 7/30/90 day weight forecast with confidence |
| GET | `/api/hostel/menu?user_id=` | Get today's hostel menu |
| POST | `/api/hostel/menu` | Save breakfast/lunch/dinner mess menu |
| POST | `/api/hostel/analyze-menu` | Analyze hostel meal macros, nutrition quality, recommendations, and optionally mark consumed |
| GET | `/api/hostel/assistant?user_id=` | Get combined mess analysis, budget plan, protein gap, grocery plan, survival mode, hostel health score, and insights |
| GET | `/api/hostel/budget-plan?user_id=` | Get affordable diet plan with daily, weekly, and monthly cost |
| GET | `/api/hostel/protein-gap?user_id=` | Get target protein, consumed protein, remaining protein, and budget-fit foods |
| GET | `/api/hostel/grocery-plan?user_id=` | Get weekly grocery list with estimated weekly and monthly cost |
| GET | `/api/hostel/survival?user_id=&budget_remaining=` | Rank low-cost protein sources by protein per rupee |
| GET | `/api/hostel/health-score?user_id=` | Get hostel health score using habits, budget discipline, and mess quality |
| GET | `/api/hostel/insights?user_id=` | Get hostel trends, mess logs, budget plan, and AI insights |
| GET | `/api/coach/diet-recommendation?user_id=` | Get personalized daily AI diet plan |
| GET | `/api/coach/workout-recommendation?user_id=` | Get personalized daily AI workout plan |
| GET | `/api/coach/weekly-recommendation?user_id=` | Get weekly AI health recommendations |
| POST | `/api/coach/chat` | Chat with AI coach |
| GET | `/api/coach/history?user_id=` | Get last AI coach messages |
| POST | `/api/wellness/coach` | Chat with wellness coach |
| GET | `/api/wellness/coach/history?user_id=` | Get wellness coach chat history |
| GET | `/api/reports/summary?user_id=` | Get professional report data |

---

## 💡 Notes

- **No sample chart data**: Analytics charts use `user_daily_metrics`, `user_progress`, `hostel_consumption`, and real profile/menu rows. Empty ranges render as empty states instead of dummy values.
- **Goal weight**: Users can save an optional `goal_weight_kg`; if they skip it, the app derives a safe target from their profile metrics.
- **Hostel opt-out**: `uses_hostel` controls whether hostel pages, recommendations, API data, and report lines appear.
- **Schema self-healing**: Live API routes run safe schema checks so older TiDB tables receive missing hostel, metric, and budget columns without data loss.
- **Budget estimates**: Hostel grocery and survival mode use the shared nutrition/cost catalog in `backend/utils/nutrition.py` and combine it with saved user budget, diet type, and logged nutrition data.
- **TiDB Auto-Pause**: TiDB Serverless free clusters may auto-pause after inactivity. The backend automatically retries connection up to 3 times, and the frontend shows a friendly `"Database is waking up..."` message during retry. To disable auto-pause permanently, go to your TiDB Cloud Console → Cluster Settings → Auto Pause → Disable.
- **SSL**: The `isrgrootx1.pem` certificate file must be present in the `backend/` directory for secure connection to TiDB Cloud.
