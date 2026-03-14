"""Key lifecycle API routes — generate, rotate, revoke per-user APIM keys."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from src.auth import get_current_user
from src.registry import registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/keys", tags=["keys"])


def _require_user(user: dict | None) -> dict:
    """Raise 401 if not authenticated."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


@router.get("")
async def list_user_keys(
    user: Annotated[dict | None, Depends(get_current_user)],
) -> dict[str, Any]:
    """List all key records for the current user."""
    u = _require_user(user)
    from src.main import cosmos_store

    records = await cosmos_store.get_user_keys(u["user_id"])

    enriched = []
    for rec in records:
        server = registry.get_by_id(rec["server_id"])
        enriched.append(
            {
                "server_id": rec["server_id"],
                "server_name": server.name if server else rec["server_id"],
                "server_icon": server.icon if server else None,
                "key_hint": rec.get("key_hint", ""),
                "state": rec["state"],
                "created_at": rec.get("created_at"),
                "last_rotated_at": rec.get("last_rotated_at"),
                "rotation_count": rec.get("rotation_count", 0),
            }
        )

    return {"keys": enriched, "total": len(enriched)}


@router.post("/{server_id}")
async def generate_key(
    server_id: str,
    user: Annotated[dict | None, Depends(get_current_user)],
) -> dict[str, Any]:
    """Generate a new per-user APIM subscription key for a server."""
    u = _require_user(user)
    from src.main import apim_manager, cosmos_store

    server = registry.get_by_id(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    product_id = apim_manager.get_product_id(server_id)
    if not product_id:
        raise HTTPException(status_code=400, detail="Server has no APIM product mapping")

    result = await apim_manager.create_subscription(
        user_oid=u["user_id"],
        user_email=u["email"],
        server_id=server_id,
    )

    await cosmos_store.upsert_key_record(
        user_oid=u["user_id"],
        user_email=u["email"],
        server_id=server_id,
        apim_subscription_id=result["apim_subscription_id"],
        apim_product_id=product_id,
        key_hint=result["key_hint"],
    )

    await cosmos_store.log_audit_event(
        user_oid=u["user_id"],
        user_email=u["email"],
        action="create",
        server_id=server_id,
        details={"apim_subscription_id": result["apim_subscription_id"]},
    )

    logger.info(f"Key created: user={u['email']} server={server_id}")
    return {
        "server_id": server_id,
        "primary_key": result["primary_key"],
        "key_hint": result["key_hint"],
        "message": "Key generated successfully",
    }


@router.post("/{server_id}/rotate")
async def rotate_key(
    server_id: str,
    user: Annotated[dict | None, Depends(get_current_user)],
) -> dict[str, Any]:
    """Rotate (regenerate) the user's key for a server."""
    u = _require_user(user)
    from src.main import apim_manager, cosmos_store

    existing = await cosmos_store.get_user_key(u["user_id"], server_id)
    if not existing or existing.get("state") != "active":
        raise HTTPException(status_code=404, detail="No active key found for this server")

    result = await apim_manager.rotate_key(
        user_oid=u["user_id"],
        server_id=server_id,
    )

    product_id = apim_manager.get_product_id(server_id) or ""
    await cosmos_store.upsert_key_record(
        user_oid=u["user_id"],
        user_email=u["email"],
        server_id=server_id,
        apim_subscription_id=existing["apim_subscription_id"],
        apim_product_id=product_id,
        key_hint=result["key_hint"],
    )

    await cosmos_store.log_audit_event(
        user_oid=u["user_id"],
        user_email=u["email"],
        action="rotate",
        server_id=server_id,
        details={"rotation_count": existing.get("rotation_count", 0) + 1},
    )

    logger.info(f"Key rotated: user={u['email']} server={server_id}")
    return {
        "server_id": server_id,
        "primary_key": result["primary_key"],
        "key_hint": result["key_hint"],
        "message": "Key rotated successfully",
    }


@router.delete("/{server_id}")
async def revoke_key(
    server_id: str,
    user: Annotated[dict | None, Depends(get_current_user)],
) -> dict[str, Any]:
    """Revoke (suspend) the user's key for a server."""
    u = _require_user(user)
    from src.main import apim_manager, cosmos_store

    existing = await cosmos_store.get_user_key(u["user_id"], server_id)
    if not existing or existing.get("state") != "active":
        raise HTTPException(status_code=404, detail="No active key found for this server")

    await apim_manager.revoke_subscription(
        user_oid=u["user_id"],
        server_id=server_id,
    )

    await cosmos_store.revoke_key_record(u["user_id"], server_id)

    await cosmos_store.log_audit_event(
        user_oid=u["user_id"],
        user_email=u["email"],
        action="revoke",
        server_id=server_id,
    )

    logger.info(f"Key revoked: user={u['email']} server={server_id}")
    return {
        "server_id": server_id,
        "message": "Key revoked successfully",
    }
