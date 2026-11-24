"""Metin modelleri: Gemini (ücretsiz katman) varsayılan, Claude isteğe bağlı.

- GEMINI_API_KEY zorunlu (aistudio.google.com, Pipaloo'daki anahtar da olur).
- ANTHROPIC_API_KEY eklenirse sözleri Claude yazar, Gemini yedek kalır.
  LYRICS_ENGINE=gemini ile Claude anahtarı olsa bile Gemini'ye zorlanabilir.
Her iki yol da JSON döndürür.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time

import requests

log = logging.getLogger(__name__)
GEMINI = "https://generativelanguage.googleapis.com/v1beta"
CLAUDE = "https://api.anthropic.com/v1/messages"


class QuotaError(RuntimeError):
    pass


def _clean(key: str | None) -> str:
    return re.sub(r"\s+", "", key or "")


def _parse_json(text: str):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}|\[.*\]", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


# ------------------------------------------------------------------ Gemini
_models_cache: list[str] | None = None


def _ghdr() -> dict:
    return {"x-goog-api-key": _clean(os.environ.get("GEMINI_API_KEY"))}


def gemini_models() -> list[str]:
    """Ücretsiz katmandaki en iyi metin modelleri (adlar sık değiştiği için API'den okunur)."""
    global _models_cache
    if _models_cache:
        return _models_cache
    if os.environ.get("GEMINI_MODEL"):
        _models_cache = [os.environ["GEMINI_MODEL"]]
        return _models_cache
    r = requests.get(f"{GEMINI}/models", params={"pageSize": 200}, headers=_ghdr(), timeout=30)
    if not r.ok:
        raise RuntimeError(f"Gemini model listesi alınamadı: {r.status_code} {r.text[:200]}"
                           + (" (API anahtarı yanlış olabilir)" if r.status_code in (400, 401, 403) else ""))
    names = [m["name"].split("/", 1)[1] for m in r.json().get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    bad = ("image", "tts", "live", "audio", "embedding", "exp", "robotics", "computer", "lyria", "veo", "nano")

    def score(n: str):
        nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", n)] or [0]
        return ("preview" not in n, "pro" in n, ("flash" in n) and ("lite" not in n), nums[0])

    good = sorted((n for n in names if "gemini" in n and not any(b in n for b in bad)), key=score, reverse=True)
    if not good:
        raise RuntimeError(f"Uygun Gemini modeli bulunamadı: {names[:20]}")
    # Söz yazımı yaratıcı iş: önce pro (ücretsiz kotası varsa), sonra flash, en son lite
    pro = [n for n in good if "pro" in n][:1]
    flash = [n for n in good if "flash" in n and "lite" not in n][:2]
    lite = [n for n in good if "lite" in n][:1]
    # Yedek: Gemma modellerinin ücretsiz kotası Gemini'den ayrı ve çok daha geniş (Pipaloo/İş Radarı ile çakışmaz)
    gemma = sorted((n for n in names if n.startswith("gemma") and "-it" in n and not any(b in n for b in bad)),
                   key=lambda n: [float(x) for x in re.findall(r"\d+(?:\.\d+)?", n)] or [0], reverse=True)[:2]
    _models_cache = (pro + flash + lite or good[:3]) + gemma
    log.info("Gemini modelleri: %s", ", ".join(_models_cache))
    return _models_cache


def _gemini_one(model: str, prompt: str, temperature: float) -> dict:
    if model.startswith("gemma"):  # Gemma: JSON modu ve thinking ayarı yok, JSON metinden ayıklanır
        variants = [{"temperature": temperature, "maxOutputTokens": 8192}]
        prompt += "\n\nYalnızca geçerli JSON döndür; açıklama veya kod bloğu yazma."
    else:
        base = {"responseMimeType": "application/json", "temperature": temperature}
        variants = [{**base, "thinkingConfig": {"thinkingLevel": "low"}},
                    {**base, "thinkingConfig": {"thinkingBudget": 1024}}, base]
    v = n429 = busy = 0
    for attempt in range(6):
        if busy >= 2:
            raise QuotaError(f"{model} yoğun")
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": variants[v]}
        try:
            r = requests.post(f"{GEMINI}/models/{model}:generateContent", headers=_ghdr(), json=body, timeout=180)
        except requests.exceptions.Timeout:
            busy += 1
            continue
        if r.status_code == 400 and "thinking" in r.text.lower() and v < len(variants) - 1:
            v += 1
            continue
        if r.status_code == 429:
            n429 += 1
            if n429 >= 3 or "per day" in r.text.lower() or "perday" in r.text.lower() or "limit: 0" in r.text:
                raise QuotaError(r.text[:200])
            time.sleep(20 * n429)
            continue
        if r.status_code in (500, 503):
            busy += 1
            time.sleep(10)
            continue
        if r.status_code == 404:
            raise QuotaError(f"{model} bulunamadı")
        if not r.ok:
            raise RuntimeError(f"Gemini hatası: {r.status_code} {r.text[:300]}")
        cand = r.json().get("candidates") or [{}]
        parts = cand[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text.strip():
            busy += 1
            continue
        return _parse_json(text)
    raise QuotaError(f"{model} cevap vermedi")


def gemini(prompt: str, temperature: float = 1.0) -> dict:
    if not _clean(os.environ.get("GEMINI_API_KEY")):
        raise RuntimeError("GEMINI_API_KEY yok")
    last = None
    for cycle in range(3):
        if cycle:
            log.info("Tüm modeller meşgul/kotada; %d dk bekleniyor", 2 * cycle)
            time.sleep(120 * cycle)
        for m in gemini_models():
            try:
                return _gemini_one(m, prompt, temperature)
            except QuotaError as e:
                last = e
                log.warning("%s olmadı (%s), sıradaki model", m, re.sub(r"\s+", " ", str(e))[:160])
    raise RuntimeError(f"Gemini cevap vermedi: {last}")


# ------------------------------------------------------------------ Claude
def claude_enabled() -> bool:
    return bool(_clean(os.environ.get("ANTHROPIC_API_KEY"))) and os.environ.get("LYRICS_ENGINE", "") != "gemini"


def claude(prompt: str, temperature: float = 1.0) -> dict:
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
    body = {"model": model, "max_tokens": 6000, "temperature": temperature,
            "system": "Sadece geçerli JSON döndür. Açıklama, markdown ya da kod bloğu yazma.",
            "messages": [{"role": "user", "content": prompt}]}
    hdr = {"x-api-key": _clean(os.environ.get("ANTHROPIC_API_KEY")), "anthropic-version": "2023-06-01",
           "content-type": "application/json"}
    for attempt in range(4):
        r = requests.post(CLAUDE, headers=hdr, json=body, timeout=240)
        if r.status_code in (429, 500, 529):
            time.sleep(15 * (attempt + 1))
            continue
        if not r.ok:
            raise RuntimeError(f"Claude hatası: {r.status_code} {r.text[:300]}")
        text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
        return _parse_json(text)
    raise RuntimeError("Claude cevap vermedi")


def ask(prompt: str, temperature: float = 1.0) -> dict:
    """Claude açıksa önce Claude, olmazsa Gemini."""
    if claude_enabled():
        try:
            return claude(prompt, temperature)
        except Exception as e:
            log.warning("Claude başarısız, Gemini'ye geçiliyor: %s", e)
    return gemini(prompt, temperature)
