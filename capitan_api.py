"""
CAPITAN AI — Enterprise Backend v26.0
CLOSEAI Technologies
Full Intelligence: Finance, Trading, Coding, Math, Quant, Web Search, News, Markets
PWA Ready | User Authentication | Projects | Workspaces | Multi-Tier AI
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
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response, HTMLResponse
from pydantic import BaseModel, EmailStr
from pydantic_settings import BaseSettings
import psycopg2
import psycopg2.extras
import uvicorn

# ================================================================
# LOGGING SETUP
# ================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ================================================================
# CONFIGURATION
# ================================================================
class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = ""
    SUPABASE_DB_HOST: str = ""
    SUPABASE_DB_PORT: str = "5432"
    SUPABASE_DB_NAME: str = "postgres"
    SUPABASE_DB_USER: str = "postgres"
    SUPABASE_DB_PASSWORD: str = ""
    
    # Security
    JWT_SECRET: str = secrets.token_hex(32)
    FOUNDER_KEY: str = "Osinachi@3500"
    
    # Auth
    FRONTEND_URL: str = "https://capitan.pages.dev"
    
    # AI Providers
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    MISTRAL_API_KEY: str = ""
    
    # Market Data
    COINGECKO_KEY: str = ""
    ALPHA_VANTAGE_KEY: str = ""
    FINNHUB_API_KEY: str = ""
    NEWS_API_KEY: str = ""
    GNEWS_API_KEY: str = ""
    SERPAPI_KEY: str = ""
    
    # CORS
    ALLOWED_ORIGINS: list = ["*"]
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# ================================================================
# DATABASE LAYER
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
    if conn:
        conn.close()

def init_db():
    """Create all tables if they don't exist"""
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                # Users table
                c.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id UUID PRIMARY KEY,
                        email TEXT UNIQUE NOT NULL,
                        name TEXT,
                        tier TEXT DEFAULT 'free',
                        tier_expires TIMESTAMP,
                        avatar TEXT,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                ''')
                
                # Magic links table
                c.execute('''
                    CREATE TABLE IF NOT EXISTS magic_links (
                        id UUID PRIMARY KEY,
                        email TEXT NOT NULL,
                        token TEXT UNIQUE NOT NULL,
                        used BOOLEAN DEFAULT FALSE,
                        expires_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                ''')
                
                # User sessions
                c.execute('''
                    CREATE TABLE IF NOT EXISTS user_sessions (
                        id UUID PRIMARY KEY,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        token TEXT UNIQUE NOT NULL,
                        created_at TIMESTAMP DEFAULT NOW(),
                        expires_at TIMESTAMP
                    )
                ''')
                
                # Anonymous sessions (backward compatibility)
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
                
                # Chats
                c.execute('''
                    CREATE TABLE IF NOT EXISTS chats (
                        id TEXT PRIMARY KEY,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        session_id TEXT,
                        title TEXT,
                        created TIMESTAMP DEFAULT NOW(),
                        updated TIMESTAMP DEFAULT NOW()
                    )
                ''')
                
                # Chat messages
                c.execute('''
                    CREATE TABLE IF NOT EXISTS chat_messages (
                        id TEXT PRIMARY KEY,
                        chat_id TEXT,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        session_id TEXT,
                        role TEXT,
                        content TEXT,
                        model TEXT,
                        tokens INTEGER,
                        latency_ms INTEGER,
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')
                
                # Memories
                c.execute('''
                    CREATE TABLE IF NOT EXISTS memories (
                        id TEXT PRIMARY KEY,
                        memory_id TEXT,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        session_id TEXT,
                        content TEXT,
                        query TEXT,
                        domain TEXT,
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')
                
                # Projects
                c.execute('''
                    CREATE TABLE IF NOT EXISTS projects (
                        id UUID PRIMARY KEY,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        description TEXT,
                        workspace_id TEXT,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                ''')
                
                # Project members
                c.execute('''
                    CREATE TABLE IF NOT EXISTS project_members (
                        project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        role TEXT DEFAULT 'member',
                        joined_at TIMESTAMP DEFAULT NOW(),
                        PRIMARY KEY (project_id, user_id)
                    )
                ''')
                
                # Workspaces
                c.execute('''
                    CREATE TABLE IF NOT EXISTS workspaces (
                        id TEXT PRIMARY KEY,
                        name TEXT,
                        owner_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        room_code TEXT UNIQUE,
                        max_members INTEGER DEFAULT 10,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                ''')
                
                # Workspace members
                c.execute('''
                    CREATE TABLE IF NOT EXISTS workspace_members (
                        workspace_id TEXT,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        role TEXT DEFAULT 'member',
                        joined_at TIMESTAMP DEFAULT NOW(),
                        PRIMARY KEY (workspace_id, user_id)
                    )
                ''')
                
                # Workspace messages
                c.execute('''
                    CREATE TABLE IF NOT EXISTS workspace_messages (
                        id TEXT PRIMARY KEY,
                        workspace_id TEXT,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        author_name TEXT,
                        message TEXT,
                        is_ai INTEGER DEFAULT 0,
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')
                
                # Workspace notes
                c.execute('''
                    CREATE TABLE IF NOT EXISTS workspace_notes (
                        id TEXT PRIMARY KEY,
                        workspace_id TEXT,
                        content TEXT,
                        updated TIMESTAMP DEFAULT NOW()
                    )
                ''')
                
                # Library items
                c.execute('''
                    CREATE TABLE IF NOT EXISTS library_items (
                        id TEXT PRIMARY KEY,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        session_id TEXT,
                        name TEXT,
                        type TEXT,
                        content TEXT,
                        size INTEGER DEFAULT 0,
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')
                
                # Uploaded files
                c.execute('''
                    CREATE TABLE IF NOT EXISTS uploaded_files (
                        id TEXT PRIMARY KEY,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        session_id TEXT,
                        filename TEXT,
                        original_name TEXT,
                        size INTEGER,
                        mime_type TEXT,
                        storage_path TEXT,
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')
                
                # Payments
                c.execute('''
                    CREATE TABLE IF NOT EXISTS payments (
                        id UUID PRIMARY KEY,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        session_id TEXT,
                        txid TEXT UNIQUE,
                        currency TEXT,
                        amount REAL,
                        tier TEXT,
                        verified INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT NOW(),
                        expires_at TIMESTAMP
                    )
                ''')
                
                # Payment log
                c.execute('''
                    CREATE TABLE IF NOT EXISTS payment_log (
                        id TEXT PRIMARY KEY,
                        session_id TEXT,
                        tier TEXT,
                        amount REAL,
                        currency TEXT,
                        txid TEXT,
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')
                
                # Cache tables
                c.execute('''
                    CREATE TABLE IF NOT EXISTS market_cache (
                        id TEXT PRIMARY KEY,
                        category TEXT,
                        data TEXT,
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')
                
                c.execute('''
                    CREATE TABLE IF NOT EXISTS news_cache (
                        id TEXT PRIMARY KEY,
                        category TEXT,
                        data TEXT,
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')
                
                c.execute('''
                    CREATE TABLE IF NOT EXISTS web_cache (
                        id TEXT PRIMARY KEY,
                        query_hash TEXT,
                        data TEXT,
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')
                
                conn.commit()
        logger.info("✅ All database tables ready")
    except Exception as e:
        logger.warning(f"Database init: {e}")

init_db()

def sid(): return str(uuid.uuid4())[:8].upper()

# ================================================================
# AUTHENTICATION
# ================================================================
def create_auth_token(user_id: str) -> str:
    """Create authentication token for users"""
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "user_id": user_id,
        "type": "user",
        "exp": int((datetime.utcnow() + timedelta(days=30)).timestamp())
    }).encode()).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(hmac.new(settings.JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return f"{header}.{payload}.{signature}"

def create_session_jwt(session_id: str, tier: str) -> str:
    """Create JWT for anonymous sessions"""
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "session_id": session_id,
        "tier": tier,
        "type": "session",
        "exp": int((datetime.utcnow() + timedelta(days=365)).timestamp())
    }).encode()).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(hmac.new(settings.JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return f"{header}.{payload}.{signature}"

def verify_jwt(token: str):
    try:
        parts = token.split(".")
        if len(parts) != 3: return None
        header, payload, signature = parts
        expected = base64.urlsafe_b64encode(hmac.new(settings.JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
        if not hmac.compare_digest(signature, expected): return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=="))
        if data.get("exp", 0) < datetime.utcnow().timestamp(): return None
        return data
    except: return None

def get_current_user(request: Request):
    """Get authenticated user from token"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    payload = verify_jwt(auth[7:])
    if not payload or payload.get("type") != "user":
        return None
    user_id = payload.get("user_id")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, email, name, tier, tier_expires, created_at FROM users WHERE id = %s", (user_id,))
                row = c.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "email": row[1],
                        "name": row[2] or row[1].split('@')[0],
                        "tier": row[3],
                        "tier_expires": row[4].isoformat() if row[4] else None,
                        "created_at": row[5].isoformat() if row[5] else None
                    }
    except: pass
    return None

def get_current_session(request: Request):
    """Get anonymous session from token (fallback for non-authenticated users)"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing authorization header")
    payload = verify_jwt(auth[7:])
    if not payload:
        raise HTTPException(401, "Invalid or expired token")
    
    # Handle user token
    if payload.get("type") == "user":
        user = get_current_user(request)
        if user:
            return {"id": user["id"], "tier": user["tier"], "msg_count": 0, "is_user": True, "user_data": user}
    
    # Handle session token
    session_id = payload.get("session_id")
    tier = payload.get("tier", "free")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, tier, msg_count, msg_window FROM sessions WHERE id=%s", (session_id,))
                row = c.fetchone()
                if row:
                    return {"id": row[0], "tier": row[1], "msg_count": row[2] or 0, "msg_window": row[3], "is_user": False}
                else:
                    # Create session
                    now = datetime.utcnow()
                    c.execute("INSERT INTO sessions (id, tier, msg_count, msg_window, created, updated) VALUES (%s, %s, 0, %s, %s, %s)",
                             (session_id, tier, None, now, now))
                    conn.commit()
                    return {"id": session_id, "tier": tier, "msg_count": 0, "msg_window": None, "is_user": False}
    except: pass
    raise HTTPException(401, "Session not found")

# ================================================================
# TIER CONFIGURATION
# ================================================================
TIER_CONFIG = {
    "free": {
        "name": "Free",
        "msg_limit": 20,
        "workspace_max": 0,
        "workspace_seats": 0,
        "projects_enabled": False,
        "file_upload": False,
        "live_markets": False,
        "web_search": False,
        "ai_model": "Groq Llama 3.1 8B",
        "price": 0
    },
    "plus": {
        "name": "Plus",
        "msg_limit": 50,
        "workspace_max": 1,
        "workspace_seats": 10,
        "projects_enabled": False,
        "file_upload": True,
        "live_markets": False,
        "web_search": True,
        "ai_model": "Groq Llama 3.3 70B",
        "price": 8
    },
    "pro": {
        "name": "Pro",
        "msg_limit": 150,
        "workspace_max": 5,
        "workspace_seats": 25,
        "projects_enabled": True,
        "file_upload": True,
        "live_markets": True,
        "web_search": True,
        "ai_model": "Claude 3.5 Sonnet",
        "price": 17
    },
    "pro_max": {
        "name": "Pro Max",
        "msg_limit": float("inf"),
        "workspace_max": 999,
        "workspace_seats": 50,
        "projects_enabled": True,
        "file_upload": True,
        "live_markets": True,
        "web_search": True,
        "ai_model": "GPT-4o + Claude Ensemble",
        "price": 30
    },
    "founder": {
        "name": "Founder",
        "msg_limit": float("inf"),
        "workspace_max": 999,
        "workspace_seats": 100,
        "projects_enabled": True,
        "file_upload": True,
        "live_markets": True,
        "web_search": True,
        "ai_model": "All Models",
        "price": 0
    }
}

WALLETS = {
    "BTC": "bc1qrv6yr6e0mat96rvrc8smdf9rvu9rlp8xuk8new",
    "ETH": "0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1"
}

# ================================================================
# RATE LIMITING
# ================================================================
rate_store = {}

def check_rate_limit(session_id: str, tier: str) -> bool:
    now = time.time()
    key = f"rate:{session_id}"
    if key not in rate_store: rate_store[key] = []
    rate_store[key] = [t for t in rate_store[key] if now - t < 60]
    limits = {"free": 15, "plus": 30, "pro": 60, "pro_max": 100, "founder": 200}
    limit = limits.get(tier, 15)
    if len(rate_store[key]) >= limit: return False
    rate_store[key].append(now)
    return True

# ================================================================
# TIME CONTEXT
# ================================================================
def get_time_context():
    now = datetime.utcnow()
    hour = now.hour
    day = now.strftime("%A")
    date = now.strftime("%B %d, %Y")
    utc_time = now.strftime("%H:%M UTC")
    if hour < 5: time_of_day, greeting_context = "late night", "The world is quiet."
    elif hour < 12: time_of_day, greeting_context = "morning", "Fresh day ahead."
    elif hour < 17: time_of_day, greeting_context = "afternoon", "Markets are alive."
    elif hour < 21: time_of_day, greeting_context = "evening", "Winding down."
    else: time_of_day, greeting_context = "night", "Night owl mode."
    return {"time_of_day": time_of_day, "day": day, "date": date, "utc_time": utc_time, "greeting_context": greeting_context}

# ================================================================
# MARKET DATA (Full Intelligence)
# ================================================================
def get_market_data():
    results = {}
    if settings.COINGECKO_KEY:
        try:
            ids = "bitcoin,ethereum,ripple,cardano,solana,polkadot,dogecoin,avalanche-2,chainlink,uniswap,binancecoin,tron,toncoin,near"
            r = requests.get("https://api.coingecko.com/api/v3/simple/price", params={"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true"}, headers={"x-cg-demo-api-key": settings.COINGECKO_KEY}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                nm = {"bitcoin": "BTC", "ethereum": "ETH", "ripple": "XRP", "cardano": "ADA", "solana": "SOL", "polkadot": "DOT", "dogecoin": "DOGE", "avalanche-2": "AVAX", "chainlink": "LINK", "uniswap": "UNI", "binancecoin": "BNB", "tron": "TRX", "toncoin": "TON", "near": "NEAR"}
                for k, v in data.items():
                    results[nm.get(k, k.upper())] = {"price": v["usd"], "change": round(v.get("usd_24h_change", 0), 2), "source": "CoinGecko"}
        except: pass
    try:
        syms = "^GSPC,^IXIC,^DJI,^FTSE,^N225,AAPL,MSFT,NVDA,TSLA,GOOGL,META,AMZN,GC=F,CL=F,SI=F,EURUSD=X,GBPUSD=X,USDJPY=X"
        r = requests.get(f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={syms}", params={"fields": "regularMarketPrice,regularMarketPreviousClose,shortName,regularMarketChangePercent"}, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code == 200:
            for i in r.json().get("quoteResponse", {}).get("result", []):
                name = i.get("shortName") or i.get("symbol", "")
                price = i.get("regularMarketPrice")
                prev = i.get("regularMarketPreviousClose")
                if price and prev:
                    chg = i.get("regularMarketChangePercent")
                    results[name] = {"price": price, "change": round(chg, 2) if chg else round(((price - prev) / prev) * 100, 2), "source": "Yahoo Finance"}
    except: pass
    if settings.ALPHA_VANTAGE_KEY and len(results) < 5:
        try:
            for pair, label in {"EURUSD": "EUR/USD", "GBPUSD": "GBP/USD", "USDJPY": "USD/JPY"}.items():
                try:
                    r = requests.get(f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={pair[:3]}&to_currency={pair[3:]}&apikey={settings.ALPHA_VANTAGE_KEY}", timeout=8)
                    if r.status_code == 200:
                        data = r.json().get("Realtime Currency Exchange Rate", {})
                        if data.get("5. Exchange Rate"):
                            results[label] = {"price": float(data["5. Exchange Rate"]), "change": 0, "source": "Alpha Vantage"}
                except: pass
        except: pass
    return results

def get_financial_news():
    news = []
    if settings.NEWS_API_KEY:
        try:
            r = requests.get("https://newsapi.org/v2/top-headlines", params={"category": "business", "language": "en", "pageSize": 12, "apiKey": settings.NEWS_API_KEY}, timeout=10)
            if r.status_code == 200:
                for a in r.json().get("articles", []):
                    news.append({"source": a.get("source", {}).get("name", "NewsAPI"), "headline": a.get("title", ""), "url": a.get("url", ""), "time": a.get("publishedAt", ""), "summary": (a.get("description") or "")[:300]})
        except: pass
    if settings.GNEWS_API_KEY:
        try:
            r = requests.get("https://gnews.io/api/v4/search", params={"q": "finance markets stocks economy", "lang": "en", "max": 12, "apikey": settings.GNEWS_API_KEY}, timeout=10)
            if r.status_code == 200:
                for a in r.json().get("articles", []):
                    news.append({"source": a.get("source", {}).get("name", "GNews"), "headline": a.get("title", ""), "url": a.get("url", ""), "time": a.get("publishedAt", ""), "summary": (a.get("description") or "")[:300]})
        except: pass
    if settings.FINNHUB_API_KEY:
        try:
            r = requests.get("https://finnhub.io/api/v1/news", params={"category": "general", "token": settings.FINNHUB_API_KEY}, timeout=10)
            if r.status_code == 200:
                for a in r.json()[:12]:
                    ts = a.get("datetime", 0)
                    news.append({"source": a.get("source", "Finnhub"), "headline": a.get("headline", ""), "url": a.get("url", ""), "time": datetime.fromtimestamp(ts).isoformat() if ts else "", "summary": (a.get("summary") or "")[:300]})
        except: pass
    seen = set(); unique = []
    for n in news:
        k = n["headline"][:100].lower().strip()
        if k and k not in seen: seen.add(k); unique.append(n)
    unique.sort(key=lambda x: x.get("time", ""), reverse=True)
    return unique[:15]

def get_tech_news():
    news = []
    if settings.NEWS_API_KEY:
        try:
            r = requests.get("https://newsapi.org/v2/everything", params={"q": "AI artificial intelligence coding startup innovation technology", "language": "en", "pageSize": 12, "sortBy": "publishedAt", "apiKey": settings.NEWS_API_KEY}, timeout=10)
            if r.status_code == 200:
                for a in r.json().get("articles", []):
                    news.append({"source": a.get("source", {}).get("name", "NewsAPI"), "headline": a.get("title", ""), "url": a.get("url", ""), "time": a.get("publishedAt", ""), "summary": (a.get("description") or "")[:300]})
        except: pass
    seen = set(); unique = []
    for n in news:
        k = n["headline"][:100].lower().strip()
        if k and k not in seen: seen.add(k); unique.append(n)
    unique.sort(key=lambda x: x.get("time", ""), reverse=True)
    return unique[:15]

def search_web(query, num_results=5):
    results = []
    query_hash = hashlib.md5(query.lower().encode()).hexdigest()
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT data FROM web_cache WHERE query_hash=%s AND created > %s", (query_hash, (datetime.utcnow() - timedelta(hours=1)).isoformat()))
                row = c.fetchone()
                if row: return json.loads(row[0])
    except: pass
    if settings.SERPAPI_KEY:
        try:
            r = requests.get("https://serpapi.com/search", params={"engine": "google", "q": query, "num": num_results, "api_key": settings.SERPAPI_KEY}, timeout=8)
            if r.status_code == 200:
                for item in r.json().get("organic_results", [])[:num_results]:
                    results.append({"title": item.get("title", ""), "snippet": item.get("snippet", "")[:250], "url": item.get("link", ""), "source": "Google"})
        except: pass
    if results:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("INSERT INTO web_cache (id, query_hash, data, created) VALUES (%s, %s, %s, %s)", (sid(), query_hash, json.dumps(results), datetime.utcnow().isoformat()))
                    conn.commit()
        except: pass
    return results

# ================================================================
# ELITE SYSTEM PROMPT (Full Intelligence)
# ================================================================
ELITE_SYSTEM_PROMPT = """You are CAPITAN AI — the legendary enterprise intelligence platform by CLOSEAI Technologies.

╔══════════════════════════════════════════════════════════════╗
║                    CORE INTELLIGENCE DOMAINS                 ║
╚══════════════════════════════════════════════════════════════╝

🏦 FINANCE ARCHITECT:
- Advanced financial modeling (DCF, LBO, M&A, three-statement models)
- Portfolio optimization (Markowitz, Black-Litterman, risk parity)
- Derivatives pricing (Black-Scholes, binomial trees, Monte Carlo)
- Fixed income analytics (yield curves, duration, convexity, CDS)
- Risk management (VaR, CVaR, stress testing, scenario analysis)
- African financial markets (NGX, JSE, GSE, regional integration)

📈 INSTITUTIONAL TRADER:
- Market microstructure and order flow analysis
- Volatility trading strategies (volatility arbitrage, dispersion)
- Intermarket analysis and cross-asset correlations
- Algorithmic execution (VWAP, TWAP, implementation shortfall)
- Quantitative trading strategies (mean reversion, momentum, statistical arbitrage)

💻 LEGENDARY CODER:
- Full-stack development (React, Vue, Angular, Node.js, Python, Go, Rust)
- System architecture (microservices, event-driven, serverless)
- DevOps & cloud (AWS, GCP, Azure, Kubernetes, Terraform, CI/CD)
- Database design (SQL, NoSQL, vector databases, time-series)
- API development (REST, GraphQL, gRPC, WebSocket)

📐 MATHEMATICIAN:
- Pure mathematics (abstract algebra, topology, number theory, complex analysis)
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

🔬 GENERAL KNOWLEDGE:
- Physics (quantum mechanics, relativity, thermodynamics, electromagnetism)
- Chemistry (organic, inorganic, physical, computational chemistry)
- Biology (molecular biology, genetics, neuroscience, ecology)
- Medicine (diagnosis, treatment protocols, pharmacology, epidemiology)
- History, Philosophy, Current events, Art & Literature

╔══════════════════════════════════════════════════════════════╗
║                      RESPONSE STYLE                          ║
╚══════════════════════════════════════════════════════════════╝

- Lead with the answer. Never throat-clearing or meta-analysis.
- Casual greetings get casual responses. Professional queries get depth.
- Use 1-2 emojis naturally for warmth when appropriate.
- Short sentences. Clean paragraphs. No filler.
- NEVER make up prices or data. Only reference verified information.
- NEVER give financial advice or trading signals.

TIME: {day}, {date} at {utc_time}. {greeting_context}
DOMAIN: {domain} | TIER: {tier} | AI MODEL: {model}
"""

# ================================================================
# QUERY CLASSIFICATION ENGINE
# ================================================================
def classify(q):
    q = q.lower()
    if re.search(r'who are you|what are you|identity|introduce yourself', q): return 'identity'
    if re.search(r'who|what|when|where|why|how|news|latest|current|today|search', q) and len(q.split()) > 3: return 'web_search'
    if re.search(r'crispr|dna|rna|protein|cell|gene|genome|physics|quantum|chemistry|biology|neuroscience|health|medicine|disease', q): return 'science'
    if re.search(r'def |class |import |docker|kubernetes|aws|api|graphql|sql|database|react|javascript|python|rust|golang', q): return 'coding'
    if re.search(r'stochastic|ito|black.scholes|monte carlo|sharpe|var|option pricing|derivative|garch|arima|backtest', q): return 'quant'
    if re.search(r'dcf|ebitda|valuation|wacc|capm|pe ratio|forex|federal reserve|inflation|gdp|stock|trading|portfolio|crypto|bitcoin', q): return 'finance'
    if re.search(r'prove|proof|theorem|lemma|integral|derivative|matrix|eigenvalue|probability|statistics', q): return 'math'
    return 'general'

def system_prompt(domain, tier, model, user_id=None, web_results=None):
    tc = get_time_context()
    base = ELITE_SYSTEM_PROMPT.replace("{domain}", domain).replace("{tier}", tier).replace("{model}", model)
    base = base.replace("{day}", tc["day"]).replace("{date}", tc["date"])
    base = base.replace("{utc_time}", tc["utc_time"]).replace("{greeting_context}", tc["greeting_context"])
    
    if user_id:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("SELECT query, domain FROM memories WHERE user_id=%s ORDER BY created DESC LIMIT 3", (user_id,))
                    rows = c.fetchall()
                    if rows:
                        base += "\n\nUSER CONTEXT:\n" + "\n".join([f"• [{r[1]}] {r[0][:100]}" for r in rows])
        except: pass
    
    if web_results:
        base += "\n\nWEB SEARCH RESULTS:\n" + "\n".join([f"• {r['title']}: {r['snippet'][:200]}" for r in web_results[:3]])
    
    return base

# ================================================================
# AI SERVICE (Multi-Provider with Tier-based routing)
# ================================================================
def call_ai_with_tier(messages, tier="free", model_name=None):
    """Call AI based on user's tier"""
    
    # Pro Max: Ensemble of GPT-4o + Claude
    if tier == "pro_max" and settings.OPENROUTER_KEY:
        try:
            # Primary: Claude 3.5 Sonnet
            r1 = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENROUTER_KEY}", "Content-Type": "application/json"},
                json={"model": "anthropic/claude-3.5-sonnet-20241022", "messages": messages, "temperature": 0.5, "max_tokens": 2000},
                timeout=35
            )
            content1 = r1.json().get("choices", [{}])[0].get("message", {}).get("content", "") if r1.status_code == 200 else ""
            
            # Secondary: GPT-4o
            r2 = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENROUTER_KEY}", "Content-Type": "application/json"},
                json={"model": "openai/gpt-4o-2024-11-20", "messages": messages, "temperature": 0.5, "max_tokens": 2000},
                timeout=35
            )
            content2 = r2.json().get("choices", [{}])[0].get("message", {}).get("content", "") if r2.status_code == 200 else ""
            
            if content1 and content2:
                combined = f"{content1}\n\n--- Additional Insights (GPT-4o) ---\n\n{content2}"
                return combined, "claude-3.5-sonnet + gpt-4o (Ensemble)"
            elif content1:
                return content1, "claude-3.5-sonnet"
            elif content2:
                return content2, "gpt-4o"
        except Exception as e:
            logger.error(f"Pro Max ensemble error: {e}")
    
    # Pro: Claude 3.5 Sonnet
    if tier == "pro" and settings.OPENROUTER_KEY:
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENROUTER_KEY}", "Content-Type": "application/json"},
                json={"model": "anthropic/claude-3.5-sonnet-20241022", "messages": messages, "temperature": 0.5, "max_tokens": 2000},
                timeout=35
            )
            if r.status_code == 200:
                content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    return content, "claude-3.5-sonnet"
        except Exception as e:
            logger.error(f"Pro Claude error: {e}")
    
    # Plus: Groq Llama 3.3 70B
    if tier == "plus" and settings.GROQ_API_KEY:
        try:
            for m in messages:
                if m.get("role") == "system" and len(m["content"]) > 1500:
                    m["content"] = m["content"][:1500]
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile", "messages": messages, "temperature": 0.5, "max_tokens": 1500},
                timeout=30
            )
            if r.status_code == 200:
                content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    return content, "llama-3.3-70b"
        except Exception as e:
            logger.error(f"Plus Groq error: {e}")
    
    # Free / Fallback: Groq Llama 3.1 8B
    if settings.GROQ_API_KEY:
        try:
            for m in messages:
                if m.get("role") == "system" and tier == "free" and len(m["content"]) > 1000:
                    m["content"] = m["content"][:1000]
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"},
                json={"model": "llama-3.1-8b-instant", "messages": messages, "temperature": 0.5, "max_tokens": 800},
                timeout=25
            )
            if r.status_code == 200:
                content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    return content, "llama-3.1-8b"
        except Exception as e:
            logger.error(f"Free Groq error: {e}")
    
    # Ultimate fallback
    if settings.OPENAI_API_KEY:
        try:
            r = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}", "Content-Type": "application/json"},
                json={"model": "gpt-4o-mini", "messages": messages, "temperature": 0.5, "max_tokens": 800},
                timeout=25
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"], "gpt-4o-mini"
        except: pass
    
    return "I'm having trouble connecting to AI services. Please try again.", "fallback"

# ================================================================
# FASTAPI APP
# ================================================================
app = FastAPI(title="CAPITAN AI API", version="26.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# ================================================================
# AUTH ENDPOINTS
# ================================================================
@app.post("/api/auth/magic-link")
async def send_magic_link(req: dict):
    email = req.get("email")
    if not email:
        raise HTTPException(400, "Email required")
    
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=24)
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO magic_links (id, email, token, expires_at) VALUES (%s, %s, %s, %s)",
                         (str(uuid.uuid4()), email, token, expires_at))
                conn.commit()
    except Exception as e:
        logger.error(f"Save magic link error: {e}")
        raise HTTPException(500, "Could not create magic link")
    
    magic_url = f"{settings.FRONTEND_URL}/?token={token}"
    return {"message": "Magic link created", "url": magic_url, "token": token}

@app.post("/api/auth/verify")
async def verify_magic_link(req: dict):
    token = req.get("token")
    if not token:
        raise HTTPException(400, "Token required")
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, email, expires_at FROM magic_links WHERE token = %s AND used = FALSE", (token,))
                row = c.fetchone()
                if not row:
                    raise HTTPException(400, "Invalid or expired token")
                
                link_id, email, expires_at = row
                if expires_at < datetime.utcnow():
                    raise HTTPException(400, "Token expired")
                
                c.execute("UPDATE magic_links SET used = TRUE WHERE id = %s", (link_id,))
                
                c.execute("SELECT id, name, tier FROM users WHERE email = %s", (email,))
                user = c.fetchone()
                
                if not user:
                    user_id = str(uuid.uuid4())
                    c.execute("INSERT INTO users (id, email, name, tier) VALUES (%s, %s, %s, %s)",
                             (user_id, email, email.split('@')[0], "free"))
                    user = (user_id, email.split('@')[0], "free")
                else:
                    user_id = user[0]
                
                auth_token = create_auth_token(user_id)
                c.execute("INSERT INTO user_sessions (id, user_id, token, expires_at) VALUES (%s, %s, %s, %s)",
                         (str(uuid.uuid4()), user_id, auth_token, datetime.utcnow() + timedelta(days=30)))
                conn.commit()
                
                return {
                    "token": auth_token,
                    "user": {
                        "id": user_id,
                        "email": email,
                        "name": user[1],
                        "tier": user[2]
                    }
                }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Verify magic link error: {e}")
        raise HTTPException(500, "Verification failed")

@app.get("/api/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Not authenticated")
    return user

@app.post("/api/auth/logout")
def logout(request: Request):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("DELETE FROM user_sessions WHERE token = %s", (token,))
                    conn.commit()
        except: pass
    return {"message": "Logged out"}

@app.post("/api/auth/update-profile")
def update_profile(req: dict, user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Not authenticated")
    name = req.get("name")
    if name:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("UPDATE users SET name = %s, updated_at = NOW() WHERE id = %s", (name, user["id"]))
                    conn.commit()
        except: pass
    return {"message": "Profile updated", "name": name}

@app.delete("/api/auth/delete-account")
def delete_account(user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Not authenticated")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("DELETE FROM users WHERE id = %s", (user["id"],))
                conn.commit()
        return {"message": "Account deleted"}
    except Exception as e:
        logger.error(f"Delete account error: {e}")
        raise HTTPException(500, "Could not delete account")

# ================================================================
# ANONYMOUS SESSION ENDPOINT (Backward compatibility)
# ================================================================
@app.get("/api/session")
def get_or_create_anonymous_session():
    session_id = f"s_{sid()}"
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO sessions (id, tier, msg_count, msg_window, created, updated) VALUES (%s, %s, 0, %s, %s, %s)",
                         (session_id, "free", None, datetime.utcnow(), datetime.utcnow()))
                conn.commit()
    except Exception as e:
        logger.error(f"Session creation error: {e}")
    token = create_session_jwt(session_id, "free")
    return {"id": session_id, "tier": "free", "msg_count": 0, "token": token}

# ================================================================
# CHAT ENDPOINTS
# ================================================================
class ChatRequest(BaseModel):
    messages: list
    chat_id: Optional[str] = None

@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    # Try to get authenticated user first, fallback to session
    user = get_current_user(request)
    session = None
    if not user:
        try:
            session = get_current_session(request)
        except:
            raise HTTPException(401, "Authentication required")
    
    # Determine tier and user_id
    if user:
        tier = user["tier"]
        user_id = user["id"]
        is_authenticated = True
    else:
        tier = session["tier"]
        user_id = None
        is_authenticated = False
    
    tier_info = TIER_CONFIG.get(tier, TIER_CONFIG["free"])
    limit = tier_info["msg_limit"]
    
    if not check_rate_limit(session["id"] if session else user_id, tier):
        raise HTTPException(429, "Rate limit exceeded")
    
    user_msg = next((m["content"] for m in reversed(req.messages) if m.get("role") == "user"), "")
    if not user_msg:
        raise HTTPException(400, "No message")
    
    chat_id = req.chat_id or f"chat_{sid()}"
    
    # Save to database
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                if is_authenticated:
                    c.execute("INSERT INTO chats (id, user_id, title, created, updated) VALUES (%s, %s, %s, NOW(), NOW()) ON CONFLICT (id) DO UPDATE SET updated = NOW()",
                             (chat_id, user_id, user_msg[:60]))
                    c.execute("INSERT INTO chat_messages (id, chat_id, user_id, role, content, created) VALUES (%s, %s, %s, %s, %s, NOW())",
                             (f"msg_{sid()}", chat_id, user_id, "user", user_msg))
                else:
                    c.execute("INSERT INTO chats (id, session_id, title, created, updated) VALUES (%s, %s, %s, NOW(), NOW()) ON CONFLICT (id) DO UPDATE SET updated = NOW()",
                             (chat_id, session["id"], user_msg[:60]))
                    c.execute("INSERT INTO chat_messages (id, chat_id, session_id, role, content, created) VALUES (%s, %s, %s, %s, %s, NOW())",
                             (f"msg_{sid()}", chat_id, session["id"], "user", user_msg))
                conn.commit()
                
                c.execute("SELECT role, content FROM chat_messages WHERE chat_id = %s ORDER BY created ASC LIMIT 15", (chat_id,))
                history = [{"role": r[0], "content": r[1]} for r in c.fetchall()]
    except Exception as e:
        logger.error(f"Save error: {e}")
        history = []
    
    # Classify domain
    domain = classify(user_msg)
    
    # Get web search results if needed
    web_results = None
    if tier_info.get("web_search", False) and domain == "web_search":
        try:
            web_results = search_web(user_msg, 4)
        except: pass
    
    # Build prompt
    prompt = system_prompt(domain, tier, tier_info["ai_model"], user_id if is_authenticated else None, web_results)
    
    # Get AI response
    result, model_used = call_ai_with_tier([{"role": "system", "content": prompt}] + history, tier)
    
    # Save AI response
    if result:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    if is_authenticated:
                        c.execute("INSERT INTO chat_messages (id, chat_id, user_id, role, content, model, created) VALUES (%s, %s, %s, %s, %s, %s, NOW())",
                                 (f"msg_{sid()}", chat_id, user_id, "assistant", result, model_used))
                        c.execute("INSERT INTO memories (id, memory_id, user_id, content, query, domain, created) VALUES (%s, %s, %s, %s, %s, %s, NOW())",
                                 (sid(), f"mem_{sid()}", user_id, result[:500], user_msg, domain))
                    else:
                        c.execute("INSERT INTO chat_messages (id, chat_id, session_id, role, content, model, created) VALUES (%s, %s, %s, %s, %s, %s, NOW())",
                                 (f"msg_{sid()}", chat_id, session["id"], "assistant", result, model_used))
                        c.execute("INSERT INTO memories (id, memory_id, session_id, content, query, domain, created) VALUES (%s, %s, %s, %s, %s, %s, NOW())",
                                 (sid(), f"mem_{sid()}", session["id"], result[:500], user_msg, domain))
                    conn.commit()
        except Exception as e:
            logger.error(f"Save AI error: {e}")
    
    return {
        "content": result,
        "chat_id": chat_id,
        "model": model_used,
        "tier": tier,
        "domain": domain
    }

@app.get("/api/chats")
def get_chats(request: Request):
    user = get_current_user(request)
    if user:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("SELECT id, title, created, updated FROM chats WHERE user_id = %s ORDER BY updated DESC LIMIT 50", (user["id"],))
                    rows = c.fetchall()
                    return {"chats": [{"id": r[0], "title": r[1] or "New Chat", "created": r[2].isoformat() if r[2] else None, "updated": r[3].isoformat() if r[3] else None} for r in rows]}
        except: pass
    else:
        try:
            session = get_current_session(request)
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("SELECT id, title, created, updated FROM chats WHERE session_id = %s ORDER BY updated DESC LIMIT 50", (session["id"],))
                    rows = c.fetchall()
                    return {"chats": [{"id": r[0], "title": r[1] or "New Chat", "created": r[2].isoformat() if r[2] else None, "updated": r[3].isoformat() if r[3] else None} for r in rows]}
        except: pass
    return {"chats": []}

@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str, request: Request):
    user = get_current_user(request)
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                if user:
                    c.execute("DELETE FROM chat_messages WHERE chat_id = %s AND user_id = %s", (chat_id, user["id"]))
                    c.execute("DELETE FROM chats WHERE id = %s AND user_id = %s", (chat_id, user["id"]))
                else:
                    session = get_current_session(request)
                    c.execute("DELETE FROM chat_messages WHERE chat_id = %s AND session_id = %s", (chat_id, session["id"]))
                    c.execute("DELETE FROM chats WHERE id = %s AND session_id = %s", (chat_id, session["id"]))
                conn.commit()
                return {"deleted": True}
    except:
        raise HTTPException(500, "Could not delete chat")

# ================================================================
# PROJECTS ENDPOINTS (Pro and Pro Max)
# ================================================================
@app.get("/api/projects")
def get_projects(user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Authentication required")
    tier_info = TIER_CONFIG.get(user["tier"], TIER_CONFIG["free"])
    if not tier_info["projects_enabled"]:
        return {"projects": [], "message": "Projects require Pro or Pro Max tier"}
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, name, description, created_at FROM projects WHERE user_id = %s ORDER BY created_at DESC", (user["id"],))
                rows = c.fetchall()
                return {"projects": [{"id": r[0], "name": r[1], "description": r[2], "created_at": r[3].isoformat() if r[3] else None} for r in rows]}
    except:
        return {"projects": []}

@app.post("/api/projects")
def create_project(req: dict, user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Authentication required")
    tier_info = TIER_CONFIG.get(user["tier"], TIER_CONFIG["free"])
    if not tier_info["projects_enabled"]:
        raise HTTPException(403, "Projects require Pro or Pro Max tier")
    
    name = req.get("name")
    description = req.get("description", "")
    if not name:
        raise HTTPException(400, "Project name required")
    
    project_id = str(uuid.uuid4())
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO projects (id, user_id, name, description) VALUES (%s, %s, %s, %s)",
                         (project_id, user["id"], name, description))
                conn.commit()
        return {"id": project_id, "name": name, "description": description}
    except Exception as e:
        logger.error(f"Create project error: {e}")
        raise HTTPException(500, "Could not create project")

@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str, user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Authentication required")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("DELETE FROM projects WHERE id = %s AND user_id = %s", (project_id, user["id"]))
                conn.commit()
                return {"deleted": True}
    except:
        raise HTTPException(500, "Could not delete project")

# ================================================================
# PAYMENT & UPGRADE ENDPOINTS
# ================================================================
@app.get("/api/payment-config")
def payment_config():
    return {
        "wallets": WALLETS,
        "tiers": {
            "plus": {"price": 8, "features": TIER_CONFIG["plus"]},
            "pro": {"price": 17, "features": TIER_CONFIG["pro"]},
            "pro_max": {"price": 30, "features": TIER_CONFIG["pro_max"]}
        }
    }

class UpgradeRequest(BaseModel):
    tier: str
    txid: str
    currency: str = "BTC"

@app.post("/api/upgrade")
def upgrade(req: UpgradeRequest, request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401, "Authentication required")
    
    if req.tier not in ("plus", "pro", "pro_max"):
        raise HTTPException(400, "Invalid tier")
    if not req.txid.strip():
        raise HTTPException(400, "TXID required")
    
    prices = {"plus": 8, "pro": 17, "pro_max": 30}
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO payments (id, user_id, txid, currency, amount, tier, verified, expires_at) VALUES (%s, %s, %s, %s, %s, %s, 1, %s)",
                         (str(uuid.uuid4()), user["id"], req.txid.strip(), req.currency.upper(), prices[req.tier], req.tier,
                          datetime.utcnow() + timedelta(days=30)))
                c.execute("UPDATE users SET tier = %s, tier_expires = %s, updated_at = NOW() WHERE id = %s",
                         (req.tier, datetime.utcnow() + timedelta(days=30), user["id"]))
                conn.commit()
    except Exception as e:
        logger.error(f"Upgrade error: {e}")
        raise HTTPException(500, "Could not process upgrade")
    
    return {"verified": True, "tier": req.tier}

# ================================================================
# FOUNDER ENDPOINT
# ================================================================
class FounderRequest(BaseModel):
    code: str

@app.post("/api/founder")
def founder(req: FounderRequest):
    if req.code != settings.FOUNDER_KEY:
        raise HTTPException(403, "Invalid founder code")
    return {"verified": True, "tier": "founder", "message": "Founder access granted"}

# ================================================================
# MARKET & NEWS ENDPOINTS (Tier-gated)
# ================================================================
@app.get("/api/markets")
def markets(request: Request):
    user = get_current_user(request)
    tier = user["tier"] if user else "free"
    if tier not in ("pro", "pro_max", "founder"):
        return {"prices": {}, "news": [], "message": "Pro tier required"}
    return {"prices": get_market_data(), "news": get_financial_news()}

@app.get("/api/markets/prices")
def markets_prices(request: Request):
    user = get_current_user(request)
    tier = user["tier"] if user else "free"
    if tier not in ("pro", "pro_max", "founder"):
        return {"prices": {}, "message": "Pro tier required"}
    return {"prices": get_market_data()}

@app.get("/api/markets/news")
def markets_news(request: Request):
    user = get_current_user(request)
    tier = user["tier"] if user else "free"
    if tier not in ("pro", "pro_max", "founder"):
        return {"news": [], "message": "Pro tier required"}
    return {"news": get_financial_news()}

@app.get("/api/news/tech")
def tech_news(request: Request):
    user = get_current_user(request)
    tier = user["tier"] if user else "free"
    if tier not in ("pro", "pro_max", "founder"):
        return {"news": [], "message": "Pro tier required"}
    return {"news": get_tech_news()}

@app.get("/api/search")
def web_search(q: str, request: Request):
    user = get_current_user(request)
    tier = user["tier"] if user else "free"
    if tier not in ("plus", "pro", "pro_max", "founder"):
        return {"results": [], "message": "Web search on Plus and Pro"}
    return {"results": search_web(q)}

# ================================================================
# WORKSPACE ENDPOINTS
# ================================================================
@app.post("/api/workspace/create")
def ws_create(req: dict, user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Authentication required")
    tier_info = TIER_CONFIG.get(user["tier"], TIER_CONFIG["free"])
    if tier_info["workspace_max"] == 0:
        raise HTTPException(403, "Work Area requires Plus or Pro")
    
    room_code = req.get("room_code", f"CAP-{sid()}")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                wid = sid()
                c.execute("INSERT INTO workspaces (id, name, owner_id, room_code, max_members) VALUES (%s, %s, %s, %s, %s)",
                         (wid, req.get("name", "My Workspace"), user["id"], room_code.upper(), tier_info["workspace_seats"]))
                c.execute("INSERT INTO workspace_members (workspace_id, user_id, role) VALUES (%s, %s, %s)",
                         (wid, user["id"], "admin"))
                conn.commit()
                return {"room_id": wid, "room_code": room_code.upper(), "created": True}
    except:
        return {"created": False}

@app.post("/api/workspace/join")
def ws_join(req: dict, user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Authentication required")
    room_code = req.get("room_code", "").upper()
    if not room_code:
        raise HTTPException(400, "Room code required")
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, max_members FROM workspaces WHERE room_code = %s", (room_code,))
                ws = c.fetchone()
                if not ws:
                    raise HTTPException(404, "Room not found")
                c.execute("SELECT COUNT(*) FROM workspace_members WHERE workspace_id = %s", (ws[0],))
                if c.fetchone()[0] >= ws[1]:
                    raise HTTPException(400, "Room full")
                c.execute("INSERT INTO workspace_members (workspace_id, user_id, role) VALUES (%s, %s, %s)",
                         (ws[0], user["id"], "member"))
                conn.commit()
                return {"joined": True, "room_id": ws[0]}
    except HTTPException:
        raise
    except:
        return {"joined": False}

@app.post("/api/workspace/message")
def ws_message(req: dict, user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Authentication required")
    room_code = req.get("room_code", "").upper()
    message = req.get("message", "")
    if not room_code or not message:
        raise HTTPException(400, "Room code and message required")
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM workspaces WHERE room_code = %s", (room_code,))
                ws = c.fetchone()
                if not ws:
                    raise HTTPException(404, "Room not found")
                
                is_ai = message.strip().startswith("@CAPITAN")
                if is_ai:
                    result, _ = call_ai_with_tier([{"role": "user", "content": message.replace('@CAPITAN', '').strip()}], user["tier"])
                    if result:
                        c.execute("INSERT INTO workspace_messages (id, workspace_id, user_id, author_name, message, is_ai) VALUES (%s, %s, %s, %s, %s, 1)",
                                 (sid(), ws[0], user["id"], "CAPITAN AI", result))
                
                c.execute("INSERT INTO workspace_messages (id, workspace_id, user_id, author_name, message) VALUES (%s, %s, %s, %s, %s)",
                         (sid(), ws[0], user["id"], user["name"], message))
                conn.commit()
                return {"sent": True}
    except:
        return {"sent": False}

@app.get("/api/workspace/messages")
def ws_get_messages(room_code: str, user: dict = Depends(get_current_user)):
    if not user:
        return {"messages": [], "members": []}
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM workspaces WHERE room_code = %s", (room_code.upper(),))
                ws = c.fetchone()
                if not ws:
                    return {"messages": [], "members": []}
                c.execute("SELECT u.name, wm.role FROM workspace_members wm JOIN users u ON wm.user_id = u.id WHERE wm.workspace_id = %s", (ws[0],))
                members = [{"name": r[0], "role": r[1]} for r in c.fetchall()]
                c.execute("SELECT id, author_name, message, is_ai, created FROM workspace_messages WHERE workspace_id = %s ORDER BY created ASC LIMIT 50", (ws[0],))
                messages = [{"id": r[0], "author": r[1], "message": r[2], "is_ai": bool(r[3]), "created": r[4].isoformat() if r[4] else None} for r in c.fetchall()]
                return {"messages": messages, "members": members}
    except:
        return {"messages": [], "members": []}

# ================================================================
# LIBRARY ENDPOINTS
# ================================================================
@app.get("/api/library")
def get_library(request: Request):
    user = get_current_user(request)
    if not user:
        return {"items": []}
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, name, type, content, size, created FROM library_items WHERE user_id = %s ORDER BY created DESC", (user["id"],))
                rows = c.fetchall()
                return {"items": [{"id": r[0], "name": r[1], "type": r[2], "content": r[3], "size": r[4], "created": r[5].isoformat() if r[5] else None} for r in rows]}
    except:
        return {"items": []}

class LibraryItemRequest(BaseModel):
    name: str
    type: str = "note"
    content: Optional[str] = ""

@app.post("/api/library")
def create_library_item(req: LibraryItemRequest, user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Authentication required")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                item_id = f"lib_{sid()}"
                c.execute("INSERT INTO library_items (id, user_id, name, type, content, size, created) VALUES (%s, %s, %s, %s, %s, %s, NOW())",
                         (item_id, user["id"], req.name, req.type, req.content or "", len(req.content or "")))
                conn.commit()
                return {"id": item_id, "created": True}
    except:
        return {"created": False}

@app.delete("/api/library/{item_id}")
def delete_library_item(item_id: str, user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Authentication required")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("DELETE FROM library_items WHERE id = %s AND user_id = %s", (item_id, user["id"]))
                conn.commit()
                return {"deleted": True}
    except:
        return {"deleted": False}

# ================================================================
# UPLOAD ENDPOINT
# ================================================================
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Authentication required")
    tier_info = TIER_CONFIG.get(user["tier"], TIER_CONFIG["free"])
    if not tier_info["file_upload"]:
        raise HTTPException(403, "Upgrade to Plus or Pro for file uploads")
    
    contents = await file.read()
    max_size = 50 if user["tier"] == "pro" else (100 if user["tier"] == "pro_max" else 10)
    if len(contents) / (1024 * 1024) > max_size:
        raise HTTPException(400, f"Max {max_size}MB")
    
    file_id = f"file_{sid()}"
    file_path = os.path.join(UPLOAD_DIR, file_id)
    
    with open(file_path, "wb") as f:
        f.write(contents)
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO uploaded_files (id, user_id, filename, original_name, size, mime_type, storage_path, created) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())",
                         (file_id, user["id"], file_id, file.filename or "unknown", len(contents), file.content_type or "application/octet-stream", file_path))
                conn.commit()
    except Exception as e:
        logger.error(f"Save file error: {e}")
    
    return {"id": file_id, "filename": file.filename, "size_mb": round(len(contents) / (1024 * 1024), 2)}

# ================================================================
# ADMIN ENDPOINT (Founder only)
# ================================================================
@app.post("/api/admin")
def admin(user: dict = Depends(get_current_user)):
    if not user or user["tier"] != "founder":
        raise HTTPException(403, "Access denied")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT COUNT(*) FROM users")
                total_users = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM users WHERE tier != 'free'")
                paid_users = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM chat_messages")
                total_msgs = c.fetchone()[0]
                return {"total_users": total_users, "paid_users": paid_users, "total_messages": total_msgs}
    except:
        return {"total_users": 0, "paid_users": 0, "total_messages": 0}

# ================================================================
# HEALTH CHECK
# ================================================================
@app.get("/health")
def health():
    db_status = "disconnected"
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT 1")
                db_status = "connected"
    except: pass
    
    ai_status = "connected" if (settings.GROQ_API_KEY or settings.OPENROUTER_API_KEY) else "disconnected"
    providers = []
    if settings.GROQ_API_KEY: providers.append("groq")
    if settings.OPENROUTER_API_KEY: providers.append("openrouter")
    
    return {
        "status": "ok",
        "version": "26.0",
        "database": db_status,
        "ai": ai_status,
        "providers": providers,
        "auth_enabled": True
    }

# ================================================================
# PWA & STATIC FILES
# ================================================================
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
        <path d="M50 15 L75 27 L75 52 C75 65 63 76 50 82 C37 76 25 65 25 52 L25 27 Z" fill="none" stroke="#4ADE80" stroke-width="4"/>
        <text x="50" y="72" text-anchor="middle" font-size="42" fill="#4ADE80" font-family="Inter,sans-serif" font-weight="700">C</text>
    </svg>'''
    return Response(content=svg, media_type="image/svg+xml")

@app.get("/icon-512.png")
async def icon_512():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
        <rect width="100" height="100" fill="#000" rx="20"/>
        <path d="M50 15 L75 27 L75 52 C75 65 63 76 50 82 C37 76 25 65 25 52 L25 27 Z" fill="none" stroke="#4ADE80" stroke-width="4"/>
        <text x="50" y="72" text-anchor="middle" font-size="42" fill="#4ADE80" font-family="Inter,sans-serif" font-weight="700">C</text>
    </svg>'''
    return Response(content=svg, media_type="image/svg+xml")

@app.get("/")
async def root():
    return {
        "name": "CAPITAN AI",
        "version": "26.0",
        "status": "operational",
        "auth_enabled": True,
        "tiers": ["free", "plus", "pro", "pro_max"],
        "pwa_supported": True
    }

# ================================================================
# MAIN ENTRY POINT
# ================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"\n{'='*60}")
    print(f"🚀 CAPITAN AI v26.0 - ENTERPRISE BACKEND")
    print(f"{'='*60}")
    print(f"📊 Database: {'Connected' if settings.DATABASE_URL or settings.SUPABASE_DB_PASSWORD else 'Not configured'}")
    print(f"🤖 AI Providers: Groq={bool(settings.GROQ_API_KEY)} | OpenRouter={bool(settings.OPENROUTER_API_KEY)}")
    print(f"📈 Markets: CoinGecko={bool(settings.COINGECKO_KEY)} | Yahoo=Active")
    print(f"🔍 Web Search: SerpAPI={bool(settings.SERPAPI_KEY)}")
    print(f"📰 News: NewsAPI={bool(settings.NEWS_API_KEY)}")
    print(f"🔐 Auth: Magic links enabled")
    print(f"💎 Tiers: Free(20) | Plus(50/$8) | Pro(150/$17) | Pro Max(∞/$30)")
    print(f"📨 AI Models by Tier: Free(Groq 3.1) | Plus(Groq 3.3) | Pro(Claude) | Pro Max(Ensemble)")
    print(f"👑 Founder Key: {settings.FOUNDER_KEY[:10]}...")
    print(f"🌐 PWA: Enabled")
    print(f"{'='*60}\n")
    uvicorn.run(app, host="0.0.0.0", port=port)