"""
Ajanda yedegi (Faz 13a). Yalniz standart kutuphane.

Kullanim (repo kokunde):  uv run python scripts/backup.py [--dest KLASOR] [--if-missing-today]

Yedek kokunde (varsayilan %LOCALAPPDATA%\\Ajanda\\yedek) "YYYY-MM-DD_HHMM" klasoru uretir:
iki SQLite veritabani (cevrimici kopya), ekler (zip), anahtar dosyalari ve manifest.json.
Cikis kodu: 0 basarili, 2 yedek bozuk, 1 diger hata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import logging.handlers
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

NAME_RE = re.compile(r"\d{4}-\d{2}-\d{2}_\d{4}")
BOZUK_RE = re.compile(r"\d{4}-\d{2}-\d{2}_\d{4}_BOZUK")
BOZUK_KEEP_DAYS = 14
OFFSITE_FILES = ("task_management.db", "assistant.db", "attachments.zip", "manifest.json")
OFFSITE_KEEP = 4

DB_SOURCES = {
    "task_management.db": "services/task-api/task_management.db",
    "assistant.db": "services/assistant-service/assistant.db",
}
FILE_SOURCES = {
    "task-api.secret_key": "services/task-api/.secret_key",
    "assistant.secret_key": "services/assistant-service/.secret_key",
    "task-api.jwt_secret": "services/task-api/.jwt_secret",
    "task-api.env": "services/task-api/.env",
    "assistant.env": "services/assistant-service/.env",
}
ATTACHMENTS_DIR = "services/task-api/data/attachments"
ALEMBIC_KEYS = {"task_management.db": "task-api", "assistant.db": "assistant"}

log = logging.getLogger("ajanda.yedek")


def default_dest() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Ajanda" / "yedek"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _db_check(path: Path) -> tuple[str | None, str | None]:
    """(alembic_revision, hata). Hata yoksa None."""
    try:
        con = sqlite3.connect(path)
        try:
            res = con.execute("PRAGMA integrity_check").fetchone()
            if not res or res[0] != "ok":
                return None, f"integrity_check basarisiz: {res[0] if res else '?'}"
            try:
                row = con.execute("SELECT version_num FROM alembic_version").fetchone()
            except sqlite3.DatabaseError:
                return None, "alembic_version okunamadi"
            return (row[0] if row else None), None
        finally:
            con.close()
    except sqlite3.DatabaseError as e:
        return None, f"veritabani acilamadi: {e}"


def _backup_db(src: Path, dst: Path) -> None:
    s = sqlite3.connect(f"{src.resolve().as_uri()}?mode=ro", uri=True)
    d = sqlite3.connect(dst)
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()


def _git_commit(repo: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode != 0:
            return None
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def verify(folder: Path) -> list[str]:
    """Yedek klasorunu dogrular: DB butunlugu + (manifest varsa) sha256. Hata listesi."""
    errors: list[str] = []
    for db in sorted(folder.glob("*.db")):
        _, err = _db_check(db)
        if err:
            errors.append(f"{db.name}: {err}")
    manifest = folder / "manifest.json"
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            for f in data.get("files", []):
                p = folder / f["name"]
                if not p.exists():
                    errors.append(f"{f['name']}: dosya yok")
                elif sha256_of(p) != f["sha256"]:
                    errors.append(f"{f['name']}: sha256 uyusmuyor")
        except (OSError, ValueError, KeyError) as e:
            errors.append(f"manifest okunamadi: {e}")
    return errors


def make_backup(repo: Path, dest_root: Path, now: datetime) -> Path:
    name = now.strftime("%Y-%m-%d_%H%M")
    final = dest_root / name
    if final.exists() or (dest_root / (name + "_BOZUK")).exists():
        raise FileExistsError(f"{name} zaten var")
    work = dest_root / (name + ".partial")
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    missing: list[str] = []
    errors: list[str] = []
    alembic: dict[str, str | None] = {"task-api": None, "assistant": None}
    try:
        for out_name, rel in DB_SOURCES.items():
            src = repo / rel
            if not src.exists():
                missing.append(rel)
                continue
            try:
                _backup_db(src, work / out_name)
            except sqlite3.DatabaseError as e:
                errors.append(f"{out_name}: kopyalanamadi: {e}")
                continue
            rev, err = _db_check(work / out_name)
            alembic[ALEMBIC_KEYS[out_name]] = rev
            if err:
                errors.append(f"{out_name}: {err}")
        att = repo / ATTACHMENTS_DIR
        if att.is_dir():
            with zipfile.ZipFile(work / "attachments.zip", "w", zipfile.ZIP_DEFLATED) as z:
                for p in sorted(att.rglob("*")):
                    if p.is_file():
                        z.write(p, p.relative_to(att).as_posix())
        else:
            missing.append(ATTACHMENTS_DIR)
        for out_name, rel in FILE_SOURCES.items():
            src = repo / rel
            if src.exists():
                shutil.copy2(src, work / out_name)
            elif not out_name.endswith(".env"):
                missing.append(rel)
        files = [
            {"name": p.name, "size": p.stat().st_size, "sha256": sha256_of(p)}
            for p in sorted(work.iterdir())
            if p.is_file()
        ]
        manifest = {
            "created_at": now.isoformat(timespec="seconds"),
            "files": files,
            "alembic": alembic,
            "git_commit": _git_commit(repo),
            "missing": missing,
            "ok": not errors,
            "errors": errors,
        }
        (work / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise
    target = final if not errors else dest_root / (name + "_BOZUK")
    work.rename(target)
    return target


def _date_of(name: str) -> date:
    return datetime.strptime(name[:10], "%Y-%m-%d").date()


def plan_rotation(names: list[str], today: date) -> list[str]:
    """Silinecek klasor adlari (saf). Yalniz desene uyan adlar donebilir."""
    valid = sorted((n for n in names if NAME_RE.fullmatch(n)), reverse=True)  # yeni -> eski
    keep: set[str] = set()

    def newest(pred) -> None:
        for n in valid:
            if pred(_date_of(n)):
                keep.add(n)
                return

    for i in range(7):
        d = today - timedelta(days=i)
        newest(lambda x, d=d: x == d)
    for i in range(4):
        w = (today - timedelta(weeks=i)).isocalendar()
        newest(lambda x, w=w: tuple(x.isocalendar()[:2]) == tuple(w[:2]))
    y, m = today.year, today.month
    for _ in range(3):
        newest(lambda x, y=y, m=m: (x.year, x.month) == (y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    out = [n for n in valid if n not in keep]
    for n in names:
        if BOZUK_RE.fullmatch(n) and (today - _date_of(n)).days > BOZUK_KEEP_DAYS:
            out.append(n)
    return sorted(out)


def _rmtree_child(root: Path, name: str) -> None:
    target = (root / name).resolve()
    if target.parent != root.resolve() or not (
        NAME_RE.fullmatch(name) or BOZUK_RE.fullmatch(name)
    ):
        raise ValueError(f"guvenli olmayan silme reddedildi: {name}")
    shutil.rmtree(target)


def copy_offsite(folder: Path, onedrive_root: Path, now: datetime) -> Path | None:
    """OneDrive'a haftada bir, yalniz DB + ekler + manifest (anahtar/.env ASLA)."""
    root = onedrive_root / "Ajanda-yedek"
    week = tuple(now.isocalendar()[:2])
    if root.is_dir():
        for p in root.iterdir():
            if (
                p.is_dir()
                and NAME_RE.fullmatch(p.name)
                and tuple(_date_of(p.name).isocalendar()[:2]) == week
            ):
                return None
    dst = root / folder.name
    dst.mkdir(parents=True, exist_ok=True)
    for fname in OFFSITE_FILES:
        src = folder / fname
        if src.exists():
            shutil.copy2(src, dst / fname)
    kept = sorted(
        (p.name for p in root.iterdir() if p.is_dir() and NAME_RE.fullmatch(p.name)),
        reverse=True,
    )
    for old in kept[OFFSITE_KEEP:]:
        _rmtree_child(root, old)
    return dst


def _setup_log(dest_root: Path) -> None:
    dest_root.mkdir(parents=True, exist_ok=True)
    h = logging.handlers.RotatingFileHandler(
        dest_root / "backup.log", maxBytes=1_000_000, backupCount=1, encoding="utf-8"
    )
    h.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%S")
    )
    for old in list(log.handlers):
        old.close()
    log.handlers = [h, logging.StreamHandler(sys.stdout)]
    log.setLevel(logging.INFO)
    log.propagate = False


def _valid_today(dest_root: Path, today: date) -> bool:
    if not dest_root.is_dir():
        return False
    prefix = today.strftime("%Y-%m-%d") + "_"
    for p in dest_root.iterdir():
        if p.is_dir() and NAME_RE.fullmatch(p.name) and p.name.startswith(prefix):
            try:
                m = json.loads((p / "manifest.json").read_text(encoding="utf-8"))
                if m.get("ok"):
                    return True
            except (OSError, ValueError):
                continue
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ajanda yedegi")
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--dest", default=None)
    ap.add_argument("--onedrive", default=None, help="bos string: kapat (testler icin)")
    ap.add_argument("--if-missing-today", action="store_true")
    ap.add_argument("--now", default=None, help="testler icin ISO zaman")
    a = ap.parse_args(argv)
    repo = Path(a.repo)
    dest_root = Path(a.dest) if a.dest else default_dest()
    now = datetime.fromisoformat(a.now) if a.now else datetime.now()
    try:
        _setup_log(dest_root)
        if a.if_missing_today and _valid_today(dest_root, now.date()):
            log.info("Bugunun yedegi var, atlandi")
            return 0
        folder = make_backup(repo, dest_root, now)
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if not manifest["ok"]:
            log.error("Yedek BOZUK: %s -> %s", folder.name, "; ".join(manifest["errors"]))
            return 2
        log.info("Yedek alindi: %s (%d dosya)", folder.name, len(manifest["files"]))
        names = [p.name for p in dest_root.iterdir() if p.is_dir()]
        for old in plan_rotation(names, now.date()):
            _rmtree_child(dest_root, old)
            log.info("Dondurme: silindi %s", old)
        onedrive = os.environ.get("OneDrive") if a.onedrive is None else a.onedrive
        if onedrive and Path(onedrive).is_dir():
            out = copy_offsite(folder, Path(onedrive), now)
            log.info("OneDrive: %s", f"kopyalandi {out.name}" if out else "bu hafta zaten var")
        else:
            log.info("OneDrive yok, atlandi")
        return 0
    except Exception as e:  # noqa: BLE001
        try:
            log.error("Yedek hatasi: %s", e)
        except Exception:  # noqa: BLE001
            print(f"Yedek hatasi: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
