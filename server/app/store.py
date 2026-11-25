"""Local SQLite storage. No student images or tokens go into Git."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

def now():
    return datetime.now(timezone.utc).isoformat()

class Store:
    def __init__(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        self.images = directory / 'images'
        self.images.mkdir(exist_ok=True)
        self.db = directory / 'attendance.sqlite3'
        with self.connection() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS sessions (
              session_id TEXT PRIMARY KEY, place_id TEXT NOT NULL, token TEXT NOT NULL,
              created_at TEXT NOT NULL, expires_at TEXT NOT NULL, active INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts (
              attempt_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, student_id TEXT NOT NULL,
              created_at TEXT NOT NULL, status TEXT NOT NULL, result TEXT);
            CREATE TABLE IF NOT EXISTS calibration_samples (
              attempt_id TEXT PRIMARY KEY, label TEXT NOT NULL, rtt_ms REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS runtime_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS collection_records (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, label TEXT NOT NULL, purpose TEXT NOT NULL, result TEXT NOT NULL);
            ''')
            db.execute("UPDATE attempts SET status='interrupted' WHERE status='processing'")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.db, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def create_session(self, item):
        with self.connection() as db:
            db.execute('INSERT INTO sessions VALUES (?,?,?,?,?,1)',
                       tuple(item[k] for k in ['session_id','place_id','token','created_at','expires_at']))

    def session(self, session_id):
        with self.connection() as db:
            row = db.execute('SELECT * FROM sessions WHERE session_id=?', (session_id,)).fetchone()
            return dict(row) if row else None

    def sessions(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute('SELECT session_id,place_id,created_at,expires_at,active FROM sessions ORDER BY created_at DESC LIMIT 100')]

    def close_session(self, session_id):
        with self.connection() as db:
            db.execute('UPDATE sessions SET active=0 WHERE session_id=?', (session_id,))

    def reserve(self, attempt_id, session_id, student_id):
        try:
            with self.connection() as db:
                db.execute('INSERT INTO attempts VALUES (?,?,?,?,?,NULL)',
                           (attempt_id, session_id, student_id, now(), 'processing'))
            return True
        except sqlite3.IntegrityError:
            return False

    def complete(self, attempt_id, status, result):
        with self.connection() as db:
            db.execute('UPDATE attempts SET status=?,result=? WHERE attempt_id=?',
                       (status, json.dumps(result, ensure_ascii=False), attempt_id))

    def attempts(self):
        with self.connection() as db:
            rows = [dict(row) for row in db.execute('SELECT * FROM attempts ORDER BY created_at DESC LIMIT 100')]
        for row in rows:
            row['result'] = json.loads(row['result']) if row['result'] else None
        return rows

    def calibration_samples(self):
        with self.connection() as db:
            return [dict(r) for r in db.execute('SELECT * FROM calibration_samples ORDER BY rowid')]

    def tag_sample(self, attempt_id, label):
        with self.connection() as db:
            if label == 'remove':
                db.execute('DELETE FROM calibration_samples WHERE attempt_id=?',(attempt_id,))
                return
            row=db.execute('SELECT status,result FROM attempts WHERE attempt_id=?',(attempt_id,)).fetchone()
            if not row or row['status']!='complete':raise ValueError('완료된 인증을 선택하세요')
            result=json.loads(row['result'])
            relay=result.get('relay',{})
            if relay.get('sample_count')!=10 or relay.get('statistic')!='median':raise ValueError('10회 중앙값 표본만 등록할 수 있습니다')
            db.execute('INSERT INTO calibration_samples VALUES (?,?,?) ON CONFLICT(attempt_id) DO UPDATE SET label=excluded.label,rtt_ms=excluded.rtt_ms',
                       (attempt_id,label,relay['rtt_ms']))

    def active_calibration(self):
        with self.connection() as db:
            row=db.execute("SELECT value FROM runtime_settings WHERE key='calibration'").fetchone()
            return json.loads(row['value']) if row else None

    def save_calibration(self, value):
        with self.connection() as db:
            db.execute("INSERT INTO runtime_settings VALUES ('calibration',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(value),))

    def add_collection_record(self, record_id, run_id, label, purpose, result):
        with self.connection() as db:
            db.execute('INSERT INTO collection_records VALUES (?,?,?,?,?)',(record_id,run_id,label,purpose,json.dumps(result)))
            if purpose=='calibration':
                db.execute('INSERT INTO calibration_samples VALUES (?,?,?)',(record_id,label,result['rtt_ms']))

    def collection_records(self):
        with self.connection() as db:
            rows=[dict(r) for r in db.execute('SELECT * FROM collection_records ORDER BY rowid DESC LIMIT 20000')]
        for r in rows:r['result']=json.loads(r['result'])
        return rows
