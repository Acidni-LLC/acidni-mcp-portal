"""MCP Server registry and discovery service."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MCPServer:
    """MCP Server definition."""

    id: str
    name: str
    description: str
    url: str
    transport: str  # "sse" or "stdio"
    health_url: str | None = None
    icon: str | None = None
    product_code: str | None = None
    subscription_key: str | None = None  # APIM subscription key
    requires_auth: bool = True
    capabilities: list[str] | None = None
    status: str = "active"  # active, maintenance, deprecated

    def to_discovery_format(self, include_credentials: bool = False) -> dict[str, Any]:
        """Convert to MCP discovery format.
        
        Args:
            include_credentials: Whether to include subscription key
            
        Returns:
            Discovery-compliant dict
        """
        result = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "transport": {
                "type": self.transport,
                "url": self.url,
            },
            "capabilities": self.capabilities or [],
        }
        
        if include_credentials and self.subscription_key:
            result["transport"]["headers"] = {
                "Ocp-Apim-Subscription-Key": self.subscription_key
            }
        
        return result

    def to_claude_config(self, key_override: str | None = None) -> dict[str, Any]:
        """Convert to Claude Desktop config format.
        
        Args:
            key_override: Per-user key to use instead of the shared key.
            
        Returns:
            Claude Desktop mcpServers entry
        """
        config: dict[str, Any] = {
            "command": "npx",
            "args": ["-y", "mcp-remote", self.url],
        }
        
        key = key_override or self.subscription_key
        if key:
            config["env"] = {
                "MCP_HEADERS": f"Ocp-Apim-Subscription-Key:{key}"
            }
        
        return config

    def to_vscode_config(self, key_override: str | None = None) -> dict[str, Any]:
        """Convert to VS Code MCP config format.
        
        Args:
            key_override: Per-user key to use instead of the shared key.
            
        Returns:
            VS Code mcp.json entry
        """
        config: dict[str, Any] = {
            "type": "sse",
            "url": self.url,
        }
        
        key = key_override or self.subscription_key
        if key:
            config["headers"] = {
                "Ocp-Apim-Subscription-Key": key
            }
        
        return config


class MCPRegistry:
    """Registry of available MCP servers."""

    def __init__(self) -> None:
        """Initialize the registry with known servers."""
        self._servers: dict[str, MCPServer] = {}
        self._load_servers()

    def _load_servers(self) -> None:
        """Load the known MCP servers."""
        # These will be populated from Key Vault at runtime
        servers = [
            MCPServer(
                id="terprint-mcp",
                name="Terprint MCP",
                description="Cannabis batch data, terpene profiles, and inventory analytics",
                url="https://api.acidni.net/terprint-mcp/mcp",
                transport="sse",
                health_url="https://api.acidni.net/terprint-mcp/health",
                icon="🌿",
                product_code="terprint-mcp",
                capabilities=["batch_search", "terpene_lookup", "inventory_analytics"],
            ),
            MCPServer(
                id="sdo-mcp",
                name="AI SDO MCP",
                description="AI Software Development Organization - CMDB, products, and governance",
                url="https://api.acidni.net/sdo-mcp/mcp",
                transport="sse",
                health_url="https://api.acidni.net/sdo-mcp/health",
                icon="🏢",
                product_code="sdo-mcp",
                capabilities=["cmdb_query", "product_catalog", "governance_lookup"],
            ),
            MCPServer(
                id="solar-mcp",
                name="Solar MCP",
                description="Solar energy monitoring, EG4 inverter data, and battery analytics",
                url="https://api.acidni.net/solar-mcp/mcp",
                transport="sse",
                health_url="https://api.acidni.net/solar-mcp/health",
                icon="☀️",
                product_code="solar-mcp",
                capabilities=["inverter_status", "battery_analytics", "energy_metrics"],
            ),
            MCPServer(
                id="repolens-mcp",
                name="RepoLens MCP",
                description="GitHub repository analysis, code insights, and PR metrics",
                url="https://api.acidni.net/repolens-mcp/mcp",
                transport="sse",
                health_url="https://api.acidni.net/repolens-mcp/health",
                icon="🔍",
                product_code="repolens-mcp",
                capabilities=["repo_analysis", "code_metrics", "pr_insights"],
            ),
        ]

        for server in servers:
            self._servers[server.id] = server

    def get_all(self) -> list[MCPServer]:
        """Get all registered servers.
        
        Returns:
            List of all MCP servers
        """
        return list(self._servers.values())

    def get_active(self) -> list[MCPServer]:
        """Get only active servers.
        
        Returns:
            List of active MCP servers
        """
        return [s for s in self._servers.values() if s.status == "active"]

    def get_by_id(self, server_id: str) -> MCPServer | None:
        """Get a server by ID.
        
        Args:
            server_id: Server identifier
            
        Returns:
            MCPServer or None if not found
        """
        return self._servers.get(server_id)

    def set_subscription_key(self, server_id: str, key: str) -> None:
        """Set the subscription key for a server.
        
        Args:
            server_id: Server identifier
            key: APIM subscription key
        """
        if server_id in self._servers:
            self._servers[server_id].subscription_key = key

    def get_discovery_manifest(
        self, include_credentials: bool = False
    ) -> dict[str, Any]:
        """Get the discovery manifest for MCP clients.
        
        Args:
            include_credentials: Include subscription keys
            
        Returns:
            Discovery manifest dict
        """
        return {
            "discovery_version": "1.0",
            "provider": {
                "name": "Acidni LLC",
                "url": "https://acidni.net",
            },
            "servers": [
                s.to_discovery_format(include_credentials=include_credentials)
                for s in self.get_active()
            ],
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }


# Singleton instance
registry = MCPRegistry()
