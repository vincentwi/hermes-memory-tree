"""Base class for all source providers."""
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime
from models import Document


class SourceProvider(ABC):
    """Abstract base for a source that can provide documents."""

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Unique identifier for this source."""
        ...

    @abstractmethod
    def fetch_changes(self, since: Optional[datetime] = None) -> List[Document]:
        """Fetch documents changed since the given timestamp.
        If since is None, fetch all documents.
        """
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the source is accessible."""
        ...
