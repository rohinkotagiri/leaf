"""Seed script to populate the local database and ChromaDB with mock data.

Generates ~200 mock emails, conversation threads, and AI analysis records.
"""

import asyncio
import logging
import random
import uuid
from datetime import UTC, datetime, timedelta

from app.database import Base, async_session_factory, engine
from app.models.account import Account, ProviderType
from app.models.thread import Thread
from app.schemas.analysis import ActionItem, AnalysisCreate, ExtractedDate
from app.schemas.email import Attachment, EmailMessage, Recipient, RecipientType
from app.services.storage.account_repo import AccountRepository
from app.services.storage.analysis_repo import AnalysisRepository
from app.services.storage.email_repo import EmailRepository
from app.services.storage.storage_service import StorageService
from app.services.storage.vector_store import ChromaDBStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("seed")

# Core seed data parameters
NUM_EMAILS = 200
ACCOUNT_EMAIL = "user@privatemailai.local"
ACCOUNT_NAME = "Local User"

SUBJECTS = [
    "Project status update",
    "Meeting notes: marketing sync",
    "Urgent action required on contract",
    "Weekend plans?",
    "Weekly newsletter - Tech Trends",
    "Invoice #10928 attached",
    "Welcome to the team!",
    "Bug report: login screen layout",
    "Discussion on database migrations",
    "Question regarding Ollama setup",
    "Lunch tomorrow?",
    "Flight confirmation for San Francisco",
    "Antigravity repository updates",
    "Security alert: new sign-in detected",
    "Feedback request: design system mockup",
]

SENDERS = [
    ("Alice Smith", "alice@company.com"),
    ("Bob Jones", "bob@marketing.com"),
    ("Charlie Miller", "charlie@devs.net"),
    ("Delta Airlines", "noreply@delta.com"),
    ("Antigravity AI", "system@antigravity.ai"),
    ("GitHub", "noreply@github.com"),
    ("David Vance", "david@finance.org"),
    ("Emma Watson", "emma@creative.co"),
]

BODIES = [
    "Hi there, just wanted to check in and see if you had any updates on the project status. Let me know if you need anything from my end.",
    "Great meeting today. Here are the action items we discussed:\n1. Update layout mocks\n2. Prepare database migration plan\n3. Review Ollama models.",
    "Please find attached the signed contract for next year. Let us know if you need any adjustments or additional terms.",
    "Hey! Are you free this weekend for some hiking? The weather looks great. Let me know by Thursday.",
    "Welcome to this week's edition of Tech Trends. Today we discuss local LLMs, private storage architectures, and vector search strategies.",
    "Hello, your invoice #10928 is ready. Total due is $1,245.00 with net 30 terms. Thank you for your business.",
    "We are thrilled to welcome you to the engineering organization. Looking forward to working together on PrivateMailAI.",
    "The login screen is breaking on smaller viewports. The submit button overlaps with the footer. Can we get this fixed by tomorrow morning?",
    "We need to discuss our database migration strategy using Alembic. SQLite with async session handling is running great but we should monitor locks.",
]


def generate_random_embedding() -> list[float]:
    """Generate a random normalized 384-dimensional vector."""
    vec = [random.uniform(-1.0, 1.0) for _ in range(384)]
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm for x in vec]


async def seed_data() -> None:
    # 1. Initialize Tables
    logger.info("Initializing database schema...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Initialize Repos & Vector Store
    account_repo = AccountRepository()
    email_repo = EmailRepository()
    analysis_repo = AnalysisRepository()
    vector_store = ChromaDBStore()
    storage_service = StorageService(email_repo=email_repo, vector_store=vector_store)

    async with async_session_factory() as session:
        # Check if already seeded
        existing_accts = await account_repo.get_all(session)
        if existing_accts:
            logger.info("Database already seeded. Skipping...")
            return

        # 2. Create Email Account
        logger.info("Creating local email account...")
        account = Account(
            display_name=ACCOUNT_NAME,
            email_address=ACCOUNT_EMAIL,
            provider=ProviderType.GENERIC,
            imap_host="imap.privatemailai.local",
            imap_port=993,
            use_ssl=True,
            sync_enabled=True,
        )
        session.add(account)
        await session.flush()

        logger.info("Generating %d mock emails...", NUM_EMAILS)

        # Generate emails & threads
        emails_to_ingest = []
        threads_to_create = {}

        now = datetime.now(UTC)

        # Pre-create a few Thread ORMs to associate with conversation chains
        thread_ids = [str(uuid.uuid4()) for _ in range(20)]
        for tid in thread_ids:
            t_subject = f"Thread Conversation #{random.randint(100, 999)}"
            thread = Thread(
                id=tid,
                account_id=account.id,
                subject_base=t_subject,
                participants_json='["alice@company.com", "user@privatemailai.local"]',
                message_count=0,
                last_activity=now,
            )
            session.add(thread)
            threads_to_create[tid] = thread

        await session.flush()

        for i in range(NUM_EMAILS):
            sender_name, sender_email = random.choice(SENDERS)
            subject = random.choice(SUBJECTS)
            body = random.choice(BODIES)

            # Random folder distribution
            rand = random.random()
            if rand < 0.65:
                folder = "INBOX"
            elif rand < 0.85:
                folder = "Sent"
            elif rand < 0.95:
                folder = "Archive"
            else:
                folder = "Spam"

            # Randomize dates within last 30 days
            email_date = now - timedelta(
                days=random.randint(0, 30),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            )

            # Assign to thread with 30% probability
            thread_id = None
            if random.random() < 0.3:
                thread_id = random.choice(thread_ids)
                t = threads_to_create[thread_id]
                t.message_count += 1
                if not t.last_activity or email_date > t.last_activity:
                    t.last_activity = email_date

            # Random attachments
            attachments = []
            if random.random() < 0.15:
                attachments.append(
                    Attachment(
                        filename=f"attachment_{random.randint(1,100)}.pdf",
                        content_type="application/pdf",
                        size=random.randint(1000, 100000),
                    )
                )

            # Build parsed email DTO
            msg = EmailMessage(
                id=f"mock_email_{i}_{str(uuid.uuid4())[:8]}",
                account_id=account.id,
                thread_id=thread_id or "",
                message_id=f"<mock_{i}@privatemailai.local>",
                subject=subject if folder != "Sent" else f"Re: {subject}",
                sender_name=sender_name if folder != "Sent" else ACCOUNT_NAME,
                sender_email=sender_email if folder != "Sent" else ACCOUNT_EMAIL,
                recipients=[
                    Recipient(
                        name=ACCOUNT_NAME if folder != "Sent" else sender_name,
                        email=ACCOUNT_EMAIL if folder != "Sent" else sender_email,
                        type=RecipientType.TO,
                    )
                ],
                date=email_date,
                body_text=body,
                body_html=f"<html><body><p>{body}</p></body></html>",
                attachments=attachments,
                flags=["\\Seen"] if random.random() > 0.3 else [],
                folder=folder,
                uid=1000 + i,
            )
            emails_to_ingest.append(msg)

        # Sort emails by date for logical ingestion order
        emails_to_ingest.sort(key=lambda x: x.date)

        # Ingest emails via storage service (saves to SQL + ChromaDB)
        logger.info("Ingesting emails into SQL and ChromaDB vector store...")
        for idx, email_msg in enumerate(emails_to_ingest):
            embedding = generate_random_embedding()
            await storage_service.ingest_email(
                session,
                email_msg,
                embedding=embedding,
                raw_size_bytes=random.randint(500, 15000),
            )

            # Create mock analysis for ~40% of INBOX emails
            if email_msg.folder == "INBOX" and random.random() < 0.4:
                analysis_data = AnalysisCreate(
                    email_id=email_msg.id,
                    category=random.choice(["Work", "Personal", "Finance", "Updates", "Social"]),
                    priority_score=round(random.uniform(0.1, 0.95), 2),
                    spam_score=round(random.uniform(0.0, 0.2), 2),
                    is_phishing=random.random() < 0.02,
                    summary=f"Summary: {email_msg.body_text[:80]}...",
                    action_items=[
                        ActionItem(task="Reply to this thread", deadline="ASAP", priority="Medium")
                    ] if random.random() < 0.5 else [],
                    extracted_dates=[
                        ExtractedDate(date="Tomorrow", context="meeting deadline")
                    ] if random.random() < 0.3 else [],
                    extracted_entities={"organizations": [email_msg.sender_email.split("@")[1]]},
                    suggested_action="Reply to sender",
                    sentiment=random.choice(["positive", "neutral", "negative"]),
                    model_name="llama3:8b",
                    prompt_version="v1.2",
                    confidence=0.88,
                )
                await analysis_repo.save_analysis(session, analysis_data)
                # Mark as analyzed in DB
                await email_repo.mark_analyzed(session, email_msg.id)

            if (idx + 1) % 50 == 0:
                logger.info("Ingested %d/%d emails...", idx + 1, len(emails_to_ingest))

        # Commit session
        await session.commit()
        logger.info("Database seeding successfully completed!")


if __name__ == "__main__":
    asyncio.run(seed_data())
