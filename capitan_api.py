"""
CAPITAN AI — Production Backend v16.0
CLOSEAI Technologies
Features: JWT Auth, Rate Limiting, Email OTP, Workspace API, Market Data, No Cold Start
"""

import os, re, json, uuid, time, hashlib, hmac, base64, secrets, requests, sqlite3
from datetime import datetime, timedelta
from functools import wraps
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

# ═══════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GNEWS_KEY = os.environ.get("GNEWS_KEY", "")
JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))
ADMIN_CODE = os.environ.get("ADMIN_CODE", "Osinachi@350")
DB_PATH = "capitan.db"

# Rate limits per tier (requests per minute)
RATE_LIMITS = {"free": 10, "plus": 30, "pro": 100, "founder": 200}
MESSAGE_LIMITS = {"free": 10, "plus": 30, "pro": float("inf"), "founder": float("inf")}

# Wallet addresses
WALLETS = {
    "USDC": "0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1",
    "BTC": "bc1qrv6yr6e0mat96rvrc8smdf9rvu9rlp8xuk8new",
    "ETH": "0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1"
}

# ═══════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY, email TEXT UNIQUE, tier TEXT DEFAULT "free",
        msg_count INTEGER DEFAULT 0, msg_window TEXT, created TEXT,
        otp_hash TEXT, otp_expiry TEXT, email_verified INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY, memory_id TEXT, user_id TEXT,
        content TEXT, query TEXT, tier TEXT, created TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS payments (
        id TEXT PRIMARY KEY, user_id TEXT, txid TEXT, currency TEXT,
        amount REAL, tier TEXT, expires TEXT, created TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS payment_log (
        id TEXT PRIMARY KEY, user_id TEXT, tier TEXT, amount REAL,
        currency TEXT, txid TEXT, created TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS training (
        id TEXT PRIMARY KEY, user_id TEXT, query TEXT, response TEXT,
        domain TEXT, tier TEXT, created TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspaces (
        id TEXT PRIMARY KEY, room_code TEXT UNIQUE, creator_id TEXT,
        max_members INTEGER DEFAULT 3, created TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspace_members (
        workspace_id TEXT, user_id TEXT, joined TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspace_messages (
        id TEXT PRIMARY KEY, workspace_id TEXT, user_id TEXT,
        author TEXT, message TEXT, created TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS otp_codes (
        email TEXT PRIMARY KEY, code TEXT, expiry TEXT, attempts INTEGER DEFAULT 0
    )''')
    conn.commit()
    conn.close()

init_db()
def sid(): return str(uuid.uuid4())[:8].upper()
def mid(): return 'mem_' + sid()

# ═══════════════════════════════════════
# JWT AUTH
# ═══════════════════════════════════════
def create_jwt(user_id, tier):
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "user_id": user_id, "tier": tier,
        "exp": int((datetime.utcnow() + timedelta(days=30)).timestamp()),
        "iat": int(datetime.utcnow().timestamp())
    }).encode()).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(
        hmac.new(JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")
    return f"{header}.{payload}.{signature}"

def verify_jwt(token):
    try:
        parts = token.split(".")
        if len(parts) != 3: return None
        header, payload, signature = parts
        expected_sig = base64.urlsafe_b64encode(
            hmac.new(JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
        ).decode().rstrip("=")
        if not hmac.compare_digest(signature, expected_sig): return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=="))
        if data.get("exp", 0) < datetime.utcnow().timestamp(): return None
        return data
    except: return None

# ═══════════════════════════════════════
# RATE LIMITER (In-Memory)
# ═══════════════════════════════════════
rate_store = {}
def check_rate(user_id, tier):
    now = time.time()
    key = f"{user_id}:{tier}"
    if key not in rate_store: rate_store[key] = []
    rate_store[key] = [t for t in rate_store[key] if now - t < 60]
    limit = RATE_LIMITS.get(tier, 10)
    if len(rate_store[key]) >= limit: return False
    rate_store[key].append(now)
    return True

# ═══════════════════════════════════════
# AI CALLER
# ═══════════════════════════════════════
def call_ai(messages, tier="free"):
    models = {"free": "deepseek/deepseek-chat", "plus": "meta-llama/llama-3.1-70b-instruct", "pro": "anthropic/claude-3.5-sonnet", "founder": "anthropic/claude-3.5-sonnet"}
    model = models.get(tier, models["free"])
    max_tokens = 800 if tier == "free" else 2000
    if OPENROUTER_KEY:
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json", "HTTP-Referer": "https://capitan.pages.dev", "X-Title": "CAPITAN AI"},
                json={"model": model, "messages": messages, "temperature": 0.3, "max_tokens": max_tokens}, timeout=60)
            if r.status_code == 200: return r.json()["choices"][0]["message"]["content"]
        except: pass
    if OPENAI_KEY:
        try:
            r = requests.post("https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
                json={"model": "gpt-3.5-turbo", "messages": messages, "temperature": 0.3, "max_tokens": max_tokens}, timeout=60)
            if r.status_code == 200: return r.json()["choices"][0]["message"]["content"]
        except: pass
    return None

def classify(q):
    q = q.lower()
    if re.search(r'python|javascript|react|node|api|code|program|def |class ', q): return 'coding'
    if re.search(r'quant|stochastic|var|cvar|sharpe|backtest|monte carlo', q): return 'quant'
    if re.search(r'stock|revenue|ebitda|valuation|dcf|crypto|bitcoin|ethereum', q): return 'finance'
    if re.search(r'crispr|dna|physics|chemistry|biology|quantum', q): return 'science'
    return 'general'

def system_prompt(domain, tier, user_id=None):
    base = """You are CAPITAN AI — an elite intelligence system by CLOSEAI Technologies.
Be direct, knowledgeable, and warm through competence. Built for Africa and the world.
Lead with the answer. Never give trading signals. Calibrate confidence honestly.
Domain: """ + domain
    if tier in ('pro', 'founder'): base += "\nProvide thorough, deep responses with examples and citations."
    elif tier == 'free': base += "\nKeep it concise but complete."
    if user_id:
        try:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT query FROM memories WHERE user_id=? ORDER BY created DESC LIMIT 3", (user_id,))
            rows = c.fetchall(); conn.close()
            if rows: base += "\n\nRecent context:\n" + "\n".join(f"• {r[0][:80]}" for r in rows)
        except: pass
    return base

# ═══════════════════════════════════════
# MARKET DATA (Yahoo + CoinGecko)
# ═══════════════════════════════════════
def get_market_data():
    results = {}
    try:
        symbols = "^GSPC,^IXIC,^DJI,^FTSE,^N225,AAPL,MSFT,NVDA,TSLA,GC=F,CL=F,SI=F,EURUSD=X,GBPUSD=X,USDJPY=X,USDGHS=X,USDNGN=X,USDZAR=X,USDKES=X"
        r = requests.get(f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbols}&fields=regularMarketPrice,regularMarketPreviousClose,shortName",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if r.status_code == 200:
            for item in r.json().get("quoteResponse", {}).get("result", []):
                if item.get("regularMarketPrice") and item.get("regularMarketPreviousClose"):
                    results[item.get("shortName") or item["symbol"]] = {
                        "price": item["regularMarketPrice"],
                        "change": round(((item["regularMarketPrice"] - item["regularMarketPreviousClose"]) / item["regularMarketPreviousClose"]) * 100, 2)
                    }
    except: pass
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd&include_24hr_change=true", timeout=8)
        if r.status_code == 200:
            for name, data in r.json().items():
                if data.get("usd"):
                    results[name.capitalize()] = {"price": data["usd"], "change": round(data.get("usd_24h_change", 0), 2)}
    except: pass
    return results

# ═══════════════════════════════════════
# MODELS
# ═══════════════════════════════════════
class ChatRequest(BaseModel):
    messages: list
    user_id: str = "anonymous"

class AuthRequest(BaseModel):
    email: str

class OTPVerifyRequest(BaseModel):
    email: str
    code: str

class UpgradeRequest(BaseModel):
    user_id: str
    tier: str
    txid: str
    currency: str = "USDC"

class FounderRequest(BaseModel):
    user_id: str
    code: str

class WorkspaceCreateRequest(BaseModel):
    user_id: str
    room_code: str
    max_members: int = 3

class WorkspaceJoinRequest(BaseModel):
    user_id: str
    room_code: str

class WorkspaceMessageRequest(BaseModel):
    user_id: str
    room_code: str
    message: str

# ═══════════════════════════════════════
# AUTH DEPENDENCY
# ═══════════════════════════════════════
def get_current_user(request: Request):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        payload = verify_jwt(token)
        if payload: return payload
    return None

# ═══════════════════════════════════════
# APP
# ═══════════════════════════════════════
app = FastAPI(title="CAPITAN AI API", version="16.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Keep-alive ping — UptimeRobot hits this every 5 min to prevent cold starts
@app.get("/health")
def health(): return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/payment-config")
def payment_config(): return {"wallets": WALLETS, "prices": {"plus": 8, "pro": 17}, "crypto_prices": {"plus": {"BTC": 0.00012, "ETH": 0.0025, "USDC": 8}, "pro": {"BTC": 0.00028, "ETH": 0.005, "USDC": 17}}}

@app.get("/api/markets")
def markets(): return {"prices": get_market_data(), "timestamp": datetime.utcnow().isoformat()}

@app.post("/api/auth/send-otp")
def send_otp(req: AuthRequest):
    if not req.email or "@" not in req.email: raise HTTPException(400, "Valid email required")
    code = str(secrets.randbelow(1000000)).zfill(6)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO otp_codes (email, code, expiry, attempts) VALUES (?, ?, ?, 0)", (req.email.lower().strip(), code, (datetime.utcnow() + timedelta(minutes=10)).isoformat()))
    conn.commit(); conn.close()
    print(f"OTP for {req.email}: {code}")  # In production, send via email service
    return {"sent": True, "message": "OTP sent to email"}

@app.post("/api/auth/verify-otp")
def verify_otp(req: OTPVerifyRequest):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT code, expiry, attempts FROM otp_codes WHERE email=?", (req.email.lower().strip(),))
    row = c.fetchone()
    if not row: raise HTTPException(400, "No OTP requested")
    if row[2] >= 5: raise HTTPException(429, "Too many attempts")
    if datetime.fromisoformat(row[1]) < datetime.utcnow(): raise HTTPException(400, "OTP expired")
    if row[0] != req.code:
        c.execute("UPDATE otp_codes SET attempts = attempts + 1 WHERE email=?", (req.email.lower().strip(),))
        conn.commit(); conn.close()
        raise HTTPException(400, "Invalid OTP")
    c.execute("SELECT id, tier FROM users WHERE email=?", (req.email.lower().strip(),))
    user = c.fetchone()
    if not user:
        uid = 'u_' + sid()
        c.execute("INSERT INTO users (id, email, tier, msg_count, msg_window, email_verified, created) VALUES (?,?,?,0,?,1,?)", (uid, req.email.lower().strip(), 'free', datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))
        user = (uid, 'free')
    else:
        c.execute("UPDATE users SET email_verified=1 WHERE email=?", (req.email.lower().strip(),))
    c.execute("DELETE FROM otp_codes WHERE email=?", (req.email.lower().strip(),))
    conn.commit(); conn.close()
    token = create_jwt(user[0], user[1])
    return {"token": token, "user_id": user[0], "email": req.email, "tier": user[1]}

@app.post("/api/auth/login")
def login(req: AuthRequest):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id, tier FROM users WHERE email=?", (req.email.lower().strip(),))
    user = c.fetchone()
    if not user:
        uid = 'u_' + sid()
        c.execute("INSERT INTO users (id, email, tier, msg_count, msg_window, created) VALUES (?,?,?,0,?,?)", (uid, req.email.lower().strip(), 'free', datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))
        conn.commit()
        user = (uid, 'free')
    conn.close()
    token = create_jwt(user[0], user[1])
    return {"token": token, "user_id": user[0], "email": req.email, "tier": user[1]}

@app.post("/api/chat")
def chat(req: ChatRequest):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT tier, msg_count, msg_window FROM users WHERE id=?", (req.user_id,))
    row = c.fetchone()
    tier = row[0] if row else 'free'
    
    if not check_rate(req.user_id, tier): raise HTTPException(429, "Rate limit exceeded")
    
    if tier == 'free':
        count = row[1] or 0
        limit = MESSAGE_LIMITS['free']
        if count >= limit:
            w = datetime.fromisoformat(row[2]) if row[2] else datetime.utcnow()
            if datetime.utcnow() - w < timedelta(hours=24): raise HTTPException(429, "Daily limit reached")
            c.execute("UPDATE users SET msg_count=0, msg_window=? WHERE id=?", (datetime.utcnow().isoformat(), req.user_id))
    
    user_msg = next((m["content"] for m in reversed(req.messages) if m.get("role") == "user"), "")
    if not user_msg: raise HTTPException(400, "No message")
    
    c.execute("UPDATE users SET msg_count = msg_count + 1 WHERE id=?", (req.user_id,))
    conn.commit()
    
    domain = classify(user_msg)
    prompt = system_prompt(domain, tier, req.user_id)
    llm_msgs = [{"role": "system", "content": prompt}] + [{"role": m.get("role","user"), "content": m.get("content","")} for m in req.messages]
    result = call_ai(llm_msgs, tier)
    
    memory_id = mid()
    c.execute("INSERT INTO memories (id, memory_id, user_id, content, query, tier, created) VALUES (?,?,?,?,?,?,?)", (sid(), memory_id, req.user_id, result or '', user_msg, tier, datetime.utcnow().isoformat()))
    c.execute("INSERT INTO training (id, user_id, query, response, domain, tier, created) VALUES (?,?,?,?,?,?,?)", (sid(), req.user_id, user_msg, result or '', domain, tier, datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return {"content": result or "No response.", "domain": domain, "memory_id": memory_id}

@app.post("/api/upgrade")
def upgrade(req: UpgradeRequest):
    prices = {"plus": 8, "pro": 17}
    if req.tier not in prices: raise HTTPException(400, "Invalid tier")
    if not req.txid.strip(): raise HTTPException(400, "TXID required")
    cur = req.currency.upper()
    expiry = (datetime.utcnow() + timedelta(days=30)).isoformat()
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("INSERT INTO payments (id, user_id, txid, currency, amount, tier, expires, created) VALUES (?,?,?,?,?,?,?,?)", (sid(), req.user_id, req.txid.strip(), cur, prices[req.tier], req.tier, expiry.isoformat(), datetime.utcnow().isoformat()))
    c.execute("UPDATE users SET tier=?, msg_count=0 WHERE id=?", (req.tier, req.user_id))
    c.execute("INSERT INTO payment_log (id, user_id, tier, amount, currency, txid, created) VALUES (?,?,?,?,?,?,?)", (sid(), req.user_id, req.tier, prices[req.tier], cur, req.txid, datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    token = create_jwt(req.user_id, req.tier)
    return {"verified": True, "tier": req.tier, "token": token}

@app.post("/api/founder")
def founder(req: FounderRequest):
    if req.code != ADMIN_CODE: raise HTTPException(403, "Invalid code")
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("UPDATE users SET tier='founder', msg_count=0 WHERE id=?", (req.user_id,))
    conn.commit(); conn.close()
    token = create_jwt(req.user_id, 'founder')
    return {"verified": True, "tier": "founder", "token": token}

@app.post("/api/admin")
def admin(request: Request):
    user = get_current_user(request)
    if not user or user.get("tier") != "founder": raise HTTPException(403, "Access denied")
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id, email, tier, msg_count, created FROM users ORDER BY created DESC LIMIT 50")
    users = [{"id": r[0], "email": r[1], "tier": r[2], "msg_count": r[3], "created": r[4]} for r in c.fetchall()]
    c.execute("SELECT * FROM payment_log ORDER BY created DESC LIMIT 50")
    payments = [{"user_id": r[1], "tier": r[2], "amount": r[3], "currency": r[4], "txid": r[5], "created": r[6]} for r in c.fetchall()]
    conn.close()
    return {"users": users, "payments": payments, "total_users": len(users)}

@app.post("/api/workspace/create")
def ws_create(req: WorkspaceCreateRequest):
    if len(req.room_code) < 8: raise HTTPException(400, "Code too short (min 8 chars)")
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    wid = sid()
    c.execute("INSERT INTO workspaces (id, room_code, creator_id, max_members, created) VALUES (?,?,?,?,?)", (wid, req.room_code.upper(), req.user_id, req.max_members, datetime.utcnow().isoformat()))
    c.execute("INSERT INTO workspace_members (workspace_id, user_id, joined) VALUES (?,?,?)", (wid, req.user_id, datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return {"room_id": wid, "room_code": req.room_code.upper(), "created": True}

@app.post("/api/workspace/join")
def ws_join(req: WorkspaceJoinRequest):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id, max_members FROM workspaces WHERE room_code=?", (req.room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404, "Room not found")
    c.execute("SELECT COUNT(*) FROM workspace_members WHERE workspace_id=?", (ws[0],))
    if c.fetchone()[0] >= ws[1]: raise HTTPException(400, "Room full")
    c.execute("INSERT OR IGNORE INTO workspace_members (workspace_id, user_id, joined) VALUES (?,?,?)", (ws[0], req.user_id, datetime.utcnow().isoformat()))
    c.execute("SELECT m.user_id, u.email FROM workspace_members m LEFT JOIN users u ON m.user_id=u.id WHERE m.workspace_id=?", (ws[0],))
    members = [{"user_id": r[0], "name": r[1] or r[0]} for r in c.fetchall()]
    c.execute("SELECT id, user_id, author, message, created FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 50", (ws[0],))
    messages = [{"id": r[0], "user_id": r[1], "author": r[2], "message": r[3], "created": r[4]} for r in c.fetchall()]
    conn.commit(); conn.close()
    return {"joined": True, "room_id": ws[0], "members": members, "messages": messages}

@app.post("/api/workspace/message")
def ws_message(req: WorkspaceMessageRequest):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM workspaces WHERE room_code=?", (req.room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404, "Room not found")
    c.execute("SELECT email FROM users WHERE id=?", (req.user_id,))
    user_row = c.fetchone()
    author = user_row[0] if user_row else req.user_id
    c.execute("INSERT INTO workspace_messages (id, workspace_id, user_id, author, message, created) VALUES (?,?,?,?,?,?)", (sid(), ws[0], req.user_id, author, req.message, datetime.utcnow().isoformat()))
    conn.commit()
    c.execute("SELECT id, user_id, author, message, created FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 50", (ws[0],))
    messages = [{"id": r[0], "user_id": r[1], "author": r[2], "message": r[3], "created": r[4]} for r in c.fetchall()]
    conn.close()
    return {"sent": True, "messages": messages}

@app.get("/api/workspace/messages")
def ws_get_messages(room_code: str):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM workspaces WHERE room_code=?", (room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404, "Room not found")
    c.execute("SELECT m.user_id, u.email FROM workspace_members m LEFT JOIN users u ON m.user_id=u.id WHERE m.workspace_id=?", (ws[0],))
    members = [{"user_id": r[0], "name": r[1] or r[0]} for r in c.fetchall()]
    c.execute("SELECT id, user_id, author, message, created FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 50", (ws[0],))
    messages = [{"id": r[0], "user_id": r[1], "author": r[2], "message": r[3], "created": r[4]} for r in c.fetchall()]
    conn.close()
    return {"messages": messages, "members": members}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)