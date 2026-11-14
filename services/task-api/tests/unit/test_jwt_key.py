"""Faz 13a: JWT anahtari - env > dosya > uret."""

import pytest

from app.core import jwt_key


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(jwt_key, "KEY_FILE", tmp_path / ".jwt_secret")
    monkeypatch.setattr(jwt_key.settings, "jwt_secret_key", None)
    jwt_key.get_jwt_secret.cache_clear()
    yield
    jwt_key.get_jwt_secret.cache_clear()


def test_generates_file_and_is_stable():
    first = jwt_key.get_jwt_secret()
    assert len(first) >= 40
    assert jwt_key.KEY_FILE.read_text(encoding="utf-8").strip() == first
    jwt_key.get_jwt_secret.cache_clear()
    assert jwt_key.get_jwt_secret() == first


def test_env_setting_wins_over_file(monkeypatch):
    jwt_key.KEY_FILE.write_text("dosyadaki", encoding="utf-8")
    monkeypatch.setattr(jwt_key.settings, "jwt_secret_key", "ortamdaki")
    assert jwt_key.get_jwt_secret() == "ortamdaki"
    assert jwt_key.KEY_FILE.read_text(encoding="utf-8") == "dosyadaki"


def test_file_content_is_stripped():
    jwt_key.KEY_FILE.write_text("  anahtar-degeri \r\n\n", encoding="utf-8")
    assert jwt_key.get_jwt_secret() == "anahtar-degeri"


def test_no_hardcoded_default():
    from app.config import Settings

    assert Settings.model_fields["jwt_secret_key"].default is None
