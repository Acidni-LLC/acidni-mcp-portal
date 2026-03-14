"""Entra ID (Azure AD) authentication module."""

import logging
from typing import Any
from urllib.parse import urlencode

import msal
from fastapi import HTTPException, Request
from itsdangerous import BadSignature, URLSafeSerializer

from src.config import settings

logger = logging.getLogger(__name__)


class AuthService:
    """Handles Entra ID authentication flows."""

    def __init__(self) -> None:
        """Initialize the auth service."""
        self._msal_app: msal.ConfidentialClientApplication | None = None
        self._serializer = URLSafeSerializer(settings.secret_key, salt="session")

    @property
    def msal_app(self) -> msal.ConfidentialClientApplication:
        """Get or create MSAL application."""
        if self._msal_app is None:
            self._msal_app = msal.ConfidentialClientApplication(
                client_id=settings.azure_client_id,
                client_credential=settings.azure_client_secret,
                authority=settings.authority,
            )
        return self._msal_app

    def get_auth_url(self, state: str | None = None) -> str:
        """Generate the authorization URL for login.
        
        Args:
            state: Optional state parameter for CSRF protection
            
        Returns:
            Authorization URL to redirect user to
        """
        scopes = ["User.Read"]  # Basic profile info
        
        flow = self.msal_app.initiate_auth_code_flow(
            scopes=scopes,
            redirect_uri=settings.redirect_uri,
            state=state,
        )
        
        return flow.get("auth_uri", "")

    async def handle_callback(self, request: Request) -> dict[str, Any]:
        """Handle the OAuth callback and get user info.
        
        Args:
            request: FastAPI request with auth code
            
        Returns:
            User information dict
        """
        # Get the code from query params
        code = request.query_params.get("code")
        if not code:
            raise HTTPException(status_code=400, detail="No authorization code provided")

        # Exchange code for token
        scopes = ["User.Read"]
        result = self.msal_app.acquire_token_by_authorization_code(
            code=code,
            scopes=scopes,
            redirect_uri=settings.redirect_uri,
        )

        if "error" in result:
            logger.error(f"Auth error: {result.get('error_description')}")
            raise HTTPException(
                status_code=401,
                detail=result.get("error_description", "Authentication failed"),
            )

        # Extract user info from ID token claims
        claims = result.get("id_token_claims", {})
        
        return {
            "user_id": claims.get("oid"),  # Object ID
            "email": claims.get("preferred_username"),
            "name": claims.get("name"),
            "tenant_id": claims.get("tid"),
            "access_token": result.get("access_token"),
        }

    def create_session_token(self, user_data: dict[str, Any]) -> str:
        """Create a signed session token.
        
        Args:
            user_data: User information to encode
            
        Returns:
            Signed session token
        """
        return self._serializer.dumps(user_data)

    def validate_session_token(self, token: str) -> dict[str, Any] | None:
        """Validate and decode a session token.
        
        Args:
            token: Session token to validate
            
        Returns:
            User data if valid, None otherwise
        """
        try:
            return self._serializer.loads(token)
        except BadSignature:
            return None


# Singleton instance
auth_service = AuthService()


async def get_current_user(request: Request) -> dict[str, Any] | None:
    """Get the current authenticated user from session.
    
    Args:
        request: FastAPI request
        
    Returns:
        User data dict or None if not authenticated
    """
    session_token = request.cookies.get("session")
    if not session_token:
        return None
    
    return auth_service.validate_session_token(session_token)


async def require_auth(request: Request) -> dict[str, Any]:
    """Require authentication, raise 401 if not authenticated.
    
    Args:
        request: FastAPI request
        
    Returns:
        User data dict
        
    Raises:
        HTTPException: If user is not authenticated
    """
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
