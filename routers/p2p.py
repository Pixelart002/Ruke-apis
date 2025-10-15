from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from bson import ObjectId

from auth import utils as auth_utils
from database import db

router = APIRouter(prefix="/p2p", tags=["P2P Exchange"])

# --- Pydantic Models (as per your plan) ---

class UserWalletUpdate(BaseModel):
    wallet_address: str

class ListingCreate(BaseModel):
    listing_type: str
    asset: str
    fiat_currency: str
    price_per_unit: float
    available_quantity: float
    min_limit: float
    max_limit: float
    payment_methods: List[str]

class ListingResponse(BaseModel):
    id: str = Field(..., alias="_id")
    owner_username: str
    listing_type: str
    asset: str
    fiat_currency: str
    price_per_unit: float
    available_quantity: float
    min_limit: float
    max_limit: float
    payment_methods: List[str]
    status: str
    
    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class TradeCreate(BaseModel):
    listing_id: str
    quantity: float

class TradeResponse(BaseModel):
    trade_id: str = Field(..., alias="_id")
    listing_id: str
    seller_username: str
    buyer_username: str
    quantity: float
    fiat_amount: float
    status: str
    created_at: datetime

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


# --- API Endpoints ---

@router.put("/users/me/wallet", status_code=status.HTTP_200_OK)
async def update_wallet_address(
    wallet_data: UserWalletUpdate,
    current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)
):
    user_id = ObjectId(current_user["_id"])
    # FIXED: Removed 'await' from the synchronous call
    db.users.update_one(
        {"_id": user_id},
        {"$set": {"wallet_address": wallet_data.wallet_address}}
    )
    return {"message": "Wallet address updated successfully."}


@router.post("/listings", response_model=ListingResponse, status_code=status.HTTP_201_CREATED)
async def create_p2p_listing(
    listing: ListingCreate,
    current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)
):
    new_listing = listing.dict()
    new_listing.update({
        "owner_id": ObjectId(current_user["_id"]),
        "owner_username": current_user["username"],
        "status": "active",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    })
    
    result = await db.p2p_listings.insert_one(new_listing)
    created_listing = await db.p2p_listings.find_one({"_id": result.inserted_id})
    return created_listing


@router.get("/listings", response_model=List[ListingResponse])
async def get_active_listings(
    asset: Optional[str] = None,
    listing_type: Optional[str] = Query(None, regex="^(buy|sell)$")
):
    query = {"status": "active"}
    if asset:
        query["asset"] = asset.upper()
    if listing_type:
        query["listing_type"] = listing_type

    listings_cursor = db.p2p_listings.find(query).sort("created_at", -1)
    return await listings_cursor.to_list(length=100)


@router.post("/trades", response_model=TradeResponse, status_code=status.HTTP_201_CREATED)
async def create_trade(
    trade: TradeCreate,
    current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)
):
    listing = await db.p2p_listings.find_one({"_id": ObjectId(trade.listing_id), "status": "active"})
    if not listing:
        raise HTTPException(status_code=404, detail="Active listing not found.")

    if trade.quantity > listing["available_quantity"] or trade.quantity < listing["min_limit"]:
        raise HTTPException(status_code=400, detail="Invalid quantity for this listing.")

    seller_id = listing["owner_id"]
    buyer_id = ObjectId(current_user["_id"])
    
    if seller_id == buyer_id:
        raise HTTPException(status_code=400, detail="You cannot trade with yourself.")

    seller = await db.users.find_one({"_id": seller_id})

    new_trade = {
        "listing_id": trade.listing_id,
        "seller_id": seller_id,
        "buyer_id": buyer_id,
        "seller_username": seller["username"],
        "buyer_username": current_user["username"],
        "quantity": trade.quantity,
        "fiat_amount": trade.quantity * listing["price_per_unit"],
        "status": "awaiting_payment",
        "created_at": datetime.now(timezone.utc)
    }

    result = await db.p2p_trades.insert_one(new_trade)
    created_trade = await db.p2p_trades.find_one({"_id": result.inserted_id})
    return created_trade


@router.put("/trades/{trade_id}/confirm-payment", status_code=status.HTTP_200_OK)
async def confirm_payment(
    trade_id: str,
    current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)
):
    trade = await db.p2p_trades.find_one({"_id": ObjectId(trade_id)})
    if not trade or str(trade["buyer_id"]) != current_user["_id"]:
        raise HTTPException(status_code=403, detail="Not authorized or trade not found.")
    
    # FIXED: Removed 'await' from the synchronous call
    db.p2p_trades.update_one(
        {"_id": ObjectId(trade_id)},
        {"$set": {"status": "payment_confirmed", "payment_confirmed_at": datetime.now(timezone.utc)}}
    )
    return {"message": "Payment confirmed. Awaiting seller to release assets."}


@router.put("/trades/{trade_id}/release-crypto", status_code=status.HTTP_200_OK)
async def release_crypto(
    trade_id: str,
    current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)
):
    trade = await db.p2p_trades.find_one({"_id": ObjectId(trade_id)})
    if not trade or str(trade["seller_id"]) != current_user["_id"]:
        raise HTTPException(status_code=403, detail="Not authorized or trade not found.")
        
    if trade["status"] != "payment_confirmed":
        raise HTTPException(status_code=400, detail="Cannot release crypto before payment is confirmed.")

    # Update trade and listing quantities
    # FIXED: Removed 'await' from both synchronous calls
    db.p2p_trades.update_one(
        {"_id": ObjectId(trade_id)},
        {"$set": {"status": "crypto_released", "released_at": datetime.now(timezone.utc)}}
    )
    db.p2p_listings.update_one(
        {"_id": ObjectId(trade["listing_id"])},
        {"$inc": {"available_quantity": -trade["quantity"]}}
    )
    return {"message": "Crypto release confirmed. Trade completed."}
