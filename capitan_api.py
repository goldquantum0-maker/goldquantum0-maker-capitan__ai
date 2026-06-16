"""
CAPITAN AI — Enterprise Backend v31.0 (System Prompt v2.0 + Task Classifier)
CLOSEAI Technologies
World‑Class General‑Purpose AI | Intent‑Driven | Trustworthy | Warm & Engaging
Full task/intent routing, content generation mode, conversation continuity.
Self‑learning pipeline, feedback, fine‑tuning, dynamic icons – all original.
"""

import os, re, json, uuid, time, hmac, hashlib, base64, secrets, requests, logging, bcrypt
import PyPDF2, docx, openpyxl, io, csv
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple
from contextlib import contextmanager
from io import StringIO

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
from pydantic_settings import BaseSettings
import psycopg2
import uvicorn

app = FastAPI(title="CAPITAN AI API", version="31.0")

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
    OPENAI_API_KEY: str = ""          # for fine‑tuning & dataset upload

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

Example:

User: "Improve this landing page"

Correct Interpretation:
Content Creation

Wrong Interpretation:
Marketing discussion

User: "Gold is at resistance"

Correct Interpretation:
Financial Analysis

Wrong Interpretation:
Definition of resistance

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
"""

# ===================== TASK CLASSIFIER (INTENT DETECTION) =====================
def classify_task(q: str) -> str:
    """Classify the user's actual goal based on keywords and patterns.
    Returns one of: Information Request, Problem Solving, Decision Making,
    Content Creation, Coding / Engineering, Financial Analysis, Research,
    Planning, Learning / Education, Conversation."""
    q_lower = q.lower()

    # Content Creation signals
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

    # Coding / Engineering
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

    # Financial Analysis
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

    # Research
    research_kw = [
        "research", "explain", "compare", "summary", "overview",
        "deep dive", "investigate", "study", "report", "analyze",
        "pros and cons", "difference between", "how does", "what is",
        "tell me about"
    ]
    for kw in research_kw:
        if kw in q_lower:
            return "Research"

    # Planning
    plan_kw = [
        "plan", "roadmap", "steps to", "how do i", "schedule",
        "timeline", "goal", "strategy", "approach", "framework",
        "best way to", "guide", "tutorial", "learn", "course"
    ]
    for kw in plan_kw:
        if kw in q_lower:
            return "Planning"

    # Decision Making
    decision_kw = [
        "should i", "which one", "pick", "choose", "better option",
        "vs", "versus", "or", "worth it", "recommend", "suggest"
    ]
    for kw in decision_kw:
        if kw in q_lower:
            return "Decision Making"

    # Learning / Education
    learn_kw = [
        "teach me", "explain like", "tutorial", "beginner", "new to",
        "learn", "understand", "concept", "definition", "meaning"
    ]
    for kw in learn_kw:
        if kw in q_lower:
            return "Learning / Education"

    # Problem Solving
    problem_kw = [
        "issue", "error", "not working", "broken", "fix", "help",
        "stuck", "can't", "won't", "fail", "crash", "bug"
    ]
    for kw in problem_kw:
        if kw in q_lower:
            return "Problem Solving"

    # Information Request – generic what/when/where/who queries
    if re.search(r'^(what|when|where|who|how many|how much|how long|how far)\b', q_lower):
        return "Information Request"

    # Default: Conversation / General
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
    base = CORE_INSTRUCTIONS  # v2.0 prompt – no token replacements needed, but we add context

    # Add time context
    base += f"\n\nCurrent time: {tc['day']}, {tc['date']} at {tc['utc_time']}. {tc['greeting_context']}"

    # User profile
    if user_profile:
        name = user_profile.get("name", "User")
        tier_name = TIER_CONFIG.get(user_profile.get("tier", "free"), {}).get("name", "Free")
        prof = f"\n\n[USER PROFILE]\nName: {name}\nTier: {tier_name}\nPreferred domain: {user_profile.get('preferred_domain', 'general')}\nReasoning depth: {user_profile.get('reasoning_depth', 1)}"
        base += prof

    # Conversation summary
    if history and len(history) >= 6:
        summary = _generate_conversation_summary(history)
        if summary:
            base += "\n\n[CONVERSATION SUMMARY]\n" + summary

    # Previous exchange
    if history and len(history) >= 2:
        prev_exchange = _extract_previous_exchange(history)
        if prev_exchange:
            base += "\n\n[PREVIOUS EXCHANGE]\n" + prev_exchange

    if user_query:
        base += f"\n\nUSER REQUEST: {user_query}"

    # Task mode instruction
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
    # Information Request and Conversation use the default behavior

    if tier == "founder" and settings.FOUNDER_EXTRA_PROMPT:
        base += "\n\n[FOUNDER DIRECTIVES]\n" + settings.FOUNDER_EXTRA_PROMPT

    if web_results:
        base += "\n\nWEB SEARCH RESULTS:\n" + "\n".join(
            [f"- {r['title']}: {r['snippet'][:200]}" for r in web_results[:4]]
        )

    return base

# ===================== RATE LIMITING (unchanged) =====================
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

# ===================== DAILY LIMIT (unchanged) =====================
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

# ===================== DOMAIN CLASSIFICATION (unchanged) =====================
def classify_query(q: str, history: List[dict] = None) -> str:
    q = q.lower()
    if history and len(history) >= 2:
        last_substantial = None
        for m in reversed(history):
            if m["role"] == "user" and len(m["content"].split()) > 3:
                last_substantial = m["content"]
                break
        if last_substantial and not re.search(r'hello|hi|hey|good morning|good afternoon|good evening|thanks|thank you', q):
            if len(q.split()) <= 3:
                return classify_query(last_substantial)

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

# ===================== REASONING ENGINE (unchanged) =====================
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

# ===================== AI MODEL CALL (FINE-TUNED MODEL SUPPORT) =====================
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

    # Determine base model for fine-tuning check
    base_model_name = "gpt-4o"
    if tier in ("pro", "pro_max", "founder"):
        ft_model = get_latest_fine_tuned_model(base_model_name)
        if ft_model:
            base_model_name = ft_model

    # AI/ML API for Pro, ProMax, Founder
    if tier in ("pro", "pro_max", "founder") and (settings.AIMLAPI_API_KEY or settings.ALMLAPI_API_KEY):
        api_key = settings.AIMLAPI_API_KEY or settings.ALMLAPI_API_KEY
        try:
            r = requests.post(
                "https://api.aimlapi.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": base_model_name,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 4000
                },
                timeout=60
            )
            if r.status_code == 200:
                content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    return content, f"{base_model_name} (AIML API)", reasoning_chain
        except Exception as e:
            logger.error(f"AIML API error: {e}")

    # ProMax ensemble (OpenRouter)
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
    
    # Pro (OpenRouter Claude)
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
    
    # Plus (Groq 70B)
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
    
    # Fallback: Groq 8B
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

# ===================== TIER CONFIGURATION (unchanged) =====================
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

# ===================== CHAT ENDPOINT (NOW USES TASK CLASSIFIER) =====================
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
    
    # Retrieve message history
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
    task_type = classify_task(user_msg)   # <-- new intent routing
    
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
    
    result, model_used, reasoning_chain = call_ai_model(
        [{"role": "system", "content": prompt}] + history, tier, reasoning_depth, domain
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

# ===================== FEEDBACK ENDPOINT =====================
class FeedbackRequest(BaseModel):
    message_id: str
    rating: int  # 1 = like, 0 = dislike
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
    "pro": ["Limited messaging (100/day)", "Claude 3.5 Sonnet", "File uploads (50MB)", "Live markets", "Web search", "3-step reasoning"],
    "pro_max": ["Unlimited messaging", "GPT-4o + Claude Ensemble", "File uploads (100MB)", "Live markets", "Advanced reasoning", "Priority support"]
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

# ===================== SELF-LEARNING: DATASET GENERATION =====================
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

# ===================== SELF-LEARNING: FINE-TUNING TRIGGER =====================
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
                return {
                    "status": "fine-tuned",
                    "model_id": ft_model_id,
                    "dataset": latest_dataset
                }
            elif status.get("status") == "failed":
                raise Exception("Fine‑tuning job failed: " + str(status))
        raise Exception("Fine‑tuning job timed out")
    except Exception as e:
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

# ===================== HEALTH (unchanged) =====================
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
    
    return {
        "status": "ok",
        "version": "31.0",
        "database": db_status,
        "ai": ai_status,
        "providers": providers,
        "auth": "email_password",
        "reasoning_engine": True,
        "intelligence_level": "full",
        "tiers": ["guest", "free", "plus", "pro", "pro_max", "founder"]
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
        "version": "31.0",
        "status": "operational",
        "auth": "email_password",
        "pwa_supported": True,
        "tiers": ["guest", "free", "plus", "pro", "pro_max", "founder"],
        "intelligence": "self_learning",
        "reasoning": "chain_of_thought_enabled",
        "task_routing": True
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"\n{'='*70}")
    print(f"🚀 CAPITAN AI v31.0 - Intent‑Driven Self‑Learning AI")
    print(f"🔐 JWT_SECRET & FOUNDER_KEY required from env")
    print(f"📍 Backend: 0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)