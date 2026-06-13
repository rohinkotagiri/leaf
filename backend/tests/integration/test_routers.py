"""Integration tests for all FastAPI routers using HTTPX AsyncClient."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.account import Account, ProviderType
from app.models.analysis import EmailAnalysis
from app.models.email import Email
from app.models.thread import Thread


@pytest.fixture
def test_app(db_session: AsyncSession) -> FastAPI:
    """Create FastAPI test application with overridden database session."""
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    yield app
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(test_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Create AsyncClient for routing testing."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture(autouse=True)
def mock_external_services():
    """Autouse fixture to mock external clients like ChromaDB and Ollama."""
    with (
        patch("app.services.ai.client.OllamaClient.is_running", new_callable=AsyncMock) as mock_is_run,
        patch("app.services.storage.vector_store.ChromaDBStore.get_collection_stats", new_callable=AsyncMock) as mock_chroma_stats,
        patch("app.services.storage.vector_store.ChromaDBStore.delete_by_ids", new_callable=AsyncMock),
        patch("app.services.ai.embedding.EmbeddingService.embed_text", new_callable=AsyncMock) as mock_embed,
        patch("app.services.storage.vector_store.ChromaDBStore.search_similar", new_callable=AsyncMock) as mock_search_similar,
    ):
        mock_is_run.return_value = True
        mock_chroma_stats.return_value = {"count": 42}
        mock_embed.return_value = [0.1] * 384
        mock_search_similar.return_value = [{"id": "msg_123", "distance": 0.1, "metadata": {}}]
        yield


@pytest.mark.asyncio
async def test_health_check_endpoint(client: AsyncClient) -> None:
    """Test GET /api/health retrieves correct status info."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"]["healthy"] is True
    assert data["chromadb"]["healthy"] is True
    assert data["ollama"]["healthy"] is True


@pytest.mark.asyncio
async def test_accounts_crud(client: AsyncClient, db_session: AsyncSession) -> None:
    """Test Account GET, POST, TEST and DELETE routes."""
    # List (empty initially)
    res_list = await client.get("/api/accounts")
    assert res_list.status_code == 200
    assert len(res_list.json()) == 0

    # Create Account
    payload = {
        "email_address": "test@example.com",
        "display_name": "Test account",
        "provider": "generic",
        "imap_host": "imap.example.com",
        "imap_port": 993,
        "use_ssl": True,
        "password": "secret_password"
    }

    with patch("app.services.imap.credential_store.AccountCredentialStore.store_password") as mock_store_pw:
        res_create = await client.post("/api/accounts", json=payload)
        assert res_create.status_code == 201
        acct_data = res_create.json()
        assert acct_data["email_address"] == "test@example.com"
        mock_store_pw.assert_called_once()

    # List again
    res_list = await client.get("/api/accounts")
    assert len(res_list.json()) == 1

    # Test Connection Route
    with patch("app.services.imap.credential_store.AccountCredentialStore.get_password", return_value="secret_password"):
        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.authenticate = AsyncMock()
        mock_client.disconnect = AsyncMock()

        with patch("app.routers.accounts.create_email_client", return_value=mock_client):
            res_test = await client.post(f"/api/accounts/{acct_data['id']}/test")
            assert res_test.status_code == 200
            assert res_test.json()["success"] is True

    # Delete Account
    res_del = await client.delete(f"/api/accounts/{acct_data['id']}")
    assert res_del.status_code == 200
    assert "deleted successfully" in res_del.json()["message"]


@pytest.mark.asyncio
async def test_emails_routing(client: AsyncClient, db_session: AsyncSession) -> None:
    """Test Email metadata listing, patching, actions, and thread/summary retrieval."""
    # Seed data
    account = Account(
        id="acct_emails_test",
        display_name="Email Tester",
        email_address="tester@example.com",
        provider=ProviderType.GENERIC,
        sync_enabled=True,
    )
    db_session.add(account)

    thread = Thread(id="thread_test", account_id=account.id, subject_base="Tester Thread")
    db_session.add(thread)

    email = Email(
        id="msg_123",
        account_id=account.id,
        thread_id=thread.id,
        message_id="<test1@example.com>",
        uid=1,
        folder="INBOX",
        subject="Hello World",
        sender_name="Alice",
        sender_email="alice@example.com",
        recipients_json="[]",
        date=datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC),
        body_text="Welcome to the system.",
        body_html="<p>Welcome</p>",
        has_attachments=False,
        attachment_names="[]",
        is_read=False,
        is_starred=False,
    )
    db_session.add(email)

    analysis = EmailAnalysis(
        email_id="msg_123",
        is_pending=False,
        category="work",
        priority_score=8.5,
        summary="Welcome greeting summary.",
        action_items="[]",
        extracted_dates="[]",
        extracted_entities="{}",
    )
    db_session.add(analysis)
    await db_session.commit()

    # 1. GET /api/emails (List with filter)
    res_list = await client.get("/api/emails?category=work&priority_min=5.0")
    assert res_list.status_code == 200
    data = res_list.json()
    assert len(data["emails"]) == 1
    assert data["emails"][0]["subject"] == "Hello World"
    assert data["emails"][0]["category"] == "work"
    assert data["emails"][0]["priority_score"] == 8.5

    # 2. GET /api/emails/{id} (Detail)
    res_detail = await client.get(f"/api/emails/{email.id}")
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert detail["body_text"] == "Welcome to the system."
    assert detail["analysis"]["summary"] == "Welcome greeting summary."

    # 3. PATCH /api/emails/{id} (Update flags)
    res_patch = await client.patch(f"/api/emails/{email.id}", json={"is_read": True, "is_starred": True})
    assert res_patch.status_code == 200
    patched_data = res_patch.json()
    assert patched_data["is_read"] is True
    assert patched_data["is_starred"] is True

    # 4. POST /api/emails/{id}/action (Archive)
    res_action = await client.post(f"/api/emails/{email.id}/action", json={"action": "archive"})
    assert res_action.status_code == 202
    assert "archive" in res_action.json()["message"]

    # Verify DB reflects folder move
    await db_session.refresh(email)
    assert email.folder == "Archive"

    # 5. GET /api/emails/{id}/thread
    res_thread = await client.get(f"/api/emails/{email.id}/thread")
    assert res_thread.status_code == 200
    thread_msgs = res_thread.json()
    assert len(thread_msgs) == 1
    assert thread_msgs[0]["id"] == email.id

    # 6. GET /api/emails/{id}/summary (Already analyzed)
    res_summary = await client.get(f"/api/emails/{email.id}/summary")
    assert res_summary.status_code == 200
    assert res_summary.json()["summary"] == "Welcome greeting summary."


@pytest.mark.asyncio
async def test_search_routing(client: AsyncClient, db_session: AsyncSession) -> None:
    """Test semantic search and autocomplete suggestion routes."""
    # Seed data
    account = Account(id="acct_search", email_address="search@example.com")
    db_session.add(account)
    email = Email(
        id="msg_123",
        account_id=account.id,
        subject="Weekly Report",
        sender_name="Alice",
        sender_email="alice@example.com",
        date=datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC),
    )
    db_session.add(email)
    await db_session.commit()

    # Semantic search query
    res_search = await client.post("/api/search", json={"query": "weekly update reports"})
    assert res_search.status_code == 200
    res_data = res_search.json()
    assert len(res_data) == 1
    assert res_data[0]["id"] == "msg_123"

    # Suggestions autocomplete
    res_suggest = await client.get("/api/search/suggestions?q=ali")
    assert res_suggest.status_code == 200
    suggest_data = res_suggest.json()
    assert "Alice <alice@example.com>" in suggest_data["senders"]


@pytest.mark.asyncio
async def test_sync_routing(client: AsyncClient, db_session: AsyncSession) -> None:
    """Test sync status and sync trigger endpoints."""
    # Seed data
    account = Account(id="acct_sync_1", email_address="sync1@example.com", sync_enabled=True)
    db_session.add(account)
    await db_session.commit()

    # GET /api/sync/status
    res_status = await client.get("/api/sync/status")
    assert res_status.status_code == 200
    status_list = res_status.json()
    assert len(status_list) == 1
    assert status_list[0]["email_address"] == "sync1@example.com"

    # POST /api/sync/{id} (trigger manual sync)
    with patch("app.workers.sync.SyncWorker.sync_account", new_callable=AsyncMock):
        res_trigger = await client.post(f"/api/sync/{account.id}")
        assert res_trigger.status_code == 202
        assert "triggered for account" in res_trigger.json()["message"]


@pytest.mark.asyncio
async def test_feedback_routing(client: AsyncClient, db_session: AsyncSession) -> None:
    """Test feedback submissions and statistics reports."""
    # Seed analysis
    analysis = EmailAnalysis(
        email_id="msg_feedback_test",
        is_pending=False,
        category="social",
        priority_score=2.0,
    )
    db_session.add(analysis)
    await db_session.commit()

    # Submit feedback correction
    payload = {
        "email_id": "msg_feedback_test",
        "field": "category",
        "old_value": "social",
        "new_value": "work"
    }
    res_post = await client.post("/api/feedback", json=payload)
    assert res_post.status_code == 201
    assert "Feedback submitted" in res_post.json()["message"]

    # Verify updated database
    await db_session.refresh(analysis)
    assert analysis.category == "work"

    # GET statistics
    res_stats = await client.get("/api/feedback/stats")
    assert res_stats.status_code == 200
    stats = res_stats.json()
    assert stats["total_corrections"] == 1
    assert stats["by_field"]["category"] == 1
