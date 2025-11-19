"""
Database Schemas for Custom Bot Selling Platform

Each Pydantic model represents a collection in MongoDB.
Collection name is the lowercase class name.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class Useraccount(BaseModel):
    """
    Users collection schema
    Collection: "useraccount"
    """
    email: str = Field(..., description="Email address")
    name: str = Field(..., description="Full name")
    password_hash: str = Field(..., description="SHA-256 salted hash of password")
    salt: str = Field(..., description="Salt used for hashing")
    is_active: bool = Field(True)
    is_admin: bool = Field(False)

class Botplan(BaseModel):
    """
    Bot plans/products available for purchase
    Collection: "botplan"
    """
    slug: str = Field(..., description="URL-safe identifier")
    title: str
    description: Optional[str] = None
    price: float = Field(..., ge=0)
    interval: str = Field("one-time", description="billing cycle: one-time | monthly | yearly")
    features: List[str] = Field(default_factory=list)
    active: bool = Field(True)

class Order(BaseModel):
    """
    Customer orders and payment records
    Collection: "order"
    """
    user_id: str = Field(..., description="ID of the purchaser (stringified ObjectId)")
    plan_slug: str
    amount: float
    currency: str = Field("USD")
    status: str = Field("created", description="created | approved | completed | failed | cancelled")
    paypal_order_id: Optional[str] = None

class Sessiontoken(BaseModel):
    """
    Simple bearer token sessions
    Collection: "sessiontoken"
    """
    user_id: str
    token: str
    expires_at: datetime
