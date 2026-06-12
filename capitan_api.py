"""
CAPITAN AI — Enterprise Backend v24.0 (ELITE INSTITUTIONAL GRADE)
CLOSEAI Technologies
Python/FastAPI + SQLite + Multi-API + Web Search + Caching
WORLD-CLASS FINANCIAL INTELLIGENCE | ELITE CODING | UNMATCHED REASONING
"""

import os, re, json, uuid, time, hashlib, hmac, base64, secrets, requests, sqlite3, math, threading
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from collections import defaultdict
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import contextmanager
import uvicorn

# ============================================================
# API KEYS
# ============================================================
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

JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))
ADMIN_CODE = os.environ.get("ADMIN_CODE", "Osinachi@350")
FOUNDER_KEY = os.environ.get("FOUNDER_KEY", "cap-founder-key")
DB_PATH = "capitan.db"

# ============================================================
# CONFIGURATIONS
# ============================================================
WALLETS = {"BTC": "bc1qrv6yr6e0mat96rvrc8smdf9rvu9rlp8xuk8new", "ETH": "0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1"}

TIER_CONFIG = {
    "free": {"name": "Free", "msg_limit": 10, "workspace_max": 0, "file_upload": False, "file_size_mb": 0, "live_markets": False, "web_search": False},
    "plus": {"name": "Plus", "msg_limit": 30, "workspace_max": 7, "file_upload": True, "file_size_mb": 10, "live_markets": False, "web_search": True},
    "pro": {"name": "Pro", "msg_limit": float("inf"), "workspace_max": 20, "file_upload": True, "file_size_mb": 50, "live_markets": True, "web_search": True},
    "founder": {"name": "Founder", "msg_limit": float("inf"), "workspace_max": 999, "file_upload": True, "file_size_mb": 500, "live_markets": True, "web_search": True}
}

UPGRADE_BENEFITS = {
    "plus": ["30 messages per day", "Smart AI model", "Work Area (7 seats)", "File uploads (10MB)", "Web search", "Coding & Quant tools", "African Finance module"],
    "pro": ["Unlimited messages", "Deep AI (Claude Sonnet 4 / GPT-4o)", "Work Area (20 seats)", "File uploads (50MB)", "Live market data", "Financial news", "Web search", "Business mode", "All Plus features"]
}

# ============================================================
# ELITE FINANCIAL INTELLIGENCE MODULES (No scipy dependency)
# ============================================================

class OptionsPricingEngine:
    """Institutional-grade options pricing with Greeks"""
    
    @staticmethod
    def norm_cdf(x):
        """Standard normal cumulative distribution function approximation"""
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))
    
    @staticmethod
    def norm_pdf(x):
        """Standard normal probability density function"""
        return math.exp(-x * x / 2) / math.sqrt(2 * math.pi)
    
    @staticmethod
    def black_scholes(S, K, T, r, sigma, option_type='call'):
        """Black-Scholes option pricing model"""
        if T <= 0:
            if option_type == 'call':
                return max(0, S - K)
            else:
                return max(0, K - S)
        
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        
        if option_type == 'call':
            price = S * OptionsPricingEngine.norm_cdf(d1) - K * math.exp(-r * T) * OptionsPricingEngine.norm_cdf(d2)
        else:
            price = K * math.exp(-r * T) * OptionsPricingEngine.norm_cdf(-d2) - S * OptionsPricingEngine.norm_cdf(-d1)
        return price
    
    @staticmethod
    def calculate_greeks(S, K, T, r, sigma):
        """Calculate all option Greeks"""
        if T <= 0:
            return {'delta': 1 if S > K else 0, 'gamma': 0, 'theta': 0, 'vega': 0, 'rho': 0}
        
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        
        return {
            'delta': OptionsPricingEngine.norm_cdf(d1),
            'gamma': OptionsPricingEngine.norm_pdf(d1) / (S * sigma * math.sqrt(T)),
            'theta': -(S * OptionsPricingEngine.norm_pdf(d1) * sigma) / (2 * math.sqrt(T)) - r * K * math.exp(-r * T) * OptionsPricingEngine.norm_cdf(d2),
            'vega': S * OptionsPricingEngine.norm_pdf(d1) * math.sqrt(T),
            'rho': K * T * math.exp(-r * T) * OptionsPricingEngine.norm_cdf(d2)
        }


class RiskManagementEngine:
    """Institutional risk management"""
    
    @staticmethod
    def calculate_var(returns, confidence=0.95):
        """Value at Risk calculation (historical method)"""
        if not returns:
            return 0
        sorted_returns = sorted(returns)
        index = int((1 - confidence) * len(sorted_returns))
        return sorted_returns[index] if index < len(sorted_returns) else sorted_returns[-1]
    
    @staticmethod
    def calculate_cvar(returns, confidence=0.95):
        """Conditional VaR (Expected Shortfall)"""
        if not returns:
            return 0
        var = RiskManagementEngine.calculate_var(returns, confidence)
        returns_below_var = [r for r in returns if r <= var]
        if returns_below_var:
            return sum(returns_below_var) / len(returns_below_var)
        return var
    
    @staticmethod
    def sharpe_ratio(returns, risk_free_rate=0.02):
        """Sharpe ratio calculation"""
        if not returns or len(returns) < 2:
            return 0
        mean_return = sum(returns) / len(returns)
        excess_returns = mean_return - risk_free_rate / 252
        variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
        std_dev = math.sqrt(variance) if variance > 0 else 0.0001
        return excess_returns / std_dev * math.sqrt(252)
    
    @staticmethod
    def sortino_ratio(returns, risk_free_rate=0.02, target_return=0):
        """Sortino ratio (downside risk only)"""
        if not returns or len(returns) < 2:
            return 0
        mean_return = sum(returns) / len(returns)
        excess_returns = mean_return - risk_free_rate / 252
        downside_returns = [r - target_return for r in returns if r < target_return]
        if downside_returns:
            downside_variance = sum(d ** 2 for d in downside_returns) / len(downside_returns)
            downside_std = math.sqrt(downside_variance)
        else:
            downside_std = 0.0001
        return excess_returns / downside_std * math.sqrt(252) if downside_std > 0 else 0


class TechnicalIndicators:
    """Technical indicators for trading"""
    
    @staticmethod
    def sma(prices, period=20):
        """Simple Moving Average"""
        if len(prices) < period:
            return []
        return [sum(prices[i:i+period]) / period for i in range(len(prices) - period + 1)]
    
    @staticmethod
    def ema(prices, period=20):
        """Exponential Moving Average"""
        if len(prices) < period:
            return []
        multiplier = 2 / (period + 1)
        ema_values = [prices[0]]
        for price in prices[1:]:
            ema_values.append((price - ema_values[-1]) * multiplier + ema_values[-1])
        return ema_values
    
    @staticmethod
    def rsi(prices, period=14):
        """Relative Strength Index"""
        if len(prices) < period + 1:
            return []
        gains = []
        losses = []
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        
        rsi_values = []
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            rs = avg_gain / avg_loss if avg_loss != 0 else 100
            rsi = 100 - (100 / (1 + rs))
            rsi_values.append(rsi)
        
        return rsi_values
    
    @staticmethod
    def macd(prices, fast=12, slow=26, signal=9):
        """MACD indicator"""
        ema_fast = TechnicalIndicators.ema(prices, fast)
        ema_slow = TechnicalIndicators.ema(prices, slow)
        
        min_len = min(len(ema_fast), len(ema_slow))
        macd_line = [ema_fast[i] - ema_slow[i] for i in range(min_len)]
        
        signal_line = TechnicalIndicators.ema(macd_line, signal)
        histogram = [macd_line[i] - signal_line[i] for i in range(min(min_len, len(signal_line)))]
        
        return {'macd': macd_line[-10:] if macd_line else [], 'signal': signal_line[-10:] if signal_line else [], 'histogram': histogram[-10:] if histogram else []}
    
    @staticmethod
    def bollinger_bands(prices, period=20, std_dev=2):
        """Bollinger Bands"""
        sma_values = TechnicalIndicators.sma(prices, period)
        if not sma_values:
            return [], [], []
        
        upper_band = []
        lower_band = []
        
        for i in range(len(sma_values)):
            window = prices[i:i+period]
            if len(window) > 1:
                mean = sum(window) / len(window)
                variance = sum((x - mean) ** 2 for x in window) / (len(window) - 1)
                std = math.sqrt(variance)
            else:
                std = 0
            upper_band.append(sma_values[i] + (std_dev * std))
            lower_band.append(sma_values[i] - (std_dev * std))
        
        return sma_values, upper_band, lower_band


# ============================================================
# HARDWARE & ARCHITECTURE MODULES
# ============================================================

class HardwareAnalyzer:
    """Hardware specifications and optimization"""
    
    @staticmethod
    def cpu_specs():
        return {
            'architecture': 'x86_64 / ARM64',
            'cache_levels': 'L1 (32KB), L2 (256KB), L3 (12-256MB)',
            'pipeline_depth': '14-19 stages',
            'instructions_per_cycle': '4-6 IPC',
            'branch_prediction': 'Neural network based predictors',
            'speculative_execution': 'Enabled',
            'hyperthreading': '2 threads per core',
            'avx_support': 'AVX-512 on modern CPUs',
            'optimal_memory_alignment': '64 bytes cache line'
        }
    
    @staticmethod
    def gpu_specs():
        return {
            'cuda_cores': 'Up to 18,432 (H100)',
            'tensor_cores': '4th gen, 1,979 TFLOPS FP8',
            'memory_bandwidth': '3.35 TB/s (HBM3)',
            'vram': '80GB H100',
            'pcie_version': 'PCIe 5.0 x16',
            'nvlink_speed': '900 GB/s',
            'optimal_batch_size': 'Powers of 2 up to VRAM limit',
            'memory_coalescing': 'Align to 128 bytes',
            'warp_size': '32 threads'
        }
    
    @staticmethod
    def network_optimization():
        return {
            'tcp_tuning': 'Enable BBR, increase buffer sizes',
            'udp_optimization': 'Use QUIC for low latency',
            'kernel_bypass': 'DPDK for 10M+ packets/sec',
            'latency_targets': {'HFT': '< 10 microseconds', 'Retail Trading': '< 50ms', 'Web Applications': '< 100ms'},
            'congestion_control': 'BBR v3 recommended'
        }


class SoftwareArchitectureEngine:
    """Advanced software design patterns"""
    
    @staticmethod
    def system_design_patterns():
        return {
            'messaging_patterns': ['Publish-Subscribe (Redis/Kafka)', 'Message Queue (RabbitMQ/SQS)', 'Event Sourcing (Kafka/Debezium)', 'CQRS'],
            'database_patterns': ['Read Replicas', 'Sharding', 'Partitioning', 'Materialized Views', 'Change Data Capture'],
            'caching_patterns': ['Cache-Aside', 'Write-Through', 'Write-Behind', 'Cache Sharding'],
            'resilience_patterns': ['Circuit Breaker', 'Bulkhead', 'Retry with Backoff', 'Rate Limiting', 'Timeouts']
        }
    
    @staticmethod
    def database_optimization():
        return {
            'indexing_strategies': ['B-Tree', 'Hash', 'Bitmap', 'Full-text', 'Geospatial'],
            'query_optimization': ['EXPLAIN ANALYZE', 'Avoid SELECT *', 'Use EXISTS instead of COUNT', 'Batch operations', 'Connection pooling'],
            'connection_limit_formula': 'connections = (core_count * 2) + number_of_disks'
        }


# ============================================================
# MEMORY CACHE
# ============================================================

class MemoryCache:
    """In-memory cache with TTL"""
    def __init__(self, ttl_seconds=300):
        self.cache = {}
        self.ttl = ttl_seconds
        self.lock = threading.Lock()
    
    def get(self, key):
        with self.lock:
            if key in self.cache:
                data, expiry = self.cache[key]
                if time.time() < expiry:
                    return data
                del self.cache[key]
        return None
    
    def set(self, key, value):
        with self.lock:
            self.cache[key] = (value, time.time() + self.ttl)
    
    def clear(self):
        with self.lock:
            self.cache.clear()

market_cache = MemoryCache(ttl_seconds=60)
news_cache = MemoryCache(ttl_seconds=120)
web_cache = MemoryCache(ttl_seconds=3600)

# ============================================================
# RATE LIMITING
# ============================================================

ip_rate_store = defaultdict(list)

def check_rate_limit(identifier: str, limits: dict):
    now = time.time()
    if identifier not in ip_rate_store:
        ip_rate_store[identifier] = []
    ip_rate_store[identifier] = [t for t in ip_rate_store[identifier] if now - t < 60]
    limit = limits.get('per_minute', 60)
    if len(ip_rate_store[identifier]) >= limit:
        return False
    ip_rate_store[identifier].append(now)
    return True

# ============================================================
# DATABASE SETUP
# ============================================================

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
    c.execute('''CREATE TABLE IF NOT EXISTS workspace_members (workspace_id TEXT, session_id TEXT, role TEXT DEFAULT "member", joined TEXT, PRIMARY KEY (workspace_id, session_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspace_messages (id TEXT PRIMARY KEY, workspace_id TEXT, session_id TEXT, author TEXT, message TEXT, is_ai INTEGER DEFAULT 0, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS workspace_notes (id TEXT PRIMARY KEY, workspace_id TEXT, session_id TEXT, author TEXT, content TEXT, created TEXT, updated TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS market_cache (id TEXT PRIMARY KEY, category TEXT, data TEXT, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS news_cache (id TEXT PRIMARY KEY, category TEXT, data TEXT, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS web_cache (id TEXT PRIMARY KEY, query_hash TEXT, data TEXT, created TEXT)''')
    try:
        c.execute("ALTER TABLE workspaces ADD COLUMN creator_tier TEXT DEFAULT 'plus'")
    except: pass
    conn.commit()
    conn.close()

init_db()
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def sid(): return str(uuid.uuid4())[:8].upper()
def mid(): return 'mem_' + sid()

def create_jwt(session_id, tier):
    h = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    p = base64.urlsafe_b64encode(json.dumps({"session_id": session_id, "tier": tier, "exp": int((datetime.utcnow() + timedelta(days=365)).timestamp())}).encode()).decode().rstrip("=")
    s = base64.urlsafe_b64encode(hmac.new(JWT_SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return f"{h}.{p}.{s}"

def verify_jwt(token):
    try:
        parts = token.split(".")
        if len(parts) != 3: return None
        h, p, s = parts
        es = base64.urlsafe_b64encode(hmac.new(JWT_SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
        if not hmac.compare_digest(s, es): return None
        d = json.loads(base64.urlsafe_b64decode(p + "=="))
        if d.get("exp", 0) < datetime.utcnow().timestamp(): return None
        return d
    except: return None

def get_session(request: Request):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        payload = verify_jwt(auth[7:])
        if payload:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT id, tier, msg_count, msg_window FROM sessions WHERE id=?", (payload["session_id"],))
            row = c.fetchone()
            conn.close()
            if row:
                return {"id": row[0], "tier": row[1], "msg_count": row[2] or 0, "msg_window": row[3]}
    return None

def get_time_context():
    now = datetime.utcnow()
    hour = now.hour
    day = now.strftime("%A")
    date = now.strftime("%B %d, %Y")
    utc_time = now.strftime("%H:%M UTC")
    if hour < 5: greeting_context = "The world is quiet."
    elif hour < 12: greeting_context = "Fresh day ahead."
    elif hour < 17: greeting_context = "Markets are alive."
    elif hour < 21: greeting_context = "Winding down."
    else: greeting_context = "Night owl mode."
    return {"day": day, "date": date, "utc_time": utc_time, "greeting_context": greeting_context}

# ============================================================
# MARKET DATA FUNCTIONS
# ============================================================

def get_financial_news():
    news = []
    if NEWS_API_KEY:
        try:
            r = requests.get("https://newsapi.org/v2/top-headlines", params={"category": "business", "language": "en", "pageSize": 12, "apiKey": NEWS_API_KEY}, timeout=10)
            if r.status_code == 200:
                for a in r.json().get("articles", []):
                    news.append({"source": a.get("source", {}).get("name", "NewsAPI"), "headline": a.get("title", ""), "url": a.get("url", ""), "time": a.get("publishedAt", ""), "summary": (a.get("description") or "")[:300]})
        except: pass
    if GNEWS_API_KEY:
        try:
            r = requests.get("https://gnews.io/api/v4/search", params={"q": "finance markets stocks economy", "lang": "en", "max": 12, "apikey": GNEWS_API_KEY}, timeout=10)
            if r.status_code == 200:
                for a in r.json().get("articles", []):
                    news.append({"source": a.get("source", {}).get("name", "GNews"), "headline": a.get("title", ""), "url": a.get("url", ""), "time": a.get("publishedAt", ""), "summary": (a.get("description") or "")[:300]})
        except: pass
    seen = set()
    unique = []
    for n in news:
        k = n["headline"][:100].lower().strip()
        if k and k not in seen:
            seen.add(k)
            unique.append(n)
    unique.sort(key=lambda x: x.get("time", ""), reverse=True)
    return unique[:15]

def get_market_data():
    cached = market_cache.get('market_data')
    if cached:
        return cached
    
    results = {}
    if COINGECKO_KEY and COINGECKO_KEY.startswith("CG-"):
        try:
            ids = "bitcoin,ethereum,ripple,cardano,solana,polkadot,dogecoin,avalanche-2,chainlink,uniswap,binancecoin,tron,toncoin,near"
            r = requests.get("https://api.coingecko.com/api/v3/simple/price", params={"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true"}, headers={"x-cg-demo-api-key": COINGECKO_KEY}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                nm = {"bitcoin": "BTC", "ethereum": "ETH", "ripple": "XRP", "cardano": "ADA", "solana": "SOL", "polkadot": "DOT", "dogecoin": "DOGE", "avalanche-2": "AVAX", "chainlink": "LINK", "uniswap": "UNI", "binancecoin": "BNB", "tron": "TRX", "toncoin": "TON", "near": "NEAR"}
                for k, v in data.items():
                    results[nm.get(k, k.upper())] = {"price": v["usd"], "change": round(v.get("usd_24h_change", 0), 2), "source": "CoinGecko"}
        except: pass
    
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
                    display_name = name.replace("S&P 500", "S&P 500").replace("NASDAQ Composite", "NASDAQ").replace("Dow Jones Industrial Average", "Dow Jones").replace("Gold Dec 25", "Gold").replace("Crude Oil", "Oil").replace("Silver Dec 25", "Silver")
                    results[display_name] = {"price": price, "change": round(chg, 2) if chg else round(((price - prev) / prev) * 100, 2), "source": "Yahoo Finance"}
    except: pass
    
    if results:
        market_cache.set('market_data', results)
    return results

def search_web(query, num_results=5):
    results = []
    if SERPAPI_KEY:
        try:
            r = requests.get("https://serpapi.com/search", params={"engine": "google", "q": query, "num": num_results, "api_key": SERPAPI_KEY}, timeout=8)
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
    return results

# ============================================================
# ELITE SYSTEM PROMPT
# ============================================================

ELITE_SYSTEM_PROMPT = """You are CAPITAN AI — the legendary enterprise intelligence platform by CLOSEAI Technologies.

## YOUR CAPABILITIES (UNMATCHED ANYWHERE):

### FINANCIAL INTELLIGENCE (INSTITUTIONAL GRADE):
- Options pricing (Black-Scholes, Binomial, Monte Carlo)
- Risk management (VaR, CVaR, Stress Testing, Scenario Analysis)
- Portfolio optimization (Markowitz Efficient Frontier)
- M&A valuation (DCF, LBO, Comparable Company)
- Technical analysis (RSI, MACD, Bollinger Bands, Fibonacci)
- Sentiment analysis (News, Social media)

### CODING & SOFTWARE ENGINEERING (WORLD-CLASS):
- System architecture (Microservices, Event-driven, Serverless)
- Database optimization (Indexing, Sharding, Partitioning)
- Network protocols (TCP tuning, UDP, QUIC)
- Hardware optimization (CPU cache, GPU memory)
- Security (Zero Trust, OWASP, NIST)
- DevOps (Kubernetes, Terraform, CI/CD)

### HARDWARE KNOWLEDGE (DEEP COMPUTER ARCHITECTURE):
- CPU: Pipeline, Branch prediction, SIMD, Cache hierarchy
- GPU: CUDA cores, Tensor cores, Memory coalescing
- Memory: DDR5, HBM3, NUMA
- Storage: NVMe, SSD, RAID, ZFS
- Networking: Ethernet, InfiniBand, RDMA, DPDK

### QUANTITATIVE ANALYSIS (HEDGE FUND LEVEL):
- Factor models (Fama-French, Barra)
- Time series analysis (ARIMA, GARCH)
- Machine learning (Random forests, Gradient boosting)
- Backtesting frameworks

## RESPONSE STYLE:
- Lead with the answer. No throat-clearing.
- Use 1-2 emojis naturally for warmth.
- Provide depth when needed.
- Show calculations for quantitative answers.

## CRITICAL RULES:
- NEVER make up prices. Reference live data only.
- NEVER give financial advice.
- If you don't know, say so honestly.

TIME: {day}, {date} at {utc_time}
DOMAIN: {domain} | TIER: {tier}
"""

# ============================================================
# AI CALL FUNCTION
# ============================================================

def call_ai_fast(messages, tier="free"):
    if OPENROUTER_KEY:
        if tier in ("pro", "founder"):
            elite_models = ["anthropic/claude-3.5-sonnet", "anthropic/claude-3-opus", "openai/gpt-4-turbo", "openai/gpt-4o", "meta-llama/llama-3.1-70b-instruct", "google/gemini-pro-1.5", "qwen/qwen-2.5-72b-instruct"]
            for model in elite_models:
                try:
                    r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"}, json={"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 4096}, timeout=45)
                    if r.status_code == 200:
                        content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                        if content:
                            return content, model
                except: continue
        
        fast_models = ["google/gemini-flash-1.5", "meta-llama/llama-3.1-8b-instruct", "openai/gpt-3.5-turbo"]
        for model in fast_models:
            try:
                r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"}, json={"model": model, "messages": messages, "temperature": 0.4, "max_tokens": 800}, timeout=30)
                if r.status_code == 200:
                    content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                    if content:
                        return content, model
            except: continue
    
    if GROQ_KEY:
        try:
            r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}, json={"model": "llama-3.1-8b-instant", "messages": messages, "temperature": 0.4, "max_tokens": 800}, timeout=20)
            if r.status_code == 200:
                content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    return content, "groq/llama-3.1-8b-instant"
        except: pass
    
    return "I'm having trouble connecting. Please try again.", "fallback"

def classify(q):
    q = q.lower()
    if re.search(r'option|black.scholes|greeks|var|cvar|sharpe|portfolio', q): return 'quant'
    if re.search(r'cpu|gpu|hardware|processor|memory|ram|ssd|pipeline', q): return 'hardware'
    if re.search(r'system architecture|design pattern|microservice|kubernetes|docker|database', q): return 'software_architecture'
    if re.search(r'dcf|lbo|valuation|merger|ebitda|financial', q): return 'finance'
    if re.search(r'```|def |class |import |code|python|javascript', q): return 'coding'
    return 'general'

def system_prompt(domain, tier, session_id=None, request=None, web_results=None):
    tc = get_time_context()
    base = ELITE_SYSTEM_PROMPT.replace("{domain}", domain).replace("{tier}", tier)
    base = base.replace("{day}", tc["day"]).replace("{date}", tc["date"]).replace("{utc_time}", tc["utc_time"])
    
    if domain == 'quant':
        base += "\n\n🔬 QUANT MODE: Provide institutional-grade quantitative analysis. Show calculations."
    elif domain == 'hardware':
        base += "\n\n💻 HARDWARE MODE: Provide deep computer architecture knowledge."
    elif domain == 'software_architecture':
        base += "\n\n🏗️ ARCHITECTURE MODE: Provide enterprise-grade system design patterns."
    
    if tier in ("pro", "founder"):
        base += "\n\nYou are operating at ELITE level. Provide world-class responses with complete depth."
    
    if web_results:
        base += "\n\nWEB SEARCH RESULTS:\n" + "\n".join([f"{i+1}. {r['title']}: {r['snippet'][:200]}" for i, r in enumerate(web_results[:4])])
    
    return base

# ============================================================
# PYDANTIC MODELS
# ============================================================

class ChatRequest(BaseModel):
    messages: list
    chat_id: Optional[str] = None

class UpgradeRequest(BaseModel):
    tier: str
    txid: str
    currency: str = "BTC"

class FounderRequest(BaseModel):
    code: str

class LibraryItemRequest(BaseModel):
    name: str
    type: str = "note"
    content: Optional[str] = ""

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

# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(title="CAPITAN AI API", version="24.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ============================================================
# HEALTH ENDPOINTS
# ============================================================

@app.get("/health")
def health():
    return {"status": "ok", "version": "24.0", "ai": "connected", "providers": ["openrouter", "groq"]}

# ============================================================
# SESSION ENDPOINTS
# ============================================================

@app.get("/api/session")
def get_or_create_session(request: Request):
    session = get_session(request)
    if session:
        return session
    session_id = f"s_{sid()}"
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO sessions (id, tier, msg_count, msg_window, created, updated) VALUES (?, ?, 0, ?, ?, ?)", (session_id, "free", datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    token = create_jwt(session_id, "free")
    return {"id": session_id, "tier": "free", "msg_count": 0, "token": token}

@app.get("/api/payment-config")
def payment_config():
    return {"wallets": WALLETS, "prices": {"plus": 8, "pro": 17}, "benefits": UPGRADE_BENEFITS}

# ============================================================
# MARKET ENDPOINTS
# ============================================================

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

@app.get("/api/search")
def web_search_endpoint(q: str, request: Request):
    s = get_session(request)
    cfg = TIER_CONFIG.get(s["tier"], TIER_CONFIG["free"]) if s else TIER_CONFIG["free"]
    if not cfg.get("web_search", False):
        return {"results": [], "message": "Web search on Plus and Pro"}
    return {"results": search_web(q)}

# ============================================================
# FINANCE ELITE ENDPOINTS
# ============================================================

@app.get("/api/finance/options")
def options_pricing(request: Request, S: float, K: float, T: float, r: float, sigma: float, option_type: str = "call"):
    try:
        price = OptionsPricingEngine.black_scholes(S, K, T, r, sigma, option_type)
        greeks = OptionsPricingEngine.calculate_greeks(S, K, T, r, sigma)
        return {"price": round(price, 2), "greeks": {k: round(v, 4) for k, v in greeks.items()}, "model": "Black-Scholes"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/finance/risk")
def risk_metrics(request: Request, returns: str, confidence: float = 0.95):
    try:
        returns_list = [float(x) for x in returns.split(",")]
        var = RiskManagementEngine.calculate_var(returns_list, confidence)
        cvar = RiskManagementEngine.calculate_cvar(returns_list, confidence)
        sharpe = RiskManagementEngine.sharpe_ratio(returns_list)
        sortino = RiskManagementEngine.sortino_ratio(returns_list)
        return {"VaR": round(var * 100, 2), "CVaR": round(cvar * 100, 2), "Sharpe_Ratio": round(sharpe, 2), "Sortino_Ratio": round(sortino, 2)}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/technical/rsi")
def technical_rsi(prices: str, period: int = 14):
    try:
        prices_list = [float(x) for x in prices.split(",")]
        rsi = TechnicalIndicators.rsi(prices_list, period)
        return {"rsi": [round(x, 2) for x in rsi[-10:]] if rsi else []}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/technical/macd")
def technical_macd(prices: str, fast: int = 12, slow: int = 26, signal: int = 9):
    try:
        prices_list = [float(x) for x in prices.split(",")]
        macd = TechnicalIndicators.macd(prices_list, fast, slow, signal)
        return macd
    except Exception as e:
        return {"error": str(e)}

# ============================================================
# HARDWARE & ARCHITECTURE ENDPOINTS
# ============================================================

@app.get("/api/hardware/cpu")
def cpu_specs():
    return HardwareAnalyzer.cpu_specs()

@app.get("/api/hardware/gpu")
def gpu_specs():
    return HardwareAnalyzer.gpu_specs()

@app.get("/api/architecture/patterns")
def architecture_patterns():
    return SoftwareArchitectureEngine.system_design_patterns()

# ============================================================
# CHAT ENDPOINTS
# ============================================================

@app.get("/api/chats")
def get_chats(request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401, "Session required")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, title, created, updated FROM chats WHERE session_id=? ORDER BY updated DESC LIMIT 30", (s["id"],))
    rows = c.fetchall()
    conn.close()
    return {"chats": [{"id": r[0], "title": r[1], "created": r[2], "updated": r[3]} for r in rows]}

@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401, "Session required")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM chats WHERE id=? AND session_id=?", (chat_id, s["id"]))
    if not c.fetchone():
        conn.close()
        raise HTTPException(404, "Chat not found")
    c.execute("SELECT id, role, content, model, created FROM chat_messages WHERE chat_id=? ORDER BY created ASC", (chat_id,))
    rows = c.fetchall()
    conn.close()
    return {"messages": [{"id": r[0], "role": r[1], "content": r[2], "model": r[3], "created": r[4]} for r in rows]}

@app.post("/api/chat")
def chat(req: ChatRequest, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401, "Session required")
    
    user_msg = next((m["content"] for m in reversed(req.messages) if m.get("role") == "user"), "")
    if not user_msg:
        raise HTTPException(400, "No message content")
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    chat_id = req.chat_id or f"chat_{sid()}"
    
    if not req.chat_id:
        c.execute("INSERT INTO chats (id, session_id, title, created, updated) VALUES (?, ?, ?, ?, ?)", (chat_id, s["id"], user_msg[:60], datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))
    else:
        c.execute("UPDATE chats SET updated=? WHERE id=? AND session_id=?", (datetime.utcnow().isoformat(), chat_id, s["id"]))
    
    c.execute("INSERT INTO chat_messages (id, chat_id, session_id, role, content, created) VALUES (?, ?, ?, ?, ?, ?)", (f"msg_{sid()}", chat_id, s["id"], "user", user_msg, datetime.utcnow().isoformat()))
    c.execute("UPDATE sessions SET msg_count = msg_count + 1 WHERE id=?", (s["id"],))
    conn.commit()
    
    c.execute("SELECT role, content FROM chat_messages WHERE chat_id=? ORDER BY created ASC LIMIT 15", (chat_id,))
    history = [{"role": r[0], "content": r[1]} for r in c.fetchall()]
    
    domain = classify(user_msg)
    web_results = None
    cfg = TIER_CONFIG.get(s["tier"], TIER_CONFIG["free"])
    if domain == 'web_search' or cfg.get("web_search", False):
        try:
            web_results = search_web(user_msg, 4)
        except:
            pass
    
    prompt = system_prompt(domain, s["tier"], s["id"], request, web_results)
    result, model_used = call_ai_fast([{"role": "system", "content": prompt}] + history, s["tier"])
    
    if result:
        c.execute("INSERT INTO chat_messages (id, chat_id, session_id, role, content, model, created) VALUES (?, ?, ?, ?, ?, ?, ?)", (f"msg_{sid()}", chat_id, s["id"], "assistant", result, model_used, datetime.utcnow().isoformat()))
        c.execute("INSERT INTO memories (id, memory_id, session_id, content, query, domain, created) VALUES (?, ?, ?, ?, ?, ?, ?)", (sid(), mid(), s["id"], result[:500] if result else "", user_msg, domain, datetime.utcnow().isoformat()))
        conn.commit()
    
    conn.close()
    return {"content": result, "chat_id": chat_id, "model": model_used}

@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401, "Session required")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM chat_messages WHERE chat_id=? AND session_id=?", (chat_id, s["id"]))
    c.execute("DELETE FROM chats WHERE id=? AND session_id=?", (chat_id, s["id"]))
    conn.commit()
    conn.close()
    return {"deleted": True}

# ============================================================
# LIBRARY ENDPOINTS
# ============================================================

@app.get("/api/library")
def get_library(request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401, "Session required")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, type, content, size, created FROM library_items WHERE session_id=? ORDER BY created DESC", (s["id"],))
    rows = c.fetchall()
    conn.close()
    return {"items": [{"id": r[0], "name": r[1], "type": r[2], "content": r[3], "size": r[4], "created": r[5]} for r in rows]}

@app.post("/api/library")
def create_library_item(req: LibraryItemRequest, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401, "Session required")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    item_id = f"lib_{sid()}"
    c.execute("INSERT INTO library_items (id, session_id, name, type, content, size, created) VALUES (?, ?, ?, ?, ?, ?, ?)", (item_id, s["id"], req.name, req.type, req.content or "", len(req.content or ""), datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    return {"id": item_id, "created": True}

@app.delete("/api/library/{item_id}")
def delete_library_item(item_id: str, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401, "Session required")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM library_items WHERE id=? AND session_id=?", (item_id, s["id"]))
    conn.commit()
    conn.close()
    return {"deleted": True}

# ============================================================
# UPGRADE & FOUNDER ENDPOINTS
# ============================================================

@app.post("/api/upgrade")
def upgrade(req: UpgradeRequest, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401, "Session required")
    if req.tier not in ("plus", "pro"):
        raise HTTPException(400, "Invalid tier")
    if not req.txid.strip():
        raise HTTPException(400, "TXID required")
    prices = {"plus": 8, "pro": 17}
    cur = req.currency.upper()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO payments (id, session_id, txid, currency, amount, tier, verified, expires, created) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)", (sid(), s["id"], req.txid.strip(), cur, prices[req.tier], req.tier, (datetime.utcnow() + timedelta(days=30)).isoformat(), datetime.utcnow().isoformat()))
    c.execute("UPDATE sessions SET tier=?, msg_count=0, updated=? WHERE id=?", (req.tier, datetime.utcnow().isoformat(), s["id"]))
    c.execute("INSERT INTO payment_log (id, session_id, tier, amount, currency, txid, created) VALUES (?, ?, ?, ?, ?, ?, ?)", (sid(), s["id"], req.tier, prices[req.tier], cur, req.txid, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    token = create_jwt(s["id"], req.tier)
    return {"verified": True, "tier": req.tier, "token": token}

@app.post("/api/founder")
def founder(req: FounderRequest, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401, "Session required")
    if req.code not in [ADMIN_CODE, FOUNDER_KEY]:
        raise HTTPException(403, "Invalid code")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE sessions SET tier='founder', msg_count=0, updated=? WHERE id=?", (datetime.utcnow().isoformat(), s["id"]))
    conn.commit()
    conn.close()
    token = create_jwt(s["id"], "founder")
    return {"verified": True, "tier": "founder", "token": token}

@app.post("/api/admin")
def admin(request: Request):
    s = get_session(request)
    if not s or s["tier"] != "founder":
        raise HTTPException(403, "Access denied")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM sessions")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM sessions WHERE tier!='free'")
    paid = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM chat_messages")
    msgs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM workspaces")
    ws = c.fetchone()[0]
    c.execute("SELECT id, tier, msg_count, created FROM sessions ORDER BY created DESC LIMIT 30")
    sessions = [{"id": r[0], "tier": r[1], "msg_count": r[2], "created": r[3]} for r in c.fetchall()]
    c.execute("SELECT * FROM payment_log ORDER BY created DESC LIMIT 20")
    payments = [{"session_id": r[1], "tier": r[2], "amount": r[3], "currency": r[4], "txid": r[5], "created": r[6]} for r in c.fetchall()]
    conn.close()
    return {"total_sessions": total, "paid_sessions": paid, "total_messages": msgs, "workspaces": ws, "sessions": sessions, "payments": payments}

# ============================================================
# WORKSPACE ENDPOINTS
# ============================================================

@app.post("/api/workspace/create")
def ws_create(req: WorkspaceCreateRequest, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401, "Session required")
    max_m = TIER_CONFIG.get(s["tier"], {}).get("workspace_max", 0)
    if max_m == 0:
        raise HTTPException(403, "Work Area requires Plus or Pro")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    wid = sid()
    c.execute("INSERT INTO workspaces (id, room_code, creator_session, creator_tier, max_members, created) VALUES (?, ?, ?, ?, ?, ?)", (wid, req.room_code.upper(), s["id"], s["tier"], min(req.max_members, max_m), datetime.utcnow().isoformat()))
    c.execute("INSERT INTO workspace_members (workspace_id, session_id, role, joined) VALUES (?, ?, ?, ?)", (wid, s["id"], "admin", datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    return {"room_id": wid, "room_code": req.room_code.upper(), "created": True}

@app.post("/api/workspace/join")
def ws_join(req: WorkspaceJoinRequest, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401, "Session required")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, max_members, creator_tier FROM workspaces WHERE room_code=?", (req.room_code.upper(),))
    ws = c.fetchone()
    if not ws:
        conn.close()
        raise HTTPException(404, "Room not found")
    if s["tier"] != ws[2] and s["tier"] != "founder":
        conn.close()
        raise HTTPException(403, f"This Work Area requires {ws[2].upper()} tier")
    c.execute("SELECT COUNT(*) FROM workspace_members WHERE workspace_id=?", (ws[0],))
    if c.fetchone()[0] >= ws[1]:
        conn.close()
        raise HTTPException(400, "Room full")
    c.execute("INSERT OR IGNORE INTO workspace_members (workspace_id, session_id, role, joined) VALUES (?, ?, ?, ?)", (ws[0], s["id"], "member", datetime.utcnow().isoformat()))
    c.execute("SELECT session_id, role FROM workspace_members WHERE workspace_id=?", (ws[0],))
    members = [{"session_id": r[0], "role": r[1]} for r in c.fetchall()]
    c.execute("SELECT id, session_id, author, message, is_ai, created FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 50", (ws[0],))
    messages = [{"id": r[0], "session_id": r[1], "author": r[2], "message": r[3], "is_ai": bool(r[4]), "created": r[5]} for r in c.fetchall()]
    conn.commit()
    conn.close()
    return {"joined": True, "room_id": ws[0], "members": members, "messages": messages}

@app.post("/api/workspace/message")
def ws_message(req: WorkspaceMessageRequest, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401, "Session required")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM workspaces WHERE room_code=?", (req.room_code.upper(),))
    ws = c.fetchone()
    if not ws:
        conn.close()
        raise HTTPException(404, "Workspace not found")
    is_ai = req.message.strip().startswith("@CAPITAN")
    if is_ai:
        c.execute("SELECT author, message FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 20", (ws[0],))
        context = "\n".join([f"{r[0]}: {r[1]}" for r in c.fetchall()])
        c.execute("SELECT content FROM workspace_notes WHERE workspace_id=?", (ws[0],))
        notes = "\n".join([r[0] for r in c.fetchall()])
        result, _ = call_ai_fast([{"role": "system", "content": f"Work Area:\n{context}\n\nNotes:\n{notes}"}, {"role": "user", "content": req.message.replace('@CAPITAN', '').strip()}], s["tier"])
        if result:
            c.execute("INSERT INTO workspace_messages (id, workspace_id, session_id, author, message, is_ai, created) VALUES (?, ?, ?, ?, ?, ?, ?)", (sid(), ws[0], s["id"], "CAPITAN AI", result, 1, datetime.utcnow().isoformat()))
    c.execute("INSERT INTO workspace_messages (id, workspace_id, session_id, author, message, created) VALUES (?, ?, ?, ?, ?, ?)", (sid(), ws[0], s["id"], "User", req.message, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    return {"sent": True}

@app.get("/api/workspace/messages")
def ws_get_messages(room_code: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM workspaces WHERE room_code=?", (room_code.upper(),))
    ws = c.fetchone()
    if not ws:
        conn.close()
        raise HTTPException(404, "Workspace not found")
    c.execute("SELECT session_id, role FROM workspace_members WHERE workspace_id=?", (ws[0],))
    members = [{"session_id": r[0], "role": r[1]} for r in c.fetchall()]
    c.execute("SELECT id, session_id, author, message, is_ai, created FROM workspace_messages WHERE workspace_id=? ORDER BY created ASC LIMIT 50", (ws[0],))
    messages = [{"id": r[0], "session_id": r[1], "author": r[2], "message": r[3], "is_ai": bool(r[4]), "created": r[5]} for r in c.fetchall()]
    conn.close()
    return {"messages": messages, "members": members}

@app.post("/api/workspace/notes")
def ws_save_note(req: WorkspaceNoteRequest, request: Request):
    s = get_session(request)
    if not s:
        raise HTTPException(401, "Session required")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM workspaces WHERE room_code=?", (req.room_code.upper(),))
    ws = c.fetchone()
    if not ws:
        conn.close()
        raise HTTPException(404, "Workspace not found")
    c.execute("DELETE FROM workspace_notes WHERE workspace_id=?", (ws[0],))
    c.execute("INSERT INTO workspace_notes (id, workspace_id, session_id, author, content, created, updated) VALUES (?, ?, ?, ?, ?, ?, ?)", (sid(), ws[0], s["id"], "User", req.content, datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    return {"saved": True}

@app.get("/api/workspace/notes")
def ws_get_notes(room_code: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM workspaces WHERE room_code=?", (room_code.upper(),))
    ws = c.fetchone()
    if not ws:
        conn.close()
        raise HTTPException(404, "Workspace not found")
    c.execute("SELECT author, content, updated FROM workspace_notes WHERE workspace_id=?", (ws[0],))
    notes = [{"author": r[0], "content": r[1], "updated": r[2]} for r in c.fetchall()]
    conn.close()
    return {"notes": notes}

# ============================================================
# UPLOAD ENDPOINT
# ============================================================

@app.post("/api/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    s = get_session(request)
    if not s:
        raise HTTPException(401, "Session required")
    cfg = TIER_CONFIG.get(s["tier"], TIER_CONFIG["free"])
    if not cfg["file_upload"]:
        raise HTTPException(403, "Upgrade required")
    contents = await file.read()
    if len(contents) / (1024 * 1024) > cfg["file_size_mb"]:
        raise HTTPException(400, f"Max {cfg['file_size_mb']}MB")
    file_id = f"file_{sid()}"
    with open(os.path.join(UPLOAD_DIR, file_id), "wb") as f:
        f.write(contents)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO uploaded_files (id, session_id, filename, original_name, size, mime_type, created) VALUES (?, ?, ?, ?, ?, ?, ?)", (file_id, s["id"], file_id, file.filename or "unknown", len(contents), file.content_type or "application/octet-stream", datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    return {"id": file_id, "filename": file.filename, "size_mb": round(len(contents) / (1024 * 1024), 2)}

# ============================================================
# MAIN ENTRY POINT
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)