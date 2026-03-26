from __future__ import annotations

from pathlib import Path

import yaml


class KnowledgeLoader:
    def __init__(self, registry_path: str) -> None:
        self.registry_path = Path(registry_path)
        self.project_root = self.registry_path.parent.parent
        self.registry = self._load_registry()

    def _load_registry(self) -> dict:
        return yaml.safe_load(self.registry_path.read_text(encoding="utf-8")) or {}

    def load_for_agent(self, agent: str, task: str | None = None) -> list[dict]:
        documents = self.registry.get("documents", [])
        loaded: list[dict] = []

        for doc in documents:
            doc_agent = doc.get("agent")
            if doc_agent not in {"shared", agent}:
                continue

            load_mode = doc.get("load_mode")
            if load_mode == "always":
                loaded.append(self._materialize_document(doc))
                continue

            if load_mode == "by_task" and task and task in doc.get("trigger_tasks", []):
                loaded.append(self._materialize_document(doc))

        return sorted(loaded, key=lambda item: item.get("priority", 0), reverse=True)

    def load_context(self, agent: str, tasks: list[str] | None = None) -> dict:
        task_names = tasks or []
        return {
            "always": self.load_for_agent(agent),
            "tasks": {task: self._load_task_documents(agent, task) for task in task_names},
        }

    def _materialize_document(self, doc: dict) -> dict:
        path = self.project_root / doc["path"]
        return {
            **doc,
            "resolved_path": str(path),
            "content": path.read_text(encoding="utf-8"),
        }

    def _load_task_documents(self, agent: str, task: str) -> list[dict]:
        documents = self.registry.get("documents", [])
        loaded: list[dict] = []

        for doc in documents:
            if doc.get("agent") != agent:
                continue
            if doc.get("load_mode") == "by_task" and task in doc.get("trigger_tasks", []):
                loaded.append(self._materialize_document(doc))

        return sorted(loaded, key=lambda item: item.get("priority", 0), reverse=True)
