# Acidni MCP Portal

MCP Discovery Portal - User dashboard and auto-discovery server for Acidni MCP servers.

## Features

- **User Dashboard**: Sign in with Microsoft to view available MCP servers and get your API keys
- **Auto-Discovery**: `/.well-known/mcp` endpoint for MCP clients to auto-discover servers
- **Copy-Paste Configs**: Pre-formatted configurations for Claude Desktop, VS Code, and more
- **Health Monitoring**: Real-time health status for all registered MCP servers

## Available MCP Servers

| Server | Description | Capabilities |
|--------|-------------|--------------|
| **Terprint MCP** | Cannabis batch data, terpene profiles, and inventory analytics | batch_search, terpene_lookup, inventory_analytics |
| **AI SDO MCP** | AI Software Development Organization - CMDB, products, governance | cmdb_query, product_catalog, governance_lookup |
| **Solar MCP** | Solar energy monitoring, EG4 inverter data, battery analytics | inverter_status, battery_analytics, energy_metrics |
| **RepoLens MCP** | GitHub repository analysis, code insights, PR metrics | repo_analysis, code_metrics, pr_insights |

## Quick Start

### Using the Portal

1. Visit https://mcp.acidni.net
2. Sign in with your Microsoft account
3. Browse available servers on the dashboard
4. Copy configuration snippets for your preferred client

### Auto-Discovery (for MCP clients)

MCP clients can discover available servers via:

```
GET https://mcp.acidni.net/.well-known/mcp
```

## Development

### Prerequisites

- Python 3.12+
- Azure CLI (for Key Vault access)

### Local Setup

```bash
# Clone the repository
git clone https://github.com/Acidni-LLC/acidni-mcp-portal.git
cd acidni-mcp-portal

# Create virtual environment
python -m venv venv
venv/Scripts/Activate.ps1  # Windows
source venv/bin/activate   # Linux/Mac

# Install dependencies
pip install -e ".[dev]"

# Create .env file
cat > .env << EOF
ENVIRONMENT=development
DEBUG=true
KEYVAULT_NAME=kv-terprint-dev
EOF

# Run locally
python -m src.main
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | development/production | development |
| `DEBUG` | Enable debug mode | false |
| `KEYVAULT_NAME` | Azure Key Vault name | kv-terprint-dev |
| `SECRET_KEY` | Session encryption key | (loaded from KV) |

### Required Key Vault Secrets

- `azure-tenant-id` - Entra ID tenant
- `mcp-portal-client-id` - App registration client ID
- `mcp-portal-client-secret` - App registration secret
- `mcp-portal-session-secret` - Session encryption key
- `apim-terprint-mcp-subscription-key` - APIM keys for each server
- `apim-sdo-mcp-subscription-key`
- `apim-solar-mcp-subscription-key`
- `apim-repolens-mcp-subscription-key`

## Deployment

Deployed via GitHub Actions to Azure Container Apps:

- **Container App**: `ca-mcp-portal`
- **Resource Group**: `rg-dev-acidni-shared`
- **Custom Domain**: `mcp.acidni.net`

## API Endpoints

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /` | No | Landing page |
| `GET /dashboard` | Yes | User dashboard |
| `GET /server/{id}` | Yes | Server details |
| `GET /.well-known/mcp` | No | MCP discovery manifest |
| `GET /api/servers` | Optional | List all servers |
| `GET /api/configs/claude-desktop` | Yes | Claude Desktop config |
| `GET /api/configs/vscode` | Yes | VS Code config |
| `GET /api/health/{id}` | No | Server health check |
| `GET /health` | No | Portal health check |

## License

Proprietary - Acidni LLC
