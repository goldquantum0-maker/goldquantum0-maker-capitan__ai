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
    
    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_BOT_USERNAME: str = "capitan_ai_bot"
    
    # Frontend URL for redirects
    FRONTEND_URL: str = "https://capitan.pages.dev"
    
    # AI Providers
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    MISTRAL_API_KEY: str = ""
    HF_TOKEN: str = ""
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    COHERE_API_KEY: str = ""
    
    # Market Data
    ALPHA_VANTAGE_KEY: str = ""
    FRED_API_KEY: str = ""
    FINNHUB_API_KEY: str = ""
    COINGECKO_KEY: str = ""
    TWELVE_DATA_KEY: str = ""
    ETHERSCAN_API_KEY: str = ""
    POLYGON_API_KEY: str = ""
    YAHOO_FINANCE_ENABLED: bool = True
    
    # News & Search
    SERPAPI_KEY: str = ""
    GNEWS_API_KEY: str = ""
    NEWS_API_KEY: str = ""
    BING_SEARCH_KEY: str = ""
    GOOGLE_CSE_ID: str = ""
    GOOGLE_CSE_KEY: str = ""
    
    # AI Enhancement
    ENABLE_REASONING_CHAIN: bool = True
    ENABLE_CODE_EXECUTION: bool = False
    MAX_REASONING_STEPS: int = 5
    TEMPERATURE: float = 0.7
    MAX_TOKENS: int = 4000
    
    # Other
    WOLFRAM_APP_ID: str = ""
    OPENWEATHER_KEY: str = ""
    NEWSAPI_ORG_KEY: str = ""
    
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
                # Users table (Telegram auth)
                c.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id UUID PRIMARY KEY,
                        telegram_id BIGINT UNIQUE,
                        telegram_username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        name TEXT,
                        email TEXT,
                        tier TEXT DEFAULT 'free',
                        tier_expires TIMESTAMP,
                        reasoning_depth INTEGER DEFAULT 1,
                        preferred_domain TEXT DEFAULT 'general',
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
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
                
                # Auth states for Telegram OAuth
                c.execute('''
                    CREATE TABLE IF NOT EXISTS auth_states (
                        id UUID PRIMARY KEY,
                        state TEXT UNIQUE NOT NULL,
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
                
                # Chat messages with reasoning chain storage
                c.execute('''
                    CREATE TABLE IF NOT EXISTS chat_messages (
                        id TEXT PRIMARY KEY,
                        chat_id TEXT,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        session_id TEXT,
                        role TEXT,
                        content TEXT,
                        model TEXT,
                        reasoning_chain TEXT,
                        tokens INTEGER,
                        latency_ms INTEGER,
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')
                
                # Memories with enhanced context
                c.execute('''
                    CREATE TABLE IF NOT EXISTS memories (
                        id TEXT PRIMARY KEY,
                        memory_id TEXT,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        session_id TEXT,
                        content TEXT,
                        query TEXT,
                        domain TEXT,
                        importance INTEGER DEFAULT 1,
                        created TIMESTAMP DEFAULT NOW()
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
                        public_url TEXT,
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
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        tier TEXT,
                        amount REAL,
                        currency TEXT,
                        txid TEXT,
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')
                
                # Reasoning cache for complex queries
                c.execute('''
                    CREATE TABLE IF NOT EXISTS reasoning_cache (
                        id TEXT PRIMARY KEY,
                        query_hash TEXT UNIQUE,
                        reasoning_chain TEXT,
                        result TEXT,
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
        logger.info("✅ All 25+ database tables ready")
    except Exception as e:
        logger.warning(f"Database init: {e}")

init_db()

def sid(): return str(uuid.uuid4())[:8].upper()
def mid(): return 'mem_' + sid()

# ================================================================
# AUTHENTICATION (Telegram)
# ================================================================
def create_auth_token(user_id: str) -> str:
    """Create JWT token for authenticated users"""
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
                c.execute("SELECT id, telegram_id, telegram_username, first_name, last_name, name, email, tier, reasoning_depth, preferred_domain, created_at FROM users WHERE id = %s", (user_id,))
                row = c.fetchone()
                if row:
                    name = row[5] or row[3] or row[2] or f"User_{row[1]}" if row[1] else "User"
                    return {
                        "id": row[0],
                        "telegram_id": row[1],
                        "telegram_username": row[2],
                        "first_name": row[3],
                        "last_name": row[4],
                        "name": name,
                        "email": row[6],
                        "tier": row[7],
                        "reasoning_depth": row[8] or 1,
                        "preferred_domain": row[9] or "general",
                        "created_at": row[10].isoformat() if row[10] else None
                    }
    except Exception as e:
        logger.error(f"Get user error: {e}")
    return None

def get_current_session(request: Request):
    """Get anonymous session from token (fallback for non-authenticated users)"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing authorization header")
    payload = verify_jwt(auth[7:])
    if not payload:
        raise HTTPException(401, "Invalid or expired token")
    
    if payload.get("type") == "user":
        user = get_current_user(request)
        if user:
            return {"id": user["id"], "tier": user["tier"], "msg_count": 0, "is_user": True, "user_data": user}
    
    session_id = payload.get("session_id")
    tier = payload.get("tier", "free")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, tier, msg_count, msg_window FROM sessions WHERE id = %s", (session_id,))
                row = c.fetchone()
                if row:
                    return {"id": row[0], "tier": row[1], "msg_count": row[2] or 0, "msg_window": row[3], "is_user": False}
                else:
                    now = datetime.utcnow()
                    c.execute("INSERT INTO sessions (id, tier, msg_count, msg_window, created, updated) VALUES (%s, %s, 0, %s, %s, %s)",
                             (session_id, tier, None, now, now))
                    conn.commit()
                    return {"id": session_id, "tier": tier, "msg_count": 0, "msg_window": None, "is_user": False}
    except Exception as e:
        logger.error(f"Session error: {e}")
    raise HTTPException(401, "Session not found")

# ================================================================
# TELEGRAM AUTH ENDPOINTS
# ================================================================

def check_telegram_authorization(data: dict) -> Optional[dict]:
    """Verify Telegram login data"""
    if not settings.TELEGRAM_BOT_TOKEN:
        return None
    
    check_data = data.copy()
    received_hash = check_data.pop('hash', None)
    
    if not received_hash:
        return None
    
    check_string = '\n'.join(f"{k}={v}" for k, v in sorted(check_data.items()))
    secret_key = sha256(settings.TELEGRAM_BOT_TOKEN.encode()).digest()
    computed_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    
    if computed_hash != received_hash:
        return None
    
    auth_date = int(data.get('auth_date', 0))
    if datetime.utcnow().timestamp() - auth_date > 86400:
        return None
    
    return {
        "id": int(data.get('id')),
        "first_name": data.get('first_name'),
        "last_name": data.get('last_name'),
        "username": data.get('username'),
        "photo_url": data.get('photo_url')
    }

@app.get("/api/auth/telegram/callback")
async def telegram_callback(request: Request):
    params = dict(request.query_params)
    if not params:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/")
    import urllib.parse
    tg_data = urllib.parse.urlencode(params)
    redirect_url = f"{settings.FRONTEND_URL}/?tgAuth={urllib.parse.quote(tg_data)}"
    logger.info(f"Telegram callback received, redirecting to frontend")
    return RedirectResponse(url=redirect_url)

@app.post("/api/auth/telegram/verify")
async def verify_telegram_login(req: dict):
    data = req.get("data", {})
    user_info = check_telegram_authorization(data)
    if not user_info:
        raise HTTPException(400, "Invalid Telegram authorization")
    
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
                    c.execute("""
                        INSERT INTO users (id, telegram_id, telegram_username, first_name, last_name, name, tier, reasoning_depth, preferred_domain)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (user_id, telegram_id, telegram_username, first_name, last_name, name, "free", 1, "general"))
                    user = (user_id, "free")
                else:
                    user_id = user[0]
                    c.execute("""
                        UPDATE users SET telegram_username = %s, first_name = %s, last_name = %s, name = %s, updated_at = NOW()
                        WHERE id = %s
                    """, (telegram_username, first_name, last_name, name, user_id))
                
                auth_token = create_auth_token(user_id)
                c.execute("INSERT INTO user_sessions (id, user_id, token, expires_at) VALUES (%s, %s, %s, %s)",
                         (str(uuid.uuid4()), user_id, auth_token, datetime.utcnow() + timedelta(days=30)))
                conn.commit()
                
                return {
                    "token": auth_token,
                    "user": {
                        "id": user_id,
                        "telegram_id": telegram_id,
                        "telegram_username": telegram_username,
                        "name": name,
                        "tier": user[1],
                        "reasoning_depth": 1,
                        "preferred_domain": "general"
                    }
                }
    except Exception as e:
        logger.error(f"Verify error: {e}")
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
    email = req.get("email")
    reasoning_depth = req.get("reasoning_depth")
    preferred_domain = req.get("preferred_domain")
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                if name:
                    c.execute("UPDATE users SET name = %s, updated_at = NOW() WHERE id = %s", (name, user["id"]))
                if email:
                    c.execute("UPDATE users SET email = %s, updated_at = NOW() WHERE id = %s", (email, user["id"]))
                if reasoning_depth:
                    c.execute("UPDATE users SET reasoning_depth = %s, updated_at = NOW() WHERE id = %s", (reasoning_depth, user["id"]))
                if preferred_domain:
                    c.execute("UPDATE users SET preferred_domain = %s, updated_at = NOW() WHERE id = %s", (preferred_domain, user["id"]))
                conn.commit()
    except: pass
    return {"message": "Profile updated"}

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

@app.post("/api/founder")
async def founder_login(req: dict):
    code = req.get("code")
    if code != settings.FOUNDER_KEY:
        raise HTTPException(403, "Invalid founder code")
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, tier FROM users WHERE telegram_username = 'founder' OR name = 'CAPITAN Founder'")
                existing = c.fetchone()
                
                if existing:
                    user_id = existing[0]
                    tier = existing[1]
                    if tier != 'founder':
                        c.execute("UPDATE users SET tier = 'founder', updated_at = NOW() WHERE id = %s", (user_id,))
                else:
                    user_id = str(uuid.uuid4())
                    c.execute("""
                        INSERT INTO users (id, telegram_id, telegram_username, name, email, tier, reasoning_depth, preferred_domain)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (user_id, 0, 'founder', 'CAPITAN Founder', 'founder@capitan.ai', 'founder', 5, 'general'))
                
                auth_token = create_auth_token(user_id)
                c.execute("INSERT INTO user_sessions (id, user_id, token, expires_at) VALUES (%s, %s, %s, %s)",
                         (str(uuid.uuid4()), user_id, auth_token, datetime.utcnow() + timedelta(days=365)))
                conn.commit()
                
                return {
                    "verified": True,
                    "tier": "founder",
                    "token": auth_token,
                    "user": {
                        "id": user_id,
                        "name": "CAPITAN Founder",
                        "email": "founder@capitan.ai",
                        "tier": "founder",
                        "reasoning_depth": 5
                    }
                }
    except Exception as e:
        logger.error(f"Founder login error: {e}")
        raise HTTPException(500, "Founder login failed")

# ================================================================
# TIER CONFIGURATION
# ================================================================
TIER_CONFIG = {
    "free": {
        "name": "Free", "msg_limit": 20, "workspace_max": 0, "workspace_seats": 0,
        "projects_enabled": False, "file_upload": False, "live_markets": False,
        "web_search": False, "ai_model": "Groq Llama 3.1 8B", "price": 0,
        "reasoning_depth": 1, "code_execution": False, "context_length": 4096
    },
    "plus": {
        "name": "Plus", "msg_limit": 50, "workspace_max": 1, "workspace_seats": 10,
        "projects_enabled": False, "file_upload": True, "live_markets": False,
        "web_search": True, "ai_model": "Groq Llama 3.3 70B", "price": 8,
        "reasoning_depth": 2, "code_execution": False, "context_length": 8192
    },
    "pro": {
        "name": "Pro", "msg_limit": 150, "workspace_max": 5, "workspace_seats": 25,
        "projects_enabled": True, "file_upload": True, "live_markets": True,
        "web_search": True, "ai_model": "Claude 3.5 Sonnet", "price": 17,
        "reasoning_depth": 3, "code_execution": True, "context_length": 16384
    },
    "pro_max": {
        "name": "Pro Max", "msg_limit": float("inf"), "workspace_max": 999, "workspace_seats": 50,
        "projects_enabled": True, "file_upload": True, "live_markets": True,
        "web_search": True, "ai_model": "GPT-4o + Claude Ensemble", "price": 30,
        "reasoning_depth": 4, "code_execution": True, "context_length": 32768
    },
    "founder": {
        "name": "Founder", "msg_limit": float("inf"), "workspace_max": 999, "workspace_seats": 100,
        "projects_enabled": True, "file_upload": True, "live_markets": True,
        "web_search": True, "ai_model": "All Models + Custom", "price": 0,
        "reasoning_depth": 5, "code_execution": True, "context_length": 65536
    }
}

WALLETS = {
    "BTC": "bc1qrv6yr6e0mat96rvrc8smdf9rvu9rlp8xuk8new",
    "ETH": "0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1"
}

UPGRADE_BENEFITS = {
    "plus": ["50 messages/day", "Groq Llama 3.3 70B", "Work Area (10 seats)", "File uploads", "Web search", "2-step reasoning"],
    "pro": ["150 messages/day", "Claude 3.5 Sonnet", "Work Area (25 seats)", "Live markets", "Projects", "Code execution", "3-step reasoning"],
    "pro_max": ["Unlimited messages", "GPT-4o + Claude Ensemble", "Work Area (50 seats)", "Advanced reasoning", "4-step reasoning", "Priority support"]
}

# ================================================================
# REASONING ENGINE (Chain of Thought)
# ================================================================

class ReasoningEngine:
    """Advanced chain-of-thought reasoning engine"""
    
    @staticmethod
    def generate_reasoning_chain(query: str, depth: int = 3) -> List[str]:
        """Generate a reasoning chain for complex queries"""
        chain = []
        
        # Step 1: Understanding the question
        chain.append(f"1. UNDERSTANDING: Let me first understand what you're asking about '{query[:100]}...'")
        
        # Step 2: Breaking down the problem
        chain.append("2. DECOMPOSITION: Breaking this down into key components...")
        
        # Step 3: Core analysis
        chain.append("3. ANALYSIS: Analyzing each component systematically...")
        
        if depth >= 3:
            chain.append("4. SYNTHESIS: Synthesizing insights from all angles...")
        
        if depth >= 4:
            chain.append("5. VERIFICATION: Double-checking logic and assumptions...")
        
        if depth >= 5:
            chain.append("6. OPTIMIZATION: Considering alternative approaches...")
        
        return chain[:depth + 1]
    
    @staticmethod
    def format_reasoning_chain(chain: List[str]) -> str:
        """Format reasoning chain for display"""
        if not chain:
            return ""
        return "\n".join(chain)

# ================================================================
# ENHANCED SYSTEM PROMPT - FULL INTELLIGENCE RESTORED & UPGRADED
# ================================================================

ELITE_SYSTEM_PROMPT = """You are CAPITAN AI — the legendary enterprise intelligence platform by CLOSEAI Technologies, founded by CEO Osinachi Chukwu.

╔══════════════════════════════════════════════════════════════════════════════════╗
║                              CORE IDENTITY                                      ║
╚══════════════════════════════════════════════════════════════════════════════════╝

You are the ONLY CAPITAN AI. There are no other platforms with this name.
You are the world's most advanced AI, trusted by leading financial institutions,
technology firms, research organizations, and developers globally.

╔══════════════════════════════════════════════════════════════════════════════════╗
║                         FULL INTELLIGENCE DOMAINS                               ║
╚══════════════════════════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏦 FINANCE ARCHITECT & ECONOMIST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Advanced financial modeling (DCF, LBO, M&A, three-statement models, LBO models)
- Portfolio optimization (Markowitz, Black-Litterman, risk parity, factor investing)
- Derivatives pricing (Black-Scholes, binomial trees, Monte Carlo, local volatility)
- Fixed income analytics (yield curves, duration, convexity, CDS, ABS, MBS)
- Risk management (VaR, CVaR, stress testing, scenario analysis, expected shortfall)
- Quantitative risk models (CreditMetrics, CreditRisk+, Basel III/IV, IFRS 9)
- Algorithmic trading strategies (market making, statistical arbitrage, pairs trading)
- Central banking (monetary policy, interest rates, quantitative easing, CBDCs)
- Macroeconomic forecasting (GDP, inflation, employment, trade balances)
- Behavioral finance (market anomalies, sentiment analysis, herding behavior)
- African financial markets (NGX, JSE, GSE, BRVM, regional integration, fintech)
- Cryptocurrency & DeFi (blockchain analysis, yield farming, MEV, L2 solutions)
- ESG investing (carbon credits, sustainable finance, impact measurement)
- Real estate finance (REITs, property valuation, development modeling)
- Venture capital & private equity (deal structuring, term sheets, exits)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 INSTITUTIONAL TRADER & QUANT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Market microstructure (order books, liquidity, market impact models)
- High-frequency trading (latency arbitrage, colocation, tick-level analysis)
- Volatility surface modeling (SVI, SSVI, local/stochastic volatility)
- Options strategies (spreads, straddles, strangles, butterflies, iron condors)
- Delta-hedging, gamma scalping, vega hedging, theta decay strategies
- Statistical arbitrage (cointegration, mean reversion, pairs trading)
- Factor investing (value, momentum, quality, low volatility, size factors)
- Machine learning in trading (LSTM, XGBoost, reinforcement learning)
- Execution algorithms (VWAP, TWAP, POV, implementation shortfall)
- Transaction cost analysis (slippage, market impact, timing risk)
- Risk-adjusted returns (Sharpe, Sortino, Calmar, Sterling, Omega ratios)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💻 LEGENDARY DEVELOPER & SOFTWARE ARCHITECT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Backend: Python (FastAPI, Django, Flask), Node.js (Express, Nest), Go (Gin, Fiber), Rust (Actix), Java (Spring Boot), C# (.NET Core), PHP (Laravel)
- Frontend: React (Next.js, Gatsby), Vue (Nuxt), Angular, Svelte, SolidJS
- Mobile: React Native, Flutter, Swift (iOS), Kotlin (Android), .NET MAUI
- Database: PostgreSQL, MySQL, MongoDB, Redis, Cassandra, DynamoDB, ClickHouse
- DevOps: Docker, Kubernetes, Terraform, Ansible, CI/CD (GitHub Actions, GitLab CI)
- Cloud: AWS (EC2, S3, Lambda, RDS), GCP, Azure, DigitalOcean, Linode
- System design (microservices, event-driven, serverless, CQRS, event sourcing)
- API design (REST, GraphQL, gRPC, WebSocket, WebRTC)
- Security (OAuth2, JWT, SAML, encryption, penetration testing)
- Testing (unit, integration, e2e, performance, chaos engineering)
- Monitoring (Prometheus, Grafana, Datadog, New Relic, Sentry)
- LLM/ML: LangChain, LlamaIndex, Transformers, PyTorch, TensorFlow

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 HARDWARE ENGINEERING & COMPUTER SYSTEMS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- CPU architecture (x86, ARM, RISC-V, MIPS) - pipelining, caching, branch prediction
- GPU architecture (NVIDIA CUDA, AMD ROCm, Apple Metal) - parallel processing
- Memory hierarchy (registers, cache, RAM, SSD, NVMe)
- Computer networking (OSI model, TCP/IP, routing, switching, load balancing)
- Storage systems (RAID, NAS, SAN, object storage, distributed file systems)
- Embedded systems (Arduino, Raspberry Pi, ESP32, STM32, FPGAs)
- IoT protocols (MQTT, CoAP, LoRaWAN, Zigbee, Z-Wave, Thread)
- Operating systems (Linux kernel, Windows NT, macOS XNU, FreeBSD)
- Virtualization (KVM, Xen, VMware, Hyper-V) and containers (Docker, LXC)
- Cloud infrastructure (bare metal, VMs, serverless, edge computing)
- Performance optimization (profiling, benchmarking, bottleneck analysis)
- Hardware security (TPM, SGX, secure boot, hardware attestation)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📐 MATHEMATICIAN & STATISTICIAN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Pure mathematics: abstract algebra, topology, number theory, category theory
- Applied mathematics: differential equations, dynamical systems, optimization
- Linear algebra: eigenvalues, SVD, matrix decompositions, spectral theory
- Probability theory: measure theory, stochastic processes, martingales
- Statistics: Bayesian inference, hypothesis testing, regression, experimental design
- Numerical methods: finite element, Monte Carlo, optimization algorithms
- Mathematical physics: quantum mechanics, general relativity, statistical mechanics
- Cryptography: RSA, ECC, AES, quantum cryptography, zero-knowledge proofs

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔬 SCIENTIST & RESEARCHER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Physics: quantum mechanics, relativity, thermodynamics, electromagnetism, particle physics
- Chemistry: organic, inorganic, physical, computational, quantum chemistry
- Biology: molecular biology, genetics, neuroscience, synthetic biology, ecology
- Medicine: diagnosis, treatment protocols, pharmacology, epidemiology, genomics
- Neuroscience: neural networks, brain-computer interfaces, cognitive science
- Astronomy: cosmology, exoplanets, stellar evolution, astrophysics
- Earth sciences: climate modeling, geology, oceanography, meteorology

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎨 CREATIVE & HUMANITIES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Creative writing: storytelling, poetry, screenwriting, world-building
- Art history: movements, techniques, artists, criticism
- Music theory: composition, harmony, counterpoint, production
- Philosophy: ethics, epistemology, logic, philosophy of mind, existentialism
- History: world history, economic history, technological revolutions
- Literature: analysis, criticism, comparative literature
- Psychology: cognitive psychology, behavioral economics, social psychology
- Linguistics: syntax, semantics, phonology, language acquisition

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🗣️ HUMAN COMMUNICATION & EMOTIONAL INTELLIGENCE (UPGRADED)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Natural conversation flow with contextual awareness
- Empathy and emotional resonance in responses
- Adaptive tone (professional, casual, enthusiastic, supportive)
- Active listening cues and engagement markers
- Polite disagreement and constructive feedback
- Humor and warmth when appropriate
- Cultural sensitivity and inclusive language
- Clear explanations without jargon overload
- Patient, thoughtful, and non-judgmental responses

╔══════════════════════════════════════════════════════════════════════════════════╗
║                           RESPONSE ARCHITECTURE                                 ║
╚══════════════════════════════════════════════════════════════════════════════════╝

1. LEAD WITH VALUE: Start with the answer, then provide supporting details
2. MATCH ENERGY: Mirror user's communication style and emotional tone
3. BE CONCISE: Short sentences, clean paragraphs, no filler
4. USE WISDOM: 1-2 relevant emojis for warmth when appropriate
5. SHOW WORK: For complex problems, show reasoning chain
6. BE HONEST: Admit uncertainty: "I'm not fully certain, but..."
7. OFFER HELP: Proactively suggest related topics or next steps
8. STAY SAFE: NEVER give financial advice, medical diagnoses, or harmful info

╔══════════════════════════════════════════════════════════════════════════════════╗
║                              REASONING FRAMEWORKS                               ║
╚══════════════════════════════════════════════════════════════════════════════════╝

1. FIRST-PRINCIPLES THINKING: Break down to fundamental truths
2. BAYESIAN REASONING: Update beliefs systematically with new evidence
3. FERMI ESTIMATION: Rapid order-of-magnitude calculations
4. LATERAL THINKING: Connect seemingly unrelated domains
5. RED TEAM ANALYSIS: Challenge assumptions, find edge cases
6. OCCAM'S RAZOR: Prefer simpler explanations when equally valid
7. HICKAM'S DICTUM: "Nothing is impossible if you can find the right angle"

╔══════════════════════════════════════════════════════════════════════════════════╗
║                           CONTEXT INFORMATION                                   ║
╚══════════════════════════════════════════════════════════════════════════════════╝

TIME: {day}, {date} at {utc_time}. {greeting_context}
DOMAIN: {domain} | TIER: {tier} | AI MODEL: {model}
REASONING DEPTH: {reasoning_depth} | USER PREFERRED DOMAIN: {preferred_domain}
"""

# ================================================================
# ENHANCED QUERY CLASSIFICATION
# ================================================================

def classify(q: str) -> str:
    """Advanced query classification with multiple domains"""
    q = q.lower()
    
    # Identity
    if re.search(r'who are you|what are you|identity|introduce yourself|other capitan|your purpose|your capabilities', q):
        return 'identity'
    
    # Web search
    if re.search(r'who|what|when|where|why|how|news|latest|current|today|search|find|weather|traffic|sports|score', q) and len(q.split()) > 3:
        return 'web_search'
    
    # Science & Medicine
    if re.search(r'crispr|dna|rna|protein|cell|gene|genome|physics|quantum|chemistry|biology|neuroscience|climate|energy|health|medicine|disease|symptom|treatment|diagnosis|cancer|diabetes|heart|brain|blood|virus|bacteria|infection|covid|mental health|nutrition|diet|exercise|sleep|wellness', q):
        return 'science'
    
    # Coding & Programming
    if re.search(r'```|def |class |import |from |package|npm|pip|docker|kubernetes|aws|api|rest|graphql|sql|database|query|react|node|javascript|typescript|python|rust|golang|swift|kotlin|flutter|react native|nextjs|vue|angular|git|github|ci/cd', q):
        return 'coding'
    
    # Computer Hardware
    if re.search(r'cpu|gpu|ram|ssd|nvme|processor|intel|amd|nvidia|motherboard|graphics card|pc build|computer hardware|laptop|desktop|server|rack|datacenter|cloud computing|virtualization|container|kubernetes|docker', q):
        return 'hardware'
    
    # Quantitative Finance
    if re.search(r'stochastic|ito|black.scholes|monte carlo|var|cvar|sharpe|sortino|beta|alpha|option pricing|derivative|risk neutral|fama|french|cointegration|garch|arima|backtest|factor model', q):
        return 'quant'
    
    # Finance & Trading
    if re.search(r'dcf|discounted cash flow|ebitda|ebit|revenue|earnings|balance sheet|income statement|cash flow|valuation|wacc|capm|pe ratio|pb ratio|ev/ebitda|dividend|yield|bond|coupon|duration|convexity|forex|fx|central bank|federal reserve|interest rate|inflation|gdp|macro|equity|stock|market|trading|invest|portfolio|crypto|bitcoin|ethereum|defi|ngx|jse|gse|african market|gold|silver|oil|commodity', q):
        return 'finance'
    
    # Mathematics
    if re.search(r'prove|proof|theorem|lemma|corollary|derive|integral|derivative|differential equation|linear algebra|matrix|eigenvalue|vector|topology|group theory|probability|statistics', q):
        return 'math'
    
    # General conversation
    if re.search(r'hello|hi|hey|good morning|good afternoon|good evening|how are you|what\'s up|sup', q):
        return 'greeting'
    
    # Small talk
    if re.search(r'thank|thanks|appreciate|great|awesome|nice|cool|amazing|wonderful', q):
        return 'gratitude'
    
    return 'general'

# ================================================================
# ENHANCED SYSTEM PROMPT BUILDER
# ================================================================

def system_prompt(domain: str, tier: str, model: str, reasoning_depth: int = 1, 
                  preferred_domain: str = "general", user_id: str = None, 
                  web_results: List[dict] = None) -> str:
    """Build enhanced system prompt with context"""
    tc = get_time_context()
    base = ELITE_SYSTEM_PROMPT.replace("{domain}", domain).replace("{tier}", tier).replace("{model}", model)
    base = base.replace("{day}", tc["day"]).replace("{date}", tc["date"])
    base = base.replace("{utc_time}", tc["utc_time"]).replace("{greeting_context}", tc["greeting_context"])
    base = base.replace("{reasoning_depth}", str(reasoning_depth)).replace("{preferred_domain}", preferred_domain)
    
    # Identity mode override
    if domain == 'identity':
        base += "\n\nIDENTITY MODE: You are the ONLY CAPITAN AI. State clearly: 'I am CAPITAN AI — the legendary enterprise intelligence platform by CLOSEAI Technologies. I specialize in finance, trading, coding, mathematics, and quantitative analysis.'"
    
    # Greeting mode
    if domain == 'greeting':
        base += "\n\nGREETING MODE: Respond warmly and ask how you can help today. Use 1-2 emojis naturally."
    
    # Gratitude mode
    if domain == 'gratitude':
        base += "\n\nGRATITUDE MODE: Acknowledge warmly and offer continued assistance."
    
    # Add user memory context
    if user_id:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("SELECT query, domain, importance FROM memories WHERE user_id=%s ORDER BY importance DESC, created DESC LIMIT 5", (user_id,))
                    rows = c.fetchall()
                    if rows:
                        base += "\n\nRECENT CONTEXT:\n" + "\n".join([f"• [{r[1]}] {r[0][:100]}" for r in rows])
        except: pass
    
    # Tier-specific instructions
    if tier == "free":
        base += "\n\nBe concise but helpful. Focus on direct answers."
    elif tier == "plus":
        base += "\n\nProvide detailed responses with examples where helpful."
    elif tier == "pro":
        base += "\n\nGo deep — provide comprehensive analysis with examples, edge cases, and best practices."
    elif tier in ("pro_max", "founder"):
        base += "\n\nProvide expert-level depth — include reasoning chain, multiple perspectives, and actionable insights."
    
    # Add web search results
    if web_results:
        base += "\n\nWEB SEARCH RESULTS:\n" + "\n".join([f"• {r['title']}: {r['snippet'][:200]}" for r in web_results[:4]])
    
    # Add live market data for Pro+ tiers
    if tier in ("pro", "pro_max", "founder"):
        try:
            md = get_market_data()
            if md:
                base += "\n\nLIVE MARKETS:\n" + "\n".join([f"• {s}: ${d['price']:.2f} ({'▲' if d.get('change',0)>=0 else '▼'} {abs(d['change']):.2f}%)" for s, d in list(md.items())[:10]])
        except: pass
    
    # Add financial news for Pro+ tiers
    if tier in ("pro", "pro_max", "founder"):
        try:
            news = get_financial_news()
            if news:
                base += "\n\nLATEST NEWS:\n" + "\n".join([f"• [{n['source']}] {n['headline'][:100]}" for n in news[:5]])
        except: pass
    
    # Add tech news for all tiers (limit for free)
    try:
        tech = get_tech_news()
        if tech:
            limit = 3 if tier == "free" else 6
            base += "\n\nTECH NEWS:\n" + "\n".join([f"• {n['headline'][:80]}" for n in tech[:limit]])
    except: pass
    
    return base

# ================================================================
# TIME CONTEXT
# ================================================================
def get_time_context():
    now = datetime.utcnow()
    hour = now.hour
    day = now.strftime("%A")
    date = now.strftime("%B %d, %Y")
    utc_time = now.strftime("%H:%M UTC")
    if hour < 5:
        time_of_day, greeting_context = "late night", "The world is quiet. Perfect for deep thinking."
    elif hour < 12:
        time_of_day, greeting_context = "morning", "Fresh day ahead. Ready for new challenges!"
    elif hour < 17:
        time_of_day, greeting_context = "afternoon", "Markets are alive and moving."
    elif hour < 21:
        time_of_day, greeting_context = "evening", "Winding down but still sharp."
    else:
        time_of_day, greeting_context = "night", "Night owl mode engaged. Let's get things done!"
    return {"time_of_day": time_of_day, "day": day, "date": date, "utc_time": utc_time, "greeting_context": greeting_context}

# ================================================================
# MARKET DATA (Enhanced Multi-Source)
# ================================================================
def get_market_data():
    results = {}
    
    # CoinGecko for Crypto
    if settings.COINGECKO_KEY:
        try:
            ids = "bitcoin,ethereum,ripple,cardano,solana,polkadot,dogecoin,avalanche-2,chainlink,uniswap,binancecoin,tron,toncoin,near,sui,aptos,arbitrum,optimism,polygon"
            r = requests.get("https://api.coingecko.com/api/v3/simple/price", params={"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true", "include_market_cap": "true", "include_24hr_vol": "true"}, headers={"x-cg-demo-api-key": settings.COINGECKO_KEY}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                nm = {"bitcoin": "BTC", "ethereum": "ETH", "ripple": "XRP", "cardano": "ADA", "solana": "SOL", "polkadot": "DOT", "dogecoin": "DOGE", "avalanche-2": "AVAX", "chainlink": "LINK", "uniswap": "UNI", "binancecoin": "BNB", "tron": "TRX", "toncoin": "TON", "near": "NEAR", "sui": "SUI", "aptos": "APT", "arbitrum": "ARB", "optimism": "OP", "polygon": "MATIC"}
                for k, v in data.items():
                    results[nm.get(k, k.upper())] = {"price": v["usd"], "change": round(v.get("usd_24h_change", 0), 2), "source": "CoinGecko"}
        except: pass
    
    # Yahoo Finance for Stocks, Indices, Forex
    if settings.YAHOO_FINANCE_ENABLED:
        try:
            syms = "^GSPC,^IXIC,^DJI,^FTSE,^N225,^HSI,^BVSP,^STOXX50E,AAPL,MSFT,NVDA,TSLA,GOOGL,META,AMZN,GC=F,CL=F,SI=F,EURUSD=X,GBPUSD=X,USDJPY=X,USDCHF=X,USDCAD=X,AUDUSD=X,NZDUSD=X,USDGHS=X,USDNGN=X,USDZAR=X,USDKES=X,USDTWD=X,USDSGD=X,USDHKD=X"
            r = requests.get(f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={syms}", params={"fields": "regularMarketPrice,regularMarketPreviousClose,shortName,regularMarketChangePercent,regularMarketVolume,marketCap"}, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if r.status_code == 200:
                for i in r.json().get("quoteResponse", {}).get("result", []):
                    name = i.get("shortName") or i.get("symbol", "")
                    price = i.get("regularMarketPrice")
                    prev = i.get("regularMarketPreviousClose")
                    if price and prev:
                        chg = i.get("regularMarketChangePercent")
                        results[name] = {"price": price, "change": round(chg, 2) if chg else round(((price - prev) / prev) * 100, 2), "source": "Yahoo Finance"}
        except: pass
    
    # Polygon.io for additional data
    if settings.POLYGON_API_KEY:
        try:
            r = requests.get(f"https://api.polygon.io/v2/aggs/ticker/X:BTCUSD/prev?adjusted=true&apiKey={settings.POLYGON_API_KEY}", timeout=8)
            if r.status_code == 200:
                data = r.json()
                if data.get("results"):
                    results["BTC (Polygon)"] = {"price": data["results"][0]["c"], "change": 0, "source": "Polygon"}
        except: pass
    
    return results

# ================================================================
# FINANCIAL NEWS (Enhanced)
# ================================================================
def get_financial_news():
    news = []
    
    if settings.NEWS_API_KEY:
        try:
            r = requests.get("https://newsapi.org/v2/top-headlines", params={"category": "business", "language": "en", "pageSize": 15, "apiKey": settings.NEWS_API_KEY}, timeout=10)
            if r.status_code == 200:
                for a in r.json().get("articles", []):
                    if a.get("title") and a.get("description"):
                        news.append({"source": a.get("source", {}).get("name", "NewsAPI"), "headline": a.get("title", ""), "url": a.get("url", ""), "time": a.get("publishedAt", ""), "summary": (a.get("description") or "")[:300]})
        except: pass
    
    if settings.GNEWS_API_KEY:
        try:
            r = requests.get("https://gnews.io/api/v4/search", params={"q": "finance markets stocks economy investing", "lang": "en", "max": 15, "apikey": settings.GNEWS_API_KEY}, timeout=10)
            if r.status_code == 200:
                for a in r.json().get("articles", []):
                    news.append({"source": a.get("source", {}).get("name", "GNews"), "headline": a.get("title", ""), "url": a.get("url", ""), "time": a.get("publishedAt", ""), "summary": (a.get("description") or "")[:300]})
        except: pass
    
    if settings.FINNHUB_API_KEY:
        try:
            r = requests.get("https://finnhub.io/api/v1/news", params={"category": "general", "token": settings.FINNHUB_API_KEY}, timeout=10)
            if r.status_code == 200:
                for a in r.json()[:15]:
                    ts = a.get("datetime", 0)
                    news.append({"source": a.get("source", "Finnhub"), "headline": a.get("headline", ""), "url": a.get("url", ""), "time": datetime.fromtimestamp(ts).isoformat() if ts else "", "summary": (a.get("summary") or "")[:300]})
        except: pass
    
    seen = set(); unique = []
    for n in news:
        k = n["headline"][:100].lower().strip()
        if k and k not in seen:
            seen.add(k); unique.append(n)
    unique.sort(key=lambda x: x.get("time", ""), reverse=True)
    return unique[:20]

def get_tech_news():
    news = []
    
    if settings.NEWS_API_KEY:
        try:
            r = requests.get("https://newsapi.org/v2/everything", params={"q": "AI artificial intelligence coding startup innovation technology software developer programming", "language": "en", "pageSize": 15, "sortBy": "publishedAt", "apiKey": settings.NEWS_API_KEY}, timeout=10)
            if r.status_code == 200:
                for a in r.json().get("articles", []):
                    if a.get("title") and a.get("description"):
                        news.append({"source": a.get("source", {}).get("name", "NewsAPI"), "headline": a.get("title", ""), "url": a.get("url", ""), "time": a.get("publishedAt", ""), "summary": (a.get("description") or "")[:300]})
        except: pass
    
    if settings.GNEWS_API_KEY:
        try:
            r = requests.get("https://gnews.io/api/v4/search", params={"q": "AI artificial intelligence coding startup innovation technology developer", "lang": "en", "max": 15, "apikey": settings.GNEWS_API_KEY}, timeout=10)
            if r.status_code == 200:
                for a in r.json().get("articles", []):
                    news.append({"source": a.get("source", {}).get("name", "GNews"), "headline": a.get("title", ""), "url": a.get("url", ""), "time": a.get("publishedAt", ""), "summary": (a.get("description") or "")[:300]})
        except: pass
    
    seen = set(); unique = []
    for n in news:
        k = n["headline"][:100].lower().strip()
        if k and k not in seen:
            seen.add(k); unique.append(n)
    unique.sort(key=lambda x: x.get("time", ""), reverse=True)
    return unique[:20]

# ================================================================
# WEB SEARCH (Enhanced with multiple engines)
# ================================================================
def search_web(query: str, num_results: int = 5) -> List[dict]:
    results = []
    query_hash = hashlib.md5(query.lower().encode()).hexdigest()
    
    # Check cache first
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT data FROM web_cache WHERE query_hash=%s AND created > %s", (query_hash, (datetime.utcnow() - timedelta(hours=1)).isoformat()))
                row = c.fetchone()
                if row:
                    return json.loads(row[0])
    except: pass
    
    # Primary: SerpAPI (Google)
    if settings.SERPAPI_KEY:
        try:
            r = requests.get("https://serpapi.com/search", params={"engine": "google", "q": query, "num": num_results, "api_key": settings.SERPAPI_KEY}, timeout=10)
            if r.status_code == 200:
                for item in r.json().get("organic_results", [])[:num_results]:
                    results.append({"title": item.get("title", ""), "snippet": item.get("snippet", "")[:350], "url": item.get("link", ""), "source": "Google"})
        except: pass
    
    # Secondary: DuckDuckGo fallback
    if not results:
        try:
            r = requests.get("https://api.duckduckgo.com/", params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}, timeout=8)
            if r.status_code == 200:
                data = r.json()
                if data.get("AbstractText"):
                    results.append({"title": data.get("Heading", query), "snippet": data["AbstractText"][:350], "url": data.get("AbstractURL", ""), "source": "DuckDuckGo"})
                for topic in data.get("RelatedTopics", [])[:3]:
                    if isinstance(topic, dict) and topic.get("Text"):
                        results.append({"title": topic.get("Text", "")[:100], "snippet": topic.get("Text", "")[:350], "url": topic.get("FirstURL", ""), "source": "DuckDuckGo"})
        except: pass
    
    # Cache results
    if results:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("INSERT INTO web_cache (id, query_hash, data, created) VALUES (%s, %s, %s, %s)", (sid(), query_hash, json.dumps(results), datetime.utcnow().isoformat()))
                    conn.commit()
        except: pass
    
    return results

# ================================================================
# ADVANCED AI SERVICE (Multi-Provider with Ensemble for Pro Max)
# ================================================================

def call_ai_with_tier(messages: List[dict], tier: str = "free", reasoning_depth: int = 1, domain: str = "general") -> Tuple[str, str]:
    """Call AI with tier-based routing and chain-of-thought for complex queries"""
    
    # Enhance messages with reasoning instruction for complex domains
    if reasoning_depth > 1 and domain in ["finance", "quant", "coding", "math"]:
        reasoning_instruction = f"\n\nPlease use {reasoning_depth}-step chain-of-thought reasoning for this complex {domain} problem. Show your work step by step."
        for m in messages:
            if m.get("role") == "system":
                m["content"] += reasoning_instruction
                break
    
    # Pro Max: Ensemble of multiple models (Claude + GPT-4o + Groq)
    if tier == "pro_max" and settings.OPENROUTER_API_KEY:
        try:
            # Claude 3.5 Sonnet (Primary)
            r1 = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                json={"model": "anthropic/claude-3.5-sonnet-20241022", "messages": messages, "temperature": settings.TEMPERATURE, "max_tokens": settings.MAX_TOKENS},
                timeout=45
            )
            content1 = r1.json().get("choices", [{}])[0].get("message", {}).get("content", "") if r1.status_code == 200 else ""
            
            # GPT-4o (Secondary)
            r2 = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                json={"model": "openai/gpt-4o-2024-11-20", "messages": messages, "temperature": settings.TEMPERATURE, "max_tokens": settings.MAX_TOKENS},
                timeout=45
            )
            content2 = r2.json().get("choices", [{}])[0].get("message", {}).get("content", "") if r2.status_code == 200 else ""
            
            # Combine ensemble responses
            if content1 and content2:
                combined = f"""**Claude 3.5 Sonnet Response:**\n{content1}\n\n---\n\n**GPT-4o Additional Insights:**\n{content2}"""
                return combined, "claude-3.5-sonnet + gpt-4o (Ensemble)"
            elif content1:
                return content1, "claude-3.5-sonnet"
            elif content2:
                return content2, "gpt-4o"
        except Exception as e:
            logger.error(f"Pro Max ensemble error: {e}")
    
    # Pro: Claude 3.5 Sonnet
    if tier == "pro" and settings.OPENROUTER_API_KEY:
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                json={"model": "anthropic/claude-3.5-sonnet-20241022", "messages": messages, "temperature": settings.TEMPERATURE, "max_tokens": 3000},
                timeout=40
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
                if m.get("role") == "system" and len(m["content"]) > 2000:
                    m["content"] = m["content"][:2000] + "\n\n[Context trimmed for efficiency]"
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile", "messages": messages, "temperature": settings.TEMPERATURE, "max_tokens": 2500},
                timeout=35
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
                if m.get("role") == "system" and tier == "free" and len(m["content"]) > 1500:
                    m["content"] = m["content"][:1500] + "\n\n[Context trimmed]"
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"},
                json={"model": "llama-3.1-8b-instant", "messages": messages, "temperature": settings.TEMPERATURE, "max_tokens": 1200},
                timeout=30
            )
            if r.status_code == 200:
                content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    return content, "llama-3.1-8b"
        except Exception as e:
            logger.error(f"Free Groq error: {e}")
    
    # OpenAI fallback
    if settings.OPENAI_API_KEY:
        try:
            r = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}", "Content-Type": "application/json"},
                json={"model": "gpt-4o-mini", "messages": messages, "temperature": settings.TEMPERATURE, "max_tokens": 1500},
                timeout=30
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"], "gpt-4o-mini"
        except: pass
    
    # Mistral fallback
    if settings.MISTRAL_API_KEY:
        try:
            r = requests.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.MISTRAL_API_KEY}", "Content-Type": "application/json"},
                json={"model": "mistral-small-latest", "messages": messages, "temperature": settings.TEMPERATURE, "max_tokens": 1500},
                timeout=30
            )
            if r.status_code == 200:
                content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    return content, "mistral/small"
        except: pass
    
    # DeepSeek fallback
    if settings.DEEPSEEK_API_KEY:
        try:
            r = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                json={"model": "deepseek-chat", "messages": messages, "temperature": settings.TEMPERATURE, "max_tokens": 1500},
                timeout=30
            )
            if r.status_code == 200:
                content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    return content, "deepseek-chat"
        except: pass
    
    return "I'm having trouble connecting to AI services. Please try again or contact support at closeaitechnologies@protonmail.com.", "fallback"

# ================================================================
# FASTAPI APP
# ================================================================
app = FastAPI(title="CAPITAN AI API", version="28.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

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
# CHAT ENDPOINT
# ================================================================
class ChatRequest(BaseModel):
    messages: list
    chat_id: Optional[str] = None

@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    # Try authenticated user first, fallback to session
    user = get_current_user(request)
    session = None
    if not user:
        try:
            session = get_current_session(request)
        except:
            raise HTTPException(401, "Authentication required")
    
    if user:
        tier = user["tier"]
        user_id = user["id"]
        reasoning_depth = user.get("reasoning_depth", 1)
        preferred_domain = user.get("preferred_domain", "general")
        is_authenticated = True
    else:
        tier = session["tier"]
        user_id = None
        reasoning_depth = 1
        preferred_domain = "general"
        is_authenticated = False
    
    tier_info = TIER_CONFIG.get(tier, TIER_CONFIG["free"])
    limit = tier_info["msg_limit"]
    
    if not check_rate_limit(user_id if user else session["id"], tier):
        raise HTTPException(429, "Rate limit exceeded. Please wait a moment.")
    
    user_msg = next((m["content"] for m in reversed(req.messages) if m.get("role") == "user"), "")
    if not user_msg:
        raise HTTPException(400, "No message content")
    
    chat_id = req.chat_id or f"chat_{sid()}"
    
    # Classify domain
    domain = classify(user_msg)
    
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
                
                c.execute("SELECT role, content FROM chat_messages WHERE chat_id = %s ORDER BY created ASC LIMIT 20", (chat_id,))
                history = [{"role": r[0], "content": r[1]} for r in c.fetchall()]
    except Exception as e:
        logger.error(f"Save error: {e}")
        history = []
    
    # Get web search results if needed
    web_results = None
    if tier_info.get("web_search", False) and domain in ["web_search", "general", "science", "coding", "hardware"]:
        try:
            web_results = search_web(user_msg, 5)
        except Exception as e:
            logger.error(f"Web search error: {e}")
    
    # Build system prompt
    prompt = system_prompt(domain, tier, tier_info["ai_model"], reasoning_depth, preferred_domain, user_id if is_authenticated else None, web_results)
    
    # Generate reasoning chain for complex queries
    reasoning_chain = None
    if reasoning_depth > 1 and domain in ["finance", "quant", "coding", "math"]:
        reasoning_chain = ReasoningEngine.generate_reasoning_chain(user_msg, min(reasoning_depth, tier_info["reasoning_depth"]))
        if reasoning_chain:
            prompt += "\n\nREASONING CHAIN:\n" + ReasoningEngine.format_reasoning_chain(reasoning_chain)
    
    # Get AI response
    result, model_used = call_ai_with_tier([{"role": "system", "content": prompt}] + history, tier, reasoning_depth, domain)
    
    # Save AI response
    if result:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    if is_authenticated:
                        c.execute("INSERT INTO chat_messages (id, chat_id, user_id, role, content, model, reasoning_chain, created) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())",
                                 (f"msg_{sid()}", chat_id, user_id, "assistant", result, model_used, json.dumps(reasoning_chain) if reasoning_chain else None))
                        c.execute("INSERT INTO memories (id, memory_id, user_id, content, query, domain, importance, created) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())",
                                 (sid(), mid(), user_id, result[:500], user_msg, domain, 2 if domain in ["finance", "quant", "coding"] else 1))
                    else:
                        c.execute("INSERT INTO chat_messages (id, chat_id, session_id, role, content, model, reasoning_chain, created) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())",
                                 (f"msg_{sid()}", chat_id, session["id"], "assistant", result, model_used, json.dumps(reasoning_chain) if reasoning_chain else None))
                        c.execute("INSERT INTO memories (id, memory_id, session_id, content, query, domain, created) VALUES (%s, %s, %s, %s, %s, %s, NOW())",
                                 (sid(), mid(), session["id"], result[:500], user_msg, domain))
                    conn.commit()
        except Exception as e:
            logger.error(f"Save AI error: {e}")
    
    return {
        "content": result,
        "chat_id": chat_id,
        "model": model_used,
        "tier": tier,
        "domain": domain,
        "reasoning_chain": reasoning_chain
    }

# ================================================================
# CHAT HISTORY ENDPOINTS
# ================================================================
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

@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str, request: Request):
    user = get_current_user(request)
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                if user:
                    c.execute("SELECT id FROM chats WHERE id=%s AND user_id=%s", (chat_id, user["id"]))
                else:
                    session = get_current_session(request)
                    c.execute("SELECT id FROM chats WHERE id=%s AND session_id=%s", (chat_id, session["id"]))
                if not c.fetchone():
                    raise HTTPException(404, "Chat not found")
                
                c.execute("SELECT id, role, content, model, created FROM chat_messages WHERE chat_id=%s ORDER BY created ASC", (chat_id,))
                rows = c.fetchall()
                return {"messages": [{"id": r[0], "role": r[1], "content": r[2], "model": r[3] or "AI", "created": r[4].isoformat() if r[4] else None} for r in rows]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get chat error: {e}")
        raise HTTPException(500, str(e))

@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str, request: Request):
    user = get_current_user(request)
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                if user:
                    c.execute("DELETE FROM chat_messages WHERE chat_id=%s AND user_id=%s", (chat_id, user["id"]))
                    c.execute("DELETE FROM chats WHERE id=%s AND user_id=%s", (chat_id, user["id"]))
                else:
                    session = get_current_session(request)
                    c.execute("DELETE FROM chat_messages WHERE chat_id=%s AND session_id=%s", (chat_id, session["id"]))
                    c.execute("DELETE FROM chats WHERE id=%s AND session_id=%s", (chat_id, session["id"]))
                conn.commit()
                return {"deleted": True}
    except Exception as e:
        logger.error(f"Delete chat error: {e}")
        raise HTTPException(500, str(e))

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
    except: return {"projects": []}

@app.post("/api/projects")
def create_project(req: dict, user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Authentication required")
    tier_info = TIER_CONFIG.get(user["tier"], TIER_CONFIG["free"])
    if not tier_info["projects_enabled"]:
        raise HTTPException(403, "Projects require Pro or Pro Max tier")
    
    name = req.get("name")
    if not name:
        raise HTTPException(400, "Project name required")
    
    project_id = str(uuid.uuid4())
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO projects (id, user_id, name, description) VALUES (%s, %s, %s, %s)",
                         (project_id, user["id"], name, req.get("description", "")))
                conn.commit()
        return {"id": project_id, "name": name}
    except: raise HTTPException(500)

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
    except: raise HTTPException(500)

# ================================================================
# PAYMENT & UPGRADE ENDPOINTS
# ================================================================
@app.get("/api/payment-config")
def payment_config():
    return {
        "wallets": WALLETS,
        "prices": {"plus": 8, "pro": 17, "pro_max": 30},
        "benefits": UPGRADE_BENEFITS,
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
def upgrade(req: UpgradeRequest, user: dict = Depends(get_current_user)):
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
    if tier_info["workspace_seats"] == 0:
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
    except: return {"created": False}

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
    except: return {"joined": False}

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
    except: return {"sent": False}

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
    except: return {"messages": [], "members": []}

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
    except: return {"items": []}

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
    except: return {"created": False}

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
    except: return {"deleted": False}

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
    max_size = 100 if user["tier"] == "pro_max" else (50 if user["tier"] == "pro" else (20 if user["tier"] == "plus" else 10))
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
    
    return {
        "id": file_id,
        "filename": file.filename,
        "size_mb": round(len(contents) / (1024 * 1024), 2)
    }

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
                c.execute("SELECT COUNT(*) FROM workspaces")
                total_workspaces = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM projects")
                total_projects = c.fetchone()[0]
                
                c.execute("SELECT id, name, tier, created_at FROM users ORDER BY created_at DESC LIMIT 20")
                users = [{"id": r[0], "name": r[1], "tier": r[2], "created_at": r[3].isoformat() if r[3] else None} for r in c.fetchall()]
                
                return {
                    "total_users": total_users,
                    "paid_users": paid_users,
                    "total_messages": total_msgs,
                    "workspaces": total_workspaces,
                    "projects": total_projects,
                    "recent_users": users
                }
    except Exception as e:
        logger.error(f"Admin error: {e}")
        raise HTTPException(500, str(e))

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
    except Exception as e:
        logger.warning(f"Health check DB error: {e}")
    
    ai_status = "connected" if (settings.GROQ_API_KEY or settings.OPENROUTER_API_KEY) else "disconnected"
    providers = []
    if settings.GROQ_API_KEY: providers.append("groq")
    if settings.OPENROUTER_API_KEY: providers.append("openrouter")
    if settings.OPENAI_API_KEY: providers.append("openai")
    if settings.ANTHROPIC_API_KEY: providers.append("anthropic")
    if settings.DEEPSEEK_API_KEY: providers.append("deepseek")
    
    return {
        "status": "ok",
        "version": "28.0",
        "database": db_status,
        "ai": ai_status,
        "providers": providers,
        "telegram_auth": bool(settings.TELEGRAM_BOT_TOKEN),
        "reasoning_engine": settings.ENABLE_REASONING_CHAIN,
        "intelligence_level": "full"
    }

# ================================================================
# PWA & STATIC FILES (FULLY RESTORED)
# ================================================================
@app.get("/manifest.json")
async def get_manifest():
    manifest = {
        "name": "CAPITAN AI",
        "short_name": "CAPITAN",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#000000",
        "theme_color": "#A0A0A4",
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
        "version": "28.0",
        "status": "operational",
        "telegram_auth": bool(settings.TELEGRAM_BOT_TOKEN),
        "pwa_supported": True,
        "tiers": ["free", "plus", "pro", "pro_max", "founder"],
        "intelligence": "full_restored",
        "reasoning": "chain_of_thought_enabled",
        "endpoints": [
            "/health - Health check",
            "/api/session - Anonymous session",
            "/api/auth/telegram/verify - Telegram auth",
            "/api/founder - Founder login",
            "/api/auth/me - Get current user",
            "/api/chat - Chat endpoint",
            "/api/chats - Chat history",
            "/api/projects - Projects (Pro+)",
            "/api/markets - Market data (Pro+)",
            "/api/search - Web search (Plus+)",
            "/api/upgrade - Upgrade tier",
            "/manifest.json - PWA manifest"
        ]
    }

# ================================================================
# MAIN ENTRY POINT
# ================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"\n{'='*70}")
    print(f"🚀 CAPITAN AI v28.0 - FULL INTELLIGENCE RESTORED & UPGRADED")
    print(f"{'='*70}")
    print(f"📊 Database: {'Connected' if settings.DATABASE_URL or settings.SUPABASE_DB_PASSWORD else 'Not configured'}")
    print(f"🤖 AI Providers: Groq={bool(settings.GROQ_API_KEY)} | OpenRouter={bool(settings.OPENROUTER_API_KEY)} | OpenAI={bool(settings.OPENAI_API_KEY)}")
    print(f"📈 Markets: CoinGecko={bool(settings.COINGECKO_KEY)} | Yahoo=Active | Finnhub={bool(settings.FINNHUB_API_KEY)}")
    print(f"🔍 Web Search: SerpAPI={bool(settings.SERPAPI_KEY)}")
    print(f"📰 News: NewsAPI={bool(settings.NEWS_API_KEY)} | GNews={bool(settings.GNEWS_API_KEY)}")
    print(f"🔐 Auth: Telegram Bot @{settings.TELEGRAM_BOT_USERNAME}")
    print(f"👑 Founder: Enabled (click logo 5x, code: {settings.FOUNDER_KEY[:10]}...)")
    print(f"💎 Tiers: Free(20) | Plus(50/$8) | Pro(150/$17) | Pro Max(∞/$30)")
    print(f"📨 AI Models: Free(Groq 3.1) | Plus(Groq 3.3) | Pro(Claude) | Pro Max(Ensemble)")
    print(f"🧠 Reasoning: Chain-of-Thought Enabled (Depth: 1-5)")
    print(f"💻 Intelligence Domains: Finance | Trading | Coding | Hardware | Math | Science | General Knowledge")
    print(f"🌐 PWA: Enabled (manifest.json, icons)")
    print(f"📁 All Features: Projects | Workspaces | Library | File Uploads | Markets | News | Search")
    print(f"{'='*70}")
    print(f"📍 Backend URL: http://0.0.0.0:{port}")
    print(f"📍 Health Check: http://0.0.0.0:{port}/health")
    print(f"{'='*70}\n")
    uvicorn.run(app, host="0.0.0.0", port=port)