"""IMAP connection pool — manages reusable connections per account.

Limits to max N connections per account, performs health checks,
and auto-reconnects stale connections.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.services.imap.client import BaseEmailClient

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONNECTIONS = 2


class ConnectionPool:
    """Pool of IMAP connections, keyed by account_id.

    Features:
    - Max N connections per account (default 2)
    - Health checks via NOOP before returning pooled connections
    - Auto-reconnect on stale connections
    - Async context manager for safe acquire/release
    """

    def __init__(self, max_per_account: int = DEFAULT_MAX_CONNECTIONS) -> None:
        self.max_per_account = max_per_account
        self._pools: dict[str, list[BaseEmailClient]] = defaultdict(list)
        self._in_use: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def connection(
        self,
        account_id: str,
        client_factory: type[BaseEmailClient] | None = None,
        **factory_kwargs: object,
    ) -> AsyncIterator[BaseEmailClient]:
        """Acquire a connection, yield it, then release it.

        Usage:
            async with pool.connection(account_id, ImapClient, host="imap.example.com") as client:
                emails = await client.fetch_emails()
        """
        client = await self.acquire(account_id, client_factory, **factory_kwargs)
        try:
            yield client
        finally:
            await self.release(account_id, client)

    async def acquire(
        self,
        account_id: str,
        client_factory: type[BaseEmailClient] | None = None,
        **factory_kwargs: object,
    ) -> BaseEmailClient:
        """Acquire a healthy connection from the pool.

        If no healthy connection is available and we haven't hit the limit,
        creates a new one via the factory.
        """
        async with self._lock:
            pool = self._pools[account_id]

            # Try to find a healthy pooled connection
            while pool:
                client = pool.pop(0)
                if await client.is_connected():
                    self._in_use[account_id] += 1
                    logger.debug(
                        "Reusing pooled connection for account %s (%d in use)",
                        account_id,
                        self._in_use[account_id],
                    )
                    return client
                else:
                    # Stale connection — discard
                    logger.debug("Discarding stale connection for account %s", account_id)
                    try:
                        await client.disconnect()
                    except Exception:
                        pass

            # Check if we can create a new connection
            if self._in_use[account_id] >= self.max_per_account:
                raise ConnectionError(
                    f"Connection pool exhausted for account {account_id} "
                    f"(max {self.max_per_account})"
                )

            # Create a new connection
            if client_factory is None:
                raise ValueError(
                    "No pooled connection available and no client_factory provided"
                )

            logger.info("Creating new connection for account %s", account_id)
            client = client_factory(**factory_kwargs)  # type: ignore[call-arg]
            self._in_use[account_id] += 1
            return client

    async def release(self, account_id: str, client: BaseEmailClient) -> None:
        """Return a connection to the pool."""
        async with self._lock:
            self._in_use[account_id] = max(0, self._in_use[account_id] - 1)

            if await client.is_connected():
                self._pools[account_id].append(client)
                logger.debug(
                    "Released connection back to pool for account %s (%d pooled, %d in use)",
                    account_id,
                    len(self._pools[account_id]),
                    self._in_use[account_id],
                )
            else:
                logger.debug("Discarding disconnected client for account %s", account_id)
                try:
                    await client.disconnect()
                except Exception:
                    pass

    async def close_all(self) -> None:
        """Close all pooled connections. Call on application shutdown."""
        async with self._lock:
            for account_id, pool in self._pools.items():
                for client in pool:
                    try:
                        await client.disconnect()
                    except Exception:
                        logger.warning(
                            "Error closing pooled connection for account %s", account_id
                        )
                pool.clear()

            self._in_use.clear()
            logger.info("All pooled connections closed")

    def stats(self) -> dict[str, dict[str, int]]:
        """Get pool statistics per account."""
        return {
            account_id: {
                "pooled": len(self._pools.get(account_id, [])),
                "in_use": self._in_use.get(account_id, 0),
            }
            for account_id in set(list(self._pools.keys()) + list(self._in_use.keys()))
        }
