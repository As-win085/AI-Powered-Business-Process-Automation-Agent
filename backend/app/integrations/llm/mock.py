"""Mock LLM provider implementation."""
from __future__ import annotations

from app.integrations.llm.base import LLMProvider
from app.schemas.invoice import InvoiceData


class MockLLMProvider(LLMProvider):
    """Deterministic mock provider for tests and offline use."""

    def extract(self, text: str) -> InvoiceData:
        return InvoiceData()

