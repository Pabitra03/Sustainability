schema_verified = False

def ensure_column(cursor, table_name, column_name, column_definition):
    cursor.execute(f"SHOW COLUMNS FROM {table_name} LIKE %s", (column_name,))
    if not cursor.fetchone():
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def ensure_app_schema(conn):
    global schema_verified
    if schema_verified:
        return
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        email VARCHAR(100) UNIQUE NOT NULL,
        password VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS profiles (
        user_id INT PRIMARY KEY,
        age INT NOT NULL,
        gender VARCHAR(10) NOT NULL,
        weight FLOAT NOT NULL,
        height FLOAT NOT NULL,
        activity_level VARCHAR(50) NOT NULL,
        goal VARCHAR(50) NOT NULL,
        diet_type VARCHAR(20) DEFAULT 'non_vegetarian',
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_progress (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        entry_date DATE NOT NULL,
        diet_completed BOOLEAN DEFAULT FALSE,
        workout_completed BOOLEAN DEFAULT FALSE,
        streak_count INT DEFAULT 0,
        UNIQUE KEY user_date (user_id, entry_date),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_daily_metrics (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        entry_date DATE NOT NULL,
        weight_kg FLOAT DEFAULT NULL,
        calories INT DEFAULT NULL,
        protein_g FLOAT DEFAULT NULL,
        fiber_g FLOAT DEFAULT NULL,
        water_ml INT DEFAULT NULL,
        sleep_hours FLOAT DEFAULT NULL,
        steps INT DEFAULT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY user_metric_date (user_id, entry_date),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS coach_chat_messages (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        role VARCHAR(20) NOT NULL,
        message TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_coach_chat_user_created (user_id, created_at),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hostels (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(150) NOT NULL,
        hostel_type VARCHAR(50) DEFAULT NULL,
        mess_type VARCHAR(50) DEFAULT NULL,
        monthly_budget FLOAT DEFAULT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY hostel_name_type (name, hostel_type, mess_type)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS mess_menus (
        id INT AUTO_INCREMENT PRIMARY KEY,
        hostel_id INT DEFAULT NULL,
        user_id INT DEFAULT NULL,
        menu_date DATE NOT NULL,
        meal_type VARCHAR(30) NOT NULL,
        menu_text TEXT NOT NULL,
        calories INT DEFAULT 0,
        protein_g FLOAT DEFAULT 0,
        carbs_g FLOAT DEFAULT 0,
        fat_g FLOAT DEFAULT 0,
        quality_score INT DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_mess_menus_user_date (user_id, menu_date),
        INDEX idx_mess_menus_hostel_date (hostel_id, menu_date)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS mess_food_items (
        id INT AUTO_INCREMENT PRIMARY KEY,
        mess_menu_id INT DEFAULT NULL,
        food_name VARCHAR(120) NOT NULL,
        meal_type VARCHAR(30) DEFAULT NULL,
        calories INT DEFAULT 0,
        protein_g FLOAT DEFAULT 0,
        carbs_g FLOAT DEFAULT 0,
        fat_g FLOAT DEFAULT 0,
        estimated_cost FLOAT DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_mess_food_items_menu (mess_menu_id),
        INDEX idx_mess_food_items_food (food_name)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hostel_menus (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        menu_date DATE NOT NULL,
        breakfast TEXT,
        lunch TEXT,
        dinner TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY user_menu_date (user_id, menu_date),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hostel_consumption (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        entry_date DATE NOT NULL,
        meal_type VARCHAR(30) NOT NULL,
        items TEXT NOT NULL,
        calories INT DEFAULT 0,
        protein_g FLOAT DEFAULT 0,
        carbs_g FLOAT DEFAULT 0,
        fat_g FLOAT DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_hostel_consumption_user_date (user_id, entry_date),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    profile_columns = {
        "favorite_foods": "TEXT DEFAULT NULL",
        "disliked_foods": "TEXT DEFAULT NULL",
        "food_allergies": "TEXT DEFAULT NULL",
        "budget": "FLOAT DEFAULT NULL",
        "hostel_name": "VARCHAR(150) DEFAULT NULL",
        "hostel_id": "INT DEFAULT NULL",
        "hostel_type": "VARCHAR(50) DEFAULT NULL",
        "mess_type": "VARCHAR(50) DEFAULT NULL",
        "uses_hostel": "BOOLEAN DEFAULT FALSE",
        "goal_weight_kg": "FLOAT DEFAULT NULL",
    }
    for column_name, definition in profile_columns.items():
        ensure_column(cursor, "profiles", column_name, definition)

    metric_columns = {
        "weight_kg": "FLOAT DEFAULT NULL",
        "calories": "INT DEFAULT NULL",
        "protein_g": "FLOAT DEFAULT NULL",
        "fiber_g": "FLOAT DEFAULT NULL",
        "water_ml": "INT DEFAULT NULL",
        "sleep_hours": "FLOAT DEFAULT NULL",
        "steps": "INT DEFAULT NULL",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    }
    for column_name, definition in metric_columns.items():
        ensure_column(cursor, "user_daily_metrics", column_name, definition)

    hostel_consumption_columns = {
        "meal_type": "VARCHAR(30) NOT NULL DEFAULT 'meal'",
        "items": "TEXT NOT NULL",
        "calories": "INT DEFAULT 0",
        "protein_g": "FLOAT DEFAULT 0",
        "carbs_g": "FLOAT DEFAULT 0",
        "fat_g": "FLOAT DEFAULT 0",
    }
    for column_name, definition in hostel_consumption_columns.items():
        ensure_column(cursor, "hostel_consumption", column_name, definition)

    conn.commit()
    cursor.close()
    schema_verified = True
