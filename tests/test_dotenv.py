import os

import pytest

from utils.dotenv import load_dotenv


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Isolate: remove the vars these tests touch so os.environ leakage can't mask bugs.
    for var in ["DOTENV_TEST_A", "DOTENV_TEST_B", "DOTENV_TEST_QUOTED", "DOTENV_TEST_EXPORT", "DOTENV_TEST_HASH"]:
        monkeypatch.delenv(var, raising=False)
    yield


def _write(tmp_path, text: str):
    p = tmp_path / ".env"
    p.write_text(text, encoding="utf-8")
    return p


def test_loads_key_value_into_environ(tmp_path):
    path = _write(tmp_path, "DOTENV_TEST_A=hello\nDOTENV_TEST_B=world\n")
    parsed = load_dotenv(path)
    assert parsed == {"DOTENV_TEST_A": "hello", "DOTENV_TEST_B": "world"}
    assert os.environ["DOTENV_TEST_A"] == "hello"
    assert os.environ["DOTENV_TEST_B"] == "world"


def test_ignores_comments_and_blank_lines(tmp_path):
    path = _write(tmp_path, "# a comment\n\n   \nDOTENV_TEST_A=v\n# trailing comment\n")
    parsed = load_dotenv(path)
    assert parsed == {"DOTENV_TEST_A": "v"}


def test_does_not_override_existing_env_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("DOTENV_TEST_A", "from_shell")
    path = _write(tmp_path, "DOTENV_TEST_A=from_file\n")
    parsed = load_dotenv(path)
    # parsed reflects the file, but the existing env var wins
    assert parsed["DOTENV_TEST_A"] == "from_file"
    assert os.environ["DOTENV_TEST_A"] == "from_shell"


def test_override_true_replaces_existing(tmp_path, monkeypatch):
    monkeypatch.setenv("DOTENV_TEST_A", "from_shell")
    path = _write(tmp_path, "DOTENV_TEST_A=from_file\n")
    load_dotenv(path, override=True)
    assert os.environ["DOTENV_TEST_A"] == "from_file"


def test_strips_surrounding_quotes(tmp_path):
    path = _write(tmp_path, 'DOTENV_TEST_QUOTED="quoted value"\n')
    parsed = load_dotenv(path)
    assert parsed["DOTENV_TEST_QUOTED"] == "quoted value"


def test_supports_export_prefix(tmp_path):
    path = _write(tmp_path, "export DOTENV_TEST_EXPORT=xyz\n")
    parsed = load_dotenv(path)
    assert parsed["DOTENV_TEST_EXPORT"] == "xyz"
    assert os.environ["DOTENV_TEST_EXPORT"] == "xyz"


def test_preserves_hash_inside_value(tmp_path):
    path = _write(tmp_path, "DOTENV_TEST_HASH=ab#cd\n")
    parsed = load_dotenv(path)
    assert parsed["DOTENV_TEST_HASH"] == "ab#cd"


def test_missing_file_returns_empty_and_noop(tmp_path):
    parsed = load_dotenv(tmp_path / "nope.env")
    assert parsed == {}
