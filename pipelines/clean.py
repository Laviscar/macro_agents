from __future__ import annotations

from agents.news_sorter import NewsSorterAgent
from schemas.resource_card import ResourceCard


def process_raw_items(raw_items: list[dict], agent: NewsSorterAgent) -> list[ResourceCard]:
    return [agent.process(item) for item in raw_items]
