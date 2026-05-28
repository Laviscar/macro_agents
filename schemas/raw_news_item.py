from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RawNewsItem(BaseModel):
    source_type: str
    source_name: str
    external_id: str | None = None
    url: str
    title: str
    summary: str = ""
    published_at: str | None = None
    fetched_at: str
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    def build_dedupe_key(self) -> str:
        return "|".join(
            [
                self.source_name,
                self.external_id or "",
                self.url,
                self.published_at or "",
                self.title,
            ]
        )

    def to_pipeline_input(self) -> dict[str, Any]:
        payload = dict(self.raw_payload)
        payload.setdefault("source", self.source_name)
        payload.setdefault("url", self.url)
        payload.setdefault("title", self.title)
        payload.setdefault("summary", self.summary or self.title)
        payload.setdefault("timestamp", self.published_at or self.fetched_at)
        return payload
