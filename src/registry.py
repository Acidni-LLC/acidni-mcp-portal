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
    tools: list[str] | None = None  # Actual MCP tool names
    verified_tools: list[str] | None = None  # Tools confirmed working
    known_issues: list[str] | None = None  # Known issues from testing
    status: str = "active"  # active, maintenance, deprecated, partial, down

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
            "tools": self.tools or [],
            "status": self.status,
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
                description="Terprint cannabis data intelligence - strains, dispensaries, batches, terpene profiles, recommendations, COA analysis",
                url="https://api.acidni.net/terprint-mcp/mcp",
                transport="sse",
                health_url="https://api.acidni.net/terprint-mcp/health",
                icon="🌿",
                product_code="terprint-mcp",
                capabilities=["batch_search", "terpene_lookup", "strain_search", "dispensary_search", "recommendations", "coa_analysis"],
                tools=[
                    "analyze_coa",
                    "calculate_temperature_mark",
                    "get_batch_details",
                    "get_dispensary_menu",
                    "get_recommendations",
                    "get_stock_index",
                    "get_terpene_profile",
                    "search_dispensaries",
                    "search_strains",
                ],
                status="partial",
                known_issues=[
                    "Data endpoints returning 404 - backend data services need verification",
                    "Check: Terprint data Container Apps (ca-terprint-data, etc.)",
                    "Check: APIM backend routing for /data, /recommend paths",
                ],
            ),
            MCPServer(
                id="sdo-mcp",
                name="AI SDO MCP",
                description="AI Software Development Organization - CMDB, App Registry, Products, Agents",
                url="https://api.acidni.net/sdo-mcp/mcp",
                transport="sse",
                health_url="https://api.acidni.net/sdo-mcp/health",
                icon="🏢",
                product_code="sdo-mcp",
                capabilities=["cmdb_query", "product_catalog", "agent_management", "app_lifecycle", "ci_search"],
                tools=[
                    "advance_lifecycle",
                    "create_cmdb_document",
                    "get_agent_config",
                    "get_ci_details",
                    "get_ci_relationships",
                    "get_cmdb_stats",
                    "get_product",
                    "get_product_repositories",
                    "list_agents",
                    "list_applications",
                    "list_products",
                    "register_application",
                    "search_cmdb",
                ],
                verified_tools=[
                    "get_cmdb_stats",
                    "search_cmdb",
                    "list_products",
                    "list_applications",
                ],
                status="active",
            ),
            MCPServer(
                id="solar-mcp",
                name="Solar MCP",
                description="Solar reporting - real-time battery SOC, power flow, energy data, alerts, generator sessions, AI insights, Solar Sizer",
                url="https://api.acidni.net/solar-mcp/mcp",
                transport="sse",
                health_url="https://api.acidni.net/solar-mcp/health",
                icon="☀️",
                product_code="solar-mcp",
                capabilities=["inverter_status", "battery_analytics", "energy_metrics", "generator_tracking", "solar_sizing", "alerts"],
                tools=[
                    "calculate_solar_sizing",
                    "get_ai_insights",
                    "get_alert_history",
                    "get_alert_rules",
                    "get_charger_power",
                    "get_current_status",
                    "get_daily_aggregates",
                    "get_energy_summary",
                    "get_generator_hours",
                    "get_generator_sessions",
                    "get_genstart_device",
                    "get_genstart_events",
                    "get_system_design",
                    "list_devices",
                    "list_genstart_devices",
                ],
                status="partial",
                known_issues=[
                    "Most endpoints returning 404 - backend Container Apps may be scaled to 0",
                    "list_genstart_devices returned 401 - APIM subscription key may need refresh",
                    "Check: ca-solar-web, ca-solar-collector replica counts",
                ],
            ),
            MCPServer(
                id="repolens-mcp",
                name="RepoLens MCP",
                description="GitHub repository analysis - manifests, CI/CD configs, Docker, K8s, IaC, PR diffs",
                url="https://api.acidni.net/repolens-mcp/mcp",
                transport="sse",
                health_url="https://api.acidni.net/repolens-mcp/health",
                icon="🔍",
                product_code="repolens-mcp",
                capabilities=["repo_analysis", "manifest_parsing", "cicd_analysis", "pr_diff", "iac_scanning"],
                tools=[
                    "analyze_repo",
                    "compare_manifests",
                    "get_manifests",
                    "get_pr_diff",
                    "get_pull_requests",
                    "get_repo_overview",
                ],
                status="down",
                known_issues=[
                    "Server not responding - no RFC 7807 errors, just empty responses",
                    "May need restart or redeployment via GitHub Actions",
                    "Check: RepoLens Container App process health",
                ],
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
        """Get servers that are not deprecated or retired.
        
        Returns:
            List of non-deprecated MCP servers (includes active, partial, down)
        """
        return [s for s in self._servers.values() if s.status not in ("deprecated", "retired")]

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
