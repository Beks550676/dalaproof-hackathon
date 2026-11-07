import sqlite3
import json

DB_NAME = "dalaproof.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Таблица задач (микро-кейсов от бизнеса)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            input_example TEXT,
            expected_output TEXT
        )
    """)
    
    # Таблица решений кандидатов и результатов AI-защиты
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            submission_id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            candidate_name TEXT NOT NULL,
            code TEXT NOT NULL,
            ast_valid BOOLEAN,
            detected_structures TEXT,
            questions TEXT,
            ai_compliance_score INTEGER DEFAULT 0,
            verdict TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks (task_id)
        )
    """)
    
    conn.commit()
    conn.close()

def create_task(title, description, input_example, expected_output):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tasks (title, description, input_example, expected_output) VALUES (?, ?, ?, ?)",
        (title, description, input_example, expected_output)
    )
    conn.commit()
    task_id = cursor.lastrowid
    conn.close()
    return task_id

def get_all_tasks():
    conn = get_db_connection()
    cursor = conn.cursor()
    tasks = cursor.execute("SELECT * FROM tasks").fetchall()
    conn.close()
    return [dict(row) for row in tasks]

def create_submission(task_id, candidate_name, code, ast_valid, structures, questions):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO submissions 
           (task_id, candidate_name, code, ast_valid, detected_structures, questions) 
           VALUES (?, ?, ?, ?, ?, ?)""",
        (task_id, candidate_name, code, ast_valid, json.dumps(structures), json.dumps(questions))
    )
    conn.commit()
    sub_id = cursor.lastrowid
    conn.close()
    return sub_id

def update_submission_score(submission_id, score, verdict):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE submissions SET ai_compliance_score = ?, verdict = ? WHERE submission_id = ?",
        (score, verdict, submission_id)
    )
    conn.commit()
    conn.close()

def get_leaderboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    rows = cursor.execute("""
        SELECT s.submission_id, s.candidate_name, t.title as task_title, 
               s.ai_compliance_score, s.verdict 
        FROM submissions s
        JOIN tasks t ON s.task_id = t.task_id
        ORDER BY s.ai_compliance_score DESC
    """).fetchall()
    conn.close()
    return [dict(row) for row in rows]
if __name__ == "__main__":
    init_db()
    print("База данных успешно инициализирована!")