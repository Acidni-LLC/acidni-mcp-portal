"""Web routes for the MCP Portal dashboard."""

import logging
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.auth import auth_service, get_current_user
from src.config import settings
from src.registry import registry

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="src/templates")


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    user: Annotated[dict | None, Depends(get_current_user)],
) -> Response:
    """Home page - redirects to dashboard if logged in, otherwise login page."""
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"settings": settings},
    )


@router.get("/login")
async def login(request: Request) -> RedirectResponse:
    """Initiate Entra ID login flow."""
    state = secrets.token_urlsafe(32)
    auth_url = auth_service.get_auth_url(state=state)
    
    response = RedirectResponse(url=auth_url, status_code=302)
    response.set_cookie(
        key="auth_state",
        value=state,
        httponly=True,
        secure=settings.is_production,
        max_age=600,  # 10 minutes
    )
    
    return response


@router.get("/auth/callback")
async def auth_callback(request: Request) -> RedirectResponse:
    """Handle OAuth callback from Entra ID."""
    try:
        # Retrieve the state from the cookie to look up the pending flow
        state = request.cookies.get("auth_state", "")
        user_data = await auth_service.handle_callback(request, state=state)
        session_token = auth_service.create_session_token(user_data)
        
        response = RedirectResponse(url="/dashboard", status_code=302)
        response.set_cookie(
            key="session",
            value=session_token,
            httponly=True,
            secure=settings.is_production,
            max_age=86400 * 7,  # 7 days
            samesite="lax",
        )
        response.delete_cookie("auth_state")
        
        logger.info(f"User logged in: {user_data.get('email')}")
        return response
        
    except Exception as e:
        logger.error(f"Auth callback error: {e}")
        return RedirectResponse(url="/?error=auth_failed", status_code=302)


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    """Log out the user."""
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("session")
    return response


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: Annotated[dict | None, Depends(get_current_user)],
) -> Response:
    """Main dashboard showing available MCP servers."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    from src.main import cosmos_store

    servers = registry.get_active()
    user_keys = await cosmos_store.get_user_keys(user["user_id"])
    key_map = {r["server_id"]: r for r in user_keys}
    
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": user,
            "servers": servers,
            "key_map": key_map,
            "settings": settings,
        },
    )


@router.get("/server/{server_id}", response_class=HTMLResponse)
async def server_detail(
    request: Request,
    server_id: str,
    user: Annotated[dict | None, Depends(get_current_user)],
) -> Response:
    """Server detail page with configuration snippets."""
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    server = registry.get_by_id(server_id)
    if not server:
        return RedirectResponse(url="/dashboard", status_code=302)

    from src.main import apim_manager, cosmos_store

    key_record = await cosmos_store.get_user_key(user["user_id"], server_id)
    per_user_key: str | None = None
    if key_record and key_record.get("state") == "active":
        per_user_key = await apim_manager.get_key(user["user_id"], server_id)

    return templates.TemplateResponse(
        request=request,
        name="server_detail.html",
        context={
            "user": user,
            "server": server,
            "key_record": key_record,
            "per_user_key": per_user_key,
            "settings": settings,
        },
    )
