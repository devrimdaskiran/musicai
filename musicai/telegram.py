"""Telegram botu: yeni şarkıyı (ses + Short önizleme) "✅ Yayınla / ❌ Atla" butonlarıyla sana gönderir.

TELEGRAM_BOT_TOKEN zorunlu. Sohbet kimliği TELEGRAM_CHAT_ID'den, yoksa state/state.json'daki
kayıttan, o da yoksa bota en son yazan sohbetten bulunur (botu açıp /start yazman yeter).
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

import requests

log = logging.getLogger(__name__)
_chat_cache: str | None = None


def _token() -> str:
    # yapıştırırken araya giren boşluk/satır sonlarını temizle
    return re.sub(r"\s+", "", os.environ.get("TELEGRAM_BOT_TOKEN", ""))


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{_token()}/{method}"


class TelegramError(RuntimeError):
    pass


def _check(r: requests.Response, what: str) -> requests.Response:
    """Hata mesajında token görünmesin diye URL'yi yazmadan hata verir."""
    if not r.ok:
        try:
            desc = r.json().get("description", "")
        except Exception:
            desc = r.text[:200]
        hint = " (token yanlış olabilir)" if r.status_code in (401, 404) else ""
        raise TelegramError(f"Telegram {what} başarısız: {r.status_code} {desc}{hint}")
    return r


def enabled() -> bool:
    return bool(_token())


def set_chat(cid: str | None) -> None:
    global _chat_cache
    if cid:
        _chat_cache = str(cid)


def chat_id() -> str:
    global _chat_cache
    if os.environ.get("TELEGRAM_CHAT_ID"):
        return os.environ["TELEGRAM_CHAT_ID"].strip()
    if _chat_cache:
        return _chat_cache
    r = _check(requests.get(_api("getUpdates"), timeout=30), "getUpdates")
    for upd in reversed(r.json().get("result", [])):
        msg = upd.get("message") or upd.get("edited_message") or upd.get("channel_post")
        if not msg and upd.get("callback_query"):
            msg = upd["callback_query"].get("message")
        if msg:
            _chat_cache = str(msg["chat"]["id"])
            return _chat_cache
    try:
        me = _check(requests.get(_api("getMe"), timeout=30), "getMe").json()["result"]["username"]
    except Exception:
        me = "?"
    raise RuntimeError(f"Sohbet bulunamadı: token @{me} botuna ait. Telegram'da @{me} ile sohbete /start yaz.")


def send_text(text: str, reply_to: int | None = None) -> None:
    if not enabled():
        log.info("Telegram kapalı: %s", text[:80])
        return
    try:
        data = {"chat_id": chat_id(), "text": text[:4000]}
        if reply_to:
            data["reply_to_message_id"] = reply_to
        _check(requests.post(_api("sendMessage"), data=data, timeout=30), "sendMessage")
    except Exception as e:  # bilgi mesajı gitmezse üretim durmasın
        log.warning("Telegram mesajı gönderilemedi: %s", e)


def _buttons(key: str) -> str:
    return json.dumps({"inline_keyboard": [[
        {"text": "✅ Yayınla", "callback_data": f"pub:{key}"},
        {"text": "❌ Atla", "callback_data": f"skip:{key}"},
    ]]})


def send_file(method: str, field: str, path: Path, caption: str = "", key: str | None = None,
              mime: str = "application/octet-stream", extra: dict | None = None) -> dict:
    """sendAudio / sendVideo / sendPhoto / sendDocument. Dönüş: {"message_id", "file_id"}"""
    if not enabled():
        log.info("Telegram kapalı, gönderilmedi: %s", path)
        return {}
    data = {"chat_id": chat_id(), "caption": caption[:1024], **(extra or {})}
    if key:
        data["reply_markup"] = _buttons(key)
    with open(path, "rb") as f:
        r = _check(requests.post(_api(method), data=data, files={field: (path.name, f, mime)}, timeout=600), method)
    res = r.json()["result"]
    obj = res.get(field) or res.get("document") or {}
    if isinstance(obj, list):  # photo: boyut listesi
        obj = obj[-1] if obj else {}
    return {"message_id": res["message_id"], "file_id": obj.get("file_id")}


# ---------------------------------------------------------------- onay dinleyici için
def get_updates(offset: int | None) -> list[dict]:
    params = {"timeout": 0, "allowed_updates": json.dumps(["callback_query", "message"])}
    if offset:
        params["offset"] = offset
    return _check(requests.get(_api("getUpdates"), params=params, timeout=30), "getUpdates").json().get("result", [])


def answer_callback(cb_id: str, text: str) -> None:
    try:
        requests.post(_api("answerCallbackQuery"), data={"callback_query_id": cb_id, "text": text[:190]}, timeout=30)
    except Exception as e:
        log.warning("answerCallbackQuery: %s", e)


def set_buttons(message_id: int, label: str | None) -> None:
    """Butonları kaldırır ya da tek bir bilgi etiketiyle değiştirir."""
    markup = {"inline_keyboard": [[{"text": label, "callback_data": "noop"}]]} if label else {"inline_keyboard": []}
    try:
        requests.post(_api("editMessageReplyMarkup"), data={"chat_id": chat_id(), "message_id": message_id,
                                                           "reply_markup": json.dumps(markup)}, timeout=30)
    except Exception as e:
        log.warning("editMessageReplyMarkup: %s", e)
