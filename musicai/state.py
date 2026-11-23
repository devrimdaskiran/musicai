"""Kalıcı hafıza (git'e kaydedilir):

- state/songs/<id>.json      : üretilen her şarkının tam paketi (sözler dahil) -> sıfır tekrar denetimi
- state/pending/<key>.json   : Telegram onayı bekleyenler
- state/history/<...>.json   : yayınlandı / atlandı kayıtları
- state/state.json           : küçük ayarlar (chat_id, telegram offset, son tarzlar)
- data/queue.json            : sıradaki tarz önceliği (ör. yarım kalan Anadolu Rock)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state/state.json"
SONGS = ROOT / "state/songs"
PENDING = ROOT / "state/pending"
HISTORY = ROOT / "state/history"
MARKS = ROOT / "state/marks"
QUEUE = ROOT / "data/queue.json"
PAST = ROOT / "data/past_titles.json"


def _read(p: Path, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def _write(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


def load() -> dict:
    st = _read(STATE, {})
    st.setdefault("recent_styles", [])
    return st


def save(st: dict) -> None:
    _write(STATE, st)


def songs() -> list[dict]:
    """Önceki tüm şarkılar (eski dönem başlıkları sözsüz olarak eklenir)."""
    out = [{"title": t, "lyrics": ""} for t in _read(PAST, [])]
    if SONGS.exists():
        out += [_read(f, {}) for f in sorted(SONGS.glob("*.json"))]
    return out


def add_song(song_id: str, song: dict) -> None:
    _write(SONGS / f"{song_id}.json", song)


def queue() -> list[str]:
    return _read(QUEUE, [])


def pop_queue(style_id: str) -> None:
    q = [s for s in queue() if s != style_id]
    _write(QUEUE, q)


def pending() -> dict[str, dict]:
    return {f.stem: _read(f, {}) for f in sorted(PENDING.glob("*.json"))} if PENDING.exists() else {}


def add_pending(key: str, item: dict) -> None:
    _write(PENDING / f"{key}.json", item)


def remove_pending(key: str) -> None:
    (PENDING / f"{key}.json").unlink(missing_ok=True)


def add_history(entry: dict) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    _write(HISTORY / f"{stamp}-{entry.get('key', 'x')}.json", entry)


def recently(name: str, minutes: int) -> bool:
    f = MARKS / name
    if not f.exists():
        return False
    try:
        t = datetime.fromisoformat(f.read_text().strip())
    except ValueError:
        return False
    return (datetime.now(timezone.utc) - t).total_seconds() < minutes * 60


def mark(name: str) -> None:
    MARKS.mkdir(parents=True, exist_ok=True)
    (MARKS / name).write_text(datetime.now(timezone.utc).isoformat())
