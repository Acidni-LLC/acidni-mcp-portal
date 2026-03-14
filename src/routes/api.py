"""API routes for MCP discovery."""

import json
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
    
    Authenticated users get subscription keys included.
    """
    include_credentials = user is not None
    
    servers = registry.get_active()
    
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
                "status": s.status,
                "subscription_key": s.subscription_key if include_credentials else None,
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
    
    include_credentials = user is not None
    
    return {
        "id": server.id,
        "name": server.name,
        "description": server.description,
        "icon": server.icon,
        "url": server.url,
        "health_url": server.health_url,
        "transport": server.transport,
        "capabilities": server.capabilities or [],
        "status": server.status,
        "subscription_key": server.subscription_key if include_credentials else None,
        "configs": {
            "claude_desktop": server.to_claude_config() if include_credentials else None,
            "vscode": server.to_vscode_config() if include_credentials else None,
        } if include_credentials else None,
    }


@router.get("/api/configs/claude-desktop")
async def claude_desktop_config(
    user: Annotated[dict | None, Depends(get_current_user)],
) -> JSONResponse:
    """Get complete Claude Desktop config for all servers.
    
    Requires authentication.
    """
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    servers = registry.get_active()
    
    config = {
        "mcpServers": {
            s.id: s.to_claude_config()
            for s in servers
            if s.subscription_key
        }
    }
    
    return JSONResponse(
        content=config,
        headers={"Content-Type": "application/json"},
    )


@router.get("/api/configs/vscode")
async def vscode_config(
    user: Annotated[dict | None, Depends(get_current_user)],
) -> JSONResponse:
    """Get VS Code MCP config for all servers.
    
    Requires authentication.
    """
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    servers = registry.get_active()
    
    config = {
        "servers": {
            s.id: s.to_vscode_config()
            for s in servers
            if s.subscription_key
        }
    }
    
    return JSONResponse(
        content=config,
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
