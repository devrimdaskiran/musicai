"""YouTube'a yükleme: Zernio API (Pipaloo'da kullandığın aynı servis; ücretsiz planda 2 hesap).

ZERNIO_API_KEY     : Zernio anahtarı (Pipaloo'daki ile aynı olabilir).
ZERNIO_ACCOUNT_ID  : MUSİCAİ YouTube kanalının Zernio hesap kimliği. ÖNEMLİ: Zernio'da Pipaloo kanalı da
                     bağlı olduğu için bu verilmezse yükleme yapılmaz (yanlış kanala gitmesin diye).
                     Kimliği bulmak için: Actions -> "MUSİCAİ bilgi" işini çalıştır.

Her yüklemede "yapay/değiştirilmiş içerik" (containsSyntheticMedia) işareti açılır, kategori Müzik (10).
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import requests

log = logging.getLogger(__name__)
API = "https://zernio.com/api/v1"


def _key() -> str:
    return re.sub(r"\s+", "", os.environ.get("ZERNIO_API_KEY", ""))


def _account() -> str:
    return re.sub(r"\s+", "", os.environ.get("ZERNIO_ACCOUNT_ID", ""))


def enabled() -> bool:
    return bool(_key() and _account())


def _h() -> dict:
    return {"Authorization": f"Bearer {_key()}"}


def _ok(r: requests.Response, what: str) -> requests.Response:
    if not r.ok:
        raise RuntimeError(f"Zernio {what} başarısız: {r.status_code} {r.text[:300]}")
    return r


def accounts() -> list[dict]:
    r = _ok(requests.get(f"{API}/accounts", headers=_h(), timeout=30), "hesap listesi")
    return r.json().get("accounts", [])


def upload_file(path: Path, content_type: str) -> str:
    """Dosyayı Zernio deposuna yükler, herkese açık adresini döndürür (onayda tekrar yüklemeye gerek kalmaz)."""
    r = _ok(requests.post(f"{API}/media/presign", headers=_h(),
                          json={"filename": path.name, "contentType": content_type}, timeout=30), "presign")
    d = r.json()
    with open(path, "rb") as f:
        put = requests.put(d["uploadUrl"], data=f, headers={"Content-Type": content_type}, timeout=1800)
    if not put.ok:
        raise RuntimeError(f"Dosya depoya yüklenemedi: {put.status_code}")
    return d["publicUrl"]


def post_youtube(media_url: str, title: str, description: str, tags: list[str], thumb_url: str | None = None) -> dict:
    tags = [t[:100] for t in tags]
    while sum(len(t) for t in tags) > 480:
        tags.pop()
    media = {"type": "video", "url": media_url}
    if thumb_url:
        media["thumbnail"] = thumb_url
    psd = {"title": title[:100], "visibility": "public", "madeForKids": False, "containsSyntheticMedia": True,
           "categoryId": "10", "defaultLanguage": "tr", "defaultAudioLanguage": "tr"}
    body = {"content": description[:5000], "tags": tags, "mediaItems": [media],
            "platforms": [{"platform": "youtube", "accountId": _account(), "platformSpecificData": psd}],
            "publishNow": True}
    return _ok(requests.post(f"{API}/posts", headers=_h(), json=body, timeout=600), "gönderi").json()


def post_url(resp: dict) -> str | None:
    try:
        for p in resp.get("post", {}).get("platforms", []):
            if p.get("platformPostUrl"):
                return p["platformPostUrl"]
    except Exception:
        pass
    return None
