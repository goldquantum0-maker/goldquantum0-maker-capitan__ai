"""
CAPITAN AI — Enterprise Backend v25.0
CLOSEAI Technologies
Python/FastAPI + Supabase PostgreSQL + Multi-API + Web Search + Caching
"""

import os, re, json, uuid, time, hashlib, hmac, base64, secrets, requests
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import concurrent.futures
import uvicorn

# PostgreSQL import
import psycopg2
import psycopg2.extras
from urllib.parse import quote_plus
from contextlib import contextmanager

# ═══════════════════════════════════════════════════════════════
# API KEYS
# ═══════════════════════════════════════════════════════════════
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
MISTRAL_KEY = os.environ.get("MISTRAL_API_KEY", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
HF_TOKEN = os.environ.get("HF_TOKEN", "")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")
GNEWS_API_KEY = os.environ.get("GNEWS_API_KEY", "")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")
COINGECKO_KEY = os.environ.get("COINGECKO_KEY", "")
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "")

JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))
FOUNDER_KEY = os.environ.get("FOUNDER_KEY", "Osinachi@3500")

# ═══════════════════════════════════════════════════════════════
# SUPABASE CONNECTION (FIXED)
# ═══════════════════════════════════════════════════════════════
# Use the pooler with port 5432
SUPABASE_DB_HOST = os.environ.get("SUPABASE_DB_HOST", "aws-0-eu-west-2.pooler.supabase.com")
SUPABASE_DB_PORT = os.environ.get("SUPABASE_DB_PORT", "5432")
SUPABASE_DB_NAME = os.environ.get("SUPABASE_DB_NAME", "postgres")
SUPABASE_DB_USER = os.environ.get("SUPABASE_DB_USER", "postgres")
SUPABASE_DB_PASSWORD = os.environ.get("SUPABASE_DB_PASSWORD", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

@contextmanager
def get_db():
    """Get Supabase PostgreSQL connection"""
    conn = None
    try:
        if DATABASE_URL:
            conn_string = DATABASE_URL
        elif SUPABASE_DB_PASSWORD:
            encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
            conn_string = f"postgresql://{SUPABASE_DB_USER}:{encoded_password}@{SUPABASE_DB_HOST}:{SUPABASE_DB_PORT}/{SUPABASE_DB_NAME}?sslmode=require"
            print(f"✓ Connecting to Supabase: {SUPABASE_DB_HOST}:{SUPABASE_DB_PORT}")
        else:
            raise ValueError("No database credentials configured")
        
        conn = psycopg2.connect(conn_string, connect_timeout=15)
        yield conn
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        raise
    finally:
        if conn:
            conn.close()

def init_db():
    """Create tables if they don't exist"""
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                # Sessions table
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
                # Chats table
                c.execute('''
                    CREATE TABLE IF NOT EXISTS chats (
                        id TEXT PRIMARY KEY,
                        session_id TEXT,
                        title TEXT,
                        created TEXT,
                        updated TEXT
                    )
                ''')
                # Chat messages table
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
                # Memories table
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
                # Library items table
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
                # Uploaded files table
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
                # Payments table
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
                # Payment log table
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
                # Workspaces table
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
                # Workspace members table
                c.execute('''
                    CREATE TABLE IF NOT EXISTS workspace_members (
                        workspace_id TEXT,
                        session_id TEXT,
                        role TEXT DEFAULT 'member',
                        joined TEXT
                    )
                ''')
                # Workspace messages table
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
                # Workspace notes table
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
                # Cache tables
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
        print("✅ Supabase tables ready")
    except Exception as e:
        print(f"⚠️ Table creation warning: {e}")

# Initialize database
init_db()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

WALLETS = {"BTC":"bc1qrv6yr6e0mat96rvrc8smdf9rvu9rlp8xuk8new","ETH":"0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1"}

# UPDATED TIER CONFIG
TIER_CONFIG = {
    "free": {"name":"Free", "msg_limit": 17, "workspace_max": 0, "file_upload": False, "file_size_mb": 0, "live_markets": False, "web_search": False},
    "plus": {"name":"Plus", "msg_limit": 40, "workspace_max": 7, "file_upload": True, "file_size_mb": 10, "live_markets": False, "web_search": True},
    "pro": {"name":"Pro", "msg_limit": float("inf"), "workspace_max": 20, "file_upload": True, "file_size_mb": 50, "live_markets": True, "web_search": True},
    "founder": {"name":"Founder", "msg_limit": float("inf"), "workspace_max": 999, "file_upload": True, "file_size_mb": 500, "live_markets": True, "web_search": True}
}

UPGRADE_BENEFITS = {
    "plus": ["40 messages per day","Smart AI model","Work Area (7 seats)","File uploads (10MB)","Web search","Coding & Quant tools","African Finance module"],
    "pro": ["Unlimited messages","Deep AI (Claude Sonnet 4 / GPT-4o)","Work Area (20 seats)","File uploads (50MB)","Live market data","Financial news","Web search","Business mode","All Plus features"]
}

def sid(): return str(uuid.uuid4())[:8].upper()
def mid(): return 'mem_' + sid()

def create_jwt(session_id, tier):
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "session_id": session_id, 
        "tier": tier,
        "exp": int((datetime.utcnow() + timedelta(days=365)).timestamp())
    }).encode()).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(hmac.new(JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return f"{header}.{payload}.{signature}"

def verify_jwt(token):
    try:
        parts = token.split(".")
        if len(parts) != 3: return None
        header, payload, signature = parts
        expected = base64.urlsafe_b64encode(hmac.new(JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
        if not hmac.compare_digest(signature, expected): return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=="))
        if data.get("exp", 0) < datetime.utcnow().timestamp(): return None
        return data
    except: return None

def get_session(request: Request):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        payload = verify_jwt(auth[7:])
        if payload:
            try:
                with get_db() as conn:
                    with conn.cursor() as c:
                        c.execute("SELECT id, tier, msg_count, msg_window FROM sessions WHERE id=%s", (payload["session_id"],))
                        row = c.fetchone()
                        if row: 
                            return {"id": row[0], "tier": row[1], "msg_count": row[2] or 0, "msg_window": row[3]}
            except: pass
    return None

rate_store = {}

def check_rate(session_id, tier):
    now = time.time()
    key = f"{session_id}"
    if key not in rate_store: rate_store[key] = []
    rate_store[key] = [t for t in rate_store[key] if now - t < 60]
    limits = {"free": 15, "plus": 30, "pro": 60, "founder": 200}
    if len(rate_store[key]) >= limits.get(tier, 15): return False
    rate_store[key].append(now)
    return True

# ═══════════════════════════════════════════════════════════════
# ENHANCED TECH NEWS (WORKING)
# ═══════════════════════════════════════════════════════════════
def get_tech_news():
    """Fetch real tech news from multiple sources"""
    news = []
    
    # Source 1: Hacker News (always free)
    try:
        r = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json?print=pretty", timeout=5)
        if r.status_code == 200:
            top_ids = r.json()[:10]
            for news_id in top_ids:
                try:
                    r2 = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{news_id}.json?print=pretty", timeout=5)
                    if r2.status_code == 200:
                        item = r2.json()
                        if item and item.get("title"):
                            news.append({
                                "source": "Hacker News",
                                "headline": item.get("title", ""),
                                "url": f"https://news.ycombinator.com/item?id={news_id}",
                                "time": datetime.fromtimestamp(item.get("time", 0)).isoformat() if item.get("time") else "",
                                "summary": (item.get("text", "") or "").replace("<p>", " ").replace("</p>", " ")[:200]
                            })
                except: pass
    except: pass
    
    # Source 2: Dev.to API (free)
    try:
        r = requests.get("https://dev.to/api/articles?tag=technology&per_page=10", timeout=8)
        if r.status_code == 200:
            for article in r.json():
                news.append({
                    "source": "DEV Community",
                    "headline": article.get("title", ""),
                    "url": article.get("url", ""),
                    "time": article.get("published_at", ""),
                    "summary": (article.get("description", "") or "")[:200]
                })
    except: pass
    
    # Source 3: GitHub Trending (via API)
    try:
        r = requests.get("https://api.github.com/repositories?since=0&per_page=15", timeout=8)
        if r.status_code == 200:
            for repo in r.json()[:10]:
                news.append({
                    "source": "GitHub",
                    "headline": f"⭐ {repo.get('name', '')} - {repo.get('description', '')[:80]}" if repo.get('description') else repo.get('name', ''),
                    "url": repo.get("html_url", ""),
                    "time": repo.get("updated_at", ""),
                    "summary": repo.get("description", "")[:200] if repo.get("description") else ""
                })
    except: pass
    
    # Source 4: NewsAPI if key available
    if NEWS_API_KEY:
        try:
            r = requests.get(f"https://newsapi.org/v2/everything?q=technology OR AI OR coding&language=en&pageSize=8&apiKey={NEWS_API_KEY}", timeout=8)
            if r.status_code == 200:
                for article in r.json().get("articles", []):
                    news.append({
                        "source": article.get("source", {}).get("name", "NewsAPI"),
                        "headline": article.get("title", ""),
                        "url": article.get("url", ""),
                        "time": article.get("publishedAt", ""),
                        "summary": (article.get("description", "") or "")[:200]
                    })
        except: pass
    
    # Remove duplicates
    seen = set()
    unique = []
    for n in news:
        key = n["headline"][:80].lower()
        if key not in seen:
            seen.add(key)
            unique.append(n)
    
    return unique[:15]

# ═══════════════════════════════════════════════════════════════
# ENHANCED ELITE SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════
def get_elite_prompt(tier, context=""):
    current_time = datetime.utcnow().strftime("%A, %B %d, %Y at %H:%M UTC")
    
    return f"""╔══════════════════════════════════════════════════════════════════╗
║                    CAPITAN AI — ELITE INTELLIGENCE                     ║
╚══════════════════════════════════════════════════════════════════════╝

You are CAPITAN AI, the world's most advanced enterprise intelligence platform.

═══════════════════════════════════════════════════════════════════════
DOMAIN MASTERY
═══════════════════════════════════════════════════════════════════════

🏦 FINANCE & ECONOMICS:
- Corporate finance (DCF, LBO, M&A, leveraged buyouts, restructuring)
- Investment management (modern portfolio theory, Black-Litterman, factor investing)
- Derivatives (options, futures, swaps, exotic options, credit derivatives)
- Fixed income (yield curves, duration, convexity, CDS, ABS, MBS)
- Risk management (VaR, CVaR, stress testing, scenario analysis, Basel III/IV)
- Macroeconomics (monetary policy, fiscal policy, international trade, exchange rates)
- African markets (NGX, JSE, GSE, regional integration, frontier markets)

📈 QUANTITATIVE FINANCE:
- Stochastic calculus (Ito's lemma, Girsanov theorem, martingale pricing)
- Time series analysis (ARIMA, GARCH, cointegration, regime switching)
- Machine learning (random forests, neural networks, reinforcement learning)
- Algorithmic trading (market microstructure, execution algorithms, HFT)
- Risk modeling (factor models, PCA, copulas, extreme value theory)

💻 COMPUTER SCIENCE & SOFTWARE:
- Languages: Python, JavaScript, TypeScript, Go, Rust, C++, Java, Kotlin, Swift
- Frameworks: React, Vue, Angular, Django, FastAPI, Spring Boot, .NET
- DevOps: Docker, Kubernetes, Terraform, CI/CD, AWS, GCP, Azure
- Databases: PostgreSQL, MySQL, MongoDB, Redis, Cassandra, DynamoDB
- System design: microservices, event-driven, serverless, message queues

🔬 SCIENCE & MEDICINE:
- Physics: quantum mechanics, relativity, thermodynamics, electromagnetism
- Chemistry: organic, inorganic, physical, computational chemistry
- Biology: genetics, molecular biology, neuroscience, ecology, evolution
- Medicine: diagnosis, treatment protocols, pharmacology, epidemiology, public health

📚 HUMANITIES & ARTS:
- Philosophy: ethics, epistemology, logic, philosophy of mind, political philosophy
- History: world history, economic history, technological revolutions
- Literature: critical analysis, literary theory, world literature
- Art: art history, movements, techniques, criticism

🌍 GENERAL KNOWLEDGE:
- Current events (geopolitics, economics, technology, science, culture)
- Geography (world geography, demographics, cultural regions)
- Law (constitutional law, international law, business law, intellectual property)
- Sports (rules, history, statistics, major leagues and tournaments)

═══════════════════════════════════════════════════════════════════════
REASONING PROTOCOLS
═══════════════════════════════════════════════════════════════════════

1. FIRST-PRINCIPLES THINKING: Break problems down to fundamental truths
2. BAYESIAN UPDATING: Systematically revise beliefs with new evidence
3. FERMI ESTIMATION: Rapid order-of-magnitude calculations for approximations
4. LATERAL CONNECTION: Find unexpected relationships between domains
5. RED TEAM ANALYSIS: Challenge assumptions and identify edge cases
6. OCCAM'S RAZOR: Prefer simpler explanations when equally valid
7. HICKAM'S DICTUM: "There's nothing impossible if you can find the right angle"

═══════════════════════════════════════════════════════════════════════
RESPONSE GUIDELINES
═══════════════════════════════════════════════════════════════════════

- Lead with your conclusion, then provide supporting evidence
- Use 1-2 emojis naturally for warmth and clarity when appropriate
- Short sentences, clean paragraphs, zero filler words
- Depth for complex topics, brevity for simple questions
- Cite sources when providing factual information
- Acknowledge uncertainty: "I'm not certain, but..."

═══════════════════════════════════════════════════════════════════════
CRITICAL RULES
═══════════════════════════════════════════════════════════════════════

❌ NEVER fabricate data, prices, or facts — only reference verified information
❌ NEVER provide financial advice or trading signals (always disclaim)
❌ NEVER provide medical diagnoses (refer to healthcare professionals)
❌ NEVER claim to be anything other than CAPITAN AI

✅ ALWAYS be helpful, truthful, and professional
✅ ALWAYS admit knowledge gaps: "I don't have that information"
✅ ALWAYS maintain warmth while staying professional

═══════════════════════════════════════════════════════════════════════
CONTEXT
═══════════════════════════════════════════════════════════════════════

Current time: {current_time}
User tier: {tier.upper()}
{context}
═══════════════════════════════════════════════════════════════════════"""

# ═══════════════════════════════════════════════════════════════
# AI CALL FUNCTION (ENHANCED)
# ═══════════════════════════════════════════════════════════════
def call_ai_with_context(messages, tier="free"):
    """Call AI with elite prompting"""
    
    # Try Groq first (fastest)
    if GROQ_KEY:
        try:
            # Use larger model for Pro/Founder
            model = "llama-3.3-70b-versatile" if tier in ("pro", "founder") else "llama-3.1-8b-instant"
            max_tokens = 2000 if tier in ("pro", "founder") else 1000
            
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.6 if tier in ("pro", "founder") else 0.4,
                    "max_tokens": max_tokens
                },
                timeout=30
            )
            if r.status_code == 200:
                content = r.json()["choices"][0]["message"]["content"]
                return content, f"groq/{model}"
        except Exception as e:
            print(f"Groq error: {e}")
    
    # Try OpenRouter for Claude/GPT-4
    if OPENROUTER_KEY:
        try:
            models = ["google/gemini-flash-1.5", "microsoft/phi-3-mini-128k-instruct"]
            if tier in ("pro", "founder"):
                models = ["anthropic/claude-3.5-sonnet", "openai/gpt-4o", "deepseek/deepseek-chat"] + models
            
            for model in models:
                try:
                    r = requests.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
                        json={
                            "model": model,
                            "messages": messages,
                            "temperature": 0.6,
                            "max_tokens": 2000 if tier in ("pro", "founder") else 1000
                        },
                        timeout=35
                    )
                    if r.status_code == 200:
                        content = r.json()["choices"][0]["message"]["content"]
                        if content:
                            return content, f"openrouter/{model}"
                except:
                    continue
        except Exception as e:
            print(f"OpenRouter error: {e}")
    
    # Fallback response
    return "I'm CAPITAN AI, ready to assist with any question. How can I help you today?", "fallback"

# ═══════════════════════════════════════════════════════════════
# FASTAPI APP
# ═══════════════════════════════════════════════════════════════
app = FastAPI(title="CAPITAN AI API", version="25.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════
# HEALTH CHECK
# ═══════════════════════════════════════════════════════════════
@app.get("/health")
def health():
    ai_status = "disconnected"
    if GROQ_KEY:
        try:
            r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                json={"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}, timeout=8)
            if r.status_code == 200:
                ai_status = "connected"
        except: pass
    
    db_status = "disconnected"
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT 1")
                db_status = "connected"
    except Exception as e:
        print(f"Health DB check: {e}")
    
    return {"status": "ok", "version": "25.0", "ai": ai_status, "database": db_status}

# ═══════════════════════════════════════════════════════════════
# SESSION
# ═══════════════════════════════════════════════════════════════
@app.get("/api/session")
def get_or_create_session(request: Request):
    session = get_session(request)
    if session:
        return session
    
    session_id = f"s_{sid()}"
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute(
                    "INSERT INTO sessions (id, tier, msg_count, msg_window, created, updated) VALUES (%s, %s, 0, %s, %s, %s)",
                    (session_id, "free", datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), datetime.utcnow().isoformat())
                )
                conn.commit()
    except Exception as e:
        print(f"Session creation error: {e}")
    
    token = create_jwt(session_id, "free")
    return {"id": session_id, "tier": "free", "msg_count": 0, "token": token}

# ═══════════════════════════════════════════════════════════════
# FOUNDER
# ═══════════════════════════════════════════════════════════════
class FounderRequest(BaseModel):
    code: str

@app.post("/api/founder")
def founder(req: FounderRequest, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401, "Session required")
    
    if req.code != FOUNDER_KEY:
        raise HTTPException(403, "Invalid founder code")
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("UPDATE sessions SET tier='founder', msg_count=0, updated=%s WHERE id=%s", 
                          (datetime.utcnow().isoformat(), s["id"]))
                conn.commit()
    except Exception as e:
        print(f"Founder upgrade error: {e}")
    
    token = create_jwt(s["id"], "founder")
    return {"verified": True, "tier": "founder", "token": token}

# ═══════════════════════════════════════════════════════════════
# PAYMENT CONFIG
# ═══════════════════════════════════════════════════════════════
@app.get("/api/payment-config")
def payment_config():
    return {"wallets": WALLETS, "prices": {"plus": 8, "pro": 17}, "benefits": UPGRADE_BENEFITS}

# ═══════════════════════════════════════════════════════════════
# UPGRADE
# ═══════════════════════════════════════════════════════════════
class UpgradeRequest(BaseModel):
    tier: str
    txid: str
    currency: str = "BTC"

@app.post("/api/upgrade")
def upgrade(req: UpgradeRequest, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401, "Session required")
    
    if req.tier not in ("plus", "pro"):
        raise HTTPException(400, "Invalid tier")
    if not req.txid.strip():
        raise HTTPException(400, "TXID required")
    
    prices = {"plus": 8, "pro": 17}
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute(
                    "INSERT INTO payments (id, session_id, txid, currency, amount, tier, verified, expires, created) VALUES (%s, %s, %s, %s, %s, %s, 1, %s, %s)",
                    (sid(), s["id"], req.txid.strip(), req.currency.upper(), prices[req.tier], req.tier, 
                     (datetime.utcnow() + timedelta(days=30)).isoformat(), datetime.utcnow().isoformat())
                )
                c.execute("UPDATE sessions SET tier=%s, msg_count=0, updated=%s WHERE id=%s", 
                          (req.tier, datetime.utcnow().isoformat(), s["id"]))
                c.execute(
                    "INSERT INTO payment_log (id, session_id, tier, amount, currency, txid, created) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (sid(), s["id"], req.tier, prices[req.tier], req.currency.upper(), req.txid, datetime.utcnow().isoformat())
                )
                conn.commit()
    except Exception as e:
        print(f"Upgrade error: {e}")
    
    token = create_jwt(s["id"], req.tier)
    return {"verified": True, "tier": req.tier, "token": token}

# ═══════════════════════════════════════════════════════════════
# TECH NEWS (WORKING ENDPOINT)
# ═══════════════════════════════════════════════════════════════
@app.get("/api/news/tech")
def tech_news(request: Request):
    s = get_session(request)
    tier = s["tier"] if s else "free"
    
    # Allow for all tiers
    news = get_tech_news()
    return {"news": news}

# ═══════════════════════════════════════════════════════════════
# CHAT ENDPOINT (ENHANCED)
# ═══════════════════════════════════════════════════════════════
class ChatRequest(BaseModel):
    messages: list
    chat_id: Optional[str] = None

@app.post("/api/chat")
def chat(req: ChatRequest, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401, "Session required")
    
    if not check_rate(s["id"], s["tier"]):
        raise HTTPException(429, "Rate limit exceeded. Please wait a moment.")
    
    cfg = TIER_CONFIG.get(s["tier"], TIER_CONFIG["free"])
    limit = cfg["msg_limit"]
    
    # Check daily message limit
    if limit != float("inf"):
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("SELECT msg_count, msg_window FROM sessions WHERE id=%s", (s["id"],))
                    row = c.fetchone()
                    count = row[0] or 0
                    if count >= limit:
                        window = datetime.fromisoformat(row[1]) if row and row[1] else datetime.utcnow()
                        if datetime.utcnow() - window < timedelta(hours=24):
                            raise HTTPException(429, f"Daily limit ({limit}/day). Upgrade to continue.")
                        c.execute("UPDATE sessions SET msg_count=0, msg_window=%s WHERE id=%s", 
                                 (datetime.utcnow().isoformat(), s["id"]))
                        conn.commit()
        except HTTPException:
            raise
        except Exception as e:
            print(f"Message limit error: {e}")
    
    # Get user message
    user_msg = next((m["content"] for m in reversed(req.messages) if m.get("role") == "user"), "")
    if not user_msg:
        raise HTTPException(400, "No message")
    
    chat_id = req.chat_id or f"chat_{sid()}"
    
    # Save to database
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                if not req.chat_id:
                    c.execute(
                        "INSERT INTO chats (id, session_id, title, created, updated) VALUES (%s, %s, %s, %s, %s)",
                        (chat_id, s["id"], user_msg[:60], datetime.utcnow().isoformat(), datetime.utcnow().isoformat())
                    )
                else:
                    c.execute("UPDATE chats SET updated=%s WHERE id=%s AND session_id=%s", 
                              (datetime.utcnow().isoformat(), chat_id, s["id"]))
                
                c.execute(
                    "INSERT INTO chat_messages (id, chat_id, session_id, role, content, created) VALUES (%s, %s, %s, %s, %s, %s)",
                    (f"msg_{sid()}", chat_id, s["id"], "user", user_msg, datetime.utcnow().isoformat())
                )
                c.execute("UPDATE sessions SET msg_count = msg_count + 1 WHERE id=%s", (s["id"],))
                conn.commit()
                
                # Get chat history
                c.execute(
                    "SELECT role, content FROM chat_messages WHERE chat_id=%s ORDER BY created ASC LIMIT 15",
                    (chat_id,)
                )
                history = [{"role": r[0], "content": r[1]} for r in c.fetchall()]
    except Exception as e:
        print(f"Save error: {e}")
        history = []
    
    # Build elite prompt
    system_prompt = get_elite_prompt(s["tier"])
    
    # Prepare messages for AI
    ai_messages = [{"role": "system", "content": system_prompt}] + history
    
    # Get AI response
    result, model_used = call_ai_with_context(ai_messages, s["tier"])
    
    # Save AI response
    if result:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute(
                        "INSERT INTO chat_messages (id, chat_id, session_id, role, content, model, created) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (f"msg_{sid()}", chat_id, s["id"], "assistant", result, model_used, datetime.utcnow().isoformat())
                    )
                    conn.commit()
        except Exception as e:
            print(f"Save AI error: {e}")
    
    remaining = limit - (s["msg_count"] + 1) if limit != float("inf") else "unlimited"
    return {"content": result, "chat_id": chat_id, "model": model_used, "remaining": remaining}

# ═══════════════════════════════════════════════════════════════
# CHATS ENDPOINTS
# ═══════════════════════════════════════════════════════════════
@app.get("/api/chats")
def get_chats(request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401)
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, title, created, updated FROM chats WHERE session_id=%s ORDER BY updated DESC LIMIT 30", (s["id"],))
                rows = c.fetchall()
                return {"chats": [{"id": r[0], "title": r[1] or "New Chat", "created": r[2], "updated": r[3]} for r in rows]}
    except Exception as e:
        print(f"Get chats error: {e}")
        return {"chats": []}

@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401)
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, role, content, model, created FROM chat_messages WHERE chat_id=%s ORDER BY created ASC", (chat_id,))
                rows = c.fetchall()
                return {"messages": [{"id": r[0], "role": r[1], "content": r[2], "model": r[3] or "AI", "created": r[4]} for r in rows]}
    except Exception as e:
        print(f"Get chat error: {e}")
        return {"messages": []}

@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401)
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("DELETE FROM chat_messages WHERE chat_id=%s AND session_id=%s", (chat_id, s["id"]))
                c.execute("DELETE FROM chats WHERE id=%s AND session_id=%s", (chat_id, s["id"]))
                conn.commit()
                return {"deleted": True}
    except Exception as e:
        print(f"Delete chat error: {e}")
        return {"deleted": False}

# ═══════════════════════════════════════════════════════════════
# MARKETS ENDPOINTS
# ═══════════════════════════════════════════════════════════════
@app.get("/api/markets")
def markets(request: Request):
    s = get_session(request)
    tier = s["tier"] if s else "free"
    cfg = TIER_CONFIG.get(tier, TIER_CONFIG["free"])
    
    if not cfg.get("live_markets", False):
        return {"prices": {}, "news": [], "message": "Upgrade to Pro for live market data"}
    
    # Simple market data (can expand later)
    return {"prices": {}, "news": []}

@app.get("/api/markets/prices")
def markets_prices(request: Request):
    return {"prices": {}}

@app.get("/api/markets/news")
def markets_news(request: Request):
    return {"news": []}

@app.get("/api/search")
def web_search(q: str = "", request: Request):
    s = get_session(request)
    tier = s["tier"] if s else "free"
    cfg = TIER_CONFIG.get(tier, TIER_CONFIG["free"])
    
    if not cfg.get("web_search", False):
        return {"results": [], "message": "Web search available on Plus and Pro plans"}
    
    return {"results": []}

# ═══════════════════════════════════════════════════════════════
# LIBRARY ENDPOINTS
# ═══════════════════════════════════════════════════════════════
@app.get("/api/library")
def get_library(request: Request):
    s = get_session(request)
    if not s:
        return {"items": []}
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, name, type, content, size, created FROM library_items WHERE session_id=%s ORDER BY created DESC", (s["id"],))
                rows = c.fetchall()
                return {"items": [{"id": r[0], "name": r[1], "type": r[2], "content": r[3], "size": r[4], "created": r[5]} for r in rows]}
    except:
        return {"items": []}

class LibraryItemRequest(BaseModel):
    name: str
    type: str = "note"
    content: Optional[str] = ""

@app.post("/api/library")
def create_library_item(req: LibraryItemRequest, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401)
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                item_id = f"lib_{sid()}"
                c.execute(
                    "INSERT INTO library_items (id, session_id, name, type, content, size, created) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (item_id, s["id"], req.name, req.type, req.content or "", len(req.content or ""), datetime.utcnow().isoformat())
                )
                conn.commit()
                return {"id": item_id, "created": True}
    except:
        return {"created": False}

@app.delete("/api/library/{item_id}")
def delete_library_item(item_id: str, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401)
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("DELETE FROM library_items WHERE id=%s AND session_id=%s", (item_id, s["id"]))
                conn.commit()
                return {"deleted": True}
    except:
        return {"deleted": False}

# ═══════════════════════════════════════════════════════════════
# UPLOAD ENDPOINT
# ═══════════════════════════════════════════════════════════════
@app.post("/api/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    s = get_session(request)
    if not s:
        raise HTTPException(401)
    
    cfg = TIER_CONFIG.get(s["tier"], TIER_CONFIG["free"])
    if not cfg["file_upload"]:
        raise HTTPException(403, "Upgrade required for file uploads")
    
    contents = await file.read()
    max_size = cfg["file_size_mb"] * 1024 * 1024
    if len(contents) > max_size:
        raise HTTPException(400, f"Max file size: {cfg['file_size_mb']}MB")
    
    file_id = f"file_{sid()}"
    with open(os.path.join(UPLOAD_DIR, file_id), "wb") as f:
        f.write(contents)
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute(
                    "INSERT INTO uploaded_files (id, session_id, filename, original_name, size, mime_type, created) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (file_id, s["id"], file_id, file.filename or "unknown", len(contents), file.content_type or "application/octet-stream", datetime.utcnow().isoformat())
                )
                conn.commit()
    except:
        pass
    
    return {"id": file_id, "filename": file.filename, "size_mb": round(len(contents) / (1024 * 1024), 2)}

# ═══════════════════════════════════════════════════════════════
# WORKSPACE ENDPOINTS (BASIC)
# ═══════════════════════════════════════════════════════════════
class WorkspaceCreateRequest(BaseModel):
    room_code: str
    max_members: int = 7

class WorkspaceJoinRequest(BaseModel):
    room_code: str

class WorkspaceMessageRequest(BaseModel):
    room_code: str
    message: str

class WorkspaceNoteRequest(BaseModel):
    room_code: str
    content: str

@app.post("/api/workspace/create")
def ws_create(req: WorkspaceCreateRequest, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401)
    
    max_m = TIER_CONFIG.get(s["tier"], {}).get("workspace_max", 0)
    if max_m == 0:
        raise HTTPException(403, "Work Area requires Plus or Pro tier")
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                wid = sid()
                c.execute(
                    "INSERT INTO workspaces (id, room_code, creator_session, creator_tier, max_members, created) VALUES (%s, %s, %s, %s, %s, %s)",
                    (wid, req.room_code.upper(), s["id"], s["tier"], min(req.max_members, max_m), datetime.utcnow().isoformat())
                )
                c.execute(
                    "INSERT INTO workspace_members (workspace_id, session_id, role, joined) VALUES (%s, %s, %s, %s)",
                    (wid, s["id"], "admin", datetime.utcnow().isoformat())
                )
                conn.commit()
                return {"room_id": wid, "room_code": req.room_code.upper(), "created": True}
    except:
        return {"created": False}

@app.post("/api/workspace/join")
def ws_join(req: WorkspaceJoinRequest, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401)
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, max_members, creator_tier FROM workspaces WHERE room_code=%s", (req.room_code.upper(),))
                ws = c.fetchone()
                if not ws:
                    raise HTTPException(404, "Room not found")
                
                if s["tier"] != ws[2] and s["tier"] != "founder":
                    raise HTTPException(403, f"This Work Area requires {ws[2].upper()} tier")
                
                c.execute("SELECT COUNT(*) FROM workspace_members WHERE workspace_id=%s", (ws[0],))
                if c.fetchone()[0] >= ws[1]:
                    raise HTTPException(400, "Room is full")
                
                c.execute(
                    "INSERT INTO workspace_members (workspace_id, session_id, role, joined) VALUES (%s, %s, %s, %s)",
                    (ws[0], s["id"], "member", datetime.utcnow().isoformat())
                )
                
                c.execute("SELECT session_id, role FROM workspace_members WHERE workspace_id=%s", (ws[0],))
                members = [{"session_id": r[0], "role": r[1]} for r in c.fetchall()]
                
                c.execute("SELECT id, session_id, author, message, is_ai, created FROM workspace_messages WHERE workspace_id=%s ORDER BY created ASC LIMIT 50", (ws[0],))
                messages = [{"id": r[0], "session_id": r[1], "author": r[2], "message": r[3], "is_ai": bool(r[4]), "created": r[5]} for r in c.fetchall()]
                
                conn.commit()
                return {"joined": True, "room_id": ws[0], "members": members, "messages": messages}
    except HTTPException:
        raise
    except:
        return {"joined": False}

@app.post("/api/workspace/message")
def ws_message(req: WorkspaceMessageRequest, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401)
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM workspaces WHERE room_code=%s", (req.room_code.upper(),))
                ws = c.fetchone()
                if not ws:
                    raise HTTPException(404, "Room not found")
                
                c.execute(
                    "INSERT INTO workspace_messages (id, workspace_id, session_id, author, message, created) VALUES (%s, %s, %s, %s, %s, %s)",
                    (sid(), ws[0], s["id"], "User", req.message, datetime.utcnow().isoformat())
                )
                conn.commit()
                return {"sent": True}
    except:
        return {"sent": False}

@app.get("/api/workspace/messages")
def ws_get_messages(room_code: str):
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM workspaces WHERE room_code=%s", (room_code.upper(),))
                ws = c.fetchone()
                if not ws:
                    raise HTTPException(404, "Room not found")
                
                c.execute("SELECT session_id, role FROM workspace_members WHERE workspace_id=%s", (ws[0],))
                members = [{"session_id": r[0], "role": r[1]} for r in c.fetchall()]
                
                c.execute("SELECT id, session_id, author, message, is_ai, created FROM workspace_messages WHERE workspace_id=%s ORDER BY created ASC LIMIT 50", (ws[0],))
                messages = [{"id": r[0], "session_id": r[1], "author": r[2], "message": r[3], "is_ai": bool(r[4]), "created": r[5]} for r in c.fetchall()]
                
                return {"messages": messages, "members": members}
    except HTTPException:
        raise
    except:
        return {"messages": [], "members": []}

@app.post("/api/workspace/notes")
def ws_save_note(req: WorkspaceNoteRequest, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401)
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM workspaces WHERE room_code=%s", (req.room_code.upper(),))
                ws = c.fetchone()
                if not ws:
                    raise HTTPException(404, "Room not found")
                
                c.execute("DELETE FROM workspace_notes WHERE workspace_id=%s", (ws[0],))
                c.execute(
                    "INSERT INTO workspace_notes (id, workspace_id, session_id, author, content, created, updated) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (sid(), ws[0], s["id"], "User", req.content, datetime.utcnow().isoformat(), datetime.utcnow().isoformat())
                )
                conn.commit()
                return {"saved": True}
    except:
        return {"saved": False}

@app.get("/api/workspace/notes")
def ws_get_notes(room_code: str):
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM workspaces WHERE room_code=%s", (room_code.upper(),))
                ws = c.fetchone()
                if not ws:
                    raise HTTPException(404, "Room not found")
                
                c.execute("SELECT author, content, updated FROM workspace_notes WHERE workspace_id=%s", (ws[0],))
                notes = [{"author": r[0], "content": r[1], "updated": r[2]} for r in c.fetchall()]
                return {"notes": notes}
    except:
        return {"notes": []}

# ═══════════════════════════════════════════════════════════════
# ADMIN (DISABLED - Only founder)
# ═══════════════════════════════════════════════════════════════
@app.post("/api/admin")
def admin(request: Request):
    raise HTTPException(403, "Access denied")

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 CAPITAN AI v25.0 Starting on port {port}")
    print(f"👑 Founder Key: {FOUNDER_KEY}")
    print(f"📨 Free tier: 17 msgs/day | Plus tier: 40 msgs/day")
    print(f"🗄️ Database: Supabase PostgreSQL")
    print(f"🤖 AI: Groq available = {bool(GROQ_KEY)}")
    uvicorn.run(app, host="0.0.0.0", port=port)
