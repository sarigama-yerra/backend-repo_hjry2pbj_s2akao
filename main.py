import os
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import db, create_document, get_documents

app = FastAPI(title="Custom Bot Selling API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------- Utility helpers ----------------------

def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    pw_hash = hashlib.sha256((salt + password).encode()).hexdigest()
    return pw_hash, salt


def make_token() -> str:
    return secrets.token_urlsafe(32)


async def get_auth_user(authorization: Optional[str] = Header(default=None)) -> Optional[dict]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ", 1)[1]
    session = db["sessiontoken"].find_one({"token": token})
    if not session:
        return None
    if session.get("expires_at") and session["expires_at"] < datetime.now(timezone.utc):
        return None
    user = db["useraccount"].find_one({"_id": session["user_id"]})
    # If we stored stringified _id, just return user by id lookup string
    if not user:
        user = db["useraccount"].find_one({"_id": session["user_id"]})
    return user


# ---------------------- Pydantic payloads ----------------------

class SignupPayload(BaseModel):
    email: str
    name: str
    password: str


class LoginPayload(BaseModel):
    email: str
    password: str


class CreateOrderPayload(BaseModel):
    plan_slug: str


class CreatePlanPayload(BaseModel):
    slug: str
    title: str
    description: Optional[str] = None
    price: float
    interval: str = "one-time"
    features: List[str] = []
    active: bool = True


# ---------------------- Public routes ----------------------

@app.get("/")
def read_root():
    return {"message": "Custom Bot Selling API running"}


@app.get("/plans")
def list_plans():
    plans = get_documents("botplan", {"active": True})
    for p in plans:
        p["_id"] = str(p["_id"])  # stringify for JSON
    return {"plans": plans}


@app.post("/signup")
def signup(payload: SignupPayload):
    existing = db["useraccount"].find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    pw_hash, salt = hash_password(payload.password)
    user_doc = {
        "email": payload.email,
        "name": payload.name,
        "password_hash": pw_hash,
        "salt": salt,
        "is_active": True,
        "is_admin": False,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    result_id = db["useraccount"].insert_one(user_doc).inserted_id
    token = make_token()
    db["sessiontoken"].insert_one({
        "user_id": result_id,
        "token": token,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    return {"token": token, "user": {"id": str(result_id), "email": payload.email, "name": payload.name}}


@app.post("/login")
def login(payload: LoginPayload):
    user = db["useraccount"].find_one({"email": payload.email})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    pw_hash, _ = hash_password(payload.password, user.get("salt"))
    if pw_hash != user.get("password_hash"):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = make_token()
    db["sessiontoken"].insert_one({
        "user_id": user["_id"],
        "token": token,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    return {"token": token, "user": {"id": str(user["_id"]), "email": user["email"], "name": user["name"]}}


# ---------------------- Authenticated user routes ----------------------

@app.get("/me")
async def me(user = Depends(get_auth_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"id": str(user["_id"]), "email": user["email"], "name": user.get("name"), "is_admin": user.get("is_admin", False)}


@app.post("/orders")
async def create_order(payload: CreateOrderPayload, user = Depends(get_auth_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    plan = db["botplan"].find_one({"slug": payload.plan_slug, "active": True})
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    order_doc = {
        "user_id": user["_id"],
        "plan_slug": payload.plan_slug,
        "amount": plan["price"],
        "currency": "USD",
        "status": "created",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    inserted_id = db["order"].insert_one(order_doc).inserted_id
    return {"order_id": str(inserted_id), "amount": plan["price"], "currency": "USD"}


@app.get("/orders")
async def list_my_orders(user = Depends(get_auth_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    orders = list(db["order"].find({"user_id": user["_id"]}).sort("created_at", -1))
    for o in orders:
        o["_id"] = str(o["_id"])  # stringify
    return {"orders": orders}


# ---------------------- PayPal Simulated Integration ----------------------
# This demo uses a minimal mock to mark orders approved/completed.
# In a production app, you'd implement PayPal Orders API server-side calls.

class PayPalApprovePayload(BaseModel):
    order_id: str
    action: str  # "approve" or "complete" or "cancel"


@app.post("/paypal/update")
async def paypal_update(payload: PayPalApprovePayload):
    order = db["order"].find_one({"_id": db["order"].database.client.get_database().get_collection("order").database.client.get_database().get_collection("order").database.client.get_database()})
    # The above is intentionally verbose; we'll instead do simple lookup by string id safely.
    from bson import ObjectId
    try:
        oid = ObjectId(payload.order_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid order id")
    order = db["order"].find_one({"_id": oid})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    new_status = {
        "approve": "approved",
        "complete": "completed",
        "cancel": "cancelled",
    }.get(payload.action)
    if not new_status:
        raise HTTPException(status_code=400, detail="Invalid action")
    db["order"].update_one({"_id": oid}, {"$set": {"status": new_status, "updated_at": datetime.now(timezone.utc)}})
    return {"status": new_status}


# ---------------------- Admin routes ----------------------

class AdminAuthPayload(BaseModel):
    password: str


ADMIN_PASSWORD = os.getenv("OWNER_PASSWORD", "Alonzo2025")

@app.post("/admin/login")
def admin_login(payload: AdminAuthPayload):
    if payload.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin password")
    token = make_token()
    db["sessiontoken"].insert_one({
        "user_id": "admin",
        "token": token,
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=12),
        "role": "admin",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    return {"admin_token": token}


def require_admin(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split(" ", 1)[1]
    session = db["sessiontoken"].find_one({"token": token, "role": "admin"})
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


@app.post("/admin/plans")
def admin_create_plan(payload: CreatePlanPayload, _: bool = Depends(require_admin)):
    exists = db["botplan"].find_one({"slug": payload.slug})
    if exists:
        raise HTTPException(status_code=400, detail="Slug already exists")
    doc = payload.model_dump()
    doc["created_at"] = datetime.now(timezone.utc)
    doc["updated_at"] = datetime.now(timezone.utc)
    db["botplan"].insert_one(doc)
    return {"ok": True}


@app.get("/admin/orders")
def admin_list_orders(_: bool = Depends(require_admin)):
    orders = list(db["order"].find().sort("created_at", -1))
    for o in orders:
        o["_id"] = str(o["_id"])  # stringify
    return {"orders": orders}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        from database import db
        if db is not None:
            response["database"] = "✅ Available"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
                response["connection_status"] = "Connected"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
