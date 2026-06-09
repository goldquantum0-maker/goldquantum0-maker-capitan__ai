"""
CAPITAN AI — Enterprise Backend v18.0
CLOSEAI Technologies
Python/FastAPI + SQLite + Resend Email
"""

import os, re, json, uuid, time, hashlib, hmac, base64, secrets, requests, sqlite3
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn

# ═══════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
RESEND_KEY = os.environ.get("RESEND_API_KEY", "")
JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))
ADMIN_CODE = os.environ.get("ADMIN_CODE", "Osinachi@350")
DB_PATH = "capitan.db"

WALLETS = {"USDC":"0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1","BTC":"bc1qrv6yr6e0mat96rvrc8smdf9rvu9rlp8xuk8new","ETH":"0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1"}

TIER_CONFIG = {
    "free":{"name":"Free","msg_limit":10,"workspace_max":0,"models":["deepseek/deepseek-chat"],"speed":"fast"},
    "plus":{"name":"Plus","msg_limit":30,"workspace_max":5,"models":["deepseek/deepseek-chat","openai/gpt-4o-mini","meta-llama/llama-3.1-70b-instruct"],"speed":"smart"},
    "pro":{"name":"Pro","msg_limit":float("inf"),"workspace_max":16,"models":["openai/gpt-4o","anthropic/claude-3.5-sonnet","groq/llama-3.1-70b-versatile"],"speed":"deep"},
    "founder":{"name":"Founder","msg_limit":float("inf"),"workspace_max":999,"models":["all"],"speed":"deep"}
}

# ═══════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY, email TEXT UNIQUE, name TEXT, password_hash TEXT,
        tier TEXT DEFAULT "free", msg_count INTEGER DEFAULT 0, msg_window TEXT,
        email_verified INTEGER DEFAULT 0, created TEXT, updated TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS chats (
        id TEXT PRIMARY KEY, user_id TEXT, title TEXT, model TEXT,
        created TEXT, updated TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS chat_messages (
        id TEXT PRIMARY KEY, chat_id TEXT, user_id TEXT, role TEXT,
        content TEXT, model TEXT, speed TEXT, created TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY, memory_id TEXT, user_id TEXT,
        content TEXT, query TEXT, domain TEXT, created TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS library_items (
        id TEXT PRIMARY KEY, user_id TEXT, name TEXT, type TEXT,
        content TEXT, size INTEGER DEFAULT 0, created TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS payments (
        id TEXT PRIMARY KEY, user_id TEXT, txid TEXT, currency TEXT,
        amount REAL, tier TEXT, expires TEXT, created TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS payment_log (
        id TEXT PRIMARY KEY, user_id TEXT, tier TEXT, amount REAL,
        currency TEXT, txid TEXT, created TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspaces (
        id TEXT PRIMARY KEY, room_code TEXT UNIQUE, creator_id TEXT,
        max_members INTEGER, created TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspace_members (
        workspace_id TEXT, user_id TEXT, joined TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspace_messages (
        id TEXT PRIMARY KEY, workspace_id TEXT, user_id TEXT,
        author TEXT, message TEXT, created TEXT
    )''')
    conn.commit()
    conn.close()

init_db()
def sid(): return str(uuid.uuid4())[:8].upper()
def mid(): return 'mem_' + sid()

# ═══════════════════════════════════════
# JWT
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
            c.execute("SELECT id,email,name,tier,msg_count,msg_window FROM users WHERE id=?",(payload["user_id"],))
            row = c.fetchone(); conn.close()
            if row: return {"id":row[0],"email":row[1],"name":row[2],"tier":row[3],"msg_count":row[4] or 0,"msg_window":row[5]}
    return None

# ═══════════════════════════════════════
# RATE LIMIT
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
# EMAIL
# ═══════════════════════════════════════
def send_email(to, subject, html):
    if not RESEND_KEY: print(f"EMAIL: {to} - {subject}"); return
    try:
        requests.post("https://api.resend.com/emails",
            headers={"Authorization":f"Bearer {RESEND_KEY}","Content-Type":"application/json"},
            json={"from":"CAPITAN AI <noreply@closeai.tech>","to":[to],"subject":subject,"html":html},timeout=10)
    except: pass

# ═══════════════════════════════════════
# AI CALLER
# ═══════════════════════════════════════
def call_ai(messages, tier="free", speed="fast"):
    models = TIER_CONFIG.get(tier,{}).get("models",["deepseek/deepseek-chat"])
    if models == ["all"]: models = ["anthropic/claude-3.5-sonnet","openai/gpt-4o","deepseek/deepseek-chat"]
    
    # Speed-based model selection
    speed_models = {
        "fast": models[0] if len(models)>0 else "deepseek/deepseek-chat",
        "smart": models[min(1,len(models)-1)] if len(models)>1 else models[0],
        "deep": models[min(2,len(models)-1)] if len(models)>2 else models[0]
    }
    model = speed_models.get(speed, models[0])
    max_tokens = {"fast":600,"smart":1500,"deep":3000}.get(speed,1000)
    
    if OPENROUTER_KEY:
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization":f"Bearer {OPENROUTER_KEY}","Content-Type":"application/json","HTTP-Referer":"https://capitan.pages.dev","X-Title":"CAPITAN AI"},
                json={"model":model,"messages":messages,"temperature":0.3,"max_tokens":max_tokens},timeout=90)
            if r.status_code==200: return r.json()["choices"][0]["message"]["content"]
        except: pass
    if OPENAI_KEY:
        try:
            r = requests.post("https://api.openai.com/v1/chat/completions",
                headers={"Authorization":f"Bearer {OPENAI_KEY}","Content-Type":"application/json"},
                json={"model":"gpt-4o-mini","messages":messages,"temperature":0.3,"max_tokens":max_tokens},timeout=90)
            if r.status_code==200: return r.json()["choices"][0]["message"]["content"]
        except: pass
    return None

def classify(q):
    q = q.lower()
    if re.search(r'python|javascript|react|node|api|code|program|def |class |function|docker|sql|algorithm',q): return 'coding'
    if re.search(r'quant|stochastic|var|cvar|sharpe|backtest|monte.carlo|option.pricing|black.scholes',q): return 'quant'
    if re.search(r'stock|revenue|ebitda|valuation|dcf|crypto|bitcoin|ethereum|forex|market|trading|invest',q): return 'finance'
    if re.search(r'crispr|dna|physics|chemistry|biology|quantum|research|paper|study',q): return 'science'
    if re.search(r'math|equation|calculate|proof|theorem|algebra|calculus|derivative|integral',q): return 'math'
    return 'general'

PERSONAS = {
    'coding':"\n\nCODE MODE: Senior software architect. Write production-grade code. Use ```language blocks.",
    'quant':"\n\nQUANT MODE: Mathematical rigor. Show derivations. Never give trading signals.",
    'finance':"\n\nFINANCE MODE: DCF, comps, scenario analysis. Balanced perspectives. No signals.",
    'science':"\n\nSCIENCE MODE: First principles. Current research. Clear analogies.",
    'math':"\n\nMATH MODE: Rigorous proofs. LaTeX notation. Step-by-step.",
    'general':"\n\nBe direct, helpful, conversational. Lead with the answer. Use markdown."
}

def system_prompt(domain, tier, user_id=None):
    base = "You are CAPITAN AI by CLOSEAI Technologies. Expert in finance, coding, math, research, and daily tasks. Conversational, precise, warm."
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

# ═══════════════════════════════════════
# MARKET DATA
# ═══════════════════════════════════════
def get_market_data():
    results = {}
    try:
        syms = "^GSPC,^IXIC,AAPL,MSFT,NVDA,TSLA,GC=F,CL=F,EURUSD=X,GBPUSD=X,USDJPY=X,USDGHS=X,USDNGN=X,USDZAR=X"
        r = requests.get(f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={syms}&fields=regularMarketPrice,regularMarketPreviousClose,shortName",headers={"User-Agent":"Mozilla/5.0"},timeout=10)
        if r.status_code==200:
            for i in r.json().get("quoteResponse",{}).get("result",[]):
                if i.get("regularMarketPrice") and i.get("regularMarketPreviousClose"):
                    results[i.get("shortName") or i["symbol"]] = {"price":i["regularMarketPrice"],"change":round(((i["regularMarketPrice"]-i["regularMarketPreviousClose"])/i["regularMarketPreviousClose"])*100,2)}
    except: pass
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd&include_24hr_change=true",timeout=10)
        if r.status_code==200:
            for n,d in r.json().items():
                if d.get("usd"): results[n.capitalize()] = {"price":d["usd"],"change":round(d.get("usd_24h_change",0),2)}
    except: pass
    return results

# ═══════════════════════════════════════
# MODELS
# ═══════════════════════════════════════
class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class ChatRequest(BaseModel):
    messages: list
    chat_id: Optional[str] = None
    speed: str = "fast"

class UpgradeRequest(BaseModel):
    tier: str
    txid: str
    currency: str = "USDC"

class FounderRequest(BaseModel):
    code: str

class LibraryItemRequest(BaseModel):
    name: str
    type: str = "note"
    content: Optional[str] = ""

class WorkspaceCreateRequest(BaseModel):
    room_code: str
    max_members: int = 3

class WorkspaceJoinRequest(BaseModel):
    room_code: str

class WorkspaceMessageRequest(BaseModel):
    room_code: str
    message: str

# ═══════════════════════════════════════
# APP
# ═══════════════════════════════════════
app = FastAPI(title="CAPITAN AI API", version="18.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health(): return {"status":"ok","version":"18.0"}

@app.get("/api/payment-config")
def payment_config(): return {"wallets":WALLETS,"prices":{"plus":8,"pro":17}}

@app.get("/api/markets")
def markets(): return {"prices":get_market_data()}

# ═══════════════════════════════════════
# AUTH
# ═══════════════════════════════════════
@app.post("/api/auth/register")
def register(req: RegisterRequest):
    if not req.email or "@" not in req.email: raise HTTPException(400,"Valid email required")
    if len(req.password) < 6: raise HTTPException(400,"Password must be 6+ characters")
    if len(req.name) < 2: raise HTTPException(400,"Name required")
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email=?",(req.email.lower().strip(),))
    if c.fetchone(): conn.close(); raise HTTPException(409,"Email already registered")
    uid = f"u_{sid()}"
    pw_hash = hashlib.sha256(req.password.encode()).hexdigest()
    c.execute("INSERT INTO users (id,email,name,password_hash,tier,msg_count,msg_window,email_verified,created,updated) VALUES (?,?,?,?,?,0,?,1,?,?)",
        (uid,req.email.lower().strip(),req.name,pw_hash,"free",datetime.utcnow().isoformat(),datetime.utcnow().isoformat(),datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    token = create_jwt(uid,"free")
    return {"token":token,"user":{"id":uid,"email":req.email,"name":req.name,"tier":"free"}}

@app.post("/api/auth/login")
def login(req: LoginRequest):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,email,name,tier,password_hash FROM users WHERE email=?",(req.email.lower().strip(),))
    row = c.fetchone(); conn.close()
    if not row: raise HTTPException(401,"Invalid credentials")
    pw_hash = hashlib.sha256(req.password.encode()).hexdigest()
    if pw_hash != row[4]: raise HTTPException(401,"Invalid credentials")
    token = create_jwt(row[0],row[3])
    return {"token":token,"user":{"id":row[0],"email":row[1],"name":row[2],"tier":row[3]}}

@app.get("/api/auth/me")
def me(request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401,"Not authenticated")
    return {"user":user}

# ═══════════════════════════════════════
# CHATS
# ═══════════════════════════════════════
@app.get("/api/chats")
def get_chats(request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,title,model,created,updated FROM chats WHERE user_id=? ORDER BY updated DESC LIMIT 30",(user["id"],))
    rows = c.fetchall(); conn.close()
    return {"chats":[{"id":r[0],"title":r[1],"model":r[2],"created":r[3],"updated":r[4]} for r in rows]}

@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM chats WHERE id=? AND user_id=?",(chat_id,user["id"]))
    if not c.fetchone(): raise HTTPException(404,"Not found")
    c.execute("SELECT id,role,content,model,speed,created FROM chat_messages WHERE chat_id=? ORDER BY created ASC",(chat_id,))
    msgs = [{"id":r[0],"role":r[1],"content":r[2],"model":r[3],"speed":r[4],"created":r[5]} for r in c.fetchall()]
    conn.close()
    return {"messages":msgs}

@app.post("/api/chat")
def chat(req: ChatRequest, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    if not check_rate(user["id"],user["tier"]): raise HTTPException(429,"Rate limit")
    
    cfg = TIER_CONFIG.get(user["tier"],TIER_CONFIG["free"])
    limit = cfg["msg_limit"]
    if limit != float("inf"):
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT msg_count,msg_window FROM users WHERE id=?",(user["id"],))
        row = c.fetchone()
        count = row[0] or 0
        if count >= limit:
            w = datetime.fromisoformat(row[1]) if row and row[1] else datetime.utcnow()
            if datetime.utcnow() - w < timedelta(hours=24): raise HTTPException(429,f"Limit reached ({limit}/day)")
            c.execute("UPDATE users SET msg_count=0, msg_window=? WHERE id=?",(datetime.utcnow().isoformat(),user["id"]))
            conn.commit()
        conn.close()
    
    user_msg = next((m["content"] for m in reversed(req.messages) if m.get("role")=="user"),"")
    if not user_msg: raise HTTPException(400,"No message")
    
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    chat_id = req.chat_id or f"chat_{sid()}"
    if not req.chat_id:
        c.execute("INSERT INTO chats (id,user_id,title,model,created,updated) VALUES (?,?,?,?,?,?)",
            (chat_id,user["id"],user_msg[:60],req.speed or "fast",datetime.utcnow().isoformat(),datetime.utcnow().isoformat()))
    else:
        c.execute("UPDATE chats SET updated=? WHERE id=? AND user_id=?",(datetime.utcnow().isoformat(),chat_id,user["id"]))
    
    c.execute("INSERT INTO chat_messages (id,chat_id,user_id,role,content,speed,created) VALUES (?,?,?,?,?,?,?)",
        (f"msg_{sid()}",chat_id,user["id"],"user",user_msg,req.speed,datetime.utcnow().isoformat()))
    c.execute("UPDATE users SET msg_count = msg_count + 1 WHERE id=?",(user["id"],))
    conn.commit()
    
    c.execute("SELECT role,content FROM chat_messages WHERE chat_id=? ORDER BY created ASC LIMIT 20",(chat_id,))
    history = [{"role":r[0],"content":r[1]} for r in c.fetchall()]
    
    domain = classify(user_msg)
    prompt = system_prompt(domain, user["tier"], user["id"])
    result = call_ai([{"role":"system","content":prompt}] + history, user["tier"], req.speed)
    
    if result:
        c.execute("INSERT INTO chat_messages (id,chat_id,user_id,role,content,model,speed,created) VALUES (?,?,?,?,?,?,?,?)",
            (f"msg_{sid()}",chat_id,user["id"],"assistant",result,req.speed or "fast",req.speed,datetime.utcnow().isoformat()))
    
    c.execute("INSERT INTO memories (id,memory_id,user_id,content,query,domain,created) VALUES (?,?,?,?,?,?,?)",
        (sid(),mid(),user["id"],result or '',user_msg,domain,datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    
    return {"content":result or "No response.","chat_id":chat_id,"domain":domain}

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
def get_library(request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,name,type,content,size,created FROM library_items WHERE user_id=? ORDER BY created DESC",(user["id"],))
    items = [{"id":r[0],"name":r[1],"type":r[2],"content":r[3],"size":r[4],"created":r[5]} for r in c.fetchall()]
    conn.close()
    return {"items":items}

@app.post("/api/library")
def create_library_item(req: LibraryItemRequest, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    item_id = f"lib_{sid()}"
    c.execute("INSERT INTO library_items (id,user_id,name,type,content,size,created) VALUES (?,?,?,?,?,?,?)",
        (item_id,user["id"],req.name,req.type,req.content or "",len(req.content or ""),datetime.utcnow().isoformat()))
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
# UPGRADE
# ═══════════════════════════════════════
@app.post("/api/upgrade")
def upgrade(req: UpgradeRequest, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    if req.tier not in ("plus","pro"): raise HTTPException(400,"Invalid tier")
    if not req.txid.strip(): raise HTTPException(400,"TXID required")
    prices = {"plus":8,"pro":17}
    cur = req.currency.upper()
    expiry = (datetime.utcnow()+timedelta(days=30)).isoformat()
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("INSERT INTO payments (id,user_id,txid,currency,amount,tier,expires,created) VALUES (?,?,?,?,?,?,?,?)",
        (sid(),user["id"],req.txid.strip(),cur,prices[req.tier],req.tier,expiry,datetime.utcnow().isoformat()))
    c.execute("UPDATE users SET tier=?, msg_count=0, updated=? WHERE id=?",(req.tier,datetime.utcnow().isoformat(),user["id"]))
    c.execute("INSERT INTO payment_log (id,user_id,tier,amount,currency,txid,created) VALUES (?,?,?,?,?,?,?)",
        (sid(),user["id"],req.tier,prices[req.tier],cur,req.txid,datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    token = create_jwt(user["id"],req.tier)
    return {"verified":True,"tier":req.tier,"token":token}

# ═══════════════════════════════════════
# FOUNDER
# ═══════════════════════════════════════
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
    c.execute("SELECT id,email,name,tier,msg_count,created FROM users ORDER BY created DESC LIMIT 30")
    users = [{"id":r[0],"email":r[1],"name":r[2],"tier":r[3],"msg_count":r[4],"created":r[5]} for r in c.fetchall()]
    c.execute("SELECT * FROM payment_log ORDER BY created DESC LIMIT 20")
    payments = [{"user_id":r[1],"tier":r[2],"amount":r[3],"currency":r[4],"txid":r[5],"created":r[6]} for r in c.fetchall()]
    conn.close()
    return {"total_users":total,"paid_users":paid,"total_messages":msgs,"users":users,"payments":payments}

# ═══════════════════════════════════════
# WORKSPACE
# ═══════════════════════════════════════
@app.post("/api/workspace/create")
def ws_create(req: WorkspaceCreateRequest, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    max_m = TIER_CONFIG.get(user["tier"],{}).get("workspace_max",0)
    if max_m == 0: raise HTTPException(403,"Upgrade required")
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    wid = sid()
    c.execute("INSERT INTO workspaces (id,room_code,creator_id,max_members,created) VALUES (?,?,?,?,?)",
        (wid,req.room_code.upper(),user["id"],min(req.max_members,max_m),datetime.utcnow().isoformat()))
    c.execute("INSERT INTO workspace_members (workspace_id,user_id,joined) VALUES (?,?,?)",(wid,user["id"],datetime.utcnow().isoformat()))
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
    c.execute("INSERT OR IGNORE INTO workspace_members (workspace_id,user_id,joined) VALUES (?,?,?)",(ws[0],user["id"],datetime.utcnow().isoformat()))
    c.execute("SELECT m.user_id,u.email FROM workspace_members m LEFT JOIN users u ON m.user_id=u.id WHERE m.workspace_id=?",(ws[0],))
    members = [{"user_id":r[0],"name":r[1] or r[0]} for r in c.fetchall()]
    c.execute("SELECT id,user_id,author,message,created FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 50",(ws[0],))
    messages = [{"id":r[0],"user_id":r[1],"author":r[2],"message":r[3],"created":r[4]} for r in c.fetchall()]
    conn.commit(); conn.close()
    return {"joined":True,"room_id":ws[0],"members":members,"messages":messages}

@app.post("/api/workspace/message")
def ws_message(req: WorkspaceMessageRequest, request: Request):
    user = get_user(request)
    if not user: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM workspaces WHERE room_code=?",(req.room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404,"Room not found")
    c.execute("INSERT INTO workspace_messages (id,workspace_id,user_id,author,message,created) VALUES (?,?,?,?,?,?)",
        (sid(),ws[0],user["id"],user["name"] or user["email"],req.message,datetime.utcnow().isoformat()))
    conn.commit()
    c.execute("SELECT id,user_id,author,message,created FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 50",(ws[0],))
    messages = [{"id":r[0],"user_id":r[1],"author":r[2],"message":r[3],"created":r[4]} for r in c.fetchall()]
    conn.close()
    return {"sent":True,"messages":messages}

@app.get("/api/workspace/messages")
def ws_get_messages(room_code: str):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM workspaces WHERE room_code=?",(room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404,"Room not found")
    c.execute("SELECT m.user_id,u.email FROM workspace_members m LEFT JOIN users u ON m.user_id=u.id WHERE m.workspace_id=?",(ws[0],))
    members = [{"user_id":r[0],"name":r[1] or r[0]} for r in c.fetchall()]
    c.execute("SELECT id,user_id,author,message,created FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 50",(ws[0],))
    messages = [{"id":r[0],"user_id":r[1],"author":r[2],"message":r[3],"created":r[4]} for r in c.fetchall()]
    conn.close()
    return {"messages":messages,"members":members}

if __name__ == "__main__":
    port = int(os.environ.get("PORT",8000))
    uvicorn.run(app,host="0.0.0.0",port=port)