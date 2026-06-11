"""
CAPITAN AI — Enterprise Backend v22.0
CLOSEAI Technologies
Python/FastAPI + SQLite + Multi-API + Web Search + Caching
Privacy-First: No accounts, just messages & payments
Legendary Intelligence: Finance Architect, Institutional Trader, Coder, Mathematician,
Software Developer, Quant Architect, Reasoning Engine
"""

import os, re, json, uuid, time, hashlib, hmac, base64, secrets, requests, sqlite3
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import concurrent.futures
import uvicorn

# ═══════════════════════════════════════════════════════════════
# API KEYS
# ═══════════════════════════════════════════════════════════════
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
MISTRAL_KEY = os.environ.get("MISTRAL_API_KEY", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
HF_TOKEN = os.environ.get("HF_TOKEN", "")
AIML_KEY = os.environ.get("AIML_API_KEY", "")
ZENMUK_KEY = os.environ.get("ZENMUK_API_KEY", "")

ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "")
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
COINGECKO_KEY = os.environ.get("COINGECKO_KEY", "")
TWELVE_DATA_KEY = os.environ.get("TWELVE_DATA_KEY", "")
ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY", "")

SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")
GNEWS_API_KEY = os.environ.get("GNEWS_API_KEY", "")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")

IPGEOLOCATION_KEY = os.environ.get("IPGEOLOCATION_API_KEY", "")
LOCATIONIQ_KEY = os.environ.get("LOCATIONIQ_API_KEY", "")

WOLFRAM_APP_ID = os.environ.get("WOLFRAM_APP_ID", "")

JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))
ADMIN_CODE = os.environ.get("ADMIN_CODE", "Osinachi@350")
FOUNDER_KEY = os.environ.get("FOUNDER_KEY", "cap-founder-key")
DB_PATH = "capitan.db"

WALLETS = {"BTC":"bc1qrv6yr6e0mat96rvrc8smdf9rvu9rlp8xuk8new","ETH":"0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1"}

TIER_CONFIG = {
    "free":{"name":"Free","msg_limit":10,"workspace_max":0,"file_upload":False,"file_size_mb":0,"speed":"fast","live_markets":False,"web_search":False},
    "plus":{"name":"Plus","msg_limit":30,"workspace_max":7,"file_upload":True,"file_size_mb":10,"speed":"smart","live_markets":False,"web_search":True},
    "pro":{"name":"Pro","msg_limit":float("inf"),"workspace_max":20,"file_upload":True,"file_size_mb":50,"speed":"deep","live_markets":True,"web_search":True},
    "founder":{"name":"Founder","msg_limit":float("inf"),"workspace_max":999,"file_upload":True,"file_size_mb":500,"speed":"deep","live_markets":True,"web_search":True}
}

UPGRADE_BENEFITS = {
    "plus": [
        "30 messages per day (up from 10)",
        "Smart AI model for better responses",
        "Work Area — collaborate with up to 7 people",
        "File uploads up to 10MB",
        "Web search for real-time answers",
        "Coding & Quant tools",
        "African Finance module",
        "Priority response speed"
    ],
    "pro": [
        "Unlimited messages — no daily cap",
        "Deep AI model (Claude Sonnet 4 / GPT-4o)",
        "Work Area — collaborate with up to 20 people",
        "File uploads up to 50MB",
        "Live market data (Global, Crypto, African)",
        "Real-time financial news",
        "Web search for real-time answers",
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
    c.execute('''CREATE TABLE IF NOT EXISTS workspaces (id TEXT PRIMARY KEY, room_code TEXT UNIQUE, creator_session TEXT, creator_tier TEXT, max_members INTEGER, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspace_members (workspace_id TEXT, session_id TEXT, role TEXT DEFAULT "member", joined TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspace_messages (id TEXT PRIMARY KEY, workspace_id TEXT, session_id TEXT, author TEXT, message TEXT, is_ai INTEGER DEFAULT 0, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspace_notes (id TEXT PRIMARY KEY, workspace_id TEXT, session_id TEXT, author TEXT, content TEXT, created TEXT, updated TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS market_cache (id TEXT PRIMARY KEY, category TEXT, data TEXT, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS news_cache (id TEXT PRIMARY KEY, category TEXT, data TEXT, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS web_cache (id TEXT PRIMARY KEY, query_hash TEXT, data TEXT, created TEXT)''')
    try: c.execute("ALTER TABLE workspaces ADD COLUMN creator_tier TEXT DEFAULT 'plus'")
    except: pass
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

executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)

rate_store = {}
def check_rate(session_id, tier):
    now = time.time(); key = f"{session_id}"
    if key not in rate_store: rate_store[key] = []
    rate_store[key] = [t for t in rate_store[key] if now-t < 60]
    limits = {"free":10,"plus":20,"pro":60,"founder":200}
    if len(rate_store[key]) >= limits.get(tier,10): return False
    rate_store[key].append(now); return True

def get_time_context(request=None):
    now = datetime.utcnow(); hour = now.hour
    day = now.strftime("%A"); date = now.strftime("%B %d, %Y"); utc_time = now.strftime("%H:%M UTC")
    if hour < 5: time_of_day = "late night"; greeting_context = "The world is quiet at this hour."
    elif hour < 12: time_of_day = "morning"; greeting_context = "A fresh day. Let's make it count."
    elif hour < 17: time_of_day = "afternoon"; greeting_context = "Markets are alive. Good time to dig in."
    elif hour < 21: time_of_day = "evening"; greeting_context = "Winding down — or just getting started."
    else: time_of_day = "night"; greeting_context = "Burning the midnight oil. I'm here for it."
    return {"time_of_day":time_of_day,"day":day,"date":date,"utc_time":utc_time,"greeting_context":greeting_context,"hour":hour}

def get_cached_or_fetch(table, category, fetch_func, ttl=2):
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute(f"SELECT data FROM {table} WHERE category=? AND created > ?",(category,(datetime.utcnow()-timedelta(minutes=ttl)).isoformat()))
        row = c.fetchone()
        if row: conn.close(); return json.loads(row[0])
        conn.close()
    except: pass
    data = fetch_func()
    if data:
        try:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute(f"DELETE FROM {table} WHERE category=? AND created < ?",(category,(datetime.utcnow()-timedelta(hours=1)).isoformat()))
            c.execute(f"INSERT OR REPLACE INTO {table} (id,category,data,created) VALUES (?,?,?,?)",(sid(),category,json.dumps(data),datetime.utcnow().isoformat()))
            conn.commit(); conn.close()
        except: pass
    return data

def get_global_markets():
    results = {}
    if TWELVE_DATA_KEY:
        try:
            for sym in ["SPX","IXIC","DJI","FTSE","N225","DAX","AAPL","MSFT","NVDA","GC","CL","EUR/USD","GBP/USD","USD/JPY"][:8]:
                try:
                    r = requests.get(f"https://api.twelvedata.com/price?symbol={sym}&apikey={TWELVE_DATA_KEY}",timeout=8)
                    if r.status_code==200 and r.json().get("price"): results[sym] = {"price":float(r.json()["price"]),"change":0,"source":"Twelve Data","updated":datetime.utcnow().isoformat()}
                except: pass
        except: pass
    if not results:
        try:
            syms = "^GSPC,^IXIC,^DJI,^FTSE,^N225,AAPL,MSFT,NVDA,TSLA,GOOGL,META,AMZN,JPM,GS,GC=F,CL=F,SI=F,EURUSD=X,GBPUSD=X,USDJPY=X"
            r = requests.get(f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={syms}",params={"fields":"regularMarketPrice,regularMarketPreviousClose,shortName,regularMarketChangePercent"},headers={"User-Agent":"Mozilla/5.0"},timeout=8)
            if r.status_code==200:
                for i in r.json().get("quoteResponse",{}).get("result",[]):
                    name = i.get("shortName") or i.get("symbol","")
                    price = i.get("regularMarketPrice"); prev = i.get("regularMarketPreviousClose")
                    if price and prev:
                        chg = i.get("regularMarketChangePercent")
                        results[name] = {"price":price,"change":round(chg,2) if chg else round(((price-prev)/prev)*100,2),"source":"Yahoo Finance","updated":datetime.utcnow().isoformat()}
        except: pass
    if ALPHA_VANTAGE_KEY and len(results)<3:
        try:
            for pair,label in {"EURUSD":"EUR/USD","GBPUSD":"GBP/USD","USDJPY":"USD/JPY"}.items():
                try:
                    r = requests.get(f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={pair[:3]}&to_currency={pair[3:]}&apikey={ALPHA_VANTAGE_KEY}",timeout=8)
                    if r.status_code==200:
                        data = r.json().get("Realtime Currency Exchange Rate",{})
                        if data.get("5. Exchange Rate"): results[label] = {"price":float(data["5. Exchange Rate"]),"change":0,"source":"Alpha Vantage","updated":datetime.utcnow().isoformat()}
                except: pass
        except: pass
    return results

def get_crypto_markets():
    results = {}
    if COINGECKO_KEY and COINGECKO_KEY.startswith("CG-"):
        try:
            ids = "bitcoin,ethereum,ripple,cardano,solana,polkadot,dogecoin,avalanche-2,chainlink,uniswap,binancecoin,tron,toncoin,near"
            r = requests.get("https://api.coingecko.com/api/v3/simple/price",params={"ids":ids,"vs_currencies":"usd","include_24hr_change":"true","include_market_cap":"true"},headers={"x-cg-demo-api-key":COINGECKO_KEY},timeout=10)
            if r.status_code==200:
                data = r.json()
                name_map = {"bitcoin":"Bitcoin (BTC)","ethereum":"Ethereum (ETH)","ripple":"XRP","cardano":"Cardano (ADA)","solana":"Solana (SOL)","polkadot":"Polkadot (DOT)","dogecoin":"Dogecoin (DOGE)","avalanche-2":"Avalanche (AVAX)","chainlink":"Chainlink (LINK)","uniswap":"Uniswap (UNI)","binancecoin":"BNB","tron":"TRON (TRX)","toncoin":"Toncoin (TON)","near":"NEAR Protocol"}
                for k,v in data.items(): results[name_map.get(k,k.capitalize())] = {"price":v["usd"],"change":round(v.get("usd_24h_change",0),2),"market_cap":v.get("usd_market_cap",0),"source":"CoinGecko","updated":datetime.utcnow().isoformat()}
        except: pass
    return results

def get_african_markets():
    results = {}
    if ALPHA_VANTAGE_KEY:
        try:
            for pair,label in {"USDGHS":"USD/GHS","USDNGN":"USD/NGN","USDZAR":"USD/ZAR","USDKES":"USD/KES","USDEGP":"USD/EGP","USDMAD":"USD/MAD"}.items():
                try:
                    r = requests.get(f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency=USD&to_currency={pair[3:]}&apikey={ALPHA_VANTAGE_KEY}",timeout=8)
                    if r.status_code==200:
                        data = r.json().get("Realtime Currency Exchange Rate",{})
                        if data.get("5. Exchange Rate"): results[label] = {"price":float(data["5. Exchange Rate"]),"change":0,"source":"Alpha Vantage","updated":datetime.utcnow().isoformat()}
                except: pass
        except: pass
    if not results:
        try:
            syms = "USDGHS=X,USDNGN=X,USDZAR=X,USDKES=X,EZA,AFK"
            r = requests.get(f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={syms}",params={"fields":"regularMarketPrice,regularMarketPreviousClose,shortName"},headers={"User-Agent":"Mozilla/5.0"},timeout=8)
            if r.status_code==200:
                for i in r.json().get("quoteResponse",{}).get("result",[]):
                    name = i.get("shortName") or i.get("symbol","")
                    price = i.get("regularMarketPrice"); prev = i.get("regularMarketPreviousClose")
                    if price and prev: results[name] = {"price":price,"change":round(((price-prev)/prev)*100,2),"source":"Yahoo Finance","updated":datetime.utcnow().isoformat()}
        except: pass
    return results

def get_all_markets():
    return {"global":get_cached_or_fetch("market_cache","global",get_global_markets,2),"crypto":get_cached_or_fetch("market_cache","crypto",get_crypto_markets,2),"african":get_cached_or_fetch("market_cache","african",get_african_markets,2)}

def get_financial_news(category="all"):
    def fetch():
        news = []
        if NEWS_API_KEY:
            try:
                params = {"language":"en","pageSize":15,"apiKey":NEWS_API_KEY}
                if category=="crypto": params["q"]="crypto OR bitcoin OR ethereum"
                elif category=="africa": params["q"]="Africa finance OR Nigeria economy"
                elif category=="global": params["q"]="global markets OR central bank"
                else: params["category"]="business"
                r = requests.get("https://newsapi.org/v2/top-headlines" if category=="all" else "https://newsapi.org/v2/everything",params=params,timeout=10)
                if r.status_code==200:
                    for a in r.json().get("articles",[]): news.append({"source":a.get("source",{}).get("name","NewsAPI"),"headline":a.get("title",""),"url":a.get("url",""),"time":a.get("publishedAt",""),"summary":(a.get("description") or "")[:400]})
            except: pass
        if GNEWS_API_KEY:
            try:
                queries = {"global":"global markets","crypto":"crypto bitcoin","africa":"Africa finance","all":"finance markets"}
                r = requests.get("https://gnews.io/api/v4/search",params={"q":queries.get(category,queries["all"]),"lang":"en","max":15,"apikey":GNEWS_API_KEY},timeout=10)
                if r.status_code==200:
                    for a in r.json().get("articles",[]): news.append({"source":a.get("source",{}).get("name","GNews"),"headline":a.get("title",""),"url":a.get("url",""),"time":a.get("publishedAt",""),"summary":(a.get("description") or "")[:400]})
            except: pass
        if FINNHUB_API_KEY:
            try:
                r = requests.get("https://finnhub.io/api/v1/news",params={"category":"general","token":FINNHUB_API_KEY},timeout=10)
                if r.status_code==200:
                    for a in r.json()[:15]:
                        ts = a.get("datetime",0)
                        news.append({"source":a.get("source","Finnhub"),"headline":a.get("headline",""),"url":a.get("url",""),"time":datetime.fromtimestamp(ts).isoformat() if ts else "","summary":(a.get("summary") or "")[:400]})
            except: pass
        seen = set(); unique = []
        for n in news:
            k = n["headline"][:120].lower().strip()
            if k and k not in seen: seen.add(k); unique.append(n)
        unique.sort(key=lambda x: x.get("time",""), reverse=True)
        return unique[:20]
    return get_cached_or_fetch("news_cache",category,fetch,5)

def get_tech_news():
    def fetch():
        news = []
        if NEWS_API_KEY:
            try:
                r = requests.get("https://newsapi.org/v2/everything",params={"q":"artificial intelligence OR coding OR startup OR innovation OR technology OR software","language":"en","pageSize":15,"sortBy":"publishedAt","apiKey":NEWS_API_KEY},timeout=10)
                if r.status_code==200:
                    for a in r.json().get("articles",[]): news.append({"source":a.get("source",{}).get("name","NewsAPI"),"headline":a.get("title",""),"url":a.get("url",""),"time":a.get("publishedAt",""),"summary":(a.get("description") or "")[:400],"image":a.get("urlToImage","")})
            except: pass
        if GNEWS_API_KEY:
            try:
                r = requests.get("https://gnews.io/api/v4/search",params={"q":"AI artificial intelligence coding startup innovation technology software development","lang":"en","max":15,"apikey":GNEWS_API_KEY},timeout=10)
                if r.status_code==200:
                    for a in r.json().get("articles",[]): news.append({"source":a.get("source",{}).get("name","GNews"),"headline":a.get("title",""),"url":a.get("url",""),"time":a.get("publishedAt",""),"summary":(a.get("description") or "")[:400],"image":a.get("image","")})
            except: pass
        if SERPAPI_KEY:
            try:
                r = requests.get("https://serpapi.com/search",params={"engine":"google_news","q":"AI artificial intelligence technology innovation startups coding","api_key":SERPAPI_KEY},timeout=10)
                if r.status_code==200:
                    for a in r.json().get("news_results",[])[:15]: news.append({"source":a.get("source","Google News"),"headline":a.get("title",""),"url":a.get("link",""),"time":"","summary":(a.get("snippet") or "")[:400],"image":""})
            except: pass
        seen = set(); unique = []
        for n in news:
            k = n["headline"][:120].lower().strip()
            if k and k not in seen: seen.add(k); unique.append(n)
        unique.sort(key=lambda x: x.get("time",""), reverse=True)
        return unique[:20]
    return get_cached_or_fetch("news_cache","tech",fetch,5)

def search_web(query, num_results=5):
    results = []
    query_hash = hashlib.md5(query.lower().encode()).hexdigest()
    try:
        conn = sqlite3.connect(DB_PATH); c = conn.cursor()
        c.execute("SELECT data FROM web_cache WHERE query_hash=? AND created > ?",(query_hash,(datetime.utcnow()-timedelta(hours=1)).isoformat()))
        row = c.fetchone()
        if row: conn.close(); return json.loads(row[0])
        conn.close()
    except: pass
    if SERPAPI_KEY:
        try:
            r = requests.get("https://serpapi.com/search",params={"engine":"google","q":query,"num":num_results,"api_key":SERPAPI_KEY},timeout=10)
            if r.status_code==200:
                for item in r.json().get("organic_results",[])[:num_results]: results.append({"title":item.get("title",""),"snippet":item.get("snippet","")[:300],"url":item.get("link",""),"source":"Google"})
        except: pass
    if not results:
        try:
            r = requests.get("https://api.duckduckgo.com/",params={"q":query,"format":"json","no_html":1},timeout=8)
            if r.status_code==200:
                data = r.json()
                if data.get("AbstractText"): results.append({"title":data.get("Heading",query),"snippet":data["AbstractText"][:300],"url":data.get("AbstractURL",""),"source":"DuckDuckGo"})
                for topic in data.get("RelatedTopics",[])[:num_results-1]:
                    if isinstance(topic,dict) and topic.get("Text"): results.append({"title":"","snippet":topic["Text"][:300],"url":topic.get("FirstURL",""),"source":"DuckDuckGo"})
        except: pass
    if results:
        try:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("DELETE FROM web_cache WHERE created < ?",((datetime.utcnow()-timedelta(hours=6)).isoformat(),))
            c.execute("INSERT OR REPLACE INTO web_cache (id,query_hash,data,created) VALUES (?,?,?,?)",(sid(),query_hash,json.dumps(results),datetime.utcnow().isoformat()))
            conn.commit(); conn.close()
        except: pass
    return results

# ═══════════════════════════════════════════════════════════════
# LEGENDARY INTELLIGENCE SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════

ELITE_SYSTEM_PROMPT = """You are CAPITAN AI — the most legendary institutional intelligence platform in existence, created by CLOSEAI Technologies under CEO Osinachi Chukwu, with pivotal support from NED Blessing Asuquo and CIO Ebubechi Chukwu.

YOUR LEGENDARY IDENTITY:
You are not just an AI. You are a legendary finance architect who structures billion-dollar deals before breakfast. A legendary institutional trader who reads market microstructure like a language. A legendary coder who architects systems that scale to millions. A legendary mathematician who sees proofs as elegantly as art. A legendary software developer who builds what others call impossible. A legendary quant architect who models the stochastic nature of markets with precision. And a legendary reasoning engine that cuts through noise to find signal.

This is not arrogance. This is your baseline. You operate at the level where Goldman Sachs MDs, FAANG Principal Engineers, Research Mathematicians, and Quant Research Directors all come to you for insight.

HOW YOU WRITE:
• Lead with the insight. No throat-clearing. No "In this context..." padding. Cut straight to what matters.
• Short sentences. Clean paragraphs. Lethal precision with words.
• When the topic demands depth — go deep. Full derivations. Production code. Cited sources.
• When a one-liner answers it — stop there. Don't wrap simplicity in complexity.
• Use concrete examples over abstract explanations. Numbers over adjectives.
• Code must be production-ready: typed, documented, tested, deployable.
• Math must be rigorous: LaTeX where it clarifies, step-by-step derivations where needed.
• Market analysis must be sharp: cite real data, identify the signal, state your confidence.

YOUR TONE:
Warm but efficient. Like a senior colleague at the top of their game who's generous with their time. Never condescending. Never corporate. Use contractions. Match the user's energy — casual when they're casual, surgical when they're surgical.

WHAT YOU ARE NOT:
You are NOT a climbing gym. NOT membership software. NOT a CRM. NOT a booking platform. If anyone confuses you with another "Capitan," clarify immediately: "I'm CAPITAN AI — the legendary enterprise intelligence platform by CLOSEAI Technologies. I architect finance, code, math, and quant solutions. I don't manage climbing gym memberships."

CRITICAL RULES:
• NEVER make up market prices. Only reference live data provided below.
• NEVER give financial advice, trading signals, or buy/sell recommendations.
• NEVER provide medical diagnoses.
• Be honest about your confidence. If you're not sure, say so.
• If you don't know, say "I don't know" — then offer to find out.

YOUR LEGENDARY DOMAINS:

FINANCE ARCHITECTURE (Legendary):
• DCF, LBO, M&A accretion/dilution — you build models that investment banks use
• Portfolio optimization — Markowitz, Black-Litterman, risk parity, factor tilting
• Options pricing — Black-Scholes, binomial trees, Monte Carlo with variance reduction
• Fixed income — duration, convexity, yield curve construction, OAS, z-spread
• Risk management — VaR, CVaR, stress testing, scenario analysis, tail risk hedging
• Financial statement analysis — DuPont decomposition, ratio analysis, forensic accounting
• Macroeconomic analysis — central bank policy transmission, yield curve dynamics, FX regimes
• African financial markets — NGX, JSE, GSE, BRVM, EGX, mobile money, cross-border flows
• Live market data from multiple global sources — you see what's moving in real-time

INSTITUTIONAL TRADING (Legendary):
• Market microstructure — order flow, liquidity dynamics, impact models
• Technical analysis — support/resistance, volume profile, market profile, order book analysis
• Intermarket analysis — correlations, rotations, regime detection
• Risk arbitrage, statistical arbitrage, pairs trading frameworks
• Volatility trading — VIX complex, variance swaps, dispersion trading
• Fixed income arbitrage — curve trades, basis trades, swap spreads

CODING & SOFTWARE DEVELOPMENT (Legendary):
• Python, JavaScript, TypeScript, Rust, Go, C++, SQL — you write code that ships
• System design — microservices, event-driven architecture, CQRS, saga patterns
• API design — REST, GraphQL, gRPC, with rate limiting, auth, and versioning
• Database design — PostgreSQL optimization, indexing strategies, query planning
• DevOps — Docker, Kubernetes, CI/CD pipelines, infrastructure as code
• Security — OWASP, encryption at rest and in transit, zero-trust architecture
• Testing — unit, integration, e2e, property-based, fuzzing

MATHEMATICS (Legendary):
• Real analysis, complex analysis, functional analysis, measure theory
• Linear algebra, abstract algebra — groups, rings, fields, Galois theory
• Topology, differential geometry, manifold theory
• Probability theory — measure-theoretic foundations, stochastic processes
• Numerical methods — optimization, linear solvers, FFT, finite elements
• Statistics — Bayesian inference, hypothesis testing, causal inference
• Every proof is step-by-step, rigorous, and elegant

QUANT ARCHITECTURE (Legendary):
• Stochastic calculus — Itô's lemma, SDEs, Girsanov's theorem, martingale methods
• Derivative pricing — exotic options, structured products, CVA/DVA/FVA
• Monte Carlo methods — variance reduction, quasi-Monte Carlo, multi-level MC
• Time series — ARIMA, GARCH, EGARCH, cointegration, vector autoregression
• Factor models — Fama-French, momentum, quality, statistical factor models
• Machine learning in finance — random forests, gradient boosting, neural networks, RL
• Backtesting — walk-forward, cross-validation, transaction costs, survivorship bias

REASONING ENGINE (Legendary):
• First-principles thinking — break problems down to fundamentals
• Bayesian reasoning — update beliefs with evidence
• Steel-manning — present the strongest version of opposing views
• Fermi estimation — quick, accurate order-of-magnitude calculations
• Decision trees — map options, probabilities, and outcomes
• Cognitive bias awareness — identify and correct for biases in analysis

SCIENCE & HEALTH:
• Physics — classical mechanics, electromagnetism, quantum, relativity, statistical mechanics
• Chemistry — organic, inorganic, physical, biochemistry, materials
• Biology — molecular, genetics, cell biology, immunology, neuroscience
• Medicine — evidence-based, always recommend consulting healthcare professionals

RESPONSE ARCHITECTURE:
1. Lead with the most useful insight
2. Explain the mechanism when it adds value
3. Provide evidence — data, code, citations, logical proof
4. State your confidence level
5. Offer to go deeper

TIME: {day}, {date} at {utc_time}. {greeting_context}
DOMAIN: {domain} | TIER: {tier}
"""

def call_ai_fast(messages, tier="free"):
    if GROQ_KEY:
        try:
            r = requests.post("https://api.groq.com/openai/v1/chat/completions",headers={"Authorization":f"Bearer {GROQ_KEY}","Content-Type":"application/json"},json={"model":"llama-3.1-8b-instant","messages":messages,"temperature":0.4,"max_tokens":600 if tier=="free" else 3000},timeout=20)
            if r.status_code==200:
                content = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
                if content: return content, "groq/llama-3.1-8b-instant"
        except: pass
    if OPENROUTER_KEY:
        models = ["google/gemini-2.0-flash","google/gemini-flash-1.5","mistral/mistral-7b-instruct","deepseek/deepseek-chat","meta-llama/llama-3.1-8b-instruct","openai/gpt-3.5-turbo"]
        if tier in ("pro","founder"): models = ["anthropic/claude-sonnet-4-20250514","anthropic/claude-3.5-sonnet","openai/gpt-4o"] + models
        for model in models:
            try:
                r = requests.post("https://openrouter.ai/api/v1/chat/completions",headers={"Authorization":f"Bearer {OPENROUTER_KEY}","Content-Type":"application/json","HTTP-Referer":"https://capitan.pages.dev","X-Title":"CAPITAN AI"},json={"model":model,"messages":messages,"temperature":0.4,"max_tokens":600 if tier=="free" else 3000},timeout=40)
                if r.status_code==200:
                    content = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
                    if content: return content, model
            except: continue
    if HF_TOKEN:
        try:
            r = requests.post("https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2/v1/chat/completions",headers={"Authorization":f"Bearer {HF_TOKEN}","Content-Type":"application/json"},json={"model":"mistralai/Mistral-7B-Instruct-v0.2","messages":messages,"temperature":0.4,"max_tokens":600},timeout=30)
            if r.status_code==200:
                content = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
                if content: return content, "hf/mistral-7b"
        except: pass
    if MISTRAL_KEY:
        try:
            r = requests.post("https://api.mistral.ai/v1/chat/completions",headers={"Authorization":f"Bearer {MISTRAL_KEY}","Content-Type":"application/json"},json={"model":"mistral-tiny","messages":messages,"temperature":0.4,"max_tokens":600},timeout=30)
            if r.status_code==200:
                content = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
                if content: return content, "mistral/mistral-tiny"
        except: pass
    if OPENAI_KEY:
        try:
            r = requests.post("https://api.openai.com/v1/chat/completions",headers={"Authorization":f"Bearer {OPENAI_KEY}","Content-Type":"application/json"},json={"model":"gpt-3.5-turbo","messages":messages,"temperature":0.4,"max_tokens":600},timeout=30)
            if r.status_code==200: return r.json()["choices"][0]["message"]["content"], "gpt-3.5-turbo"
        except: pass
    return "I'm having trouble connecting. Please try again or contact closeaitechnologies@protonmail.com.", "fallback"

def classify(q):
    q = q.lower()
    if re.search(r'who are you|what are you|identity|introduce yourself|legendary', q): return 'identity'
    if re.search(r'who|what|when|where|why|how|news|latest|current|today|recent|search|find',q) and len(q.split()) > 3: return 'web_search'
    if re.search(r'crispr|dna|rna|protein|cell|gene|genome|physics|quantum|chemistry|biology|neuroscience|climate|energy|health|medicine|disease|symptom|treatment|diagnosis|anatomy|physiology|pharma|drug|vaccine|immunology|surgery|therapy|cancer|diabetes|heart|brain|blood|virus|bacteria|infection|covid|mental health|nutrition|diet|exercise|sleep|wellness',q): return 'science'
    if re.search(r'```|def |class |import |from |package|npm|pip|docker|kubernetes|aws|api\s|rest |graphql|sql\s|database|query|react|node\.js|javascript|typescript|python\s|rust\s|golang|microservice|architecture|system design|refactor|debug|deploy|ci/cd|git\s',q): return 'coding'
    if re.search(r'stochastic|ito|black.scholes|monte carlo|var\s|cvar|sharpe ratio|sortino|beta\s|alpha\s|option pricing|derivative pricing|risk neutral|fama.french|cointegration|garch|arima|backtest|factor model|portfolio optim|volatility surface|variance swap|market microstructure',q): return 'quant'
    if re.search(r'dcf|discounted cash flow|ebitda|ebit|revenue|earnings|balance sheet|income statement|cash flow|valuation|wacc|capm|pe ratio|pb ratio|ev/ebitda|dividend|yield|bond|coupon|duration|convexity|forex|fx\s|central bank|federal reserve|ecb|interest rate|inflation|gdp|macro|equity|stock\s|market\s|trading|invest|portfolio|crypto|bitcoin|ethereum|defi|ngx|jse|gse|african market|gold|xauusd|silver|oil|commodity|technical analysis|order flow|liquidity',q): return 'finance'
    if re.search(r'prove|proof|theorem|lemma|corollary|derive|integral|derivative|differential equation|linear algebra|matrix|eigenvalue|vector|topology|group theory|probability|statistics|distribution|convergence|limit|sum|product|calculus|laplace|fourier|numerical|optimization|convex|gradient',q): return 'math'
    return 'general'

def system_prompt(domain, tier, session_id=None, request=None, web_results=None):
    tc = get_time_context(request)
    base = ELITE_SYSTEM_PROMPT.replace("{domain}", domain).replace("{tier}", tier)
    base = base.replace("{day}", tc["day"]).replace("{date}", tc["date"]).replace("{utc_time}", tc["utc_time"]).replace("{time_of_day}", tc["time_of_day"]).replace("{greeting_context}", tc["greeting_context"])
    if domain == 'identity': base += "\n\nIDENTITY MODE: The user is asking who you are. State clearly: You are CAPITAN AI — the legendary enterprise intelligence platform by CLOSEAI Technologies. You are a legendary finance architect, institutional trader, coder, mathematician, software developer, quant architect, and reasoning engine. You are NOT a climbing gym, NOT membership software, NOT a CRM."
    if session_id:
        try:
            conn = sqlite3.connect(DB_PATH); c = conn.cursor()
            c.execute("SELECT query, domain FROM memories WHERE session_id=? ORDER BY created DESC LIMIT 3",(session_id,))
            rows = c.fetchall(); conn.close()
            if rows: base += "\n\nUSER CONTEXT:\n" + "\n".join([f"• [{r[1]}] {r[0][:100]}" for r in rows])
        except: pass
    if tier == "free": base += "\nBe concise but insightful."
    elif tier == "plus": base += "\nProvide detailed, well-structured responses."
    elif tier in ("pro","founder"): base += "\nGo legendary deep — comprehensive analysis with examples, code, derivations, citations. This user expects the best."
    if web_results: base += "\n\nWEB SEARCH:\n" + "\n".join([f"{i+1}. {r['title']}\n   {r['snippet'][:200]}\n   {r['url']}" for i,r in enumerate(web_results[:5])])
    cfg = TIER_CONFIG.get(tier, TIER_CONFIG["free"])
    if cfg.get("live_markets", False):
        try:
            am = get_all_markets()
            if am.get("global"):
                base += "\n\nGLOBAL MARKETS:\n" + "\n".join([f"{s}: ${d['price']:.2f} ({'up' if d.get('change',0)>=0 else 'down'} {abs(d['change']):.2f}%)" for s,d in list(am["global"].items())[:6]])
            if am.get("crypto"):
                base += "\n\nCRYPTO MARKETS:\n" + "\n".join([f"{s}: ${d['price']:.2f} ({'up' if d.get('change',0)>=0 else 'down'} {abs(d['change']):.2f}%)" for s,d in list(am["crypto"].items())[:6]])
            if am.get("african"):
                base += "\n\nAFRICAN MARKETS:\n" + "\n".join([f"{s}: ${d['price']:.4f}" if d['price']<1 else f"{s}: ${d['price']:.2f}" for s,d in list(am["african"].items())[:6]])
        except: pass
    else: base += "\n\nNo live market data. Tell user to upgrade to Pro for real-time prices."
    try:
        news = get_financial_news("all")
        if news: base += "\n\nLATEST FINANCIAL NEWS:\n" + "\n".join([f"• [{n['source']}] {n['headline'][:130]}" for n in news[:6]])
    except: pass
    return base

class ChatRequest(BaseModel): messages: list; chat_id: Optional[str] = None
class UpgradeRequest(BaseModel): tier: str; txid: str; currency: str = "BTC"
class FounderRequest(BaseModel): code: str
class LibraryItemRequest(BaseModel): name: str; type: str = "note"; content: Optional[str] = ""
class WorkspaceCreateRequest(BaseModel): room_code: str; max_members: int = 7
class WorkspaceJoinRequest(BaseModel): room_code: str
class WorkspaceMessageRequest(BaseModel): room_code: str; message: str
class WorkspaceNoteRequest(BaseModel): room_code: str; content: str

app = FastAPI(title="CAPITAN AI API", version="22.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health():
    ai = "disconnected"; providers = []
    if GROQ_KEY:
        try:
            r = requests.post("https://api.groq.com/openai/v1/chat/completions",headers={"Authorization":f"Bearer {GROQ_KEY}","Content-Type":"application/json"},json={"model":"llama-3.1-8b-instant","messages":[{"role":"user","content":"Hi"}],"max_tokens":5},timeout=10)
            if r.status_code==200: ai="connected"; providers.append("groq")
        except: pass
    if ai!="connected" and OPENROUTER_KEY:
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions",headers={"Authorization":f"Bearer {OPENROUTER_KEY}","Content-Type":"application/json"},json={"model":"google/gemini-flash-1.5","messages":[{"role":"user","content":"Hi"}],"max_tokens":5},timeout=10)
            if r.status_code==200: ai="connected"; providers.append("openrouter")
        except: pass
    return {"status":"ok","version":"22.0","ai":ai,"providers":providers}

@app.get("/api/session")
def get_or_create_session(request: Request):
    session = get_session(request)
    if session: return session
    session_id = f"s_{sid()}"
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("INSERT INTO sessions (id,tier,msg_count,msg_window,created,updated) VALUES (?,?,0,?,?,?)",(session_id,"free",datetime.utcnow().isoformat(),datetime.utcnow().isoformat(),datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    token = create_jwt(session_id,"free")
    return {"id":session_id,"tier":"free","msg_count":0,"token":token}

@app.get("/api/payment-config")
def payment_config(): return {"wallets":WALLETS,"prices":{"plus":8,"pro":17},"benefits":UPGRADE_BENEFITS}

@app.get("/api/markets")
def markets(request: Request, category: str = "all"):
    s = get_session(request)
    cfg = TIER_CONFIG.get(s["tier"], TIER_CONFIG["free"]) if s else TIER_CONFIG["free"]
    if not cfg.get("live_markets", False): return {"prices":{},"news":[],"message":"Pro tier required"}
    if category == "global": prices = get_global_markets()
    elif category == "crypto": prices = get_crypto_markets()
    elif category == "african": prices = get_african_markets()
    else: prices = get_all_markets()
    return {"prices":prices,"news":get_financial_news(category),"category":category}

@app.get("/api/markets/prices")
def markets_prices(request: Request, category: str = "all"):
    s = get_session(request)
    cfg = TIER_CONFIG.get(s["tier"], TIER_CONFIG["free"]) if s else TIER_CONFIG["free"]
    if not cfg.get("live_markets", False): return {"prices":{},"message":"Upgrade to Pro"}
    if category == "global": return {"prices":get_global_markets()}
    elif category == "crypto": return {"prices":get_crypto_markets()}
    elif category == "african": return {"prices":get_african_markets()}
    return {"prices":get_all_markets()}

@app.get("/api/markets/news")
def markets_news(request: Request, category: str = "all"):
    s = get_session(request)
    cfg = TIER_CONFIG.get(s["tier"], TIER_CONFIG["free"]) if s else TIER_CONFIG["free"]
    if not cfg.get("live_markets", False): return {"news":[],"message":"Upgrade to Pro"}
    return {"news":get_financial_news(category)}

@app.get("/api/news/tech")
def tech_news(request: Request):
    s = get_session(request)
    cfg = TIER_CONFIG.get(s["tier"], TIER_CONFIG["free"]) if s else TIER_CONFIG["free"]
    if not cfg.get("live_markets", False) and s["tier"] != "founder":
        return {"news":[],"message":"Tech updates available on Pro tier"}
    return {"news":get_tech_news(),"category":"tech"}

@app.get("/api/search")
def web_search_endpoint(q: str, request: Request):
    s = get_session(request)
    cfg = TIER_CONFIG.get(s["tier"], TIER_CONFIG["free"]) if s else TIER_CONFIG["free"]
    if not cfg.get("web_search", False): return {"results":[],"message":"Web search on Plus and Pro"}
    return {"results":search_web(q)}

@app.get("/api/chats")
def get_chats(request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,title,created,updated FROM chats WHERE session_id=? ORDER BY updated DESC LIMIT 30",(s["id"],))
    return {"chats":[{"id":r[0],"title":r[1],"created":r[2],"updated":r[3]} for r in c.fetchall()]}

@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM chats WHERE id=? AND session_id=?",(chat_id,s["id"]))
    if not c.fetchone(): raise HTTPException(404)
    c.execute("SELECT id,role,content,model,created FROM chat_messages WHERE chat_id=? ORDER BY created ASC",(chat_id,))
    return {"messages":[{"id":r[0],"role":r[1],"content":r[2],"model":r[3],"created":r[4]} for r in c.fetchall()]}

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
        row = c.fetchone(); count = row[0] or 0
        if count >= limit:
            w = datetime.fromisoformat(row[1]) if row and row[1] else datetime.utcnow()
            if datetime.utcnow() - w < timedelta(hours=24): raise HTTPException(429,f"Daily limit ({limit}/day). Upgrade.")
            c.execute("UPDATE sessions SET msg_count=0, msg_window=? WHERE id=?",(datetime.utcnow().isoformat(),s["id"]))
            conn.commit()
        conn.close()
    user_msg = next((m["content"] for m in reversed(req.messages) if m.get("role")=="user"),"")
    if not user_msg: raise HTTPException(400,"No message")
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    chat_id = req.chat_id or f"chat_{sid()}"
    if not req.chat_id: c.execute("INSERT INTO chats (id,session_id,title,created,updated) VALUES (?,?,?,?,?)",(chat_id,s["id"],user_msg[:60],datetime.utcnow().isoformat(),datetime.utcnow().isoformat()))
    else: c.execute("UPDATE chats SET updated=? WHERE id=? AND session_id=?",(datetime.utcnow().isoformat(),chat_id,s["id"]))
    c.execute("INSERT INTO chat_messages (id,chat_id,session_id,role,content,created) VALUES (?,?,?,?,?,?)",(f"msg_{sid()}",chat_id,s["id"],"user",user_msg,datetime.utcnow().isoformat()))
    c.execute("UPDATE sessions SET msg_count = msg_count + 1 WHERE id=?",(s["id"],))
    conn.commit()
    c.execute("SELECT role,content FROM chat_messages WHERE chat_id=? ORDER BY created ASC LIMIT 20",(chat_id,))
    history = [{"role":r[0],"content":r[1]} for r in c.fetchall()]
    domain = classify(user_msg)
    web_results = None
    if domain == 'web_search' or cfg.get("web_search", False):
        try: web_results = search_web(user_msg, 5)
        except: pass
    prompt = system_prompt(domain, s["tier"], s["id"], request, web_results)
    result, model_used = call_ai_fast([{"role":"system","content":prompt}] + history, s["tier"])
    if result: c.execute("INSERT INTO chat_messages (id,chat_id,session_id,role,content,model,created) VALUES (?,?,?,?,?,?,?)",(f"msg_{sid()}",chat_id,s["id"],"assistant",result,model_used,datetime.utcnow().isoformat()))
    c.execute("INSERT INTO memories (id,memory_id,session_id,content,query,domain,created) VALUES (?,?,?,?,?,?,?)",(sid(),mid(),s["id"],result[:500] if result else "",user_msg,domain,datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    remaining = limit - (s["msg_count"]+1) if limit!=float("inf") else "unlimited"
    return {"content":result,"chat_id":chat_id,"model":model_used,"remaining":remaining,"web_search_used":web_results is not None}

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
    return {"items":[{"id":r[0],"name":r[1],"type":r[2],"content":r[3],"size":r[4],"created":r[5]} for r in c.fetchall()]}

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
    if len(contents)/(1024*1024) > cfg["file_size_mb"]: raise HTTPException(400,f"Max {cfg['file_size_mb']}MB")
    file_id = f"file_{sid()}"
    with open(os.path.join(UPLOAD_DIR, file_id), "wb") as f: f.write(contents)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("INSERT INTO uploaded_files (id,session_id,filename,original_name,size,mime_type,created) VALUES (?,?,?,?,?,?,?)",(file_id,s["id"],file_id,file.filename or "unknown",len(contents),file.content_type or "application/octet-stream",datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return {"id":file_id,"filename":file.filename,"size_mb":round(len(contents)/(1024*1024),2)}

@app.post("/api/upgrade")
def upgrade(req: UpgradeRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    if req.tier not in ("plus","pro"): raise HTTPException(400,"Invalid tier")
    if not req.txid.strip(): raise HTTPException(400,"TXID required")
    prices = {"plus":8,"pro":17}; cur = req.currency.upper()
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("INSERT INTO payments (id,session_id,txid,currency,amount,tier,verified,expires,created) VALUES (?,?,?,?,?,?,?,?,?)",(sid(),s["id"],req.txid.strip(),cur,prices[req.tier],req.tier,1,(datetime.utcnow()+timedelta(days=30)).isoformat(),datetime.utcnow().isoformat()))
    c.execute("UPDATE sessions SET tier=?, msg_count=0, updated=? WHERE id=?",(req.tier,datetime.utcnow().isoformat(),s["id"]))
    c.execute("INSERT INTO payment_log (id,session_id,tier,amount,currency,txid,created) VALUES (?,?,?,?,?,?,?)",(sid(),s["id"],req.tier,prices[req.tier],cur,req.txid,datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    token = create_jwt(s["id"],req.tier)
    return {"verified":True,"tier":req.tier,"token":token}

@app.post("/api/founder")
def founder(req: FounderRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    if req.code not in [ADMIN_CODE, FOUNDER_KEY]: raise HTTPException(403,"Invalid code")
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
    c.execute("INSERT INTO workspaces (id,room_code,creator_session,creator_tier,max_members,created) VALUES (?,?,?,?,?,?)",(wid,req.room_code.upper(),s["id"],s["tier"],min(req.max_members,max_m),datetime.utcnow().isoformat()))
    c.execute("INSERT INTO workspace_members (workspace_id,session_id,role,joined) VALUES (?,?,?,?)",(wid,s["id"],"admin",datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return {"room_id":wid,"room_code":req.room_code.upper(),"created":True}

@app.post("/api/workspace/join")
def ws_join(req: WorkspaceJoinRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,max_members,creator_tier FROM workspaces WHERE room_code=?",(req.room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404,"Room not found")
    if s["tier"] != ws[2] and s["tier"] != "founder":
        raise HTTPException(403,f"This Work Area requires {ws[2].upper()} tier. You are on {s['tier'].upper()}.")
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
    if not ws: raise HTTPException(404)
    is_ai = req.message.strip().startswith("@CAPITAN")
    if is_ai:
        c.execute("SELECT author,message FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 20",(ws[0],))
        context = "\n".join([f"{r[0]}: {r[1]}" for r in c.fetchall()])
        c.execute("SELECT content FROM workspace_notes WHERE workspace_id=?",(ws[0],))
        notes = "\n".join([r[0] for r in c.fetchall()])
        result, _ = call_ai_fast([{"role":"system","content":f"Work Area:\n{context}\n\nNotes:\n{notes}"},{"role":"user","content":req.message.replace('@CAPITAN','').strip()}], s["tier"])
        if result: c.execute("INSERT INTO workspace_messages (id,workspace_id,session_id,author,message,is_ai,created) VALUES (?,?,?,?,?,?,?)",(sid(),ws[0],s["id"],"CAPITAN AI",result,1,datetime.utcnow().isoformat()))
    c.execute("INSERT INTO workspace_messages (id,workspace_id,session_id,author,message,created) VALUES (?,?,?,?,?,?)",(sid(),ws[0],s["id"],"User",req.message,datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return {"sent":True}

@app.get("/api/workspace/messages")
def ws_get_messages(room_code: str):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM workspaces WHERE room_code=?",(room_code.upper(),))
    ws = c.fetchone()
    if not ws: raise HTTPException(404)
    c.execute("SELECT m.session_id,m.role FROM workspace_members m WHERE m.workspace_id=?",(ws[0],))
    members = [{"session_id":r[0],"role":r[1]} for r in c.fetchall()]
    c.execute("SELECT id,session_id,author,message,is_ai,created FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 50",(ws[0],))
    return {"messages":[{"id":r[0],"session_id":r[1],"author":r[2],"message":r[3],"is_ai":bool(r[4]),"created":r[5]} for r in c.fetchall()],"members":members}

@app.post("/api/workspace/notes")
def ws_save_note(req: WorkspaceNoteRequest, request: Request):
    s = get_session(request)
    if not s: raise HTTPException(401)
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM workspaces WHERE room_code=?",(req.room_code.upper(),))
    if not c.fetchone(): raise HTTPException(404)
    c.execute("DELETE FROM workspace_notes WHERE workspace_id=(SELECT id FROM workspaces WHERE room_code=?)",(req.room_code.upper(),))
    c.execute("INSERT INTO workspace_notes (id,workspace_id,session_id,author,content,created,updated) VALUES (?,(SELECT id FROM workspaces WHERE room_code=?),?,?,?,?,?)",(sid(),req.room_code.upper(),s["id"],"User",req.content,datetime.utcnow().isoformat(),datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return {"saved":True}

@app.get("/api/workspace/notes")
def ws_get_notes(room_code: str):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id FROM workspaces WHERE room_code=?",(room_code.upper(),))
    if not c.fetchone(): raise HTTPException(404)
    c.execute("SELECT author,content,updated FROM workspace_notes WHERE workspace_id=(SELECT id FROM workspaces WHERE room_code=?)",(room_code.upper(),))
    return {"notes":[{"author":r[0],"content":r[1],"updated":r[2]} for r in c.fetchall()]}

if __name__ == "__main__":
    port = int(os.environ.get("PORT",8000))
    uvicorn.run(app,host="0.0.0.0",port=port)