from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pathlib import Path
from datetime import datetime, timezone
import sqlite3, hashlib, json

DB_PATH = Path(__file__).resolve().parent.parent / "consentguard.db"
PURPOSES = {"essential", "analytics", "personalization", "advertising", "email_marketing"}
app = FastAPI(title="ConsentGuard API", version="1.0.0",
              description="Purpose-specific consent registry, audit trail and mock enforcement API.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"chrome-extension://.*",
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)

def now():
    return datetime.now(timezone.utc).isoformat()

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS consents (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          site TEXT NOT NULL, purpose TEXT NOT NULL, status TEXT NOT NULL,
          notice_version TEXT NOT NULL, notice_hash TEXT NOT NULL,
          updated_at TEXT NOT NULL, UNIQUE(site, purpose)
        );
        CREATE TABLE IF NOT EXISTS audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          site TEXT NOT NULL, purpose TEXT NOT NULL, action TEXT NOT NULL,
          previous_status TEXT, new_status TEXT NOT NULL,
          notice_version TEXT NOT NULL, notice_hash TEXT NOT NULL,
          reason TEXT NOT NULL, trace_id TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS policies (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          site TEXT NOT NULL, url TEXT NOT NULL, version_hash TEXT NOT NULL,
          changed INTEGER NOT NULL DEFAULT 0, checked_at TEXT NOT NULL,
          UNIQUE(site, url)
        );
        """)
        row = c.execute("SELECT COUNT(*) n FROM consents").fetchone()
        if row["n"] == 0:
            sample = "Demo privacy notice v1: essential storage runs the service; analytics measures usage; personalization remembers preferences; advertising supports promotions; email marketing sends promotional updates."
            h = digest(sample)
            for purpose in PURPOSES:
                status = "granted" if purpose == "essential" else "not_set"
                c.execute("""INSERT OR IGNORE INTO consents
                    (site,purpose,status,notice_version,notice_hash,updated_at)
                    VALUES(?,?,?,?,?,?)""",
                    ("demo.local", purpose, status, "v1", h, now()))
            c.execute("""INSERT OR IGNORE INTO policies(site,url,version_hash,changed,checked_at)
                         VALUES(?,?,?,?,?)""",
                      ("demo.local", "http://localhost:5173/demo-site.html#privacy", h, 0, now()))

@app.on_event("startup")
def startup():
    init_db()

class ConsentInput(BaseModel):
    site: str = "demo.local"
    purpose: str
    decision: str = Field(pattern="^(granted|rejected|withdrawn)$")
    notice_version: str = "v1"
    notice_text: str = "Demo privacy notice v1"
    reason: str = "User choice"

class PolicyCheck(BaseModel):
    site: str = "demo.local"
    url: str
    policy_text: str

class ShareRequest(BaseModel):
    site: str = "demo.local"
    purpose: str
    action: str = "share_demo_data"
    payload: dict = {}

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "ConsentGuard API"}

@app.get("/api/consents")
def get_consents(site: str = "demo.local"):
    with db() as c:
        rows = c.execute("SELECT * FROM consents WHERE site=? ORDER BY purpose", (site,)).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/consents")
def set_consent(item: ConsentInput):
    if item.purpose not in PURPOSES:
        raise HTTPException(400, "Unknown consent purpose")
    h = digest(item.notice_text)
    with db() as c:
        previous = c.execute("SELECT status FROM consents WHERE site=? AND purpose=?",
                             (item.site, item.purpose)).fetchone()
        prev = previous["status"] if previous else "not_set"
        c.execute("""INSERT INTO consents(site,purpose,status,notice_version,notice_hash,updated_at)
                     VALUES(?,?,?,?,?,?)
                     ON CONFLICT(site,purpose) DO UPDATE SET
                     status=excluded.status, notice_version=excluded.notice_version,
                     notice_hash=excluded.notice_hash, updated_at=excluded.updated_at""",
                  (item.site, item.purpose, item.decision, item.notice_version, h, now()))
        trace = digest(f"{item.site}:{item.purpose}:{item.decision}:{now()}")[:16]
        c.execute("""INSERT INTO audit(site,purpose,action,previous_status,new_status,
                     notice_version,notice_hash,reason,trace_id,created_at)
                     VALUES(?,?,?,?,?,?,?,?,?,?)""",
                  (item.site, item.purpose, item.decision, prev, item.decision,
                   item.notice_version, h, item.reason, trace, now()))
    return {"ok": True, "site": item.site, "purpose": item.purpose,
            "status": item.decision, "notice_hash": h, "trace_id": trace}

@app.get("/api/audit")
def get_audit(site: str = "demo.local", limit: int = 100):
    with db() as c:
        rows = c.execute("SELECT * FROM audit WHERE site=? ORDER BY id DESC LIMIT ?",
                         (site, min(limit, 500))).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/protected/share")
def protected_share(req: ShareRequest):
    if req.purpose not in PURPOSES:
        raise HTTPException(400, "Unknown purpose")
    with db() as c:
        row = c.execute("SELECT status FROM consents WHERE site=? AND purpose=?",
                        (req.site, req.purpose)).fetchone()
        status = row["status"] if row else "not_set"
        allowed = status == "granted" or req.purpose == "essential"
        trace = digest(f"{req.site}:{req.purpose}:{req.action}:{now()}")[:16]
        c.execute("""INSERT INTO audit(site,purpose,action,previous_status,new_status,
                     notice_version,notice_hash,reason,trace_id,created_at)
                     VALUES(?,?,?,?,?,?,?,?,?,?)""",
                  (req.site, req.purpose, "enforcement_allow" if allowed else "enforcement_deny",
                   status, status, "current", "", 
                   "Current consent permits request" if allowed else "No active grant for this purpose",
                   trace, now()))
    if not allowed:
        raise HTTPException(403, detail={
            "allowed": False, "purpose": req.purpose, "consent_status": status,
            "reason": "Request denied: current consent is not granted.", "trace_id": trace
        })
    return {"allowed": True, "purpose": req.purpose, "action": req.action,
            "message": "Mock protected action completed.", "trace_id": trace,
            "demo_payload": req.payload}

@app.get("/api/policies")
def get_policies(site: str = "demo.local"):
    with db() as c:
        rows = c.execute("SELECT * FROM policies WHERE site=? ORDER BY checked_at DESC", (site,)).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/policies/check")
def check_policy(item: PolicyCheck):
    h = digest(item.policy_text)
    with db() as c:
        old = c.execute("SELECT version_hash FROM policies WHERE site=? AND url=?",
                        (item.site, item.url)).fetchone()
        changed = bool(old and old["version_hash"] != h)
        c.execute("""INSERT INTO policies(site,url,version_hash,changed,checked_at)
                     VALUES(?,?,?,?,?)
                     ON CONFLICT(site,url) DO UPDATE SET version_hash=excluded.version_hash,
                     changed=excluded.changed, checked_at=excluded.checked_at""",
                  (item.site, item.url, h, int(changed), now()))
        if changed:
            trace = digest(f"policy:{item.site}:{h}:{now()}")[:16]
            c.execute("""INSERT INTO audit(site,purpose,action,previous_status,new_status,
                         notice_version,notice_hash,reason,trace_id,created_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?)""",
                      (item.site, "all", "policy_change_detected", "previous_version",
                       "review_required", "updated", h,
                       "Policy text hash changed; user review may be needed", trace, now()))
    return {"changed": changed, "version_hash": h,
            "message": "Policy changed — review may be needed." if changed else "No policy change detected."}
