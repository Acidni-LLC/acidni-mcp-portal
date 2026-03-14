"""API routes for MCP discovery."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from src.auth import get_current_user
from src.config import settings
from src.registry import registry

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/.well-known/mcp")
async def mcp_discovery() -> dict[str, Any]:
    """MCP Discovery endpoint - public, returns server list without credentials.
    
    This follows the MCP discovery protocol for clients to auto-discover servers.
    """
    return registry.get_discovery_manifest(include_credentials=False)


@router.get("/api/servers")
async def list_servers(
    user: Annotated[dict | None, Depends(get_current_user)],
) -> dict[str, Any]:
    """List all available MCP servers.
    
    Authenticated users get their per-user key status included.
    """
    servers = registry.get_active()

    user_keys: dict[str, dict] = {}
    if user:
        from src.main import cosmos_store

        records = await cosmos_store.get_user_keys(user["user_id"])
        user_keys = {r["server_id"]: r for r in records}

    return {
        "servers": [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "icon": s.icon,
                "url": s.url,
                "transport": s.transport,
                "capabilities": s.capabilities or [],
                "tools": s.tools or [],
                "verified_tools": s.verified_tools or [],
                "known_issues": s.known_issues or [],
                "status": s.status,
                "has_key": s.id in user_keys and user_keys[s.id].get("state") == "active",
                "key_hint": user_keys[s.id].get("key_hint") if s.id in user_keys else None,
            }
            for s in servers
        ],
        "total": len(servers),
    }


@router.get("/api/servers/{server_id}")
async def get_server(
    server_id: str,
    user: Annotated[dict | None, Depends(get_current_user)],
) -> dict[str, Any]:
    """Get details for a specific MCP server."""
    server = registry.get_by_id(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    key_record: dict | None = None
    per_user_key: str | None = None
    if user:
        from src.main import apim_manager, cosmos_store

        key_record = await cosmos_store.get_user_key(user["user_id"], server_id)
        if key_record and key_record.get("state") == "active":
            per_user_key = await apim_manager.get_key(user["user_id"], server_id)

    configs = None
    if user and per_user_key:
        configs = {
            "claude_desktop": server.to_claude_config(key_override=per_user_key),
            "vscode": server.to_vscode_config(key_override=per_user_key),
        }

    return {
        "id": server.id,
        "name": server.name,
        "description": server.description,
        "icon": server.icon,
        "url": server.url,
        "health_url": server.health_url,
        "transport": server.transport,
        "capabilities": server.capabilities or [],
        "tools": server.tools or [],
        "verified_tools": server.verified_tools or [],
        "known_issues": server.known_issues or [],
        "status": server.status,
        "has_key": bool(per_user_key),
        "key_hint": key_record.get("key_hint") if key_record else None,
        "configs": configs,
    }


@router.get("/api/configs/claude-desktop")
async def claude_desktop_config(
    user: Annotated[dict | None, Depends(get_current_user)],
) -> JSONResponse:
    """Get complete Claude Desktop config for all servers using per-user keys.
    
    Requires authentication.
    """
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    from src.main import apim_manager, cosmos_store

    servers = registry.get_active()
    user_keys = await cosmos_store.get_user_keys(user["user_id"])
    active_keys = {r["server_id"]: r for r in user_keys if r.get("state") == "active"}
    
    mcp_servers: dict[str, Any] = {}
    for s in servers:
        if s.id in active_keys:
            key = await apim_manager.get_key(user["user_id"], s.id)
            if key:
                mcp_servers[s.id] = s.to_claude_config(key_override=key)

    return JSONResponse(
        content={"mcpServers": mcp_servers},
        headers={"Content-Type": "application/json"},
    )


@router.get("/api/configs/vscode")
async def vscode_config(
    user: Annotated[dict | None, Depends(get_current_user)],
) -> JSONResponse:
    """Get VS Code MCP config for all servers using per-user keys.
    
    Requires authentication.
    """
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    from src.main import apim_manager, cosmos_store

    servers = registry.get_active()
    user_keys = await cosmos_store.get_user_keys(user["user_id"])
    active_keys = {r["server_id"]: r for r in user_keys if r.get("state") == "active"}
    
    server_configs: dict[str, Any] = {}
    for s in servers:
        if s.id in active_keys:
            key = await apim_manager.get_key(user["user_id"], s.id)
            if key:
                server_configs[s.id] = s.to_vscode_config(key_override=key)

    return JSONResponse(
        content={"servers": server_configs},
        headers={"Content-Type": "application/json"},
    )


@router.get("/api/health/{server_id}")
async def check_server_health(server_id: str) -> dict[str, Any]:
    """Check health of a specific MCP server.
    
    Public endpoint - returns basic up/down status.
    """
    import httpx
    
    server = registry.get_by_id(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    
    if not server.health_url:
        return {
            "server_id": server_id,
            "status": "unknown",
            "message": "No health endpoint configured",
        }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Hit APIM health endpoint with subscription key
            headers = {}
            if server.subscription_key:
                headers["Ocp-Apim-Subscription-Key"] = server.subscription_key
            
            response = await client.get(server.health_url, headers=headers)
            
            if response.status_code == 200:
                return {
                    "server_id": server_id,
                    "status": "healthy",
                    "response_time_ms": response.elapsed.total_seconds() * 1000,
                }
            else:
                return {
                    "server_id": server_id,
                    "status": "unhealthy",
                    "http_status": response.status_code,
                }
    except Exception as e:
        logger.warning(f"Health check failed for {server_id}: {e}")
        return {
            "server_id": server_id,
            "status": "unreachable",
            "error": str(e),
        }
