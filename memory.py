import json, sqlite3, time
from pathlib import Path
from expressions import Expr

class Memory:
    def __init__(self, path: str):
        self.path = Path(path)
        self.db = sqlite3.connect(str(self.path))
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS skills(
          id INTEGER PRIMARY KEY, expr TEXT UNIQUE, text TEXT, depth INTEGER,
          discovered_at REAL, uses INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS episodes(
          id INTEGER PRIMARY KEY, agent TEXT, problem TEXT, success INTEGER,
          experiments INTEGER, hypotheses INTEGER, seconds REAL, peak_kb INTEGER,
          started_at REAL);
        CREATE TABLE IF NOT EXISTS events(
          id INTEGER PRIMARY KEY, agent TEXT, problem TEXT, kind TEXT,
          payload TEXT, created_at REAL);
        """)
        self.db.commit()

    def skills(self):
        rows = self.db.execute("SELECT expr FROM skills ORDER BY id").fetchall()
        return [Expr.from_tuple(tuple(json.loads(r[0]))) for r in rows]

    def save_skill(self, expr: Expr):
        self.db.execute("INSERT OR IGNORE INTO skills(expr,text,depth,discovered_at) VALUES(?,?,?,?)",
                        (json.dumps(expr.to_tuple(), separators=(',', ':')), expr.text(), expr.depth(), time.time()))
        self.db.commit()

    def episode(self, agent, problem, success, experiments, hypotheses, seconds, peak_kb):
        self.db.execute("INSERT INTO episodes VALUES(NULL,?,?,?,?,?,?,?,?)",
                        (agent, problem, int(success), experiments, hypotheses, seconds, peak_kb, time.time()))
        self.db.commit()

    def event(self, agent, problem, kind, payload):
        self.db.execute("INSERT INTO events VALUES(NULL,?,?,?,?,?)",
                        (agent, problem, kind, json.dumps(payload, default=str), time.time()))
        self.db.commit()

    def close(self): self.db.close()

