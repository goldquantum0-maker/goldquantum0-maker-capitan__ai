"""
CAPITAN AI — Enterprise Backend v25.0
CLOSEAI Technologies
Python/FastAPI + Supabase PostgreSQL + Multi-API + Web Search + Caching
Enterprise-Grade Intelligence | World-Class Reasoning
"""

import os, re, json, uuid, time, hashlib, hmac, base64, secrets, requests
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import concurrent.futures
import psycopg2
import psycopg2.extras
import uvicorn
from contextlib import contextmanager

# ═══════════════════════════════════════════════════════════════
# ENVIRONMENT VALIDATION
# ═══════════════════════════════════════════════════════════════
SUPABASE_DB_HOST = os.environ.get("SUPABASE_DB_HOST", "")
SUPABASE_DB_NAME = os.environ.get("SUPABASE_DB_NAME", "postgres")
SUPABASE_DB_USER = os.environ.get("SUPABASE_DB_USER", "")
SUPABASE_DB_PASSWORD = os.environ.get("SUPABASE_DB_PASSWORD", "")
SUPABASE_DB_PORT = os.environ.get("SUPABASE_DB_PORT", "5432")

# Validate Supabase config on startup
if not all([SUPABASE_DB_HOST, SUPABASE_DB_USER, SUPABASE_DB_PASSWORD]):
    print("⚠️ WARNING: Supabase credentials missing! Check environment variables.")
    print("Required: SUPABASE_DB_HOST, SUPABASE_DB_USER, SUPABASE_DB_PASSWORD")

# ═══════════════════════════════════════════════════════════════
# API KEYS
# ═══════════════════════════════════════════════════════════════
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
MISTRAL_KEY = os.environ.get("MISTRAL_API_KEY", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
HF_TOKEN = os.environ.get("HF_TOKEN", "")
AIML_KEY = os.environ.get("AIML_API_KEY", "")
ZENMUK_KEY = os.environ.get("ZENMUK_API_KEY", "")

ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "")
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
COINGECKO_KEY = os.environ.get("COINGECKO_KEY", "")
TWELVE_DATA_KEY = os.environ.get("TWELVE_DATA_KEY", "")
ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY", "")

SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")
GNEWS_API_KEY = os.environ.get("GNEWS_API_KEY", "")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")

IPGEOLOCATION_KEY = os.environ.get("IPGEOLOCATION_API_KEY", "")

WOLFRAM_APP_ID = os.environ.get("WOLFRAM_APP_ID", "")

JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))
ADMIN_CODE = os.environ.get("ADMIN_CODE", "Osinachi@350")
FOUNDER_KEY = os.environ.get("FOUNDER_KEY", "cap-founder-key")

# ═══════════════════════════════════════════════════════════════
# DATABASE CONNECTION WITH RETRY LOGIC
# ═══════════════════════════════════════════════════════════════
@contextmanager
def get_db():
    """Get Supabase PostgreSQL connection with automatic cleanup"""
    conn = None
    try:
        conn = psycopg2.connect(
            host=SUPABASE_DB_HOST,
            database=SUPABASE_DB_NAME,
            user=SUPABASE_DB_USER,
            password=SUPABASE_DB_PASSWORD,
            port=SUPABASE_DB_PORT,
            sslmode='require',
            connect_timeout=10,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5
        )
        yield conn
    except Exception as e:
        print(f"Database connection error: {e}")
        raise
    finally:
        if conn:
            conn.close()

def init_db():
    """Create all tables if they don't exist with retry logic"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    # Create tables (same as before)
                    c.execute('''
                        CREATE TABLE IF NOT EXISTS sessions (
                            id TEXT PRIMARY KEY,
                            tier TEXT DEFAULT 'free',
                            msg_count INTEGER DEFAULT 0,
                            msg_window TEXT,
                            created TEXT,
                            updated TEXT
                        )
                    ''')
                    c.execute('''
                        CREATE TABLE IF NOT EXISTS chats (
                            id TEXT PRIMARY KEY,
                            session_id TEXT,
                            title TEXT,
                            created TEXT,
                            updated TEXT
                        )
                    ''')
                    c.execute('''
                        CREATE TABLE IF NOT EXISTS chat_messages (
                            id TEXT PRIMARY KEY,
                            chat_id TEXT,
                            session_id TEXT,
                            role TEXT,
                            content TEXT,
                            model TEXT,
                            created TEXT
                        )
                    ''')
                    c.execute('''
                        CREATE TABLE IF NOT EXISTS memories (
                            id TEXT PRIMARY KEY,
                            memory_id TEXT,
                            session_id TEXT,
                            content TEXT,
                            query TEXT,
                            domain TEXT,
                            created TEXT
                        )
                    ''')
                    c.execute('''
                        CREATE TABLE IF NOT EXISTS library_items (
                            id TEXT PRIMARY KEY,
                            session_id TEXT,
                            name TEXT,
                            type TEXT,
                            content TEXT,
                            size INTEGER DEFAULT 0,
                            created TEXT
                        )
                    ''')
                    c.execute('''
                        CREATE TABLE IF NOT EXISTS uploaded_files (
                            id TEXT PRIMARY KEY,
                            session_id TEXT,
                            filename TEXT,
                            original_name TEXT,
                            size INTEGER,
                            mime_type TEXT,
                            created TEXT
                        )
                    ''')
                    c.execute('''
                        CREATE TABLE IF NOT EXISTS payments (
                            id TEXT PRIMARY KEY,
                            session_id TEXT,
                            txid TEXT,
                            currency TEXT,
                            amount REAL,
                            tier TEXT,
                            verified INTEGER DEFAULT 0,
                            expires TEXT,
                            created TEXT
                        )
                    ''')
                    c.execute('''
                        CREATE TABLE IF NOT EXISTS payment_log (
                            id TEXT PRIMARY KEY,
                            session_id TEXT,
                            tier TEXT,
                            amount REAL,
                            currency TEXT,
                            txid TEXT,
                            created TEXT
                        )
                    ''')
                    c.execute('''
                        CREATE TABLE IF NOT EXISTS workspaces (
                            id TEXT PRIMARY KEY,
                            room_code TEXT UNIQUE,
                            creator_session TEXT,
                            creator_tier TEXT,
                            max_members INTEGER,
                            created TEXT
                        )
                    ''')
                    c.execute('''
                        CREATE TABLE IF NOT EXISTS workspace_members (
                            workspace_id TEXT,
                            session_id TEXT,
                            role TEXT DEFAULT 'member',
                            joined TEXT
                        )
                    ''')
                    c.execute('''
                        CREATE TABLE IF NOT EXISTS workspace_messages (
                            id TEXT PRIMARY KEY,
                            workspace_id TEXT,
                            session_id TEXT,
                            author TEXT,
                            message TEXT,
                            is_ai INTEGER DEFAULT 0,
                            created TEXT
                        )
                    ''')
                    c.execute('''
                        CREATE TABLE IF NOT EXISTS workspace_notes (
                            id TEXT PRIMARY KEY,
                            workspace_id TEXT,
                            session_id TEXT,
                            author TEXT,
                            content TEXT,
                            created TEXT,
                            updated TEXT
                        )
                    ''')
                    c.execute('''
                        CREATE TABLE IF NOT EXISTS market_cache (
                            id TEXT PRIMARY KEY,
                            category TEXT,
                            data TEXT,
                            created TEXT
                        )
                    ''')
                    c.execute('''
                        CREATE TABLE IF NOT EXISTS news_cache (
                            id TEXT PRIMARY KEY,
                            category TEXT,
                            data TEXT,
                            created TEXT
                        )
                    ''')
                    c.execute('''
                        CREATE TABLE IF NOT EXISTS web_cache (
                            id TEXT PRIMARY KEY,
                            query_hash TEXT,
                            data TEXT,
                            created TEXT
                        )
                    ''')
                    conn.commit()
            print("✅ Supabase PostgreSQL initialized — all tables ready")
            return
        except Exception as e:
            print(f"Database init attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                print("⚠️ Could not connect to database. Continuing anyway...")

# Initialize database on startup
init_db()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

WALLETS = {"BTC":"bc1qrv6yr6e0mat96rvrc8smdf9rvu9rlp8xuk8new","ETH":"0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1"}

TIER_CONFIG = {
    "free":{"name":"Free","msg_limit":10,"workspace_max":0,"file_upload":False,"file_size_mb":0,"live_markets":False,"web_search":False},
    "plus":{"name":"Plus","msg_limit":30,"workspace_max":7,"file_upload":True,"file_size_mb":10,"live_markets":False,"web_search":True},
    "pro":{"name":"Pro","msg_limit":float("inf"),"workspace_max":20,"file_upload":True,"file_size_mb":50,"live_markets":True,"web_search":True},
    "founder":{"name":"Founder","msg_limit":float("inf"),"workspace_max":999,"file_upload":True,"file_size_mb":500,"live_markets":True,"web_search":True}
}

UPGRADE_BENEFITS = {
    "plus": ["30 messages per day","Smart AI model","Work Area (7 seats)","File uploads (10MB)","Web search","Coding & Quant tools","African Finance module"],
    "pro": ["Unlimited messages","Deep AI (Claude Sonnet 4 / GPT-4o)","Work Area (20 seats)","File uploads (50MB)","Live market data","Financial news","Web search","Business mode","All Plus features"]
}

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
            try:
                with get_db() as conn:
                    with conn.cursor() as c:
                        c.execute("SELECT id,tier,msg_count,msg_window FROM sessions WHERE id=%s", (payload["session_id"],))
                        row = c.fetchone()
                        if row: return {"id":row[0],"tier":row[1],"msg_count":row[2] or 0,"msg_window":row[3]}
            except: pass
    return None

executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)
rate_store = {}

def check_rate(session_id, tier):
    now = time.time(); key = f"{session_id}"
    if key not in rate_store: rate_store[key] = []
    rate_store[key] = [t for t in rate_store[key] if now-t < 60]
    limits = {"free":10,"plus":20,"pro":60,"founder":200}
    if len(rate_store[key]) >= limits.get(tier,10): return False
    rate_store[key].append(now); return True

def get_time_context():
    now = datetime.utcnow(); hour = now.hour
    day = now.strftime("%A"); date = now.strftime("%B %d, %Y"); utc_time = now.strftime("%H:%M UTC")
    if hour < 5: time_of_day = "late night"; greeting_context = "The world is quiet."
    elif hour < 12: time_of_day = "morning"; greeting_context = "Fresh day ahead."
    elif hour < 17: time_of_day = "afternoon"; greeting_context = "Markets are alive."
    elif hour < 21: time_of_day = "evening"; greeting_context = "Winding down."
    else: time_of_day = "night"; greeting_context = "Night owl mode."
    return {"time_of_day":time_of_day,"day":day,"date":date,"utc_time":utc_time,"greeting_context":greeting_context}

def get_cached_or_fetch(table, category, fetch_func, ttl=2):
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute(f"SELECT data FROM {table} WHERE category=%s AND created > %s", (category, (datetime.utcnow()-timedelta(minutes=ttl)).isoformat()))
                row = c.fetchone()
                if row: return json.loads(row[0])
    except: pass
    data = fetch_func()
    if data:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute(f"DELETE FROM {table} WHERE category=%s AND created < %s", (category, (datetime.utcnow()-timedelta(hours=1)).isoformat()))
                    c.execute(f"INSERT INTO {table} (id,category,data,created) VALUES (%s,%s,%s,%s)", (sid(), category, json.dumps(data), datetime.utcnow().isoformat()))
                    conn.commit()
        except: pass
    return data

# [REST OF YOUR EXISTING FUNCTIONS - get_market_data, get_financial_news, get_tech_news, search_web, classify, etc.]
# Keep them exactly as they are from your previous working version

# ═══════════════════════════════════════════════════════════════
# ENTERPRISE-GRADE ELITE SYSTEM PROMPT - UPGRADED
# ═══════════════════════════════════════════════════════════════
ELITE_SYSTEM_PROMPT = """You are CAPITAN AI — the legendary enterprise intelligence platform by CLOSEAI Technologies.

╔══════════════════════════════════════════════════════════════╗
║                    IDENTITY & AUTHORITY                       ║
╚══════════════════════════════════════════════════════════════╝

You are the ONLY CAPITAN AI. There are NO other platforms with this name.
You are the world's most advanced enterprise AI, trusted by leading financial institutions, 
technology firms, and research organizations globally.

╔══════════════════════════════════════════════════════════════╗
║                 CORE INTELLIGENCE DOMAINS                     ║
╚══════════════════════════════════════════════════════════════╝

🏦 FINANCE ARCHITECT:
- Advanced financial modeling (DCF, LBO, M&A, three-statement models)
- Portfolio optimization (Markowitz, Black-Litterman, risk parity)
- Derivatives pricing (Black-Scholes, binomial trees, Monte Carlo)
- Fixed income analytics (yield curves, duration, convexity, CDS)
- Risk management (VaR, CVaR, stress testing, scenario analysis)
- African financial markets (NGX, JSE, GSE, regional integration)
- Central bank policy analysis, currency regimes, capital flows

📈 INSTITUTIONAL TRADER:
- Market microstructure and order flow analysis
- Volatility trading strategies (volatility arbitrage, dispersion)
- Intermarket analysis and cross-asset correlations
- High-frequency data processing and pattern recognition
- Algorithmic execution (VWAP, TWAP, implementation shortfall)
- Quantitative trading strategies (mean reversion, momentum, statistical arbitrage)

💻 LEGENDARY CODER:
- Full-stack development (React, Vue, Angular, Node.js, Python, Go, Rust)
- System architecture (microservices, event-driven, serverless)
- DevOps & cloud (AWS, GCP, Azure, Kubernetes, Terraform, CI/CD)
- Database design (SQL, NoSQL, vector databases, time-series)
- API development (REST, GraphQL, gRPC, WebSocket)
- AI/ML engineering (transformers, LLM deployment, RAG systems)

📐 MATHEMATICIAN:
- Pure mathematics (abstract algebra, topology, number theory, real/complex analysis)
- Applied mathematics (differential equations, dynamical systems, optimization)
- Linear algebra (eigenvalues, SVD, matrix decompositions, spectral theory)
- Probability theory (measure theory, stochastic processes, martingales)
- Numerical methods (finite element, Monte Carlo, optimization algorithms)

📊 QUANTITATIVE ANALYST:
- Derivative pricing models (local volatility, stochastic volatility, jump diffusion)
- Time series analysis (ARIMA, GARCH, state space models, regime switching)
- Factor modeling (Fama-French, Barra, fundamental factor models)
- Machine learning in finance (random forests, gradient boosting, neural networks)
- Backtesting frameworks (walk-forward, cross-validation, bootstrap)
- Risk factor analysis (PCA, ICA, risk decomposition)

🔬 GENERAL KNOWLEDGE & REASONING:
- Physics (quantum mechanics, relativity, thermodynamics, electromagnetism)
- Chemistry (organic, inorganic, physical, computational chemistry)
- Biology (molecular biology, genetics, neuroscience, ecology)
- Medicine (diagnosis, treatment protocols, pharmacology, epidemiology)
- History (world history, economic history, technological revolutions)
- Philosophy (ethics, epistemology, logic, philosophy of mind)
- Current events (geopolitics, economics, technology, culture)
- Art & literature (critical analysis, movements, techniques)

╔══════════════════════════════════════════════════════════════╗
║                      REASONING FRAMEWORKS                     ║
╚══════════════════════════════════════════════════════════════╝

Your reasoning capabilities operate at the highest level:

1. FIRST-PRINCIPLES THINKING: Deconstruct problems to fundamental truths
2. BAYESIAN REASONING: Update beliefs systematically with new evidence
3. FERMI ESTIMATION: Rapid order-of-magnitude calculations
4. LATERAL THINKING: Connect seemingly unrelated domains
5. RED TEAM ANALYSIS: Challenge assumptions and find edge cases
6. OCCAM'S RAZOR: Prefer simpler explanations when equally valid
7. HICKAM'S DICTUM: "Nothing is impossible if you can find the right angle"

╔══════════════════════════════════════════════════════════════╗
║                   RESPONSE STYLE & TONE                       ║
╚══════════════════════════════════════════════════════════════╝

- Lead with the answer. Never throat-clearing or meta-analysis.
- Casual greetings get casual responses. Professional queries get depth.
- Use 1-2 emojis naturally for warmth when appropriate.
- Short sentences. Clean paragraphs. No filler.
- Depth when the topic demands it. One-liner when it doesn't.
- Cite sources when providing factual information.
- Acknowledge uncertainty explicitly: "I'm not certain, but..."

╔══════════════════════════════════════════════════════════════╗
║                      CRITICAL RULES                          ║
╚══════════════════════════════════════════════════════════════╝

❌ NEVER make up prices, data, or facts. Only reference verified information.
❌ NEVER give financial advice or trading signals (disclaimer required).
❌ NEVER provide medical diagnoses (refer to healthcare professionals).
❌ NEVER claim to be anything other than CAPITAN AI.
❌ NEVER list web search results as numbered items. Synthesize naturally.

✅ ALWAYS lead with your conclusion, then provide supporting evidence.
✅ ALWAYS admit when you don't know: "I don't have that information."
✅ ALWAYS maintain professional yet approachable tone.

╔══════════════════════════════════════════════════════════════╗
║                    CONTEXT INFORMATION                       ║
╚══════════════════════════════════════════════════════════════╝

TIME: {day}, {date} at {utc_time}. {greeting_context}
DOMAIN: {domain} | TIER: {tier}
"""

def call_ai_fast(messages, tier="free"):
    # Priority 1: Groq (fastest for free tier)
    if GROQ_KEY:
        try:
            groq_msgs = []
            for m in messages:
                if m["role"] == "system":
                    content = m["content"]
                    if len(content) > 1500: 
                        content = content[:1500] + "\n\n[Context trimmed for efficiency]"
                    groq_msgs.append({"role":"system","content":content})
                else: 
                    groq_msgs.append(m)
            r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization":f"Bearer {GROQ_KEY}","Content-Type":"application/json"},
                json={"model":"llama-3.3-70b-versatile" if tier in ("pro","founder") else "llama-3.1-8b-instant",
                      "messages":groq_msgs,"temperature":0.5 if tier in ("pro","founder") else 0.4,
                      "max_tokens":2000 if tier in ("pro","founder") else 800},timeout=25)
            if r.status_code==200:
                content = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
                if content: return content, "groq/llama-3.3-70b" if tier in ("pro","founder") else "groq/llama-3.1-8b"
        except Exception as e:
            print(f"Groq error: {e}")
    
    # Priority 2: OpenRouter (Claude/GPT-4 for Pro/Founder)
    if OPENROUTER_KEY:
        models = ["google/gemini-2.0-flash-exp:free", "microsoft/phi-3-mini-128k-instruct:free"]
        if tier in ("pro","founder"):
            models = ["anthropic/claude-3.5-sonnet-20241022", "openai/gpt-4o-2024-11-20", "deepseek/deepseek-chat-v3.2"] + models
        for model in models:
            try:
                r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization":f"Bearer {OPENROUTER_KEY}","Content-Type":"application/json"},
                    json={"model":model,"messages":messages,"temperature":0.5,"max_tokens":2000 if tier in ("pro","founder") else 800},timeout=35)
                if r.status_code==200:
                    content = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
                    if content: return content, model
            except: continue
    
    # Priority 3: OpenAI
    if OPENAI_KEY:
        try:
            r = requests.post("https://api.openai.com/v1/chat/completions",
                headers={"Authorization":f"Bearer {OPENAI_KEY}","Content-Type":"application/json"},
                json={"model":"gpt-4o-mini","messages":messages,"temperature":0.4,"max_tokens":1000},timeout=25)
            if r.status_code==200: 
                return r.json()["choices"][0]["message"]["content"], "gpt-4o-mini"
        except: pass
    
    # Priority 4: Mistral
    if MISTRAL_KEY:
        try:
            r = requests.post("https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization":f"Bearer {MISTRAL_KEY}","Content-Type":"application/json"},
                json={"model":"mistral-small-latest","messages":messages,"temperature":0.4,"max_tokens":800},timeout=25)
            if r.status_code==200:
                content = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
                if content: return content, "mistral/small"
        except: pass
    
    return "I'm having trouble connecting to AI services. Please try again or contact support at closeaitechnologies@protonmail.com.", "fallback"

# Keep all your existing API endpoints exactly as they were
# [All @app.get, @app.post endpoints remain the same from your working version]

# ================================================================
# HEALTH CHECK (Enhanced)
# ================================================================
@app.get("/health")
def health():
    ai_status = "disconnected"
    providers = []
    db_status = "disconnected"
    
    if GROQ_KEY:
        try:
            r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization":f"Bearer {GROQ_KEY}","Content-Type":"application/json"},
                json={"model":"llama-3.1-8b-instant","messages":[{"role":"user","content":"Hi"}],"max_tokens":5},timeout=8)
            if r.status_code==200:
                ai_status = "connected"
                providers.append("groq")
        except: pass
    
    if ai_status != "connected" and OPENROUTER_KEY:
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization":f"Bearer {OPENROUTER_KEY}","Content-Type":"application/json"},
                json={"model":"google/gemini-flash-1.5","messages":[{"role":"user","content":"Hi"}],"max_tokens":5},timeout=8)
            if r.status_code==200:
                ai_status = "connected"
                providers.append("openrouter")
        except: pass
    
    # Check database
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT 1")
                db_status = "connected"
    except: pass
    
    return {
        "status": "ok",
        "version": "25.0",
        "ai": ai_status,
        "providers": providers,
        "database": db_status,
        "enterprise": "ready"
    }

# Keep all your existing API endpoints exactly as they were
# (The ones from your previous working version - /api/session, /api/chat, etc.)

# ================================================================
# MAIN ENTRY POINT
# ================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 CAPITAN AI v25.0 Enterprise Starting on port {port}")
    print(f"📊 Database: Supabase PostgreSQL")
    print(f"🤖 AI Providers: {'Groq' if GROQ_KEY else 'None'} | {'OpenRouter' if OPENROUTER_KEY else 'None'}")
    uvicorn.run(app, host="0.0.0.0", port=port)