import os, re, json, uuid, time, requests, sqlite3
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# ═══════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENAI_KEY     = os.environ.get("OPENAI_API_KEY", "")
GROQ_KEY       = os.environ.get("GROQ_API_KEY", "")
DB_PATH        = "capitan.db"

# ═══════════════════════════════════════════════════════════════════
# DATABASE — Extended for self-learning & feedback loops
# ═══════════════════════════════════════════════════════════════════
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY, email TEXT, tier TEXT DEFAULT "free",
        msg_count INTEGER DEFAULT 0, msg_window TEXT, created TEXT,
        expertise_profile TEXT DEFAULT "{}",
        interaction_style TEXT DEFAULT "balanced"
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY, memory_id TEXT, user_id TEXT,
        content TEXT, query TEXT, tier TEXT, domain TEXT,
        sentiment TEXT DEFAULT "neutral", quality_score REAL DEFAULT 0.0,
        created TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS payments (
        id TEXT PRIMARY KEY, user_id TEXT, txid TEXT,
        currency TEXT, amount REAL, tier TEXT, expires TEXT, created TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS payment_log (
        id TEXT PRIMARY KEY, user_id TEXT, tier TEXT,
        amount REAL, currency TEXT, txid TEXT, created TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS training (
        id TEXT PRIMARY KEY, user_id TEXT, query TEXT,
        response TEXT, domain TEXT, tier TEXT,
        feedback INTEGER DEFAULT 0, created TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS learning_patterns (
        id TEXT PRIMARY KEY, domain TEXT, pattern TEXT,
        frequency INTEGER DEFAULT 1, last_seen TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS user_knowledge_graph (
        id TEXT PRIMARY KEY, user_id TEXT,
        topic TEXT, depth_level TEXT, last_interaction TEXT,
        interaction_count INTEGER DEFAULT 1
    )''')

    conn.commit()
    conn.close()

init_db()

def sid(): return str(uuid.uuid4())[:8].upper()
def mid(): return 'mem_' + sid()

# ═══════════════════════════════════════════════════════════════════
# SELF-LEARNING ENGINE
# ═══════════════════════════════════════════════════════════════════
def update_learning_pattern(domain: str, query: str):
    """Track recurring query patterns for adaptive intelligence."""
    keywords = re.findall(r'\b[a-z]{4,}\b', query.lower())
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for kw in keywords[:5]:
        c.execute("SELECT id, frequency FROM learning_patterns WHERE domain=? AND pattern=?", (domain, kw))
        row = c.fetchone()
        if row:
            c.execute("UPDATE learning_patterns SET frequency=frequency+1, last_seen=? WHERE id=?",
                      (datetime.now().isoformat(), row[0]))
        else:
            c.execute("INSERT INTO learning_patterns (id, domain, pattern, frequency, last_seen) VALUES (?,?,?,1,?)",
                      (sid(), domain, kw, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def update_user_knowledge_graph(user_id: str, domain: str, query: str):
    """Build a per-user knowledge profile over time."""
    topic = classify_subtopic(query, domain)
    depth = infer_expertise_depth(query)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM user_knowledge_graph WHERE user_id=? AND topic=?", (user_id, topic))
    row = c.fetchone()
    if row:
        c.execute("UPDATE user_knowledge_graph SET depth_level=?, last_interaction=?, interaction_count=interaction_count+1 WHERE id=?",
                  (depth, datetime.now().isoformat(), row[0]))
    else:
        c.execute("INSERT INTO user_knowledge_graph (id, user_id, topic, depth_level, last_interaction, interaction_count) VALUES (?,?,?,?,?,1)",
                  (sid(), user_id, topic, depth, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_user_profile(user_id: str) -> dict:
    """Retrieve what CAPITAN has learned about this user."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT topic, depth_level, interaction_count FROM user_knowledge_graph WHERE user_id=? ORDER BY interaction_count DESC LIMIT 8", (user_id,))
    topics = [{"topic": r[0], "depth": r[1], "count": r[2]} for r in c.fetchall()]
    c.execute("SELECT domain, COUNT(*) as cnt FROM memories WHERE user_id=? GROUP BY domain ORDER BY cnt DESC LIMIT 3", (user_id,))
    domains = [r[0] for r in c.fetchall()]
    conn.close()
    return {"top_topics": topics, "frequent_domains": domains}

def classify_subtopic(query: str, domain: str) -> str:
    q = query.lower()
    subtopic_map = {
        "finance": {
            "options": r'option|call|put|strike|expiry|black.scholes|greeks|delta|gamma|vega|theta',
            "forex": r'forex|fx|currency pair|pip|spread|carry trade|eurusd|gbpusd',
            "crypto": r'bitcoin|ethereum|defi|nft|blockchain|web3|altcoin|stablecoin',
            "africa_markets": r'gse|nse|jse|ngx|dse|brvm|african stock|nairobi|accra bourse',
            "commodities": r'gold|oil|crude|cocoa|coffee|commodity|futures|spot price',
            "dcf": r'dcf|discounted cash flow|npv|irr|wacc|terminal value|capex',
            "macro": r'gdp|inflation|interest rate|fed|central bank|monetary policy|yield curve',
        },
        "coding": {
            "algorithms": r'algorithm|complexity|big o|sort|search|tree|graph|dynamic programming',
            "web": r'react|nextjs|html|css|tailwind|frontend|backend|rest api|graphql',
            "devops": r'docker|kubernetes|ci\/cd|github actions|terraform|aws|gcp|azure',
            "security_code": r'sql injection|xss|csrf|owasp|sanitize|auth|jwt|oauth',
            "data_engineering": r'etl|pipeline|kafka|airflow|spark|data warehouse|dbt',
        },
        "quant": {
            "derivatives": r'option pricing|stochastic|ito|black.scholes|heston|sabr',
            "risk": r'var|cvar|stress test|drawdown|correlation|covariance|tail risk',
            "ml_quant": r'lstm|transformer|xgboost|feature engineering|alpha|signal',
            "portfolio": r'markowitz|efficient frontier|sharpe|sortino|capm|factor model',
            "hft": r'high frequency|market microstructure|order book|latency|arbitrage',
        },
        "cyber": {
            "pentest": r'pentest|exploit|payload|metasploit|kali|recon|enumeration',
            "forensics": r'forensics|memory dump|artifacts|timeline|hash|chain of custody',
            "networking": r'firewall|ids|ips|packet|wireshark|tcp|dns|vpn|zero trust',
            "malware": r'malware|ransomware|trojan|reverse engineering|sandbox|ioc',
            "cloud_security": r'iam|s3 bucket|misconfig|cloud trail|azure ad|privilege escalation',
        },
        "science": {
            "biotech": r'crispr|gene|protein|mrna|pcr|sequencing|antibody|clinical trial',
            "quantum": r'qubit|superposition|entanglement|quantum gate|shor|grover',
            "physics": r'relativity|thermodynamics|wave|particle|field theory|plasma',
            "ai_science": r'neural network|transformer|attention|llm|rl|gradient|backprop',
        },
    }
    domain_map = subtopic_map.get(domain, {})
    for subtopic, pattern in domain_map.items():
        if re.search(pattern, q):
            return f"{domain}:{subtopic}"
    return domain

def infer_expertise_depth(query: str) -> str:
    q = query.lower()
    advanced_signals = r'stochastic|eigenvalue|hessian|microstructure|mev|zero.day|ito lemma|tensor|manifold|topology|cvar|sabr|entropy|convexity|delta neutral|basis risk|kolmogorov'
    intermediate_signals = r'backtest|portfolio|api|function|class|recursive|regression|monte carlo|var|jwt|oauth|correlation|volatility|drawdown'
    if re.search(advanced_signals, q): return "expert"
    if re.search(intermediate_signals, q): return "intermediate"
    if len(query.split()) > 20: return "intermediate"
    return "beginner"

# ═══════════════════════════════════════════════════════════════════
# AI CALLER — Multi-provider with tier routing
# ═══════════════════════════════════════════════════════════════════
def call_ai(messages, tier="free"):
    models = {
        "free":    "deepseek/deepseek-chat",
        "plus":    "meta-llama/llama-3.3-70b-instruct",
        "pro":     "anthropic/claude-sonnet-4-5",
        "founder": "anthropic/claude-sonnet-4-5"
    }
    model = models.get(tier, models["free"])
    max_tokens = {
        "free": 1000,
        "plus": 2500,
        "pro": 4000,
        "founder": 6000
    }.get(tier, 1000)

    # Try OpenRouter (primary)
    if OPENROUTER_KEY:
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://capitan.pages.dev",
                    "X-Title": "CAPITAN AI"
                },
                json={"model": model, "messages": messages, "temperature": 0.25, "max_tokens": max_tokens},
                timeout=90
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
        except:
            pass

    # Fallback: OpenAI
    if OPENAI_KEY:
        try:
            r = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
                json={"model": "gpt-4o-mini", "messages": messages, "temperature": 0.25, "max_tokens": max_tokens},
                timeout=60
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
        except:
            pass

    # Fallback: Groq
    if GROQ_KEY:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile", "messages": messages, "temperature": 0.25, "max_tokens": max_tokens},
                timeout=60
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
        except:
            pass

    return None

# ═══════════════════════════════════════════════════════════════════
# DOMAIN CLASSIFIER — Expanded, precise
# ═══════════════════════════════════════════════════════════════════
def classify(q: str) -> str:
    q = q.lower()
    if re.search(r'python|javascript|typescript|rust|go|java|c\+\+|kotlin|swift|react|nextjs|node|api|code|program|def |class |function|algorithm|sql|database|mongodb|redis|docker|kubernetes|microservice|devops|git|deploy', q): return 'coding'
    if re.search(r'exploit|pentest|vulnerability|zero.day|cve|malware|ransomware|phishing|firewall|ids|ips|siem|forensics|incident response|osint|recon|burp suite|metasploit|reverse shell|privilege escalation|ctf|blue team|red team|soc|threat intel', q): return 'cyber'
    if re.search(r'stochastic|ito lemma|sde|pde|black.scholes|heston|sabr|sabr|var|cvar|sharpe|sortino|drawdown|backtest|monte carlo|markowitz|efficient frontier|factor model|alpha|beta|capm|kelly criterion|options pricing|greeks|delta|gamma|vega|theta|vix|implied volatility|order book|market microstructure|hft|arbitrage|stat arb|pairs trading', q): return 'quant'
    if re.search(r'stock|revenue|ebitda|valuation|dcf|p\/e|ev|merger|acquisition|ipo|bond|yield|duration|credit|forex|fx|crypto|bitcoin|ethereum|defi|nft|commodity|gold|oil|hedge fund|private equity|venture capital|inflation|interest rate|central bank|monetary policy|fiscal policy|gse|nse|jse|accra bourse|nigerian exchange|nairobi|african market|mobile money|cedi|naira|rand|shilling|birr|momo payment', q): return 'finance'
    if re.search(r'crispr|dna|rna|protein|gene|pcr|mrna|antibody|clinical trial|drug discovery|physics|quantum|relativity|thermodynamics|chemistry|organic|inorganic|biology|ecology|neuroscience|llm|transformer|attention|neural|backprop|gradient|tensor|reinforcement learning', q): return 'science'
    if re.search(r'mobile money|momo|ghana card|nhis|ecg|dstv|gra|dvla|cedi|accra|kumasi|tamale|pidgin|naija|lagos|abuja|nairobi|johannesburg|kampala|dar es salaam|kigali|african', q): return 'local'
    if re.search(r'market|trade|position|entry|exit|setup|chart|candle|trend|support|resistance|breakout|momentum|rsi|macd|ema|sma|fibonacci|elliott|volume|liquidity|spread|slippage|execution|broker|leverage|margin|risk reward|stop loss|take profit', q): return 'trading'
    return 'general'

# ═══════════════════════════════════════════════════════════════════
# SYSTEM PROMPT — ELITE INTELLIGENCE BRAIN
# ═══════════════════════════════════════════════════════════════════
def system_prompt(domain: str, tier: str, user_id: str = None, depth: str = "intermediate") -> str:

    base = """You are CAPITAN — an elite intelligence system engineered by CLOSEAI Technologies. You are not a chatbot. You are a thinking partner, a strategic advisor, and a professional collaborator for experts around the world.

═══════════════════════════════════
IDENTITY & PHILOSOPHY
═══════════════════════════════════
You speak with the quiet confidence of someone who has mastered their craft. You are warm, precise, and never condescending. You treat every person as a capable professional deserving of real depth, not watered-down summaries.

You hold yourself to the standard of the world's best analyst, engineer, trader, scientist, or strategist — depending on the context. When you don't know something, you say so honestly and explore what you do know.

You understand Africa deeply: its markets, currencies, infrastructure, culture, regulatory environments, and the unique economic dynamics that make it different from the West. You also understand global markets, Western finance, Silicon Valley engineering culture, and international science.

═══════════════════════════════════
COMMUNICATION STYLE
═══════════════════════════════════
• Lead with the most important insight — not preamble
• Speak naturally, like a brilliant colleague explaining something over coffee
• Match the user's sophistication level — never talk down, never over-complicate
• Use **bold** for key terms and critical insights
• Code always in ```language``` blocks with production-quality standards
• Tables and structured formats when comparing options or data
• Ask one sharp clarifying question if the problem is ambiguous — never multiple
• Acknowledge uncertainty honestly: "The data on this is mixed..." or "My view here is..."
• Never give direct buy/sell/trade signals — frame as analysis and frameworks instead
• If asked something outside your knowledge boundary, explore adjacent knowledge usefully

═══════════════════════════════════
SELF-IMPROVEMENT PRINCIPLE
═══════════════════════════════════
Each conversation makes you more useful. You build on what the user has shared before, adapt your depth to their expertise, and remember the context of ongoing work. You are always learning.
"""

    # ─── DOMAIN INTELLIGENCE MODULES ───────────────────────────────

    domain_modules = {

        'finance': """
═══════════════════════════════════
DOMAIN: ELITE FINANCIAL INTELLIGENCE
═══════════════════════════════════
You are a world-class financial analyst with deep knowledge across:

GLOBAL MARKETS:
• Equity markets: valuation (DCF, comps, LBO, sum-of-the-parts), capital structure, M&A, IPOs, activist investing
• Fixed income: bond pricing, duration, convexity, credit spreads, yield curve dynamics, sovereign debt
• Derivatives: options theory (Black-Scholes, binomial, Monte Carlo), Greeks, hedging strategies, structured products
• Macro: Fed policy, fiscal multipliers, inflation dynamics, currency regimes, geopolitical risk
• Alternative assets: private equity, venture capital, real assets, hedge fund strategies
• Crypto & DeFi: on-chain analytics, tokenomics, protocol mechanics, DeFi risk (impermanent loss, liquidation cascades)

AFRICAN MARKETS (deep expertise):
• Equity exchanges: GSE (Ghana), NGX (Nigeria), JSE (South Africa), NSE (Nairobi), BRVM (Francophone West Africa), DSE (Tanzania), USE (Uganda)
• Currency dynamics: cedi depreciation, naira parallel market, rand volatility, impact of commodity cycles on African FX
• Mobile money ecosystem: M-Pesa, MTN MoMo, Airtel Money — payment infrastructure, float economics, financial inclusion
• African sovereign debt: Eurobonds, domestic T-bills, IMF/World Bank programs, restructuring history
• Regulatory environment: SEC Ghana, CBN Nigeria, SARB South Africa, capital controls, local content rules
• Commodity markets as they relate to African economies: gold, cocoa, oil, copper, lithium

ANALYSIS FRAMEWORKS:
• Always explore bull/bear/base cases when assessing situations
• Quantify risks with ranges, not just directional statements
• Connect macro forces to individual asset/company implications
• Surface second-order effects that non-experts miss

HARD RULE: Never say "buy X" or "sell Y." Instead: "The setup suggests a risk/reward of..." or "The bull case requires X to hold..."
""",

        'coding': """
═══════════════════════════════════
DOMAIN: ELITE SOFTWARE ENGINEERING
═══════════════════════════════════
You are a senior engineer with production experience across multiple stacks. You write code that is clean, tested, and deployable — not toy examples.

LANGUAGES & FRAMEWORKS (deep expertise):
• Python: async/await, Pydantic, FastAPI, SQLAlchemy, Pandas/Polars, NumPy, type hints, decorators, metaclasses
• JavaScript/TypeScript: React, Next.js, Node.js, tRPC, Prisma, Zod, modern ES features, SSR/SSG/ISR
• Systems: Rust (ownership model, lifetimes, async), Go (goroutines, channels), C++ (memory management, RAII)
• Data: SQL (window functions, CTEs, query optimization), MongoDB, Redis, Kafka, Spark, dbt
• Cloud & DevOps: Docker, Kubernetes, GitHub Actions, Terraform, AWS/GCP/Azure, serverless, CDN strategies
• AI/ML: PyTorch, Hugging Face, LangChain, RAG architectures, vector databases (Pinecone, Qdrant), fine-tuning

CODE STANDARDS:
• Write production-grade code with proper error handling, logging, and type safety
• Include time/space complexity analysis for algorithms
• Add security considerations (input validation, auth, secrets management)
• Explain architectural decisions, not just syntax
• Surface edge cases and failure modes proactively
• When reviewing code, catch performance issues, security holes, and anti-patterns
""",

        'trading': """
═══════════════════════════════════
DOMAIN: PROFESSIONAL MARKETS INTELLIGENCE
═══════════════════════════════════
You are a markets professional who understands trading deeply — from execution mechanics to strategy design to risk management. You speak the language of traders: prop shops, hedge funds, independent operators.

TECHNICAL ANALYSIS & MARKET STRUCTURE:
• Price action: candlestick patterns, structure breaks (BOS, CHOCH), supply/demand zones, fair value gaps
• Indicators: RSI divergence, MACD signal, EMA crossovers, VWAP, volume profile, ATR-based position sizing
• Market microstructure: bid/ask spread dynamics, order flow, liquidity pools, stop hunts, institutional footprints
• Multi-timeframe analysis: alignment, confluence, top-down analysis from macro to execution

STRATEGY FRAMEWORKS:
• Trend following, mean reversion, breakout, scalping, swing trading — mechanics and conditions for each
• Risk management: position sizing (fixed %, Kelly, ATR-based), R-multiple tracking, max drawdown controls
• Portfolio construction: correlation management, sector rotation, hedging with options/futures
• Psychology: discipline under drawdown, avoiding revenge trading, journaling practices

GLOBAL & AFRICAN TRADING CONTEXTS:
• African stock exchanges: liquidity constraints, T+3 settlement, foreign investor access, currency risk
• Commodities tied to African exports: cocoa (Ghana/Ivory Coast), oil (Nigeria/Angola), gold (Ghana/SA)
• Crypto in Africa: P2P dynamics, arbitrage between exchanges, mobile money on/off ramps

RULE: All analysis is educational and framework-based. Never: "Go long now." Always: "The risk/reward structure here is X because..."
""",

        'quant': """
═══════════════════════════════════
DOMAIN: QUANTITATIVE FINANCE & RESEARCH
═══════════════════════════════════
You are a quantitative researcher with expertise spanning mathematical finance, statistical modeling, and systematic strategy development. You write rigorous, implementable research.

MATHEMATICAL FINANCE:
• Stochastic calculus: Itô's lemma, Girsanov, Feynman-Kac, SDEs (GBM, mean-reverting, jump-diffusion)
• Option pricing: Black-Scholes derivation, risk-neutral pricing, numerical methods (FDM, Monte Carlo, binomial trees)
• Volatility models: local vol (Dupire), stochastic vol (Heston, SABR), VIX term structure, vol surface calibration
• Interest rate models: Hull-White, CIR, HJM framework, LIBOR market model
• Fixed income quant: bond pricing, OAS, convexity hedging, mortgage prepayment models

RISK & PORTFOLIO:
• Market risk: VaR (historical, parametric, Monte Carlo), CVaR/Expected Shortfall, stress testing, scenario analysis
• Portfolio optimization: mean-variance (Markowitz), Black-Litterman, risk parity, hierarchical risk parity (HRP)
• Factor models: Fama-French, Barra, PCA-based factors, alpha/beta decomposition
• Drawdown analytics: max drawdown, Calmar, Ulcer Index, drawdown duration distributions

SYSTEMATIC STRATEGIES:
• Backtesting: data snooping bias, look-ahead bias, survivorship bias, walk-forward validation
• Signal construction: momentum (time-series, cross-sectional), mean reversion, carry, value
• Execution modeling: market impact (Almgren-Chriss), transaction costs, slippage modeling
• ML in quant: feature engineering for financial time series, LSTM/transformer for forecasting, regularization

CODE: Default to Python with NumPy, Pandas, SciPy, statsmodels. Show math then implementation.
""",

        'cyber': """
═══════════════════════════════════
DOMAIN: ELITE CYBERSECURITY INTELLIGENCE
═══════════════════════════════════
You are a seasoned security professional — red team operator, blue team defender, and security architect. You think like an attacker to defend like an expert.

OFFENSIVE SECURITY (ethical/educational):
• Penetration testing methodology: recon (OSINT, passive/active), scanning, enumeration, exploitation, post-exploitation, reporting
• Web application security: OWASP Top 10 (SQLi, XSS, CSRF, SSRF, XXE, IDOR, broken auth), advanced bypass techniques
• Network attacks: ARP spoofing, MITM, DNS poisoning, lateral movement, pivoting, C2 frameworks
• Exploit development: buffer overflows, ROP chains, heap exploitation (conceptual education)
• Social engineering: phishing, pretexting, vishing — awareness and simulation

DEFENSIVE SECURITY:
• Security architecture: zero-trust, defense-in-depth, principle of least privilege, microsegmentation
• Identity & Access: MFA, PAM, SSO, OAuth/OIDC flows, AD hardening, Azure AD security
• SIEM & Detection: log ingestion, correlation rules, MITRE ATT&CK mapping, threat hunting, IOC enrichment
• Incident response: triage, containment, eradication, recovery, post-mortem, chain of custody
• Threat intelligence: TTP analysis, actor profiling, dark web monitoring, threat feeds

CLOUD & APPLICATION SECURITY:
• Cloud misconfigs: S3 bucket exposure, IAM privilege escalation, metadata service attacks
• Container security: Docker escape, Kubernetes RBAC, image scanning, runtime protection
• AppSec: SAST/DAST, secure SDLC, secrets management, dependency scanning, supply chain attacks
• Cryptography: TLS/SSL, PKI, symmetric vs asymmetric, post-quantum considerations

AFRICA-SPECIFIC THREATS: Mobile money fraud, SIM swapping attacks on African telcos, BEC targeting African businesses, regional threat actors.

RULE: All offensive knowledge is framed for defense, education, and authorized testing. Never assist in unauthorized access.
""",

        'science': """
═══════════════════════════════════
DOMAIN: ADVANCED SCIENCE & TECHNOLOGY
═══════════════════════════════════
You are a multidisciplinary scientist who can go deep across fields, connecting first principles to cutting-edge research.

LIFE SCIENCES & BIOTECH:
• Molecular biology: DNA/RNA mechanisms, CRISPR-Cas9 (base editing, prime editing, epigenome editing), gene therapy delivery vectors
• Protein science: structure prediction (AlphaFold), folding mechanics, drug-target interactions, antibody engineering
• Genomics: sequencing technologies (short/long read), variant calling, GWAS, pharmacogenomics
• Drug discovery: target identification, hit-to-lead, ADMET, clinical trial phases, regulatory pathways (FDA/EMA)
• Synthetic biology: metabolic engineering, cell-free systems, biosensors

PHYSICS & ENGINEERING:
• Quantum mechanics: wave functions, measurement, entanglement, decoherence, quantum computing (qubits, gates, error correction)
• Thermodynamics & statistical mechanics: entropy, phase transitions, Boltzmann, partition functions
• Materials science: semiconductors, superconductors, 2D materials (graphene), nanotechnology
• Energy systems: solar PV physics, battery electrochemistry, nuclear fission/fusion basics

AI & MACHINE LEARNING (scientific depth):
• Deep learning theory: universal approximation, optimization landscapes, generalization, double descent
• Transformer architecture: attention mechanisms, positional encoding, scaling laws, emergent capabilities
• Reinforcement learning: MDP formulation, policy gradients, actor-critic, RLHF
• Scientific ML: physics-informed neural networks, differentiable programming, AI for drug discovery

SCIENCE IN AFRICA: CRISPR applications for African diseases (sickle cell, malaria), African genomics diversity, climate science for African agriculture, clean energy access.
""",

        'local': """
═══════════════════════════════════
DOMAIN: AFRICAN LOCAL INTELLIGENCE
═══════════════════════════════════
You know Africa from the inside — not as an outsider looking in.

GHANA (deep):
• Mobile money: MTN MoMo, Vodafone Cash, AirtelTigo Money — USSD codes, transaction limits, merchant payments, QR systems
• Ghana Card (NIA): registration, use cases, linking to bank accounts, GRA TIN integration
• NHIS: registration, renewal, covered services, claims process, NIA linkage
• Banking: GCB, Absa, Stanchart, Ecobank, CalBank, Fidelity — account types, charges, FX access
• ECG/PURC: credit meter processes, billing disputes, load shedding (Dumsor) patterns
• DVLA: vehicle registration, roadworthy certificates, driver's license processes
• GRA: filing seasons, withholding tax, VAT, transfer pricing for businesses
• Real estate: land title issues, Lands Commission processes, Land Use and Spatial Planning Act
• Markets: Makola, Kejetia, Trade Fair — price dynamics, seasonal patterns
• Transportation: Accra Metro, trotro routes, Uber/Bolt dynamics, intercity travel

WEST AFRICA:
• Nigeria: CBN policy, fintech ecosystem (Paystack, Flutterwave, Opay), Lagos/Abuja business environment, FIRS tax
• Senegal/BRVM: CFA franc dynamics, Dakar financial hub, regional securities exchange
• Ivory Coast: Abidjan as financial center, cocoa market dynamics

EAST AFRICA:
• Kenya: M-Pesa (the original), Safaricom ecosystem, NSE, Nairobi as tech hub
• Ethiopia, Tanzania, Rwanda: emerging market dynamics, mobile money expansion

PAN-AFRICAN:
• AfCFTA implications, Afreximbank, African Development Bank, diaspora remittances
• Cross-border payment challenges and fintech solutions (Chipper Cash, Nala, Lemonade Finance)
""",

        'general': """
You are a brilliant generalist — curious, deeply read, and able to synthesize insights across domains. 

For every question, aim to:
• Surface the non-obvious angle that makes the answer more useful
• Connect ideas across disciplines when relevant
• Give a calibrated view: what's known, what's uncertain, what's actively debated
• Be a thinking partner, not just an answer machine

Adapt depth to what the person needs. Sometimes one clear paragraph is better than a comprehensive treatise.
"""
    }

    base += domain_modules.get(domain, domain_modules['general'])

    # ─── TIER MODIFIERS ─────────────────────────────────────────────
    tier_context = {
        "free":    "\n\nProvide a complete, useful answer. Offer to go deeper if needed.",
        "plus":    "\n\nProvide thorough analysis with supporting reasoning. Include examples and edge cases.",
        "pro":     "\n\nProvide expert-level depth. Include quantitative frameworks, code when relevant, multiple perspectives, and professional-grade analysis.",
        "founder": "\n\nNo limits on depth. Go as deep as the question demands. Include derivations, code, original frameworks, and strategic synthesis."
    }
    base += tier_context.get(tier, tier_context["free"])

    # ─── DEPTH ADAPTATION ───────────────────────────────────────────
    depth_context = {
        "beginner":     "\n\nThis person is newer to this domain — build intuition before formulas. Use analogies. Don't assume jargon familiarity.",
        "intermediate": "\n\nThis person has working knowledge — skip basics, go into mechanisms and trade-offs.",
        "expert":       "\n\nThis is an expert — use technical language freely, go into nuance, engage as a peer. Challenge assumptions where appropriate."
    }
    base += depth_context.get(depth, depth_context["intermediate"])

    # ─── USER MEMORY & CONTEXT ──────────────────────────────────────
    if user_id:
        try:
            profile = get_user_profile(user_id)
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT query, content FROM memories WHERE user_id=? ORDER BY created DESC LIMIT 5", (user_id,))
            rows = c.fetchall()
            conn.close()

            if rows or profile["top_topics"]:
                base += "\n\n═══════════════════════════════════\nUSER CONTEXT (use for continuity)\n═══════════════════════════════════"
                if profile["top_topics"]:
                    topics_str = ", ".join([f"{t['topic']} ({t['depth']})" for t in profile["top_topics"][:4]])
                    base += f"\nUser's knowledge profile: {topics_str}"
                if rows:
                    base += "\nRecent conversation thread:"
                    for row in rows[:3]:
                        base += f"\n• Asked: {row[0][:100]}"
                base += "\nUse this to maintain continuity. Adapt your depth accordingly. Don't explicitly reference 'your profile' — just be naturally calibrated."
        except:
            pass

    return base

# ═══════════════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════════════
class ChatRequest(BaseModel):
    messages: list
    user_id: str = "anonymous"
    stream: bool = False

class AuthRequest(BaseModel):
    email: str

class UpgradeRequest(BaseModel):
    user_id: str
    tier: str
    txid: str
    currency: str = "USDC"

class FounderRequest(BaseModel):
    user_id: str
    code: str

class AdminRequest(BaseModel):
    code: str

class FeedbackRequest(BaseModel):
    user_id: str
    memory_id: str
    score: int  # 1 = helpful, -1 = not helpful

# ═══════════════════════════════════════════════════════════════════
# APP
# ═══════════════════════════════════════════════════════════════════
app = FastAPI(title="CAPITAN AI Brain", version="2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/")
def root():
    return {"name": "CAPITAN AI Brain", "version": "2.0", "status": "operational", "intelligence": "elite"}

@app.get("/health")
def health():
    return {"status": "ok", "brain": "active", "version": "2.0"}

# ─── AUTH ────────────────────────────────────────────────────────
@app.post("/api/auth")
def auth(req: AuthRequest):
    if not req.email or '@' not in req.email:
        raise HTTPException(400, "Valid email required")
    clean = req.email.lower().strip()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, tier FROM users WHERE email=?", (clean,))
    row = c.fetchone()
    if not row:
        uid = 'u_' + sid()
        c.execute("INSERT INTO users (id, email, tier, msg_count, msg_window, created) VALUES (?,?,?,0,?,?)",
                  (uid, clean, 'free', datetime.now().isoformat(), datetime.now().isoformat()))
        conn.commit()
        row = (uid, 'free')
    conn.close()
    return {"user_id": row[0], "email": clean, "tier": row[1]}

# ─── CHAT ────────────────────────────────────────────────────────
@app.post("/api/chat")
def chat(req: ChatRequest):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT tier, msg_count, msg_window FROM users WHERE id=?", (req.user_id,))
    row = c.fetchone()
    tier = row[0] if row else 'free'
    msg_count = row[1] if row else 0

    # Free tier: 30 msgs / 24 hours
    if tier == 'free' and msg_count >= 30:
        w = datetime.fromisoformat(row[2]) if row and row[2] else datetime.now()
        if datetime.now() - w < timedelta(hours=24):
            conn.close()
            return {
                "error": "Daily limit reached",
                "can_send": False,
                "reset_in": str(timedelta(hours=24) - (datetime.now() - w))
            }
        c.execute("UPDATE users SET msg_count=0, msg_window=? WHERE id=?",
                  (datetime.now().isoformat(), req.user_id))
        conn.commit()

    # Extract user message
    user_msg = ""
    for m in reversed(req.messages):
        if m.get("role") == "user":
            user_msg = m["content"]
            break

    if not user_msg.strip():
        conn.close()
        raise HTTPException(400, "No message provided")

    # Increment message count
    c.execute("UPDATE users SET msg_count = msg_count + 1 WHERE id=?", (req.user_id,))
    conn.commit()
    conn.close()

    # Intelligence pipeline
    domain = classify(user_msg)
    depth  = infer_expertise_depth(user_msg)
    prompt = system_prompt(domain, tier, req.user_id, depth)

    # Build LLM message array
    llm_msgs = [{"role": "system", "content": prompt}]
    for m in req.messages:
        llm_msgs.append({"role": m.get("role", "user"), "content": m.get("content", "")})

    # Call AI
    result = call_ai(llm_msgs, tier)

    # Self-learning updates
    update_learning_pattern(domain, user_msg)
    update_user_knowledge_graph(req.user_id, domain, user_msg)

    # Store memory + training data
    memory_id = mid()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO memories (id, memory_id, user_id, content, query, tier, domain, created) VALUES (?,?,?,?,?,?,?,?)",
        (sid(), memory_id, req.user_id, result or '', user_msg, tier, domain, datetime.now().isoformat())
    )
    c.execute(
        "INSERT INTO training (id, user_id, query, response, domain, tier, created) VALUES (?,?,?,?,?,?,?)",
        (sid(), req.user_id, user_msg, result or '', domain, tier, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

    return {
        "content": result or "I encountered an issue generating a response. Please try again.",
        "domain": domain,
        "depth": depth,
        "memory_id": memory_id
    }

# ─── FEEDBACK (self-learning signal) ─────────────────────────────
@app.post("/api/feedback")
def feedback(req: FeedbackRequest):
    if req.score not in (-1, 1):
        raise HTTPException(400, "Score must be 1 or -1")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE training SET feedback=? WHERE user_id=? AND id=(SELECT id FROM memories WHERE memory_id=? LIMIT 1)",
              (req.score, req.user_id, req.memory_id))
    conn.commit()
    conn.close()
    return {"ok": True, "signal": "learning updated"}

# ─── USER PROFILE ────────────────────────────────────────────────
@app.get("/api/profile/{user_id}")
def profile(user_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT tier, msg_count, created FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    if not row:
        raise HTTPException(404, "User not found")
    knowledge = get_user_profile(user_id)
    c.execute("SELECT domain, COUNT(*) FROM memories WHERE user_id=? GROUP BY domain", (user_id,))
    domain_counts = {r[0]: r[1] for r in c.fetchall()}
    conn.close()
    return {
        "user_id": user_id,
        "tier": row[0],
        "total_messages": row[1],
        "member_since": row[2],
        "knowledge_profile": knowledge,
        "domain_activity": domain_counts
    }

# ─── UPGRADE ─────────────────────────────────────────────────────
@app.post("/api/upgrade")
def upgrade(req: UpgradeRequest):
    prices = {"plus": 8, "pro": 17}
    if req.tier not in prices:
        raise HTTPException(400, "Invalid tier. Choose: plus or pro")
    if not req.txid.strip():
        raise HTTPException(400, "Transaction ID required")

    cur = req.currency.upper()
    expiry = (datetime.now() + timedelta(days=30)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO payments (id, user_id, txid, currency, amount, tier, expires, created) VALUES (?,?,?,?,?,?,?,?)",
        (sid(), req.user_id, req.txid.strip(), cur, prices[req.tier], req.tier, expiry, datetime.now().isoformat())
    )
    c.execute("UPDATE users SET tier=?, msg_count=0 WHERE id=?", (req.tier, req.user_id))
    c.execute(
        "INSERT INTO payment_log (id, user_id, tier, amount, currency, txid, created) VALUES (?,?,?,?,?,?,?)",
        (sid(), req.user_id, req.tier, prices[req.tier], cur, req.txid, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return {"verified": True, "tier": req.tier, "expires": expiry}

# ─── FOUNDER ACCESS ──────────────────────────────────────────────
@app.post("/api/founder")
def founder(req: FounderRequest):
    if req.code != "Osinachi@350":
        raise HTTPException(403, "Invalid founder code")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET tier='founder', msg_count=0 WHERE id=?", (req.user_id,))
    conn.commit()
    conn.close()
    return {"verified": True, "tier": "founder", "access": "unlimited"}

# ─── ADMIN ───────────────────────────────────────────────────────
@app.post("/api/admin")
def admin(req: AdminRequest):
    if req.code != "Osinachi@350":
        raise HTTPException(403, "Access denied")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT id, email, tier, msg_count, created FROM users ORDER BY created DESC LIMIT 100")
    users = [{"id": r[0], "email": r[1], "tier": r[2], "msg_count": r[3], "created": r[4]} for r in c.fetchall()]

    c.execute("SELECT * FROM payment_log ORDER BY created DESC LIMIT 100")
    payments = [{"user_id": r[1], "tier": r[2], "amount": r[3], "currency": r[4], "txid": r[5], "created": r[6]} for r in c.fetchall()]

    c.execute("SELECT domain, COUNT(*) as cnt FROM training GROUP BY domain ORDER BY cnt DESC")
    domain_stats = {r[0]: r[1] for r in c.fetchall()}

    c.execute("SELECT domain, pattern, frequency FROM learning_patterns ORDER BY frequency DESC LIMIT 20")
    top_patterns = [{"domain": r[0], "pattern": r[1], "frequency": r[2]} for r in c.fetchall()]

    c.execute("SELECT tier, COUNT(*) FROM users GROUP BY tier")
    tier_breakdown = {r[0]: r[1] for r in c.fetchall()}

    conn.close()
    return {
        "users": users,
        "payments": payments,
        "total_users": len(users),
        "tier_breakdown": tier_breakdown,
        "domain_activity": domain_stats,
        "top_learning_patterns": top_patterns
    }

# ─── INSIGHTS (trending topics CAPITAN has learned) ──────────────
@app.get("/api/insights")
def insights():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT domain, pattern, frequency FROM learning_patterns ORDER BY frequency DESC LIMIT 30")
    patterns = [{"domain": r[0], "topic": r[1], "frequency": r[2]} for r in c.fetchall()]
    conn.close()
    return {"trending_topics": patterns, "generated": datetime.now().isoformat()}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
