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
            if 'hidden' not in {r[1] for r in db.execute('PRAGMA table_info(attempts)')}:
                db.execute('ALTER TABLE attempts ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0')
            db.execute('CREATE TABLE IF NOT EXISTS locations (place_id TEXT PRIMARY KEY, created_at TEXT NOT NULL)')
            for table in ('calibration_samples','collection_records'):
                if 'place_id' not in {r[1] for r in db.execute('PRAGMA table_info('+table+')')}:
                    db.execute('ALTER TABLE '+table+" ADD COLUMN place_id TEXT NOT NULL DEFAULT ''")
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
        # A new QR replaces earlier QRs for the same place, so their tokens must stop working.
        # Same transaction as the insert; returns how many earlier sessions were closed.
        with self.connection() as db:
            closed = db.execute('UPDATE sessions SET active=0 WHERE place_id=? AND active=1',
                                (item['place_id'],)).rowcount
            db.execute('INSERT INTO sessions VALUES (?,?,?,?,?,1)',
                       tuple(item[k] for k in ['session_id','place_id','token','created_at','expires_at']))
        return closed

    def session(self, session_id):
        with self.connection() as db:
            row = db.execute('SELECT * FROM sessions WHERE session_id=?', (session_id,)).fetchone()
            return dict(row) if row else None

    def sessions(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute('SELECT session_id,place_id,created_at,expires_at,active FROM sessions ORDER BY created_at DESC')]

    def close_session(self, session_id):
        with self.connection() as db:
            db.execute('UPDATE sessions SET active=0 WHERE session_id=?', (session_id,))

    def reserve(self, attempt_id, session_id, student_id):
        try:
            with self.connection() as db:
                db.execute('INSERT INTO attempts (attempt_id,session_id,student_id,created_at,status,result) VALUES (?,?,?,?,?,NULL)',
                           (attempt_id, session_id, student_id, now(), 'processing'))
            return True
        except sqlite3.IntegrityError:
            return False

    def complete(self, attempt_id, status, result):
        with self.connection() as db:
            db.execute('UPDATE attempts SET status=?,result=? WHERE attempt_id=?',
                       (status, json.dumps(result, ensure_ascii=False), attempt_id))

    def attempts(self, session_id=None):
        with self.connection() as db:
            rows = [dict(row) for row in db.execute('SELECT * FROM attempts WHERE hidden=0 AND (? IS NULL OR session_id=?) ORDER BY created_at DESC',(session_id,session_id))]
        for row in rows:
            row['result'] = json.loads(row['result']) if row['result'] else None
        return rows

    def calibration_samples(self, place_id):
        with self.connection() as db:
            return [dict(r) for r in db.execute('SELECT * FROM calibration_samples WHERE place_id=? ORDER BY rowid',(place_id,))]

    def tag_sample(self, attempt_id, label, place_id):
        with self.connection() as db:
            if label == 'remove':
                if not db.execute('DELETE FROM calibration_samples WHERE attempt_id=? AND place_id=?',(attempt_id,place_id)).rowcount:
                    raise ValueError('등록된 표본이 아닙니다')
                return
            row=db.execute('SELECT a.status,a.result FROM attempts a JOIN sessions s ON a.session_id=s.session_id WHERE a.attempt_id=? AND s.place_id=?',(attempt_id,place_id)).fetchone()
            if not row or row['status']!='complete':raise ValueError('완료된 인증을 선택하세요')
            result=json.loads(row['result'])
            relay=result.get('relay',{})
            if relay.get('sample_count')!=10 or relay.get('statistic')!='median':raise ValueError('10회 중앙값 표본만 등록할 수 있습니다')
            db.execute('INSERT INTO calibration_samples (attempt_id,label,rtt_ms,place_id) VALUES (?,?,?,?) ON CONFLICT(attempt_id) DO UPDATE SET label=excluded.label,rtt_ms=excluded.rtt_ms',
                       (attempt_id,label,relay['rtt_ms'],place_id))

    def active_calibration(self, place_id):
        with self.connection() as db:
            row=db.execute("SELECT value FROM runtime_settings WHERE key=?",('calibration:'+place_id,)).fetchone()
            return json.loads(row['value']) if row else None

    def save_calibration(self, value, place_id):
        with self.connection() as db:
            db.execute("INSERT INTO runtime_settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",('calibration:'+place_id,json.dumps(value)))

    def add_collection_record(self, record_id, run_id, label, purpose, result, place_id):
        with self.connection() as db:
            db.execute('INSERT INTO collection_records (id,run_id,label,purpose,result,place_id) VALUES (?,?,?,?,?,?)',(record_id,run_id,label,purpose,json.dumps(result),place_id))
            if purpose=='calibration':
                db.execute('INSERT INTO calibration_samples (attempt_id,label,rtt_ms,place_id) VALUES (?,?,?,?)',(record_id,label,result['rtt_ms'],place_id))

    def collection_records(self, place_id):
        with self.connection() as db:
            rows=[dict(r) for r in db.execute('SELECT * FROM collection_records WHERE place_id=? ORDER BY rowid DESC LIMIT 20000',(place_id,))]
        for r in rows:r['result']=json.loads(r['result'])
        return rows

    def clear_attempts(self, session_id):
        with self.connection() as db:
            db.execute('UPDATE attempts SET hidden=1 WHERE session_id=?',(session_id,))

    def reset_samples(self, place_id):
        with self.connection() as db:
            db.execute('DELETE FROM calibration_samples WHERE place_id=?',(place_id,))
            db.execute('DELETE FROM collection_records WHERE place_id=?',(place_id,))
            db.execute("DELETE FROM runtime_settings WHERE key=?",('calibration:'+place_id,))

    def ensure_place(self, place_id):
        with self.connection() as db:
            db.execute('INSERT OR IGNORE INTO locations VALUES (?,?)',(place_id,now()))

    def places(self):
        with self.connection() as db:
            return [dict(r) for r in db.execute('SELECT * FROM locations ORDER BY created_at DESC')]
