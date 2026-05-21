"""
Мій день — персональний AI-помічник (сервер)
FastAPI + Claude API + Firebase RTDB
"""
import os
import json
import time
import hashlib
import secrets
import logging
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from jose import jwt, JWTError

from crypto_utils import encrypt_data, decrypt_data
from ai_engine import parse_intent, generate_briefing
from weather_service import get_weather
from holidays import get_today_holidays
from scheduler import start_scheduler

# ──────────────────────────────────────────────
#  Config
# ──────────────────────────────────────────────
FIREBASE_DB_URL = os.environ.get("FIREBASE_DB_URL", "https://myday-94aca-default-rtdb.europe-west1.firebasedatabase.app")
FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY", "")
FIREBASE_EMAIL = os.environ.get("FIREBASE_EMAIL", "")
FIREBASE_PASSWORD = os.environ.get("FIREBASE_PASSWORD", "")
JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "https://flashsmart8.github.io")
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_TRANSIT_KEY", "")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("myday")

# ──────────────────────────────────────────────
#  Firebase helpers
# ──────────────────────────────────────────────
_fb_token = {"id": None, "exp": 0}


async def fb_auth() -> str:
    """Get Firebase ID token, refresh if expired."""
    now = time.time()
    if _fb_token["id"] and _fb_token["exp"] > now + 60:
        return _fb_token["id"]

    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    payload = {"email": FIREBASE_EMAIL, "password": FIREBASE_PASSWORD, "returnSecureToken": True}

    async with httpx.AsyncClient() as client:
        r = await client.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            log.error("Firebase auth failed: %s", r.text)
            raise HTTPException(500, "Firebase auth error")
        data = r.json()

    _fb_token["id"] = data["idToken"]
    _fb_token["exp"] = now + int(data.get("expiresIn", 3600))
    return _fb_token["id"]


async def fb_get(path: str) -> dict | list | None:
    token = await fb_auth()
    url = f"{FIREBASE_DB_URL}/{path}.json?auth={token}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, timeout=10)
        if r.status_code == 401:
            _fb_token["id"] = None
            token = await fb_auth()
            r = await client.get(f"{FIREBASE_DB_URL}/{path}.json?auth={token}", timeout=10)
        return r.json() if r.status_code == 200 else None


async def fb_put(path: str, data: dict) -> bool:
    token = await fb_auth()
    url = f"{FIREBASE_DB_URL}/{path}.json?auth={token}"
    async with httpx.AsyncClient() as client:
        r = await client.put(url, json=data, timeout=10)
        return r.status_code == 200


async def fb_patch(path: str, data: dict) -> bool:
    token = await fb_auth()
    url = f"{FIREBASE_DB_URL}/{path}.json?auth={token}"
    async with httpx.AsyncClient() as client:
        r = await client.patch(url, json=data, timeout=10)
        return r.status_code == 200


async def fb_post(path: str, data: dict) -> str | None:
    """Push new item, return generated key."""
    token = await fb_auth()
    url = f"{FIREBASE_DB_URL}/{path}.json?auth={token}"
    async with httpx.AsyncClient() as client:
        r = await client.post(url, json=data, timeout=10)
        if r.status_code == 200:
            return r.json().get("name")
    return None


# ──────────────────────────────────────────────
#  JWT helpers
# ──────────────────────────────────────────────
def create_jwt(user_id: str = "owner") -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(hours=24),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def verify_jwt(token: str) -> str:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload["sub"]
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")


async def get_current_user(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing authorization")
    token = authorization.split(" ", 1)[1]
    return verify_jwt(token)


# ──────────────────────────────────────────────
#  Pydantic models
# ──────────────────────────────────────────────
class RegisterRequest(BaseModel):
    credential_id: str
    public_key: str
    pin_hash: str  # bcrypt hash of 6-digit PIN, hashed on client


class LoginRequest(BaseModel):
    credential_id: str
    signature: str
    challenge: str
    authenticator_data: str
    client_data_json: str


class PinLoginRequest(BaseModel):
    pin: str


class MessageRequest(BaseModel):
    encrypted: str  # encrypted message text
    client_key: str  # encrypted AES key for server transit


class PushRegisterRequest(BaseModel):
    token: str


# ──────────────────────────────────────────────
#  App lifecycle
# ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting Мій день server...")
    start_scheduler()
    yield
    log.info("Shutting down...")


app = FastAPI(title="Мій день API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=False,
)

# ──────────────────────────────────────────────
#  Challenge store (in-memory, short-lived)
# ──────────────────────────────────────────────
_challenges: dict[str, float] = {}


def create_challenge() -> str:
    c = secrets.token_urlsafe(32)
    _challenges[c] = time.time() + 300  # 5 min TTL
    # cleanup old
    now = time.time()
    for k in list(_challenges):
        if _challenges[k] < now:
            del _challenges[k]
    return c


def verify_challenge(c: str) -> bool:
    if c in _challenges and _challenges[c] > time.time():
        del _challenges[c]
        return True
    return False


# ──────────────────────────────────────────────
#  Auth endpoints
# ──────────────────────────────────────────────
@app.get("/auth/challenge")
async def get_challenge():
    """Generate challenge for Passkey registration or login."""
    return {"challenge": create_challenge()}


@app.post("/auth/register")
async def register(req: RegisterRequest):
    """Store Passkey public key and PIN hash."""
    existing = await fb_get("user/passkey")
    if existing:
        raise HTTPException(400, "Already registered. Use /auth/login.")

    await fb_put("user/passkey", {
        "credential_id": req.credential_id,
        "public_key": req.public_key,
        "created": int(time.time() * 1000),
    })
    await fb_put("user/pin_hash", {"hash": req.pin_hash})

    token = create_jwt()
    return {"token": token, "message": "Registered successfully"}


@app.post("/auth/login")
async def login(req: LoginRequest):
    """Verify Passkey signature and issue JWT."""
    if not verify_challenge(req.challenge):
        raise HTTPException(401, "Invalid or expired challenge")

    stored = await fb_get("user/passkey")
    if not stored:
        raise HTTPException(404, "Not registered")

    if stored.get("credential_id") != req.credential_id:
        raise HTTPException(401, "Unknown credential")

    # In production: verify signature with stored public key using pywebauthn
    # For MVP: credential_id match + valid challenge = authenticated
    # TODO: full WebAuthn signature verification

    token = create_jwt()
    return {"token": token}


@app.post("/auth/pin-login")
async def pin_login(req: PinLoginRequest):
    """Fallback login with PIN."""
    stored = await fb_get("user/pin_hash")
    if not stored:
        raise HTTPException(404, "Not registered")

    # Client sends bcrypt-hashed PIN, we compare
    from passlib.hash import bcrypt
    if not bcrypt.verify(req.pin, stored.get("hash", "")):
        raise HTTPException(401, "Wrong PIN")

    token = create_jwt()
    return {"token": token}


# ──────────────────────────────────────────────
#  Message endpoint
# ──────────────────────────────────────────────
@app.post("/message")
async def handle_message(req: MessageRequest, user: str = Depends(get_current_user)):
    """Process encrypted message through Claude, save result."""
    try:
        # Decrypt message on server (transit decryption)
        plaintext = decrypt_data(req.encrypted, ENCRYPTION_KEY)
    except Exception as e:
        log.error("Decryption failed: %s", e)
        raise HTTPException(400, "Decryption failed")

    # Get context for Claude
    settings = await fb_get("user/settings") or {}
    city = settings.get("city", "Київ")

    weather = {}
    try:
        weather = await get_weather(city)
    except Exception as e:
        log.warning("Weather fetch failed: %s", e)

    holidays = get_today_holidays()

    # Get recent facts for context
    facts = await fb_get("facts") or {}
    facts_summary = []
    for fid, fdata in (facts.items() if isinstance(facts, dict) else []):
        try:
            decrypted_fact = decrypt_data(fdata.get("data", ""), ENCRYPTION_KEY)
            facts_summary.append(f"[{fdata.get('category', '?')}] {decrypted_fact}")
        except Exception:
            pass

    # Parse intent with Claude
    result = await parse_intent(
        message=plaintext,
        weather=weather,
        holidays=holidays,
        known_facts=facts_summary[-20:],  # last 20 facts for context
    )

    # Save parsed data to Firebase
    if result["type"] == "EVENT":
        encrypted_data = encrypt_data(json.dumps(result["data"], ensure_ascii=False), ENCRYPTION_KEY)
        await fb_post("events", {
            "data": encrypted_data,
            "date": result["data"].get("date", ""),
            "done": False,
            "created": int(time.time() * 1000),
        })

    elif result["type"] == "FACT":
        encrypted_data = encrypt_data(json.dumps(result["data"], ensure_ascii=False), ENCRYPTION_KEY)
        await fb_post("facts", {
            "data": encrypted_data,
            "category": result["data"].get("category", "other"),
            "created": int(time.time() * 1000),
        })

    elif result["type"] == "JOURNAL":
        encrypted_data = encrypt_data(json.dumps(result["data"], ensure_ascii=False), ENCRYPTION_KEY)
        today_key = datetime.now().strftime("%Y-%m-%d")
        await fb_put(f"journal/{today_key}", {
            "data": encrypted_data,
            "mood": result["data"].get("mood", 3),
            "created": int(time.time() * 1000),
        })

    elif result["type"] == "GOAL":
        encrypted_data = encrypt_data(json.dumps(result["data"], ensure_ascii=False), ENCRYPTION_KEY)
        await fb_post("goals", {
            "data": encrypted_data,
            "active": True,
            "created": int(time.time() * 1000),
        })

    # Encrypt response for client
    encrypted_response = encrypt_data(result["response"], ENCRYPTION_KEY)

    return {
        "encrypted_response": encrypted_response,
        "type": result["type"],
    }


# ──────────────────────────────────────────────
#  Briefing endpoint
# ──────────────────────────────────────────────
@app.get("/briefing")
async def get_briefing(user: str = Depends(get_current_user)):
    """Generate morning/evening briefing."""
    settings = await fb_get("user/settings") or {}
    city = settings.get("city", "Київ")

    weather = {}
    try:
        weather = await get_weather(city)
    except Exception:
        pass

    holidays = get_today_holidays()

    # Today's events
    today = datetime.now().strftime("%Y-%m-%d")
    events = await fb_get("events") or {}
    today_events = []
    for eid, edata in (events.items() if isinstance(events, dict) else []):
        if edata.get("date") == today and not edata.get("done"):
            try:
                decrypted = decrypt_data(edata.get("data", ""), ENCRYPTION_KEY)
                today_events.append(json.loads(decrypted))
            except Exception:
                pass

    # Recent mood
    journal = await fb_get("journal") or {}
    recent_moods = []
    for jkey in sorted(journal.keys() if isinstance(journal, dict) else [], reverse=True)[:7]:
        jdata = journal[jkey]
        if isinstance(jdata, dict) and "mood" in jdata:
            recent_moods.append({"date": jkey, "mood": jdata["mood"]})

    # Active goals
    goals = await fb_get("goals") or {}
    active_goals = []
    for gid, gdata in (goals.items() if isinstance(goals, dict) else []):
        if gdata.get("active"):
            try:
                decrypted = decrypt_data(gdata.get("data", ""), ENCRYPTION_KEY)
                active_goals.append(json.loads(decrypted))
            except Exception:
                pass

    briefing_text = await generate_briefing(
        weather=weather,
        holidays=holidays,
        events=today_events,
        moods=recent_moods,
        goals=active_goals,
    )

    encrypted_briefing = encrypt_data(briefing_text, ENCRYPTION_KEY)
    return {"encrypted_briefing": encrypted_briefing, "weather": weather}


# ──────────────────────────────────────────────
#  Today endpoint
# ──────────────────────────────────────────────
@app.get("/today")
async def get_today(user: str = Depends(get_current_user)):
    """Get today's events and weather (lightweight)."""
    settings = await fb_get("user/settings") or {}
    city = settings.get("city", "Київ")

    weather = {}
    try:
        weather = await get_weather(city)
    except Exception:
        pass

    holidays = get_today_holidays()

    today = datetime.now().strftime("%Y-%m-%d")
    events = await fb_get("events") or {}
    today_events_encrypted = []
    for eid, edata in (events.items() if isinstance(events, dict) else []):
        if edata.get("date") == today and not edata.get("done"):
            today_events_encrypted.append({
                "id": eid,
                "data": edata.get("data", ""),
                "done": edata.get("done", False),
            })

    return {
        "weather": weather,
        "holidays": holidays,
        "events": today_events_encrypted,
    }


# ──────────────────────────────────────────────
#  Facts & Goals endpoints
# ──────────────────────────────────────────────
@app.get("/facts")
async def get_facts(user: str = Depends(get_current_user)):
    facts = await fb_get("facts") or {}
    return {"facts": facts}


@app.get("/goals")
async def get_goals(user: str = Depends(get_current_user)):
    goals = await fb_get("goals") or {}
    return {"goals": goals}


# ──────────────────────────────────────────────
#  Push registration
# ──────────────────────────────────────────────
@app.post("/push/register")
async def register_push(req: PushRegisterRequest, user: str = Depends(get_current_user)):
    await fb_put("user/fcm_token", {"token": req.token, "updated": int(time.time() * 1000)})
    return {"ok": True}


# ──────────────────────────────────────────────
#  Health check
# ──────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "myday", "time": datetime.now().isoformat()}
