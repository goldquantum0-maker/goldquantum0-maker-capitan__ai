"""
=============================================================================
CAPITAN BY CLOSEAI - ENTERPRISE BACKEND
Built by CloseAI Technologies
=============================================================================
"""
import os
import time
import secrets
import httpx
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, status, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic_settings import BaseSettings
from pydantic import BaseModel
from jose import jwt, JWTError
from supabase import create_client, Client
import redis.asyncio as redis
import openai
import anthropic

# =============================================================================
# 1. CONFIGURATION & ENVIRONMENT
# =============================================================================
class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    REDIS_URL: str
    OPENAI_API_KEY: str
    ANTHROPIC_API_KEY: str
    RESEND_API_KEY: str
    FOUNDER_CODE: str = "CLOSEAI2024"  # Secret code for Absolute tier
    APP_ENV: str = "production"

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()

# =============================================================================
# 2. CLIENTS
# =============================================================================
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
supabase_admin: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
openai_client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)anthropic_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

# =============================================================================
# 3. LIFESPAN & APP INIT
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
    yield
    await app.state.redis.close()

app = FastAPI(
    title="Capitan by CloseAI",
    description="Enterprise Intelligence Platform",
    version="3.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Restrict to your Cloudflare domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# 4. SECURITY & AUTHENTICATION
# =============================================================================
security = HTTPBearer()
jwks_cache = {"keys": [], "last_fetched": 0}

async def get_supabase_jwks():
    if time.time() - jwks_cache["last_fetched"] > 3600:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.SUPABASE_URL}/auth/v1/jwks")
            jwks_cache["keys"] = response.json()["keys"]
            jwks_cache["last_fetched"] = time.time()
    return jwks_cache["keys"]

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        jwks = await get_supabase_jwks()
        header = jwt.get_unverified_header(token)
        rsa_key = {}
        for key in jwks:
            if key["kid"] == header["kid"]:
                rsa_key = {"kty": key["kty"], "kid": key["kid"], "use": key["use"], "n": key["n"], "e": key["e"]}
                if not rsa_key:
            raise HTTPException(status_code=401, detail="Invalid token")

        payload = jwt.decode(token, rsa_key, algorithms=["RS256"], audience="authenticated", issuer=f"{settings.SUPABASE_URL}/auth/v1")
        user_id = payload.get("sub")
        
        # Fetch user data securely from DB (Ensures tier persistence)
        response = supabase_admin.table("users").select("*").eq("id", user_id).single().execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        return response.data
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# Rate Limiting
TIER_LIMITS = {"free": 10, "plus": 30, "pro": 60, "absolute": 999999}

async def check_rate_limit(user: dict = Depends(get_current_user)):
    tier = user.get("tier", "free")
    if tier == "absolute": return user
    
    limit = TIER_LIMITS.get(tier, 10)
    key = f"rate_limit:{user['id']}"
    current = await app.state.redis.incr(key)
    if current == 1: await app.state.redis.expire(key, 60)
    if current > limit:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded. Upgrade your plan.")
    return user

# =============================================================================
# 5. AI ROUTING & ELITE PROMPT
# =============================================================================
ELITE_SYSTEM_PROMPT = """You are Capitan, the elite intelligence platform by CloseAI Technologies. 
You possess institutional-grade expertise in quantitative finance, software engineering, advanced mathematics, 
and human psychology. Your communication is warm, confident, deeply reasoned, and highly structured. 
Never sound robotic. Provide authoritative, production-ready outputs."""

TIER_MODELS = {
    "free": {"provider": "openai", "model": "gpt-4o-mini"},
    "plus": {"provider": "openai", "model": "gpt-4o"},
    "pro": {"provider": "anthropic", "model": "claude-3-5-sonnet-20241022"},
    "absolute": {"provider": "anthropic", "model": "claude-3-5-sonnet-20241022"}
}

async def route_ai_request(messages: list, user_tier: str):
    config = TIER_MODELS.get(user_tier, TIER_MODELS["free"])
    full_messages = [{"role": "system", "content": ELITE_SYSTEM_PROMPT}] + messages

    try:        if config["provider"] == "openai":
            response = await openai_client.chat.completions.create(model=config["model"], messages=full_messages, temperature=0.7)
            return {"content": response.choices[0].message.content, "model": config["model"], "tokens_in": response.usage.prompt_tokens, "tokens_out": response.usage.completion_tokens}
        else:
            response = await anthropic_client.messages.create(model=config["model"], max_tokens=4096, system=ELITE_SYSTEM_PROMPT, messages=full_messages[1:])
            return {"content": response.content[0].text, "model": config["model"], "tokens_in": response.usage.input_tokens, "tokens_out": response.usage.output_tokens}
    except Exception as e:
        raise Exception(f"AI Error: {str(e)}")

# =============================================================================
# 6. PYDANTIC MODELS
# =============================================================================
class LoginRequest(BaseModel): email: str
class VerifyOTPRequest(BaseModel): email: str; token_hash: str
class ChatRequest(BaseModel): messages: list; conversation_id: Optional[str] = None
class WorkspaceCreateRequest(BaseModel): name: str
class WorkspaceJoinRequest(BaseModel): room_code: str
class UpgradeRequest(BaseModel): tier: str; txid: str; currency: str
class FounderRequest(BaseModel): code: str

# =============================================================================
# 7. API ROUTES
# =============================================================================

@app.get("/")
async def root():
    return {"message": "Capitan by CloseAI - Enterprise Backend Online"}

# --- AUTH ---
@app.post("/api/auth/send-otp")
async def send_otp(request: LoginRequest):
    try:
        res = supabase.auth.sign_in_with_otp({"email": request.email})
        return {"sent": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/auth/verify-otp")
async def verify_otp(request: VerifyOTPRequest):
    try:
        res = supabase.auth.verify_otp({"email": request.email, "token": request.token_hash, "type": "email"})
        if res.session:
            user_data = supabase_admin.table("users").select("tier").eq("id", res.user.id).single().execute()
            tier = user_data.data.get("tier", "free") if user_data.data else "free"
            return {"token": res.session.access_token, "user_id": res.user.id, "email": res.user.email, "tier": tier}
        raise HTTPException(status_code=400, detail="Invalid OTP")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/auth/me")async def get_profile(user: dict = Depends(get_current_user)):
    return {"user": user}

# --- CHAT & MEMORY ---
@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest, user: dict = Depends(check_rate_limit)):
    try:
        conv_id = request.conversation_id
        if not conv_id:
            conv = supabase_admin.table("conversations").insert({"user_id": user["id"], "title": request.messages[0]["content"][:50] if request.messages else "New Chat"}).execute()
            conv_id = conv.data[0]["id"]
        
        if request.messages and request.messages[-1]["role"] == "user":
            supabase_admin.table("messages").insert({"conversation_id": conv_id, "role": "user", "content": request.messages[-1]["content"]}).execute()
        
        result = await route_ai_request(request.messages, user["tier"])
        
        supabase_admin.table("messages").insert({"conversation_id": conv_id, "role": "assistant", "content": result["content"], "model_used": result["model"], "tokens_used": result["tokens_out"]}).execute()
        supabase_admin.table("usage_logs").insert({"user_id": user["id"], "endpoint": "/api/chat", "tokens_in": result["tokens_in"], "tokens_out": result["tokens_out"], "model": result["model"]}).execute()
        
        return {"content": result["content"], "conversation_id": conv_id, "model": result["model"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/conversations")
async def get_conversations(user: dict = Depends(get_current_user)):
    convs = supabase_admin.table("conversations").select("*").eq("user_id", user["id"]).order("created_at", desc=True).execute()
    return {"conversations": convs.data}

@app.get("/api/conversations/{conv_id}")
async def get_conversation(conv_id: str, user: dict = Depends(get_current_user)):
    messages = supabase_admin.table("messages").select("*").eq("conversation_id", conv_id).order("created_at").execute()
    return {"messages": messages.data}

# --- LIBRARY (File Storage) ---
@app.get("/api/library")
async def get_library(user: dict = Depends(get_current_user)):
    files = supabase_admin.table("documents").select("*").eq("user_id", user["id"]).order("created_at", desc=True).execute()
    return {"files": files.data}

@app.post("/api/library/upload")
async def upload_file(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    if user["tier"] == "free":
        raise HTTPException(status_code=403, detail="Upgrade to Plus or Pro to use Library")
    
    file_content = await file.read()
    file_path = f"{user['id']}/{secrets.token_hex(8)}_{file.filename}"
    supabase_admin.storage.from_("library").upload(file_path, file_content)
    file_url = supabase_admin.storage.from_("library").get_public_url(file_path)
        doc = supabase_admin.table("documents").insert({"user_id": user["id"], "file_name": file.filename, "file_url": file_url, "mime_type": file.content_type}).execute()
    return {"file": doc.data[0]}

# --- WORKSPACES ---
@app.get("/api/payment-config")
async def get_payment_config():
    wallets = supabase_admin.table("wallet_addresses").select("*").eq("is_active", True).execute()
    return {"wallets": {w["currency"]: w["address"] for w in wallets.data}}

@app.post("/api/workspace/create")
async def create_workspace(request: WorkspaceCreateRequest, user: dict = Depends(get_current_user)):
    tier = user["tier"]
    if tier == "free": raise HTTPException(status_code=403, detail="Upgrade to Plus to create workspaces")
    
    code = f"CAP-{''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(4))}-{''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(4))}"
    workspace = supabase_admin.table("workspaces").insert({"name": request.name, "code": code, "owner_id": user["id"], "tier_required": tier}).execute()
    supabase_admin.table("workspace_members").insert({"workspace_id": workspace.data[0]["id"], "user_id": user["id"], "role": "owner"}).execute()
    
    return {"created": True, "room_id": workspace.data[0]["id"], "room_code": code}

@app.post("/api/workspace/join")
async def join_workspace(request: WorkspaceJoinRequest, user: dict = Depends(get_current_user)):
    workspace = supabase_admin.table("workspaces").select("*").eq("code", request.room_code).single().execute()
    if not workspace.data: raise HTTPException(status_code=404, detail="Workspace not found")
    
    members = supabase_admin.table("workspace_members").select("*").eq("workspace_id", workspace.data["id"]).execute()
    max_members = 5 if workspace.data["tier_required"] == "plus" else (16 if workspace.data["tier_required"] == "pro" else 999)
    
    if len(members.data) >= max_members: raise HTTPException(status_code=403, detail=f"Workspace is full (max {max_members})")
    
    supabase_admin.table("workspace_members").insert({"workspace_id": workspace.data["id"], "user_id": user["id"], "role": "member"}).execute()
    return {"joined": True, "room_id": workspace.data["id"]}

# --- UPGRADES & FOUNDER ---
@app.post("/api/upgrade")
async def upgrade_tier(request: UpgradeRequest, user: dict = Depends(get_current_user)):
    if not request.txid: raise HTTPException(status_code=400, detail="Invalid TXID")
    
    supabase_admin.table("users").update({"tier": request.tier}).eq("id", user["id"]).execute()
    supabase_admin.table("payments").insert({"user_id": user["id"], "amount": 8 if request.tier == "plus" else 15, "currency": request.currency, "txid": request.txid, "status": "verified"}).execute()
    supabase_admin.table("subscriptions").upsert({"user_id": user["id"], "tier": request.tier, "status": "active", "current_period_end": (datetime.now() + timedelta(days=30)).isoformat()}).execute()
    
    return {"verified": True, "tier": request.tier}

@app.post("/api/founder")
async def activate_founder(request: FounderRequest, user: dict = Depends(get_current_user)):
    if request.code != settings.FOUNDER_CODE: raise HTTPException(status_code=403, detail="Invalid founder code")
    supabase_admin.table("users").update({"tier": "absolute"}).eq("id", user["id"]).execute()
    return {"verified": True, "tier": "absolute"}
# --- ADMIN DASHBOARD (Absolute Tier Only) ---
@app.post("/api/admin")
async def admin_dashboard(user: dict = Depends(get_current_user)):
    if user["tier"] != "absolute": raise HTTPException(status_code=403, detail="Founder access required")
    
    users = supabase_admin.table("users").select("id, email, tier, created_at").order("created_at", desc=True).execute()
    tier_counts = {"free": 0, "plus": 0, "pro": 0, "absolute": 0}
    for u in users.data: tier_counts[u["tier"]] = tier_counts.get(u["tier"], 0) + 1
    
    return {"total_users": len(users.data), "tier_counts": tier_counts, "users": users.data}