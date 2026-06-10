# main.py — Capitan AI Backend (Production Ready for Render)
import os, uuid, time, requests, redis, jwt, sqlite3
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from passlib.context import CryptContext
from loguru import logger

# --- Config ---
JWT_SECRET = os.environ.get("JWT_SECRET", "supersecret")
ADMIN_CODE = os.environ.get("ADMIN_CODE", "")
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
RESEND_KEY = os.environ.get("RESEND_API_KEY", "")
DB_PATH = "capitan.db"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
r = redis.Redis(
    host=os.environ.get("REDIS_HOST", "localhost"),
    port=int(os.environ.get("REDIS_PORT", "6379")),
    db=0
)

# --- Helpers ---
def sid(): return str(uuid.uuid4())[:8].upper()

def hash_password(password): return pwd_context.hash(password)
def verify_password(password, hashed): return pwd_context.verify(password, hashed)

def create_jwt(user_id, tier):
    payload = {"user_id": user_id, "tier": tier, "exp": datetime.utcnow() + timedelta(days=30)}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def verify_jwt(token):
    try: return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError: return None
    except jwt.InvalidTokenError: return None

def get_user(request: Request):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        payload = verify_jwt(auth[7:])
        if payload:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT id,email,name,tier FROM users WHERE id=?", (payload["user_id"],))
            row = c.fetchone(); conn.close()
            if row: return {"id": row[0], "email": row[1], "name": row[2], "tier": row[3]}
    return None

def check_rate(user_id, tier):
    limits = {"free": 10, "plus": 20, "pro": 60, "founder": 200}
    key = f"rate:{user_id}"
    current = r.incr(key)
    if current == 1: r.expire(key, 60)
    return current <= limits.get(tier, 10)

def send_email(to, subject, html):
    if not RESEND_KEY:
        logger.warning(f"Email skipped: {to} - {subject}")
        return
    try:
        requests.post("https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_KEY}", "Content-Type": "application/json"},
            json={"from": "CAPITAN AI <noreply@closeai.tech>", "to": [to], "subject": subject, "html": html}, timeout=10)
    except Exception as e:
        logger.error(f"Email send failed: {e}")

# --- Models ---
class RegisterRequest(BaseModel):
    email: str; name: str; password: str
class LoginRequest(BaseModel):
    email: str; password: str
class ChatRequest(BaseModel):
    messages: list; chat_id: Optional[str] = None
class WorkspaceMessageRequest(BaseModel):
    room_code: str; message: str

# --- App ---
app = FastAPI(title="CAPITAN AI API", version="20.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- Endpoints ---
@app.get("/health")
def health(): return {"status": "ok", "version": "20.0"}

@app.post("/api/auth/register")
def register(req: RegisterRequest):
    if not req.email or "@" not in req.email: raise HTTPException(400, "Valid email required")
    if len(req.password) < 6: raise HTTPException(400, "Password too short")
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email=?", (req.email.lower().strip(),))
    if c.fetchone(): conn.close(); raise HTTPException(409, "Email exists")
    uid = f"u_{sid()}"; pw_hash = hash_password(req.password)
    c.execute("INSERT INTO users (id,email,name,password_hash,tier,created,updated) VALUES (?,?,?,?,?,?,?)",
        (uid, req.email.lower().strip(), req.name, pw_hash, "free", datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    token = create_jwt(uid, "free")
    send_email(req.email, "Welcome to CAPITAN AI 👌", "<p>Your account is ready.</p>")
    return {"token": token, "user": {"id": uid, "email": req.email, "name": req.name, "tier": "free"}}

@app.post("/api/auth/login")
def login(req: LoginRequest):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,email,name,tier,password_hash FROM users WHERE email=?", (req.email.lower().strip(),))
    row = c.fetchone(); conn.close()
    if not row or not verify_password(req.password, row[4]): raise HTTPException(401, "Invalid credentials")
    token = create_jwt(row[0], row[3])
    return {"token": token, "user": {"id": row[0], "email": row[1], "name": row[2], "tier": row[3]}}

@app.post("/api/chat")
def chat(req: ChatRequest, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    if not check_rate(user["id"], user["tier"]): raise HTTPException(429, "Rate limit")
    user_msg = next((m["content"] for m in reversed(req.messages) if m.get("role") == "user"), "")
    if not user_msg: raise HTTPException(400, "No message")
    # AI call stub (replace with actual model integration)
    result = f"Echo: {user_msg}"
    return {"content": result, "chat_id": req.chat_id or f"chat_{sid()}"}

@app.post("/api/workspace/message")
def ws_message(req: WorkspaceMessageRequest, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM workspaces WHERE room_code=?", (req.room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404, "Room not found")
    c.execute("INSERT INTO workspace_messages (id,workspace_id,user_id,author,message,created) VALUES (?,?,?,?,?,?)",
              (sid(), ws[0], user["id"], user["name"], req.message, datetime.utcnow().isoformat()))
    conn.commit()
    c.execute("SELECT id,user_id,author,message,is_ai,created FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 50", (ws[0],))
    messages = [{"id": r[0], "user_id": r[1], "author": r[2], "message": r[3], "is_ai": bool(r[4]), "created": r[5]} for r in c.fetchall()]
    conn.close()
    return {"sent": True, "messages": messages}

@app.get("/api/workspace/messages")
def ws_get_messages(room_code: str, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM workspaces WHERE room_code=?", (room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404, "Room not found")
    c.execute("SELECT id,user_id,author,message,is_ai,created FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 50", (ws[0],))
    messages = [{"id": r[0], "user_id": r[1], "author": r[2], "message": r[3], "is_ai": bool(r[4]), "created": r[5]} for r in c.fetchall()]
    conn.close()
    return {"messages": messages}