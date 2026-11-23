"""Söz bekçisi: MUSİCAİ'nin değişmez kurallarını kodla denetler.

1. Yasaklı kelimeler (asfalt, beton, labirent, silüet, karanlık kuyu ...) hiçbir biçimde geçemez.
2. Sıfır tekrar: eski şarkılardan 4 kelimelik herhangi bir dizi aynen geçemez, başlık tekrar edemez.
3. Hece ölçüsü: Türkçede hece sayısı = sesli harf sayısı. Aynı bölümdeki satırlar birbirine
   yakın uzunlukta olmalı (beat'e oturması ve Suno/ACE-Step'te "kayma" olmaması için).
4. Yapı: [Intro] [Verse 1] [Pre-Chorus] [Chorus] [Verse 2] [Bridge] [Outro] etiketleri bulunmalı.

check() bir sorun listesi döndürür; liste boşsa sözler yayına hazırdır.
"""
from __future__ import annotations

import re
import statistics

# Kök biçimde yazılır; ekli halleri de yakalanır (betonun, labirentte, silüetler ...)
BANNED_ROOTS = ["asfalt", "beton", "labirent", "silüet", "siluet", "karanlık kuyu", "karanlik kuyu"]
VOWELS = set("aeıioöuüâîûAEIİOÖUÜÂÎÛ")
REQUIRED = ["intro", "verse 1", "pre-chorus", "chorus", "verse 2", "bridge", "outro"]
TAG = re.compile(r"^\s*\[([^\]]+)\]\s*$")

# Satır uzunluğu sınırları (hece). Çok kısa satırlar ezgiyi boşaltır, çok uzunlar sıkıştırır.
MIN_SYL, MAX_SYL = 5, 16
# Aynı bölümde satırın, bölüm ortancasından en fazla bu kadar sapmasına izin verilir.
MAX_SPREAD = 2


def tr_lower(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def syllables(line: str) -> int:
    return sum(1 for ch in line if ch in VOWELS)


def words(text: str) -> list[str]:
    return re.findall(r"[a-zçğıöşüâîû0-9]+", tr_lower(text))


def sections(lyrics: str) -> list[tuple[str, list[str]]]:
    """[(etiket, [satırlar])] — etiketsiz baştaki satırlar 'giriş' sayılır."""
    out: list[tuple[str, list[str]]] = []
    cur, lines = "giriş", []
    for raw in lyrics.splitlines():
        m = TAG.match(raw)
        if m:
            if lines or cur != "giriş":
                out.append((cur, lines))
            cur, lines = m.group(1).strip(), []
        elif raw.strip():
            lines.append(raw.strip())
    out.append((cur, lines))
    return [(t, ls) for t, ls in out if ls or t != "giriş"]


def banned_hits(text: str) -> list[str]:
    low = tr_lower(text)
    low_plain = re.sub(r"\s+", " ", low)
    return [b for b in BANNED_ROOTS if b in low_plain]


def ngrams(text: str, n: int = 4) -> set[tuple[str, ...]]:
    w = words(text)
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def lyric_lines(lyrics: str) -> list[str]:
    return [ln for _, ls in sections(lyrics) for ln in ls]


def check(song: dict, history: list[dict]) -> list[str]:
    """Sorunları Türkçe ve modele geri verilebilecek netlikte listeler."""
    problems: list[str] = []
    lyrics = song.get("lyrics", "")
    everything = " ".join(str(song.get(k, "")) for k in ("title", "lyrics", "story", "hook", "concept"))

    hits = banned_hits(everything)
    if hits:
        problems.append(f"YASAKLI kelime/ifade kullanılmış: {', '.join(hits)}. Bunları ve eş anlamlı imgelerini tamamen çıkar.")

    title = tr_lower(song.get("title", "")).strip()
    if not title:
        problems.append("Şarkı adı boş.")
    for old in history:
        if tr_lower(old.get("title", "")).strip() == title:
            problems.append(f"'{song['title']}' adı daha önce kullanıldı, yeni bir ad bul.")
            break

    tags = [t.lower() for t, _ in sections(lyrics)]  # etiketler İngilizce
    missing = [r for r in REQUIRED if not any(t.startswith(r) for t in tags)]
    if missing:
        problems.append("Eksik bölüm etiketleri: " + ", ".join(f"[{m.title()}]" for m in missing))

    # Sıfır tekrar: eski şarkılarla ortak 4 kelimelik dizi olmamalı
    mine = ngrams(lyrics)
    for old in history:
        common = mine & ngrams(old.get("lyrics", ""))
        if common:
            sample = " ".join(next(iter(common)))
            problems.append(f"Eski şarkı '{old.get('title')}' ile aynı ifade var: \"{sample}\". Tamamen yeni cümle kur.")

    # Hece ölçüsü
    for tag, lines in sections(lyrics):
        if not lines or tag.lower().startswith(("intro", "outro")):
            continue  # giriş/çıkış ünlemleri serbest
        counts = [syllables(ln) for ln in lines]
        for ln, c in zip(lines, counts):
            if c < MIN_SYL or c > MAX_SYL:
                problems.append(f"[{tag}] '{ln}' satırı {c} hece; {MIN_SYL}-{MAX_SYL} arası olmalı.")
        if len(lines) >= 2:
            med = statistics.median(counts)
            for ln, c in zip(lines, counts):
                if abs(c - med) > MAX_SPREAD and MIN_SYL <= c <= MAX_SYL:
                    problems.append(f"[{tag}] '{ln}' satırı {c} hece ama bölümün ölçüsü ~{int(med)}; "
                                    f"satırları eşitle (en fazla ±{MAX_SPREAD}).")

    # Nakarat akılda kalıcı olsun: en az 4 satır, tekrar eden bir kanca
    chorus = [ls for t, ls in sections(lyrics) if t.lower().startswith("chorus")]
    if chorus and len(chorus[0]) < 4:
        problems.append("Nakarat en az 4 satır olmalı.")

    n_lines = len(lyric_lines(lyrics))
    if n_lines < 18:
        problems.append(f"Sözler çok kısa ({n_lines} satır); tam şarkı için en az 18 satır yaz.")
    if n_lines > 48:
        problems.append(f"Sözler çok uzun ({n_lines} satır); 48 satırı geçme.")
    return problems


def syllable_report(lyrics: str) -> str:
    """Telegram'da göstermek için satır satır hece dökümü."""
    out = []
    for tag, lines in sections(lyrics):
        out.append(f"[{tag}]")
        out += [f"{syllables(ln):>2} | {ln}" for ln in lines]
    return "\n".join(out)
