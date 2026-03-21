"""ViralForge v3 — Database layer with memory/learning system"""
import sqlite3, os, json
from datetime import datetime

DB = os.path.join(os.path.dirname(__file__), "../data/vf3.db")

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS trends (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    views INTEGER DEFAULT 0,
    source TEXT,
    hook_type TEXT,
    triggers TEXT DEFAULT '[]',
    virality_score REAL DEFAULT 0,
    fetched_at TEXT,
    url TEXT DEFAULT '',
    thumbnail TEXT DEFAULT '',
    niche TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS idea_batches (
    id TEXT PRIMARY KEY,
    niche TEXT,
    trend_context TEXT,
    ideas_json TEXT,
    selected_idx INTEGER DEFAULT -1,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS scripts (
    id TEXT PRIMARY KEY,
    batch_id TEXT,
    idea_idx INTEGER DEFAULT 0,
    title TEXT,
    hook TEXT,
    script_json TEXT,
    decision_json TEXT,
    virality_score REAL DEFAULT 0,
    created_at TEXT,
    niche TEXT
);

CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY,
    script_id TEXT,
    status TEXT DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    file_path TEXT DEFAULT '',
    thumb_path TEXT DEFAULT '',
    created_at TEXT,
    file_size INTEGER DEFAULT 0,
    palette TEXT DEFAULT 'amber',
    export_dir TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    script_id TEXT,
    video_id TEXT,
    platform TEXT,
    views INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    recorded_at TEXT
);

CREATE TABLE IF NOT EXISTS pattern_weights (
    pattern_key TEXT PRIMARY KEY,
    weight REAL DEFAULT 1.0,
    sample_count INTEGER DEFAULT 0,
    avg_performance REAL DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    value TEXT,
    expires_at TEXT
);
"""

def get_db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init():
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    # Seed default pattern weights if empty
    if not conn.execute("SELECT 1 FROM pattern_weights LIMIT 1").fetchone():
        defaults = [
            ("hook:curiosity_gap", 1.4), ("hook:pattern_interrupt", 1.3),
            ("hook:fear_hook", 1.2),     ("hook:number_hook", 1.1),
            ("hook:transformation", 1.0), ("hook:question_hook", 0.9),
            ("hook:list_format", 0.85),  ("hook:neutral", 0.4),
            ("trigger:curiosity", 1.3),  ("trigger:fear", 1.2),
            ("trigger:aspiration", 1.1), ("trigger:relatability", 1.1),
            ("trigger:controversy", 1.0),("trigger:humor", 0.9),
        ]
        for key, w in defaults:
            conn.execute(
                "INSERT OR IGNORE INTO pattern_weights (pattern_key,weight,updated_at) VALUES (?,?,?)",
                (key, w, datetime.now().isoformat())
            )
        conn.commit()
    conn.close()

def get_weights() -> dict:
    conn = get_db()
    rows = conn.execute("SELECT pattern_key, weight FROM pattern_weights").fetchall()
    conn.close()
    return {r["pattern_key"]: r["weight"] for r in rows}

def update_weight(pattern_key: str, performance_score: float):
    """Bayesian-style weight update from performance feedback."""
    conn = get_db()
    row = conn.execute(
        "SELECT weight, sample_count, avg_performance FROM pattern_weights WHERE pattern_key=?",
        (pattern_key,)
    ).fetchone()
    if row:
        n = row["sample_count"] + 1
        new_avg = (row["avg_performance"] * row["sample_count"] + performance_score) / n
        # Nudge weight toward performance signal (learning rate 0.1)
        new_weight = row["weight"] * 0.9 + (performance_score / 50.0) * 0.1
        new_weight = max(0.2, min(2.5, new_weight))
        conn.execute(
            "UPDATE pattern_weights SET weight=?,sample_count=?,avg_performance=?,updated_at=? WHERE pattern_key=?",
            (new_weight, n, new_avg, datetime.now().isoformat(), pattern_key)
        )
        conn.commit()
    conn.close()

def cache_get(key: str):
    conn = get_db()
    row = conn.execute(
        "SELECT value, expires_at FROM cache WHERE key=?", (key,)
    ).fetchone()
    conn.close()
    if not row: return None
    if row["expires_at"] < datetime.now().isoformat(): return None
    try: return json.loads(row["value"])
    except: return None

def cache_set(key: str, value, ttl_seconds: int = 600):
    from datetime import timedelta
    expires = (datetime.now() + timedelta(seconds=ttl_seconds)).isoformat()
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO cache (key,value,expires_at) VALUES (?,?,?)",
        (key, json.dumps(value), expires)
    )
    conn.commit()
    conn.close()
