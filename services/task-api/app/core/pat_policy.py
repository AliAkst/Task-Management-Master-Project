"""PAT (kisisel erisim jetonu) politika tablosu (Faz 13b) - tek kaynak."""

API_PREFIX = "/api/v1"

# Yontemden bagimsiz yasak yollar (onek eslemesi); tek istisna ALLOWED_EXACT
FORBIDDEN_PREFIXES: tuple[str, ...] = (
    f"{API_PREFIX}/auth",
    f"{API_PREFIX}/integrations",
    f"{API_PREFIX}/attachments",
)
ALLOWED_EXACT: frozenset[tuple[str, str]] = frozenset(
    {("GET", f"{API_PREFIX}/auth/me")}
)
# Yalniz okuyan POST'lar (read kapsami yeter)
READ_ONLY_POSTS: frozenset[str] = frozenset({f"{API_PREFIX}/cards/parse-title"})
READ_METHODS = frozenset({"GET", "HEAD"})
SETTINGS_PREFIX = f"{API_PREFIX}/settings"


def _norm(path: str) -> str:
    return path.rstrip("/") or "/"


def _under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def is_forbidden(method: str, path: str) -> bool:
    """Yol/yontem PAT ile hic yapilamaz mi?"""
    path = _norm(path)
    method = method.upper()
    if (method, path) in ALLOWED_EXACT:
        return False
    if any(_under(path, p) for p in FORBIDDEN_PREFIXES):
        return True
    # /api/v1/cards/{id}/attachments*
    parts = path.split("/")
    if (
        path.startswith(f"{API_PREFIX}/cards/")
        and len(parts) >= 6
        and parts[5] == "attachments"
    ):
        return True
    if method in {"PUT", "PATCH"} and _under(path, SETTINGS_PREFIX):
        return True
    return False


def needs_write(method: str, path: str) -> bool:
    """Yazma kapsami (write) gerekir mi?"""
    method = method.upper()
    if method in READ_METHODS:
        return False
    if method == "POST" and _norm(path) in READ_ONLY_POSTS:
        return False
    return True
