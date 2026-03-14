"""MCP Discovery Portal - Main application entry point."""

import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.config import settings
from src.registry import registry
from src.routes import api_router, keys_router, web_router
from src.services.cosmos_client import CosmosKeyStore
from src.services.key_manager import APIMKeyManager

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Module-level service instances (initialized in lifespan)
cosmos_store: CosmosKeyStore
apim_manager: APIMKeyManager


def load_secrets_from_keyvault() -> None:
    """Load secrets from Azure Key Vault."""
    try:
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=settings.keyvault_url, credential=credential)

        # Load Entra ID credentials
        settings.azure_tenant_id = client.get_secret("azure-tenant-id").value or ""
        settings.azure_client_id = client.get_secret("mcp-portal-client-id").value or ""
        settings.azure_client_secret = client.get_secret("mcp-portal-client-secret").value or ""
        
        # Load secret key for sessions
        try:
            settings.secret_key = client.get_secret("mcp-portal-session-secret").value or settings.secret_key
        except Exception:
            logger.warning("Session secret not found in KV, using default (not for production!)")

        # Load APIM subscription keys for each server
        server_keys = [
            ("terprint-mcp", "apim-terprint-mcp-subscription-key"),
            ("sdo-mcp", "apim-sdo-mcp-subscription-key"),
            ("solar-mcp", "apim-solar-mcp-subscription-key"),
            ("repolens-mcp", "apim-repolens-mcp-subscription-key"),
        ]

        for server_id, secret_name in server_keys:
            try:
                key = client.get_secret(secret_name).value
                if key:
                    registry.set_subscription_key(server_id, key)
                    logger.info(f"Loaded subscription key for {server_id}")
            except Exception as e:
                logger.warning(f"Could not load key for {server_id}: {e}")

        # Load Application Insights connection string
        try:
            settings.applicationinsights_connection_string = (
                client.get_secret("appinsights-connection-string").value or ""
            )
        except Exception:
            logger.warning("App Insights connection string not found in KV")

        logger.info("Successfully loaded secrets from Key Vault")

    except Exception as e:
        logger.error(f"Failed to load secrets from Key Vault: {e}")
        if settings.is_production:
            raise


def setup_telemetry() -> None:
    """Configure OpenTelemetry for Application Insights."""
    if not settings.applicationinsights_connection_string:
        logger.warning("No Application Insights connection string - telemetry disabled")
        return

    try:
        from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter
        from opentelemetry import trace
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": settings.otel_service_name})
        provider = TracerProvider(resource=resource)

        exporter = AzureMonitorTraceExporter(
            connection_string=settings.applicationinsights_connection_string
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)
        logger.info("OpenTelemetry configured for Application Insights")

    except Exception as e:
        logger.error(f"Failed to configure telemetry: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    global cosmos_store, apim_manager

    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Environment: {settings.environment}")

    # Load secrets
    load_secrets_from_keyvault()

    # Setup telemetry
    setup_telemetry()

    # Initialize per-user key services
    cosmos_store = CosmosKeyStore(
        endpoint=settings.cosmos_endpoint,
        database_name=settings.cosmos_database,
    )
    await cosmos_store.initialize()

    apim_manager = APIMKeyManager(
        subscription_id=settings.azure_subscription_id,
        resource_group=settings.apim_resource_group,
        service_name=settings.apim_service_name,
    )
    await apim_manager.initialize()

    logger.info("Application startup complete")
    yield

    await cosmos_store.close()
    await apim_manager.close()
    logger.info("Application shutdown")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="MCP Discovery Portal - User dashboard and auto-discovery server for Acidni MCP servers",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    lifespan=lifespan,
)

# Add CORS for API endpoints
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://mcp.acidni.net", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Mount static files
try:
    app.mount("/static", StaticFiles(directory="src/static"), name="static")
except Exception:
    logger.warning("No static files directory found")

# Include routers
app.include_router(web_router)
app.include_router(api_router)
app.include_router(keys_router)


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "servers_registered": len(registry.get_active()),
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "type": "https://acidni.net/errors/internal-server-error",
            "title": "Internal Server Error",
            "status": 500,
            "detail": "An unexpected error occurred",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8080,
        reload=settings.debug,
    )
