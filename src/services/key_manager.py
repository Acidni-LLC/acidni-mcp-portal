"""APIM key lifecycle manager — creates per-user subscriptions via Azure Management REST API."""

import logging
from typing import Any

import httpx
from azure.identity.aio import DefaultAzureCredential

logger = logging.getLogger(__name__)

# APIM product IDs keyed by MCP server ID
_SERVER_TO_PRODUCT: dict[str, str] = {
    "terprint-mcp": "prod-terprint-mcp",
    "sdo-mcp": "prod-sdo-mcp",
    "solar-mcp": "prod-solar-mcp",
    "repolens-mcp": "prod-repolens-mcp",
}

_API_VERSION = "2023-09-01-preview"
_MGMT_SCOPE = "https://management.azure.com/.default"


class APIMKeyManager:
    """Manages per-user APIM subscriptions scoped to MCP products."""

    def __init__(
        self,
        subscription_id: str,
        resource_group: str,
        service_name: str,
    ) -> None:
        self._base = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}"
            f"/providers/Microsoft.ApiManagement/service/{service_name}"
        )
        self._credential: DefaultAzureCredential | None = None

    async def initialize(self) -> None:
        """Initialize credentials."""
        self._credential = DefaultAzureCredential()
        logger.info("APIM Key Manager initialized")

    async def close(self) -> None:
        """Clean up resources."""
        if self._credential:
            await self._credential.close()

    async def _get_token(self) -> str:
        """Get an Azure Management bearer token."""
        token = await self._credential.get_token(_MGMT_SCOPE)
        return token.token

    def _subscription_sid(self, user_oid: str, server_id: str) -> str:
        """Build deterministic subscription name: mcp-{oid_short}-{server}."""
        return f"mcp-{user_oid[:12]}-{server_id}"

    def get_product_id(self, server_id: str) -> str | None:
        """Get the APIM product ID for a server."""
        return _SERVER_TO_PRODUCT.get(server_id)

    async def create_subscription(
        self,
        user_oid: str,
        user_email: str,
        server_id: str,
    ) -> dict[str, Any]:
        """Create (or re-enable) a per-user APIM subscription for a server.

        Returns:
            Dict with apim_subscription_id, primary_key, key_hint.
        """
        product_id = _SERVER_TO_PRODUCT.get(server_id)
        if not product_id:
            raise ValueError(f"Unknown server: {server_id}")

        sid = self._subscription_sid(user_oid, server_id)
        product_scope = f"{self._base}/products/{product_id}"
        url = f"{self._base}/subscriptions/{sid}?api-version={_API_VERSION}"

        body = {
            "properties": {
                "scope": product_scope,
                "displayName": f"MCP | {user_email} | {server_id}",
                "state": "active",
            }
        }

        token = await self._get_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.put(
                url,
                json=body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()

        # Fetch the primary key
        primary_key = await self._list_secrets(sid)
        return {
            "apim_subscription_id": sid,
            "primary_key": primary_key,
            "key_hint": primary_key[-4:] if primary_key else "",
        }

    async def rotate_key(self, user_oid: str, server_id: str) -> dict[str, Any]:
        """Rotate the primary key by regenerating it.

        Returns:
            Dict with primary_key, key_hint.
        """
        sid = self._subscription_sid(user_oid, server_id)
        url = f"{self._base}/subscriptions/{sid}/regeneratePrimaryKey?api-version={_API_VERSION}"

        token = await self._get_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()

        primary_key = await self._list_secrets(sid)
        return {
            "primary_key": primary_key,
            "key_hint": primary_key[-4:] if primary_key else "",
        }

    async def revoke_subscription(self, user_oid: str, server_id: str) -> None:
        """Suspend a user's subscription (soft-delete — does not destroy)."""
        sid = self._subscription_sid(user_oid, server_id)
        url = f"{self._base}/subscriptions/{sid}?api-version={_API_VERSION}"

        body = {"properties": {"state": "suspended"}}

        token = await self._get_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.patch(
                url,
                json=body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()

    async def get_key(self, user_oid: str, server_id: str) -> str | None:
        """Fetch the current primary key for an existing subscription."""
        sid = self._subscription_sid(user_oid, server_id)
        try:
            return await self._list_secrets(sid)
        except httpx.HTTPStatusError:
            return None

    async def _list_secrets(self, sid: str) -> str:
        """Call listSecrets to retrieve the primary key for a subscription."""
        url = f"{self._base}/subscriptions/{sid}/listSecrets?api-version={_API_VERSION}"
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("primaryKey", "")
