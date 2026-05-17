"""Data classes and enums for Memory Tree Pipeline."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import json
import hashlib


class LifecycleStatus(str, Enum):
    PENDING_EXTRACTION = "pending_extraction"
    ADMITTED = "admitted"
    BUFFERED = "buffered"
    SEALED = "sealed"
    DROPPED = "dropped"


class JobKind(str, Enum):
    EXTRACT_CHUNK = "extract_chunk"
    APPEND_BUFFER = "append_buffer"
    SEAL = "seal"
    TOPIC_ROUTE = "topic_route"
    DIGEST_DAILY = "digest_daily"
    FLUSH_STALE = "flush_stale"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    DEAD = "dead"


class TreeType(str, Enum):
    SOURCE = "source"
    TOPIC = "topic"
    GLOBAL = "global"


class EntityType(str, Enum):
    PERSON = "person"
    ORG = "org"
    PROJECT = "project"
    CONCEPT = "concept"
    PLACE = "place"
    EVENT = "event"


@dataclass
class Chunk:
    chunk_id: str
    source_id: str
    source_path: Optional[str]
    content: str
    token_count: int
    lifecycle_status: LifecycleStatus = LifecycleStatus.PENDING_EXTRACTION

    @staticmethod
    def make_id(content: str) -> str:
        normalized = " ".join(content.strip().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


@dataclass
class Score:
    chunk_id: str
    fast_score: float = 0.0
    llm_score: Optional[float] = None
    entity_count: int = 0
    info_density: float = 0.0
    recency_score: float = 0.0


@dataclass
class Entity:
    name: str
    entity_type: EntityType
    mention_count: int = 1
    hotness: float = 0.0


@dataclass
class Relation:
    subject: str
    predicate: str
    object: str
    chunk_id: Optional[str] = None
    confidence: float = 1.0


@dataclass
class Job:
    kind: JobKind
    payload: dict = field(default_factory=dict)
    dedupe_key: Optional[str] = None
    job_id: Optional[int] = None
    status: JobStatus = JobStatus.PENDING
    attempts: int = 0

    @property
    def payload_json(self) -> str:
        return json.dumps(self.payload)


@dataclass
class Document:
    """A document from any source, before chunking."""
    source_id: str
    source_path: str
    content: str
    title: Optional[str] = None
    metadata: dict = field(default_factory=dict)
