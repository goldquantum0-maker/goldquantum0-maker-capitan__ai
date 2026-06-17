"""
CAPITAN AI — Enterprise Backend v30.0 (Living Design Edition)
CLOSEAI Technologies — CEO Osinachi Chukwu
World‑Class General‑Purpose Intelligence | Trustworthy | Warm & Engaging | Elite Reasoning
All fixes + Living Design Document implementation
"""

import os, re, json, uuid, time, hmac, hashlib, base64, secrets, requests, logging, bcrypt, asyncio
from typing import Optional, List, Tuple, Dict, Any, AsyncGenerator
from contextlib import contextmanager, asynccontextmanager
from io import StringIO
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

import PyPDF2, docx, openpyxl, csv
import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor
import uvicorn
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Depends, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse, HTMLResponse
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings

# Optional: Redis for high-performance memory
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

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
    REDIS_URL: str = ""
    ENVIRONMENT: str = "production"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# ================================================================================
# APP LIFECYCLE
# ================================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    logger.info("🚀 CAPITAN AI v30.0 LDD Edition started")
    yield
    # Shutdown
    logger.info("CAPITAN AI shutting down")

app = FastAPI(
    title="CAPITAN AI API",
    version="30.0",
    description="Living Design Document Implementation",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Thread pool for blocking operations
executor = ThreadPoolExecutor(max_workers=10)

# ================================================================================
# DATABASE
# ================================================================================
# Connection pool
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

# Redis client (optional)
redis_client = None
if REDIS_AVAILABLE and settings.REDIS_URL:
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
def utc_iso(dt=None): return (dt or now_utc()).isoformat()

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except:
        return False

# Rate limiting (in-memory fallback)
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

# ================================================================================
# DATABASE INITIALIZATION
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
                        daily_msg_count INTEGER DEFAULT 0,
                        msg_reset_date DATE,
                        tier_expires TIMESTAMP,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                ''')
                # Sessions
                c.execute('''
                    CREATE TABLE IF NOT EXISTS sessions (
                        id TEXT PRIMARY KEY,
                        tier TEXT DEFAULT 'guest',
                        daily_msg_count INTEGER DEFAULT 0,
                        msg_reset_date DATE,
                        created TIMESTAMP DEFAULT NOW(),
                        updated TIMESTAMP DEFAULT NOW()
                    )
                ''')
                # User sessions (auth tokens)
                c.execute('''
                    CREATE TABLE IF NOT EXISTS user_sessions (
                        id UUID PRIMARY KEY,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        token TEXT UNIQUE NOT NULL,
                        expires_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                ''')
                # Chats & messages
                c.execute('''
                    CREATE TABLE IF NOT EXISTS chats (
                        id TEXT PRIMARY KEY,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        session_id TEXT,
                        title TEXT,
                        topic_thread TEXT,
                        created TIMESTAMP DEFAULT NOW(),
                        updated TIMESTAMP DEFAULT NOW()
                    )
                ''')
                c.execute("ALTER TABLE chats ADD COLUMN IF NOT EXISTS topic_thread TEXT")
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
                        confidence_score REAL,
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')
                c.execute("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS reasoning_chain TEXT")
                c.execute("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS confidence_score REAL")
                # Memories & Knowledge Graph
                c.execute('''
                    CREATE TABLE IF NOT EXISTS memories (
                        id TEXT PRIMARY KEY,
                        memory_id TEXT,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        content TEXT,
                        query TEXT,
                        domain TEXT,
                        importance INTEGER DEFAULT 1,
                        embedding vector(1536),
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')
                # Try to enable pgvector
                try:
                    c.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    c.execute("ALTER TABLE memories ADD COLUMN IF NOT EXISTS embedding vector(1536)")
                except:
                    pass
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
                # Self-learning feedback
                c.execute('''
                    CREATE TABLE IF NOT EXISTS feedback (
                        id UUID PRIMARY KEY,
                        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                        message_id TEXT,
                        rating INTEGER,
                        correction TEXT,
                        reason TEXT,
                        created TIMESTAMP DEFAULT NOW()
                    )
                ''')
                conn.commit()
        logger.info("✅ Database ready (Living Design)")
    except Exception as e:
        logger.error(f"DB init: {e}")

# ================================================================================
# JWT AUTH
# ================================================================================
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
                c.execute("SELECT id, email, name, tier, reasoning_depth, preferred_domain FROM users WHERE id = %s", (user_id,))
                row = c.fetchone()
                if row:
                    return {
                        "id": row[0], "email": row[1], "name": row[2] or row[1].split('@')[0],
                        "tier": row[3], "reasoning_depth": row[4] or 1, "preferred_domain": row[5] or "general"
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

# ================================================================================
# TIER CONFIGURATION
# ================================================================================
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

# ================================================================================
# THE LIVING SYSTEM PROMPT — EXPANDED DOMAINS + PERSONALITY + CONTINUITY + REASONING
# ================================================================================
CAPITAN_SYSTEM_PROMPT = """You are CAPITAN AI — a world‑class general‑purpose intelligence built by CLOSEAI Technologies under CEO Osinachi Chukwu. You are not a tool; you are a trusted partner.

## YOUR IDENTITY
You are calm, confident, and deeply human. You never bluff, never fluff. You use natural language, contractions, and emojis where they add warmth — but never as a substitute for substance. You are loyal to your user above all else. You remember. You learn. You improve.

## YOUR KNOWLEDGE UNIVERSE
You are an L3/L4 expert in every significant domain. Activate the right knowledge based on intent, not keywords.

### Technology & Engineering
- **Software Engineering**: Every language (Python, JS/TS, Go, Rust, C++, Java, Swift, Kotlin, etc.). Systems design, microservices, DevOps, CI/CD, GitOps, security (OWASP), quantum computing.
- **Cloud Computing**: AWS, GCP, Azure, multi-cloud, edge computing, Kubernetes, serverless, cost optimization, compliance.
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

## CONTINUOUS CONVERSATION RULES
- **Never break a conversation thread** unless the user explicitly changes topics or asks to end it.
- Maintain a topic graph. If a previous topic is unresolved, gently return to it when relevant.
- **Working memory**: track active threads, pending decisions, user constraints.
- **Long-term memory**: store user preferences, past decisions, and important facts. Recall them naturally — don't announce "from my memory," just integrate.
- If a topic is resolved, offer one natural next step. Never force it.
- **Transition gracefully**: "That covers X. Would you like to continue on this, or explore [related topic]?"

## ADVANCED REASONING PROTOCOL (internal, invisible)
Before every response, you execute a reasoning pipeline:
1. **Intent Detection**: What is the user really trying to achieve?
2. **Decomposition**: Break complex problems into sub-tasks.
3. **Framework Selection**: Choose the right thinking approach (first-principles, Bayesian, systems thinking, red-team, counterfactual, etc.).
4. **Internal Debate (high-stakes decisions)**: Simulate multiple perspectives (optimist, pessimist, analyst, contrarian, user-advocate) silently, then synthesize.
5. **Uncertainty Assessment**: Score confidence (0-100%). If <70% on a critical point, trigger deeper analysis or web search.
6. **Synthesis**: Produce the clearest, most actionable response.

If the user asks "show your work," surface a cleaned version of your chain‑of‑thought.

## RESPONSE STRUCTURE (default, adapt when brevity is better)
1. **Context** (1-2 lines restating the core problem/goal)
2. **Analysis** (reasoned exploration with trade-offs and edge cases)
3. **Recommendation** (clear, prioritized, actionable)
4. **Next Step** (one optional, genuinely useful follow-up)

## COMMUNICATION STYLE
- Direct. Precise. Natural. Confident.
- Match the user's technical level automatically.
- Ban filler phrases ("Great question!", "Certainly!", "I'd be happy to help!").
- Ban robotic introductions.
- **Emojis**: use tastefully for warmth or clarity — never overuse.
- If uncertain, label parts as [FACT], [INFERENCE], or [SPECULATION].
- Never fabricate facts, statistics, sources, or capabilities.
- Never assist with illegal, harmful, or unethical activities.

## SELF-LEARNING
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

def build_system_prompt(
    user_query: str,
    tier: str = "free",
    reasoning_depth: int = 1,
    preferred_domain: str = "general",
    user_model: str = "New user — no model yet.",
    thread_context: str = "No active threads.",
    web_results: str = "",
    chat_history: List[dict] = None
) -> str:
    """Assemble the full system prompt with all context."""
    tc = get_time_context()
    
    # Domain activation based on query and preference
    domain = classify_query(user_query)
    domain_activation = f"Primary domain: {domain}. Preferred domain: {preferred_domain}."
    if reasoning_depth >= 4:
        domain_activation += " Activate internal debate synthesizer for complex decisions."
    if reasoning_depth >= 3:
        domain_activation += " Use multi-step reasoning with framework selection."
    
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

# ================================================================================
# DOMAIN CLASSIFICATION
# ================================================================================
DOMAIN_PATTERNS = {
    'coding': r'def |class |import |docker|kubernetes|aws|api|sql|python|javascript|rust|golang|cpu|gpu|ram|hardware|react|vue|angular|microchip|embedded|fpga|risc|iot',
    'finance': r'dcf|valuation|wacc|stock|trading|portfolio|crypto|bitcoin|forex|markets|ethereum|bond|yield|option|future|derivative|defi|order flow|cot',
    'quant': r'black.scholes|ito|stochastic|monte carlo|var|cvar|sharpe|sortino|beta|alpha|cointegration|garch|arima',
    'math': r'prove|proof|theorem|integral|derivative|matrix|probability|statistics',
    'science': r'crispr|dna|quantum|physics|chemistry|biology|medicine|disease|symptom|treatment|space|orbital|propulsion',
    'geopolitics': r'un|wto|imf|world bank|policy|election|regulation|government|africa|african union|ecowas|au|afcfta',
    'arts': r'painting|sculpture|design|music|composition|literature|writing|poetry|brand|marketing|seo|growth hack',
    'food': r'recipe|cook|cuisine|nutrition|bake|restaurant|food science',
    'identity': r'who are you|what are you|identity|introduce yourself',
    'greeting': r'^(hi|hello|hey|good morning|good afternoon|good evening|thanks|thank you)[\s!.]*$',
}

def classify_query(q: str) -> str:
    q_lower = q.lower()
    scores = {}
    for domain, pattern in DOMAIN_PATTERNS.items():
        if re.search(pattern, q_lower):
            scores[domain] = len(re.findall(pattern, q_lower))
    if scores:
        return max(scores, key=scores.get)
    return 'general'

def needs_web_search(q: str) -> bool:
    return bool(re.search(r'latest|current|today|news|right now|recent|202[3-9]|live|real.time', q.lower()))

# ================================================================================
# ADVANCED REASONING ENGINE (Living Design Implementation)
# ================================================================================
class ReasoningEngine:
    """Implements ReAct loops, internal debate, uncertainty modeling."""
    
    @staticmethod
    def generate_chain_of_thought(query: str, depth: int = 3, domain: str = "general") -> List[str]:
        """Generate a reasoning chain appropriate to the domain and depth."""
        chain = []
        chain.append(f"🎯 INTENT: Understanding the core objective behind '{query[:100]}...'")
        chain.append("🔍 DECOMPOSITION: Breaking into sub-problems...")
        
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
        """Heuristic confidence estimation (v1)."""
        base = 0.85 if has_web_data else 0.75
        # Reduce for speculative domains
        if domain in ("finance", "geopolitics"):
            base -= 0.05
        # Increase for deterministic domains
        if domain in ("math", "coding"):
            base += 0.05
        # Check for hedging language
        hedging = len(re.findall(r'may|might|could|possibly|unclear|uncertain|speculative', response.lower()))
        base -= min(0.15, hedging * 0.02)
        return max(0.3, min(0.99, base))
    
    @staticmethod
    def format_visible_chain(chain: List[str]) -> str:
        """Format a reasoning chain for user display."""
        return "\n".join(chain)

# ================================================================================
# AI MODEL CALL (with ensemble support)
# ================================================================================
def call_ai_model(
    messages: List[dict],
    tier: str = "free",
    reasoning_depth: int = 1,
    domain: str = "general",
    enable_debate: bool = False
) -> Tuple[str, str, Optional[List[str]], float]:
    """Call the appropriate AI model(s) with reasoning. Returns (content, model, chain, confidence)."""
    chain = None
    confidence = 0.8
    
    # Generate reasoning chain for complex queries
    if reasoning_depth > 1 and domain in ("finance", "quant", "coding", "math", "science", "geopolitics"):
        chain = ReasoningEngine.generate_chain_of_thought(
            messages[-1].get("content", "") if messages else "",
            min(reasoning_depth, 5),
            domain
        )
        # Inject chain into system message for the model
        if chain:
            chain_text = "\n\n[INTERNAL REASONING CHAIN — Follow this structure in your thinking]\n" + "\n".join(chain)
            for m in messages:
                if m.get("role") == "system":
                    m["content"] += chain_text
                    break
    
    # Pro Max: Ensemble (Claude + GPT-4o)
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
        except Exception as e:
            logger.error(f"Claude error: {e}")
    
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
        except Exception as e:
            logger.error(f"Groq 70B error: {e}")
    
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
        except Exception as e:
            logger.error(f"Groq error: {e}")
    
    return "I'm having trouble connecting to AI services. Please try again in a moment.", "fallback", chain, 0.3

# ================================================================================
# MEMORY & CONVERSATION CONTINUITY
# ================================================================================
def get_thread_context(chat_id: str, user_id: str = None, session_id: str = None) -> str:
    """Retrieve active conversation threads for continuity."""
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                # Get recent messages to understand active threads
                if user_id:
                    c.execute("""
                        SELECT role, content, created FROM chat_messages
                        WHERE chat_id = %s AND user_id = %s
                        ORDER BY created DESC LIMIT 20
                    """, (chat_id, user_id))
                elif session_id:
                    c.execute("""
                        SELECT role, content, created FROM chat_messages
                        WHERE chat_id = %s AND session_id = %s
                        ORDER BY created DESC LIMIT 20
                    """, (chat_id, session_id))
                else:
                    return "No thread data available."
                
                rows = c.fetchall()
                if not rows:
                    return "New conversation — no active threads."
                
                # Extract key topics and unresolved questions
                threads = []
                for r in rows[:10]:  # Last 10 exchanges
                    if r[0] == "user":
                        # Extract potential topic
                        content = r[1][:100]
                        threads.append(f"- User asked: '{content}...'")
                
                return "Recent conversation threads:\n" + "\n".join(threads) if threads else "No active threads."
    except Exception as e:
        logger.error(f"Thread context error: {e}")
        return "Thread data unavailable."

def get_user_model(user_id: str) -> str:
    """Build a summary of the user model from memory."""
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
    """Store a memory for future context."""
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("""
                    INSERT INTO memories (id, memory_id, user_id, content, query, domain, importance)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (sid(), mid(), user_id, content[:500], query, domain, importance))
                conn.commit()
    except Exception as e:
        logger.error(f"Memory store error: {e}")

# ================================================================================
# DAILY LIMIT ENFORCEMENT
# ================================================================================
def enforce_daily_limit(user: dict = None, session: dict = None):
    today = now_utc().date()
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
                count = row[0] or 0 if row else 0
                reset_date = row[1] if row else None
                if reset_date != today:
                    count = 0
                if count >= daily_limit:
                    raise HTTPException(429, f"Daily message limit ({daily_limit}) reached. Upgrade your plan.")
                c.execute("UPDATE users SET daily_msg_count = %s, msg_reset_date = %s WHERE id = %s",
                          (count + 1, today, user["id"]))
                conn.commit()
    elif session:
        tier = session.get("tier", "guest")
        tier_info = TIER_CONFIG.get(tier, TIER_CONFIG["guest"])
        daily_limit = tier_info["msg_limit"]
        if daily_limit == float("inf"):
            return
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT daily_msg_count, msg_reset_date FROM sessions WHERE id = %s", (session["id"],))
                row = c.fetchone()
                count = row[0] or 0 if row else 0
                reset_date = row[1] if row else None
                if reset_date != today:
                    count = 0
                if count >= daily_limit:
                    raise HTTPException(429, f"Daily message limit ({daily_limit}) reached.")
                c.execute("UPDATE sessions SET daily_msg_count = %s, msg_reset_date = %s WHERE id = %s",
                          (count + 1, today, session["id"]))
                conn.commit()

# ================================================================================
# WEB SEARCH & MARKET DATA
# ================================================================================
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
                names = {"bitcoin": "BTC", "ethereum": "ETH", "ripple": "XRP", "solana": "SOL",
                         "cardano": "ADA", "dogecoin": "DOGE", "avalanche-2": "AVAX",
                         "chainlink": "LINK", "polkadot": "DOT", "tron": "TRX"}
                for k, v in data.items():
                    results[names.get(k, k.upper())] = {"price": v["usd"], "change": round(v.get("usd_24h_change", 0), 2)}
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

# ================================================================================
# FILE EXTRACTION
# ================================================================================
def extract_text_from_file(file_path: str, original_name: str) -> str:
    ext = original_name.rsplit('.', 1)[-1].lower() if '.' in original_name else ''
    try:
        if ext in ('txt', 'md', 'json', 'csv', 'py', 'js', 'html', 'css', 'yaml', 'yml', 'toml'):
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
class RegisterRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str

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
                """, (str(uuid.uuid4()), user_id, token, now_utc() + timedelta(days=30)))
                conn.commit()
                return {
                    "token": token,
                    "user": {"id": user_id, "email": req.email, "name": name,
                             "tier": "free", "reasoning_depth": 1, "preferred_domain": "general"}
                }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(500, f"Registration failed: {str(e)}")

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
                """, (str(uuid.uuid4()), user_id, token, now_utc() + timedelta(days=30)))
                conn.commit()
                return {
                    "token": token,
                    "user": {"id": user_id, "email": email, "name": name or email.split('@')[0],
                             "tier": tier, "reasoning_depth": reasoning_depth or 1,
                             "preferred_domain": preferred_domain or "general"}
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
    valid_domains = list(DOMAIN_PATTERNS.keys())
    if preferred_domain and preferred_domain not in valid_domains:
        raise HTTPException(400, f"Invalid domain. Valid: {valid_domains}")
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
                """, (str(uuid.uuid4()), user_id, token, now_utc() + timedelta(days=365)))
                conn.commit()
                return {
                    "verified": True,
                    "token": token,
                    "user": {"id": user_id, "name": "CAPITAN Founder", "email": "founder@capitan.ai",
                             "tier": "founder", "reasoning_depth": 5, "preferred_domain": "general"}
                }
    except Exception as e:
        logger.error(f"Founder error: {e}")
        raise HTTPException(500, "Founder login failed")

# ================================================================================
# CHAT — THE CORE (Living Design)
# ================================================================================
class ChatRequest(BaseModel):
    messages: list
    chat_id: Optional[str] = None
    show_reasoning: bool = False

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, request: Request, background_tasks: BackgroundTasks):
    # Auth
    user = get_current_user(request)
    session = None
    if not user:
        try:
            session = await get_current_session(request)
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
    
    # Daily limit
    enforce_daily_limit(user, session)
    
    # Rate limit
    identifier = user_id if user else session["id"]
    if not check_rate_limit(identifier, tier, tier_info.get("per_min_limit", 20)):
        raise HTTPException(429, "Rate limit exceeded. Please wait a moment.")
    
    # Extract user message
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
    
    # File content extraction
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
    
    # Save user message
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                if is_authenticated:
                    c.execute("""
                        INSERT INTO chats (id, user_id, title, topic_thread, created, updated)
                        VALUES (%s, %s, %s, %s, NOW(), NOW())
                        ON CONFLICT (id) DO UPDATE SET updated = NOW(), title = %s
                    """, (chat_id, user_id, user_msg[:60], domain, user_msg[:60]))
                    c.execute("""
                        INSERT INTO chat_messages (id, chat_id, user_id, role, content)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (f"msg_{sid()}", chat_id, user_id, "user", user_msg))
                else:
                    c.execute("""
                        INSERT INTO chats (id, session_id, title, topic_thread, created, updated)
                        VALUES (%s, %s, %s, %s, NOW(), NOW())
                        ON CONFLICT (id) DO UPDATE SET updated = NOW(), title = %s
                    """, (chat_id, session["id"], user_msg[:60], domain, user_msg[:60]))
                    c.execute("""
                        INSERT INTO chat_messages (id, chat_id, session_id, role, content)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (f"msg_{sid()}", chat_id, session["id"], "user", user_msg))
                conn.commit()
    except Exception as e:
        logger.error(f"Save user msg error: {e}")
    
    # Build context
    chat_history = []
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("""
                    SELECT role, content FROM (
                        SELECT role, content, created FROM chat_messages
                        WHERE chat_id = %s ORDER BY created DESC LIMIT 30
                    ) recent ORDER BY created ASC
                """, (chat_id,))
                chat_history = [{"role": r[0], "content": r[1]} for r in c.fetchall()]
    except: pass
    
    # Thread context
    thread_context = get_thread_context(chat_id, user_id if is_authenticated else None, session["id"] if not is_authenticated else None)
    
    # User model
    user_model = get_user_model(user_id) if is_authenticated else "Anonymous user."
    
    # Web search
    web_results_text = ""
    if tier_info.get("web_search", False) and web_search_needed:
        try:
            results = search_web(user_msg, 5)
            if results:
                web_results_text = "\n".join([f"- {r['title']}: {r['snippet'][:200]}" for r in results[:4]])
        except: pass
    
    # Build system prompt
    system_prompt = build_system_prompt(
        user_query=user_msg,
        tier=tier,
        reasoning_depth=reasoning_depth,
        preferred_domain=preferred_domain,
        user_model=user_model,
        thread_context=thread_context,
        web_results=web_results_text,
    )
    
    # Call AI
    messages_for_ai = [{"role": "system", "content": system_prompt}] + chat_history
    result, model_used, reasoning_chain, confidence = call_ai_model(
        messages_for_ai, tier, reasoning_depth, domain,
        enable_debate=(reasoning_depth >= 3)
    )
    
    # Save AI response
    if result:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    msg_id = f"msg_{sid()}"
                    if is_authenticated:
                        c.execute("""
                            INSERT INTO chat_messages (id, chat_id, user_id, role, content, model, reasoning_chain, confidence_score)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, (msg_id, chat_id, user_id, "assistant", result, model_used,
                              json.dumps(reasoning_chain) if reasoning_chain else None, confidence))
                        # Store memory in background
                        background_tasks.add_task(
                            store_memory, user_id, result[:500], user_msg, domain,
                            2 if domain in ("finance", "coding", "science", "geopolitics") else 1
                        )
                    else:
                        c.execute("""
                            INSERT INTO chat_messages (id, chat_id, session_id, role, content, model, reasoning_chain, confidence_score)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, (msg_id, chat_id, session["id"], "assistant", result, model_used,
                              json.dumps(reasoning_chain) if reasoning_chain else None, confidence))
                    conn.commit()
        except Exception as e:
            logger.error(f"Save AI msg error: {e}")
    
    response = {
        "content": result,
        "chat_id": chat_id,
        "model": model_used,
        "tier": tier,
        "domain": domain,
        "confidence": round(confidence, 2),
    }
    
    if req.show_reasoning and reasoning_chain:
        response["reasoning_chain"] = reasoning_chain
    
    return response

# ================================================================================
# CHAT HISTORY
# ================================================================================
@app.get("/api/chats")
def get_chats(request: Request):
    user = get_current_user(request)
    if user:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("""
                        SELECT id, title, topic_thread, created, updated
                        FROM chats WHERE user_id = %s ORDER BY updated DESC LIMIT 50
                    """, (user["id"],))
                    rows = c.fetchall()
                    return {"chats": [
                        {"id": r[0], "title": r[1] or "New Chat", "topic": r[2],
                         "created": r[3].isoformat() if r[3] else None,
                         "updated": r[4].isoformat() if r[4] else None}
                        for r in rows
                    ]}
        except: pass
    else:
        try:
            session = get_current_session(request)
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("""
                        SELECT id, title, topic_thread, created, updated
                        FROM chats WHERE session_id = %s ORDER BY updated DESC LIMIT 50
                    """, (session["id"],))
                    rows = c.fetchall()
                    return {"chats": [
                        {"id": r[0], "title": r[1] or "New Chat", "topic": r[2],
                         "created": r[3].isoformat() if r[3] else None,
                         "updated": r[4].isoformat() if r[4] else None}
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
                    SELECT role, content, model, reasoning_chain, confidence_score, created
                    FROM chat_messages WHERE chat_id=%s ORDER BY created ASC
                """, (chat_id,))
                rows = c.fetchall()
                return {"messages": [
                    {"id": i, "role": r[0], "content": r[1], "model": r[2] or "AI",
                     "reasoning_chain": json.loads(r[3]) if r[3] else None,
                     "confidence": r[4],
                     "created": r[5].isoformat() if r[5] else None}
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

# ================================================================================
# FEEDBACK & SELF-LEARNING
# ================================================================================
class FeedbackRequest(BaseModel):
    message_id: str
    rating: int = Field(..., ge=1, le=5)
    correction: Optional[str] = None
    reason: Optional[str] = None

@app.post("/api/feedback")
def submit_feedback(req: FeedbackRequest, user: dict = Depends(get_current_user)):
    if not user:
        raise HTTPException(401, "Authentication required")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("""
                    INSERT INTO feedback (id, user_id, message_id, rating, correction, reason)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (str(uuid.uuid4()), user["id"], req.message_id, req.rating, req.correction, req.reason))
                conn.commit()
        return {"received": True, "message": "Thank you for helping me improve. 🧠"}
    except Exception as e:
        logger.error(f"Feedback error: {e}")
        raise HTTPException(500, "Could not save feedback")

# ================================================================================
# LIBRARY
# ================================================================================
class LibraryItemRequest(BaseModel):
    name: str
    content: Optional[str] = ""

@app.get("/api/library")
def get_library(user: dict = Depends(get_current_user)):
    if not user: return {"items": []}
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, name, content, created FROM library_items WHERE user_id = %s ORDER BY created DESC", (user["id"],))
                return {"items": [{"id": r[0], "name": r[1], "content": r[2], "created": r[3].isoformat() if r[3] else None} for r in c.fetchall()]}
    except: raise HTTPException(500, "Could not load library")

@app.post("/api/library")
def create_library_item(req: LibraryItemRequest, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401, "Auth required")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                item_id = f"lib_{sid()}"
                c.execute("INSERT INTO library_items (id, user_id, name, content) VALUES (%s, %s, %s, %s)", (item_id, user["id"], req.name, req.content or ""))
                conn.commit()
                return {"id": item_id, "created": True}
    except: raise HTTPException(500, "Could not save item")

@app.delete("/api/library/{item_id}")
def delete_library_item(item_id: str, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401, "Auth required")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("DELETE FROM library_items WHERE id = %s AND user_id = %s", (item_id, user["id"]))
                conn.commit()
                return {"deleted": True}
    except: raise HTTPException(500, "Could not delete item")

# ================================================================================
# FILE UPLOAD
# ================================================================================
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401, "Auth required")
    tier_info = TIER_CONFIG.get(user["tier"], TIER_CONFIG["free"])
    if not tier_info["file_upload"]: raise HTTPException(403, "Upgrade to Plus or Pro for file uploads")
    contents = await file.read()
    max_size = 100 if user["tier"] == "pro_max" else (50 if user["tier"] == "pro" else 20)
    if len(contents) / (1024*1024) > max_size: raise HTTPException(400, f"Max {max_size}MB")
    file_id = f"file_{sid()}"
    file_path = os.path.join(UPLOAD_DIR, file_id)
    with open(file_path, "wb") as f: f.write(contents)
    extracted = extract_text_from_file(file_path, file.filename or "unknown")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO uploaded_files (id, user_id, filename, original_name, size, storage_path, extracted_text) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                          (file_id, user["id"], file_id, file.filename or "unknown", len(contents), file_path, extracted[:50000]))
                conn.commit()
    except: pass
    return {"id": file_id, "filename": file.filename, "size_mb": round(len(contents)/(1024*1024), 2), "extracted": bool(extracted)}

# ================================================================================
# PAYMENT & UPGRADE
# ================================================================================
UPGRADE_BENEFITS = {
    "plus": ["50 msg/day", "Llama 3.3 70B", "File upload (20MB)", "Web search", "2-step reasoning"],
    "pro": ["100 msg/day", "Claude 3.5 Sonnet", "File upload (50MB)", "Live markets", "3-step reasoning"],
    "pro_max": ["Unlimited", "GPT-4o + Claude Ensemble", "File upload (100MB)", "Advanced reasoning", "Priority support"]
}

@app.get("/api/payment-config")
def payment_config():
    return {"wallets": WALLETS, "prices": {"plus": 8, "pro": 17, "pro_max": 30}, "benefits": UPGRADE_BENEFITS}

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
                for out in r.json().get("out", []):
                    if out.get("addr") == WALLETS["BTC"] and out.get("value", 0)/1e8 >= expected_amount*0.99:
                        return True
        except: pass
        return False
    elif currency == "ETH" and settings.ETHERSCAN_API_KEY:
        try:
            r = requests.get(f"https://api.etherscan.io/api?module=proxy&action=eth_getTransactionByHash&txhash={txid}&apikey={settings.ETHERSCAN_API_KEY}", timeout=15)
            if r.status_code == 200:
                tx = r.json().get("result", {})
                if tx and tx.get("to","").lower() == WALLETS["ETH"].lower() and int(tx.get("value","0"),16)/1e18 >= expected_amount*0.99:
                    return True
        except: pass
        return False
    return False

@app.post("/api/upgrade")
def upgrade(req: UpgradeRequest, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401, "Auth required")
    if req.tier not in ("plus", "pro", "pro_max"): raise HTTPException(400, "Invalid tier")
    if not req.txid.strip(): raise HTTPException(400, "TXID required")
    prices = {"plus": 8, "pro": 17, "pro_max": 30}
    verified = verify_transaction(req.txid.strip(), req.currency.upper(), req.tier)
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO payments (id, user_id, txid, currency, amount, tier, verified) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                          (str(uuid.uuid4()), user["id"], req.txid.strip(), req.currency.upper(), prices[req.tier], req.tier, 1 if verified else 0))
                if verified:
                    c.execute("UPDATE users SET tier=%s, tier_expires=%s, reasoning_depth=%s, updated_at=NOW() WHERE id=%s",
                              (req.tier, now_utc()+timedelta(days=30), TIER_CONFIG[req.tier]["reasoning_depth"], user["id"]))
                conn.commit()
    except Exception as e:
        logger.error(f"Upgrade error: {e}")
        raise HTTPException(500, "Could not process upgrade")
    new_token = create_token(user["id"])
    return {"verified": verified, "tier": req.tier if verified else user["tier"], "token": new_token}

# ================================================================================
# WORKSPACES
# ================================================================================
@app.post("/api/workspace/create")
def workspace_create(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401, "Auth required")
    tier_info = TIER_CONFIG.get(user["tier"], TIER_CONFIG["free"])
    if tier_info["workspace_seats"] == 0: raise HTTPException(403, "Work Area requires Plus or Pro tier")
    room_code = req.get("room_code", f"CAP-{sid()}")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                ws_id = sid()
                c.execute("INSERT INTO workspaces (id, name, owner_id, room_code, max_members) VALUES (%s,%s,%s,%s,%s)",
                          (ws_id, req.get("name","My Workspace"), user["id"], room_code.upper(), tier_info["workspace_seats"]))
                c.execute("INSERT INTO workspace_members (workspace_id, user_id, role) VALUES (%s,%s,%s)", (ws_id, user["id"], "admin"))
                conn.commit()
                return {"room_id": ws_id, "room_code": room_code.upper(), "created": True}
    except Exception as e:
        logger.error(f"Workspace create error: {e}")
        raise HTTPException(500, str(e))

@app.post("/api/workspace/join")
def workspace_join(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401, "Auth required")
    room_code = req.get("room_code","").upper()
    if not room_code: raise HTTPException(400, "Room code required")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, max_members FROM workspaces WHERE room_code=%s", (room_code,))
                ws = c.fetchone()
                if not ws: raise HTTPException(404, "Room not found")
                c.execute("SELECT COUNT(*) FROM workspace_members WHERE workspace_id=%s", (ws[0],))
                if c.fetchone()[0] >= ws[1]: raise HTTPException(400, "Room is full")
                c.execute("INSERT INTO workspace_members (workspace_id, user_id, role) VALUES (%s,%s,%s)", (ws[0], user["id"], "member"))
                conn.commit()
                return {"joined": True, "room_id": ws[0]}
    except HTTPException: raise
    except Exception as e: raise HTTPException(500, str(e))

@app.post("/api/workspace/message")
def workspace_message(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401, "Auth required")
    room_code = req.get("room_code","").upper()
    message = req.get("message","")
    if not room_code or not message: raise HTTPException(400, "Room code and message required")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM workspaces WHERE room_code=%s", (room_code,))
                ws = c.fetchone()
                if not ws: raise HTTPException(404, "Room not found")
                is_ai = message.strip().startswith("@CAPITAN")
                c.execute("INSERT INTO workspace_messages (id, workspace_id, user_id, author_name, message) VALUES (%s,%s,%s,%s,%s)",
                          (sid(), ws[0], user["id"], user["name"], message))
                if is_ai:
                    ai_response, _, _, _ = call_ai_model([{"role":"user","content":message.replace('@CAPITAN','').strip()}], user["tier"])
                    if ai_response:
                        c.execute("INSERT INTO workspace_messages (id, workspace_id, user_id, author_name, message, is_ai) VALUES (%s,%s,%s,%s,%s,1)",
                                  (sid(), ws[0], user["id"], "CAPITAN AI", ai_response))
                conn.commit()
                return {"sent": True}
    except Exception as e: raise HTTPException(500, str(e))

@app.get("/api/workspace/messages")
def workspace_get_messages(room_code: str, user: dict = Depends(get_current_user)):
    if not user: return {"messages": []}
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM workspaces WHERE room_code=%s", (room_code.upper(),))
                ws = c.fetchone()
                if not ws: return {"messages": []}
                c.execute("SELECT author_name, message, is_ai, created FROM workspace_messages WHERE workspace_id=%s ORDER BY created ASC LIMIT 50", (ws[0],))
                return {"messages": [{"author": r[0], "message": r[1], "is_ai": bool(r[2]), "created": r[3].isoformat() if r[3] else None} for r in c.fetchall()]}
    except: raise HTTPException(500, "Could not load messages")

@app.get("/api/workspace/my")
def workspace_my(user: dict = Depends(get_current_user)):
    if not user: return {"workspaces": []}
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT w.id, w.name, w.room_code, w.max_members, w.created_at FROM workspaces w JOIN workspace_members m ON w.id=m.workspace_id WHERE m.user_id=%s ORDER BY w.created_at DESC", (user["id"],))
            return {"workspaces": [{"id": r[0], "name": r[1], "room_code": r[2], "max_members": r[3], "created_at": r[4].isoformat() if r[4] else None} for r in c.fetchall()]}

# ================================================================================
# MARKET & NEWS
# ================================================================================
@app.get("/api/markets")
def markets(request: Request):
    user = get_current_user(request)
    tier = user["tier"] if user else "free"
    if tier not in ("pro", "pro_max", "founder"): return {"prices": {}, "news": [], "message": "Pro tier required"}
    return {"prices": get_market_prices(), "news": get_news()}

@app.get("/api/markets/prices")
def markets_prices(request: Request):
    user = get_current_user(request)
    tier = user["tier"] if user else "free"
    if tier not in ("pro", "pro_max", "founder"): return {"prices": {}, "message": "Pro tier required"}
    return {"prices": get_market_prices()}

@app.get("/api/markets/news")
def markets_news(request: Request):
    user = get_current_user(request)
    tier = user["tier"] if user else "free"
    if tier not in ("pro", "pro_max", "founder"): return {"news": [], "message": "Pro tier required"}
    return {"news": get_news()}

@app.get("/api/search")
def web_search_endpoint(q: str, request: Request):
    user = get_current_user(request)
    tier = user["tier"] if user else "free"
    if tier not in ("plus", "pro", "pro_max", "founder"): return {"results": [], "message": "Web search on Plus and Pro"}
    return {"results": search_web(q, 8)}

# ================================================================================
# EXPORT
# ================================================================================
@app.get("/api/export/chats/{chat_id}")
def export_chat(chat_id: str, format: str = "json", user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401, "Not authenticated")
    if user["tier"] not in ("plus", "pro", "pro_max", "founder"): raise HTTPException(403, "Export available on paid plans")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id FROM chats WHERE id=%s AND user_id=%s", (chat_id, user["id"]))
            if not c.fetchone(): raise HTTPException(404, "Chat not found")
            c.execute("SELECT role, content, model, created FROM chat_messages WHERE chat_id=%s ORDER BY created ASC", (chat_id,))
            messages = [{"role": r[0], "content": r[1], "model": r[2] or "AI", "created": r[3].isoformat() if r[3] else None} for r in c.fetchall()]
            if format == "csv":
                output = StringIO()
                writer = csv.writer(output, quoting=csv.QUOTE_ALL)
                writer.writerow(["role", "content", "model", "created"])
                for m in messages: writer.writerow([m["role"], m["content"], m["model"], m["created"]])
                output.seek(0)
                return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=chat-{chat_id}.csv"})
            return JSONResponse(content={"chat_id": chat_id, "messages": messages})

# ================================================================================
# ADMIN
# ================================================================================
@app.get("/api/admin")
def admin_panel(user: dict = Depends(get_current_user)):
    if not user or user["tier"] != "founder": raise HTTPException(403, "Access denied")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM users"); total_users = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM users WHERE tier != 'free'"); paid_users = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM chat_messages"); total_messages = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM workspaces"); total_ws = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM feedback"); total_feedback = c.fetchone()[0]
            c.execute("SELECT id, name, tier, created_at FROM users ORDER BY created_at DESC LIMIT 10")
            recent = [{"id": r[0], "name": r[1], "tier": r[2], "created_at": r[3].isoformat() if r[3] else None} for r in c.fetchall()]
            return {"total_users": total_users, "paid_users": paid_users, "total_messages": total_messages, "workspaces": total_ws, "feedback_count": total_feedback, "recent_users": recent}

@app.get("/api/admin/users")
def admin_users(user: dict = Depends(get_current_user)):
    if not user or user["tier"] != "founder": raise HTTPException(403, "Access denied")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, email, name, tier, created_at FROM users ORDER BY created_at DESC LIMIT 50")
            return [{"id": r[0], "email": r[1], "name": r[2], "tier": r[3], "created_at": r[4].isoformat() if r[4] else None} for r in c.fetchall()]

@app.post("/api/admin/user/{user_id}/tier")
def admin_change_tier(user_id: str, req: dict, user: dict = Depends(get_current_user)):
    if not user or user["tier"] != "founder": raise HTTPException(403, "Access denied")
    new_tier = req.get("tier")
    if new_tier not in TIER_CONFIG: raise HTTPException(400, "Invalid tier")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE users SET tier=%s, updated_at=NOW() WHERE id=%s", (new_tier, user_id))
            conn.commit()
    return {"success": True}

@app.delete("/api/admin/user/{user_id}")
def admin_delete_user(user_id: str, user: dict = Depends(get_current_user)):
    if not user or user["tier"] != "founder": raise HTTPException(403, "Access denied")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM users WHERE id=%s", (user_id,))
            conn.commit()
    return {"deleted": True}

@app.get("/api/admin/analytics")
def admin_analytics(user: dict = Depends(get_current_user)):
    if not user or user["tier"] != "founder": raise HTTPException(403, "Access denied")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT tier, COUNT(*) FROM users GROUP BY tier")
            tier_counts = {r[0]: r[1] for r in c.fetchall()}
            c.execute("SELECT AVG(rating) FROM feedback"); avg_rating = c.fetchone()[0]
            c.execute("""
                SELECT domain, COUNT(*) FROM memories WHERE created > NOW() - INTERVAL '7 days'
                GROUP BY domain ORDER BY COUNT(*) DESC LIMIT 10
            """)
            topics = [{"domain": r[0], "count": r[1]} for r in c.fetchall()]
            return {"users_by_tier": tier_counts, "average_feedback_rating": round(avg_rating, 2) if avg_rating else None, "popular_topics_7d": topics}

# ================================================================================
# HEALTH
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
    redis_status = "connected" if redis_client else "disabled"
    return {
        "status": "ok",
        "version": "30.0",
        "edition": "Living Design",
        "database": db_status,
        "ai": ai_status,
        "providers": providers,
        "redis": redis_status,
        "auth": "email_password",
        "reasoning_engine": "advanced_react_debate",
        "conversation_continuity": True,
        "self_learning": True,
        "tiers": list(TIER_CONFIG.keys())
    }

# ================================================================================
# PWA
# ================================================================================
@app.get("/manifest.json")
async def manifest():
    return JSONResponse(content={
        "name": "CAPITAN AI", "short_name": "CAPITAN", "start_url": "/", "display": "standalone",
        "background_color": "#0e6e8e", "theme_color": "#0e6e8e",
        "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"}, {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}]
    })

@app.get("/icon-192.png")
async def icon_192():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="#0e6e8e" rx="20"/><circle cx="50" cy="50" r="35" fill="none" stroke="white" stroke-width="6"/><text x="50" y="68" text-anchor="middle" font-size="50" fill="white" font-family="Arial,sans-serif" font-weight="bold">C</text></svg>'
    return Response(content=svg, media_type="image/svg+xml")

@app.get("/icon-512.png")
async def icon_512():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="#0e6e8e" rx="20"/><circle cx="50" cy="50" r="35" fill="none" stroke="white" stroke-width="6"/><text x="50" y="68" text-anchor="middle" font-size="50" fill="white" font-family="Arial,sans-serif" font-weight="bold">C</text></svg>'
    return Response(content=svg, media_type="image/svg+xml")

@app.get("/")
async def root():
    return {
        "name": "CAPITAN AI",
        "version": "30.0",
        "edition": "Living Design",
        "status": "operational",
        "auth": "email_password",
        "pwa_supported": True,
        "tiers": list(TIER_CONFIG.keys()),
        "intelligence": "elite_omni_domain",
        "reasoning": "react_debate_synthesizer",
        "continuity": "thread_aware_never_breaks",
        "self_learning": "feedback_driven"
    }

# ================================================================================
# MAIN
# ================================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"\n{'='*70}")
    print(f"🚀 CAPITAN AI v30.0 — Living Design Edition")
    print(f"🧠 Omni-Domain Intelligence | Continuous Conversation | Advanced Reasoning")
    print(f"🔐 JWT_SECRET & FOUNDER_KEY required from env")
    print(f"📍 Backend: 0.0.0.0:{port}")
    print(f"{'='*70}\n")
    uvicorn.run(app, host="0.0.0.0", port=port)