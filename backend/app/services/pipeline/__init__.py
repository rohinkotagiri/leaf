"""AI Processing Pipeline — orchestrates ingestion, embedding, classification, and deep analysis."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.schemas.email import EmailMessage
from app.schemas.analysis import AnalysisCreate, ActionItem, ExtractedDate
from app.services.storage.storage_service import StorageService
from app.services.storage.email_repo import EmailRepository
from app.services.storage.analysis_repo import AnalysisRepository
from app.services.ai.embedding import EmbeddingService
from app.services.ai.classification import ClassificationService
from app.services.ai.summarization import SummarizationService
from app.services.ai.extraction import ExtractionService
from app.services.priority import PriorityScorer

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Represents the results of the IngestionPipeline."""
    email_id: str
    stages_completed: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    duration_ms: float = 0.0
    model_versions: dict[str, str] = field(default_factory=dict)


class AnalysisResult(BaseModel):
    """Represents the results of the AnalysisPipeline."""
    email_id: str
    success: bool
    stages_completed: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    category: str | None = None
    priority_score: float | None = None
    spam_score: float | None = None
    is_spam: bool = False
    is_phishing: bool = False
    duration_ms: float = 0.0


class IngestionPipeline:
    """Orchestrates Stage 1 to 4 of email ingestion: Parse/Deduplicate, SQL, Embeddings, Queue."""

    def __init__(
        self,
        storage_service: StorageService | None = None,
        embedding_service: EmbeddingService | None = None,
        analysis_repo: AnalysisRepository | None = None,
    ) -> None:
        self.storage_service = storage_service or StorageService()
        self.embedding_service = embedding_service or EmbeddingService()
        self.analysis_repo = analysis_repo or AnalysisRepository()

    async def ingest_email(self, session: AsyncSession, raw_email: EmailMessage) -> PipelineResult:
        """Process a parsed email message: deduplicate, save metadata, generate embeddings, and queue for AI."""
        start_time = time.perf_counter()
        
        result = PipelineResult(
            email_id=raw_email.id,
            model_versions={
                "embed_model": self.embedding_service.model
            }
        )
        
        # Stage 1: Parse & Deduplicate
        try:
            existing = await self.storage_service.email_repo.get_by_id(session, raw_email.id)
            if existing is not None:
                logger.info("Email %s already exists. Skipping ingestion.", raw_email.id[:12])
                result.stages_completed.append("deduplication")
                result.duration_ms = (time.perf_counter() - start_time) * 1000.0
                return result
            result.stages_completed.append("deduplication")
        except Exception as e:
            logger.error("Deduplication stage failed for email %s", raw_email.id, exc_info=True)
            result.errors["deduplication"] = str(e)
            result.duration_ms = (time.perf_counter() - start_time) * 1000.0
            return result

        # Stage 2: Save to SQL
        try:
            await self.storage_service.email_repo.save_email(session, raw_email)
            result.stages_completed.append("sql_save")
        except Exception as e:
            logger.error("SQL save stage failed for email %s", raw_email.id, exc_info=True)
            result.errors["sql_save"] = str(e)
            result.duration_ms = (time.perf_counter() - start_time) * 1000.0
            return result

        # Stage 3: Generate embedding & save to ChromaDB (non-critical)
        embedding = None
        if raw_email.body_text or raw_email.subject:
            try:
                # Combine subject and body text to generate richer embedding context
                embed_text = f"Subject: {raw_email.subject}\nBody: {raw_email.body_text}"
                embedding = await self.embedding_service.embed_text(embed_text)
                
                if self.storage_service.vector_store is not None:
                    metadata = self.storage_service._build_vector_metadata(raw_email)
                    await self.storage_service.vector_store.add_embedding(
                        email_id=raw_email.id,
                        embedding=embedding,
                        metadata=metadata,
                    )
                    await self.storage_service.email_repo.mark_indexed(session, raw_email.id)
                result.stages_completed.append("embedding")
            except Exception as e:
                logger.warning("Embedding stage failed for email %s — proceeding anyway", raw_email.id, exc_info=True)
                result.errors["embedding"] = str(e)

        # Stage 4: Enqueue for AI analysis (non-critical)
        try:
            analysis_data = AnalysisCreate(
                email_id=raw_email.id,
                is_pending=True,
                action_items=[],
                extracted_dates=[],
                extracted_entities={},
            )
            await self.analysis_repo.save_analysis(session, analysis_data)
            result.stages_completed.append("enqueue")
        except Exception as e:
            logger.warning("Enqueue stage failed for email %s — proceeding anyway", raw_email.id, exc_info=True)
            result.errors["enqueue"] = str(e)

        result.duration_ms = (time.perf_counter() - start_time) * 1000.0
        return result


class AnalysisPipeline:
    """Orchestrates the AI classification (Fast Pass) and deep analysis (Deep Pass)."""

    def __init__(
        self,
        email_repo: EmailRepository | None = None,
        analysis_repo: AnalysisRepository | None = None,
        classification_service: ClassificationService | None = None,
        summarization_service: SummarizationService | None = None,
        extraction_service: ExtractionService | None = None,
    ) -> None:
        self.email_repo = email_repo or EmailRepository()
        self.analysis_repo = analysis_repo or AnalysisRepository()
        self.classification_service = classification_service or ClassificationService()
        self.summarization_service = summarization_service or SummarizationService()
        self.extraction_service = extraction_service or ExtractionService()

    async def analyze_email(self, session: AsyncSession, email_id: str) -> AnalysisResult:
        """Run two-pass classification & analysis. Applies spam filter and enriches non-spam."""
        start_time = time.perf_counter()
        
        stages_completed = []
        errors = {}
        
        # 1. Fetch Email
        email = await self.email_repo.get_by_id(session, email_id)
        if not email:
            duration = (time.perf_counter() - start_time) * 1000.0
            return AnalysisResult(
                email_id=email_id,
                success=False,
                stages_completed=stages_completed,
                errors={"fetch": "Email not found in database"},
                duration_ms=duration
            )
            
        # 2. Fast pass: Classification (Llama 3.2 3B)
        try:
            class_res = await self.classification_service.classify_email(
                subject=email.subject,
                sender=f"{email.sender_name} <{email.sender_email}>",
                body=email.body_text,
                session=session
            )
            stages_completed.append("classification")
        except Exception as e:
            logger.exception("Classification failed for email %s", email_id)
            duration = (time.perf_counter() - start_time) * 1000.0
            return AnalysisResult(
                email_id=email_id,
                success=False,
                stages_completed=stages_completed,
                errors={"classification": str(e)},
                duration_ms=duration
            )

        # 3. Gate check: If spam_score > 0.85, skip deep pass, save as spam
        is_spam_gate = class_res.spam_score > 0.85
        if is_spam_gate:
            try:
                analysis_data = AnalysisCreate(
                    email_id=email_id,
                    is_pending=False,
                    category="spam",
                    priority_score=0.0,
                    spam_score=class_res.spam_score,
                    is_phishing=class_res.is_phishing,
                    summary="Spam filtered (fast pass)",
                    action_items=[],
                    extracted_dates=[],
                    extracted_entities={},
                    suggested_action="archive",
                    sentiment="neutral",
                    model_name=self.classification_service.model,
                    prompt_version=settings.PROMPT_VERSION,
                    confidence=class_res.confidence,
                )
                await self.analysis_repo.save_analysis(session, analysis_data)
                await self.email_repo.mark_analyzed(session, email_id)
                stages_completed.append("spam_gate")
                
                # Emit WebSocket Event
                try:
                    from app.services.websocket import manager
                    await manager.broadcast({"type": "analysis_complete", "email_id": email_id})
                    stages_completed.append("websocket_emit")
                except Exception as e:
                    logger.warning("WebSocket emit failed for email %s", email_id, exc_info=True)
                    errors["websocket"] = str(e)
                
                duration = (time.perf_counter() - start_time) * 1000.0
                return AnalysisResult(
                    email_id=email_id,
                    success=True,
                    stages_completed=stages_completed,
                    errors=errors,
                    category="spam",
                    priority_score=0.0,
                    spam_score=class_res.spam_score,
                    is_spam=True,
                    is_phishing=class_res.is_phishing,
                    duration_ms=duration
                )
            except Exception as e:
                logger.exception("Spam save failed for email %s", email_id)
                duration = (time.perf_counter() - start_time) * 1000.0
                return AnalysisResult(
                    email_id=email_id,
                    success=False,
                    stages_completed=stages_completed,
                    errors={"spam_save": str(e)},
                    duration_ms=duration
                )

        # 4. Deep pass: Summarization & Extraction (Mistral 7B)
        summary = ""
        action_items = []
        extracted_dates = []
        extracted_entities = {}
        
        # Summarize
        try:
            summary = await self.summarization_service.summarize_email(
                subject=email.subject,
                sender=f"{email.sender_name} <{email.sender_email}>",
                body=email.body_text
            )
            stages_completed.append("summarization")
        except Exception as e:
            logger.warning("Summarization failed for email %s", email_id, exc_info=True)
            errors["summarization"] = str(e)
            
        # Extract
        try:
            extract_res = await self.extraction_service.extract_email(
                subject=email.subject,
                sender=f"{email.sender_name} <{email.sender_email}>",
                body=email.body_text
            )
            # Map action items
            action_items = [
                ActionItem(
                    task=item.task,
                    deadline=item.deadline,
                    priority=item.priority
                ) for item in extract_res.action_items
            ]
            
            # Gather extracted dates
            for appt in extract_res.appointments:
                if appt.date:
                    extracted_dates.append(ExtractedDate(date=appt.date, context=f"Appointment: {appt.title}"))
            for comm in extract_res.commitments:
                if comm.due_date:
                    extracted_dates.append(ExtractedDate(date=comm.due_date, context=f"Commitment: {comm.description}"))
            for item in extract_res.action_items:
                if item.deadline:
                    extracted_dates.append(ExtractedDate(date=item.deadline, context=f"Action Item: {item.task}"))
            
            # Gather entities
            extracted_entities = {
                "people": extract_res.entities.people,
                "organizations": extract_res.entities.organizations,
                "monetary_amounts": extract_res.entities.monetary_amounts,
            }
            
            stages_completed.append("extraction")
        except Exception as e:
            logger.warning("Extraction failed for email %s", email_id, exc_info=True)
            errors["extraction"] = str(e)

        # 5. Priority Scoring (Business Logic)
        final_priority = class_res.priority_score
        try:
            dates_dict = [d.model_dump() for d in extracted_dates]
            final_priority = await PriorityScorer.calculate_score(
                session=session,
                email=email,
                category=class_res.category,
                base_ai_priority=class_res.priority_score,
                extracted_dates=dates_dict,
            )
            stages_completed.append("priority_score")
        except Exception as e:
            logger.warning("Priority score calculation failed for email %s", email_id, exc_info=True)
            errors["priority_score"] = str(e)

        # 6. Save Complete Analysis
        try:
            analysis_data = AnalysisCreate(
                email_id=email_id,
                is_pending=False,
                category=class_res.category,
                priority_score=final_priority,
                spam_score=class_res.spam_score,
                is_phishing=class_res.is_phishing,
                summary=summary,
                action_items=action_items,
                extracted_dates=extracted_dates,
                extracted_entities=extracted_entities,
                suggested_action=class_res.suggested_action,
                sentiment="neutral",
                model_name=self.summarization_service.model,
                prompt_version=settings.PROMPT_VERSION,
                confidence=class_res.confidence,
            )
            await self.analysis_repo.save_analysis(session, analysis_data)
            await self.email_repo.mark_analyzed(session, email_id)
            stages_completed.append("save")
        except Exception as e:
            logger.exception("Failed to save analysis for email %s", email_id)
            duration = (time.perf_counter() - start_time) * 1000.0
            return AnalysisResult(
                email_id=email_id,
                success=False,
                stages_completed=stages_completed,
                errors={"save": str(e)},
                duration_ms=duration
            )

        # 7. Thread-level Aggregation (Summarize thread if all messages in it are analyzed)
        if email.thread_id:
            try:
                thread_emails = await self.email_repo.get_by_thread(session, email.thread_id)
                if thread_emails and all(e.is_analyzed for e in thread_emails):
                    # Convert ORM Emails to DTO EmailMessages
                    dto_messages = [self.email_repo.email_to_message(e) for e in thread_emails]
                    
                    thread_summary = await self.summarization_service.summarize_thread(dto_messages)
                    
                    from app.models.thread import Thread
                    thread = await session.get(Thread, email.thread_id)
                    if thread:
                        thread.summary = thread_summary
                        await session.flush()
                        stages_completed.append("thread_summary")
            except Exception as e:
                logger.warning("Thread summarization failed for thread %s", email.thread_id, exc_info=True)
                errors["thread_summary"] = str(e)

        # 8. Emit WebSocket Event
        try:
            from app.services.websocket import manager
            await manager.broadcast({"type": "analysis_complete", "email_id": email_id})
            stages_completed.append("websocket_emit")
        except Exception as e:
            logger.warning("WebSocket emit failed for email %s", email_id, exc_info=True)
            errors["websocket"] = str(e)

        duration = (time.perf_counter() - start_time) * 1000.0
        return AnalysisResult(
            email_id=email_id,
            success=True,
            stages_completed=stages_completed,
            errors=errors,
            category=class_res.category,
            priority_score=final_priority,
            spam_score=class_res.spam_score,
            is_spam=False,
            is_phishing=class_res.is_phishing,
            duration_ms=duration
        )
