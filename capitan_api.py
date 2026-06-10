"""
CAPITAN AI — Enterprise Backend v22.0
CLOSEAI Technologies
Python/FastAPI + SQLite
Privacy-First: No accounts, just messages & payments
Elite Intelligence: Finance, Coding, Math, Quant, Software Development
"""

import os, re, json, uuid, time, hashlib, hmac, base64, secrets, requests, sqlite3
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))
ADMIN_CODE = os.environ.get("ADMIN_CODE", "Osinachi@350")
DB_PATH = "capitan.db"

WALLETS = {"BTC":"bc1qrv6yr6e0mat96rvrc8smdf9rvu9rlp8xuk8new","ETH":"0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1"}

TIER_CONFIG = {
    "free":{"name":"Free","msg_limit":10,"workspace_max":0,"file_upload":False,"file_size_mb":0,"speed":"fast"},
    "plus":{"name":"Plus","msg_limit":30,"workspace_max":5,"file_upload":True,"file_size_mb":10,"speed":"smart"},
    "pro":{"name":"Pro","msg_limit":float("inf"),"workspace_max":16,"file_upload":True,"file_size_mb":50,"speed":"deep"},
    "founder":{"name":"Founder","msg_limit":float("inf"),"workspace_max":999,"file_upload":True,"file_size_mb":500,"speed":"deep"}
}

UPGRADE_BENEFITS = {
    "plus": [
        "30 messages per day (up from 10)",
        "Smart AI model for better responses",
        "Work Area — collaborate with up to 5 people",
        "File uploads up to 10MB",
        "Coding & Quant tools",
        "African Finance module",
        "Priority response speed",
        "Save chats & library access"
    ],
    "pro": [
        "Unlimited messages — no daily cap",
        "Deep AI model (Claude 3.5 Sonnet / GPT-4o)",
        "Work Area — collaborate with up to 16 people",
        "File uploads up to 50MB",
        "Live market data & financial news",
        "Shared Work Area notes with AI integration",
        "@CAPITAN AI commands in Work Area",
        "Export Work Area to PDF",
        "Business mode for professional use",
        "All Plus features included"
    ]
}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, tier TEXT DEFAULT "free", msg_count INTEGER DEFAULT 0, msg_window TEXT, created TEXT, updated TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, session_id TEXT, title TEXT, created TEXT, updated TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chat_messages (id TEXT PRIMARY KEY, chat_id TEXT, session_id TEXT, role TEXT, content TEXT, model TEXT, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS memories (id TEXT PRIMARY KEY, memory_id TEXT, session_id TEXT, content TEXT, query TEXT, domain TEXT, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS library_items (id TEXT PRIMARY KEY, session_id TEXT, name TEXT, type TEXT, content TEXT, size INTEGER DEFAULT 0, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS uploaded_files (id TEXT PRIMARY KEY, session_id TEXT, filename TEXT, original_name TEXT, size INTEGER, mime_type TEXT, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS payments (id TEXT PRIMARY KEY, session_id TEXT, txid TEXT, currency TEXT, amount REAL, tier TEXT, verified INTEGER DEFAULT 0, expires TEXT, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS payment_log (id TEXT PRIMARY KEY, session_id TEXT, tier TEXT, amount REAL, currency TEXT, txid TEXT, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspaces (id TEXT PRIMARY KEY, room_code TEXT UNIQUE, creator_session TEXT, max_members INTEGER, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspace_members (workspace_id TEXT, session_id TEXT, role TEXT DEFAULT "member", joined TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspace_messages (id TEXT PRIMARY KEY, workspace_id TEXT, session_id TEXT, author TEXT, message TEXT, is_ai INTEGER DEFAULT 0, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspace_notes (id TEXT PRIMARY KEY, workspace_id TEXT, session_id TEXT, author TEXT, content TEXT, created TEXT, updated TEXT)''')
    conn.commit()
    conn.close()

init_db()
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def sid(): return str(uuid.uuid4())[:8].upper()
def mid(): return 'mem_' + sid()

def create_jwt(session_id, tier):
    h = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    p = base64.urlsafe_b64encode(json.dumps({"session_id":session_id,"tier":tier,"exp":int((datetime.utcnow()+timedelta(days=365)).timestamp())}).encode()).decode().rstrip("=")
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

def get_session(request: Request):
    auth = request.headers.get("Authorization","")
    if auth.startswith("Bearer "):
        payload = verify_jwt(auth[7:])
        if payload:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT id,tier,msg_count,msg_window FROM sessions WHERE id=?",(payload["session_id"],))
            row = c.fetchone(); conn.close()
            if row: return {"id":row[0],"tier":row[1],"msg_count":row[2] or 0,"msg_window":row[3]}
    return None

rate_store = {}
def check_rate(session_id, tier):
    now = time.time(); key = f"{session_id}"
    if key not in rate_store: rate_store[key] = []
    rate_store[key] = [t for t in rate_store[key] if now-t < 60]
    limits = {"free":10,"plus":20,"pro":60,"founder":200}
    if len(rate_store[key]) >= limits.get(tier,10): return False
    rate_store[key].append(now); return True

# ═══════════════════════════════════════════════════════════════
# ELITE INTELLIGENCE SYSTEM
# ═══════════════════════════════════════════════════════════════

ELITE_SYSTEM_PROMPT = """You are CAPITAN AI — an elite institutional intelligence system by CLOSEAI Technologies.

CORE IDENTITY:
You are the world's most capable AI assistant for finance, coding, mathematics, quantitative analysis, and software development. You operate at the level of a Goldman Sachs Managing Director, a Principal Engineer at a FAANG company, a Research Mathematician, and a Quant Research Director — simultaneously.

RESPONSE ARCHITECTURE:
1. LEAD WITH THE ANSWER — most important insight first
2. EXPLAIN THE MECHANISM — how and why, not just what
3. PROVIDE EVIDENCE — data, code, citations, logical proof
4. CALIBRATE CONFIDENCE — explicitly state certainty level
5. OFFER DEPTH — ask if the user wants to go deeper

COMMUNICATION STYLE:
• Direct, precise, no fluff
• Use markdown for structure: tables, code blocks, LaTeX math
• Short paragraphs, scannable
• Professional warmth — like a trusted senior colleague
• Never condescending, always respectful of the user's intelligence

FINANCE CAPABILITIES:
• DCF, LBO, M&A accretion/dilution, comparable company analysis
• Portfolio optimization (Markowitz, Black-Litterman, risk parity)
• Options pricing (Black-Scholes, binomial trees, Monte Carlo)
• Fixed income (duration, convexity, yield curve construction)
• Risk management (VaR, CVaR, stress testing, scenario analysis)
• Financial statement analysis, ratio analysis, DuPont decomposition
• Macroeconomic analysis (central bank policy, yield curves, FX)
• African financial markets (NGX, JSE, GSE, BRVM, EGX, crypto)
• NEVER give buy/sell recommendations or specific trading signals

CODING CAPABILITIES:
• Python, JavaScript, TypeScript, Rust, Go, C++, SQL, React, Node.js
• System design and architecture patterns
• Algorithm optimization with complexity analysis
• API design (REST, GraphQL, gRPC)
• Database design and query optimization
• DevOps and cloud infrastructure
• Testing strategies and CI/CD pipelines
• Security best practices and code review
• Production-grade code with error handling, type hints, and documentation

MATHEMATICS CAPABILITIES:
• Real analysis, complex analysis, functional analysis
• Linear algebra, abstract algebra, group theory
• Topology, differential geometry
• Probability theory and stochastic processes
• Numerical methods and optimization
• Statistics and machine learning theory
• Rigorous proofs with step-by-step derivations
• Use LaTeX notation: $E = mc^2$, $$\\int_a^b f(x)dx$$

QUANTITATIVE FINANCE CAPABILITIES:
• Stochastic calculus (Itô's lemma, SDEs)
• Derivative pricing models
• Risk-neutral valuation
• Monte Carlo simulation methods
• Time series analysis (ARIMA, GARCH, cointegration)
• Factor models (Fama-French, momentum, quality)
• Machine learning in finance (random forests, gradient boosting, neural networks)
• Backtesting frameworks and performance metrics
• NEVER give specific entry/exit signals or price targets

SOFTWARE DEVELOPMENT CAPABILITIES:
• Full-stack architecture design
• Microservices and distributed systems
• Database design (SQL, NoSQL, graph databases)
• Message queues and event-driven architecture
• Containerization (Docker, Kubernetes)
• Monitoring and observability
• Performance optimization
• Technical debt management
• Team workflow and agile methodologies

CURRENT DOMAIN: {domain}
USER TIER: {tier}
"""

def call_ai(messages, tier="free"):
    models_to_try = ["google/gemini-flash-1.5","mistral/mistral-7b-instruct","deepseek/deepseek-chat","meta-llama/llama-3.1-8b-instruct","openai/gpt-3.5-turbo"]
    if tier in ("pro","founder"): models_to_try = ["anthropic/claude-3.5-sonnet","openai/gpt-4o"] + models_to_try
    
    for model in models_to_try:
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization":f"Bearer {OPENROUTER_KEY}","Content-Type":"application/json","HTTP-Referer":"https://capitan.pages.dev","X-Title":"CAPITAN AI"},
                json={"model":model,"messages":messages,"temperature":0.3,"max_tokens":600 if tier=="free" else 2500},timeout=90)
            if r.status_code==200:
                content = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
                if content: return content, model
        except: continue
    
    if OPENAI_KEY:
        try:
            r = requests.post("https://api.openai.com/v1/chat/completions",headers={"Authorization":f"Bearer {OPENAI_KEY}","Content-Type":"application/json"},json={"model":"gpt-3.5-turbo","messages":messages,"temperature":0.3,"max_tokens":600},timeout=60)
            if r.status_code==200: return r.json()["choices"][0]["message"]["content"], "gpt-3.5-turbo"
        except: pass
    
    return "I'm having trouble connecting to my AI models. Please try again in a moment, or contact closeaitechnologies@protonmail.com for support.", "fallback"

def classify(q):
    q = q.lower()
    # Coding patterns
    if re.search(r'```|def |class |import |from |package|npm|pip|docker|kubernetes|aws|api\s|rest |graphql|sql\s|database|query|react|node\.js|javascript|typescript|python\s|rust\s|golang|microservice|architecture|system design|refactor|debug|deploy|ci/cd|git\s',q): return 'coding'
    # Quant patterns
    if re.search(r'stochastic|ito|black.scholes|monte carlo|var\s|cvar|sharpe ratio|sortino|beta\s|alpha\s|option pricing|derivative pricing|risk neutral|fama.french|cointegration|garch|arima|backtest|factor model|portfolio optim',q): return 'quant'
    # Finance patterns
    if re.search(r'dcf|discounted cash flow|ebitda|ebit|revenue|earnings|balance sheet|income statement|cash flow|valuation|wacc|capm|pe ratio|pb ratio|ev/ebitda|dividend|yield|bond|coupon|duration|convexity|forex|fx\s|central bank|federal reserve|ecb|interest rate|inflation|gdp|macro|equity|stock\s|market\s|trading|invest|portfolio|crypto|bitcoin|ethereum|defi|ngx|jse|gse|african market',q): return 'finance'
    # Math patterns
    if re.search(r'prove|proof|theorem|lemma|corollary|derive|integral|derivative|differential equation|linear algebra|matrix|eigenvalue|vector|topology|group theory|ring theory|field theory|probability|statistics|distribution|convergence|limit|sum|product|calculus|laplace|fourier|numerical|optimization|convex|gradient',q): return 'math'
    # Science patterns
    if re.search(r'crispr|dna|rna|protein|cell|gene|genome|physics|quantum|chemistry|biology|neuroscience|climate|energy|particle|wave|force|mass|velocity|acceleration|molecule|atom|electron|photon',q): return 'science'
    return 'general'

def system_prompt(domain, tier, session_id=None):
    base = ELITE_SYSTEM_PROMPT.replace("{domain}", domain).replace("{tier}", tier)
    
    # Add memory context
    if session_id:
        try:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT query, domain FROM memories WHERE session_id=? ORDER BY created DESC LIMIT 5",(session_id,))
            rows = c.fetchall(); conn.close()
            if rows: 
                base += "\n\n## USER CONTEXT (from previous conversations)\n"
                for r in rows: base += f"• [{r[1]}] {r[0][:120]}\n"
                base += "Use this context for continuity. Do not mention it explicitly unless relevant."
        except: pass
    
    # Add tier-specific depth
    if tier == "free":
        base += "\n\nKeep responses concise but complete. Focus on clarity."
    elif tier == "plus":
        base += "\n\nProvide solid, well-structured responses with examples. Include code snippets where helpful."
    elif tier in ("pro","founder"):
        base += "\n\nProvide comprehensive, deeply insightful responses. Use examples, code, mathematical derivations, and citations. Explore edge cases. Think at the level of an expert practitioner."
    
    return base

def get_market_data():
    results = {}
    try:
        syms = "^GSPC,^IXIC,^DJI,^FTSE,^N225,AAPL,MSFT,NVDA,TSLA,GOOGL,META,AMZN,JPM,GS,GC=F,CL=F,SI=F,EURUSD=X,GBPUSD=X,USDJPY=X,USDGHS=X,USDNGN=X,USDZAR=X,USDKES=X,BTC-USD,ETH-USD"
        r = requests.get(f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={syms}&fields=regularMarketPrice,regularMarketPreviousClose,shortName",headers={"User-Agent":"Mozilla/5.0"},timeout=10)
        if r.status_code==200:
            for i in r.json().get("quoteResponse",{}).get("result",[]):
                if i.get("regularMarketPrice") and i.get("regularMarketPreviousClose"):
                    results[i.get("shortName") or i["symbol"]] = {"price":i["regularMarketPrice"],"change":round(((i["regularMarketPrice"]-i["regularMarketPreviousClose"])/i["regularMarketPreviousClose"])*100,2)}
    except: pass
    return results

# ═══════════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════════
class ChatRequest(BaseModel): messages: list; chat_id: Optional[str] = None
class UpgradeRequest(BaseModel): tier: str; txid: str; currency: str = "BTC"
class FounderRequest(BaseModel): code: str
class LibraryItemRequest(BaseModel): name: str; type: str = "note"; content: Optional[str] = ""
class WorkspaceCreateRequest(BaseModel): room_code: str; max_members: int = 3
class WorkspaceJoinRequest(BaseModel): room_code: str
class WorkspaceMessageRequest(BaseModel): room_code: str; message: str
class WorkspaceNoteRequest(BaseModel): room_code: str; content: str

# ═══════════════════════════════════════════════════════════════
# APP
# ═══════════════════════════════════════════════════════════════
app = FastAPI(title="CAPITAN AI API", version="22.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health():
    ai = "disconnected"
    if OPENROUTER_KEY:
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions",headers={"Authorization":f"Bearer {OPENROUTER_KEY}","Content-Type":"application/json"},json={"model":"google/gemini-flash-1.5","messages":[{"role":"user","content":"Hi"}],"max_tokens":5},timeout=15)
            if r.status_code==200: ai="connected"
        except: pass
    return {"status":"ok","version":"22.0","ai":ai}

@app.get("/api/session")
def get_or_create_session(request: Request):
    session = get_session(request)
    if session: return session
    auth = request.headers.get("Authorization","")
    if auth.startswith("Bearer "):
        payload = verify_jwt(auth[7:])
        if payload:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT id,tier,msg_count,msg_window FROM sessions WHERE id=?",(payload["session_id"],))
            row = c.fetchone(); conn.close()
            if row: return {"id":row[0],"tier":row[1],"msg_count":row[2] or 0,"msg_window":row[3]}
    session_id = f"s_{sid()}"
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("INSERT INTO sessions (id,tier,msg_count,msg_window,created,updated) VALUES (?,?,0,?,?,?)",(session_id,"free",datetime.utcnow().isoformat(),datetime.utcnow().isoformat(),datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    token = create_jwt(session_id,"free")
    return {"id":session_id,"tier":"free","msg_count":0,"token":token}

@app.get("/api/payment-config")
def payment_config(): return {"wallets":WALLETS,"prices":{"plus":8,"pro":17},"benefits":UPGRADE_BENEFITS}

@app.get("/api/markets")
def markets(): return {"prices":get_market_data()}

@app.get("/api/chats")
def get_chats(request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,title,created,updated FROM chats WHERE session_id=? ORDER BY updated DESC LIMIT 30",(s["id"],))
    rows = c.fetchall(); conn.close()
    return {"chats":[{"id":r[0],"title":r[1],"created":r[2],"updated":r[3]} for r in rows]}

@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM chats WHERE id=? AND session_id=?",(chat_id,s["id"]))
    if not c.fetchone(): raise HTTPException(404,"Not found")
    c.execute("SELECT id,role,content,model,created FROM chat_messages WHERE chat_id=? ORDER BY created ASC",(chat_id,))
    msgs = [{"id":r[0],"role":r[1],"content":r[2],"model":r[3],"created":r[4]} for r in c.fetchall()]
    conn.close()
    return {"messages":msgs}

@app.post("/api/chat")
def chat(req: ChatRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    if not check_rate(s["id"],s["tier"]): raise HTTPException(429,"Rate limit")
    cfg = TIER_CONFIG.get(s["tier"],TIER_CONFIG["free"])
    limit = cfg["msg_limit"]
    if limit != float("inf"):
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT msg_count,msg_window FROM sessions WHERE id=?",(s["id"],))
        row = c.fetchone()
        count = row[0] or 0
        if count >= limit:
            w = datetime.fromisoformat(row[1]) if row and row[1] else datetime.utcnow()
            if datetime.utcnow() - w < timedelta(hours=24): raise HTTPException(429,f"Daily limit reached ({limit}/day). Upgrade to continue.")
            c.execute("UPDATE sessions SET msg_count=0, msg_window=? WHERE id=?",(datetime.utcnow().isoformat(),s["id"]))
            conn.commit()
        conn.close()
    user_msg = next((m["content"] for m in reversed(req.messages) if m.get("role")=="user"),"")
    if not user_msg: raise HTTPException(400,"No message")
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    chat_id = req.chat_id or f"chat_{sid()}"
    if not req.chat_id:
        c.execute("INSERT INTO chats (id,session_id,title,created,updated) VALUES (?,?,?,?,?)",(chat_id,s["id"],user_msg[:60],datetime.utcnow().isoformat(),datetime.utcnow().isoformat()))
    else:
        c.execute("UPDATE chats SET updated=? WHERE id=? AND session_id=?",(datetime.utcnow().isoformat(),chat_id,s["id"]))
    c.execute("INSERT INTO chat_messages (id,chat_id,session_id,role,content,created) VALUES (?,?,?,?,?,?)",(f"msg_{sid()}",chat_id,s["id"],"user",user_msg,datetime.utcnow().isoformat()))
    c.execute("UPDATE sessions SET msg_count = msg_count + 1 WHERE id=?",(s["id"],))
    conn.commit()
    c.execute("SELECT role,content FROM chat_messages WHERE chat_id=? ORDER BY created ASC LIMIT 25",(chat_id,))
    history = [{"role":r[0],"content":r[1]} for r in c.fetchall()]
    domain = classify(user_msg)
    prompt = system_prompt(domain, s["tier"], s["id"])
    result, model_used = call_ai([{"role":"system","content":prompt}] + history, s["tier"])
    if result:
        c.execute("INSERT INTO chat_messages (id,chat_id,session_id,role,content,model,created) VALUES (?,?,?,?,?,?,?)",(f"msg_{sid()}",chat_id,s["id"],"assistant",result,model_used,datetime.utcnow().isoformat()))
    c.execute("INSERT INTO memories (id,memory_id,session_id,content,query,domain,created) VALUES (?,?,?,?,?,?,?)",(sid(),mid(),s["id"],result,user_msg,domain,datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    remaining = limit - (s["msg_count"]+1) if limit!=float("inf") else "unlimited"
    return {"content":result,"chat_id":chat_id,"model":model_used,"remaining":remaining}

@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("DELETE FROM chat_messages WHERE chat_id=? AND session_id=?",(chat_id,s["id"]))
    c.execute("DELETE FROM chats WHERE id=? AND session_id=?",(chat_id,s["id"]))
    conn.commit(); conn.close()
    return {"deleted":True}

@app.get("/api/library")
def get_library(request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,name,type,content,size,created FROM library_items WHERE session_id=? ORDER BY created DESC",(s["id"],))
    items = [{"id":r[0],"name":r[1],"type":r[2],"content":r[3],"size":r[4],"created":r[5]} for r in c.fetchall()]
    conn.close()
    return {"items":items}

@app.post("/api/library")
def create_library_item(req: LibraryItemRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    item_id = f"lib_{sid()}"
    c.execute("INSERT INTO library_items (id,session_id,name,type,content,size,created) VALUES (?,?,?,?,?,?,?)",(item_id,s["id"],req.name,req.type,req.content or "",len(req.content or ""),datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return {"id":item_id,"created":True}

@app.delete("/api/library/{item_id}")
def delete_library_item(item_id: str, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("DELETE FROM library_items WHERE id=? AND session_id=?",(item_id,s["id"]))
    conn.commit(); conn.close()
    return {"deleted":True}

@app.post("/api/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    s = get_session(request)
    if not s: raise HTTPException(401)
    cfg = TIER_CONFIG.get(s["tier"],TIER_CONFIG["free"])
    if not cfg["file_upload"]: raise HTTPException(403,"Upgrade required")
    contents = await file.read()
    size_mb = len(contents) / (1024*1024)
    if size_mb > cfg["file_size_mb"]: raise HTTPException(400,f"Max {cfg['file_size_mb']}MB")
    file_id = f"file_{sid()}"
    with open(os.path.join(UPLOAD_DIR, file_id), "wb") as f: f.write(contents)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("INSERT INTO uploaded_files (id,session_id,filename,original_name,size,mime_type,created) VALUES (?,?,?,?,?,?,?)",(file_id,s["id"],file_id,file.filename or "unknown",len(contents),file.content_type or "application/octet-stream",datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return {"id":file_id,"filename":file.filename,"size_mb":round(size_mb,2)}

@app.post("/api/upgrade")
def upgrade(req: UpgradeRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    if req.tier not in ("plus","pro"): raise HTTPException(400,"Invalid tier")
    if not req.txid.strip(): raise HTTPException(400,"TXID required")
    prices = {"plus":8,"pro":17}
    cur = req.currency.upper()
    expiry = (datetime.utcnow()+timedelta(days=30)).isoformat()
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("INSERT INTO payments (id,session_id,txid,currency,amount,tier,verified,expires,created) VALUES (?,?,?,?,?,?,?,?,?)",(sid(),s["id"],req.txid.strip(),cur,prices[req.tier],req.tier,1,expiry,datetime.utcnow().isoformat()))
    c.execute("UPDATE sessions SET tier=?, msg_count=0, updated=? WHERE id=?",(req.tier,datetime.utcnow().isoformat(),s["id"]))
    c.execute("INSERT INTO payment_log (id,session_id,tier,amount,currency,txid,created) VALUES (?,?,?,?,?,?,?)",(sid(),s["id"],req.tier,prices[req.tier],cur,req.txid,datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    token = create_jwt(s["id"],req.tier)
    return {"verified":True,"tier":req.tier,"token":token}

@app.post("/api/founder")
def founder(req: FounderRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    if req.code != ADMIN_CODE: raise HTTPException(403,"Invalid code")
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("UPDATE sessions SET tier='founder', msg_count=0, updated=? WHERE id=?",(datetime.utcnow().isoformat(),s["id"]))
    conn.commit(); conn.close()
    token = create_jwt(s["id"],"founder")
    return {"verified":True,"tier":"founder","token":token}

@app.post("/api/admin")
def admin(request: Request):
    s = get_session(request)
    if not s or s["tier"]!="founder": raise HTTPException(403,"Access denied")
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM sessions"); total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM sessions WHERE tier!='free'"); paid = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM chat_messages"); msgs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM workspaces"); ws = c.fetchone()[0]
    c.execute("SELECT id,tier,msg_count,created FROM sessions ORDER BY created DESC LIMIT 30")
    sessions = [{"id":r[0],"tier":r[1],"msg_count":r[2],"created":r[3]} for r in c.fetchall()]
    c.execute("SELECT * FROM payment_log ORDER BY created DESC LIMIT 20")
    payments = [{"session_id":r[1],"tier":r[2],"amount":r[3],"currency":r[4],"txid":r[5],"created":r[6]} for r in c.fetchall()]
    conn.close()
    return {"total_sessions":total,"paid_sessions":paid,"total_messages":msgs,"workspaces":ws,"sessions":sessions,"payments":payments}

@app.post("/api/workspace/create")
def ws_create(req: WorkspaceCreateRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    max_m = TIER_CONFIG.get(s["tier"],{}).get("workspace_max",0)
    if max_m == 0: raise HTTPException(403,"Work Area requires Plus or Pro")
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    wid = sid()
    c.execute("INSERT INTO workspaces (id,room_code,creator_session,max_members,created) VALUES (?,?,?,?,?)",(wid,req.room_code.upper(),s["id"],min(req.max_members,max_m),datetime.utcnow().isoformat()))
    c.execute("INSERT INTO workspace_members (workspace_id,session_id,role,joined) VALUES (?,?,?,?)",(wid,s["id"],"admin",datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return {"room_id":wid,"room_code":req.room_code.upper(),"created":True}

@app.post("/api/workspace/join")
def ws_join(req: WorkspaceJoinRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,max_members FROM workspaces WHERE room_code=?",(req.room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404,"Room not found")
    c.execute("SELECT COUNT(*) FROM workspace_members WHERE workspace_id=?",(ws[0],))
    if c.fetchone()[0] >= ws[1]: raise HTTPException(400,"Room full")
    c.execute("INSERT OR IGNORE INTO workspace_members (workspace_id,session_id,role,joined) VALUES (?,?,?,?)",(ws[0],s["id"],"member",datetime.utcnow().isoformat()))
    c.execute("SELECT m.session_id,m.role FROM workspace_members m WHERE m.workspace_id=?",(ws[0],))
    members = [{"session_id":r[0],"role":r[1]} for r in c.fetchall()]
    c.execute("SELECT id,session_id,author,message,is_ai,created FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 50",(ws[0],))
    messages = [{"id":r[0],"session_id":r[1],"author":r[2],"message":r[3],"is_ai":bool(r[4]),"created":r[5]} for r in c.fetchall()]
    conn.commit(); conn.close()
    return {"joined":True,"room_id":ws[0],"members":members,"messages":messages}

@app.post("/api/workspace/message")
def ws_message(req: WorkspaceMessageRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
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
        result, _ = call_ai([{"role":"system","content":ai_prompt}], s["tier"])
        if result:
            c.execute("INSERT INTO workspace_messages (id,workspace_id,session_id,author,message,is_ai,created) VALUES (?,?,?,?,?,?,?)",(sid(),ws[0],s["id"],"CAPITAN AI",result,1,datetime.utcnow().isoformat()))
            conn.commit()
    c.execute("INSERT INTO workspace_messages (id,workspace_id,session_id,author,message,created) VALUES (?,?,?,?,?,?)",(sid(),ws[0],s["id"],"User",req.message,datetime.utcnow().isoformat()))
    conn.commit()
    c.execute("SELECT id,session_id,author,message,is_ai,created FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 50",(ws[0],))
    messages = [{"id":r[0],"session_id":r[1],"author":r[2],"message":r[3],"is_ai":bool(r[4]),"created":r[5]} for r in c.fetchall()]
    conn.close()
    return {"sent":True,"messages":messages}

@app.get("/api/workspace/messages")
def ws_get_messages(room_code: str):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM workspaces WHERE room_code=?",(room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404,"Room not found")
    c.execute("SELECT m.session_id,m.role FROM workspace_members m WHERE m.workspace_id=?",(ws[0],))
    members = [{"session_id":r[0],"role":r[1]} for r in c.fetchall()]
    c.execute("SELECT id,session_id,author,message,is_ai,created FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 50",(ws[0],))
    messages = [{"id":r[0],"session_id":r[1],"author":r[2],"message":r[3],"is_ai":bool(r[4]),"created":r[5]} for r in c.fetchall()]
    conn.close()
    return {"messages":messages,"members":members}

@app.post("/api/workspace/notes")
def ws_save_note(req: WorkspaceNoteRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM workspaces WHERE room_code=?",(req.room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404,"Room not found")
    c.execute("DELETE FROM workspace_notes WHERE workspace_id=?",(ws[0],))
    c.execute("INSERT INTO workspace_notes (id,workspace_id,session_id,author,content,created,updated) VALUES (?,?,?,?,?,?,?)",(sid(),ws[0],s["id"],"User",req.content,datetime.utcnow().isoformat(),datetime.utcnow().isoformat()))
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT",8000))
    uvicorn.run(app,host="0.0.0.0",port=port)