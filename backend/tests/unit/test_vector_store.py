"""Unit tests for ChromaDBStore wrapper."""

import pytest
from app.services.storage.vector_store import ChromaDBStore


@pytest.fixture
def temp_chroma_store(tmp_path) -> ChromaDBStore:
    """Create a ChromaDBStore instance pointing to a temp directory."""
    persist_dir = tmp_path / "chromadb"
    # Ensure it uses a custom collection to avoid interference
    return ChromaDBStore(persist_dir=str(persist_dir), collection_name="test_collection")


@pytest.mark.asyncio
async def test_add_and_retrieve_embedding(temp_chroma_store: ChromaDBStore) -> None:
    # Adding a single embedding
    email_id = "test_email_1"
    embedding = [0.1, 0.2, 0.3, 0.4]
    metadata = {
        "account_id": "acct_1",
        "folder": "INBOX",
        "sender_email": "user@example.com",
        "has_attachments": False,
        "date_iso": "2024-01-01T12:00:00",
        "subject_short": "Meeting",
        "unsafe_key": "will_be_ignored",  # This should be sanitized out
    }

    await temp_chroma_store.add_embedding(email_id, embedding, metadata)

    # Check stats
    stats = await temp_chroma_store.get_collection_stats()
    assert stats["count"] == 1
    assert stats["collection_name"] == "test_collection"

    # Search (cosine distance)
    results = await temp_chroma_store.search_similar(query_embedding=[0.1, 0.2, 0.3, 0.35], n_results=1)
    assert len(results) == 1
    assert results[0]["id"] == email_id
    assert results[0]["metadata"]["folder"] == "INBOX"
    assert "unsafe_key" not in results[0]["metadata"]


@pytest.mark.asyncio
async def test_bulk_add_and_delete(temp_chroma_store: ChromaDBStore) -> None:
    items = [
        {
            "id": "email_a",
            "embedding": [1.0, 0.0, 0.0],
            "metadata": {"folder": "INBOX", "account_id": "acct_1"},
        },
        {
            "id": "email_b",
            "embedding": [0.0, 1.0, 0.0],
            "metadata": {"folder": "Sent", "account_id": "acct_1"},
        },
    ]

    added = await temp_chroma_store.add_embeddings_bulk(items)
    assert added == 2

    # Query with filter
    results = await temp_chroma_store.search_similar(
        query_embedding=[1.0, 0.0, 0.0],
        n_results=10,
        where={"folder": "Sent"},
    )
    assert len(results) == 1
    assert results[0]["id"] == "email_b"

    # Delete single
    await temp_chroma_store.delete_by_id("email_a")
    stats = await temp_chroma_store.get_collection_stats()
    assert stats["count"] == 1

    # Delete bulk
    await temp_chroma_store.delete_by_ids(["email_b"])
    stats = await temp_chroma_store.get_collection_stats()
    assert stats["count"] == 0
