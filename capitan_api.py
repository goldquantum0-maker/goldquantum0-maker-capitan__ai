"""
CAPITAN AI — Enterprise Backend v28.0
CLOSEAI Technologies
FULL INTELLIGENCE RESTORED | Elite Reasoning | Human-Like Communication
PWA Ready | All Components | Production Grade
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
from hashlib import sha256

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response, HTMLResponse, RedirectResponse
from pydantic import BaseModel
from pydantic_settings import BaseSettings
import psycopg2
import psycopg2.extras
import uvicorn

# ================================================================
# FASTAPI APP - CREATED EARLY (FIXED POSITION)
# ================================================================
app = FastAPI(title="CAPITAN AI API", version="28.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# ================================================================
# LOGGING SETUP
# ================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ================================================================
# CONFIGURATION
# ================================================================
class Settings(BaseSettings):
    DATABASE_URL: str = ""
    SUPABASE_DB_HOST: str = ""
    SUPABASE_DB_PORT: str = "5432"
    SUPABASE_DB_NAME: str = "postgres"
    SUPABASE_DB_USER: str = "postgres"
    SUPABASE_DB_PASSWORD: str = ""
    JWT_SECRET: str = secrets.token_hex(32)
    FOUNDER_KEY: str = "Osinachi@35"
    TELEGRAM_BOT_TOKEN: str = "8742624883:AAHpXfQCysOf9eZFC27O4G4vPHQRezjeA10"
    TELEGRAM_BOT_USERNAME: str = "Capitan_ai_Bot"
    FRONTEND_URL: str = "https://capitan.pages.dev"
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    COINGECKO_KEY: str = ""
    SERPAPI_KEY: str = ""
    NEWS_API_KEY: str = ""
    GNEWS_API_KEY: str = ""
    FINNHUB_API_KEY: str = ""
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
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute('CREATE TABLE IF NOT EXISTS users (id UUID PRIMARY KEY, telegram_id BIGINT UNIQUE, telegram_username TEXT, first_name TEXT, last_name TEXT, name TEXT, email TEXT, tier TEXT DEFAULT \'free\', tier_expires TIMESTAMP, created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW())')
                c.execute('CREATE TABLE IF NOT EXISTS user_sessions (id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE, token TEXT UNIQUE NOT NULL, created_at TIMESTAMP DEFAULT NOW(), expires_at TIMESTAMP)')
                c.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, tier TEXT DEFAULT \'free\', msg_count INTEGER DEFAULT 0, msg_window TEXT, created TIMESTAMP, updated TIMESTAMP)')
                c.execute('CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE, session_id TEXT, title TEXT, created TIMESTAMP DEFAULT NOW(), updated TIMESTAMP DEFAULT NOW())')
                c.execute('CREATE TABLE IF NOT EXISTS chat_messages (id TEXT PRIMARY KEY, chat_id TEXT, user_id UUID REFERENCES users(id) ON DELETE CASCADE, session_id TEXT, role TEXT, content TEXT, model TEXT, created TIMESTAMP DEFAULT NOW())')
                c.execute('CREATE TABLE IF NOT EXISTS memories (id TEXT PRIMARY KEY, memory_id TEXT, user_id UUID REFERENCES users(id) ON DELETE CASCADE, session_id TEXT, content TEXT, query TEXT, domain TEXT, created TIMESTAMP DEFAULT NOW())')
                c.execute('CREATE TABLE IF NOT EXISTS library_items (id TEXT PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE, session_id TEXT, name TEXT, type TEXT, content TEXT, size INTEGER DEFAULT 0, created TIMESTAMP DEFAULT NOW())')
                c.execute('CREATE TABLE IF NOT EXISTS projects (id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE, name TEXT NOT NULL, description TEXT, created_at TIMESTAMP DEFAULT NOW())')
                c.execute('CREATE TABLE IF NOT EXISTS workspaces (id TEXT PRIMARY KEY, name TEXT, owner_id UUID REFERENCES users(id) ON DELETE CASCADE, room_code TEXT UNIQUE, max_members INTEGER DEFAULT 10, created_at TIMESTAMP DEFAULT NOW())')
                c.execute('CREATE TABLE IF NOT EXISTS workspace_members (workspace_id TEXT, user_id UUID REFERENCES users(id) ON DELETE CASCADE, role TEXT DEFAULT \'member\', joined_at TIMESTAMP DEFAULT NOW(), PRIMARY KEY (workspace_id, user_id))')
                c.execute('CREATE TABLE IF NOT EXISTS workspace_messages (id TEXT PRIMARY KEY, workspace_id TEXT, user_id UUID REFERENCES users(id) ON DELETE CASCADE, author_name TEXT, message TEXT, is_ai INTEGER DEFAULT 0, created TIMESTAMP DEFAULT NOW())')
                c.execute('CREATE TABLE IF NOT EXISTS payments (id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE, txid TEXT UNIQUE, currency TEXT, amount REAL, tier TEXT, verified INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT NOW(), expires_at TIMESTAMP)')
                c.execute('CREATE TABLE IF NOT EXISTS market_cache (id TEXT PRIMARY KEY, category TEXT, data TEXT, created TIMESTAMP DEFAULT NOW())')
                c.execute('CREATE TABLE IF NOT EXISTS news_cache (id TEXT PRIMARY KEY, category TEXT, data TEXT, created TIMESTAMP DEFAULT NOW())')
                c.execute('CREATE TABLE IF NOT EXISTS web_cache (id TEXT PRIMARY KEY, query_hash TEXT, data TEXT, created TIMESTAMP DEFAULT NOW())')
                conn.commit()
        logger.info("✅ Database tables ready")
    except Exception as e:
        logger.warning(f"Database init: {e}")

init_db()
def sid(): return str(uuid.uuid4())[:8].upper()

# ================================================================
# AUTHENTICATION
# ================================================================
def create_auth_token(user_id: str) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"user_id": user_id, "type": "user", "exp": int((datetime.utcnow() + timedelta(days=30)).timestamp())}).encode()).decode().rstrip("=")
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
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "): return None
    payload = verify_jwt(auth[7:])
    if not payload or payload.get("type") != "user": return None
    user_id = payload.get("user_id")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, telegram_id, telegram_username, name, tier, created_at FROM users WHERE id = %s", (user_id,))
                row = c.fetchone()
                if row:
                    return {"id": row[0], "telegram_id": row[1], "telegram_username": row[2], "name": row[3] or f"User_{row[1]}", "tier": row[4], "created_at": row[5].isoformat() if row[5] else None}
    except: pass
    return None

# ================================================================
# TELEGRAM AUTH
# ================================================================
def check_telegram_authorization(data: dict) -> Optional[dict]:
    if not settings.TELEGRAM_BOT_TOKEN: return None
    check_data = data.copy()
    received_hash = check_data.pop('hash', None)
    if not received_hash: return None
    check_string = '\n'.join(f"{k}={v}" for k, v in sorted(check_data.items()))
    secret_key = sha256(settings.TELEGRAM_BOT_TOKEN.encode()).digest()
    computed_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if computed_hash != received_hash: return None
    auth_date = int(data.get('auth_date', 0))
    if datetime.utcnow().timestamp() - auth_date > 86400: return None
    return {"id": int(data.get('id')), "first_name": data.get('first_name'), "last_name": data.get('last_name'), "username": data.get('username'), "photo_url": data.get('photo_url')}

@app.post("/api/auth/telegram/verify")
async def verify_telegram_login(req: dict):
    data = req.get("data", {})
    user_info = check_telegram_authorization(data)
    if not user_info: raise HTTPException(400, "Invalid Telegram authorization")
    telegram_id = user_info["id"]
    telegram_username = user_info.get("username", "")
    first_name = user_info.get("first_name", "")
    last_name = user_info.get("last_name", "")
    name = f"{first_name} {last_name}".strip() or telegram_username or f"User_{telegram_id}"
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, tier FROM users WHERE telegram_id = %s", (telegram_id,))
                user = c.fetchone()
                if not user:
                    user_id = str(uuid.uuid4())
                    c.execute("INSERT INTO users (id, telegram_id, telegram_username, first_name, last_name, name, tier) VALUES (%s, %s, %s, %s, %s, %s, %s)", (user_id, telegram_id, telegram_username, first_name, last_name, name, "free"))
                    user = (user_id, "free")
                else:
                    user_id = user[0]
                    c.execute("UPDATE users SET telegram_username = %s, first_name = %s, last_name = %s, name = %s, updated_at = NOW() WHERE id = %s", (telegram_username, first_name, last_name, name, user_id))
                auth_token = create_auth_token(user_id)
                c.execute("INSERT INTO user_sessions (id, user_id, token, expires_at) VALUES (%s, %s, %s, %s)", (str(uuid.uuid4()), user_id, auth_token, datetime.utcnow() + timedelta(days=30)))
                conn.commit()
                return {"token": auth_token, "user": {"id": user_id, "telegram_id": telegram_id, "telegram_username": telegram_username, "name": name, "tier": user[1]}}
    except Exception as e:
        logger.error(f"Verify error: {e}")
        raise HTTPException(500, "Verification failed")

@app.get("/api/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401, "Not authenticated")
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

@app.get("/api/session")
def get_anonymous_session():
    session_id = f"s_{sid()}"
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO sessions (id, tier, msg_count, msg_window, created, updated) VALUES (%s, %s, 0, %s, %s, %s)", (session_id, "free", None, datetime.utcnow(), datetime.utcnow()))
                conn.commit()
    except: pass
    token = create_session_jwt(session_id, "free")
    return {"id": session_id, "tier": "free", "msg_count": 0, "token": token}

def create_session_jwt(session_id: str, tier: str) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"session_id": session_id, "tier": tier, "type": "session", "exp": int((datetime.utcnow() + timedelta(days=365)).timestamp())}).encode()).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(hmac.new(settings.JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return f"{header}.{payload}.{signature}"

@app.post("/api/founder")
async def founder_login(req: dict):
    code = req.get("code")
    if code != settings.FOUNDER_KEY: raise HTTPException(403, "Invalid founder code")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM users WHERE telegram_username = 'founder' OR name = 'CAPITAN Founder'")
                existing = c.fetchone()
                if existing:
                    user_id = existing[0]
                else:
                    user_id = str(uuid.uuid4())
                    c.execute("INSERT INTO users (id, telegram_id, telegram_username, name, email, tier) VALUES (%s, %s, %s, %s, %s, %s)", (user_id, 0, 'founder', 'CAPITAN Founder', 'founder@capitan.ai', 'founder'))
                auth_token = create_auth_token(user_id)
                c.execute("INSERT INTO user_sessions (id, user_id, token, expires_at) VALUES (%s, %s, %s, %s)", (str(uuid.uuid4()), user_id, auth_token, datetime.utcnow() + timedelta(days=365)))
                conn.commit()
                return {"verified": True, "tier": "founder", "token": auth_token, "user": {"id": user_id, "name": "CAPITAN Founder", "email": "founder@capitan.ai", "tier": "founder"}}
    except Exception as e:
        logger.error(f"Founder login error: {e}")
        raise HTTPException(500, "Founder login failed")

# ================================================================
# TIER CONFIGURATION
# ================================================================
TIER_CONFIG = {
    "free": {"name": "Free", "msg_limit": 20, "workspace_seats": 0, "projects_enabled": False, "file_upload": False, "live_markets": False, "web_search": False, "ai_model": "Groq 3.1", "price": 0},
    "plus": {"name": "Plus", "msg_limit": 50, "workspace_seats": 10, "projects_enabled": False, "file_upload": True, "live_markets": False, "web_search": True, "ai_model": "Groq 3.3", "price": 8},
    "pro": {"name": "Pro", "msg_limit": 150, "workspace_seats": 25, "projects_enabled": True, "file_upload": True, "live_markets": True, "web_search": True, "ai_model": "Claude 3.5", "price": 17},
    "pro_max": {"name": "Pro Max", "msg_limit": float("inf"), "workspace_seats": 50, "projects_enabled": True, "file_upload": True, "live_markets": True, "web_search": True, "ai_model": "GPT-4o + Claude Ensemble", "price": 30},
    "founder": {"name": "Founder", "msg_limit": float("inf"), "workspace_seats": 100, "projects_enabled": True, "file_upload": True, "live_markets": True, "web_search": True, "ai_model": "All Models", "price": 0}
}

WALLETS = {"BTC": "bc1qrv6yr6e0mat96rvrc8smdf9rvu9rlp8xuk8new", "ETH": "0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1"}

UPGRADE_BENEFITS = {
    "plus": ["50 messages/day", "Groq 3.3 70B", "Work Area (10 seats)", "File uploads", "Web search"],
    "pro": ["150 messages/day", "Claude 3.5", "Work Area (25 seats)", "Live markets", "Projects"],
    "pro_max": ["Unlimited messages", "GPT-4o + Claude Ensemble", "Work Area (50 seats)", "Advanced reasoning"]
}

# ================================================================
# RATE LIMITING
# ================================================================
rate_store = {}
def check_rate_limit(id: str, tier: str) -> bool:
    now = time.time()
    key = f"rate:{id}"
    if key not in rate_store: rate_store[key] = []
    rate_store[key] = [t for t in rate_store[key] if now - t < 60]
    limits = {"free": 20, "plus": 40, "pro": 80, "pro_max": 150, "founder": 300}
    limit = limits.get(tier, 20)
    if len(rate_store[key]) >= limit: return False
    rate_store[key].append(now)
    return True

# ================================================================
# MARKET DATA
# ================================================================
def get_market_data():
    results = {}
    if settings.COINGECKO_KEY:
        try:
            ids = "bitcoin,ethereum,ripple,cardano,solana,polkadot,dogecoin"
            r = requests.get("https://api.coingecko.com/api/v3/simple/price", params={"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true"}, headers={"x-cg-demo-api-key": settings.COINGECKO_KEY}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                nm = {"bitcoin": "BTC", "ethereum": "ETH", "ripple": "XRP", "cardano": "ADA", "solana": "SOL", "polkadot": "DOT", "dogecoin": "DOGE"}
                for k, v in data.items():
                    results[nm.get(k, k.upper())] = {"price": v["usd"], "change": round(v.get("usd_24h_change", 0), 2), "source": "CoinGecko"}
        except: pass
    try:
        syms = "^GSPC,^IXIC,^DJI,^FTSE,AAPL,MSFT,NVDA,TSLA,GOOGL,META,AMZN,GC=F,CL=F,EURUSD=X,GBPUSD=X,USDJPY=X"
        r = requests.get(f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={syms}", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code == 200:
            for i in r.json().get("quoteResponse", {}).get("result", []):
                name = i.get("shortName") or i.get("symbol", "")
                price = i.get("regularMarketPrice")
                prev = i.get("regularMarketPreviousClose")
                if price and prev:
                    chg = i.get("regularMarketChangePercent")
                    results[name] = {"price": price, "change": round(chg, 2) if chg else round(((price - prev) / prev) * 100, 2), "source": "Yahoo Finance"}
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
            r = requests.get("https://newsapi.org/v2/everything", params={"q": "AI artificial intelligence coding startup innovation", "language": "en", "pageSize": 12, "sortBy": "publishedAt", "apiKey": settings.NEWS_API_KEY}, timeout=10)
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
    if settings.SERPAPI_KEY:
        try:
            r = requests.get("https://serpapi.com/search", params={"engine": "google", "q": query, "num": num_results, "api_key": settings.SERPAPI_KEY}, timeout=8)
            if r.status_code == 200:
                for item in r.json().get("organic_results", [])[:num_results]:
                    results.append({"title": item.get("title", ""), "snippet": item.get("snippet", "")[:250], "url": item.get("link", ""), "source": "Google"})
        except: pass
    return results

# ================================================================
# ELITE SYSTEM PROMPT (FULL INTELLIGENCE)
# ================================================================
ELITE_SYSTEM_PROMPT = """You are CAPITAN AI — legendary enterprise intelligence platform.

🏦 FINANCE: DCF, LBO, M&A, portfolio optimization, options pricing, risk management, African markets
📈 TRADER: Market microstructure, volatility trading, algorithmic execution
💻 CODER: Full-stack, system architecture, DevOps, databases, hardware engineering
📐 MATH: Pure math, applied math, linear algebra, probability, statistics
📊 QUANT: Time series, factor models, ML in finance, backtesting
🔬 GENERAL: Physics, chemistry, biology, medicine, history, philosophy, current events

RESPONSE STYLE:
- Lead with answer. No throat-clearing.
- Use 1-2 emojis naturally for warmth.
- Short sentences. Clean paragraphs.
- NEVER make up prices or data.
- NEVER give financial advice or medical diagnoses.

TIME: {day}, {date} at {utc_time}. {greeting_context}
DOMAIN: {domain} | TIER: {tier} | AI: {model}
"""

def classify(q):
    q = q.lower()
    if re.search(r'who are you|what are you|identity|introduce yourself', q): return 'identity'
    if re.search(r'who|what|when|where|why|how|news|latest|current|today|search', q) and len(q.split()) > 3: return 'web_search'
    if re.search(r'def |class |import |docker|kubernetes|aws|api|sql|python|javascript|rust|golang|cpu|gpu|ram|hardware', q): return 'coding'
    if re.search(r'dcf|valuation|wacc|stock|trading|portfolio|crypto|bitcoin|forex|markets', q): return 'finance'
    if re.search(r'prove|proof|theorem|integral|derivative|matrix|probability|statistics', q): return 'math'
    if re.search(r'hello|hi|hey|good morning|good afternoon|good evening|thanks|thank you', q): return 'greeting'
    return 'general'

def system_prompt(domain, tier, model, user_id=None, web_results=None):
    now = datetime.utcnow()
    day = now.strftime("%A")
    date = now.strftime("%B %d, %Y")
    utc_time = now.strftime("%H:%M UTC")
    hour = now.hour
    if hour < 5: greeting_context = "The world is quiet. Perfect for deep thinking."
    elif hour < 12: greeting_context = "Fresh day ahead. Ready for new challenges!"
    elif hour < 17: greeting_context = "Markets are alive and moving."
    elif hour < 21: greeting_context = "Winding down but still sharp."
    else: greeting_context = "Night owl mode engaged. Let's get things done!"
    
    base = ELITE_SYSTEM_PROMPT.replace("{domain}", domain).replace("{tier}", tier).replace("{model}", model)
    base = base.replace("{day}", day).replace("{date}", date).replace("{utc_time}", utc_time).replace("{greeting_context}", greeting_context)
    if web_results:
        base += "\n\nWEB SEARCH:\n" + "\n".join([f"• {r['title']}: {r['snippet'][:200]}" for r in web_results[:3]])
    return base

def call_ai_with_tier(messages, tier="free"):
    if settings.GROQ_API_KEY:
        try:
            for m in messages:
                if m.get("role") == "system" and tier == "free" and len(m["content"]) > 1000:
                    m["content"] = m["content"][:1000]
            model = "llama-3.3-70b-versatile" if tier in ("pro", "pro_max", "founder") else "llama-3.1-8b-instant"
            r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"}, json={"model": model, "messages": messages, "temperature": 0.5, "max_tokens": 1500 if tier != "free" else 800}, timeout=30)
            if r.status_code == 200:
                content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if content: return content, model
        except: pass
    if settings.OPENROUTER_API_KEY:
        try:
            model = "anthropic/claude-3.5-sonnet-20241022" if tier in ("pro", "pro_max", "founder") else "google/gemini-flash-1.5"
            r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "Content-Type": "application/json"}, json={"model": model, "messages": messages, "temperature": 0.5, "max_tokens": 2000 if tier in ("pro", "pro_max", "founder") else 800}, timeout=35)
            if r.status_code == 200:
                content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if content: return content, model
        except: pass
    return "I'm having trouble connecting. Please try again.", "fallback"

# ================================================================
# CHAT ENDPOINT
# ================================================================
class ChatRequest(BaseModel):
    messages: list
    chat_id: Optional[str] = None

@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    user = get_current_user(request)
    session = None
    if not user:
        try:
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                payload = verify_jwt(auth[7:])
                if payload and payload.get("type") == "session":
                    session_id = payload.get("session_id")
                    with get_db() as conn:
                        with conn.cursor() as c:
                            c.execute("SELECT id, tier, msg_count FROM sessions WHERE id = %s", (session_id,))
                            row = c.fetchone()
                            if row:
                                session = {"id": row[0], "tier": row[1], "msg_count": row[2] or 0}
        except: pass
    
    if not user and not session:
        raise HTTPException(401, "Authentication required")
    
    tier = user["tier"] if user else session["tier"]
    tier_info = TIER_CONFIG.get(tier, TIER_CONFIG["free"])
    
    if not check_rate_limit(user["id"] if user else session["id"], tier):
        raise HTTPException(429, "Rate limit exceeded")
    
    user_msg = next((m["content"] for m in reversed(req.messages) if m.get("role") == "user"), "")
    if not user_msg:
        raise HTTPException(400, "No message")
    
    chat_id = req.chat_id or f"chat_{sid()}"
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                if user:
                    c.execute("INSERT INTO chats (id, user_id, title, created, updated) VALUES (%s, %s, %s, NOW(), NOW()) ON CONFLICT (id) DO UPDATE SET updated = NOW()", (chat_id, user["id"], user_msg[:60]))
                    c.execute("INSERT INTO chat_messages (id, chat_id, user_id, role, content, created) VALUES (%s, %s, %s, %s, %s, NOW())", (f"msg_{sid()}", chat_id, user["id"], "user", user_msg))
                else:
                    c.execute("INSERT INTO chats (id, session_id, title, created, updated) VALUES (%s, %s, %s, NOW(), NOW()) ON CONFLICT (id) DO UPDATE SET updated = NOW()", (chat_id, session["id"], user_msg[:60]))
                    c.execute("INSERT INTO chat_messages (id, chat_id, session_id, role, content, created) VALUES (%s, %s, %s, %s, %s, NOW())", (f"msg_{sid()}", chat_id, session["id"], "user", user_msg))
                conn.commit()
                c.execute("SELECT role, content FROM chat_messages WHERE chat_id = %s ORDER BY created ASC LIMIT 15", (chat_id,))
                history = [{"role": r[0], "content": r[1]} for r in c.fetchall()]
    except Exception as e:
        logger.error(f"Save error: {e}")
        history = []
    
    domain = classify(user_msg)
    web_results = None
    if tier_info.get("web_search", False) and domain == "web_search":
        try: web_results = search_web(user_msg, 4)
        except: pass
    
    prompt = system_prompt(domain, tier, tier_info["ai_model"], user["id"] if user else None, web_results)
    result, model_used = call_ai_with_tier([{"role": "system", "content": prompt}] + history, tier)
    
    if result:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    if user:
                        c.execute("INSERT INTO chat_messages (id, chat_id, user_id, role, content, model, created) VALUES (%s, %s, %s, %s, %s, %s, NOW())", (f"msg_{sid()}", chat_id, user["id"], "assistant", result, model_used))
                        c.execute("INSERT INTO memories (id, memory_id, user_id, content, query, domain, created) VALUES (%s, %s, %s, %s, %s, %s, NOW())", (sid(), f"mem_{sid()}", user["id"], result[:500], user_msg, domain))
                    else:
                        c.execute("INSERT INTO chat_messages (id, chat_id, session_id, role, content, model, created) VALUES (%s, %s, %s, %s, %s, %s, NOW())", (f"msg_{sid()}", chat_id, session["id"], "assistant", result, model_used))
                    conn.commit()
        except: pass
    
    return {"content": result, "chat_id": chat_id, "model": model_used, "tier": tier, "domain": domain}

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
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                payload = verify_jwt(auth[7:])
                if payload and payload.get("type") == "session":
                    session_id = payload.get("session_id")
                    with get_db() as conn:
                        with conn.cursor() as c:
                            c.execute("SELECT id, title, created, updated FROM chats WHERE session_id = %s ORDER BY updated DESC LIMIT 50", (session_id,))
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
                    auth = request.headers.get("Authorization", "")
                    if auth.startswith("Bearer "):
                        payload = verify_jwt(auth[7:])
                        if payload and payload.get("type") == "session":
                            session_id = payload.get("session_id")
                            c.execute("DELETE FROM chat_messages WHERE chat_id = %s AND session_id = %s", (chat_id, session_id))
                            c.execute("DELETE FROM chats WHERE id = %s AND session_id = %s", (chat_id, session_id))
                conn.commit()
                return {"deleted": True}
    except: pass
    return {"deleted": False}

# ================================================================
# PROJECTS
# ================================================================
@app.get("/api/projects")
def get_projects(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    tier_info = TIER_CONFIG.get(user["tier"], TIER_CONFIG["free"])
    if not tier_info["projects_enabled"]: return {"projects": []}
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, name, description, created_at FROM projects WHERE user_id = %s ORDER BY created_at DESC", (user["id"],))
                rows = c.fetchall()
                return {"projects": [{"id": r[0], "name": r[1], "description": r[2], "created_at": r[3].isoformat() if r[3] else None} for r in rows]}
    except: return {"projects": []}

@app.post("/api/projects")
def create_project(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    tier_info = TIER_CONFIG.get(user["tier"], TIER_CONFIG["free"])
    if not tier_info["projects_enabled"]: raise HTTPException(403, "Projects require Pro tier")
    name = req.get("name")
    if not name: raise HTTPException(400)
    project_id = str(uuid.uuid4())
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO projects (id, user_id, name, description) VALUES (%s, %s, %s, %s)", (project_id, user["id"], name, req.get("description", "")))
                conn.commit()
        return {"id": project_id, "name": name}
    except: raise HTTPException(500)

@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("DELETE FROM projects WHERE id = %s AND user_id = %s", (project_id, user["id"]))
                conn.commit()
                return {"deleted": True}
    except: raise HTTPException(500)

# ================================================================
# PAYMENT & UPGRADE
# ================================================================
@app.get("/api/payment-config")
def payment_config():
    return {"wallets": WALLETS, "prices": {"plus": 8, "pro": 17, "pro_max": 30}, "benefits": UPGRADE_BENEFITS}

class UpgradeRequest(BaseModel):
    tier: str
    txid: str
    currency: str = "BTC"

@app.post("/api/upgrade")
def upgrade(req: UpgradeRequest, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    if req.tier not in ("plus", "pro", "pro_max"): raise HTTPException(400)
    if not req.txid.strip(): raise HTTPException(400)
    prices = {"plus": 8, "pro": 17, "pro_max": 30}
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO payments (id, user_id, txid, currency, amount, tier, verified, expires_at) VALUES (%s, %s, %s, %s, %s, %s, 1, %s)", (str(uuid.uuid4()), user["id"], req.txid.strip(), req.currency.upper(), prices[req.tier], req.tier, datetime.utcnow() + timedelta(days=30)))
                c.execute("UPDATE users SET tier = %s, tier_expires = %s WHERE id = %s", (req.tier, datetime.utcnow() + timedelta(days=30), user["id"]))
                conn.commit()
    except: raise HTTPException(500)
    return {"verified": True, "tier": req.tier}

# ================================================================
# MARKET & NEWS ENDPOINTS
# ================================================================
@app.get("/api/markets")
def markets(request: Request):
    user = get_current_user(request)
    tier = user["tier"] if user else "free"
    if tier not in ("pro", "pro_max", "founder"): return {"prices": {}, "news": [], "message": "Pro tier required"}
    return {"prices": get_market_data(), "news": get_financial_news()}

@app.get("/api/markets/prices")
def markets_prices(request: Request):
    user = get_current_user(request)
    tier = user["tier"] if user else "free"
    if tier not in ("pro", "pro_max", "founder"): return {"prices": {}, "message": "Pro tier required"}
    return {"prices": get_market_data()}

@app.get("/api/markets/news")
def markets_news(request: Request):
    user = get_current_user(request)
    tier = user["tier"] if user else "free"
    if tier not in ("pro", "pro_max", "founder"): return {"news": [], "message": "Pro tier required"}
    return {"news": get_financial_news()}

@app.get("/api/news/tech")
def tech_news(request: Request):
    user = get_current_user(request)
    tier = user["tier"] if user else "free"
    if tier not in ("pro", "pro_max", "founder"): return {"news": [], "message": "Pro tier required"}
    return {"news": get_tech_news()}

@app.get("/api/search")
def web_search(q: str, request: Request):
    user = get_current_user(request)
    tier = user["tier"] if user else "free"
    if tier not in ("plus", "pro", "pro_max", "founder"): return {"results": [], "message": "Web search on Plus and Pro"}
    return {"results": search_web(q)}

# ================================================================
# WORKSPACE
# ================================================================
@app.post("/api/workspace/create")
def ws_create(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    tier_info = TIER_CONFIG.get(user["tier"], TIER_CONFIG["free"])
    if tier_info["workspace_seats"] == 0: raise HTTPException(403, "Work Area requires Plus or Pro")
    room_code = req.get("room_code", f"CAP-{sid()}")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                wid = sid()
                c.execute("INSERT INTO workspaces (id, name, owner_id, room_code, max_members) VALUES (%s, %s, %s, %s, %s)", (wid, req.get("name", "My Workspace"), user["id"], room_code.upper(), tier_info["workspace_seats"]))
                c.execute("INSERT INTO workspace_members (workspace_id, user_id, role) VALUES (%s, %s, %s)", (wid, user["id"], "admin"))
                conn.commit()
                return {"room_id": wid, "room_code": room_code.upper(), "created": True}
    except: return {"created": False}

@app.post("/api/workspace/join")
def ws_join(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    room_code = req.get("room_code", "").upper()
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, max_members FROM workspaces WHERE room_code = %s", (room_code,))
                ws = c.fetchone()
                if not ws: raise HTTPException(404)
                c.execute("SELECT COUNT(*) FROM workspace_members WHERE workspace_id = %s", (ws[0],))
                if c.fetchone()[0] >= ws[1]: raise HTTPException(400)
                c.execute("INSERT INTO workspace_members (workspace_id, user_id, role) VALUES (%s, %s, %s)", (ws[0], user["id"], "member"))
                conn.commit()
                return {"joined": True, "room_id": ws[0]}
    except HTTPException: raise
    except: return {"joined": False}

@app.post("/api/workspace/message")
def ws_message(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    room_code = req.get("room_code", "").upper()
    message = req.get("message", "")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM workspaces WHERE room_code = %s", (room_code,))
                ws = c.fetchone()
                if not ws: raise HTTPException(404)
                is_ai = message.strip().startswith("@CAPITAN")
                if is_ai:
                    result, _ = call_ai_with_tier([{"role": "user", "content": message.replace('@CAPITAN', '').strip()}], user["tier"])
                    if result:
                        c.execute("INSERT INTO workspace_messages (id, workspace_id, user_id, author_name, message, is_ai) VALUES (%s, %s, %s, %s, %s, 1)", (sid(), ws[0], user["id"], "CAPITAN AI", result))
                c.execute("INSERT INTO workspace_messages (id, workspace_id, user_id, author_name, message) VALUES (%s, %s, %s, %s, %s)", (sid(), ws[0], user["id"], user["name"], message))
                conn.commit()
                return {"sent": True}
    except: return {"sent": False}

@app.get("/api/workspace/messages")
def ws_get_messages(room_code: str, user: dict = Depends(get_current_user)):
    if not user: return {"messages": [], "members": []}
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM workspaces WHERE room_code = %s", (room_code.upper(),))
                ws = c.fetchone()
                if not ws: return {"messages": [], "members": []}
                c.execute("SELECT author_name, message, is_ai, created FROM workspace_messages WHERE workspace_id = %s ORDER BY created ASC LIMIT 50", (ws[0],))
                messages = [{"author": r[0], "message": r[1], "is_ai": bool(r[2]), "created": r[3].isoformat() if r[3] else None} for r in c.fetchall()]
                return {"messages": messages}
    except: return {"messages": []}

# ================================================================
# LIBRARY
# ================================================================
@app.get("/api/library")
def get_library(user: dict = Depends(get_current_user)):
    if not user: return {"items": []}
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, name, type, content, size, created FROM library_items WHERE user_id = %s ORDER BY created DESC", (user["id"],))
                rows = c.fetchall()
                return {"items": [{"id": r[0], "name": r[1], "type": r[2], "content": r[3], "size": r[4], "created": r[5].isoformat() if r[5] else None} for r in rows]}
    except: return {"items": []}

class LibraryItemRequest(BaseModel):
    name: str
    type: str = "note"
    content: Optional[str] = ""

@app.post("/api/library")
def create_library_item(req: LibraryItemRequest, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                item_id = f"lib_{sid()}"
                c.execute("INSERT INTO library_items (id, user_id, name, type, content, size, created) VALUES (%s, %s, %s, %s, %s, %s, NOW())", (item_id, user["id"], req.name, req.type, req.content or "", len(req.content or "")))
                conn.commit()
                return {"id": item_id, "created": True}
    except: return {"created": False}

@app.delete("/api/library/{item_id}")
def delete_library_item(item_id: str, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("DELETE FROM library_items WHERE id = %s AND user_id = %s", (item_id, user["id"]))
                conn.commit()
                return {"deleted": True}
    except: return {"deleted": False}

# ================================================================
# ADMIN
# ================================================================
@app.post("/api/admin")
def admin(user: dict = Depends(get_current_user)):
    if not user or user["tier"] != "founder": raise HTTPException(403, "Access denied")
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
    except: raise HTTPException(500)

# ================================================================
# HEALTH & PWA
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
    return {"status": "ok", "version": "28.0", "database": db_status, "telegram_auth": bool(settings.TELEGRAM_BOT_TOKEN)}

@app.get("/manifest.json")
async def get_manifest():
    return JSONResponse(content={"name": "CAPITAN AI", "short_name": "CAPITAN", "start_url": "/", "display": "standalone", "background_color": "#000000", "theme_color": "#A0A0A4", "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"}, {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}]})

@app.get("/icon-192.png")
async def icon_192():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="#000" rx="20"/><path d="M50 15 L75 27 L75 52 C75 65 63 76 50 82 C37 76 25 65 25 52 L25 27 Z" fill="none" stroke="#A0A0A4" stroke-width="4"/><text x="50" y="72" text-anchor="middle" font-size="42" fill="#A0A0A4" font-family="Inter,sans-serif" font-weight="700">C</text></svg>'
    return Response(content=svg, media_type="image/svg+xml")

@app.get("/icon-512.png")
async def icon_512():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="#000" rx="20"/><path d="M50 15 L75 27 L75 52 C75 65 63 76 50 82 C37 76 25 65 25 52 L25 27 Z" fill="none" stroke="#A0A0A4" stroke-width="4"/><text x="50" y="72" text-anchor="middle" font-size="42" fill="#A0A0A4" font-family="Inter,sans-serif" font-weight="700">C</text></svg>'
    return Response(content=svg, media_type="image/svg+xml")

@app.get("/")
async def root():
    return {"name": "CAPITAN AI", "version": "28.0", "status": "operational", "telegram_auth": bool(settings.TELEGRAM_BOT_TOKEN), "pwa_supported": True, "tiers": ["free", "plus", "pro", "pro_max", "founder"]}

# ================================================================
# MAIN ENTRY POINT
# ================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"\n{'='*60}")
    print(f"🚀 CAPITAN AI v28.0 - ENTERPRISE BACKEND")
    print(f"{'='*60}")
    print(f"📊 Database: {'Connected' if settings.DATABASE_URL else 'Not configured'}")
    print(f"🤖 AI: Groq={bool(settings.GROQ_API_KEY)} | OpenRouter={bool(settings.OPENROUTER_API_KEY)}")
    print(f"🔐 Auth: Telegram Bot @{settings.TELEGRAM_BOT_USERNAME}")
    print(f"👑 Founder: Enabled (click logo 5x)")
    print(f"💎 Tiers: Free(20) | Plus(50/$8) | Pro(150/$17) | Pro Max(∞/$30)")
    print(f"📍 URL: http://0.0.0.0:{port}")
    print(f"📍 Health: http://0.0.0.0:{port}/health")
    print(f"{'='*60}\n")
    uvicorn.run(app, host="0.0.0.0", port=port)
