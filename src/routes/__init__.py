"""Routes package."""

from src.routes.api import router as api_router
from src.routes.keys import router as keys_router
from src.routes.web import router as web_router

__all__ = ["api_router", "keys_router", "web_router"]
