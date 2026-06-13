"""
CAPITAN AI — Enterprise Backend v25.0
CLOSEAI Technologies
Production-Ready Single-File Deployment
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
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from contextlib import contextmanager
from urllib.parse import quote_plus

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic_settings import BaseSettings
import psycopg2
import psycopg2.extras
import uvicorn

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
    
    # AI Providers
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    MISTRAL_API_KEY: str = ""
    
    # Market Data
    COINGECKO_KEY: str = ""
    ALPHA_VANTAGE_KEY: str = ""
    NEWS_API_KEY: str = ""
    SERPAPI_KEY: str = ""
    
    # CORS
    ALLOWED_ORIGINS: list = ["*"]
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# ================================================================
# DATABASE LAYER (SQLAlchemy-style but with raw psycopg2)
# ================================================================

@contextmanager
def get_db():
    """Get database connection with automatic cleanup and retry"""
    conn = None
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            # Build connection string
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
            print(f"Database connection attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                raise
    
    if conn:
        conn.close()

def init_db():
    """Create all tables if they don't exist"""
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
                        created TIMESTAMP,
                        updated TIMESTAMP
                    )
                ''')
                
                # Chats table
                c.execute('''
                    CREATE TABLE IF NOT EXISTS chats (
                        id TEXT PRIMARY KEY,
                        session_id TEXT,
                        title TEXT,
                        created TIMESTAMP,
                        updated TIMESTAMP
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
                        tokens INTEGER,
                        latency_ms INTEGER,
                        created TIMESTAMP
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
                        created TIMESTAMP
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
                        created TIMESTAMP
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
                        created TIMESTAMP
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
                        expires TIMESTAMP,
                        created TIMESTAMP
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
                        created TIMESTAMP
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
                        created TIMESTAMP
                    )
                ''')
                
                # Workspace members table
                c.execute('''
                    CREATE TABLE IF NOT EXISTS workspace_members (
                        workspace_id TEXT,
                        session_id TEXT,
                        role TEXT DEFAULT 'member',
                        joined TIMESTAMP,
                        PRIMARY KEY (workspace_id, session_id)
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
                        created TIMESTAMP
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
                        created TIMESTAMP,
                        updated TIMESTAMP
                    )
                ''')
                
                # Cache tables
                c.execute('''
                    CREATE TABLE IF NOT EXISTS market_cache (
                        id TEXT PRIMARY KEY,
                        category TEXT,
                        data TEXT,
                        created TIMESTAMP
                    )
                ''')
                
                c.execute('''
                    CREATE TABLE IF NOT EXISTS news_cache (
                        id TEXT PRIMARY KEY,
                        category TEXT,
                        data TEXT,
                        created TIMESTAMP
                    )
                ''')
                
                c.execute('''
                    CREATE TABLE IF NOT EXISTS web_cache (
                        id TEXT PRIMARY KEY,
                        query_hash TEXT,
                        data TEXT,
                        created TIMESTAMP
                    )
                ''')
                
                conn.commit()
        print("✅ Database tables ready")
    except Exception as e:
        print(f"⚠️ Database init warning: {e}")

# ================================================================
# SECURITY & AUTH
# ================================================================

def create_jwt(session_id: str, tier: str) -> str:
    """Create JWT token"""
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

def verify_jwt(token: str) -> Optional[dict]:
    """Verify JWT token"""
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

def get_current_session(request: Request):
    """Get current session from JWT"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing authorization header")
    
    token = auth[7:]
    payload = verify_jwt(token)
    if not payload:
        raise HTTPException(401, "Invalid or expired token")
    
    session_id = payload.get("session_id")
    tier = payload.get("tier")
    
    # Verify session exists in database
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, tier, msg_count, msg_window FROM sessions WHERE id=%s", (session_id,))
                row = c.fetchone()
                if not row:
                    raise HTTPException(401, "Session not found")
                return {
                    "id": row[0],
                    "tier": row[1],
                    "msg_count": row[2] or 0,
                    "msg_window": row[3]
                }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Session error: {e}")
        raise HTTPException(500, "Database error")

# ================================================================
# RATE LIMITING
# ================================================================

rate_store = {}

def check_rate_limit(session_id: str, tier: str) -> bool:
    """Check rate limit (per minute)"""
    now = time.time()
    key = f"rate:{session_id}"
    
    if key not in rate_store:
        rate_store[key] = []
    
    # Clean old entries
    rate_store[key] = [t for t in rate_store[key] if now - t < 60]
    
    limits = {"free": 15, "plus": 30, "pro": 60, "founder": 200}
    limit = limits.get(tier, 15)
    
    if len(rate_store[key]) >= limit:
        return False
    
    rate_store[key].append(now)
    return True

def check_daily_limit(current_count: int, last_reset: Optional[str], tier: str) -> tuple[bool, int]:
    """Check daily message limit, returns (allowed, remaining)"""
    limits = {"free": 17, "plus": 40, "pro": 999999, "founder": 999999}
    daily_limit = limits.get(tier, 17)
    
    if daily_limit >= 999999:
        return True, -1
    
    if last_reset:
        last = datetime.fromisoformat(last_reset)
        if datetime.utcnow() - last >= timedelta(hours=24):
            # Reset window
            return True, daily_limit
    
    if current_count >= daily_limit:
        return False, 0
    
    return True, daily_limit - current_count

# ================================================================
# AI SERVICE
# ================================================================

class AIService:
    def __init__(self):
        self.providers = []
        if settings.GROQ_API_KEY:
            self.providers.append(("groq", settings.GROQ_API_KEY, "llama-3.1-8b-instant"))
        if settings.OPENROUTER_API_KEY:
            self.providers.append(("openrouter", settings.OPENROUTER_API_KEY, "google/gemini-flash-1.5"))
        if settings.OPENAI_API_KEY:
            self.providers.append(("openai", settings.OPENAI_API_KEY, "gpt-3.5-turbo"))
    
    async def generate(self, messages: List[Dict], tier: str) -> Tuple[str, str, int]:
        start_time = time.time()
        
        for provider_name, api_key, model in self.providers:
            try:
                if provider_name == "groq":
                    # Trim system prompt for free tier
                    for m in messages:
                        if m.get("role") == "system" and tier == "free":
                            m["content"] = m["content"][:1000]
                    
                    response = requests.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={
                            "model": "llama-3.3-70b-versatile" if tier in ("pro", "founder") else model,
                            "messages": messages,
                            "temperature": 0.5,
                            "max_tokens": 2000 if tier in ("pro", "founder") else 800
                        },
                        timeout=25
                    )
                    if response.status_code == 200:
                        content = response.json()["choices"][0]["message"]["content"]
                        latency = int((time.time() - start_time) * 1000)
                        return content, provider_name, latency
                
                elif provider_name == "openrouter":
                    response = requests.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={
                            "model": "anthropic/claude-3.5-sonnet" if tier in ("pro", "founder") else model,
                            "messages": messages,
                            "temperature": 0.5,
                            "max_tokens": 2000 if tier in ("pro", "founder") else 800
                        },
                        timeout=30
                    )
                    if response.status_code == 200:
                        content = response.json()["choices"][0]["message"]["content"]
                        latency = int((time.time() - start_time) * 1000)
                        return content, provider_name, latency
                
                elif provider_name == "openai":
                    response = requests.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={
                            "model": "gpt-4o-mini" if tier in ("pro", "founder") else model,
                            "messages": messages,
                            "temperature": 0.5,
                            "max_tokens": 2000 if tier in ("pro", "founder") else 800
                        },
                        timeout=25
                    )
                    if response.status_code == 200:
                        content = response.json()["choices"][0]["message"]["content"]
                        latency = int((time.time() - start_time) * 1000)
                        return content, provider_name, latency
                        
            except Exception as e:
                print(f"{provider_name} error: {e}")
                continue
        
        return "I'm having trouble connecting to AI services. Please try again.", "fallback", 0

ai_service = AIService()

# ================================================================
# FASTAPI APP
# ================================================================

app = FastAPI(title="CAPITAN AI API", version="25.0")

# CORS - Allow all for Cloudflare frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================================================================
# HEALTH CHECK
# ================================================================

@app.get("/health")
def health_check():
    """Health check endpoint"""
    db_status = "disconnected"
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT 1")
                db_status = "connected"
    except Exception as e:
        print(f"Health check DB error: {e}")
    
    ai_status = "connected" if ai_service.providers else "disconnected"
    providers = [p[0] for p in ai_service.providers]
    
    return {
        "status": "ok",
        "version": "25.0",
        "database": db_status,
        "ai": ai_status,
        "providers": providers
    }

# ================================================================
# SESSION ENDPOINTS
# ================================================================

@app.get("/api/session")
def get_or_create_session():
    """Get or create anonymous session"""
    session_id = f"s_{str(uuid.uuid4())[:8].upper()}"
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute(
                    "INSERT INTO sessions (id, tier, msg_count, msg_window, created, updated) VALUES (%s, %s, 0, %s, %s, %s)",
                    (session_id, "free", None, datetime.utcnow(), datetime.utcnow())
                )
                conn.commit()
    except Exception as e:
        print(f"Session creation error: {e}")
        raise HTTPException(500, "Could not create session")
    
    token = create_jwt(session_id, "free")
    return {
        "id": session_id,
        "tier": "free",
        "msg_count": 0,
        "token": token
    }

# ================================================================
# FOUNDER ENDPOINT
# ================================================================

class FounderRequest(BaseModel):
    code: str

@app.post("/api/founder")
def founder_upgrade(req: FounderRequest, current_session: dict = Depends(get_current_session)):
    """Upgrade to founder tier"""
    if req.code != settings.FOUNDER_KEY:
        raise HTTPException(403, "Invalid founder code")
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute(
                    "UPDATE sessions SET tier='founder', msg_count=0, updated=%s WHERE id=%s",
                    (datetime.utcnow(), current_session["id"])
                )
                conn.commit()
    except Exception as e:
        print(f"Founder upgrade error: {e}")
        raise HTTPException(500, "Could not upgrade session")
    
    token = create_jwt(current_session["id"], "founder")
    return {
        "verified": True,
        "tier": "founder",
        "token": token
    }

# ================================================================
# PAYMENT CONFIG
# ================================================================

WALLETS = {
    "BTC": "bc1qrv6yr6e0mat96rvrc8smdf9rvu9rlp8xuk8new",
    "ETH": "0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1"
}

UPGRADE_BENEFITS = {
    "plus": ["40 messages per day", "Smart AI model", "Work Area (7 seats)", "File uploads (10MB)", "Web search"],
    "pro": ["Unlimited messages", "Deep AI (Claude/GPT-4)", "Work Area (20 seats)", "Live market data", "All Plus features"]
}

@app.get("/api/payment-config")
def payment_config():
    return {
        "wallets": WALLETS,
        "prices": {"plus": 8, "pro": 17},
        "benefits": UPGRADE_BENEFITS
    }

class UpgradeRequest(BaseModel):
    tier: str
    txid: str
    currency: str = "BTC"

@app.post("/api/upgrade")
def upgrade(req: UpgradeRequest, current_session: dict = Depends(get_current_session)):
    """Upgrade user tier"""
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
                    (str(uuid.uuid4())[:8], current_session["id"], req.txid.strip(), req.currency.upper(), prices[req.tier], req.tier,
                     datetime.utcnow() + timedelta(days=30), datetime.utcnow())
                )
                c.execute(
                    "UPDATE sessions SET tier=%s, msg_count=0, updated=%s WHERE id=%s",
                    (req.tier, datetime.utcnow(), current_session["id"])
                )
                conn.commit()
    except Exception as e:
        print(f"Upgrade error: {e}")
        raise HTTPException(500, "Could not process upgrade")
    
    token = create_jwt(current_session["id"], req.tier)
    return {
        "verified": True,
        "tier": req.tier,
        "token": token
    }

# ================================================================
# CHAT ENDPOINTS
# ================================================================

class ChatRequest(BaseModel):
    messages: list
    chat_id: Optional[str] = None

def sid():
    return str(uuid.uuid4())[:8].upper()

@app.post("/api/chat")
async def chat(req: ChatRequest, current_session: dict = Depends(get_current_session)):
    """Send a chat message"""
    
    # Check rate limit (per minute)
    if not check_rate_limit(current_session["id"], current_session["tier"]):
        raise HTTPException(429, "Rate limit exceeded. Please wait a moment.")
    
    # Get user message
    user_msg = next((m["content"] for m in reversed(req.messages) if m.get("role") == "user"), "")
    if not user_msg:
        raise HTTPException(400, "No message content")
    
    # Check daily limit
    allowed, remaining = check_daily_limit(
        current_session["msg_count"],
        current_session.get("msg_window"),
        current_session["tier"]
    )
    
    if not allowed:
        raise HTTPException(429, f"Daily limit reached. Upgrade to continue.")
    
    chat_id = req.chat_id or f"chat_{sid()}"
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                # Create or update chat
                if not req.chat_id:
                    c.execute(
                        "INSERT INTO chats (id, session_id, title, created, updated) VALUES (%s, %s, %s, %s, %s)",
                        (chat_id, current_session["id"], user_msg[:60], datetime.utcnow(), datetime.utcnow())
                    )
                else:
                    c.execute(
                        "UPDATE chats SET updated=%s WHERE id=%s AND session_id=%s",
                        (datetime.utcnow(), chat_id, current_session["id"])
                    )
                
                # Save user message
                c.execute(
                    "INSERT INTO chat_messages (id, chat_id, session_id, role, content, created) VALUES (%s, %s, %s, %s, %s, %s)",
                    (f"msg_{sid()}", chat_id, current_session["id"], "user", user_msg, datetime.utcnow())
                )
                
                # Update session message count
                c.execute(
                    "UPDATE sessions SET msg_count = msg_count + 1, updated=%s WHERE id=%s",
                    (datetime.utcnow(), current_session["id"])
                )
                conn.commit()
                
                # Get chat history
                c.execute(
                    "SELECT role, content FROM chat_messages WHERE chat_id=%s ORDER BY created ASC LIMIT 15",
                    (chat_id,)
                )
                history = [{"role": r[0], "content": r[1]} for r in c.fetchall()]
    except Exception as e:
        print(f"Save message error: {e}")
        history = []
    
    # Create system prompt
    system_prompt = f"""You are CAPITAN AI, an enterprise intelligence platform.
User tier: {current_session["tier"]}
Current time: {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}

Be helpful, concise, and professional. Use 1-2 emojis for warmth when appropriate."""
    
    messages = [{"role": "system", "content": system_prompt}] + history
    
    # Get AI response
    ai_content, model_used, latency = await ai_service.generate(messages, current_session["tier"])
    
    # Save AI response
    if ai_content:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute(
                        "INSERT INTO chat_messages (id, chat_id, session_id, role, content, model, latency_ms, created) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (f"msg_{sid()}", chat_id, current_session["id"], "assistant", ai_content, model_used, latency, datetime.utcnow())
                    )
                    conn.commit()
        except Exception as e:
            print(f"Save AI response error: {e}")
    
    # Calculate remaining messages
    limits = {"free": 17, "plus": 40, "pro": 999999, "founder": 999999}
    daily_limit = limits.get(current_session["tier"], 17)
    msgs_left = daily_limit - (current_session["msg_count"] + 1) if daily_limit < 999999 else "unlimited"
    
    return {
        "content": ai_content,
        "chat_id": chat_id,
        "model": model_used,
        "remaining": msgs_left,
        "latency_ms": latency
    }

# ================================================================
# CHAT HISTORY ENDPOINTS
# ================================================================

@app.get("/api/chats")
def get_chats(current_session: dict = Depends(get_current_session)):
    """Get user's chat list"""
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute(
                    "SELECT id, title, created, updated FROM chats WHERE session_id=%s ORDER BY updated DESC LIMIT 30",
                    (current_session["id"],)
                )
                rows = c.fetchall()
                return {"chats": [{"id": r[0], "title": r[1] or "New Chat", "created": r[2].isoformat() if r[2] else None, "updated": r[3].isoformat() if r[3] else None} for r in rows]}
    except Exception as e:
        print(f"Get chats error: {e}")
        return {"chats": []}

@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str, current_session: dict = Depends(get_current_session)):
    """Get specific chat messages"""
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM chats WHERE id=%s AND session_id=%s", (chat_id, current_session["id"]))
                if not c.fetchone():
                    raise HTTPException(404, "Chat not found")
                
                c.execute(
                    "SELECT id, role, content, model, created FROM chat_messages WHERE chat_id=%s ORDER BY created ASC",
                    (chat_id,)
                )
                rows = c.fetchall()
                return {"messages": [{"id": r[0], "role": r[1], "content": r[2], "model": r[3] or "AI", "created": r[4].isoformat() if r[4] else None} for r in rows]}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Get chat error: {e}")
        raise HTTPException(500, str(e))

@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str, current_session: dict = Depends(get_current_session)):
    """Delete a chat"""
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("DELETE FROM chat_messages WHERE chat_id=%s AND session_id=%s", (chat_id, current_session["id"]))
                c.execute("DELETE FROM chats WHERE id=%s AND session_id=%s", (chat_id, current_session["id"]))
                conn.commit()
                return {"deleted": True}
    except Exception as e:
        print(f"Delete chat error: {e}")
        raise HTTPException(500, str(e))

# ================================================================
# MARKET & NEWS ENDPOINTS (Placeholders - can be expanded)
# ================================================================

@app.get("/api/markets")
def markets():
    return {"prices": {}, "news": [], "message": "Upgrade to Pro for market data"}

@app.get("/api/markets/prices")
def markets_prices():
    return {"prices": {}, "message": "Upgrade to Pro for market data"}

@app.get("/api/markets/news")
def markets_news():
    return {"news": [], "message": "Upgrade to Pro for market news"}

@app.get("/api/news/tech")
def tech_news():
    return {"news": [], "message": "Upgrade to Pro for tech news"}

@app.get("/api/search")
def web_search(q: str = ""):
    return {"results": [], "message": "Web search on Plus and Pro plans"}

# ================================================================
# LIBRARY ENDPOINTS (Placeholders)
# ================================================================

@app.get("/api/library")
def get_library():
    return {"items": []}

class LibraryItemRequest(BaseModel):
    name: str
    type: str = "note"
    content: Optional[str] = ""

@app.post("/api/library")
def create_library_item(req: LibraryItemRequest):
    return {"id": f"lib_{sid()}", "created": True}

@app.delete("/api/library/{item_id}")
def delete_library_item(item_id: str):
    return {"deleted": True}

# ================================================================
# WORKSPACE ENDPOINTS (Placeholders - can be expanded)
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
def ws_create():
    return {"created": False, "message": "Upgrade to Plus or Pro"}

@app.post("/api/workspace/join")
def ws_join():
    return {"joined": False, "message": "Upgrade to Plus or Pro"}

@app.post("/api/workspace/message")
def ws_message():
    return {"sent": False}

@app.get("/api/workspace/messages")
def ws_get_messages():
    return {"messages": [], "members": []}

@app.post("/api/workspace/notes")
def ws_save_note():
    return {"saved": False}

@app.get("/api/workspace/notes")
def ws_get_notes():
    return {"notes": []}

# ================================================================
# UPLOAD ENDPOINT
# ================================================================

from fastapi import UploadFile, File

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), current_session: dict = Depends(get_current_session)):
    """Upload a file (Plus/Pro only)"""
    if current_session["tier"] == "free":
        raise HTTPException(403, "Upgrade to Plus or Pro for file uploads")
    
    contents = await file.read()
    file_id = f"file_{sid()}"
    file_path = os.path.join(UPLOAD_DIR, file_id)
    
    with open(file_path, "wb") as f:
        f.write(contents)
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute(
                    "INSERT INTO uploaded_files (id, session_id, filename, original_name, size, mime_type, created) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (file_id, current_session["id"], file_id, file.filename or "unknown", len(contents), file.content_type or "application/octet-stream", datetime.utcnow())
                )
                conn.commit()
    except Exception as e:
        print(f"Save file error: {e}")
    
    return {
        "id": file_id,
        "filename": file.filename,
        "size_mb": round(len(contents) / (1024 * 1024), 2)
    }

# ================================================================
# ADMIN ENDPOINT (Founder only)
# ================================================================

@app.post("/api/admin")
def admin(current_session: dict = Depends(get_current_session)):
    """Admin endpoint - founder only"""
    if current_session["tier"] != "founder":
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
                
                return {
                    "total_sessions": total,
                    "paid_sessions": paid,
                    "total_messages": msgs,
                    "workspaces": ws
                }
    except Exception as e:
        print(f"Admin error: {e}")
        raise HTTPException(500, str(e))

# ================================================================
# MAIN ENTRY POINT
# ================================================================

if __name__ == "__main__":
    # Initialize database
    init_db()
    
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 CAPITAN AI v25.0 Starting on port {port}")
    print(f"📊 Database: {'Supabase' if settings.DATABASE_URL or settings.SUPABASE_DB_PASSWORD else 'Not configured'}")
    print(f"🤖 AI Providers: {[p[0] for p in ai_service.providers] or 'None'}")
    print(f"👑 Founder Key: {settings.FOUNDER_KEY[:10]}...")
    print(f"📨 Limits: Free=17/day, Plus=40/day, Pro=Unlimited")
    
    uvicorn.run(app, host="0.0.0.0", port=port)