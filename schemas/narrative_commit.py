from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, model_validator


NarrativeType = Literal["main", "branch"]
CommitAction = Literal["update", "upgrade", "downgrade", "promote", "archive"]


class NarrativeCommit(BaseModel):
    id: str
    narrative_type: NarrativeType
    narrative_id: str
    source_evidence_ids: list[str]
    action: CommitAction
    summary: str
    field_changes: dict[str, Any]
    created_at: str

    @model_validator(mode="after")
    def validate_field_changes(self) -> "NarrativeCommit":
        if not self.field_changes:
            raise ValueError("NarrativeCommit.field_changes must not be empty.")
        return self
