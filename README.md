# 🌿 Sustainability — AI Diet & Fitness System

An intelligent health optimization web app that analyzes your biological metrics to build personalized diet plans, workout routines, and tracks your progress over time.

---

## ✨ Features

- **🔐 Auth System** — Secure user registration & login with bcrypt password hashing
- **📋 Smart Onboarding** — Collects age, gender, weight, height, activity level, and goal to personalize everything
- **🥗 Personalized Diet Plans** — AI-generated meal plans (breakfast, lunch, dinner) with exact macro breakdowns tailored to your caloric goal
- **💪 Workout Plans** — Metabolic routines built to burn fat or build muscle based on your profile
- **📊 Progress Tracking** — Visual charts (weekly streaks, diet vs workout completion) that load instantly with async rendering
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
│   ├── progress.html   # Progress tracking & charts
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
    │   └── progress_routes.py
    ├── models/         # AI/ML recommendation models
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
| GET | `/api/progress/status/<user_id>` | Get progress tracking data |
| POST | `/api/progress/mark-complete` | Mark diet/workout as done |

---

## 💡 Notes

- **TiDB Auto-Pause**: TiDB Serverless free clusters may auto-pause after inactivity. The backend automatically retries connection up to 3 times, and the frontend shows a friendly `"Database is waking up..."` message during retry. To disable auto-pause permanently, go to your TiDB Cloud Console → Cluster Settings → Auto Pause → Disable.
- **SSL**: The `isrgrootx1.pem` certificate file must be present in the `backend/` directory for secure connection to TiDB Cloud.
