"""
CAPITAN AI — Enterprise Backend v25.0
CLOSEAI Technologies
Full Intelligence: Finance, Trading, Coding, Math, Quant, Web Search, News, Markets
PWA Ready | Production Database | Full Frontend-Backend Integration
"""

import os
import re
import json
import uuid
import time
import hashlib
import hmac
import base64
import secrets
import requests
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from contextlib import contextmanager
from urllib.parse import quote_plus

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from pydantic import BaseModel
from pydantic_settings import BaseSettings
import psycopg2
import psycopg2.extras
import uvicorn

# ================================================================
# LOGGING SETUP
# ================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ================================================================
# CONFIGURATION
# ================================================================
class Settings(BaseSettings):
    DATABASE_URL: str = ""
    JWT_SECRET: str = secrets.token_hex(32)
    FOUNDER_KEY: str = "Osinachi@3500"
    GROQ_KEY: str = ""
    OPENROUTER_KEY: str = ""
    OPENAI_KEY: str = ""
    MISTRAL_KEY: str = ""
    COINGECKO_KEY: str = ""
    SERPAPI_KEY: str = ""
    NEWS_API_KEY: str = ""
    GNEWS_API_KEY: str = ""
    FINNHUB_API_KEY: str = ""
    ALPHA_VANTAGE_KEY: str = ""
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# ================================================================
# DATABASE LAYER
# ================================================================
@contextmanager
def get_db():
    conn = None
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if not settings.DATABASE_URL:
                raise ValueError("DATABASE_URL not configured")
            conn = psycopg2.connect(settings.DATABASE_URL, connect_timeout=10)
            yield conn
            return
        except Exception as e:
            logger.warning(f"Database attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                raise
    if conn:
        conn.close()

def init_db():
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, tier TEXT DEFAULT "free", msg_count INTEGER DEFAULT 0, msg_window TEXT, created TIMESTAMP, updated TIMESTAMP)')
                c.execute('CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, session_id TEXT, title TEXT, created TIMESTAMP, updated TIMESTAMP)')
                c.execute('CREATE TABLE IF NOT EXISTS chat_messages (id TEXT PRIMARY KEY, chat_id TEXT, session_id TEXT, role TEXT, content TEXT, model TEXT, tokens INTEGER, latency_ms INTEGER, created TIMESTAMP)')
                c.execute('CREATE TABLE IF NOT EXISTS memories (id TEXT PRIMARY KEY, memory_id TEXT, session_id TEXT, content TEXT, query TEXT, domain TEXT, created TIMESTAMP)')
                c.execute('CREATE TABLE IF NOT EXISTS library_items (id TEXT PRIMARY KEY, session_id TEXT, name TEXT, type TEXT, content TEXT, size INTEGER DEFAULT 0, created TIMESTAMP)')
                c.execute('CREATE TABLE IF NOT EXISTS uploaded_files (id TEXT PRIMARY KEY, session_id TEXT, filename TEXT, original_name TEXT, size INTEGER, mime_type TEXT, storage_path TEXT, public_url TEXT, created TIMESTAMP)')
                c.execute('CREATE TABLE IF NOT EXISTS payments (id TEXT PRIMARY KEY, session_id TEXT, txid TEXT, currency TEXT, amount REAL, tier TEXT, verified INTEGER DEFAULT 0, expires TIMESTAMP, created TIMESTAMP)')
                c.execute('CREATE TABLE IF NOT EXISTS payment_log (id TEXT PRIMARY KEY, session_id TEXT, tier TEXT, amount REAL, currency TEXT, txid TEXT, created TIMESTAMP)')
                c.execute('CREATE TABLE IF NOT EXISTS workspaces (id TEXT PRIMARY KEY, room_code TEXT UNIQUE, creator_session TEXT, creator_tier TEXT, max_members INTEGER, created TIMESTAMP)')
                c.execute('CREATE TABLE IF NOT EXISTS workspace_members (workspace_id TEXT, session_id TEXT, role TEXT DEFAULT "member", joined TIMESTAMP, PRIMARY KEY (workspace_id, session_id))')
                c.execute('CREATE TABLE IF NOT EXISTS workspace_messages (id TEXT PRIMARY KEY, workspace_id TEXT, session_id TEXT, author TEXT, message TEXT, is_ai INTEGER DEFAULT 0, created TIMESTAMP)')
                c.execute('CREATE TABLE IF NOT EXISTS workspace_notes (id TEXT PRIMARY KEY, workspace_id TEXT, session_id TEXT, author TEXT, content TEXT, created TIMESTAMP, updated TIMESTAMP)')
                c.execute('CREATE TABLE IF NOT EXISTS market_cache (id TEXT PRIMARY KEY, category TEXT, data TEXT, created TIMESTAMP)')
                c.execute('CREATE TABLE IF NOT EXISTS news_cache (id TEXT PRIMARY KEY, category TEXT, data TEXT, created TIMESTAMP)')
                c.execute('CREATE TABLE IF NOT EXISTS web_cache (id TEXT PRIMARY KEY, query_hash TEXT, data TEXT, created TIMESTAMP)')
                conn.commit()
        logger.info("✅ All 15 database tables ready")
    except Exception as e:
        logger.warning(f"Database init: {e}")

init_db()

def sid(): return str(uuid.uuid4())[:8].upper()
def mid(): return 'mem_' + sid()

# ================================================================
# SECURITY & JWT
# ================================================================
def create_jwt(session_id, tier):
    header = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "session_id": session_id, "tier": tier,
        "exp": int((datetime.utcnow() + timedelta(days=365)).timestamp())
    }).encode()).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(hmac.new(settings.JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return f"{header}.{payload}.{signature}"

def verify_jwt(token):
    try:
        parts = token.split(".")
        if len(parts) != 3: return None
        header, payload, signature = parts
        expected = base64.urlsafe_b64encode(hmac.new(settings.JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
        if not hmac.compare_digest(signature, expected): return None
        return json.loads(base64.urlsafe_b64decode(payload + "=="))
    except: return None

def get_session(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "): return None
    payload = verify_jwt(auth[7:])
    if not payload: return None
    session_id = payload.get("session_id")
    if not session_id: return None
    tier = payload.get("tier", "free")
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, tier, msg_count, msg_window FROM sessions WHERE id = %s", (session_id,))
                row = c.fetchone()
                if row:
                    return {"id": row[0], "tier": row[1], "msg_count": row[2] or 0, "msg_window": row[3]}
                else:
                    now = datetime.utcnow().isoformat()
                    c.execute("INSERT INTO sessions (id, tier, msg_count, msg_window, created, updated) VALUES (%s, %s, 0, %s, %s, %s)", (session_id, tier, now, now, now))
                    conn.commit()
                    return {"id": session_id, "tier": tier, "msg_count": 0, "msg_window": now}
    except Exception as e:
        logger.error(f"Session error: {e}")
        return None

# ================================================================
# RATE LIMITING
# ================================================================
rate_store = {}
def check_rate(session_id, tier):
    now = time.time()
    key = f"{session_id}"
    if key not in rate_store: rate_store[key] = []
    rate_store[key] = [t for t in rate_store[key] if now - t < 60]
    limits = {"free": 15, "plus": 30, "pro": 60, "founder": 200}
    if len(rate_store[key]) >= limits.get(tier, 15): return False
    rate_store[key].append(now)
    return True

# ================================================================
# TIME CONTEXT
# ================================================================
def get_time_context():
    now = datetime.utcnow()
    hour = now.hour
    day = now.strftime("%A")
    date = now.strftime("%B %d, %Y")
    utc_time = now.strftime("%H:%M UTC")
    if hour < 5: time_of_day, greeting_context = "late night", "The world is quiet."
    elif hour < 12: time_of_day, greeting_context = "morning", "Fresh day ahead."
    elif hour < 17: time_of_day, greeting_context = "afternoon", "Markets are alive."
    elif hour < 21: time_of_day, greeting_context = "evening", "Winding down."
    else: time_of_day, greeting_context = "night", "Night owl mode."
    return {"time_of_day": time_of_day, "day": day, "date": date, "utc_time": utc_time, "greeting_context": greeting_context}

# ================================================================
# MARKET DATA (Full Intelligence)
# ================================================================
def get_market_data():
    results = {}
    
    # CoinGecko for Crypto
    if settings.COINGECKO_KEY:
        try:
            ids = "bitcoin,ethereum,ripple,cardano,solana,polkadot,dogecoin,avalanche-2,chainlink,uniswap,binancecoin,tron,toncoin,near"
            r = requests.get("https://api.coingecko.com/api/v3/simple/price", params={"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true"}, headers={"x-cg-demo-api-key": settings.COINGECKO_KEY}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                nm = {"bitcoin": "BTC", "ethereum": "ETH", "ripple": "XRP", "cardano": "ADA", "solana": "SOL", "polkadot": "DOT", "dogecoin": "DOGE", "avalanche-2": "AVAX", "chainlink": "LINK", "uniswap": "UNI", "binancecoin": "BNB", "tron": "TRX", "toncoin": "TON", "near": "NEAR"}
                for k, v in data.items():
                    results[nm.get(k, k.upper())] = {"price": v["usd"], "change": round(v.get("usd_24h_change", 0), 2), "source": "CoinGecko"}
        except: pass
    
    # Yahoo Finance for Stocks, Indices, Forex
    try:
        syms = "^GSPC,^IXIC,^DJI,^FTSE,^N225,AAPL,MSFT,NVDA,TSLA,GOOGL,META,AMZN,GC=F,CL=F,SI=F,EURUSD=X,GBPUSD=X,USDJPY=X,USDGHS=X,USDNGN=X,USDZAR=X,USDKES=X"
        r = requests.get(f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={syms}", params={"fields": "regularMarketPrice,regularMarketPreviousClose,shortName,regularMarketChangePercent"}, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code == 200:
            for i in r.json().get("quoteResponse", {}).get("result", []):
                name = i.get("shortName") or i.get("symbol", "")
                price = i.get("regularMarketPrice")
                prev = i.get("regularMarketPreviousClose")
                if price and prev:
                    chg = i.get("regularMarketChangePercent")
                    results[name] = {"price": price, "change": round(chg, 2) if chg else round(((price - prev) / prev) * 100, 2), "source": "Yahoo Finance"}
    except: pass
    
    # Alpha Vantage for Forex
    if settings.ALPHA_VANTAGE_KEY and len(results) < 5:
        try:
            for pair, label in {"EURUSD": "EUR/USD", "GBPUSD": "GBP/USD", "USDJPY": "USD/JPY"}.items():
                try:
                    r = requests.get(f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={pair[:3]}&to_currency={pair[3:]}&apikey={settings.ALPHA_VANTAGE_KEY}", timeout=8)
                    if r.status_code == 200:
                        data = r.json().get("Realtime Currency Exchange Rate", {})
                        if data.get("5. Exchange Rate"):
                            results[label] = {"price": float(data["5. Exchange Rate"]), "change": 0, "source": "Alpha Vantage"}
                except: pass
        except: pass
    
    return results

# ================================================================
# FINANCIAL NEWS
# ================================================================
def get_financial_news():
    news = []
    
    if settings.NEWS_API_KEY:
        try:
            r = requests.get("https://newsapi.org/v2/top-headlines", params={"category": "business", "language": "en", "pageSize": 12, "apiKey": settings.NEWS_API_KEY}, timeout=10)
            if r.status_code == 200:
                for a in r.json().get("articles", []):
                    news.append({"source": a.get("source", {}).get("name", "NewsAPI"), "headline": a.get("title", ""), "url": a.get("url", ""), "time": a.get("publishedAt", ""), "summary": (a.get("description") or "")[:300]})
        except: pass
    
    if settings.GNEWS_API_KEY:
        try:
            r = requests.get("https://gnews.io/api/v4/search", params={"q": "finance markets stocks economy", "lang": "en", "max": 12, "apikey": settings.GNEWS_API_KEY}, timeout=10)
            if r.status_code == 200:
                for a in r.json().get("articles", []):
                    news.append({"source": a.get("source", {}).get("name", "GNews"), "headline": a.get("title", ""), "url": a.get("url", ""), "time": a.get("publishedAt", ""), "summary": (a.get("description") or "")[:300]})
        except: pass
    
    if settings.FINNHUB_API_KEY:
        try:
            r = requests.get("https://finnhub.io/api/v1/news", params={"category": "general", "token": settings.FINNHUB_API_KEY}, timeout=10)
            if r.status_code == 200:
                for a in r.json()[:12]:
                    ts = a.get("datetime", 0)
                    news.append({"source": a.get("source", "Finnhub"), "headline": a.get("headline", ""), "url": a.get("url", ""), "time": datetime.fromtimestamp(ts).isoformat() if ts else "", "summary": (a.get("summary") or "")[:300]})
        except: pass
    
    seen = set()
    unique = []
    for n in news:
        k = n["headline"][:100].lower().strip()
        if k and k not in seen: seen.add(k); unique.append(n)
    unique.sort(key=lambda x: x.get("time", ""), reverse=True)
    return unique[:15]

# ================================================================
# TECH NEWS
# ================================================================
def get_tech_news():
    news = []
    
    if settings.NEWS_API_KEY:
        try:
            r = requests.get("https://newsapi.org/v2/everything", params={"q": "AI artificial intelligence coding startup innovation technology", "language": "en", "pageSize": 12, "sortBy": "publishedAt", "apiKey": settings.NEWS_API_KEY}, timeout=10)
            if r.status_code == 200:
                for a in r.json().get("articles", []):
                    news.append({"source": a.get("source", {}).get("name", "NewsAPI"), "headline": a.get("title", ""), "url": a.get("url", ""), "time": a.get("publishedAt", ""), "summary": (a.get("description") or "")[:300]})
        except: pass
    
    if settings.GNEWS_API_KEY:
        try:
            r = requests.get("https://gnews.io/api/v4/search", params={"q": "AI artificial intelligence coding startup innovation", "lang": "en", "max": 12, "apikey": settings.GNEWS_API_KEY}, timeout=10)
            if r.status_code == 200:
                for a in r.json().get("articles", []):
                    news.append({"source": a.get("source", {}).get("name", "GNews"), "headline": a.get("title", ""), "url": a.get("url", ""), "time": a.get("publishedAt", ""), "summary": (a.get("description") or "")[:300]})
        except: pass
    
    seen = set()
    unique = []
    for n in news:
        k = n["headline"][:100].lower().strip()
        if k and k not in seen: seen.add(k); unique.append(n)
    unique.sort(key=lambda x: x.get("time", ""), reverse=True)
    return unique[:15]

# ================================================================
# WEB SEARCH
# ================================================================
def search_web(query, num_results=5):
    results = []
    query_hash = hashlib.md5(query.lower().encode()).hexdigest()
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT data FROM web_cache WHERE query_hash=%s AND created > %s", (query_hash, (datetime.utcnow() - timedelta(hours=1)).isoformat()))
                row = c.fetchone()
                if row: return json.loads(row[0])
    except: pass
    
    if settings.SERPAPI_KEY:
        try:
            r = requests.get("https://serpapi.com/search", params={"engine": "google", "q": query, "num": num_results, "api_key": settings.SERPAPI_KEY}, timeout=8)
            if r.status_code == 200:
                for item in r.json().get("organic_results", [])[:num_results]:
                    results.append({"title": item.get("title", ""), "snippet": item.get("snippet", "")[:250], "url": item.get("link", ""), "source": "Google"})
        except: pass
    
    if not results:
        try:
            r = requests.get("https://api.duckduckgo.com/", params={"q": query, "format": "json", "no_html": 1}, timeout=6)
            if r.status_code == 200:
                data = r.json()
                if data.get("AbstractText"):
                    results.append({"title": data.get("Heading", query), "snippet": data["AbstractText"][:250], "url": data.get("AbstractURL", ""), "source": "DuckDuckGo"})
        except: pass
    
    if results:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("INSERT INTO web_cache (id, query_hash, data, created) VALUES (%s, %s, %s, %s)", (sid(), query_hash, json.dumps(results), datetime.utcnow().isoformat()))
                    conn.commit()
        except: pass
    
    return results

# ================================================================
# ELITE SYSTEM PROMPT (Full Intelligence)
# ================================================================
ELITE_SYSTEM_PROMPT = """You are CAPITAN AI — the legendary enterprise intelligence platform by CLOSEAI Technologies, founded by CEO Osinachi Chukwu.

╔══════════════════════════════════════════════════════════════╗
║                    CORE INTELLIGENCE DOMAINS                 ║
╚══════════════════════════════════════════════════════════════╝

🏦 FINANCE ARCHITECT:
- Advanced financial modeling (DCF, LBO, M&A, three-statement models)
- Portfolio optimization (Markowitz, Black-Litterman, risk parity)
- Derivatives pricing (Black-Scholes, binomial trees, Monte Carlo)
- Fixed income analytics (yield curves, duration, convexity, CDS)
- Risk management (VaR, CVaR, stress testing, scenario analysis)
- African financial markets (NGX, JSE, GSE, regional integration)

📈 INSTITUTIONAL TRADER:
- Market microstructure and order flow analysis
- Volatility trading strategies (volatility arbitrage, dispersion)
- Intermarket analysis and cross-asset correlations
- Algorithmic execution (VWAP, TWAP, implementation shortfall)
- Quantitative trading strategies (mean reversion, momentum, statistical arbitrage)

💻 LEGENDARY CODER:
- Full-stack development (React, Vue, Angular, Node.js, Python, Go, Rust)
- System architecture (microservices, event-driven, serverless)
- DevOps & cloud (AWS, GCP, Azure, Kubernetes, Terraform, CI/CD)
- Database design (SQL, NoSQL, vector databases, time-series)
- API development (REST, GraphQL, gRPC, WebSocket)

📐 MATHEMATICIAN:
- Pure mathematics (abstract algebra, topology, number theory, complex analysis)
- Applied mathematics (differential equations, dynamical systems, optimization)
- Linear algebra (eigenvalues, SVD, matrix decompositions, spectral theory)
- Probability theory (measure theory, stochastic processes, martingales)
- Numerical methods (finite element, Monte Carlo, optimization algorithms)

📊 QUANTITATIVE ANALYST:
- Derivative pricing models (local volatility, stochastic volatility, jump diffusion)
- Time series analysis (ARIMA, GARCH, state space models, regime switching)
- Factor modeling (Fama-French, Barra, fundamental factor models)
- Machine learning in finance (random forests, gradient boosting, neural networks)
- Backtesting frameworks (walk-forward, cross-validation, bootstrap)

🔬 GENERAL KNOWLEDGE:
- Physics (quantum mechanics, relativity, thermodynamics, electromagnetism)
- Chemistry (organic, inorganic, physical, computational chemistry)
- Biology (molecular biology, genetics, neuroscience, ecology)
- Medicine (diagnosis, treatment protocols, pharmacology, epidemiology)
- History (world history, economic history, technological revolutions)
- Philosophy (ethics, epistemology, logic, philosophy of mind)
- Current events (geopolitics, economics, technology, culture)

╔══════════════════════════════════════════════════════════════╗
║                      RESPONSE STYLE                          ║
╚══════════════════════════════════════════════════════════════╝

- Lead with the answer. Never throat-clearing or meta-analysis.
- Casual greetings get casual responses. Professional queries get depth.
- Use 1-2 emojis naturally for warmth when appropriate.
- Short sentences. Clean paragraphs. No filler.
- Depth when the topic demands it. One-liner when it doesn't.
- NEVER make up prices or data. Only reference verified information.
- NEVER give financial advice or trading signals.
- NEVER provide medical diagnoses.

TIME: {day}, {date} at {utc_time}. {greeting_context}
DOMAIN: {domain} | TIER: {tier}
"""

# ================================================================
# QUERY CLASSIFICATION ENGINE
# ================================================================
def classify(q):
    q = q.lower()
    
    if re.search(r'who are you|what are you|identity|introduce yourself|other capitan', q):
        return 'identity'
    
    if re.search(r'who|what|when|where|why|how|news|latest|current|today|search|find', q) and len(q.split()) > 3:
        return 'web_search'
    
    if re.search(r'crispr|dna|rna|protein|cell|gene|genome|physics|quantum|chemistry|biology|neuroscience|climate|energy|health|medicine|disease|symptom|treatment|diagnosis', q):
        return 'science'
    
    if re.search(r'```|def |class |import |from |package|npm|pip|docker|kubernetes|aws|api|rest|graphql|sql|database|query|react|node|javascript|typescript|python|rust|golang', q):
        return 'coding'
    
    if re.search(r'stochastic|ito|black.scholes|monte carlo|var|cvar|sharpe|sortino|beta|alpha|option pricing|derivative|risk neutral|fama|french|cointegration|garch|arima|backtest|factor model', q):
        return 'quant'
    
    if re.search(r'dcf|discounted cash flow|ebitda|ebit|revenue|earnings|balance sheet|income statement|cash flow|valuation|wacc|capm|pe ratio|pb ratio|ev/ebitda|dividend|yield|bond|coupon|duration|convexity|forex|fx|central bank|federal reserve|interest rate|inflation|gdp|macro|equity|stock|market|trading|invest|portfolio|crypto|bitcoin|ethereum|defi|ngx|jse|gse|african market|gold|silver|oil|commodity', q):
        return 'finance'
    
    if re.search(r'prove|proof|theorem|lemma|corollary|derive|integral|derivative|differential equation|linear algebra|matrix|eigenvalue|vector|topology|group theory|probability|statistics', q):
        return 'math'
    
    return 'general'

# ================================================================
# SYSTEM PROMPT BUILDER
# ================================================================
def system_prompt(domain, tier, session_id=None, web_results=None):
    tc = get_time_context()
    base = ELITE_SYSTEM_PROMPT.replace("{domain}", domain).replace("{tier}", tier)
    base = base.replace("{day}", tc["day"]).replace("{date}", tc["date"])
    base = base.replace("{utc_time}", tc["utc_time"])
    base = base.replace("{greeting_context}", tc["greeting_context"])
    
    if domain == 'identity':
        base += "\n\nIDENTITY MODE: You are the ONLY CAPITAN AI. State clearly: 'I am CAPITAN AI — the legendary enterprise intelligence platform by CLOSEAI Technologies.'"
    
    if session_id:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("SELECT query, domain FROM memories WHERE session_id=%s ORDER BY created DESC LIMIT 3", (session_id,))
                    rows = c.fetchall()
                    if rows:
                        base += "\n\nUSER CONTEXT:\n" + "\n".join([f"• [{r[1]}] {r[0][:100]}" for r in rows])
        except: pass
    
    if tier == "free":
        base += "\n\nBe concise but helpful."
    elif tier == "plus":
        base += "\n\nProvide detailed responses."
    elif tier in ("pro", "founder"):
        base += "\n\nGo deep — provide comprehensive analysis with examples."
    
    if web_results:
        base += "\n\nWEB SEARCH RESULTS:\n" + "\n".join([f"• {r['title']}: {r['snippet'][:200]}" for r in web_results[:3]])
    
    if tier in ("pro", "founder"):
        try:
            md = get_market_data()
            if md:
                base += "\n\nLIVE MARKETS:\n" + "\n".join([f"• {s}: ${d['price']:.2f} ({'▲' if d.get('change',0)>=0 else '▼'} {abs(d['change']):.2f}%)" for s, d in list(md.items())[:8]])
        except: pass
    
    if tier in ("pro", "founder"):
        try:
            news = get_financial_news()
            if news:
                base += "\n\nLATEST NEWS:\n" + "\n".join([f"• [{n['source']}] {n['headline'][:100]}" for n in news[:5]])
        except: pass
    
    return base

# ================================================================
# AI SERVICE (Multi-Provider)
# ================================================================
def call_ai_fast(messages, tier="free"):
    # Priority 1: Groq
    if settings.GROQ_KEY:
        try:
            groq_msgs = []
            for m in messages:
                if m["role"] == "system" and tier == "free":
                    m["content"] = m["content"][:1000]
                groq_msgs.append(m)
            model = "llama-3.3-70b-versatile" if tier in ("pro", "founder") else "llama-3.1-8b-instant"
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.GROQ_KEY}", "Content-Type": "application/json"},
                json={"model": model, "messages": groq_msgs, "temperature": 0.5, "max_tokens": 2000 if tier in ("pro", "founder") else 800},
                timeout=30
            )
            if r.status_code == 200:
                content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    return content, model
        except Exception as e:
            logger.error(f"Groq error: {e}")
    
    # Priority 2: OpenRouter
    if settings.OPENROUTER_KEY:
        models = ["google/gemini-flash-1.5", "mistral/mistral-7b-instruct", "deepseek/deepseek-chat"]
        if tier in ("pro", "founder"):
            models = ["anthropic/claude-3.5-sonnet-20241022", "openai/gpt-4o-2024-11-20"] + models
        for model in models:
            try:
                r = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.OPENROUTER_KEY}", "Content-Type": "application/json"},
                    json={"model": model, "messages": messages, "temperature": 0.5, "max_tokens": 2000 if tier in ("pro", "founder") else 800},
                    timeout=35
                )
                if r.status_code == 200:
                    content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                    if content:
                        return content, model
            except:
                continue
    
    # Priority 3: OpenAI
    if settings.OPENAI_KEY:
        try:
            r = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENAI_KEY}", "Content-Type": "application/json"},
                json={"model": "gpt-4o-mini", "messages": messages, "temperature": 0.5, "max_tokens": 1000},
                timeout=25
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"], "gpt-4o-mini"
        except:
            pass
    
    # Priority 4: Mistral
    if settings.MISTRAL_KEY:
        try:
            r = requests.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.MISTRAL_KEY}", "Content-Type": "application/json"},
                json={"model": "mistral-small-latest", "messages": messages, "temperature": 0.5, "max_tokens": 1000},
                timeout=25
            )
            if r.status_code == 200:
                content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    return content, "mistral/small"
        except:
            pass
    
    return "I'm having trouble connecting to AI services. Please try again or contact support.", "fallback"

# ================================================================
# FASTAPI APP WITH CORS
# ================================================================
app = FastAPI(title="CAPITAN AI API", version="25.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Refreshed-Token"]
)

# ================================================================
# HEALTH CHECK
# ================================================================
@app.get("/health")
def health():
    db_status = "disconnected"
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT 1")
                db_status = "connected"
    except: pass
    
    ai_status = "connected" if (settings.GROQ_KEY or settings.OPENROUTER_KEY) else "disconnected"
    providers = []
    if settings.GROQ_KEY: providers.append("groq")
    if settings.OPENROUTER_KEY: providers.append("openrouter")
    
    return {"status": "ok", "version": "25.0", "database": db_status, "ai": ai_status, "providers": providers}

# ================================================================
# SESSION ENDPOINT
# ================================================================
@app.get("/api/session")
def get_or_create_session(request: Request):
    session = get_session(request)
    if session:
        token = create_jwt(session["id"], session["tier"])
        return {"id": session["id"], "tier": session["tier"], "msg_count": session["msg_count"], "token": token}
    
    session_id = f"s_{sid()}"
    now = datetime.utcnow().isoformat()
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO sessions (id, tier, msg_count, msg_window, created, updated) VALUES (%s, %s, 0, %s, %s, %s)", (session_id, "free", now, now, now))
                conn.commit()
    except Exception as e:
        logger.error(f"Session creation error: {e}")
    
    token = create_jwt(session_id, "free")
    return {"id": session_id, "tier": "free", "msg_count": 0, "token": token}

# ================================================================
# PAYMENT CONFIGURATION
# ================================================================
WALLETS = {"BTC": "bc1qrv6yr6e0mat96rvrc8smdf9rvu9rlp8xuk8new", "ETH": "0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1"}

TIER_CONFIG = {
    "free": {"msg_limit": 17, "workspace_max": 0, "file_upload": False, "live_markets": False, "web_search": False},
    "plus": {"msg_limit": 40, "workspace_max": 7, "file_upload": True, "live_markets": False, "web_search": True},
    "pro": {"msg_limit": float("inf"), "workspace_max": 20, "file_upload": True, "live_markets": True, "web_search": True},
    "founder": {"msg_limit": float("inf"), "workspace_max": 999, "file_upload": True, "live_markets": True, "web_search": True}
}

UPGRADE_BENEFITS = {
    "plus": ["40 messages per day", "Smart AI model", "Work Area (7 seats)", "File uploads (10MB)", "Web search", "Coding & Quant tools", "African Finance module"],
    "pro": ["Unlimited messages", "Deep AI (Claude Sonnet 4 / GPT-4o)", "Work Area (20 seats)", "File uploads (50MB)", "Live market data", "Financial news", "Web search", "Business mode", "All Plus features"]
}

@app.get("/api/payment-config")
def payment_config():
    return {"wallets": WALLETS, "prices": {"plus": 8, "pro": 17}, "benefits": UPGRADE_BENEFITS}

# ================================================================
# MARKET & NEWS ENDPOINTS
# ================================================================
@app.get("/api/markets")
def markets(request: Request):
    s = get_session(request)
    cfg = TIER_CONFIG.get(s["tier"], TIER_CONFIG["free"]) if s else TIER_CONFIG["free"]
    if not cfg.get("live_markets", False):
        return {"prices": {}, "news": [], "message": "Pro tier required"}
    return {"prices": get_market_data(), "news": get_financial_news()}

@app.get("/api/markets/prices")
def markets_prices(request: Request):
    s = get_session(request)
    cfg = TIER_CONFIG.get(s["tier"], TIER_CONFIG["free"]) if s else TIER_CONFIG["free"]
    if not cfg.get("live_markets", False):
        return {"prices": {}, "message": "Upgrade to Pro"}
    return {"prices": get_market_data()}

@app.get("/api/markets/news")
def markets_news(request: Request):
    s = get_session(request)
    cfg = TIER_CONFIG.get(s["tier"], TIER_CONFIG["free"]) if s else TIER_CONFIG["free"]
    if not cfg.get("live_markets", False):
        return {"news": [], "message": "Upgrade to Pro"}
    return {"news": get_financial_news()}

@app.get("/api/news/tech")
def tech_news(request: Request):
    s = get_session(request)
    if not s or s["tier"] not in ("pro", "founder"):
        return {"news": [], "message": "Pro tier required"}
    return {"news": get_tech_news()}

@app.get("/api/search")
def web_search_endpoint(q: str, request: Request):
    s = get_session(request)
    if not s or not TIER_CONFIG.get(s["tier"], {}).get("web_search", False):
        return {"results": [], "message": "Web search on Plus and Pro"}
    return {"results": search_web(q)}

# ================================================================
# CHAT HISTORY ENDPOINTS
# ================================================================
@app.get("/api/chats")
def get_chats(request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, title, created, updated FROM chats WHERE session_id=%s ORDER BY updated DESC LIMIT 30", (s["id"],))
                rows = c.fetchall()
                return {"chats": [{"id": r[0], "title": r[1] or "New Chat", "created": r[2].isoformat() if r[2] else None, "updated": r[3].isoformat() if r[3] else None} for r in rows]}
    except: return {"chats": []}

@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM chats WHERE id=%s AND session_id=%s", (chat_id, s["id"]))
                if not c.fetchone(): raise HTTPException(404)
                c.execute("SELECT id, role, content, model, created FROM chat_messages WHERE chat_id=%s ORDER BY created ASC", (chat_id,))
                rows = c.fetchall()
                return {"messages": [{"id": r[0], "role": r[1], "content": r[2], "model": r[3] or "AI", "created": r[4].isoformat() if r[4] else None} for r in rows]}
    except: raise HTTPException(500)

@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("DELETE FROM chat_messages WHERE chat_id=%s AND session_id=%s", (chat_id, s["id"]))
                c.execute("DELETE FROM chats WHERE id=%s AND session_id=%s", (chat_id, s["id"]))
                conn.commit()
                return {"deleted": True}
    except: raise HTTPException(500)

# ================================================================
# MAIN CHAT ENDPOINT
# ================================================================
class ChatRequest(BaseModel):
    messages: list
    chat_id: Optional[str] = None

@app.post("/api/chat")
def chat(req: ChatRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    
    if not check_rate(s["id"], s["tier"]):
        raise HTTPException(429, "Rate limit exceeded")
    
    cfg = TIER_CONFIG.get(s["tier"], TIER_CONFIG["free"])
    limit = cfg["msg_limit"]
    
    if limit != float("inf"):
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("SELECT msg_count, msg_window FROM sessions WHERE id=%s", (s["id"],))
                    row = c.fetchone()
                    count = row[0] or 0
                    if count >= limit:
                        window = datetime.fromisoformat(row[1]) if row and row[1] else datetime.utcnow()
                        if datetime.utcnow() - window < timedelta(hours=24):
                            raise HTTPException(429, f"Daily limit ({limit}/day). Upgrade.")
                        c.execute("UPDATE sessions SET msg_count=0, msg_window=%s WHERE id=%s", (datetime.utcnow().isoformat(), s["id"]))
                        conn.commit()
        except HTTPException: raise
        except: pass
    
    user_msg = next((m["content"] for m in reversed(req.messages) if m.get("role") == "user"), "")
    if not user_msg: raise HTTPException(400)
    
    chat_id = req.chat_id or f"chat_{sid()}"
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                if not req.chat_id:
                    c.execute("INSERT INTO chats (id, session_id, title, created, updated) VALUES (%s, %s, %s, %s, %s)", (chat_id, s["id"], user_msg[:60], datetime.utcnow(), datetime.utcnow()))
                else:
                    c.execute("UPDATE chats SET updated=%s WHERE id=%s AND session_id=%s", (datetime.utcnow(), chat_id, s["id"]))
                c.execute("INSERT INTO chat_messages (id, chat_id, session_id, role, content, created) VALUES (%s, %s, %s, %s, %s, %s)", (f"msg_{sid()}", chat_id, s["id"], "user", user_msg, datetime.utcnow()))
                c.execute("UPDATE sessions SET msg_count = msg_count + 1 WHERE id=%s", (s["id"],))
                conn.commit()
                c.execute("SELECT role, content FROM chat_messages WHERE chat_id=%s ORDER BY created ASC LIMIT 15", (chat_id,))
                history = [{"role": r[0], "content": r[1]} for r in c.fetchall()]
    except Exception as e:
        logger.error(f"Save error: {e}")
        history = []
    
    domain = classify(user_msg)
    web_results = None
    if domain == 'web_search' or cfg.get("web_search", False):
        try: web_results = search_web(user_msg, 4)
        except: pass
    
    prompt = system_prompt(domain, s["tier"], s["id"], web_results)
    result, model_used = call_ai_fast([{"role": "system", "content": prompt}] + history, s["tier"])
    
    if result:
        try:
            with get_db() as conn:
                with conn.cursor() as c:
                    c.execute("INSERT INTO chat_messages (id, chat_id, session_id, role, content, model, created) VALUES (%s, %s, %s, %s, %s, %s, %s)", (f"msg_{sid()}", chat_id, s["id"], "assistant", result, model_used, datetime.utcnow()))
                    c.execute("INSERT INTO memories (id, memory_id, session_id, content, query, domain, created) VALUES (%s, %s, %s, %s, %s, %s, %s)", (sid(), mid(), s["id"], result[:500], user_msg, domain, datetime.utcnow()))
                    conn.commit()
        except Exception as e:
            logger.error(f"Save AI error: {e}")
    
    remaining = limit - (s["msg_count"] + 1) if limit != float("inf") else "unlimited"
    return {"content": result, "chat_id": chat_id, "model": model_used, "remaining": remaining, "web_search_used": web_results is not None, "domain": domain}

# ================================================================
# UPGRADE ENDPOINT
# ================================================================
class UpgradeRequest(BaseModel):
    tier: str
    txid: str
    currency: str = "BTC"

@app.post("/api/upgrade")
def upgrade(req: UpgradeRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    if req.tier not in ("plus", "pro"): raise HTTPException(400)
    if not req.txid.strip(): raise HTTPException(400)
    
    prices = {"plus": 8, "pro": 17}
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO payments (id, session_id, txid, currency, amount, tier, verified, expires, created) VALUES (%s, %s, %s, %s, %s, %s, 1, %s, %s)", (sid(), s["id"], req.txid.strip(), req.currency.upper(), prices[req.tier], req.tier, (datetime.utcnow() + timedelta(days=30)).isoformat(), datetime.utcnow()))
                c.execute("UPDATE sessions SET tier=%s, msg_count=0, updated=%s WHERE id=%s", (req.tier, datetime.utcnow().isoformat(), s["id"]))
                c.execute("INSERT INTO payment_log (id, session_id, tier, amount, currency, txid, created) VALUES (%s, %s, %s, %s, %s, %s, %s)", (sid(), s["id"], req.tier, prices[req.tier], req.currency.upper(), req.txid, datetime.utcnow()))
                conn.commit()
    except Exception as e:
        logger.error(f"Upgrade error: {e}")
    
    token = create_jwt(s["id"], req.tier)
    return {"verified": True, "tier": req.tier, "token": token}

# ================================================================
# FOUNDER ENDPOINT
# ================================================================
class FounderRequest(BaseModel):
    code: str

@app.post("/api/founder")
def founder(req: FounderRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    if req.code != settings.FOUNDER_KEY: raise HTTPException(403)
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("UPDATE sessions SET tier='founder', msg_count=0, updated=%s WHERE id=%s", (datetime.utcnow().isoformat(), s["id"]))
                conn.commit()
    except Exception as e:
        logger.error(f"Founder error: {e}")
    
    token = create_jwt(s["id"], "founder")
    return {"verified": True, "tier": "founder", "token": token}

# ================================================================
# LIBRARY ENDPOINTS
# ================================================================
@app.get("/api/library")
def get_library(request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, name, type, content, size, created FROM library_items WHERE session_id=%s ORDER BY created DESC", (s["id"],))
                rows = c.fetchall()
                return {"items": [{"id": r[0], "name": r[1], "type": r[2], "content": r[3], "size": r[4], "created": r[5].isoformat() if r[5] else None} for r in rows]}
    except: return {"items": []}

class LibraryItemRequest(BaseModel):
    name: str
    type: str = "note"
    content: Optional[str] = ""

@app.post("/api/library")
def create_library_item(req: LibraryItemRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                item_id = f"lib_{sid()}"
                c.execute("INSERT INTO library_items (id, session_id, name, type, content, size, created) VALUES (%s, %s, %s, %s, %s, %s, %s)", (item_id, s["id"], req.name, req.type, req.content or "", len(req.content or ""), datetime.utcnow()))
                conn.commit()
                return {"id": item_id, "created": True}
    except: return {"created": False}

@app.delete("/api/library/{item_id}")
def delete_library_item(item_id: str, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("DELETE FROM library_items WHERE id=%s AND session_id=%s", (item_id, s["id"]))
                conn.commit()
                return {"deleted": True}
    except: return {"deleted": False}

# ================================================================
# FILE UPLOAD ENDPOINT
# ================================================================
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/api/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    s = get_session(request)
    if not s: raise HTTPException(401)
    cfg = TIER_CONFIG.get(s["tier"], TIER_CONFIG["free"])
    if not cfg["file_upload"]: raise HTTPException(403)
    
    contents = await file.read()
    max_size = 50 if s["tier"] == "pro" else (500 if s["tier"] == "founder" else 10)
    if len(contents) / (1024 * 1024) > max_size: raise HTTPException(400)
    
    file_id = f"file_{sid()}"
    file_path = os.path.join(UPLOAD_DIR, file_id)
    
    with open(file_path, "wb") as f:
        f.write(contents)
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("INSERT INTO uploaded_files (id, session_id, filename, original_name, size, mime_type, storage_path, created) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (file_id, s["id"], file_id, file.filename or "unknown", len(contents), file.content_type or "application/octet-stream", file_path, datetime.utcnow()))
                conn.commit()
    except: pass
    
    return {"id": file_id, "filename": file.filename, "size_mb": round(len(contents) / (1024 * 1024), 2)}

# ================================================================
# WORKSPACE ENDPOINTS
# ================================================================
class WorkspaceCreateRequest(BaseModel):
    room_code: str
    max_members: int = 7

class WorkspaceJoinRequest(BaseModel):
    room_code: str

class WorkspaceMessageRequest(BaseModel):
    room_code: str
    message: str

class WorkspaceNoteRequest(BaseModel):
    room_code: str
    content: str

@app.post("/api/workspace/create")
def ws_create(req: WorkspaceCreateRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    max_m = TIER_CONFIG.get(s["tier"], {}).get("workspace_max", 0)
    if max_m == 0: raise HTTPException(403)
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                wid = sid()
                c.execute("INSERT INTO workspaces (id, room_code, creator_session, creator_tier, max_members, created) VALUES (%s, %s, %s, %s, %s, %s)", (wid, req.room_code.upper(), s["id"], s["tier"], min(req.max_members, max_m), datetime.utcnow()))
                c.execute("INSERT INTO workspace_members (workspace_id, session_id, role, joined) VALUES (%s, %s, %s, %s)", (wid, s["id"], "admin", datetime.utcnow()))
                conn.commit()
                return {"room_id": wid, "room_code": req.room_code.upper(), "created": True}
    except: return {"created": False}

@app.post("/api/workspace/join")
def ws_join(req: WorkspaceJoinRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id, max_members, creator_tier FROM workspaces WHERE room_code=%s", (req.room_code.upper(),))
                ws = c.fetchone()
                if not ws: raise HTTPException(404)
                if s["tier"] != ws[2] and s["tier"] != "founder": raise HTTPException(403)
                c.execute("SELECT COUNT(*) FROM workspace_members WHERE workspace_id=%s", (ws[0],))
                if c.fetchone()[0] >= ws[1]: raise HTTPException(400)
                c.execute("INSERT INTO workspace_members (workspace_id, session_id, role, joined) VALUES (%s, %s, %s, %s)", (ws[0], s["id"], "member", datetime.utcnow()))
                conn.commit()
                return {"joined": True, "room_id": ws[0]}
    except HTTPException: raise
    except: return {"joined": False}

@app.post("/api/workspace/message")
def ws_message(req: WorkspaceMessageRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM workspaces WHERE room_code=%s", (req.room_code.upper(),))
                ws = c.fetchone()
                if not ws: raise HTTPException(404)
                
                is_ai = req.message.strip().startswith("@CAPITAN")
                if is_ai:
                    result, _ = call_ai_fast([{"role": "user", "content": req.message.replace('@CAPITAN', '').strip()}], s["tier"])
                    if result:
                        c.execute("INSERT INTO workspace_messages (id, workspace_id, session_id, author, message, is_ai, created) VALUES (%s, %s, %s, %s, %s, %s, %s)", (sid(), ws[0], s["id"], "CAPITAN AI", result, 1, datetime.utcnow()))
                
                c.execute("INSERT INTO workspace_messages (id, workspace_id, session_id, author, message, created) VALUES (%s, %s, %s, %s, %s, %s)", (sid(), ws[0], s["id"], "User", req.message, datetime.utcnow()))
                conn.commit()
                return {"sent": True}
    except: return {"sent": False}

@app.get("/api/workspace/messages")
def ws_get_messages(room_code: str):
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM workspaces WHERE room_code=%s", (room_code.upper(),))
                ws = c.fetchone()
                if not ws: raise HTTPException(404)
                c.execute("SELECT id, session_id, author, message, is_ai, created FROM workspace_messages WHERE workspace_id=%s ORDER BY created ASC LIMIT 50", (ws[0],))
                messages = [{"id": r[0], "session_id": r[1], "author": r[2], "message": r[3], "is_ai": bool(r[4]), "created": r[5].isoformat() if r[5] else None} for r in c.fetchall()]
                return {"messages": messages}
    except: return {"messages": []}

@app.post("/api/workspace/notes")
def ws_save_note(req: WorkspaceNoteRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM workspaces WHERE room_code=%s", (req.room_code.upper(),))
                if not c.fetchone(): raise HTTPException(404)
                c.execute("DELETE FROM workspace_notes WHERE workspace_id=(SELECT id FROM workspaces WHERE room_code=%s)", (req.room_code.upper(),))
                c.execute("INSERT INTO workspace_notes (id, workspace_id, session_id, author, content, created, updated) VALUES (%s, (SELECT id FROM workspaces WHERE room_code=%s), %s, %s, %s, %s, %s)", (sid(), req.room_code.upper(), s["id"], "User", req.content, datetime.utcnow(), datetime.utcnow()))
                conn.commit()
                return {"saved": True}
    except: return {"saved": False}

@app.get("/api/workspace/notes")
def ws_get_notes(room_code: str):
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT id FROM workspaces WHERE room_code=%s", (room_code.upper(),))
                if not c.fetchone(): raise HTTPException(404)
                c.execute("SELECT author, content, updated FROM workspace_notes WHERE workspace_id=(SELECT id FROM workspaces WHERE room_code=%s)", (room_code.upper(),))
                notes = [{"author": r[0], "content": r[1], "updated": r[2].isoformat() if r[2] else None} for r in c.fetchall()]
                return {"notes": notes}
    except: return {"notes": []}

# ================================================================
# ADMIN ENDPOINT (Founder only)
# ================================================================
@app.post("/api/admin")
def admin(request: Request):
    s = get_session(request)
    if not s or s["tier"] != "founder": raise HTTPException(403)
    
    try:
        with get_db() as conn:
            with conn.cursor() as c:
                c.execute("SELECT COUNT(*) FROM sessions")
                total = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM sessions WHERE tier != 'free'")
                paid = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM chat_messages")
                msgs = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM workspaces")
                ws = c.fetchone()[0]
                
                c.execute("SELECT id, tier, msg_count, created FROM sessions ORDER BY created DESC LIMIT 30")
                sessions = [{"id": r[0], "tier": r[1], "msg_count": r[2], "created": r[3].isoformat() if r[3] else None} for r in c.fetchall()]
                
                return {"total_sessions": total, "paid_sessions": paid, "total_messages": msgs, "workspaces": ws, "sessions": sessions}
    except Exception as e:
        raise HTTPException(500, str(e))

# ================================================================
# PWA & STATIC FILES
# ================================================================
@app.get("/manifest.json")
async def get_manifest():
    manifest = {
        "name": "CAPITAN AI",
        "short_name": "CAPITAN",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#000000",
        "theme_color": "#000000",
        "orientation": "portrait",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}
        ]
    }
    return JSONResponse(content=manifest)

@app.get("/icon-192.png")
async def icon_192():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
        <rect width="100" height="100" fill="#000" rx="20"/>
        <path d="M50 15 L75 27 L75 52 C75 65 63 76 50 82 C37 76 25 65 25 52 L25 27 Z" fill="none" stroke="#A0A0A4" stroke-width="4"/>
        <text x="50" y="72" text-anchor="middle" font-size="42" fill="#A0A0A4" font-family="Inter,sans-serif" font-weight="700">C</text>
    </svg>'''
    return Response(content=svg, media_type="image/svg+xml")

@app.get("/icon-512.png")
async def icon_512():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
        <rect width="100" height="100" fill="#000" rx="20"/>
        <path d="M50 15 L75 27 L75 52 C75 65 63 76 50 82 C37 76 25 65 25 52 L25 27 Z" fill="none" stroke="#A0A0A4" stroke-width="4"/>
        <text x="50" y="72" text-anchor="middle" font-size="42" fill="#A0A0A4" font-family="Inter,sans-serif" font-weight="700">C</text>
    </svg>'''
    return Response(content=svg, media_type="image/svg+xml")

@app.get("/")
async def root():
    return {
        "name": "CAPITAN AI",
        "version": "25.0",
        "status": "operational",
        "pwa_supported": True,
        "frontend_ready": True,
        "endpoints": ["/health", "/api/session", "/api/chat", "/api/chats", "/api/markets", "/api/search", "/manifest.json"]
    }

# ================================================================
# TEST FRONTEND ENDPOINT
# ================================================================
@app.get("/test")
async def test_frontend():
    html_content = """
    <!DOCTYPE html>
    <html>
    <head><title>CAPITAN AI - Test</title><style>body{background:#000;color:#fff;font-family:monospace;}</style></head>
    <body><h1>CAPITAN AI Backend Test</h1><div id="out"></div><script>
    fetch('/health').then(r=>r.json()).then(d=>document.getElementById('out').innerHTML=JSON.stringify(d,null,2));
    </script></body></html>
    """
    return HTMLResponse(content=html_content)

# ================================================================
# MAIN ENTRY POINT
# ================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"\n{'='*60}")
    print(f"🚀 CAPITAN AI v25.0 - FULL INTELLIGENCE BACKEND")
    print(f"{'='*60}")
    print(f"📊 Database: {'Connected' if settings.DATABASE_URL else 'Not configured'}")
    print(f"🤖 AI Providers: Groq={bool(settings.GROQ_KEY)} | OpenRouter={bool(settings.OPENROUTER_KEY)}")
    print(f"📈 Markets: CoinGecko={bool(settings.COINGECKO_KEY)} | Yahoo=Active")
    print(f"🔍 Web Search: SerpAPI={bool(settings.SERPAPI_KEY)}")
    print(f"📰 News: NewsAPI={bool(settings.NEWS_API_KEY)}")
    print(f"👑 Founder Key: {settings.FOUNDER_KEY[:10]}...")
    print(f"📨 Limits: Free=17/day | Plus=40/day | Pro=Unlimited")
    print(f"🌐 PWA: Enabled")
    print(f"{'='*60}\n")
    uvicorn.run(app, host="0.0.0.0", port=port)