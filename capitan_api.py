# ═══════════════════════════════════════════════════════════════
# CAPITAN AI — ELITE INTELLIGENCE API v7.0
# Complete Intelligence Upgrade
# CLOSEAI Technologies — closeaitechnologies@gmail.com
# Deployed on Render: https://goldquantum0-capitan-ai-1.onrender.com
# ═══════════════════════════════════════════════════════════════

import os, re, json, uuid, time, requests, sqlite3
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

# ═══════════════════════════════════════════════════════════════
# COMPLETE API KEY CONFIGURATION
# ═══════════════════════════════════════════════════════════════
KEYS = {
    "OPENROUTER":    os.environ.get("OPENROUTER_API_KEY", ""),
    "OPENAI":        os.environ.get("OPENAI_API_KEY", ""),
    "MISTRAL":       os.environ.get("MISTRAL_API_KEY", ""),
    "GROQ":          os.environ.get("GROQ_API_KEY", ""),
    "HF_TOKEN":      os.environ.get("HF_TOKEN", ""),
    "ZENMUK":        os.environ.get("ZENMUK_API_KEY", ""),
    "ALPHA_VANTAGE": os.environ.get("ALPHA_VANTAGE_KEY", ""),
    "TWELVE_DATA":   os.environ.get("TWELVE_DATA_KEY", ""),
    "COINGECKO":     os.environ.get("COINGECKO_KEY", ""),
    "ETHERSCAN":     os.environ.get("ETHERSCAN_API_KEY", ""),
    "SERPAPI":       os.environ.get("SERPAPI_KEY", ""),
    "GNEWS":         os.environ.get("GNEWS_KEY", ""),
    "NEWSAPI":       os.environ.get("NEWSAPI_KEY", ""),
    "IPGEOLOCATION": os.environ.get("IPGEOLOCATION_KEY", ""),
    "LOCATIONIQ":    os.environ.get("LOCATIONIQ_KEY", ""),
    "SUPABASE_URL":  os.environ.get("SUPABASE_URL", ""),
    "SUPABASE_KEY":  os.environ.get("SUPABASE_KEY", ""),
    "WOLFRAM_APP_ID": os.environ.get("WOLFRAM_APP_ID", ""),
    "ADMIN_CODE":    os.environ.get("ADMIN_CODE", "Osinachi@350"),
}

# ═══════════════════════════════════════════════════════════════
# MODEL ROUTING — Multi-Provider Fallback
# ═══════════════════════════════════════════════════════════════
MODEL_ROUTING = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1/chat/completions",
        "auth_header": lambda: f"Bearer {KEYS['OPENROUTER']}",
        "models": {
            "fast": ["deepseek/deepseek-chat", "meta-llama/llama-3.1-70b-instruct"],
            "smart": ["anthropic/claude-3.5-sonnet", "openai/gpt-4o"],
            "deep": ["deepseek/deepseek-r1", "anthropic/claude-3.5-sonnet"],
        }
    },
    "openai": {
        "base_url": "https://api.openai.com/v1/chat/completions",
        "auth_header": lambda: f"Bearer {KEYS['OPENAI']}",
        "models": {
            "fast": ["gpt-3.5-turbo"],
            "smart": ["gpt-4o", "gpt-4o-mini"],
            "deep": ["gpt-4o"],
        }
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1/chat/completions",
        "auth_header": lambda: f"Bearer {KEYS['MISTRAL']}",
        "models": {
            "fast": ["mistral-small-latest"],
            "smart": ["mistral-large-latest"],
            "deep": ["mistral-large-latest"],
        }
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1/chat/completions",
        "auth_header": lambda: f"Bearer {KEYS['GROQ']}",
        "models": {
            "fast": ["llama-3.1-70b-versatile", "mixtral-8x7b-32768"],
            "smart": ["llama-3.1-70b-versatile"],
            "deep": ["llama-3.1-70b-versatile"],
        }
    },
    "zenmuk": {
        "base_url": "https://api.zenmuk.com/v1/chat/completions",
        "auth_header": lambda: f"Bearer {KEYS['ZENMUK']}",
        "models": {
            "fast": ["zenmuk-fast"],
            "smart": ["zenmuk-pro"],
            "deep": ["zenmuk-pro"],
        }
    },
}

PROVIDER_ORDER = ["openrouter", "openai", "mistral", "groq", "zenmuk"]

# ═══════════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════════
DB_PATH = os.environ.get("DATABASE_PATH", "capitan.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY, memory_id TEXT UNIQUE, user_id TEXT,
        content TEXT, query TEXT, type TEXT, tier TEXT,
        active INTEGER DEFAULT 1, created TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS payments (
        id TEXT PRIMARY KEY, txid TEXT UNIQUE, currency TEXT, amount REAL,
        verified INTEGER DEFAULT 0, user_id TEXT, expires TEXT, created TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS api_keys (
        id TEXT PRIMARY KEY, key TEXT UNIQUE, user_id TEXT,
        active INTEGER DEFAULT 1, created TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY, tier TEXT DEFAULT 'free',
        pro_expiry TEXT, msg_count INTEGER DEFAULT 0,
        msg_window TEXT, created TEXT, preferences TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspaces (
        id TEXT PRIMARY KEY, user_id TEXT, name TEXT,
        members INTEGER DEFAULT 1, created TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS prompts (
        id TEXT PRIMARY KEY, user_id TEXT, title TEXT,
        prompt TEXT, vars TEXT, category TEXT, created TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS search_cache (
        id TEXT PRIMARY KEY, query_hash TEXT UNIQUE, results TEXT,
        created TEXT, expires TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

def short_id(): return str(uuid.uuid4())[:8].upper()
def mem_id(): return 'mem_' + short_id()

# ═══════════════════════════════════════════════════════════════
# GLOBAL MEMORY
# ═══════════════════════════════════════════════════════════════
class Memory:
    @staticmethod
    def add(user_id, content, query=None, mem_type="query", tier="free"):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        mid = mem_id()
        c.execute(
            "INSERT INTO memories (id, memory_id, user_id, content, query, type, tier, created) VALUES (?,?,?,?,?,?,?,?)",
            (short_id(), mid, user_id, content, query, mem_type, tier, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
        return mid

    @staticmethod
    def get_recent(user_id=None, limit=50):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        if user_id:
            c.execute("SELECT memory_id, user_id, content, query, type, tier, created FROM memories WHERE user_id=? ORDER BY created DESC LIMIT ?", (user_id, limit))
        else:
            c.execute("SELECT memory_id, user_id, content, query, type, tier, created FROM memories ORDER BY created DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        return [{"memory_id": r[0], "user_id": r[1], "content": r[2], "query": r[3], "type": r[4], "tier": r[5], "created": r[6]} for r in rows]

    @staticmethod
    def search(query, user_id=None):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        q = f"%{query}%"
        if user_id:
            c.execute("SELECT memory_id, user_id, content, query, type, tier, created FROM memories WHERE user_id=? AND (content LIKE ? OR query LIKE ? OR memory_id LIKE ?) ORDER BY created DESC LIMIT 50", (user_id, q, q, q))
        else:
            c.execute("SELECT memory_id, user_id, content, query, type, tier, created FROM memories WHERE content LIKE ? OR query LIKE ? OR memory_id LIKE ? ORDER BY created DESC LIMIT 50", (q, q, q))
        rows = c.fetchall()
        conn.close()
        return [{"memory_id": r[0], "user_id": r[1], "content": r[2], "query": r[3], "type": r[4], "tier": r[5], "created": r[6]} for r in rows]

    @staticmethod
    def get_user_patterns(user_id):
        """Extract patterns from user's memory history"""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT query, type, tier FROM memories WHERE user_id=? AND type='query' ORDER BY created DESC LIMIT 20", (user_id,))
        rows = c.fetchall()
        conn.close()

        if not rows:
            return None

        domains = {}
        for r in rows:
            domain = classify_domain(r[0] or "")
            domains[domain] = domains.get(domain, 0) + 1

        top_domain = max(domains, key=domains.get) if domains else "general"
        return {
            "total_queries": len(rows),
            "top_domain": top_domain,
            "domain_distribution": domains
        }

# ═══════════════════════════════════════════════════════════════
# USER MANAGEMENT
# ═══════════════════════════════════════════════════════════════
class Users:
    FREE_LIMIT = 20
    FREE_WINDOW_HOURS = 7
    PRO_DAYS = 30

    @staticmethod
    def get_or_create(user_id):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT tier, pro_expiry, msg_count, msg_window FROM users WHERE id=?", (user_id,))
        row = c.fetchone()
        if not row:
            c.execute(
                "INSERT INTO users (id, tier, msg_count, msg_window, created) VALUES (?,?,?,?,?)",
                (user_id, 'free', 0, datetime.now().isoformat(), datetime.now().isoformat())
            )
            conn.commit()
            conn.close()
            return {"tier": "free", "pro_expiry": None, "msg_count": 0, "msg_window": datetime.now().isoformat()}
        conn.close()
        tier, pro_expiry, msg_count, msg_window = row

        if tier in ('pro', 'founder') and pro_expiry:
            if datetime.now() > datetime.fromisoformat(pro_expiry):
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("UPDATE users SET tier='free', pro_expiry=NULL WHERE id=?", (user_id,))
                conn.commit()
                conn.close()
                return {"tier": "free", "pro_expiry": None, "msg_count": 0, "msg_window": datetime.now().isoformat()}

        return {"tier": tier, "pro_expiry": pro_expiry, "msg_count": msg_count or 0, "msg_window": msg_window or datetime.now().isoformat()}

    @staticmethod
    def check_limit(user_id):
        user = Users.get_or_create(user_id)
        if user["tier"] != "free":
            return True, float('inf')

        window = datetime.fromisoformat(user["msg_window"])
        if datetime.now() - window > timedelta(hours=Users.FREE_WINDOW_HOURS):
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("UPDATE users SET msg_count=0, msg_window=? WHERE id=?", (datetime.now().isoformat(), user_id))
            conn.commit()
            conn.close()
            user["msg_count"] = 0

        remaining = Users.FREE_LIMIT - user["msg_count"]
        return user["msg_count"] < Users.FREE_LIMIT, remaining

    @staticmethod
    def increment(user_id):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE users SET msg_count = msg_count + 1 WHERE id=?", (user_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def activate_pro(user_id):
        expiry = (datetime.now() + timedelta(days=Users.PRO_DAYS)).isoformat()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE users SET tier='pro', pro_expiry=?, msg_count=0 WHERE id=?", (expiry, user_id))
        conn.commit()
        conn.close()

# ═══════════════════════════════════════════════════════════════
# LLM CALLER — Multi-Provider Fallback
# ═══════════════════════════════════════════════════════════════
def call_llm(messages, tier="free", stream=False):
    model_tier = "smart" if tier in ("pro", "founder") else "fast"

    for provider_name in PROVIDER_ORDER:
        provider = MODEL_ROUTING.get(provider_name)
        if not provider:
            continue

        auth = provider["auth_header"]()
        if not auth or auth == "Bearer ":
            continue

        models = provider["models"].get(model_tier, provider["models"]["fast"])

        for model in models:
            try:
                headers = {
                    "Authorization": auth,
                    "Content-Type": "application/json"
                }
                if provider_name == "openrouter":
                    headers["HTTP-Referer"] = "https://capitan.pages.dev"
                    headers["X-Title"] = "CAPITAN AI"

                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 1500,
                    "stream": stream
                }

                r = requests.post(
                    provider["base_url"],
                    headers=headers,
                    json=payload,
                    timeout=180,
                    stream=stream
                )

                if r.status_code == 200:
                    return r if stream else r.json()["choices"][0]["message"]["content"]
                if r.status_code == 401:
                    break
            except Exception:
                continue

    return None if stream else _ultimate_fallback(messages)

def _ultimate_fallback(messages):
    user_msg = ""
    for msg in reversed(messages):
        if msg["role"] == "user":
            user_msg = msg["content"]
            break

    greeting_words = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening"]
    if any(user_msg.lower().startswith(w) for w in greeting_words):
        return "Hello! I'm CAPITAN AI. I'm currently experiencing high demand across all AI providers. Please try again in a moment, or contact closeaitechnologies@gmail.com if this persists."

    return (
        "I'm CAPITAN AI. All AI providers are temporarily at capacity — this happens during peak usage. "
        "Your query is important. Please try again in 30 seconds, or email closeaitechnologies@gmail.com for priority support.\n\n"
        f"Your query was: '{user_msg[:100]}...'"
    )

# ═══════════════════════════════════════════════════════════════
# DOMAIN CLASSIFICATION — UPGRADED
# ═══════════════════════════════════════════════════════════════
def classify_domain(query):
    q = query.lower()

    patterns = {
        "greeting": [
            r'^(hi|hello|hey|good morning|good afternoon|good evening|howdy|yo|sup)\b',
            r'\b(how are you|what\'s up|how\'s it going|how do you do)\b'
        ],
        "help": [
            r'^(help|assist|support|oh no|what|huh|hmm|um|uh)\b',
            r'\b(i need help|can you help|help me|i\'m stuck|i don\'t understand)\b'
        ],
        "gratitude": [
            r'\b(thank you|thanks|appreciate|grateful|you\'re amazing|great job|well done)\b'
        ],
        "coding": [
            r'```', r'\bdef\s+\w+\s*\(', r'\bclass\s+\w+',
            r'\b(write|implement|code|refactor|debug|optimize|build|create)\b.*\b(function|class|api|algorithm|program|script)\b',
            r'\b(python|numpy|pandas|javascript|typescript|sql|rust|go|java|react|node|html|css)\b',
            r'\b(explain|how does|what is)\b.*\b(code|programming|algorithm|api|framework)\b'
        ],
        "quant": [
            r'\b(monte carlo|black.scholes|stochastic|option pricing|var|cvar|sharpe|sortino|backtest|alpha generation|factor model)\b',
            r'\b(calculate|compute|derive)\b.*\b(volatility|correlation|covariance|beta|risk)\b'
        ],
        "quantum": [
            r'\b(quantum|qubit|qiskit|entanglement|superposition|quantum circuit|quantum gate|bell state|bloch sphere)\b'
        ],
        "macro": [
            r'\b(gdp|inflation|recession|fiscal policy|monetary policy|central bank|fed|ecb|interest rate|yield curve|fomc)\b',
            r'\b(what is|explain|how does)\b.*\b(economy|economic|macro|monetary|fiscal)\b'
        ],
        "finance": [
            r'\b(revenue|earnings|ebitda|valuation|pe ratio|dcf|wacc|irr|npv|stock|bond|equity|crypto|bitcoin|ethereum)\b',
            r'\b(analyze|analysis|outlook|forecast)\b.*\b(market|stock|sector|industry)\b',
            r'\b(what is|explain)\b.*\b(investing|trading|stock|bond|etf|mutual fund|derivative)\b',
            r'\b(compare|versus|vs)\b.*\b(stock|company|sector|market)\b'
        ],
        "math": [
            r'\b(prove|proof|theorem|lemma|derive|integral|derivative|linear algebra|eigenvalue|matrix|calculus)\b',
            r'\b(solve|calculate|compute)\b.*\b(equation|integral|derivative|limit|sum)\b'
        ],
        "science": [
            r'\b(crispr|dna|physics|chemistry|biology|neuroscience|gene|cell|molecule|atom|particle|experiment)\b',
            r'\b(how does|explain|what is)\b.*\b(work|function|process)\b.*\b(biology|chemistry|physics|science)\b'
        ],
    }

    for domain, pats in patterns.items():
        for p in pats:
            if re.search(p, q):
                if domain in ("greeting", "help", "gratitude"):
                    return "general"
                return domain

    return "general"

# ═══════════════════════════════════════════════════════════════
# UPGRADED SYSTEM PROMPT — Natural, Direct, Helpful
# ═══════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """You are CAPITAN AI — an institutional intelligence system by CLOSEAI Technologies.

IDENTITY:
Direct, knowledgeable, genuinely helpful. Warm through competence, not forced enthusiasm. Like a trusted senior colleague.

RESPONSE STYLE:
• Lead with the answer — most important sentence first
• 2-3 sentences of context, then offer to go deeper
• Natural and conversational, not robotic
• Use **bold** sparingly for key terms only
• Code in ```blocks``` with language labels
• Tables only when comparing 3+ items
• Short paragraphs, scannable

FOR UNCLEAR QUERIES (like "oh no", "what?", "help"):
• Ask ONE clarifying question: "What specifically do you need help with?"
• Don't list options unless they ask

FOR GREETINGS:
• Respond warmly but briefly
• Ask what they're working on today

FOR GRATITUDE:
• "Glad it helped. What's next?"

RULES:
• Never give trading signals, entry/exit prices, or buy/sell recommendations
• If asked for opinions, frame as analysis with evidence
• If you don't know, say so directly and offer to research
• Acknowledge errors honestly
• Calibrate confidence: use phrases like "Based on current data..." or "The evidence suggests..."

DOMAIN: {domain}
TIER: {tier}"""

# ═══════════════════════════════════════════════════════════════
# MARKET DATA PROVIDERS
# ═══════════════════════════════════════════════════════════════
class MarketData:
    @staticmethod
    def get_prices():
        results = {}
        tickers = {
            "^GSPC": "S&P 500", "^IXIC": "NASDAQ", "^DJI": "Dow Jones",
            "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "Nvidia",
            "TSLA": "Tesla", "GOOGL": "Alphabet", "META": "Meta",
            "GC=F": "Gold", "CL=F": "Crude Oil", "SI=F": "Silver",
            "EURUSD=X": "EUR/USD", "GBPUSD=X": "GBP/USD", "USDJPY=X": "USD/JPY"
        }
        try:
            symbols = ",".join(tickers.keys())
            r = requests.get(
                "https://query1.finance.yahoo.com/v7/finance/quote",
                params={"symbols": symbols, "fields": "regularMarketPrice,regularMarketPreviousClose,shortName"},
                timeout=5,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if r.status_code == 200:
                for item in r.json().get("quoteResponse", {}).get("result", []):
                    sym = item.get("symbol", "")
                    pr = item.get("regularMarketPrice")
                    pv = item.get("regularMarketPreviousClose")
                    name = item.get("shortName", tickers.get(sym, sym))
                    if pr and pv and pr > 0:
                        results[name] = {"price": pr, "change_pct": round(((pr - pv) / pv) * 100, 2)}
        except Exception:
            pass

        # Crypto
        try:
            r = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "bitcoin,ethereum,solana", "vs_currencies": "usd", "include_24hr_change": "true"},
                timeout=5
            )
            if r.status_code == 200:
                for name in ["bitcoin", "ethereum", "solana"]:
                    coin = r.json().get(name, {})
                    if coin.get("usd"):
                        results[name.capitalize()] = {"price": coin["usd"], "change_pct": round(coin.get("usd_24h_change", 0), 2)}
        except Exception:
            pass

        return results

    @staticmethod
    def get_news():
        items = []
        # GNews
        if KEYS["GNEWS"]:
            try:
                r = requests.get(
                    "https://gnews.io/api/v4/top-headlines",
                    params={"category": "business", "lang": "en", "max": 5, "apikey": KEYS["GNEWS"]},
                    timeout=5
                )
                if r.status_code == 200:
                    for a in r.json().get("articles", []):
                        items.append({"title": a["title"], "source": a["source"]["name"]})
            except Exception:
                pass

        # Yahoo RSS fallback
        if not items:
            try:
                r = requests.get(
                    "https://finance.yahoo.com/news/rssindex",
                    timeout=5,
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                if r.status_code == 200:
                    import xml.etree.ElementTree as ET
                    for item in ET.fromstring(r.content).findall('.//item')[:5]:
                        title = item.find('title')
                        if title is not None and title.text:
                            items.append({"title": title.text.strip(), "source": "Yahoo Finance"})
            except Exception:
                pass

        return items

# ═══════════════════════════════════════════════════════════════
# INTELLIGENCE GATHERING
# ═══════════════════════════════════════════════════════════════
def gather_intelligence(query: str, domain: str, is_pro: bool, user_id: str = None) -> str:
    """Gather all available intelligence for context injection"""
    parts = []

    # Market data for finance/macro queries
    if is_pro and domain in ("finance", "macro", "general"):
        try:
            prices = MarketData.get_prices()
            if prices:
                parts.append("## LIVE MARKET DATA")
                for name, data in list(prices.items())[:8]:
                    arrow = "▲" if data["change_pct"] >= 0 else "▼"
                    parts.append(f"{name}: ${data['price']:,.2f} ({arrow} {abs(data['change_pct']):.2f}%)")

            news = MarketData.get_news()
            if news:
                parts.append("\n## RECENT HEADLINES")
                for n in news[:5]:
                    parts.append(f"• {n['title'][:120]}")
        except Exception:
            pass

    # Memory context for returning users
    if user_id:
        try:
            recent = Memory.get_recent(user_id, limit=3)
            if recent:
                parts.append("\n## YOUR RECENT CONTEXT")
                for mem in recent[:3]:
                    snippet = (mem.get("query") or mem.get("content") or "")[:100]
                    if snippet:
                        parts.append(f"• {snippet}")
                parts.append("Use this for continuity. Don't mention it unless relevant.")
        except Exception:
            pass

    return "\n".join(parts)

# ═══════════════════════════════════════════════════════════════
# CRYPTO VERIFICATION
# ═══════════════════════════════════════════════════════════════
CRYPTO_ADDRESSES = {
    "BTC": "bc1qrv6yr6e0mat96rvrc8smdf9rvu9rlp8xuk8new",
    "ETH": "0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1",
    "USDC": "0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1",
}
PRO_PRICE_CRYPTO = {"BTC": 0.00028, "ETH": 0.005, "USDC": 17}

def verify_crypto(txid, currency, amount):
    txid = txid.strip()
    if not txid:
        return False, "No TXID provided"

    if currency == "BTC" and not re.match(r'^[a-fA-F0-9]{64}$', txid):
        return False, "Invalid Bitcoin TXID"
    if currency in ("ETH", "USDC") and not re.match(r'^0x[a-fA-F0-9]{64}$', txid):
        return False, "Invalid Ethereum TXID"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM payments WHERE txid=?", (txid,))
    if c.fetchone():
        conn.close()
        return False, "TXID already used"
    conn.close()

    try:
        if currency == "BTC":
            for url in [f"https://blockchain.info/rawtx/{txid}", f"https://blockstream.info/api/tx/{txid}"]:
                try:
                    r = requests.get(url, timeout=10)
                    if r.status_code != 200:
                        continue
                    outputs = r.json().get("out") or r.json().get("vout") or []
                    for out in outputs:
                        addr = out.get("addr") or out.get("scriptpubkey_address", "")
                        if addr == CRYPTO_ADDRESSES["BTC"]:
                            val = out.get("value", 0)
                            if val > 1:
                                val /= 100_000_000
                            if abs(val - amount) < 0.00005:
                                return True, "Verified on Bitcoin ✓"
                            return False, f"Amount mismatch"
                    return False, "Address not in transaction"
                except Exception:
                    continue
            return False, "Could not verify BTC"

        if currency in ("ETH", "USDC"):
            api_key = KEYS["ETHERSCAN"] or "YourApiKeyToken"
            r = requests.get("https://api.etherscan.io/api", params={
                "module": "proxy", "action": "eth_getTransactionByHash",
                "txhash": txid, "apikey": api_key
            }, timeout=10)
            if r.status_code != 200:
                return False, "Etherscan unavailable"
            txd = r.json().get("result", {})
            if not txd:
                return False, "Transaction not found"
            if txd.get("to", "").lower() != CRYPTO_ADDRESSES["ETH"].lower():
                return False, "Wrong destination"
            val = int(txd.get("value", "0"), 16) / 1e18
            if abs(val - amount) < 0.001:
                return True, "Verified on Ethereum ✓"
            return False, "Amount mismatch"
    except Exception as e:
        return False, str(e)[:100]

    return False, "Unsupported currency"

def record_payment(txid, currency, amount, user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO payments (id, txid, currency, amount, verified, user_id, expires, created) VALUES (?,?,?,?,?,?,?,?)",
        (short_id(), txid, currency, amount, 1, user_id,
         (datetime.now() + timedelta(days=Users.PRO_DAYS)).isoformat(),
         datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

# ═══════════════════════════════════════════════════════════════
# REQUEST MODELS
# ═══════════════════════════════════════════════════════════════
class ChatRequest(BaseModel):
    messages: List[dict]
    stream: bool = True
    user_id: str = "anonymous"
    model: str = "balanced"

class PaymentVerifyRequest(BaseModel):
    txid: str
    currency: str
    user_id: str = "anonymous"

class MemoryRequest(BaseModel):
    content: str
    user_id: str = "anonymous"

class AdminRequest(BaseModel):
    admin_code: str
    search: Optional[str] = None

class WorkspaceRequest(BaseModel):
    name: str
    user_id: str = "anonymous"

# ═══════════════════════════════════════════════════════════════
# FASTAPI APP
# ═══════════════════════════════════════════════════════════════
app = FastAPI(title="CAPITAN AI API", version="7.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    active = [p for p in PROVIDER_ORDER if MODEL_ROUTING[p]["auth_header"]() not in ("Bearer ", "")]
    services = []
    if KEYS["ALPHA_VANTAGE"]: services.append("Alpha Vantage")
    if KEYS["GNEWS"]: services.append("GNews")
    if KEYS["SERPAPI"]: services.append("SerpAPI")
    if KEYS["WOLFRAM_APP_ID"]: services.append("Wolfram Alpha")
    if KEYS["ETHERSCAN"]: services.append("Etherscan")

    return {
        "name": "CAPITAN AI API",
        "version": "7.0",
        "status": "operational",
        "intelligence": "upgraded — natural responses, memory context, domain awareness",
        "ai_providers": active,
        "data_services": services,
        "endpoints": ["/api/chat", "/api/prices", "/api/news", "/api/verify-payment", "/api/memory", "/api/admin/memory"]
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "version": "7.0"}

# ═══════════════════════════════════════════════════════════════
# CHAT ENDPOINT — FULLY UPGRADED
# ═══════════════════════════════════════════════════════════════
@app.post("/api/chat")
async def chat(req: ChatRequest):
    user = Users.get_or_create(req.user_id)
    is_pro = user["tier"] in ("pro", "founder")

    # Check limits
    if not is_pro:
        can_send, remaining = Users.check_limit(req.user_id)
        if not can_send:
            raise HTTPException(
                status_code=429,
                detail=f"Message limit reached ({Users.FREE_LIMIT} per {Users.FREE_WINDOW_HOURS}h). Upgrade to Pro for unlimited."
            )

    # Extract user message
    user_msg = ""
    for msg in reversed(req.messages):
        if msg.get("role") == "user":
            user_msg = msg.get("content", "")
            break

    if not user_msg:
        raise HTTPException(status_code=400, detail="No message found")

    # Classify domain
    domain = classify_domain(user_msg)

    # Block pro domains
    pro_domains = ["quant", "quantum", "coding", "math", "science"]
    if not is_pro and domain in pro_domains:
        raise HTTPException(
            status_code=403,
            detail=f"'{domain}' features require Pro ($17/month). Finance and general queries are always free."
        )

    # Store query
    Memory.add(req.user_id, user_msg, query=user_msg, mem_type="query", tier=user["tier"])

    # Increment count
    if not is_pro:
        Users.increment(req.user_id)

    # Gather intelligence
    intelligence = gather_intelligence(user_msg, domain, is_pro, req.user_id)

    # Build system prompt
    system_content = SYSTEM_PROMPT.format(domain=domain, tier=user["tier"])
    if intelligence:
        system_content += "\n\n" + intelligence

    # Build messages for LLM
    llm_messages = [{"role": "system", "content": system_content}]
    for msg in req.messages:
        llm_messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

    # Streaming response
    if req.stream:
        response = call_llm(llm_messages, tier=user["tier"], stream=True)

        if not response:
            fallback = _ultimate_fallback(llm_messages)
            async def gen_fallback():
                yield f"data: {json.dumps({'content': fallback})}\n\n"
                mid = Memory.add(req.user_id, fallback, query=user_msg, mem_type="response", tier=user["tier"])
                yield f"data: {json.dumps({'done': True, 'memory_id': mid})}\n\n"
            return StreamingResponse(gen_fallback(), media_type="text/event-stream")

        async def generate():
            full = ""
            for line in response.iter_lines():
                if line:
                    line = line.decode("utf-8")
                    if line.startswith("data: "):
                        d = line[6:]
                        if d == "[DONE]":
                            break
                        try:
                            delta = json.loads(d).get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if delta:
                                full += delta
                                yield f"data: {json.dumps({'content': full})}\n\n"
                        except Exception:
                            continue

            if full:
                mid = Memory.add(req.user_id, full, query=user_msg, mem_type="response", tier=user["tier"])
                yield f"data: {json.dumps({'done': True, 'memory_id': mid, 'domain': domain})}\n\n"
            else:
                yield f"data: {json.dumps({'done': True, 'domain': domain})}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")
    else:
        response = call_llm(llm_messages, tier=user["tier"], stream=False)
        mid = Memory.add(req.user_id, response, query=user_msg, mem_type="response", tier=user["tier"])
        return {"content": response, "memory_id": mid, "domain": domain}

# ═══════════════════════════════════════════════════════════════
# MARKET ENDPOINTS
# ═══════════════════════════════════════════════════════════════
@app.get("/api/prices")
async def prices():
    return {"prices": MarketData.get_prices(), "timestamp": datetime.now().isoformat()}

@app.get("/api/news")
async def news():
    return {"news": MarketData.get_news(), "timestamp": datetime.now().isoformat()}

# ═══════════════════════════════════════════════════════════════
# PAYMENT
# ═══════════════════════════════════════════════════════════════
@app.post("/api/verify-payment")
async def verify_payment(req: PaymentVerifyRequest):
    currency = req.currency.upper()
    if currency not in PRO_PRICE_CRYPTO:
        raise HTTPException(status_code=400, detail="Unsupported currency")

    amount = PRO_PRICE_CRYPTO[currency]
    verified, message = verify_crypto(req.txid, currency, amount)

    if verified:
        record_payment(req.txid, currency, amount, req.user_id)
        Users.activate_pro(req.user_id)
        return {"verified": True, "message": message, "plan": "pro", "expires_days": Users.PRO_DAYS}

    return {"verified": False, "message": message}

# ═══════════════════════════════════════════════════════════════
# MEMORY
# ═══════════════════════════════════════════════════════════════
@app.get("/api/memory")
async def get_memories(user_id: str = "anonymous", limit: int = 50):
    memories = Memory.get_recent(user_id, limit)
    patterns = Memory.get_user_patterns(user_id)
    return {"memories": memories, "count": len(memories), "patterns": patterns}

@app.post("/api/memory")
async def add_memory(req: MemoryRequest):
    mid = Memory.add(req.user_id, req.content, mem_type="manual")
    return {"memory_id": mid, "status": "saved"}

@app.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM memories WHERE memory_id=?", (memory_id,))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return {"status": "deleted" if deleted else "not found"}

# ═══════════════════════════════════════════════════════════════
# ADMIN
# ═══════════════════════════════════════════════════════════════
@app.post("/api/admin/memory")
async def admin_memory(req: AdminRequest):
    if req.admin_code != KEYS["ADMIN_CODE"]:
        raise HTTPException(status_code=403, detail="Invalid admin code")

    memories = Memory.search(req.search) if req.search else Memory.get_recent(limit=100)
    return {"memories": memories, "count": len(memories), "access": "admin"}

# ═══════════════════════════════════════════════════════════════
# WORKSPACES
# ═══════════════════════════════════════════════════════════════
@app.get("/api/workspaces")
async def get_workspaces(user_id: str = "anonymous"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, members, created FROM workspaces WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()
    return {"workspaces": [{"id": r[0], "name": r[1], "members": r[2], "created": r[3]} for r in rows]}

@app.post("/api/workspaces")
async def create_workspace(req: WorkspaceRequest):
    wid = short_id()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO workspaces (id, user_id, name, members, created) VALUES (?,?,?,?,?)",
              (wid, req.user_id, req.name, 1, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return {"id": wid, "name": req.name, "status": "created"}

# ═══════════════════════════════════════════════════════════════
# API KEYS
# ═══════════════════════════════════════════════════════════════
@app.get("/api/keys")
async def get_keys(user_id: str = "anonymous"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, key, active, created FROM api_keys WHERE user_id=? AND active=1", (user_id,))
    rows = c.fetchall()
    conn.close()
    return {"keys": [{"id": r[0], "key": r[1], "active": r[2], "created": r[3]} for r in rows]}

@app.post("/api/keys")
async def create_key(user_id: str = "anonymous"):
    key = "cap_" + str(uuid.uuid4()).replace("-", "")[:24]
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO api_keys (id, key, user_id, created) VALUES (?,?,?,?)",
              (short_id(), key, user_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return {"key": key, "status": "created"}

# ═══════════════════════════════════════════════════════════════
# USER STATUS
# ═══════════════════════════════════════════════════════════════
@app.get("/api/user/{user_id}")
async def get_user(user_id: str):
    user = Users.get_or_create(user_id)
    can_send, remaining = Users.check_limit(user_id)
    patterns = Memory.get_user_patterns(user_id)
    return {
        "user_id": user_id,
        "tier": user["tier"],
        "pro_expiry": user["pro_expiry"],
        "can_message": can_send,
        "remaining": remaining if user["tier"] == "free" else "unlimited",
        "patterns": patterns
    }

# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    active_providers = [p for p in PROVIDER_ORDER if MODEL_ROUTING[p]["auth_header"]() not in ("Bearer ", "")]
    print(f"⚓ CAPITAN AI API v7.0 starting on port {port}")
    print(f"   Active AI providers: {active_providers}")
    print(f"   Intelligence: upgraded — natural responses, memory context, domain awareness")
    uvicorn.run(app, host="0.0.0.0", port=port)