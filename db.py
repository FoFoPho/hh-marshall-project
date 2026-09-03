import json
import os
import sqlite3
from datetime import datetime, timezone


def get_db_path():
    path = os.environ.get('DATABASE_PATH')
    if path:
        return path
    instance_dir = os.path.join(os.path.dirname(__file__), 'instance')
    os.makedirs(instance_dir, exist_ok=True)
    return os.path.join(instance_dir, 'progress.db')


def get_connection():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS progress (
                email               TEXT NOT NULL,
                module_id           INTEGER NOT NULL,
                first_name          TEXT NOT NULL,
                last_name           TEXT NOT NULL,
                job_title           TEXT,
                current_step        INTEGER NOT NULL DEFAULT 1,
                completed_sections  TEXT NOT NULL DEFAULT '[]',
                quiz_failed_section TEXT,
                cert_number         TEXT,
                completed_at        TEXT,
                updated_at          TEXT NOT NULL,
                PRIMARY KEY (email, module_id)
            )
        ''')


def normalize_email(email):
    return (email or '').strip().lower()


def _row_to_dict(row):
    if row is None:
        return None
    data = dict(row)
    data['completed_sections'] = json.loads(data['completed_sections'])
    return data


def get_progress(email, module_id):
    email = normalize_email(email)
    with get_connection() as conn:
        row = conn.execute(
            'SELECT * FROM progress WHERE email = ? AND module_id = ?',
            (email, module_id),
        ).fetchone()
    return _row_to_dict(row)


def get_progress_for_email(email):
    email = normalize_email(email)
    with get_connection() as conn:
        rows = conn.execute(
            'SELECT * FROM progress WHERE email = ?',
            (email,),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def save_progress(email, module_id, first_name, last_name, job_title,
                   current_step, completed_sections, quiz_failed_section=None,
                   cert_number=None, completed_at=None):
    email = normalize_email(email)
    updated_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute('''
            INSERT INTO progress (
                email, module_id, first_name, last_name, job_title,
                current_step, completed_sections, quiz_failed_section,
                cert_number, completed_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (email, module_id) DO UPDATE SET
                first_name          = excluded.first_name,
                last_name           = excluded.last_name,
                job_title           = excluded.job_title,
                current_step        = excluded.current_step,
                completed_sections  = excluded.completed_sections,
                quiz_failed_section = excluded.quiz_failed_section,
                cert_number         = excluded.cert_number,
                completed_at        = excluded.completed_at,
                updated_at          = excluded.updated_at
        ''', (
            email, module_id, first_name, last_name, job_title,
            current_step, json.dumps(completed_sections), quiz_failed_section,
            cert_number, completed_at, updated_at,
        ))


def delete_progress(email, module_id):
    email = normalize_email(email)
    with get_connection() as conn:
        conn.execute(
            'DELETE FROM progress WHERE email = ? AND module_id = ?',
            (email, module_id),
        )


def get_all_progress():
    with get_connection() as conn:
        rows = conn.execute(
            'SELECT * FROM progress ORDER BY updated_at DESC',
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def reset_all_progress():
    with get_connection() as conn:
        conn.execute('DELETE FROM progress')
