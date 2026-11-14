"""Windows bildirimi: scripts/toast.ps1 (PowerShell WinRT). Windows disinda no-op."""

import asyncio
import sys
from pathlib import Path

TOAST_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "toast.ps1"
TIMEOUT = 15.0


class ToastError(Exception):
    pass


async def send_toast(title: str, body: str) -> None:
    if sys.platform != "win32":
        return
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(TOAST_SCRIPT),
            "-Title",
            title,
            "-Body",
            body,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError as e:
        raise ToastError(f"PowerShell başlatılamadı ({type(e).__name__})") from None
    try:
        code = await asyncio.wait_for(proc.wait(), TIMEOUT)
    except TimeoutError:
        proc.kill()
        raise ToastError("Windows bildirimi zaman aşımına uğradı") from None
    if code != 0:
        raise ToastError(f"Windows bildirimi gösterilemedi (kod {code})")
