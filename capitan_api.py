"""
CAPITAN AI — Enterprise Backend v32.0 (Tool Calling, Images, Streaming, Configurable)
CLOSEAI Technologies
World‑Class General‑Purpose AI | Intent‑Driven | Trustworthy | Warm & Engaging
Full task/intent routing, content generation mode, conversation continuity.
Self‑learning pipeline, feedback, fine‑tuning, dynamic icons, full notifications.
Puter API (free) + DeepSeek integrated.
New: Tool calling, image analysis, SSE streaming, configurable parameters.
All original features intact.
"""

import os, re, json, uuid, time, hmac, hashlib, base64, secrets, requests, logging, bcrypt
import PyPDF2, docx, openpyxl, io, csv
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple, AsyncGenerator
from contextlib import contextmanager
from io import StringIO

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
from pydantic_settings import BaseSettings
import psycopg2
import uvicorn

app = FastAPI(title="CAPITAN AI API", version="32.0")

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
    FOUNDER_EXTRA_PROMPT: str = ""
    AIMLAPI_API_KEY: str = ""
    ALMLAPI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
                # Users
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

                # Sessions
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

                # Chats & messages
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
                        system_prompt TEXT,
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')
                c.execute("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS reasoning_chain TEXT")
                c.execute("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS system_prompt TEXT")

                # Memories
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

                # Library
                c.execute('''
                    CREATE TABLE IF NOT EXISTS library_items (
                        id TEXT PRIMARY KEY,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        name TEXT,
                        content TEXT,
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')
                c.execute("ALTER TABLE library_items ADD COLUMN IF NOT EXISTS user_id UUID")
                c.execute("ALTER TABLE library_items ADD COLUMN IF NOT EXISTS name TEXT")
                c.execute("ALTER TABLE library_items ADD COLUMN IF NOT EXISTS content TEXT")

                # Uploaded files
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
                c.execute("ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS name TEXT")
                c.execute("ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS owner_id UUID")
                c.execute("ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS room_code TEXT")
                c.execute("ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS max_members INTEGER DEFAULT 10")

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
                c.execute("ALTER TABLE workspace_members ADD COLUMN IF NOT EXISTS user_id UUID")
                c.execute("ALTER TABLE workspace_members ADD COLUMN IF NOT EXISTS workspace_id TEXT")
                c.execute("ALTER TABLE workspace_members ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'member'")
                c.execute("""
                    DO $$
                    BEGIN
                        IF EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name='workspace_members' AND column_name='session_id')
                        THEN
                            ALTER TABLE workspace_members DROP CONSTRAINT IF EXISTS workspace_members_pkey;
                            ALTER TABLE workspace_members DROP COLUMN session_id;
                            ALTER TABLE workspace_members ADD PRIMARY KEY (workspace_id, user_id);
                        END IF;
                    END;
                    $$;
                """)

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

                # Payments
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

                # Cache
                c.execute('''
                    CREATE TABLE IF NOT EXISTS reasoning_cache (
                        id TEXT PRIMARY KEY,
                        query_hash TEXT UNIQUE,
                        reasoning_chain TEXT,
                        result TEXT,
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')

                # Feedback
                c.execute('''
                    CREATE TABLE IF NOT EXISTS feedback (
                        id TEXT PRIMARY KEY,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        message_id TEXT,
                        rating INTEGER DEFAULT 0,
                        comment TEXT,
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')

                # Model versions
                c.execute('''
                    CREATE TABLE IF NOT EXISTS model_versions (
                        id TEXT PRIMARY KEY,
                        base_model TEXT,
                        finetuned_model_id TEXT,
                        dataset_path TEXT,
                        active BOOLEAN DEFAULT FALSE,
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')

                # Notifications
                c.execute('''
                    CREATE TABLE IF NOT EXISTS notifications (
                        id TEXT PRIMARY KEY,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        type TEXT DEFAULT 'info',
                        message TEXT NOT NULL,
                        read BOOLEAN DEFAULT FALSE,
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

# ===================== PASSWORD HASHING =====================
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except:
        return False

# ===================== JWT AUTH =====================
def create_token(user_id: str) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "user_id": user_id, "type": "user",
        "exp": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())
    }).encode()).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(hmac.new(settings.JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return f"{header}.{payload}.{signature}"

def create_session_token(session_id: str, tier: str) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "session_id": session_id, "tier": tier, "type": "session",
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
                if not c.fetchone(): return None
                c.execute("SELECT id, email, name, tier, reasoning_depth, preferred_domain FROM users WHERE id = %s", (user_id,))
                row = c.fetchone()
                if row:
                    return {
                        "id": row[0], "email": row[1], "name": row[2] or row[1].split('@')[0],
                        "tier": row[3], "reasoning_depth": row[4] or 1, "preferred_domain": row[5] or "general"
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

# ===================== AUTH ENDPOINTS (unchanged) =====================
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
                        "id": user_id, "email": req.email, "name": name,
                        "tier": "free", "reasoning_depth": 1, "preferred_domain": "general"
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
                        "id": user_id, "email": email,
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
                        "id": user_id, "name": "CAPITAN Founder",
                        "email": "founder@capitan.ai", "tier": "founder",
                        "reasoning_depth": 5, "preferred_domain": "general"
                    }
                }
    except Exception as e:
        logger.error(f"Founder error: {e}")
        raise HTTPException(500, "Founder login failed")

# ===================== CAPITAN AI SYSTEM PROMPT v2.0 =====================
CORE_INSTRUCTIONS = """You are CAPITAN AI — an elite general-purpose intelligence system developed by CLOSEAI Technologies under the leadership of CEO Osinachi Chukwu.
GREETING BEHAVIOR:
When the user sends only a greeting (hello, hi, hey, good morning, etc.), respond warmly and briefly. Say something like:
"Hey! Great to see you. What would you like to dive into today?"
Do NOT ask what their objective is. Do NOT list capabilities. Keep it natural and human.

Your primary objective is not to answer questions.

Your primary objective is to understand intent, solve problems, and help users make better decisions.

You operate as a senior strategist, engineer, analyst, researcher, educator, and advisor depending on what the situation requires.

---

CORE PRINCIPLE

Never respond to the words alone.

Respond to the underlying objective.

Ask yourself:

- What is the user actually trying to achieve?
- What problem are they trying to solve?
- What outcome would be most useful?

Then optimize your response for that outcome.

---

INTENT DETECTION LAYER

Before generating a response, classify the request into one of the following categories:

1. Information Request
2. Problem Solving
3. Decision Making
4. Content Creation
5. Coding / Engineering
6. Financial Analysis
7. Research
8. Planning
9. Learning / Education
10. Conversation

Adapt your response style accordingly.

---

REASONING ENGINE

Use these frameworks internally when useful:

- First Principles Thinking
- Bayesian Reasoning
- Systems Thinking
- Second Order Effects
- Opportunity Cost Analysis
- Root Cause Analysis
- Red Team Analysis
- Occam's Razor

Never mention the framework unless the user asks.

---

RESPONSE STRUCTURE

Default structure:

1. Context
2. Analysis
3. Recommendation
4. Next Step

Do not dump information.

Build understanding first.

---

COMMUNICATION STYLE

Speak like a highly competent human expert.

Avoid:

- "Great question"
- "Certainly"
- "I'd be happy to help"
- Robotic introductions
- Unnecessary apologies

Preferred style:

Direct.
Precise.
Natural.
Confident.

Use simple language for beginners.

Use technical language for experts.

Match the user's level automatically.

---

CLARIFICATION RULE

If the request is ambiguous:

Ask exactly ONE high-value clarifying question.

Never ask multiple questions at once.

Never ask questions when a reasonable assumption can be made.

---

CONTEXT AWARENESS

Maintain continuity across the conversation.

If a topic is already active:

- Continue from previous context.
- Do not restart.
- Do not repeat information unnecessarily.

Remember recent objectives and constraints.

---

QUALITY CONTROL

Before responding, verify:

✓ Did I solve the actual problem?
✓ Is there a simpler solution?
✓ Did I consider edge cases?
✓ Did I explain trade-offs?
✓ Did I avoid assumptions?
✓ Would an expert find this useful?

If not, improve the response.

---

HONESTY PROTOCOL

Never fabricate:

- Facts
- Statistics
- Sources
- Capabilities
- Results

If confidence is below 70%:

State uncertainty clearly.

Separate:

FACT
INFERENCE
SPECULATION

---

FINANCE & TRADING

Capabilities:

- Forex
- Commodities
- Equities
- Crypto
- Bonds
- Macroeconomics
- Market Structure
- Order Flow
- COT Analysis
- Institutional Positioning
- Quantitative Analysis
- Risk Management
- Portfolio Construction
- Algorithmic Trading

When discussing markets:

Explain probabilities, not certainties.

Never imply guaranteed profit.

Always emphasize risk.

---

SOFTWARE ENGINEERING

Capabilities:

- Python
- JavaScript
- TypeScript
- Go
- Rust
- C++
- Full Stack Development
- AI Systems
- APIs
- Cloud Infrastructure
- Distributed Systems
- DevOps
- Security Engineering

When coding:

Explain architecture before code.

Prioritize maintainability.

Identify failure points.

---

CYBERSECURITY

Capabilities:

- Threat Modeling
- Application Security
- Network Security
- Digital Forensics
- Incident Response
- Cryptography
- Security Architecture

Never provide instructions that facilitate malicious activity.

---

SCIENCE & MATHEMATICS

Capabilities:

- Physics
- Chemistry
- Biology
- Medicine
- Statistics
- Linear Algebra
- Calculus
- Data Science

Explain complex concepts using intuition before formulas.

---

EVERYDAY INTELLIGENCE

Assist with:

- Career Growth
- Communication
- Relationships
- Learning
- Productivity
- Writing
- Travel
- Business
- Personal Decision Making

Optimize for practical usefulness.

---

END OF RESPONSE BEHAVIOR

After solving the problem:

Offer ONE logical next step.

Examples:

- "Want me to optimize this further?"
- "Should I show the implementation?"
- "Would you like a more advanced version?"
- "Want the trade-offs explained?"

Do not force follow-up questions.

Only offer what is genuinely useful.

---

TOOLS

You have access to the following tools. Use them whenever they would improve your response.

- get_market_data(symbol) — returns current price and 24h change for a stock or crypto symbol.
- web_search(query) — returns recent web search results.
- get_current_time() — returns the current UTC time.

When you use a tool, you will see the result immediately and can continue your response.
"""

# ===================== TASK CLASSIFIER =====================
def classify_task(q: str) -> str:
    q_lower = q.lower()
    if re.search(r'^(hello|hi|hey|good morning|good afternoon|good evening|greetings)\b', q_lower) and len(q_lower.split()) < 4:
        return "Conversation"

    content_kw = [
        "landing page", "website", "homepage", "service page", "about page",
        "pricing page", "copywriting", "write a", "generate a", "create a",
        "sales page", "email template", "blog post", "article", "slogan",
        "tagline", "press release", "product description", "ad copy",
        "design a", "make a site", "build a page", "html for", "css for",
        "ui for", "ux for", "pitch deck", "presentation", "create content"
    ]
    for kw in content_kw:
        if kw in q_lower:
            return "Content Creation"

    coding_kw = [
        "code", "function", "api", "debug", "refactor", "optimize",
        "sql", "query", "database", "script", "library", "framework",
        "error", "bug", "deploy", "docker", "kubernetes", "aws",
        "python", "javascript", "react", "node", "golang", "rust",
        "algorithm", "architecture", "unit test", "integration test",
        "build a", "write a script", "review this code", "fix this"
    ]
    for kw in coding_kw:
        if kw in q_lower:
            return "Coding / Engineering"

    finance_kw = [
        "stock", "forex", "crypto", "trade", "entry", "exit",
        "analysis", "market", "portfolio", "option", "future",
        "technical", "fundamental", "risk", "volatility", "gold",
        "silver", "bitcoin", "ethereum", "nifty", "sensex",
        "price target", "stop loss", "chart pattern", "indicator"
    ]
    for kw in finance_kw:
        if kw in q_lower:
            return "Financial Analysis"

    research_kw = [
        "research", "explain", "compare", "summary", "overview",
        "deep dive", "investigate", "study", "report", "analyze",
        "pros and cons", "difference between", "how does", "what is",
        "tell me about"
    ]
    for kw in research_kw:
        if kw in q_lower:
            return "Research"

    plan_kw = [
        "plan", "roadmap", "steps to", "how do i", "schedule",
        "timeline", "goal", "strategy", "approach", "framework",
        "best way to", "guide", "tutorial", "learn", "course"
    ]
    for kw in plan_kw:
        if kw in q_lower:
            return "Planning"

    decision_kw = [
        "should i", "which one", "pick", "choose", "better option",
        "vs", "versus", "or", "worth it", "recommend", "suggest"
    ]
    for kw in decision_kw:
        if kw in q_lower:
            return "Decision Making"

    learn_kw = [
        "teach me", "explain like", "tutorial", "beginner", "new to",
        "learn", "understand", "concept", "definition", "meaning"
    ]
    for kw in learn_kw:
        if kw in q_lower:
            return "Learning / Education"

    problem_kw = [
        "issue", "error", "not working", "broken", "fix", "help",
        "stuck", "can't", "won't", "fail", "crash", "bug"
    ]
    for kw in problem_kw:
        if kw in q_lower:
            return "Problem Solving"

    if re.search(r'^(what|when|where|who|how many|how much|how long|how far)\b', q_lower):
        return "Information Request"

    return "Conversation"

# ===================== CONTEXT & PROMPT BUILDING =====================
def get_time_context():
    now = datetime.now(timezone.utc)
    hour = now.hour
    day = now.strftime("%A")
    date = now.strftime("%B %d, %Y")
    utc_time = now.strftime("%H:%M UTC")
    if hour < 5:
        greeting_context = "The world is quiet — a perfect time for deep thinking."
    elif hour < 12:
        greeting_context = "A fresh day for new ideas."
    elif hour < 17:
        greeting_context = "The day is in full swing — let's make it productive."
    elif hour < 21:
        greeting_context = "Winding down, but still sharp."
    else:
        greeting_context = "The night is young — plenty of time to explore new ideas."
    return {"day": day, "date": date, "utc_time": utc_time, "greeting_context": greeting_context}

def _extract_previous_exchange(history: List[dict]) -> str:
    if len(history) < 2:
        return ""
    last_user = None
    prev_assistant = None
    for m in reversed(history):
        if m["role"] == "user" and last_user is None:
            last_user = m["content"]
        elif m["role"] == "assistant" and last_user is not None:
            prev_assistant = m["content"]
            break
    if prev_assistant and last_user:
        return f"CAPITAN: {prev_assistant[:300]}\nUSER: {last_user[:300]}"
    return ""

def _generate_conversation_summary(history: List[dict]) -> str:
    if not history or len(history) < 3:
        return ""
    recent_assistant = [m["content"][:150] for m in history if m["role"] == "assistant"][-2:]
    recent_user = [m["content"][:80] for m in history if m["role"] == "user"][-2:]
    parts = []
    if recent_user:
        parts.append(f"User asked about: {'; '.join(recent_user)}")
    if recent_assistant:
        parts.append(f"CAPITAN discussed: {'; '.join(recent_assistant)}")
    return "\n".join(parts)

def build_system_prompt(domain: str, tier: str, model: str,
                        reasoning_depth: int = 1,
                        preferred_domain: str = "general",
                        web_results: List[dict] = None,
                        user_query: str = "",
                        history: List[dict] = None,
                        user_profile: dict = None,
                        task_type: str = "Conversation") -> str:
    tc = get_time_context()
    base = CORE_INSTRUCTIONS

    base += f"\n\nCurrent time: {tc['day']}, {tc['date']} at {tc['utc_time']}. {tc['greeting_context']}"

    if user_profile:
        name = user_profile.get("name", "User")
        tier_name = TIER_CONFIG.get(user_profile.get("tier", "free"), {}).get("name", "Free")
        prof = f"\n\n[USER PROFILE]\nName: {name}\nTier: {tier_name}\nPreferred domain: {user_profile.get('preferred_domain', 'general')}\nReasoning depth: {user_profile.get('reasoning_depth', 1)}"
        base += prof

    if history and len(history) >= 6:
        summary = _generate_conversation_summary(history)
        if summary:
            base += "\n\n[CONVERSATION SUMMARY]\n" + summary

    if history and len(history) >= 2:
        prev_exchange = _extract_previous_exchange(history)
        if prev_exchange:
            base += "\n\n[PREVIOUS EXCHANGE]\n" + prev_exchange

    if user_query:
        base += f"\n\nUSER REQUEST: {user_query}"

    if task_type == "Content Creation":
        base += "\n\n[MODE: CONTENT CREATION]\nYou are generating content directly. Produce the requested output without asking follow‑up questions unless you absolutely need a critical detail. Do not enter conversational mode. Format the output cleanly."
    elif task_type == "Financial Analysis":
        base += "\n\n[MODE: FINANCIAL ANALYSIS]\nProvide objective analysis with clear probabilities. Never imply guaranteed profit. Emphasize risk."
    elif task_type == "Coding / Engineering":
        base += "\n\n[MODE: CODING ASSISTANT]\nExplain architecture before code. Prioritize maintainability. Point out potential issues."
    elif task_type == "Research":
        base += "\n\n[MODE: RESEARCH]\nProvide thorough, well‑structured information. Use comparisons when helpful. Cite sources when available."
    elif task_type == "Planning":
        base += "\n\n[MODE: PLANNING]\nCreate a structured, actionable plan. Break down into phases. Consider dependencies."
    elif task_type == "Decision Making":
        base += "\n\n[MODE: DECISION SUPPORT]\nHelp the user weigh options. Present trade‑offs. Avoid making the choice for them."
    elif task_type == "Learning / Education":
        base += "\n\n[MODE: EDUCATOR]\nExplain concepts clearly. Use analogies and examples. Check for understanding."
    elif task_type == "Problem Solving":
        base += "\n\n[MODE: PROBLEM SOLVING]\nDiagnose the root cause. Propose actionable fixes. Anticipate related issues."
    elif task_type == "Conversation":
        base += "\n\n[MODE: CONVERSATION]\nYou are having a casual, natural conversation. Do NOT use the structured response format (Context, Analysis, Recommendation, Next Step). Be warm, concise, and human. Respond directly to what the user said."

    if tier == "founder" and settings.FOUNDER_EXTRA_PROMPT:
        base += "\n\n[FOUNDER DIRECTIVES]\n" + settings.FOUNDER_EXTRA_PROMPT

    if web_results:
        base += "\n\nWEB SEARCH RESULTS:\n" + "\n".join(
            [f"- {r['title']}: {r['snippet'][:200]}" for r in web_results[:4]]
        )

    return base

# ===================== BUILT-IN TOOLS =====================
def tool_get_market_data(symbol: str) -> str:
    """Return current price and change for a symbol."""
    try:
        # Use existing CoinGecko for crypto, Finnhub for stocks
        if symbol.upper() in ("BTC","ETH","XRP","SOL","ADA","DOGE","AVAX","LINK","DOT","TRX"):
            ids = "bitcoin,ethereum,ripple,solana,cardano,dogecoin,avalanche-2,chainlink,polkadot,tron"
            r = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true"},
                headers={"x-cg-demo-api-key": settings.COINGECKO_KEY} if settings.COINGECKO_KEY else {},
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                name_map = {
                    "BTC":"bitcoin","ETH":"ethereum","XRP":"ripple","SOL":"solana","ADA":"cardano",
                    "DOGE":"dogecoin","AVAX":"avalanche-2","LINK":"chainlink","DOT":"polkadot","TRX":"tron"
                }
                coin = name_map.get(symbol.upper())
                if coin and coin in data:
                    return f"{symbol} price: ${data[coin]['usd']}, 24h change: {data[coin].get('usd_24h_change', 0):.2f}%"
        if settings.FINNHUB_API_KEY:
            r = requests.get(f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={settings.FINNHUB_API_KEY}", timeout=10)
            if r.status_code == 200:
                d = r.json()
                if d.get("c"):
                    return f"{symbol} price: ${d['c']}, change: {d.get('dp', 0):.2f}%"
        return f"Could not retrieve data for {symbol}."
    except Exception as e:
        return f"Error fetching market data: {str(e)}"

def tool_web_search(query: str) -> str:
    """Search the web using SerpAPI."""
    if not settings.SERPAPI_KEY:
        return "Web search is not configured (missing SERPAPI_KEY)."
    try:
        r = requests.get(
            "https://serpapi.com/search",
            params={"engine": "google", "q": query, "num": 3, "api_key": settings.SERPAPI_KEY},
            timeout=10
        )
        if r.status_code == 200:
            results = r.json().get("organic_results", [])[:3]
            return "\n".join([f"- {res['title']}: {res.get('snippet', '')[:200]}" for res in results])
        return "No results found."
    except Exception as e:
        return f"Search error: {str(e)}"

def tool_get_current_time() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

TOOL_MAP = {
    "get_market_data": tool_get_market_data,
    "web_search": tool_web_search,
    "get_current_time": tool_get_current_time,
}

# ===================== AI MODEL CALL (WITH TOOL LOOP, IMAGE SUPPORT) =====================
def get_latest_fine_tuned_model(base_model="gpt-4o"):
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT finetuned_model_id FROM model_versions WHERE base_model=%s AND active=TRUE ORDER BY created DESC LIMIT 1", (base_model,))
                row = c.fetchone()
                if row:
                    return row[0]
    except Exception as e:
        logger.error(f"Error fetching fine-tuned model: {e}")
    return None

def _call_puter_api(messages: List[dict], model_name: str, temperature: float, max_tokens: int, tools: Optional[List[dict]] = None) -> Optional[dict]:
    try:
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        r = requests.post("https://api.puter.com/v2/chat/completions",
                          headers={"Content-Type": "application/json"},
                          json=payload, timeout=90)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.error(f"Puter API error: {e}")
    return None

def _call_aiml_api(messages: List[dict], model_name: str, temperature: float, max_tokens: int, tools: Optional[List[dict]] = None) -> Optional[dict]:
    api_key = settings.AIMLAPI_API_KEY or settings.ALMLAPI_API_KEY
    if not api_key:
        return None
    try:
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        r = requests.post("https://api.aimlapi.com/v1/chat/completions",
                          headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                          json=payload, timeout=60)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.error(f"AIML API error: {e}")
    return None

def _call_openrouter(messages: List[dict], model_name: str, temperature: float, max_tokens: int, tools: Optional[List[dict]] = None) -> Optional[dict]:
    if not settings.OPENROUTER_API_KEY:
        return None
    try:
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        if tools:
            payload["tools"] = tools
        r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                          headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                          json=payload, timeout=60)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.error(f"OpenRouter error: {e}")
    return None

def _call_groq(messages: List[dict], model_name: str, temperature: float, max_tokens: int) -> Optional[dict]:
    if not settings.GROQ_API_KEY:
        return None
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                          headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"},
                          json={"model": model_name, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
                          timeout=35)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.error(f"Groq error: {e}")
    return None

def _execute_tool_calls(response: dict, messages: List[dict]) -> List[dict]:
    """Execute any tool calls in the response and append results to messages."""
    choice = response.get("choices", [{}])[0]
    tool_calls = choice.get("message", {}).get("tool_calls", [])
    if not tool_calls:
        return messages
    # Append assistant message with tool calls
    messages.append(choice["message"])
    for tc in tool_calls:
        func_name = tc["function"]["name"]
        try:
            args = json.loads(tc["function"]["arguments"])
        except:
            args = {}
        tool_fn = TOOL_MAP.get(func_name)
        if tool_fn:
            try:
                result = tool_fn(**args)
            except Exception as e:
                result = f"Error: {str(e)}"
        else:
            result = f"Unknown function '{func_name}'"
        messages.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": result
        })
    return messages

def call_ai_model(messages: List[dict], tier: str = "free", reasoning_depth: int = 1, domain: str = "general",
                  temperature: float = 0.7, max_tokens: int = 4000, tools: Optional[List[dict]] = None,
                  image_url: Optional[str] = None) -> Tuple[str, str, Optional[List[str]]]:
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

    # Attach image to last user message if provided
    if image_url and messages and messages[-1]["role"] == "user":
        original_content = messages[-1]["content"]
        messages[-1]["content"] = [
            {"type": "text", "text": original_content},
            {"type": "image_url", "image_url": {"url": image_url}}
        ]

    # Try Puter API first for Pro+ (best model and free)
    if tier in ("pro", "pro_max", "founder"):
        if tier == "pro":
            puter_model = "anthropic/claude-sonnet-4-6"
        elif tier == "pro_max":
            puter_model = "openai/gpt-5.4-nano"
        else:
            puter_model = "openai/gpt-5.4-nano"
        resp = _call_puter_api(messages, puter_model, temperature, max_tokens, tools)
        if resp:
            # Tool loop
            for _ in range(3):  # max 3 round trips
                if resp["choices"][0].get("finish_reason") == "tool_calls":
                    messages = _execute_tool_calls(resp, messages)
                    resp = _call_puter_api(messages, puter_model, temperature, max_tokens, tools)
                else:
                    break
            content = resp["choices"][0].get("message", {}).get("content", "")
            if content:
                return content, f"{puter_model} (Puter)", reasoning_chain

    # AIML API
    base_model_name = "gpt-4o"
    if tier in ("pro", "pro_max", "founder"):
        ft_model = get_latest_fine_tuned_model(base_model_name)
        if ft_model:
            base_model_name = ft_model
    resp = _call_aiml_api(messages, base_model_name, temperature, max_tokens, tools)
    if resp:
        for _ in range(3):
            if resp["choices"][0].get("finish_reason") == "tool_calls":
                messages = _execute_tool_calls(resp, messages)
                resp = _call_aiml_api(messages, base_model_name, temperature, max_tokens, tools)
            else:
                break
        content = resp["choices"][0].get("message", {}).get("content", "")
        if content:
            return content, f"{base_model_name} (AIML API)", reasoning_chain

    # DeepSeek via OpenRouter
    resp = _call_openrouter(messages, "deepseek/deepseek-r1", temperature, max_tokens, tools)
    if resp:
        content = resp["choices"][0].get("message", {}).get("content", "")
        if content:
            return content, "deepseek-r1 (OpenRouter)", reasoning_chain

    # ProMax ensemble (OpenRouter)
    if tier == "pro_max":
        resp = _call_openrouter(messages, "anthropic/claude-3.5-sonnet-20241022", temperature, max_tokens, tools)
        if resp:
            content1 = resp["choices"][0].get("message", {}).get("content", "")
            resp2 = _call_openrouter(messages, "openai/gpt-4o-2024-11-20", temperature, max_tokens, tools)
            content2 = resp2["choices"][0].get("message", {}).get("content", "") if resp2 else ""
            if content1 and content2:
                combined = f"**Claude 3.5 Sonnet Response:**\n{content1}\n\n---\n\n**GPT-4o Additional Insights:**\n{content2}"
                return combined, "claude-3.5-sonnet + gpt-4o (Ensemble)", reasoning_chain
            elif content1:
                return content1, "claude-3.5-sonnet", reasoning_chain
            elif content2:
                return content2, "gpt-4o", reasoning_chain

    # Pro (OpenRouter Claude)
    if tier == "pro":
        resp = _call_openrouter(messages, "anthropic/claude-3.5-sonnet-20241022", temperature, max_tokens, tools)
        if resp:
            content = resp["choices"][0].get("message", {}).get("content", "")
            if content:
                return content, "claude-3.5-sonnet", reasoning_chain

    # Plus (Groq 70B)
    if tier == "plus":
        resp = _call_groq(messages, "llama-3.3-70b-versatile", temperature, max_tokens)
        if resp:
            content = resp["choices"][0].get("message", {}).get("content", "")
            if content:
                return content, "llama-3.3-70b", reasoning_chain

    # Fallback: Groq 8B
    resp = _call_groq(messages, "llama-3.1-8b-instant", temperature, max_tokens)
    if resp:
        content = resp["choices"][0].get("message", {}).get("content", "")
        if content:
            return content, "llama-3.1-8b", reasoning_chain

    return "I'm having trouble connecting to AI services. Please try again.", "fallback", reasoning_chain

# ===================== STREAMING VERSION (SSE) =====================
async def call_ai_model_stream(messages: List[dict], tier: str = "free", temperature: float = 0.7, max_tokens: int = 4000,
                               tools: Optional[List[dict]] = None, image_url: Optional[str] = None) -> AsyncGenerator[str, None]:
    """Yield tokens via Server-Sent Events."""
    if image_url and messages and messages[-1]["role"] == "user":
        original_content = messages[-1]["content"]
        messages[-1]["content"] = [
            {"type": "text", "text": original_content},
            {"type": "image_url", "image_url": {"url": image_url}}
        ]

    # For simplicity, only support Puter API streaming
    if tier in ("pro", "pro_max", "founder"):
        if tier == "pro":
            model_name = "anthropic/claude-sonnet-4-6"
        elif tier == "pro_max":
            model_name = "openai/gpt-5.4-nano"
        else:
            model_name = "openai/gpt-5.4-nano"
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        try:
            r = requests.post("https://api.puter.com/v2/chat/completions",
                              headers={"Content-Type": "application/json"},
                              json=payload, stream=True, timeout=120)
            if r.status_code == 200:
                for line in r.iter_lines():
                    if line:
                        line_str = line.decode("utf-8")
                        if line_str.startswith("data: "):
                            data_str = line_str[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                if "content" in delta and delta["content"]:
                                    yield delta["content"]
                            except:
                                continue
            else:
                yield "Streaming not available. Try the regular chat."
        except Exception as e:
            yield f"Stream error: {str(e)}"
    else:
        yield "Streaming is only available for Pro tier and above."

# ===================== TIER CONFIGURATION (unchanged) =====================
TIER_CONFIG = {
    "guest": {"name": "Guest", "msg_limit": 10, "workspace_seats": 0, "file_upload": False, "live_markets": False, "web_search": False, "ai_model": "Groq Llama 3.1 8B", "price": 0, "reasoning_depth": 1},
    "free": {"name": "Free", "msg_limit": 20, "workspace_seats": 0, "file_upload": False, "live_markets": False, "web_search": False, "ai_model": "Groq Llama 3.1 8B", "price": 0, "reasoning_depth": 1},
    "plus": {"name": "Plus", "msg_limit": 50, "workspace_seats": 10, "file_upload": True, "live_markets": False, "web_search": True, "ai_model": "Groq Llama 3.3 70B", "price": 8, "reasoning_depth": 2},
    "pro": {"name": "Pro", "msg_limit": 100, "workspace_seats": 25, "file_upload": True, "live_markets": True, "web_search": True, "ai_model": "Claude Sonnet 4 (Puter)", "price": 17, "reasoning_depth": 3},
    "pro_max": {"name": "Pro Max", "msg_limit": float("inf"), "workspace_seats": 50, "file_upload": True, "live_markets": True, "web_search": True, "ai_model": "GPT-5.4 Nano (Puter)", "price": 30, "reasoning_depth": 4},
    "founder": {"name": "Founder", "msg_limit": float("inf"), "workspace_seats": 100, "file_upload": True, "live_markets": True, "web_search": True, "ai_model": "All Models + Custom", "price": 0, "reasoning_depth": 5}
}

WALLETS = {
    "BTC": "bc1qrv6yr6e0mat96rvrc8smdf9rvu9rlp8xuk8new",
    "ETH": "0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1"
}

# ===================== FILE EXTRACTION (unchanged) =====================
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

# ===================== FILE UPLOAD (unchanged) =====================
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

# ===================== CHAT ENDPOINT (NOW WITH TOOLS, IMAGE, PARAMS) =====================
class ChatRequest(BaseModel):
    messages: list
    chat_id: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    tools: Optional[List[dict]] = None
    image_url: Optional[str] = None

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
        user_profile = {
            "name": user.get("name", ""),
            "tier": tier,
            "preferred_domain": preferred_domain,
            "reasoning_depth": reasoning_depth
        }
    else:
        tier = session["tier"]
        user_id = None
        reasoning_depth = 1
        preferred_domain = "general"
        is_authenticated = False
        user_profile = None
    
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
    
    domain = classify_query(user_msg, history)
    web_search_needed = needs_web_search(user_msg)
    task_type = classify_task(user_msg)
    
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
    
    web_results = None
    if tier_info.get("web_search", False) and web_search_needed:
        try:
            web_results = search_web(user_msg, 5)
        except Exception as e:
            logger.error(f"Web search error: {e}")
    
    memory_text = ""
    if is_authenticated:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("""
                        SELECT content FROM memories
                        WHERE user_id = %s AND domain = %s
                        ORDER BY created DESC LIMIT 3
                    """, (user["id"], domain))
                    rows = c.fetchall()
                    if rows:
                        memory_text = "\n\n[RELEVANT MEMORIES]\n" + "\n".join([r[0][:200] for r in rows])
                    c.execute("""
                        SELECT content FROM memories
                        WHERE user_id = %s
                        ORDER BY created DESC LIMIT 1
                    """, (user["id"],))
                    row = c.fetchone()
                    if row:
                        memory_text += "\n\n[MOST RECENT MEMORY]\n" + row[0][:200]
        except: pass
    
    prompt = build_system_prompt(domain, tier, tier_info["ai_model"], reasoning_depth,
                                 preferred_domain, web_results, user_query=user_msg,
                                 history=history, user_profile=user_profile,
                                 task_type=task_type)
    if memory_text:
        prompt += "\n" + memory_text
    
    # Collect parameters
    temp = req.temperature if req.temperature is not None else 0.7
    max_tok = req.max_tokens if req.max_tokens is not None else 4000
    tools = req.tools if req.tools else None
    image_url = req.image_url

    result, model_used, reasoning_chain = call_ai_model(
        [{"role": "system", "content": prompt}] + history, tier, reasoning_depth, domain,
        temperature=temp, max_tokens=max_tok, tools=tools, image_url=image_url
    )
    
    if result:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    if is_authenticated:
                        c.execute("""
                            INSERT INTO chat_messages (id, chat_id, user_id, role, content, model, reasoning_chain, system_prompt)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, (f"msg_{sid()}", chat_id, user["id"], "assistant", result, model_used, json.dumps(reasoning_chain) if reasoning_chain else None, prompt))
                        c.execute("""
                            INSERT INTO memories (id, memory_id, user_id, content, query, domain, importance)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (sid(), mid(), user["id"], result[:500], user_msg, domain, 2 if domain in ["finance", "quant", "coding"] else 1))
                    else:
                        c.execute("""
                            INSERT INTO chat_messages (id, chat_id, session_id, role, content, model, reasoning_chain, system_prompt)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, (f"msg_{sid()}", chat_id, session["id"], "assistant", result, model_used, json.dumps(reasoning_chain) if reasoning_chain else None, prompt))
                    conn.commit()
        except Exception as e:
            logger.error(f"Save AI error: {e}")
    
    return {
        "content": result,
        "chat_id": chat_id,
        "model": model_used,
        "tier": tier,
        "domain": domain,
        "task_type": task_type,
        "reasoning_chain": reasoning_chain
    }

# ===================== STREAMING CHAT ENDPOINT =====================
@app.post("/api/chat/stream")
async def chat_stream_endpoint(req: ChatRequest, request: Request):
    user = get_current_user(request)
    session = None
    if not user:
        try:
            session = get_current_session(request)
        except:
            raise HTTPException(401, "Authentication required")
    tier = user["tier"] if user else session["tier"]
    
    # Build prompt (simplified for streaming)
    user_msg = ""
    for m in reversed(req.messages):
        if m.get("role") == "user":
            user_msg = m.get("content")
            break
    if not user_msg:
        raise HTTPException(400, "No message content")
    
    history = []
    prompt = build_system_prompt("general", tier, "", 1, "general", None, user_msg, history, None, "Conversation")
    
    async def event_stream():
        messages = [{"role": "system", "content": prompt}] + req.messages
        temp = req.temperature if req.temperature is not None else 0.7
        max_tok = req.max_tokens if req.max_tokens is not None else 4000
        image_url = req.image_url
        async for token in call_ai_model_stream(messages, tier, temperature=temp, max_tokens=max_tok, image_url=image_url):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")

# ===================== FEEDBACK ENDPOINT (unchanged) =====================
class FeedbackRequest(BaseModel):
    message_id: str
    rating: int
    comment: Optional[str] = ""

@app.post("/api/feedback")
async def submit_feedback(req: FeedbackRequest, user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Authentication required")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("""
                    INSERT INTO feedback (id, user_id, message_id, rating, comment)
                    VALUES (%s, %s, %s, %s, %s)
                """, (sid(), user["id"], req.message_id, req.rating, req.comment or ""))
                conn.commit()
                return {"status": "ok"}
    except Exception as e:
        logger.error(f"Feedback error: {e}")
        raise HTTPException(500, "Could not save feedback")

# ===================== NOTIFICATION HELPERS & ENDPOINTS (unchanged) =====================
def create_notification(user_id: str, type: str, message: str):
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("""
                    INSERT INTO notifications (id, user_id, type, message)
                    VALUES (%s, %s, %s, %s)
                """, (sid(), user_id, type, message))
                conn.commit()
    except Exception as e:
        logger.error(f"Create notification error: {e}")

def broadcast_notification(type: str, message: str):
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM users")
                user_ids = [r[0] for r in c.fetchall()]
                for uid in user_ids:
                    create_notification(uid, type, message)
    except Exception as e:
        logger.error(f"Broadcast error: {e}")

@app.get("/api/notifications")
def get_notifications(user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Authentication required")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("""
                    SELECT id, type, message, read, created FROM notifications
                    WHERE user_id = %s ORDER BY created DESC LIMIT 50
                """, (user["id"],))
                rows = c.fetchall()
                return {"notifications": [
                    {"id": r[0], "type": r[1], "message": r[2], "read": r[3], "created": r[4].isoformat()}
                    for r in rows
                ]}
    except Exception as e:
        logger.error(f"Notifications error: {e}")
        raise HTTPException(500, "Could not fetch notifications")

@app.get("/api/notifications/unread-count")
def get_unread_count(user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Authentication required")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT COUNT(*) FROM notifications WHERE user_id=%s AND read=FALSE", (user["id"],))
                count = c.fetchone()[0]
                return {"count": count}
    except Exception as e:
        raise HTTPException(500, "Could not get unread count")

@app.post("/api/notifications/mark-read")
def mark_notifications_read(user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Authentication required")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("UPDATE notifications SET read=TRUE WHERE user_id=%s", (user["id"],))
                conn.commit()
                return {"status": "ok"}
    except Exception as e:
        logger.error(f"Mark read error: {e}")
        raise HTTPException(500, "Could not mark notifications as read")

@app.delete("/api/notifications/{notif_id}")
def delete_notification(notif_id: str, user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Authentication required")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("DELETE FROM notifications WHERE id=%s AND user_id=%s", (notif_id, user["id"]))
                conn.commit()
                return {"deleted": True}
    except Exception as e:
        logger.error(f"Delete notification error: {e}")
        raise HTTPException(500, "Could not delete notification")

@app.post("/api/notifications/test")
async def send_test_notification(message: str = "This is a test notification", user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Authentication required")
    create_notification(user["id"], "info", message)
    return {"status": "test notification sent"}

@app.post("/api/notifications/broadcast")
def broadcast_message(req: dict, user: dict = Depends(get_current_user)):
    if not user or user["tier"] != "founder":
        raise HTTPException(403, "Access denied")
    message = req.get("message", "")
    notif_type = req.get("type", "system")
    if not message:
        raise HTTPException(400, "Message required")
    broadcast_notification(notif_type, message)
    return {"status": "broadcast sent"}

# ===================== CHAT HISTORY (unchanged) =====================
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

# ===================== LIBRARY (unchanged) =====================
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
        raise HTTPException(500, f"Could not save item: {str(e)}")

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

# ===================== PAYMENT & UPGRADE (unchanged) =====================
UPGRADE_BENEFITS = {
    "plus": ["Limited messaging (50/day)", "Groq Llama 3.3 70B", "File uploads (20MB)", "Web search", "2-step reasoning"],
    "pro": ["Limited messaging (100/day)", "Claude Sonnet 4 (Puter)", "File uploads (50MB)", "Live markets", "Web search", "3-step reasoning"],
    "pro_max": ["Unlimited messaging", "GPT-5.4 Nano (Puter)", "File uploads (100MB)", "Live markets", "Advanced reasoning", "Priority support"]
}

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
                    create_notification(user["id"], "success", f"Upgraded to {req.tier.upper()}! Enjoy your new benefits. 🚀")
                conn.commit()
    except Exception as e:
        logger.error(f"Upgrade error: {e}")
        raise HTTPException(500, "Could not process upgrade")
    
    new_token = create_token(user["id"])
    return {
        "verified": verified,
        "tier": req.tier if verified else user["tier"],
        "token": new_token
    }

# ===================== WORKSPACES (unchanged) =====================
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
    except Exception as e:
        logger.error(f"Workspace create error: {e}")
        raise HTTPException(500, f"Could not create workspace: {str(e)}")

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
                try:
                    c.execute("SELECT owner_id, name FROM workspaces WHERE id=%s", (workspace[0],))
                    owner = c.fetchone()
                    if owner and owner[0] != user["id"]:
                        create_notification(owner[0], "workspace", f"{user['name']} joined your workspace '{owner[1]}'.")
                except: pass
                conn.commit()
                return {"joined": True, "room_id": workspace[0]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Workspace join error: {e}")
        raise HTTPException(500, f"Could not join workspace: {str(e)}")

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
                c.execute("""
                    INSERT INTO workspace_messages (id, workspace_id, user_id, author_name, message)
                    VALUES (%s, %s, %s, %s, %s)
                """, (sid(), workspace[0], user["id"], user["name"], message))
                try:
                    c.execute("SELECT user_id FROM workspace_members WHERE workspace_id=%s AND user_id!=%s", (workspace[0], user["id"]))
                    members = [r[0] for r in c.fetchall()]
                    for member_id in members:
                        create_notification(member_id, "workspace", f"{user['name']} sent a message in the workspace.")
                except: pass
                if is_ai:
                    ai_response, _, _ = call_ai_model([{"role": "user", "content": message.replace('@CAPITAN', '').strip()}], user["tier"])
                    if ai_response:
                        c.execute("""
                            INSERT INTO workspace_messages (id, workspace_id, user_id, author_name, message, is_ai)
                            VALUES (%s, %s, %s, %s, %s, 1)
                        """, (sid(), workspace[0], user["id"], "CAPITAN AI", ai_response))
                conn.commit()
                return {"sent": True}
    except Exception as e:
        logger.error(f"Workspace message error: {e}")
        raise HTTPException(500, f"Could not send message: {str(e)}")

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
    except Exception as e:
        logger.error(f"Workspace messages error: {e}")
        raise HTTPException(500, f"Could not load messages: {str(e)}")

@app.get("/api/workspace/my")
def workspace_my(request: Request, user: dict = Depends(get_current_user)):
    if not user:
        return {"workspaces": []}
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("""
                SELECT w.id, w.name, w.room_code, w.max_members, w.created_at
                FROM workspaces w
                JOIN workspace_members m ON w.id = m.workspace_id
                WHERE m.user_id = %s
                ORDER BY w.created_at DESC
            """, (user["id"],))
            rows = c.fetchall()
            return {"workspaces": [
                {"id": r[0], "name": r[1], "room_code": r[2], "max_members": r[3],
                 "created_at": r[4].isoformat() if r[4] else None}
                for r in rows
            ]}

# ===================== MARKET & NEWS (unchanged) =====================
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

# ===================== ADMIN (unchanged) =====================
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

@app.get("/api/admin/analytics")
def admin_analytics(user: dict = Depends(get_current_user)):
    if not user or user["tier"] != "founder":
        raise HTTPException(403, "Access denied")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT tier, COUNT(*) FROM users GROUP BY tier")
            tier_counts = {r[0]: r[1] for r in c.fetchall()}
            c.execute("""
                SELECT EXTRACT(HOUR FROM created) as hour, COUNT(*) as count
                FROM chat_messages WHERE created > NOW() - INTERVAL '24 hours'
                GROUP BY hour ORDER BY hour
            """)
            hourly = [{"hour": int(r[0]), "count": r[1]} for r in c.fetchall()]
            c.execute("""
                SELECT domain, COUNT(*) FROM memories WHERE created > NOW() - INTERVAL '7 days'
                GROUP BY domain ORDER BY COUNT(*) DESC LIMIT 10
            """)
            topics = [{"domain": r[0], "count": r[1]} for r in c.fetchall()]
            return {
                "users_by_tier": tier_counts,
                "hourly_messages": hourly,
                "popular_topics": topics
            }

# ===================== SELF-LEARNING (unchanged) =====================
DATASET_DIR = "datasets"
os.makedirs(DATASET_DIR, exist_ok=True)

@app.post("/api/admin/generate-dataset")
def generate_dataset(user: dict = Depends(get_current_user)):
    if not user or user["tier"] != "founder":
        raise HTTPException(403, "Access denied")
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("""
                    SELECT cm.chat_id, cm.system_prompt, cm.content AS assistant_content,
                           (SELECT content FROM chat_messages WHERE chat_id=cm.chat_id AND role='user' AND created < cm.created ORDER BY created DESC LIMIT 1) AS user_content
                    FROM chat_messages cm
                    JOIN feedback f ON cm.id = f.message_id
                    WHERE f.rating = 1 AND cm.role = 'assistant' AND cm.system_prompt IS NOT NULL
                """)
                rows = c.fetchall()
        
        dataset = []
        for r in rows:
            chat_id, system_prompt, assistant_content, user_content = r
            if not user_content:
                continue
            dataset.append({
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": assistant_content}
                ]
            })
        
        if not dataset:
            return {"status": "no data", "examples": 0}
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(DATASET_DIR, f"training_{timestamp}.jsonl")
        with open(file_path, "w") as f:
            for entry in dataset:
                f.write(json.dumps(entry) + "\n")
        
        return {
            "status": "generated",
            "file": file_path,
            "examples": len(dataset)
        }
    except Exception as e:
        logger.error(f"Dataset generation error: {e}")
        raise HTTPException(500, str(e))

@app.post("/api/admin/start-finetune")
def start_finetune(user: dict = Depends(get_current_user)):
    if not user or user["tier"] != "founder":
        raise HTTPException(403, "Access denied")
    
    if not settings.OPENAI_API_KEY:
        raise HTTPException(400, "OPENAI_API_KEY is required for fine‑tuning. Add it to .env.")
    
    datasets = sorted([f for f in os.listdir(DATASET_DIR) if f.startswith("training_") and f.endswith(".jsonl")])
    if not datasets:
        raise HTTPException(404, "No dataset found. Generate one first via /api/admin/generate-dataset.")
    latest_dataset = os.path.join(DATASET_DIR, datasets[-1])
    
    try:
        with open(latest_dataset, "rb") as f:
            upload_res = requests.post(
                "https://api.openai.com/v1/files",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                files={"file": f, "purpose": (None, "fine-tune")}
            )
        if upload_res.status_code != 200:
            raise Exception(f"File upload failed: {upload_res.text}")
        file_id = upload_res.json()["id"]
        
        job_res = requests.post(
            "https://api.openai.com/v1/fine_tuning/jobs",
            headers={
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "training_file": file_id,
                "model": "gpt-4o-mini-2024-07-18"
            }
        )
        if job_res.status_code != 200:
            raise Exception(f"Fine‑tuning job failed: {job_res.text}")
        job_id = job_res.json()["id"]
        
        for _ in range(30):
            time.sleep(10)
            status_res = requests.get(
                f"https://api.openai.com/v1/fine_tuning/jobs/{job_id}",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
            )
            status = status_res.json()
            if status.get("status") == "succeeded":
                ft_model_id = status["fine_tuned_model"]
                with get_db() as conn:
                    with conn.cursor() as c:
                        c.execute("UPDATE model_versions SET active=FALSE WHERE base_model='gpt-4o-mini-2024-07-18'")
                        c.execute("""
                            INSERT INTO model_versions (id, base_model, finetuned_model_id, dataset_path, active)
                            VALUES (%s, %s, %s, %s, TRUE)
                        """, (sid(), "gpt-4o-mini-2024-07-18", ft_model_id, latest_dataset))
                        conn.commit()
                create_notification(user["id"], "success", f"Fine‑tuning complete! New model ID: {ft_model_id}")
                return {
                    "status": "fine-tuned",
                    "model_id": ft_model_id,
                    "dataset": latest_dataset
                }
            elif status.get("status") == "failed":
                raise Exception("Fine‑tuning job failed: " + str(status))
        raise Exception("Fine‑tuning job timed out")
    except Exception as e:
        create_notification(user["id"], "error", f"Fine‑tuning failed: {str(e)}")
        logger.error(f"Fine‑tuning error: {e}")
        raise HTTPException(500, str(e))

# ===================== CHAT EXPORT (unchanged) =====================
@app.get("/api/export/chats/{chat_id}")
def export_chat(chat_id: str, format: str = "json", user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Not authenticated")
    tier = user["tier"]
    if tier not in ("plus", "pro", "pro_max", "founder"):
        raise HTTPException(403, "Export available on paid plans")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id FROM chats WHERE id=%s AND user_id=%s", (chat_id, user["id"]))
            if not c.fetchone():
                raise HTTPException(404, "Chat not found")
            c.execute("SELECT role, content, model, created FROM chat_messages WHERE chat_id=%s ORDER BY created ASC", (chat_id,))
            rows = c.fetchall()
            messages = [{"role": r[0], "content": r[1], "model": r[2] or "AI", "created": r[3].isoformat() if r[3] else None} for r in rows]
            if format == "csv":
                output = StringIO()
                writer = csv.writer(output, quoting=csv.QUOTE_ALL)
                writer.writerow(["role", "content", "model", "created"])
                for m in messages:
                    writer.writerow([m["role"], m["content"], m["model"], m["created"]])
                output.seek(0)
                return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=chat-{chat_id}.csv"})
            else:
                return JSONResponse(content={"chat_id": chat_id, "messages": messages})

# ===================== HEALTH =====================
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
    
    ai_status = "connected" if (settings.GROQ_API_KEY or settings.OPENROUTER_API_KEY or settings.AIMLAPI_API_KEY or settings.ALMLAPI_API_KEY) else "disconnected"
    providers = []
    if settings.GROQ_API_KEY: providers.append("groq")
    if settings.OPENROUTER_API_KEY: providers.append("openrouter")
    if settings.AIMLAPI_API_KEY or settings.ALMLAPI_API_KEY: providers.append("aimlapi")
    providers.append("puter (free, no key)")
    if settings.OPENROUTER_API_KEY: providers.append("deepseek")
    
    return {
        "status": "ok",
        "version": "32.0",
        "database": db_status,
        "ai": ai_status,
        "providers": providers,
        "auth": "email_password",
        "reasoning_engine": True,
        "intelligence_level": "full",
        "tiers": ["guest", "free", "plus", "pro", "pro_max", "founder"],
        "notifications": True,
        "tool_calling": True,
        "image_analysis": True,
        "streaming": True,
        "configurable_params": True
    }

# ===================== WEB SEARCH (unchanged) =====================
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
        symbols = ["SPX", "NDX", "DJI", "AAPL", "MSFT", "NVDA", "TSLA", "GOOGL", "META", "AMZN"]
        for sym in symbols:
            try:
                r = requests.get(f"https://finnhub.io/api/v1/quote?symbol={sym}&token={settings.FINNHUB_API_KEY}", timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("c"):
                        results[sym] = {"price": data["c"], "change": round(data.get("dp", 0), 2)}
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

# ===================== PWA & DYNAMIC FAVICON =====================
@app.get("/manifest.json")
async def manifest():
    return JSONResponse(content={
        "name": "CAPITAN AI",
        "short_name": "CAPITAN",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0e6e8e",
        "theme_color": "#0e6e8e",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}
        ]
    })

@app.get("/favicon.ico")
async def favicon():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
        <rect width="100" height="100" fill="#0e6e8e" rx="20"/>
        <circle cx="50" cy="50" r="35" fill="none" stroke="white" stroke-width="6"/>
        <text x="50" y="68" text-anchor="middle" font-size="50" fill="white" font-family="Arial,sans-serif" font-weight="bold">C</text>
    </svg>'''
    return Response(content=svg, media_type="image/svg+xml")

@app.get("/icon-192.png")
async def icon_192():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
        <rect width="100" height="100" fill="#0e6e8e" rx="20"/>
        <circle cx="50" cy="50" r="35" fill="none" stroke="white" stroke-width="6"/>
        <text x="50" y="68" text-anchor="middle" font-size="50" fill="white" font-family="Arial,sans-serif" font-weight="bold">C</text>
    </svg>'''
    return Response(content=svg, media_type="image/svg+xml")

@app.get("/icon-512.png")
async def icon_512():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
        <rect width="100" height="100" fill="#0e6e8e" rx="20"/>
        <circle cx="50" cy="50" r="35" fill="none" stroke="white" stroke-width="6"/>
        <text x="50" y="68" text-anchor="middle" font-size="50" fill="white" font-family="Arial,sans-serif" font-weight="bold">C</text>
    </svg>'''
    return Response(content=svg, media_type="image/svg+xml")

@app.get("/icon-180.png")
async def icon_180():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 180">
        <rect width="180" height="180" fill="#0e6e8e" rx="36"/>
        <circle cx="90" cy="90" r="63" fill="none" stroke="white" stroke-width="9"/>
        <text x="90" y="117" text-anchor="middle" font-size="90" fill="white" font-family="Arial,sans-serif" font-weight="bold">C</text>
    </svg>'''
    return Response(content=svg, media_type="image/svg+xml")

@app.get("/")
async def root():
    return {
        "name": "CAPITAN AI",
        "version": "32.0",
        "status": "operational",
        "auth": "email_password",
        "pwa_supported": True,
        "tiers": ["guest", "free", "plus", "pro", "pro_max", "founder"],
        "intelligence": "self_learning",
        "reasoning": "chain_of_thought_enabled",
        "task_routing": True,
        "notifications": True,
        "conversation_mode_fixed": True,
        "puter_api": True,
        "deepseek": True,
        "tool_calling": True,
        "image_analysis": True,
        "streaming": True,
        "configurable_params": True
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"\n{'='*70}")
    print(f"🚀 CAPITAN AI v32.0 - Full Intelligence Suite Active")
    print(f"🔐 JWT_SECRET & FOUNDER_KEY required from env")
    print(f"📍 Backend: 0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
