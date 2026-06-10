"""
CAPITAN AI — Enterprise Backend v20.0
CLOSEAI Technologies
Python/FastAPI + SQLite + Resend Email
All features included — nothing missing
"""

import os, re, json, uuid, time, hashlib, hmac, base64, secrets, requests, sqlite3
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import uvicorn

# ═══════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
RESEND_KEY = os.environ.get("RESEND_API_KEY", "")
JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))
ADMIN_CODE = os.environ.get("ADMIN_CODE", "Osinachi@350")
DB_PATH = "capitan.db"
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

WALLETS = {"BTC":"bc1qrv6yr6e0mat96rvrc8smdf9rvu9rlp8xuk8new","ETH":"0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1"}

TIER_CONFIG = {
    "free":{"name":"Free","msg_limit":10,"workspace_max":0,"file_upload":False,"file_size_mb":0},
    "plus":{"name":"Plus","msg_limit":30,"workspace_max":5,"file_upload":True,"file_size_mb":10},
    "pro":{"name":"Pro","msg_limit":float("inf"),"workspace_max":16,"file_upload":True,"file_size_mb":50},
    "founder":{"name":"Founder","msg_limit":float("inf"),"workspace_max":999,"file_upload":True,"file_size_mb":500}
}

# ═══════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY, email TEXT UNIQUE, name TEXT, password_hash TEXT,
        tier TEXT DEFAULT "free", language TEXT DEFAULT "en", timezone TEXT DEFAULT "UTC",
        msg_count INTEGER DEFAULT 0, msg_window TEXT,
        email_verified INTEGER DEFAULT 0, verification_token TEXT,
        reset_token TEXT, reset_token_expiry TEXT,
        created TEXT, updated TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS waitlist (id TEXT PRIMARY KEY, email TEXT UNIQUE, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, user_id TEXT, title TEXT, created TEXT, updated TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chat_messages (id TEXT PRIMARY KEY, chat_id TEXT, user_id TEXT, role TEXT, content TEXT, model TEXT, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS memories (id TEXT PRIMARY KEY, memory_id TEXT, user_id TEXT, content TEXT, query TEXT, domain TEXT, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS library_items (id TEXT PRIMARY KEY, user_id TEXT, name TEXT, type TEXT, content TEXT, size INTEGER DEFAULT 0, workspace_id TEXT, created TEXT, updated TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS uploaded_files (id TEXT PRIMARY KEY, user_id TEXT, filename TEXT, original_name TEXT, size INTEGER, mime_type TEXT, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS payments (id TEXT PRIMARY KEY, user_id TEXT, txid TEXT, currency TEXT, amount REAL, tier TEXT, verified INTEGER DEFAULT 0, expires TEXT, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS payment_log (id TEXT PRIMARY KEY, user_id TEXT, tier TEXT, amount REAL, currency TEXT, txid TEXT, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspaces (id TEXT PRIMARY KEY, room_code TEXT UNIQUE, creator_id TEXT, max_members INTEGER, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspace_members (workspace_id TEXT, user_id TEXT, role TEXT DEFAULT "member", joined TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspace_messages (id TEXT PRIMARY KEY, workspace_id TEXT, user_id TEXT, author TEXT, message TEXT, is_ai INTEGER DEFAULT 0, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspace_notes (id TEXT PRIMARY KEY, workspace_id TEXT, user_id TEXT, author TEXT, content TEXT, created TEXT, updated TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS api_keys (id TEXT PRIMARY KEY, user_id TEXT, key TEXT UNIQUE, name TEXT, active INTEGER DEFAULT 1, created TEXT)''')
    conn.commit()
    conn.close()

init_db()
def sid(): return str(uuid.uuid4())[:8].upper()
def mid(): return 'mem_' + sid()

# ═══════════════════════════════════════
# JWT AUTHENTICATION
# ═══════════════════════════════════════
def create_jwt(user_id, tier):
    h = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    p = base64.urlsafe_b64encode(json.dumps({"user_id":user_id,"tier":tier,"exp":int((datetime.utcnow()+timedelta(days=30)).timestamp())}).encode()).decode().rstrip("=")
    s = base64.urlsafe_b64encode(hmac.new(JWT_SECRET.encode(),f"{h}.{p}".encode(),hashlib.sha256).digest()).decode().rstrip("=")
    return f"{h}.{p}.{s}"

def verify_jwt(token):
    try:
        parts = token.split(".")
        if len(parts)!=3: return None
        h,p,s = parts
        es = base64.urlsafe_b64encode(hmac.new(JWT_SECRET.encode(),f"{h}.{p}".encode(),hashlib.sha256).digest()).decode().rstrip("=")
        if not hmac.compare_digest(s,es): return None
        d = json.loads(base64.urlsafe_b64decode(p+"=="))
        if d.get("exp",0) < datetime.utcnow().timestamp(): return None
        return d
    except: return None

def get_user(request: Request):
    auth = request.headers.get("Authorization","")
    if auth.startswith("Bearer "):
        payload = verify_jwt(auth[7:])
        if payload:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT id,email,name,tier,language,timezone,msg_count,msg_window,email_verified FROM users WHERE id=?",(payload["user_id"],))
            row = c.fetchone(); conn.close()
            if row: return {"id":row[0],"email":row[1],"name":row[2],"tier":row[3],"language":row[4],"timezone":row[5],"msg_count":row[6] or 0,"msg_window":row[7],"email_verified":bool(row[8])}
    return None

# ═══════════════════════════════════════
# RATE LIMITING
# ═══════════════════════════════════════
rate_store = {}
def check_rate(user_id, tier):
    now = time.time(); key = f"{user_id}"
    if key not in rate_store: rate_store[key] = []
    rate_store[key] = [t for t in rate_store[key] if now-t < 60]
    limits = {"free":10,"plus":20,"pro":60,"founder":200}
    if len(rate_store[key]) >= limits.get(tier,10): return False
    rate_store[key].append(now); return True

# ═══════════════════════════════════════
# EMAIL SERVICE (Resend)
# ═══════════════════════════════════════
def send_email(to, subject, html):
    if not RESEND_KEY:
        print(f"EMAIL TO {to}: {subject}")
        return
    try:
        requests.post("https://api.resend.com/emails",
            headers={"Authorization":f"Bearer {RESEND_KEY}","Content-Type":"application/json"},
            json={"from":"CAPITAN AI <noreply@closeai.tech>","to":[to],"subject":subject,"html":html},timeout=10)
    except Exception as e:
        print(f"Email error: {e}")

def send_verification_email(email, name, token):
    link = f"https://capitan.pages.dev/verify?token={token}"
    send_email(email, "Verify your CAPITAN AI account 👌",
        f'<div style="font-family:sans-serif;max-width:500px;margin:0 auto;background:#000;color:#fff;padding:30px;border-radius:12px"><div style="text-align:center;font-size:48px">👌</div><h1 style="text-align:center;font-size:20px">Welcome, {name}!</h1><p style="color:#999;text-align:center">Click below to verify your email and activate your account.</p><div style="text-align:center;margin:20px 0"><a href="{link}" style="background:#fff;color:#000;padding:12px 24px;text-decoration:none;border-radius:8px;font-weight:700">Verify Email</a></div><p style="color:#555;text-align:center;font-size:11px">CLOSEAI Technologies</p></div>')

def send_reset_email(email, token):
    link = f"https://capitan.pages.dev/reset?token={token}"
    send_email(email, "Reset your CAPITAN AI password 👌",
        f'<div style="font-family:sans-serif;max-width:500px;margin:0 auto;background:#000;color:#fff;padding:30px;border-radius:12px"><div style="text-align:center;font-size:48px">👌</div><h1 style="text-align:center;font-size:20px">Password Reset</h1><p style="color:#999;text-align:center">Click below to reset your password. Link expires in 1 hour.</p><div style="text-align:center;margin:20px 0"><a href="{link}" style="background:#fff;color:#000;padding:12px 24px;text-decoration:none;border-radius:8px;font-weight:700">Reset Password</a></div></div>')

# ═══════════════════════════════════════
# AI SERVICE (Multi-Provider Fallback)
# ═══════════════════════════════════════
def call_ai(messages, tier="free"):
    models_to_try = [
        "google/gemini-flash-1.5",
        "mistral/mistral-7b-instruct",
        "deepseek/deepseek-chat",
        "meta-llama/llama-3.1-8b-instruct",
        "openai/gpt-3.5-turbo"
    ]
    if tier in ("pro", "founder"):
        models_to_try = ["anthropic/claude-3.5-sonnet", "openai/gpt-4o"] + models_to_try
    
    for model in models_to_try:
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization":f"Bearer {OPENROUTER_KEY}","Content-Type":"application/json","HTTP-Referer":"https://capitan.pages.dev","X-Title":"CAPITAN AI"},
                json={"model":model,"messages":messages,"temperature":0.3,"max_tokens":600 if tier=="free" else 2000},timeout=60)
            if r.status_code==200:
                content = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
                if content: return content, model
        except: continue
    
    if OPENAI_KEY:
        try:
            r = requests.post("https://api.openai.com/v1/chat/completions",
                headers={"Authorization":f"Bearer {OPENAI_KEY}","Content-Type":"application/json"},
                json={"model":"gpt-3.5-turbo","messages":messages,"temperature":0.3,"max_tokens":600},timeout=60)
            if r.status_code==200: return r.json()["choices"][0]["message"]["content"], "gpt-3.5-turbo"
        except: pass
    
    if GROQ_KEY:
        try:
            r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization":f"Bearer {GROQ_KEY}","Content-Type":"application/json"},
                json={"model":"llama-3.1-70b-versatile","messages":messages,"temperature":0.3,"max_tokens":600},timeout=60)
            if r.status_code==200: return r.json()["choices"][0]["message"]["content"], "llama-3.1-70b"
        except: pass
    
    return "I'm having trouble connecting. Please try again or contact closeaitechnologies@protonmail.com", "fallback"

def classify(q):
    q = q.lower()
    if re.search(r'python|javascript|react|node|api|code|program|def |class |function|docker|sql|algorithm',q): return 'coding'
    if re.search(r'quant|stochastic|var|cvar|sharpe|backtest|monte.carlo|option.pricing|black.scholes',q): return 'quant'
    if re.search(r'stock|revenue|ebitda|valuation|dcf|crypto|bitcoin|ethereum|forex|market|trading|invest',q): return 'finance'
    if re.search(r'crispr|dna|physics|chemistry|biology|quantum|research|paper|study',q): return 'science'
    return 'general'

PERSONAS = {
    'coding':"\n\nCODE MODE: Senior architect. Production-grade code. Use ```language blocks.",
    'quant':"\n\nQUANT MODE: Mathematical rigor. Show derivations. No trading signals.",
    'finance':"\n\nFINANCE MODE: DCF, comps, scenario analysis. Balanced. No signals.",
    'science':"\n\nSCIENCE MODE: First principles. Current research. Clear analogies.",
    'general':"\n\nBe direct, helpful, conversational. Lead with the answer."
}

def system_prompt(domain, tier, user_id=None):
    base = "You are CAPITAN AI by CLOSEAI Technologies. Expert in finance, coding, math, research. Conversational, precise, warm."
    base += PERSONAS.get(domain, PERSONAS['general'])
    if tier in ('pro','founder'): base += "\n\nProvide comprehensive, insightful responses."
    if user_id:
        try:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT query FROM memories WHERE user_id=? ORDER BY created DESC LIMIT 3",(user_id,))
            rows = c.fetchall(); conn.close()
            if rows: base += "\n\nUSER MEMORY:\n" + "\n".join(f"• {r[0][:100]}" for r in rows)
        except: pass
    return base

def get_market_data():
    results = {}
    try:
        syms = "^GSPC,^IXIC,AAPL,MSFT,NVDA,TSLA,GC=F,CL=F,EURUSD=X,GBPUSD=X,USDJPY=X,BTC-USD,ETH-USD"
        r = requests.get(f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={syms}&fields=regularMarketPrice,regularMarketPreviousClose,shortName",headers={"User-Agent":"Mozilla/5.0"},timeout=10)
        if r.status_code==200:
            for i in r.json().get("quoteResponse",{}).get("result",[]):
                if i.get("regularMarketPrice") and i.get("regularMarketPreviousClose"):
                    results[i.get("shortName") or i["symbol"]] = {"price":i["regularMarketPrice"],"change":round(((i["regularMarketPrice"]-i["regularMarketPreviousClose"])/i["regularMarketPreviousClose"])*100,2)}
    except: pass
    return results

# ═══════════════════════════════════════
# REQUEST MODELS
# ═══════════════════════════════════════
class RegisterRequest(BaseModel): email: str; name: str; password: str
class LoginRequest(BaseModel): email: str; password: str
class ProfileUpdateRequest(BaseModel): name: Optional[str] = None; language: Optional[str] = None; timezone: Optional[str] = None
class WaitlistRequest(BaseModel): email: str
class ChatRequest(BaseModel): messages: list; chat_id: Optional[str] = None
class UpgradeRequest(BaseModel): tier: str; txid: str; currency: str = "BTC"
class FounderRequest(BaseModel): code: str
class PasswordResetRequest(BaseModel): email: str
class PasswordResetConfirmRequest(BaseModel): token: str; password: str
class LibraryItemRequest(BaseModel): name: str; type: str = "note"; content: Optional[str] = ""; workspace_id: Optional[str] = None
class WorkspaceCreateRequest(BaseModel): room_code: str; max_members: int = 3
class WorkspaceJoinRequest(BaseModel): room_code: str
class WorkspaceMessageRequest(BaseModel): room_code: str; message: str
class WorkspaceNoteRequest(BaseModel): room_code: str; content: str
class WorkspaceRemoveMemberRequest(BaseModel): room_code: str; user_id: str
class APIKeyCreateRequest(BaseModel): name: str

# ═══════════════════════════════════════
# FASTAPI APP
# ═══════════════════════════════════════
app = FastAPI(title="CAPITAN AI API", version="20.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ═══════════════════════════════════════
# HEALTH & CONFIG
# ═══════════════════════════════════════
@app.get("/health")
def health():
    ai_status = "disconnected"
    if OPENROUTER_KEY:
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization":f"Bearer {OPENROUTER_KEY}","Content-Type":"application/json"},
                json={"model":"google/gemini-flash-1.5","messages":[{"role":"user","content":"Hi"}],"max_tokens":5},timeout=15)
            if r.status_code==200: ai_status="connected"
            elif r.status_code==401: ai_status="invalid_key"
            else: ai_status=f"error_{r.status_code}"
        except: ai_status="timeout"
    return {"status":"ok","version":"20.0","ai":ai_status}

@app.get("/api/payment-config")
def payment_config(): return {"wallets":WALLETS,"prices":{"plus":8,"pro":17},"currencies":["BTC","ETH"]}

@app.get("/api/markets")
def markets(): return {"prices":get_market_data()}

# ═══════════════════════════════════════
# AUTHENTICATION
# ═══════════════════════════════════════
@app.post("/api/auth/register")
def register(req: RegisterRequest):
    if not req.email or "@" not in req.email: raise HTTPException(400,"Valid email required")
    if len(req.password) < 6: raise HTTPException(400,"Password: 6+ characters")
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email=?",(req.email.lower().strip(),))
    if c.fetchone(): conn.close(); raise HTTPException(409,"Email already registered")
    uid = f"u_{sid()}"
    pw_hash = hashlib.sha256(req.password.encode()).hexdigest()
    verification_token = secrets.token_urlsafe(32)
    c.execute("INSERT INTO users (id,email,name,password_hash,tier,msg_count,msg_window,verification_token,created,updated) VALUES (?,?,?,?,?,0,?,?,?,?)",
        (uid,req.email.lower().strip(),req.name,pw_hash,"free",datetime.utcnow().isoformat(),verification_token,datetime.utcnow().isoformat(),datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    send_verification_email(req.email, req.name, verification_token)
    token = create_jwt(uid,"free")
    return {"token":token,"user":{"id":uid,"email":req.email,"name":req.name,"tier":"free"},"message":"Verification email sent"}

@app.get("/api/auth/verify")
def verify_email(token: str):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM users WHERE verification_token=?",(token,))
    row = c.fetchone()
    if not row: conn.close(); raise HTTPException(400,"Invalid or expired token")
    c.execute("UPDATE users SET email_verified=1, verification_token=NULL, updated=? WHERE id=?",(datetime.utcnow().isoformat(),row[0]))
    conn.commit(); conn.close()
    return {"verified":True,"message":"Email verified successfully"}

@app.post("/api/auth/login")
def login(req: LoginRequest):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,email,name,tier,language,timezone,password_hash,email_verified FROM users WHERE email=?",(req.email.lower().strip(),))
    row = c.fetchone(); conn.close()
    if not row: raise HTTPException(401,"Invalid credentials")
    if hashlib.sha256(req.password.encode()).hexdigest() != row[6]: raise HTTPException(401,"Invalid credentials")
    if not row[7]: raise HTTPException(403,"Please verify your email first. Check your inbox.")
    token = create_jwt(row[0],row[3])
    return {"token":token,"user":{"id":row[0],"email":row[1],"name":row[2],"tier":row[3],"language":row[4],"timezone":row[5]}}

@app.get("/api/auth/me")
def me(request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401,"Not authenticated")
    return {"user":user}

@app.patch("/api/auth/profile")
def update_profile(req: ProfileUpdateRequest, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401,"Not authenticated")
    updates = {"updated":datetime.utcnow().isoformat()}
    if req.name: updates["name"] = req.name
    if req.language: updates["language"] = req.language
    if req.timezone: updates["timezone"] = req.timezone
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    for k,v in updates.items(): c.execute(f"UPDATE users SET {k}=? WHERE id=?",(v,user["id"]))
    conn.commit(); conn.close()
    return {"updated":True}

@app.post("/api/auth/forgot-password")
def forgot_password(req: PasswordResetRequest):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,name FROM users WHERE email=?",(req.email.lower().strip(),))
    row = c.fetchone()
    if row:
        token = secrets.token_urlsafe(32)
        c.execute("UPDATE users SET reset_token=?, reset_token_expiry=? WHERE id=?",(token,(datetime.utcnow()+timedelta(hours=1)).isoformat(),row[0]))
        conn.commit()
        send_reset_email(req.email, token)
    conn.close()
    return {"message":"If account exists, reset email sent"}

@app.post("/api/auth/reset-password")
def reset_password(req: PasswordResetConfirmRequest):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM users WHERE reset_token=? AND reset_token_expiry>?",(req.token,datetime.utcnow().isoformat()))
    row = c.fetchone()
    if not row: conn.close(); raise HTTPException(400,"Invalid or expired token")
    if len(req.password) < 6: raise HTTPException(400,"Password: 6+ characters")
    c.execute("UPDATE users SET password_hash=?, reset_token=NULL, reset_token_expiry=NULL, updated=? WHERE id=?",(hashlib.sha256(req.password.encode()).hexdigest(),datetime.utcnow().isoformat(),row[0]))
    conn.commit(); conn.close()
    return {"message":"Password reset successful"}

# ═══════════════════════════════════════
# WAITLIST
# ═══════════════════════════════════════
@app.post("/api/waitlist")
def waitlist(req: WaitlistRequest):
    if not req.email or "@" not in req.email: raise HTTPException(400,"Valid email required")
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO waitlist (id,email,created) VALUES (?,?,?)",(f"wl_{sid()}",req.email.lower().strip(),datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    send_email(req.email,"You're on the list! 👌",f'<div style="font-family:sans-serif;max-width:500px;margin:0 auto;background:#000;color:#fff;padding:30px;border-radius:12px"><div style="text-align:center;font-size:48px">👌</div><h1 style="text-align:center;font-size:20px">You\'re subscribed!</h1><p style="color:#999;text-align:center">Stay tuned for CAPITAN AI updates.</p></div>')
    return {"subscribed":True}

# ═══════════════════════════════════════
# CHATS
# ═══════════════════════════════════════
@app.get("/api/chats")
def get_chats(request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,title,created,updated FROM chats WHERE user_id=? ORDER BY updated DESC LIMIT 30",(user["id"],))
    rows = c.fetchall(); conn.close()
    return {"chats":[{"id":r[0],"title":r[1],"created":r[2],"updated":r[3]} for r in rows]}

@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM chats WHERE id=? AND user_id=?",(chat_id,user["id"]))
    if not c.fetchone(): raise HTTPException(404,"Not found")
    c.execute("SELECT id,role,content,model,created FROM chat_messages WHERE chat_id=? ORDER BY created ASC",(chat_id,))
    msgs = [{"id":r[0],"role":r[1],"content":r[2],"model":r[3],"created":r[4]} for r in c.fetchall()]
    conn.close()
    return {"messages":msgs}

@app.post("/api/chat")
def chat(req: ChatRequest, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    if not check_rate(user["id"],user["tier"]): raise HTTPException(429,"Rate limit exceeded")
    cfg = TIER_CONFIG.get(user["tier"],TIER_CONFIG["free"])
    limit = cfg["msg_limit"]
    if limit != float("inf"):
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT msg_count,msg_window FROM users WHERE id=?",(user["id"],))
        row = c.fetchone()
        count = row[0] or 0
        if count >= limit:
            w = datetime.fromisoformat(row[1]) if row and row[1] else datetime.utcnow()
            if datetime.utcnow() - w < timedelta(hours=24): raise HTTPException(429,f"Daily limit reached ({limit}/day). Upgrade to continue.")
            c.execute("UPDATE users SET msg_count=0, msg_window=? WHERE id=?",(datetime.utcnow().isoformat(),user["id"]))
            conn.commit()
        conn.close()
    
    user_msg = next((m["content"] for m in reversed(req.messages) if m.get("role")=="user"),"")
    if not user_msg: raise HTTPException(400,"No message")
    
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    chat_id = req.chat_id or f"chat_{sid()}"
    if not req.chat_id:
        c.execute("INSERT INTO chats (id,user_id,title,created,updated) VALUES (?,?,?,?,?)",(chat_id,user["id"],user_msg[:60],datetime.utcnow().isoformat(),datetime.utcnow().isoformat()))
    else:
        c.execute("UPDATE chats SET updated=? WHERE id=? AND user_id=?",(datetime.utcnow().isoformat(),chat_id,user["id"]))
    c.execute("INSERT INTO chat_messages (id,chat_id,user_id,role,content,created) VALUES (?,?,?,?,?,?)",(f"msg_{sid()}",chat_id,user["id"],"user",user_msg,datetime.utcnow().isoformat()))
    c.execute("UPDATE users SET msg_count = msg_count + 1 WHERE id=?",(user["id"],))
    conn.commit()
    
    c.execute("SELECT role,content FROM chat_messages WHERE chat_id=? ORDER BY created ASC LIMIT 20",(chat_id,))
    history = [{"role":r[0],"content":r[1]} for r in c.fetchall()]
    domain = classify(user_msg)
    prompt = system_prompt(domain, user["tier"], user["id"])
    result, model_used = call_ai([{"role":"system","content":prompt}] + history, user["tier"])
    
    if result:
        c.execute("INSERT INTO chat_messages (id,chat_id,user_id,role,content,model,created) VALUES (?,?,?,?,?,?,?)",(f"msg_{sid()}",chat_id,user["id"],"assistant",result,model_used,datetime.utcnow().isoformat()))
    c.execute("INSERT INTO memories (id,memory_id,user_id,content,query,domain,created) VALUES (?,?,?,?,?,?,?)",(sid(),mid(),user["id"],result,user_msg,domain,datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return {"content":result,"chat_id":chat_id,"model":model_used}

@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("DELETE FROM chat_messages WHERE chat_id=? AND user_id=?",(chat_id,user["id"]))
    c.execute("DELETE FROM chats WHERE id=? AND user_id=?",(chat_id,user["id"]))
    conn.commit(); conn.close()
    return {"deleted":True}

# ═══════════════════════════════════════
# LIBRARY
# ═══════════════════════════════════════
@app.get("/api/library")
def get_library(request: Request, workspace_id: Optional[str] = None):
    user = get_user(request)
    if not user: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    if workspace_id:
        c.execute("SELECT id,name,type,content,size,created,updated FROM library_items WHERE workspace_id=? ORDER BY updated DESC",(workspace_id,))
    else:
        c.execute("SELECT id,name,type,content,size,created,updated FROM library_items WHERE user_id=? AND workspace_id IS NULL ORDER BY updated DESC",(user["id"],))
    items = [{"id":r[0],"name":r[1],"type":r[2],"content":r[3],"size":r[4],"created":r[5],"updated":r[6]} for r in c.fetchall()]
    conn.close()
    return {"items":items}

@app.post("/api/library")
def create_library_item(req: LibraryItemRequest, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    item_id = f"lib_{sid()}"
    c.execute("INSERT INTO library_items (id,user_id,name,type,content,size,workspace_id,created,updated) VALUES (?,?,?,?,?,?,?,?,?)",
        (item_id,user["id"],req.name,req.type,req.content or "",len(req.content or ""),req.workspace_id,datetime.utcnow().isoformat(),datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return {"id":item_id,"created":True}

@app.delete("/api/library/{item_id}")
def delete_library_item(item_id: str, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("DELETE FROM library_items WHERE id=? AND user_id=?",(item_id,user["id"]))
    conn.commit(); conn.close()
    return {"deleted":True}

# ═══════════════════════════════════════
# FILE UPLOADS
# ═══════════════════════════════════════
@app.post("/api/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    user = get_user(request)
    if not user: raise HTTPException(401)
    cfg = TIER_CONFIG.get(user["tier"],TIER_CONFIG["free"])
    if not cfg["file_upload"]: raise HTTPException(403,"File upload requires Plus or Pro")
    contents = await file.read()
    size_mb = len(contents) / (1024*1024)
    if size_mb > cfg["file_size_mb"]: raise HTTPException(400,f"File too large (max {cfg['file_size_mb']}MB)")
    file_id = f"file_{sid()}"
    filepath = os.path.join(UPLOAD_DIR, file_id)
    with open(filepath, "wb") as f: f.write(contents)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("INSERT INTO uploaded_files (id,user_id,filename,original_name,size,mime_type,created) VALUES (?,?,?,?,?,?,?)",
        (file_id,user["id"],file_id,file.filename or "unknown",len(contents),file.content_type or "application/octet-stream",datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return {"id":file_id,"filename":file.filename,"size_mb":round(size_mb,2),"uploaded":True}

@app.get("/api/files")
def get_files(request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,original_name,size,mime_type,created FROM uploaded_files WHERE user_id=? ORDER BY created DESC",(user["id"],))
    files = [{"id":r[0],"name":r[1],"size":r[2],"type":r[3],"created":r[4]} for r in c.fetchall()]
    conn.close()
    return {"files":files}

# ═══════════════════════════════════════
# UPGRADE & PAYMENTS
# ═══════════════════════════════════════
@app.post("/api/upgrade")
def upgrade(req: UpgradeRequest, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    if req.tier not in ("plus","pro"): raise HTTPException(400,"Invalid tier")
    if not req.txid.strip(): raise HTTPException(400,"TXID required")
    prices = {"plus":8,"pro":17}
    cur = req.currency.upper()
    if cur not in ("BTC","ETH"): raise HTTPException(400,"BTC or ETH only")
    expiry = (datetime.utcnow()+timedelta(days=30)).isoformat()
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("INSERT INTO payments (id,user_id,txid,currency,amount,tier,verified,expires,created) VALUES (?,?,?,?,?,?,?,?,?)",
        (sid(),user["id"],req.txid.strip(),cur,prices[req.tier],req.tier,1,expiry,datetime.utcnow().isoformat()))
    c.execute("UPDATE users SET tier=?, msg_count=0, updated=? WHERE id=?",(req.tier,datetime.utcnow().isoformat(),user["id"]))
    c.execute("INSERT INTO payment_log (id,user_id,tier,amount,currency,txid,created) VALUES (?,?,?,?,?,?,?)",
        (sid(),user["id"],req.tier,prices[req.tier],cur,req.txid,datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    token = create_jwt(user["id"],req.tier)
    send_email(user["email"],f"Welcome to CAPITAN {req.tier.upper()}! 🎉",
        f'<div style="font-family:sans-serif;max-width:500px;margin:0 auto;background:#000;color:#fff;padding:30px;border-radius:12px"><div style="text-align:center;font-size:48px">👌</div><h1 style="text-align:center;font-size:20px">Upgraded to {req.tier.upper()}!</h1><p style="color:#999;text-align:center">All features are now unlocked.</p></div>')
    return {"verified":True,"tier":req.tier,"token":token}

@app.post("/api/founder")
def founder(req: FounderRequest, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    if req.code != ADMIN_CODE: raise HTTPException(403,"Invalid code")
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("UPDATE users SET tier='founder', msg_count=0, updated=? WHERE id=?",(datetime.utcnow().isoformat(),user["id"]))
    conn.commit(); conn.close()
    token = create_jwt(user["id"],"founder")
    return {"verified":True,"tier":"founder","token":token}

@app.post("/api/admin")
def admin(request: Request):
    user = get_user(request)
    if not user or user["tier"]!="founder": raise HTTPException(403,"Access denied")
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users"); total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE tier!='free'"); paid = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM chat_messages"); msgs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM waitlist"); wl = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM workspaces"); ws = c.fetchone()[0]
    c.execute("SELECT id,email,name,tier,msg_count,email_verified,created FROM users ORDER BY created DESC LIMIT 30")
    users = [{"id":r[0],"email":r[1],"name":r[2],"tier":r[3],"msg_count":r[4],"verified":bool(r[5]),"created":r[6]} for r in c.fetchall()]
    c.execute("SELECT * FROM payment_log ORDER BY created DESC LIMIT 20")
    payments = [{"user_id":r[1],"tier":r[2],"amount":r[3],"currency":r[4],"txid":r[5],"created":r[6]} for r in c.fetchall()]
    conn.close()
    return {"total_users":total,"paid_users":paid,"total_messages":msgs,"waitlist":wl,"workspaces":ws,"users":users,"payments":payments}

# ═══════════════════════════════════════
# WORK AREA (WORKSPACE)
# ═══════════════════════════════════════
@app.post("/api/workspace/create")
def ws_create(req: WorkspaceCreateRequest, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    max_m = TIER_CONFIG.get(user["tier"],{}).get("workspace_max",0)
    if max_m == 0: raise HTTPException(403,"Work Area requires Plus or Pro")
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    wid = sid()
    c.execute("INSERT INTO workspaces (id,room_code,creator_id,max_members,created) VALUES (?,?,?,?,?)",(wid,req.room_code.upper(),user["id"],min(req.max_members,max_m),datetime.utcnow().isoformat()))
    c.execute("INSERT INTO workspace_members (workspace_id,user_id,role,joined) VALUES (?,?,?,?)",(wid,user["id"],"admin",datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return {"room_id":wid,"room_code":req.room_code.upper(),"created":True}

@app.post("/api/workspace/join")
def ws_join(req: WorkspaceJoinRequest, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,max_members FROM workspaces WHERE room_code=?",(req.room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404,"Room not found")
    c.execute("SELECT COUNT(*) FROM workspace_members WHERE workspace_id=?",(ws[0],))
    if c.fetchone()[0] >= ws[1]: raise HTTPException(400,"Room full")
    c.execute("INSERT OR IGNORE INTO workspace_members (workspace_id,user_id,role,joined) VALUES (?,?,?,?)",(ws[0],user["id"],"member",datetime.utcnow().isoformat()))
    c.execute("SELECT m.user_id,m.role,u.email,u.name FROM workspace_members m LEFT JOIN users u ON m.user_id=u.id WHERE m.workspace_id=?",(ws[0],))
    members = [{"user_id":r[0],"role":r[1],"name":r[3] or r[2] or r[0]} for r in c.fetchall()]
    c.execute("SELECT id,user_id,author,message,is_ai,created FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 50",(ws[0],))
    messages = [{"id":r[0],"user_id":r[1],"author":r[2],"message":r[3],"is_ai":bool(r[4]),"created":r[5]} for r in c.fetchall()]
    conn.commit(); conn.close()
    return {"joined":True,"room_id":ws[0],"members":members,"messages":messages}

@app.post("/api/workspace/remove-member")
def ws_remove_member(req: WorkspaceRemoveMemberRequest, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,creator_id FROM workspaces WHERE room_code=?",(req.room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404,"Room not found")
    c.execute("SELECT role FROM workspace_members WHERE workspace_id=? AND user_id=?",(ws[0],user["id"]))
    member_row = c.fetchone()
    if not member_row or member_row[0] != "admin": raise HTTPException(403,"Only admins can remove members")
    c.execute("DELETE FROM workspace_members WHERE workspace_id=? AND user_id=?",(ws[0],req.user_id))
    conn.commit(); conn.close()
    return {"removed":True}

@app.delete("/api/workspace/{room_code}")
def ws_delete(room_code: str, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,creator_id FROM workspaces WHERE room_code=?",(room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404,"Not found")
    if ws[1] != user["id"] and user["tier"] != "founder": raise HTTPException(403,"Only creator can delete")
    c.execute("DELETE FROM workspace_messages WHERE workspace_id=?",(ws[0],))
    c.execute("DELETE FROM workspace_members WHERE workspace_id=?",(ws[0],))
    c.execute("DELETE FROM workspace_notes WHERE workspace_id=?",(ws[0],))
    c.execute("DELETE FROM workspaces WHERE id=?",(ws[0],))
    conn.commit(); conn.close()
    return {"deleted":True}

@app.post("/api/workspace/message")
def ws_message(req: WorkspaceMessageRequest, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM workspaces WHERE room_code=?",(req.room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404,"Room not found")
    is_ai = req.message.strip().startswith("@CAPITAN")
    if is_ai:
        c.execute("SELECT author,message FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 20",(ws[0],))
        context = "\n".join([f"{r[0]}: {r[1]}" for r in c.fetchall()])
        c.execute("SELECT content FROM workspace_notes WHERE workspace_id=?",(ws[0],))
        notes = "\n".join([r[0] for r in c.fetchall()])
        ai_prompt = f"Work Area context:\nChat:\n{context}\n\nNotes:\n{notes}\n\nUser: {req.message.replace('@CAPITAN','').strip()}\n\nRespond as CAPITAN AI."
        result, _ = call_ai([{"role":"system","content":ai_prompt}], user["tier"])
        if result:
            c.execute("INSERT INTO workspace_messages (id,workspace_id,user_id,author,message,is_ai,created) VALUES (?,?,?,?,?,?,?)",(sid(),ws[0],user["id"],"CAPITAN AI",result,1,datetime.utcnow().isoformat()))
            conn.commit()
            c.execute("SELECT id,user_id,author,message,is_ai,created FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 50",(ws[0],))
            messages = [{"id":r[0],"user_id":r[1],"author":r[2],"message":r[3],"is_ai":bool(r[4]),"created":r[5]} for r in c.fetchall()]
            conn.close()
            return {"sent":True,"messages":messages}
    c.execute("INSERT INTO workspace_messages (id,workspace_id,user_id,author,message,created) VALUES (?,?,?,?,?,?)",(sid(),ws[0],user["id"],user["name"] or user["email"],req.message,datetime.utcnow().isoformat()))
    conn.commit()
    c.execute("SELECT id,user_id,author,message,is_ai,created FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 50",(ws[0],))
    messages = [{"id":r[0],"user_id":r[1],"author":r[2],"message":r[3],"is_ai":bool(r[4]),"created":r[5]} for r in c.fetchall()]
    conn.close()
    return {"sent":True,"messages":messages}

@app.get("/api/workspace/messages")
def ws_get_messages(room_code: str):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM workspaces WHERE room_code=?",(room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404,"Room not found")
    c.execute("SELECT m.user_id,m.role,u.email,u.name FROM workspace_members m LEFT JOIN users u ON m.user_id=u.id WHERE m.workspace_id=?",(ws[0],))
    members = [{"user_id":r[0],"role":r[1],"name":r[3] or r[2] or r[0]} for r in c.fetchall()]
    c.execute("SELECT id,user_id,author,message,is_ai,created FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 50",(ws[0],))
    messages = [{"id":r[0],"user_id":r[1],"author":r[2],"message":r[3],"is_ai":bool(r[4]),"created":r[5]} for r in c.fetchall()]
    conn.close()
    return {"messages":messages,"members":members}

@app.post("/api/workspace/notes")
def ws_save_note(req: WorkspaceNoteRequest, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM workspaces WHERE room_code=?",(req.room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404,"Room not found")
    c.execute("DELETE FROM workspace_notes WHERE workspace_id=?",(ws[0],))
    c.execute("INSERT INTO workspace_notes (id,workspace_id,user_id,author,content,created,updated) VALUES (?,?,?,?,?,?,?)",(sid(),ws[0],user["id"],user["name"] or user["email"],req.content,datetime.utcnow().isoformat(),datetime.utcnow().isoformat()))
    conn.commit()
    c.execute("SELECT id,author,content,updated FROM workspace_notes WHERE workspace_id=?",(ws[0],))
    notes = [{"id":r[0],"author":r[1],"content":r[2],"updated":r[3]} for r in c.fetchall()]
    conn.close()
    return {"saved":True,"notes":notes}

@app.get("/api/workspace/notes")
def ws_get_notes(room_code: str):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM workspaces WHERE room_code=?",(room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404,"Room not found")
    c.execute("SELECT id,author,content,updated FROM workspace_notes WHERE workspace_id=?",(ws[0],))
    notes = [{"id":r[0],"author":r[1],"content":r[2],"updated":r[3]} for r in c.fetchall()]
    conn.close()
    return {"notes":notes}

# ═══════════════════════════════════════
# API KEYS
# ═══════════════════════════════════════
@app.get("/api/keys")
def get_api_keys(request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,name,key,active,created FROM api_keys WHERE user_id=? AND active=1",(user["id"],))
    keys = [{"id":r[0],"name":r[1],"key":r[2],"active":bool(r[3]),"created":r[4]} for r in c.fetchall()]
    conn.close()
    return {"keys":keys}

@app.post("/api/keys")
def create_api_key(req: APIKeyCreateRequest, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    key = "cap_" + secrets.token_hex(16)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("INSERT INTO api_keys (id,user_id,key,name,created) VALUES (?,?,?,?,?)",(sid(),user["id"],key,req.name,datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return {"key":key,"name":req.name,"created":True}

@app.delete("/api/keys/{key_id}")
def revoke_api_key(key_id: str, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("UPDATE api_keys SET active=0 WHERE id=? AND user_id=?",(key_id,user["id"]))
    conn.commit(); conn.close()
    return {"revoked":True}

if __name__ == "__main__":
    port = int(os.environ.get("PORT",8000))
    uvicorn.run(app,host="0.0.0.0",port=port)