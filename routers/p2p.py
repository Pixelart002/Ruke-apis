from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from bson import ObjectId, errors as bson_errors
from pymongo import ReturnDocument

from auth import utils as auth_utils
from database import db

router = APIRouter(prefix="/p2p", tags=["P2P Exchange"])

# --- Pydantic Models (Unchanged) ---
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

# --- Reusable Dependency for fetching a Trade ---
async def get_trade_or_404(trade_id: str) -> Dict[str, Any]:
    try:
        trade_obj_id = ObjectId(trade_id)
    except bson_errors.InvalidId:
        raise HTTPException(status_code=400, detail=f"Invalid trade_id format: '{trade_id}'")
    
    trade = await run_in_threadpool(db.p2p_trades.find_one, {"_id": trade_obj_id})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found.")
    return trade

# --- API Endpoints ---

@router.put("/users/me/wallet", status_code=status.HTTP_200_OK)
async def update_wallet_address(
    wallet_data: UserWalletUpdate,
    current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)
):
    user_id = ObjectId(current_user["_id"])
    await run_in_threadpool(
        db.users.update_one,
        {"_id": user_id},
        {"$set": {"wallet_address": wallet_data.wallet_address}}
    )
    return {"message": "Wallet address updated successfully."}

@router.post("/listings", response_model=ListingResponse, status_code=status.HTTP_201_CREATED)
async def create_p2p_listing(
    listing: ListingCreate,
    current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)
):
    if listing.min_limit > listing.max_limit or listing.max_limit > listing.available_quantity:
        raise HTTPException(status_code=400, detail="Invalid limits: min_limit cannot be greater than max_limit or available_quantity.")

    new_listing_doc = listing.dict()
    new_listing_doc.update({
        "owner_id": ObjectId(current_user["_id"]),
        "owner_username": current_user["username"],
        "status": "active",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    })
    
    result = await run_in_threadpool(db.p2p_listings.insert_one, new_listing_doc)
    
    # OPTIMIZATION: Manually construct response, avoiding a redundant DB read.
    new_listing_doc["_id"] = result.inserted_id
    return new_listing_doc

@router.get("/listings", response_model=List[ListingResponse])
async def get_active_listings(
    asset: Optional[str] = None,
    listing_type: Optional[str] = Query(None, regex="^(buy|sell)$")
):
    query = {"status": "active"}
    if asset: query["asset"] = asset.upper()
    if listing_type: query["listing_type"] = listing_type

    # OPTIMIZATION: Use projection to fetch only necessary data, reducing network load.
    projection = {
        "owner_username": 1, "listing_type": 1, "asset": 1, "fiat_currency": 1,
        "price_per_unit": 1, "available_quantity": 1, "min_limit": 1, "max_limit": 1,
        "payment_methods": 1, "status": 1
    }

    listings_cursor = db.p2p_listings.find(query, projection).sort("created_at", -1)
    return await listings_cursor.to_list(length=100)

@router.post("/trades", response_model=TradeResponse, status_code=status.HTTP_201_CREATED)
async def create_trade(
    trade: TradeCreate,
    current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)
):
    try:
        listing_obj_id = ObjectId(trade.listing_id)
    except bson_errors.InvalidId:
        raise HTTPException(status_code=400, detail=f"Invalid listing_id format: '{trade.listing_id}'")

    # ATOMIC OPERATION: Find listing and decrement quantity if criteria are met
    updated_listing = await run_in_threadpool(
        db.p2p_listings.find_one_and_update,
        {
            "_id": listing_obj_id, "status": "active",
            "owner_id": {"$ne": ObjectId(current_user["_id"])},
            "available_quantity": {"$gte": trade.quantity},
            "min_limit": {"$lte": trade.quantity},
            "max_limit": {"$gte": trade.quantity}
        },
        {"$inc": {"available_quantity": -trade.quantity}},
        return_document=ReturnDocument.BEFORE # Get document before the update
    )

    if not updated_listing:
        raise HTTPException(status_code=400, detail="Trade could not be created. Listing not found, quantity insufficient, trade size out of limits, or you are the owner.")

    new_trade_doc = {
        "listing_id": str(updated_listing["_id"]),
        "seller_id": updated_listing["owner_id"],
        "buyer_id": ObjectId(current_user["_id"]),
        "seller_username": updated_listing["owner_username"], # OPTIMIZATION: Use existing data
        "buyer_username": current_user["username"],
        "quantity": trade.quantity,
        "fiat_amount": trade.quantity * updated_listing["price_per_unit"],
        "status": "awaiting_payment",
        "created_at": datetime.now(timezone.utc)
    }

    result = await run_in_threadpool(db.p2p_trades.insert_one, new_trade_doc)
    
    # OPTIMIZATION: Manually construct response, avoiding a redundant DB read.
    new_trade_doc["_id"] = result.inserted_id
    return new_trade_doc

@router.put("/trades/{trade_id}/confirm-payment", status_code=status.HTTP_200_OK)
async def confirm_payment(
    trade: Dict[str, Any] = Depends(get_trade_or_404),
    current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)
):
    if str(trade["buyer_id"]) != current_user["_id"]:
        raise HTTPException(status_code=403, detail="Not authorized. You are not the buyer in this trade.")
    if trade["status"] != "awaiting_payment":
        raise HTTPException(status_code=400, detail="Trade is not awaiting payment.")

    await run_in_threadpool(
        db.p2p_trades.update_one,
        {"_id": trade["_id"]},
        {"$set": {"status": "payment_confirmed", "payment_confirmed_at": datetime.now(timezone.utc)}}
    )
    return {"message": "Payment confirmed. Awaiting seller to release assets."}

@router.put("/trades/{trade_id}/release-crypto", status_code=status.HTTP_200_OK)
async def release_crypto(
    trade: Dict[str, Any] = Depends(get_trade_or_404),
    current_user: Dict[str, Any] = Depends(auth_utils.get_current_user)
):
    if str(trade["seller_id"]) != current_user["_id"]:
        raise HTTPException(status_code=403, detail="Not authorized. You are not the seller in this trade.")
    if trade["status"] != "payment_confirmed":
        raise HTTPException(status_code=400, detail="Cannot release assets before payment is confirmed.")

    # DATABASE TRANSACTION: Ensure both operations succeed or fail together
    async with await db.client.start_session() as session:
        async with session.start_transaction():
            # Update the trade status to completed
            await db.p2p_trades.update_one(
                {"_id": trade["_id"]},
                {"$set": {"status": "completed", "released_at": datetime.now(timezone.utc)}},
                session=session
            )
            
            # Check if the listing is now depleted and should be deactivated
            listing = await db.p2p_listings.find_one(
                {"_id": ObjectId(trade["listing_id"])},
                projection={"available_quantity": 1, "min_limit": 1},
                session=session
            )
            if listing and listing["available_quantity"] < listing["min_limit"]:
                await db.p2p_listings.update_one(
                    {"_id": ObjectId(trade["listing_id"])},
                    {"$set": {"status": "inactive"}},
                    session=session
                )
            
    return {"message": "Assets released. Trade completed."}