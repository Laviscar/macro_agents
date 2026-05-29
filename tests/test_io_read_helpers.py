import pytest
from pydantic import BaseModel
from utils.io import read_model, read_models, write_model, write_models


class _Sample(BaseModel):
    id: str
    value: int


def test_read_model_round_trip(tmp_path):
    path = tmp_path / "item.json"
    write_model(path, _Sample(id="a", value=1))
    loaded = read_model(path, _Sample)
    assert loaded == _Sample(id="a", value=1)


def test_read_model_missing_returns_none(tmp_path):
    assert read_model(tmp_path / "nope.json", _Sample) is None


def test_read_models_round_trip(tmp_path):
    write_models(tmp_path / "dir", [_Sample(id="a", value=1), _Sample(id="b", value=2)])
    loaded = read_models(tmp_path / "dir", _Sample)
    assert {m.id for m in loaded} == {"a", "b"}
    assert len(loaded) == 2


def test_read_models_missing_dir_returns_empty(tmp_path):
    assert read_models(tmp_path / "missing", _Sample) == []


def test_read_models_skips_underscore_files(tmp_path):
    target = tmp_path / "dir"
    write_models(target, [_Sample(id="a", value=1)])
    (target / "_status.json").write_text('{"status": "no_alert"}', encoding="utf-8")
    loaded = read_models(target, _Sample)
    assert len(loaded) == 1
    assert loaded[0].id == "a"
