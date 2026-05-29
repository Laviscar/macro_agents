from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

_ModelT = TypeVar("_ModelT", bound=BaseModel)


def ensure_dir(path: str | Path) -> Path:
    resolved = Path(path)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def clear_json_files(directory: str | Path) -> Path:
    target_dir = ensure_dir(directory)
    for file_path in target_dir.glob("*.json"):
        file_path.unlink()
    return target_dir


def read_json(path: str | Path, default: Any | None = None) -> Any:
    file_path = Path(path)
    if not file_path.exists():
        return default
    return json.loads(file_path.read_text(encoding="utf-8"))


def write_json(path: str | Path, data: Any) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_model(path: str | Path, model: BaseModel) -> None:
    write_json(path, model.model_dump(mode="json"))


def write_models(directory: str | Path, models: list[BaseModel]) -> None:
    target_dir = ensure_dir(directory)
    for model in models:
        write_model(target_dir / f"{model.id}.json", model)


def read_model(path: str | Path, model_cls: type[_ModelT]) -> _ModelT | None:
    data = read_json(path)
    if data is None:
        return None
    return model_cls.model_validate(data)


def read_models(directory: str | Path, model_cls: type[_ModelT]) -> list[_ModelT]:
    target_dir = Path(directory)
    if not target_dir.exists():
        return []
    models: list[_ModelT] = []
    for file_path in sorted(target_dir.glob("*.json")):
        if file_path.name.startswith("_"):
            continue
        models.append(model_cls.model_validate(read_json(file_path)))
    return models
