"""LLM provider interface and implementations."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.schemas.invoice import InvoiceData


class LLMProvider(ABC):
    """Provider-independent LLM interface for structured extraction."""

    @abstractmethod
    def extract(self, text: str) -> InvoiceData:
        raise NotImplementedError


def get_llm_provider(**kwargs: Any) -> LLMProvider:
    from app.core.config import settings

    provider_name = kwargs.get("provider", settings.llm_provider)
    if provider_name == "mock":
        from .mock import MockLLMProvider

        return MockLLMProvider()
    # Placeholder for real providers; default to mock for now.
    from .mock import MockLLMProvider

    return MockLLMProvider()

