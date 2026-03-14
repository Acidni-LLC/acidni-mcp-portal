"""Cosmos DB client for user key records and audit logs."""

import logging
from datetime import datetime, timezone
from typing import Any

from azure.cosmos.aio import CosmosClient
from azure.identity.aio import DefaultAzureCredential

logger = logging.getLogger(__name__)


class CosmosKeyStore:
    """Manages user-key records and audit logs in Cosmos DB."""

    def __init__(self, endpoint: str, database_name: str) -> None:
        self._endpoint = endpoint
        self._database_name = database_name
        self._client: CosmosClient | None = None
        self._credential: DefaultAzureCredential | None = None

    async def initialize(self) -> None:
        """Initialize the Cosmos DB client with managed identity."""
        self._credential = DefaultAzureCredential()
        self._client = CosmosClient(self._endpoint, credential=self._credential)
        database = self._client.get_database_client(self._database_name)
        self._keys_container = database.get_container_client("user-keys")
        self._audit_container = database.get_container_client("audit-log")
        logger.info("Cosmos DB key store initialized")

    async def close(self) -> None:
        """Close the Cosmos DB client."""
        if self._client:
            await self._client.close()
        if self._credential:
            await self._credential.close()

    async def get_user_keys(self, user_oid: str) -> list[dict[str, Any]]:
        """Get all key records for a user.

        Args:
            user_oid: User's Entra ID object identifier.

        Returns:
            List of key records for the user.
        """
        query = "SELECT * FROM c WHERE c.user_oid = @user_oid AND c.state = 'active'"
        params: list[dict[str, Any]] = [{"name": "@user_oid", "value": user_oid}]
        items = []
        async for item in self._keys_container.query_items(
            query=query,
            parameters=params,
            partition_key=user_oid,
        ):
            items.append(item)
        return items

    async def get_user_key(self, user_oid: str, server_id: str) -> dict[str, Any] | None:
        """Get a specific key record for a user and server.

        Args:
            user_oid: User's Entra ID object identifier.
            server_id: MCP server identifier.

        Returns:
            Key record dict or None.
        """
        doc_id = f"{user_oid}:{server_id}"
        try:
            return await self._keys_container.read_item(item=doc_id, partition_key=user_oid)
        except Exception:
            return None

    async def upsert_key_record(
        self,
        user_oid: str,
        user_email: str,
        server_id: str,
        apim_subscription_id: str,
        apim_product_id: str,
        key_hint: str,
    ) -> dict[str, Any]:
        """Create or update a key record.

        Args:
            user_oid: User's Entra ID object identifier.
            user_email: User's email address.
            server_id: MCP server identifier.
            apim_subscription_id: APIM subscription resource name.
            apim_product_id: APIM product identifier.
            key_hint: Last 4 chars of the key for display.

        Returns:
            The upserted document.
        """
        now = datetime.now(timezone.utc).isoformat()
        doc_id = f"{user_oid}:{server_id}"

        existing = await self.get_user_key(user_oid, server_id)
        if existing:
            existing["last_rotated_at"] = now
            existing["rotation_count"] = existing.get("rotation_count", 0) + 1
            existing["key_hint"] = key_hint
            existing["state"] = "active"
            return await self._keys_container.upsert_item(existing)

        record = {
            "id": doc_id,
            "user_oid": user_oid,
            "user_email": user_email,
            "server_id": server_id,
            "apim_subscription_id": apim_subscription_id,
            "apim_product_id": apim_product_id,
            "key_hint": key_hint,
            "state": "active",
            "created_at": now,
            "last_rotated_at": now,
            "rotation_count": 0,
        }
        return await self._keys_container.upsert_item(record)

    async def revoke_key_record(self, user_oid: str, server_id: str) -> bool:
        """Mark a key record as revoked.

        Args:
            user_oid: User's Entra ID object identifier.
            server_id: MCP server identifier.

        Returns:
            True if revoked, False if not found.
        """
        existing = await self.get_user_key(user_oid, server_id)
        if not existing:
            return False

        existing["state"] = "revoked"
        existing["revoked_at"] = datetime.now(timezone.utc).isoformat()
        await self._keys_container.upsert_item(existing)
        return True

    async def log_audit_event(
        self,
        user_oid: str,
        user_email: str,
        action: str,
        server_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Write an audit log entry.

        Args:
            user_oid: User OID.
            user_email: User email.
            action: Action performed (create, rotate, revoke).
            server_id: MCP server ID.
            details: Optional extra details.
        """
        now = datetime.now(timezone.utc)
        entry = {
            "id": f"{user_oid}:{server_id}:{now.strftime('%Y%m%d%H%M%S%f')}",
            "user_oid": user_oid,
            "user_email": user_email,
            "action": action,
            "server_id": server_id,
            "timestamp": now.isoformat(),
            "details": details or {},
        }
        await self._audit_container.upsert_item(entry)
