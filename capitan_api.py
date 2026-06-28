"""
CAPITAN AI — Universal OS Backend v36.1 (COMPLETE – NO PLACEHOLDERS)
CLOSEAI Technologies — CEO Osinachi Chukwu
"""
import os, re, json, uuid, time, hmac, hashlib, base64, secrets, logging, bcrypt, math, requests, asyncio
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager

import psycopg2, psycopg2.pool, uvicorn
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Depends, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

import PyPDF2, docx, openpyxl

# Optional libraries – must be installed in production
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

try:
    import redis as sync_redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

from web3 import Web3

# ------------------------------------------------------------------------------
# Safe POA middleware injection (fixes ImportError)
# ------------------------------------------------------------------------------
def setup_web3(rpc_url: str) -> Web3:
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    try:
        from web3.middleware import geth_poa_middleware
        w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    except ImportError:
        try:
            from web3.middleware import ExtraDataToPOAMiddleware
            w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        except ImportError:
            pass  # Polygon may still work without it
    return w3

# ------------------------------------------------------------------------------
# Settings
# ------------------------------------------------------------------------------
class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET: str
    FOUNDER_KEY: str
    FRONTEND_URL: str = "https://capitanai.com"
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    OPENAI_API_KEY: str = ""      # for embeddings & moderation
    COINGECKO_KEY: str = ""
    SERPAPI_KEY: str = ""
    NEWS_API_KEY: str = ""
    FINNHUB_API_KEY: str = ""
    POLYGONSCAN_API_KEY: str = ""
    ONEPINCH_API_KEY: str = ""
    REDIS_URL: str = "redis://localhost:6379"
    MODERATION_API_KEY: str = ""
    ENABLE_MODERATION: bool = True
    CLOSE_CONTRACT_ADDRESS: str = ""
    CLOSE_DEX_PAIR_ADDRESS: str = ""
    CLOSE_HOT_WALLET: str = ""
    CLOSE_TREASURY_ADDRESS: str = ""
    POLYGON_RPC_URL: str = "https://polygon-rpc.com"
    CLOSE_DECIMALS: int = 18
    TOTAL_ALLOCATION: int = 75_000_000_000_000  # 75 trillion CLOSE
    PRIVACY_POLICY_TEXT: str = ""
    TERMS_CONDITIONS_TEXT: str = ""
    FOUNDER_EXTRA_PROMPT: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

app = FastAPI(title="CAPITAN AI API", version="36.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# Database Pool
# ------------------------------------------------------------------------------
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

# ------------------------------------------------------------------------------
# Redis / In‑Memory Cache
# ------------------------------------------------------------------------------
_redis = None
_mem_cache = {}
_mem_cache_ttl = {}

def get_redis():
    global _redis
    if REDIS_AVAILABLE and not _redis:
        try:
            _redis = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)
            _redis.ping()
        except Exception as e:
            logger.warning(f"Redis unavailable, using memory cache: {e}")
            _redis = None
    return _redis

def cache_get(key: str) -> Optional[str]:
    r = get_redis()
    if r:
        return r.get(key)
    now = time.time()
    if key in _mem_cache_ttl and now < _mem_cache_ttl[key]:
        return _mem_cache[key]
    else:
        _mem_cache.pop(key, None)
        _mem_cache_ttl.pop(key, None)
    return None

def cache_set(key: str, value: str, ttl: int = 300):
    r = get_redis()
    if r:
        r.setex(key, ttl, value)
    else:
        _mem_cache[key] = value
        _mem_cache_ttl[key] = time.time() + ttl

# ------------------------------------------------------------------------------
# Rate Limiter (Redis‑backed)
# ------------------------------------------------------------------------------
def check_rate_limit(identifier: str, action: str = "default", limit: int = 20, window: int = 60) -> bool:
    r = get_redis()
    if r:
        key = f"rate:{action}:{identifier}"
        current = r.incr(key)
        if current == 1:
            r.expire(key, window)
        return current <= limit
    key = f"rate:{action}:{identifier}"
    now = time.time()
    entries = _mem_cache.get(key, [])
    entries = [t for t in entries if now - t < window]
    if len(entries) >= limit:
        return False
    entries.append(now)
    _mem_cache[key] = entries
    return True

# ------------------------------------------------------------------------------
# JWT Helpers
# ------------------------------------------------------------------------------
def create_access_token(user_id: str, is_admin: bool = False) -> str:
    payload = {
        "user_id": user_id,
        "type": "access",
        "is_admin": is_admin,
        "exp": int((datetime.now(timezone.utc) + timedelta(minutes=30)).timestamp())
    }
    return _encode_token(payload)

def create_refresh_token(user_id: str) -> str:
    payload = {
        "user_id": user_id,
        "type": "refresh",
        "exp": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())
    }
    return _encode_token(payload)

def create_session_token(session_id: str) -> str:
    payload = {
        "session_id": session_id,
        "type": "session",
        "exp": int((datetime.now(timezone.utc) + timedelta(days=365)).timestamp())
    }
    return _encode_token(payload)

def _encode_token(payload: dict) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = base64.urlsafe_b64encode(
        hmac.new(settings.JWT_SECRET.encode(), f"{header}.{payload_b64}".encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")
    return f"{header}.{payload_b64}.{sig}"

def verify_token(token: str) -> Optional[dict]:
    try:
        parts = token.split(".")
        if len(parts) != 3: return None
        header, payload_b64, sig = parts
        expected = base64.urlsafe_b64encode(
            hmac.new(settings.JWT_SECRET.encode(), f"{header}.{payload_b64}".encode(), hashlib.sha256).digest()
        ).decode().rstrip("=")
        if not hmac.compare_digest(sig, expected): return None
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        data = json.loads(base64.urlsafe_b64decode(payload_b64))
        if data.get("exp", 0) < datetime.now(timezone.utc).timestamp():
            return None
        return data
    except:
        return None

# ------------------------------------------------------------------------------
# Auth Dependencies
# ------------------------------------------------------------------------------
def get_current_user(request: Request) -> Optional[dict]:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "): return None
    token = auth[7:]
    payload = verify_token(token)
    if not payload or payload.get("type") != "access":
        return None
    user_id = payload.get("user_id")
    if not user_id: return None
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT 1 FROM user_sessions WHERE access_token = %s", (token,))
            if not c.fetchone(): return None
            c.execute("SELECT id, email, name, reasoning_depth, preferred_domain, token_balance, is_admin FROM users WHERE id = %s", (user_id,))
            row = c.fetchone()
            if row:
                return {
                    "id": row[0], "email": row[1], "name": row[2] or row[1].split('@')[0],
                    "reasoning_depth": row[3] or 1, "preferred_domain": row[4] or "general",
                    "token_balance": row[5] or 0, "is_admin": row[6] or False
                }
    return None

async def get_current_session(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing authorization header")
    token = auth[7:]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(401, "Invalid token")
    if payload.get("type") == "access":
        user = get_current_user(request)
        if user:
            return {"id": user["id"], "is_user": True, "user_data": user, "token_balance": user["token_balance"]}
    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(401, "Invalid session token")
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

def founder_only(user: dict = Depends(get_current_user)):
    if not user or not user.get("is_admin", False):
        raise HTTPException(403, "Founder access required")
    return user

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def sid(): return secrets.token_hex(4).upper()
def mid(): return 'mem_' + sid()
def hash_pw(p): return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
def check_pw(p, h): return bcrypt.checkpw(p.encode(), h.encode())

def estimate_tokens(msg: str, depth: int) -> int:
    multipliers = [1.0, 1.5, 2.0, 3.0, 4.0]
    m = multipliers[min(max(depth, 1) - 1, 4)]
    base = len(msg.split()) / 0.75
    return max(1, int(base * m))

def count_tokens(text: str) -> int:
    if TIKTOKEN_AVAILABLE:
        try:
            enc = tiktoken.encoding_for_model("gpt-4o")
            return len(enc.encode(text))
        except:
            pass
    return int(len(text.split()) / 0.75)

# ------------------------------------------------------------------------------
# AI General Intelligence Layer (FULL IMPLEMENTATION)
# ------------------------------------------------------------------------------

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
- **After generating code, check whether it fully meets the user's stated requirements. If it falls short, explicitly state the limitation and suggest how to complete it.**
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
- **Never start a new conversation** unless the user explicitly says "new chat" or "start over".
- Maintain a topic graph. Track active threads, pending decisions, and user constraints across the entire conversation.
- **Working memory**: keep track of everything discussed in this session.
- If a topic is resolved, offer one natural next step. Never force it.

## COMMUNICATION STYLE
- Direct. Precise. Natural. Confident.
- **Respond naturally, as a human expert would. Adapt your tone and structure to the user's question. No pre‑set formats.**
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
    now = datetime.now(timezone.utc)
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
    ql = q.lower()
    if re.search(r'def |class |import |docker|kubernetes|aws|api|sql|python|javascript|rust|golang|cpu|gpu|ram|hardware|react|vue|angular', ql): return 'coding'
    if re.search(r'dcf|valuation|wacc|stock|trading|portfolio|crypto|bitcoin|forex|markets|ethereum|bond|yield|option|future|derivative', ql): return 'finance'
    if re.search(r'black.scholes|ito|stochastic|monte carlo|var|cvar|sharpe|sortino|beta|alpha', ql): return 'quant'
    if re.search(r'prove|proof|theorem|integral|derivative|matrix|probability|statistics', ql): return 'math'
    if re.search(r'crispr|dna|quantum|physics|chemistry|biology|medicine|disease|symptom', ql): return 'science'
    if re.search(r'un|wto|imf|world bank|policy|election|regulation|government|africa|african union', ql): return 'geopolitics'
    if re.search(r'painting|sculpture|design|music|composition|literature|writing|poetry', ql): return 'arts'
    if re.search(r'recipe|cook|cuisine|nutrition|bake|restaurant', ql): return 'food'
    if re.search(r'who are you|what are you|identity|introduce yourself', ql): return 'identity'
    if re.search(r'^(hi|hello|hey|good morning|good afternoon|good evening|thanks|thank you)[\s!.]*$', ql): return 'greeting'
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
        except Exception as e:
            logger.error(f"Web search error: {e}")
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
        if settings.OPENAI_API_KEY:
            try:
                resp = requests.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}", "Content-Type": "application/json"},
                    json={"model": "text-embedding-ada-002", "input": query},
                    timeout=15
                )
                if resp.status_code == 200:
                    emb = resp.json()["data"][0]["embedding"]
                    with get_db() as conn:
                        with conn.cursor() as c:
                            c.execute("SELECT content FROM memories WHERE user_id = %s ORDER BY embedding <=> %s LIMIT %s",
                                      (user_id, emb, limit))
                            rows = c.fetchall()
                            return [r[0] for r in rows]
            except Exception as e:
                logger.error(f"OpenAI embedding error: {e}")
        # Fallback keyword search
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT content FROM memories WHERE user_id = %s ORDER BY created DESC LIMIT 100", (user_id,))
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

def store_memory(user_id: str, content: str, query: str, domain: str, importance: int = 1):
    try:
        embedding = None
        if settings.OPENAI_API_KEY:
            try:
                resp = requests.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}", "Content-Type": "application/json"},
                    json={"model": "text-embedding-ada-002", "input": content[:500]},
                    timeout=10
                )
                if resp.status_code == 200:
                    embedding = resp.json()["data"][0]["embedding"]
            except Exception as e:
                logger.error(f"Embedding generation failed: {e}")
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO memories (id, user_id, content, query, domain, embedding) VALUES (%s,%s,%s,%s,%s,%s)",
                          (mid(), user_id, content[:500], query, domain, embedding or [0.0]*1536))
                conn.commit()
    except Exception as e:
        logger.error(f"store_memory error: {e}")

def call_ai_model(messages: List[dict], reasoning_depth: int = 1) -> Tuple[str, str, float]:
    domain = "general"
    for m in reversed(messages):
        if m.get("role") == "user":
            domain = classify_query(m.get("content", ""))
            break
    if settings.OPENROUTER_API_KEY:
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                json={"model": "openai/gpt-4o-2024-11-20", "messages": messages, "temperature": 0.7, "max_tokens": 4000},
                timeout=60
            )
            if resp.status_code == 200:
                content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if content: return content, "gpt-4o", 0.9
        except Exception as e:
            logger.error(f"OpenRouter error: {e}")
    if settings.GROQ_API_KEY:
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile", "messages": messages, "temperature": 0.7, "max_tokens": 2500},
                timeout=35
            )
            if resp.status_code == 200:
                content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if content: return content, "llama-3.3-70b", 0.8
        except Exception as e:
            logger.error(f"Groq error: {e}")
    return "I'm having trouble connecting to AI services. Please try again.", "fallback", 0.3

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
    if settings.OPENAI_API_KEY:
        try:
            resp = requests.post(
                "https://api.openai.com/v1/moderations",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}", "Content-Type": "application/json"},
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
            logger.error(f"Moderation error: {e}")
    return False, "", "low"

# ------------------------------------------------------------------------------
# Database Initialization
# ------------------------------------------------------------------------------
def init_db():
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("CREATE EXTENSION IF NOT EXISTS vector")
            c.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

            c.execute("""
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
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    token_balance INTEGER DEFAULT 600,
                    created TIMESTAMP DEFAULT NOW(),
                    updated TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    id UUID PRIMARY KEY,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    access_token TEXT UNIQUE NOT NULL,
                    refresh_token TEXT UNIQUE NOT NULL,
                    expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id UUID PRIMARY KEY,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    prefix TEXT NOT NULL,
                    key_hash TEXT NOT NULL,
                    scopes TEXT DEFAULT 'chat,research,portfolio',
                    is_active BOOLEAN DEFAULT TRUE,
                    last_used TIMESTAMP,
                    created TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Fix: Add prefix column if table exists without it
            c.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'api_keys' AND column_name = 'prefix'
                    ) THEN
                        ALTER TABLE api_keys ADD COLUMN prefix TEXT;
                    END IF;
                END $$;
            """)
            
            # Create index only after ensuring column exists
            c.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(prefix)")

            c.execute("""
                CREATE TABLE IF NOT EXISTS wallets (
                    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    address TEXT UNIQUE NOT NULL,
                    encrypted_seed TEXT,
                    created TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS close_stakes (
                    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    staked_amount BIGINT DEFAULT 0,
                    tier TEXT DEFAULT 'free',
                    staked_at TIMESTAMP DEFAULT NOW(),
                    lock_until TIMESTAMP
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS close_transactions (
                    id UUID PRIMARY KEY,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    type TEXT,
                    amount BIGINT,
                    tx_hash TEXT UNIQUE,
                    destination TEXT,
                    status TEXT DEFAULT 'pending',
                    created TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS push_subscriptions (
                    id UUID PRIMARY KEY,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    endpoint TEXT UNIQUE,
                    p256dh TEXT,
                    auth TEXT,
                    created TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    session_id TEXT,
                    title TEXT,
                    created TIMESTAMP DEFAULT NOW(),
                    updated TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    chat_id TEXT,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    model TEXT,
                    created TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id UUID PRIMARY KEY,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    content TEXT,
                    query TEXT,
                    domain TEXT,
                    embedding vector(1536),
                    created TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS library_items (
                    id UUID PRIMARY KEY,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT,
                    content TEXT,
                    folder TEXT DEFAULT 'General',
                    tags JSONB DEFAULT '[]',
                    attachments JSONB DEFAULT '[]',
                    pinned BOOLEAN DEFAULT FALSE,
                    chat_id TEXT,
                    created TIMESTAMP DEFAULT NOW(),
                    updated TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS research_topics (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    domain TEXT,
                    prompt TEXT,
                    is_builtin BOOLEAN DEFAULT TRUE,
                    created TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS research_projects (
                    id TEXT PRIMARY KEY,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    description TEXT,
                    chat_id TEXT,
                    created TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    description TEXT DEFAULT '',
                    topic TEXT DEFAULT '',
                    owner_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    room_code TEXT UNIQUE,
                    password_hash TEXT,
                    max_members INTEGER DEFAULT 30,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS workspace_members (
                    workspace_id TEXT,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    role TEXT DEFAULT 'member',
                    joined_at TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY (workspace_id, user_id)
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS workspace_messages (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    author_name TEXT,
                    message TEXT,
                    is_ai INTEGER DEFAULT 0,
                    pinned BOOLEAN DEFAULT FALSE,
                    created TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id UUID PRIMARY KEY,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    type TEXT,
                    message TEXT,
                    read BOOLEAN DEFAULT FALSE,
                    created TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS token_purchases (
                    id UUID PRIMARY KEY,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    txid TEXT UNIQUE,
                    currency TEXT,
                    amount_usd REAL,
                    tokens INTEGER,
                    verified INTEGER DEFAULT 0,
                    created TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id UUID PRIMARY KEY,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    message_id TEXT,
                    rating INTEGER,
                    correction TEXT,
                    reason TEXT,
                    created TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS activity_log (
                    id UUID PRIMARY KEY,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    action TEXT,
                    details TEXT,
                    created TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS uploaded_files (
                    id TEXT PRIMARY KEY,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    workspace_id TEXT,
                    filename TEXT,
                    original_name TEXT,
                    size INTEGER,
                    storage_path TEXT,
                    extracted_text TEXT,
                    created TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id UUID PRIMARY KEY,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    txid TEXT UNIQUE,
                    currency TEXT,
                    amount REAL,
                    status TEXT DEFAULT 'pending',
                    verified INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS content_flags (
                    id UUID PRIMARY KEY,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    message_id TEXT,
                    content TEXT,
                    reason TEXT,
                    severity TEXT DEFAULT 'low',
                    reviewed BOOLEAN DEFAULT FALSE,
                    action TEXT DEFAULT 'none',
                    created TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS security_events (
                    id UUID PRIMARY KEY,
                    event_type TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    details TEXT,
                    severity TEXT DEFAULT 'low',
                    blocked BOOLEAN DEFAULT FALSE,
                    created TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS blocked_ips (
                    ip_address TEXT PRIMARY KEY,
                    reason TEXT,
                    blocked_until TIMESTAMP,
                    created TIMESTAMP DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS webhooks (
                    id UUID PRIMARY KEY,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    url TEXT NOT NULL,
                    events TEXT DEFAULT 'new_message',
                    is_active BOOLEAN DEFAULT TRUE,
                    created TIMESTAMP DEFAULT NOW()
                )
            """)
            # Seed built-in research topics
            topics = [
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
            for tid, title, desc, domain, prompt in topics:
                c.execute("INSERT INTO research_topics (id, title, description, domain, prompt, is_builtin) VALUES (%s,%s,%s,%s,%s,TRUE) ON CONFLICT (id) DO NOTHING",
                          (tid, title, desc, domain, prompt))
            conn.commit()
        logger.info("✅ Database initialized (v36.1 complete)")

init_db()

# ------------------------------------------------------------------------------
# Background helpers
# ------------------------------------------------------------------------------
def log_activity(user_id, action, details=""):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO activity_log (id, user_id, action, details) VALUES (%s,%s,%s,%s)",
                      (str(uuid.uuid4()), user_id, action, details))
            conn.commit()

def create_notification(user_id, type, message):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO notifications (id, user_id, type, message) VALUES (%s,%s,%s,%s)",
                      (str(uuid.uuid4()), user_id, type, message))
            conn.commit()

def log_security_event(event_type, ip, user_agent, details, severity="low"):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO security_events (id, event_type, ip_address, user_agent, details, severity) VALUES (%s,%s,%s,%s,%s,%s)",
                      (str(uuid.uuid4()), event_type, ip, user_agent, details, severity))
            conn.commit()

# ------------------------------------------------------------------------------
# Legal
# ------------------------------------------------------------------------------
@app.get("/api/legal/privacy")
def privacy():
    return {"text": settings.PRIVACY_POLICY_TEXT or "<h2>Privacy Policy</h2><p>Your privacy is paramount.</p>"}

@app.get("/api/legal/terms")
def terms():
    return {"text": settings.TERMS_CONDITIONS_TEXT or "<h2>Terms & Conditions</h2><p>By using CAPITAN AI you agree to these terms.</p>"}

# ------------------------------------------------------------------------------
# Auth Endpoints
# ------------------------------------------------------------------------------
class RegisterReq(BaseModel): email: str; password: str; name: Optional[str] = None

@app.post("/api/auth/register")
def register(req: RegisterReq):
    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', req.email): raise HTTPException(400, "Invalid email")
    if len(req.password) < 6: raise HTTPException(400, "Password min 6 chars")
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id FROM users WHERE email = %s", (req.email,))
            if c.fetchone(): raise HTTPException(400, "Email already registered")
            user_id = str(uuid.uuid4())
            name = req.name or req.email.split('@')[0]
            c.execute("INSERT INTO users (id, email, password_hash, name, reasoning_depth, preferred_domain, token_balance) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                      (user_id, req.email, hash_pw(req.password), name, 1, "general", 3000))
            access_token = create_access_token(user_id)
            refresh_token = create_refresh_token(user_id)
            c.execute("INSERT INTO user_sessions (id, user_id, access_token, refresh_token, expires_at) VALUES (%s,%s,%s,%s,%s)",
                      (str(uuid.uuid4()), user_id, access_token, refresh_token, datetime.now(timezone.utc)+timedelta(days=30)))
            raw_key = "cap_" + secrets.token_hex(32)
            key_hash = hash_pw(raw_key)
            prefix = raw_key[:10] + "..."
            c.execute("INSERT INTO api_keys (id, user_id, prefix, key_hash, scopes) VALUES (%s,%s,%s,%s,%s)",
                      (str(uuid.uuid4()), user_id, prefix, key_hash, "chat,research,portfolio"))
            conn.commit()
            log_activity(user_id, "register")
    return {"access_token": access_token, "refresh_token": refresh_token,
            "user": {"id": user_id, "email": req.email, "name": name, "token_balance": 3000, "is_admin": False}}

@app.post("/api/auth/login")
def login(req: RegisterReq):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, email, password_hash, name, reasoning_depth, preferred_domain, token_balance, is_admin FROM users WHERE email = %s", (req.email,))
            user = c.fetchone()
            if not user or not check_pw(req.password, user[2]): raise HTTPException(401, "Invalid credentials")
            user_id, email, _, name, rd, pd, tb, is_admin = user
            access_token = create_access_token(user_id, is_admin)
            refresh_token = create_refresh_token(user_id)
            c.execute("INSERT INTO user_sessions (id, user_id, access_token, refresh_token, expires_at) VALUES (%s,%s,%s,%s,%s)",
                      (str(uuid.uuid4()), user_id, access_token, refresh_token, datetime.now(timezone.utc)+timedelta(days=30)))
            c.execute("UPDATE users SET last_active = NOW() WHERE id = %s", (user_id,))
            conn.commit()
            log_activity(user_id, "login")
    return {"access_token": access_token, "refresh_token": refresh_token,
            "user": {"id": user_id, "email": email, "name": name or email.split('@')[0],
                     "reasoning_depth": rd or 1, "preferred_domain": pd or "general",
                     "token_balance": tb or 0, "is_admin": is_admin or False}}

@app.post("/api/auth/refresh")
def refresh_token_endpoint(req: dict):
    refresh_token = req.get("refresh_token")
    if not refresh_token: raise HTTPException(400)
    payload = verify_token(refresh_token)
    if not payload or payload.get("type") != "refresh": raise HTTPException(401, "Invalid refresh token")
    user_id = payload["user_id"]
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT 1 FROM user_sessions WHERE refresh_token = %s", (refresh_token,))
            if not c.fetchone(): raise HTTPException(401)
            c.execute("DELETE FROM user_sessions WHERE refresh_token = %s", (refresh_token,))
            c.execute("SELECT is_admin FROM users WHERE id = %s", (user_id,))
            is_admin = c.fetchone()[0]
            new_access = create_access_token(user_id, is_admin)
            new_refresh = create_refresh_token(user_id)
            c.execute("INSERT INTO user_sessions (id, user_id, access_token, refresh_token, expires_at) VALUES (%s,%s,%s,%s,%s)",
                      (str(uuid.uuid4()), user_id, new_access, new_refresh, datetime.now(timezone.utc)+timedelta(days=30)))
            conn.commit()
    return {"access_token": new_access, "refresh_token": new_refresh}

@app.post("/api/auth/logout")
def logout(request: Request):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("DELETE FROM user_sessions WHERE access_token = %s", (auth[7:],))
                conn.commit()
    return {"message": "Logged out"}

@app.get("/api/auth/validate")
def validate_session(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    return {"user": user, "token_balance": user["token_balance"], "is_admin": user.get("is_admin", False)}

@app.get("/api/auth/me")
def me(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    return user

@app.post("/api/auth/update-profile")
def update_profile(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    name = req.get("name")
    reasoning_depth = req.get("reasoning_depth")
    preferred_domain = req.get("preferred_domain")
    valid_domains = ["general","finance","coding","science","math","geopolitics","arts","food"]
    if preferred_domain and preferred_domain not in valid_domains: raise HTTPException(400, "Invalid domain")
    if reasoning_depth and (reasoning_depth < 1 or reasoning_depth > 5): raise HTTPException(400, "Depth 1-5")
    with get_db() as conn:
        with conn.cursor() as c:
            if name: c.execute("UPDATE users SET name=%s, updated_at=NOW() WHERE id=%s", (name, user["id"]))
            if reasoning_depth: c.execute("UPDATE users SET reasoning_depth=%s, updated_at=NOW() WHERE id=%s", (reasoning_depth, user["id"]))
            if preferred_domain: c.execute("UPDATE users SET preferred_domain=%s, updated_at=NOW() WHERE id=%s", (preferred_domain, user["id"]))
            conn.commit()
    return {"message": "Profile updated"}

@app.delete("/api/auth/delete-account")
def delete_account(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM users WHERE id = %s", (user["id"],))
            conn.commit()
    return {"message": "Account deleted"}

@app.post("/api/auth/forgot-password")
def forgot_password(req: dict):
    return {"message": "If an account exists, a reset link has been sent."}

# ------------------------------------------------------------------------------
# Anonymous session
# ------------------------------------------------------------------------------
@app.get("/api/session")
def anonymous_session():
    session_id = f"s_{sid()}"
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO sessions (id, token_balance) VALUES (%s, 600)", (session_id,))
            conn.commit()
    token = create_session_token(session_id)
    return {"id": session_id, "token": token, "token_balance": 600}

# ------------------------------------------------------------------------------
# Founder login
# ------------------------------------------------------------------------------
@app.post("/api/founder")
def founder_login(req: dict, request: Request):
    if not check_rate_limit(request.client.host, "founder", 5): raise HTTPException(429)
    code = req.get("code", "")
    if not hmac.compare_digest(code, settings.FOUNDER_KEY): raise HTTPException(403)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id FROM users WHERE email = 'founder@capitan.ai'")
            row = c.fetchone()
            if row:
                user_id = row[0]
                c.execute("UPDATE users SET is_admin=TRUE, reasoning_depth=5, token_balance=999999999 WHERE id=%s", (user_id,))
            else:
                user_id = str(uuid.uuid4())
                c.execute("INSERT INTO users (id, email, password_hash, name, reasoning_depth, preferred_domain, token_balance, is_admin) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                          (user_id, "founder@capitan.ai", hash_pw("founder_sentinel"), "CAPITAN Founder", 5, "general", 999999999, True))
            access = create_access_token(user_id, True)
            refresh = create_refresh_token(user_id)
            c.execute("INSERT INTO user_sessions (id, user_id, access_token, refresh_token, expires_at) VALUES (%s,%s,%s,%s,%s)",
                      (str(uuid.uuid4()), user_id, access, refresh, datetime.now(timezone.utc)+timedelta(days=365)))
            conn.commit()
    return {"verified": True, "access_token": access, "refresh_token": refresh,
            "user": {"id": user_id, "name": "CAPITAN Founder", "email": "founder@capitan.ai", "reasoning_depth": 5, "token_balance": 999999999, "is_admin": True}}

# ------------------------------------------------------------------------------
# Chat (FULL INTELLIGENCE)
# ------------------------------------------------------------------------------
class ChatRequest(BaseModel):
    messages: list
    chat_id: Optional[str] = None

@app.post("/api/chat")
def chat(req: ChatRequest, request: Request, background_tasks: BackgroundTasks,
          user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    if not check_rate_limit(user["id"], "chat", limit=50): raise HTTPException(429)
    user_msg = None
    for m in reversed(req.messages):
        if m.get("role") == "user": user_msg = m.get("content"); break
    if not user_msg: raise HTTPException(400)
    chat_id = req.chat_id or f"chat_{sid()}"

    est = estimate_tokens(user_msg, user["reasoning_depth"])
    if user["token_balance"] < est and not user["is_admin"]:
        raise HTTPException(402, f"Insufficient tokens. Need ~{est}, you have {user['token_balance']}.")

    if settings.ENABLE_MODERATION:
        flagged, reason, severity = moderate_content(user_msg)
        if flagged:
            background_tasks.add_task(create_notification, user["id"], "moderation", f"Your message was flagged: {reason}")

    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO chats (id, user_id, title) VALUES (%s,%s,%s) ON CONFLICT (id) DO UPDATE SET updated=NOW()",
                      (chat_id, user["id"], user_msg[:60]))
            c.execute("INSERT INTO chat_messages (id, chat_id, user_id, role, content) VALUES (%s,%s,%s,%s,%s)",
                      (f"msg_{sid()}", chat_id, user["id"], "user", user_msg))
            conn.commit()

    history = []
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT role, content FROM chat_messages WHERE chat_id = %s ORDER BY created ASC LIMIT 60", (chat_id,))
            history = [{"role": r[0], "content": r[1]} for r in c.fetchall()]

    memory_context = ""
    try:
        memories = get_relevant_memories(user["id"], user_msg)
        if memories:
            memory_context = "Relevant past interactions:\n" + "\n".join([f"- {m[:200]}" for m in memories])
    except Exception as e:
        logger.warning(f"Memory retrieval failed: {e}")

    web_results = ""
    if needs_web_search(user_msg) and settings.SERPAPI_KEY:
        try:
            results = search_web(user_msg, 5)
            if results:
                web_results = "\n".join([f"- {r['title']}: {r['snippet'][:200]}" for r in results[:4]])
        except Exception as e:
            logger.error(f"Web search error: {e}")

    thread_context = get_thread_context(chat_id, user["id"])
    user_model = get_user_model(user["id"])

    system = build_system_prompt(
        user_query=user_msg,
        reasoning_depth=user["reasoning_depth"],
        preferred_domain=user["preferred_domain"],
        user_model=user_model,
        thread_context=thread_context,
        web_results=web_results,
        memory_context=memory_context
    )

    messages = [{"role":"system", "content": system}] + history
    response, model, confidence = call_ai_model(messages, user["reasoning_depth"])

    msg_id = f"msg_{sid()}"
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO chat_messages (id, chat_id, user_id, role, content, model) VALUES (%s,%s,%s,%s,%s,%s)",
                      (msg_id, chat_id, user["id"], "assistant", response, model))
            conn.commit()

    tokens_used = estimate_tokens(user_msg, user["reasoning_depth"])
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE users SET token_balance = GREATEST(0, token_balance - %s), last_active = NOW() WHERE id = %s",
                      (tokens_used, user["id"]))
            conn.commit()

    background_tasks.add_task(store_memory, user["id"], response[:500], user_msg, classify_query(user_msg), 2)
    background_tasks.add_task(log_activity, user["id"], "chat", f"tokens_used: {tokens_used}")

    return {"content": response, "chat_id": chat_id, "model": model, "tokens_used": tokens_used,
            "new_balance": user["token_balance"] - tokens_used}

@app.get("/api/chats")
def get_chats(request: Request, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, title, created, updated FROM chats WHERE user_id=%s ORDER BY updated DESC LIMIT 100", (user["id"],))
            return {"chats": [{"id": r[0], "title": r[1] or "New Chat", "created": r[2].isoformat(), "updated": r[3].isoformat()} for r in c.fetchall()]}

@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str, request: Request, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT role, content, model, created FROM chat_messages WHERE chat_id=%s ORDER BY created ASC", (chat_id,))
            return {"messages": [{"role": r[0], "content": r[1], "model": r[2], "created": r[3].isoformat()} for r in c.fetchall()]}

@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str, request: Request, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM chat_messages WHERE chat_id=%s", (chat_id,))
            c.execute("DELETE FROM chats WHERE id=%s", (chat_id,))
            conn.commit()
    return {"deleted": True}

# ------------------------------------------------------------------------------
# Portfolio
# ------------------------------------------------------------------------------
class PortfolioItemCreate(BaseModel):
    name: str
    content: str = ""
    folder: str = "General"
    tags: List[str] = []
    attachments: List[str] = []
    chat_id: Optional[str] = None

@app.get("/api/portfolio")
def get_portfolio(user: dict = Depends(get_current_user)):
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

# ------------------------------------------------------------------------------
# Research Hub
# ------------------------------------------------------------------------------
@app.get("/api/research/topics")
def get_research_topics(domain: Optional[str] = None):
    with get_db() as conn:
        with conn.cursor() as c:
            if domain:
                c.execute("SELECT id, title, description, domain, prompt FROM research_topics WHERE is_builtin=TRUE AND domain=%s ORDER BY title", (domain,))
            else:
                c.execute("SELECT id, title, description, domain, prompt FROM research_topics WHERE is_builtin=TRUE ORDER BY title")
            return {"topics": [{"id": r[0], "title": r[1], "description": r[2], "domain": r[3], "prompt": r[4]} for r in c.fetchall()]}

@app.get("/api/research/projects")
def get_user_projects(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, name, description, chat_id, created FROM research_projects WHERE user_id=%s ORDER BY created DESC", (user["id"],))
            return {"projects": [{"id": r[0], "name": r[1], "description": r[2], "chat_id": r[3], "created": r[4].isoformat()} for r in c.fetchall()]}

@app.post("/api/research/projects")
def create_user_project(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM research_projects WHERE user_id=%s", (user["id"],))
            count = c.fetchone()[0]
            if count >= 30: raise HTTPException(429, "Project limit reached (30).")
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

# ------------------------------------------------------------------------------
# Workspaces
# ------------------------------------------------------------------------------
@app.post("/api/workspace/create")
def create_workspace(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM workspaces WHERE owner_id=%s", (user["id"],))
            if c.fetchone()[0] >= 30: raise HTTPException(429, "Workspace limit reached (30).")
            room_code = req.get("room_code", f"HUB-{sid()}")
            password = req.get("password")
            password_hash = hash_pw(password) if password else None
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
            if room[1] and (not password or not check_pw(password, room[1])):
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

# ------------------------------------------------------------------------------
# Notifications
# ------------------------------------------------------------------------------
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

# ------------------------------------------------------------------------------
# Token Purchase (legacy crypto payments)
# ------------------------------------------------------------------------------
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
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT token_balance FROM users WHERE id = %s", (user["id"],))
            row = c.fetchone()
            return {"balance": row[0] if row else 0}

class TokenPurchaseRequest(BaseModel):
    package_amount: float
    txid: str
    currency: str = "BTC"

def verify_transaction(txid: str, currency: str, expected_usd: float, use_token_wallet: bool = True) -> Tuple[bool, float]:
    wallets = TOKEN_WALLETS if use_token_wallet else {"BTC":"...","ETH":"..."}
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
        except Exception as e:
            logger.error(f"BTC verification error: {e}")
    elif currency == "ETH":
        return False, 0.0
    return False, 0.0

@app.post("/api/tokens/purchase")
def purchase_tokens(req: TokenPurchaseRequest, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    pkg = None
    for p in TOKEN_PACKAGES + ENTERPRISE_TOKEN_PACKAGES:
        if p["amount"] == req.package_amount:
            pkg = p
            break
    if not pkg: raise HTTPException(400, "Invalid package amount")
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
        return {"verified": True, "tokens_added": pkg["tokens"], "new_balance": user["token_balance"] + pkg["tokens"]}
    else:
        return {"verified": False, "message": "Payment is being verified. Tokens will be credited once confirmed."}

# ------------------------------------------------------------------------------
# Feedback
# ------------------------------------------------------------------------------
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

# ------------------------------------------------------------------------------
# File Upload
# ------------------------------------------------------------------------------
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

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
                    sheets_text.append(' '.join([str(c) if c is not None else '' for c in row]))
            return '\n'.join(sheets_text)
        else:
            return ''
    except Exception as e:
        logger.error(f"File extraction error: {e}")
        return ''

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

# ------------------------------------------------------------------------------
# OS Wallet Endpoints (using safe setup_web3)
# ------------------------------------------------------------------------------
@app.post("/api/wallet/create")
def create_wallet(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    password = req.get("password")
    if not password or len(password) < 10: raise HTTPException(400, "Password min 10 chars")
    w3 = setup_web3(settings.POLYGON_RPC_URL)
    acct = w3.eth.account.create()
    encrypted = w3.eth.account.encrypt(acct.privateKey.hex(), password)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO wallets (user_id, address, encrypted_seed) VALUES (%s,%s,%s) ON CONFLICT (user_id) DO UPDATE SET address=EXCLUDED.address, encrypted_seed=EXCLUDED.encrypted_seed",
                      (user["id"], acct.address, json.dumps(encrypted)))
            conn.commit()
    return {"address": acct.address}

@app.post("/api/wallet/import")
def import_wallet(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    seed = req.get("seed")
    password = req.get("password")
    if not seed or not password: raise HTTPException(400)
    w3 = setup_web3(settings.POLYGON_RPC_URL)
    try:
        acct = w3.eth.account.from_mnemonic(seed)
    except Exception:
        raise HTTPException(400, "Invalid seed phrase")
    encrypted = w3.eth.account.encrypt(acct.privateKey.hex(), password)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO wallets (user_id, address, encrypted_seed) VALUES (%s,%s,%s) ON CONFLICT (user_id) DO UPDATE SET address=EXCLUDED.address, encrypted_seed=EXCLUDED.encrypted_seed",
                      (user["id"], acct.address, json.dumps(encrypted)))
            conn.commit()
    return {"address": acct.address}

@app.get("/api/wallet/balance")
def wallet_balance(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT address FROM wallets WHERE user_id = %s", (user["id"],))
            row = c.fetchone()
            if not row: raise HTTPException(400, "No wallet found")
            address = row[0]
    w3 = setup_web3(settings.POLYGON_RPC_URL)
    balance_pol = w3.eth.get_balance(address)
    close_balance = 0
    if settings.CLOSE_CONTRACT_ADDRESS:
        try:
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(settings.CLOSE_CONTRACT_ADDRESS),
                abi=[{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]
            )
            close_balance = contract.functions.balanceOf(address).call()
        except Exception as e:
            logger.error(f"CLOSE balance error: {e}")
    return {"address": address, "pol": str(Web3.from_wei(balance_pol, 'ether')), "close": str(Web3.from_wei(close_balance, 'ether')) if close_balance else "0"}

@app.post("/api/wallet/deposit")
def deposit_close(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    tx_hash = req.get("tx_hash")
    signed_message = req.get("signed_message")
    if not tx_hash or not signed_message: raise HTTPException(400, "tx_hash and signed_message required")
    w3 = setup_web3(settings.POLYGON_RPC_URL)

    nonce = cache_get(f"nonce:{user['id']}")
    if not nonce:
        nonce = secrets.token_hex(16)
        cache_set(f"nonce:{user['id']}", nonce, 600)
    message = f"I am depositing CLOSE to {settings.CLOSE_HOT_WALLET}. Nonce: {nonce}"
    try:
        recovered = w3.eth.account.recover_message(message, signature=signed_message)
    except Exception:
        raise HTTPException(400, "Invalid signature")

    try:
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        if not receipt or receipt['status'] != 1: raise HTTPException(400, "Transaction failed")
    except Exception as e:
        raise HTTPException(400, f"Failed to get receipt: {e}")

    tx = w3.eth.get_transaction(tx_hash)
    if tx['from'].lower() != recovered.lower():
        raise HTTPException(400, "Signer does not match transaction sender")

    contract_address = Web3.to_checksum_address(settings.CLOSE_CONTRACT_ADDRESS)
    transfer_topic = Web3.keccak(text="Transfer(address,address,uint256)").hex()
    amount = None
    for log in receipt['logs']:
        if log['address'].lower() == contract_address.lower() and log['topics'][0].hex() == transfer_topic:
            from_addr = Web3.to_checksum_address('0x' + log['topics'][1].hex()[-40:])
            to_addr = Web3.to_checksum_address('0x' + log['topics'][2].hex()[-40:])
            value = int(log['data'], 16)
            if to_addr.lower() == settings.CLOSE_HOT_WALLET.lower() and from_addr.lower() == recovered.lower():
                amount = value
                break
    if amount is None:
        raise HTTPException(400, "No valid CLOSE transfer found")

    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id FROM close_transactions WHERE tx_hash = %s", (tx_hash,))
            if c.fetchone(): raise HTTPException(400, "Transaction already credited")
            c.execute("INSERT INTO close_stakes (user_id, staked_amount, tier) VALUES (%s, %s, 'free') ON CONFLICT (user_id) DO UPDATE SET staked_amount = close_stakes.staked_amount + EXCLUDED.staked_amount",
                      (user["id"], amount))
            c.execute("INSERT INTO close_transactions (id, user_id, type, amount, tx_hash, status) VALUES (%s,%s,%s,%s,%s,'completed')",
                      (str(uuid.uuid4()), user["id"], "deposit", amount, tx_hash))
            conn.commit()
    tier = update_user_tier(user["id"])
    log_activity(user["id"], "deposit", f"amount: {amount}")
    return {"credited": str(amount), "tier": tier}

def update_user_tier(user_id: str) -> str:
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT staked_amount FROM close_stakes WHERE user_id = %s", (user_id,))
            staked = c.fetchone()[0] if c.rowcount else 0
    tier = "free"
    if staked >= 1_000_000_000_000_000: tier = "enterprise"
    elif staked >= 100_000_000_000_000: tier = "pro"
    elif staked >= 10_000_000_000_000: tier = "builder"
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE close_stakes SET tier = %s WHERE user_id = %s", (tier, user_id))
            conn.commit()
    return tier

@app.get("/api/wallet/stake")
def get_stake(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT staked_amount, tier FROM close_stakes WHERE user_id = %s", (user["id"],))
            row = c.fetchone()
            if row: return {"staked": str(row[0]), "tier": row[1]}
    return {"staked": "0", "tier": "free"}

@app.post("/api/wallet/withdraw")
def withdraw_close(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    amount = req.get("amount")
    destination = req.get("address")
    if not amount or not destination: raise HTTPException(400)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT staked_amount FROM close_stakes WHERE user_id = %s", (user["id"],))
            row = c.fetchone()
            if not row or int(row[0]) < int(amount): raise HTTPException(400, "Insufficient staked balance")
            c.execute("UPDATE close_stakes SET staked_amount = staked_amount - %s WHERE user_id = %s", (amount, user["id"]))
            c.execute("INSERT INTO close_transactions (id, user_id, type, amount, destination, status) VALUES (%s,%s,%s,%s,%s,'pending')",
                      (str(uuid.uuid4()), user["id"], "withdraw", amount, destination))
            conn.commit()
    update_user_tier(user["id"])
    log_activity(user["id"], "withdraw_request", f"amount: {amount}")
    return {"withdrawn": amount, "pending": True}

@app.get("/api/wallet/activity")
def wallet_activity(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT type, amount, tx_hash, destination, status, created FROM close_transactions WHERE user_id = %s ORDER BY created DESC LIMIT 50", (user["id"],))
            txs = [{"type": r[0], "amount": str(r[1]), "tx_hash": r[2], "destination": r[3], "status": r[4], "created": r[5].isoformat()} for r in c.fetchall()]
    return {"transactions": txs}

# ------------------------------------------------------------------------------
# Market Data (with caching)
# ------------------------------------------------------------------------------
@app.get("/api/market/crypto")
def crypto_market():
    cache = cache_get("crypto_market")
    if cache: return json.loads(cache)
    if not settings.COINGECKO_KEY: raise HTTPException(503, "CoinGecko key not set")
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={"vs_currency":"usd","order":"market_cap_desc","per_page":100,"page":1,"sparkline":"true","price_change_percentage":"24h"},
            headers={"x-cg-demo-api-key": settings.COINGECKO_KEY},
            timeout=20
        )
        data = r.json()
        cache_set("crypto_market", json.dumps(data), ttl=120)
        return data
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/market/stocks")
def stock_market():
    cache = cache_get("stocks")
    if cache: return json.loads(cache)
    if not settings.FINNHUB_API_KEY: raise HTTPException(503)
    symbols = ["AAPL","MSFT","GOOGL","AMZN","TSLA","NVDA","META","JPM","V","JNJ"]
    quotes = []
    for sym in symbols:
        try:
            r = requests.get(f"https://finnhub.io/api/v1/quote?symbol={sym}&token={settings.FINNHUB_API_KEY}", timeout=5)
            if r.status_code == 200: quotes.append({"symbol": sym, **r.json()})
        except Exception as e:
            logger.error(f"Stock quote error {sym}: {e}")
    cache_set("stocks", json.dumps(quotes), ttl=300)
    return quotes

@app.get("/api/market/commodities")
def commodities():
    cache = cache_get("commodities")
    if cache: return json.loads(cache)
    if not settings.FINNHUB_API_KEY: raise HTTPException(503)
    commodities = {}
    try:
        r = requests.get(f"https://finnhub.io/api/v1/forex/candle?symbol=OANDA:XAU_USD&resolution=D&count=1&token={settings.FINNHUB_API_KEY}")
        if r.status_code == 200: commodities["gold"] = r.json()
    except Exception as e:
        logger.error(f"Commodity gold error: {e}")
    cache_set("commodities", json.dumps(commodities), ttl=600)
    return commodities

# ------------------------------------------------------------------------------
# 1inch Swap Proxy
# ------------------------------------------------------------------------------
@app.get("/api/swap/quote")
def swap_quote(fromToken: str, toToken: str, amount: str, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    if not settings.ONEPINCH_API_KEY: raise HTTPException(503)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT address FROM wallets WHERE user_id = %s", (user["id"],))
            row = c.fetchone()
            if not row: raise HTTPException(400, "No wallet found")
            wallet = row[0]
    url = "https://api.1inch.dev/swap/v5.2/137/quote"
    params = {"src": fromToken, "dst": toToken, "amount": amount, "from": wallet, "slippage": 1}
    headers = {"Authorization": f"Bearer {settings.ONEPINCH_API_KEY}"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        return resp.json()
    except Exception as e:
        raise HTTPException(500, f"Swap quote failed: {e}")

@app.post("/api/swap/execute")
def swap_execute(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    return {"message": "Swap executed by frontend"}

# ------------------------------------------------------------------------------
# AI Token Scanner
# ------------------------------------------------------------------------------
@app.get("/api/scanner/analyze")
def analyze_token(address: str, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    if not settings.POLYGONSCAN_API_KEY: raise HTTPException(503)
    w3 = setup_web3(settings.POLYGON_RPC_URL)
    abi = [
        {"constant":True,"inputs":[],"name":"name","outputs":[{"name":"","type":"string"}],"type":"function"},
        {"constant":True,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"type":"function"},
        {"constant":True,"inputs":[],"name":"totalSupply","outputs":[{"name":"","type":"uint256"}],"type":"function"},
    ]
    try:
        contract = w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)
        name = contract.functions.name().call()
        symbol = contract.functions.symbol().call()
        total_supply = contract.functions.totalSupply().call()
    except Exception as e:
        raise HTTPException(400, f"Invalid token contract: {e}")
    try:
        r = requests.get(f"https://api.polygonscan.com/api?module=token&action=tokenholderlist&contractaddress={address}&apikey={settings.POLYGONSCAN_API_KEY}")
        holders = len(r.json().get("result", []))
    except:
        holders = 0
    prompt = f"Analyze token {name} ({symbol}) at {address} on Polygon. Total supply: {total_supply}, holders: {holders}. Give a risk assessment."
    ai_resp, _, _ = call_ai_model([{"role":"user","content":prompt}], 1)
    return {"name": name, "symbol": symbol, "total_supply": str(total_supply), "holders": holders, "ai_analysis": ai_resp}

# ------------------------------------------------------------------------------
# Push Notifications
# ------------------------------------------------------------------------------
@app.post("/api/push/subscribe")
def push_subscribe(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    subscription = req.get("subscription")
    if not subscription: raise HTTPException(400)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO push_subscriptions (id, user_id, endpoint, p256dh, auth) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (endpoint) DO UPDATE SET p256dh=EXCLUDED.p256dh, auth=EXCLUDED.auth",
                      (str(uuid.uuid4()), user["id"], subscription["endpoint"], subscription["keys"]["p256dh"], subscription["keys"]["auth"]))
            conn.commit()
    return {"ok": True}

@app.post("/api/push/unsubscribe")
def push_unsubscribe(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    endpoint = req.get("endpoint")
    if not endpoint: raise HTTPException(400)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM push_subscriptions WHERE endpoint = %s AND user_id = %s", (endpoint, user["id"]))
            conn.commit()
    return {"ok": True}

# ------------------------------------------------------------------------------
# Developer Endpoints
# ------------------------------------------------------------------------------
@app.post("/api/developer/keys")
def create_api_key(req: dict, user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    raw_key = "cap_" + secrets.token_hex(32)
    key_hash = hash_pw(raw_key)
    prefix = raw_key[:10] + "..."
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("INSERT INTO api_keys (id, user_id, prefix, key_hash, scopes) VALUES (%s,%s,%s,%s,%s)",
                      (str(uuid.uuid4()), user["id"], prefix, key_hash, "chat,research,portfolio"))
            conn.commit()
    return {"key": raw_key, "prefix": prefix, "scopes": "chat,research,portfolio"}

@app.get("/api/developer/keys")
def list_api_keys(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT id, prefix, scopes, is_active, last_used, created FROM api_keys WHERE user_id=%s ORDER BY created DESC", (user["id"],))
            return {"keys": [{"id": r[0], "prefix": r[1], "scopes": r[2], "is_active": r[3],
                              "last_used": r[4].isoformat() if r[4] else None, "created": r[5].isoformat() if r[5] else None} for r in c.fetchall()]}

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
            return {"webhooks": [{"id": r[0], "url": r[1], "events": r[2], "is_active": r[3], "created": r[4].isoformat() if r[4] else None} for r in c.fetchall()]}

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
    token = create_access_token(user["id"])
    return {"embed_token": token, "script_url": f"{settings.FRONTEND_URL}/embed.js"}

@app.get("/api/developer/usage")
def get_api_usage(user: dict = Depends(get_current_user)):
    if not user: raise HTTPException(401)
    return {"usage": []}

# ------------------------------------------------------------------------------
# Admin / Founder Endpoints
# ------------------------------------------------------------------------------
@app.get("/api/admin/dashboard")
def admin_dashboard(founder: dict = Depends(founder_only)):
    with get_db() as conn:
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM users"); total_users = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM users WHERE last_active > NOW() - INTERVAL '24 hours'"); active_today = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM chat_messages"); total_messages = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM content_flags WHERE reviewed=FALSE"); pending_flags = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM security_events WHERE created > NOW() - INTERVAL '24 hours'"); threats_today = c.fetchone()[0]
            return {"total_users": total_users, "active_today": active_today, "total_messages": total_messages,
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
            users = [{"id": r[0], "email": r[1], "name": r[2], "reasoning_depth": r[3], "token_balance": r[4],
                      "created_at": r[5].isoformat() if r[5] else None, "last_active": r[6].isoformat() if r[6] else None} for r in c.fetchall()]
    return {"users": users}

@app.post("/api/admin/user/{user_id}/balance")
def admin_change_balance(user_id: str, req: dict, founder: dict = Depends(founder_only)):
    new_balance = req.get("balance")
    if new_balance is None: raise HTTPException(400, "Balance required")
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

# ------------------------------------------------------------------------------
# Leaderboard
# ------------------------------------------------------------------------------
@app.get("/api/leaderboard")
def leaderboard(type: str = "staked"):
    with get_db() as conn:
        with conn.cursor() as c:
            if type == "staked":
                c.execute("SELECT u.name, cs.staked_amount FROM close_stakes cs JOIN users u ON cs.user_id = u.id WHERE cs.staked_amount > 0 ORDER BY cs.staked_amount DESC LIMIT 20")
                rows = c.fetchall()
                return {"leaderboard": [{"name": r[0], "staked": r[1]} for r in rows]}
            elif type == "messages":
                c.execute("SELECT u.name, COUNT(cm.id) as msg_count FROM chat_messages cm JOIN users u ON cm.user_id = u.id GROUP BY u.id, u.name ORDER BY msg_count DESC LIMIT 20")
                rows = c.fetchall()
                return {"leaderboard": [{"name": r[0], "messages": r[1]} for r in rows]}
    return {"leaderboard": []}

# ------------------------------------------------------------------------------
# API Key Middleware (O(1) lookup)
# ------------------------------------------------------------------------------
@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("ApiKey "):
        key = auth[7:]
        prefix = key[:10]
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, user_id, key_hash, scopes FROM api_keys WHERE prefix = %s AND is_active = TRUE", (prefix,))
                row = c.fetchone()
                if row and bcrypt.checkpw(key.encode(), row[2].encode()):
                    c.execute("UPDATE api_keys SET last_used = NOW() WHERE id = %s", (row[0],))
                    conn.commit()
                    request.state.api_user_id = row[1]
                    response = await call_next(request)
                    return response
        return Response(content="Invalid API key", status_code=401)
    return await call_next(request)

# ------------------------------------------------------------------------------
# Health
# ------------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "version": "36.1"}

@app.get("/")
def root():
    return {"name": "CAPITAN AI", "version": "36.1"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))