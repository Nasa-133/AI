"""Sync natijasi hisobi: rad etilgan satrlar va batch identifikatori (sof mantiq)."""

from dataclasses import dataclass, field
from uuid import UUID, uuid5

MAX_REJECTION_SAMPLES = 50
_BATCH_NAMESPACE = UUID("6f1c2b0e-8b7a-4d0e-9a5c-2f1e3d4c5b6a")


def batch_id_for(sync_run_id: UUID, entity: str) -> UUID:
    """Deterministik: bir sync run qayta ishlansa ham batch ID o‘zgarmaydi (idempotentlik)."""
    return uuid5(_BATCH_NAMESPACE, f"{sync_run_id}:{entity}")


@dataclass(frozen=True, slots=True)
class Rejection:
    row_number: int
    source_id: str | None
    reason: str


@dataclass(slots=True)
class RejectionReport:
    count: int = 0
    samples: list[Rejection] = field(default_factory=list)

    def add(self, rejection: Rejection) -> None:
        self.count += 1
        if len(self.samples) < MAX_REJECTION_SAMPLES:
            self.samples.append(rejection)
