"""Routes package."""

from src.routes.api import router as api_router
from src.routes.web import router as web_router

__all__ = ["api_router", "web_router"]
