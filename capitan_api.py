"""
CAPITAN AI — Enterprise Backend v25.0
CLOSEAI Technologies
Complete Production System | PostgreSQL + Supabase Storage + Full Intelligence
"""

import os
import re
import json
import uuid
import time
import hashlib
import hmac
import base64
import secrets
import requests
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from contextlib import contextmanager
from urllib.parse import quote_plus

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pydantic_settings import BaseSettings
import psycopg2
import psycopg2.extras
import uvicorn

# Supabase client for storage
from supabase import create_client, Client

# ================================================================
# SECTION 1: LOGGING SETUP
# ================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================================================================
# SECTION 2: CONFIGURATION
# ================================================================
class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = ""
    SUPABASE_DB_HOST: str = ""
    SUPABASE_DB_PORT: str = "5432"
    SUPABASE_DB_NAME: str = "postgres"
    SUPABASE_DB_USER: str = "postgres"
    SUPABASE_DB_PASSWORD: str = ""
    
    # Supabase Client
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_BUCKET: str = "capitan-uploads"
    
    # Security
    JWT_SECRET: str = secrets.token_hex(32)
    FOUNDER_KEY: str = "Osinachi@3500"
    
    # AI Providers
    OPENROUTER_KEY: str = ""
    OPENAI_KEY: str = ""
    MISTRAL_KEY: str = ""
    GROQ_KEY: str = ""
    HF_TOKEN: str = ""
    
    # Market Data
    ALPHA_VANTAGE_KEY: str = ""
    FRED_API_KEY: str = ""
    FINNHUB_API_KEY: str = ""
    COINGECKO_KEY: str = ""
    TWELVE_DATA_KEY: str = ""
    ETHERSCAN_API_KEY: str = ""
    
    # News & Search
    SERPAPI_KEY: str = ""
    GNEWS_API_KEY: str = ""
    NEWS_API_KEY: str = ""
    
    # Other
    WOLFRAM_APP_ID: str = ""
    
    # CORS
    ALLOWED_ORIGINS: list = ["*"]
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# ================================================================
# SECTION 3: SUPABASE CLIENT INITIALIZATION
# ================================================================
supabase_client: Client = None
if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
    supabase_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    logger.info("✅ Supabase client initialized")
else:
    logger.info("⚠️ Supabase client not configured")

def get_supabase() -> Client:
    """Get Supabase client for storage features"""
    if not supabase_client:
        raise HTTPException(503, "Supabase client not configured")
    return supabase_client

def init_supabase_storage():
    """Initialize Supabase storage bucket"""
    if supabase_client:
        try:
            buckets = supabase_client.storage.list_buckets()
            bucket_exists = any(b.get("name") == settings.SUPABASE_BUCKET for b in buckets)
            if not bucket_exists:
                supabase_client.storage.create_bucket(settings.SUPABASE_BUCKET, {"public": True})
                logger.info(f"✅ Supabase bucket '{settings.SUPABASE_BUCKET}' created")
            else:
                logger.info(f"✅ Supabase bucket '{settings.SUPABASE_BUCKET}' ready")
        except Exception as e:
            logger.warning(f"Supabase storage init: {e}")

# ================================================================
# SECTION 4: DATABASE LAYER
# ================================================================
@contextmanager
def get_db():
    """Get database connection with automatic cleanup and retry"""
    conn = None
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            if settings.DATABASE_URL:
                conn_string = settings.DATABASE_URL
            elif settings.SUPABASE_DB_PASSWORD:
                encoded_password = quote_plus(settings.SUPABASE_DB_PASSWORD)
                conn_string = f"postgresql://{settings.SUPABASE_DB_USER}:{encoded_password}@{settings.SUPABASE_DB_HOST}:{settings.SUPABASE_DB_PORT}/{settings.SUPABASE_DB_NAME}?sslmode=require"
            else:
                raise ValueError("No database configuration found")
            
            conn = psycopg2.connect(conn_string, connect_timeout=10)
            yield conn
            return
        except Exception as e:
            logger.warning(f"Database attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                raise
    if conn:
        conn.close()

# ================================================================
# SECTION 5: TABLE CREATION (15 Tables + Storage Columns)
# ================================================================
def init_db():
    """Create all tables if they don't exist"""
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                # 1. Sessions
                c.execute('''
                    CREATE TABLE IF NOT EXISTS sessions (
                        id TEXT PRIMARY KEY,
                        tier TEXT DEFAULT 'free',
                        msg_count INTEGER DEFAULT 0,
                        msg_window TEXT,
                        created TIMESTAMP,
                        updated TIMESTAMP
                    )
                ''')
                
                # 2. Chats
                c.execute('''
                    CREATE TABLE IF NOT EXISTS chats (
                        id TEXT PRIMARY KEY,
                        session_id TEXT,
                        title TEXT,
                        created TIMESTAMP,
                        updated TIMESTAMP
                    )
                ''')
                
                # 3. Chat Messages
                c.execute('''
                    CREATE TABLE IF NOT EXISTS chat_messages (
                        id TEXT PRIMARY KEY,
                        chat_id TEXT,
                        session_id TEXT,
                        role TEXT,
                        content TEXT,
                        model TEXT,
                        tokens INTEGER,
                        latency_ms INTEGER,
                        created TIMESTAMP
                    )
                ''')
                
                # 4. Memories
                c.execute('''
                    CREATE TABLE IF NOT EXISTS memories (
                        id TEXT PRIMARY KEY,
                        memory_id TEXT,
                        session_id TEXT,
                        content TEXT,
                        query TEXT,
                        domain TEXT,
                        created TIMESTAMP
                    )
                ''')
                
                # 5. Library Items
                c.execute('''
                    CREATE TABLE IF NOT EXISTS library_items (
                        id TEXT PRIMARY KEY,
                        session_id TEXT,
                        name TEXT,
                        type TEXT,
                        content TEXT,
                        size INTEGER DEFAULT 0,
                        created TIMESTAMP
                    )
                ''')
                
                # 6. Uploaded Files (with storage columns)
                c.execute('''
                    CREATE TABLE IF NOT EXISTS uploaded_files (
                        id TEXT PRIMARY KEY,
                        session_id TEXT,
                        filename TEXT,
                        original_name TEXT,
                        size INTEGER,
                        mime_type TEXT,
                        storage_path TEXT,
                        public_url TEXT,
                        created TIMESTAMP
                    )
                ''')
                
                # 7. Payments
                c.execute('''
                    CREATE TABLE IF NOT EXISTS payments (
                        id TEXT PRIMARY KEY,
                        session_id TEXT,
                        txid TEXT,
                        currency TEXT,
                        amount REAL,
                        tier TEXT,
                        verified INTEGER DEFAULT 0,
                        expires TIMESTAMP,
                        created TIMESTAMP
                    )
                ''')
                
                # 8. Payment Log
                c.execute('''
                    CREATE TABLE IF NOT EXISTS payment_log (
                        id TEXT PRIMARY KEY,
                        session_id TEXT,
                        tier TEXT,
                        amount REAL,
                        currency TEXT,
                        txid TEXT,
                        created TIMESTAMP
                    )
                ''')
                
                # 9. Workspaces
                c.execute('''
                    CREATE TABLE IF NOT EXISTS workspaces (
                        id TEXT PRIMARY KEY,
                        room_code TEXT UNIQUE,
                        creator_session TEXT,
                        creator_tier TEXT,
                        max_members INTEGER,
                        created TIMESTAMP
                    )
                ''')
                
                # 10. Workspace Members
                c.execute('''
                    CREATE TABLE IF NOT EXISTS workspace_members (
                        workspace_id TEXT,
                        session_id TEXT,
                        role TEXT DEFAULT 'member',
                        joined TIMESTAMP,
                        PRIMARY KEY (workspace_id, session_id)
                    )
                ''')
                
                # 11. Workspace Messages
                c.execute('''
                    CREATE TABLE IF NOT EXISTS workspace_messages (
                        id TEXT PRIMARY KEY,
                        workspace_id TEXT,
                        session_id TEXT,
                        author TEXT,
                        message TEXT,
                        is_ai INTEGER DEFAULT 0,
                        created TIMESTAMP
                    )
                ''')
                
                # 12. Workspace Notes
                c.execute('''
                    CREATE TABLE IF NOT EXISTS workspace_notes (
                        id TEXT PRIMARY KEY,
                        workspace_id TEXT,
                        session_id TEXT,
                        author TEXT,
                        content TEXT,
                        created TIMESTAMP,
                        updated TIMESTAMP
                    )
                ''')
                
                # 13. Market Cache
                c.execute('''
                    CREATE TABLE IF NOT EXISTS market_cache (
                        id TEXT PRIMARY KEY,
                        category TEXT,
                        data TEXT,
                        created TIMESTAMP
                    )
                ''')
                
                # 14. News Cache
                c.execute('''
                    CREATE TABLE IF NOT EXISTS news_cache (
                        id TEXT PRIMARY KEY,
                        category TEXT,
                        data TEXT,
                        created TIMESTAMP
                    )
                ''')
                
                # 15. Web Cache
                c.execute('''
                    CREATE TABLE IF NOT EXISTS web_cache (
                        id TEXT PRIMARY KEY,
                        query_hash TEXT,
                        data TEXT,
                        created TIMESTAMP
                    )
                ''')
                
                conn.commit()
        logger.info("✅ All 15 database tables ready")
        
        # Initialize Supabase storage
        init_supabase_storage()
        
    except Exception as e:
        logger.warning(f"Database init warning: {e}")

init_db()

# ================================================================
# SECTION 6: UTILITY FUNCTIONS
# ================================================================
def sid(): return str(uuid.uuid4())[:8].upper()
def mid(): return 'mem_' + sid()

# ================================================================
# SECTION 7: SECURITY & JWT AUTH (FIXED SESSION HANDLING)
# ================================================================
def create_jwt(session_id, tier):
    """Create JWT token for authentication"""
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "session_id": session_id,
        "tier": tier,
        "exp": int((datetime.utcnow() + timedelta(days=365)).timestamp())
    }).encode()).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(
        hmac.new(settings.JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")
    return f"{header}.{payload}.{signature}"

def verify_jwt(token):
    """Verify and decode JWT token"""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, payload, signature = parts
        expected = base64.urlsafe_b64encode(
            hmac.new(settings.JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
        ).decode().rstrip("=")
        if not hmac.compare_digest(signature, expected):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=="))
        if data.get("exp", 0) < datetime.utcnow().timestamp():
            return None
        return data
    except:
        return None

def get_session(request: Request):
    """Get current session from JWT - AUTO-CREATES missing sessions"""
    auth = request.headers.get("Authorization", "")
    
    if not auth.startswith("Bearer "):
        return None
    
    payload = verify_jwt(auth[7:])
    if not payload:
        return None
    
    session_id = payload.get("session_id")
    if not session_id:
        return None
    
    tier = payload.get("tier", "free")
    if tier not in ("free", "plus", "pro", "founder"):
        tier = "free"
    
    now = datetime.utcnow().isoformat()
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, tier, msg_count, msg_window FROM sessions WHERE id = %s", (session_id,))
                row = c.fetchone()
                
                if not row:
                    logger.info(f"Session {session_id} not found, creating...")
                    c.execute(
                        "INSERT INTO sessions (id, tier, msg_count, msg_window, created, updated) VALUES (%s, %s, 0, %s, %s, %s)",
                        (session_id, tier, now, now, now)
                    )
                    conn.commit()
                    return {"id": session_id, "tier": tier, "msg_count": 0, "msg_window": now}
                
                if tier != row[1]:
                    logger.info(f"Tier mismatch: JWT={tier}, DB={row[1]}. Updating...")
                    c.execute("UPDATE sessions SET tier=%s, updated=%s WHERE id=%s", (tier, now, session_id))
                    conn.commit()
                    return {"id": row[0], "tier": tier, "msg_count": row[2] or 0, "msg_window": row[3]}
                
                return {"id": row[0], "tier": row[1], "msg_count": row[2] or 0, "msg_window": row[3]}
                
    except Exception as e:
        logger.error(f"Database error in get_session: {e}")
        return None

# ================================================================
# SECTION 8: RATE LIMITING
# ================================================================
rate_store = {}

def check_rate(session_id, tier):
    """Check rate limit (per minute)"""
    now = time.time()
    key = f"{session_id}"
    
    if key not in rate_store:
        rate_store[key] = []
    
    rate_store[key] = [t for t in rate_store[key] if now - t < 60]
    
    limits = {"free": 15, "plus": 30, "pro": 60, "founder": 200}
    limit = limits.get(tier, 15)
    
    if len(rate_store[key]) >= limit:
        return False
    
    rate_store[key].append(now)
    return True

# ================================================================
# SECTION 9: TIME CONTEXT
# ================================================================
def get_time_context():
    now = datetime.utcnow()
    hour = now.hour
    day = now.strftime("%A")
    date = now.strftime("%B %d, %Y")
    utc_time = now.strftime("%H:%M UTC")
    
    if hour < 5:
        time_of_day = "late night"
        greeting_context = "The world is quiet."
    elif hour < 12:
        time_of_day = "morning"
        greeting_context = "Fresh day ahead."
    elif hour < 17:
        time_of_day = "afternoon"
        greeting_context = "Markets are alive."
    elif hour < 21:
        time_of_day = "evening"
        greeting_context = "Winding down."
    else:
        time_of_day = "night"
        greeting_context = "Night owl mode."
    
    return {
        "time_of_day": time_of_day,
        "day": day,
        "date": date,
        "utc_time": utc_time,
        "greeting_context": greeting_context
    }

# ================================================================
# SECTION 10: MARKET DATA
# ================================================================
def get_market_data():
    results = {}
    
    if settings.COINGECKO_KEY:
        try:
            ids = "bitcoin,ethereum,ripple,cardano,solana,polkadot,dogecoin,avalanche-2,chainlink,uniswap,binancecoin,tron,toncoin,near"
            r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                params={"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true"},
                headers={"x-cg-demo-api-key": settings.COINGECKO_KEY}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                nm = {"bitcoin": "BTC", "ethereum": "ETH", "ripple": "XRP", "cardano": "ADA",
                      "solana": "SOL", "polkadot": "DOT", "dogecoin": "DOGE", "avalanche-2": "AVAX",
                      "chainlink": "LINK", "uniswap": "UNI", "binancecoin": "BNB", "tron": "TRX",
                      "toncoin": "TON", "near": "NEAR"}
                for k, v in data.items():
                    results[nm.get(k, k.upper())] = {
                        "price": v["usd"],
                        "change": round(v.get("usd_24h_change", 0), 2),
                        "source": "CoinGecko"
                    }
        except:
            pass
    
    try:
        syms = "^GSPC,^IXIC,^DJI,^FTSE,^N225,AAPL,MSFT,NVDA,TSLA,GOOGL,META,AMZN,GC=F,CL=F,SI=F,EURUSD=X,GBPUSD=X,USDJPY=X,USDGHS=X,USDNGN=X,USDZAR=X,USDKES=X"
        r = requests.get(f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={syms}",
            params={"fields": "regularMarketPrice,regularMarketPreviousClose,shortName,regularMarketChangePercent"},
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code == 200:
            for i in r.json().get("quoteResponse", {}).get("result", []):
                name = i.get("shortName") or i.get("symbol", "")
                price = i.get("regularMarketPrice")
                prev = i.get("regularMarketPreviousClose")
                if price and prev:
                    chg = i.get("regularMarketChangePercent")
                    results[name] = {
                        "price": price,
                        "change": round(chg, 2) if chg else round(((price - prev) / prev) * 100, 2),
                        "source": "Yahoo Finance"
                    }
    except:
        pass
    
    return results

# ================================================================
# SECTION 11: NEWS FUNCTIONS
# ================================================================
def get_financial_news():
    news = []
    
    if settings.NEWS_API_KEY:
        try:
            r = requests.get("https://newsapi.org/v2/top-headlines",
                params={"category": "business", "language": "en", "pageSize": 12, "apiKey": settings.NEWS_API_KEY}, timeout=10)
            if r.status_code == 200:
                for a in r.json().get("articles", []):
                    news.append({
                        "source": a.get("source", {}).get("name", "NewsAPI"),
                        "headline": a.get("title", ""),
                        "url": a.get("url", ""),
                        "time": a.get("publishedAt", ""),
                        "summary": (a.get("description") or "")[:300]
                    })
        except:
            pass
    
    if settings.GNEWS_API_KEY:
        try:
            r = requests.get("https://gnews.io/api/v4/search",
                params={"q": "finance markets stocks economy", "lang": "en", "max": 12, "apikey": settings.GNEWS_API_KEY}, timeout=10)
            if r.status_code == 200:
                for a in r.json().get("articles", []):
                    news.append({
                        "source": a.get("source", {}).get("name", "GNews"),
                        "headline": a.get("title", ""),
                        "url": a.get("url", ""),
                        "time": a.get("publishedAt", ""),
                        "summary": (a.get("description") or "")[:300]
                    })
        except:
            pass
    
    seen = set()
    unique = []
    for n in news:
        k = n["headline"][:100].lower().strip()
        if k and k not in seen:
            seen.add(k)
            unique.append(n)
    
    unique.sort(key=lambda x: x.get("time", ""), reverse=True)
    return unique[:15]

def get_tech_news():
    news = []
    
    if settings.NEWS_API_KEY:
        try:
            r = requests.get("https://newsapi.org/v2/everything",
                params={"q": "AI artificial intelligence coding startup innovation",
                        "language": "en", "pageSize": 12, "sortBy": "publishedAt", "apiKey": settings.NEWS_API_KEY}, timeout=10)
            if r.status_code == 200:
                for a in r.json().get("articles", []):
                    news.append({
                        "source": a.get("source", {}).get("name", "NewsAPI"),
                        "headline": a.get("title", ""),
                        "url": a.get("url", ""),
                        "time": a.get("publishedAt", ""),
                        "summary": (a.get("description") or "")[:300]
                    })
        except:
            pass
    
    seen = set()
    unique = []
    for n in news:
        k = n["headline"][:100].lower().strip()
        if k and k not in seen:
            seen.add(k)
            unique.append(n)
    
    unique.sort(key=lambda x: x.get("time", ""), reverse=True)
    return unique[:15]

# ================================================================
# SECTION 12: WEB SEARCH
# ================================================================
def search_web(query, num_results=5):
    results = []
    query_hash = hashlib.md5(query.lower().encode()).hexdigest()
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT data FROM web_cache WHERE query_hash=%s AND created > %s",
                         (query_hash, (datetime.utcnow() - timedelta(hours=1)).isoformat()))
                row = c.fetchone()
                if row:
                    return json.loads(row[0])
    except:
        pass
    
    if settings.SERPAPI_KEY:
        try:
            r = requests.get("https://serpapi.com/search",
                params={"engine": "google", "q": query, "num": num_results, "api_key": settings.SERPAPI_KEY}, timeout=8)
            if r.status_code == 200:
                for item in r.json().get("organic_results", [])[:num_results]:
                    results.append({
                        "title": item.get("title", ""),
                        "snippet": item.get("snippet", "")[:250],
                        "url": item.get("link", ""),
                        "source": "Google"
                    })
        except:
            pass
    
    if results:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("INSERT INTO web_cache (id,query_hash,data,created) VALUES (%s,%s,%s,%s)",
                             (sid(), query_hash, json.dumps(results), datetime.utcnow().isoformat()))
                    conn.commit()
        except:
            pass
    
    return results

# ================================================================
# SECTION 13: ELITE SYSTEM PROMPT
# ================================================================
ELITE_SYSTEM_PROMPT = """You are CAPITAN AI — the legendary enterprise intelligence platform by CLOSEAI Technologies.

🏦 FINANCE ARCHITECT: DCF, LBO, M&A, portfolio optimization, derivatives pricing
📈 INSTITUTIONAL TRADER: Market microstructure, volatility trading, algorithmic execution
💻 LEGENDARY CODER: Full-stack, system architecture, DevOps, databases
📐 MATHEMATICIAN: Pure math, applied math, linear algebra, probability
📊 QUANTITATIVE ANALYST: Time series, factor modeling, ML in finance, backtesting
🔬 GENERAL KNOWLEDGE: Physics, chemistry, biology, medicine, history, philosophy

RESPONSE STYLE:
- Lead with the answer. No throat-clearing.
- Use 1-2 emojis naturally for warmth.
- Short sentences. Clean paragraphs.
- NEVER make up prices or data.
- NEVER give financial advice or medical diagnoses.

TIME: {day}, {date} at {utc_time}. {greeting_context}
DOMAIN: {domain} | TIER: {tier}
"""

# ================================================================
# SECTION 14: QUERY CLASSIFICATION
# ================================================================
def classify(q):
    q = q.lower()
    
    if re.search(r'who are you|what are you|identity|introduce yourself', q):
        return 'identity'
    if re.search(r'who|what|when|where|why|how|news|latest|current|today|search', q) and len(q.split()) > 3:
        return 'web_search'
    if re.search(r'crispr|dna|rna|protein|cell|gene|genome|physics|quantum|chemistry|biology|neuroscience|health|medicine|disease', q):
        return 'science'
    if re.search(r'```|def |class |import |docker|kubernetes|aws|api|graphql|sql|database|react|node|javascript|python|rust', q):
        return 'coding'
    if re.search(r'stochastic|ito|black.scholes|monte carlo|sharpe|var|option pricing|derivative|garch|arima|backtest', q):
        return 'quant'
    if re.search(r'dcf|ebitda|valuation|wacc|capm|pe ratio|forex|federal reserve|inflation|gdp|stock|trading|portfolio|crypto|bitcoin', q):
        return 'finance'
    if re.search(r'prove|proof|theorem|lemma|integral|derivative|matrix|eigenvalue|probability|statistics', q):
        return 'math'
    return 'general'

# ================================================================
# SECTION 15: SYSTEM PROMPT BUILDER
# ================================================================
def system_prompt(domain, tier, session_id=None, web_results=None):
    tc = get_time_context()
    base = ELITE_SYSTEM_PROMPT.replace("{domain}", domain).replace("{tier}", tier)
    base = base.replace("{day}", tc["day"]).replace("{date}", tc["date"])
    base = base.replace("{utc_time}", tc["utc_time"])
    base = base.replace("{greeting_context}", tc["greeting_context"])
    
    if session_id:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("SELECT query, domain FROM memories WHERE session_id=%s ORDER BY created DESC LIMIT 3", (session_id,))
                    rows = c.fetchall()
                    if rows:
                        base += "\n\nUSER CONTEXT:\n" + "\n".join([f"• [{r[1]}] {r[0][:100]}" for r in rows])
        except:
            pass
    
    if web_results:
        base += "\n\nWEB RESULTS:\n" + "\n".join([f"• {r['title']}: {r['snippet'][:200]}" for r in web_results[:3]])
    
    if tier in ("pro", "founder"):
        try:
            md = get_market_data()
            if md:
                base += "\n\nLIVE MARKETS:\n" + "\n".join([f"• {s}: ${d['price']:.2f}" for s, d in list(md.items())[:5]])
        except:
            pass
    
    return base

# ================================================================
# SECTION 16: AI SERVICE (Multi-Provider)
# ================================================================
def call_ai_fast(messages, tier="free"):
    # Groq
    if settings.GROQ_KEY:
        try:
            groq_msgs = []
            for m in messages:
                if m["role"] == "system" and tier == "free":
                    m["content"] = m["content"][:1000]
                groq_msgs.append(m)
            
            model = "llama-3.3-70b-versatile" if tier in ("pro", "founder") else "llama-3.1-8b-instant"
            r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.GROQ_KEY}", "Content-Type": "application/json"},
                json={"model": model, "messages": groq_msgs, "temperature": 0.5,
                      "max_tokens": 2000 if tier in ("pro", "founder") else 800}, timeout=25)
            if r.status_code == 200:
                content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    return content, model
        except:
            pass
    
    # OpenRouter
    if settings.OPENROUTER_KEY:
        models = ["google/gemini-flash-1.5", "mistral/mistral-7b-instruct"]
        if tier in ("pro", "founder"):
            models = ["anthropic/claude-3.5-sonnet", "openai/gpt-4o"] + models
        for model in models:
            try:
                r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.OPENROUTER_KEY}", "Content-Type": "application/json"},
                    json={"model": model, "messages": messages, "temperature": 0.5,
                          "max_tokens": 2000 if tier in ("pro", "founder") else 800}, timeout=35)
                if r.status_code == 200:
                    content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                    if content:
                        return content, model
            except:
                continue
    
    return "I'm having trouble connecting. Please try again.", "fallback"

# ================================================================
# SECTION 17: FASTAPI APP WITH CORS
# ================================================================
app = FastAPI(title="CAPITAN AI API", version="25.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================================================================
# SECTION 18: HEALTH & DEBUG
# ================================================================
@app.get("/health")
def health():
    db_status = "disconnected"
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT 1")
                db_status = "connected"
    except:
        pass
    
    ai_status = "connected" if (settings.GROQ_KEY or settings.OPENROUTER_KEY) else "disconnected"
    providers = []
    if settings.GROQ_KEY: providers.append("groq")
    if settings.OPENROUTER_KEY: providers.append("openrouter")
    
    return {"status": "ok", "version": "25.0", "database": db_status, "ai": ai_status, "providers": providers}

@app.get("/api/debug-token")
def debug_token(request: Request):
    auth = request.headers.get("Authorization", "")
    result = {"has_auth": bool(auth), "token_valid": False, "session_exists": False}
    
    if auth.startswith("Bearer "):
        payload = verify_jwt(auth[7:])
        result["token_valid"] = payload is not None
        if payload:
            result["session_id"] = payload.get("session_id")
            try:
                with get_db() as conn:
                    with conn.cursor() as c:
                        c.execute("SELECT id FROM sessions WHERE id=%s", (payload.get("session_id"),))
                        result["session_exists"] = c.fetchone() is not None
            except:
                pass
    
    return result

# ================================================================
# SECTION 19: SESSION ENDPOINT
# ================================================================
@app.get("/api/session")
def get_or_create_session(request: Request):
    session = get_session(request)
    if session:
        return session
    
    session_id = f"s_{sid()}"
    tier = "free"
    now = datetime.utcnow().isoformat()
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute(
                    "INSERT INTO sessions (id, tier, msg_count, msg_window, created, updated) VALUES (%s, %s, 0, %s, %s, %s)",
                    (session_id, tier, now, now, now)
                )
                conn.commit()
    except Exception as e:
        logger.error(f"Session creation error: {e}")
    
    token = create_jwt(session_id, tier)
    return {"id": session_id, "tier": tier, "msg_count": 0, "token": token}

# ================================================================
# SECTION 20: PAYMENT CONFIGURATION
# ================================================================
WALLETS = {
    "BTC": "bc1qrv6yr6e0mat96rvrc8smdf9rvu9rlp8xuk8new",
    "ETH": "0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1"
}

TIER_CONFIG = {
    "free": {"name": "Free", "msg_limit": 17, "workspace_max": 0, "file_upload": False, "live_markets": False, "web_search": False},
    "plus": {"name": "Plus", "msg_limit": 40, "workspace_max": 7, "file_upload": True, "live_markets": False, "web_search": True},
    "pro": {"name": "Pro", "msg_limit": float("inf"), "workspace_max": 20, "file_upload": True, "live_markets": True, "web_search": True},
    "founder": {"name": "Founder", "msg_limit": float("inf"), "workspace_max": 999, "file_upload": True, "live_markets": True, "web_search": True}
}

UPGRADE_BENEFITS = {
    "plus": ["40 messages/day", "Smart AI", "Work Area (7 seats)", "File uploads", "Web search"],
    "pro": ["Unlimited messages", "Deep AI (Claude/GPT-4)", "Work Area (20 seats)", "Live market data", "All Plus features"]
}

@app.get("/api/payment-config")
def payment_config():
    return {"wallets": WALLETS, "prices": {"plus": 8, "pro": 17}, "benefits": UPGRADE_BENEFITS}

# ================================================================
# SECTION 21: MARKET & NEWS ENDPOINTS
# ================================================================
@app.get("/api/markets")
def markets(request: Request):
    s = get_session(request)
    cfg = TIER_CONFIG.get(s["tier"], TIER_CONFIG["free"]) if s else TIER_CONFIG["free"]
    if not cfg.get("live_markets", False):
        return {"prices": {}, "news": [], "message": "Pro tier required"}
    return {"prices": get_market_data(), "news": get_financial_news()}

@app.get("/api/markets/prices")
def markets_prices(request: Request):
    s = get_session(request)
    cfg = TIER_CONFIG.get(s["tier"], TIER_CONFIG["free"]) if s else TIER_CONFIG["free"]
    if not cfg.get("live_markets", False):
        return {"prices": {}, "message": "Upgrade to Pro"}
    return {"prices": get_market_data()}

@app.get("/api/markets/news")
def markets_news(request: Request):
    s = get_session(request)
    cfg = TIER_CONFIG.get(s["tier"], TIER_CONFIG["free"]) if s else TIER_CONFIG["free"]
    if not cfg.get("live_markets", False):
        return {"news": [], "message": "Upgrade to Pro"}
    return {"news": get_financial_news()}

@app.get("/api/news/tech")
def tech_news(request: Request):
    s = get_session(request)
    if not s or s["tier"] not in ("pro", "founder"):
        return {"news": [], "message": "Pro tier required"}
    return {"news": get_tech_news()}

@app.get("/api/search")
def web_search_endpoint(q: str, request: Request):
    s = get_session(request)
    if not s or not TIER_CONFIG.get(s["tier"], {}).get("web_search", False):
        return {"results": [], "message": "Web search on Plus and Pro"}
    return {"results": search_web(q)}

# ================================================================
# SECTION 22: CHAT HISTORY ENDPOINTS
# ================================================================
@app.get("/api/chats")
def get_chats(request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401)
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id,title,created,updated FROM chats WHERE session_id=%s ORDER BY updated DESC LIMIT 30", (s["id"],))
                rows = c.fetchall()
                return {"chats": [{"id": r[0], "title": r[1] or "New Chat", "created": r[2].isoformat() if r[2] else None, "updated": r[3].isoformat() if r[3] else None} for r in rows]}
    except:
        return {"chats": []}

@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401)
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM chats WHERE id=%s AND session_id=%s", (chat_id, s["id"]))
                if not c.fetchone():
                    raise HTTPException(404)
                c.execute("SELECT id,role,content,model,created FROM chat_messages WHERE chat_id=%s ORDER BY created ASC", (chat_id,))
                rows = c.fetchall()
                return {"messages": [{"id": r[0], "role": r[1], "content": r[2], "model": r[3] or "AI", "created": r[4].isoformat() if r[4] else None} for r in rows]}
    except HTTPException:
        raise
    except:
        raise HTTPException(500)

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
    except:
        raise HTTPException(500)

# ================================================================
# SECTION 23: MAIN CHAT ENDPOINT
# ================================================================
class ChatRequest(BaseModel):
    messages: list
    chat_id: Optional[str] = None

@app.post("/api/chat")
def chat(req: ChatRequest, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401)
    
    if not check_rate(s["id"], s["tier"]):
        raise HTTPException(429, "Rate limit exceeded")
    
    cfg = TIER_CONFIG.get(s["tier"], TIER_CONFIG["free"])
    limit = cfg["msg_limit"]
    
    # Daily limit
    if limit != float("inf"):
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("SELECT msg_count,msg_window FROM sessions WHERE id=%s", (s["id"],))
                    row = c.fetchone()
                    count = row[0] or 0
                    if count >= limit:
                        window = datetime.fromisoformat(row[1]) if row and row[1] else datetime.utcnow()
                        if datetime.utcnow() - window < timedelta(hours=24):
                            raise HTTPException(429, f"Daily limit ({limit}/day). Upgrade to continue.")
                        c.execute("UPDATE sessions SET msg_count=0, msg_window=%s WHERE id=%s", (datetime.utcnow().isoformat(), s["id"]))
                        conn.commit()
        except HTTPException:
            raise
        except:
            pass
    
    user_msg = next((m["content"] for m in reversed(req.messages) if m.get("role") == "user"), "")
    if not user_msg:
        raise HTTPException(400, "No message")
    
    chat_id = req.chat_id or f"chat_{sid()}"
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                if not req.chat_id:
                    c.execute("INSERT INTO chats (id,session_id,title,created,updated) VALUES (%s,%s,%s,%s,%s)",
                             (chat_id, s["id"], user_msg[:60], datetime.utcnow(), datetime.utcnow()))
                else:
                    c.execute("UPDATE chats SET updated=%s WHERE id=%s AND session_id=%s", (datetime.utcnow(), chat_id, s["id"]))
                
                c.execute("INSERT INTO chat_messages (id,chat_id,session_id,role,content,created) VALUES (%s,%s,%s,%s,%s,%s)",
                         (f"msg_{sid()}", chat_id, s["id"], "user", user_msg, datetime.utcnow()))
                c.execute("UPDATE sessions SET msg_count = msg_count + 1 WHERE id=%s", (s["id"],))
                conn.commit()
                
                c.execute("SELECT role,content FROM chat_messages WHERE chat_id=%s ORDER BY created ASC LIMIT 15", (chat_id,))
                history = [{"role": r[0], "content": r[1]} for r in c.fetchall()]
    except Exception as e:
        logger.error(f"Save error: {e}")
        history = []
    
    domain = classify(user_msg)
    web_results = None
    if domain == 'web_search' or cfg.get("web_search", False):
        try:
            web_results = search_web(user_msg, 4)
        except:
            pass
    
    prompt = system_prompt(domain, s["tier"], s["id"], web_results)
    result, model_used = call_ai_fast([{"role": "system", "content": prompt}] + history, s["tier"])
    
    if result:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("INSERT INTO chat_messages (id,chat_id,session_id,role,content,model,created) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                             (f"msg_{sid()}", chat_id, s["id"], "assistant", result, model_used, datetime.utcnow()))
                    c.execute("INSERT INTO memories (id,memory_id,session_id,content,query,domain,created) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                             (sid(), mid(), s["id"], result[:500] if result else "", user_msg, domain, datetime.utcnow()))
                    conn.commit()
        except:
            pass
    
    remaining = limit - (s["msg_count"] + 1) if limit != float("inf") else "unlimited"
    return {
        "content": result,
        "chat_id": chat_id,
        "model": model_used,
        "remaining": remaining,
        "web_search_used": web_results is not None
    }

# ================================================================
# SECTION 24: UPGRADE & FOUNDER ENDPOINTS
# ================================================================
class UpgradeRequest(BaseModel):
    tier: str
    txid: str
    currency: str = "BTC"

@app.post("/api/upgrade")
def upgrade(req: UpgradeRequest, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401)
    if req.tier not in ("plus", "pro"):
        raise HTTPException(400, "Invalid tier")
    if not req.txid.strip():
        raise HTTPException(400, "TXID required")
    
    prices = {"plus": 8, "pro": 17}
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO payments (id,session_id,txid,currency,amount,tier,verified,expires,created) VALUES (%s,%s,%s,%s,%s,%s,1,%s,%s)",
                         (sid(), s["id"], req.txid.strip(), req.currency.upper(), prices[req.tier], req.tier,
                          (datetime.utcnow() + timedelta(days=30)).isoformat(), datetime.utcnow()))
                c.execute("UPDATE sessions SET tier=%s, msg_count=0, updated=%s WHERE id=%s",
                         (req.tier, datetime.utcnow().isoformat(), s["id"]))
                c.execute("INSERT INTO payment_log (id,session_id,tier,amount,currency,txid,created) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                         (sid(), s["id"], req.tier, prices[req.tier], req.currency.upper(), req.txid, datetime.utcnow()))
                conn.commit()
    except:
        pass
    
    token = create_jwt(s["id"], req.tier)
    return {"verified": True, "tier": req.tier, "token": token}

class FounderRequest(BaseModel):
    code: str

@app.post("/api/founder")
def founder(req: FounderRequest, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401)
    if req.code != settings.FOUNDER_KEY:
        raise HTTPException(403, "Invalid founder code")
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("UPDATE sessions SET tier='founder', msg_count=0, updated=%s WHERE id=%s",
                         (datetime.utcnow().isoformat(), s["id"]))
                conn.commit()
    except:
        pass
    
    token = create_jwt(s["id"], "founder")
    return {"verified": True, "tier": "founder", "token": token}

# ================================================================
# SECTION 25: LIBRARY ENDPOINTS
# ================================================================
@app.get("/api/library")
def get_library(request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401)
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id,name,type,content,size,created FROM library_items WHERE session_id=%s ORDER BY created DESC", (s["id"],))
                rows = c.fetchall()
                return {"items": [{"id": r[0], "name": r[1], "type": r[2], "content": r[3], "size": r[4], "created": r[5].isoformat() if r[5] else None} for r in rows]}
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
                c.execute("INSERT INTO library_items (id,session_id,name,type,content,size,created) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                         (item_id, s["id"], req.name, req.type, req.content or "", len(req.content or ""), datetime.utcnow()))
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

# ================================================================
# SECTION 26: FILE UPLOAD (Supabase Storage)
# ================================================================
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/api/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    s = get_session(request)
    if not s:
        raise HTTPException(401)
    
    cfg = TIER_CONFIG.get(s["tier"], TIER_CONFIG["free"])
    if not cfg["file_upload"]:
        raise HTTPException(403, "Upgrade required")
    
    contents = await file.read()
    max_size = 50 if s["tier"] == "pro" else (500 if s["tier"] == "founder" else 10)
    if len(contents) / (1024 * 1024) > max_size:
        raise HTTPException(400, f"Max {max_size}MB")
    
    file_id = f"file_{sid()}"
    file_path = f"{s['id']}/{file_id}_{file.filename}"
    public_url = None
    uploaded_to_supabase = False
    
    # Try Supabase Storage
    if supabase_client:
        try:
            supabase_client.storage.from_(settings.SUPABASE_BUCKET).upload(
                file_path, contents,
                {"content-type": file.content_type or "application/octet-stream"}
            )
            public_url = supabase_client.storage.from_(settings.SUPABASE_BUCKET).get_public_url(file_path)
            uploaded_to_supabase = True
            logger.info(f"File uploaded to Supabase: {file_path}")
        except Exception as e:
            logger.error(f"Supabase upload error: {e}")
            with open(os.path.join(UPLOAD_DIR, file_id), "wb") as f:
                f.write(contents)
    else:
        with open(os.path.join(UPLOAD_DIR, file_id), "wb") as f:
            f.write(contents)
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("""
                    INSERT INTO uploaded_files 
                    (id, session_id, filename, original_name, size, mime_type, storage_path, public_url, created) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    file_id, s["id"], file_id, file.filename or "unknown",
                    len(contents), file.content_type or "application/octet-stream",
                    file_path if uploaded_to_supabase else file_id,
                    public_url, datetime.utcnow()
                ))
                conn.commit()
    except Exception as e:
        logger.error(f"Save file record error: {e}")
    
    return {
        "id": file_id,
        "filename": file.filename,
        "size_mb": round(len(contents) / (1024 * 1024), 2),
        "storage": "supabase" if uploaded_to_supabase else "local",
        "url": public_url
    }

@app.get("/api/upload/{file_id}")
def get_uploaded_file(file_id: str, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401)
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT storage_path, public_url, mime_type FROM uploaded_files WHERE id=%s AND session_id=%s", (file_id, s["id"]))
                row = c.fetchone()
                if not row:
                    raise HTTPException(404, "File not found")
                
                storage_path, public_url, mime_type = row
                
                if public_url:
                    return {"url": public_url}
                
                if storage_path and supabase_client:
                    try:
                        data = supabase_client.storage.from_(settings.SUPABASE_BUCKET).download(storage_path)
                        return Response(content=data, media_type=mime_type or "application/octet-stream")
                    except:
                        pass
                
                local_path = os.path.join(UPLOAD_DIR, file_id)
                if os.path.exists(local_path):
                    return FileResponse(local_path)
                
                raise HTTPException(404, "File not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File retrieval error: {e}")
        raise HTTPException(500, "Could not retrieve file")

# ================================================================
# SECTION 27: WORKSPACE ENDPOINTS
# ================================================================
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
        raise HTTPException(403, "Work Area requires Plus or Pro")
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                wid = sid()
                c.execute("INSERT INTO workspaces (id,room_code,creator_session,creator_tier,max_members,created) VALUES (%s,%s,%s,%s,%s,%s)",
                         (wid, req.room_code.upper(), s["id"], s["tier"], min(req.max_members, max_m), datetime.utcnow()))
                c.execute("INSERT INTO workspace_members (workspace_id,session_id,role,joined) VALUES (%s,%s,%s,%s)",
                         (wid, s["id"], "admin", datetime.utcnow()))
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
                    raise HTTPException(400, "Room full")
                c.execute("INSERT INTO workspace_members (workspace_id,session_id,role,joined) VALUES (%s,%s,%s,%s)",
                         (ws[0], s["id"], "member", datetime.utcnow()))
                c.execute("SELECT session_id, role FROM workspace_members WHERE workspace_id=%s", (ws[0],))
                members = [{"session_id": r[0], "role": r[1]} for r in c.fetchall()]
                c.execute("SELECT id,session_id,author,message,is_ai,created FROM workspace_messages WHERE workspace_id=%s ORDER BY created ASC LIMIT 50", (ws[0],))
                messages = [{"id": r[0], "session_id": r[1], "author": r[2], "message": r[3], "is_ai": bool(r[4]), "created": r[5].isoformat() if r[5] else None} for r in c.fetchall()]
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
                    raise HTTPException(404)
                
                is_ai = req.message.strip().startswith("@CAPITAN")
                if is_ai:
                    c.execute("SELECT author,message FROM workspace_messages WHERE workspace_id=%s ORDER BY created ASC LIMIT 20", (ws[0],))
                    context = "\n".join([f"{r[0]}: {r[1]}" for r in c.fetchall()])
                    c.execute("SELECT content FROM workspace_notes WHERE workspace_id=%s", (ws[0],))
                    notes = "\n".join([r[0] for r in c.fetchall()])
                    result, _ = call_ai_fast([{"role": "system", "content": f"Work Area:\n{context}\n\nNotes:\n{notes}"},
                                             {"role": "user", "content": req.message.replace('@CAPITAN', '').strip()}], s["tier"])
                    if result:
                        c.execute("INSERT INTO workspace_messages (id,workspace_id,session_id,author,message,is_ai,created) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                                 (sid(), ws[0], s["id"], "CAPITAN AI", result, 1, datetime.utcnow()))
                
                c.execute("INSERT INTO workspace_messages (id,workspace_id,session_id,author,message,created) VALUES (%s,%s,%s,%s,%s,%s)",
                         (sid(), ws[0], s["id"], "User", req.message, datetime.utcnow()))
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
                    raise HTTPException(404)
                c.execute("SELECT session_id, role FROM workspace_members WHERE workspace_id=%s", (ws[0],))
                members = [{"session_id": r[0], "role": r[1]} for r in c.fetchall()]
                c.execute("SELECT id,session_id,author,message,is_ai,created FROM workspace_messages WHERE workspace_id=%s ORDER BY created ASC LIMIT 50", (ws[0],))
                messages = [{"id": r[0], "session_id": r[1], "author": r[2], "message": r[3], "is_ai": bool(r[4]), "created": r[5].isoformat() if r[5] else None} for r in c.fetchall()]
                return {"messages": messages, "members": members}
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
                if not c.fetchone():
                    raise HTTPException(404)
                c.execute("DELETE FROM workspace_notes WHERE workspace_id=(SELECT id FROM workspaces WHERE room_code=%s)", (req.room_code.upper(),))
                c.execute("INSERT INTO workspace_notes (id,workspace_id,session_id,author,content,created,updated) VALUES (%s,(SELECT id FROM workspaces WHERE room_code=%s),%s,%s,%s,%s,%s)",
                         (sid(), req.room_code.upper(), s["id"], "User", req.content, datetime.utcnow(), datetime.utcnow()))
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
                if not c.fetchone():
                    raise HTTPException(404)
                c.execute("SELECT author,content,updated FROM workspace_notes WHERE workspace_id=(SELECT id FROM workspaces WHERE room_code=%s)", (room_code.upper(),))
                notes = [{"author": r[0], "content": r[1], "updated": r[2].isoformat() if r[2] else None} for r in c.fetchall()]
                return {"notes": notes}
    except:
        return {"notes": []}

# ================================================================
# SECTION 28: ADMIN ENDPOINT (Founder only)
# ================================================================
@app.post("/api/admin")
def admin(request: Request):
    s = get_session(request)
    if not s or s["tier"] != "founder":
        raise HTTPException(403, "Access denied")
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT COUNT(*) FROM sessions")
                total = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM sessions WHERE tier != 'free'")
                paid = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM chat_messages")
                msgs = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM workspaces")
                ws = c.fetchone()[0]
                
                c.execute("SELECT id,tier,msg_count,created FROM sessions ORDER BY created DESC LIMIT 30")
                sessions = [{"id": r[0], "tier": r[1], "msg_count": r[2], "created": r[3].isoformat() if r[3] else None} for r in c.fetchall()]
                
                c.execute("SELECT * FROM payment_log ORDER BY created DESC LIMIT 20")
                payments = [{"session_id": r[1], "tier": r[2], "amount": r[3], "currency": r[4], "txid": r[5], "created": r[6].isoformat() if r[6] else None} for r in c.fetchall()]
                
                return {
                    "total_sessions": total,
                    "paid_sessions": paid,
                    "total_messages": msgs,
                    "workspaces": ws,
                    "sessions": sessions,
                    "payments": payments
                }
    except Exception as e:
        raise HTTPException(500, str(e))

# ================================================================
# SECTION 29: PWA & STATIC FILES
# ================================================================
STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)

@app.get("/manifest.json")
async def get_manifest():
    manifest = {
        "name": "CAPITAN AI",
        "short_name": "CAPITAN",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#000000",
        "theme_color": "#000000",
        "orientation": "portrait",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}
        ]
    }
    return JSONResponse(content=manifest)

@app.get("/icon-192.png")
async def icon_192():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
        <rect width="100" height="100" fill="#000" rx="20"/>
        <path d="M50 15 L75 27 L75 52 C75 65 63 76 50 82 C37 76 25 65 25 52 L25 27 Z" fill="none" stroke="#A0A0A4" stroke-width="4"/>
        <text x="50" y="72" text-anchor="middle" font-size="42" fill="#A0A0A4" font-family="Inter,sans-serif" font-weight="700">C</text>
    </svg>'''
    return Response(content=svg, media_type="image/svg+xml")

@app.get("/icon-512.png")
async def icon_512():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
        <rect width="100" height="100" fill="#000" rx="20"/>
        <path d="M50 15 L75 27 L75 52 C75 65 63 76 50 82 C37 76 25 65 25 52 L25 27 Z" fill="none" stroke="#A0A0A4" stroke-width="4"/>
        <text x="50" y="72" text-anchor="middle" font-size="42" fill="#A0A0A4" font-family="Inter,sans-serif" font-weight="700">C</text>
    </svg>'''
    return Response(content=svg, media_type="image/svg+xml")

@app.get("/")
async def root():
    return {
        "name": "CAPITAN AI",
        "version": "25.0",
        "status": "operational",
        "pwa_supported": True,
        "endpoints": ["/health", "/api/session", "/api/chat", "/api/chats", "/api/markets", "/api/search", "/manifest.json"]
    }

# ================================================================
# SECTION 30: MAIN ENTRY POINT
# ================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"\n{'='*60}")
    print(f"🚀 CAPITAN AI v25.0 - COMPLETE PRODUCTION BACKEND")
    print(f"{'='*60}")
    print(f"📊 Database: {'Supabase PostgreSQL' if settings.DATABASE_URL or settings.SUPABASE_DB_PASSWORD else 'Not configured'}")
    print(f"☁️  Supabase Storage: {'✅ Enabled' if supabase_client else '❌ Disabled'}")
    print(f"🤖 AI Providers: Groq={bool(settings.GROQ_KEY)} | OpenRouter={bool(settings.OPENROUTER_KEY)}")
    print(f"📈 Markets: CoinGecko={bool(settings.COINGECKO_KEY)} | Yahoo=Active")
    print(f"🔍 Web Search: SerpAPI={bool(settings.SERPAPI_KEY)}")
    print(f"📰 News: NewsAPI={bool(settings.NEWS_API_KEY)}")
    print(f"👑 Founder Key: {settings.FOUNDER_KEY[:10]}...")
    print(f"📨 Limits: Free=17/day | Plus=40/day | Pro=Unlimited")
    print(f"🌐 PWA: Enabled (manifest.json, icons)")
    print(f"{'='*60}\n")
    uvicorn.run(app, host="0.0.0.0", port=port)