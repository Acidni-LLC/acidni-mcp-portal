"""Configuration settings for MCP Discovery Portal."""

from functools import cached_property

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "Acidni MCP Portal"
    app_version: str = "0.1.1"
    environment: str = "development"
    debug: bool = False
    secret_key: str = "change-me-in-production"

    # Azure Key Vault
    keyvault_name: str = "kv-terprint-dev"

    @cached_property
    def keyvault_url(self) -> str:
        """Get Key Vault URL."""
        return f"https://{self.keyvault_name}.vault.azure.net/"

    # Entra ID (Azure AD) - loaded from Key Vault in production
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""

    # Cosmos DB
    cosmos_endpoint: str = "https://acidni-cosmos-dev.documents.azure.com:443/"
    cosmos_database: str = "mcp-portal-dev"

    # APIM
    apim_base_url: str = "https://api.acidni.net"
    azure_subscription_id: str = "bb40fccf-9ffa-4bad-b9c0-ea40e326882c"
    apim_resource_group: str = "rg-terprint-apim-dev"
    apim_service_name: str = "apim-terprint-dev"

    # OpenTelemetry
    otel_service_name: str = "acidni-mcp-portal"
    applicationinsights_connection_string: str = ""

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment.lower() == "production"

    @property
    def authority(self) -> str:
        """Get Entra ID authority URL."""
        return f"https://login.microsoftonline.com/{self.azure_tenant_id}"

    @property
    def redirect_uri(self) -> str:
        """Get OAuth redirect URI based on environment."""
        if self.is_production:
            return "https://mcp.acidni.net/auth/callback"
        return "http://localhost:8080/auth/callback"


settings = Settings()
