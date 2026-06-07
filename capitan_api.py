# ═══════════════════════════════════════════════════════════════
# CAPITAN AI — ULTIMATE API SERVER v6.0
# ALL API Keys Integrated · Render Deployment
# CLOSEAI Technologies — closeaitechnologies@gmail.com
# ═══════════════════════════════════════════════════════════════

import os, re, json, uuid, time, requests, sqlite3
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
import uvicorn

# ═══════════════════════════════════════════════════════════════
# COMPLETE API KEY CONFIGURATION
# ═══════════════════════════════════════════════════════════════
KEYS = {
    # AI Providers
    "OPENROUTER":    os.environ.get("OPENROUTER_API_KEY", ""),
    "OPENAI":        os.environ.get("OPENAI_API_KEY", ""),
    "MISTRAL":       os.environ.get("MISTRAL_API_KEY", ""),
    "GROQ":          os.environ.get("GROQ_API_KEY", ""),
    "HF_TOKEN":      os.environ.get("HF_TOKEN", ""),
    "ZENMUK":        os.environ.get("ZENMUK_API_KEY", ""),
    
    # Market Data
    "ALPHA_VANTAGE": os.environ.get("ALPHA_VANTAGE_KEY", ""),
    "TWELVE_DATA":   os.environ.get("TWELVE_DATA_KEY", ""),
    "COINGECKO":     os.environ.get("COINGECKO_KEY", ""),  # Optional, basic tier is free
    
    # Blockchain
    "ETHERSCAN":     os.environ.get("ETHERSCAN_API_KEY", ""),
    
    # Search & News
    "SERPAPI":       os.environ.get("SERPAPI_KEY", ""),
    "GNEWS":         os.environ.get("GNEWS_KEY", ""),
    "NEWSAPI":       os.environ.get("NEWSAPI_KEY", ""),
    
    # Location
    "IPGEOLOCATION": os.environ.get("IPGEOLOCATION_KEY", ""),
    "LOCATIONIQ":    os.environ.get("LOCATIONIQ_KEY", ""),
    
    # Database
    "SUPABASE_URL":  os.environ.get("SUPABASE_URL", ""),
    "SUPABASE_KEY":  os.environ.get("SUPABASE_KEY", ""),
    
    # Computation
    "WOLFRAM_APP_ID": os.environ.get("WOLFRAM_APP_ID", ""),
    
    # Admin
    "ADMIN_CODE":    os.environ.get("ADMIN_CODE", "Osinachi@350"),
    "FOUNDER_KEY":   os.environ.get("FOUNDER_KEY", "cap-founder-key"),
}

# ═══════════════════════════════════════════════════════════════
# MODEL ROUTING — Multi-Provider Fallback
# ═══════════════════════════════════════════════════════════════
MODEL_ROUTING = {
    # Primary: OpenRouter (access to all models)
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1/chat/completions",
        "auth_header": lambda: f"Bearer {KEYS['OPENROUTER']}",
        "models": {
            "fast": ["deepseek/deepseek-chat", "meta-llama/llama-3.1-70b-instruct"],
            "smart": ["anthropic/claude-3.5-sonnet", "openai/gpt-4o"],
            "deep": ["deepseek/deepseek-r1", "anthropic/claude-3.5-sonnet"],
        }
    },
    # Fallback 1: OpenAI Direct
    "openai": {
        "base_url": "https://api.openai.com/v1/chat/completions",
        "auth_header": lambda: f"Bearer {KEYS['OPENAI']}",
        "models": {
            "fast": ["gpt-3.5-turbo"],
            "smart": ["gpt-4o", "gpt-4o-mini"],
            "deep": ["gpt-4o"],
        }
    },
    # Fallback 2: Mistral
    "mistral": {
        "base_url": "https://api.mistral.ai/v1/chat/completions",
        "auth_header": lambda: f"Bearer {KEYS['MISTRAL']}",
        "models": {
            "fast": ["mistral-small-latest"],
            "smart": ["mistral-large-latest"],
            "deep": ["mistral-large-latest"],
        }
    },
    # Fallback 3: Groq (fastest)
    "groq": {
        "base_url": "https://api.groq.com/openai/v1/chat/completions",
        "auth_header": lambda: f"Bearer {KEYS['GROQ']}",
        "models": {
            "fast": ["llama-3.1-70b-versatile", "mixtral-8x7b-32768"],
            "smart": ["llama-3.1-70b-versatile"],
            "deep": ["llama-3.1-70b-versatile"],
        }
    },
    # Fallback 4: Zenmuk
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
# MARKET DATA PROVIDERS — Multi-Source Fallback
# ═══════════════════════════════════════════════════════════════
class MarketDataProviders:
    @staticmethod
    def get_stock_price_yahoo(symbols: list) -> dict:
        """Yahoo Finance — Free, no key needed"""
        try:
            r = requests.get(
                "https://query1.finance.yahoo.com/v7/finance/quote",
                params={"symbols": ",".join(symbols), "fields": "regularMarketPrice,regularMarketPreviousClose,shortName"},
                timeout=5,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if r.status_code == 200:
                results = {}
                for item in r.json().get("quoteResponse", {}).get("result", []):
                    sym = item.get("symbol", "")
                    pr = item.get("regularMarketPrice")
                    pv = item.get("regularMarketPreviousClose")
                    name = item.get("shortName", sym)
                    if pr and pv and pr > 0:
                        results[sym] = {"name": name, "price": pr, "change_pct": round(((pr - pv) / pv) * 100, 2)}
                return results
        except: pass
        return {}
    
    @staticmethod
    def get_stock_price_alpha_vantage(symbol: str) -> dict:
        """Alpha Vantage — Free tier"""
        if not KEYS["ALPHA_VANTAGE"]: return {}
        try:
            r = requests.get(
                "https://www.alphavantage.co/query",
                params={"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": KEYS["ALPHA_VANTAGE"]},
                timeout=10
            )
            if r.status_code == 200:
                data = r.json().get("Global Quote", {})
                if data:
                    return {
                        "price": float(data.get("05. price", 0)),
                        "change_pct": float(data.get("10. change percent", "0%").replace("%", ""))
                    }
        except: pass
        return {}
    
    @staticmethod
    def get_stock_price_twelve_data(symbols: list) -> dict:
        """Twelve Data — Free tier"""
        if not KEYS["TWELVE_DATA"]: return {}
        results = {}
        for sym in symbols[:5]:  # Rate limit protection
            try:
                r = requests.get(
                    f"https://api.twelvedata.com/price",
                    params={"symbol": sym, "apikey": KEYS["TWELVE_DATA"]},
                    timeout=5
                )
                if r.status_code == 200:
                    data = r.json()
                    if "price" in data:
                        results[sym] = {"price": float(data["price"]), "change_pct": 0}
            except: pass
        return results
    
    @staticmethod
    def get_crypto_prices() -> dict:
        """CoinGecko — Free tier"""
        try:
            r = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    "ids": "bitcoin,ethereum,solana,cardano,ripple",
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                    "x_cg_demo_api_key": KEYS["COINGECKO"]
                },
                timeout=8
            )
            if r.status_code == 200:
                results = {}
                for name, data in r.json().items():
                    if data.get("usd"):
                        results[name.capitalize()] = {
                            "price": data["usd"],
                            "change_pct": round(data.get("usd_24h_change", 0), 2)
                        }
                return results
        except: pass
        return {}

# ═══════════════════════════════════════════════════════════════
# NEWS PROVIDERS
# ═══════════════════════════════════════════════════════════════
class NewsProviders:
    @staticmethod
    def get_gnews() -> list:
        """GNews API"""
        if not KEYS["GNEWS"]: return []
        try:
            r = requests.get(
                "https://gnews.io/api/v4/top-headlines",
                params={"category": "business", "lang": "en", "max": 10, "apikey": KEYS["GNEWS"]},
                timeout=8
            )
            if r.status_code == 200:
                return [
                    {"title": a["title"], "source": a["source"]["name"], "url": a["url"]}
                    for a in r.json().get("articles", [])
                ]
        except: pass
        return []
    
    @staticmethod
    def get_newsapi() -> list:
        """NewsAPI"""
        if not KEYS["NEWSAPI"]: return []
        try:
            r = requests.get(
                "https://newsapi.org/v2/top-headlines",
                params={"category": "business", "language": "en", "pageSize": 10, "apiKey": KEYS["NEWSAPI"]},
                timeout=8
            )
            if r.status_code == 200:
                return [
                    {"title": a["title"], "source": a["source"]["name"], "url": a["url"]}
                    for a in r.json().get("articles", [])
                ]
        except: pass
        return []
    
    @staticmethod
    def get_yahoo_rss() -> list:
        """Yahoo Finance RSS — Free"""
        try:
            r = requests.get(
                "https://finance.yahoo.com/news/rssindex",
                timeout=5,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if r.status_code == 200:
                import xml.etree.ElementTree as ET
                items = []
                for item in ET.fromstring(r.content).findall('.//item')[:10]:
                    title = item.find('title')
                    if title is not None and title.text:
                        items.append({"title": title.text.strip(), "source": "Yahoo Finance"})
                return items
        except: pass
        return []

# ═══════════════════════════════════════════════════════════════
# WEB SEARCH
# ═══════════════════════════════════════════════════════════════
def web_search(query: str, num: int = 5) -> str:
    """Search using SerpAPI"""
    if not KEYS["SERPAPI"]: return ""
    try:
        r = requests.get(
            "https://serpapi.com/search",
            params={"q": query, "num": num, "api_key": KEYS["SERPAPI"], "engine": "google"},
            timeout=8
        )
        if r.status_code == 200:
            results = r.json().get("organic_results", [])
            return "\n\n".join([
                f"[{i+1}] {res.get('title', '')}\n{res.get('snippet', '')}\n{res.get('link', '')}"
                for i, res in enumerate(results[:num])
            ])
    except: pass
    return ""

# ═══════════════════════════════════════════════════════════════
# WOLFRAM ALPHA — Computation Engine
# ═══════════════════════════════════════════════════════════════
def wolfram_query(expression: str) -> str:
    """Wolfram Alpha computation"""
    if not KEYS["WOLFRAM_APP_ID"]: return ""
    try:
        r = requests.get(
            "https://api.wolframalpha.com/v2/query",
            params={
                "input": expression,
                "appid": KEYS["WOLFRAM_APP_ID"],
                "output": "json",
                "format": "plaintext"
            },
            timeout=10
        )
        if r.status_code == 200:
            pods = r.json().get("queryresult", {}).get("pods", [])
            results = []
            for pod in pods[:5]:
                for sub in pod.get("subpods", []):
                    text = sub.get("plaintext", "").strip()
                    if text and len(text) > 1:
                        results.append(f"{pod.get('title', '')}: {text}")
            return "\n".join(results)
    except: pass
    return ""

# ═══════════════════════════════════════════════════════════════
# LOCATION & GEOLOCATION
# ═══════════════════════════════════════════════════════════════
def get_user_location(ip: str = None) -> dict:
    """Get user location from IP"""
    results = {}
    
    # Try IPGeolocation
    if KEYS["IPGEOLOCATION"]:
        try:
            url = f"https://api.ipgeolocation.io/ipgeo"
            params = {"apiKey": KEYS["IPGEOLOCATION"]}
            if ip: params["ip"] = ip
            r = requests.get(url, params=params, timeout=5)
            if r.status_code == 200:
                d = r.json()
                results = {"country": d.get("country_name"), "city": d.get("city"), "currency": d.get("currency", {}).get("code")}
        except: pass
    
    # Fallback to LocationIQ
    if not results and KEYS["LOCATIONIQ"]:
        try:
            r = requests.get(
                "https://us1.locationiq.com/v1/reverse",
                params={"key": KEYS["LOCATIONIQ"], "format": "json"},
                timeout=5
            )
            if r.status_code == 200:
                d = r.json()
                results = {"country": d.get("address", {}).get("country"), "city": d.get("address", {}).get("city")}
        except: pass
    
    return results

# ═══════════════════════════════════════════════════════════════
# DATABASE (SQLite + Supabase)
# ═══════════════════════════════════════════════════════════════
DB_PATH = os.environ.get("DATABASE_PATH", "/var/data/capitan.db")
os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else "/var/data", exist_ok=True)

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
        msg_window TEXT, created TEXT, location TEXT
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

# ═══════════════════════════════════════════════════════════════
# USER MANAGEMENT
# ═══════════════════════════════════════════════════════════════
class Users:
    FREE_LIMIT = 20
    FREE_WINDOW_HOURS = 7
    PRO_DAYS = 30
    
    @staticmethod
    def get_or_create(user_id, ip=None):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT tier, pro_expiry, msg_count, msg_window FROM users WHERE id=?", (user_id,))
        row = c.fetchone()
        if not row:
            location = json.dumps(get_user_location(ip)) if ip else "{}"
            c.execute(
                "INSERT INTO users (id, tier, msg_count, msg_window, location, created) VALUES (?,?,?,?,?,?)",
                (user_id, 'free', 0, datetime.now().isoformat(), location, datetime.now().isoformat())
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
# LLM CALLER — Multi-Provider with Full Fallback
# ═══════════════════════════════════════════════════════════════
def call_llm(messages: list, tier: str = "free", stream: bool = False) -> Any:
    """Call LLM with full provider fallback chain"""
    model_tier = "smart" if tier in ("pro", "founder") else "fast"
    
    for provider_name in PROVIDER_ORDER:
        provider = MODEL_ROUTING.get(provider_name)
        if not provider: continue
        
        auth = provider["auth_header"]()
        if not auth or auth == "Bearer ":
            continue  # Skip if no key configured
        
        models = provider["models"].get(model_tier, provider["models"]["fast"])
        
        for model in models:
            try:
                headers = {
                    "Authorization": auth,
                    "Content-Type": "application/json"
                }
                
                # Add OpenRouter-specific headers
                if provider_name == "openrouter":
                    headers["HTTP-Referer"] = "https://capitan.pages.dev"
                    headers["X-Title"] = "CAPITAN AI"
                
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": 1024,
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
                    if stream:
                        return r  # Return raw response for streaming
                    data = r.json()
                    return data["choices"][0]["message"]["content"]
                
                if r.status_code == 401:
                    break  # Auth error — skip this provider entirely
                    
            except Exception:
                continue
    
    # Ultimate fallback
    return _ultimate_fallback(messages)

def _ultimate_fallback(messages):
    """Final fallback when no API is available"""
    user_msg = ""
    for msg in reversed(messages):
        if msg["role"] == "user":
            user_msg = msg["content"]
            break
    
    return (
        "I'm CAPITAN AI. I'm currently experiencing connectivity issues across all AI providers. "
        "This is a rare occurrence — our systems automatically try OpenRouter, OpenAI, Mistral, Groq, and Zenmuk in sequence. "
        "Please try again in a moment, or contact closeaitechnologies@gmail.com if this persists.\n\n"
        f"Your query was: '{user_msg[:100]}...'"
    )

# ═══════════════════════════════════════════════════════════════
# COMPREHENSIVE DATA GATHERING
# ═══════════════════════════════════════════════════════════════
def gather_intelligence(query: str, domain: str, is_pro: bool) -> str:
    """Gather all available intelligence for a query"""
    context_parts = []
    
    # 1. Market Data
    if is_pro and domain in ("finance", "macro", "general"):
        try:
            # Try Yahoo first (fastest, free)
            yahoo_data = MarketDataProviders.get_stock_price_yahoo([
                "^GSPC", "^IXIC", "AAPL", "MSFT", "NVDA", "TSLA", "GC=F", "CL=F"
            ])
            if yahoo_data:
                context_parts.append("📈 LIVE MARKET DATA:")
                for sym, data in list(yahoo_data.items())[:6]:
                    arrow = "▲" if data["change_pct"] >= 0 else "▼"
                    context_parts.append(f"  {data.get('name', sym)}: ${data['price']:,.2f} ({arrow} {abs(data['change_pct']):.2f}%)")
            
            # Try Twelve Data as backup
            if not yahoo_data:
                twelve_data = MarketDataProviders.get_stock_price_twelve_data(["SPX", "NDX", "AAPL", "MSFT"])
                if twelve_data:
                    context_parts.append("📈 MARKET DATA (Twelve Data):")
                    for sym, data in twelve_data.items():
                        context_parts.append(f"  {sym}: ${data['price']:,.2f}")
            
            # Crypto
            crypto_data = MarketDataProviders.get_crypto_prices()
            if crypto_data:
                context_parts.append("\n₿ CRYPTO:")
                for name, data in crypto_data.items():
                    arrow = "▲" if data["change_pct"] >= 0 else "▼"
                    context_parts.append(f"  {name}: ${data['price']:,.2f} ({arrow} {abs(data['change_pct']):.2f}%)")
        except Exception:
            pass
    
    # 2. News
    if is_pro:
        try:
            news = NewsProviders.get_gnews() or NewsProviders.get_newsapi() or NewsProviders.get_yahoo_rss()
            if news:
                context_parts.append("\n📰 TOP HEADLINES:")
                for n in news[:5]:
                    context_parts.append(f"  • {n['title'][:120]}")
        except Exception:
            pass
    
    # 3. Web Search (for complex queries)
    if is_pro and len(query) > 20:
        try:
            search_results = web_search(query[:200], num=3)
            if search_results:
                context_parts.append("\n🔍 WEB SEARCH:")
                context_parts.append(search_results[:800])
        except Exception:
            pass
    
    # 4. Wolfram Alpha (for math/science queries)
    if domain in ("math", "quant", "science") and len(query) > 10:
        try:
            wolfram_result = wolfram_query(query[:100])
            if wolfram_result:
                context_parts.append("\n🧮 WOLFRAM ALPHA:")
                context_parts.append(wolfram_result[:500])
        except Exception:
            pass
    
    return "\n".join(context_parts)

# ═══════════════════════════════════════════════════════════════
# CRYPTO VERIFICATION
# ═══════════════════════════════════════════════════════════════
CRYPTO_ADDRESSES = {
    "BTC": "bc1qrv6yr6e0mat96rvrc8smdf9rvu9rlp8xuk8new",
    "ETH": "0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1",
    "USDC": "0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1",
}
PRO_PRICE_CRYPTO = {"BTC": 0.00028, "ETH": 0.005, "USDC": 17}

def verify_crypto_payment(txid, currency, amount):
    txid = txid.strip()
    if not txid: return False, "No TXID provided"
    
    if currency == "BTC" and not re.match(r'^[a-fA-F0-9]{64}$', txid):
        return False, "Invalid Bitcoin TXID"
    if currency in ("ETH", "USDC") and not re.match(r'^0x[a-fA-F0-9]{64}$', txid):
        return False, "Invalid Ethereum TXID"
    
    # Check duplicates
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
                    if r.status_code != 200: continue
                    outputs = r.json().get("out") or r.json().get("vout") or []
                    for out in outputs:
                        addr = out.get("addr") or out.get("scriptpubkey_address", "")
                        if addr == CRYPTO_ADDRESSES["BTC"]:
                            val = out.get("value", 0)
                            if val > 1: val /= 100_000_000
                            if abs(val - amount) < 0.00005:
                                return True, "✓ Verified on Bitcoin"
                            return False, f"Amount mismatch: {val:.6f} BTC"
                    return False, "Address not in transaction"
                except: continue
            return False, "Could not verify"
        
        if currency in ("ETH", "USDC"):
            api_key = KEYS["ETHERSCAN"] or "YourApiKeyToken"
            r = requests.get("https://api.etherscan.io/api", params={
                "module": "proxy", "action": "eth_getTransactionByHash",
                "txhash": txid, "apikey": api_key
            }, timeout=10)
            if r.status_code != 200: return False, "Etherscan unavailable"
            txd = r.json().get("result", {})
            if not txd: return False, "Transaction not found"
            if txd.get("to", "").lower() != CRYPTO_ADDRESSES["ETH"].lower():
                return False, "Wrong destination"
            val = int(txd.get("value", "0"), 16) / 1e18
            if abs(val - amount) < 0.001:
                return True, "✓ Verified on Ethereum"
            return False, f"Amount mismatch: {val:.4f} ETH"
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
# DOMAIN CLASSIFICATION
# ═══════════════════════════════════════════════════════════════
def classify_domain(query):
    q = query.lower()
    patterns = {
        "coding": [r'```', r'\bdef\s+\w+\s*\(', r'\bclass\s+\w+', r'\b(write|implement|code|refactor|debug)\b.*\b(function|class|api|algorithm)\b', r'\b(python|numpy|pandas|javascript|sql|rust|go|java)\b'],
        "quant": [r'\b(monte carlo|black.scholes|stochastic|option pricing|var|cvar|sharpe|backtest|alpha|beta|capm)\b'],
        "quantum": [r'\b(quantum|qubit|qiskit|entanglement|superposition|quantum circuit|bell state)\b'],
        "macro": [r'\b(gdp|inflation|recession|fiscal|monetary|central bank|fed|ecb|interest rate|yield curve)\b'],
        "finance": [r'\b(revenue|earnings|ebitda|valuation|pe ratio|dcf|wacc|irr|stock|bond|equity|crypto|bitcoin)\b'],
        "math": [r'\b(prove|proof|theorem|lemma|derive|integral|derivative|linear algebra|eigenvalue)\b'],
        "science": [r'\b(crispr|dna|physics|chemistry|biology|neuroscience|gene|cell|molecule)\b'],
    }
    for domain, pats in patterns.items():
        for p in pats:
            if re.search(p, q): return domain
    return "general"

SYSTEM_PROMPT = """You are CAPITAN AI — institutional intelligence by CLOSEAI Technologies.
Be direct, precise, helpful. Lead with key insight. State confidence. Cite sources. Never give trading signals.
Domain: {domain}"""

# ═══════════════════════════════════════════════════════════════
# REQUEST MODELS
# ═══════════════════════════════════════════════════════════════
class ChatRequest(BaseModel):
    messages: List[dict]
    stream: bool = True
    user_id: str = "anonymous"
    model: str = "balanced"
    client_ip: Optional[str] = None

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
app = FastAPI(title="CAPITAN AI API", version="6.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/")
async def root():
    active_providers = [p for p in PROVIDER_ORDER if MODEL_ROUTING[p]["auth_header"]() not in ("Bearer ", "")]
    active_services = []
    if KEYS["ALPHA_VANTAGE"]: active_services.append("Alpha Vantage")
    if KEYS["TWELVE_DATA"]: active_services.append("Twelve Data")
    if KEYS["GNEWS"]: active_services.append("GNews")
    if KEYS["NEWSAPI"]: active_services.append("NewsAPI")
    if KEYS["SERPAPI"]: active_services.append("SerpAPI")
    if KEYS["WOLFRAM_APP_ID"]: active_services.append("Wolfram Alpha")
    if KEYS["ETHERSCAN"]: active_services.append("Etherscan")
    
    return {
        "name": "CAPITAN AI API",
        "version": "6.0",
        "status": "operational",
        "ai_providers": active_providers,
        "data_services": active_services,
        "endpoints": ["/api/chat", "/api/prices", "/api/news", "/api/search", "/api/verify-payment", "/api/memory", "/api/admin/memory"]
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "providers_active": len([p for p in PROVIDER_ORDER if MODEL_ROUTING[p]["auth_header"]() not in ("Bearer ", "")])}

# ── CHAT ─────────────────────────────────────────────────────
@app.post("/api/chat")
async def chat(req: ChatRequest):
    user = Users.get_or_create(req.user_id, req.client_ip)
    is_pro = user["tier"] in ("pro", "founder")
    
    if not is_pro:
        can_send, remaining = Users.check_limit(req.user_id)
        if not can_send:
            raise HTTPException(status_code=429, detail=f"Limit reached ({Users.FREE_LIMIT}/{Users.FREE_WINDOW_HOURS}h). Upgrade to Pro.")
    
    user_msg = ""
    for msg in reversed(req.messages):
        if msg.get("role") == "user":
            user_msg = msg.get("content", "")
            break
    
    if not user_msg:
        raise HTTPException(status_code=400, detail="No message")
    
    domain = classify_domain(user_msg)
    pro_domains = ["quant", "quantum", "coding", "math", "science"]
    
    if not is_pro and domain in pro_domains:
        raise HTTPException(status_code=403, detail=f"'{domain}' requires Pro. $17/month.")
    
    Memory.add(req.user_id, user_msg, query=user_msg, mem_type="query", tier=user["tier"])
    
    if not is_pro:
        Users.increment(req.user_id)
    
    # Gather all intelligence
    intelligence = gather_intelligence(user_msg, domain, is_pro)
    
    system_content = SYSTEM_PROMPT.format(domain=domain)
    if intelligence:
        system_content += "\n\n=== LIVE INTELLIGENCE ===\n" + intelligence + "\n=== END INTELLIGENCE ==="
    
    llm_messages = [{"role": "system", "content": system_content}]
    for msg in req.messages:
        llm_messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    
    if req.stream:
        response = call_llm(llm_messages, tier=user["tier"], stream=True)
        
        if not response or not hasattr(response, 'iter_lines'):
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
                        if d == "[DONE]": break
                        try:
                            delta = json.loads(d).get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if delta:
                                full += delta
                                yield f"data: {json.dumps({'content': full})}\n\n"
                        except: continue
            if full:
                mid = Memory.add(req.user_id, full, query=user_msg, mem_type="response", tier=user["tier"])
                yield f"data: {json.dumps({'done': True, 'memory_id': mid})}\n\n"
            else:
                yield f"data: {json.dumps({'done': True})}\n\n"
        
        return StreamingResponse(generate(), media_type="text/event-stream")
    else:
        response = call_llm(llm_messages, tier=user["tier"], stream=False)
        mid = Memory.add(req.user_id, response, query=user_msg, mem_type="response", tier=user["tier"])
        return {"content": response, "memory_id": mid, "domain": domain}

# ── MARKET DATA ──────────────────────────────────────────────
@app.get("/api/prices")
async def prices():
    yahoo = MarketDataProviders.get_stock_price_yahoo(["^GSPC", "^IXIC", "AAPL", "MSFT", "NVDA", "TSLA", "GC=F", "CL=F"])
    crypto = MarketDataProviders.get_crypto_prices()
    return {"stocks": yahoo, "crypto": crypto, "timestamp": datetime.now().isoformat()}

@app.get("/api/news")
async def news():
    gnews = NewsProviders.get_gnews()
    newsapi = NewsProviders.get_newsapi()
    yahoo = NewsProviders.get_yahoo_rss()
    return {"gnews": gnews, "newsapi": newsapi, "yahoo": yahoo, "timestamp": datetime.now().isoformat()}

@app.get("/api/search")
async def search(q: str):
    results = web_search(q)
    return {"query": q, "results": results}

@app.get("/api/wolfram")
async def wolfram(q: str):
    results = wolfram_query(q)
    return {"query": q, "results": results}

# ── PAYMENT ──────────────────────────────────────────────────
@app.post("/api/verify-payment")
async def verify_payment(req: PaymentVerifyRequest):
    currency = req.currency.upper()
    if currency not in PRO_PRICE_CRYPTO:
        raise HTTPException(status_code=400, detail="Unsupported currency")
    
    amount = PRO_PRICE_CRYPTO[currency]
    verified, message = verify_crypto_payment(req.txid, currency, amount)
    
    if verified:
        record_payment(req.txid, currency, amount, req.user_id)
        Users.activate_pro(req.user_id)
        return {"verified": True, "message": message, "plan": "pro", "expires_days": Users.PRO_DAYS}
    
    return {"verified": False, "message": message}

# ── MEMORY ───────────────────────────────────────────────────
@app.get("/api/memory")
async def get_memories(user_id: str = "anonymous", limit: int = 50):
    memories = Memory.get_recent(user_id, limit)
    return {"memories": memories, "count": len(memories)}

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

# ── ADMIN ────────────────────────────────────────────────────
@app.post("/api/admin/memory")
async def admin_memory(req: AdminRequest):
    if req.admin_code != KEYS["ADMIN_CODE"]:
        raise HTTPException(status_code=403, detail="Invalid admin code")
    
    memories = Memory.search(req.search) if req.search else Memory.get_recent(limit=100)
    return {"memories": memories, "count": len(memories), "access": "admin"}

# ── WORKSPACES ───────────────────────────────────────────────
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

# ── API KEYS ─────────────────────────────────────────────────
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

# ── USER STATUS ──────────────────────────────────────────────
@app.get("/api/user/{user_id}")
async def get_user(user_id: str):
    user = Users.get_or_create(user_id)
    can_send, remaining = Users.check_limit(user_id)
    return {
        "user_id": user_id,
        "tier": user["tier"],
        "pro_expiry": user["pro_expiry"],
        "can_message": can_send,
        "remaining": remaining if user["tier"] == "free" else "unlimited"
    }

# ── LOCATION ─────────────────────────────────────────────────
@app.get("/api/location")
async def location(request: Request):
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    loc = get_user_location(ip)
    return {"ip": ip, "location": loc}

# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"⚓ CAPITAN AI API v6.0 starting on port {port}")
    print(f"   Active AI providers: {[p for p in PROVIDER_ORDER if MODEL_ROUTING[p]['auth_header']() not in ('Bearer ', '')]}")
    uvicorn.run(app, host="0.0.0.0", port=port)