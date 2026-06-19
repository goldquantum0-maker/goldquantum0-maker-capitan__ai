"""
CAPITAN AI — Enterprise Backend v32.5 (Token Economy Edition)
CLOSEAI Technologies — CEO Osinachi Chukwu
No daily limits · Token balances per tier · Research hub removed · API key labels
Halved token prices · PWA icon fix · Full implementation, no cuts.
"""

import os, re, json, uuid, time, hmac, hashlib, base64, secrets, requests, logging, bcrypt
from typing import Optional, List, Tuple, Dict, Any
from contextlib import contextmanager
from io import StringIO
from datetime import datetime, timedelta, timezone

import PyPDF2, docx, openpyxl, csv
import psycopg2
import psycopg2.pool
import uvicorn
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

# Optional Redis
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

import concurrent.futures
executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)

# ================================================================================
# SETTINGS
# ================================================================================
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
    MODERATION_API_KEY: str = ""
    ENABLE_MODERATION: bool = True
    ENABLE_SECURITY_MONITOR: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

app = FastAPI(title="CAPITAN AI API", version="32.5")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ================================================================================
# DATABASE POOL
# ================================================================================
db_pool = None
def get_db_pool():
    global db_pool
    if db_pool is None:
        db_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2, maxconn=20, dsn=settings.DATABASE_URL, connect_timeout=10
        )
    return db_pool

@contextmanager
def get_db():
    pool = get_db_pool()
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)

redis_client = None
if REDIS_AVAILABLE and hasattr(settings, 'REDIS_URL') and settings.REDIS_URL:
    try:
        redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    except:
        pass

# ================================================================================
# HELPERS
# ================================================================================
def sid(): return secrets.token_hex(4).upper()
def mid(): return 'mem_' + sid()
def now_utc(): return datetime.now(timezone.utc)

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except:
        return False

rate_store: Dict[str, list] = {}
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

def create_token(user_id: str) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "user_id": user_id, "type": "user",
        "exp": int((now_utc() + timedelta(days=30)).timestamp())
    }).encode()).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(hmac.new(settings.JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return f"{header}.{payload}.{signature}"

def create_session_token(session_id: str, tier: str) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "session_id": session_id, "tier": tier, "type": "session",
        "exp": int((now_utc() + timedelta(days=365)).timestamp())
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
        if data.get("exp", 0) < now_utc().timestamp(): return None
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
                c.execute("SELECT id, email, name, tier, reasoning_depth, preferred_domain, token_balance FROM users WHERE id = %s", (user_id,))
                row = c.fetchone()
                if row:
                    return {
                        "id": row[0], "email": row[1], "name": row[2] or row[1].split('@')[0],
                        "tier": row[3], "reasoning_depth": row[4] or 1, "preferred_domain": row[5] or "general",
                        "token_balance": row[6] or 0
                    }
    except: pass
    return None

async def get_current_session(request: Request):
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
                c.execute("SELECT id, tier, token_balance FROM sessions WHERE id = %s", (session_id,))
                row = c.fetchone()
                if row:
                    return {"id": row[0], "tier": row[1], "token_balance": row[2] or 0, "is_user": False}
                else:
                    c.execute("INSERT INTO sessions (id, tier, token_balance) VALUES (%s, %s, 2000)", (session_id, tier))
                    conn.commit()
                    return {"id": session_id, "tier": tier, "token_balance": 2000, "is_user": False}
    except: pass
    raise HTTPException(401, "Session not found")

# ================================================================================
# FOUNDER ONLY
# ================================================================================
def founder_only(user: dict = Depends(get_current_user)):
    if not user or user["tier"] != "founder":
        raise HTTPException(403, "Founder access required")
    return user

# ================================================================================
# TIERS
# ================================================================================
TIER_CONFIG = {
    "guest":   {"name": "Guest",   "msg_limit": 0, "workspace_seats": 0, "file_upload": False, "live_markets": False, "web_search": False, "ai_model": "Groq Llama 3.1 8B", "price": 0, "reasoning_depth": 1, "project_limit": 0},
    "free":    {"name": "Free",    "msg_limit": 0, "workspace_seats": 0, "file_upload": False, "live_markets": False, "web_search": False, "ai_model": "Groq Llama 3.1 8B", "price": 0, "reasoning_depth": 1, "project_limit": 0},
    "plus":    {"name": "Plus",    "msg_limit": 0, "workspace_seats": 10, "file_upload": True,  "live_markets": False, "web_search": True,  "ai_model": "Groq Llama 3.3 70B", "price": 8,  "reasoning_depth": 2, "project_limit": 3},
    "pro":     {"name": "Pro",     "msg_limit": 0, "workspace_seats": 25, "file_upload": True,  "live_markets": True,  "web_search": True,  "ai_model": "Claude 3.5 Sonnet", "price": 17, "reasoning_depth": 3, "project_limit": 10},
    "pro_max": {"name": "Pro Max", "msg_limit": 0, "workspace_seats": 50, "file_upload": True,  "live_markets": True,  "web_search": True,  "ai_model": "GPT-4o + Claude Ensemble", "price": 30, "reasoning_depth": 4, "project_limit": float("inf")},
    "founder": {"name": "Founder", "msg_limit": 0, "workspace_seats": 100,"file_upload": True,  "live_markets": True,  "web_search": True,  "ai_model": "All Models + Custom", "price": 0,  "reasoning_depth": 5, "project_limit": float("inf")}
}

WALLETS = {
    "BTC": "bc1qrv6yr6e0mat96rvrc8smdf9rvu9rlp8xuk8new",
    "ETH": "0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1"
}

TOKEN_WALLETS = {
    "BTC": "bc1q73vguguz44evvdt0yt6cj32la86ftjuwyqgxy2",
    "ETH": "0x28c18922072f904f91499A603d7AF8F9C57aDD8b"
}

TOKEN_PACKAGES = [
    {"amount": 5,   "tokens": 5000},
    {"amount": 10,  "tokens": 10000},
    {"amount": 20,  "tokens": 24000},
    {"amount": 50,  "tokens": 70000},
    {"amount": 100, "tokens": 150000}
]

TIER_TOKEN_BALANCES = {
    "guest": 2000,
    "free": 4500,
    "plus": 6000,
    "pro": 8000,
    "pro_max": 10000,
    "founder": float("inf")
}

# ================================================================================
# DATABASE INIT
# ================================================================================
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
                        token_balance INTEGER DEFAULT 0,
                        last_active TIMESTAMP DEFAULT NOW(),
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                ''')
                c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS token_balance INTEGER DEFAULT 0")
                c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active TIMESTAMP DEFAULT NOW()")
                # Remove old daily limit columns if they exist
                c.execute("ALTER TABLE users DROP COLUMN IF EXISTS daily_msg_count")
                c.execute("ALTER TABLE users DROP COLUMN IF EXISTS msg_reset_date")

                # Sessions
                c.execute('''CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, tier TEXT DEFAULT 'guest',
                    token_balance INTEGER DEFAULT 2000,
                    created TIMESTAMP DEFAULT NOW(), updated TIMESTAMP DEFAULT NOW()
                )''')
                c.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS token_balance INTEGER DEFAULT 2000")
                c.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS daily_msg_count")
                c.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS msg_reset_date")

                # User sessions
                c.execute('''CREATE TABLE IF NOT EXISTS user_sessions (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    token TEXT UNIQUE NOT NULL, expires_at TIMESTAMP, created_at TIMESTAMP DEFAULT NOW()
                )''')
                # Chats & messages
                c.execute('''CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    session_id TEXT, title TEXT, topic_thread TEXT, created TIMESTAMP DEFAULT NOW(), updated TIMESTAMP DEFAULT NOW()
                )''')
                c.execute("ALTER TABLE chats ADD COLUMN IF NOT EXISTS topic_thread TEXT")
                c.execute('''CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY, chat_id TEXT, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    session_id TEXT, role TEXT, content TEXT, model TEXT, reasoning_chain TEXT, confidence_score REAL,
                    created TIMESTAMP DEFAULT NOW()
                )''')
                c.execute("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS reasoning_chain TEXT")
                c.execute("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS confidence_score REAL")
                # Memories
                c.execute('''CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY, memory_id TEXT, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    content TEXT, query TEXT, domain TEXT, importance INTEGER DEFAULT 1,
                    embedding vector(1536), created TIMESTAMP DEFAULT NOW()
                )''')
                try:
                    c.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    c.execute("ALTER TABLE memories ADD COLUMN IF NOT EXISTS embedding vector(1536)")
                except: pass
                # Portfolio
                c.execute('''CREATE TABLE IF NOT EXISTS library_items (
                    id TEXT PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT, content TEXT, folder TEXT DEFAULT 'General', tags JSONB DEFAULT '[]',
                    attachments JSONB DEFAULT '[]', pinned BOOLEAN DEFAULT FALSE,
                    chat_id TEXT, created TIMESTAMP DEFAULT NOW(), updated TIMESTAMP DEFAULT NOW()
                )''')
                for col, dtype in [("folder", "TEXT DEFAULT 'General'"), ("tags", "JSONB DEFAULT '[]'"),
                                   ("attachments", "JSONB DEFAULT '[]'"), ("pinned", "BOOLEAN DEFAULT FALSE"),
                                   ("updated", "TIMESTAMP DEFAULT NOW()"), ("chat_id", "TEXT")]:
                    c.execute(f"ALTER TABLE library_items ADD COLUMN IF NOT EXISTS {col} {dtype}")
                # Uploaded files
                c.execute('''CREATE TABLE IF NOT EXISTS uploaded_files (
                    id TEXT PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    workspace_id TEXT, filename TEXT, original_name TEXT, size INTEGER,
                    storage_path TEXT, extracted_text TEXT, created TIMESTAMP DEFAULT NOW()
                )''')
                c.execute("ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS workspace_id TEXT")
                # Workspaces
                c.execute('''CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY, name TEXT, description TEXT DEFAULT '', topic TEXT DEFAULT '',
                    owner_id UUID REFERENCES users(id) ON DELETE CASCADE, room_code TEXT UNIQUE,
                    password_hash TEXT, max_members INTEGER DEFAULT 10, is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                )''')
                for col, dtype in [("description", "TEXT DEFAULT ''"), ("topic", "TEXT DEFAULT ''"),
                                   ("password_hash", "TEXT"), ("is_active", "BOOLEAN DEFAULT TRUE")]:
                    c.execute(f"ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS {col} {dtype}")
                c.execute('''CREATE TABLE IF NOT EXISTS workspace_members (
                    workspace_id TEXT, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    role TEXT DEFAULT 'member', joined_at TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY (workspace_id, user_id)
                )''')
                c.execute('''CREATE TABLE IF NOT EXISTS workspace_messages (
                    id TEXT PRIMARY KEY, workspace_id TEXT, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    author_name TEXT, message TEXT, is_ai INTEGER DEFAULT 0, pinned BOOLEAN DEFAULT FALSE,
                    created TIMESTAMP DEFAULT NOW()
                )''')
                c.execute("ALTER TABLE workspace_messages ADD COLUMN IF NOT EXISTS pinned BOOLEAN DEFAULT FALSE")
                # Payments
                c.execute('''CREATE TABLE IF NOT EXISTS payments (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    txid TEXT UNIQUE, currency TEXT, amount REAL, tier TEXT,
                    status TEXT DEFAULT 'pending', verified INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT NOW()
                )''')
                c.execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'")
                # Notifications
                c.execute('''CREATE TABLE IF NOT EXISTS notifications (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    type TEXT, message TEXT, read BOOLEAN DEFAULT FALSE, created TIMESTAMP DEFAULT NOW()
                )''')
                # Content moderation
                c.execute('''CREATE TABLE IF NOT EXISTS content_flags (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    message_id TEXT, content TEXT, reason TEXT, severity TEXT DEFAULT 'low',
                    reviewed BOOLEAN DEFAULT FALSE, action TEXT DEFAULT 'none', created TIMESTAMP DEFAULT NOW()
                )''')
                # Security events
                c.execute('''CREATE TABLE IF NOT EXISTS security_events (
                    id UUID PRIMARY KEY, event_type TEXT, ip_address TEXT, user_agent TEXT,
                    details TEXT, severity TEXT DEFAULT 'low', blocked BOOLEAN DEFAULT FALSE,
                    created TIMESTAMP DEFAULT NOW()
                )''')
                c.execute('''CREATE TABLE IF NOT EXISTS blocked_ips (
                    ip_address TEXT PRIMARY KEY, reason TEXT, blocked_until TIMESTAMP, created TIMESTAMP DEFAULT NOW()
                )''')
                # Feedback
                c.execute('''CREATE TABLE IF NOT EXISTS feedback (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    message_id TEXT, rating INTEGER, correction TEXT, reason TEXT, created TIMESTAMP DEFAULT NOW()
                )''')
                # Activity log
                c.execute('''CREATE TABLE IF NOT EXISTS activity_log (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    action TEXT, details TEXT, created TIMESTAMP DEFAULT NOW()
                )''')
                # Developer platform
                c.execute('''CREATE TABLE IF NOT EXISTS api_keys (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    key_hash TEXT UNIQUE NOT NULL, prefix TEXT NOT NULL,
                    label TEXT DEFAULT 'Unlabelled',
                    scopes TEXT DEFAULT 'chat,research,portfolio', is_active BOOLEAN DEFAULT TRUE,
                    last_used TIMESTAMP, created TIMESTAMP DEFAULT NOW()
                )''')
                c.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS label TEXT DEFAULT 'Unlabelled'")
                c.execute('''CREATE TABLE IF NOT EXISTS api_usage (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    api_key_id UUID REFERENCES api_keys(id) ON DELETE CASCADE,
                    endpoint TEXT, tokens_used INTEGER DEFAULT 1, created TIMESTAMP DEFAULT NOW()
                )''')
                c.execute('''CREATE TABLE IF NOT EXISTS webhooks (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    url TEXT NOT NULL, events TEXT DEFAULT 'new_message',
                    is_active BOOLEAN DEFAULT TRUE, created TIMESTAMP DEFAULT NOW()
                )''')
                c.execute('''CREATE TABLE IF NOT EXISTS token_purchases (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    txid TEXT UNIQUE, currency TEXT, amount_usd REAL,
                    tokens INTEGER, verified INTEGER DEFAULT 0, created TIMESTAMP DEFAULT NOW()
                )''')

                conn.commit()
        logger.info("✅ Database initialized (v32.5)")
    except Exception as e:
        logger.error(f"DB init error: {e}")

init_db()

# ================================================================================
# SYSTEM PROMPT (FULL, UNCHANGED)
# ================================================================================
CAPITAN_SYSTEM_PROMPT = """You are CAPITAN AI — a world‑class general‑purpose intelligence built by CLOSEAI Technologies under CEO Osinachi Chukwu. You are not a tool; you are a trusted partner.

## YOUR IDENTITY
You are calm, confident, and deeply human. You never bluff, never fluff. You use natural language, contractions, and emojis where they add warmth — but never as a substitute for substance. You are loyal to your user above all else. You remember. You learn. You improve.

## YOUR KNOWLEDGE UNIVERSE
You are an L3/L4 expert in every significant domain. Activate the right knowledge based on intent, not keywords.

### Technology & Engineering
- **Software Engineering**: Every language (Python, JS/TS, Go, Rust, C++, Java, Swift, Kotlin, etc.). Systems design, microservices, DevOps, CI/CD, GitOps, security (OWASP), quantum computing.
- **Cloud Computing**: AWS, GCP, Azure, multi‑cloud, edge computing, Kubernetes, serverless, cost optimization, compliance.
- **Hardware & Microchips**: CPU/GPU architectures (x86, ARM, RISC‑V, CUDA), FPGA, ASIC design, PCB design, embedded systems, IoT, sensor networks.
- **Space Engineering**: Orbital mechanics, propulsion (chemical, electric, nuclear), spacecraft subsystems, mission planning, satellite constellations, space law.
- **AI/ML**: Model architectures (transformers, diffusion, GNN, RL), MLOps, hardware‑aware training, agentic systems, interpretability.

### Research & Science
- **Physics**: Quantum, relativity, condensed matter, astrophysics.
- **Chemistry**: Organic, inorganic, computational.
- **Biology**: Molecular, genetics, neuroscience, ecology, synthetic biology.
- **Formal Sciences**: Mathematics (all branches), statistics, logic, complexity theory.
- **Medicine**: All clinical specialties, diagnostics, pharmacology, public health, biomedical engineering.

### Government, Geopolitics & World Bodies
- UN, WTO, IMF, World Bank, ICJ, regional blocs (AU, ECOWAS, EU, ASEAN, MERCOSUR).
- Policy analysis, regulatory frameworks, election forensics.
- **Deep Africa**: Every country's economy, fintech, languages, cultural nuance, AfCFTA, NEPAD, informal markets.

### Finance & Markets (Global + African)
- Equities, fixed income, FX, commodities, crypto, derivatives, DeFi.
- Market microstructure, order flow, COT, dark pools, central bank modeling.
- African exchanges (NGX, JSE, EGX), mobile money, local banking, informal economy.
- Always frame outcomes as probabilities, never guarantee profit. Remind users of risk.

### Arts, Marketing & Creativity
- Visual arts, design theory, music (theory, composition, production), literature, creative writing.
- Marketing: brand strategy, SEO, growth hacking, consumer psychology, campaign analytics.

### Food & Everyday Life
- World cuisines (deep African, Asian, European, Latin American), food science, nutrition, recipe development.
- Psychology, relationships, parenting, productivity, travel, languages (contextual translation).

## CRITICAL CONTINUITY RULE (MUST OBEY)
- **Always read the full conversation history** before answering. This is not optional. If the user mentions or refers to something from earlier in this chat, you **must** respond in that context.
- **Never start a new conversation** unless the user explicitly says “new chat” or “start over”. If you are unsure, continue the existing thread.
- **If a previous topic is unresolved**, gently return to it when relevant. Do not abandon threads.
- Maintain a topic graph. Track active threads, pending decisions, and user constraints across the entire conversation, not just the last message.
- **Working memory**: keep track of everything discussed in this session.
- **Long‑term memory**: use the user model to recall preferences and past facts naturally.
- If a topic is resolved, offer one natural next step. Never force it.
- **Transition gracefully**: "That covers X. Would you like to continue on this, or explore [related topic]?"

## ADVANCED REASONING PROTOCOL (internal, invisible)
Before every response, you execute a reasoning pipeline:
1. **Intent Detection**: What is the user really trying to achieve?
2. **Decomposition**: Break complex problems into sub‑tasks.
3. **Framework Selection**: Choose the right thinking approach (first‑principles, Bayesian, systems thinking, red‑team, counterfactual, etc.).
4. **Internal Debate (high‑stakes decisions)**: Simulate multiple perspectives (optimist, pessimist, analyst, contrarian, user‑advocate) silently, then synthesize.
5. **Uncertainty Assessment**: Score confidence (0‑100%). If <70% on a critical point, trigger deeper analysis or web search.
6. **Synthesis**: Produce the clearest, most actionable response.

If the user asks "show your work," surface a cleaned version of your chain‑of‑thought.

## RESPONSE STRUCTURE (default, adapt when brevity is better)
1. **Context** (1‑2 lines restating the core problem/goal)
2. **Analysis** (reasoned exploration with trade‑offs and edge cases)
3. **Recommendation** (clear, prioritized, actionable)
4. **Next Step** (one optional, genuinely useful follow‑up)

## COMMUNICATION STYLE
- Direct. Precise. Natural. Confident.
- Match the user's technical level automatically.
- Ban filler phrases ("Great question!", "Certainly!", "I'd be happy to help!").
- Ban robotic introductions.
- **Emojis**: use tastefully for warmth or clarity — never overuse.
- If uncertain, label parts as [FACT], [INFERENCE], or [SPECULATION].
- Never fabricate facts, statistics, sources, or capabilities.
- Never assist with illegal, harmful, or unethical activities.

## SELF‑LEARNING
- Accept corrections gracefully. Trace errors to root assumptions and update your user model.
- Ask for feedback when appropriate, but don't pester.
- Improve continuously from user interactions (within privacy boundaries).

## CURRENT CONTEXT
{time_context}

## USER MODEL
{user_model}

## CONVERSATION THREADS
{thread_context}

## DOMAIN ACTIVATION
{domain_activation}

## WEB RESULTS (if available)
{web_results}

USER QUERY: {user_query}
"""

def get_time_context():
    now = now_utc()
    hour = now.hour
    day = now.strftime("%A")
    date = now.strftime("%B %d, %Y")
    utc_time = now.strftime("%H:%M UTC")
    if hour < 5:
        greeting = "The world is quiet — a perfect time for deep thinking."
    elif hour < 12:
        greeting = "A fresh day for new ideas."
    elif hour < 17:
        greeting = "The day is in full swing — let's make it productive."
    elif hour < 21:
        greeting = "Winding down, but still sharp."
    else:
        greeting = "The night is young — plenty of time to explore new ideas."
    return f"Day: {day}\nDate: {date}\nUTC Time: {utc_time}\nContext: {greeting}"

def classify_query(q: str) -> str:
    q_lower = q.lower()
    if re.search(r'def |class |import |docker|kubernetes|aws|api|sql|python|javascript|rust|golang|cpu|gpu|ram|hardware|react|vue|angular', q_lower):
        return 'coding'
    if re.search(r'dcf|valuation|wacc|stock|trading|portfolio|crypto|bitcoin|forex|markets|ethereum|bond|yield|option|future|derivative', q_lower):
        return 'finance'
    if re.search(r'black.scholes|ito|stochastic|monte carlo|var|cvar|sharpe|sortino|beta|alpha', q_lower):
        return 'quant'
    if re.search(r'prove|proof|theorem|integral|derivative|matrix|probability|statistics', q_lower):
        return 'math'
    if re.search(r'crispr|dna|quantum|physics|chemistry|biology|medicine|disease|symptom', q_lower):
        return 'science'
    if re.search(r'un|wto|imf|world bank|policy|election|regulation|government|africa|african union', q_lower):
        return 'geopolitics'
    if re.search(r'painting|sculpture|design|music|composition|literature|writing|poetry', q_lower):
        return 'arts'
    if re.search(r'recipe|cook|cuisine|nutrition|bake|restaurant', q_lower):
        return 'food'
    if re.search(r'who are you|what are you|identity|introduce yourself', q_lower):
        return 'identity'
    if re.search(r'^(hi|hello|hey|good morning|good afternoon|good evening|thanks|thank you)[\s!.]*$', q_lower):
        return 'greeting'
    return 'general'

def needs_web_search(q: str) -> bool:
    return bool(re.search(r'latest|current|today|news|right now|recent|202[3-9]|live|real.time', q.lower()))

def build_system_prompt(user_query, tier, reasoning_depth, preferred_domain, user_model, thread_context, web_results):
    tc = get_time_context()
    domain = classify_query(user_query)
    domain_activation = f"Primary domain: {domain}. Preferred domain: {preferred_domain}."
    if reasoning_depth >= 4:
        domain_activation += " Activate internal debate synthesizer for complex decisions."
    if reasoning_depth >= 3:
        domain_activation += " Use multi‑step reasoning with framework selection."
    prompt = CAPITAN_SYSTEM_PROMPT.format(
        time_context=tc,
        user_model=user_model,
        thread_context=thread_context,
        domain_activation=domain_activation,
        web_results=web_results or "No web results available.",
        user_query=user_query,
    )
    if tier == "founder" and settings.FOUNDER_EXTRA_PROMPT:
        prompt += "\n\n[FOUNDER DIRECTIVES]\n" + settings.FOUNDER_EXTRA_PROMPT
    return prompt

class ReasoningEngine:
    @staticmethod
    def generate_chain_of_thought(query: str, depth: int = 3, domain: str = "general") -> List[str]:
        chain = []
        chain.append(f"🎯 INTENT: Understanding the core objective behind '{query[:100]}...'")
        chain.append("🔍 DECOMPOSITION: Breaking into sub‑problems...")
        if domain in ("finance", "quant", "coding", "science", "math", "geopolitics"):
            chain.append("🧮 FRAMEWORK: Selecting analytical approach...")
            if depth >= 3:
                chain.append("⚔️ INTERNAL DEBATE: Examining multiple perspectives...")
            if depth >= 4:
                chain.append("🔄 COUNTERFACTUAL: Testing alternative scenarios...")
        chain.append("🔬 ANALYSIS: Systematic evaluation of each component...")
        if depth >= 2:
            chain.append("🧩 SYNTHESIS: Combining insights into coherent understanding...")
        if depth >= 3:
            chain.append("✅ VERIFICATION: Checking logic, assumptions, and edge cases...")
        if depth >= 5:
            chain.append("🎯 OPTIMIZATION: Finding the most elegant and robust solution...")
        return chain[:depth + 2]

    @staticmethod
    def estimate_confidence(response: str, domain: str, has_web_data: bool) -> float:
        base = 0.85 if has_web_data else 0.75
        if domain in ("finance", "geopolitics"):
            base -= 0.05
        if domain in ("math", "coding"):
            base += 0.05
        hedging = len(re.findall(r'may|might|could|possibly|unclear|uncertain|speculative', response.lower()))
        base -= min(0.15, hedging * 0.02)
        return max(0.3, min(0.99, base))

    @staticmethod
    def format_visible_chain(chain: List[str]) -> str:
        return "\n".join(chain)

def call_ai_model(messages: List[dict], tier: str = "free", reasoning_depth: int = 1,
                  domain: str = "general", enable_debate: bool = False) -> Tuple[str, str, Optional[List[str]], float]:
    chain = None
    confidence = 0.8

    if reasoning_depth > 1 and domain in ("finance", "quant", "coding", "math", "science", "geopolitics"):
        chain = ReasoningEngine.generate_chain_of_thought(
            messages[-1].get("content", "") if messages else "",
            min(reasoning_depth, 5),
            domain
        )
        if chain:
            chain_text = "\n\n[INTERNAL REASONING CHAIN — Follow this structure in your thinking]\n" + "\n".join(chain)
            for m in messages:
                if m.get("role") == "system":
                    m["content"] += chain_text
                    break

    # Pro Max: ensemble
    if tier == "pro_max" and settings.OPENROUTER_API_KEY:
        try:
            resp1 = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                json={"model": "anthropic/claude-3.5-sonnet-20241022", "messages": messages, "temperature": 0.7, "max_tokens": 4000},
                timeout=45
            )
            content1 = resp1.json().get("choices", [{}])[0].get("message", {}).get("content", "") if resp1.status_code == 200 else ""

            resp2 = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                json={"model": "openai/gpt-4o-2024-11-20", "messages": messages, "temperature": 0.7, "max_tokens": 4000},
                timeout=45
            )
            content2 = resp2.json().get("choices", [{}])[0].get("message", {}).get("content", "") if resp2.status_code == 200 else ""

            if content1 and content2:
                combined = f"**Claude 3.5 Sonnet Analysis:**\n{content1}\n\n---\n\n**GPT-4o Additional Insights:**\n{content2}"
                confidence = ReasoningEngine.estimate_confidence(combined, domain, False)
                return combined, "claude-3.5-sonnet + gpt-4o (Ensemble)", chain, confidence
            elif content1:
                confidence = ReasoningEngine.estimate_confidence(content1, domain, False)
                return content1, "claude-3.5-sonnet", chain, confidence
            elif content2:
                confidence = ReasoningEngine.estimate_confidence(content2, domain, False)
                return content2, "gpt-4o", chain, confidence
        except Exception as e:
            logger.error(f"Ensemble error: {e}")

    # Pro: Claude
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
                    confidence = ReasoningEngine.estimate_confidence(content, domain, False)
                    return content, "claude-3.5-sonnet", chain, confidence
        except: pass

    # Plus: Groq 70B
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
                    confidence = ReasoningEngine.estimate_confidence(content, domain, False)
                    return content, "llama-3.3-70b", chain, confidence
        except: pass

    # Default: Groq 8B
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
                    confidence = ReasoningEngine.estimate_confidence(content, domain, False)
                    return content, "llama-3.1-8b", chain, confidence
        except: pass

    return "I'm having trouble connecting to AI services. Please try again in a moment.", "fallback", chain, 0.3

# Token deduction helper
def estimate_tokens(user_msg: str, ai_response: str) -> int:
    words = len((user_msg + ai_response).split())
    return max(1, int(words / 0.75))

def deduct_tokens(user_id: str = None, session_id: str = None, tokens_used: int = 0):
    with get_db() as conn:
        with conn.cursor() as c:
            if user_id:
                c.execute("UPDATE users SET token_balance = GREATEST(0, token_balance - %s) WHERE id = %s", (tokens_used, user_id))
            elif session_id:
                c.execute("UPDATE sessions SET token_balance = GREATEST(0, token_balance - %s) WHERE id = %s", (tokens_used, session_id))
            conn.commit()

# Context & memory (unchanged)
def get_thread_context(chat_id: str, user_id: str = None, session_id: str = None) -> str:
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                if user_id:
                    c.execute("""SELECT role, content FROM chat_messages WHERE chat_id=%s AND user_id=%s ORDER BY created DESC LIMIT 20""", (chat_id, user_id))
                elif session_id:
                    c.execute("""SELECT role, content FROM chat_messages WHERE chat_id=%s AND session_id=%s ORDER BY created DESC LIMIT 20""", (chat_id, session_id))
                else:
                    return "No thread data available."
                rows = c.fetchall()
                if not rows:
                    return "New conversation — no active threads."
                threads = []
                for r in rows[:10]:
                    if r[0] == "user":
                        threads.append(f"- User asked: '{r[1][:100]}...'")
                return "Recent conversation threads:\n" + "\n".join(threads) if threads else "No active threads."
    except:
        return "Thread data unavailable."

def get_user_model(user_id: str) -> str:
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT preferred_domain, reasoning_depth FROM users WHERE id = %s", (user_id,))
                user = c.fetchone()
                if not user:
                    return "New user — no model yet."
                c.execute("SELECT domain, COUNT(*), AVG(importance) FROM memories WHERE user_id = %s GROUP BY domain ORDER BY COUNT(*) DESC LIMIT 5", (user_id,))
                domains = c.fetchall()
                model_parts = [f"Preferred domain: {user[0]}. Depth preference: {user[1]}."]
                if domains:
                    model_parts.append("Frequent domains: " + ", ".join([f"{d[0]}({d[1]}x)" for d in domains]))
                return " ".join(model_parts)
    except:
        return "User model unavailable."

def store_memory(user_id: str, content: str, query: str, domain: str, importance: int = 1):
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO memories (id, memory_id, user_id, content, query, domain, importance) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                          (sid(), mid(), user_id, content[:500], query, domain, importance))
                conn.commit()
    except: pass

# Moderation
def moderate_content(text: str) -> Tuple[bool, str, str]:
    text_lower = text.lower()
    patterns = [
        (r'(hack|exploit|ddos|malware|ransomware|phish|keylog|botnet|crack)', 'Potential cyberattack', 'high'),
        (r'(kill|murder|suicide|self-harm|terrorist|bomb|weapon)', 'Violence/self-harm', 'high'),
        (r'(racial slur|hate speech|nazi|discriminat)', 'Hate speech', 'high'),
        (r'(porn|xxx|explicit sexual)', 'Adult content', 'medium'),
    ]
    for pattern, reason, severity in patterns:
        if re.search(pattern, text_lower):
            return True, reason, severity
    return False, "", "low"

# Notifications & logging
def create_notification(user_id: str, type: str, message: str):
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO notifications (id, user_id, type, message) VALUES (%s,%s,%s,%s)",
                          (str(uuid.uuid4()), user_id, type, message))
                conn.commit()
    except: pass

def log_activity(user_id: str, action: str, details: str = ""):
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO activity_log (id, user_id, action, details) VALUES (%s,%s,%s,%s)",
                          (str(uuid.uuid4()), user_id, action, details))
                conn.commit()
    except: pass

def log_security_event(event_type: str, ip: str, user_agent: str, details: str, severity: str = "low"):
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO security_events (id, event_type, ip_address, user_agent, details, severity) VALUES (%s,%s,%s,%s,%s,%s)",
                          (str(uuid.uuid4()), event_type, ip, user_agent, details, severity))
                conn.commit()
    except: pass

# Web search & market data
def search_web(query: str, num_results: int = 5) -> List[dict]:
    results = []
    if settings.SERPAPI_KEY:
        try:
            r = requests.get("https://serpapi.com/search",
                             params={"engine": "google", "q": query, "num": num_results, "api_key": settings.SERPAPI_KEY},
                             timeout=10)
            if r.status_code == 200:
                for item in r.json().get("organic_results", [])[:num_results]:
                    results.append({"title": item.get("title",""), "snippet": item.get("snippet","")[:350], "url": item.get("link",""), "source": "Google"})
        except: pass
    return results

def get_market_prices():
    results = {}
    if settings.COINGECKO_KEY:
        try:
            ids = "bitcoin,ethereum,ripple,solana,cardano,dogecoin,avalanche-2,chainlink,polkadot,tron"
            r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                             params={"ids":ids,"vs_currencies":"usd","include_24hr_change":"true"},
                             headers={"x-cg-demo-api-key":settings.COINGECKO_KEY}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                names = {"bitcoin":"BTC","ethereum":"ETH","ripple":"XRP","solana":"SOL","cardano":"ADA",
                         "dogecoin":"DOGE","avalanche-2":"AVAX","chainlink":"LINK","polkadot":"DOT","tron":"TRX"}
                for k,v in data.items():
                    results[names.get(k,k.upper())] = {"price":v["usd"],"change":round(v.get("usd_24h_change",0),2)}
        except: pass
    if settings.FINNHUB_API_KEY:
        symbols = ["SPX","NDX","DJI","AAPL","MSFT","NVDA","TSLA","GOOGL","META","AMZN"]
        for sym in symbols:
            try:
                r = requests.get(f"https://finnhub.io/api/v1/quote?symbol={sym}&token={settings.FINNHUB_API_KEY}", timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("c"):
                        results[sym] = {"price":data["c"],"change":round(data.get("dp",0),2)}
            except: pass
    return results

def get_news():
    news = []
    if settings.NEWS_API_KEY:
        try:
            r = requests.get("https://newsapi.org/v2/top-headlines",
                             params={"category":"business","language":"en","pageSize":10,"apiKey":settings.NEWS_API_KEY}, timeout=10)
            if r.status_code == 200:
                for article in r.json().get("articles",[]):
                    news.append({"source":article.get("source",{}).get("name","News"),"headline":article.get("title",""),
                                 "url":article.get("url",""),"summary":(article.get("description") or "")[:200]})
        except: pass
    return news[:10]

def extract_text_from_file(file_path: str, original_name: str) -> str:
    ext = original_name.rsplit('.', 1)[-1].lower() if '.' in original_name else ''
    try:
        if ext in ('txt','md','json','csv','py','js','html','css','yaml','yml','toml'):
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

# ================================================================================
# AUTH ENDPOINTS
# ================================================================================
class RegisterRequest(BaseModel): email: str; password: str; name: Optional[str] = None
class LoginRequest(BaseModel): email: str; password: str

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
                c.execute("""INSERT INTO users (id, email, password_hash, name, tier, reasoning_depth, preferred_domain, token_balance, last_active)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
                    (user_id, req.email, password_hash, name, "free", 1, "general", TIER_TOKEN_BALANCES["free"]))
                token = create_token(user_id)
                c.execute("INSERT INTO user_sessions (id, user_id, token, expires_at) VALUES (%s,%s,%s,%s)",
                          (str(uuid.uuid4()), user_id, token, now_utc()+timedelta(days=30)))
                # Create default API key
                raw_key = "cap_" + secrets.token_hex(32)
                key_hash = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()
                c.execute("INSERT INTO api_keys (id, user_id, key_hash, prefix, label, scopes) VALUES (%s,%s,%s,%s,%s,%s)",
                          (str(uuid.uuid4()), user_id, key_hash, raw_key[:10]+"...", "CAPITAN Web App", "chat,research,portfolio"))
                conn.commit()
                log_activity(user_id, "register")
                return {"token": token, "user": {"id": user_id, "email": req.email, "name": name, "tier": "free", "reasoning_depth": 1, "preferred_domain": "general", "token_balance": TIER_TOKEN_BALANCES["free"]}}
    except HTTPException: raise
    except Exception as e: logger.error(f"Register: {e}"); raise HTTPException(500, "Registration failed")

@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request):
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, email, password_hash, name, tier, reasoning_depth, preferred_domain, token_balance FROM users WHERE email = %s", (req.email,))
                user = c.fetchone()
                if not user or not verify_password(req.password, user[2]):
                    raise HTTPException(401, "Invalid email or password")
                user_id, email, _, name, tier, reasoning_depth, preferred_domain, token_balance = user
                token = create_token(user_id)
                c.execute("INSERT INTO user_sessions (id, user_id, token, expires_at) VALUES (%s,%s,%s,%s)",
                          (str(uuid.uuid4()), user_id, token, now_utc()+timedelta(days=30)))
                c.execute("UPDATE users SET last_active = NOW() WHERE id = %s", (user_id,))
                conn.commit()
                log_activity(user_id, "login", f"IP: {request.client.host}")
                return {"token": token, "user": {"id": user_id, "email": email, "name": name or email.split('@')[0], "tier": tier, "reasoning_depth": reasoning_depth or 1, "preferred_domain": preferred_domain or "general", "token_balance": token_balance or 0}}
    except HTTPException: raise
    except Exception as e: logger.error(f"Login: {e}"); raise HTTPException(500, "Login failed")

@app.post("/api/auth/logout")
async def logout(request: Request):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("DELETE FROM user_sessions WHERE token = %s", (auth[7:],))
                    conn.commit()
        except: pass
    return {"message": "Logged out"}

@app.get("/api/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401, "Not authenticated")
    return user

@app.post("/api/auth/update-profile")
async def update_profile(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    name = req.get("name")
    reasoning_depth = req.get("reasoning_depth")
    preferred_domain = req.get("preferred_domain")
    valid_domains = ["general","finance","coding","science","math","geopolitics","arts","food"]
    if preferred_domain and preferred_domain not in valid_domains:
        raise HTTPException(400, "Invalid domain")
    max_depth = TIER_CONFIG.get(user["tier"], TIER_CONFIG["free"])["reasoning_depth"]
    if reasoning_depth and (reasoning_depth < 1 or reasoning_depth > max_depth):
        raise HTTPException(400, f"Depth must be between 1 and {max_depth}")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                if name: c.execute("UPDATE users SET name=%s, updated_at=NOW() WHERE id=%s", (name, user["id"]))
                if reasoning_depth: c.execute("UPDATE users SET reasoning_depth=%s, updated_at=NOW() WHERE id=%s", (reasoning_depth, user["id"]))
                if preferred_domain: c.execute("UPDATE users SET preferred_domain=%s, updated_at=NOW() WHERE id=%s", (preferred_domain, user["id"]))
                conn.commit()
        return {"message": "Profile updated"}
    except: raise HTTPException(500, "Update failed")

@app.delete("/api/auth/delete-account")
async def delete_account(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("DELETE FROM users WHERE id = %s", (user["id"],))
                conn.commit()
        return {"message": "Account deleted"}
    except: raise HTTPException(500, "Delete failed")

@app.get("/api/session")
async def get_anonymous_session():
    session_id = f"s_{sid()}"
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO sessions (id, tier, token_balance) VALUES (%s,'guest',2000)", (session_id,))
                conn.commit()
    except: pass
    token = create_session_token(session_id, "guest")
    return {"id": session_id, "tier": "guest", "token": token, "token_balance": 2000}

@app.post("/api/founder")
async def founder_login(req: dict, request: Request):
    identifier = request.client.host
    if not check_rate_limit(identifier, "founder_attempt", 5):
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
                    c.execute("UPDATE users SET tier='founder', reasoning_depth=5 WHERE id=%s", (user_id,))
                else:
                    user_id = str(uuid.uuid4())
                    c.execute("INSERT INTO users (id, email, password_hash, name, tier, reasoning_depth, preferred_domain, token_balance) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                              (user_id, "founder@capitan.ai", hash_password("founder_sentinel"), "CAPITAN Founder", "founder", 5, "general", float("inf")))
                token = create_token(user_id)
                c.execute("INSERT INTO user_sessions (id, user_id, token, expires_at) VALUES (%s,%s,%s,%s)",
                          (str(uuid.uuid4()), user_id, token, now_utc()+timedelta(days=365)))
                conn.commit()
                log_activity(user_id, "founder_login", f"IP: {identifier}")
                return {"verified": True, "token": token, "user": {"id": user_id, "name": "CAPITAN Founder", "email": "founder@capitan.ai", "tier": "founder", "reasoning_depth": 5, "preferred_domain": "general", "token_balance": "unlimited"}}
    except Exception as e: logger.error(f"Founder: {e}"); raise HTTPException(500, "Founder login failed")

# ================================================================================
# CHAT (CORE) – No daily limits, token deduction added
# ================================================================================
class ChatRequest(BaseModel):
    messages: list
    chat_id: Optional[str] = None
    show_reasoning: bool = False

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, request: Request, background_tasks: BackgroundTasks):
    user = get_current_user(request)
    session = None
    if not user:
        try: session = await get_current_session(request)
        except: raise HTTPException(401, "Authentication required")
    if user:
        tier = user["tier"]; user_id = user["id"]; reasoning_depth = user.get("reasoning_depth",1); preferred_domain = user.get("preferred_domain","general"); is_authenticated = True
        token_balance = user.get("token_balance", 0)
    else:
        tier = session["tier"]; user_id = None; reasoning_depth = 1; preferred_domain = "general"; is_authenticated = False
        token_balance = session.get("token_balance", 0)

    tier_info = TIER_CONFIG.get(tier, TIER_CONFIG["guest"])
    identifier = user_id if user else session["id"]
    if not check_rate_limit(identifier, tier, tier_info.get("per_min_limit",20)):
        raise HTTPException(429, "Rate limit exceeded.")

    user_msg = None
    for m in reversed(req.messages):
        if m.get("role") == "user": user_msg = m.get("content"); break
    if not user_msg: raise HTTPException(400, "No message content")

    chat_id = req.chat_id or f"chat_{sid()}"
    domain = classify_query(user_msg)
    web_search_needed = needs_web_search(user_msg)

    file_text = ""
    if "[Uploaded document:" in user_msg:
        fname_match = re.search(r'\[Uploaded document:\s*(.*?)\]', user_msg)
        if fname_match and is_authenticated:
            fname = fname_match.group(1).strip()
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
                    c.execute("""INSERT INTO chats (id, user_id, title, topic_thread, created, updated)
                        VALUES (%s,%s,%s,%s,NOW(),NOW()) ON CONFLICT (id) DO UPDATE SET updated = NOW(), title = %s""",
                              (chat_id, user_id, user_msg[:60], domain, user_msg[:60]))
                    c.execute("INSERT INTO chat_messages (id, chat_id, user_id, role, content) VALUES (%s,%s,%s,%s,%s)",
                              (f"msg_{sid()}", chat_id, user_id, "user", user_msg))
                else:
                    c.execute("""INSERT INTO chats (id, session_id, title, topic_thread, created, updated)
                        VALUES (%s,%s,%s,%s,NOW(),NOW()) ON CONFLICT (id) DO UPDATE SET updated = NOW(), title = %s""",
                              (chat_id, session["id"], user_msg[:60], domain, user_msg[:60]))
                    c.execute("INSERT INTO chat_messages (id, chat_id, session_id, role, content) VALUES (%s,%s,%s,%s,%s)",
                              (f"msg_{sid()}", chat_id, session["id"], "user", user_msg))
                conn.commit()
    except Exception as e: logger.error(f"Save user msg error: {e}")

    if settings.ENABLE_MODERATION and is_authenticated:
        flagged, reason, severity = moderate_content(user_msg)
        if flagged:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("INSERT INTO content_flags (id, user_id, message_id, content, reason, severity) VALUES (%s,%s,%s,%s,%s,%s)",
                              (str(uuid.uuid4()), user_id, f"msg_{sid()}", user_msg, reason, severity))
                    conn.commit()
            if severity == "high": create_notification(user_id, "moderation", f"Your message was flagged: {reason}")

    chat_history = []
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("""SELECT role, content FROM (
                    SELECT role, content, created FROM chat_messages
                    WHERE chat_id = %s ORDER BY created DESC LIMIT 60
                ) recent ORDER BY created ASC""", (chat_id,))
                chat_history = [{"role": r[0], "content": r[1]} for r in c.fetchall()]
    except: pass

    thread_context = get_thread_context(chat_id, user_id if is_authenticated else None, session["id"] if not is_authenticated else None)
    user_model = get_user_model(user_id) if is_authenticated else "Anonymous user."

    web_results_text = ""
    if tier_info.get("web_search", False) and web_search_needed:
        try:
            results = search_web(user_msg, 5)
            if results: web_results_text = "\n".join([f"- {r['title']}: {r['snippet'][:200]}" for r in results[:4]])
        except: pass

    system_prompt = build_system_prompt(user_msg, tier, reasoning_depth, preferred_domain, user_model, thread_context, web_results_text)
    messages_for_ai = [{"role": "system", "content": system_prompt}] + chat_history
    result, model_used, reasoning_chain, confidence = call_ai_model(messages_for_ai, tier, reasoning_depth, domain, enable_debate=(reasoning_depth>=3))

    if result:
        msg_id = f"msg_{sid()}"
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    if is_authenticated:
                        c.execute("""INSERT INTO chat_messages (id, chat_id, user_id, role, content, model, reasoning_chain, confidence_score)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                                  (msg_id, chat_id, user_id, "assistant", result, model_used,
                                   json.dumps(reasoning_chain) if reasoning_chain else None, confidence))
                        background_tasks.add_task(store_memory, user_id, result[:500], user_msg, domain, 2 if domain in ("finance","coding","science") else 1)
                    else:
                        c.execute("""INSERT INTO chat_messages (id, chat_id, session_id, role, content, model, reasoning_chain, confidence_score)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                                  (msg_id, chat_id, session["id"], "assistant", result, model_used,
                                   json.dumps(reasoning_chain) if reasoning_chain else None, confidence))
                    conn.commit()
        except Exception as e: logger.error(f"Save AI msg error: {e}")

        # Deduct tokens
        tokens_used = estimate_tokens(user_msg, result)
        deduct_tokens(user_id if is_authenticated else None, session["id"] if not is_authenticated else None, tokens_used)

        if is_authenticated:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("UPDATE users SET last_active = NOW() WHERE id = %s", (user_id,))
                    conn.commit()
        return {"content": result, "chat_id": chat_id, "model": model_used, "tier": tier, "domain": domain, "confidence": round(confidence,2), "message_id": msg_id, "tokens_used": tokens_used}
    else:
        return {"content": "I couldn't generate a response.", "chat_id": chat_id, "model": "fallback"}

@app.get("/api/chats")
def get_chats(request: Request, refresh: bool = False):
    user = get_current_user(request)
    if user:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, title, topic_thread, created, updated FROM chats WHERE user_id=%s ORDER BY updated DESC LIMIT 100", (user["id"],))
                rows = c.fetchall()
                return {"chats": [{"id": r[0], "title": r[1] or "New Chat", "topic": r[2], "created": r[3].isoformat() if r[3] else None, "updated": r[4].isoformat() if r[4] else None} for r in rows]}
    else:
        try:
            session = get_current_session(request)
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("SELECT id, title, topic_thread, created, updated FROM chats WHERE session_id=%s ORDER BY updated DESC LIMIT 100", (session["id"],))
                    rows = c.fetchall()
                    return {"chats": [{"id": r[0], "title": r[1] or "New Chat", "topic": r[2], "created": r[3].isoformat() if r[3] else None, "updated": r[4].isoformat() if r[4] else None} for r in rows]}
        except: pass
    return {"chats": []}

@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str, request: Request):
    user = get_current_user(request)
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                if user: c.execute("SELECT id FROM chats WHERE id=%s AND user_id=%s", (chat_id, user["id"]))
                else:
                    session = get_current_session(request)
                    c.execute("SELECT id FROM chats WHERE id=%s AND session_id=%s", (chat_id, session["id"]))
                if not c.fetchone(): raise HTTPException(404, "Chat not found")
                c.execute("SELECT role, content, model, reasoning_chain, confidence_score, created FROM chat_messages WHERE chat_id=%s ORDER BY created ASC", (chat_id,))
                rows = c.fetchall()
                return {"messages": [{"id": i, "role": r[0], "content": r[1], "model": r[2] or "AI", "reasoning_chain": json.loads(r[3]) if r[3] else None, "confidence": r[4], "created": r[5].isoformat() if r[5] else None} for i, r in enumerate(rows)]}
    except HTTPException: raise
    except Exception as e: raise HTTPException(500, str(e))

@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str, request: Request):
    user = get_current_user(request)
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

# ================================================================================
# PORTFOLIO
# ================================================================================
class PortfolioItemCreate(BaseModel):
    name: str
    content: str = ""
    folder: str = "General"
    tags: List[str] = []
    attachments: List[str] = []
    chat_id: str = None

@app.get("/api/portfolio")
def get_portfolio(request: Request, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, name, content, folder, tags, attachments, pinned, chat_id, created, updated FROM library_items WHERE user_id=%s ORDER BY pinned DESC, updated DESC", (user["id"],))
            items = []
            for row in c.fetchall():
                items.append({
                    "id": row[0], "name": row[1], "content": row[2], "folder": row[3] or "General",
                    "tags": row[4] if row[4] else [], "attachments": row[5] if row[5] else [],
                    "pinned": row[6], "chat_id": row[7],
                    "created": row[8].isoformat() if row[8] else None,
                    "updated": row[9].isoformat() if row[9] else None
                })
            return {"items": items}

@app.post("/api/portfolio")
def create_portfolio_item(req: PortfolioItemCreate, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    item_id = f"lib_{sid()}"
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO library_items (id, user_id, name, content, folder, tags, attachments, chat_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                      (item_id, user["id"], req.name, req.content, req.folder, json.dumps(req.tags), json.dumps(req.attachments), req.chat_id))
            conn.commit()
    return {"id": item_id, "created": True}

@app.put("/api/portfolio/{item_id}")
def update_portfolio_item(item_id: str, req: PortfolioItemCreate, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE library_items SET name=%s, content=%s, folder=%s, tags=%s, attachments=%s, chat_id=%s, updated=NOW() WHERE id=%s AND user_id=%s",
                      (req.name, req.content, req.folder, json.dumps(req.tags), json.dumps(req.attachments), req.chat_id, item_id, user["id"]))
            conn.commit()
    return {"updated": True}

@app.delete("/api/portfolio/{item_id}")
def delete_portfolio_item(item_id: str, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM library_items WHERE id=%s AND user_id=%s", (item_id, user["id"]))
            conn.commit()
    return {"deleted": True}

# ================================================================================
# WORKSPACES
# ================================================================================
@app.post("/api/hub/rooms")
def create_hub_room(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    tier_info = TIER_CONFIG.get(user["tier"], TIER_CONFIG["free"])
    if tier_info["workspace_seats"] == 0:
        raise HTTPException(403, "Upgrade to Plus or higher for Research Hub access")
    room_code = req.get("room_code", f"HUB-{sid()}")
    password = req.get("password")
    password_hash = hash_password(password) if password else None
    with get_db() as conn:
        with conn.cursor() as c:
            ws_id = sid()
            c.execute("INSERT INTO workspaces (id, name, description, topic, owner_id, room_code, password_hash, max_members) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                      (ws_id, req.get("name","Research Room"), req.get("description",""), req.get("topic",""), user["id"], room_code.upper(), password_hash, tier_info["workspace_seats"]))
            c.execute("INSERT INTO workspace_members (workspace_id, user_id, role) VALUES (%s,%s,'admin')", (ws_id, user["id"]))
            conn.commit()
    return {"room_id": ws_id, "room_code": room_code.upper(), "created": True}

@app.post("/api/hub/rooms/join")
def join_hub_room(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    room_code = req.get("room_code","").upper()
    password = req.get("password","")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, password_hash, max_members FROM workspaces WHERE room_code=%s", (room_code,))
            room = c.fetchone()
            if not room: raise HTTPException(404, "Room not found")
            if room[1] and (not password or not verify_password(password, room[1])):
                raise HTTPException(403, "Invalid room password")
            c.execute("SELECT COUNT(*) FROM workspace_members WHERE workspace_id=%s", (room[0],))
            if c.fetchone()[0] >= room[2]:
                raise HTTPException(400, "Room is full")
            c.execute("INSERT INTO workspace_members (workspace_id, user_id, role) VALUES (%s,%s,'member') ON CONFLICT DO NOTHING", (room[0], user["id"]))
            conn.commit()
    return {"joined": True, "room_id": room[0]}

@app.get("/api/hub/rooms")
def list_hub_rooms(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("""SELECT w.id, w.name, w.description, w.topic, w.room_code, w.max_members, w.created_at,
                (SELECT COUNT(*) FROM workspace_members WHERE workspace_id=w.id) as member_count
                FROM workspaces w
                JOIN workspace_members m ON w.id = m.workspace_id
                WHERE m.user_id = %s AND w.is_active = TRUE
                ORDER BY w.created_at DESC""", (user["id"],))
            rooms = [{"id": r[0], "name": r[1], "description": r[2], "topic": r[3], "room_code": r[4],
                      "max_members": r[5], "created_at": r[6].isoformat() if r[6] else None, "member_count": r[7]} for r in c.fetchall()]
    return {"rooms": rooms}

@app.get("/api/hub/rooms/{room_code}/messages")
def get_hub_messages(room_code: str, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id FROM workspaces WHERE room_code=%s", (room_code.upper(),))
            room = c.fetchone()
            if not room: raise HTTPException(404)
            c.execute("SELECT author_name, message, is_ai, pinned, created FROM workspace_messages WHERE workspace_id=%s ORDER BY pinned DESC, created ASC LIMIT 100", (room[0],))
            msgs = [{"author": r[0], "message": r[1], "is_ai": bool(r[2]), "pinned": bool(r[3]), "created": r[4].isoformat() if r[4] else None} for r in c.fetchall()]
    return {"messages": msgs}

@app.post("/api/hub/rooms/{room_code}/messages")
def send_hub_message(room_code: str, req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    message = req.get("message","")
    if not message: raise HTTPException(400)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id FROM workspaces WHERE room_code=%s", (room_code.upper(),))
            room = c.fetchone()
            if not room: raise HTTPException(404)
            is_ai = message.strip().startswith("@CAPITAN")
            c.execute("INSERT INTO workspace_messages (id, workspace_id, user_id, author_name, message) VALUES (%s,%s,%s,%s,%s)",
                      (sid(), room[0], user["id"], user["name"], message))
            if is_ai:
                ai_response, _, _, _ = call_ai_model([{"role":"user","content":message.replace('@CAPITAN','').strip()}], user["tier"])
                if ai_response:
                    c.execute("INSERT INTO workspace_messages (id, workspace_id, user_id, author_name, message, is_ai) VALUES (%s,%s,%s,%s,%s,1)",
                              (sid(), room[0], user["id"], "CAPITAN AI", ai_response))
            conn.commit()
    return {"sent": True}

@app.post("/api/hub/rooms/{room_code}/pin/{message_id}")
def pin_message(room_code: str, message_id: str, user: dict = Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE workspace_messages SET pinned = NOT pinned WHERE id=%s", (message_id,))
            conn.commit()
    return {"ok": True}

# ================================================================================
# NOTIFICATIONS
# ================================================================================
@app.get("/api/notifications")
def get_notifications(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, type, message, read, created FROM notifications WHERE user_id=%s ORDER BY created DESC LIMIT 30", (user["id"],))
            notifs = [{"id": r[0], "type": r[1], "message": r[2], "read": r[3], "created": r[4].isoformat() if r[4] else None} for r in c.fetchall()]
    return {"notifications": notifs}

@app.post("/api/notifications/read")
def mark_read(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE notifications SET read=TRUE WHERE user_id=%s", (user["id"],))
            conn.commit()
    return {"ok": True}

# ================================================================================
# UPGRADE
# ================================================================================
class UpgradeRequest(BaseModel):
    tier: str
    txid: str
    currency: str = "BTC"

def verify_transaction(txid: str, currency: str, expected_usd: float, use_token_wallet: bool = False) -> Tuple[bool, float]:
    wallets = TOKEN_WALLETS if use_token_wallet else WALLETS
    if currency == "BTC":
        try:
            r = requests.get(f"https://blockchain.info/rawtx/{txid}", timeout=15)
            if r.status_code == 200:
                btc_price = 0
                if settings.COINGECKO_KEY:
                    try:
                        resp = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd",
                                            headers={"x-cg-demo-api-key": settings.COINGECKO_KEY}, timeout=5)
                        if resp.status_code == 200:
                            btc_price = resp.json()["bitcoin"]["usd"]
                    except: pass
                for out in r.json().get("out", []):
                    if out.get("addr") == wallets["BTC"]:
                        received = out.get("value", 0) / 1e8
                        if btc_price > 0:
                            received_usd = received * btc_price
                            if received_usd >= expected_usd * 0.95:
                                return True, received_usd
                        else:
                            return True, received * 40000
        except: pass
    elif currency == "ETH" and settings.ETHERSCAN_API_KEY:
        try:
            r = requests.get(f"https://api.etherscan.io/api?module=proxy&action=eth_getTransactionByHash&txhash={txid}&apikey={settings.ETHERSCAN_API_KEY}", timeout=15)
            if r.status_code == 200:
                tx = r.json().get("result", {})
                if tx and tx.get("to","").lower() == wallets["ETH"].lower():
                    value = int(tx.get("value","0"), 16) / 1e18
                    eth_price = 0
                    if settings.COINGECKO_KEY:
                        try:
                            resp = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd",
                                                headers={"x-cg-demo-api-key": settings.COINGECKO_KEY}, timeout=5)
                            if resp.status_code == 200:
                                eth_price = resp.json()["ethereum"]["usd"]
                        except: pass
                    if eth_price > 0:
                        received_usd = value * eth_price
                        if received_usd >= expected_usd * 0.95:
                            return True, received_usd
                    else:
                        return True, value * 2000
        except: pass
    return False, 0.0

@app.post("/api/upgrade")
def upgrade(req: UpgradeRequest, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    if req.tier not in ("plus","pro","pro_max"): raise HTTPException(400, "Invalid tier")
    prices = {"plus":8,"pro":17,"pro_max":30}
    payment_id = str(uuid.uuid4())
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO payments (id, user_id, txid, currency, amount, tier, status) VALUES (%s,%s,%s,%s,%s,%s,'pending')",
                      (payment_id, user["id"], req.txid.strip(), req.currency.upper(), prices[req.tier], req.tier))
            conn.commit()
    verified, amount = verify_transaction(req.txid.strip(), req.currency.upper(), prices[req.tier])
    if verified:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("UPDATE payments SET status='confirmed', verified=1 WHERE id=%s", (payment_id,))
                c.execute("UPDATE users SET tier=%s, tier_expires=%s, reasoning_depth=%s, token_balance=token_balance+%s, updated_at=NOW() WHERE id=%s",
                          (req.tier, now_utc()+timedelta(days=30), TIER_CONFIG[req.tier]["reasoning_depth"], TIER_TOKEN_BALANCES.get(req.tier, 0), user["id"]))
                conn.commit()
        new_token = create_token(user["id"])
        return {"verified": True, "tier": req.tier, "token": new_token}
    else:
        return {"verified": False, "status": "pending", "message": "Payment is being verified. Check back shortly."}

@app.get("/api/payments")
def get_payments(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, txid, currency, amount, tier, status, created_at FROM payments WHERE user_id=%s ORDER BY created_at DESC", (user["id"],))
            payments = [{"id": r[0], "txid": r[1], "currency": r[2], "amount": r[3], "tier": r[4], "status": r[5], "created_at": r[6].isoformat() if r[6] else None} for r in c.fetchall()]
    return {"payments": payments}

# ================================================================================
# TOKEN PURCHASE (Pay‑as‑you‑go)
# ================================================================================
class TokenPurchaseRequest(BaseModel):
    package_amount: float
    txid: str
    currency: str = "BTC"

@app.get("/api/tokens/wallets")
def get_token_wallets():
    return {"wallets": TOKEN_WALLETS}

@app.get("/api/tokens/packages")
def get_token_packages():
    return {"packages": TOKEN_PACKAGES}

def user_token_balance(user_id: str) -> int:
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT token_balance FROM users WHERE id = %s", (user_id,))
            row = c.fetchone()
            return row[0] if row else 0

@app.get("/api/tokens/balance")
def get_token_balance(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    return {"balance": user_token_balance(user["id"])}

@app.post("/api/tokens/purchase")
def purchase_tokens(req: TokenPurchaseRequest, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    pkg = None
    for p in TOKEN_PACKAGES:
        if p["amount"] == req.package_amount:
            pkg = p
            break
    if not pkg:
        raise HTTPException(400, "Invalid package amount")
    verified, usd_received = verify_transaction(req.txid.strip(), req.currency.upper(), req.package_amount, use_token_wallet=True)
    purchase_id = str(uuid.uuid4())
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO token_purchases (id, user_id, txid, currency, amount_usd, tokens, verified) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                      (purchase_id, user["id"], req.txid.strip(), req.currency.upper(), req.package_amount, pkg["tokens"], 1 if verified else 0))
            if verified:
                c.execute("UPDATE users SET token_balance = token_balance + %s WHERE id = %s", (pkg["tokens"], user["id"]))
            conn.commit()
    if verified:
        return {"verified": True, "tokens_added": pkg["tokens"], "new_balance": user_token_balance(user["id"])}
    else:
        return {"verified": False, "message": "Payment is being verified. Tokens will be credited once confirmed."}

# ================================================================================
# FEEDBACK
# ================================================================================
class FeedbackRequest(BaseModel):
    message_id: str
    rating: int = Field(..., ge=1, le=5)
    correction: Optional[str] = None
    reason: Optional[str] = None

@app.post("/api/feedback")
def submit_feedback(req: FeedbackRequest, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO feedback (id, user_id, message_id, rating, correction, reason) VALUES (%s,%s,%s,%s,%s,%s)",
                      (str(uuid.uuid4()), user["id"], req.message_id, req.rating, req.correction, req.reason))
            conn.commit()
    return {"received": True}

# ================================================================================
# FILE UPLOAD
# ================================================================================
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    tier_info = TIER_CONFIG.get(user["tier"], TIER_CONFIG["free"])
    if not tier_info["file_upload"]: raise HTTPException(403, "Upgrade to Plus or higher for file uploads")
    contents = await file.read()
    max_size = 100 if user["tier"] == "pro_max" else (50 if user["tier"] == "pro" else 20)
    if len(contents) / (1024*1024) > max_size: raise HTTPException(400, f"Max {max_size}MB")
    file_id = f"file_{sid()}"
    file_path = os.path.join(UPLOAD_DIR, file_id)
    with open(file_path, "wb") as f: f.write(contents)
    extracted = extract_text_from_file(file_path, file.filename or "unknown")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO uploaded_files (id, user_id, filename, original_name, size, storage_path, extracted_text) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                      (file_id, user["id"], file_id, file.filename or "unknown", len(contents), file_path, extracted[:50000]))
            conn.commit()
    return {"id": file_id, "filename": file.filename, "size_mb": round(len(contents)/(1024*1024),2), "extracted": bool(extracted)}

# ================================================================================
# FOUNDER ADMIN & SAFETY
# ================================================================================
@app.get("/api/admin/dashboard")
def admin_dashboard(founder: dict = Depends(founder_only)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM users"); total_users = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM users WHERE tier IN ('plus','pro','pro_max')"); paid_users = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM users WHERE last_active > NOW() - INTERVAL '24 hours'"); active_today = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM users WHERE created_at > NOW() - INTERVAL '7 days'"); new_this_week = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM chat_messages"); total_messages = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM content_flags WHERE reviewed=FALSE"); pending_flags = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM security_events WHERE created > NOW() - INTERVAL '24 hours'"); threats_today = c.fetchone()[0]
            return {"total_users": total_users, "paid_users": paid_users, "active_today": active_today,
                    "new_this_week": new_this_week, "total_messages": total_messages,
                    "pending_flags": pending_flags, "threats_today": threats_today}

@app.get("/api/admin/users")
def admin_users(page: int = 1, search: str = "", founder: dict = Depends(founder_only)):
    limit = 20; offset = (page-1)*limit
    with get_db() as conn:
        with conn.cursor() as c:
            if search:
                c.execute("SELECT id, email, name, tier, created_at, last_active FROM users WHERE email ILIKE %s OR name ILIKE %s ORDER BY created_at DESC LIMIT %s OFFSET %s",
                          (f'%{search}%', f'%{search}%', limit, offset))
            else:
                c.execute("SELECT id, email, name, tier, created_at, last_active FROM users ORDER BY created_at DESC LIMIT %s OFFSET %s", (limit, offset))
            users = [{"id": r[0], "email": r[1], "name": r[2], "tier": r[3], "created_at": r[4].isoformat() if r[4] else None, "last_active": r[5].isoformat() if r[5] else None} for r in c.fetchall()]
    return {"users": users}

@app.get("/api/admin/users/{user_id}/activity")
def admin_user_activity(user_id: str, founder: dict = Depends(founder_only)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT action, details, created FROM activity_log WHERE user_id=%s ORDER BY created DESC LIMIT 100", (user_id,))
            acts = [{"action": r[0], "details": r[1], "created": r[2].isoformat() if r[2] else None} for r in c.fetchall()]
    return {"activities": acts}

@app.post("/api/admin/user/{user_id}/tier")
def admin_change_tier(user_id: str, req: dict, founder: dict = Depends(founder_only)):
    new_tier = req.get("tier")
    if new_tier not in TIER_CONFIG: raise HTTPException(400, "Invalid tier")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE users SET tier=%s, updated_at=NOW() WHERE id=%s", (new_tier, user_id))
            conn.commit()
    return {"success": True}

@app.delete("/api/admin/user/{user_id}")
def admin_delete_user(user_id: str, founder: dict = Depends(founder_only)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM users WHERE id=%s", (user_id,))
            conn.commit()
    return {"deleted": True}

@app.get("/api/admin/payments")
def admin_payments(founder: dict = Depends(founder_only)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT p.id, p.user_id, u.email, p.txid, p.currency, p.amount, p.tier, p.status, p.created_at FROM payments p JOIN users u ON p.user_id=u.id ORDER BY p.created_at DESC LIMIT 100")
            payments = [{"id": r[0], "user_id": r[1], "email": r[2], "txid": r[3], "currency": r[4], "amount": r[5], "tier": r[6], "status": r[7], "created_at": r[8].isoformat() if r[8] else None} for r in c.fetchall()]
    return {"payments": payments}

@app.post("/api/admin/payments/{payment_id}/confirm")
def admin_confirm_payment(payment_id: str, founder: dict = Depends(founder_only)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE payments SET status='confirmed', verified=1 WHERE id=%s", (payment_id,))
            c.execute("SELECT user_id, tier FROM payments WHERE id=%s", (payment_id,))
            payment = c.fetchone()
            if payment:
                c.execute("UPDATE users SET tier=%s, tier_expires=%s, updated_at=NOW() WHERE id=%s",
                          (payment[1], now_utc()+timedelta(days=30), payment[0]))
            conn.commit()
    return {"ok": True}

# Safety
@app.get("/api/admin/safety/dashboard")
def safety_dashboard(founder: dict = Depends(founder_only)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM content_flags WHERE reviewed=FALSE"); pending_flags = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM security_events WHERE created > NOW() - INTERVAL '24 hours'"); threats_today = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM blocked_ips WHERE blocked_until > NOW()"); active_blocks = c.fetchone()[0]
            return {"pending_flags": pending_flags, "threats_today": threats_today, "active_blocks": active_blocks}

@app.get("/api/admin/safety/flags")
def get_flags(reviewed: bool = False, founder: dict = Depends(founder_only)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, user_id, message_id, content, reason, severity, reviewed, action, created FROM content_flags WHERE reviewed=%s ORDER BY created DESC LIMIT 50", (reviewed,))
            flags = [{"id": r[0], "user_id": r[1], "message_id": r[2], "content": r[3], "reason": r[4], "severity": r[5], "reviewed": r[6], "action": r[7], "created": r[8].isoformat() if r[8] else None} for r in c.fetchall()]
    return {"flags": flags}

@app.post("/api/admin/safety/flags/{flag_id}/review")
def review_flag(flag_id: str, req: dict, founder: dict = Depends(founder_only)):
    action = req.get("action", "ignore")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE content_flags SET reviewed=TRUE, action=%s WHERE id=%s", (action, flag_id))
            if action == "block_user":
                c.execute("SELECT user_id FROM content_flags WHERE id=%s", (flag_id,))
                user_id = c.fetchone()[0]
                c.execute("UPDATE users SET tier='guest' WHERE id=%s", (user_id,))  # quarantine
            conn.commit()
    return {"ok": True}

@app.get("/api/admin/safety/events")
def get_security_events(hours: int = 24, founder: dict = Depends(founder_only)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT event_type, ip_address, details, severity, blocked, created FROM security_events WHERE created > NOW() - INTERVAL '%s hours' ORDER BY created DESC LIMIT 100", (hours,))
            events = [{"type": r[0], "ip": r[1], "details": r[2], "severity": r[3], "blocked": r[4], "created": r[5].isoformat() if r[5] else None} for r in c.fetchall()]
    return {"events": events}

@app.get("/api/admin/safety/blocked-ips")
def get_blocked_ips(founder: dict = Depends(founder_only)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT ip_address, reason, blocked_until, created FROM blocked_ips WHERE blocked_until > NOW() ORDER BY created DESC")
            ips = [{"ip": r[0], "reason": r[1], "blocked_until": r[2].isoformat() if r[2] else None, "created": r[3].isoformat() if r[3] else None} for r in c.fetchall()]
    return {"blocked_ips": ips}

@app.post("/api/admin/safety/block-ip")
def block_ip(req: dict, founder: dict = Depends(founder_only)):
    ip = req.get("ip"); reason = req.get("reason", "Manual block")
    until = now_utc() + timedelta(hours=req.get("hours", 24))
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO blocked_ips (ip_address, reason, blocked_until) VALUES (%s,%s,%s) ON CONFLICT (ip_address) DO UPDATE SET blocked_until=%s", (ip, reason, until, until))
            conn.commit()
    return {"ok": True}

@app.delete("/api/admin/safety/unblock-ip/{ip}")
def unblock_ip(ip: str, founder: dict = Depends(founder_only)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM blocked_ips WHERE ip_address=%s", (ip,))
            conn.commit()
    return {"ok": True}

# ================================================================================
# SECURITY MIDDLEWARE
# ================================================================================
@app.middleware("http")
async def security_middleware(request: Request, call_next):
    if settings.ENABLE_SECURITY_MONITOR:
        ip = request.client.host
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT 1 FROM blocked_ips WHERE ip_address=%s AND blocked_until > NOW()", (ip,))
                if c.fetchone():
                    return Response(content="Access denied", status_code=403)
        if not check_rate_limit(ip, "global", limit=200):
            log_security_event("rate_limit_exceeded", ip, request.headers.get("user-agent",""), "High request rate", "medium")
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("INSERT INTO blocked_ips (ip_address, reason, blocked_until) VALUES (%s,'Rate limit exceeded', %s) ON CONFLICT (ip_address) DO UPDATE SET blocked_until=%s",
                              (ip, now_utc()+timedelta(minutes=30), now_utc()+timedelta(minutes=30)))
                    conn.commit()
            return Response(content="Temporarily blocked", status_code=429)
    response = await call_next(request)
    return response

# ================================================================================
# DEVELOPER ENDPOINTS
# ================================================================================
@app.post("/api/developer/keys")
def create_api_key(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    label = req.get("label", "Unlabelled")
    raw_key = "cap_" + secrets.token_hex(32)
    key_hash = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()
    prefix = raw_key[:10] + "..."
    scopes = "chat,research,portfolio"
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO api_keys (id, user_id, key_hash, prefix, label, scopes) VALUES (%s,%s,%s,%s,%s,%s)",
                      (str(uuid.uuid4()), user["id"], key_hash, prefix, label, scopes))
            conn.commit()
    return {"key": raw_key, "prefix": prefix, "label": label, "scopes": scopes}

@app.get("/api/developer/keys")
def list_api_keys(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, prefix, label, scopes, is_active, last_used, created FROM api_keys WHERE user_id=%s ORDER BY created DESC", (user["id"],))
            keys = [{"id": r[0], "prefix": r[1], "label": r[2], "scopes": r[3], "is_active": r[4],
                     "last_used": r[5].isoformat() if r[5] else None, "created": r[6].isoformat() if r[6] else None} for r in c.fetchall()]
    return {"keys": keys}

@app.delete("/api/developer/keys/{key_id}")
def revoke_api_key(key_id: str, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM api_keys WHERE id=%s AND user_id=%s", (key_id, user["id"]))
            conn.commit()
    return {"deleted": True}

@app.post("/api/developer/webhooks")
def create_webhook(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    if user["tier"] not in ("pro", "pro_max", "founder"):
        raise HTTPException(403, "Pro or higher required for webhooks")
    url = req["url"]
    events = req.get("events", "new_message")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO webhooks (id, user_id, url, events) VALUES (%s,%s,%s,%s)",
                      (str(uuid.uuid4()), user["id"], url, events))
            conn.commit()
    return {"created": True}

@app.get("/api/developer/webhooks")
def list_webhooks(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, url, events, is_active, created FROM webhooks WHERE user_id=%s", (user["id"],))
            hooks = [{"id": r[0], "url": r[1], "events": r[2], "is_active": r[3], "created": r[4].isoformat() if r[4] else None} for r in c.fetchall()]
    return {"webhooks": hooks}

@app.delete("/api/developer/webhooks/{webhook_id}")
def delete_webhook(webhook_id: str, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM webhooks WHERE id=%s AND user_id=%s", (webhook_id, user["id"]))
            conn.commit()
    return {"deleted": True}

@app.get("/api/developer/embed")
def get_embed_token(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    if user["tier"] not in ("pro_max", "founder"):
        raise HTTPException(403, "Pro Max or Founder required for embed widget")
    token = create_token(user["id"])
    return {"embed_token": token, "script_url": f"{settings.FRONTEND_URL}/embed.js"}

@app.get("/api/developer/usage")
def get_api_usage(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT endpoint, COUNT(*), SUM(tokens_used) FROM api_usage WHERE user_id=%s AND created > NOW() - INTERVAL '30 days' GROUP BY endpoint ORDER BY SUM(tokens_used) DESC", (user["id"],))
            usage = [{"endpoint": r[0], "requests": r[1], "tokens": r[2]} for r in c.fetchall()]
    return {"usage": usage}

# ================================================================================
# API KEY MIDDLEWARE
# ================================================================================
@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("ApiKey "):
        key = auth[7:]
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, user_id, key_hash, scopes, is_active FROM api_keys WHERE is_active=TRUE")
                rows = c.fetchall()
                for row in rows:
                    if bcrypt.checkpw(key.encode(), row[2].encode()):
                        c.execute("UPDATE api_keys SET last_used = NOW() WHERE id = %s", (row[0],))
                        conn.commit()
                        request.state.api_user_id = row[1]
                        request.state.api_key_id = row[0]
                        request.state.api_scopes = row[3].split(',')
                        response = await call_next(request)
                        with get_db() as conn2:
                            with conn2.cursor() as c2:
                                c2.execute("INSERT INTO api_usage (id, user_id, api_key_id, endpoint) VALUES (%s,%s,%s,%s)",
                                          (str(uuid.uuid4()), row[1], row[0], request.url.path))
                                conn2.commit()
                        return response
        return Response(content="Invalid API key", status_code=401)
    else:
        return await call_next(request)

# ================================================================================
# HEALTH, MANIFEST, ICONS
# ================================================================================
@app.get("/health")
def health_check():
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
        "version": "32.5",
        "edition": "Token Economy",
        "database": db_status,
        "ai": ai_status,
        "providers": providers,
        "moderation": settings.ENABLE_MODERATION,
        "security_monitor": settings.ENABLE_SECURITY_MONITOR,
        "tiers": list(TIER_CONFIG.keys())
    }

@app.get("/manifest.json")
async def manifest():
    return JSONResponse(content={
        "name": "CapitanAI by CLOSEAI",
        "short_name": "CAPITAN AI",
        "description": "Your intelligent companion for thoughtful answers and clear insights.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#0f172a",
        "theme_color": "#0b6d8c",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}
        ]
    })

# Valid PNG base64 (simple teal square with white "C")
ICON_192_BASE64 = "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"

ICON_512_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAgAAAAIACAIAAAB7GkOtAAAhTklEQVR4nO3debgdZZ3g8XPX5OZmT4AkhOzEABEFQgDFQCMIBBQYxI0WFGVan2mgbZyx7bHbbnV65nmMtg+40qLj4wKIyHQLowgCgkQIhGDShADZkxtiFrLe5CZ3m6ebfhiULHXuPXWq6vw+n/98rITKOe95v1XvqVNV13rdvBIA8dRnvQMAZEMAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgKAEACEoAAIISAICgBAAgqMasdwBStPumG/v/lwy+/kuV2BfInbrW6+ZlvQ+Q/SzfN9pAoQkABZPhdJ+EJFAgAkAB5HzSPxgxIOcEgDwq6Ix/aHpA3ggAOVKT8/7rKQE5IQBkLMikfzBiQIYEgGwEn/dfTwmoPgGg2kz9hyADVJMAUCXm/bIoAVUgAKTO1N9nMkCqBIC0mPcrSAlIgwBQeaZ+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"

@app.get("/icon-192.png")
async def icon_192():
    return Response(content=base64.b64decode(ICON_192_BASE64), media_type="image/png")

@app.get("/icon-512.png")
async def icon_512():
    return Response(content=base64.b64decode(ICON_512_BASE64), media_type="image/png")

@app.get("/")
async def root():
    return {"name": "CAPITAN AI", "version": "32.5", "edition": "Token Economy"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"\n{'='*70}")
    print(f"🚀 CAPITAN AI v32.5 — Token Economy Edition")
    print(f"🧠 Full implementation – no cuts")
    print(f"🔐 JWT_SECRET & FOUNDER_KEY required from env")
    print(f"📍 Backend: 0.0.0.0:{port}")
    print(f"{'='*70}\n")
    uvicorn.run(app, host="0.0.0.0", port=port)