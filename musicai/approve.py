"""Onay: Telegram'daki "✅ Yayınla / ❌ Atla" butonlarını işler (cron-job.org ile ~15 dk.da bir).

Yayınla -> tam şarkı videosu (kapak görseliyle) + 40 sn'lik Short, YouTube'a aynı başlıkla yüklenir.
"""
from __future__ import annotations

import logging

from . import publish, state, telegram

log = logging.getLogger("musicai.approve")


def handle(action: str, key: str, msg_id: int | None, cb_id: str | None) -> bool:
    item = state.pending().get(key)
    if not item:
        if cb_id:
            telegram.answer_callback(cb_id, "Bu şarkı zaten işlendi.")
        return False
    msg_id = msg_id or item.get("message_id")
    if action == "skip":
        if cb_id:
            telegram.answer_callback(cb_id, "Atlandı")
        telegram.set_buttons(msg_id, "❌ Atlandı")
        state.remove_pending(key)
        state.add_history({"key": key, "title": item["title"], "status": "skipped", "date": state.now()})
        return True
    if action != "pub":
        return False
    if cb_id:
        telegram.answer_callback(cb_id, "Yükleniyor…")
    telegram.set_buttons(msg_id, "⏳ YouTube'a yükleniyor…")
    urls = {}
    try:
        if not item.get("full_done"):
            r = publish.post_youtube(item["full_url"], item["title"], item["description"], item["tags"],
                                     thumb_url=item.get("thumb_url"))
            urls["full"] = publish.post_url(r)
            item["full_done"] = True
            state.add_pending(key, item)  # Short başarısız olursa tam şarkı tekrar yüklenmesin
        r = publish.post_youtube(item["short_url"], item["title"], item["short_description"], item["tags"])
        urls["short"] = publish.post_url(r)
    except Exception as e:
        log.error("Yükleme başarısız: %s", e)
        telegram.set_buttons(msg_id, None)
        telegram.send_text(f"⚠️ Yüklenemedi: {e}\nBir saat içinde tekrar denenecek; istersen ✅ ile tekrar gönder.", msg_id)
        import requests  # butonları geri koy ki tekrar basılabilsin
        try:
            requests.post(telegram._api("editMessageReplyMarkup"), data={
                "chat_id": telegram.chat_id(), "message_id": msg_id, "reply_markup": telegram._buttons(key)}, timeout=30)
        except Exception:
            pass
        return False
    telegram.set_buttons(msg_id, "✅ YouTube'da yayında")
    telegram.send_text("✅ Yayında: " + item["title"] + "".join(f"\n{u}" for u in urls.values() if u), msg_id)
    state.remove_pending(key)
    state.add_history({"key": key, "title": item["title"], "status": "published", "urls": urls, "date": state.now()})
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    st = state.load()
    telegram.set_chat(st.get("chat_id"))
    if not telegram.enabled():
        log.info("Telegram kapalı")
        return
    updates = telegram.get_updates(st.get("tg_offset"))
    offset, done = st.get("tg_offset"), 0
    for u in updates:
        offset = u["update_id"] + 1
        cb = u.get("callback_query")
        if not cb or ":" not in cb.get("data", ""):
            if cb:
                telegram.answer_callback(cb["id"], "👍")
            continue
        action, key = cb["data"].split(":", 1)
        if handle(action, key, cb.get("message", {}).get("message_id"), cb["id"]):
            done += 1
    if offset != st.get("tg_offset"):
        st = state.load()
        st["tg_offset"] = offset
        state.save(st)
    log.info("%d buton işlendi", done)


if __name__ == "__main__":
    main()
