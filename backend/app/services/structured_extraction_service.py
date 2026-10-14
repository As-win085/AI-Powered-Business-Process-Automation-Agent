"""Structured extraction service for invoices."""
from __future__ import annotations

from pydantic import ValidationError

from app.integrations.llm import LLMProvider, get_llm_provider
from app.schemas.invoice import InvoiceData


SYSTEM_PROMPT = (
    "Return null rather than guess. Never compute invoice/subtotal/tax/total amounts. "
    "Do not fabricate supplier/customer IDs. Be conservative with uncertain fields."
)


class StructuredExtractionError(Exception):
    pass


class StructuredExtractionService:
    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider or get_llm_provider()

    def extract(self, text: str) -> InvoiceData:
        try:
            result = self.provider.extract(text=text)
        except Exception as exc:
            raise StructuredExtractionError(str(exc)) from exc

        try:
            if isinstance(result, InvoiceData):
                return result
            if isinstance(result, dict):
                return InvoiceData.model_validate(result)
            return InvoiceData()
        except ValidationError as exc:
            raise StructuredExtractionError(str(exc)) from exc

