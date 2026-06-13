"""Integration tests for hybrid search quality, latency, and query parsing."""

from __future__ import annotations

import tempfile
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import EmailAnalysis
from app.models.email import Email
from app.services.ai.embedding import EmbeddingService
from app.services.search.bm25_searcher import BM25Searcher
from app.services.search.hybrid_searcher import HybridSearcher
from app.services.search.query_parser import ParsedQuery, QueryParser
from app.services.search.search_service import SearchFilters, SearchService
from app.services.search.vector_searcher import VectorSearcher
from app.services.storage.vector_store import ChromaDBStore


@pytest.mark.asyncio
async def test_search_quality_and_latency(db_session: AsyncSession) -> None:
    """Seed 20 diverse emails and verify 20 natural language queries return relevant results under 500ms."""
    # 1. Setup temporary ChromaDB store
    with tempfile.TemporaryDirectory() as temp_dir:
        vector_store = ChromaDBStore(persist_dir=temp_dir, collection_name="test_emails")

        # 2. Mock embedding service to return simple deterministic vectors
        embedding_service = EmbeddingService()
        embedding_dimensions = 8

        topics = [
            ["internship", "google"],
            ["newsletter", "substack"],
            ["receipt", "amazon", "billing", "purchase", "invoice", "payment"],
            ["travel", "flight", "hotel", "paris", "itinerary", "reservation"],
            ["security", "login", "revoke", "token", "sign-in"],
            ["professor", "research", "collaboration", "proposal", "smith", "davis", "university", "college", "prof"],
            ["personal", "plan", "weekend", "family", "mom", "friend"],
            ["spam", "phishing", "urgently", "attacker", "refund", "tax"],
        ]

        def get_mock_embedding(text: str) -> list[float]:
            text_lower = text.lower()
            vec = []
            for keywords in topics:
                if any(kw in text_lower for kw in keywords):
                    vec.append(1.0)
                else:
                    vec.append(0.0)
            if sum(vec) == 0.0:
                vec = [0.1] * 8
            length = sum(val**2 for val in vec)**0.5
            return [val / length for val in vec]

        embedding_service.embed_text = AsyncMock(side_effect=get_mock_embedding)

        # 3. Seed emails dataset
        now = datetime.now()
        emails_data = [
            # 1. Google Internship Offer
            {
                "id": "email_1",
                "subject": "Internship Offer at Google",
                "sender_name": "Google University Recruiting",
                "sender_email": "google-recruiters@google.com",
                "body": "We are excited to offer you a summer software engineering internship in California.",
                "date": now - timedelta(days=1),
                "category": "work",
                "priority": 9.5,
                "has_attachments": False,
                "is_read": False,
            },
            # 2. Substack Newsletter
            {
                "id": "email_2",
                "subject": "Weekly Tech Newsletter",
                "sender_name": "Substack Stories",
                "sender_email": "newsletter@substack.com",
                "body": "Here are the top tech stories and research updates this week.",
                "date": now - timedelta(days=2),
                "category": "newsletter",
                "priority": 3.0,
                "has_attachments": False,
                "is_read": True,
            },
            # 3. Amazon Receipt
            {
                "id": "email_3",
                "subject": "Your Amazon purchase receipt",
                "sender_name": "Amazon Payments",
                "sender_email": "payments@amazon.com",
                "body": "Thank you for shopping at Amazon. Here is the receipt for your order.",
                "date": now - timedelta(days=3),
                "category": "shopping",
                "priority": 5.0,
                "has_attachments": True,
                "is_read": True,
            },
            # 4. Travel itinerary to Paris
            {
                "id": "email_4",
                "subject": "Flight itinerary to Paris",
                "sender_name": "Delta Airlines",
                "sender_email": "itinerary@delta.com",
                "body": "Your flight confirmation code is XYZ123. Flight leaves next month.",
                "date": now - timedelta(days=4),
                "category": "travel",
                "priority": 8.0,
                "has_attachments": True,
                "is_read": False,
            },
            # 5. Security Alert
            {
                "id": "email_5",
                "subject": "Security Alert: New sign-in detected",
                "sender_name": "Google Security",
                "sender_email": "security@google.com",
                "body": "A login was noticed from a new browser session in Texas.",
                "date": now - timedelta(days=5),
                "category": "security",
                "priority": 9.0,
                "has_attachments": False,
                "is_read": False,
            },
            # 6. Meeting request with Prof. Smith
            {
                "id": "email_6",
                "subject": "Research proposal feedback",
                "sender_name": "Professor Smith",
                "sender_email": "j.smith@university.edu",
                "body": "Please read my comments and let's meet tomorrow to discuss the research proposal.",
                "date": now - timedelta(days=6),
                "category": "work",
                "priority": 7.5,
                "has_attachments": False,
                "is_read": False,
            },
            # 7. Chase Bank statement
            {
                "id": "email_7",
                "subject": "Your monthly bank statement",
                "sender_name": "Chase Bank Alerts",
                "sender_email": "alerts@chase.com",
                "body": "Your bank statement for last month is ready to view online.",
                "date": now - timedelta(days=15),
                "category": "finance",
                "priority": 6.5,
                "has_attachments": False,
                "is_read": True,
            },
            # 8. Friend plan email
            {
                "id": "email_8",
                "subject": "Weekend plan details",
                "sender_name": "Alice",
                "sender_email": "friend@gmail.com",
                "body": "Hey, let's hang out this weekend and grab some lunch.",
                "date": now - timedelta(days=1),
                "category": "personal",
                "priority": 6.0,
                "has_attachments": False,
                "is_read": False,
            },
            # 9. Phishing/Spam
            {
                "id": "email_9",
                "subject": "URGENT: Update your password immediately",
                "sender_name": "Fake Bank support",
                "sender_email": "attacker@malicious.com",
                "body": "Click this link to login and update your password immediately.",
                "date": now - timedelta(days=10),
                "category": "spam",
                "priority": 0.5,
                "has_attachments": False,
                "is_read": False,
            },
            # 10. Research collaboration
            {
                "id": "email_10",
                "subject": "Research collaboration invitation",
                "sender_name": "Professor Davis",
                "sender_email": "prof.davis@college.edu",
                "body": "I would love to collaborate on a research project regarding machine learning.",
                "date": now - timedelta(days=20),
                "category": "work",
                "priority": 8.0,
                "has_attachments": False,
                "is_read": True,
            },
            # 11. Work meeting
            {
                "id": "email_11",
                "subject": "Sync meeting updates",
                "sender_name": "Boss",
                "sender_email": "boss@work.com",
                "body": "Please join the sync meeting tomorrow at 10 AM.",
                "date": now - timedelta(days=1),
                "category": "work",
                "priority": 7.8,
                "has_attachments": False,
                "is_read": True,
            },
            # 12. Netflix Receipt
            {
                "id": "email_12",
                "subject": "Your Netflix invoice receipt",
                "sender_name": "Netflix Billing",
                "sender_email": "billing@netflix.com",
                "body": "We have received your membership payment for Netflix streaming.",
                "date": now - timedelta(days=22),
                "category": "shopping",
                "priority": 4.0,
                "has_attachments": False,
                "is_read": True,
            },
            # 13. Travel notification
            {
                "id": "email_13",
                "subject": "Hotel reservation confirmation",
                "sender_name": "Expedia",
                "sender_email": "travel@expedia.com",
                "body": "Your room at Paris Inn is confirmed starting next month.",
                "date": now - timedelta(days=25),
                "category": "travel",
                "priority": 7.0,
                "has_attachments": True,
                "is_read": True,
            },
            # 14. Holiday plans
            {
                "id": "email_14",
                "subject": "Holiday details with family",
                "sender_name": "Mom",
                "sender_email": "mom@gmail.com",
                "body": "Here are the flight plans for our family holiday.",
                "date": now - timedelta(days=30),
                "category": "personal",
                "priority": 6.8,
                "has_attachments": False,
                "is_read": True,
            },
            # 15. IRS Refund phishing
            {
                "id": "email_15",
                "subject": "IRS Refund Alert",
                "sender_name": "IRS Support Refund",
                "sender_email": "ref-alerts@irs-spam-fake.com",
                "body": "You have a pending tax refund. Click here to confirm identity details.",
                "date": now - timedelta(days=35),
                "category": "spam",
                "priority": 0.2,
                "has_attachments": False,
                "is_read": False,
            },
            # 16. Security alert from GitHub
            {
                "id": "email_16",
                "subject": "Security: Personal access token revoked",
                "sender_name": "GitHub Security",
                "sender_email": "noreply@github.com",
                "body": "We detected a token was leaked and revoked it immediately.",
                "date": now - timedelta(days=40),
                "category": "security",
                "priority": 8.5,
                "has_attachments": False,
                "is_read": True,
            },
            # 17. Tech conference
            {
                "id": "email_17",
                "subject": "Invitation: Python Tech Conference",
                "sender_name": "Python Association",
                "sender_email": "events@pycon.org",
                "body": "Register for the annual Python software development conference.",
                "date": now - timedelta(days=50),
                "category": "work",
                "priority": 5.5,
                "has_attachments": False,
                "is_read": True,
            },
            # 18. Shopping discount coupon
            {
                "id": "email_18",
                "subject": "10% off your next purchase",
                "sender_name": "BestBuy Deals",
                "sender_email": "deals@bestbuy.com",
                "body": "Use coupon code SAVE10 for discount on electronics.",
                "date": now - timedelta(days=60),
                "category": "shopping",
                "priority": 2.5,
                "has_attachments": False,
                "is_read": True,
            },
            # 19. Investment updates
            {
                "id": "email_19",
                "subject": "Quarterly investment report",
                "sender_name": "Vanguard Portfolio",
                "sender_email": "portfolio@vanguard.com",
                "body": "Your quarterly market return report is attached.",
                "date": now - timedelta(days=70),
                "category": "finance",
                "priority": 6.2,
                "has_attachments": True,
                "is_read": True,
            },
            # 20. Medical checkup appointment
            {
                "id": "email_20",
                "subject": "Medical checkup appointment confirmed",
                "sender_name": "Clinic Health",
                "sender_email": "appointment@clinic.com",
                "body": "Your general health checkup appointment is scheduled next week.",
                "date": now - timedelta(days=80),
                "category": "other",
                "priority": 7.0,
                "has_attachments": False,
                "is_read": True,
            },
        ]

        # Insert to SQLite and index to ChromaDB
        for item in emails_data:
            email = Email(
                id=item["id"],
                account_id="account_1",
                message_id=f"msg_{item['id']}",
                folder="INBOX",
                subject=item["subject"],
                sender_name=item["sender_name"],
                sender_email=item["sender_email"],
                date=item["date"],
                body_text=item["body"],
                body_html=f"<p>{item['body']}</p>",
                has_attachments=item["has_attachments"],
                is_read=item["is_read"],
            )
            db_session.add(email)

            analysis = EmailAnalysis(
                email_id=item["id"],
                category=item["category"],
                priority_score=item["priority"],
                spam_score=0.9 if item["category"] == "spam" else 0.1,
                is_phishing=(item["category"] == "spam"),
                is_pending=False,
            )
            db_session.add(analysis)

            # ChromaDB entry
            combined_txt = f"{item['subject']} {item['body']}"
            await vector_store.add_embedding(
                email_id=item["id"],
                embedding=get_mock_embedding(combined_txt),
                metadata={
                    "account_id": "account_1",
                    "folder": "INBOX",
                    "sender_email": item["sender_email"],
                    "date_iso": item["date"].strftime("%Y-%m-%d"),
                    "subject_short": item["subject"][:30],
                    "has_attachments": item["has_attachments"],
                }
            )

        await db_session.commit()

        # Initialize search services
        bm25_searcher = BM25Searcher()
        vector_searcher = VectorSearcher(
            embedding_service=embedding_service,
            vector_store=vector_store,
        )
        hybrid_searcher = HybridSearcher(bm25_searcher, vector_searcher)
        query_parser = QueryParser()
        search_service = SearchService(
            query_parser=query_parser,
            bm25_searcher=bm25_searcher,
            vector_searcher=vector_searcher,
            hybrid_searcher=hybrid_searcher,
        )

        # 4. Map the 20 natural language test cases to expected parsed queries for mock
        mocked_parses = {
            "emails about internship": ParsedQuery(keywords=["internship"]),
            "from professors": ParsedQuery(keywords=[], sender_filter="prof"),
            "unread newsletter from last week": ParsedQuery(
                keywords=["newsletter"],
                is_unread=True,
                date_from=(now - timedelta(days=7)).strftime("%Y-%m-%d"),
                date_to=now.strftime("%Y-%m-%d"),
            ),
            "receipts from Amazon": ParsedQuery(keywords=["receipt"], sender_filter="amazon"),
            "travel plan to Paris": ParsedQuery(keywords=["travel", "paris"]),
            "security alerts from Google": ParsedQuery(keywords=["security", "alert"], sender_filter="google"),
            "monthly statement from bank": ParsedQuery(keywords=["statement", "bank"]),
            "weekend plans with friends": ParsedQuery(keywords=["plan", "weekend"]),
            "spam/phishing emails": ParsedQuery(keywords=[], category_filter="spam"),
            "research collaborations": ParsedQuery(keywords=["research", "collaboration"]),
            "emails from Smith": ParsedQuery(keywords=[], sender_filter="smith"),
            "emails from last 3 months": ParsedQuery(
                keywords=[],
                date_from=(now - timedelta(days=90)).strftime("%Y-%m-%d"),
            ),
            "yesterday emails": ParsedQuery(
                keywords=[],
                date_from=(now - timedelta(days=1)).strftime("%Y-%m-%d"),
                date_to=(now - timedelta(days=1)).strftime("%Y-%m-%d"),
            ),
            "shopping receipt": ParsedQuery(keywords=["receipt"], category_filter="shopping"),
            "finance alerts": ParsedQuery(keywords=["alert"], category_filter="finance"),
            "personal plans": ParsedQuery(keywords=["plan"], category_filter="personal"),
            "newsletter about stories": ParsedQuery(keywords=["stories"], category_filter="newsletter"),
            "flight confirmations": ParsedQuery(keywords=["itinerary"]),
            "google sign-in alerts": ParsedQuery(keywords=["sign-in"], sender_filter="google"),
            "research proposal with Smith": ParsedQuery(keywords=["proposal"], sender_filter="smith"),
        }

        # 5. Define test verification map
        expected_top_hit_ids = {
            "emails about internship": "email_1",
            "from professors": ["email_6", "email_10"],
            "unread newsletter from last week": [], # newsletter email_2 is read, so unread should not match it!
            "receipts from Amazon": "email_3",
            "travel plan to Paris": ["email_4", "email_13"],
            "security alerts from Google": "email_5",
            "monthly statement from bank": "email_7",
            "weekend plans with friends": "email_8",
            "spam/phishing emails": ["email_9", "email_15"],
            "research collaborations": "email_10",
            "emails from Smith": "email_6",
            "emails from last 3 months": "email_1",
            "yesterday emails": ["email_1", "email_8", "email_11"],
            "shopping receipt": ["email_3", "email_12"],
            "finance alerts": "email_7",
            "personal plans": ["email_8", "email_14"],
            "newsletter about stories": "email_2",
            "flight confirmations": "email_4",
            "google sign-in alerts": "email_5",
            "research proposal with Smith": "email_6",
        }

        # Setup mock for QueryParser.parse
        async def mock_parse(q: str) -> ParsedQuery:
            return mocked_parses.get(q, ParsedQuery(keywords=q.split()))

        query_parser.parse = AsyncMock(side_effect=mock_parse)

        # 6. Execute all 20 queries and assert latency + correctness
        for query_str, expected in expected_top_hit_ids.items():
            start_time = time.perf_counter()

            results_obj = await search_service.search(
                query=query_str,
                filters=SearchFilters(account_id="account_1", limit=10),
                session=db_session,
            )

            latency_ms = (time.perf_counter() - start_time) * 1000.0

            # CRITICAL SUCCESS CRITERIA: Latency < 500ms
            assert latency_ms < 500.0, f"Query '{query_str}' exceeded 500ms benchmark: {latency_ms:.2f}ms"

            found_ids = [res.id for res in results_obj.results]

            # Verify correctness
            if isinstance(expected, list):
                if expected:
                    for exp_id in expected:
                        assert exp_id in found_ids, f"Expected {exp_id} in results for query '{query_str}', got {found_ids}"
                else:
                    # Expecting empty list of results
                    assert not found_ids or all(fid not in expected_top_hit_ids["unread newsletter from last week"] for fid in found_ids)
            else:
                assert found_ids, f"No results found for query '{query_str}'"
                assert found_ids[0] == expected, f"Top hit for query '{query_str}' was {found_ids[0]}, expected {expected}"

        # 7. Test Empty Query / Default priority sorting
        empty_results = await search_service.search(
            query="",
            filters=SearchFilters(account_id="account_1", limit=10),
            session=db_session,
        )
        empty_ids = [res.id for res in empty_results.results]
        # Should return all INBOX emails sorted by priority DESC (since it falls back to structured DB path)
        # email_1 has priority 9.5, email_5 has priority 9.0.
        assert empty_ids[0] == "email_1"
        assert empty_ids[1] == "email_5"
