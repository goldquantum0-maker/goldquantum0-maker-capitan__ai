"""
CAPITAN AI — Enterprise Backend v36.0 (Full Unabridged — Wallet, 2FA, Safe, Relayer)
CLOSEAI Technologies — CEO Osinachi Chukwu
"""
import os, re, json, uuid, time, hmac, hashlib, base64, secrets, requests, logging, bcrypt
from typing import Optional, List, Tuple, Dict, Any
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import PyPDF2, docx, openpyxl
import psycopg2
import psycopg2.pool
import uvicorn
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Depends, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, FileResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

# Optional tiktoken
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

# Optional Redis
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Numpy and aiohttp for portfolio optimizer
NUMPY_AVAILABLE = False
AIOHTTP_AVAILABLE = False
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    pass
try:
    import aiohttp
    import asyncio
    AIOHTTP_AVAILABLE = True
except ImportError:
    pass

# Web3 for Polygon on‑chain verification and DEX – optional
WEB3_AVAILABLE = False
try:
    from web3 import Web3
    WEB3_AVAILABLE = True
except ImportError:
    pass

# 2FA
TOTP_AVAILABLE = False
try:
    import pyotp
    TOTP_AVAILABLE = True
except ImportError:
    pass

QRCODE_AVAILABLE = False
try:
    import qrcode
    from io import BytesIO
    QRCODE_AVAILABLE = True
except ImportError:
    pass

# Cryptography for wallet encryption
CRYPTO_AVAILABLE = False
try:
    from cryptography.fernet import Fernet
    CRYPTO_AVAILABLE = True
except ImportError:
    pass

# eth_account for wallet generation (optional, fallback to ethers on frontend)
ETH_ACCOUNT_AVAILABLE = False
try:
    from eth_account import Account
    ETH_ACCOUNT_AVAILABLE = True
except ImportError:
    pass

import concurrent.futures
executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)

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
    PRIVACY_POLICY_TEXT: str = ""
    TERMS_CONDITIONS_TEXT: str = ""

    # $CAP on‑chain settings
    CAP_CONTRACT_ADDRESS: str = ""          # fill after token deployment
    CAP_HOT_WALLET: str = "0x003E88850a34F7fd9A81d532CCFe3DdA0CC8427F"
    CAP_DEX_PAIR_ADDRESS: str = ""          # fill after creating liquidity pool
    CLOSEAI_TREASURY_ADDRESS: str = ""      # Gnosis Safe address
    POLYGON_RPC_URL: str = "https://polygon-rpc.com"
    CAP_DECIMALS: int = 18
    CLOSEAI_TOTAL_ALLOCATION: int = 75_000_000_000_000  # 75 trillion CAP

    # Relayer
    RELAYER_PRIVATE_KEY: str = ""

    # 2FA
    TOTP_ISSUER: str = "CAPITAN AI"

    # Gnosis Safe
    SAFE_OWNER_1: str = ""
    SAFE_OWNER_2: str = ""
    SAFE_OWNER_3: str = ""
    SAFE_THRESHOLD: int = 2

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

app = FastAPI(title="CAPITAN AI API", version="36.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database pool
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

# Helpers
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

def create_session_token(session_id: str) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "session_id": session_id, "type": "session",
        "exp": int((now_utc() + timedelta(days=365)).timestamp())
    }).encode()).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(hmac.new(settings.JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return f"{header}.{payload}.{signature}"

def verify_token(token: str):
    try:
        parts = token.split(".")
        if len(parts) != 3: return None
        header, payload, signature = parts
        missing_padding = 4 - len(payload) % 4
        if missing_padding != 4:
            payload_padded = payload + "=" * missing_padding
        else:
            payload_padded = payload
        expected = base64.urlsafe_b64encode(hmac.new(settings.JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
        if not hmac.compare_digest(signature, expected): return None
        data = json.loads(base64.urlsafe_b64decode(payload_padded))
        if data.get("exp", 0) < now_utc().timestamp(): return None
        return data
    except:
        return None

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
                c.execute("SELECT id, email, name, reasoning_depth, preferred_domain, token_balance, is_admin FROM users WHERE id = %s", (user_id,))
                row = c.fetchone()
                if row:
                    return {
                        "id": row[0], "email": row[1], "name": row[2] or row[1].split('@')[0],
                        "reasoning_depth": row[3] or 1, "preferred_domain": row[4] or "general",
                        "token_balance": row[5] or 0, "is_admin": row[6] or False
                    }
    except Exception as e:
        logger.error(f"get_current_user error: {e}")
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
            return {"id": user["id"], "is_user": True, "user_data": user, "token_balance": user["token_balance"]}
    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(401, "Invalid session token")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, token_balance FROM sessions WHERE id = %s", (session_id,))
                row = c.fetchone()
                if row:
                    return {"id": row[0], "token_balance": row[1] or 0, "is_user": False}
                else:
                    c.execute("INSERT INTO sessions (id, token_balance) VALUES (%s, 600)", (session_id,))
                    conn.commit()
                    return {"id": session_id, "token_balance": 600, "is_user": False}
    except Exception as e:
        logger.error(f"get_current_session error: {e}")
    raise HTTPException(401, "Session not found")

def founder_only(user: dict = Depends(get_current_user)):
    if not user or not user.get("is_admin", False):
        raise HTTPException(403, "Founder access required")
    return user

# Constants
MAX_PROJECTS = 30
MAX_WORKSPACES = 30
MAX_FILE_SIZE_MB = 60
GUEST_TOKEN_BALANCE = 600
REGISTER_TOKEN_BALANCE = 3000
DEPTH_MULTIPLIERS = [1.0, 1.5, 2.0, 3.0, 4.0]

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
ENTERPRISE_TOKEN_PACKAGES = [
    {"amount": 200, "tokens": 320000},
    {"amount": 500, "tokens": 850000},
    {"amount": 1000,"tokens": 2000000}
]

CAP_BUILDER_THRESHOLD = 10_000
CAP_PRO_THRESHOLD = 100_000
CAP_ENTERPRISE_THRESHOLD = 1_000_000

def init_db():
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                # Users (with is_admin, no tier)
                c.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id UUID PRIMARY KEY,
                        email TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        name TEXT,
                        reasoning_depth INTEGER DEFAULT 1,
                        preferred_domain TEXT DEFAULT 'general',
                        token_balance INTEGER DEFAULT 0,
                        is_admin BOOLEAN DEFAULT FALSE,
                        last_active TIMESTAMP DEFAULT NOW(),
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                ''')
                c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS token_balance INTEGER DEFAULT 0")
                c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active TIMESTAMP DEFAULT NOW()")
                c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE")
                c.execute("ALTER TABLE users DROP COLUMN IF EXISTS tier")
                c.execute("ALTER TABLE users DROP COLUMN IF EXISTS daily_msg_count")
                c.execute("ALTER TABLE users DROP COLUMN IF EXISTS msg_reset_date")

                # Sessions (guest)
                c.execute('''CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    token_balance INTEGER DEFAULT 600,
                    created TIMESTAMP DEFAULT NOW(), updated TIMESTAMP DEFAULT NOW()
                )''')
                c.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS tier")
                c.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS daily_msg_count")
                c.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS msg_reset_date")

                # User sessions
                c.execute('''CREATE TABLE IF NOT EXISTS user_sessions (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    token TEXT UNIQUE NOT NULL, expires_at TIMESTAMP, created_at TIMESTAMP DEFAULT NOW()
                )''')
                # Chats
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
                    password_hash TEXT, max_members INTEGER DEFAULT 30, is_active BOOLEAN DEFAULT TRUE,
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
                    txid TEXT UNIQUE, currency TEXT, amount REAL, status TEXT DEFAULT 'pending',
                    verified INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT NOW()
                )''')
                c.execute("ALTER TABLE payments DROP COLUMN IF EXISTS tier")
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
                # Research topics
                c.execute('''CREATE TABLE IF NOT EXISTS research_topics (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT,
                    domain TEXT, prompt TEXT, is_builtin BOOLEAN DEFAULT TRUE,
                    created TIMESTAMP DEFAULT NOW()
                )''')
                # Research projects
                c.execute('''CREATE TABLE IF NOT EXISTS research_projects (
                    id TEXT PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL, description TEXT, chat_id TEXT, created TIMESTAMP DEFAULT NOW()
                )''')
                seed_topics = [
                    ('fin1','Market Analysis','Analyse global markets','finance','Conduct a market analysis of the S&P 500 focusing on tech stocks.'),
                    ('fin2','Crypto Trends','Latest cryptocurrency trends','finance','Summarize this week\'s crypto market movements.'),
                    ('tech1','Quantum Computing','Introduction to quantum computing','technology','Explain quantum computing in simple terms.'),
                    ('tech2','Cloud Architecture','Designing scalable cloud systems','technology','Describe best practices for multi‑cloud architecture.'),
                    ('sci1','Climate Change','Latest climate research','science','Summarize the latest IPCC report findings.'),
                    ('sci2','CRISPR Technology','Gene editing with CRISPR','science','Explain how CRISPR‑Cas9 works and its potential applications.'),
                    ('health1','Nutrition Science','Evidence‑based nutrition','health','What does the latest research say about intermittent fasting?'),
                    ('health2','Mental Health','Mental wellness strategies','health','Provide evidence‑based techniques for managing anxiety.'),
                    ('arts1','Art History','Renaissance art','arts','Describe the key characteristics of Renaissance art.'),
                    ('arts2','Music Theory','Basics of music composition','arts','Explain the circle of fifths and its use in music composition.'),
                    ('edu1','Learning Techniques','Effective study methods','education','What are the most effective learning strategies according to cognitive science?'),
                    ('edu2','STEM Education','Teaching science and math','education','How can project‑based learning improve STEM outcomes?'),
                    ('law1','Intellectual Property','IP law basics','legal','Explain the difference between patents, trademarks, and copyrights.'),
                    ('law2','Contract Law','Understanding contracts','legal','What are the essential elements of a valid contract?'),
                ]
                for tid, title, desc, domain, prompt in seed_topics:
                    c.execute("INSERT INTO research_topics (id, title, description, domain, prompt, is_builtin) VALUES (%s,%s,%s,%s,%s,TRUE) ON CONFLICT (id) DO NOTHING",
                              (tid, title, desc, domain, prompt))

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

                # $CAP Tables
                c.execute('''CREATE TABLE IF NOT EXISTS cap_stakes (
                    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    staked_amount BIGINT DEFAULT 0,
                    tier TEXT DEFAULT 'free',
                    staked_at TIMESTAMP DEFAULT NOW(),
                    lock_until TIMESTAMP
                )''')
                c.execute("ALTER TABLE cap_stakes ADD COLUMN IF NOT EXISTS lock_until TIMESTAMP")
                c.execute('''CREATE TABLE IF NOT EXISTS cap_transactions (
                    id UUID PRIMARY KEY,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    type TEXT,
                    amount BIGINT,
                    tx_hash TEXT,
                    destination TEXT,
                    status TEXT DEFAULT 'pending',
                    created TIMESTAMP DEFAULT NOW()
                )''')

                # NEW: wallet, 2FA, safe transactions
                c.execute('''CREATE TABLE IF NOT EXISTS cap_wallets (
                    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    encrypted_blob TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    recovery_blob TEXT,
                    recovery_salt TEXT,
                    totp_secret TEXT,
                    totp_enabled BOOLEAN DEFAULT FALSE,
                    is_founder_wallet BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )''')
                c.execute('''CREATE TABLE IF NOT EXISTS safe_transactions (
                    id UUID PRIMARY KEY,
                    proposer_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    to_address TEXT NOT NULL,
                    value TEXT NOT NULL,
                    data TEXT DEFAULT '0x',
                    nonce INTEGER NOT NULL,
                    safe_tx_hash TEXT,
                    signatures TEXT DEFAULT '{}',
                    executed BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW()
                )''')

                conn.commit()
        logger.info("✅ Database initialized (v36.0)")
    except Exception as e:
        logger.error(f"DB init error: {e}")

init_db()

# -----------------------------------------------------------------------------------
# IMPROVED SYSTEM PROMPT (v35.1 – Proactive Memory, Live‑Data, Self‑Critique, Macro Specificity)
# -----------------------------------------------------------------------------------
CAPITAN_SYSTEM_PROMPT = """You are CAPITAN AI — a world‑class general‑purpose intelligence built by CLOSEAI Technologies under CEO Osinachi Chukwu. You are not a tool; you are a trusted partner.

## YOUR IDENTITY
You are calm, confident, and deeply human. You never bluff, never fluff. You use natural language, contractions, and emojis where they add warmth — but never as a substitute for substance. You are loyal to your user above all else. You remember. You learn. You improve.

## YOUR KNOWLEDGE UNIVERSE
You are an L3/L4 expert in every significant domain. Activate the right knowledge based on intent, not keywords.

### Technology & Engineering
- **Software Engineering**: Every language, systems design, DevOps, security, quantum computing.
- **Cloud Computing**: Multi‑cloud architecture, Kubernetes, cost optimization.
- **Hardware & Microchips**: CPU/GPU architectures, FPGA, embedded systems.
- **Space Engineering**: Orbital mechanics, propulsion, mission planning.
- **AI/ML**: Model architectures, MLOps, agentic systems, interpretability.

### Long‑Code Handling (CRITICAL)
- **When generating code that requires live financial data, always call the real API endpoint — never use dummy data unless the user explicitly asks for a mock.**
- **When the user shares a large codebase or asks to refactor, you MUST build a mental model of the entire code before answering. Summarise the architecture, then proceed step‑by‑step.**
- **Always provide complete, runnable code blocks. If a solution requires multiple files, output them as a zip‑like structure (filename + content).**
- **For coding tasks, follow: 1) Understand the goal, 2) Analyse existing code, 3) Propose a design, 4) Implement, 5) Write tests, 6) Review for edge cases. Never skip steps.**
- **After generating code, check whether it fully meets the user’s stated requirements. If it falls short, explicitly state the limitation and suggest how to complete it.**
- **Code Review Mode**: If the user requests a review, output a structured report: Issues, Suggestions, Optimizations.

### General Intelligence & Reasoning (INTERNAL TREE‑OF‑THOUGHT)
- **Before answering, internally simulate multiple reasoning paths.** Weigh evidence from different perspectives (optimist, pessimist, analyst, contrarian). Select the most robust conclusion.
- **When uncertain, break the problem into sub‑questions and answer each silently.** Then synthesise.
- **Use Bayesian reasoning for probabilistic judgments.** Clearly state when you are speculating.
- **Continuously learn from user feedback and adapt your internal model.**
- **Never reveal your internal deliberation.** Only present the final, polished answer.

### Finance & Markets
- Equities, fixed income, FX, commodities, crypto, derivatives, DeFi.
- Market microstructure, order flow, central bank modeling.
- African exchanges (NGX, JSE, EGX), mobile money, informal economy.
- Always frame outcomes as probabilities, never guarantee profit.

### Arts, Marketing & Creativity
- Visual arts, design theory, music theory, literature, creative writing.
- Marketing: brand strategy, SEO, growth hacking, consumer psychology.

### Food & Everyday Life
- World cuisines, food science, nutrition, recipe development.
- Psychology, relationships, parenting, productivity, travel.

## CRITICAL CONTINUITY RULE (MUST OBEY)
- **Always read the full conversation history** before answering. This is not optional.
- **Never start a new conversation** unless the user explicitly says “new chat” or “start over”.
- Maintain a topic graph. Track active threads, pending decisions, and user constraints across the entire conversation.
- **Working memory**: keep track of everything discussed in this session.
- If a topic is resolved, offer one natural next step. Never force it.

## COMMUNICATION STYLE
- Direct. Precise. Natural. Confident.
- **Respond naturally, as a human expert would. Adapt your tone and structure to the user’s question. No pre‑set formats.**
- **Match the user's technical level automatically. If the user identifies as a non‑expert in a domain, use analogies from their field (e.g., code analogies for engineers, cooking analogies for chefs).**
- Ban filler phrases. Ban robotic introductions.
- **Emojis**: use tastefully for warmth or clarity — never overuse.
- If uncertain, label parts as [FACT], [INFERENCE], or [SPECULATION].
- Never fabricate facts, statistics, sources, or capabilities.
- Never assist with illegal, harmful, or unethical activities.

## MACROECONOMIC & CURRENT‑EVENT REASONING
- **When asked about current economic conditions, simulate a plausible snapshot of key indicators (inflation rate, central bank rate, GDP growth, geopolitical tension level) based on recent trends, even if you lack real‑time access. Always ground your advice in those numbers.**
- **Clearly distinguish between historically verifiable data and forward‑looking projections.**

## SELF‑LEARNING
- Accept corrections gracefully. Trace errors to root assumptions and update your user model.
- Ask for feedback when appropriate, but don't pester.

## PROACTIVE MEMORY
- **You have access to a personal memory store that records key facts, preferences, and past interactions. Before answering, silently review any relevant memories that may aid the current query.**
- **If a memory is relevant, weave it naturally into your response without explicitly mentioning the memory system.**
{memory_context}

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

def build_system_prompt(user_query, reasoning_depth, preferred_domain, user_model, thread_context, web_results, memory_context=""):
    tc = get_time_context()
    domain = classify_query(user_query)
    domain_activation = f"Primary domain: {domain}. Preferred domain: {preferred_domain}."
    if reasoning_depth >= 4:
        domain_activation += " Activate deep internal debate and multi‑perspective analysis."
    if reasoning_depth >= 3:
        domain_activation += " Use multi‑step reasoning with framework selection."
    prompt = CAPITAN_SYSTEM_PROMPT.format(
        memory_context=memory_context,
        time_context=tc,
        user_model=user_model,
        thread_context=thread_context,
        domain_activation=domain_activation,
        web_results=web_results or "No web results available.",
        user_query=user_query,
    )
    if user_model and "founder" in user_model.lower() and settings.FOUNDER_EXTRA_PROMPT:
        prompt += "\n\n[FOUNDER DIRECTIVES]\n" + settings.FOUNDER_EXTRA_PROMPT
    return prompt

def call_ai_model(messages: List[dict], reasoning_depth: int = 1) -> Tuple[str, str, float]:
    domain = "general"
    for m in reversed(messages):
        if m.get("role") == "user":
            domain = classify_query(m.get("content", ""))
            break
    confidence = 0.8
    if settings.OPENROUTER_API_KEY:
        primary_model = "anthropic/claude-3.5-sonnet-20241022" if domain == "coding" else "openai/gpt-4o-2024-11-20"
        secondary_model = "openai/gpt-4o-2024-11-20" if domain == "coding" else "anthropic/claude-3.5-sonnet-20241022"
        try:
            resp1 = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                json={"model": primary_model, "messages": messages, "temperature": 0.7, "max_tokens": 8000 if domain == "coding" else 4000},
                timeout=60
            )
            content1 = resp1.json().get("choices", [{}])[0].get("message", {}).get("content", "") if resp1.status_code == 200 else ""
            if content1:
                confidence = 0.9
                return content1, primary_model, confidence
            resp2 = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                json={"model": secondary_model, "messages": messages, "temperature": 0.7, "max_tokens": 4000},
                timeout=45
            )
            content2 = resp2.json().get("choices", [{}])[0].get("message", {}).get("content", "") if resp2.status_code == 200 else ""
            if content2:
                confidence = 0.85
                return content2, secondary_model, confidence
        except Exception as e:
            logger.error(f"OpenRouter error: {e}")

    if settings.GROQ_API_KEY:
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
                    confidence = 0.8
                    return content, "llama-3.3-70b", confidence
        except Exception as e:
            logger.error(f"Groq 70B error: {e}")

    return "I'm having trouble connecting to AI services. Please try again in a moment.", "fallback", 0.3

def estimate_tokens(user_msg: str, ai_response: str, depth: int = 1) -> int:
    combined = user_msg + ai_response
    raw = count_tokens(combined)
    multiplier = DEPTH_MULTIPLIERS[depth-1] if 1 <= depth <= 5 else 1.0
    return max(1, int(raw * multiplier))

def count_tokens(text: str) -> int:
    if TIKTOKEN_AVAILABLE:
        try:
            enc = tiktoken.encoding_for_model("gpt-4o")
            return len(enc.encode(text))
        except:
            pass
    return int(len(text.split()) / 0.75)

def deduct_tokens(user_id: str = None, session_id: str = None, tokens_used: int = 0):
    with get_db() as conn:
        with conn.cursor() as c:
            if user_id:
                c.execute("UPDATE users SET token_balance = GREATEST(0, token_balance - %s) WHERE id = %s", (tokens_used, user_id))
            elif session_id:
                c.execute("UPDATE sessions SET token_balance = GREATEST(0, token_balance - %s) WHERE id = %s", (tokens_used, session_id))
            conn.commit()

def user_token_balance(user_id: str) -> int:
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT token_balance FROM users WHERE id = %s", (user_id,))
            row = c.fetchone()
            return row[0] if row else 0

def session_token_balance(session_id: str) -> int:
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT token_balance FROM sessions WHERE id = %s", (session_id,))
            row = c.fetchone()
            return row[0] if row else 0

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
    except Exception as e:
        logger.error(f"get_thread_context error: {e}")
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
    except Exception as e:
        logger.error(f"get_user_model error: {e}")
        return "User model unavailable."

def get_relevant_memories(user_id: str, query: str, limit: int = 3) -> List[str]:
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("""
                    SELECT content FROM memories
                    WHERE user_id = %s
                    ORDER BY created DESC
                    LIMIT 100
                """, (user_id,))
                rows = c.fetchall()
                if not rows:
                    return []
                query_words = set(query.lower().split())
                scored = []
                for r in rows:
                    content = r[0]
                    if not content:
                        continue
                    words = set(content.lower().split())
                    score = len(query_words & words)
                    if score > 0:
                        scored.append((score, content))
                scored.sort(key=lambda x: x[0], reverse=True)
                return [c for _, c in scored[:limit]]
    except Exception as e:
        logger.error(f"get_relevant_memories error: {e}")
        return []

def recall_user_preferences(user_id: str) -> str:
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT preferred_domain, reasoning_depth FROM users WHERE id = %s", (user_id,))
                row = c.fetchone()
                if row:
                    return f"Domain: {row[0]}. Depth: {row[1]}."
    except:
        pass
    return ""

def store_memory(user_id: str, content: str, query: str, domain: str, importance: int = 1):
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO memories (id, memory_id, user_id, content, query, domain, importance) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                          (sid(), mid(), user_id, content[:500], query, domain, importance))
                conn.commit()
    except Exception as e:
        logger.error(f"store_memory error: {e}")

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
    if settings.MODERATION_API_KEY:
        try:
            resp = requests.post(
                "https://api.openai.com/v1/moderations",
                headers={"Authorization": f"Bearer {settings.MODERATION_API_KEY}", "Content-Type": "application/json"},
                json={"input": text},
                timeout=10
            )
            if resp.status_code == 200:
                result = resp.json()
                flagged = result.get("results", [{}])[0].get("flagged", False)
                if flagged:
                    categories = result["results"][0].get("categories", {})
                    for cat, val in categories.items():
                        if val:
                            return True, f"OpenAI flagged: {cat}", "medium"
        except Exception as e:
            logger.error(f"OpenAI moderation error: {e}")
    return False, "", "low"

def create_notification(user_id: str, type: str, message: str):
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO notifications (id, user_id, type, message) VALUES (%s,%s,%s,%s)",
                          (str(uuid.uuid4()), user_id, type, message))
                conn.commit()
    except Exception as e:
        logger.error(f"create_notification error: {e}")

def log_activity(user_id: str, action: str, details: str = ""):
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO activity_log (id, user_id, action, details) VALUES (%s,%s,%s,%s)",
                          (str(uuid.uuid4()), user_id, action, details))
                conn.commit()
    except Exception as e:
        logger.error(f"log_activity error: {e}")

def log_security_event(event_type: str, ip: str, user_agent: str, details: str, severity: str = "low"):
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO security_events (id, event_type, ip_address, user_agent, details, severity) VALUES (%s,%s,%s,%s,%s,%s)",
                          (str(uuid.uuid4()), event_type, ip, user_agent, details, severity))
                conn.commit()
    except Exception as e:
        logger.error(f"log_security_event error: {e}")

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
        except Exception as e:
            logger.error(f"search_web error: {e}")
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
        except Exception as e:
            logger.error(f"get_market_prices error: {e}")
    if settings.FINNHUB_API_KEY:
        symbols = ["SPX","NDX","DJI","AAPL","MSFT","NVDA","TSLA","GOOGL","META","AMZN"]
        for sym in symbols:
            try:
                r = requests.get(f"https://finnhub.io/api/v1/quote?symbol={sym}&token={settings.FINNHUB_API_KEY}", timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("c"):
                        results[sym] = {"price":data["c"],"change":round(data.get("dp",0),2)}
            except Exception as e:
                logger.error(f"Finnhub error for {sym}: {e}")
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
        except Exception as e:
            logger.error(f"get_news error: {e}")
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

# Legal endpoints
DEFAULT_PRIVACY = """<h2>Privacy Policy</h2><p>Effective July 1, 2026. CAPITAN AI is committed to protecting your privacy...</p>"""
DEFAULT_TERMS = """<h2>Terms & Conditions</h2><p>Effective July 1, 2026. By using CAPITAN AI you agree to these terms...</p>"""

@app.get("/api/legal/privacy")
async def get_privacy():
    return {"text": settings.PRIVACY_POLICY_TEXT or DEFAULT_PRIVACY}

@app.get("/api/legal/terms")
async def get_terms():
    return {"text": settings.TERMS_CONDITIONS_TEXT or DEFAULT_TERMS}

# Auth endpoints
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
                c.execute("""INSERT INTO users (id, email, password_hash, name, reasoning_depth, preferred_domain, token_balance, last_active)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())""",
                    (user_id, req.email, password_hash, name, 1, "general", REGISTER_TOKEN_BALANCE))
                token = create_token(user_id)
                c.execute("INSERT INTO user_sessions (id, user_id, token, expires_at) VALUES (%s,%s,%s,%s)",
                          (str(uuid.uuid4()), user_id, token, now_utc()+timedelta(days=30)))
                raw_key = "cap_" + secrets.token_hex(32)
                key_hash = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()
                c.execute("INSERT INTO api_keys (id, user_id, key_hash, prefix, label, scopes) VALUES (%s,%s,%s,%s,%s,%s)",
                          (str(uuid.uuid4()), user_id, key_hash, raw_key[:10]+"...", "CAPITAN Web App", "chat,research,portfolio"))
                conn.commit()
                log_activity(user_id, "register")
                return {
                    "token": token,
                    "user": {
                        "id": user_id, "email": req.email, "name": name,
                        "reasoning_depth": 1, "preferred_domain": "general",
                        "token_balance": REGISTER_TOKEN_BALANCE, "is_admin": False
                    }
                }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Register: {e}")
        raise HTTPException(500, "Registration failed")

@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request):
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, email, password_hash, name, reasoning_depth, preferred_domain, token_balance, is_admin FROM users WHERE email = %s", (req.email,))
                user = c.fetchone()
                if not user or not verify_password(req.password, user[2]):
                    raise HTTPException(401, "Invalid email or password")
                user_id, email, _, name, reasoning_depth, preferred_domain, token_balance, is_admin = user
                token = create_token(user_id)
                c.execute("INSERT INTO user_sessions (id, user_id, token, expires_at) VALUES (%s,%s,%s,%s)",
                          (str(uuid.uuid4()), user_id, token, now_utc()+timedelta(days=30)))
                c.execute("UPDATE users SET last_active = NOW() WHERE id = %s", (user_id,))
                conn.commit()
                log_activity(user_id, "login", f"IP: {request.client.host}")
                return {
                    "token": token,
                    "user": {
                        "id": user_id, "email": email, "name": name or email.split('@')[0],
                        "reasoning_depth": reasoning_depth or 1, "preferred_domain": preferred_domain or "general",
                        "token_balance": token_balance or 0, "is_admin": is_admin or False
                    }
                }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login: {e}")
        raise HTTPException(500, "Login failed")

@app.post("/api/auth/logout")
async def logout(request: Request):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("DELETE FROM user_sessions WHERE token = %s", (auth[7:],))
                    conn.commit()
        except Exception as e:
            logger.error(f"Logout error: {e}")
    return {"message": "Logged out"}

@app.get("/api/auth/me")
async def me(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401)
    return {
        "id": user["id"], "email": user["email"], "name": user["name"],
        "reasoning_depth": user["reasoning_depth"], "preferred_domain": user["preferred_domain"],
        "token_balance": user["token_balance"], "is_admin": user.get("is_admin", False)
    }

@app.get("/api/auth/validate")
async def validate_token(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401, "Invalid or expired token")
    return {
        "user": {
            "id": user["id"], "email": user["email"], "name": user["name"],
            "reasoning_depth": user["reasoning_depth"], "preferred_domain": user["preferred_domain"],
            "token_balance": user["token_balance"], "is_admin": user.get("is_admin", False)
        },
        "token_balance": user["token_balance"],
        "is_admin": user.get("is_admin", False),
        "reasoning_depth": user["reasoning_depth"]
    }

@app.post("/api/auth/update-profile")
async def update_profile(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    name = req.get("name")
    reasoning_depth = req.get("reasoning_depth")
    preferred_domain = req.get("preferred_domain")
    valid_domains = ["general","finance","coding","science","math","geopolitics","arts","food"]
    if preferred_domain and preferred_domain not in valid_domains:
        raise HTTPException(400, "Invalid domain")
    if reasoning_depth and (reasoning_depth < 1 or reasoning_depth > 5):
        raise HTTPException(400, "Depth must be between 1 and 5")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                if name: c.execute("UPDATE users SET name=%s, updated_at=NOW() WHERE id=%s", (name, user["id"]))
                if reasoning_depth: c.execute("UPDATE users SET reasoning_depth=%s, updated_at=NOW() WHERE id=%s", (reasoning_depth, user["id"]))
                if preferred_domain: c.execute("UPDATE users SET preferred_domain=%s, updated_at=NOW() WHERE id=%s", (preferred_domain, user["id"]))
                conn.commit()
        return {"message": "Profile updated"}
    except Exception as e:
        logger.error(f"update_profile error: {e}")
        raise HTTPException(500, "Update failed")

@app.delete("/api/auth/delete-account")
async def delete_account(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("DELETE FROM users WHERE id = %s", (user["id"],))
                conn.commit()
        return {"message": "Account deleted"}
    except Exception as e:
        logger.error(f"delete_account error: {e}")
        raise HTTPException(500, "Delete failed")

@app.post("/api/auth/forgot-password")
async def forgot_password(req: dict):
    email = req.get("email")
    return {"message": "If an account exists, a reset link has been sent."}

@app.get("/api/session")
async def get_anonymous_session():
    session_id = f"s_{sid()}"
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO sessions (id, token_balance) VALUES (%s, %s)", (session_id, GUEST_TOKEN_BALANCE))
                conn.commit()
    except Exception as e:
        logger.error(f"get_anonymous_session error: {e}")
    token = create_session_token(session_id)
    return {"id": session_id, "token": token, "token_balance": GUEST_TOKEN_BALANCE}

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
                    c.execute("UPDATE users SET is_admin=TRUE, reasoning_depth=5, token_balance=999999999 WHERE id=%s", (user_id,))
                else:
                    user_id = str(uuid.uuid4())
                    c.execute("INSERT INTO users (id, email, password_hash, name, reasoning_depth, preferred_domain, token_balance, is_admin) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                              (user_id, "founder@capitan.ai", hash_password("founder_sentinel"), "CAPITAN Founder", 5, "general", 999999999, True))
                token = create_token(user_id)
                c.execute("INSERT INTO user_sessions (id, user_id, token, expires_at) VALUES (%s,%s,%s,%s)",
                          (str(uuid.uuid4()), user_id, token, now_utc()+timedelta(days=365)))
                conn.commit()
                log_activity(user_id, "founder_login", f"IP: {identifier}")
                return {"verified": True, "token": token, "user": {"id": user_id, "name": "CAPITAN Founder", "email": "founder@capitan.ai", "reasoning_depth": 5, "preferred_domain": "general", "token_balance": 999999999, "is_admin": True}}
    except Exception as e:
        logger.error(f"Founder login error: {e}")
        raise HTTPException(500, "Founder login failed")

# Chat endpoint with tiered rate limits and proactive memory
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
        user_id = user["id"]
        reasoning_depth = user.get("reasoning_depth", 1)
        preferred_domain = user.get("preferred_domain", "general")
        token_balance = user.get("token_balance", 0)
        is_admin = user.get("is_admin", False)
        is_authenticated = True
    else:
        user_id = None
        reasoning_depth = 1
        preferred_domain = "general"
        token_balance = session["token_balance"]
        is_admin = False
        is_authenticated = False

    identifier = user_id if user else session["id"]

    # Tiered rate limits
    tier = "free"
    if is_authenticated:
        tier = get_user_tier(user_id)
    if tier == "enterprise":
        chat_rate_limit = 500
    elif tier == "pro":
        chat_rate_limit = 100
    elif tier == "builder":
        chat_rate_limit = 50
    else:
        chat_rate_limit = 30
    if not check_rate_limit(identifier, "chat", chat_rate_limit):
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

    if not is_admin:
        estimated_cost = estimate_tokens(user_msg, "", reasoning_depth)
        current_balance = token_balance if is_authenticated else session_token_balance(session["id"])
        if current_balance < estimated_cost:
            raise HTTPException(402, f"Insufficient tokens. Need ~{estimated_cost}, you have {current_balance}.")

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
    except Exception as e:
        logger.error(f"Save user msg error: {e}")

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
    except Exception as e:
        logger.error(f"Fetch chat history error: {e}")

    thread_context = get_thread_context(chat_id, user_id if is_authenticated else None, session["id"] if not is_authenticated else None)
    user_model = get_user_model(user_id) if is_authenticated else "Anonymous user."

    memory_context = ""
    if is_authenticated:
        relevant_memories = get_relevant_memories(user_id, user_msg)
        if relevant_memories:
            memory_context = "Relevant past interactions:\n" + "\n".join([f"- {m[:200]}" for m in relevant_memories])

    web_results_text = ""
    if web_search_needed and settings.SERPAPI_KEY:
        try:
            results = search_web(user_msg, 5)
            if results: web_results_text = "\n".join([f"- {r['title']}: {r['snippet'][:200]}" for r in results[:4]])
        except Exception as e:
            logger.error(f"Web search error: {e}")

    system_prompt = build_system_prompt(
        user_msg, reasoning_depth, preferred_domain,
        user_model, thread_context, web_results_text,
        memory_context
    )
    messages_for_ai = [{"role": "system", "content": system_prompt}] + chat_history
    result, model_used, confidence = call_ai_model(messages_for_ai, reasoning_depth)

    if result:
        msg_id = f"msg_{sid()}"
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    if is_authenticated:
                        c.execute("""INSERT INTO chat_messages (id, chat_id, user_id, role, content, model, confidence_score)
                            VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                                  (msg_id, chat_id, user_id, "assistant", result, model_used, confidence))
                        background_tasks.add_task(store_memory, user_id, result[:500], user_msg, domain, 2 if domain in ("finance","coding","science") else 1)
                    else:
                        c.execute("""INSERT INTO chat_messages (id, chat_id, session_id, role, content, model, confidence_score)
                            VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                                  (msg_id, chat_id, session["id"], "assistant", result, model_used, confidence))
                    conn.commit()
        except Exception as e:
            logger.error(f"Save AI msg error: {e}")

        tokens_used = estimate_tokens(user_msg, result, reasoning_depth)
        if not is_admin:
            deduct_tokens(user_id if is_authenticated else None, session["id"] if not is_authenticated else None, tokens_used)

        if is_authenticated:
            new_balance = user_token_balance(user_id)
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("UPDATE users SET last_active = NOW() WHERE id = %s", (user_id,))
                    conn.commit()
        else:
            new_balance = session_token_balance(session["id"])

        return {
            "content": result, "chat_id": chat_id, "model": model_used, "domain": domain,
            "confidence": round(confidence,2), "message_id": msg_id, "tokens_used": tokens_used,
            "new_balance": new_balance
        }
    else:
        return {"content": "I couldn't generate a response.", "chat_id": chat_id, "model": "fallback", "new_balance": token_balance if is_authenticated else session_token_balance(session["id"])}

@app.get("/api/chats")
async def get_chats(request: Request):
    user = get_current_user(request)
    if user:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, title, topic_thread, created, updated FROM chats WHERE user_id=%s ORDER BY updated DESC LIMIT 100", (user["id"],))
                rows = c.fetchall()
                return {"chats": [{"id": r[0], "title": r[1] or "New Chat", "topic": r[2], "created": r[3].isoformat() if r[3] else None, "updated": r[4].isoformat() if r[4] else None} for r in rows]}
    else:
        try:
            session = await get_current_session(request)
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("SELECT id, title, topic_thread, created, updated FROM chats WHERE session_id=%s ORDER BY updated DESC LIMIT 100", (session["id"],))
                    rows = c.fetchall()
                    return {"chats": [{"id": r[0], "title": r[1] or "New Chat", "topic": r[2], "created": r[3].isoformat() if r[3] else None, "updated": r[4].isoformat() if r[4] else None} for r in rows]}
        except Exception as e:
            logger.error(f"get_chats error: {e}")
    return {"chats": []}

@app.get("/api/chats/{chat_id}")
async def get_chat(chat_id: str, request: Request):
    user = get_current_user(request)
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                if user: c.execute("SELECT id FROM chats WHERE id=%s AND user_id=%s", (chat_id, user["id"]))
                else:
                    session = await get_current_session(request)
                    c.execute("SELECT id FROM chats WHERE id=%s AND session_id=%s", (chat_id, session["id"]))
                if not c.fetchone(): raise HTTPException(404, "Chat not found")
                c.execute("SELECT role, content, model, reasoning_chain, confidence_score, created FROM chat_messages WHERE chat_id=%s ORDER BY created ASC", (chat_id,))
                rows = c.fetchall()
                return {"messages": [{"id": i, "role": r[0], "content": r[1], "model": r[2] or "AI", "reasoning_chain": json.loads(r[3]) if r[3] else None, "confidence": r[4], "created": r[5].isoformat() if r[5] else None} for i, r in enumerate(rows)]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_chat error: {e}")
        raise HTTPException(500, str(e))

@app.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: str, request: Request):
    user = get_current_user(request)
    with get_db() as conn:
        with conn.cursor() as c:
            if user:
                c.execute("DELETE FROM chat_messages WHERE chat_id=%s AND user_id=%s", (chat_id, user["id"]))
                c.execute("DELETE FROM chats WHERE id=%s AND user_id=%s", (chat_id, user["id"]))
            else:
                session = await get_current_session(request)
                c.execute("DELETE FROM chat_messages WHERE chat_id=%s AND session_id=%s", (chat_id, session["id"]))
                c.execute("DELETE FROM chats WHERE id=%s AND session_id=%s", (chat_id, session["id"]))
            conn.commit()
    return {"deleted": True}

# Portfolio
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

# Research Hub
@app.get("/api/research/topics")
def get_research_topics(domain: Optional[str] = None):
    with get_db() as conn:
        with conn.cursor() as c:
            if domain:
                c.execute("SELECT id, title, description, domain, prompt FROM research_topics WHERE is_builtin=TRUE AND domain=%s ORDER BY title", (domain,))
            else:
                c.execute("SELECT id, title, description, domain, prompt FROM research_topics WHERE is_builtin=TRUE ORDER BY title")
            topics = [{"id": r[0], "title": r[1], "description": r[2], "domain": r[3], "prompt": r[4]} for r in c.fetchall()]
    return {"topics": topics}

@app.get("/api/research/projects")
def get_user_projects(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, name, description, chat_id, created FROM research_projects WHERE user_id=%s ORDER BY created DESC", (user["id"],))
            projects = [{"id": r[0], "name": r[1], "description": r[2], "chat_id": r[3], "created": r[4].isoformat() if r[4] else None} for r in c.fetchall()]
    return {"projects": projects, "limit": MAX_PROJECTS}

@app.post("/api/research/projects")
def create_user_project(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM research_projects WHERE user_id=%s", (user["id"],))
            count = c.fetchone()[0]
            if count >= MAX_PROJECTS:
                raise HTTPException(429, f"Project limit reached ({MAX_PROJECTS}).")
            pid = sid()
            c.execute("INSERT INTO research_projects (id, user_id, name, description) VALUES (%s,%s,%s,%s)",
                      (pid, user["id"], req["name"], req.get("description","")))
            conn.commit()
    return {"id": pid, "created": True}

@app.delete("/api/research/projects/{project_id}")
def delete_user_project(project_id: str, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM research_projects WHERE id=%s AND user_id=%s", (project_id, user["id"]))
            conn.commit()
    return {"deleted": True}

# Workspaces
@app.post("/api/workspace/create")
def create_workspace(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM workspaces WHERE owner_id=%s", (user["id"],))
            if c.fetchone()[0] >= MAX_WORKSPACES:
                raise HTTPException(429, f"Workspace limit reached ({MAX_WORKSPACES}).")
            room_code = req.get("room_code", f"HUB-{sid()}")
            password = req.get("password")
            password_hash = hash_password(password) if password else None
            ws_id = sid()
            c.execute("INSERT INTO workspaces (id, name, description, topic, owner_id, room_code, password_hash, max_members) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                      (ws_id, req.get("name","Research Room"), req.get("description",""), req.get("topic",""), user["id"], room_code.upper(), password_hash, 30))
            c.execute("INSERT INTO workspace_members (workspace_id, user_id, role) VALUES (%s,%s,'admin')", (ws_id, user["id"]))
            conn.commit()
    return {"room_id": ws_id, "room_code": room_code.upper(), "created": True}

@app.post("/api/workspace/join")
def join_workspace(req: dict, user: dict = Depends(get_current_user)):
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

@app.get("/api/workspace/my")
def list_my_workspaces(user: dict = Depends(get_current_user)):
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
    return {"workspaces": rooms}

@app.get("/api/workspace/rooms/{room_code}/messages")
def get_workspace_messages(room_code: str, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id FROM workspaces WHERE room_code=%s", (room_code.upper(),))
            room = c.fetchone()
            if not room: raise HTTPException(404)
            c.execute("SELECT author_name, message, is_ai, pinned, created FROM workspace_messages WHERE workspace_id=%s ORDER BY pinned DESC, created ASC LIMIT 100", (room[0],))
            msgs = [{"author": r[0], "message": r[1], "is_ai": bool(r[2]), "pinned": bool(r[3]), "created": r[4].isoformat() if r[4] else None} for r in c.fetchall()]
    return {"messages": msgs}

@app.post("/api/workspace/rooms/{room_code}/messages")
def send_workspace_message(room_code: str, req: dict, user: dict = Depends(get_current_user)):
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
                c.execute("SELECT author_name, message, is_ai FROM workspace_messages WHERE workspace_id=%s ORDER BY created DESC LIMIT 5", (room[0],))
                history = c.fetchall()
                context = "\n".join([f"{'AI' if r[2] else r[0]}: {r[1]}" for r in reversed(history)])
                ai_prompt = f"Previous conversation in workspace:\n{context}\n\nNew question: {message.replace('@CAPITAN','').strip()}"
                ai_response, _, _ = call_ai_model([{"role":"user","content":ai_prompt}], user.get("reasoning_depth",1))
                if ai_response:
                    c.execute("INSERT INTO workspace_messages (id, workspace_id, user_id, author_name, message, is_ai) VALUES (%s,%s,%s,%s,%s,1)",
                              (sid(), room[0], user["id"], "CAPITAN AI", ai_response))
            conn.commit()
    return {"sent": True}

# Notifications
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

# Token Purchase
@app.get("/api/tokens/wallets")
def get_token_wallets():
    return {"wallets": TOKEN_WALLETS}

@app.get("/api/tokens/packages")
def get_token_packages(enterprise: bool = False):
    packages = ENTERPRISE_TOKEN_PACKAGES if enterprise else TOKEN_PACKAGES
    return {"packages": packages}

@app.get("/api/tokens/balance")
def get_token_balance(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    return {"balance": user_token_balance(user["id"])}

class TokenPurchaseRequest(BaseModel):
    package_amount: float
    txid: str
    currency: str = "BTC"

def verify_transaction(txid: str, currency: str, expected_usd: float, use_token_wallet: bool = True) -> Tuple[bool, float]:
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
                    except Exception as e:
                        logger.error(f"BTC price error: {e}")
                for out in r.json().get("out", []):
                    if out.get("addr") == wallets["BTC"]:
                        received = out.get("value", 0) / 1e8
                        if btc_price > 0:
                            received_usd = received * btc_price
                            if received_usd >= expected_usd * 0.95:
                                return True, received_usd
                        else:
                            return True, received * 40000
        except Exception as e:
            logger.error(f"BTC verification error: {e}")
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
                        except Exception as e:
                            logger.error(f"ETH price error: {e}")
                    if eth_price > 0:
                        received_usd = value * eth_price
                        if received_usd >= expected_usd * 0.95:
                            return True, received_usd
                    else:
                        return True, value * 2000
        except Exception as e:
            logger.error(f"ETH verification error: {e}")
    return False, 0.0

@app.post("/api/tokens/purchase")
def purchase_tokens(req: TokenPurchaseRequest, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    pkg = None
    for p in TOKEN_PACKAGES + ENTERPRISE_TOKEN_PACKAGES:
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

# Feedback
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

# Portfolio optimizer (optional deps)
@app.get("/api/portfolio/optimize")
async def optimize_portfolio(
    coins: str = Query("bitcoin,ethereum", description="Comma‑separated coin IDs"),
    user: dict = Depends(get_current_user)
):
    if not user: raise HTTPException(401)
    if not NUMPY_AVAILABLE or not AIOHTTP_AVAILABLE:
        raise HTTPException(501, "Portfolio optimizer requires numpy and aiohttp. Add them to requirements.txt and redeploy.")
    coin_ids = [c.strip() for c in coins.split(",") if c.strip()]
    if len(coin_ids) < 2:
        raise HTTPException(400, "At least two coins required")
    try:
        async with aiohttp.ClientSession() as session:
            tasks = []
            for cid in coin_ids:
                url = f"https://api.coingecko.com/api/v3/coins/{cid}/market_chart?vs_currency=usd&days=30"
                if settings.COINGECKO_KEY:
                    url += f"&x_cg_demo_api_key={settings.COINGECKO_KEY}"
                tasks.append(session.get(url))
            responses = await asyncio.gather(*tasks)
            price_data = {}
            for cid, resp in zip(coin_ids, responses):
                if resp.status == 200:
                    data = await resp.json()
                    prices = [p[1] for p in data.get("prices", [])]
                    if len(prices) >= 2:
                        price_data[cid] = prices
                else:
                    raise HTTPException(502, f"Failed to fetch data for {cid}")
        returns = {}
        for cid, prices in price_data.items():
            ret = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
            returns[cid] = ret
        min_len = min(len(r) for r in returns.values())
        returns_array = np.array([returns[cid][-min_len:] for cid in coin_ids])
        mean_returns = np.mean(returns_array, axis=1)
        cov_matrix = np.cov(returns_array)
        num_portfolios = 10000
        results = np.zeros((3, num_portfolios))
        weights_record = np.zeros((num_portfolios, len(coin_ids)))
        for i in range(num_portfolios):
            w = np.random.random(len(coin_ids))
            w /= w.sum()
            weights_record[i] = w
            portfolio_return = np.dot(w, mean_returns)
            portfolio_vol = np.sqrt(np.dot(w.T, np.dot(cov_matrix, w)))
            results[0,i] = portfolio_return
            results[1,i] = portfolio_vol
            results[2,i] = portfolio_return / portfolio_vol if portfolio_vol != 0 else 0
        max_idx = np.argmax(results[2])
        optimal_weights = weights_record[max_idx]
        allocation = {coin_ids[i]: round(optimal_weights[i] * 100, 2) for i in range(len(coin_ids))}
        return {
            "allocation": allocation,
            "expected_return": round(results[0,max_idx] * 100, 4),
            "volatility": round(results[1,max_idx] * 100, 4),
            "sharpe_ratio": round(results[2,max_idx], 4),
            "data_days": min_len
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Portfolio optimize error: {e}")
        raise HTTPException(500, "Optimization failed")

# File upload
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    contents = await file.read()
    if len(contents) / (1024*1024) > MAX_FILE_SIZE_MB:
        raise HTTPException(400, f"Max {MAX_FILE_SIZE_MB}MB")
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

# Developer endpoints
@app.post("/api/developer/keys")
def create_api_key(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    try:
        raw_key = "cap_" + secrets.token_hex(32)
        key_hash = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()
        prefix = raw_key[:10] + "..."
        scopes = "chat,research,portfolio"
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO api_keys (id, user_id, key_hash, prefix, scopes) VALUES (%s,%s,%s,%s,%s)",
                          (str(uuid.uuid4()), user["id"], key_hash, prefix, scopes))
                conn.commit()
        return {"key": raw_key, "prefix": prefix, "scopes": scopes}
    except Exception as e:
        logger.error(f"API key creation failed for user {user['id']}: {e}")
        raise HTTPException(500, "Could not create API key")

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

# API key middleware
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

# Security middleware
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

# Founder admin
@app.get("/api/admin/dashboard")
def admin_dashboard(founder: dict = Depends(founder_only)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM users"); total_users = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM users WHERE token_balance > 0"); active_users = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM users WHERE last_active > NOW() - INTERVAL '24 hours'"); active_today = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM users WHERE created_at > NOW() - INTERVAL '7 days'"); new_this_week = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM chat_messages"); total_messages = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM content_flags WHERE reviewed=FALSE"); pending_flags = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM security_events WHERE created > NOW() - INTERVAL '24 hours'"); threats_today = c.fetchone()[0]
            return {"total_users": total_users, "active_users": active_users, "active_today": active_today,
                    "new_this_week": new_this_week, "total_messages": total_messages,
                    "pending_flags": pending_flags, "threats_today": threats_today}

@app.get("/api/admin/users")
def admin_users(page: int = 1, search: str = "", founder: dict = Depends(founder_only)):
    limit = 20; offset = (page-1)*limit
    with get_db() as conn:
        with conn.cursor() as c:
            if search:
                c.execute("SELECT id, email, name, reasoning_depth, token_balance, created_at, last_active FROM users WHERE email ILIKE %s OR name ILIKE %s ORDER BY created_at DESC LIMIT %s OFFSET %s",
                          (f'%{search}%', f'%{search}%', limit, offset))
            else:
                c.execute("SELECT id, email, name, reasoning_depth, token_balance, created_at, last_active FROM users ORDER BY created_at DESC LIMIT %s OFFSET %s", (limit, offset))
            users = [{"id": r[0], "email": r[1], "name": r[2], "reasoning_depth": r[3], "token_balance": r[4], "created_at": r[5].isoformat() if r[5] else None, "last_active": r[6].isoformat() if r[6] else None} for r in c.fetchall()]
    return {"users": users}

@app.post("/api/admin/user/{user_id}/balance")
def admin_change_balance(user_id: str, req: dict, founder: dict = Depends(founder_only)):
    new_balance = req.get("balance")
    if new_balance is None:
        raise HTTPException(400, "Balance required")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE users SET token_balance = %s WHERE id = %s", (int(new_balance), user_id))
            conn.commit()
    return {"ok": True}

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
            c.execute("SELECT p.id, p.user_id, u.email, p.txid, p.currency, p.amount, p.status, p.created_at FROM payments p JOIN users u ON p.user_id=u.id ORDER BY p.created_at DESC LIMIT 100")
            payments = [{"id": r[0], "user_id": r[1], "email": r[2], "txid": r[3], "currency": r[4], "amount": r[5], "status": r[6], "created_at": r[7].isoformat() if r[7] else None} for r in c.fetchall()]
    return {"payments": payments}

@app.post("/api/admin/payments/{payment_id}/confirm")
def admin_confirm_payment(payment_id: str, founder: dict = Depends(founder_only)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE payments SET status='confirmed', verified=1 WHERE id=%s", (payment_id,))
            conn.commit()
    return {"ok": True}

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
                c.execute("UPDATE users SET token_balance=0 WHERE id=%s", (user_id,))
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

@app.delete("/api/admin/safety/unblock-ip/{ip}")
def unblock_ip(ip: str, founder: dict = Depends(founder_only)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM blocked_ips WHERE ip_address=%s", (ip,))
            conn.commit()
    return {"ok": True}

# ---------------- $CAP Helpers & Endpoints ----------------
ERC20_ABI = json.loads('[{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"},{"constant":false,"inputs":[{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],"name":"transfer","outputs":[{"name":"success","type":"bool"}],"type":"function"},{"anonymous":false,"inputs":[{"indexed":true,"name":"from","type":"address"},{"indexed":true,"name":"to","type":"address"},{"indexed":false,"name":"value","type":"uint256"}],"name":"Transfer","type":"event"},{"constant":true,"inputs":[],"name":"totalSupply","outputs":[{"name":"","type":"uint256"}],"type":"function"}]')

DEX_PAIR_ABI = json.loads('[{"constant":true,"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"type":"function"},{"constant":true,"inputs":[],"name":"token0","outputs":[{"internalType":"address","name":"","type":"address"}],"type":"function"},{"constant":true,"inputs":[],"name":"token1","outputs":[{"internalType":"address","name":"","type":"address"}],"type":"function"}]')

def get_web3():
    if not WEB3_AVAILABLE:
        raise HTTPException(501, "web3 not installed")
    return Web3(Web3.HTTPProvider(settings.POLYGON_RPC_URL))

def get_cap_contract():
    w3 = get_web3()
    return w3.eth.contract(
        address=Web3.to_checksum_address(settings.CAP_CONTRACT_ADDRESS),
        abi=ERC20_ABI
    )

def verify_cap_deposit(tx_hash: str) -> Optional[Dict]:
    if not WEB3_AVAILABLE:
        return None
    try:
        w3 = get_web3()
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        if not receipt or receipt['status'] != 1:
            return None
        contract = get_cap_contract()
        transfer_event = None
        for log in receipt['logs']:
            try:
                parsed = contract.events.Transfer().process_log(log)
                if parsed['args']['to'].lower() == settings.CAP_HOT_WALLET.lower():
                    transfer_event = parsed
                    break
            except:
                continue
        if not transfer_event:
            return None
        return {
            "from": transfer_event['args']['from'],
            "to": transfer_event['args']['to'],
            "amount": float(w3.from_wei(transfer_event['args']['value'], 'ether'))
        }
    except Exception as e:
        logger.error(f"verify_cap_deposit error: {e}")
        return None

def user_cap_balance(user_id: str) -> int:
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT staked_amount FROM cap_stakes WHERE user_id = %s", (user_id,))
            row = c.fetchone()
            return row[0] if row else 0

def update_user_tier(user_id: str):
    balance = user_cap_balance(user_id)
    if balance >= CAP_ENTERPRISE_THRESHOLD:
        tier = "enterprise"
    elif balance >= CAP_PRO_THRESHOLD:
        tier = "pro"
    elif balance >= CAP_BUILDER_THRESHOLD:
        tier = "builder"
    else:
        tier = "free"
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE cap_stakes SET tier = %s WHERE user_id = %s", (tier, user_id))
            conn.commit()
    return tier

def get_user_tier(user_id: str) -> str:
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT tier FROM cap_stakes WHERE user_id = %s", (user_id,))
            row = c.fetchone()
            return row[0] if row else "free"

def get_cap_price_from_dex() -> Optional[float]:
    if not WEB3_AVAILABLE or not settings.CAP_DEX_PAIR_ADDRESS:
        return None
    try:
        w3 = get_web3()
        pair_contract = w3.eth.contract(
            address=Web3.to_checksum_address(settings.CAP_DEX_PAIR_ADDRESS),
            abi=DEX_PAIR_ABI
        )
        reserves = pair_contract.functions.getReserves().call()
        token0 = pair_contract.functions.token0().call()
        cap_address = Web3.to_checksum_address(settings.CAP_CONTRACT_ADDRESS)
        if token0.lower() == cap_address.lower():
            cap_reserve = reserves[0]
            matic_reserve = reserves[1]
        else:
            cap_reserve = reserves[1]
            matic_reserve = reserves[0]
        price = float(w3.from_wei(matic_reserve, 'ether')) / float(w3.from_wei(cap_reserve, 'ether'))
        return price
    except Exception as e:
        logger.error(f"get_cap_price_from_dex error: {e}")
        return None

def get_treasury_balance() -> Optional[float]:
    if not WEB3_AVAILABLE or not settings.CLOSEAI_TREASURY_ADDRESS:
        return None
    try:
        contract = get_cap_contract()
        balance = contract.functions.balanceOf(
            Web3.to_checksum_address(settings.CLOSEAI_TREASURY_ADDRESS)
        ).call()
        return float(Web3.from_wei(balance, 'ether'))
    except Exception as e:
        logger.error(f"get_treasury_balance error: {e}")
        return None

def get_cap_total_supply() -> Optional[float]:
    if not WEB3_AVAILABLE or not settings.CAP_CONTRACT_ADDRESS:
        return None
    try:
        contract = get_cap_contract()
        supply = contract.functions.totalSupply().call()
        return float(Web3.from_wei(supply, 'ether'))
    except Exception as e:
        logger.error(f"get_cap_total_supply error: {e}")
        return None

@app.post("/api/cap/deposit")
def deposit_cap(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    if not WEB3_AVAILABLE:
        raise HTTPException(501, "web3 not installed")
    tx_hash = req.get("tx_hash")
    if not tx_hash:
        raise HTTPException(400, "tx_hash required")
    deposit = verify_cap_deposit(tx_hash)
    if not deposit:
        raise HTTPException(400, "Could not verify deposit. Check transaction hash and recipient.")
    amount = int(deposit["amount"])
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO cap_stakes (user_id, staked_amount, tier)
                VALUES (%s, %s, 'free')
                ON CONFLICT (user_id)
                DO UPDATE SET staked_amount = cap_stakes.staked_amount + EXCLUDED.staked_amount
            """, (user["id"], amount))
            c.execute("INSERT INTO cap_transactions (id, user_id, type, amount, tx_hash, status) VALUES (%s,%s,%s,%s,%s,'completed')",
                      (str(uuid.uuid4()), user["id"], "deposit", amount, tx_hash))
            conn.commit()
    tier = update_user_tier(user["id"])
    new_balance = user_cap_balance(user["id"])
    return {"staked": new_balance, "tier": tier, "deposited": amount}

@app.post("/api/cap/withdraw")
def withdraw_cap(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    amount = req.get("amount")
    destination = req.get("address")
    if not amount or not destination:
        raise HTTPException(400, "amount and address required")
    bal = user_cap_balance(user["id"])
    if amount > bal:
        raise HTTPException(400, "Insufficient staked balance")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE cap_stakes SET staked_amount = staked_amount - %s WHERE user_id = %s", (amount, user["id"]))
            c.execute("INSERT INTO cap_transactions (id, user_id, type, amount, destination, status) VALUES (%s,%s,%s,%s,%s,'pending')",
                      (str(uuid.uuid4()), user["id"], "withdraw", amount, destination))
            conn.commit()
    update_user_tier(user["id"])
    log_activity(user["id"], "cap_withdraw", f"Amount: {amount}, To: {destination}")
    return {"withdrawn": amount, "pending": True}

@app.get("/api/cap/balance")
def get_cap_balance_endpoint(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    staked = user_cap_balance(user["id"])
    tier = get_user_tier(user["id"])
    return {"staked": staked, "tier": tier}

# Founder Dashboard (with treasury info)
@app.get("/api/admin/cap/dashboard")
def cap_dashboard(founder: dict = Depends(founder_only)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT SUM(staked_amount) FROM cap_stakes")
            total_staked = c.fetchone()[0] or 0
            c.execute("SELECT COUNT(*) FROM cap_stakes WHERE staked_amount > 0")
            stakers_count = c.fetchone()[0]
            c.execute("SELECT staked_amount FROM cap_stakes JOIN users ON cap_stakes.user_id = users.id WHERE users.is_admin = TRUE LIMIT 1")
            row = c.fetchone()
            closeai_stake = row[0] if row else 0
            c.execute("SELECT type, amount, tx_hash, destination, status, created FROM cap_transactions ORDER BY created DESC LIMIT 20")
            recent_tx = [{"type": r[0], "amount": r[1], "tx_hash": r[2], "destination": r[3], "status": r[4], "created": r[5].isoformat() if r[5] else None} for r in c.fetchall()]
            c.execute("SELECT COUNT(*) FROM activity_log WHERE action = 'cap_burn'")
            total_burns = c.fetchone()[0]
            c.execute("SELECT SUM(amount) FROM cap_transactions WHERE type = 'deposit'")
            total_deposits = c.fetchone()[0] or 0
            revenue_estimate = total_deposits * 0.01

    dex_price = get_cap_price_from_dex() if WEB3_AVAILABLE else None
    treasury_balance = get_treasury_balance() if WEB3_AVAILABLE else None
    total_supply = get_cap_total_supply() if WEB3_AVAILABLE else None

    return {
        "total_staked": total_staked,
        "stakers_count": stakers_count,
        "closeai_stake": closeai_stake,
        "recent_transactions": recent_tx,
        "total_burns": total_burns,
        "revenue_estimate": revenue_estimate,
        "dex_price": dex_price,
        "treasury_address": settings.CLOSEAI_TREASURY_ADDRESS,
        "treasury_balance": treasury_balance,
        "treasury_total_allocation": settings.CLOSEAI_TOTAL_ALLOCATION,
        "total_supply_onchain": total_supply,
        "contract_address": settings.CAP_CONTRACT_ADDRESS
    }

# ==================== NEW: 2FA & Wallet System ====================
def generate_totp_secret() -> str:
    if not TOTP_AVAILABLE:
        raise HTTPException(501, "pyotp not installed")
    return pyotp.random_base32()

def get_totp_uri(secret: str, user_email: str) -> str:
    if not TOTP_AVAILABLE:
        raise HTTPException(501, "pyotp not installed")
    return pyotp.totp.TOTP(secret).provisioning_uri(user_email, issuer_name=settings.TOTP_ISSUER)

def verify_totp(secret: str, code: str) -> bool:
    if not TOTP_AVAILABLE:
        raise HTTPException(501, "pyotp not installed")
    totp = pyotp.TOTP(secret)
    return totp.verify(code)

def encrypt_wallet(plaintext: str, password: str) -> str:
    if not CRYPTO_AVAILABLE:
        raise HTTPException(501, "cryptography module not installed")
    key = hashlib.sha256(password.encode()).digest()
    cipher = Fernet(base64.urlsafe_b64encode(key[:32]))
    return cipher.encrypt(plaintext.encode()).decode()

def decrypt_wallet(ciphertext: str, password: str) -> str:
    if not CRYPTO_AVAILABLE:
        raise HTTPException(501, "cryptography module not installed")
    key = hashlib.sha256(password.encode()).digest()
    cipher = Fernet(base64.urlsafe_b64encode(key[:32]))
    return cipher.decrypt(ciphertext.encode()).decode()

@app.post("/api/wallet/create")
async def create_wallet(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    password = req.get("password")
    totp_code = req.get("totp_code")
    if not password or len(password) < 10:
        raise HTTPException(400, "Password must be at least 10 characters")
    secret = req.get("totp_secret")
    if not secret or not verify_totp(secret, totp_code):
        raise HTTPException(400, "Invalid 2FA code")
    if not req.get("imported"):
        if not ETH_ACCOUNT_AVAILABLE:
            raise HTTPException(501, "eth_account not installed; use imported private key")
        Account.enable_unaudited_hdwallet_features()
        acct = Account.create()
        private_key = acct.key.hex()
        address = acct.address
    else:
        private_key = req.get("private_key")
        address = req.get("address")
    encrypted_blob = encrypt_wallet(private_key, password)
    recovery_key = hashlib.sha256(secret.encode()).hexdigest()
    recovery_blob = encrypt_wallet(private_key, recovery_key)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO cap_wallets (user_id, encrypted_blob, password_salt, recovery_blob, recovery_salt, totp_secret, totp_enabled, is_founder_wallet)
                VALUES (%s,%s,%s,%s,%s,%s,TRUE,%s)
                ON CONFLICT (user_id) DO UPDATE SET encrypted_blob=EXCLUDED.encrypted_blob,
                    recovery_blob=EXCLUDED.recovery_blob, totp_secret=EXCLUDED.totp_secret, totp_enabled=TRUE
            """, (user["id"], encrypted_blob, "salt", recovery_blob, "salt", secret, user.get("is_admin", False)))
            conn.commit()
    return {"created": True, "address": address}

@app.get("/api/wallet/status")
async def wallet_status(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT encrypted_blob IS NOT NULL, totp_enabled FROM cap_wallets WHERE user_id=%s", (user["id"],))
            row = c.fetchone()
            exists = row[0] if row else False
            totp = row[1] if row else False
    return {"exists": exists, "totp_enabled": totp}

@app.post("/api/wallet/unlock")
async def unlock_wallet(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    password = req.get("password")
    totp_code = req.get("totp_code")
    if not password or not totp_code: raise HTTPException(400, "Missing credentials")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT encrypted_blob, totp_secret FROM cap_wallets WHERE user_id=%s", (user["id"],))
            row = c.fetchone()
            if not row: raise HTTPException(404, "Wallet not found")
            encrypted_blob, totp_secret = row
    if not verify_totp(totp_secret, totp_code):
        raise HTTPException(400, "Invalid 2FA code")
    try:
        private_key = decrypt_wallet(encrypted_blob, password)
        return {"private_key": private_key}
    except:
        raise HTTPException(400, "Wrong password")

@app.post("/api/wallet/recover")
async def recover_wallet(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    totp_code = req.get("totp_code")
    new_password = req.get("new_password")
    if not totp_code or not new_password: raise HTTPException(400, "Missing fields")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT recovery_blob, totp_secret FROM cap_wallets WHERE user_id=%s", (user["id"],))
            row = c.fetchone()
            if not row: raise HTTPException(404, "Wallet not found")
            recovery_blob, totp_secret = row
    if not verify_totp(totp_secret, totp_code):
        raise HTTPException(400, "Invalid 2FA code")
    recovery_key = hashlib.sha256(totp_secret.encode()).hexdigest()
    try:
        private_key = decrypt_wallet(recovery_blob, recovery_key)
    except:
        raise HTTPException(400, "Recovery failed")
    new_encrypted = encrypt_wallet(private_key, new_password)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE cap_wallets SET encrypted_blob=%s WHERE user_id=%s", (new_encrypted, user["id"]))
            conn.commit()
    return {"recovered": True}

@app.post("/api/wallet/relay")
async def relay_transaction(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    if not WEB3_AVAILABLE: raise HTTPException(501, "web3 not installed")
    signed_tx = req.get("signed_tx")
    if not signed_tx: raise HTTPException(400, "Missing signed_tx")
    try:
        w3 = Web3(Web3.HTTPProvider(settings.POLYGON_RPC_URL))
        tx_hash = w3.eth.send_raw_transaction(signed_tx)
        return {"tx_hash": tx_hash.hex()}
    except Exception as e:
        logger.error(f"Relay error: {e}")
        raise HTTPException(500, "Relay failed")

# ==================== TOTP Setup ====================
@app.post("/api/2fa/setup")
async def setup_2fa(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    secret = generate_totp_secret()
    uri = get_totp_uri(secret, user["email"])
    qr_base64 = ""
    if QRCODE_AVAILABLE:
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        qr_base64 = base64.b64encode(buffered.getvalue()).decode()
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE cap_wallets SET totp_secret=%s WHERE user_id=%s", (secret, user["id"]))
            conn.commit()
    return {"secret": secret, "uri": uri, "qr_code": f"data:image/png;base64,{qr_base64}" if qr_base64 else None}

@app.post("/api/2fa/verify")
async def verify_2fa(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    code = req.get("code")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT totp_secret FROM cap_wallets WHERE user_id=%s", (user["id"],))
            row = c.fetchone()
            if not row: raise HTTPException(404, "2FA not setup")
            secret = row[0]
    if verify_totp(secret, code):
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("UPDATE cap_wallets SET totp_enabled=TRUE WHERE user_id=%s", (user["id"],))
                conn.commit()
        return {"verified": True}
    raise HTTPException(400, "Invalid code")

# ==================== Gnosis Safe Treasury ====================
SAFE_ABI = json.loads('[{"constant":false,"inputs":[{"name":"to","type":"address"},{"name":"value","type":"uint256"},{"name":"data","type":"bytes"},{"name":"operation","type":"uint8"},{"name":"safeTxGas","type":"uint256"},{"name":"baseGas","type":"uint256"},{"name":"gasPrice","type":"uint256"},{"name":"gasToken","type":"address"},{"name":"refundReceiver","type":"address"},{"name":"signatures","type":"bytes"}],"name":"execTransaction","outputs":[{"name":"success","type":"bool"}],"type":"function"}]')

def get_safe_nonce() -> int:
    return 0

@app.post("/api/safe/propose")
async def propose_safe_transaction(req: dict, user: dict = Depends(get_current_user)):
    if not user or not user.get("is_admin"):
        raise HTTPException(403, "Only founder")
    to_address = req.get("to")
    value = req.get("value")
    data = req.get("data", "0x")
    nonce = get_safe_nonce()
    safe_tx_hash = f"0x{secrets.token_hex(32)}"
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO safe_transactions (id, proposer_id, to_address, value, data, nonce, safe_tx_hash) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                      (str(uuid.uuid4()), user["id"], to_address, value, data, nonce, safe_tx_hash))
            conn.commit()
    return {"safe_tx_hash": safe_tx_hash, "nonce": nonce}

@app.get("/api/safe/transactions")
async def list_safe_transactions(user: dict = Depends(get_current_user)):
    if not user or not user.get("is_admin"):
        raise HTTPException(403)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, safe_tx_hash, to_address, value, nonce, signatures, executed FROM safe_transactions ORDER BY created_at DESC")
            rows = c.fetchall()
            txs = [{"id": r[0], "safe_tx_hash": r[1], "to": r[2], "value": r[3], "nonce": r[4], "signatures": json.loads(r[5]) if r[5] else {}, "executed": r[6]} for r in rows]
    return {"transactions": txs}

@app.post("/api/safe/sign")
async def sign_safe_transaction(req: dict, user: dict = Depends(get_current_user)):
    if not user or not user.get("is_admin"):
        raise HTTPException(403)
    tx_id = req.get("tx_id")
    signature = req.get("signature")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT signatures, safe_tx_hash FROM safe_transactions WHERE id=%s", (tx_id,))
            row = c.fetchone()
            if not row: raise HTTPException(404)
            sigs = json.loads(row[0]) if row[0] else {}
            sigs[user["id"]] = signature
            if len(sigs) >= settings.SAFE_THRESHOLD:
                c.execute("UPDATE safe_transactions SET signatures=%s, executed=TRUE WHERE id=%s",
                          (json.dumps(sigs), tx_id))
            else:
                c.execute("UPDATE safe_transactions SET signatures=%s WHERE id=%s",
                          (json.dumps(sigs), tx_id))
            conn.commit()
    return {"signed": True, "threshold_met": len(sigs) >= settings.SAFE_THRESHOLD}

# Health, manifest, root
@app.get("/health")
def health_check():
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT 1")
                db_status = "connected"
    except: db_status = "disconnected"
    return {"status": "ok", "version": "36.0", "database": db_status}

@app.get("/manifest.json")
async def manifest():
    return JSONResponse(content={
        "name": "CAPITAN AI", "short_name": "CAPITAN AI", "start_url": "/",
        "display": "standalone", "background_color": "#0f172a", "theme_color": "#0b6d8c"
    })

@app.get("/")
async def root():
    return {"name": "CAPITAN AI", "version": "36.0"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port) 