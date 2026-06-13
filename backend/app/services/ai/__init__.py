"""AI service exports."""

from app.services.ai.classification import ClassificationService
from app.services.ai.client import (
    OllamaClient,
    OllamaClientError,
    OllamaModelUnavailableError,
)
from app.services.ai.embedding import EmbeddingService
from app.services.ai.extraction import ExtractionService
from app.services.ai.mock_client import MockOllamaClient
from app.services.ai.schemas import (
    MVP_CATEGORIES,
    Appointment,
    ClassificationResult,
    Commitment,
    ExtractedActionItem,
    ExtractionResult,
    HeaderSignal,
    LLMSpamSignal,
    NamedEntities,
    SpamDetectionResult,
    URLSignal,
)
from app.services.ai.spam import SpamDetectionService
from app.services.ai.summarization import SummarizationService

__all__ = [
    "MVP_CATEGORIES",
    "Appointment",
    "ClassificationResult",
    "ClassificationService",
    "Commitment",
    "EmbeddingService",
    "ExtractedActionItem",
    "ExtractionService",
    "ExtractionResult",
    "HeaderSignal",
    "LLMSpamSignal",
    "MockOllamaClient",
    "NamedEntities",
    "OllamaClient",
    "OllamaClientError",
    "OllamaModelUnavailableError",
    "SpamDetectionResult",
    "SpamDetectionService",
    "SummarizationService",
    "URLSignal",
]
