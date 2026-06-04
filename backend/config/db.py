import pymysql
import os
import time
from threading import Lock
from dotenv import load_dotenv
from utils.schema import ensure_app_schema

load_dotenv(override=True)

_pool = []
_pool_lock = Lock()


class PooledConnection:
    def __init__(self, conn):
        self._conn = conn
        self._returned = False

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        if self._returned:
            return
        self._returned = True
        max_size = int(os.getenv('DB_POOL_SIZE', 4))
        try:
            self._conn.ping(reconnect=False)
        except Exception:
            try:
                self._conn.close()
            except Exception:
                pass
            return
        with _pool_lock:
            if len(_pool) < max_size:
                _pool.append(self._conn)
                return
        self._conn.close()


def _pooled_connection():
    with _pool_lock:
        conn = _pool.pop() if _pool else None
    if not conn:
        return None
    try:
        conn.ping(reconnect=True)
        return PooledConnection(conn)
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return None


def get_db_connection(with_db=True, retries=3, retry_delay=2):
    """
    Get a database connection with automatic retry logic.
    TiDB Serverless clusters auto-pause after inactivity and need
    a few seconds to wake up. This retry mechanism handles that
    transparently so users never see a failed connection.
    """
    if with_db and os.getenv('DB_DISABLE_POOL', 'false').lower() != 'true':
        pooled = _pooled_connection()
        if pooled:
            return pooled

    config = {
        'host': os.getenv('DB_HOST', '127.0.0.1'),
        'user': os.getenv('DB_USER', 'root'),
        'password': os.getenv('DB_PASSWORD', ''),
        'port': int(os.getenv('DB_PORT', 3306)),
        'charset': 'utf8mb4',
        'connect_timeout': int(os.getenv('DB_CONNECT_TIMEOUT', 10)),
        'read_timeout': int(os.getenv('DB_READ_TIMEOUT', 12)),
        'write_timeout': int(os.getenv('DB_WRITE_TIMEOUT', 12)),
        'autocommit': True
    }

    if with_db:
        config['cursorclass'] = pymysql.cursors.DictCursor

    ssl_ca = os.getenv('DB_SSL_CA')
    if ssl_ca:
        if not os.path.isabs(ssl_ca):
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ssl_ca = os.path.join(backend_dir, ssl_ca)
        config['ssl'] = {'ca': ssl_ca}

    if with_db:
        config['database'] = os.getenv('DB_NAME', 'fitness_db')

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            conn = pymysql.connect(**config)
            if attempt > 1:
                print(f"DB connected on attempt {attempt}")
            if with_db and os.getenv('DB_DISABLE_POOL', 'false').lower() != 'true':
                return PooledConnection(conn)
            return conn
        except Exception as e:
            last_error = e
            print(f"DB connection attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(retry_delay)

    print(f"All {retries} DB connection attempts failed. Last error: {last_error}")
    return None

def init_db():
    # First, connect without a database to create it if it doesn't exist
    conn = get_db_connection(with_db=False)
    if not conn:
        print("Failed to connect to MySQL server. Ensure MySQL is running and credentials are correct.")
        return
    
    cursor = conn.cursor()
    db_name = os.getenv('DB_NAME', 'fitness_db')
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
    conn.commit()
    cursor.close()
    conn.close()

    # Now connect with the database to create tables
    conn = get_db_connection(with_db=True)
    if not conn:
        print("Failed to initialize database tables.")
        return
    cursor = conn.cursor()
    cursor.execute(f"USE {os.getenv('DB_NAME', 'fitness_db')}")
    
    # Create Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        email VARCHAR(100) UNIQUE NOT NULL,
        password VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Create Profiles Table
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

    # Create User Progress Table
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

    conn.commit()
    cursor.close()
    ensure_app_schema(conn)
    conn.close()
    print("Database initialized successfully.")
