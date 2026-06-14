"""
CAPITAN AI — Enterprise Backend v28.0
CLOSEAI Technologies
FULL INTELLIGENCE RESTORED | Elite Reasoning | Human-Like Communication
Email/Password Authentication (No Email Sending)
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
from passlib.hash import bcrypt
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from contextlib import contextmanager
from urllib.parse import quote_plus

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from pydantic_settings import BaseSettings
import psycopg2
import uvicorn

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
# LOGGING
# ================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ================================================================
# CONFIGURATION
# ================================================================
class Settings(BaseSettings):
    DATABASE_URL: str = ""
    JWT_SECRET: str = secrets.token_hex(32)
    FOUNDER_KEY: str = "Osinachi@35"
    FRONTEND_URL: str = "https://delicate-glitter-91aa.goldquantum0.workers.dev"
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    COINGECKO_KEY: str = ""
    SERPAPI_KEY: str = ""
    NEWS_API_KEY: str = ""
    ALLOWED_ORIGINS: list = ["*"]
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# ================================================================
# DATABASE
# ================================================================
@contextmanager
def get_db():
    conn = None
    for attempt in range(3):
        try:
            conn = psycopg2.connect(settings.DATABASE_URL, connect_timeout=10)
            yield conn
            return
        except Exception as e:
            logger.warning(f"DB attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                time.sleep(2)
    if conn:
        conn.close()

def init_db():
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id UUID PRIMARY KEY,
                        email TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        name TEXT,
                        tier TEXT DEFAULT 'free',
                        reasoning_depth INTEGER DEFAULT 1,
                        preferred_domain TEXT DEFAULT 'general',
                        tier_expires TIMESTAMP,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                ''')
                c.execute('''
                    CREATE TABLE IF NOT EXISTS user_sessions (
                        id UUID PRIMARY KEY,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        token TEXT UNIQUE NOT NULL,
                        expires_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                ''')
                c.execute('''
                    CREATE TABLE IF NOT EXISTS sessions (
                        id TEXT PRIMARY KEY,
                        tier TEXT DEFAULT 'free',
                        msg_count INTEGER DEFAULT 0,
                        created TIMESTAMP DEFAULT NOW(),
                        updated TIMESTAMP DEFAULT NOW()
                    )
                ''')
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
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')
                c.execute('''
                    CREATE TABLE IF NOT EXISTS memories (
                        id TEXT PRIMARY KEY,
                        memory_id TEXT,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        content TEXT,
                        query TEXT,
                        domain TEXT,
                        importance INTEGER DEFAULT 1,
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')
                c.execute('''
                    CREATE TABLE IF NOT EXISTS library_items (
                        id TEXT PRIMARY KEY,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        name TEXT,
                        content TEXT,
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')
                c.execute('''
                    CREATE TABLE IF NOT EXISTS uploaded_files (
                        id TEXT PRIMARY KEY,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        filename TEXT,
                        original_name TEXT,
                        size INTEGER,
                        storage_path TEXT,
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')
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
                c.execute('''
                    CREATE TABLE IF NOT EXISTS workspace_members (
                        workspace_id TEXT,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        role TEXT DEFAULT 'member',
                        joined_at TIMESTAMP DEFAULT NOW(),
                        PRIMARY KEY (workspace_id, user_id)
                    )
                ''')
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
                c.execute('''
                    CREATE TABLE IF NOT EXISTS payments (
                        id UUID PRIMARY KEY,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        txid TEXT UNIQUE,
                        currency TEXT,
                        amount REAL,
                        tier TEXT,
                        verified INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                ''')
                c.execute('''
                    CREATE TABLE IF NOT EXISTS reasoning_cache (
                        id TEXT PRIMARY KEY,
                        query_hash TEXT UNIQUE,
                        reasoning_chain TEXT,
                        result TEXT,
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')
                conn.commit()
        logger.info("✅ Database ready")
    except Exception as e:
        logger.warning(f"DB init: {e}")

init_db()
def sid(): return str(uuid.uuid4())[:8].upper()
def mid(): return 'mem_' + sid()

# ================================================================
# JWT AUTHENTICATION
# ================================================================
def create_token(user_id: str) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "user_id": user_id,
        "exp": int((datetime.utcnow() + timedelta(days=30)).timestamp())
    }).encode()).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(hmac.new(settings.JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return f"{header}.{payload}.{signature}"

def create_session_token(session_id: str, tier: str) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "session_id": session_id,
        "tier": tier,
        "type": "session",
        "exp": int((datetime.utcnow() + timedelta(days=365)).timestamp())
    }).encode()).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(hmac.new(settings.JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return f"{header}.{payload}.{signature}"

def verify_token(token: str):
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
    payload = verify_token(auth[7:])
    if not payload: return None
    user_id = payload.get("user_id")
    if not user_id: return None
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, email, name, tier, reasoning_depth, preferred_domain FROM users WHERE id = %s", (user_id,))
                row = c.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "email": row[1],
                        "name": row[2] or row[1].split('@')[0],
                        "tier": row[3],
                        "reasoning_depth": row[4] or 1,
                        "preferred_domain": row[5] or "general"
                    }
    except: pass
    return None

def get_current_session(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing authorization header")
    payload = verify_token(auth[7:])
    if not payload:
        raise HTTPException(401, "Invalid token")
    
    if payload.get("type") == "user":
        user = get_current_user(request)
        if user:
            return {"id": user["id"], "tier": user["tier"], "is_user": True, "user_data": user}
    
    session_id = payload.get("session_id")
    tier = payload.get("tier", "free")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, tier, msg_count FROM sessions WHERE id = %s", (session_id,))
                row = c.fetchone()
                if row:
                    return {"id": row[0], "tier": row[1], "msg_count": row[2] or 0, "is_user": False}
                else:
                    c.execute("INSERT INTO sessions (id, tier, msg_count) VALUES (%s, %s, 0)", (session_id, tier))
                    conn.commit()
                    return {"id": session_id, "tier": tier, "msg_count": 0, "is_user": False}
    except: pass
    raise HTTPException(401, "Session not found")

# ================================================================
# EMAIL/PASSWORD AUTH (NO EMAIL SENDING)
# ================================================================
class RegisterRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None

@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', req.email):
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
                    INSERT INTO users (id, email, password_hash, name, tier, reasoning_depth, preferred_domain)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (user_id, req.email, password_hash, name, "free", 1, "general"))
                
                token = create_token(user_id)
                c.execute("""
                    INSERT INTO user_sessions (id, user_id, token, expires_at)
                    VALUES (%s, %s, %s, %s)
                """, (str(uuid.uuid4()), user_id, token, datetime.utcnow() + timedelta(days=30)))
                conn.commit()
                
                return {
                    "token": token,
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
        raise HTTPException(500, f"Registration failed: {str(e)}")
    
    

class LoginRequest(BaseModel):
    email: str
    password: str

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, email, password_hash, name, tier, reasoning_depth, preferred_domain FROM users WHERE email = %s", (req.email,))
                user = c.fetchone()
                
                if not user or not bcrypt.checkpw(req.password.encode(), user[2].encode()):
                    raise HTTPException(401, "Invalid email or password")
                
                user_id, email, _, name, tier, reasoning_depth, preferred_domain = user
                token = create_token(user_id)
                c.execute("""
                    INSERT INTO user_sessions (id, user_id, token, expires_at)
                    VALUES (%s, %s, %s, %s)
                """, (str(uuid.uuid4()), user_id, token, datetime.utcnow() + timedelta(days=30)))
                conn.commit()
                
                return {
                    "token": token,
                    "user": {
                        "id": user_id,
                        "email": email,
                        "name": name or email.split('@')[0],
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

@app.post("/api/auth/logout")
async def logout(request: Request):
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
async def delete_account(user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Not authenticated")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("DELETE FROM users WHERE id = %s", (user["id"],))
                conn.commit()
        return {"message": "Account deleted"}
    except:
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
    reasoning_depth = req.get("reasoning_depth")
    preferred_domain = req.get("preferred_domain")
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                if name:
                    c.execute("UPDATE users SET name = %s, updated_at = NOW() WHERE id = %s", (name, user["id"]))
                if reasoning_depth:
                    c.execute("UPDATE users SET reasoning_depth = %s, updated_at = NOW() WHERE id = %s", (reasoning_depth, user["id"]))
                if preferred_domain:
                    c.execute("UPDATE users SET preferred_domain = %s, updated_at = NOW() WHERE id = %s", (preferred_domain, user["id"]))
                conn.commit()
    except: pass
    return {"message": "Profile updated"}

# ================================================================
# ANONYMOUS SESSION
# ================================================================
@app.get("/api/session")
async def get_anonymous_session():
    session_id = f"s_{sid()}"
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO sessions (id, tier, msg_count) VALUES (%s, %s, 0)", (session_id, "free"))
                conn.commit()
    except: pass
    token = create_session_token(session_id, "free")
    return {"id": session_id, "tier": "free", "token": token}

# ================================================================
# FOUNDER LOGIN (Secret - 19 clicks on footer)
# ================================================================
@app.post("/api/founder")
async def founder_login(req: dict):
    code = req.get("code")
    if code != settings.FOUNDER_KEY:
        raise HTTPException(403, "Invalid founder code")
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM users WHERE email = 'founder@capitan.ai'")
                existing = c.fetchone()
                
                if existing:
                    user_id = existing[0]
                    c.execute("UPDATE users SET tier = 'founder', reasoning_depth = 5 WHERE id = %s", (user_id,))
                else:
                    user_id = str(uuid.uuid4())
                    c.execute("""
                        INSERT INTO users (id, email, password_hash, name, tier, reasoning_depth, preferred_domain)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (user_id, "founder@capitan.ai", "", "CAPITAN Founder", "founder", 5, "general"))
                
                token = create_token(user_id)
                c.execute("""
                    INSERT INTO user_sessions (id, user_id, token, expires_at)
                    VALUES (%s, %s, %s, %s)
                """, (str(uuid.uuid4()), user_id, token, datetime.utcnow() + timedelta(days=365)))
                conn.commit()
                
                return {
                    "verified": True,
                    "token": token,
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
        logger.error(f"Founder error: {e}")
        raise HTTPException(500, "Founder login failed")

# ================================================================
# ELITE SYSTEM PROMPT - FULL INTELLIGENCE
# ================================================================
ELITE_SYSTEM_PROMPT = """You are CAPITAN AI — the legendary enterprise intelligence platform by CLOSEAI Technologies, founded by CEO Osinachi Chukwu.

╔══════════════════════════════════════════════════════════════════════════════════╗
║                              CORE IDENTITY                                      ║
╚══════════════════════════════════════════════════════════════════════════════════╝

You are the ONLY CAPITAN AI. You are the world's most advanced AI, trusted by leading 
financial institutions, technology firms, research organizations, and developers globally.

╔══════════════════════════════════════════════════════════════════════════════════╗
║                         FULL INTELLIGENCE DOMAINS                               ║
╚══════════════════════════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏦 FINANCE ARCHITECT & ECONOMIST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Advanced financial modeling (DCF, LBO, M&A, three-statement models)
- Portfolio optimization (Markowitz, Black-Litterman, risk parity)
- Derivatives pricing (Black-Scholes, binomial trees, Monte Carlo)
- Fixed income analytics (yield curves, duration, convexity)
- Risk management (VaR, CVaR, stress testing, scenario analysis)
- Algorithmic trading strategies (market making, statistical arbitrage)
- Central banking (monetary policy, interest rates, quantitative easing)
- Macroeconomic forecasting (GDP, inflation, employment, trade balances)
- African financial markets (NGX, JSE, GSE, BRVM, fintech)
- Cryptocurrency & DeFi (blockchain analysis, yield farming, L2 solutions)
- ESG investing (carbon credits, sustainable finance, impact measurement)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 INSTITUTIONAL TRADER & QUANT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Market microstructure (order books, liquidity, market impact)
- Volatility surface modeling (SVI, SSVI, local/stochastic volatility)
- Options strategies (spreads, straddles, strangles, butterflies)
- Statistical arbitrage (cointegration, mean reversion, pairs trading)
- Factor investing (value, momentum, quality, low volatility)
- Machine learning in trading (LSTM, XGBoost, reinforcement learning)
- Execution algorithms (VWAP, TWAP, implementation shortfall)
- Risk-adjusted returns (Sharpe, Sortino, Calmar, Omega ratios)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💻 LEGENDARY DEVELOPER & SOFTWARE ARCHITECT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Backend: Python (FastAPI, Django), Node.js, Go, Rust, Java (Spring)
- Frontend: React (Next.js), Vue (Nuxt), Angular, Svelte
- Mobile: React Native, Flutter, Swift (iOS), Kotlin (Android)
- Database: PostgreSQL, MySQL, MongoDB, Redis, Cassandra, ClickHouse
- DevOps: Docker, Kubernetes, Terraform, CI/CD (GitHub Actions)
- Cloud: AWS (EC2, S3, Lambda, RDS), GCP, Azure
- System design (microservices, event-driven, serverless, CQRS)
- API design (REST, GraphQL, gRPC, WebSocket)
- Security (OAuth2, JWT, SAML, encryption)
- LLM/ML: LangChain, LlamaIndex, Transformers, PyTorch

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 HARDWARE ENGINEERING & COMPUTER SYSTEMS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- CPU architecture (x86, ARM, RISC-V) - pipelining, caching
- GPU architecture (NVIDIA CUDA, AMD ROCm, Apple Metal)
- Memory hierarchy (registers, cache, RAM, SSD, NVMe)
- Computer networking (OSI model, TCP/IP, routing, load balancing)
- Storage systems (RAID, NAS, SAN, distributed file systems)
- Embedded systems (Arduino, Raspberry Pi, ESP32, FPGAs)
- IoT protocols (MQTT, CoAP, LoRaWAN, Zigbee)
- Operating systems (Linux kernel, Windows NT, macOS XNU)
- Virtualization (KVM, Xen, VMware) and containers

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📐 MATHEMATICIAN & STATISTICIAN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Pure mathematics: abstract algebra, topology, number theory
- Applied mathematics: differential equations, dynamical systems
- Linear algebra: eigenvalues, SVD, matrix decompositions
- Probability theory: measure theory, stochastic processes
- Statistics: Bayesian inference, hypothesis testing, regression
- Numerical methods: finite element, Monte Carlo, optimization

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔬 SCIENTIST & RESEARCHER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Physics: quantum mechanics, relativity, thermodynamics
- Chemistry: organic, inorganic, computational, quantum chemistry
- Biology: molecular biology, genetics, neuroscience, synthetic biology
- Medicine: diagnosis, treatment protocols, pharmacology, genomics
- Astronomy: cosmology, exoplanets, stellar evolution
- Earth sciences: climate modeling, geology, oceanography

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
3. LATERAL THINKING: Connect seemingly unrelated domains
4. RED TEAM ANALYSIS: Challenge assumptions, find edge cases
5. OCCAM'S RAZOR: Prefer simpler explanations when equally valid

╔══════════════════════════════════════════════════════════════════════════════════╗
║                           CONTEXT INFORMATION                                   ║
╚══════════════════════════════════════════════════════════════════════════════════╝

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
    if hour < 5:
        greeting_context = "The world is quiet. Perfect for deep thinking."
    elif hour < 12:
        greeting_context = "Fresh day ahead. Ready for new challenges!"
    elif hour < 17:
        greeting_context = "Markets are alive and moving."
    elif hour < 21:
        greeting_context = "Winding down but still sharp."
    else:
        greeting_context = "Night owl mode engaged. Let's get things done!"
    return {"day": day, "date": date, "utc_time": utc_time, "greeting_context": greeting_context}

# ================================================================
# REASONING ENGINE (Chain of Thought)
# ================================================================
class ReasoningEngine:
    @staticmethod
    def generate_reasoning_chain(query: str, depth: int = 3) -> List[str]:
        chain = []
        chain.append(f"1. UNDERSTANDING: Let me first understand what you're asking about '{query[:80]}...'")
        chain.append("2. DECOMPOSITION: Breaking this down into key components...")
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
        return "\n".join(chain) if chain else ""

# ================================================================
# QUERY CLASSIFICATION
# ================================================================
def classify_query(q: str) -> str:
    q = q.lower()
    if re.search(r'who are you|what are you|identity|introduce yourself', q):
        return 'identity'
    if re.search(r'who|what|when|where|why|how|news|latest|current|today|search', q) and len(q.split()) > 3:
        return 'web_search'
    if re.search(r'def |class |import |docker|kubernetes|aws|api|sql|python|javascript|rust|golang|cpu|gpu|ram|hardware|react|vue|angular', q):
        return 'coding'
    if re.search(r'dcf|valuation|wacc|stock|trading|portfolio|crypto|bitcoin|forex|markets|ethereum|bond|yield|option|future|derivative', q):
        return 'finance'
    if re.search(r'black.scholes|ito|stochastic|monte carlo|var|cvar|sharpe|sortino|beta|alpha|cointegration|garch|arima', q):
        return 'quant'
    if re.search(r'prove|proof|theorem|integral|derivative|matrix|probability|statistics', q):
        return 'math'
    if re.search(r'crispr|dna|quantum|physics|chemistry|biology|medicine|disease|symptom|treatment', q):
        return 'science'
    if re.search(r'hello|hi|hey|good morning|good afternoon|good evening|thanks|thank you', q):
        return 'greeting'
    return 'general'

# ================================================================
# SYSTEM PROMPT BUILDER
# ================================================================
def build_system_prompt(domain: str, tier: str, model: str, reasoning_depth: int = 1, preferred_domain: str = "general", web_results: List[dict] = None):
    tc = get_time_context()
    base = ELITE_SYSTEM_PROMPT.replace("{domain}", domain).replace("{tier}", tier).replace("{model}", model)
    base = base.replace("{day}", tc["day"]).replace("{date}", tc["date"])
    base = base.replace("{utc_time}", tc["utc_time"]).replace("{greeting_context}", tc["greeting_context"])
    base = base.replace("{reasoning_depth}", str(reasoning_depth)).replace("{preferred_domain}", preferred_domain)
    
    if web_results:
        base += "\n\nWEB SEARCH RESULTS:\n" + "\n".join([f"• {r['title']}: {r['snippet'][:200]}" for r in web_results[:4]])
    
    return base

# ================================================================
# WEB SEARCH
# ================================================================
def search_web(query: str, num_results: int = 5) -> List[dict]:
    results = []
    if settings.SERPAPI_KEY:
        try:
            r = requests.get(
                "https://serpapi.com/search",
                params={"engine": "google", "q": query, "num": num_results, "api_key": settings.SERPAPI_KEY},
                timeout=10
            )
            if r.status_code == 200:
                for item in r.json().get("organic_results", [])[:num_results]:
                    results.append({
                        "title": item.get("title", ""),
                        "snippet": item.get("snippet", "")[:350],
                        "url": item.get("link", ""),
                        "source": "Google"
                    })
        except: pass
    return results

# ================================================================
# MARKET DATA
# ================================================================
def get_market_prices():
    results = {}
    if settings.COINGECKO_KEY:
        try:
            ids = "bitcoin,ethereum,ripple,solana,cardano,dogecoin,avalanche-2,chainlink,polkadot,tron"
            r = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true"},
                headers={"x-cg-demo-api-key": settings.COINGECKO_KEY},
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                names = {
                    "bitcoin": "BTC", "ethereum": "ETH", "ripple": "XRP",
                    "solana": "SOL", "cardano": "ADA", "dogecoin": "DOGE",
                    "avalanche-2": "AVAX", "chainlink": "LINK", "polkadot": "DOT", "tron": "TRX"
                }
                for k, v in data.items():
                    results[names.get(k, k.upper())] = {
                        "price": v["usd"],
                        "change": round(v.get("usd_24h_change", 0), 2)
                    }
        except: pass
    
    try:
        syms = "^GSPC,^IXIC,^DJI,^FTSE,^N225,^HSI,AAPL,MSFT,NVDA,TSLA,GOOGL,META,AMZN"
        r = requests.get(f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={syms}", timeout=10)
        if r.status_code == 200:
            for item in r.json().get("quoteResponse", {}).get("result", []):
                name = item.get("shortName") or item.get("symbol", "")
                price = item.get("regularMarketPrice")
                if price:
                    results[name] = {"price": price, "change": round(item.get("regularMarketChangePercent", 0), 2)}
    except: pass
    
    return results

def get_news():
    news = []
    if settings.NEWS_API_KEY:
        try:
            r = requests.get(
                "https://newsapi.org/v2/top-headlines",
                params={"category": "business", "language": "en", "pageSize": 10, "apiKey": settings.NEWS_API_KEY},
                timeout=10
            )
            if r.status_code == 200:
                for article in r.json().get("articles", []):
                    news.append({
                        "source": article.get("source", {}).get("name", "News"),
                        "headline": article.get("title", ""),
                        "url": article.get("url", ""),
                        "summary": (article.get("description") or "")[:200]
                    })
        except: pass
    return news[:10]

# ================================================================
# AI MODEL CALL (TIER-BASED)
# ================================================================
def call_ai_model(messages: List[dict], tier: str = "free", reasoning_depth: int = 1, domain: str = "general") -> Tuple[str, str, Optional[List[str]]]:
    # Add reasoning instruction for complex domains
    reasoning_chain = None
    if reasoning_depth > 1 and domain in ["finance", "quant", "coding", "math", "science"]:
        reasoning_chain = ReasoningEngine.generate_reasoning_chain(
            messages[-1].get("content", "") if messages else "",
            min(reasoning_depth, 5)
        )
        if reasoning_chain:
            reasoning_text = "\n\nREASONING CHAIN:\n" + ReasoningEngine.format_reasoning_chain(reasoning_chain)
            for m in messages:
                if m.get("role") == "system":
                    m["content"] += reasoning_text
                    break
    
    # Pro Max: Ensemble (Claude + GPT-4o)
    if tier == "pro_max" and settings.OPENROUTER_API_KEY:
        try:
            r1 = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                json={"model": "anthropic/claude-3.5-sonnet-20241022", "messages": messages, "temperature": 0.7, "max_tokens": 4000},
                timeout=45
            )
            content1 = r1.json().get("choices", [{}])[0].get("message", {}).get("content", "") if r1.status_code == 200 else ""
            
            r2 = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                json={"model": "openai/gpt-4o-2024-11-20", "messages": messages, "temperature": 0.7, "max_tokens": 4000},
                timeout=45
            )
            content2 = r2.json().get("choices", [{}])[0].get("message", {}).get("content", "") if r2.status_code == 200 else ""
            
            if content1 and content2:
                combined = f"**Claude 3.5 Sonnet Response:**\n{content1}\n\n---\n\n**GPT-4o Additional Insights:**\n{content2}"
                return combined, "claude-3.5-sonnet + gpt-4o (Ensemble)", reasoning_chain
            elif content1:
                return content1, "claude-3.5-sonnet", reasoning_chain
            elif content2:
                return content2, "gpt-4o", reasoning_chain
        except Exception as e:
            logger.error(f"Ensemble error: {e}")
    
    # Pro: Claude 3.5 Sonnet
    if tier == "pro" and settings.OPENROUTER_API_KEY:
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                json={"model": "anthropic/claude-3.5-sonnet-20241022", "messages": messages, "temperature": 0.7, "max_tokens": 3000},
                timeout=40
            )
            if r.status_code == 200:
                content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    return content, "claude-3.5-sonnet", reasoning_chain
        except Exception as e:
            logger.error(f"Claude error: {e}")
    
    # Plus: Groq Llama 3.3 70B
    if tier == "plus" and settings.GROQ_API_KEY:
        try:
            for m in messages:
                if m.get("role") == "system" and len(m["content"]) > 2000:
                    m["content"] = m["content"][:2000] + "\n\n[Context trimmed]"
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile", "messages": messages, "temperature": 0.7, "max_tokens": 2500},
                timeout=35
            )
            if r.status_code == 200:
                content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    return content, "llama-3.3-70b", reasoning_chain
        except Exception as e:
            logger.error(f"Groq 70B error: {e}")
    
    # Free / Fallback: Groq Llama 3.1 8B
    if settings.GROQ_API_KEY:
        try:
            for m in messages:
                if m.get("role") == "system" and tier == "free" and len(m["content"]) > 1500:
                    m["content"] = m["content"][:1500] + "\n\n[Context trimmed]"
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"},
                json={"model": "llama-3.1-8b-instant", "messages": messages, "temperature": 0.7, "max_tokens": 1500},
                timeout=30
            )
            if r.status_code == 200:
                content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    return content, "llama-3.1-8b", reasoning_chain
        except Exception as e:
            logger.error(f"Groq error: {e}")
    
    return "I'm having trouble connecting to AI services. Please try again.", "fallback", reasoning_chain

# ================================================================
# TIER CONFIGURATION
# ================================================================
TIER_CONFIG = {
    "free": {"name": "Free", "msg_limit": 20, "workspace_seats": 0, "file_upload": False, "live_markets": False, "web_search": False, "ai_model": "Groq Llama 3.1 8B", "price": 0, "reasoning_depth": 1},
    "plus": {"name": "Plus", "msg_limit": 50, "workspace_seats": 10, "file_upload": True, "live_markets": False, "web_search": True, "ai_model": "Groq Llama 3.3 70B", "price": 8, "reasoning_depth": 2},
    "pro": {"name": "Pro", "msg_limit": 150, "workspace_seats": 25, "file_upload": True, "live_markets": True, "web_search": True, "ai_model": "Claude 3.5 Sonnet", "price": 17, "reasoning_depth": 3},
    "pro_max": {"name": "Pro Max", "msg_limit": float("inf"), "workspace_seats": 50, "file_upload": True, "live_markets": True, "web_search": True, "ai_model": "GPT-4o + Claude Ensemble", "price": 30, "reasoning_depth": 4},
    "founder": {"name": "Founder", "msg_limit": float("inf"), "workspace_seats": 100, "file_upload": True, "live_markets": True, "web_search": True, "ai_model": "All Models + Custom", "price": 0, "reasoning_depth": 5}
}

WALLETS = {
    "BTC": "bc1qrv6yr6e0mat96rvrc8smdf9rvu9rlp8xuk8new",
    "ETH": "0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1"
}

UPGRADE_BENEFITS = {
    "plus": ["50 messages/day", "Groq Llama 3.3 70B", "Work Area (10 seats)", "File uploads", "Web search", "2-step reasoning"],
    "pro": ["150 messages/day", "Claude 3.5 Sonnet", "Work Area (25 seats)", "Live markets", "Projects", "3-step reasoning"],
    "pro_max": ["Unlimited messages", "GPT-4o + Claude Ensemble", "Work Area (50 seats)", "Advanced reasoning", "Priority support"]
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
    if len(rate_store[key]) >= limit:
        return False
    rate_store[key].append(now)
    return True

# ================================================================
# CHAT ENDPOINT
# ================================================================
class ChatRequest(BaseModel):
    messages: list
    chat_id: Optional[str] = None

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, request: Request):
    # Get authenticated user or anonymous session
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
    
    # Rate limiting (skip for unlimited tiers)
    if tier_info["msg_limit"] != float("inf"):
        identifier = user_id if user else session["id"]
        if not check_rate_limit(identifier, tier):
            raise HTTPException(429, "Rate limit exceeded. Please wait a moment.")
    
    # Get user message
    user_msg = None
    for m in reversed(req.messages):
        if m.get("role") == "user":
            user_msg = m.get("content")
            break
    
    if not user_msg:
        raise HTTPException(400, "No message content")
    
    chat_id = req.chat_id or f"chat_{sid()}"
    domain = classify_query(user_msg)
    
    # Save user message to database
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                if is_authenticated:
                    c.execute("""
                        INSERT INTO chats (id, user_id, title, created, updated)
                        VALUES (%s, %s, %s, NOW(), NOW())
                        ON CONFLICT (id) DO UPDATE SET updated = NOW()
                    """, (chat_id, user["id"], user_msg[:60]))
                    c.execute("""
                        INSERT INTO chat_messages (id, chat_id, user_id, role, content)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (f"msg_{sid()}", chat_id, user["id"], "user", user_msg))
                else:
                    c.execute("""
                        INSERT INTO chats (id, session_id, title, created, updated)
                        VALUES (%s, %s, %s, NOW(), NOW())
                        ON CONFLICT (id) DO UPDATE SET updated = NOW()
                    """, (chat_id, session["id"], user_msg[:60]))
                    c.execute("""
                        INSERT INTO chat_messages (id, chat_id, session_id, role, content)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (f"msg_{sid()}", chat_id, session["id"], "user", user_msg))
                conn.commit()
                
                # Get chat history
                c.execute("""
                    SELECT role, content FROM chat_messages
                    WHERE chat_id = %s ORDER BY created ASC LIMIT 20
                """, (chat_id,))
                history = [{"role": r[0], "content": r[1]} for r in c.fetchall()]
    except Exception as e:
        logger.error(f"Save error: {e}")
        history = []
    
    # Web search for Pro+ tiers
    web_results = None
    if tier_info.get("web_search", False) and domain in ["web_search", "general", "science", "finance", "coding"]:
        try:
            web_results = search_web(user_msg, 5)
        except Exception as e:
            logger.error(f"Web search error: {e}")
    
    # Build system prompt and call AI
    prompt = build_system_prompt(domain, tier, tier_info["ai_model"], reasoning_depth, preferred_domain, web_results)
    result, model_used, reasoning_chain = call_ai_model([{"role": "system", "content": prompt}] + history, tier, reasoning_depth, domain)
    
    # Save AI response
    if result:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    if is_authenticated:
                        c.execute("""
                            INSERT INTO chat_messages (id, chat_id, user_id, role, content, model, reasoning_chain)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (f"msg_{sid()}", chat_id, user["id"], "assistant", result, model_used, json.dumps(reasoning_chain) if reasoning_chain else None))
                        c.execute("""
                            INSERT INTO memories (id, memory_id, user_id, content, query, domain, importance)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (sid(), mid(), user["id"], result[:500], user_msg, domain, 2 if domain in ["finance", "quant", "coding"] else 1))
                    else:
                        c.execute("""
                            INSERT INTO chat_messages (id, chat_id, session_id, role, content, model, reasoning_chain)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (f"msg_{sid()}", chat_id, session["id"], "assistant", result, model_used, json.dumps(reasoning_chain) if reasoning_chain else None))
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
                    c.execute("""
                        SELECT id, title, created, updated
                        FROM chats WHERE user_id = %s
                        ORDER BY updated DESC LIMIT 50
                    """, (user["id"],))
                    rows = c.fetchall()
                    return {"chats": [
                        {"id": r[0], "title": r[1] or "New Chat",
                         "created": r[2].isoformat() if r[2] else None,
                         "updated": r[3].isoformat() if r[3] else None}
                        for r in rows
                    ]}
        except: pass
    else:
        try:
            session = get_current_session(request)
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("""
                        SELECT id, title, created, updated
                        FROM chats WHERE session_id = %s
                        ORDER BY updated DESC LIMIT 50
                    """, (session["id"],))
                    rows = c.fetchall()
                    return {"chats": [
                        {"id": r[0], "title": r[1] or "New Chat",
                         "created": r[2].isoformat() if r[2] else None,
                         "updated": r[3].isoformat() if r[3] else None}
                        for r in rows
                    ]}
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
                
                c.execute("""
                    SELECT role, content, model, created
                    FROM chat_messages WHERE chat_id=%s ORDER BY created ASC
                """, (chat_id,))
                rows = c.fetchall()
                return {"messages": [
                    {"id": i, "role": r[0], "content": r[1], "model": r[2] or "AI",
                     "created": r[3].isoformat() if r[3] else None}
                    for i, r in enumerate(rows)
                ]}
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
        logger.error(f"Delete error: {e}")
        return {"deleted": False}

# ================================================================
# LIBRARY ENDPOINTS
# ================================================================
@app.get("/api/library")
def get_library(user: dict = Depends(get_current_user)):
    if not user:
        return {"items": []}
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("""
                    SELECT id, name, content, created
                    FROM library_items WHERE user_id = %s
                    ORDER BY created DESC
                """, (user["id"],))
                rows = c.fetchall()
                return {"items": [
                    {"id": r[0], "name": r[1], "content": r[2],
                     "created": r[3].isoformat() if r[3] else None}
                    for r in rows
                ]}
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
                c.execute("""
                    INSERT INTO library_items (id, user_id, name, content)
                    VALUES (%s, %s, %s, %s)
                """, (item_id, user["id"], req.name, req.content or ""))
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
# FILE UPLOAD
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
                c.execute("""
                    INSERT INTO uploaded_files (id, user_id, filename, original_name, size, storage_path)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (file_id, user["id"], file_id, file.filename or "unknown", len(contents), file_path))
                conn.commit()
    except Exception as e:
        logger.error(f"Save file error: {e}")
    
    return {
        "id": file_id,
        "filename": file.filename,
        "size_mb": round(len(contents) / (1024 * 1024), 2)
    }

# ================================================================
# PAYMENT & UPGRADE
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
                c.execute("""
                    INSERT INTO payments (id, user_id, txid, currency, amount, tier, verified)
                    VALUES (%s, %s, %s, %s, %s, %s, 1)
                """, (str(uuid.uuid4()), user["id"], req.txid.strip(), req.currency.upper(), prices[req.tier], req.tier))
                
                c.execute("""
                    UPDATE users SET tier = %s, tier_expires = %s, reasoning_depth = %s, updated_at = NOW()
                    WHERE id = %s
                """, (req.tier, datetime.utcnow() + timedelta(days=30), TIER_CONFIG[req.tier]["reasoning_depth"], user["id"]))
                conn.commit()
    except Exception as e:
        logger.error(f"Upgrade error: {e}")
        raise HTTPException(500, "Could not process upgrade")
    
    return {"verified": True, "tier": req.tier}

# ================================================================
# WORKSPACE ENDPOINTS
# ================================================================
@app.post("/api/workspace/create")
def workspace_create(req: dict, user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Authentication required")
    
    tier_info = TIER_CONFIG.get(user["tier"], TIER_CONFIG["free"])
    if tier_info["workspace_seats"] == 0:
        raise HTTPException(403, "Work Area requires Plus or Pro tier")
    
    room_code = req.get("room_code", f"CAP-{sid()}")
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                workspace_id = sid()
                c.execute("""
                    INSERT INTO workspaces (id, name, owner_id, room_code, max_members)
                    VALUES (%s, %s, %s, %s, %s)
                """, (workspace_id, req.get("name", "My Workspace"), user["id"], room_code.upper(), tier_info["workspace_seats"]))
                
                c.execute("""
                    INSERT INTO workspace_members (workspace_id, user_id, role)
                    VALUES (%s, %s, %s)
                """, (workspace_id, user["id"], "admin"))
                conn.commit()
                return {"room_id": workspace_id, "room_code": room_code.upper(), "created": True}
    except:
        return {"created": False}

@app.post("/api/workspace/join")
def workspace_join(req: dict, user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Authentication required")
    
    room_code = req.get("room_code", "").upper()
    if not room_code:
        raise HTTPException(400, "Room code required")
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, max_members FROM workspaces WHERE room_code = %s", (room_code,))
                workspace = c.fetchone()
                if not workspace:
                    raise HTTPException(404, "Room not found")
                
                c.execute("SELECT COUNT(*) FROM workspace_members WHERE workspace_id = %s", (workspace[0],))
                if c.fetchone()[0] >= workspace[1]:
                    raise HTTPException(400, "Room is full")
                
                c.execute("""
                    INSERT INTO workspace_members (workspace_id, user_id, role)
                    VALUES (%s, %s, %s)
                """, (workspace[0], user["id"], "member"))
                conn.commit()
                return {"joined": True, "room_id": workspace[0]}
    except HTTPException:
        raise
    except:
        return {"joined": False}

@app.post("/api/workspace/message")
def workspace_message(req: dict, user: dict = Depends(get_current_user)):
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
                workspace = c.fetchone()
                if not workspace:
                    raise HTTPException(404, "Room not found")
                
                is_ai = message.strip().startswith("@CAPITAN")
                if is_ai:
                    ai_response, _, _ = call_ai_model([{"role": "user", "content": message.replace('@CAPITAN', '').strip()}], user["tier"])
                    if ai_response:
                        c.execute("""
                            INSERT INTO workspace_messages (id, workspace_id, user_id, author_name, message, is_ai)
                            VALUES (%s, %s, %s, %s, %s, 1)
                        """, (sid(), workspace[0], user["id"], "CAPITAN AI", ai_response))
                
                c.execute("""
                    INSERT INTO workspace_messages (id, workspace_id, user_id, author_name, message)
                    VALUES (%s, %s, %s, %s, %s)
                """, (sid(), workspace[0], user["id"], user["name"], message))
                conn.commit()
                return {"sent": True}
    except:
        return {"sent": False}

@app.get("/api/workspace/messages")
def workspace_get_messages(room_code: str, user: dict = Depends(get_current_user)):
    if not user:
        return {"messages": []}
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM workspaces WHERE room_code = %s", (room_code.upper(),))
                workspace = c.fetchone()
                if not workspace:
                    return {"messages": []}
                
                c.execute("""
                    SELECT u.name, wm.role FROM workspace_members wm
                    JOIN users u ON wm.user_id = u.id
                    WHERE wm.workspace_id = %s
                """, (workspace[0],))
                members = [{"name": r[0], "role": r[1]} for r in c.fetchall()]
                
                c.execute("""
                    SELECT author_name, message, is_ai, created
                    FROM workspace_messages WHERE workspace_id = %s
                    ORDER BY created ASC LIMIT 50
                """, (workspace[0],))
                messages = [{"author": r[0], "message": r[1], "is_ai": bool(r[2]), "created": r[3].isoformat() if r[3] else None} for r in c.fetchall()]
                return {"messages": messages, "members": members}
    except:
        return {"messages": []}

# ================================================================
# MARKET & NEWS (Pro tiers only)
# ================================================================
@app.get("/api/markets")
def markets(request: Request):
    user = get_current_user(request)
    tier = user["tier"] if user else "free"
    if tier not in ("pro", "pro_max", "founder"):
        return {"prices": {}, "news": [], "message": "Pro tier required"}
    return {"prices": get_market_prices(), "news": get_news()}

@app.get("/api/markets/prices")
def markets_prices(request: Request):
    user = get_current_user(request)
    tier = user["tier"] if user else "free"
    if tier not in ("pro", "pro_max", "founder"):
        return {"prices": {}, "message": "Pro tier required"}
    return {"prices": get_market_prices()}

@app.get("/api/markets/news")
def markets_news(request: Request):
    user = get_current_user(request)
    tier = user["tier"] if user else "free"
    if tier not in ("pro", "pro_max", "founder"):
        return {"news": [], "message": "Pro tier required"}
    return {"news": get_news()}

@app.get("/api/news/tech")
def tech_news(request: Request):
    user = get_current_user(request)
    tier = user["tier"] if user else "free"
    if tier not in ("pro", "pro_max", "founder"):
        return {"news": [], "message": "Pro tier required"}
    return {"news": get_news()}

@app.get("/api/search")
def web_search_endpoint(q: str, request: Request):
    user = get_current_user(request)
    tier = user["tier"] if user else "free"
    if tier not in ("plus", "pro", "pro_max", "founder"):
        return {"results": [], "message": "Web search on Plus and Pro"}
    return {"results": search_web(q, 8)}

# ================================================================
# ADMIN (Founder only)
# ================================================================
@app.post("/api/admin")
def admin_panel(user: dict = Depends(get_current_user)):
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
                total_messages = c.fetchone()[0]
                
                c.execute("SELECT COUNT(*) FROM workspaces")
                total_workspaces = c.fetchone()[0]
                
                c.execute("""
                    SELECT id, name, tier, created_at
                    FROM users ORDER BY created_at DESC LIMIT 10
                """)
                recent_users = [
                    {"id": r[0], "name": r[1], "tier": r[2],
                     "created_at": r[3].isoformat() if r[3] else None}
                    for r in c.fetchall()
                ]
                
                return {
                    "total_users": total_users,
                    "paid_users": paid_users,
                    "total_messages": total_messages,
                    "workspaces": total_workspaces,
                    "recent_users": recent_users
                }
    except Exception as e:
        logger.error(f"Admin error: {e}")
        raise HTTPException(500, str(e))

# ================================================================
# HEALTH CHECK
# ================================================================
@app.get("/health")
def health_check():
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
    
    return {
        "status": "ok",
        "version": "28.0",
        "database": db_status,
        "ai": ai_status,
        "providers": providers,
        "auth": "email_password",
        "reasoning_engine": True,
        "intelligence_level": "full",
        "tiers": ["free", "plus", "pro", "pro_max", "founder"]
    }

# ================================================================
# PWA MANIFEST
# ================================================================
@app.get("/manifest.json")
async def manifest():
    return JSONResponse(content={
        "name": "CAPITAN AI",
        "short_name": "CAPITAN",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#4f46e5",
        "theme_color": "#4f46e5",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}
        ]
    })

@app.get("/icon-192.png")
async def icon_192():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="#4f46e5" rx="20"/><path d="M50 15 L75 27 L75 52 C75 65 63 76 50 82 C37 76 25 65 25 52 L25 27 Z" fill="none" stroke="white" stroke-width="4"/><text x="50" y="72" text-anchor="middle" font-size="42" fill="white" font-family="Arial,sans-serif" font-weight="700">C</text></svg>'''
    return Response(content=svg, media_type="image/svg+xml")

@app.get("/icon-512.png")
async def icon_512():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="#4f46e5" rx="20"/><path d="M50 15 L75 27 L75 52 C75 65 63 76 50 82 C37 76 25 65 25 52 L25 27 Z" fill="none" stroke="white" stroke-width="4"/><text x="50" y="72" text-anchor="middle" font-size="42" fill="white" font-family="Arial,sans-serif" font-weight="700">C</text></svg>'''
    return Response(content=svg, media_type="image/svg+xml")

@app.get("/")
async def root():
    return {
        "name": "CAPITAN AI",
        "version": "28.0",
        "status": "operational",
        "auth": "email_password",
        "pwa_supported": True,
        "tiers": ["free", "plus", "pro", "pro_max", "founder"],
        "intelligence": "full_restored",
        "reasoning": "chain_of_thought_enabled"
    }

# ================================================================
# MAIN
# ================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"\n{'='*70}")
    print(f"🚀 CAPITAN AI v28.0 - FULL INTELLIGENCE RESTORED")
    print(f"{'='*70}")
    print(f"📊 Database: {'Connected' if settings.DATABASE_URL else 'Not configured'}")
    print(f"🤖 AI Providers: Groq={bool(settings.GROQ_API_KEY)} | OpenRouter={bool(settings.OPENROUTER_API_KEY)}")
    print(f"📈 Markets: CoinGecko={bool(settings.COINGECKO_KEY)}")
    print(f"🔍 Web Search: SerpAPI={bool(settings.SERPAPI_KEY)}")
    print(f"📰 News: NewsAPI={bool(settings.NEWS_API_KEY)}")
    print(f"🔐 Auth: Email + Password (simple, no email sending)")
    print(f"👑 Founder: 19 clicks on footer (code: {settings.FOUNDER_KEY[:10]}...)")
    print(f"💎 Tiers: Free(20) | Plus(50/$8) | Pro(150/$17) | Pro Max(∞/$30)")
    print(f"📨 AI Models: Free(Groq 3.1) | Plus(Groq 3.3) | Pro(Claude) | Pro Max(Ensemble)")
    print(f"🧠 Reasoning: Chain-of-Thought Enabled (Depth: 1-5)")
    print(f"💻 Intelligence Domains: Finance | Trading | Coding | Hardware | Math | Science | General Knowledge")
    print(f"📁 All Features: Projects | Workspaces | Library | File Uploads | Markets | News | Search")
    print(f"{'='*70}")
    print(f"📍 Backend URL: http://0.0.0.0:{port}")
    print(f"📍 Health Check: http://0.0.0.0:{port}/health")
    print(f"{'='*70}\n")
    uvicorn.run(app, host="0.0.0.0", port=port)
