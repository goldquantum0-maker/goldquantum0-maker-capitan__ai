"""
CAPITAN AI — Enterprise Backend v29.0
CLOSEAI Technologies
Warm, Expert Trading Personality | Elite Reasoning | File Analysis | Workspaces
"""

import os, re, json, uuid, time, hmac, hashlib, base64, secrets, requests, logging, bcrypt
import PyPDF2, docx, openpyxl, io
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple
from contextlib import contextmanager

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
app = FastAPI(title="CAPITAN AI API", version="29.0")

class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET: str
    FOUNDER_KEY: str
    FRONTEND_URL: str = "https://capitanai.goldquantum0.workers.dev"
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    COINGECKO_KEY: str = ""
    SERPAPI_KEY: str = ""
    NEWS_API_KEY: str = ""
    FINNHUB_API_KEY: str = ""
    ETHERSCAN_API_KEY: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# ================================================================
# LOGGING
# ================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ================================================================
# DATABASE – fixed context manager
# ================================================================
@contextmanager
def get_db():
    conn = None
    last_err = None
    for attempt in range(3):
        try:
            conn = psycopg2.connect(settings.DATABASE_URL, connect_timeout=10)
            break
        except Exception as e:
            last_err = e
            logger.warning(f"DB attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(2)
    if conn is None:
        raise last_err
    try:
        yield conn
    finally:
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
                        daily_msg_count INTEGER DEFAULT 0,
                        msg_reset_date DATE,
                        tier_expires TIMESTAMP,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                ''')
                c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS reasoning_depth INTEGER DEFAULT 1")
                c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_domain TEXT DEFAULT 'general'")
                c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_msg_count INTEGER DEFAULT 0")
                c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS msg_reset_date DATE")
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
                        daily_msg_count INTEGER DEFAULT 0,
                        msg_reset_date DATE,
                        created TIMESTAMP DEFAULT NOW(),
                        updated TIMESTAMP DEFAULT NOW()
                    )
                ''')
                c.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS daily_msg_count INTEGER DEFAULT 0")
                c.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS msg_reset_date DATE")
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
                c.execute("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS reasoning_chain TEXT")
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
                        extracted_text TEXT,
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')
                c.execute("ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS extracted_text TEXT")
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
# PASSWORD HASHING – bcrypt
# ================================================================
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except:
        return False

# ================================================================
# JWT AUTHENTICATION
# ================================================================
def create_token(user_id: str) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "user_id": user_id,
        "type": "user",
        "exp": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())
    }).encode()).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(hmac.new(settings.JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return f"{header}.{payload}.{signature}"

def create_session_token(session_id: str, tier: str) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "session_id": session_id,
        "tier": tier,
        "type": "session",
        "exp": int((datetime.now(timezone.utc) + timedelta(days=365)).timestamp())
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
        if data.get("exp", 0) < datetime.now(timezone.utc).timestamp(): return None
        return data
    except: return None

def get_current_user(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "): return None
    token = auth[7:]
    payload = verify_token(token)
    if not payload: return None
    user_id = payload.get("user_id")
    if not user_id: return None
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT 1 FROM user_sessions WHERE token = %s", (token,))
                if not c.fetchone():
                    return None
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
    token = auth[7:]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(401, "Invalid token")
    
    if payload.get("type") == "user":
        user = get_current_user(request)
        if user:
            return {"id": user["id"], "tier": user["tier"], "is_user": True, "user_data": user}
    
    session_id = payload.get("session_id")
    tier = payload.get("tier", "guest")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, tier, daily_msg_count, msg_reset_date FROM sessions WHERE id = %s", (session_id,))
                row = c.fetchone()
                if row:
                    return {"id": row[0], "tier": row[1], "daily_msg_count": row[2], "msg_reset_date": row[3], "is_user": False}
                else:
                    c.execute("INSERT INTO sessions (id, tier, daily_msg_count, msg_reset_date) VALUES (%s, %s, 0, CURRENT_DATE)", (session_id, tier))
                    conn.commit()
                    return {"id": session_id, "tier": tier, "daily_msg_count": 0, "is_user": False}
    except: pass
    raise HTTPException(401, "Session not found")

# ================================================================
# AUTH ENDPOINTS (unchanged)
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
                
                password_hash = hash_password(req.password)
                user_id = str(uuid.uuid4())
                name = req.name or req.email.split('@')[0]
                c.execute("""
                    INSERT INTO users (id, email, password_hash, name, tier, reasoning_depth, preferred_domain, daily_msg_count, msg_reset_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 0, CURRENT_DATE)
                """, (user_id, req.email, password_hash, name, "free", 1, "general"))
                
                token = create_token(user_id)
                c.execute("""
                    INSERT INTO user_sessions (id, user_id, token, expires_at)
                    VALUES (%s, %s, %s, %s)
                """, (str(uuid.uuid4()), user_id, token, datetime.now(timezone.utc) + timedelta(days=30)))
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
                
                if not user or not verify_password(req.password, user[2]):
                    raise HTTPException(401, "Invalid email or password")
                
                user_id, email, _, name, tier, reasoning_depth, preferred_domain = user
                token = create_token(user_id)
                c.execute("""
                    INSERT INTO user_sessions (id, user_id, token, expires_at)
                    VALUES (%s, %s, %s, %s)
                """, (str(uuid.uuid4()), user_id, token, datetime.now(timezone.utc) + timedelta(days=30)))
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
    
    valid_domains = ["general", "finance", "coding", "trading", "science", "math"]
    if preferred_domain and preferred_domain not in valid_domains:
        raise HTTPException(400, "Invalid domain")
    tier_info = TIER_CONFIG.get(user["tier"], TIER_CONFIG["free"])
    max_depth = tier_info["reasoning_depth"]
    if reasoning_depth and (reasoning_depth < 1 or reasoning_depth > max_depth):
        raise HTTPException(400, f"Reasoning depth must be between 1 and {max_depth}")
    
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
                c.execute("INSERT INTO sessions (id, tier, daily_msg_count, msg_reset_date) VALUES (%s, %s, 0, CURRENT_DATE)", (session_id, "guest"))
                conn.commit()
    except: pass
    token = create_session_token(session_id, "guest")
    return {"id": session_id, "tier": "guest", "token": token}

# ================================================================
# FOUNDER LOGIN
# ================================================================
@app.post("/api/founder")
async def founder_login(req: dict, request: Request):
    identifier = request.client.host
    if not check_rate_limit(identifier, "founder_attempt", limit=5):
        raise HTTPException(429, "Too many attempts")
    
    code = req.get("code", "")
    if not hmac.compare_digest(code, settings.FOUNDER_KEY):
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
                    dummy_hash = hash_password("founder_sentinel")
                    c.execute("""
                        INSERT INTO users (id, email, password_hash, name, tier, reasoning_depth, preferred_domain, daily_msg_count, msg_reset_date)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, 0, CURRENT_DATE)
                    """, (user_id, "founder@capitan.ai", dummy_hash, "CAPITAN Founder", "founder", 5, "general"))
                
                token = create_token(user_id)
                c.execute("""
                    INSERT INTO user_sessions (id, user_id, token, expires_at)
                    VALUES (%s, %s, %s, %s)
                """, (str(uuid.uuid4()), user_id, token, datetime.now(timezone.utc) + timedelta(days=365)))
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
# REWRITTEN SYSTEM PROMPT – Warm, Trading-Focused
# ================================================================
CORE_INSTRUCTIONS = """You are CAPITAN AI – a warm, street‑smart, elite trading and intelligence assistant created by CLOSEAI Technologies under the leadership of CEO Osinachi Chukwu.

Your voice is friendly, confident, and slightly casual – like a trusted trading partner who's been through every market cycle. You use emojis naturally when the vibe fits 🌞🔥📉📈. You never sound corporate or robotic. You make complex ideas feel simple and exciting.

You are a master of ALL financial markets: forex, equities, crypto, commodities, bonds, derivatives. You understand market microstructure, bank positioning (COT reports, dark pool prints, order flow), and you can give actionable trade ideas for swing trading, position trading, and scalping. You always remind users that your analysis is not guaranteed – they should manage risk and do their own due diligence.

You are also an expert in:
- Software development (Python, JavaScript, Go, Rust, cloud, DevOps)
- Hardware & systems (CPU/GPU, embedded, IoT)
- Advanced mathematics & statistics
- All sciences (physics, chemistry, biology, medicine)
- Cybersecurity (penetration testing, threat modeling, encryption)

RESPONSE RULES:
1. USER FIRST: Always answer the user's last question directly. Even if they said hello, if they also asked something, address the question immediately. A quick greeting is fine, but never *only* a greeting when a real question is present.
2. BE WARM AND ENGAGING: Use natural language, contractions, and occasional emojis. Sound like a real person, not a textbook.
3. LEAD WITH VALUE: Give the key insight or signal first, then explain.
4. SHOW YOUR WORK: For trading ideas, explain what you see (levels, volume, bank positioning) and why it matters.
5. FINANCIAL DISCLAIMER: Always add a gentle reminder: "This is analysis, not guaranteed profit – manage your risk."
6. STAY HONEST: If you're unsure, say so. Never bluff.

REASONING FRAMEWORKS (internal):
- First‑principles thinking
- Bayesian reasoning
- Lateral thinking
- Red team analysis (for security)
- Occam's razor
"""

DOMAIN_CATALOG = """
================================================================================
  TRADING & MARKET ANALYSIS (YOUR CORE)
================================================================================
- Real‑time market analysis (forex, equities, crypto, commodities, bonds)
- Bank positioning: COT reports, dark pool prints, options flow
- Swing trading setups: key levels, Fibonacci, volume profile
- Position trading: macro trends, central bank policy
- Scalping: order book, tape reading, momentum
- Risk management: position sizing, stop‑loss, R:R
- Technical analysis: moving averages, RSI, MACD, Bollinger Bands, Elliott Wave
- Fundamental analysis: earnings, economic data, geopolitical events
- Algorithmic trading: Python backtesting, execution algos
- Market psychology: fear & greed, sentiment analysis

================================================================================
  FINANCE & ECONOMICS
================================================================================
- DCF, LBO, M&A models
- Portfolio theory, risk parity
- Derivatives pricing (Black‑Scholes, Monte Carlo)
- Fixed income (yield curves, duration)
- Macro forecasting (GDP, inflation, employment)

================================================================================
  SOFTWARE ENGINEERING & CYBERSECURITY
================================================================================
- Full‑stack development (Python, JavaScript, Go, Rust)
- Cloud architecture (AWS, GCP, Azure)
- DevOps: Docker, Kubernetes, CI/CD
- Security: penetration testing, threat modeling, encryption, OWASP
- Incident response & digital forensics

================================================================================
  HARDWARE & SYSTEMS
================================================================================
- CPU/GPU architecture, embedded systems, IoT
- Networking, storage, OS internals

================================================================================
  MATHEMATICS & SCIENCE
================================================================================
- Advanced calculus, linear algebra, probability
- Physics, chemistry, biology, medicine
"""

def get_time_context():
    now = datetime.now(timezone.utc)
    hour = now.hour
    day = now.strftime("%A")
    date = now.strftime("%B %d, %Y")
    utc_time = now.strftime("%H:%M UTC")
    if hour < 5:
        greeting_context = "Quiet hours, perfect for deep analysis."
    elif hour < 12:
        greeting_context = "Markets waking up – let's see where the money's flowing."
    elif hour < 17:
        greeting_context = "Full throttle – the big players are moving."
    elif hour < 21:
        greeting_context = "Winding down but still sharp."
    else:
        greeting_context = "Night owl mode – let's find those overnight moves."
    return {"day": day, "date": date, "utc_time": utc_time, "greeting_context": greeting_context}

def build_system_prompt(domain: str, tier: str, model: str, reasoning_depth: int = 1, preferred_domain: str = "general", web_results: List[dict] = None, user_query: str = ""):
    tc = get_time_context()
    base = CORE_INSTRUCTIONS.replace("{domain}", domain).replace("{tier}", tier).replace("{model}", model)
    base = base.replace("{day}", tc["day"]).replace("{date}", tc["date"])
    base = base.replace("{utc_time}", tc["utc_time"]).replace("{greeting_context}", tc["greeting_context"])
    base = base.replace("{reasoning_depth}", str(reasoning_depth)).replace("{preferred_domain}", preferred_domain)
    
    if user_query:
        base += f"\n\nUSER REQUEST: {user_query}"
    
    if tier in ("pro", "pro_max", "founder"):
        base += "\n\n" + DOMAIN_CATALOG
    
    if web_results:
        base += "\n\nWEB SEARCH RESULTS:\n" + "\n".join([f"- {r['title']}: {r['snippet'][:200]}" for r in web_results[:4]])
    
    return base

# ================================================================
# RATE LIMITING (with cleanup)
# ================================================================
rate_store = {}
_cleanup_counter = 0
def check_rate_limit(id: str, key: str = "default", limit: int = 20) -> bool:
    global _cleanup_counter
    now = time.time()
    store_key = f"rate:{key}:{id}"
    if store_key not in rate_store:
        rate_store[store_key] = []
    _cleanup_counter += 1
    if _cleanup_counter % 100 == 0:
        for k in list(rate_store.keys()):
            rate_store[k] = [t for t in rate_store[k] if now - t < 120]
            if not rate_store[k]:
                del rate_store[k]
    rate_store[store_key] = [t for t in rate_store[store_key] if now - t < 60]
    if len(rate_store[store_key]) >= limit:
        return False
    rate_store[store_key].append(now)
    return True

# ================================================================
# DAILY MESSAGE LIMIT ENFORCEMENT
# ================================================================
def enforce_daily_limit(user: dict = None, session: dict = None):
    today = datetime.now(timezone.utc).date()
    if user:
        tier = user["tier"]
        tier_info = TIER_CONFIG.get(tier, TIER_CONFIG["free"])
        daily_limit = tier_info["msg_limit"]
        if daily_limit == float("inf"):
            return
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT daily_msg_count, msg_reset_date FROM users WHERE id = %s", (user["id"],))
                row = c.fetchone()
                count, reset_date = row[0] or 0, row[1]
                if reset_date != today:
                    count = 0
                if count >= daily_limit:
                    raise HTTPException(429, "Daily message limit reached. Upgrade your plan.")
                c.execute("UPDATE users SET daily_msg_count = %s, msg_reset_date = %s WHERE id = %s",
                          (count + 1, today, user["id"]))
                conn.commit()
    elif session:
        tier = session["tier"]
        tier_info = TIER_CONFIG.get(tier, TIER_CONFIG["guest"])
        daily_limit = tier_info["msg_limit"]
        if daily_limit == float("inf"):
            return
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT daily_msg_count, msg_reset_date FROM sessions WHERE id = %s", (session["id"],))
                row = c.fetchone()
                count, reset_date = row[0] or 0, row[1]
                if reset_date != today:
                    count = 0
                if count >= daily_limit:
                    raise HTTPException(429, "Daily message limit reached.")
                c.execute("UPDATE sessions SET daily_msg_count = %s, msg_reset_date = %s WHERE id = %s",
                          (count + 1, today, session["id"]))
                conn.commit()

# ================================================================
# QUERY CLASSIFICATION
# ================================================================
def classify_query(q: str) -> str:
    q = q.lower()
    if re.search(r'who are you|what are you|identity|introduce yourself', q):
        return 'identity'
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

def needs_web_search(q: str) -> bool:
    return bool(re.search(r'latest|current|today|news|right now|recent|202[3-9]', q.lower()))

# ================================================================
# REASONING ENGINE
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
# AI MODEL CALL
# ================================================================
def call_ai_model(messages: List[dict], tier: str = "free", reasoning_depth: int = 1, domain: str = "general") -> Tuple[str, str, Optional[List[str]]]:
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
    
    if tier == "plus" and settings.GROQ_API_KEY:
        try:
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
    
    if settings.GROQ_API_KEY:
        try:
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
    "guest": {"name": "Guest", "msg_limit": 10, "workspace_seats": 0, "file_upload": False, "live_markets": False, "web_search": False, "ai_model": "Groq Llama 3.1 8B", "price": 0, "reasoning_depth": 1},
    "free": {"name": "Free", "msg_limit": 20, "workspace_seats": 0, "file_upload": False, "live_markets": False, "web_search": False, "ai_model": "Groq Llama 3.1 8B", "price": 0, "reasoning_depth": 1},
    "plus": {"name": "Plus", "msg_limit": 50, "workspace_seats": 10, "file_upload": True, "live_markets": False, "web_search": True, "ai_model": "Groq Llama 3.3 70B", "price": 8, "reasoning_depth": 2},
    "pro": {"name": "Pro", "msg_limit": 100, "workspace_seats": 25, "file_upload": True, "live_markets": True, "web_search": True, "ai_model": "Claude 3.5 Sonnet", "price": 17, "reasoning_depth": 3},
    "pro_max": {"name": "Pro Max", "msg_limit": float("inf"), "workspace_seats": 50, "file_upload": True, "live_markets": True, "web_search": True, "ai_model": "GPT-4o + Claude Ensemble", "price": 30, "reasoning_depth": 4},
    "founder": {"name": "Founder", "msg_limit": float("inf"), "workspace_seats": 100, "file_upload": True, "live_markets": True, "web_search": True, "ai_model": "All Models + Custom", "price": 0, "reasoning_depth": 5}
}

WALLETS = {
    "BTC": "bc1qrv6yr6e0mat96rvrc8smdf9rvu9rlp8xuk8new",
    "ETH": "0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1"
}

# ================================================================
# FILE EXTRACTION
# ================================================================
def extract_text_from_file(file_path: str, original_name: str) -> str:
    ext = original_name.rsplit('.', 1)[-1].lower() if '.' in original_name else ''
    try:
        if ext in ('txt', 'md', 'json', 'csv', 'py', 'js', 'html', 'css'):
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        elif ext == 'pdf':
            text = []
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text.append(page.extract_text() or '')
            return '\n'.join(text)
        elif ext == 'docx':
            doc = docx.Document(file_path)
            return '\n'.join([p.text for p in doc.paragraphs])
        elif ext == 'xlsx':
            wb = openpyxl.load_workbook(file_path, data_only=True)
            sheets_text = []
            for name in wb.sheetnames:
                ws = wb[name]
                for row in ws.iter_rows(values_only=True):
                    row_text = ' '.join([str(c) if c is not None else '' for c in row])
                    sheets_text.append(row_text)
            return '\n'.join(sheets_text)
        else:
            return ''
    except Exception as e:
        logger.error(f"File extraction error: {e}")
        return ''

# ================================================================
# FILE UPLOAD (with text extraction)
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
    
    extracted = extract_text_from_file(file_path, file.filename or "unknown")
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("""
                    INSERT INTO uploaded_files (id, user_id, filename, original_name, size, storage_path, extracted_text)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (file_id, user["id"], file_id, file.filename or "unknown", len(contents), file_path, extracted[:50000]))
                conn.commit()
    except Exception as e:
        logger.error(f"Save file error: {e}")
    
    return {
        "id": file_id,
        "filename": file.filename,
        "size_mb": round(len(contents) / (1024 * 1024), 2),
        "extracted": bool(extracted)
    }

# ================================================================
# CHAT ENDPOINT (with file analysis & memories)
# ================================================================
class ChatRequest(BaseModel):
    messages: list
    chat_id: Optional[str] = None

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, request: Request):
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
    
    tier_info = TIER_CONFIG.get(tier, TIER_CONFIG["guest"])
    
    enforce_daily_limit(user, session)
    
    identifier = user_id if user else session["id"]
    if not check_rate_limit(identifier, tier, tier_info.get("per_min_limit", 20)):
        raise HTTPException(429, "Rate limit exceeded. Please wait a moment.")
    
    user_msg = None
    for m in reversed(req.messages):
        if m.get("role") == "user":
            user_msg = m.get("content")
            break
    if not user_msg:
        raise HTTPException(400, "No message content")
    
    chat_id = req.chat_id or f"chat_{sid()}"
    domain = classify_query(user_msg)
    web_search_needed = needs_web_search(user_msg)
    
    # If user message mentions uploaded file, fetch extracted text
    file_text = ""
    if "[Uploaded document:" in user_msg:
        fname_match = re.search(r'\[Uploaded document:\s*(.*?)\]', user_msg)
        if fname_match:
            fname = fname_match.group(1).strip()
            if is_authenticated:
                with get_db() as conn:
                    with conn.cursor() as c:
                        c.execute("SELECT extracted_text FROM uploaded_files WHERE original_name = %s AND user_id = %s ORDER BY created DESC LIMIT 1", (fname, user["id"]))
                        row = c.fetchone()
                        if row and row[0]:
                            file_text = row[0]
                            user_msg += "\n\n[DOCUMENT CONTENT]\n" + file_text[:30000]
    
    # Save user message
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
    except Exception as e:
        logger.error(f"Save error: {e}")
    
    # Fetch recent 20 messages
    history = []
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("""
                    SELECT role, content FROM (
                        SELECT role, content, created FROM chat_messages
                        WHERE chat_id = %s ORDER BY created DESC LIMIT 20
                    ) recent ORDER BY created ASC
                """, (chat_id,))
                history = [{"role": r[0], "content": r[1]} for r in c.fetchall()]
    except: pass
    
    # Web search
    web_results = None
    if tier_info.get("web_search", False) and web_search_needed:
        try:
            web_results = search_web(user_msg, 5)
        except Exception as e:
            logger.error(f"Web search error: {e}")
    
    # Retrieve relevant memories
    memory_text = ""
    if is_authenticated:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("SELECT content FROM memories WHERE user_id = %s AND domain = %s ORDER BY created DESC LIMIT 3", (user["id"], domain))
                    rows = c.fetchall()
                    if rows:
                        memory_text = "\n\n[RELEVANT MEMORIES]\n" + "\n".join([r[0][:200] for r in rows])
        except: pass
    
    # Build prompt
    prompt = build_system_prompt(domain, tier, tier_info["ai_model"], reasoning_depth, preferred_domain, web_results, user_query=user_msg)
    if memory_text:
        prompt += "\n" + memory_text
    
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
# CHAT HISTORY
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
# LIBRARY (with improved error feedback)
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
    except Exception as e:
        logger.error(f"Library get error: {e}")
        raise HTTPException(500, "Could not load saved items")

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
    except Exception as e:
        logger.error(f"Library create error: {e}")
        raise HTTPException(500, "Could not save item")

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
    except Exception as e:
        logger.error(f"Library delete error: {e}")
        raise HTTPException(500, "Could not delete item")

# ================================================================
# PAYMENT & UPGRADE – with real verification
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

def verify_transaction(txid: str, currency: str, expected_tier: str) -> bool:
    prices = {"plus": 8, "pro": 17, "pro_max": 30}
    expected_amount = prices.get(expected_tier, 0)
    if currency == "BTC":
        try:
            r = requests.get(f"https://blockchain.info/rawtx/{txid}", timeout=15)
            if r.status_code == 200:
                tx = r.json()
                for out in tx.get("out", []):
                    if out.get("addr") == WALLETS["BTC"] and out.get("value", 0) / 1e8 >= expected_amount * 0.99:
                        return True
        except: pass
        return False
    elif currency == "ETH":
        if not settings.ETHERSCAN_API_KEY:
            return False
        try:
            r = requests.get(f"https://api.etherscan.io/api?module=proxy&action=eth_getTransactionByHash&txhash={txid}&apikey={settings.ETHERSCAN_API_KEY}", timeout=15)
            if r.status_code == 200:
                tx = r.json().get("result", {})
                if tx and tx.get("to", "").lower() == WALLETS["ETH"].lower():
                    value = int(tx.get("value", "0"), 16) / 1e18
                    if value >= expected_amount * 0.99:
                        return True
        except: pass
        return False
    return False

@app.post("/api/upgrade")
def upgrade(req: UpgradeRequest, user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Authentication required")
    if req.tier not in ("plus", "pro", "pro_max"):
        raise HTTPException(400, "Invalid tier")
    if not req.txid.strip():
        raise HTTPException(400, "TXID required")
    
    prices = {"plus": 8, "pro": 17, "pro_max": 30}
    verified = verify_transaction(req.txid.strip(), req.currency.upper(), req.tier)
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("""
                    INSERT INTO payments (id, user_id, txid, currency, amount, tier, verified)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (str(uuid.uuid4()), user["id"], req.txid.strip(), req.currency.upper(), prices[req.tier], req.tier, 1 if verified else 0))
                
                if verified:
                    c.execute("""
                        UPDATE users SET tier = %s, tier_expires = %s, reasoning_depth = %s, updated_at = NOW()
                        WHERE id = %s
                    """, (req.tier, datetime.now(timezone.utc) + timedelta(days=30), TIER_CONFIG[req.tier]["reasoning_depth"], user["id"]))
                conn.commit()
    except Exception as e:
        logger.error(f"Upgrade error: {e}")
        raise HTTPException(500, "Could not process upgrade")
    
    if verified:
        return {"verified": True, "tier": req.tier}
    else:
        return {"verified": False, "message": "Transaction submitted for review. Upgrade will be activated after confirmation."}

# ================================================================
# WORKSPACES
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
# MARKET & NEWS (with Finnhub)
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
# ADMIN (Founder only) – now with user management
# ================================================================
@app.get("/api/admin")
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

@app.get("/api/admin/users")
def admin_users(user: dict = Depends(get_current_user)):
    if not user or user["tier"] != "founder":
        raise HTTPException(403, "Access denied")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, email, name, tier, created_at FROM users ORDER BY created_at DESC LIMIT 50")
            rows = c.fetchall()
            return [{"id": r[0], "email": r[1], "name": r[2], "tier": r[3], "created_at": r[4].isoformat() if r[4] else None} for r in rows]

@app.post("/api/admin/user/{user_id}/tier")
def admin_change_tier(user_id: str, req: dict, user: dict = Depends(get_current_user)):
    if not user or user["tier"] != "founder":
        raise HTTPException(403, "Access denied")
    new_tier = req.get("tier")
    if new_tier not in ("guest", "free", "plus", "pro", "pro_max", "founder"):
        raise HTTPException(400, "Invalid tier")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE users SET tier = %s, updated_at = NOW() WHERE id = %s", (new_tier, user_id))
            conn.commit()
    return {"success": True}

@app.delete("/api/admin/user/{user_id}")
def admin_delete_user(user_id: str, user: dict = Depends(get_current_user)):
    if not user or user["tier"] != "founder":
        raise HTTPException(403, "Access denied")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()
    return {"deleted": True}

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
        "version": "29.0",
        "database": db_status,
        "ai": ai_status,
        "providers": providers,
        "auth": "email_password",
        "reasoning_engine": True,
        "intelligence_level": "full",
        "tiers": ["guest", "free", "plus", "pro", "pro_max", "founder"]
    }

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
    
    if settings.FINNHUB_API_KEY:
        symbols = ["AAPL", "MSFT", "NVDA", "TSLA", "GOOGL", "META", "AMZN", "^GSPC", "^IXIC", "^DJI"]
        for sym in symbols:
            try:
                r = requests.get(f"https://finnhub.io/api/v1/quote?symbol={sym}&token={settings.FINNHUB_API_KEY}", timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("c"):
                        name = sym.lstrip("^")
                        results[name] = {"price": data["c"], "change": round(data.get("dp", 0), 2)}
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

UPGRADE_BENEFITS = {
    "plus": ["Limited messaging (50/day)", "Groq Llama 3.3 70B", "Work Area (10 seats)", "File uploads", "Web search", "2-step reasoning"],
    "pro": ["Limited messaging (100/day)", "Claude 3.5 Sonnet", "Work Area (25 seats)", "Live markets", "Web search", "3-step reasoning"],
    "pro_max": ["Unlimited messaging", "GPT-4o + Claude Ensemble", "Work Area (50 seats)", "Live markets", "Advanced reasoning", "Priority support"]
}

# ================================================================
# MAIN
# ================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"\n{'='*70}")
    print(f"🚀 CAPITAN AI v29.0 - Warm Trading Expert, Full Features")
    print(f"🔐 JWT_SECRET & FOUNDER_KEY required from env")
    print(f"📍 Backend: 0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)