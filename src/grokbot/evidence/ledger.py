"""Evidence ledger.

Phase 2 evidence is fixture- or test-supplied. Records must be explicitly
marked MOCK or TEST, and verified records require a source reference. The
ledger does not fetch anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from ..validation import validate

ALLOWED_SOURCE_TYPES = {"mock", "test", "operator_supplied", "unknown"}
VERIFICATION_STATUSES = {"verified", "unverified", "unknown"}


class EvidenceError(ValueError):
    pass


@dataclass
class EvidenceRecord:
    evidence_id: str
    source_type: str
    source_reference: str
    claim_supported: str
    collected_by: str
    verification_status: str
    retrieved_at: Optional[str] = None
    freshness: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> dict:
        data = {
            "evidence_id": self.evidence_id,
            "source_type": self.source_type,
            "source_reference": self.source_reference,
            "claim_supported": self.claim_supported,
            "collected_by": self.collected_by,
            "verification_status": self.verification_status,
            "notes": self.notes,
        }
        if self.retrieved_at is not None:
            data["retrieved_at"] = self.retrieved_at
        if self.freshness is not None:
            data["freshness"] = self.freshness
        return data

    def check(self) -> None:
        validate(self.to_dict(), "evidence_record", source=f"evidence:{self.evidence_id}")
        if self.source_type not in ALLOWED_SOURCE_TYPES:
            raise EvidenceError(f"{self.evidence_id}: source_type '{self.source_type}' is not allowed.")
        if self.verification_status not in VERIFICATION_STATUSES:
            raise EvidenceError(f"{self.evidence_id}: invalid verification status.")
        if self.verification_status == "verified" and not self.source_reference.strip():
            raise EvidenceError(f"{self.evidence_id}: verified evidence requires a source reference.")
        lowered = self.source_reference.lower()
        if lowered.startswith("http://") or lowered.startswith("https://"):
            raise EvidenceError(
                f"{self.evidence_id}: live URLs are not evidence in Phase 2. Use a MOCK: reference."
            )
        blob = " ".join((self.source_reference, self.notes, self.claim_supported)).upper()
        if "MOCK" not in blob and "TEST" not in blob:
            raise EvidenceError(
                f"{self.evidence_id}: evidence must be explicitly marked MOCK or TEST."
            )


class EvidenceLedger:
    def __init__(self) -> None:
        self._records: Dict[str, EvidenceRecord] = {}

    def add(self, record: EvidenceRecord) -> EvidenceRecord:
        record.check()
        if record.evidence_id in self._records:
            raise EvidenceError(f"Duplicate evidence id: {record.evidence_id}")
        self._records[record.evidence_id] = record
        return record

    def get(self, evidence_id: str) -> Optional[EvidenceRecord]:
        return self._records.get(evidence_id)

    def __contains__(self, evidence_id: object) -> bool:
        return evidence_id in self._records

    def __len__(self) -> int:
        return len(self._records)

    def all(self) -> List[EvidenceRecord]:
        return list(self._records.values())

    def as_index(self) -> Dict[str, EvidenceRecord]:
        return dict(self._records)

    def to_list(self) -> List[dict]:
        return [record.to_dict() for record in self._records.values()]


def record_from_dict(data: dict, *, collected_by: Optional[str] = None) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=data["evidence_id"],
        source_type=data["source_type"],
        source_reference=data["source_reference"],
        claim_supported=data["claim_supported"],
        collected_by=collected_by or data["collected_by"],
        verification_status=data["verification_status"],
        retrieved_at=data.get("retrieved_at"),
        freshness=data.get("freshness"),
        notes=data.get("notes", ""),
    )
