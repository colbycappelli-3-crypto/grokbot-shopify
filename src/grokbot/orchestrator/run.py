"""In-memory state for one offline opportunity run."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..audit.log import AuditLog
from ..evidence.ledger import EvidenceLedger
from ..phase import PHASE
from ..state.project_state import ProjectState
from ..workflows.loader import WorkflowSpec


@dataclass
class OpportunityRun:
    project: ProjectState
    workflow: WorkflowSpec
    objective: str
    fixture: Optional[dict]
    gate_config: dict
    jobs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, dict] = field(default_factory=dict)
    results: Dict[str, Any] = field(default_factory=dict)
    evidence: EvidenceLedger = field(default_factory=EvidenceLedger)
    audit: AuditLog = field(default_factory=AuditLog)
    dossier: Optional[dict] = None
    review_packet: Optional[dict] = None
    gate_results: List[dict] = field(default_factory=list)
    stopped: bool = False
    stop_reason: Optional[str] = None
    stop_details: dict = field(default_factory=dict)
    external_actions_performed: List[dict] = field(default_factory=list)
    pending_approval_action: Optional[str] = None
    review_item_id: Optional[str] = None
    phase: str = PHASE

    def stage_status(self, stage_id: str) -> str:
        return self.project.stage(stage_id)["status"]
