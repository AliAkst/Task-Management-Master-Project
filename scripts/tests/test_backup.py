"""scripts/backup.py testleri (Faz 13a) - yalniz stdlib + pytest."""

import json
import re
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import backup  # noqa: E402


def _make_db(path: Path, rev: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE alembic_version (version_num TEXT)")
    con.execute("INSERT INTO alembic_version VALUES (?)", (rev,))
    con.execute("CREATE TABLE t (x INTEGER)")
    con.execute("INSERT INTO t VALUES (42)")
    con.commit()
    con.close()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    _make_db(r / "services/task-api/task_management.db", "aaa111")
    _make_db(r / "services/assistant-service/assistant.db", "bbb222")
    (r / "services/task-api/.secret_key").write_text("gizli-1")
    (r / "services/assistant-service/.secret_key").write_text("gizli-2")
    (r / "services/task-api/.jwt_secret").write_text("gizli-3")
    return r


NOW = datetime(2026, 11, 14, 13, 0)


def _main(repo, dest, *extra, now="2026-11-14T13:00"):
    return backup.main(
        ["--repo", str(repo), "--dest", str(dest), "--onedrive", "", "--now", now, *extra]
    )


def test_make_backup_creates_folder_manifest_and_hashes(repo, tmp_path):
    folder = backup.make_backup(repo, tmp_path / "yedek", NOW)
    assert folder.name == "2026-11-14_1300"
    m = json.loads((folder / "manifest.json").read_text())
    assert m["ok"] is True and m["errors"] == []
    assert m["alembic"] == {"task-api": "aaa111", "assistant": "bbb222"}
    names = {f["name"] for f in m["files"]}
    assert {
        "task_management.db",
        "assistant.db",
        "task-api.secret_key",
        "assistant.secret_key",
        "task-api.jwt_secret",
    } <= names
    assert "attachments.zip" not in names
    assert any("attachments" in x for x in m["missing"])
    assert all(len(f["sha256"]) == 64 for f in m["files"])
    con = sqlite3.connect(folder / "task_management.db")
    assert con.execute("SELECT x FROM t").fetchone() == (42,)
    con.close()


def test_verify_clean_backup_has_no_errors(repo, tmp_path):
    folder = backup.make_backup(repo, tmp_path / "yedek", NOW)
    assert backup.verify(folder) == []


def test_verify_detects_tampered_file(repo, tmp_path):
    folder = backup.make_backup(repo, tmp_path / "yedek", NOW)
    (folder / "task-api.secret_key").write_text("degisti")
    assert backup.verify(folder)


def test_corrupt_db_marks_folder_bozuk_and_skips_rotation(repo, tmp_path):
    dest = tmp_path / "yedek"
    (repo / "services/task-api/task_management.db").write_bytes(b"\x00rastgele" * 500)
    folder = backup.make_backup(repo, dest, NOW)
    assert folder.name == "2026-11-14_1300_BOZUK"
    m = json.loads((folder / "manifest.json").read_text())
    assert m["ok"] is False and m["errors"]
    old = dest / "2026-01-01_1300"
    old.mkdir(parents=True)
    assert _main(repo, dest, now="2026-11-15T13:00") == 2
    assert old.exists()


def test_rotation_table():
    today = date(2026, 11, 14)
    names = []
    for i in range(40):
        d = date.fromordinal(today.toordinal() - i).strftime("%Y-%m-%d")
        names += [d + "_1300", d + "_0900"]
    names += [
        "pre-restore_20260101_120000",
        "notlarim",
        "2026-11-14_1300_BOZUK",
        "2026-10-01_1300_BOZUK",
        "backup.log",
    ]
    out = backup.plan_rotation(names, today)
    assert "2026-11-14_0900" in out and "2026-11-14_1300" not in out
    for i in range(7):
        d = date.fromordinal(today.toordinal() - i).strftime("%Y-%m-%d")
        assert d + "_1300" not in out
    for safe in ("pre-restore_20260101_120000", "notlarim", "backup.log"):
        assert safe not in out
    assert "2026-10-01_1300_BOZUK" in out
    assert "2026-11-14_1300_BOZUK" not in out
    for n in out:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d{4}(_BOZUK)?", n)


def test_rotation_keeps_weekly_and_monthly():
    today = date(2026, 11, 14)  # Cumartesi, ISO hafta 46
    names = [
        "2026-11-14_1300",
        "2026-11-08_1300",
        "2026-11-01_1300",
        "2026-10-25_1300",
        "2026-10-18_1300",
        "2026-10-03_1300",
        "2026-09-20_1300",
        "2026-09-01_1300",
        "2026-08-15_1300",
        "2026-07-01_1300",
    ]
    out = set(backup.plan_rotation(names, today))
    # son 7 gun + 4 hafta (h46, h45, h44, h43) + ayin en yenisi (Kas, Eki, Eyl)
    for kept in ("2026-11-14_1300", "2026-11-08_1300", "2026-11-01_1300", "2026-10-25_1300"):
        assert kept not in out
    assert "2026-09-20_1300" not in out  # Eylul'un en yenisi
    # 18 Eki: ne son 7 gun, ne haftanin ne ayin en yenisi -> silinir
    assert "2026-10-18_1300" in out
    # 3 aydan eski
    assert "2026-08-15_1300" in out and "2026-07-01_1300" in out


def test_offsite_copy_has_no_keys_and_one_per_week(repo, tmp_path):
    (repo / "services/task-api/.env").write_text("X=1")
    (repo / "services/task-api/data/attachments").mkdir(parents=True)
    (repo / "services/task-api/data/attachments/a.txt").write_text("ek")
    folder = backup.make_backup(repo, tmp_path / "yedek", NOW)
    assert (folder / "task-api.env").exists() and (folder / "attachments.zip").exists()
    onedrive = tmp_path / "OneDrive"
    onedrive.mkdir()
    out = backup.copy_offsite(folder, onedrive, NOW)
    assert out is not None
    files = {p.name for p in out.iterdir()}
    assert files == {"task_management.db", "assistant.db", "attachments.zip", "manifest.json"}
    for p in out.iterdir():
        assert "secret" not in p.name and "jwt" not in p.name and "env" not in p.name
    folder2 = tmp_path / "yedek" / "2026-11-15_1300"
    folder2.mkdir()
    assert backup.copy_offsite(folder2, onedrive, datetime(2026, 11, 15, 13, 0)) is None


def test_if_missing_today_is_idempotent(repo, tmp_path):
    dest = tmp_path / "yedek"
    assert _main(repo, dest, "--if-missing-today") == 0
    first = sorted(p.name for p in dest.iterdir() if p.is_dir())
    assert len(first) == 1
    assert _main(repo, dest, "--if-missing-today", now="2026-11-14T18:30") == 0
    assert sorted(p.name for p in dest.iterdir() if p.is_dir()) == first


def test_rotation_via_main_never_touches_pre_restore(repo, tmp_path):
    dest = tmp_path / "yedek"
    (dest / "pre-restore_20250101_000000").mkdir(parents=True)
    (dest / "2020-01-01_1300").mkdir()
    assert _main(repo, dest) == 0
    assert (dest / "pre-restore_20250101_000000").exists()
    assert not (dest / "2020-01-01_1300").exists()
