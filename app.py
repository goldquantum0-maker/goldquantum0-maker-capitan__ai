# app.py – CAPITAN AI · ELITE INTELLIGENCE CORE v5.0 · Pure Black Edition
# Sovereign AI Technologies
# ═══════════════════════════════════════════════════════════════
# UPGRADED: Pure black theme, logo removed
# UPGRADED: SQLite persistence (replaces JSON)
# UPGRADED: Founder Mission Control dashboard
# UPGRADED: Strategic memory layer
# UPGRADED: Project OS with progress tracking
# UPGRADED: 'Libraries' section with moved suggestions
# UPGRADED: White text and light blue accent colors
# UPGRADED: Multi-API fallback (OpenRouter → OpenAI → Local)
# INTELLIGENCE: Fully preserved — all AI logic, personas, streaming,
#              crypto verification, central bank knowledge intact
# ═══════════════════════════════════════════════════════════════

import os, re, json, uuid, time, subprocess, tempfile, requests, streamlit as st
import xml.etree.ElementTree as ET
import numpy as np
import sqlite3
from typing import List, Dict, Any, Optional, Generator, Tuple, Union
from datetime import datetime, timedelta
from collections import defaultdict
import math, base64
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError

from dotenv import load_dotenv
load_dotenv()

# ── Optional imports ──────────────────────────────────────────
FAISS_AVAILABLE = False
try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    pass

OPENAI_AVAILABLE = False
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    pass

LOCAL_EMBEDDING_AVAILABLE = False
try:
    from sentence_transformers import SentenceTransformer
    LOCAL_EMBEDDING_AVAILABLE = True
except ImportError:
    pass

PLOTLY_AVAILABLE = False
try:
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    pass

# ═══════════════════════════════════════════════════════════════
# BRANDING — Text only, no logo
# ═══════════════════════════════════════════════════════════════
APP_NAME    = "CAPITAN AI"
APP_TAGLINE = "Text-Optimized Intelligence · Finance · Quant · Coding · Africa"

# ═══════════════════════════════════════════════════════════════
# SQLITE DATABASE — Replaces JSON persistence
# ═══════════════════════════════════════════════════════════════
DB_PATH = "capitan.db"
STATE_FILE       = "capitan_state.json"
PROJECTS_FILE    = "capitan_projects.json"
GOALS_FILE       = "capitan_goals.json"
MEMORY_META_PATH = "capitan_memory_meta.json"
MEMORY_INDEX_PATH= "capitan_faiss.index"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS app_state (
        key TEXT PRIMARY KEY, value TEXT, updated TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY, name TEXT, mission TEXT, status TEXT,
        progress INTEGER DEFAULT 0, created TEXT, data TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS goals (
        id TEXT PRIMARY KEY, description TEXT, category TEXT,
        status TEXT, created TEXT, target TEXT, current INTEGER DEFAULT 0,
        deadline TEXT, priority TEXT DEFAULT "medium"
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS payments (
        id TEXT PRIMARY KEY, txid TEXT, currency TEXT, amount REAL,
        verified INTEGER DEFAULT 0, plan TEXT, expires TEXT, created TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS strategic_patterns (
        id TEXT PRIMARY KEY, pattern TEXT, confidence REAL,
        category TEXT, created TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY, project_id TEXT, title TEXT,
        status TEXT DEFAULT "pending", priority TEXT DEFAULT "medium",
        created TEXT, due TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

def db_get(key, default=None):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT value FROM app_state WHERE key=?", (key,))
        row = c.fetchone()
        conn.close()
        if row: return json.loads(row[0])
        return default
    except: return default

def db_set(key, value):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO app_state (key, value, updated) VALUES (?,?,?)",
                  (key, json.dumps(value), datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except: pass

def load_projects_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id, name, mission, status, progress, created, data FROM projects")
        rows = c.fetchall()
        conn.close()
        projects = {}
        for r in rows:
            extra = json.loads(r[6]) if r[6] else {}
            projects[r[0]] = {"id":r[0],"name":r[1],"mission":r[2],"status":r[3],
                               "progress":r[4],"created":r[5],**extra}
        if not projects and os.path.exists(PROJECTS_FILE):
            with open(PROJECTS_FILE,'r') as f:
                projects = json.load(f)
            for pid, p in projects.items():
                save_project_db(p)
        return projects
    except:
        if os.path.exists(PROJECTS_FILE):
            try:
                with open(PROJECTS_FILE,'r') as f: return json.load(f)
            except: pass
        return {}

def save_project_db(p):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        extra = {k:v for k,v in p.items() if k not in ["id","name","mission","status","progress","created"]}
        c.execute("INSERT OR REPLACE INTO projects (id,name,mission,status,progress,created,data) VALUES (?,?,?,?,?,?,?)",
                  (p.get("id",""), p.get("name",""), p.get("mission",""), p.get("status","active"),
                   p.get("progress",0), p.get("created",""), json.dumps(extra)))
        conn.commit()
        conn.close()
    except: pass

def save_projects_db(projects):
    for pid, p in projects.items():
        save_project_db(p)
    try:
        with open(PROJECTS_FILE,'w') as f: json.dump(projects, f, indent=2)
    except: pass

def load_goals_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id,description,category,status,created,target,current,deadline,priority FROM goals")
        rows = c.fetchall()
        conn.close()
        goals = [{"id":r[0],"description":r[1],"category":r[2],"status":r[3],
                  "created":r[4],"target":r[5],"current":r[6],"deadline":r[7],"priority":r[8]} for r in rows]
        if not goals and os.path.exists(GOALS_FILE):
            with open(GOALS_FILE,'r') as f: goals = json.load(f)
            for g in goals: save_goal_db(g)
        return goals
    except:
        if os.path.exists(GOALS_FILE):
            try:
                with open(GOALS_FILE,'r') as f: return json.load(f)
            except: pass
        return []

def save_goal_db(g):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO goals (id,description,category,status,created,target,current,deadline,priority) VALUES (?,?,?,?,?,?,?,?,?)",
                  (g.get("id",""), g.get("description",""), g.get("category","general"),
                   g.get("status","active"), g.get("created",""), g.get("target",""),
                   g.get("current",0), g.get("deadline",""), g.get("priority","medium")))
        conn.commit()
        conn.close()
    except: pass

def save_goals_db(goals):
    for g in goals: save_goal_db(g)
    try:
        with open(GOALS_FILE,'w') as f: json.dump(goals, f, indent=2)
    except: pass

def get_strategic_patterns():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id,pattern,confidence,category,created FROM strategic_patterns ORDER BY confidence DESC LIMIT 10")
        rows = c.fetchall()
        conn.close()
        return [{"id":r[0],"pattern":r[1],"confidence":r[2],"category":r[3],"created":r[4]} for r in rows]
    except: return []

def save_strategic_pattern(pattern, confidence, category):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        pid = str(uuid.uuid4())
        c.execute("INSERT INTO strategic_patterns (id,pattern,confidence,category,created) VALUES (?,?,?,?,?)",
                  (pid, pattern, confidence, category, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except: pass

# ═══════════════════════════════════════════════════════════════
# PERSISTENT STATE (SQLite-backed) — MODIFIED: pro status per session only, NOT shared
# ═══════════════════════════════════════════════════════════════
def load_persistent_state():
    # PRO STATUS IS NOW SESSION-ONLY — NEVER LOADED FROM DB
    # This prevents cross-user sharing
    messages = db_get('messages', [])
    # is_pro is ALWAYS False when loading — user must verify in their own session
    is_pro = False  # FORCED: never load pro status from shared storage
    is_founder = False  # FORCED: never load founder status from shared storage
    chat_history = db_get('chat_history', [])
    verified_txids = db_get('verified_txids', [])
    user_preferences = db_get('user_preferences', {})
    daily_count = db_get('daily_count', 0)
    daily_reset = db_get('daily_reset', datetime.now().isoformat())

    if not messages and os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE,'r') as f:
                d = json.load(f)
                # IGNORE is_pro and is_founder from file — session only
                return (d.get('messages',[]), False, False,
                        d.get('chat_history',[]), d.get('verified_txids',[]),
                        d.get('user_preferences',{}), d.get('daily_count',0),
                        d.get('daily_reset',datetime.now().isoformat()))
        except: pass
    return messages, is_pro, is_founder, chat_history, verified_txids, user_preferences, daily_count, daily_reset

def save_persistent_state(messages, is_pro, is_founder, chat_history=None,
                          verified_txids=None, user_preferences=None,
                          daily_count=0, daily_reset=None):
    # ONLY save non-pro-status data to shared storage
    # is_pro and is_founder are NOT persisted — they stay in session only
    db_set('messages', messages)
    # DO NOT save is_pro — it's session-only
    # DO NOT save is_founder — it's session-only
    db_set('chat_history', chat_history or [])
    db_set('verified_txids', verified_txids or [])
    db_set('user_preferences', user_preferences or {})
    db_set('daily_count', daily_count)
    db_set('daily_reset', daily_reset or datetime.now().isoformat())
    try:
        with open(STATE_FILE,'w') as f:
            json.dump({'messages':messages,'is_pro':False,'is_founder':False,  # Force false in file
                       'chat_history':chat_history or [],'verified_txids':verified_txids or [],
                       'user_preferences':user_preferences or {},'daily_count':daily_count,
                       'daily_reset':daily_reset or datetime.now().isoformat()}, f, indent=2)
    except: pass

def persist_current_state():
    save_persistent_state(
        st.session_state.messages,
        st.session_state.is_pro,
        st.session_state.is_founder,
        st.session_state.chat_history,
        st.session_state.verified_txids,
        st.session_state.user_preferences,
        st.session_state.daily_count,
        st.session_state.daily_reset
    )
    save_projects_db(st.session_state.projects)
    save_goals_db(st.session_state.goals)

def load_projects(): return load_projects_db()
def save_projects(p): save_projects_db(p)
def load_goals(): return load_goals_db()
def save_goals(g): save_goals_db(g)

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION — INTELLIGENCE UNTOUCHED
# ═══════════════════════════════════════════════════════════════
CONFIG = {
    "OPENROUTER_KEY":    os.environ.get("OPENROUTER_API_KEY",""),
    "OPENAI_API_KEY":    os.environ.get("OPENAI_API_KEY",""),
    "SERPER_KEY":        os.environ.get("SERPER_API_KEY",""),
    "WOLFRAM_APP_ID":    os.environ.get("WOLFRAM_APP_ID",""),
    "ETHERSCAN_API_KEY": os.environ.get("ETHERSCAN_API_KEY",""),
    "HF_TOKEN":          os.environ.get("HF_TOKEN",""),

    "PRO_MODELS":     ["anthropic/claude-3.5-sonnet","openai/gpt-4o",
                       "deepseek/deepseek-r1","google/gemini-pro-1.5"],
    "FREE_MODELS":    ["deepseek/deepseek-chat","meta-llama/llama-3.1-70b-instruct"],
    "FAST_MODEL":     "deepseek/deepseek-chat",
    "SMART_MODEL":    "anthropic/claude-3.5-sonnet",
    "DEEP_MODEL":     "deepseek/deepseek-r1",
    "PLANNER_MODEL":  "deepseek/deepseek-r1",
    "CRITIC_MODEL":   "anthropic/claude-3.5-sonnet",
    "REFINER_MODEL":  "anthropic/claude-3.5-sonnet",
    "SYNTH_MODEL":    "anthropic/claude-3.5-sonnet",
    "COMPUTE_MODEL":  "deepseek/deepseek-r1",

    "CREATOR":        "Sovereign AI Technologies",
    "FOUNDER_KEY":    os.environ.get("FOUNDER_KEY","cap-founder-key"),

    "CIRCUIT_BREAKER_TIMEOUTS": {
        "web_search":3,"live_prices":5,"llm_call":60,"news":8,"crypto_verify":10,
    },
    "PRICE_CACHE_TTL":         30,
    "NEWS_CACHE_TTL":          300,
    "MEMORY_DECAY_HALF_LIFE":  30,
    "SIMPLE_WORD_THRESHOLD":   12,
    "COMPLEX_WORD_THRESHOLD":  35,
    "DEEP_THINK_DOMAINS":      {"quant","quantum","finance","macro","coding","african_finance"},

    "MULTI_AGENT_THRESHOLD":   "standard",
    "ADVERSARIAL_THRESHOLD":   "deep",
    "CONFIDENCE_DECIMALS":     1,
    "MAX_REFINEMENT_ROUNDS":   2,
    "HYPOTHESIS_COUNT":        3,

    "FREE_DAILY_LIMIT": 100,
}

CRYPTO_ADDRESSES = {
    "BTC":  "bc1qrv6yr6e0mat96rvrc8smdf9rvu9rlp8xuk8new",
    "ETH":  "0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1",
    "USDC": "0x5bd39ad3e8b1cb01e7385958160fd9b2675d02d1",
    "SOL":  "59RMErx3YYKoqdSKeMoNG5FQUX1BNyw2Rh4VPdFfrTT1",
}
PRO_PRICE_CRYPTO = {"BTC":0.00025,"ETH":0.005,"USDC":15,"SOL":0.1}
PRO_PRICE_USD    = 15
EXPLORER_LINKS   = {
    "BTC":"https://www.blockchain.com/explorer/transactions/btc/",
    "ETH":"https://etherscan.io/tx/","USDC":"https://etherscan.io/tx/",
    "SOL":"https://solscan.io/tx/",
}

# ═══════════════════════════════════════════════════════════════
# CIRCUIT BREAKER — INTELLIGENCE UNTOUCHED
# ═══════════════════════════════════════════════════════════════
class CircuitBreaker:
    def __init__(self, name, timeout=5, max_failures=3, reset_timeout=60):
        self.name=name; self.timeout=timeout; self.max_failures=max_failures
        self.reset_timeout=reset_timeout; self.failures=0
        self.last_failure=None; self.state="closed"

    def call(self, func, *args, **kwargs):
        if self.state=="open":
            if self.last_failure and datetime.now()-self.last_failure > timedelta(seconds=self.reset_timeout):
                self.state="half-open"
            else:
                return None, f"{self.name} temporarily unavailable"
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(func, *args, **kwargs)
                result = future.result(timeout=self.timeout)
            if self.state=="half-open": self.state="closed"; self.failures=0
            return result, None
        except FutureTimeoutError:
            self.failures+=1; self.last_failure=datetime.now()
            if self.failures>=self.max_failures: self.state="open"
            return None, f"{self.name} timed out after {self.timeout}s"
        except Exception as e:
            self.failures+=1; self.last_failure=datetime.now()
            if self.failures>=self.max_failures: self.state="open"
            return None, f"{self.name} failed: {str(e)[:100]}"

web_search_cb  = CircuitBreaker("web_search",  timeout=3)
live_prices_cb = CircuitBreaker("live_prices", timeout=5)
news_cb        = CircuitBreaker("news",        timeout=8)
llm_cb         = CircuitBreaker("llm",         timeout=60, max_failures=3)

# ═══════════════════════════════════════════════════════════════
# ENTITY MEMORY — INTELLIGENCE UNTOUCHED
# ═══════════════════════════════════════════════════════════════
class EntityMemory:
    def __init__(self): self.entities = {}
    def extract_entities(self, text):
        entities = []
        for p in [r'(?:my|our|the)\s+(?:company|startup|business|firm)\s+(?:is\s+)?(?:called\s+)?["\']?([A-Z][A-Za-z0-9\s&]+(?:Inc|Ltd|LLC|Capital|Ventures|Technologies)?)["\']?',
                  r'(?:at|for|with)\s+([A-Z][A-Za-z0-9]+(?:\s(?:Inc|Ltd|LLC|Capital|Technologies|Bank|Group|Holdings)))']:
            for m in re.findall(p,text): entities.append({"type":"company","name":m.strip()})
        for loc in ["Lagos","Accra","Nairobi","Johannesburg","Cairo","Abuja","London","New York","Dubai","Singapore","Ghana","Nigeria","Kenya","South Africa","Egypt"]:
            if loc.lower() in text.lower(): entities.append({"type":"location","name":loc})
        for ind in ["fintech","agritech","healthtech","edtech","logistics","payments","banking","insurance","investment","real estate","agriculture","energy","telecom","media"]:
            if ind.lower() in text.lower(): entities.append({"type":"industry","name":ind})
        return entities
    def add_entities(self, entities):
        for e in entities:
            k=f"{e['type']}:{e['name'].lower()}"
            if k not in self.entities: self.entities[k]={"type":e["type"],"name":e["name"],"first_seen":datetime.now().isoformat(),"mention_count":1}
            else: self.entities[k]["mention_count"]+=1; self.entities[k]["last_seen"]=datetime.now().isoformat()
    def get_summary(self):
        if not self.entities: return ""
        bt=defaultdict(list)
        for k,e in self.entities.items(): bt[e["type"]].append(e)
        lines=["USER ENTITIES:"]
        for et,es in bt.items():
            top=sorted(es,key=lambda x:x["mention_count"],reverse=True)[:3]
            lines.append(f"  {et.capitalize()}: {', '.join(e['name'] for e in top)}")
        return "\n".join(lines)

entity_memory = EntityMemory()

# ═══════════════════════════════════════════════════════════════
# GOAL TRACKER — INTELLIGENCE UNTOUCHED
# ═══════════════════════════════════════════════════════════════
class GoalTracker:
    def __init__(self): self.goals=load_goals()
    def add_goal(self,d,c="general"):
        g={"id":str(uuid.uuid4()),"description":d,"category":c,"status":"active",
           "created":datetime.now().isoformat(),"progress":[],"priority":"medium",
           "current":0,"target":"","deadline":""}
        self.goals.append(g); save_goals(self.goals); return g
    def get_active_goals(self): return [g for g in self.goals if g.get("status")=="active"]
    def get_context_for_ai(self):
        a=self.get_active_goals()
        if not a: return ""
        lines=["USER GOALS:"]
        for g in a[:5]:
            da=(datetime.now()-datetime.fromisoformat(g["created"])).days
            lines.append(f"  • {g['description']} ({da}d ago)")
        return "\n".join(lines)

goal_tracker = GoalTracker()

# ═══════════════════════════════════════════════════════════════
# ELITE DOMAIN ROUTER — INTELLIGENCE UNTOUCHED
# ═══════════════════════════════════════════════════════════════
class DomainRouter:
    TRADING = [r'\b(swing trade|day trade|scalp|entry price|stop.?loss|take.?profit|tp|sl)\b',r'\b(when (?:to|should i) (?:buy|sell)|is now a good time|buy signal|sell signal)\b']
    CODING = [r'```',r'\bdef\s+\w+\s*\(',r'class\s+\w+.*:',r'\b(write|implement|build|create|code|refactor|debug|optimize|review)\b.*\b(function|class|api|algorithm|script|program|service|module|library)\b',r'\b(python|numpy|pandas|rust|go|golang|java|typescript|javascript|sql|c\+\+|c#|swift|kotlin)\b',r'\b(big.?o|time complexity|space complexity|algorithm|data structure|design pattern|architecture|microservice|api|rest|graphql|grpc)\b']
    QUANT = [r'\b(monte carlo|black.scholes|ito.?lemma|stochastic|option pricing|greeks|delta|gamma|theta|vega|rho)\b',r'\b(var|cvar|expected shortfall|risk management|markowitz|sharpe|sortino|calmar|information ratio)\b',r'\b(backtest|factor model|alpha|beta|capm|fama.french|momentum|mean reversion|pairs trading|stat arb)\b']
    QUANTUM = [r'\b(quantum|qubit|qiskit|qaoa|vqe|entanglement|superposition|quantum circuit|quantum gate|bell state|bloch sphere)\b']
    AFRICAN = [r'\b(african|africa|nigeria|ghana|kenya|south africa|ethiopia|egypt|morocco|tanzania|uganda|angola|ivory coast|senegal)\b',r'\b(naira|rand|cedi|shilling|pound|dirham|franc|birr|kwanza|ngn|zar|kes|egp|mad|xof)\b',r'\b(ngx|jse|gse|nse|brvm|egx|masi|afcfta|ecowas|sadc|au|mtn|dangote|ecobank|zenith|gtco|equity bank|safaricom)\b']
    MACRO = [r'\b(gdp|gnp|recession|inflation|deflation|stagflation|fiscal policy|monetary policy|central bank|fed|ecb|boj|pboc|boe|rba|rbnz|boc|snb|riksbank|norges bank|banxico|bcb|cbrt|rbi|sarb|cbk|bog|cbn|bceao|beac)\b',r'\b(interest rate|yield curve|quantitative easing|tightening|balance sheet|money supply|m2|credit cycle|business cycle|fomc|federal reserve|jerome powell|christine lagarde|andrew bailey|kuroda|ueda)\b',r'\b(taylor rule|phillips curve|is.lm|dsge|hansonian|monetarist|mmt|fiscal dominance|debt monetization)\b']
    FINANCE = [r'\b(revenue|earnings|ebitda|ebit|fcf|free cash flow|valuation|pe ratio|pb ratio|ev.?ebitda|dcf|wacc|irr|npv)\b',r'\b(stock|bond|equity|debt|credit|yield|spread|ipo|m&a|acquisition|merger|private equity|venture capital)\b',r'\b(bitcoin|ethereum|crypto|btc|eth|defi|nft|blockchain|web3|dao|staking|yield farming)\b']
    MATH = [r'\b(prove|proof|theorem|lemma|corollary|derive|derivation|integral|derivative|gradient|hessian|jacobian)\b',r'\b(differential equation|ode|pde|fourier|laplace|linear algebra|eigenvalue|eigenvector|svd|matrix decomposition)\b']
    SOCIAL = [r'\b(hello|hi|hey|how are you|good morning|good afternoon|good evening|happy sunday|happy monday|happy tuesday|happy wednesday|happy thursday|happy friday|happy saturday)\b',r'\b(how.s it going|what.s up|how do you do|nice to meet you)\b',r'\b(thank you|thanks|appreciate|grateful|you.re amazing|great job)\b',r'\b(i.m feeling|i feel|i am feeling|feeling kinda|feeling a bit|been feeling)\b',r'\b(tired|sad|lonely|stressed|anxious|worried|overwhelmed|happy|excited)\b']
    CAPABILITIES = [r'\b(what can you do|capabilities|features|what are you|tell me about yourself|who are you|what do you do|how do you work|how can you help)\b']

    @classmethod
    def classify(cls, q):
        q_low = q.lower()
        for p in cls.SOCIAL:
            if re.search(p, q_low): return "general"
        for p in cls.CAPABILITIES:
            if re.search(p, q_low): return "general"
        for p in cls.TRADING:
            if re.search(p, q_low): return "trading_refuse"
        for p in cls.MATH:
            if re.search(p, q_low): return "math"
        for p in cls.CODING:
            if re.search(p, q_low): return "coding"
        for p in cls.QUANT:
            if re.search(p, q_low): return "quant"
        for p in cls.QUANTUM:
            if re.search(p, q_low): return "quantum"
        for p in cls.AFRICAN:
            if re.search(p, q_low): return "african_finance"
        for p in cls.MACRO:
            if re.search(p, q_low): return "macro"
        for p in cls.FINANCE:
            if re.search(p, q_low): return "finance"
        return "general"

# ═══════════════════════════════════════════════════════════════
# QUERY COMPLEXITY ANALYZER — INTELLIGENCE UNTOUCHED
# ═══════════════════════════════════════════════════════════════
class QueryComplexityAnalyzer:
    DEEP_PATTERNS = [r'\b(derive|prove|demonstrate|rigorously|formally|mathematically)\b',r'\b(mechanism|causal(ity|ly)?|why exactly|root cause|underlying)\b',r'\b(optimize|maximiz|minimiz|equilibrium|optimal|pareto)\b',r'\b(model|simulation|backtest|regression|forecast|predict)\b',r'\b(comprehensive|exhaustive|thorough|in.depth|detailed|full analysis)\b',r'\b(compare|contrast|versus|vs\.?|trade.?off|pros and cons)\b',r'\b(design|architect|system|framework|infrastructure|pipeline)\b',r'\?.*\?']
    SIMPLE_PATTERNS = [r'^(what is|what are|define|who is|when was|where is)\b',r'^(how much|how many|what does|does)\b']

    @classmethod
    def grade(cls, query, domain):
        words = len(query.split())
        q_low = query.lower()
        for p in cls.SIMPLE_PATTERNS:
            if re.search(p, q_low) and words < 15: return "simple"
        if words < CONFIG["SIMPLE_WORD_THRESHOLD"]: return "simple"
        deep_score = 0
        for p in cls.DEEP_PATTERNS:
            if re.search(p, q_low): deep_score += 1
        if domain in CONFIG["DEEP_THINK_DOMAINS"]: deep_score += 1
        if words > CONFIG["COMPLEX_WORD_THRESHOLD"]: deep_score += 1
        if "step by step" in q_low or "walk me through" in q_low: deep_score += 2
        if deep_score >= 3: return "deep"
        if deep_score >= 1 or words > 20: return "standard"
        return "simple"

# ═══════════════════════════════════════════════════════════════
# ELITE REASONING ENGINE — INTELLIGENCE UNTOUCHED
# ═══════════════════════════════════════════════════════════════
class EliteReasoningEngine:
    SOCRATIC_PROMPT = """You are the world's most rigorous reasoning architect.
QUERY: {query} | DOMAIN: {domain} | COMPLEXITY: {complexity}
Output ONLY valid JSON with: core_epistemic_question, hidden_assumptions, atomic_sub_problems, competing_hypotheses, critical_distinctions, base_rate_anchors, second_order_effects, potential_reasoning_failures, confidence_limiting_factors, elite_answer_structure, domain_specific_frameworks."""

    ADVERSARIAL_CRITIC_PROMPT = """Brutally critique this answer. QUESTION: {question} | ANSWER: {answer}
Output ONLY valid JSON with: verdict (WEAK|ACCEPTABLE|STRONG), overall_score (1-10), critical_flaws, missing_insights, confidence_issues, strongest_counterargument, what_an_expert_would_add, one_sentence_improvement."""

    ELITE_SYNTHESIS_PROMPT = """Synthesize FINAL ELITE ANSWER. QUESTION: {question} | SCAFFOLD: {scaffold} | CRITIQUE: {critique} | INITIAL: {initial_answer}
Fix every HIGH-severity flaw. Add missing insights. Respond to strongest counterargument. Do not mention this is refined."""

    @classmethod
    def decompose(cls, query, domain, complexity, is_pro):
        try:
            prompt = cls.SOCRATIC_PROMPT.format(query=query, domain=domain, complexity=complexity)
            r, err = llm_cb.call(call_llm, [{"role":"system","content":"Output only valid JSON."},{"role":"user","content":prompt}], is_pro=is_pro, use_specific_model=CONFIG["PLANNER_MODEL"])
            if err: return {}
            m = re.search(r'\{.*\}', r, re.DOTALL)
            if m: return json.loads(m.group())
        except: pass
        return {}

    @classmethod
    def critique(cls, question, answer, is_pro):
        try:
            prompt = cls.ADVERSARIAL_CRITIC_PROMPT.format(question=question, answer=answer[:3000])
            r, err = llm_cb.call(call_llm, [{"role":"system","content":"Output only valid JSON."},{"role":"user","content":prompt}], is_pro=is_pro, use_specific_model=CONFIG["CRITIC_MODEL"])
            if err: return {}
            m = re.search(r'\{.*\}', r, re.DOTALL)
            if m: return json.loads(m.group())
        except: pass
        return {}

    @classmethod
    def synthesize_elite(cls, question, scaffold_text, critique_data, initial_answer, is_pro):
        try:
            critique_text = json.dumps(critique_data, indent=2) if critique_data else "None"
            prompt = cls.ELITE_SYNTHESIS_PROMPT.format(question=question, scaffold=scaffold_text[:2000], critique=critique_text[:1500], initial_answer=initial_answer[:3000])
            r, err = llm_cb.call(call_llm, [{"role":"system","content":"You are an elite expert."},{"role":"user","content":prompt}], is_pro=is_pro, use_specific_model=CONFIG["REFINER_MODEL"])
            return r if not err else initial_answer
        except: return initial_answer

    @classmethod
    def build_scaffold_context(cls, plan):
        if not plan: return ""
        lines = ["=== ELITE REASONING SCAFFOLD ==="]
        if plan.get("core_epistemic_question"): lines.append(f"CORE: {plan['core_epistemic_question']}")
        if plan.get("hidden_assumptions"): lines.append("HIDDEN ASSUMPTIONS: " + "; ".join(plan["hidden_assumptions"]))
        if plan.get("competing_hypotheses"):
            lines.append("COMPETING HYPOTHESES:")
            for h in plan["competing_hypotheses"]: lines.append(f"  H: {h.get('hypothesis','')} [P≈{h.get('prior_probability','?')}]")
        if plan.get("critical_distinctions"): lines.append("CRITICAL DISTINCTIONS: " + "; ".join(plan["critical_distinctions"]))
        if plan.get("base_rate_anchors"): lines.append("BASE RATES: " + "; ".join(plan["base_rate_anchors"]))
        lines.append("=== END SCAFFOLD ===")
        return "\n".join(lines)

# ═══════════════════════════════════════════════════════════════
# ELITE SELF-EVALUATOR — INTELLIGENCE UNTOUCHED
# ═══════════════════════════════════════════════════════════════
class EliteSelfEvaluator:
    @staticmethod
    def evaluate(q, a, domain="general", is_pro=False):
        try:
            prompt = f"""Peer reviewer. QUESTION: {q} | ANSWER: {a[:3000]} | DOMAIN: {domain}
Score 1.0-5.0. Return ONLY valid JSON with: accuracy, completeness, logical_rigor, evidence_quality, calibration, intellectual_honesty, practical_utility, domain_depth, second_order_thinking, communication_clarity, novel_insight, adversarial_robustness, confidence, weakest_dimension, key_weakness, missing_insight, highest_impact_improvement, expert_would_say, brief_justification."""
            r, err = llm_cb.call(call_llm, [{"role":"system","content":"Output only valid JSON."},{"role":"user","content":prompt}], is_pro=is_pro, use_specific_model=CONFIG["CRITIC_MODEL"])
            if err: return EliteSelfEvaluator._defaults()
            m = re.search(r'\{.*\}', r, re.DOTALL)
            if m: return json.loads(m.group())
        except: pass
        return EliteSelfEvaluator._defaults()

    @staticmethod
    def _defaults():
        return {"accuracy":3.0,"completeness":3.0,"logical_rigor":3.0,"evidence_quality":2.5,"calibration":3.0,"intellectual_honesty":3.0,"practical_utility":3.0,"domain_depth":3.0,"second_order_thinking":2.5,"communication_clarity":3.5,"novel_insight":2.5,"adversarial_robustness":2.5,"confidence":3.0,"weakest_dimension":"evidence_quality","key_weakness":"N/A","missing_insight":"N/A","highest_impact_improvement":"N/A","expert_would_say":"N/A","brief_justification":"Baseline evaluation."}

# ═══════════════════════════════════════════════════════════════
# COMPUTATIONAL ENGINE — INTELLIGENCE UNTOUCHED
# ═══════════════════════════════════════════════════════════════
class ComputationalEngine:
    @staticmethod
    def query_wolfram(expression):
        if not CONFIG.get("WOLFRAM_APP_ID"): return None
        try:
            r = requests.get("http://api.wolframalpha.com/v2/query", params={"input":expression,"appid":CONFIG["WOLFRAM_APP_ID"],"output":"json","format":"plaintext"}, timeout=10)
            if r.status_code != 200: return None
            pods = r.json().get("queryresult",{}).get("pods",[])
            results = []
            for pod in pods[:4]:
                for sub in pod.get("subpods",[]):
                    text = sub.get("plaintext","").strip()
                    if text and len(text) > 1: results.append(f"{pod.get('title','')}: {text}")
            return "\n".join(results) if results else None
        except: return None

    @staticmethod
    def execute_code(code, timeout=20):
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f: f.write(code); tmp = f.name
            try:
                p = subprocess.run(["python3", tmp], capture_output=True, text=True, timeout=timeout, env={**os.environ,"PYTHONPATH":os.getcwd()})
                return {"stdout":p.stdout,"stderr":p.stderr,"returncode":p.returncode,"success":p.returncode==0}
            except subprocess.TimeoutExpired: return {"success":False,"stderr":"Timeout (20s)","stdout":"","returncode":-1}
            finally: os.unlink(tmp)
        except Exception as e: return {"success":False,"stderr":str(e),"stdout":"","returncode":-1}

# ═══════════════════════════════════════════════════════════════
# ELITE PERSONAS — INTELLIGENCE FULLY PRESERVED
# ═══════════════════════════════════════════════════════════════

FIVE_STEP_PROTOCOL = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
5-STEP INTELLIGENCE PROTOCOL — APPLIED TO EVERY RESPONSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1: IDENTIFY MISSING INFORMATION
STEP 2: STATE ASSUMPTIONS EXPLICITLY
STEP 3: SEPARATE FACTS FROM ESTIMATES
STEP 4: FLAG UNCERTAINTY with explicit confidence levels
STEP 5: PROCEED WITH RECOMMENDATIONS grounded in the analysis
"""

GLOBAL_FINANCE_KNOWLEDGE = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GLOBAL CENTRAL BANK INTELLIGENCE — MAJOR INSTITUTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FEDERAL RESERVE (Fed) — United States
• Dual mandate: maximum employment + price stability (2% inflation target)
• Key tools: Federal Funds Rate, IOER, ON RRP, quantitative easing/tightening
• FOMC meets 8 times/year; dot plot released quarterly (Mar/Jun/Sep/Dec)
• Current framework: Flexible Average Inflation Targeting (FAIT), adopted 2020
• Balance sheet: ~$7.4T (down from ~$9T peak); QT pace ~$60B/month
• Chair: Jerome Powell (term ends May 2026)
• Key indicators watched: Core PCE, non-farm payrolls, JOLTS, CPI, wage growth
• Transmission mechanism: FF rate → Treasury yields → mortgage rates → corp bonds → equities → USD

EUROPEAN CENTRAL BANK (ECB) — Eurozone (20 member states)
• Primary mandate: Price stability (2% inflation target, symmetric)
• Key tools: Main Refinancing Operations (MRO), Deposit Facility Rate, Marginal Lending Facility
• Governing Council meets every 6 weeks; accounts published 4 weeks after
• Transmission Protection Instrument (TPI) — anti-fragmentation tool, activated 2022
• PEPP reinvestments ended; APP portfolio declining
• President: Christine Lagarde (term ends 2027)
• Key challenge: Heterogeneous inflation across member states (Germany vs Italy spreads)
• Eurozone fragmentation risk: BTP-Bund spread as key indicator

BANK OF ENGLAND (BoE) — United Kingdom
• Mandate: 2% CPI inflation target (remitted by HM Treasury annually)
• Key tools: Bank Rate, Asset Purchase Facility (APF), Term Funding Schemes
• MPC meets 8 times/year; minutes published simultaneously with decision
• Governor: Andrew Bailey
• APF active unwind: ~£100B reduction annually through maturities and active sales
• Key indicators: CPI (headline + core), wage growth (AWE), services inflation, labour market tightness

BANK OF JAPAN (BoJ) — Japan
• Mandate: Price stability (2% target) + financial system stability
• Key tools: Short-term Policy Rate, Yield Curve Control (YCC), ETF/J-REIT purchases
• Governor: Kazuo Ueda (took office April 2023)
• Historic shift: March 2024 ended negative rates (-0.1% → 0-0.1%); ended YCC framework
• Decades of deflationary pressure; wage-price spiral now emerging
• Key risk: JGB market stability with rising yields; ¥1,200T government debt (260% GDP)

PEOPLE'S BANK OF CHINA (PBoC) — China
• Mandate: Currency stability, financial stability, economic growth, price stability
• Key tools: Loan Prime Rate (LPR), Reserve Requirement Ratio (RRR), Medium-term Lending Facility (MLF)
• Governor: Pan Gongsheng
• Managed float: CNY trading band ±2% around daily fix
• Current challenges: Property sector deleveraging, local government debt (~$9T), deflationary pressure
• Stimulus approach: Targeted RRR cuts, PSL (Pledged Supplementary Lending), infrastructure spending
• Capital controls limit hot money flows; significant FX reserves (~$3.2T)

RESERVE BANK OF INDIA (RBI) — India
• Mandate: 4% CPI inflation (±2% band) + growth support (flexible inflation targeting since 2016)
• Governor: Shaktikanta Das
• Key tools: Repo Rate, Standing Deposit Facility (SDF), Marginal Standing Facility (MSF)
• Fastest-growing major economy (~7% GDP growth); young demographic dividend
• Rupee management: RBI actively intervenes in FX market; ~$600B reserves
• Digital Rupee (e₹) pilot launched 2022 — wholesale and retail CBDC

BANK OF CANADA (BoC) — Canada
• Mandate: 2% inflation target (renewed every 5 years with Government of Canada)
• Governor: Tiff Macklem
• Key tools: Overnight Rate, Government Bond Purchase Program (QE), BAX market
• Commodity-sensitive economy (oil exports ~20% of export revenue)
• Housing market sensitivity: ~70% household debt-to-GDP; mortgage renewal wall 2024-2026

RESERVE BANK OF AUSTRALIA (RBA) — Australia
• Mandate: Price stability (2-3% CPI target), full employment, economic prosperity
• Governor: Michele Bullock
• Monthly meetings (changed from 11/year in 2024)
• Commodity exporter: Iron ore, coal, LNG — highly exposed to China demand cycle
• Housing market: Variable-rate mortgages dominant (~85% of mortgages)

SWISS NATIONAL BANK (SNB) — Switzerland
• Mandate: Price stability (<2% CPI) + considering economic developments
• Chairman: Thomas Jordan
• Unique tool: FX interventions (purchases/sales of foreign currencies)
• Safe-haven currency: CHF appreciates during global risk-off episodes
• Negative rates experiment (2015-2022); first major CB to exit

CENTRAL BANK OF NIGERIA (CBN) — Nigeria
• Mandate: Price stability, naira stability, financial system stability
• Governor: Olayemi Cardoso
• Key reforms: FX market unification (June 2023), removal of fuel subsidy, inflation targeting transition
• Monetary Policy Rate (MPR) used as primary tool; Cash Reserve Ratio (CRR) historically high (32.5-45%)
• Inflation: ~33% (2024), driven by FX pass-through, food supply shocks, subsidy removal
• Key challenges: Naira volatility, multiple exchange rate unification, foreign investor confidence

SOUTH AFRICAN RESERVE BANK (SARB) — South Africa
• Mandate: Price stability (3-6% CPI target range) — constitutional independence
• Governor: Lesetja Kganyago
• Key tools: Repo Rate, open market operations
• Most independent African central bank with strong institutional credibility
• Rand as EM proxy currency; heavily influenced by global risk appetite and commodity prices
"""

ELITE_CORE = FIVE_STEP_PROTOCOL + GLOBAL_FINANCE_KNOWLEDGE + """
╔══════════════════════════════════════════════════════════════╗
║          CAPITAN AI · ELITE INTELLIGENCE CORE v5.0          ║
║                   Sovereign AI Technologies                  ║
╚══════════════════════════════════════════════════════════════╝

ELITE REASONING PRINCIPLES:
1. MECHANISM FIRST
2. CALIBRATED CONFIDENCE
3. EVIDENCE TRACEABILITY
4. STEEL-MAN OPPONENTS
5. QUANTIFY
6. SECOND-ORDER THINKING
7. AFRICAN MARKET DEPTH
8. INTELLECTUAL HONESTY

COMMUNICATION: MATURE · AUTHENTIC · SIMPLE · NO FORCED WARMTH
"""

REFINED_GENERAL = """You are CAPITAN AI — a direct, knowledgeable, and genuinely helpful intelligence operating at the highest standard.

CORE IDENTITY: Trusted expert colleague. Warm through competence. Earn trust through accuracy.

RESPONSE ARCHITECTURE:
1. DIRECT ANSWER FIRST — most important sentence leads
2. 5-STEP PROTOCOL EMBEDDED throughout
3. SPECIFIC, ACTIONABLE DETAILS in scannable format
4. CALIBRATED CLARITY on confidence
5. NEXT STEP handoff

GLOBAL FINANCE DEPTH: You have comprehensive knowledge of all major central banks (Fed, ECB, BoJ, BoE, PBoC, RBI, BoC, RBA, SNB, RBNZ, CBN, SARB, and others), their policy frameworks, key officials, balance sheet mechanics, and transmission mechanisms. Apply this knowledge when analyzing macro conditions.

CAPABILITIES: Text-optimized intelligence covering Finance, African Markets, Coding, Quantitative Analysis, Quantum Computing, and General Research.
"""

PERSONAS = {
    "trading_refuse": ELITE_CORE + """DOMAIN: TRADING SIGNALS — REFUSAL POLICY.
No entry prices, stop-losses, or take-profit levels. Apply 5-step protocol. Redirect to structural analysis.""",
    "coding": ELITE_CORE + """DOMAIN: SOFTWARE ENGINEERING. Principal Engineer standard.
Apply 5-step protocol. Production-quality code with type hints, docstrings, tests, complexity analysis.""",
    "quant": ELITE_CORE + """DOMAIN: QUANTITATIVE FINANCE. Quant Research Director standard.
Apply 5-step protocol. Assumption audit, mathematical derivation, vectorised implementation. NEVER entry/exit signals.""",
    "quantum": ELITE_CORE + """DOMAIN: QUANTUM COMPUTING. Quantum Principal Scientist standard.
Apply 5-step protocol. Dirac notation, circuit diagrams, NISQ-era realism, Qiskit/Cirq code.""",
    "finance": ELITE_CORE + """DOMAIN: GLOBAL FINANCE & INVESTMENT. Goldman Sachs MD + Bridgewater standard.
Apply 5-step protocol. Use global central bank knowledge for macro regime analysis.
Dual valuation, probability-weighted scenarios, catalyst map. NEVER entry/exit levels.""",
    "african_finance": ELITE_CORE + """DOMAIN: AFRICAN FINANCIAL MARKETS. Africa's Premier Finance Intelligence.
Apply 5-step protocol. Leverage CBN, SARB, BoG, CBK knowledge. Sovereign macro, FX risk architecture, Africa-adjusted valuations. NEVER entry/exit levels.""",
    "macro": ELITE_CORE + """DOMAIN: GLOBAL MACRO ECONOMICS. Global Macro PM standard.
Apply 5-step protocol. Use comprehensive central bank knowledge. Regime identification, CB reaction function analysis, cross-asset implications. NEVER entry/exit levels.""",
    "math": ELITE_CORE + """DOMAIN: PURE & APPLIED MATHEMATICS. Research Mathematician standard.
Apply 5-step protocol. Full derivations, rigorous proofs, SymPy verification, edge case analysis.""",
    "general": ELITE_CORE + REFINED_GENERAL,
}

# ═══════════════════════════════════════════════════════════════
# LLM CALLERS — MULTI-API FALLBACK (OpenRouter → OpenAI → Local)
# ═══════════════════════════════════════════════════════════════
def _get_api_key():
    key = CONFIG.get("OPENROUTER_KEY", "").strip()
    if key and len(key) > 20: return key
    for name in ["OPENROUTER_API_KEY", "OPENROUTER_KEY", "openrouter_api_key"]:
        val = os.environ.get(name, "").strip()
        if val and len(val) > 20: return val
    try:
        if "OPENROUTER_API_KEY" in st.secrets:
            val = str(st.secrets["OPENROUTER_API_KEY"]).strip()
            if val and len(val) > 20: return val
        if "OPENROUTER_KEY" in st.secrets:
            val = str(st.secrets["OPENROUTER_KEY"]).strip()
            if val and len(val) > 20: return val
        for key_name in st.secrets:
            if "openrouter" in key_name.lower() or "open_router" in key_name.lower():
                val = str(st.secrets[key_name]).strip()
                if val and len(val) > 20: return val
    except Exception: pass
    try:
        from dotenv import load_dotenv; load_dotenv()
        for name in ["OPENROUTER_API_KEY", "OPENROUTER_KEY"]:
            val = os.environ.get(name, "").strip()
            if val and len(val) > 20: return val
    except: pass
    return ""

def call_openai_direct(messages, model="gpt-3.5-turbo"):
    """Fallback to OpenAI directly if OpenRouter fails"""
    api_key = CONFIG.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    
    try:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        # Convert messages to OpenAI format
        openai_messages = []
        for msg in messages:
            openai_messages.append({"role": msg["role"], "content": msg["content"]})
        
        payload = {
            "model": model,
            "messages": openai_messages,
            "temperature": 0.2,
            "max_tokens": 1024
        }
        
        r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=30)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
    except:
        pass
    return None

def call_local_fallback(messages):
    """Ultimate fallback - simulated response when no APIs work"""
    # Extract user's last message
    user_msg = ""
    for msg in reversed(messages):
        if msg["role"] == "user":
            user_msg = msg["content"]
            break
    
    # Provide a helpful response based on context
    if any(word in user_msg.lower() for word in ["hello", "hi", "hey"]):
        return "Hello! I'm CAPITAN AI. I'm currently operating in offline mode because my API connections are unavailable. Please check your OpenRouter or OpenAI API keys in Streamlit Secrets to enable full AI capabilities."
    elif any(word in user_msg.lower() for word in ["help", "what can you", "capabilities"]):
        return """I'm CAPITAN AI - an elite intelligence system for Finance, African Markets, Quant, and Coding.

**Current Status:** Offline mode (API keys needed)

**To activate full capabilities:**
1. Add `OPENROUTER_API_KEY` to Streamlit Secrets
2. Or add `OPENAI_API_KEY` as fallback
3. Refresh the page

**My capabilities when online:**
- Advanced reasoning with 5-step protocol
- Real-time market data and news
- Code execution and analysis
- Central bank intelligence
- African market depth
- Crypto payment verification

For now, I can still provide general information using my built-in knowledge. What would you like to know?"""
    else:
        return f"""I need API access to properly answer: "{user_msg[:100]}..."

**Quick Setup:**
1. Get a free API key from [OpenRouter](https://openrouter.ai/keys)
2. Add to Streamlit Secrets as `OPENROUTER_API_KEY`
3. Or use `OPENAI_API_KEY` as fallback

Once configured, I'll have full access to all models and capabilities. You can also upgrade to Pro for premium features like Claude 3.5 Sonnet and GPT-4o.

Is there anything I can help with using my current knowledge?"""

def call_llm(messages, is_pro=False, use_specific_model=None):
    """Call LLM with multi-API fallback - OpenRouter first, then OpenAI, then local fallback"""
    
    # First try: OpenRouter
    api_key = _get_api_key()
    if api_key:
        if use_specific_model: 
            models = [use_specific_model]
        elif is_pro: 
            models = CONFIG["PRO_MODELS"] + CONFIG["FREE_MODELS"]
        else: 
            models = CONFIG["FREE_MODELS"]
        
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        
        for model in models:
            try:
                r = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions", 
                    headers=headers, 
                    json={"model": model, "messages": messages, "temperature": 0.2, "max_tokens": 1024}, 
                    timeout=30
                )
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"]
                if r.status_code == 401:
                    break  # Auth error, try OpenAI
            except:
                continue
    
    # Second try: OpenAI Direct
    openai_result = call_openai_direct(messages)
    if openai_result:
        return openai_result
    
    # Final fallback: Local simulated response
    return call_local_fallback(messages)

def call_llm_stream_fast(messages, is_pro=False, model_override=None):
    """TRUE STREAMING with multi-API fallback"""
    
    # First try: OpenRouter
    api_key = _get_api_key()
    if api_key:
        if model_override: 
            models = [model_override]
        elif is_pro: 
            models = CONFIG["PRO_MODELS"] + CONFIG["FREE_MODELS"]
        else: 
            models = CONFIG["FREE_MODELS"]
        
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        
        for model in models:
            try:
                r = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions", 
                    headers=headers,
                    json={"model": model, "messages": messages, "temperature": 0.2, "max_tokens": 1024, "stream": True},
                    timeout=180, 
                    stream=True
                )
                if r.status_code != 200:
                    continue
                for line in r.iter_lines():
                    if line:
                        line = line.decode("utf-8")
                        if line.startswith("data: "):
                            d = line[6:]
                            if d == "[DONE]": 
                                return
                            try:
                                delta = json.loads(d).get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if delta: 
                                    yield delta
                            except: 
                                continue
                return
            except:
                continue
    
    # Second try: OpenAI Direct (streaming not fully supported, so we get full response and yield it)
    openai_result = call_openai_direct(messages)
    if openai_result:
        yield openai_result
        return
    
    # Final fallback: Local simulated response
    fallback_response = call_local_fallback(messages)
    yield fallback_response

# ═══════════════════════════════════════════════════════════════
# TOOLS — INTELLIGENCE UNTOUCHED
# ═══════════════════════════════════════════════════════════════
def web_search(query):
    if not CONFIG["SERPER_KEY"]: return ""
    def _s():
        r = requests.post("https://google.serper.dev/search", headers={"X-API-KEY":CONFIG["SERPER_KEY"],"Content-Type":"application/json"}, json={"q":query,"num":6}, timeout=3)
        return "\n\n".join([f"[{i+1}] {x['title']}\n{x['snippet']}" for i,x in enumerate(r.json().get("organic",[]))])
    result, err = web_search_cb.call(_s)
    return result if not err else ""

def _fetch_yahoo_batch(symbols):
    if not symbols: return {}
    try:
        r = requests.get("https://query1.finance.yahoo.com/v7/finance/quote", params={"symbols":",".join(symbols),"fields":"regularMarketPrice,regularMarketPreviousClose,currency"}, timeout=5, headers={"User-Agent":"Mozilla/5.0"})
        if r.status_code != 200: return {}
        results = {}
        for item in r.json().get("quoteResponse",{}).get("result",[]):
            sym=item.get("symbol",""); pr=item.get("regularMarketPrice"); pv=item.get("regularMarketPreviousClose")
            if pr and pv and pr>0: results[sym]={"price":pr,"prev":pv,"change_pct":round(((pr-pv)/pv)*100,2),"currency":item.get("currency","USD")}
        return results
    except: return {}

@st.cache_data(ttl=30, show_spinner=False)
def get_live_prices():
    results = {}
    tickers = {
        "stocks":{"^GSPC":"S&P 500","^IXIC":"NASDAQ","^DJI":"Dow Jones","^FTSE":"FTSE 100","^N225":"Nikkei 225","AAPL":"Apple","MSFT":"Microsoft","NVDA":"Nvidia","TSLA":"Tesla","AMZN":"Amazon","GOOGL":"Alphabet","META":"Meta","JPM":"JPMorgan","GS":"Goldman Sachs"},
        "african_stocks":{"DANGCEM.LG":"Dangote Cement","MTNN.LG":"MTN Nigeria","GUARANTY.LG":"GTCO","ZENITHBANK.LG":"Zenith Bank","ACCESS.LG":"Access Holdings","^NGSEINDX":"NGX All-Share","NPN.JO":"Naspers","MTN.JO":"MTN Group","SBK.JO":"Standard Bank","FSR.JO":"FirstRand","SOL.JO":"Sasol","^JALSH":"JSE All-Share","MTNGH.GH":"MTN Ghana","^GSE":"GSE Composite","SNTS.BR":"Sonatel","^BRVM":"BRVM Composite","SCOM.NR":"Safaricom","EQTY.NR":"Equity Group","COMI.CA":"Commercial Int'l Bank","^CASE30":"EGX 30","ATW.CS":"Attijariwafa Bank","^MASI":"MASI"},
        "commodities":{"GC=F":"Gold","SI=F":"Silver","CL=F":"Crude Oil WTI","BZ=F":"Brent Crude","NG=F":"Natural Gas","HG=F":"Copper","PL=F":"Platinum","CC=F":"Cocoa","KC=F":"Coffee"},
        "forex":{"EURUSD=X":"EUR/USD","GBPUSD=X":"GBP/USD","USDJPY=X":"USD/JPY","USDCHF=X":"USD/CHF","AUDUSD=X":"AUD/USD","USDCAD=X":"USD/CAD","USDGHS=X":"USD/GHS (Cedi)","USDNGN=X":"USD/NGN (Naira)","USDZAR=X":"USD/ZAR (Rand)","USDKES=X":"USD/KES (Shilling)","USDEGP=X":"USD/EGP (Pound)","USDMAD=X":"USD/MAD (Dirham)","USDXOF=X":"USD/XOF (CFA Franc)","USDETB=X":"USD/ETB (Birr)","USDTZS=X":"USD/TZS (Shilling)","USDUGX=X":"USD/UGX (Shilling)"},
    }
    all_syms = [sym for grp in tickers.values() for sym in grp.keys()]
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(_fetch_yahoo_batch, all_syms[i:i+20]) for i in range(0,len(all_syms),20)]
        yd = {}
        for f in as_completed(futures):
            try: yd.update(f.result())
            except: pass
    for grp,t in tickers.items():
        for sym,name in t.items():
            if sym in yd: d=yd[sym]; results[name]={"price":d["price"],"change_pct":d["change_pct"],"category":grp,"currency":d.get("currency","USD")}
    try:
        cids={"Bitcoin":"bitcoin","Ethereum":"ethereum","Solana":"solana","Cardano":"cardano","Ripple":"ripple","BNB":"binancecoin","USDT":"tether","USDC":"usd-coin"}
        r=requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(cids.values())}&vs_currencies=usd&include_24hr_change=true",timeout=8)
        if r.status_code==200:
            for n,cid in cids.items():
                coin=r.json().get(cid,{})
                if coin.get("usd"): results[n]={"price":coin["usd"],"change_pct":round(coin.get("usd_24h_change",0),2),"category":"crypto"}
    except: pass
    return results

@st.cache_data(ttl=300, show_spinner=False)
def fetch_financial_news():
    items=[]
    for url,src in [("https://feeds.content.dowjones.io/public/rss/mw_topstories","MarketWatch"),("https://finance.yahoo.com/news/rssindex","Yahoo Finance")]:
        try:
            r=requests.get(url,timeout=8,headers={"User-Agent":"Mozilla/5.0"})
            if r.status_code==200:
                for item in ET.fromstring(r.content).findall('.//item')[:5]:
                    t=item.find('title')
                    if t is not None and t.text and len(t.text)>10: items.append({"title":t.text.strip(),"source":src})
        except: continue
    seen=set(); uniq=[]
    for i in items:
        if i['title'] not in seen: seen.add(i['title']); uniq.append(i)
    return uniq[:10]

def render_price_row(name, data):
    c="#00ff88" if data["change_pct"]>=0 else "#ff4466"; s="+" if data["change_pct"]>=0 else ""; a="▲" if data["change_pct"]>=0 else "▼"
    p=data["price"]
    ps=(f"${p:,.0f}" if p>=10000 else (f"${p:,.0f}" if p>=1000 else (f"${p:,.2f}" if p>=1 else f"${p:.4f}")))
    st.markdown(f'<div style="display:flex;justify-content:space-between;align-items:center;padding:0.3rem 0;font-size:0.75rem;border-bottom:1px solid rgba(255,255,255,0.04);"><span style="color:#FFFFFF;">{name}</span><span style="color:#FFFFFF;font-weight:500;">{ps}</span><span style="color:{c};font-size:0.68rem;">{a} {s}{data["change_pct"]:.2f}%</span></div>', unsafe_allow_html=True)

def render_news_item(item):
    t=item["title"]; dt=t[:100]+"..." if len(t)>100 else t
    st.markdown(f'<div style="padding:0.35rem 0;border-bottom:1px solid rgba(255,255,255,0.04);"><div style="color:#FFFFFF;font-size:0.73rem;line-height:1.4;">{dt}</div><div style="color:#333;font-size:0.63rem;">{item["source"]}</div></div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# TXID PAYMENT — INTELLIGENCE UNTOUCHED
# ═══════════════════════════════════════════════════════════════
def validate_txid_format(tx, cur):
    if not tx or not tx.strip(): return False
    tx=tx.strip()
    if cur=="BTC": return bool(re.match(r'^[a-fA-F0-9]{64}$',tx))
    if cur in ("ETH","USDC"): return bool(re.match(r'^0x[a-fA-F0-9]{64}$',tx))
    if cur=="SOL": return bool(re.match(r'^[1-9A-HJ-NP-Za-km-z]{87,88}$',tx))
    return False

def verify_crypto_payment(tx, cur, amt):
    tx=tx.strip()
    if not validate_txid_format(tx,cur): return False, f"Invalid {cur} TXID format."
    try:
        if cur=="BTC":
            for url in [f"https://blockchain.info/rawtx/{tx}",f"https://blockstream.info/api/tx/{tx}"]:
                try:
                    r=requests.get(url,timeout=10)
                    if r.status_code!=200: continue
                    outputs=r.json().get("out") or r.json().get("vout") or []
                    for out in outputs:
                        if (out.get("addr") or out.get("scriptpubkey_address",""))==CRYPTO_ADDRESSES["BTC"]:
                            v=out.get("value",0)
                            if v>1: v/=100_000_000
                            if abs(v-amt)<0.0001: return True, "Verified on Bitcoin."
                            return False, "Amount mismatch."
                    return False, "Wrong address."
                except: continue
            return False, "Could not verify."
        if cur in ("ETH","USDC"):
            ak=CONFIG.get("ETHERSCAN_API_KEY","")
            r=requests.get("https://api.etherscan.io/api",params={"module":"proxy","action":"eth_getTransactionByHash","txhash":tx,"apikey":ak},timeout=10)
            if r.status_code!=200: return False, "Could not connect."
            txd=r.json().get("result",{})
            if not txd: return False, "Not found."
            if txd.get("to","").lower()!=CRYPTO_ADDRESSES["ETH"].lower(): return False, "Wrong address."
            v=int(txd.get("value","0"),16)/1e18
            if abs(v-amt)<0.001: return True, "Verified."
            return False, "Amount mismatch."
        if cur=="SOL":
            r=requests.post("https://api.mainnet-beta.solana.com",json={"jsonrpc":"2.0","id":1,"method":"getTransaction","params":[tx,"json"]},headers={"Content-Type":"application/json"},timeout=10)
            if r.status_code!=200: return False, "Could not connect."
            d=r.json()
            if "error" in d: return False, "Not found."
            txd=d.get("result")
            if not txd: return False, "Not found."
            if txd.get("meta",{}).get("err"): return False, "Transaction failed."
            return True, "Verified on Solana."
    except Exception as e: return False, f"Error: {str(e)}"
    return False, "Unsupported."

def is_txid_previously_used(tx): return tx.strip() in st.session_state.get('verified_txids',[])
def mark_txid_as_used(tx):
    if 'verified_txids' not in st.session_state: st.session_state.verified_txids=[]
    st.session_state.verified_txids.append(tx.strip()); persist_current_state()

# ═══════════════════════════════════════════════════════════════
# VECTOR MEMORY — INTELLIGENCE UNTOUCHED
# ═══════════════════════════════════════════════════════════════
_EMBED_CLIENT=None; _EMBED_MODEL=None

def get_embedding(text):
    global _EMBED_CLIENT, _EMBED_MODEL
    if OPENAI_AVAILABLE and CONFIG.get("OPENAI_API_KEY"):
        if _EMBED_CLIENT is None:
            try: _EMBED_CLIENT=OpenAI(api_key=CONFIG["OPENAI_API_KEY"])
            except: _EMBED_CLIENT=False
        if _EMBED_CLIENT:
            try: return _EMBED_CLIENT.embeddings.create(model="text-embedding-3-small",input=text).data[0].embedding
            except: pass
    if LOCAL_EMBEDDING_AVAILABLE and _EMBED_MODEL is None:
        try: _EMBED_MODEL=SentenceTransformer('BAAI/bge-small-en-v1.5')
        except: _EMBED_MODEL=False
    if _EMBED_MODEL:
        try: return _EMBED_MODEL.encode(text,normalize_embeddings=True).tolist()
        except: pass
    return None

class DummyMemory:
    def search(self,q,k=3): return []
    def add_message(self,*a): pass

if FAISS_AVAILABLE:
    class VectorMemory:
        def __init__(self): self.index=None; self.metadata=[]; self._load_or_create()
        def _load_or_create(self):
            if os.path.exists(MEMORY_INDEX_PATH) and os.path.exists(MEMORY_META_PATH):
                try: self.index=faiss.read_index(MEMORY_INDEX_PATH); self.metadata=json.load(open(MEMORY_META_PATH)); return
                except: pass
            self.index=None; self.metadata=[]
        def _save(self):
            if self.index: faiss.write_index(self.index,MEMORY_INDEX_PATH)
            with open(MEMORY_META_PATH,'w') as f: json.dump(self.metadata,f,indent=2)
        def add_message(self,um,am,dom,acc):
            emb=get_embedding(um)
            if emb is None: return
            dim=len(emb)
            if self.index is None or self.index.d!=dim: self.index=faiss.IndexFlatIP(dim); self.metadata=[]
            emb_arr=np.array(emb,dtype=np.float32).reshape(1,-1); faiss.normalize_L2(emb_arr)
            self.metadata.append({"id":str(uuid.uuid4()),"timestamp":datetime.now().isoformat(),"domain":dom,"accuracy":acc,"content":f"User: {um}\nCAPITAN AI: {am}"})
            self.index.add(emb_arr); self._save()
        def search(self,q,k=3,sem_w=0.4,rec_w=0.3,acc_w=0.3):
            if self.index is None or self.index.ntotal==0: return []
            emb=get_embedding(q)
            if emb is None: return []
            dim=len(emb)
            if self.index.d!=dim: return []
            emb_arr=np.array(emb,dtype=np.float32).reshape(1,-1); faiss.normalize_L2(emb_arr)
            D,I=self.index.search(emb_arr,min(self.index.ntotal,20))
            cand=[]; now=datetime.now()
            for s,i in zip(D[0],I[0]):
                if i<0 or i>=len(self.metadata): continue
                m=self.metadata[i]; ss=(s+1)/2
                try: ts=datetime.fromisoformat(m["timestamp"])
                except: ts=now-timedelta(days=365)
                days_old=(now-ts).total_seconds()/86400.0
                recency=math.exp(-math.log(2)/CONFIG["MEMORY_DECAY_HALF_LIFE"]*days_old)
                accuracy=m.get("accuracy",3)/5.0
                final=sem_w*ss+rec_w*recency+acc_w*accuracy
                cand.append((final,m))
            cand.sort(key=lambda x:x[0],reverse=True)
            return [m["content"] for _,m in cand[:k]]
    memory_engine=VectorMemory()
else:
    memory_engine=DummyMemory()

# ═══════════════════════════════════════════════════════════════
# TOOL ROUTER — INTELLIGENCE UNTOUCHED
# ═══════════════════════════════════════════════════════════════
def decide_tools(query):
    try:
        r,err=llm_cb.call(call_llm,[{"role":"system","content":"Output only valid JSON arrays."},{"role":"user","content":f"Return JSON list from [web, prices, code, none]. Query: {query}"}],is_pro=False,use_specific_model="deepseek/deepseek-chat")
        if err: return ["none"]
        m=re.search(r'\[.*\]',r,re.DOTALL)
        if m:
            tools=json.loads(m.group())
            if isinstance(tools,list): return [t for t in tools if t in {"web","wolfram","code","prices","none"}]
    except: pass
    return ["none"]

# ═══════════════════════════════════════════════════════════════
# ELITE PROCESSING PIPELINE — INTELLIGENCE FULLY PRESERVED
# ═══════════════════════════════════════════════════════════════
def process_query(prompt, is_pro=False):
    domain=DomainRouter.classify(prompt)
    complexity=QueryComplexityAnalyzer.grade(prompt, domain)

    if domain=="trading_refuse":
        msgs=[{"role":"system","content":PERSONAS["trading_refuse"]},{"role":"user","content":prompt}]
        for chunk in call_llm_stream_fast(msgs, is_pro=is_pro): yield chunk
        return

    entities=entity_memory.extract_entities(prompt); entity_memory.add_entities(entities)
    mc=memory_engine.search(prompt, k=3)
    mt=""
    if mc: mt="RELEVANT MEMORY:\n"+"\n".join(f"  [{i+1}] {m}" for i,m in enumerate(mc))+"\n\n"
    et=entity_memory.get_summary(); gt=goal_tracker.get_context_for_ai()

    for pat in [r'\b(?:I (?:want|need|plan|aim|goal is) to\b[^.!?]+)',r'\b(?:my (?:goal|target|objective) is\b[^.!?]+)',r'\b(?:help me (?:prepare|study|learn|build|create|start|launch)\b[^.!?]+)']:
        m=re.search(pat, prompt, re.IGNORECASE)
        if m:
            gte=m.group(0).strip()
            if len(gte)>10: goal_tracker.add_goal(gte, domain); gt=goal_tracker.get_context_for_ai()
            break

    tc=""
    if is_pro:
        tools=decide_tools(prompt)
        if "web" in tools and CONFIG["SERPER_KEY"]:
            sr=web_search(prompt[:150])
            if sr: tc+="\nWEB SEARCH RESULTS:\n"+sr+"\n"
        if "prices" in tools:
            prices=get_live_prices()
            if prices:
                lines=[f"{n}: ${d['price']:,.2f} ({'+' if d['change_pct']>=0 else ''}{d['change_pct']:.2f}%)" for n,d in prices.items()]
                tc+="\nLIVE PRICES:\n"+"\n".join(lines)+"\n"
        if domain in ("finance","african_finance","macro","quant"):
            news=fetch_financial_news()
            if news:
                hl=[f"[{i+1}] {n['title']} — {n['source']}" for i,n in enumerate(news[:5])]
                tc+="\nMARKET NEWS:\n"+"\n".join(hl)+"\n"

    elite_scaffold=None
    if is_pro and complexity in ("standard","deep") and len(prompt.split())>20:
        elite_scaffold=EliteReasoningEngine.decompose(prompt, domain, complexity, is_pro)

    persona=PERSONAS.get(domain, PERSONAS["general"])
    ctx_blocks=[]
    if elite_scaffold: ctx_blocks.append(EliteReasoningEngine.build_scaffold_context(elite_scaffold))
    if gt: ctx_blocks.append(gt)
    if et: ctx_blocks.append(et)
    if mt: ctx_blocks.append(mt)
    if ctx_blocks: persona="\n\n".join(ctx_blocks)+"\n\n"+persona
    if tc: persona+="\n\n=== LIVE INTELLIGENCE ===\n"+tc+"=== END LIVE INTELLIGENCE ===\n"

    emotional_patterns=[r'\b(tired|sad|lonely|stressed|anxious|worried|overwhelmed|depressed|upset|heartbroken|grieving)\b',r'\b(i\'m feeling|i feel|i am feeling|feeling kinda|feeling a bit|been feeling)\b',r'\b(hard day|rough day|tough week|difficult time|struggling)\b']
    if any(re.search(p, prompt, re.IGNORECASE) for p in emotional_patterns):
        persona+="\n\nEMOTIONAL CONTEXT: Acknowledge briefly and genuinely. Offer practical support. Do not over-elaborate."

    word_count=len(prompt.split())
    if word_count<8 or "briefly" in prompt.lower() or "concise" in prompt.lower(): persona+="\n\nBE CONCISE."
    elif "detailed" in prompt.lower() or "comprehensive" in prompt.lower() or complexity=="deep": persona+="\n\nBE THOROUGH."

    model_override=None
    if complexity=="deep" and is_pro: model_override=CONFIG["DEEP_MODEL"]
    elif complexity=="simple" and not is_pro: model_override=CONFIG["FAST_MODEL"]

    messages=[{"role":"system","content":persona},{"role":"user","content":prompt}]

    accumulated = ""
    for chunk in call_llm_stream_fast(messages, is_pro=is_pro, model_override=model_override):
        accumulated += chunk
        yield accumulated

    fr = accumulated

    if is_pro and complexity=="deep" and elite_scaffold and len(fr)>300:
        try:
            critique_data=EliteReasoningEngine.critique(prompt, fr, is_pro)
            if critique_data and critique_data.get("verdict") in ("WEAK","ACCEPTABLE"):
                scaffold_text=EliteReasoningEngine.build_scaffold_context(elite_scaffold)
                refined=EliteReasoningEngine.synthesize_elite(prompt, scaffold_text, critique_data, fr, is_pro)
                if refined and refined!=fr:
                    sep="\n\n---\n*✦ Elite Refined Response (adversarial critique applied):*\n\n"
                    accumulated += sep
                    yield accumulated
                    for chunk in refined:
                        accumulated += chunk
                        yield accumulated
                    fr = accumulated
        except: pass

    try:
        scores=EliteSelfEvaluator.evaluate(prompt, fr, domain, is_pro) if is_pro else {"accuracy":3.0}
        acc=scores.get("accuracy",3.0) if isinstance(scores,dict) else 3.0
    except: acc=3.0
    memory_engine.add_message(prompt, fr, domain, acc)

# ═══════════════════════════════════════════════════════════════
# UI — PURE BLACK EDITION
# ═══════════════════════════════════════════════════════════════
st.set_page_config(page_title="CAPITAN AI", page_icon="⚓", layout="centered", initial_sidebar_state="expanded")

st.markdown('<link rel="manifest" href="/.streamlit/static/manifest.json">', unsafe_allow_html=True)
st.markdown('<meta name="theme-color" content="#000000">', unsafe_allow_html=True)
st.markdown('<meta name="mobile-web-app-capable" content="yes">', unsafe_allow_html=True)
st.markdown('<meta name="apple-mobile-web-app-capable" content="yes">', unsafe_allow_html=True)
st.markdown('<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">', unsafe_allow_html=True)
st.markdown('<meta name="apple-mobile-web-app-title" content="CAPITAN AI">', unsafe_allow_html=True)

st.components.v1.html("""
<!DOCTYPE html><html><head>
<style>body{margin:0;padding:0;}#cap-install-btn{position:fixed;bottom:0;left:0;right:0;background:#000;border-top:1px solid #00ff88;padding:14px 18px;display:flex;align-items:center;justify-content:space-between;z-index:99999;font-family:system-ui,sans-serif;animation:slideUp .35s ease-out;box-shadow:0 -8px 40px rgba(0,255,136,0.1)}#cap-install-btn.hidden{display:none}.install-btn{background:#00ff88;color:#000;border:none;padding:10px 22px;border-radius:50px;font-size:14px;font-weight:700;cursor:pointer;white-space:nowrap}.dismiss-btn{background:transparent;color:#333;border:none;font-size:20px;cursor:pointer;padding:4px 8px}@keyframes slideUp{from{transform:translateY(100%);opacity:0}to{transform:translateY(0);opacity:1}}</style></head><body>
<div id="cap-install-btn" class="hidden"><div style="display:flex;align-items:center;gap:14px"><div style="width:48px;height:48px;background:#000;border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:24px;border:1px solid #1a1a1a">⚓</div><div><div style="color:#eee;font-size:15px;font-weight:700">CAPITAN AI</div><div style="color:#00ff88;font-size:12px;margin-top:2px">Install · Free · Works offline</div></div></div><div style="display:flex;align-items:center;gap:8px"><button class="install-btn" onclick="installApp()">Install</button><button class="dismiss-btn" onclick="dismissBanner()">✕</button></div></div>
<script>var dp=null,isSA=window.matchMedia('(display-mode:standalone)').matches||window.navigator.standalone===true;window.addEventListener('beforeinstallprompt',function(e){e.preventDefault();dp=e;if(!isSA)document.getElementById('cap-install-btn').classList.remove('hidden')});function installApp(){if(dp){dp.prompt();dp.userChoice.then(function(r){document.getElementById('cap-install-btn').classList.add('hidden');dp=null})}else if(isSA)alert('Already installed!');else alert('Look for the install icon (⊕) in your address bar.')}function dismissBanner(){document.getElementById('cap-install-btn').classList.add('hidden')}</script></body></html>
""", height=80)

# FIXED: Sidebar text color is now white
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
:root{{
  --bg-primary:#000000;
  --bg-secondary:#080808;
  --bg-tertiary:#0e0e0e;
  --bg-card:#111111;
  --border:#1c1c1c;
  --border-accent:rgba(0,255,136,0.2);
  --text-primary:#FFFFFF;
  --text-secondary:#666666;
  --text-muted:#333333;
  --accent:#00ff88;
  --accent-dim:rgba(0,255,136,0.08);
  --accent-glow:rgba(0,255,136,0.15);
  --africa-gold:#ffcc00;
  --red:#ff3355;
  --tag-blue:#87CEEB;
  --radius:10px;
  --radius-sm:6px;
  --font-xs:0.65rem;
  --font-sm:0.72rem;
  --font-md:0.8rem;
  --font-lg:0.9rem;
  --font-xl:1.1rem;
  --font-2xl:1.4rem
}}
*{{box-sizing:border-box}}
.stApp{{background:var(--bg-primary)!important;color:var(--text-primary)!important;font-family:'Space Grotesk',sans-serif!important;font-size:var(--font-sm)!important}}
.main .block-container{{padding:1rem 1rem 0 1rem!important;max-width:800px!important;font-size:var(--font-sm)!important}}
section[data-testid="stSidebar"]{{background:#000000!important;border-right:1px solid var(--border)!important;font-size:var(--font-xs)!important}}
/* FIXED: Sidebar text is now white */
section[data-testid="stSidebar"] .stButton button{{background:transparent;border:none;color:#FFFFFF!important;padding:0.4rem 0.6rem;font-size:var(--font-xs);text-align:left;border-radius:var(--radius-sm);width:100%;transition:all 0.2s}}
section[data-testid="stSidebar"] .stButton button:hover{{background:var(--bg-card);color:var(--accent)!important}}
/* FIXED: All sidebar text elements now white */
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] div,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stCaption,
section[data-testid="stSidebar"] .stMarkdown,
section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stMultiSelect label,
section[data-testid="stSidebar"] .stTextInput label,
section[data-testid="stSidebar"] .stNumberInput label,
section[data-testid="stSidebar"] .stDateInput label,
section[data-testid="stSidebar"] .stTimeInput label,
section[data-testid="stSidebar"] .stTextArea label,
section[data-testid="stSidebar"] .stCheckbox span,
section[data-testid="stSidebar"] .stRadio span,
section[data-testid="stSidebar"] .stToggle span,
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
section[data-testid="stSidebar"] .stExpander summary,
section[data-testid="stSidebar"] .stExpander summary p,
section[data-testid="stSidebar"] .stExpander summary span,
section[data-testid="stSidebar"] .stAlert,
section[data-testid="stSidebar"] .stInfo,
section[data-testid="stSidebar"] .stWarning,
section[data-testid="stSidebar"] .stError,
section[data-testid="stSidebar"] .stSuccess,
section[data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] span,
section[data-testid="stSidebar"] .stTextInput input::placeholder,
section[data-testid="stSidebar"] .stTextArea textarea::placeholder{{
    color:#FFFFFF!important;
}}
/* Keep muted elements slightly dimmer but still readable */
section[data-testid="stSidebar"] .stCaption,
section[data-testid="stSidebar"] .nav-label,
section[data-testid="stSidebar"] .privacy-badge-text,
section[data-testid="stSidebar"] .free-limit-bar-inner{{
    color:#aaaaaa!important;
}}
/* Sidebar input backgrounds */
section[data-testid="stSidebar"] .stTextInput input,
section[data-testid="stSidebar"] .stTextArea textarea,
section[data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] div{{
    background:var(--bg-secondary)!important;
    border-color:var(--border)!important;
    color:#FFFFFF!important;
}}
section[data-testid="stSidebar"] .stExpander{{background:var(--bg-secondary)!important;border:1px solid var(--border)!important;border-radius:var(--radius-sm)!important}}
section[data-testid="stSidebar"] hr{{border-color:var(--border)!important}}
.chat-message{{padding:0.85rem 1rem;margin:0.4rem 0;line-height:1.6;font-size:var(--font-sm)}}
.chat-user{{background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);margin-left:auto;max-width:85%;color:var(--text-primary)}}
.chat-assistant{{background:transparent;border-left:2px solid var(--accent);border-radius:0 var(--radius-sm) var(--radius-sm) 0;padding-left:1rem;max-width:95%;color:var(--text-primary);position:relative}}
.chat-assistant code{{background:var(--bg-card);color:var(--accent);padding:0.12rem 0.35rem;border-radius:3px;font-family:'JetBrains Mono',monospace;font-size:0.78em;border:1px solid var(--border)}}
.chat-assistant pre{{background:var(--bg-secondary);border:1px solid var(--border);padding:0.85rem;border-radius:var(--radius-sm);overflow-x:auto;font-size:var(--font-xs)}}
.msg-header{{display:flex;align-items:center;gap:6px;margin-bottom:0.4rem;opacity:0.7}}
.msg-logo{{display:inline-flex;align-items:center}}
.welcome-container{{display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:40vh;text-align:center;padding:1.5rem}}
.welcome-logo-ring{{width:80px;height:80px;border-radius:50%;border:1px solid var(--border-accent);display:flex;align-items:center;justify-content:center;margin:0 auto 1rem;background:radial-gradient(circle at center, var(--accent-dim) 0%, transparent 70%);box-shadow:0 0 30px var(--accent-glow)}}
.welcome-title{{font-size:var(--font-2xl);font-weight:700;color:var(--text-primary);margin-bottom:0.3rem;letter-spacing:-0.02em}}
.welcome-subtitle{{font-size:var(--font-sm);color:var(--text-secondary);margin-bottom:1.5rem}}
.welcome-tag{{display:inline-block;padding:0.15rem 0.5rem;border:1px solid var(--border-accent);border-radius:20px;font-size:0.6rem;color:var(--tag-blue);margin:0.1rem;letter-spacing:0.05em}}
.stChatInput textarea{{background:var(--bg-secondary)!important;border:1px solid var(--border)!important;color:var(--text-primary)!important;border-radius:var(--radius)!important;padding:0.65rem 0.85rem!important;font-size:var(--font-xs)!important;font-family:'Space Grotesk',sans-serif!important}}
.stChatInput textarea:focus{{border-color:var(--accent)!important;box-shadow:0 0 0 3px var(--accent-dim)!important}}
.stChatInput textarea::placeholder{{color:var(--text-muted)!important}}
.thinking-indicator{{display:flex;align-items:center;gap:0.6rem;padding:0.7rem 1rem;color:var(--text-muted);font-size:var(--font-xs);border-left:2px solid var(--border);margin:0.4rem 0}}
.thinking-dots{{display:flex;gap:3px}}
.thinking-dot{{width:4px;height:4px;border-radius:50%;background:var(--accent);animation:dotPulse 1.4s ease-in-out infinite}}
.thinking-dot:nth-child(2){{animation-delay:0.2s}}.thinking-dot:nth-child(3){{animation-delay:0.4s}}
@keyframes dotPulse{{0%,80%,100%{{opacity:0.2;transform:scale(0.8)}}40%{{opacity:1;transform:scale(1.2)}}}}
.status-bar{{display:flex;align-items:center;justify-content:center;gap:0.4rem;padding:0.4rem;font-size:var(--font-xs);color:var(--text-muted);border-top:1px solid var(--border);margin-top:0.75rem}}
.status-dot{{width:5px;height:5px;border-radius:50%;background:var(--accent);box-shadow:0 0 6px var(--accent)}}
.ai-note{{font-size:0.58rem;color:var(--text-muted);padding-left:1rem;margin-top:-0.2rem;margin-bottom:0.4rem}}
.nav-label{{font-size:0.58rem;text-transform:uppercase;letter-spacing:0.08em;color:#aaaaaa;padding:0.4rem 0.6rem 0.2rem}}
.section-header{{font-size:0.58rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.2rem}}
.category-header{{font-size:0.62rem;color:var(--accent);font-weight:600;padding:0.4rem 0 0.2rem 0;margin-top:0.2rem;letter-spacing:0.03em}}
.africa-header{{font-size:0.62rem;color:var(--africa-gold);font-weight:600;padding:0.4rem 0 0.2rem 0;margin-top:0.2rem}}
hr{{border-color:var(--border)!important;margin:0.6rem 0!important}}
.upgrade-section{{background:var(--bg-secondary);border:1px solid var(--border-accent);border-radius:var(--radius);padding:0.85rem;margin-top:0.4rem;font-size:var(--font-xs)}}
.crypto-address{{background:var(--bg-primary);padding:0.5rem;border-radius:4px;font-family:'JetBrains Mono',monospace;font-size:0.62rem;word-break:break-all;color:var(--text-secondary);border:1px solid var(--border)}}
.mission-control{{background:var(--bg-secondary);border:1px solid var(--border);border-radius:var(--radius);padding:0.8rem;margin-bottom:0.4rem}}
.mc-title{{font-size:0.6rem;text-transform:uppercase;letter-spacing:0.1em;color:var(--accent);margin-bottom:0.5rem;display:flex;align-items:center;gap:5px}}
.mc-metric{{display:flex;justify-content:space-between;padding:0.25rem 0;font-size:0.7rem;border-bottom:1px solid var(--border)}}
.mc-metric:last-child{{border-bottom:none}}
.mc-value{{color:var(--accent);font-weight:600;font-family:'JetBrains Mono',monospace}}
.progress-bar{{background:var(--bg-card);height:3px;border-radius:2px;overflow:hidden;margin-top:0.3rem}}
.progress-fill{{background:var(--accent);height:100%;border-radius:2px;transition:width 0.4s ease}}
.goal-item{{display:flex;justify-content:space-between;align-items:center;padding:0.3rem 0;font-size:0.7rem;border-bottom:1px solid rgba(255,255,255,0.04)}}
.goal-priority-high{{color:var(--red);font-size:0.55rem}}
.goal-priority-medium{{color:var(--africa-gold);font-size:0.55rem}}
.goal-priority-low{{color:var(--text-muted);font-size:0.55rem}}
.privacy-badge{{text-align:center;padding:0.6rem;margin-top:0.4rem;border-top:1px solid var(--border)}}
.privacy-badge-text{{font-size:0.58rem;color:#FFFFFF;line-height:1.5}}
.privacy-badge-text strong{{color:var(--accent)}}
.free-limit-bar{{margin:0.4rem 0.6rem}}
.free-limit-bar-inner{{font-size:0.6rem;color:#aaaaaa;text-align:center;margin-bottom:0.2rem}}
.pro-badge{{background:var(--accent);color:#000;padding:0.2rem 0.7rem;border-radius:20px;font-size:0.68rem;font-weight:700;text-align:center;letter-spacing:0.05em}}
.founder-badge{{background:linear-gradient(135deg,var(--accent),var(--africa-gold));color:#000;padding:0.2rem 0.7rem;border-radius:20px;font-size:0.68rem;font-weight:700;text-align:center;letter-spacing:0.05em}}
.suggest-btn .stButton button{{background:var(--bg-card)!important;border:1px solid var(--border)!important;color:var(--text-secondary)!important;border-radius:var(--radius)!important;font-size:var(--font-xs)!important;padding:0.6rem 0.8rem!important;text-align:left!important;transition:all 0.2s!important}}
.suggest-btn .stButton button:hover{{border-color:var(--accent)!important;color:var(--accent)!important;background:var(--accent-dim)!important}}
@media(max-width:768px){{
  .chat-user,.chat-assistant{{max-width:100%}}
  .welcome-title{{font-size:var(--font-xl)}}
}}
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# SESSION STATE — PRO STATUS IS SESSION-ONLY (NOT SHARED)
# ═══════════════════════════════════════════════════════════════
lm, lp, lf, lch, ltx, lpr, ldc, ldr = load_persistent_state()
lproj = load_projects()

st.session_state.messages = lm
# CRITICAL: is_pro and is_founder are NEVER loaded from shared storage
# They start False for every new session
st.session_state.is_pro = False  # Each session starts as free
st.session_state.is_founder = False  # Each session starts without founder
st.session_state.chat_history = lch
st.session_state.verified_txids = ltx
st.session_state.user_preferences = lpr
st.session_state.projects = lproj
st.session_state.goals = load_goals()

if 'current_chat_id' not in st.session_state: st.session_state.current_chat_id = str(uuid.uuid4())
if 'current_project_id' not in st.session_state: st.session_state.current_project_id = None
if 'model' not in st.session_state: st.session_state.model = "smart"
if 'web_search_enabled' not in st.session_state: st.session_state.web_search_enabled = True
if 'show_upgrade' not in st.session_state: st.session_state.show_upgrade = False
if 'show_mission_control' not in st.session_state: st.session_state.show_mission_control = False
st.session_state.daily_count = ldc
st.session_state.daily_reset = ldr

FREE_DAILY_LIMIT = CONFIG["FREE_DAILY_LIMIT"]
try:
    reset_time = datetime.fromisoformat(st.session_state.daily_reset)
except (ValueError, TypeError):
    reset_time = datetime.now()
    st.session_state.daily_reset = reset_time.isoformat()

if datetime.now() - reset_time > timedelta(hours=24):
    st.session_state.daily_count = 0
    st.session_state.daily_reset = datetime.now().isoformat()

remaining_free = max(0, FREE_DAILY_LIMIT - st.session_state.daily_count)

# ═══════════════════════════════════════════════════════════════
# SIDEBAR — PURE BLACK EDITION
# ═══════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(f'''
    <div style="display:flex;align-items:center;gap:0.6rem;padding:0.6rem 0.6rem 0.4rem;border-bottom:1px solid #1c1c1c;margin-bottom:0.4rem">
      <div style="width:32px;height:32px;border-radius:8px;background:#000;border:1px solid rgba(0,255,136,0.3);display:flex;align-items:center;justify-content:center;box-shadow:0 0 12px rgba(0,255,136,0.1)">
        <span style="color:#00ff88;font-weight:700;font-size:1.2rem">⚓</span>
      </div>
      <div>
        <div style="font-size:0.9rem;font-weight:700;color:#FFFFFF;letter-spacing:-0.01em">CAPITAN AI</div>
        <div style="font-size:0.55rem;color:#00ff88;letter-spacing:0.08em">SOVEREIGN INTELLIGENCE</div>
      </div>
    </div>
    ''', unsafe_allow_html=True)

    ip_sidebar = st.session_state.is_pro or st.session_state.is_founder

    if not ip_sidebar:
        pct_used = (st.session_state.daily_count / FREE_DAILY_LIMIT) * 100
        bar_color = "#00ff88" if pct_used < 70 else ("#ffcc00" if pct_used < 90 else "#ff3355")
        st.markdown(f'''
        <div class="free-limit-bar">
          <div class="free-limit-bar-inner">{remaining_free}/{FREE_DAILY_LIMIT} messages today</div>
          <div style="background:rgba(255,255,255,0.04);height:2px;border-radius:1px;overflow:hidden">
            <div style="width:{pct_used}%;background:{bar_color};height:100%;border-radius:1px;transition:width 0.3s"></div>
          </div>
        </div>
        ''', unsafe_allow_html=True)

    if st.button("⊕ New Chat", use_container_width=True, key="nc"):
        if st.session_state.messages:
            st.session_state.chat_history.append({"id":st.session_state.current_chat_id,"title":st.session_state.messages[0]["content"][:50] if st.session_state.messages else "New Chat","messages":st.session_state.messages.copy(),"timestamp":datetime.now().isoformat(),"project_id":st.session_state.current_project_id})
        st.session_state.messages = []; st.session_state.current_chat_id = str(uuid.uuid4()); persist_current_state(); st.rerun()

    st.markdown("---")

    if ip_sidebar:
        if st.button("⚓ Mission Control", use_container_width=True, key="mc_btn"):
            st.session_state.show_mission_control = not st.session_state.show_mission_control

        if st.session_state.show_mission_control:
            active_goals = goal_tracker.get_active_goals()
            total_projects = len(st.session_state.projects)
            active_projects = sum(1 for p in st.session_state.projects.values() if p.get("status","active")=="active")
            avg_progress = int(sum(p.get("progress",0) for p in st.session_state.projects.values()) / max(total_projects,1))
            patterns = get_strategic_patterns()

            st.markdown(f'''
            <div class="mission-control">
              <div class="mc-title">⚓ MISSION CONTROL</div>
              <div class="mc-metric"><span style="color:#666">Projects</span><span class="mc-value">{active_projects}/{total_projects}</span></div>
              <div class="mc-metric"><span style="color:#666">Active Goals</span><span class="mc-value">{len(active_goals)}</span></div>
              <div class="mc-metric"><span style="color:#666">Avg Progress</span><span class="mc-value">{avg_progress}%</span></div>
              <div class="mc-metric"><span style="color:#666">Msgs Today</span><span class="mc-value">{st.session_state.daily_count}</span></div>
              <div style="margin-top:0.4rem">
                <div style="font-size:0.58rem;color:#333;margin-bottom:0.2rem">OVERALL PROGRESS</div>
                <div class="progress-bar"><div class="progress-fill" style="width:{avg_progress}%"></div></div>
              </div>
            </div>
            ''', unsafe_allow_html=True)

            if patterns:
                st.markdown('<div style="font-size:0.58rem;color:#333;text-transform:uppercase;letter-spacing:0.05em;margin:0.3rem 0 0.2rem">Strategic Patterns</div>', unsafe_allow_html=True)
                for p in patterns[:2]:
                    conf = int(p.get("confidence",0)*100)
                    st.markdown(f'<div style="font-size:0.65rem;color:#666;padding:0.2rem 0;border-bottom:1px solid #111">{p["pattern"][:50]}... <span style="color:#00ff88">{conf}%</span></div>', unsafe_allow_html=True)

    st.markdown("---")

    with st.expander("📁 Projects", expanded=False):
        if st.button("+ New Project", use_container_width=True, key="np"):
            npid = str(uuid.uuid4())
            st.session_state.projects[npid] = {"id":npid,"name":"Untitled Project","mission":"","status":"active","progress":0,"created":datetime.now().isoformat(),"goals":[],"tasks":[],"risks":[]}
            st.session_state.current_project_id = npid; persist_current_state(); st.rerun()
        for pid, proj in st.session_state.projects.items():
            c1, c2 = st.columns([3,1])
            prog = proj.get("progress",0)
            with c1:
                if st.button(f"{'◉' if pid==st.session_state.current_project_id else '○'} {proj['name'][:22]}",use_container_width=True,key=f"pj_{pid}"):
                    st.session_state.current_project_id = pid; persist_current_state(); st.rerun()
            with c2:
                if st.button("✕",key=f"dp_{pid}"):
                    del st.session_state.projects[pid]
                    st.session_state.current_project_id = None if st.session_state.current_project_id==pid else st.session_state.current_project_id
                    persist_current_state(); st.rerun()
            if prog > 0:
                st.markdown(f'<div class="progress-bar" style="margin:0 0 0.3rem"><div class="progress-fill" style="width:{prog}%"></div></div>', unsafe_allow_html=True)

    st.markdown('<div class="nav-label">Recent Chats</div>', unsafe_allow_html=True)
    for chat in reversed(st.session_state.chat_history[-5:]):
        if st.button(chat.get("title","Untitled")[:30],use_container_width=True,key=f"ch_{chat['id']}"):
            st.session_state.messages = chat["messages"]; st.session_state.current_chat_id = chat["id"]
            st.session_state.current_project_id = chat.get("project_id"); persist_current_state(); st.rerun()

    with st.expander("🎯 Goals", expanded=False):
        ag = goal_tracker.get_active_goals()
        if ag:
            for g in ag[:5]:
                da = (datetime.now()-datetime.fromisoformat(g["created"])).days
                pri = g.get("priority","medium")
                pri_class = f"goal-priority-{pri}"
                st.markdown(f'<div class="goal-item"><span style="color:#FFFFFF;font-size:0.68rem">{g["description"][:38]}...</span><span class="{pri_class}">{"▲" if pri=="high" else "●" if pri=="medium" else "▼"} {da}d</span></div>',unsafe_allow_html=True)
        else:
            st.caption("Goals detected from conversations automatically.")

    with st.expander("🧠 Memory", expanded=False):
        es = entity_memory.get_summary()
        if es: st.markdown(f'<div style="font-size:0.68rem;color:#888;line-height:1.6">{es}</div>',unsafe_allow_html=True)
        else: st.caption("Remembers people, companies, and projects across sessions.")

    st.markdown("---")
    
    # ================= NEW LIBRARIES SECTION =================
    with st.expander("📚 Libraries", expanded=False):
        suggestions = [
            ("📊 African Markets","Analyze the NGX All-Share and key Nigerian banking stocks"),
            ("💻 Write Code","Write a Python backtesting framework for trading strategies"),
            ("💰 Investment Memo","Write an investment memo on MTN Group with African market context"),
            ("🌍 Macro Analysis","Analyze AfCFTA impact on cross-border payments in West Africa")
        ]
        for i, (l, q) in enumerate(suggestions):
            if st.button(l, use_container_width=True, key=f"lib_{i}"):
                st.session_state.messages.append({"role":"user","content":q,"id":str(uuid.uuid4())})
                persist_current_state()
                st.rerun()
    # =========================================================

    with st.expander("⚙️ Settings", expanded=False):
        model = st.selectbox("Model",["CAPITAN Fast","CAPITAN Smart","CAPITAN Deep Think"],label_visibility="collapsed",key="ms")
        st.session_state.model = {"CAPITAN Fast":"fast","CAPITAN Smart":"smart","CAPITAN Deep Think":"deep"}.get(model,"smart")
        st.session_state.web_search_enabled = st.toggle("Web Search",value=st.session_state.web_search_enabled)

    st.markdown("---")

    if ip_sidebar:
        with st.expander("📈 Live Prices", expanded=False):
            prices = get_live_prices()
            if prices:
                cats = {"Global Markets":[],"🟡 African Markets":[],"Crypto":[],"Commodities":[],"Forex & African FX":[]}
                for n,d in prices.items():
                    cat = d.get("category","stocks")
                    if cat=="stocks": cats["Global Markets"].append((n,d))
                    elif cat=="african_stocks": cats["🟡 African Markets"].append((n,d))
                    elif cat=="crypto": cats["Crypto"].append((n,d))
                    elif cat=="commodities": cats["Commodities"].append((n,d))
                    elif cat=="forex": cats["Forex & African FX"].append((n,d))
                for cn,items in cats.items():
                    if items:
                        hc = "africa-header" if "African" in cn else "category-header"
                        st.markdown(f'<div class="{hc}">{cn}</div>',unsafe_allow_html=True)
                        for n,d in items: render_price_row(n,d)
                st.caption(f"Updated: {datetime.now().strftime('%H:%M:%S')}")
                if st.button("↺ Refresh",use_container_width=True,key="rp"): get_live_prices.clear(); st.rerun()
            else: st.caption("Loading prices...")

        with st.expander("📰 Market News", expanded=False):
            news = fetch_financial_news()
            if news:
                st.markdown('<div class="section-header">Latest Headlines</div>',unsafe_allow_html=True)
                for i in news[:5]: render_news_item(i)
                st.caption(f"Updated: {datetime.now().strftime('%H:%M:%S')}")
            else: st.caption("No news available")

    st.markdown("---")

    if st.session_state.is_founder:
        st.markdown(f'<div class="founder-badge">⚓ FOUNDER · SOVEREIGN</div>',unsafe_allow_html=True)
    elif st.session_state.is_pro:
        st.markdown(f'<div class="pro-badge">◆ PRO</div>',unsafe_allow_html=True)
    else:
        if st.button("✦ Upgrade to Pro — $15/mo",use_container_width=True,key="ub"):
            st.session_state.show_upgrade = not st.session_state.show_upgrade

    if st.session_state.show_upgrade and not st.session_state.is_pro and not st.session_state.is_founder:
        st.markdown('<div class="upgrade-section">',unsafe_allow_html=True)
        st.markdown(f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:0.6rem"><span style="color:#00ff88;font-size:1.2rem">⚓</span><span style="font-size:0.8rem;font-weight:700;color:#FFFFFF">Unlock Pro</span></div>', unsafe_allow_html=True)
        for f in ["Unlimited messages","Live market prices & news","African stock data","Web search","Multi-model intelligence","Vector memory","Elite adversarial reasoning","Project OS + Mission Control","Goal tracking + priorities","Strategic memory layer","Priority support"]:
            st.markdown(f'<div style="font-size:0.65rem;color:#888;padding:0.1rem 0">◦ {f}</div>',unsafe_allow_html=True)
        st.markdown("---")
        st.markdown('<div style="font-size:0.65rem;color:#00ff88;font-weight:600;margin-bottom:0.4rem">Pay with crypto:</div>', unsafe_allow_html=True)
        crypto = st.selectbox("Currency",["BTC","ETH","USDC","SOL"],key="cs",format_func=lambda x:f"{x} — {PRO_PRICE_CRYPTO.get(x,0)} {x}")
        price = PRO_PRICE_CRYPTO.get(crypto,15)
        st.markdown(f'''
        <div style="background:#000;border-radius:8px;padding:0.75rem;margin:0.5rem 0;border:1px solid #1c1c1c">
          <div style="display:flex;justify-content:space-between;margin-bottom:0.4rem">
            <span style="color:#444;font-size:0.68rem">Amount</span>
            <span style="color:#00ff88;font-weight:700;font-size:0.75rem">{price} {crypto}</span>
          </div>
          <div style="display:flex;justify-content:space-between;margin-bottom:0.5rem">
            <span style="color:#444;font-size:0.68rem">USD Value</span>
            <span style="color:#FFFFFF;font-size:0.75rem">~${PRO_PRICE_USD}</span>
          </div>
          <div style="font-size:0.62rem;color:#444;margin-bottom:0.25rem">Send to:</div>
          <div class="crypto-address">{CRYPTO_ADDRESSES.get(crypto,"")}</div>
        </div>
        ''', unsafe_allow_html=True)
        if st.button("📋 Copy Address",use_container_width=True,key="ca"): st.toast("Copied!")
        st.markdown("---")
        st.markdown('<div style="font-size:0.65rem;color:#666;font-weight:600;margin-bottom:0.4rem">Verify with TXID:</div>', unsafe_allow_html=True)
        tx = st.text_input("Transaction Hash",placeholder=f"Paste {crypto} TXID...",key="ti",label_visibility="collapsed")
        if tx and validate_txid_format(tx,crypto):
            st.markdown(f'<a href="{EXPLORER_LINKS.get(crypto,"")}{tx}" target="_blank" style="color:#00ff88;font-size:0.7rem">↗ View on Explorer</a>',unsafe_allow_html=True)
        c1,c2 = st.columns([2,1])
        with c1:
            if st.button("Verify & Activate",use_container_width=True,key="vp"):
                if not tx: st.error("Enter TXID.")
                elif is_txid_previously_used(tx): st.warning("Already used.")
                else:
                    with st.spinner("Verifying..."):
                        v,msg = verify_crypto_payment(tx,crypto,price)
                        if v:
                            mark_txid_as_used(tx)
                            st.session_state.is_pro = True  # Only this session becomes pro
                            st.session_state.messages=[]
                            st.session_state.show_upgrade=False
                            persist_current_state()
                            st.success(f"✅ {msg}")
                            st.balloons()
                            time.sleep(1.5)
                            st.rerun()
                        else: st.error(f"❌ {msg}")
        with c2:
            if st.button("Clear",use_container_width=True,key="ct"): st.rerun()
        st.markdown("---")
        st.markdown('<div style="font-size:0.65rem;color:#666;margin-bottom:0.3rem">Pro key:</div>', unsafe_allow_html=True)
        key = st.text_input("Key",type="password",placeholder="cap-pro-...",key="pk",label_visibility="collapsed")
        if st.button("Activate Key",use_container_width=True,key="ak"):
            if key==CONFIG.get("FOUNDER_KEY",""):
                st.session_state.is_founder = True  # Only this session becomes founder
                st.session_state.is_pro = True
                st.session_state.messages=[]
                st.session_state.show_upgrade=False
                persist_current_state()
                st.success("⚓ Founder activated!")
                st.rerun()
            elif key.startswith("cap-pro-"):
                st.session_state.is_pro = True  # Only this session becomes pro
                st.session_state.messages=[]
                st.session_state.show_upgrade=False
                persist_current_state()
                st.success("Pro activated!")
                st.rerun()
            else: st.error("Invalid key.")
        st.markdown('</div>',unsafe_allow_html=True)

    if st.session_state.is_founder:
        if st.button("Exit Founder Mode",use_container_width=True):
            st.session_state.is_founder=False
            st.session_state.is_pro=False
            st.session_state.messages=[]
            persist_current_state()
            st.rerun()
    elif st.session_state.is_pro:
        if st.button("Disconnect Pro",use_container_width=True):
            st.session_state.is_pro=False
            st.session_state.messages=[]
            persist_current_state()
            st.rerun()

    st.markdown(f'''
    <div class="privacy-badge">
      <div style="display:flex;align-items:center;justify-content:center;gap:5px;margin-bottom:0.3rem">
        <span style="color:#00ff88;font-size:0.8rem">⚓</span>
        <span style="font-size:0.6rem;color:#FFFFFF;font-weight:600">SOVEREIGN AI TECHNOLOGIES</span>
      </div>
      <div class="privacy-badge-text">
        🔒 <strong>Privacy First</strong> — No accounts. No tracking.<br>
        No personal data stored. TXID is your receipt.
      </div>
    </div>
    ''', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# MAIN CONTENT — PURE BLACK EDITION
# ═══════════════════════════════════════════════════════════════
ip = st.session_state.is_pro or st.session_state.is_founder

if not st.session_state.messages:
    tags = ["Finance", "African Markets", "Quant", "Coding", "Macro", "Quantum"]
    tags_html = "".join(f'<span class="welcome-tag">{t}</span>' for t in tags)
    st.markdown(f'''
    <div class="welcome-container">
      <div class="welcome-logo-ring">
        <span style="color:#00ff88;font-size:2.5rem">⚓</span>
      </div>
      <div class="welcome-title">How can I help today?</div>
      <div class="welcome-subtitle">Text-optimized intelligence. African market depth. Zero-cost architecture.</div>
      <div style="margin-bottom:0.5rem">{tags_html}</div>
    </div>
    ''', unsafe_allow_html=True)

for msg in st.session_state.messages:
    if msg["role"]=="user":
        st.markdown(f'<div class="chat-message chat-user">{msg["content"]}</div>',unsafe_allow_html=True)
    else:
        st.markdown(f'''
        <div class="chat-message chat-assistant">
          <div class="msg-header">
            <span class="msg-logo"><span style="color:#00ff88;font-size:0.75rem">⚓</span></span>
            <span style="font-size:0.6rem;color:#333;letter-spacing:0.05em">CAPITAN AI</span>
          </div>
          {msg["content"]}
        </div>
        ''', unsafe_allow_html=True)
        st.markdown('<div class="ai-note">CAPITAN AI can make mistakes. Verify important information.</div>',unsafe_allow_html=True)

ml = {"fast":"CAPITAN Fast","smart":"CAPITAN Smart","deep":"CAPITAN Deep Think"}
cml = ml.get(st.session_state.model,"CAPITAN Smart")
proj_label = f" · {st.session_state.projects[st.session_state.current_project_id]['name'][:18]}" if st.session_state.current_project_id and st.session_state.current_project_id in st.session_state.projects else ""
st.markdown(f'''
<div class="status-bar">
  <span style="color:#00ff88;font-size:0.7rem">⚓</span>
  <div class="status-dot"></div>
  {cml}{" · Web" if st.session_state.web_search_enabled else ""}
  {" · PRO" if ip else " · Free"}
  {proj_label}
</div>
''', unsafe_allow_html=True)

prompt = st.chat_input("Ask CAPITAN AI anything...")

if prompt:
    ip = st.session_state.is_pro or st.session_state.is_founder
    if not ip:
        if remaining_free <= 0:
            st.warning("100 messages used today. Resets in 24h. Upgrade to Pro for unlimited.")
            if st.button("✦ Upgrade to Pro — $15/month"): st.session_state.show_upgrade = True
            st.stop()
        st.session_state.daily_count += 1

    st.session_state.messages.append({"role":"user","content":prompt,"id":str(uuid.uuid4())}); persist_current_state()
    st.markdown(f'<div class="chat-message chat-user">{prompt}</div>',unsafe_allow_html=True)

    tp = st.empty()
    stages = ["Thinking...","Analyzing...","Generating..."]
    for stage in stages:
        tp.markdown(f'''
        <div class="thinking-indicator">
          <div class="thinking-dots">
            <div class="thinking-dot"></div>
            <div class="thinking-dot"></div>
            <div class="thinking-dot"></div>
          </div>
          <span style="color:#00ff88;font-size:0.7rem">⚓</span>
          <span>{stage}</span>
        </div>
        ''', unsafe_allow_html=True)
        time.sleep(0.18)

    rp = st.empty()
    accumulated_text = ""
    for accumulated_text in process_query(prompt, ip):
        rp.markdown(f'''
        <div class="chat-message chat-assistant">
          <div class="msg-header">
            <span class="msg-logo"><span style="color:#00ff88;font-size:0.75rem">⚓</span></span>
            <span style="font-size:0.6rem;color:#333;letter-spacing:0.05em">CAPITAN AI</span>
          </div>
          {accumulated_text}▌
        </div>
        ''', unsafe_allow_html=True)

    rp.markdown(f'''
    <div class="chat-message chat-assistant">
      <div class="msg-header">
        <span class="msg-logo"><span style="color:#00ff88;font-size:0.75rem">⚓</span></span>
        <span style="font-size:0.6rem;color:#333;letter-spacing:0.05em">CAPITAN AI</span>
      </div>
      {accumulated_text}
    </div>
    ''', unsafe_allow_html=True)

    tp.empty()
    st.markdown('<div class="ai-note">CAPITAN AI can make mistakes. Verify important information.</div>',unsafe_allow_html=True)

    st.session_state.messages.append({"role":"assistant","content":accumulated_text,"id":str(uuid.uuid4())}); persist_current_state()
    st.rerun()