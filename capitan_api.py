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
import bcrypt
import httpx
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
# FASTAPI APP - CREATED EARLY
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
    FRONTEND_URL: str = "https://delicate-glitter-91aa.goldquantum0.workers.dev"
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    COINGECKO_KEY: str = ""
    SERPAPI_KEY: str = ""
    NEWS_API_KEY: str = ""
    GNEWS_API_KEY: str = ""
    FINNHUB_API_KEY: str = ""
    ALLOWED_ORIGINS: list = ["*"]
    
    # Email (Resend)
    RESEND_API_KEY: str = os.environ.get("RESEND_API_KEY", "")
    FROM_EMAIL: str = "noreply@goldquantum0.com"
    APP_NAME: str = "CAPITAN AI"
    
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
                # Users table with email columns
                c.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id UUID PRIMARY KEY,
                        telegram_id BIGINT UNIQUE,
                        telegram_username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        name TEXT,
                        email TEXT UNIQUE,
                        password_hash TEXT,
                        email_verified BOOLEAN DEFAULT FALSE,
                        verification_token TEXT,
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
                
                # Password reset tokens
                c.execute('''
                    CREATE TABLE IF NOT EXISTS password_resets (
                        id UUID PRIMARY KEY,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        token TEXT UNIQUE NOT NULL,
                        expires_at TIMESTAMP NOT NULL,
                        created_at TIMESTAMP DEFAULT NOW()
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
                
                # Anonymous sessions
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
                        reasoning_chain TEXT,
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
                
                # Reasoning cache
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
        logger.info("✅ Database tables ready")
    except Exception as e:
        logger.warning(f"Database init: {e}")

init_db()
def sid(): return str(uuid.uuid4())[:8].upper()
def mid(): return 'mem_' + sid()

# ================================================================
# EMAIL HELPER FUNCTIONS (Resend)
# ================================================================
async def send_email_via_resend(to_email: str, subject: str, html_content: str) -> bool:
    """Send email using Resend API"""
    if not settings.RESEND_API_KEY:
        logger.warning("Resend API key not configured")
        return False
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "from": f"{settings.APP_NAME} <{settings.FROM_EMAIL}>",
                    "to": [to_email],
                    "subject": subject,
                    "html": html_content
                },
                timeout=30.0
            )
            return response.status_code == 200
    except Exception as e:
        logger.error(f"Email error: {e}")
        return False

def send_welcome_email(email: str, name: str) -> bool:
    """Send welcome email to new user"""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #4f46e5, #6366f1); padding: 40px; text-align: center; border-radius: 20px;">
            <h1 style="color: white; margin: 0;">CAPITAN AI</h1>
        </div>
        <div style="background: #f9fafb; padding: 30px; border-radius: 20px; margin-top: 20px;">
            <h2 style="color: #1f2937;">Welcome to CAPITAN AI, {name}!</h2>
            <p style="color: #4b5563;">Your account has been successfully created.</p>
            <p style="color: #4b5563;">You now have access to:</p>
            <ul style="color: #4b5563;">
                <li>🤖 Advanced AI Chat (Finance, Coding, Research)</li>
                <li>📚 Personal Library to save important notes</li>
                <li>🌍 Work Area for team collaboration</li>
                <li>📄 File uploads and document analysis</li>
            </ul>
            <a href="{settings.FRONTEND_URL}" style="display: inline-block; background: #4f46e5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 30px; margin-top: 20px;">Start Chatting →</a>
        </div>
        <p style="text-align: center; color: #9ca3af; font-size: 12px; margin-top: 20px;">© 2026 CAPITAN AI by CLOSEAI Technologies</p>
    </body>
    </html>
    """
    return send_email_via_resend(email, f"Welcome to {settings.APP_NAME}!", html)

def send_password_reset_email(email: str, token: str) -> bool:
    """Send password reset email"""
    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #4f46e5, #6366f1); padding: 40px; text-align: center; border-radius: 20px;">
            <h1 style="color: white; margin: 0;">Reset Your Password</h1>
        </div>
        <div style="background: #f9fafb; padding: 30px; border-radius: 20px; margin-top: 20px;">
            <p style="color: #4b5563;">We received a request to reset your password.</p>
            <p style="color: #4b5563;">Click the button below to create a new password:</p>
            <a href="{reset_link}" style="display: inline-block; background: #4f46e5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 30px; margin: 20px 0;">Reset Password</a>
            <p style="color: #4b5563;">This link will expire in 1 hour.</p>
            <p style="color: #9ca3af; font-size: 12px;">If you didn't request this, please ignore this email.</p>
        </div>
    </body>
    </html>
    """
    return send_email_via_resend(email, f"Reset your {settings.APP_NAME} password", html)

# ================================================================
# AUTHENTICATION (JWT)
# ================================================================
def create_auth_token(user_id: str) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "user_id": user_id,
        "type": "user",
        "exp": int((datetime.utcnow() + timedelta(days=30)).timestamp())
    }).encode()).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(hmac.new(settings.JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return f"{header}.{payload}.{signature}"

def create_session_jwt(session_id: str, tier: str) -> str:
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
    """Get current authenticated user (supports both Telegram and Email users)"""
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
                c.execute("""
                    SELECT id, telegram_id, telegram_username, email, name, tier, reasoning_depth, preferred_domain, created_at 
                    FROM users WHERE id = %s
                """, (user_id,))
                row = c.fetchone()
                if row:
                    name = row[5] or row[2] or row[4] or "User"
                    return {
                        "id": row[0],
                        "telegram_id": row[1],
                        "telegram_username": row[2],
                        "email": row[3],
                        "name": name,
                        "tier": row[6],
                        "reasoning_depth": row[7] or 1,
                        "preferred_domain": row[8] or "general",
                        "created_at": row[9].isoformat() if row[9] else None
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
# EMAIL/PASSWORD AUTH ENDPOINTS
# ================================================================
class RegisterRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None

@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    """Register new user with email and password"""
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', req.email):
        raise HTTPException(400, "Invalid email format")
    
    if len(req.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM users WHERE email = %s", (req.email,))
                if c.fetchone():
                    raise HTTPException(400, "Email already registered")
                
                password_hash = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
                user_id = str(uuid.uuid4())
                name = req.name or req.email.split('@')[0]
                c.execute("""
                    INSERT INTO users (id, email, password_hash, name, tier, reasoning_depth, preferred_domain, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                """, (user_id, req.email, password_hash, name, "free", 1, "general"))
                
                auth_token = create_auth_token(user_id)
                c.execute("""
                    INSERT INTO user_sessions (id, user_id, token, expires_at)
                    VALUES (%s, %s, %s, %s)
                """, (str(uuid.uuid4()), user_id, auth_token, datetime.utcnow() + timedelta(days=30)))
                conn.commit()
                
                import asyncio
                asyncio.create_task(asyncio.to_thread(send_welcome_email, req.email, name))
                
                return {
                    "token": auth_token,
                    "user": {
                        "id": user_id,
                        "email": req.email,
                        "name": name,
                        "tier": "free",
                        "reasoning_depth": 1,
                        "preferred_domain": "general"
                    }
                }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(500, "Registration failed")

class LoginRequest(BaseModel):
    email: str
    password: str

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    """Login with email and password"""
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, email, password_hash, name, tier, reasoning_depth, preferred_domain FROM users WHERE email = %s", (req.email,))
                user = c.fetchone()
                
                if not user:
                    raise HTTPException(401, "Invalid email or password")
                
                user_id, email, password_hash, name, tier, reasoning_depth, preferred_domain = user
                
                if not bcrypt.checkpw(req.password.encode(), password_hash.encode()):
                    raise HTTPException(401, "Invalid email or password")
                
                auth_token = create_auth_token(user_id)
                c.execute("""
                    INSERT INTO user_sessions (id, user_id, token, expires_at)
                    VALUES (%s, %s, %s, %s)
                """, (str(uuid.uuid4()), user_id, auth_token, datetime.utcnow() + timedelta(days=30)))
                conn.commit()
                
                return {
                    "token": auth_token,
                    "user": {
                        "id": user_id,
                        "email": email,
                        "name": name,
                        "tier": tier,
                        "reasoning_depth": reasoning_depth or 1,
                        "preferred_domain": preferred_domain or "general"
                    }
                }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(500, "Login failed")

@app.post("/api/auth/forgot-password")
async def forgot_password(req: dict):
    """Request password reset"""
    email = req.get("email")
    if not email:
        raise HTTPException(400, "Email required")
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM users WHERE email = %s", (email,))
                user = c.fetchone()
                
                if not user:
                    return {"message": "If an account exists, a reset link has been sent"}
                
                user_id = user[0]
                reset_token = secrets.token_urlsafe(32)
                expires_at = datetime.utcnow() + timedelta(hours=1)
                
                c.execute("""
                    INSERT INTO password_resets (id, user_id, token, expires_at)
                    VALUES (%s, %s, %s, %s)
                """, (str(uuid.uuid4()), user_id, reset_token, expires_at))
                conn.commit()
                
                import asyncio
                asyncio.create_task(asyncio.to_thread(send_password_reset_email, email, reset_token))
                
                return {"message": "If an account exists, a reset link has been sent"}
    except Exception as e:
        logger.error(f"Forgot password error: {e}")
        return {"message": "If an account exists, a reset link has been sent"}

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

@app.post("/api/auth/reset-password")
async def reset_password(req: ResetPasswordRequest):
    """Reset password with token"""
    if len(req.new_password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("""
                    SELECT user_id FROM password_resets 
                    WHERE token = %s AND expires_at > NOW()
                """, (req.token,))
                reset = c.fetchone()
                
                if not reset:
                    raise HTTPException(400, "Invalid or expired reset token")
                
                user_id = reset[0]
                new_hash = bcrypt.hashpw(req.new_password.encode(), bcrypt.gensalt()).decode()
                c.execute("UPDATE users SET password_hash = %s, updated_at = NOW() WHERE id = %s", (new_hash, user_id))
                c.execute("DELETE FROM password_resets WHERE token = %s", (req.token,))
                c.execute("DELETE FROM user_sessions WHERE user_id = %s", (user_id,))
                conn.commit()
                
                return {"message": "Password reset successfully. Please log in."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reset password error: {e}")
        raise HTTPException(500, "Password reset failed")

@app.post("/api/auth/logout")
async def logout(request: Request):
    """Logout - delete current session"""
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

@app.delete("/api/auth/delete-account")
async def delete_account(request: Request, user: dict = Depends(get_current_user)):
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

@app.get("/api/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Not authenticated")
    return user

@app.post("/api/auth/update-profile")
async def update_profile(req: dict, user: dict = Depends(get_current_user)):
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

# ================================================================
# TELEGRAM AUTH (Preserved)
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

@app.get("/api/auth/telegram/callback")
async def telegram_callback(request: Request):
    params = dict(request.query_params)
    frontend_url = params.pop('frontend', settings.FRONTEND_URL)
    tg_data = "&".join([f"{k}={v}" for k, v in params.items()])
    redirect_url = f"{frontend_url}/?tgAuth={tg_data}"
    return RedirectResponse(url=redirect_url)

# ================================================================
# ANONYMOUS SESSION
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
# FOUNDER LOGIN
# ================================================================
@app.post("/api/founder")
async def founder_login(req: dict):
    code = req.get("code")
    if code != settings.FOUNDER_KEY:
        raise HTTPException(403, "Invalid founder code")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM users WHERE telegram_username = 'founder' OR name = 'CAPITAN Founder'")
                existing = c.fetchone()
                if existing:
                    user_id = existing[0]
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
                        "reasoning_depth": 5,
                        "preferred_domain": "general"
                    }
                }
    except Exception as e:
        logger.error(f"Founder login error: {e}")
        raise HTTPException(500, "Founder login failed")

# ================================================================
# TIER CONFIGURATION
# ================================================================
TIER_CONFIG = {
    "free": {"name": "Free", "msg_limit": 20, "workspace_seats": 0, "projects_enabled": False, "file_upload": False, "live_markets": False, "web_search": False, "ai_model": "Groq Llama 3.1 8B", "price": 0, "reasoning_depth": 1, "context_length": 4096},
    "plus": {"name": "Plus", "msg_limit": 50, "workspace_seats": 10, "projects_enabled": False, "file_upload": True, "live_markets": False, "web_search": True, "ai_model": "Groq Llama 3.3 70B", "price": 8, "reasoning_depth": 2, "context_length": 8192},
    "pro": {"name": "Pro", "msg_limit": 150, "workspace_seats": 25, "projects_enabled": True, "file_upload": True, "live_markets": True, "web_search": True, "ai_model": "Claude 3.5 Sonnet", "price": 17, "reasoning_depth": 3, "context_length": 16384},
    "pro_max": {"name": "Pro Max", "msg_limit": float("inf"), "workspace_seats": 50, "projects_enabled": True, "file_upload": True, "live_markets": True, "web_search": True, "ai_model": "GPT-4o + Claude Ensemble", "price": 30, "reasoning_depth": 4, "context_length": 32768},
    "founder": {"name": "Founder", "msg_limit": float("inf"), "workspace_seats": 100, "projects_enabled": True, "file_upload": True, "live_markets": True, "web_search": True, "ai_model": "All Models + Custom", "price": 0, "reasoning_depth": 5, "context_length": 65536}
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
# REASONING ENGINE
# ================================================================
class ReasoningEngine:
    @staticmethod
    def generate_reasoning_chain(query: str, depth: int = 3) -> List[str]:
        chain = []
        chain.append(f"1. UNDERSTANDING: Let me first understand what you're asking about '{query[:100]}...'")
        chain.append("2. DECOMPOSITION: Breaking this down into key components...")
        chain.append("3. ANALYSIS: Analyzing each component systematically...")
        if depth >= 3: chain.append("4. SYNTHESIS: Synthesizing insights from all angles...")
        if depth >= 4: chain.append("5. VERIFICATION: Double-checking logic and assumptions...")
        if depth >= 5: chain.append("6. OPTIMIZATION: Considering alternative approaches...")
        return chain[:depth + 1]
    
    @staticmethod
    def format_reasoning_chain(chain: List[str]) -> str:
        return "\n".join(chain) if chain else ""

# ================================================================
# SYSTEM PROMPT & AI
# ================================================================
ELITE_SYSTEM_PROMPT = """You are CAPITAN AI — the legendary enterprise intelligence platform by CLOSEAI Technologies.

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
REASONING DEPTH: {reasoning_depth} | USER PREFERRED DOMAIN: {preferred_domain}
"""

def get_time_context():
    now = datetime.utcnow()
    hour = now.hour
    day = now.strftime("%A")
    date = now.strftime("%B %d, %Y")
    utc_time = now.strftime("%H:%M UTC")
    if hour < 5: greeting_context = "The world is quiet. Perfect for deep thinking."
    elif hour < 12: greeting_context = "Fresh day ahead. Ready for new challenges!"
    elif hour < 17: greeting_context = "Markets are alive and moving."
    elif hour < 21: greeting_context = "Winding down but still sharp."
    else: greeting_context = "Night owl mode engaged. Let's get things done!"
    return {"day": day, "date": date, "utc_time": utc_time, "greeting_context": greeting_context}

def classify(q: str) -> str:
    q = q.lower()
    if re.search(r'who are you|what are you|identity|introduce yourself', q): return 'identity'
    if re.search(r'who|what|when|where|why|how|news|latest|current|today|search', q) and len(q.split()) > 3: return 'web_search'
    if re.search(r'def |class |import |docker|kubernetes|aws|api|sql|python|javascript|rust|golang|cpu|gpu|ram|hardware', q): return 'coding'
    if re.search(r'dcf|valuation|wacc|stock|trading|portfolio|crypto|bitcoin|forex|markets', q): return 'finance'
    if re.search(r'prove|proof|theorem|integral|derivative|matrix|probability|statistics', q): return 'math'
    if re.search(r'hello|hi|hey|good morning|good afternoon|good evening|thanks|thank you', q): return 'greeting'
    return 'general'

def system_prompt(domain, tier, model, reasoning_depth=1, preferred_domain="general", user_id=None, web_results=None):
    tc = get_time_context()
    base = ELITE_SYSTEM_PROMPT.replace("{domain}", domain).replace("{tier}", tier).replace("{model}", model)
    base = base.replace("{day}", tc["day"]).replace("{date}", tc["date"])
    base = base.replace("{utc_time}", tc["utc_time"]).replace("{greeting_context}", tc["greeting_context"])
    base = base.replace("{reasoning_depth}", str(reasoning_depth)).replace("{preferred_domain}", preferred_domain)
    if web_results:
        base += "\n\nWEB SEARCH RESULTS:\n" + "\n".join([f"• {r['title']}: {r['snippet'][:200]}" for r in web_results[:4]])
    return base

def search_web(query: str, num_results: int = 5) -> List[dict]:
    results = []
    if settings.SERPAPI_KEY:
        try:
            r = requests.get("https://serpapi.com/search", params={"engine": "google", "q": query, "num": num_results, "api_key": settings.SERPAPI_KEY}, timeout=10)
            if r.status_code == 200:
                for item in r.json().get("organic_results", [])[:num_results]:
                    results.append({"title": item.get("title", ""), "snippet": item.get("snippet", "")[:350], "url": item.get("link", ""), "source": "Google"})
        except: pass
    return results

def get_market_data():
    results = {}
    if settings.COINGECKO_KEY:
        try:
            ids = "bitcoin,ethereum,ripple,cardano,solana,polkadot,dogecoin,avalanche-2,chainlink"
            r = requests.get("https://api.coingecko.com/api/v3/simple/price", params={"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true"}, headers={"x-cg-demo-api-key": settings.COINGECKO_KEY}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                nm = {"bitcoin": "BTC", "ethereum": "ETH", "ripple": "XRP", "cardano": "ADA", "solana": "SOL", "polkadot": "DOT", "dogecoin": "DOGE", "avalanche-2": "AVAX", "chainlink": "LINK"}
                for k, v in data.items():
                    results[nm.get(k, k.upper())] = {"price": v["usd"], "change": round(v.get("usd_24h_change", 0), 2), "source": "CoinGecko"}
        except: pass
    return results

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
    seen = set(); unique = []
    for n in news:
        k = n["headline"][:100].lower().strip()
        if k and k not in seen: seen.add(k); unique.append(n)
    unique.sort(key=lambda x: x.get("time", ""), reverse=True)
    return unique[:20]

def get_tech_news():
    news = []
    if settings.NEWS_API_KEY:
        try:
            r = requests.get("https://newsapi.org/v2/everything", params={"q": "AI artificial intelligence coding startup innovation technology", "language": "en", "pageSize": 15, "sortBy": "publishedAt", "apiKey": settings.NEWS_API_KEY}, timeout=10)
            if r.status_code == 200:
                for a in r.json().get("articles", []):
                    if a.get("title") and a.get("description"):
                        news.append({"source": a.get("source", {}).get("name", "NewsAPI"), "headline": a.get("title", ""), "url": a.get("url", ""), "time": a.get("publishedAt", ""), "summary": (a.get("description") or "")[:300]})
        except: pass
    seen = set(); unique = []
    for n in news:
        k = n["headline"][:100].lower().strip()
        if k and k not in seen: seen.add(k); unique.append(n)
    unique.sort(key=lambda x: x.get("time", ""), reverse=True)
    return unique[:20]

def call_ai_with_tier(messages: List[dict], tier: str = "free", reasoning_depth: int = 1, domain: str = "general") -> Tuple[str, str]:
    if reasoning_depth > 1 and domain in ["finance", "quant", "coding", "math"]:
        reasoning_instruction = f"\n\nPlease use {reasoning_depth}-step chain-of-thought reasoning for this complex {domain} problem. Show your work step by step."
        for m in messages:
            if m.get("role") == "system":
                m["content"] += reasoning_instruction
                break
    
    if tier == "pro_max" and settings.OPENROUTER_API_KEY:
        try:
            r1 = requests.post("https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "Content-Type": "application/json"}, json={"model": "anthropic/claude-3.5-sonnet-20241022", "messages": messages, "temperature": 0.7, "max_tokens": 4000}, timeout=45)
            content1 = r1.json().get("choices", [{}])[0].get("message", {}).get("content", "") if r1.status_code == 200 else ""
            r2 = requests.post("https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "Content-Type": "application/json"}, json={"model": "openai/gpt-4o-2024-11-20", "messages": messages, "temperature": 0.7, "max_tokens": 4000}, timeout=45)
            content2 = r2.json().get("choices", [{}])[0].get("message", {}).get("content", "") if r2.status_code == 200 else ""
            if content1 and content2:
                combined = f"**Claude 3.5 Sonnet Response:**\n{content1}\n\n---\n\n**GPT-4o Additional Insights:**\n{content2}"
                return combined, "claude-3.5-sonnet + gpt-4o (Ensemble)"
            elif content1: return content1, "claude-3.5-sonnet"
            elif content2: return content2, "gpt-4o"
        except Exception as e: logger.error(f"Pro Max ensemble error: {e}")
    
    if tier == "pro" and settings.OPENROUTER_API_KEY:
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "Content-Type": "application/json"}, json={"model": "anthropic/claude-3.5-sonnet-20241022", "messages": messages, "temperature": 0.7, "max_tokens": 3000}, timeout=40)
            if r.status_code == 200:
                content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if content: return content, "claude-3.5-sonnet"
        except Exception as e: logger.error(f"Pro Claude error: {e}")
    
    if tier == "plus" and settings.GROQ_API_KEY:
        try:
            for m in messages:
                if m.get("role") == "system" and len(m["content"]) > 2000:
                    m["content"] = m["content"][:2000] + "\n\n[Context trimmed for efficiency]"
            r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"}, json={"model": "llama-3.3-70b-versatile", "messages": messages, "temperature": 0.7, "max_tokens": 2500}, timeout=35)
            if r.status_code == 200:
                content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if content: return content, "llama-3.3-70b"
        except Exception as e: logger.error(f"Plus Groq error: {e}")
    
    if settings.GROQ_API_KEY:
        try:
            for m in messages:
                if m.get("role") == "system" and tier == "free" and len(m["content"]) > 1500:
                    m["content"] = m["content"][:1500] + "\n\n[Context trimmed]"
            r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"}, json={"model": "llama-3.1-8b-instant", "messages": messages, "temperature": 0.7, "max_tokens": 1200}, timeout=30)
            if r.status_code == 200:
                content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if content: return content, "llama-3.1-8b"
        except Exception as e: logger.error(f"Free Groq error: {e}")
    
    return "I'm having trouble connecting to AI services. Please try again or contact support.", "fallback"

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
    
    if not isinstance(limit, float) or limit != float("inf"):
        if not check_rate_limit(user_id if user else session["id"], tier):
            raise HTTPException(429, "Rate limit exceeded. Please wait a moment.")
    
    user_msg = next((m["content"] for m in reversed(req.messages) if m.get("role") == "user"), "")
    if not user_msg:
        raise HTTPException(400, "No message content")
    
    chat_id = req.chat_id or f"chat_{sid()}"
    domain = classify(user_msg)
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                if is_authenticated:
                    c.execute("INSERT INTO chats (id, user_id, title, created, updated) VALUES (%s, %s, %s, NOW(), NOW()) ON CONFLICT (id) DO UPDATE SET updated = NOW()", (chat_id, user_id, user_msg[:60]))
                    c.execute("INSERT INTO chat_messages (id, chat_id, user_id, role, content, created) VALUES (%s, %s, %s, %s, %s, NOW())", (f"msg_{sid()}", chat_id, user_id, "user", user_msg))
                else:
                    c.execute("INSERT INTO chats (id, session_id, title, created, updated) VALUES (%s, %s, %s, NOW(), NOW()) ON CONFLICT (id) DO UPDATE SET updated = NOW()", (chat_id, session["id"], user_msg[:60]))
                    c.execute("INSERT INTO chat_messages (id, chat_id, session_id, role, content, created) VALUES (%s, %s, %s, %s, %s, NOW())", (f"msg_{sid()}", chat_id, session["id"], "user", user_msg))
                conn.commit()
                c.execute("SELECT role, content FROM chat_messages WHERE chat_id = %s ORDER BY created ASC LIMIT 20", (chat_id,))
                history = [{"role": r[0], "content": r[1]} for r in c.fetchall()]
    except Exception as e:
        logger.error(f"Save error: {e}")
        history = []
    
    web_results = None
    if tier_info.get("web_search", False) and domain in ["web_search", "general", "science", "coding", "hardware"]:
        try: web_results = search_web(user_msg, 5)
        except: pass
    
    prompt = system_prompt(domain, tier, tier_info["ai_model"], reasoning_depth, preferred_domain, user_id if is_authenticated else None, web_results)
    
    reasoning_chain = None
    if reasoning_depth > 1 and domain in ["finance", "quant", "coding", "math"]:
        reasoning_chain = ReasoningEngine.generate_reasoning_chain(user_msg, min(reasoning_depth, tier_info["reasoning_depth"]))
        if reasoning_chain:
            prompt += "\n\nREASONING CHAIN:\n" + ReasoningEngine.format_reasoning_chain(reasoning_chain)
    
    result, model_used = call_ai_with_tier([{"role": "system", "content": prompt}] + history, tier, reasoning_depth, domain)
    
    if result:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    if is_authenticated:
                        c.execute("INSERT INTO chat_messages (id, chat_id, user_id, role, content, model, reasoning_chain, created) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())", (f"msg_{sid()}", chat_id, user_id, "assistant", result, model_used, json.dumps(reasoning_chain) if reasoning_chain else None))
                        c.execute("INSERT INTO memories (id, memory_id, user_id, content, query, domain, importance, created) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())", (sid(), mid(), user_id, result[:500], user_msg, domain, 2 if domain in ["finance", "quant", "coding"] else 1))
                    else:
                        c.execute("INSERT INTO chat_messages (id, chat_id, session_id, role, content, model, reasoning_chain, created) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())", (f"msg_{sid()}", chat_id, session["id"], "assistant", result, model_used, json.dumps(reasoning_chain) if reasoning_chain else None))
                        c.execute("INSERT INTO memories (id, memory_id, session_id, content, query, domain, created) VALUES (%s, %s, %s, %s, %s, %s, NOW())", (sid(), mid(), session["id"], result[:500], user_msg, domain))
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
# PROJECTS ENDPOINTS
# ================================================================
@app.get("/api/projects")
def get_projects(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401, "Authentication required")
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
    if not user: raise HTTPException(401, "Authentication required")
    tier_info = TIER_CONFIG.get(user["tier"], TIER_CONFIG["free"])
    if not tier_info["projects_enabled"]:
        raise HTTPException(403, "Projects require Pro or Pro Max tier")
    name = req.get("name")
    if not name: raise HTTPException(400, "Project name required")
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
    if not user: raise HTTPException(401, "Authentication required")
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
    if not user: raise HTTPException(401, "Authentication required")
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
# MARKET & NEWS ENDPOINTS
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
    if not user: raise HTTPException(401, "Authentication required")
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
    if not user: raise HTTPException(401, "Authentication required")
    room_code = req.get("room_code", "").upper()
    if not room_code:
        raise HTTPException(400, "Room code required")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, max_members FROM workspaces WHERE room_code = %s", (room_code,))
                ws = c.fetchone()
                if not ws: raise HTTPException(404, "Room not found")
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
    if not user: raise HTTPException(401, "Authentication required")
    room_code = req.get("room_code", "").upper()
    message = req.get("message", "")
    if not room_code or not message:
        raise HTTPException(400, "Room code and message required")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM workspaces WHERE room_code = %s", (room_code,))
                ws = c.fetchone()
                if not ws: raise HTTPException(404, "Room not found")
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
    return {
        "status": "ok",
        "version": "28.0",
        "database": db_status,
        "ai": ai_status,
        "providers": providers,
        "telegram_auth": bool(settings.TELEGRAM_BOT_TOKEN),
        "email_auth": bool(settings.RESEND_API_KEY),
        "reasoning_engine": True,
        "intelligence_level": "full"
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
        "background_color": "#4f46e5",
        "theme_color": "#4f46e5",
        "orientation": "portrait",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}
        ]
    }
    return JSONResponse(content=manifest)

@app.get("/icon-192.png")
async def icon_192():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="#4f46e5" rx="20"/><path d="M50 15 L75 27 L75 52 C75 65 63 76 50 82 C37 76 25 65 25 52 L25 27 Z" fill="none" stroke="white" stroke-width="4"/><text x="50" y="72" text-anchor="middle" font-size="42" fill="white" font-family="Inter,sans-serif" font-weight="700">C</text></svg>'''
    return Response(content=svg, media_type="image/svg+xml")

@app.get("/icon-512.png")
async def icon_512():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="#4f46e5" rx="20"/><path d="M50 15 L75 27 L75 52 C75 65 63 76 50 82 C37 76 25 65 25 52 L25 27 Z" fill="none" stroke="white" stroke-width="4"/><text x="50" y="72" text-anchor="middle" font-size="42" fill="white" font-family="Inter,sans-serif" font-weight="700">C</text></svg>'''
    return Response(content=svg, media_type="image/svg+xml")

@app.get("/")
async def root():
    return {
        "name": "CAPITAN AI",
        "version": "28.0",
        "status": "operational",
        "telegram_auth": bool(settings.TELEGRAM_BOT_TOKEN),
        "email_auth": bool(settings.RESEND_API_KEY),
        "pwa_supported": True,
        "tiers": ["free", "plus", "pro", "pro_max", "founder"],
        "intelligence": "full_restored",
        "reasoning": "chain_of_thought_enabled"
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
    print(f"🔐 Auth: Telegram Bot @{settings.TELEGRAM_BOT_USERNAME} | Email via Resend={bool(settings.RESEND_API_KEY)}")
    print(f"👑 Founder: Enabled (19 clicks on footer)")
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
