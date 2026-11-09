"""
Kart icerigi araclari (Faz 8a): checklist maddeleri ve etiketler.

Model madde/etiketi METIN ya da id ile soyler; cozumu (hangi madde, hangi etiket,
yeni etiket mi) KOD yapar ve onay kartina yazar. Yurutme ani tekrar okur: arada
kullanici elle etiket/madde eklemis olabilir, onlar kaybolmaz.
"""

from typing import Any

from app.llm.types import ToolSpec
from app.tools.task_api import TaskApiClient, TaskApiError

MAX_ITEMS = 20
ITEM_MAX_LEN = 500

CONTENT_ACTION_TYPES: dict[str, str] = {
    "edit_checklist": "Checklist düzenleme",
    "manage_labels": "Etiket ekleme/çıkarma",
    "delete_checklist_items": "Checklist maddesi silme",
}
# Arac adi -> izin turu (iki arac ayni izni paylasir)
CONTENT_TOOL_TO_ACTION: dict[str, str] = {
    "add_checklist_items": "edit_checklist",
    "update_checklist_items": "edit_checklist",
    "set_card_labels": "manage_labels",
}

CONTENT_SPECS: list[ToolSpec] = [
    ToolSpec(
        "add_checklist_items",
        "Kartın checklist'ine madde ekler (en fazla 20). Karttaki aynı maddeler "
        "atlanır. Kart id'sini search_cards ile bul.",
        {
            "type": "object",
            "properties": {
                "card_id": {"type": "integer"},
                "items": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["card_id", "items"],
        },
    ),
    ToolSpec(
        "update_checklist_items",
        "Checklist maddesini tamamlandı/açık yapar ya da metnini değiştirir. "
        "Maddeyi METİNLE değil item_id ile belirt; id'leri önce get_card ile al.",
        {
            "type": "object",
            "properties": {
                "card_id": {"type": "integer"},
                "changes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "item_id": {"type": "integer"},
                            "is_done": {"type": "boolean"},
                            "text": {"type": "string"},
                        },
                        "required": ["item_id"],
                    },
                },
            },
            "required": ["card_id", "changes"],
        },
    ),
    ToolSpec(
        "delete_checklist_items",
        "Checklist maddelerini siler. item_id'leri önce get_card ile al.",
        {
            "type": "object",
            "properties": {
                "card_id": {"type": "integer"},
                "item_ids": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["card_id", "item_ids"],
        },
    ),
    ToolSpec(
        "set_card_labels",
        "Karta etiket ekler/çıkarır (adla). Board'da olmayan ad eklenirse yeni "
        "etiket oluşturulur; mevcut etiketleri önce get_card/get_board ile gör.",
        {
            "type": "object",
            "properties": {
                "card_id": {"type": "integer"},
                "add": {"type": "array", "items": {"type": "string"}},
                "remove": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["card_id"],
        },
    ),
]


# ---------------- saf yardimcilar ----------------
def norm(text: Any) -> str:
    """Etiket eslestirme anahtari: kucuk harf + yalniz harf/rakam ('Acil!' = 'acil')."""
    return "".join(ch for ch in str(text).casefold() if ch.isalnum())


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def clean_texts(raw: Any, field: str = "items") -> list[str]:
    """Metin listesi: 1-20 oge, bosluk temizlenir, 500'e kirpilir, tekrarlar atilir."""
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{field} en az bir metin içeren liste olmalı")
    if len(raw) > MAX_ITEMS:
        raise ValueError(f"{field} en fazla {MAX_ITEMS} madde içerebilir")
    seen: set[str] = set()
    out: list[str] = []
    for r in raw:
        t = str(r).strip()[:ITEM_MAX_LEN]
        if t and t.casefold() not in seen:
            seen.add(t.casefold())
            out.append(t)
    if not out:
        raise ValueError(f"{field} boş olamaz")
    return out


def names_list(raw: Any, field: str) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{field} liste olmalı")
    return [str(x).strip() for x in raw if str(x).strip()]


def split_known(
    names: list[str], board_labels: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Adlari board etiketleriyle eslestirir -> (var olanlar, bulunamayan adlar)."""
    by_norm = {norm(lb["name"]): lb for lb in board_labels}
    found: list[dict[str, Any]] = []
    missing: list[str] = []
    seen: set[str] = set()
    for n in names:
        key = norm(n)
        if not key or key in seen:
            continue
        seen.add(key)
        if key in by_norm:
            found.append(by_norm[key])
        else:
            missing.append(n[:50])
    return found, missing


def label_line(
    found: list[dict[str, Any]],
    missing: list[str],
    board_labels: list[dict[str, Any]],
    removed: list[dict[str, Any]] | None = None,
) -> str:
    """Onay kartindaki etiket satiri: +Okul (yeni etiket; mevcutlar: …), −Bekliyor."""
    parts = [f"+{lb['name']}" for lb in found]
    if missing:
        have = ", ".join(lb["name"] for lb in board_labels)
        note = f"yeni etiket; mevcutlar: {have}" if have else "yeni etiket"
        parts += [f"+{n} ({note})" for n in missing]
    parts += [f"−{lb['name']}" for lb in removed or []]
    return ", ".join(parts)


# ---------------- yurutme ----------------
async def _resolve_label_ids(
    api: TaskApiClient, board_id: int, add_ids: list[int], add_new: list[str]
) -> list[int]:
    """Var olan id'ler + yeni adlar (yurutme aninda yeniden okunur: ayni ad bu arada
    olusmussa o kullanilir, cift etiket acilmaz)."""
    ids = list(add_ids)
    if not add_new:
        return ids
    labels = (await api.get(f"/boards/{board_id}")).get("labels", [])
    by_norm = {norm(lb["name"]): lb["id"] for lb in labels}
    for name in add_new:
        key = norm(name)
        if key not in by_norm:
            created = await api.write(
                "POST", f"/boards/{board_id}/labels", {"name": name}
            )
            by_norm[key] = created["id"]
        ids.append(by_norm[key])
    return ids


async def apply_labels(
    api: TaskApiClient,
    card_id: int,
    board_id: int,
    add_ids: list[int],
    add_new: list[str],
    remove_ids: list[int],
) -> dict[str, Any]:
    """label_ids = (guncel ∪ eklenecek) − cikarilacak; guncel liste yurutmede okunur."""
    card = await api.get(f"/cards/{card_id}")
    current = list(card.get("label_ids", []))
    wanted = await _resolve_label_ids(api, board_id, add_ids, add_new)
    result = [i for i in current + wanted if i not in remove_ids]
    result = list(dict.fromkeys(result))
    if result != current:
        await api.write("PATCH", f"/cards/{card_id}", {"label_ids": result})
    return {"card_id": card_id, "label_ids": result}


async def execute_checklist(api: TaskApiClient, args: dict[str, Any]) -> dict[str, Any]:
    card_id = args["card_id"]
    added = updated = 0
    skipped: list[int] = []
    for text in args.get("add", []):
        await api.write("POST", f"/cards/{card_id}/checklist", {"text": text})
        added += 1
    for ch in args.get("changes", []):
        body = {k: ch[k] for k in ("is_done", "text") if k in ch}
        try:
            await api.write("PATCH", f"/checklist/{ch['item_id']}", body)
            updated += 1
        except TaskApiError as e:
            if e.status != 404:
                raise
            skipped.append(ch["item_id"])  # arada silinmis
    return {"card_id": card_id, "added": added, "updated": updated, "skipped": skipped}


async def execute_delete_items(
    api: TaskApiClient, args: dict[str, Any]
) -> dict[str, Any]:
    deleted: list[int] = []
    skipped: list[int] = []
    for iid in args["item_ids"]:
        try:
            await api.write("DELETE", f"/checklist/{iid}")
            deleted.append(iid)
        except TaskApiError as e:
            if e.status != 404:
                raise
            skipped.append(iid)
    return {"card_id": args["card_id"], "deleted": deleted, "skipped": skipped}


def shorten(text: str, n: int = 40) -> str:
    return _clip(text, n)
