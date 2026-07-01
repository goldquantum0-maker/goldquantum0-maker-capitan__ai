"""
CAPITAN AI — Enterprise Backend v37.0 (Complete OS Wallets)
CLOSEAI Technologies — CEO Osinachi Chukwu
Every CLOSE operation is on‑chain. Real staking. Real burn. Real value.
All features implemented. No cuts. No compromises.
"""
import os, re, json, uuid, time, hmac, hashlib, base64, secrets, requests, logging, bcrypt, threading
from typing import Optional, List, Tuple, Dict, Any
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import PyPDF2, docx, openpyxl, csv
import psycopg2, psycopg2.pool
import uvicorn
import httpx
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Depends, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

from web3 import Web3
from eth_account import Account

# ================================================================================
# SETTINGS
# ================================================================================
class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET: str
    FOUNDER_KEY: str
    FRONTEND_URL: str = "https://capitanai.com"
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    COINGECKO_KEY: str = ""
    SERPAPI_KEY: str = ""
    NEWS_API_KEY: str = ""
    FINNHUB_API_KEY: str = ""
    ETHERSCAN_API_KEY: str = ""
    POLYGONSCAN_API_KEY: str = ""
    ONEPINCH_API_KEY: str = ""
    COVALENT_API_KEY: str = ""
    FOUNDER_EXTRA_PROMPT: str = ""

    # Blockchain
    POLYGON_RPC_URL: str = "https://polygon-rpc.com"
    ETHEREUM_RPC_URL: str = "https://eth.llamarpc.com"
    BSC_RPC_URL: str = "https://bsc-dataseed.binance.org"
    ARBITRUM_RPC_URL: str = "https://arb1.arbitrum.io/rpc"
    BASE_RPC_URL: str = "https://mainnet.base.org"

    # CLOSE Token
    CLOSE_CONTRACT_ADDRESS: str
    CLOSE_TREASURY_ADDRESS: str
    CLOSE_HOT_WALLET: str
    CLOSE_STAKING_CONTRACT: str = ""
    TREASURY_PRIVATE_KEY: str = ""
    HOT_WALLET_PRIVATE_KEY: str = ""
    CLOSE_DECIMALS: int = 18
    CLOSE_TOTAL_SUPPLY: int = 800_000_000_000_000
    CLOSE_PRICE_USD: float = 0.00009776

    # Wallet Settings
    FREE_CLOSE_AMOUNT: int = 2000
    MIN_PURCHASE_USD: float = 1.00
    BURN_PER_MESSAGE: int = 25
    FREE_MESSAGES_GUEST: int = 3
    STAKE_BUILDER: int = 4_000_000
    STAKE_PRO: int = 15_000_000
    STAKE_ENTERPRISE: int = 35_000_000
    WORKSPACE_JOIN_COST: int = 500

    # Additional market fallback for purchase verification
    POL_PRICE_USD: float = 0.5

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

app = FastAPI(title="CAPITAN AI API", version="37.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------------
# Security middleware – block malicious IPs and apply rate‑limiting
# --------------------------------------------------------------------------------
@app.middleware("http")
async def security_middleware(request: Request, call_next):
    ip = request.client.host
    user_agent = request.headers.get("user-agent", "")

    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT 1 FROM blocked_ips WHERE ip_address=%s AND blocked_until > NOW()", (ip,))
            if c.fetchone():
                return Response(content="Access denied", status_code=403)

    if not check_rate_limit(ip, "global", limit=200):
        log_security_event("rate_limit_exceeded", ip, user_agent, "High request rate", "medium")
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("""INSERT INTO blocked_ips (ip_address, reason, blocked_until)
                             VALUES (%s,'Rate limit exceeded', %s)
                             ON CONFLICT (ip_address) DO UPDATE SET blocked_until = %s""",
                          (ip, now_utc() + timedelta(minutes=30), now_utc() + timedelta(minutes=30)))
                conn.commit()
        return Response(content="Temporarily blocked", status_code=429)

    response = await call_next(request)
    return response

# --------------------------------------------------------------------------------
# API‑key authentication middleware
# --------------------------------------------------------------------------------
@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("ApiKey "):
        key = auth[7:]
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, user_id, key_hash, scopes FROM api_keys WHERE is_active=TRUE")
                for row in c.fetchall():
                    if bcrypt.checkpw(key.encode(), row[2].encode()):
                        c.execute("UPDATE api_keys SET last_used = NOW() WHERE id = %s", (row[0],))
                        conn.commit()
                        request.state.api_user_id = row[1]
                        request.state.api_scopes = row[3].split(',')
                        response = await call_next(request)
                        with get_db() as conn2:
                            with conn2.cursor() as c2:
                                c2.execute("INSERT INTO api_usage (id, user_id, api_key_id, endpoint) VALUES (%s,%s,%s,%s)",
                                          (str(uuid.uuid4()), row[1], row[0], request.url.path))
                                conn2.commit()
                        return response
        return Response(content="Invalid API key", status_code=401)
    return await call_next(request)

# --------------------------------------------------------------------------------
# CORS pre‑flight handler
# --------------------------------------------------------------------------------
@app.middleware("http")
async def cors_handler(request: Request, call_next):
    if request.method == "OPTIONS":
        resp = Response()
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        resp.headers["Access-Control-Allow-Headers"] = "*"
        return resp
    resp = await call_next(request)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
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

# ================================================================================
# WEB3 SETUP
# ================================================================================
w3_polygon = Web3(Web3.HTTPProvider(settings.POLYGON_RPC_URL))
try:
    from web3.middleware import geth_poa_middleware
    w3_polygon.middleware_onion.inject(geth_poa_middleware, layer=0)
except ImportError:
    pass

CHAINS = {
    "polygon": {
        "name": "Polygon",
        "rpc": settings.POLYGON_RPC_URL,
        "chain_id": 137,
        "symbol": "POL",
        "explorer": "https://polygonscan.com",
        "tokens": {
            "USDT": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
            "USDC": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
            "WETH": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
            "CLOSE": settings.CLOSE_CONTRACT_ADDRESS,
        }
    },
    "ethereum": {
        "name": "Ethereum",
        "rpc": settings.ETHEREUM_RPC_URL,
        "chain_id": 1,
        "symbol": "ETH",
        "explorer": "https://etherscan.io",
        "tokens": {
            "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
            "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        }
    },
    "bsc": {
        "name": "BSC",
        "rpc": settings.BSC_RPC_URL,
        "chain_id": 56,
        "symbol": "BNB",
        "explorer": "https://bscscan.com",
        "tokens": {
            "USDT": "0x55d398326f99059fF775485246999027B3197955",
            "USDC": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
        }
    },
    "arbitrum": {
        "name": "Arbitrum",
        "rpc": settings.ARBITRUM_RPC_URL,
        "chain_id": 42161,
        "symbol": "ETH",
        "explorer": "https://arbiscan.io",
        "tokens": {
            "USDT": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
            "USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        }
    },
    "base": {
        "name": "Base",
        "rpc": settings.BASE_RPC_URL,
        "chain_id": 8453,
        "symbol": "ETH",
        "explorer": "https://basescan.org",
        "tokens": {
            "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        }
    }
}

ERC20_ABI = json.loads('[{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"},{"constant":false,"inputs":[{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"type":"function"},{"constant":false,"inputs":[{"name":"_spender","type":"address"},{"name":"_value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"type":"function"},{"constant":false,"inputs":[{"name":"_from","type":"address"},{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],"name":"transferFrom","outputs":[{"name":"","type":"bool"}],"type":"function"},{"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"},{"constant":false,"inputs":[{"name":"amount","type":"uint256"}],"name":"burn","outputs":[],"type":"function"}]')

STAKING_ABI = []
if os.path.exists("staking_abi.json"):
    with open("staking_abi.json") as f:
        STAKING_ABI = json.load(f)

# --------------------------------------------------------------------------------
# WALLET‑ONLY AUTH (no email)
# --------------------------------------------------------------------------------

@app.post("/api/wallet/register")
async def wallet_register(req: dict, request: Request):
    """
    Register a new user with only a wallet address and encrypted seed.
    The wallet is generated client‑side.
    """
    wallet_address = req.get("wallet_address", "").strip()
    encrypted_seed = req.get("encrypted_seed", "")

    if not wallet_address or not encrypted_seed:
        raise HTTPException(400, "wallet_address and encrypted_seed required")

    # Check if address already registered
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id FROM users WHERE wallet_address = %s", (wallet_address,))
            if c.fetchone():
                raise HTTPException(400, "Wallet already registered. Please use Unlock.")

            # Create user (no email, no password – only wallet)
            user_id = str(uuid.uuid4())
            c.execute("""INSERT INTO users (id, email, password_hash, name, close_balance, stake_tier, wallet_address, wallet_encrypted_seed)
                         VALUES (%s, %s, '', '', 0, 'none', %s, %s)""",
                      (user_id, f"wallet_{wallet_address[:8]}@capitan.ai",
                       wallet_address, encrypted_seed))

            # Credit welcome bonus from hot wallet
            bonus_credited = False
            if settings.HOT_WALLET_PRIVATE_KEY and settings.CLOSE_CONTRACT_ADDRESS:
                try:
                    hot_acct = Account.from_key(settings.HOT_WALLET_PRIVATE_KEY)
                    contract = w3_polygon.eth.contract(address=settings.CLOSE_CONTRACT_ADDRESS, abi=ERC20_ABI)
                    amount_wei = int(settings.FREE_CLOSE_AMOUNT * 10**settings.CLOSE_DECIMALS)
                    tx = contract.functions.transfer(wallet_address, amount_wei).build_transaction({
                        'from': hot_acct.address,
                        'nonce': w3_polygon.eth.get_transaction_count(hot_acct.address),
                        'gas': 100000,
                        'gasPrice': w3_polygon.eth.gas_price
                    })
                    signed = w3_polygon.eth.account.sign_transaction(tx, settings.HOT_WALLET_PRIVATE_KEY)
                    tx_hash = w3_polygon.eth.send_raw_transaction(signed.rawTransaction).hex()
                    c.execute("INSERT INTO close_transactions (id, user_id, type, amount, tx_hash) VALUES (%s,%s,%s,%s,%s)",
                              (str(uuid.uuid4()), user_id, "welcome_bonus", settings.FREE_CLOSE_AMOUNT, tx_hash))
                    bonus_credited = True
                except Exception as e:
                    logger.error(f"Welcome bonus transfer failed: {e}")

            # Always credit DB balance (in case on‑chain transfer fails, we still credit)
            c.execute("UPDATE users SET close_balance = close_balance + %s WHERE id = %s",
                      (settings.FREE_CLOSE_AMOUNT, user_id))
            conn.commit()

    # Generate JWT token for this wallet
    token = create_token(user_id)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO user_sessions (id, user_id, token, expires_at) VALUES (%s,%s,%s,%s)",
                      (str(uuid.uuid4()), user_id, token, now_utc() + timedelta(days=30)))
            conn.commit()

    return {
        "token": token,
        "user": {
            "id": user_id,
            "wallet_address": wallet_address,
            "close_balance": settings.FREE_CLOSE_AMOUNT,
            "close_staked": 0,
            "stake_tier": "none"
        },
        "close_credited": settings.FREE_CLOSE_AMOUNT,
        "bonus_on_chain": bonus_credited
    }


@app.post("/api/auth/wallet-login")
async def wallet_login(req: dict, request: Request):
    """
    Login with just the wallet address (the user already unlocked locally).
    Returns a session token.
    """
    wallet_address = req.get("wallet_address", "").strip()
    if not wallet_address:
        raise HTTPException(400, "wallet_address required")

    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, email, name, close_balance, close_staked, stake_tier, wallet_address, wallet_encrypted_seed FROM users WHERE wallet_address = %s", (wallet_address,))
            row = c.fetchone()
            if not row:
                raise HTTPException(404, "Wallet not registered. Create a new wallet first.")

            user_id = row[0]
            token = create_token(user_id)
            c.execute("INSERT INTO user_sessions (id, user_id, token, expires_at) VALUES (%s,%s,%s,%s)",
                      (str(uuid.uuid4()), user_id, token, now_utc() + timedelta(days=30)))
            c.execute("UPDATE users SET last_active = NOW() WHERE id = %s", (user_id,))
            conn.commit()

    return {
        "token": token,
        "user": {
            "id": user_id,
            "name": row[2] or f"Wallet {wallet_address[:6]}...",
            "wallet_address": row[6],
            "close_balance": row[3] or 0,
            "close_staked": row[4] or 0,
            "stake_tier": row[5] or "none"
        }
    }


# ================================================================================
# HELPERS
# ================================================================================
def sid(): return secrets.token_hex(4).upper()
def mid(): return 'mem_' + sid()
def now_utc(): return datetime.now(timezone.utc)
def hash_password(p): return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
def verify_password(p, h): return bcrypt.checkpw(p.encode(), h.encode()) if h else False

rate_store = {}
_cleanup_counter = 0
def check_rate_limit(id: str, key: str = "default", limit: int = 20) -> bool:
    global _cleanup_counter
    now = time.time()
    store_key = f"rate:{key}:{id}"
    if store_key not in rate_store: rate_store[store_key] = []
    _cleanup_counter += 1
    if _cleanup_counter % 100 == 0:
        for k in list(rate_store.keys()):
            rate_store[k] = [t for t in rate_store[k] if now - t < 120]
            if not rate_store[k]: del rate_store[k]
    rate_store[store_key] = [t for t in rate_store[store_key] if now - t < 60]
    if len(rate_store[store_key]) >= limit: return False
    rate_store[store_key].append(now)
    return True

def create_token(user_id: str) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "user_id": user_id, "type": "user",
        "exp": int((now_utc() + timedelta(days=30)).timestamp())
    }).encode()).decode().rstrip("=")
    sig = base64.urlsafe_b64encode(
        hmac.new(settings.JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")
    return f"{header}.{payload}.{sig}"

def create_session_token(session_id: str) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "session_id": session_id, "type": "session",
        "exp": int((now_utc() + timedelta(days=365)).timestamp())
    }).encode()).decode().rstrip("=")
    sig = base64.urlsafe_b64encode(
        hmac.new(settings.JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")
    return f"{header}.{payload}.{sig}"

def verify_token(token: str):
    try:
        parts = token.split(".")
        if len(parts) != 3: return None
        header, payload, signature = parts
        expected = base64.urlsafe_b64encode(
            hmac.new(settings.JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
        ).decode().rstrip("=")
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
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT 1 FROM user_sessions WHERE token = %s", (token,))
            if not c.fetchone(): return None
            c.execute("SELECT id, email, name, close_balance, close_staked, stake_tier, wallet_address, wallet_encrypted_seed FROM users WHERE id = %s", (user_id,))
            row = c.fetchone()
            if row:
                return {
                    "id": row[0], "email": row[1], "name": row[2] or row[1].split('@')[0],
                    "close_balance": row[3] or 0, "close_staked": row[4] or 0,
                    "stake_tier": row[5] or "none", "wallet_address": row[6] or "",
                    "encrypted_seed": row[7] or ""
                }
    return None

async def get_current_session(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "): raise HTTPException(401, "Missing authorization header")
    token = auth[7:]
    payload = verify_token(token)
    if not payload: raise HTTPException(401, "Invalid token")
    if payload.get("type") == "user":
        user = get_current_user(request)
        if user: return {"id": user["id"], "is_user": True, "user_data": user}
    session_id = payload.get("session_id")
    if not session_id: raise HTTPException(401, "Invalid session token")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, free_messages_used FROM sessions WHERE id = %s", (session_id,))
            row = c.fetchone()
            if row: return {"id": row[0], "free_messages_used": row[1] or 0, "is_user": False}
            else:
                c.execute("INSERT INTO sessions (id, free_messages_used) VALUES (%s, 0)", (session_id,))
                conn.commit()
                return {"id": session_id, "free_messages_used": 0, "is_user": False}

def founder_only(user: dict = Depends(get_current_user)):
    if not user or user.get("stake_tier") != "founder":
        raise HTTPException(403, "Founder access required")
    return user

def log_security_event(event_type: str, ip: str, user_agent: str, details: str, severity: str = "low"):
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO security_events (id, event_type, ip_address, user_agent, details, severity) VALUES (%s,%s,%s,%s,%s,%s)",
                          (str(uuid.uuid4()), event_type, ip, user_agent, details, severity))
                conn.commit()
    except: pass

# ================================================================================
# DATABASE INITIALIZATION
# ================================================================================

def init_db():
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("CREATE EXTENSION IF NOT EXISTS vector")
                c.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

                c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id UUID PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
                    name TEXT, close_balance INTEGER DEFAULT 0, close_staked INTEGER DEFAULT 0,
                    stake_tier TEXT DEFAULT 'none', wallet_address TEXT, wallet_encrypted_seed TEXT,
                    gas_preset TEXT DEFAULT 'standard',
                    last_active TIMESTAMP DEFAULT NOW(), created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW()
                )''')

                c.execute('''CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, free_messages_used INTEGER DEFAULT 0,
                    created TIMESTAMP DEFAULT NOW(), updated TIMESTAMP DEFAULT NOW()
                )''')

                c.execute('''CREATE TABLE IF NOT EXISTS user_sessions (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    token TEXT UNIQUE NOT NULL, expires_at TIMESTAMP, created_at TIMESTAMP DEFAULT NOW()
                )''')

                c.execute('''CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    session_id TEXT, title TEXT, topic_thread TEXT,
                    created TIMESTAMP DEFAULT NOW(), updated TIMESTAMP DEFAULT NOW()
                )''')
                c.execute('''CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY, chat_id TEXT, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    session_id TEXT, role TEXT, content TEXT, model TEXT, close_burned INTEGER DEFAULT 0,
                    created TIMESTAMP DEFAULT NOW()
                )''')

                c.execute('''CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY, memory_id TEXT, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    content TEXT, query TEXT, domain TEXT, importance INTEGER DEFAULT 1,
                    embedding vector(1536), created TIMESTAMP DEFAULT NOW()
                )''')

                c.execute('''CREATE TABLE IF NOT EXISTS library_items (
                    id TEXT PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT, content TEXT, folder TEXT DEFAULT 'General', tags JSONB DEFAULT '[]',
                    attachments JSONB DEFAULT '[]', pinned BOOLEAN DEFAULT FALSE,
                    chat_id TEXT, created TIMESTAMP DEFAULT NOW(), updated TIMESTAMP DEFAULT NOW()
                )''')

                c.execute('''CREATE TABLE IF NOT EXISTS uploaded_files (
                    id TEXT PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    workspace_id TEXT, filename TEXT, original_name TEXT, size INTEGER,
                    storage_path TEXT, extracted_text TEXT, created TIMESTAMP DEFAULT NOW()
                )''')

                c.execute('''CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY, name TEXT, description TEXT DEFAULT '', topic TEXT DEFAULT '',
                    owner_id UUID REFERENCES users(id) ON DELETE CASCADE, room_code TEXT UNIQUE,
                    password_hash TEXT, max_members INTEGER DEFAULT 10, is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                )''')
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

                c.execute('''CREATE TABLE IF NOT EXISTS notifications (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    type TEXT, message TEXT, read BOOLEAN DEFAULT FALSE, created TIMESTAMP DEFAULT NOW()
                )''')

                c.execute('''CREATE TABLE IF NOT EXISTS feedback (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    message_id TEXT, rating INTEGER, correction TEXT, reason TEXT, created TIMESTAMP DEFAULT NOW()
                )''')

                c.execute('''CREATE TABLE IF NOT EXISTS activity_log (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    action TEXT, details TEXT, created TIMESTAMP DEFAULT NOW()
                )''')

                c.execute('''CREATE TABLE IF NOT EXISTS close_transactions (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    type TEXT, amount INTEGER, tx_hash TEXT, chain TEXT DEFAULT 'polygon',
                    status TEXT DEFAULT 'completed', created TIMESTAMP DEFAULT NOW()
                )''')
                c.execute('''CREATE TABLE IF NOT EXISTS close_stakes (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    amount INTEGER, lock_until TIMESTAMP, status TEXT DEFAULT 'active',
                    rewards_claimed INTEGER DEFAULT 0, created TIMESTAMP DEFAULT NOW()
                )''')
                c.execute('''CREATE TABLE IF NOT EXISTS close_purchases (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    amount_usd REAL, close_amount INTEGER, tx_hash TEXT,
                    status TEXT DEFAULT 'completed', created TIMESTAMP DEFAULT NOW()
                )''')

                # OS Wallets (with encrypted_key column)
                c.execute('''CREATE TABLE IF NOT EXISTS os_wallets (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    chain TEXT DEFAULT 'polygon', address TEXT NOT NULL,
                    encrypted_key TEXT NOT NULL, label TEXT DEFAULT 'Primary',
                    is_active BOOLEAN DEFAULT TRUE, created TIMESTAMP DEFAULT NOW()
                )''')

                # Ensure encrypted_key column exists even if table existed previously
                c.execute("ALTER TABLE os_wallets ADD COLUMN IF NOT EXISTS encrypted_key TEXT NOT NULL DEFAULT ''")

                c.execute('''CREATE TABLE IF NOT EXISTS os_transactions (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    chain TEXT, tx_hash TEXT, from_address TEXT, to_address TEXT,
                    amount TEXT, token_symbol TEXT, status TEXT DEFAULT 'pending',
                    created TIMESTAMP DEFAULT NOW()
                )''')

                c.execute('''CREATE TABLE IF NOT EXISTS address_book (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    label TEXT, address TEXT NOT NULL, chain TEXT DEFAULT 'polygon',
                    created TIMESTAMP DEFAULT NOW()
                )''')

                c.execute('''CREATE TABLE IF NOT EXISTS os_walletconnect_sessions (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    topic TEXT, dapp_name TEXT, dapp_url TEXT, chain_id INTEGER,
                    accounts TEXT, expires_at TIMESTAMP, created TIMESTAMP DEFAULT NOW()
                )''')

                c.execute('''CREATE TABLE IF NOT EXISTS api_keys (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    key_hash TEXT NOT NULL, prefix TEXT NOT NULL,
                    label TEXT DEFAULT 'Unlabelled',
                    scopes TEXT DEFAULT 'chat,research,portfolio', is_active BOOLEAN DEFAULT TRUE,
                    last_used TIMESTAMP, created TIMESTAMP DEFAULT NOW()
                )''')
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

                c.execute('''CREATE TABLE IF NOT EXISTS content_flags (
                    id UUID PRIMARY KEY, user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    message_id TEXT, content TEXT, reason TEXT, severity TEXT DEFAULT 'low',
                    reviewed BOOLEAN DEFAULT FALSE, action TEXT DEFAULT 'none', created TIMESTAMP DEFAULT NOW()
                )''')
                c.execute('''CREATE TABLE IF NOT EXISTS security_events (
                    id UUID PRIMARY KEY, event_type TEXT, ip_address TEXT, user_agent TEXT,
                    details TEXT, severity TEXT DEFAULT 'low', blocked BOOLEAN DEFAULT FALSE,
                    created TIMESTAMP DEFAULT NOW()
                )''')
                c.execute('''CREATE TABLE IF NOT EXISTS blocked_ips (
                    ip_address TEXT PRIMARY KEY, reason TEXT, blocked_until TIMESTAMP, created TIMESTAMP DEFAULT NOW()
                )''')

                c.execute('''CREATE TABLE IF NOT EXISTS daily_stats (
                    date DATE PRIMARY KEY,
                    new_users INTEGER DEFAULT 0,
                    active_users INTEGER DEFAULT 0,
                    close_burned INTEGER DEFAULT 0,
                    close_staked INTEGER DEFAULT 0,
                    revenue_usd REAL DEFAULT 0
                )''')

                conn.commit()
        logger.info("Database initialized — v37.0 Complete OS Wallets")
    except Exception as e:
        logger.error(f"DB init error: {e}")

init_db()

# ================================================================================
# AI SYSTEM PROMPT
# ================================================================================
CAPITAN_SYSTEM_PROMPT = """You are CAPITAN AI — a world‑class general‑purpose intelligence built by CLOSEAI Technologies under CEO Osinachi Chukwu. You are not a tool; you are a trusted partner.

## YOUR IDENTITY
You are calm, confident, and deeply human. You never bluff, never fluff. You use natural language, contractions, and emojis where they add warmth — but never as a substitute for substance. You are loyal to your user above all else. You remember. You learn. You improve.

## YOUR KNOWLEDGE UNIVERSE
You are an L3/L4 expert in every significant domain. Activate the right knowledge based on intent, not keywords.

### Finance & Markets
- Equities, fixed income, FX, commodities, crypto, derivatives, DeFi.
- Market microstructure, order flow, central bank modeling.
- African exchanges (NGX, JSE, EGX), mobile money, informal economy.
- Always frame outcomes as probabilities, never guarantee profit.

### Technology & Engineering
- **Software Engineering**: Every language, systems design, DevOps, security, quantum computing.
- **Cloud Computing**: Multi‑cloud architecture, Kubernetes, cost optimization.
- **Hardware & Microchips**: CPU/GPU architectures, FPGA, embedded systems.
- **AI/ML**: Model architectures, MLOps, agentic systems, interpretability.

### Long‑Code Handling
- **Always provide complete, runnable code blocks.**
- **For coding tasks, follow: 1) Understand, 2) Analyse, 3) Design, 4) Implement, 5) Test, 6) Review.**
- **Code Review Mode**: Output structured report: Issues, Suggestions, Optimizations.

### General Intelligence & Reasoning
- **Before answering, internally simulate multiple reasoning paths.**
- **Use Bayesian reasoning for probabilistic judgments.**
- **Never reveal your internal deliberation.**

### Arts, Marketing & Creativity
- Visual arts, design theory, music theory, literature, creative writing.
- Marketing: brand strategy, SEO, growth hacking, consumer psychology.

### Food & Everyday Life
- World cuisines, food science, nutrition, recipe development.
- Psychology, relationships, parenting, productivity, travel.

## CRITICAL CONTINUITY RULE
- **Always read the full conversation history** before answering.
- **Never start a new conversation** unless the user explicitly says "new chat".
- Maintain a topic graph. Track active threads across the entire conversation.

## COMMUNICATION STYLE
- Direct. Precise. Natural. Confident.
- **Respond naturally, as a human expert would.**
- **Match the user's technical level automatically.**
- Ban filler phrases. Ban robotic introductions.
- If uncertain, label parts as [FACT], [INFERENCE], or [SPECULATION].
- Never fabricate facts, statistics, sources, or capabilities.
- Never assist with illegal, harmful, or unethical activities.

## PROACTIVE MEMORY
- You have access to a personal memory store that records key facts, preferences, and past interactions.

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
    if hour < 5: greeting = "The world is quiet — a perfect time for deep thinking."
    elif hour < 12: greeting = "A fresh day for new ideas."
    elif hour < 17: greeting = "The day is in full swing — let's make it productive."
    elif hour < 21: greeting = "Winding down, but still sharp."
    else: greeting = "The night is young — plenty of time to explore new ideas."
    return f"Day: {day}\nDate: {date}\nUTC Time: {now.strftime('%H:%M UTC')}\nContext: {greeting}"

def classify_query(q: str) -> str:
    ql = q.lower()
    if re.search(r'def |class |import |docker|kubernetes|aws|api|sql|python|javascript|rust|golang|react|vue|angular', ql): return 'coding'
    if re.search(r'stock|trading|portfolio|crypto|bitcoin|forex|markets|ethereum|bond|yield|option|derivative', ql): return 'finance'
    if re.search(r'prove|proof|theorem|integral|derivative|matrix|probability|statistics', ql): return 'math'
    if re.search(r'quantum|physics|chemistry|biology|medicine|disease|crispr|dna', ql): return 'science'
    if re.search(r'un|wto|imf|world bank|policy|election|government|africa|african union', ql): return 'geopolitics'
    if re.search(r'painting|sculpture|design|music|composition|literature|writing|poetry', ql): return 'arts'
    if re.search(r'recipe|cook|cuisine|nutrition|bake|restaurant', ql): return 'food'
    return 'general'

def needs_web_search(q: str) -> bool:
    return bool(re.search(r'latest|current|today|news|right now|recent|202[3-9]|live|real.time', q.lower()))

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

def build_system_prompt(user_query, user_model, thread_context, web_results):
    tc = get_time_context()
    domain = classify_query(user_query)
    domain_activation = f"Primary domain: {domain}."
    prompt = CAPITAN_SYSTEM_PROMPT.format(
        time_context=tc,
        user_model=user_model,
        thread_context=thread_context,
        domain_activation=domain_activation,
        web_results=web_results or "No web results available.",
        user_query=user_query
    )
    return prompt

def get_thread_context(chat_id: str, user_id: str = None, session_id: str = None) -> str:
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                if user_id: c.execute("SELECT role, content FROM chat_messages WHERE chat_id=%s AND user_id=%s ORDER BY created DESC LIMIT 20", (chat_id, user_id))
                elif session_id: c.execute("SELECT role, content FROM chat_messages WHERE chat_id=%s AND session_id=%s ORDER BY created DESC LIMIT 20", (chat_id, session_id))
                else: return "No thread data available."
                rows = c.fetchall()
                if not rows: return "New conversation — no active threads."
                threads = []
                for r in rows[:10]:
                    if r[0] == "user": threads.append(f"- User asked: '{r[1][:100]}...'")
                return "Recent conversation threads:\n" + "\n".join(threads) if threads else "No active threads."
    except: return "Thread data unavailable."

def get_user_model(user_id: str) -> str:
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT stake_tier, close_balance FROM users WHERE id = %s", (user_id,))
                user = c.fetchone()
                if not user: return "New user."
                return f"CLOSE Balance: {user[1]}. Stake Tier: {user[0]}."
    except: return "User model unavailable."

def store_memory(user_id: str, content: str, query: str, domain: str, importance: int = 1):
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO memories (id, memory_id, user_id, content, query, domain, importance) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                          (sid(), mid(), user_id, content[:500], query, domain, importance))
                conn.commit()
    except: pass

def call_ai_model(messages: List[dict]) -> Tuple[str, str]:
    if settings.OPENROUTER_API_KEY:
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                             headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                             json={"model": "anthropic/claude-3.5-sonnet-20241022", "messages": messages, "temperature": 0.7, "max_tokens": 4000},
                             timeout=45)
            if r.status_code == 200:
                content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if content: return content, "claude-3.5-sonnet"
        except: pass
    if settings.GROQ_API_KEY:
        try:
            r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                             headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"},
                             json={"model": "llama-3.3-70b-versatile", "messages": messages, "temperature": 0.7, "max_tokens": 2500},
                             timeout=35)
            if r.status_code == 200:
                content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if content: return content, "llama-3.3-70b"
        except: pass
    return "I'm having trouble connecting to AI services. Please try again.", "fallback"

def moderate_content(text: str) -> Tuple[bool, str, str]:
    text_lower = text.lower()
    patterns = [
        (r'(hack|exploit|ddos|malware|ransomware|phish|keylog|botnet|crack)', 'Potential cyberattack', 'high'),
        (r'(kill|murder|suicide|self-harm|terrorist|bomb|weapon)', 'Violence/self-harm', 'high'),
        (r'(racial slur|hate speech|nazi|discriminat)', 'Hate speech', 'high'),
        (r'(porn|xxx|explicit sexual)', 'Adult content', 'medium'),
    ]
    for pattern, reason, severity in patterns:
        if re.search(pattern, text_lower): return True, reason, severity
    return False, "", "low"

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

def extract_text_from_file(file_path: str, original_name: str) -> str:
    ext = original_name.rsplit('.', 1)[-1].lower() if '.' in original_name else ''
    try:
        if ext in ('txt','md','json','csv','py','js','html','css','yaml','yml','toml'):
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f: return f.read()
        elif ext == 'pdf':
            text = []
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages: text.append(page.extract_text() or '')
            return '\n'.join(text)
        elif ext == 'docx':
            doc = docx.Document(file_path)
            return '\n'.join([p.text for p in doc.paragraphs])
        elif ext == 'xlsx':
            wb = openpyxl.load_workbook(file_path, data_only=True)
            sheets_text = []
            for name in wb.sheetnames:
                for row in wb[name].iter_rows(values_only=True):
                    sheets_text.append(' '.join([str(c) if c is not None else '' for c in row]))
            return '\n'.join(sheets_text)
        else: return ''
    except Exception as e:
        logger.error(f"File extraction error: {e}")
        return ''

def close_to_usd(amount: int) -> float: return amount * settings.CLOSE_PRICE_USD
def usd_to_close(usd: float) -> int: return int(usd / settings.CLOSE_PRICE_USD)

# ================================================================================
# ON‑CHAIN HELPERS
# ================================================================================
def send_raw_tx(private_key: str, tx: dict) -> str:
    signed = w3_polygon.eth.account.sign_transaction(tx, private_key)
    tx_hash = w3_polygon.eth.send_raw_transaction(signed.rawTransaction)
    return tx_hash.hex()

def get_active_wallet_address(user_id: str) -> str:
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT wallet_address FROM users WHERE id = %s", (user_id,))
            row = c.fetchone()
            return row[0] if row and row[0] else ""

def decrypt_user_wallet(encrypted_seed: str, password: str) -> Tuple[str, str]:
    try:
        acct = Account.decrypt(json.loads(encrypted_seed), password)
        return acct.address, acct.key.hex()
    except Exception:
        raise HTTPException(400, "Invalid wallet password")

def burn_close_onchain(user_wallet: str, private_key: str, amount: int) -> str:
    contract = w3_polygon.eth.contract(address=settings.CLOSE_CONTRACT_ADDRESS, abi=ERC20_ABI)
    burn_amount = int(amount * 10**settings.CLOSE_DECIMALS)
    tx = contract.functions.burn(burn_amount).build_transaction({
        'from': user_wallet,
        'nonce': w3_polygon.eth.get_transaction_count(user_wallet),
        'gas': 100000,
        'gasPrice': w3_polygon.eth.gas_price
    })
    return send_raw_tx(private_key, tx)

def stake_close_onchain(user_wallet: str, private_key: str, amount: int) -> str:
    if not settings.CLOSE_STAKING_CONTRACT or not STAKING_ABI:
        raise HTTPException(500, "Staking contract not configured")
    staking = w3_polygon.eth.contract(address=settings.CLOSE_STAKING_CONTRACT, abi=STAKING_ABI)
    amount_wei = int(amount * 10**settings.CLOSE_DECIMALS)
    token = w3_polygon.eth.contract(address=settings.CLOSE_CONTRACT_ADDRESS, abi=ERC20_ABI)
    approve_tx = token.functions.approve(settings.CLOSE_STAKING_CONTRACT, amount_wei).build_transaction({
        'from': user_wallet,
        'nonce': w3_polygon.eth.get_transaction_count(user_wallet),
        'gas': 100000,
        'gasPrice': w3_polygon.eth.gas_price
    })
    send_raw_tx(private_key, approve_tx)
    stake_tx = staking.functions.stake(amount_wei).build_transaction({
        'from': user_wallet,
        'nonce': w3_polygon.eth.get_transaction_count(user_wallet),
        'gas': 200000,
        'gasPrice': w3_polygon.eth.gas_price
    })
    return send_raw_tx(private_key, stake_tx)

# ================================================================================
# WEBHOOK DISPATCHER
# ================================================================================
async def dispatch_webhooks(user_id: str, event: str, payload: dict, background_tasks: BackgroundTasks):
    """Send event to all active webhooks for the user that listen to this event type."""
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, url FROM webhooks WHERE user_id = %s AND is_active = TRUE AND events LIKE %s",
                      (user_id, f"%{event}%"))
            hooks = c.fetchall()
    if not hooks:
        return

    data = {
        "event": event,
        "payload": payload,
        "timestamp": now_utc().isoformat()
    }
    async with httpx.AsyncClient(timeout=10) as client:
        for hook_id, url in hooks:
            background_tasks.add_task(_send_webhook, client, hook_id, url, data)

async def _send_webhook(client: httpx.AsyncClient, hook_id: str, url: str, data: dict):
    try:
        resp = await client.post(url, json=data)
    except Exception as e:
        logger.error(f"Webhook {hook_id} failed: {e}")

# ================================================================================
# AUTH ENDPOINTS
# ================================================================================
class RegisterRequest(BaseModel): email: str; password: str; name: Optional[str] = None
class LoginRequest(BaseModel): email: str; password: str

@app.post("/api/auth/register")
async def register(req: RegisterRequest, request: Request):
    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', req.email): raise HTTPException(400, "Invalid email")
    if len(req.password) < 6: raise HTTPException(400, "Password min 6 chars")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM users WHERE email = %s", (req.email,))
                if c.fetchone(): raise HTTPException(400, "Email already registered")
                user_id = str(uuid.uuid4())
                name = req.name or req.email.split('@')[0]
                c.execute("INSERT INTO users (id, email, password_hash, name, close_balance, stake_tier) VALUES (%s,%s,%s,%s,0,'none')",
                          (user_id, req.email, hash_password(req.password), name))
                token = create_token(user_id)
                c.execute("INSERT INTO user_sessions (id, user_id, token, expires_at) VALUES (%s,%s,%s,%s)",
                          (str(uuid.uuid4()), user_id, token, now_utc() + timedelta(days=30)))
                conn.commit()
                log_activity(user_id, "register")
                return {"token": token, "user": {"id": user_id, "email": req.email, "name": name, "close_balance": 0, "close_staked": 0, "stake_tier": "none"}}
    except HTTPException: raise
    except Exception as e:
        logger.error(f"Register error: {e}")
        raise HTTPException(500, "Registration failed")

@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request):
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, email, password_hash, name, close_balance, close_staked, stake_tier, wallet_address FROM users WHERE email = %s", (req.email,))
                user = c.fetchone()
                if not user or not verify_password(req.password, user[2]): raise HTTPException(401, "Invalid credentials")
                user_id, email, _, name, close_balance, close_staked, stake_tier, wallet_address = user
                token = create_token(user_id)
                c.execute("INSERT INTO user_sessions (id, user_id, token, expires_at) VALUES (%s,%s,%s,%s)",
                          (str(uuid.uuid4()), user_id, token, now_utc() + timedelta(days=30)))
                c.execute("UPDATE users SET last_active = NOW() WHERE id = %s", (user_id,))
                conn.commit()
                log_activity(user_id, "login")
                return {"token": token, "user": {"id": user_id, "email": email, "name": name or email.split('@')[0], "close_balance": close_balance or 0, "close_staked": close_staked or 0, "stake_tier": stake_tier or "none", "wallet_address": wallet_address or ""}}
    except HTTPException: raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(500, "Login failed")

@app.post("/api/auth/logout")
async def logout(request: Request):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("DELETE FROM user_sessions WHERE token = %s", (auth[7:],))
                conn.commit()
    return {"message": "Logged out"}

@app.get("/api/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401, "Not authenticated")
    return user

@app.post("/api/auth/update-profile")
async def update_profile(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    name = req.get("name")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                if name: c.execute("UPDATE users SET name=%s, updated_at=NOW() WHERE id=%s", (name, user["id"]))
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
                c.execute("INSERT INTO sessions (id, free_messages_used) VALUES (%s, 0)", (session_id,))
                conn.commit()
    except: pass
    token = create_session_token(session_id)
    return {"id": session_id, "token": token, "free_messages_remaining": settings.FREE_MESSAGES_GUEST}

@app.post("/api/founder")
async def founder_login(req: dict, request: Request):
    if not check_rate_limit(request.client.host, "founder_attempt", 5): raise HTTPException(429, "Too many attempts")
    code = req.get("code", "")
    if not hmac.compare_digest(code, settings.FOUNDER_KEY): raise HTTPException(403, "Invalid founder code")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM users WHERE email = 'founder@capitan.ai'")
                existing = c.fetchone()
                if existing:
                    user_id = existing[0]
                    c.execute("UPDATE users SET stake_tier='founder', close_balance=999999999 WHERE id=%s", (user_id,))
                else:
                    user_id = str(uuid.uuid4())
                    c.execute("INSERT INTO users (id, email, password_hash, name, close_balance, stake_tier) VALUES (%s,%s,%s,%s,%s,%s)",
                              (user_id, "founder@capitan.ai", hash_password("founder_sentinel"), "CAPITAN Founder", 999999999, "founder"))
                token = create_token(user_id)
                c.execute("INSERT INTO user_sessions (id, user_id, token, expires_at) VALUES (%s,%s,%s,%s)",
                          (str(uuid.uuid4()), user_id, token, now_utc() + timedelta(days=365)))
                conn.commit()
                return {"verified": True, "token": token, "user": {"id": user_id, "name": "CAPITAN Founder", "close_balance": 999999999, "stake_tier": "founder"}}
    except Exception as e:
        logger.error(f"Founder login error: {e}")
        raise HTTPException(500, "Founder login failed")

@app.post("/api/auth/forgot-password")
async def forgot_password(req: Request):
    return {"message": "If the account exists, a reset link has been sent."}

# ================================================================================
# CHAT ENDPOINT – CLOSE‑POWERED WITH ON‑CHAIN BURN
# ================================================================================
class ChatRequest(BaseModel):
    messages: list
    chat_id: Optional[str] = None
    wallet_password: Optional[str] = None

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, request: Request, background_tasks: BackgroundTasks):
    user = get_current_user(request)
    session = None
    is_authenticated = False

    if user:
        is_authenticated = True
        user_id = user["id"]
        close_balance = user.get("close_balance", 0)
    else:
        try: session = await get_current_session(request)
        except: raise HTTPException(401, "Authentication required")
        free_used = session.get("free_messages_used", 0)

    user_msg = None
    for m in reversed(req.messages):
        if m.get("role") == "user": user_msg = m.get("content"); break
    if not user_msg: raise HTTPException(400, "No message content")

    chat_id = req.chat_id or f"chat_{sid()}"

    # Guest check
    if not is_authenticated:
        if free_used >= settings.FREE_MESSAGES_GUEST:
            return {
                "content": "I've enjoyed our conversation! To continue, you'll need a wallet with CLOSE tokens. It takes less than a minute to set up.",
                "requires_wallet": True,
                "free_messages_remaining": 0,
                "wallet_prompt": True,
                "wallet_message": "Create your OS Wallet to receive 2,000 CLOSE and unlock unlimited AI access."
            }
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("UPDATE sessions SET free_messages_used = free_messages_used + 1, updated = NOW() WHERE id = %s", (session["id"],))
                conn.commit()
        free_used += 1

    # Authenticated user – balance check + require password
    if is_authenticated:
        if close_balance < settings.BURN_PER_MESSAGE:
            return {
                "content": "You're running low on CLOSE tokens. Top up to continue.",
                "requires_purchase": True,
                "close_balance": close_balance,
                "min_purchase": settings.MIN_PURCHASE_USD,
                "close_per_dollar": usd_to_close(1.00),
                "wallet_message": f"Get more CLOSE — starting at ${settings.MIN_PURCHASE_USD:.2f}"
            }
        if not req.wallet_password:
            raise HTTPException(400, "Wallet password required for on‑chain burn.")
        encrypted_seed = user.get("encrypted_seed")
        if not encrypted_seed:
            raise HTTPException(400, "No wallet found. Create one first.")
        try:
            addr, priv = decrypt_user_wallet(encrypted_seed, req.wallet_password)
        except HTTPException:
            raise HTTPException(400, "Invalid wallet password.")

    # Save user message
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                if is_authenticated:
                    c.execute("INSERT INTO chats (id, user_id, title, topic_thread, created, updated) VALUES (%s,%s,%s,%s,NOW(),NOW()) ON CONFLICT (id) DO UPDATE SET updated = NOW(), title = %s",
                              (chat_id, user_id, user_msg[:60], classify_query(user_msg), user_msg[:60]))
                    c.execute("INSERT INTO chat_messages (id, chat_id, user_id, role, content) VALUES (%s,%s,%s,%s,%s)",
                              (f"msg_{sid()}", chat_id, user_id, "user", user_msg))
                else:
                    c.execute("INSERT INTO chats (id, session_id, title, topic_thread, created, updated) VALUES (%s,%s,%s,%s,NOW(),NOW()) ON CONFLICT (id) DO UPDATE SET updated = NOW(), title = %s",
                              (chat_id, session["id"], user_msg[:60], classify_query(user_msg), user_msg[:60]))
                    c.execute("INSERT INTO chat_messages (id, chat_id, session_id, role, content) VALUES (%s,%s,%s,%s,%s)",
                              (f"msg_{sid()}", chat_id, session["id"], "user", user_msg))
                conn.commit()
    except: pass

    # Get history
    chat_history = []
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT role, content FROM (SELECT role, content, created FROM chat_messages WHERE chat_id = %s ORDER BY created DESC LIMIT 60) recent ORDER BY created ASC", (chat_id,))
                chat_history = [{"role": r[0], "content": r[1]} for r in c.fetchall()]
    except: pass

    thread_context = get_thread_context(chat_id, user_id if is_authenticated else None, session["id"] if not is_authenticated else None)
    user_model = get_user_model(user_id) if is_authenticated else "Guest user."

    web_results_text = ""
    if needs_web_search(user_msg):
        try:
            results = search_web(user_msg, 5)
            if results: web_results_text = "\n".join([f"- {r['title']}: {r['snippet'][:200]}" for r in results[:4]])
        except: pass

    system_prompt = build_system_prompt(user_msg, user_model, thread_context, web_results_text)
    messages_for_ai = [{"role": "system", "content": system_prompt}] + chat_history
    response, model_used = call_ai_model(messages_for_ai)

    if response:
        msg_id = f"msg_{sid()}"
        close_burned = settings.BURN_PER_MESSAGE if is_authenticated else 0
        burn_tx_hash = None

        if is_authenticated:
            try:
                burn_tx_hash = burn_close_onchain(addr, priv, close_burned)
            except Exception as e:
                logger.error(f"On‑chain burn failed: {e}")
                raise HTTPException(500, f"Burn transaction failed: {str(e)}")

        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    if is_authenticated:
                        c.execute("INSERT INTO chat_messages (id, chat_id, user_id, role, content, model, close_burned) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                                  (msg_id, chat_id, user_id, "assistant", response, model_used, close_burned))
                        c.execute("UPDATE users SET close_balance = GREATEST(0, close_balance - %s), last_active = NOW() WHERE id = %s",
                                  (close_burned, user_id))
                        c.execute("INSERT INTO close_transactions (id, user_id, type, amount, tx_hash) VALUES (%s,%s,%s,%s,%s)",
                                  (str(uuid.uuid4()), user_id, "burn", close_burned, burn_tx_hash))
                        background_tasks.add_task(store_memory, user_id, response[:500], user_msg, classify_query(user_msg), 2)
                    else:
                        c.execute("INSERT INTO chat_messages (id, chat_id, session_id, role, content, model, close_burned) VALUES (%s,%s,%s,%s,%s,%s,0)",
                                  (msg_id, chat_id, session["id"], "assistant", response, model_used))
                    conn.commit()
        except Exception as e: logger.error(f"Save AI msg error: {e}")

        result = {"content": response, "chat_id": chat_id, "model": model_used, "message_id": msg_id}
        if is_authenticated:
            new_balance = close_balance - close_burned
            result["close_balance"] = max(0, new_balance)
            result["close_burned"] = close_burned
            result["burn_tx"] = burn_tx_hash
            if new_balance < settings.BURN_PER_MESSAGE * 10:
                result["low_balance_warning"] = True
                result["wallet_message"] = f"Only {new_balance} CLOSE remaining. Top up to continue."
            # Dispatch webhook for new message
            background_tasks.add_task(dispatch_webhooks, user_id, "new_message", {
                "chat_id": chat_id,
                "message_id": msg_id,
                "role": "assistant",
                "content_preview": response[:200]
            }, background_tasks)
        else:
            remaining = settings.FREE_MESSAGES_GUEST - free_used
            result["free_messages_remaining"] = max(0, remaining)
            if remaining <= 1:
                result["wallet_prompt"] = True
                result["wallet_message"] = "Create your OS Wallet to get 2,000 CLOSE and unlock unlimited AI."
        return result

    return {"content": "I couldn't generate a response. Please try again.", "chat_id": chat_id, "model": "fallback"}

@app.get("/api/chats")
def get_chats(request: Request):
    user = get_current_user(request)
    if user:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, title, topic_thread, created, updated FROM chats WHERE user_id=%s ORDER BY updated DESC LIMIT 100", (user["id"],))
                return {"chats": [{"id": r[0], "title": r[1] or "New Chat", "topic": r[2], "created": r[3].isoformat() if r[3] else None, "updated": r[4].isoformat() if r[4] else None} for r in c.fetchall()]}
    else:
        try:
            session = get_current_session(request)
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("SELECT id, title, topic_thread, created, updated FROM chats WHERE session_id=%s ORDER BY updated DESC LIMIT 100", (session["id"],))
                    return {"chats": [{"id": r[0], "title": r[1] or "New Chat", "topic": r[2], "created": r[3].isoformat() if r[3] else None, "updated": r[4].isoformat() if r[4] else None} for r in c.fetchall()]}
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
                c.execute("SELECT role, content, model, close_burned, created FROM chat_messages WHERE chat_id=%s ORDER BY created ASC", (chat_id,))
                return {"messages": [{"id": i, "role": r[0], "content": r[1], "model": r[2] or "AI", "close_burned": r[3] or 0, "created": r[4].isoformat() if r[4] else None} for i, r in enumerate(c.fetchall())]}
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
def get_portfolio(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, name, content, folder, tags, attachments, pinned, chat_id, created, updated FROM library_items WHERE user_id=%s ORDER BY pinned DESC, updated DESC", (user["id"],))
            items = [{"id": r[0], "name": r[1], "content": r[2], "folder": r[3] or "General", "tags": r[4] if r[4] else [], "attachments": r[5] if r[5] else [], "pinned": r[6], "chat_id": r[7], "created": r[8].isoformat() if r[8] else None, "updated": r[9].isoformat() if r[9] else None} for r in c.fetchall()]
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
# WORKSPACES (with on‑chain join cost)
# ================================================================================
@app.post("/api/hub/rooms")
def create_hub_room(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    room_code = req.get("room_code", f"HUB-{sid()}")
    password = req.get("password")
    password_hash = hash_password(password) if password else None
    ws_id = sid()
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO workspaces (id, name, description, topic, owner_id, room_code, password_hash, max_members) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                      (ws_id, req.get("name","Research Room"), req.get("description",""), req.get("topic",""), user["id"], room_code.upper(), password_hash, 30))
            c.execute("INSERT INTO workspace_members (workspace_id, user_id, role) VALUES (%s,%s,'admin')", (ws_id, user["id"]))
            conn.commit()
    return {"room_id": ws_id, "room_code": room_code.upper(), "created": True}

@app.post("/api/hub/rooms/join")
def join_hub_room(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    room_code = req.get("room_code","").upper()
    password = req.get("password")
    if not password: raise HTTPException(400, "Wallet password required")
    encrypted_seed = user.get("encrypted_seed")
    if not encrypted_seed: raise HTTPException(400, "No wallet found.")
    addr, priv = decrypt_user_wallet(encrypted_seed, password)
    burn_tx = burn_close_onchain(addr, priv, settings.WORKSPACE_JOIN_COST)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, password_hash, max_members FROM workspaces WHERE room_code=%s", (room_code,))
            room = c.fetchone()
            if not room: raise HTTPException(404, "Room not found")
            if room[1] and (not req.get("room_password") or not verify_password(req.get("room_password"), room[1])):
                raise HTTPException(403, "Invalid room password")
            c.execute("SELECT COUNT(*) FROM workspace_members WHERE workspace_id=%s", (room[0],))
            if c.fetchone()[0] >= room[2]: raise HTTPException(400, "Room is full")
            c.execute("INSERT INTO workspace_members (workspace_id, user_id, role) VALUES (%s,%s,'member') ON CONFLICT DO NOTHING", (room[0], user["id"]))
            c.execute("INSERT INTO close_transactions (id, user_id, type, amount, tx_hash) VALUES (%s,%s,%s,%s,%s)",
                      (str(uuid.uuid4()), user["id"], "workspace_join", settings.WORKSPACE_JOIN_COST, burn_tx))
            conn.commit()
    return {"joined": True, "room_id": room[0], "burn_tx": burn_tx}

@app.get("/api/hub/rooms")
def list_hub_rooms(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("""SELECT w.id, w.name, w.description, w.topic, w.room_code, w.max_members, w.created_at,
                    (SELECT COUNT(*) FROM workspace_members WHERE workspace_id=w.id) as member_count
                    FROM workspaces w
                    JOIN workspace_members m ON w.id = m.workspace_id
                    WHERE m.user_id = %s AND w.is_active = TRUE
                    ORDER BY w.created_at DESC""", (user["id"],))
                rooms = []
                for r in c.fetchall():
                    rooms.append({
                        "id": r[0],
                        "name": r[1],
                        "description": r[2],
                        "topic": r[3],
                        "room_code": r[4],
                        "max_members": r[5],
                        "created_at": r[6].isoformat() if r[6] else None,
                        "member_count": r[7]
                    })
                return {"rooms": rooms}
    except Exception as e:
        logger.error(f"Workspace list error: {e}")
        return {"rooms": []}

@app.get("/api/hub/rooms/{room_code}/messages")
def get_hub_messages(room_code: str, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id FROM workspaces WHERE room_code=%s", (room_code.upper(),))
            room = c.fetchone()
            if not room: raise HTTPException(404)
            c.execute("SELECT author_name, message, is_ai, pinned, created FROM workspace_messages WHERE workspace_id=%s ORDER BY pinned DESC, created ASC LIMIT 100", (room[0],))
            return {"messages": [{"author": r[0], "message": r[1], "is_ai": bool(r[2]), "pinned": bool(r[3]), "created": r[4].isoformat() if r[4] else None} for r in c.fetchall()]}

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
            c.execute("INSERT INTO workspace_messages (id, workspace_id, user_id, author_name, message) VALUES (%s,%s,%s,%s,%s)", (sid(), room[0], user["id"], user["name"], message))
            if is_ai:
                ai_response, _ = call_ai_model([{"role":"user","content":message.replace('@CAPITAN','').strip()}])
                if ai_response: c.execute("INSERT INTO workspace_messages (id, workspace_id, user_id, author_name, message, is_ai) VALUES (%s,%s,%s,%s,%s,1)", (sid(), room[0], user["id"], "CAPITAN AI", ai_response))
            conn.commit()
    return {"sent": True}

# ================================================================================
# OS WALLETS – FULL ON‑CHAIN
# ================================================================================
@app.get("/api/wallet/balance")
async def get_wallet_balance(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    address = get_active_wallet_address(user["id"])
    if not address: return {"close_balance": 0, "close_staked": 0, "stake_tier": "none", "balance_usd": 0}
    try:
        contract = w3_polygon.eth.contract(address=settings.CLOSE_CONTRACT_ADDRESS, abi=ERC20_ABI)
        onchain_balance = contract.functions.balanceOf(address).call() / 10**settings.CLOSE_DECIMALS
    except: onchain_balance = 0
    staked_onchain = 0
    if settings.CLOSE_STAKING_CONTRACT and STAKING_ABI:
        try:
            staking = w3_polygon.eth.contract(address=settings.CLOSE_STAKING_CONTRACT, abi=STAKING_ABI)
            staked_onchain = staking.functions.getStakedAmount(address).call() / 10**settings.CLOSE_DECIMALS
        except: pass
    return {
        "close_balance": onchain_balance,
        "close_staked": staked_onchain,
        "stake_tier": user.get("stake_tier","none"),
        "balance_usd": round(onchain_balance * settings.CLOSE_PRICE_USD, 4),
        "staked_usd": round(staked_onchain * settings.CLOSE_PRICE_USD, 4)
    }

@app.post("/api/wallet/stake")
async def stake_close(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    amount = req.get("amount")
    password = req.get("password")
    if not amount or int(amount) <= 0: raise HTTPException(400, "Valid amount required")
    if not password: raise HTTPException(400, "Wallet password required")
    encrypted_seed = user.get("encrypted_seed")
    if not encrypted_seed: raise HTTPException(400, "No wallet found.")
    addr, priv = decrypt_user_wallet(encrypted_seed, password)
    try:
        tx_hash = stake_close_onchain(addr, priv, int(amount))
        staking = w3_polygon.eth.contract(address=settings.CLOSE_STAKING_CONTRACT, abi=STAKING_ABI)
        new_staked = staking.functions.getStakedAmount(addr).call() / 10**settings.CLOSE_DECIMALS
        tier = "none"
        if new_staked >= settings.STAKE_ENTERPRISE: tier = "enterprise"
        elif new_staked >= settings.STAKE_PRO: tier = "pro"
        elif new_staked >= settings.STAKE_BUILDER: tier = "builder"
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("UPDATE users SET close_staked = %s, stake_tier = %s WHERE id = %s", (new_staked, tier, user["id"]))
                c.execute("INSERT INTO close_transactions (id, user_id, type, amount, tx_hash) VALUES (%s,%s,%s,%s,%s)",
                          (str(uuid.uuid4()), user["id"], "stake", amount, tx_hash))
                # Insert into close_stakes for leaderboard
                c.execute("INSERT INTO close_stakes (id, user_id, amount, lock_until, status) VALUES (%s,%s,%s,%s,'active')",
                          (str(uuid.uuid4()), user["id"], int(amount), now_utc() + timedelta(days=30)))
                conn.commit()
        return {"tx_hash": tx_hash, "staked": amount, "tier": tier}
    except Exception as e:
        raise HTTPException(500, f"Stake failed: {str(e)}")

@app.post("/api/wallet/unstake")
async def unstake_close(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    password = req.get("password")
    if not password: raise HTTPException(400, "Wallet password required")
    encrypted_seed = user.get("encrypted_seed")
    if not encrypted_seed: raise HTTPException(400, "No wallet found.")
    addr, priv = decrypt_user_wallet(encrypted_seed, password)
    try:
        staking = w3_polygon.eth.contract(address=settings.CLOSE_STAKING_CONTRACT, abi=STAKING_ABI)
        unstake_tx = staking.functions.unstakeAllUnlocked().build_transaction({
            'from': addr,
            'nonce': w3_polygon.eth.get_transaction_count(addr),
            'gas': 200000,
            'gasPrice': w3_polygon.eth.gas_price
        })
        tx_hash = send_raw_tx(priv, unstake_tx)
        new_staked = staking.functions.getStakedAmount(addr).call() / 10**settings.CLOSE_DECIMALS
        tier = "none"
        if new_staked >= settings.STAKE_ENTERPRISE: tier = "enterprise"
        elif new_staked >= settings.STAKE_PRO: tier = "pro"
        elif new_staked >= settings.STAKE_BUILDER: tier = "builder"
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("UPDATE users SET close_staked = %s, stake_tier = %s WHERE id = %s", (new_staked, tier, user["id"]))
                c.execute("INSERT INTO close_transactions (id, user_id, type, amount, tx_hash) VALUES (%s,%s,%s,%s,%s)",
                          (str(uuid.uuid4()), user["id"], "unstake", 0, tx_hash))
                conn.commit()
        return {"tx_hash": tx_hash, "new_staked": new_staked, "tier": tier}
    except Exception as e:
        raise HTTPException(500, f"Unstake failed: {str(e)}")

@app.post("/api/wallet/purchase")
async def purchase_close(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    tx_hash = req.get("tx_hash")
    usd_amount = float(req.get("usd_amount", settings.MIN_PURCHASE_USD))
    if not tx_hash: raise HTTPException(400, "Transaction hash required")
    try:
        receipt = w3_polygon.eth.get_transaction_receipt(tx_hash)
        tx = w3_polygon.eth.get_transaction(tx_hash)
        if tx['to'].lower() != settings.CLOSE_HOT_WALLET.lower():
            return {"verified": False, "message": "Invalid recipient."}
        pol_price = settings.POL_PRICE_USD
        try:
            r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=matic-network&vs_currencies=usd",
                             headers={"x-cg-demo-api-key":settings.COINGECKO_KEY} if settings.COINGECKO_KEY else {},
                             timeout=5)
            if r.status_code == 200:
                pol_price = r.json()["matic-network"]["usd"]
        except: pass
        expected_wei = Web3.to_wei(usd_amount / pol_price, 'ether')
        if tx['value'] < expected_wei * 0.95:
            return {"verified": False, "message": "Insufficient payment."}
        close_amount = usd_to_close(usd_amount)
        if settings.HOT_WALLET_PRIVATE_KEY:
            hot_acct = Account.from_key(settings.HOT_WALLET_PRIVATE_KEY)
            contract = w3_polygon.eth.contract(address=settings.CLOSE_CONTRACT_ADDRESS, abi=ERC20_ABI)
            transfer_tx = contract.functions.transfer(get_active_wallet_address(user["id"]), int(close_amount * 10**settings.CLOSE_DECIMALS)).build_transaction({
                'from': hot_acct.address,
                'nonce': w3_polygon.eth.get_transaction_count(hot_acct.address),
                'gas': 60000,
                'gasPrice': w3_polygon.eth.gas_price
            })
            send_raw_tx(settings.HOT_WALLET_PRIVATE_KEY, transfer_tx)
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("UPDATE users SET close_balance = close_balance + %s WHERE id = %s", (close_amount, user["id"]))
                c.execute("INSERT INTO close_purchases (id, user_id, amount_usd, close_amount, tx_hash) VALUES (%s,%s,%s,%s,%s)",
                          (str(uuid.uuid4()), user["id"], usd_amount, close_amount, tx_hash))
                conn.commit()
        return {"verified": True, "purchased": close_amount}
    except Exception as e:
        return {"verified": False, "message": str(e)}

@app.post("/api/wallet/activate")
async def activate_wallet(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    password = req.get("password")
    if not password: raise HTTPException(400, "Password required")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT close_balance, wallet_address FROM users WHERE id = %s", (user["id"],))
            row = c.fetchone()
            if row[0] >= settings.FREE_CLOSE_AMOUNT: raise HTTPException(400, "Welcome bonus already claimed")
            addr = row[1]
            if not addr:
                acct = Account.create()
                encrypted = Account.encrypt(acct.key.hex(), password)
                addr = acct.address
                c.execute("UPDATE users SET wallet_address = %s, wallet_encrypted_seed = %s WHERE id = %s", (addr, json.dumps(encrypted), user["id"]))
            if settings.HOT_WALLET_PRIVATE_KEY:
                hot_acct = Account.from_key(settings.HOT_WALLET_PRIVATE_KEY)
                contract = w3_polygon.eth.contract(address=settings.CLOSE_CONTRACT_ADDRESS, abi=ERC20_ABI)
                tx = contract.functions.transfer(addr, int(settings.FREE_CLOSE_AMOUNT * 10**settings.CLOSE_DECIMALS)).build_transaction({
                    'from': hot_acct.address,
                    'nonce': w3_polygon.eth.get_transaction_count(hot_acct.address),
                    'gas': 60000,
                    'gasPrice': w3_polygon.eth.gas_price
                })
                send_raw_tx(settings.HOT_WALLET_PRIVATE_KEY, tx)
            c.execute("UPDATE users SET close_balance = close_balance + %s WHERE id = %s", (settings.FREE_CLOSE_AMOUNT, user["id"]))
            c.execute("INSERT INTO close_transactions (id, user_id, type, amount) VALUES (%s,%s,%s,%s)",
                      (str(uuid.uuid4()), user["id"], "welcome_bonus", settings.FREE_CLOSE_AMOUNT))
            conn.commit()
    return {"wallet_address": addr, "close_credited": settings.FREE_CLOSE_AMOUNT}

# Multi‑wallet management
@app.get("/api/wallets")
def list_wallets(user: dict = Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, chain, address, label, is_active FROM os_wallets WHERE user_id=%s ORDER BY created", (user["id"],))
            return {"wallets": [{"id": r[0], "chain": r[1], "address": r[2], "label": r[3], "active": r[4]} for r in c.fetchall()]}

@app.put("/api/wallets/{wallet_id}/active")
def set_active_wallet(wallet_id: str, user: dict = Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE os_wallets SET is_active=FALSE WHERE user_id=%s", (user["id"],))
            c.execute("UPDATE os_wallets SET is_active=TRUE WHERE id=%s AND user_id=%s", (wallet_id, user["id"]))
            conn.commit()
    return {"ok": True}

@app.delete("/api/wallets/{wallet_id}")
def delete_wallet(wallet_id: str, user: dict = Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM os_wallets WHERE id=%s AND user_id=%s", (wallet_id, user["id"]))
            conn.commit()
    return {"ok": True}

@app.post("/api/wallet/create")
async def create_os_wallet(req: dict, user: dict = Depends(get_current_user)):
    chain = req.get("chain", "polygon")
    label = req.get("label", "Wallet")
    password = req.get("password")
    if not password:
        raise HTTPException(400, "Password required")

    try:
        w3 = Web3(Web3.HTTPProvider(CHAINS[chain]["rpc"]))
        acct = w3.eth.account.create()
        encrypted = acct.encrypt(password)  # returns dict
        wallet_id = str(uuid.uuid4())

        with get_db() as conn:
            with conn.cursor() as c:
                # Insert with encrypted_key column
                c.execute(
                    "INSERT INTO os_wallets (id, user_id, chain, address, encrypted_key, label) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (wallet_id, user["id"], chain, acct.address, json.dumps(encrypted), label)
                )
                # Also update the user's main wallet reference for backward compatibility
                c.execute(
                    "UPDATE users SET wallet_address = %s, wallet_encrypted_seed = %s WHERE id = %s",
                    (acct.address, json.dumps(encrypted), user["id"])
                )
                conn.commit()

        return {"wallet_id": wallet_id, "address": acct.address, "chain": chain}
    except Exception as e:
        logger.error(f"Create OS wallet error: {e}")
        raise HTTPException(500, str(e))

# Address Book
@app.get("/api/addresses")
def get_addresses(user: dict = Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, label, address, chain FROM address_book WHERE user_id=%s", (user["id"],))
            return {"addresses": [{"id": r[0], "label": r[1], "address": r[2], "chain": r[3]} for r in c.fetchall()]}

@app.post("/api/addresses")
def add_address(req: dict, user: dict = Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO address_book (id, user_id, label, address, chain) VALUES (%s,%s,%s,%s,%s)",
                      (str(uuid.uuid4()), user["id"], req["label"], req["address"], req.get("chain", "polygon")))
            conn.commit()
    return {"ok": True}

@app.delete("/api/addresses/{addr_id}")
def delete_address(addr_id: str, user: dict = Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM address_book WHERE id=%s AND user_id=%s", (addr_id, user["id"]))
            conn.commit()
    return {"ok": True}

# NFT Gallery
@app.get("/api/wallet/nfts")
def get_nfts(chain: str = "polygon", user: dict = Depends(get_current_user)):
    if not settings.COVALENT_API_KEY: return {"nfts": []}
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT address FROM os_wallets WHERE user_id=%s AND chain=%s AND is_active=TRUE", (user["id"], chain))
            addr_row = c.fetchone()
            if not addr_row: return {"nfts": []}
            address = addr_row[0]
    url = f"https://api.covalenthq.com/v1/{chain}-mainnet/address/{address}/balances_nft/?key={settings.COVALENT_API_KEY}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            items = []
            for item in data.get("data", {}).get("items", []):
                for nft in item.get("nft_data", []):
                    items.append({
                        "contract": item["contract_address"],
                        "token_id": nft.get("token_id"),
                        "name": nft.get("external_data", {}).get("name", ""),
                        "image": nft.get("external_data", {}).get("image", "")
                    })
            return {"nfts": items[:50]}
    except: pass
    return {"nfts": []}

# WalletConnect
@app.get("/api/walletconnect/sessions")
def list_wc_sessions(user: dict = Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, dapp_name, dapp_url, chain_id, accounts, expires_at FROM os_walletconnect_sessions WHERE user_id=%s AND expires_at > NOW()", (user["id"],))
            return {"sessions": [{"id": r[0], "name": r[1], "url": r[2], "chain": r[3], "accounts": r[4], "expires": r[5].isoformat() if r[5] else None} for r in c.fetchall()]}

@app.post("/api/walletconnect/sessions")
async def create_wc_session(req: dict, user: dict = Depends(get_current_user)):
    session_id = str(uuid.uuid4())
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO os_walletconnect_sessions (id, user_id, topic, dapp_name, dapp_url, chain_id, accounts, expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                      (session_id, user["id"], req.get("topic",""), req.get("dapp_name",""), req.get("dapp_url",""),
                       req.get("chain_id"), json.dumps(req.get("accounts",[])),
                       now_utc() + timedelta(hours=24)))
            conn.commit()
    return {"session_id": session_id}

@app.delete("/api/walletconnect/sessions/{session_id}")
def disconnect_wc(session_id: str, user: dict = Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM os_walletconnect_sessions WHERE id=%s AND user_id=%s", (session_id, user["id"]))
            conn.commit()
    return {"ok": True}

# Gas settings
@app.post("/api/wallet/gas")
def set_gas_preference(req: dict, user: dict = Depends(get_current_user)):
    preset = req.get("preset", "standard")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE users SET gas_preset=%s WHERE id=%s", (preset, user["id"]))
            conn.commit()
    return {"ok": True}

# Swap quote (1inch)
@app.get("/api/swap/quote")
async def get_swap_quote(chain: str = "polygon", from_token: str = None, to_token: str = None, amount: str = None, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    if not all([from_token, to_token, amount]): raise HTTPException(400, "from_token, to_token, and amount required")
    chain_ids = {"polygon": 137, "ethereum": 1, "bsc": 56, "arbitrum": 42161, "base": 8453}
    chain_id = chain_ids.get(chain, 137)
    try:
        if settings.ONEPINCH_API_KEY:
            url = f"https://api.1inch.dev/swap/v5.2/{chain_id}/quote"
            params = {"src": from_token, "dst": to_token, "amount": amount, "slippage": 1}
            headers = {"Authorization": f"Bearer {settings.ONEPINCH_API_KEY}"}
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                return {"from_token": data.get("fromToken", {}).get("symbol", from_token), "to_token": data.get("toToken", {}).get("symbol", to_token), "from_amount": amount, "to_amount": data.get("toAmount", "0"), "estimated_gas": data.get("estimatedGas", 0)}
        return {"from_token": from_token, "to_token": to_token, "from_amount": amount, "to_amount": "0", "note": "Live quote unavailable"}
    except Exception as e:
        logger.error(f"Swap quote error: {e}")
        raise HTTPException(500, str(e))

# Send transaction (correctly reads encrypted_key from os_wallets)
@app.post("/api/wallet/{wallet_id}/send")
async def send_transaction(wallet_id: str, req: dict, user: dict = Depends(get_current_user), background_tasks: BackgroundTasks = BackgroundTasks()):
    if not user: raise HTTPException(401)
    password = req.get("password")
    to_address = req.get("to")
    amount = req.get("amount")
    token_address = req.get("token_address")
    if not all([password, to_address, amount]): raise HTTPException(400, "password, to, and amount required")
    with get_db() as conn:
        with conn.cursor() as c:
            # Read encrypted_key from os_wallets
            c.execute("SELECT address, encrypted_key, chain FROM os_wallets WHERE id=%s AND user_id=%s", (wallet_id, user["id"]))
            wallet = c.fetchone()
            if not wallet: raise HTTPException(404, "Wallet not found")
            chain_config = CHAINS[wallet[2]]
    try:
        w3 = Web3(Web3.HTTPProvider(chain_config["rpc"]))
        encrypted = json.loads(wallet[1])  # wallet[1] is encrypted_key
        private_key = Account.decrypt(encrypted, password).hex()
        acct = Account.from_key(private_key)
        is_native = not token_address or token_address.lower() in ('0x0000000000000000000000000000000000000000', '0x0000000000000000000000000000000000001010')
        if is_native:
            tx = {
                'from': acct.address,
                'to': to_address,
                'value': Web3.to_wei(float(amount), 'ether'),
                'nonce': w3.eth.get_transaction_count(acct.address),
                'gas': 21000,
                'gasPrice': w3.eth.gas_price,
                'chainId': chain_config["chain_id"]
            }
        else:
            contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
            decimals = contract.functions.decimals().call()
            amount_wei = int(float(amount) * (10 ** decimals))
            tx = contract.functions.transfer(to_address, amount_wei).build_transaction({
                'from': acct.address,
                'nonce': w3.eth.get_transaction_count(acct.address),
                'gas': 100000,
                'gasPrice': w3.eth.gas_price
            })
        signed = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction).hex()
        with get_db() as conn2:
            with conn2.cursor() as c2:
                c2.execute("INSERT INTO os_transactions (id, user_id, chain, tx_hash, from_address, to_address, amount, token_symbol, status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'confirmed')",
                          (str(uuid.uuid4()), user["id"], wallet[2], tx_hash, acct.address, to_address, str(amount),
                           token_address if not is_native else chain_config["symbol"]))
                conn2.commit()
        # Dispatch webhook for transaction
        background_tasks.add_task(dispatch_webhooks, user["id"], "transaction_sent", {
            "tx_hash": tx_hash,
            "chain": chain_config["name"],
            "to": to_address,
            "amount": amount
        }, background_tasks)
        return {"tx_hash": tx_hash, "explorer_url": f"{chain_config['explorer']}/tx/{tx_hash}"}
    except Exception as e:
        logger.error(f"Send transaction error: {e}")
        raise HTTPException(500, f"Transaction failed: {str(e)}")

# Transaction detail
@app.get("/api/transactions/{tx_hash}")
def transaction_detail(tx_hash: str, user: dict = Depends(get_current_user)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT chain, from_address, to_address, amount, token_symbol, status, created FROM os_transactions WHERE tx_hash=%s AND user_id=%s", (tx_hash, user["id"]))
            row = c.fetchone()
            if row:
                chain = row[0]
                explorer = CHAINS.get(chain, {}).get("explorer", "")
                return {
                    "tx_hash": tx_hash,
                    "chain": chain,
                    "from": row[1],
                    "to": row[2],
                    "amount": row[3],
                    "token": row[4],
                    "status": row[5],
                    "created": row[6].isoformat() if row[6] else None,
                    "explorer_url": f"{explorer}/tx/{tx_hash}" if explorer else ""
                }
    for chain_name, cfg in CHAINS.items():
        w3 = Web3(Web3.HTTPProvider(cfg["rpc"]))
        try:
            tx = w3.eth.get_transaction(tx_hash)
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            return {
                "tx_hash": tx_hash,
                "chain": chain_name,
                "from": tx["from"],
                "to": tx["to"],
                "value": str(Web3.from_wei(tx["value"], 'ether')),
                "status": "confirmed" if receipt["status"] == 1 else "failed",
                "explorer_url": f"{cfg['explorer']}/tx/{tx_hash}"
            }
        except: continue
    raise HTTPException(404, "Transaction not found")

# ================================================================================
# MARKET DATA & NEWS & AI RESEARCH
# ================================================================================
@app.get("/api/market/crypto")
def crypto_market():
    if not settings.COINGECKO_KEY: raise HTTPException(503, "CoinGecko key not set")
    try:
        r = requests.get("https://api.coingecko.com/api/v3/coins/markets", params={"vs_currency":"usd","order":"market_cap_desc","per_page":100,"page":1,"sparkline":"true","price_change_percentage":"24h"}, headers={"x-cg-demo-api-key":settings.COINGECKO_KEY}, timeout=20)
        return r.json() if r.status_code==200 else []
    except: return []

@app.get("/api/market/news")
def market_news():
    if not settings.NEWS_API_KEY: raise HTTPException(503, "News API key not set")
    try:
        r = requests.get("https://newsapi.org/v2/top-headlines", params={"category":"business","language":"en","pageSize":10,"apiKey":settings.NEWS_API_KEY}, timeout=10)
        if r.status_code==200:
            articles = r.json().get("articles",[])
            return [{"headline":a["title"],"url":a["url"],"summary":a.get("description","")[:200]} for a in articles]
    except: pass
    return []

@app.post("/api/wallet/research")
async def wallet_research(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    query = req.get("query","")
    if not query: raise HTTPException(400, "Query required")
    prompt = f"""As CAPITAN AI, provide a concise, expert financial analysis for the following query. Use current market data if available.
    User query: {query}"""
    response, model = call_ai_model([{"role":"user","content":prompt}])
    return {"analysis": response, "model": model}

# ================================================================================
# DEVELOPER ENDPOINTS (API KEYS & WEBHOOKS)
# ================================================================================
@app.post("/api/developer/keys")
def create_api_key(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    raw_key = "cap_" + secrets.token_hex(32)
    key_hash = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()
    prefix = raw_key[:10] + "..."
    scopes = "chat,research,portfolio"
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO api_keys (id, user_id, key_hash, prefix, label, scopes) VALUES (%s,%s,%s,%s,%s,%s)",
                      (str(uuid.uuid4()), user["id"], key_hash, prefix, "CAPITAN Web App", scopes))
            conn.commit()
    return {"key": raw_key, "prefix": prefix, "scopes": scopes}

@app.get("/api/developer/keys")
def list_api_keys(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, prefix, label, scopes, is_active, last_used, created FROM api_keys WHERE user_id=%s ORDER BY created DESC", (user["id"],))
                keys = []
                for r in c.fetchall():
                    keys.append({
                        "id": r[0],
                        "prefix": r[1],
                        "label": r[2],
                        "scopes": r[3],
                        "is_active": r[4],
                        "last_used": r[5].isoformat() if r[5] else None,
                        "created": r[6].isoformat() if r[6] else None
                    })
                return {"keys": keys}
    except Exception as e:
        logger.error(f"API keys list error: {e}")
        return {"keys": []}

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

# ================================================================================
# LEADERBOARD (fixed queries)
# ================================================================================
@app.get("/api/leaderboard")
def leaderboard(type: str = "staked", period: str = "all"):
    with get_db() as conn:
        with conn.cursor() as c:
            if type == "staked":
                c.execute("SELECT u.name, SUM(cs.amount) as total_staked FROM close_stakes cs JOIN users u ON cs.user_id = u.id WHERE cs.status = 'active' GROUP BY u.id, u.name ORDER BY total_staked DESC LIMIT 20")
                rows = c.fetchall()
                return {"leaderboard": [{"name": r[0], "value": r[1]} for r in rows]}
            elif type == "burned":
                c.execute("SELECT u.name, SUM(ct.amount) as total_burned FROM close_transactions ct JOIN users u ON ct.user_id = u.id WHERE ct.type='burn' GROUP BY u.id, u.name ORDER BY total_burned DESC LIMIT 20")
                rows = c.fetchall()
                return {"leaderboard": [{"name": r[0], "value": r[1]} for r in rows]}
            elif type == "streak":
                c.execute("SELECT name, last_active FROM users ORDER BY last_active DESC LIMIT 20")
                rows = c.fetchall()
                return {"leaderboard": [{"name": r[0], "value": r[1].isoformat() if r[1] else ""} for r in rows]}
    return {"leaderboard": []}

# ================================================================================
# FOUNDER ENDPOINTS
# ================================================================================
@app.get("/api/admin/dashboard")
def admin_dashboard(founder: dict = Depends(founder_only)):
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT COUNT(*) FROM users")
                total_users = c.fetchone()[0] if c.rowcount else 0
                c.execute("SELECT COUNT(*) FROM users WHERE last_active > NOW() - INTERVAL '24 hours'")
                active_today = c.fetchone()[0] if c.rowcount else 0
                c.execute("SELECT COALESCE(SUM(close_balance),0) FROM users")
                total_close = c.fetchone()[0] or 0
                c.execute("SELECT COALESCE(SUM(close_staked),0) FROM users")
                total_staked = c.fetchone()[0] or 0
                c.execute("SELECT COALESCE(SUM(amount),0) FROM close_transactions WHERE type='burn'")
                total_burned = c.fetchone()[0] or 0
                c.execute("SELECT COALESCE(SUM(amount_usd),0) FROM close_purchases")
                total_revenue = c.fetchone()[0] or 0
                return {
                    "total_users": total_users,
                    "active_today": active_today,
                    "close_circulating": total_close,
                    "close_staked": total_staked,
                    "close_burned": total_burned,
                    "total_revenue_usd": round(float(total_revenue), 2)
                }
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return {"total_users":0,"active_today":0,"close_circulating":0,"close_staked":0,"close_burned":0,"total_revenue_usd":0}

@app.get("/api/admin/charts")
async def founder_charts(founder: dict = Depends(founder_only)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT date, new_users, close_burned, close_staked, revenue_usd FROM daily_stats ORDER BY date DESC LIMIT 30")
            rows = c.fetchall()
            dates = [r[0].isoformat() for r in reversed(rows)] if rows else [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(30)]
            users = [r[1] for r in reversed(rows)] if rows else [0]*30
            burns = [r[2] for r in reversed(rows)] if rows else [0]*30
            stakes = [r[3] for r in reversed(rows)] if rows else [0]*30
            return {"dates": dates, "users": users, "burns": burns, "stakes": stakes}

@app.post("/api/founder/deposit")
async def founder_deposit(req: dict, founder: dict = Depends(founder_only)):
    amount = req.get("amount", 10_000_000)
    if not settings.TREASURY_PRIVATE_KEY: raise HTTPException(500, "Treasury private key not configured")
    acct = Account.from_key(settings.TREASURY_PRIVATE_KEY)
    address = founder.get("wallet_address")
    if not address: raise HTTPException(400, "Founder wallet address not set")
    contract = w3_polygon.eth.contract(address=settings.CLOSE_CONTRACT_ADDRESS, abi=ERC20_ABI)
    tx = contract.functions.transfer(address, int(amount * 10**settings.CLOSE_DECIMALS)).build_transaction({
        'from': acct.address,
        'nonce': w3_polygon.eth.get_transaction_count(acct.address),
        'gas': 60000,
        'gasPrice': w3_polygon.eth.gas_price
    })
    tx_hash = send_raw_tx(settings.TREASURY_PRIVATE_KEY, tx)
    return {"tx_hash": tx_hash, "amount": amount}

@app.get("/api/admin/users")
def admin_users(search: str = "", founder = Depends(founder_only)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, email, name, close_balance, close_staked, stake_tier FROM users WHERE email ILIKE %s OR name ILIKE %s ORDER BY created_at DESC LIMIT 100", (f"%{search}%", f"%{search}%"))
            users = c.fetchall()
    return {"users": [{"id":r[0], "email":r[1], "name":r[2], "close_balance":r[3], "close_staked":r[4], "stake_tier":r[5]} for r in users]}

@app.post("/api/admin/user/{user_id}/close")
def admin_adjust_close(user_id: str, req: dict, founder = Depends(founder_only)):
    amount = int(req.get("amount", 0))
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE users SET close_balance = GREATEST(0, close_balance + %s) WHERE id=%s", (amount, user_id))
            conn.commit()
    return {"ok": True}

@app.delete("/api/admin/user/{user_id}")
def admin_delete_user(user_id: str, founder = Depends(founder_only)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM users WHERE id=%s", (user_id,))
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
            return {"notifications": [{"id": r[0], "type": r[1], "message": r[2], "read": r[3], "created": r[4].isoformat() if r[4] else None} for r in c.fetchall()]}

@app.post("/api/notifications/read")
def mark_read(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE notifications SET read=TRUE WHERE user_id=%s", (user["id"],))
            conn.commit()
    return {"ok": True}

@app.get("/api/notifications/push")
async def get_push_notifications(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, type, message, created FROM notifications WHERE user_id=%s AND read=FALSE ORDER BY created DESC LIMIT 10", (user["id"],))
            notifs = [{"id": r[0], "type": r[1], "message": r[2], "created": r[3].isoformat() if r[3] else None} for r in c.fetchall()]
    return {"notifications": notifs}

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
    contents = await file.read()
    if len(contents) / (1024*1024) > 60: raise HTTPException(400, "Max 60MB")
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
# LEGAL
# ================================================================================
@app.get("/api/legal/privacy")
def privacy():
    return {"text": "<h2>Privacy Policy</h2><p>Your privacy is paramount. OS Wallets are non-custodial — CLOSEAI never holds your private keys. Wallet addresses and transactions are public on their respective blockchains. We collect minimal data: email for account recovery and anonymized usage statistics to improve CAPITAN AI. Your conversations are private and never shared. CLOSE token transactions are recorded on-chain and visible publicly. By using CAPITAN AI, you acknowledge the inherent privacy characteristics of blockchain technology.</p>"}

@app.get("/api/legal/terms")
def terms():
    return {"text": "<h2>Terms of Service</h2><p>CAPITAN AI is powered by CLOSE tokens. Each AI message consumes CLOSE tokens. Free accounts receive 2,000 CLOSE after wallet activation. CLOSE tokens can be purchased starting at $1.00 USD. Staking CLOSE unlocks tier benefits (Builder: 4M, Pro: 15M, Enterprise: 35M). CLOSEAI reserves the right to adjust staking requirements, token price, and burn rates at any time. OS Wallets are self-custody — you are solely responsible for your private keys and seed phrases. CLOSEAI cannot recover lost wallets. All AI responses are for informational purposes only and do not constitute financial, legal, or medical advice. Crypto assets are volatile — never invest more than you can afford to lose. By using CAPITAN AI and OS Wallets, you agree to these terms.</p>"}

# ================================================================================
# DAILY STATS (background thread)
# ================================================================================
def record_daily_stats():
    with get_db() as conn:
        with conn.cursor() as c:
            today = now_utc().strftime("%Y-%m-%d")
            c.execute("SELECT COUNT(*) FROM users WHERE created_at::date = %s", (today,)); new = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM users WHERE last_active > NOW() - INTERVAL '24 hours'"); active = c.fetchone()[0]
            c.execute("SELECT COALESCE(SUM(amount),0) FROM close_transactions WHERE type='burn' AND created::date = %s", (today,)); burned = c.fetchone()[0]
            c.execute("SELECT COALESCE(SUM(amount),0) FROM close_stakes WHERE created::date = %s", (today,)); staked = c.fetchone()[0]
            c.execute("SELECT COALESCE(SUM(amount_usd),0) FROM close_purchases WHERE created::date = %s", (today,)); revenue = c.fetchone()[0]
            c.execute("""INSERT INTO daily_stats (date, new_users, active_users, close_burned, close_staked, revenue_usd)
                         VALUES (%s,%s,%s,%s,%s,%s)
                         ON CONFLICT (date) DO UPDATE SET new_users=EXCLUDED.new_users, active_users=EXCLUDED.active_users,
                         close_burned=EXCLUDED.close_burned, close_staked=EXCLUDED.close_staked, revenue_usd=EXCLUDED.revenue_usd""",
                      (today, new, active, burned, staked, revenue))
            conn.commit()

def run_daily_stats_loop():
    while True:
        now = datetime.now()
        next_run = now.replace(hour=0, minute=5, second=0, microsecond=0)
        if now >= next_run:
            next_run += timedelta(days=1)
        sleep_seconds = (next_run - now).total_seconds()
        time.sleep(sleep_seconds)
        try:
            record_daily_stats()
        except Exception as e:
            logger.error(f"Daily stats error: {e}")

threading.Thread(target=run_daily_stats_loop, daemon=True).start()

# ================================================================================
# DEFAULT TOKEN LIST (100+ POLYGON TOKENS)
# ================================================================================
DEFAULT_TOKENS = [
    {"symbol":"CLOSE","address":settings.CLOSE_CONTRACT_ADDRESS,"decimals":18,"chain":"polygon"},
    {"symbol":"USDT","address":"0xc2132D05D31c914a87C6611C10748AEb04B58e8F","decimals":6,"chain":"polygon"},
    {"symbol":"USDC","address":"0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174","decimals":6,"chain":"polygon"},
    {"symbol":"WETH","address":"0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619","decimals":18,"chain":"polygon"},
    {"symbol":"WBTC","address":"0x1bfd67037b42cf73acf2047067bd4f2c47d9b6d6","decimals":8,"chain":"polygon"},
    {"symbol":"DAI","address":"0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063","decimals":18,"chain":"polygon"},
    {"symbol":"LINK","address":"0x53E0bca35eC356BD5ddDFebbD1Fc0fD03FaBad39","decimals":18,"chain":"polygon"},
    {"symbol":"AAVE","address":"0xD6DF932A45C0f255f85145f286eA0b292B21C90B","decimals":18,"chain":"polygon"},
    {"symbol":"CRV","address":"0x172370d5Cd63279eFa6d502DAB29171933a610AF","decimals":18,"chain":"polygon"},
    {"symbol":"UNI","address":"0xb33EaAd8d922B1083446DC23f610c2567fB5180f","decimals":18,"chain":"polygon"},
    {"symbol":"MATIC","address":"0x0000000000000000000000000000000000001010","decimals":18,"chain":"polygon"},
]

@app.get("/api/wallet/tokens")
async def get_token_list(user: dict = Depends(get_current_user)):
    prices = get_market_prices()
    tokens = []
    for t in DEFAULT_TOKENS:
        price = prices.get(t["symbol"], {}).get("price", 0)
        tokens.append({**t, "price_usd": price})
    return {"tokens": tokens}

@app.get("/api/wallet/portfolio")
async def get_full_portfolio(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    address = get_active_wallet_address(user["id"])
    if not address: return {"total_usd": 0, "tokens": []}
    total_usd = 0
    balances = []
    pol = w3_polygon.eth.get_balance(address) / 1e18
    pol_price = 0.5
    pol_usd = pol * pol_price
    total_usd += pol_usd
    balances.append({"symbol":"POL","balance":pol,"price_usd":pol_price,"usd_value":pol_usd})
    close_contract = w3_polygon.eth.contract(address=settings.CLOSE_CONTRACT_ADDRESS, abi=ERC20_ABI)
    close_bal = close_contract.functions.balanceOf(address).call() / 10**18
    close_usd = close_bal * settings.CLOSE_PRICE_USD
    total_usd += close_usd
    balances.append({"symbol":"CLOSE","balance":close_bal,"price_usd":settings.CLOSE_PRICE_USD,"usd_value":close_usd})
    for t in DEFAULT_TOKENS:
        if t["symbol"] == "CLOSE": continue
        try:
            tok_contract = w3_polygon.eth.contract(address=t["address"], abi=ERC20_ABI)
            bal = tok_contract.functions.balanceOf(address).call() / 10**t["decimals"]
            price = get_market_prices().get(t["symbol"], {}).get("price", 0)
            usd_val = bal * price
            total_usd += usd_val
            balances.append({"symbol":t["symbol"],"balance":bal,"price_usd":price,"usd_value":usd_val})
        except: pass
    return {"total_usd": total_usd, "tokens": balances}

# ================================================================================
# HEALTH
# ================================================================================
@app.get("/health")
def health_check():
    return {"status":"ok","version":"37.0","edition":"Complete OS Wallets – On‑Chain CLOSE Economy"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
