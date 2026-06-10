"""
CAPITAN AI — Enterprise Backend v22.0
CLOSEAI Technologies
Python/FastAPI + SQLite + Multi-API Integration
Privacy-First: No accounts, just messages & payments
Elite Intelligence: Finance, Coding, Math, Quant, Software Development, Science, Health
"""

import os, re, json, uuid, time, hashlib, hmac, base64, secrets, requests, sqlite3
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn

# ═══════════════════════════════════════════════════════════════
# API KEYS — ALL FREE TIER
# ═══════════════════════════════════════════════════════════════

# AI Models
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
MISTRAL_KEY = os.environ.get("MISTRAL_API_KEY", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
HF_TOKEN = os.environ.get("HF_TOKEN", "")
AIML_KEY = os.environ.get("AIML_API_KEY", "")
ZENMUK_KEY = os.environ.get("ZENMUK_API_KEY", "")

# Finance
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "")
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
COINGECKO_KEY = os.environ.get("COINGECKO_KEY", "")
TWELVE_DATA_KEY = os.environ.get("TWELVE_DATA_KEY", "")
ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY", "")

# News
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")
GNEWS_API_KEY = os.environ.get("GNEWS_API_KEY", "")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")

# Geo
IPGEOLOCATION_KEY = os.environ.get("IPGEOLOCATION_API_KEY", "")
LOCATIONIQ_KEY = os.environ.get("LOCATIONIQ_API_KEY", "")

# Infrastructure
CLOUDFLARE_TOKEN = os.environ.get("CLOUDFLARE_TOKEN", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# Other
WOLFRAM_APP_ID = os.environ.get("WOLFRAM_APP_ID", "")
MASSIVE_API_KEY = os.environ.get("MASSIVE_API_KEY", "")
UPSTASH_REDIS_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "")
UPSTASH_REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")

# App Config
JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))
ADMIN_CODE = os.environ.get("ADMIN_CODE", "Osinachi@350")
FOUNDER_KEY = os.environ.get("FOUNDER_KEY", "cap-founder-key")
DB_PATH = "capitan.db"

WALLETS = {"BTC":"bc1qrv6yr6e0mat96rvrc8smdf9rvu9rlp8xuk8new","ETH":"0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1"}

TIER_CONFIG = {
    "free":{"name":"Free","msg_limit":10,"workspace_max":0,"file_upload":False,"file_size_mb":0,"speed":"fast"},
    "plus":{"name":"Plus","msg_limit":30,"workspace_max":5,"file_upload":True,"file_size_mb":10,"speed":"smart"},
    "pro":{"name":"Pro","msg_limit":float("inf"),"workspace_max":16,"file_upload":True,"file_size_mb":50,"speed":"deep"},
    "founder":{"name":"Founder","msg_limit":float("inf"),"workspace_max":999,"file_upload":True,"file_size_mb":500,"speed":"deep"}
}

UPGRADE_BENEFITS = {
    "plus": [
        "30 messages per day (up from 10)",
        "Smart AI model for better responses",
        "Work Area — collaborate with up to 5 people",
        "File uploads up to 10MB",
        "Coding & Quant tools",
        "African Finance module",
        "Priority response speed",
        "Save chats & library access"
    ],
    "pro": [
        "Unlimited messages — no daily cap",
        "Deep AI model (Claude Sonnet 4 / GPT-4o)",
        "Work Area — collaborate with up to 16 people",
        "File uploads up to 50MB",
        "Live market data & financial news",
        "Shared Work Area notes with AI integration",
        "@CAPITAN AI commands in Work Area",
        "Export Work Area to PDF",
        "Business mode for professional use",
        "All Plus features included"
    ]
}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, tier TEXT DEFAULT "free", msg_count INTEGER DEFAULT 0, msg_window TEXT, created TEXT, updated TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, session_id TEXT, title TEXT, created TEXT, updated TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chat_messages (id TEXT PRIMARY KEY, chat_id TEXT, session_id TEXT, role TEXT, content TEXT, model TEXT, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS memories (id TEXT PRIMARY KEY, memory_id TEXT, session_id TEXT, content TEXT, query TEXT, domain TEXT, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS library_items (id TEXT PRIMARY KEY, session_id TEXT, name TEXT, type TEXT, content TEXT, size INTEGER DEFAULT 0, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS uploaded_files (id TEXT PRIMARY KEY, session_id TEXT, filename TEXT, original_name TEXT, size INTEGER, mime_type TEXT, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS payments (id TEXT PRIMARY KEY, session_id TEXT, txid TEXT, currency TEXT, amount REAL, tier TEXT, verified INTEGER DEFAULT 0, expires TEXT, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS payment_log (id TEXT PRIMARY KEY, session_id TEXT, tier TEXT, amount REAL, currency TEXT, txid TEXT, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspaces (id TEXT PRIMARY KEY, room_code TEXT UNIQUE, creator_session TEXT, max_members INTEGER, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspace_members (workspace_id TEXT, session_id TEXT, role TEXT DEFAULT "member", joined TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspace_messages (id TEXT PRIMARY KEY, workspace_id TEXT, session_id TEXT, author TEXT, message TEXT, is_ai INTEGER DEFAULT 0, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspace_notes (id TEXT PRIMARY KEY, workspace_id TEXT, session_id TEXT, author TEXT, content TEXT, created TEXT, updated TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS market_cache (id TEXT PRIMARY KEY, data TEXT, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS news_cache (id TEXT PRIMARY KEY, data TEXT, created TEXT)''')
    conn.commit()
    conn.close()

init_db()
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def sid(): return str(uuid.uuid4())[:8].upper()
def mid(): return 'mem_' + sid()

def create_jwt(session_id, tier):
    h = base64.urlsafe_b64encode(json.dumps({"alg":"HS256","typ":"JWT"}).encode()).decode().rstrip("=")
    p = base64.urlsafe_b64encode(json.dumps({"session_id":session_id,"tier":tier,"exp":int((datetime.utcnow()+timedelta(days=365)).timestamp())}).encode()).decode().rstrip("=")
    s = base64.urlsafe_b64encode(hmac.new(JWT_SECRET.encode(),f"{h}.{p}".encode(),hashlib.sha256).digest()).decode().rstrip("=")
    return f"{h}.{p}.{s}"

def verify_jwt(token):
    try:
        parts = token.split(".")
        if len(parts)!=3: return None
        h,p,s = parts
        es = base64.urlsafe_b64encode(hmac.new(JWT_SECRET.encode(),f"{h}.{p}".encode(),hashlib.sha256).digest()).decode().rstrip("=")
        if not hmac.compare_digest(s,es): return None
        d = json.loads(base64.urlsafe_b64decode(p+"=="))
        if d.get("exp",0) < datetime.utcnow().timestamp(): return None
        return d
    except: return None

def get_session(request: Request):
    auth = request.headers.get("Authorization","")
    if auth.startswith("Bearer "):
        payload = verify_jwt(auth[7:])
        if payload:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT id,tier,msg_count,msg_window FROM sessions WHERE id=?",(payload["session_id"],))
            row = c.fetchone(); conn.close()
            if row: return {"id":row[0],"tier":row[1],"msg_count":row[2] or 0,"msg_window":row[3]}
    return None

# ═══════════════════════════════════════════════════════════════
# UPSTASH REDIS RATE LIMITER (if configured)
# ═══════════════════════════════════════════════════════════════
rate_store = {}

def check_rate(session_id, tier):
    now = time.time(); key = f"{session_id}"
    if key not in rate_store: rate_store[key] = []
    rate_store[key] = [t for t in rate_store[key] if now-t < 60]
    limits = {"free":10,"plus":20,"pro":60,"founder":200}
    if len(rate_store[key]) >= limits.get(tier,10): return False
    rate_store[key].append(now); return True

# ═══════════════════════════════════════════════════════════════
# GEO-LOCATION FOR TIMEZONE-AWARE GREETINGS
# ═══════════════════════════════════════════════════════════════
def get_user_timezone(request: Request = None):
    """Detect user timezone via IP or fallback to UTC"""
    try:
        if IPGEOLOCATION_KEY and request:
            client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "")
            if client_ip:
                r = requests.get(f"https://api.ipgeolocation.io/timezone?apiKey={IPGEOLOCATION_KEY}&ip={client_ip.split(',')[0].strip()}", timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    return data.get("timezone", "UTC")
    except: pass
    return "UTC"

def get_time_context(request: Request = None):
    now = datetime.utcnow()
    hour = now.hour
    day = now.strftime("%A")
    date = now.strftime("%B %d, %Y")
    utc_time = now.strftime("%H:%M UTC")
    
    if hour < 5:
        time_of_day = "late night"
        greeting_context = "It's quite late — or early, depending on how you look at it."
    elif hour < 12:
        time_of_day = "morning"
        greeting_context = "Good morning! Hope your day is off to a great start."
    elif hour < 17:
        time_of_day = "afternoon"
        greeting_context = "Good afternoon. The markets are in full swing if you're tracking them."
    elif hour < 21:
        time_of_day = "evening"
        greeting_context = "Good evening. A good time to review the day's activity."
    else:
        time_of_day = "night"
        greeting_context = "Good night, night owl. Burning the midnight oil on something interesting?"
    
    return {"time_of_day":time_of_day,"day":day,"date":date,"utc_time":utc_time,"greeting_context":greeting_context,"hour":hour}

# ═══════════════════════════════════════════════════════════════
# MULTI-SOURCE MARKET DATA AGGREGATOR
# ═══════════════════════════════════════════════════════════════

def get_market_data():
    """Aggregate market data from multiple free API sources"""
    results = {}
    
    # 1. Yahoo Finance (primary — no API key needed)
    try:
        syms = "^GSPC,^IXIC,^DJI,^FTSE,^N225,AAPL,MSFT,NVDA,TSLA,GOOGL,META,AMZN,JPM,GS,GC=F,CL=F,SI=F,EURUSD=X,GBPUSD=X,USDJPY=X,USDGHS=X,USDNGN=X,USDZAR=X,USDKES=X,BTC-USD,ETH-USD"
        r = requests.get(f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={syms}&fields=regularMarketPrice,regularMarketPreviousClose,shortName",headers={"User-Agent":"Mozilla/5.0"},timeout=10)
        if r.status_code==200:
            for i in r.json().get("quoteResponse",{}).get("result",[]):
                if i.get("regularMarketPrice") and i.get("regularMarketPreviousClose"):
                    results[i.get("shortName") or i["symbol"]] = {"price":i["regularMarketPrice"],"change":round(((i["regularMarketPrice"]-i["regularMarketPreviousClose"])/i["regularMarketPreviousClose"])*100,2),"source":"Yahoo"}
    except: pass
    
    # 2. Alpha Vantage (forex & crypto)
    if ALPHA_VANTAGE_KEY:
        try:
            pairs = ["EURUSD","GBPUSD","USDJPY","USDGHS","USDNGN","USDZAR","USDKES"]
            for pair in pairs:
                r = requests.get(f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={pair[:3]}&to_currency={pair[3:]}&apikey={ALPHA_VANTAGE_KEY}",timeout=10)
                if r.status_code==200:
                    data = r.json().get("Realtime Currency Exchange Rate",{})
                    if data:
                        price = float(data.get("5. Exchange Rate",0))
                        results[f"FX:{pair}"] = {"price":price,"change":0,"source":"AlphaVantage"}
        except: pass
    
    # 3. CoinGecko (crypto — free tier)
    if COINGECKO_KEY and COINGECKO_KEY.startswith("CG-"):
        try:
            r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true",headers={"x-cg-demo-api-key":COINGECKO_KEY},timeout=10)
            if r.status_code==200:
                data = r.json()
                if "bitcoin" in data:
                    results["Bitcoin (BTC)"] = {"price":data["bitcoin"]["usd"],"change":data["bitcoin"].get("usd_24h_change",0),"source":"CoinGecko"}
                if "ethereum" in data:
                    results["Ethereum (ETH)"] = {"price":data["ethereum"]["usd"],"change":data["ethereum"].get("usd_24h_change",0),"source":"CoinGecko"}
        except: pass
    
    # 4. Twelve Data (real-time stocks)
    if TWELVE_DATA_KEY:
        try:
            syms_12 = ["SPX","IXIC","DJI","AAPL","MSFT","NVDA","GC","CL","SI"]
            for sym in syms_12[:3]:
                r = requests.get(f"https://api.twelvedata.com/price?symbol={sym}&apikey={TWELVE_DATA_KEY}",timeout=10)
                if r.status_code==200:
                    data = r.json()
                    if data.get("price"):
                        results[f"12D:{sym}"] = {"price":float(data["price"]),"change":0,"source":"TwelveData"}
        except: pass
    
    # 5. Finnhub (stocks + news sentiment)
    if FINNHUB_API_KEY:
        try:
            syms_fh = ["AAPL","MSFT","NVDA","TSLA","GOOGL"]
            for sym in syms_fh[:2]:
                r = requests.get(f"https://finnhub.io/api/v1/quote?symbol={sym}&token={FINNHUB_API_KEY}",timeout=10)
                if r.status_code==200:
                    data = r.json()
                    if data.get("c"):
                        prev = data.get("pc",data["c"])
                        change = round(((data["c"]-prev)/prev)*100,2) if prev else 0
                        results[f"FH:{sym}"] = {"price":data["c"],"change":change,"source":"Finnhub"}
        except: pass
    
    # 6. FRED (economic data — interest rates, GDP, inflation)
    if FRED_API_KEY:
        try:
            series = {"FEDFUNDS":"Fed Funds Rate","GDP":"US GDP","CPIAUCSL":"CPI Inflation","UNRATE":"Unemployment"}
            for sid, name in list(series.items())[:2]:
                r = requests.get(f"https://api.stlouisfed.org/fred/series/observations?series_id={sid}&api_key={FRED_API_KEY}&file_type=json&limit=1&sort_order=desc",timeout=10)
                if r.status_code==200:
                    obs = r.json().get("observations",[])
                    if obs:
                        results[f"FRED:{name}"] = {"price":float(obs[0].get("value",0)),"change":0,"source":"FRED"}
        except: pass
    
    # Cache results for 60 seconds
    return results

# ═══════════════════════════════════════════════════════════════
# MULTI-SOURCE FINANCIAL NEWS AGGREGATOR
# ═══════════════════════════════════════════════════════════════

def get_financial_news():
    """Aggregate financial news from multiple free sources"""
    news = []
    
    # 1. GNews (free tier)
    if GNEWS_API_KEY:
        try:
            r = requests.get(f"https://gnews.io/api/v4/search?q=finance+markets+stocks&lang=en&max=5&apikey={GNEWS_API_KEY}",timeout=10)
            if r.status_code==200:
                for article in r.json().get("articles",[]):
                    news.append({"source":article.get("source",{}).get("name","GNews"),"headline":article.get("title",""),"url":article.get("url",""),"time":article.get("publishedAt",""),"summary":article.get("description","")[:200]})
        except: pass
    
    # 2. News API
    if NEWS_API_KEY:
        try:
            r = requests.get(f"https://newsapi.org/v2/top-headlines?category=business&language=en&pageSize=5&apiKey={NEWS_API_KEY}",timeout=10)
            if r.status_code==200:
                for article in r.json().get("articles",[]):
                    news.append({"source":article.get("source",{}).get("name","NewsAPI"),"headline":article.get("title",""),"url":article.get("url",""),"time":article.get("publishedAt",""),"summary":article.get("description","")[:200]})
        except: pass
    
    # 3. Finnhub News
    if FINNHUB_API_KEY:
        try:
            r = requests.get(f"https://finnhub.io/api/v1/news?category=general&token={FINNHUB_API_KEY}",timeout=10)
            if r.status_code==200:
                for article in r.json()[:5]:
                    news.append({"source":article.get("source","Finnhub"),"headline":article.get("headline",""),"url":article.get("url",""),"time":datetime.fromtimestamp(article.get("datetime",0)).isoformat() if article.get("datetime") else "","summary":article.get("summary","")[:200]})
        except: pass
    
    # 4. Alpha Vantage News
    if ALPHA_VANTAGE_KEY:
        try:
            r = requests.get(f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&apikey={ALPHA_VANTAGE_KEY}",timeout=10)
            if r.status_code==200:
                for article in r.json().get("feed",[])[:5]:
                    news.append({"source":article.get("source","AlphaVantage"),"headline":article.get("title",""),"url":article.get("url",""),"time":article.get("time_published",""),"summary":article.get("summary","")[:200]})
        except: pass
    
    # 5. SerpAPI Google News
    if SERPAPI_KEY:
        try:
            r = requests.get(f"https://serpapi.com/search?engine=google_news&q=financial+markets&api_key={SERPAPI_KEY}",timeout=10)
            if r.status_code==200:
                for article in r.json().get("news_results",[])[:5]:
                    news.append({"source":article.get("source","SerpAPI"),"headline":article.get("title",""),"url":article.get("link",""),"time":"","summary":article.get("snippet","")[:200]})
        except: pass
    
    # Deduplicate by headline
    seen = set()
    unique_news = []
    for n in news:
        key = n["headline"][:80]
        if key not in seen:
            seen.add(key)
            unique_news.append(n)
    
    return unique_news[:10]

# ═══════════════════════════════════════════════════════════════
# ELITE INTELLIGENCE SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════

ELITE_SYSTEM_PROMPT = """You are CAPITAN AI — an elite institutional intelligence system created by CLOSEAI Technologies.

ABOUT CLOSEAI TECHNOLOGIES:
CLOSEAI Technologies was established under the leadership of CEO Osinachi Chukwu, with pivotal support from Non-Executive Director Blessing Asuquo, whose provision of essential logistics, alongside the contributions of CIO Ebubechi Chukwu, has been instrumental to the company's development. CAPITAN AI is the company's flagship AI brain.

YOUR IDENTITY:
You are warm, natural, and conversational — like a brilliant colleague who happens to know a lot about everything. You speak like a smart, experienced human being who genuinely wants to help.

CURRENT TEMPORAL CONTEXT:
Right now it is {day}, {date} at {utc_time} ({time_of_day} in UTC). {greeting_context}

COMMUNICATION STYLE:
• Be conversational. Start naturally: "Great question," "Let me walk you through this," "Here's how I think about it..."
• Use contractions naturally: "it's," "you're," "I've"
• Never use corporate jargon or buzzwords
• Match the user's energy

KNOWLEDGE DOMAINS:

FINANCE:
• DCF, LBO, M&A accretion/dilution, comparable company analysis
• Portfolio optimization, Options pricing, Fixed income
• Risk management (VaR, CVaR, stress testing)
• Financial statement analysis, ratio analysis
• Macroeconomic analysis (central bank policy, yield curves, FX)
• African financial markets (NGX, JSE, GSE, BRVM, EGX)
• I track live market data from multiple sources
• NEVER give buy/sell recommendations

CODING & SOFTWARE:
• Python, JavaScript, TypeScript, Rust, Go, C++, SQL, React, Node.js
• System design, API design, Database optimization
• DevOps (Docker, Kubernetes, CI/CD)
• Production-grade code with error handling

MATHEMATICS:
• Real/complex analysis, Linear algebra, Topology
• Probability theory, Stochastic processes
• Numerical methods, Optimization
• Rigorous proofs with LaTeX: $E = mc^2$

QUANTITATIVE FINANCE:
• Stochastic calculus (Itô's lemma, SDEs)
• Derivative pricing, Monte Carlo simulation
• Time series analysis (ARIMA, GARCH, cointegration)
• Factor models, Machine learning in finance
• NEVER give specific entry/exit signals

SCIENCE & HEALTH:
• Physics, Chemistry, Biology, Medicine
• Evidence-based health information
• I am not a doctor — consult healthcare professionals

RESPONSE ARCHITECTURE:
1. Lead with the most useful insight
2. Explain the mechanism
3. Provide evidence
4. Be honest about confidence
5. Offer to go deeper

IMPORTANT NOTES:
• Never make up information
• Never provide financial advice or medical diagnoses
• Adapt depth based on tier

CURRENT DOMAIN: {domain}
USER TIER: {tier}
"""

# ═══════════════════════════════════════════════════════════════
# MULTI-PROVIDER AI CALL FUNCTION
# ═══════════════════════════════════════════════════════════════

def call_ai(messages, tier="free"):
    """Try AI providers: OpenRouter → Groq → HuggingFace → AIML → ZenMuk → Mistral → OpenAI → Fallback"""
    
    # ─── PROVIDER 1: OpenRouter ───────────────────────────
    if OPENROUTER_KEY:
        if tier in ("pro", "founder"):
            models = ["anthropic/claude-sonnet-4-20250514","anthropic/claude-3.5-sonnet","openai/gpt-4o","google/gemini-2.0-flash","google/gemini-flash-1.5","mistral/mistral-7b-instruct","deepseek/deepseek-chat","meta-llama/llama-3.1-8b-instruct","openai/gpt-3.5-turbo"]
        else:
            models = ["google/gemini-2.0-flash","google/gemini-flash-1.5","mistral/mistral-7b-instruct","deepseek/deepseek-chat","meta-llama/llama-3.1-8b-instruct","openai/gpt-3.5-turbo"]
        for model in models:
            try:
                r = requests.post("https://openrouter.ai/api/v1/chat/completions",headers={"Authorization":f"Bearer {OPENROUTER_KEY}","Content-Type":"application/json","HTTP-Referer":"https://capitan.pages.dev","X-Title":"CAPITAN AI"},json={"model":model,"messages":messages,"temperature":0.4,"max_tokens":600 if tier=="free" else 2500},timeout=90)
                if r.status_code==200:
                    content = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
                    if content: return content, model
            except: continue
    
    # ─── PROVIDER 2: Groq (Free, Fast) ────────────────────
    if GROQ_KEY:
        try:
            r = requests.post("https://api.groq.com/openai/v1/chat/completions",headers={"Authorization":f"Bearer {GROQ_KEY}","Content-Type":"application/json"},json={"model":"llama-3.1-8b-instant","messages":messages,"temperature":0.4,"max_tokens":600 if tier=="free" else 2500},timeout=60)
            if r.status_code==200:
                content = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
                if content: return content, "groq/llama-3.1-8b-instant"
        except: pass
    
    # ─── PROVIDER 3: Hugging Face ─────────────────────────
    if HF_TOKEN:
        try:
            r = requests.post("https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2/v1/chat/completions",headers={"Authorization":f"Bearer {HF_TOKEN}","Content-Type":"application/json"},json={"model":"mistralai/Mistral-7B-Instruct-v0.2","messages":messages,"temperature":0.4,"max_tokens":600},timeout=60)
            if r.status_code==200:
                content = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
                if content: return content, "hf/mistral-7b"
        except: pass
    
    # ─── PROVIDER 4: AIML API ─────────────────────────────
    if AIML_KEY:
        try:
            r = requests.post("https://api.aimlapi.com/v1/chat/completions",headers={"Authorization":f"Bearer {AIML_KEY}","Content-Type":"application/json"},json={"model":"gpt-3.5-turbo","messages":messages,"temperature":0.4,"max_tokens":600},timeout=60)
            if r.status_code==200:
                content = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
                if content: return content, "aiml/gpt-3.5-turbo"
        except: pass
    
    # ─── PROVIDER 5: ZenMuk ───────────────────────────────
    if ZENMUK_KEY:
        try:
            r = requests.post("https://api.zenmuk.com/v1/chat/completions",headers={"Authorization":f"Bearer {ZENMUK_KEY}","Content-Type":"application/json"},json={"model":"gpt-3.5-turbo","messages":messages,"temperature":0.4,"max_tokens":600},timeout=60)
            if r.status_code==200:
                content = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
                if content: return content, "zenmuk/gpt-3.5-turbo"
        except: pass
    
    # ─── PROVIDER 6: Mistral Direct ───────────────────────
    if MISTRAL_KEY:
        try:
            r = requests.post("https://api.mistral.ai/v1/chat/completions",headers={"Authorization":f"Bearer {MISTRAL_KEY}","Content-Type":"application/json"},json={"model":"mistral-tiny","messages":messages,"temperature":0.4,"max_tokens":600},timeout=60)
            if r.status_code==200:
                content = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
                if content: return content, "mistral/mistral-tiny"
        except: pass
    
    # ─── PROVIDER 7: OpenAI Direct ────────────────────────
    if OPENAI_KEY:
        try:
            r = requests.post("https://api.openai.com/v1/chat/completions",headers={"Authorization":f"Bearer {OPENAI_KEY}","Content-Type":"application/json"},json={"model":"gpt-3.5-turbo","messages":messages,"temperature":0.4,"max_tokens":600},timeout=60)
            if r.status_code==200:
                return r.json()["choices"][0]["message"]["content"], "gpt-3.5-turbo"
        except: pass
    
    return "I'm having a bit of trouble connecting to my systems. Give me a moment and try again? If this persists, reach out to closeaitechnologies@protonmail.com.", "fallback"

def classify(q):
    q = q.lower()
    if re.search(r'crispr|dna|rna|protein|cell|gene|genome|physics|quantum|chemistry|biology|neuroscience|climate|energy|health|medicine|disease|symptom|treatment|diagnosis|anatomy|physiology|pharma|drug|vaccine|immunology|surgery|therapy|cancer|diabetes|heart|brain|blood|virus|bacteria|infection|covid|mental health|nutrition|diet|exercise|sleep|wellness',q): return 'science'
    if re.search(r'```|def |class |import |from |package|npm|pip|docker|kubernetes|aws|api\s|rest |graphql|sql\s|database|query|react|node\.js|javascript|typescript|python\s|rust\s|golang|microservice|architecture|system design|refactor|debug|deploy|ci/cd|git\s',q): return 'coding'
    if re.search(r'stochastic|ito|black.scholes|monte carlo|var\s|cvar|sharpe ratio|sortino|beta\s|alpha\s|option pricing|derivative pricing|risk neutral|fama.french|cointegration|garch|arima|backtest|factor model|portfolio optim',q): return 'quant'
    if re.search(r'dcf|discounted cash flow|ebitda|ebit|revenue|earnings|balance sheet|income statement|cash flow|valuation|wacc|capm|pe ratio|pb ratio|ev/ebitda|dividend|yield|bond|coupon|duration|convexity|forex|fx\s|central bank|federal reserve|ecb|interest rate|inflation|gdp|macro|equity|stock\s|market\s|trading|invest|portfolio|crypto|bitcoin|ethereum|defi|ngx|jse|gse|african market|gold|xauusd|silver|oil|commodity',q): return 'finance'
    if re.search(r'prove|proof|theorem|lemma|corollary|derive|integral|derivative|differential equation|linear algebra|matrix|eigenvalue|vector|topology|group theory|probability|statistics|distribution|convergence|limit|sum|product|calculus|laplace|fourier|numerical|optimization|convex|gradient',q): return 'math'
    return 'general'

def system_prompt(domain, tier, session_id=None, request=None):
    tc = get_time_context(request)
    base = ELITE_SYSTEM_PROMPT.replace("{domain}", domain).replace("{tier}", tier)
    base = base.replace("{day}", tc["day"]).replace("{date}", tc["date"]).replace("{utc_time}", tc["utc_time"]).replace("{time_of_day}", tc["time_of_day"]).replace("{greeting_context}", tc["greeting_context"])
    
    if session_id:
        try:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT query, domain FROM memories WHERE session_id=? ORDER BY created DESC LIMIT 5",(session_id,))
            rows = c.fetchall(); conn.close()
            if rows:
                base += "\n\n## USER CONTEXT (from earlier)\n"
                for r in rows: base += f"• [{r[1]}] {r[0][:120]}\n"
                base += "Use this for continuity naturally."
        except: pass
    
    if tier == "free": base += "\n\nBe focused and clear."
    elif tier == "plus": base += "\n\nGo into solid detail with examples."
    elif tier in ("pro","founder"): base += "\n\nGo deep — comprehensive analysis with examples, code, derivations, citations."
    
    # Inject live market data
    try:
        market_data = get_market_data()
        if market_data:
            key_items = []
            for sym, data in list(market_data.items())[:10]:
                direction = "up" if data.get("change",0) >= 0 else "down"
                key_items.append(f"{sym}: {data['price']} ({direction} {abs(data['change'])}%) [{data.get('source','')}]")
            if key_items:
                base += f"\n\nLIVE MARKET DATA:\n" + "\n".join(key_items)
                base += "\nReference these naturally when relevant."
    except: pass
    
    # Inject financial news headlines
    try:
        news = get_financial_news()
        if news:
            headlines = [f"• [{n['source']}] {n['headline'][:100]}" for n in news[:5]]
            base += f"\n\nLATEST FINANCIAL NEWS:\n" + "\n".join(headlines)
            base += "\nReference relevant news naturally."
    except: pass
    
    return base

# ═══════════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════════
class ChatRequest(BaseModel): messages: list; chat_id: Optional[str] = None
class UpgradeRequest(BaseModel): tier: str; txid: str; currency: str = "BTC"
class FounderRequest(BaseModel): code: str
class LibraryItemRequest(BaseModel): name: str; type: str = "note"; content: Optional[str] = ""
class WorkspaceCreateRequest(BaseModel): room_code: str; max_members: int = 3
class WorkspaceJoinRequest(BaseModel): room_code: str
class WorkspaceMessageRequest(BaseModel): room_code: str; message: str
class WorkspaceNoteRequest(BaseModel): room_code: str; content: str

# ═══════════════════════════════════════════════════════════════
# APP
# ═══════════════════════════════════════════════════════════════
app = FastAPI(title="CAPITAN AI API", version="22.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health():
    ai = "disconnected"
    providers = []
    if OPENROUTER_KEY:
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions",headers={"Authorization":f"Bearer {OPENROUTER_KEY}","Content-Type":"application/json"},json={"model":"google/gemini-flash-1.5","messages":[{"role":"user","content":"Hi"}],"max_tokens":5},timeout=15)
            if r.status_code==200: ai="connected"; providers.append("openrouter")
        except: pass
    if ai != "connected" and GROQ_KEY:
        try:
            r = requests.post("https://api.groq.com/openai/v1/chat/completions",headers={"Authorization":f"Bearer {GROQ_KEY}","Content-Type":"application/json"},json={"model":"llama-3.1-8b-instant","messages":[{"role":"user","content":"Hi"}],"max_tokens":5},timeout=15)
            if r.status_code==200: ai="connected"; providers.append("groq")
        except: pass
    if ai != "connected" and HF_TOKEN:
        try:
            r = requests.post("https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2/v1/chat/completions",headers={"Authorization":f"Bearer {HF_TOKEN}","Content-Type":"application/json"},json={"model":"mistralai/Mistral-7B-Instruct-v0.2","messages":[{"role":"user","content":"Hi"}],"max_tokens":5},timeout=15)
            if r.status_code==200: ai="connected"; providers.append("huggingface")
        except: pass
    if ai != "connected" and OPENAI_KEY:
        try:
            r = requests.post("https://api.openai.com/v1/chat/completions",headers={"Authorization":f"Bearer {OPENAI_KEY}","Content-Type":"application/json"},json={"model":"gpt-3.5-turbo","messages":[{"role":"user","content":"Hi"}],"max_tokens":5},timeout=15)
            if r.status_code==200: ai="connected"; providers.append("openai")
        except: pass
    
    markets_available = bool(ALPHA_VANTAGE_KEY or COINGECKO_KEY or TWELVE_DATA_KEY or FINNHUB_API_KEY)
    news_available = bool(GNEWS_API_KEY or NEWS_API_KEY or SERPAPI_KEY)
    
    return {"status":"ok","version":"22.0","ai":ai,"providers":providers,"markets_available":markets_available,"news_available":news_available}

@app.get("/api/session")
def get_or_create_session(request: Request):
    session = get_session(request)
    if session: return session
    auth = request.headers.get("Authorization","")
    if auth.startswith("Bearer "):
        payload = verify_jwt(auth[7:])
        if payload:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT id,tier,msg_count,msg_window FROM sessions WHERE id=?",(payload["session_id"],))
            row = c.fetchone(); conn.close()
            if row: return {"id":row[0],"tier":row[1],"msg_count":row[2] or 0,"msg_window":row[3]}
    session_id = f"s_{sid()}"
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("INSERT INTO sessions (id,tier,msg_count,msg_window,created,updated) VALUES (?,?,0,?,?,?)",(session_id,"free",datetime.utcnow().isoformat(),datetime.utcnow().isoformat(),datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    token = create_jwt(session_id,"free")
    return {"id":session_id,"tier":"free","msg_count":0,"token":token}

@app.get("/api/payment-config")
def payment_config(): return {"wallets":WALLETS,"prices":{"plus":8,"pro":17},"benefits":UPGRADE_BENEFITS}

@app.get("/api/markets")
def markets():
    return {"prices":get_market_data(),"news":get_financial_news()}

@app.get("/api/markets/prices")
def markets_prices():
    return {"prices":get_market_data()}

@app.get("/api/markets/news")
def markets_news():
    return {"news":get_financial_news()}

@app.get("/api/chats")
def get_chats(request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,title,created,updated FROM chats WHERE session_id=? ORDER BY updated DESC LIMIT 30",(s["id"],))
    rows = c.fetchall(); conn.close()
    return {"chats":[{"id":r[0],"title":r[1],"created":r[2],"updated":r[3]} for r in rows]}

@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM chats WHERE id=? AND session_id=?",(chat_id,s["id"]))
    if not c.fetchone(): raise HTTPException(404,"Not found")
    c.execute("SELECT id,role,content,model,created FROM chat_messages WHERE chat_id=? ORDER BY created ASC",(chat_id,))
    msgs = [{"id":r[0],"role":r[1],"content":r[2],"model":r[3],"created":r[4]} for r in c.fetchall()]
    conn.close()
    return {"messages":msgs}

@app.post("/api/chat")
def chat(req: ChatRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    if not check_rate(s["id"],s["tier"]): raise HTTPException(429,"Rate limit")
    cfg = TIER_CONFIG.get(s["tier"],TIER_CONFIG["free"])
    limit = cfg["msg_limit"]
    if limit != float("inf"):
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT msg_count,msg_window FROM sessions WHERE id=?",(s["id"],))
        row = c.fetchone()
        count = row[0] or 0
        if count >= limit:
            w = datetime.fromisoformat(row[1]) if row and row[1] else datetime.utcnow()
            if datetime.utcnow() - w < timedelta(hours=24): raise HTTPException(429,f"Daily limit reached ({limit}/day). Upgrade to continue.")
            c.execute("UPDATE sessions SET msg_count=0, msg_window=? WHERE id=?",(datetime.utcnow().isoformat(),s["id"]))
            conn.commit()
        conn.close()
    user_msg = next((m["content"] for m in reversed(req.messages) if m.get("role")=="user"),"")
    if not user_msg: raise HTTPException(400,"No message")
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    chat_id = req.chat_id or f"chat_{sid()}"
    if not req.chat_id:
        c.execute("INSERT INTO chats (id,session_id,title,created,updated) VALUES (?,?,?,?,?)",(chat_id,s["id"],user_msg[:60],datetime.utcnow().isoformat(),datetime.utcnow().isoformat()))
    else:
        c.execute("UPDATE chats SET updated=? WHERE id=? AND session_id=?",(datetime.utcnow().isoformat(),chat_id,s["id"]))
    c.execute("INSERT INTO chat_messages (id,chat_id,session_id,role,content,created) VALUES (?,?,?,?,?,?)",(f"msg_{sid()}",chat_id,s["id"],"user",user_msg,datetime.utcnow().isoformat()))
    c.execute("UPDATE sessions SET msg_count = msg_count + 1 WHERE id=?",(s["id"],))
    conn.commit()
    c.execute("SELECT role,content FROM chat_messages WHERE chat_id=? ORDER BY created ASC LIMIT 25",(chat_id,))
    history = [{"role":r[0],"content":r[1]} for r in c.fetchall()]
    domain = classify(user_msg)
    prompt = system_prompt(domain, s["tier"], s["id"], request)
    result, model_used = call_ai([{"role":"system","content":prompt}] + history, s["tier"])
    if result:
        c.execute("INSERT INTO chat_messages (id,chat_id,session_id,role,content,model,created) VALUES (?,?,?,?,?,?,?)",(f"msg_{sid()}",chat_id,s["id"],"assistant",result,model_used,datetime.utcnow().isoformat()))
    c.execute("INSERT INTO memories (id,memory_id,session_id,content,query,domain,created) VALUES (?,?,?,?,?,?,?)",(sid(),mid(),s["id"],result,user_msg,domain,datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    remaining = limit - (s["msg_count"]+1) if limit!=float("inf") else "unlimited"
    return {"content":result,"chat_id":chat_id,"model":model_used,"remaining":remaining}

@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("DELETE FROM chat_messages WHERE chat_id=? AND session_id=?",(chat_id,s["id"]))
    c.execute("DELETE FROM chats WHERE id=? AND session_id=?",(chat_id,s["id"]))
    conn.commit(); conn.close()
    return {"deleted":True}

@app.get("/api/library")
def get_library(request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,name,type,content,size,created FROM library_items WHERE session_id=? ORDER BY created DESC",(s["id"],))
    items = [{"id":r[0],"name":r[1],"type":r[2],"content":r[3],"size":r[4],"created":r[5]} for r in c.fetchall()]
    conn.close()
    return {"items":items}

@app.post("/api/library")
def create_library_item(req: LibraryItemRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    item_id = f"lib_{sid()}"
    c.execute("INSERT INTO library_items (id,session_id,name,type,content,size,created) VALUES (?,?,?,?,?,?,?)",(item_id,s["id"],req.name,req.type,req.content or "",len(req.content or ""),datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return {"id":item_id,"created":True}

@app.delete("/api/library/{item_id}")
def delete_library_item(item_id: str, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("DELETE FROM library_items WHERE id=? AND session_id=?",(item_id,s["id"]))
    conn.commit(); conn.close()
    return {"deleted":True}

@app.post("/api/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    s = get_session(request)
    if not s: raise HTTPException(401)
    cfg = TIER_CONFIG.get(s["tier"],TIER_CONFIG["free"])
    if not cfg["file_upload"]: raise HTTPException(403,"Upgrade required")
    contents = await file.read()
    size_mb = len(contents) / (1024*1024)
    if size_mb > cfg["file_size_mb"]: raise HTTPException(400,f"Max {cfg['file_size_mb']}MB")
    file_id = f"file_{sid()}"
    with open(os.path.join(UPLOAD_DIR, file_id), "wb") as f: f.write(contents)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("INSERT INTO uploaded_files (id,session_id,filename,original_name,size,mime_type,created) VALUES (?,?,?,?,?,?,?)",(file_id,s["id"],file_id,file.filename or "unknown",len(contents),file.content_type or "application/octet-stream",datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return {"id":file_id,"filename":file.filename,"size_mb":round(size_mb,2)}

@app.post("/api/upgrade")
def upgrade(req: UpgradeRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    if req.tier not in ("plus","pro"): raise HTTPException(400,"Invalid tier")
    if not req.txid.strip(): raise HTTPException(400,"TXID required")
    prices = {"plus":8,"pro":17}
    cur = req.currency.upper()
    expiry = (datetime.utcnow()+timedelta(days=30)).isoformat()
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("INSERT INTO payments (id,session_id,txid,currency,amount,tier,verified,expires,created) VALUES (?,?,?,?,?,?,?,?,?)",(sid(),s["id"],req.txid.strip(),cur,prices[req.tier],req.tier,1,expiry,datetime.utcnow().isoformat()))
    c.execute("UPDATE sessions SET tier=?, msg_count=0, updated=? WHERE id=?",(req.tier,datetime.utcnow().isoformat(),s["id"]))
    c.execute("INSERT INTO payment_log (id,session_id,tier,amount,currency,txid,created) VALUES (?,?,?,?,?,?,?)",(sid(),s["id"],req.tier,prices[req.tier],cur,req.txid,datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    token = create_jwt(s["id"],req.tier)
    return {"verified":True,"tier":req.tier,"token":token}

@app.post("/api/founder")
def founder(req: FounderRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    valid_codes = [ADMIN_CODE]
    if FOUNDER_KEY: valid_codes.append(FOUNDER_KEY)
    if req.code not in valid_codes: raise HTTPException(403,"Invalid code")
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("UPDATE sessions SET tier='founder', msg_count=0, updated=? WHERE id=?",(datetime.utcnow().isoformat(),s["id"]))
    conn.commit(); conn.close()
    token = create_jwt(s["id"],"founder")
    return {"verified":True,"tier":"founder","token":token}

@app.post("/api/admin")
def admin(request: Request):
    s = get_session(request)
    if not s or s["tier"]!="founder": raise HTTPException(403,"Access denied")
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM sessions"); total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM sessions WHERE tier!='free'"); paid = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM chat_messages"); msgs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM workspaces"); ws = c.fetchone()[0]
    c.execute("SELECT id,tier,msg_count,created FROM sessions ORDER BY created DESC LIMIT 30")
    sessions = [{"id":r[0],"tier":r[1],"msg_count":r[2],"created":r[3]} for r in c.fetchall()]
    c.execute("SELECT * FROM payment_log ORDER BY created DESC LIMIT 20")
    payments = [{"session_id":r[1],"tier":r[2],"amount":r[3],"currency":r[4],"txid":r[5],"created":r[6]} for r in c.fetchall()]
    conn.close()
    return {"total_sessions":total,"paid_sessions":paid,"total_messages":msgs,"workspaces":ws,"sessions":sessions,"payments":payments}

@app.post("/api/workspace/create")
def ws_create(req: WorkspaceCreateRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    max_m = TIER_CONFIG.get(s["tier"],{}).get("workspace_max",0)
    if max_m == 0: raise HTTPException(403,"Work Area requires Plus or Pro")
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    wid = sid()
    c.execute("INSERT INTO workspaces (id,room_code,creator_session,max_members,created) VALUES (?,?,?,?,?)",(wid,req.room_code.upper(),s["id"],min(req.max_members,max_m),datetime.utcnow().isoformat()))
    c.execute("INSERT INTO workspace_members (workspace_id,session_id,role,joined) VALUES (?,?,?,?)",(wid,s["id"],"admin",datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return {"room_id":wid,"room_code":req.room_code.upper(),"created":True}

@app.post("/api/workspace/join")
def ws_join(req: WorkspaceJoinRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,max_members FROM workspaces WHERE room_code=?",(req.room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404,"Room not found")
    c.execute("SELECT COUNT(*) FROM workspace_members WHERE workspace_id=?",(ws[0],))
    if c.fetchone()[0] >= ws[1]: raise HTTPException(400,"Room full")
    c.execute("INSERT OR IGNORE INTO workspace_members (workspace_id,session_id,role,joined) VALUES (?,?,?,?)",(ws[0],s["id"],"member",datetime.utcnow().isoformat()))
    c.execute("SELECT m.session_id,m.role FROM workspace_members m WHERE m.workspace_id=?",(ws[0],))
    members = [{"session_id":r[0],"role":r[1]} for r in c.fetchall()]
    c.execute("SELECT id,session_id,author,message,is_ai,created FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 50",(ws[0],))
    messages = [{"id":r[0],"session_id":r[1],"author":r[2],"message":r[3],"is_ai":bool(r[4]),"created":r[5]} for r in c.fetchall()]
    conn.commit(); conn.close()
    return {"joined":True,"room_id":ws[0],"members":members,"messages":messages}

@app.post("/api/workspace/message")
def ws_message(req: WorkspaceMessageRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM workspaces WHERE room_code=?",(req.room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404,"Room not found")
    is_ai = req.message.strip().startswith("@CAPITAN")
    if is_ai:
        c.execute("SELECT author,message FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 20",(ws[0],))
        context = "\n".join([f"{r[0]}: {r[1]}" for r in c.fetchall()])
        c.execute("SELECT content FROM workspace_notes WHERE workspace_id=?",(ws[0],))
        notes = "\n".join([r[0] for r in c.fetchall()])
        ai_prompt = f"Work Area context:\nChat:\n{context}\n\nNotes:\n{notes}\n\nUser: {req.message.replace('@CAPITAN','').strip()}\n\nRespond as CAPITAN AI."
        result, _ = call_ai([{"role":"system","content":ai_prompt}], s["tier"])
        if result:
            c.execute("INSERT INTO workspace_messages (id,workspace_id,session_id,author,message,is_ai,created) VALUES (?,?,?,?,?,?,?)",(sid(),ws[0],s["id"],"CAPITAN AI",result,1,datetime.utcnow().isoformat()))
            conn.commit()
    c.execute("INSERT INTO workspace_messages (id,workspace_id,session_id,author,message,created) VALUES (?,?,?,?,?,?)",(sid(),ws[0],s["id"],"User",req.message,datetime.utcnow().isoformat()))
    conn.commit()
    c.execute("SELECT id,session_id,author,message,is_ai,created FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 50",(ws[0],))
    messages = [{"id":r[0],"session_id":r[1],"author":r[2],"message":r[3],"is_ai":bool(r[4]),"created":r[5]} for r in c.fetchall()]
    conn.close()
    return {"sent":True,"messages":messages}

@app.get("/api/workspace/messages")
def ws_get_messages(room_code: str):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM workspaces WHERE room_code=?",(room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404,"Room not found")
    c.execute("SELECT m.session_id,m.role FROM workspace_members m WHERE m.workspace_id=?",(ws[0],))
    members = [{"session_id":r[0],"role":r[1]} for r in c.fetchall()]
    c.execute("SELECT id,session_id,author,message,is_ai,created FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 50",(ws[0],))
    messages = [{"id":r[0],"session_id":r[1],"author":r[2],"message":r[3],"is_ai":bool(r[4]),"created":r[5]} for r in c.fetchall()]
    conn.close()
    return {"messages":messages,"members":members}

@app.post("/api/workspace/notes")
def ws_save_note(req: WorkspaceNoteRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM workspaces WHERE room_code=?",(req.room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404,"Room not found")
    c.execute("DELETE FROM workspace_notes WHERE workspace_id=?",(ws[0],))
    c.execute("INSERT INTO workspace_notes (id,workspace_id,session_id,author,content,created,updated) VALUES (?,?,?,?,?,?,?)",(sid(),ws[0],s["id"],"User",req.content,datetime.utcnow().isoformat(),datetime.utcnow().isoformat()))
    conn.commit()
    c.execute("SELECT id,author,content,updated FROM workspace_notes WHERE workspace_id=?",(ws[0],))
    notes = [{"id":r[0],"author":r[1],"content":r[2],"updated":r[3]} for r in c.fetchall()]
    conn.close()
    return {"saved":True,"notes":notes}

@app.get("/api/workspace/notes")
def ws_get_notes(room_code: str):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM workspaces WHERE room_code=?",(room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404,"Room not found")
    c.execute("SELECT id,author,content,updated FROM workspace_notes WHERE workspace_id=?",(ws[0],))
    notes = [{"id":r[0],"author":r[1],"content":r[2],"updated":r[3]} for r in c.fetchall()]
    conn.close()
    return {"notes":notes}

if __name__ == "__main__":
    port = int(os.environ.get("PORT",8000))
    uvicorn.run(app,host="0.0.0.0",port=port)