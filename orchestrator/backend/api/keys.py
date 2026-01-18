"""
API Keys Management Endpoints
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from ..database import get_session
from ..models import APIKey

router = APIRouter(prefix="/api/keys", tags=["API Keys"])


class APIKeyCreate(BaseModel):
    name: str
    exchange: str = "kucoin"
    api_key: str
    api_secret: str
    api_passphrase: Optional[str] = None


class APIKeyResponse(BaseModel):
    id: int
    name: str
    exchange: str
    api_key_masked: str  # Only show last 4 chars
    created_at: str
    is_active: bool

    class Config:
        from_attributes = True


class APIKeyListItem(BaseModel):
    id: int
    name: str
    exchange: str


@router.get("/list", response_model=List[APIKeyListItem])
async def list_keys():
    """List all API keys (names only, no secrets)"""
    session = get_session()
    try:
        keys = session.query(APIKey).filter(APIKey.is_active == True).all()
        return [APIKeyListItem(id=k.id, name=k.name, exchange=k.exchange) for k in keys]
    finally:
        session.close()


@router.get("/{key_id}", response_model=APIKeyResponse)
async def get_key(key_id: int):
    """Get API key details (masked)"""
    session = get_session()
    try:
        key = session.query(APIKey).filter(APIKey.id == key_id).first()
        if not key:
            raise HTTPException(status_code=404, detail="API key not found")

        return APIKeyResponse(
            id=key.id,
            name=key.name,
            exchange=key.exchange,
            api_key_masked="****" + key.api_key[-4:]
            if len(key.api_key) > 4
            else "****",
            created_at=key.created_at.isoformat(),
            is_active=key.is_active,
        )
    finally:
        session.close()


@router.get("/{key_id}/full")
async def get_key_full(key_id: int):
    """Get full API key data (for bot creation)"""
    session = get_session()
    try:
        key = session.query(APIKey).filter(APIKey.id == key_id).first()
        if not key:
            raise HTTPException(status_code=404, detail="API key not found")

        return {
            "id": key.id,
            "name": key.name,
            "exchange": key.exchange,
            "api_key": key.api_key,
            "api_secret": key.api_secret,
            "api_passphrase": key.api_passphrase,
        }
    finally:
        session.close()


@router.post("/create", response_model=APIKeyResponse)
async def create_key(data: APIKeyCreate):
    """Create new API key"""
    session = get_session()
    try:
        # Check if name exists
        existing = session.query(APIKey).filter(APIKey.name == data.name).first()
        if existing:
            raise HTTPException(
                status_code=400, detail="Key with this name already exists"
            )

        key = APIKey(
            name=data.name,
            exchange=data.exchange,
            api_key=data.api_key,
            api_secret=data.api_secret,
            api_passphrase=data.api_passphrase,
        )
        session.add(key)
        session.commit()
        session.refresh(key)

        return APIKeyResponse(
            id=key.id,
            name=key.name,
            exchange=key.exchange,
            api_key_masked="****" + key.api_key[-4:]
            if len(key.api_key) > 4
            else "****",
            created_at=key.created_at.isoformat(),
            is_active=key.is_active,
        )
    finally:
        session.close()


@router.delete("/{key_id}")
async def delete_key(key_id: int):
    """Delete API key"""
    session = get_session()
    try:
        key = session.query(APIKey).filter(APIKey.id == key_id).first()
        if not key:
            raise HTTPException(status_code=404, detail="API key not found")

        session.delete(key)
        session.commit()
        return {"status": "deleted", "id": key_id}
    finally:
        session.close()
