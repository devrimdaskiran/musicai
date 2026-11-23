"""Söz yazarı: tarz seçer, 5 bölümlük MUSİCAİ paketini yazdırır, kurallardan geçene kadar düzelttirir.

Başlık birliği kodla garanti edilir: model yalnızca `title` ve `style_label` verir;
kapak yazısı, YouTube başlığı, Shorts başlığı ve açıklama hepsi bu iki alandan türetilir.
"""
from __future__ import annotations

import json
import logging
import random
import re
from pathlib import Path

from . import checks, llm, state

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
STYLES = json.loads((ROOT / "data/styles.json").read_text(encoding="utf-8"))
MAX_ROUNDS = 5

RULES = """KESİN KURALLAR (asla ihlal etme):
1. SIFIR TEKRAR: Aşağıda listelenen eski şarkıların hiçbir kelime grubunu, metaforunu, kalıbını, imgesini
   kullanma. Konu, hikâye ve imgeler %100 yeni olacak.
2. YASAKLI KELİMELER (hiçbir ekle, hiçbir biçimde): asfalt, beton, labirent, silüet, karanlık kuyu.
   "Betonun dili yok, silüetler konuşur" türü cümleler ve bu atmosferin klişeleri de yasak.
3. HECE ÖLÇÜSÜ: Türkçede hece sayısı = sesli harf sayısı. HER SATIR 7-10 HECE (asla 11'i geçme).
   Her bölümde satırlar aynı ölçüde olsun (örn. hepsi 8 ya da hepsi 9 hece; en fazla ±1 sapma). Kısa,
   nefes alınabilen satırlar yaz: vokal kelimeleri yutmasın, her kelime net anlaşılsın. Uzun bileşik
   kelimeler ve art arda sert ünsüzler yerine akıcı, ağızda kolay dönen kelimeler seç. Satır sonlarında net durak,
   kafiye düzeni (aabb ya da abab) olsun. Bu sözler bir yapay zekâ müzik modeline verilecek; ölçü bozuk
   olursa vokal beat'ten kayar.
4. YAPI: [Intro] [Verse 1] [Pre-Chorus] [Chorus] [Verse 2] [Pre-Chorus] [Chorus] [Bridge] [Chorus] [Outro]
   sırasını kullan. Etiketler İngilizce ve köşeli parantezde, tek başına satırda. [Intro] ve [Outro] 1-2 kısa
   satır olabilir. Nakarat 4 satır, akılda kalıcı bir kanca (hook) cümlesiyle başlasın ve her tekrarda aynı olsun.
5. SANATÇI ADI YOK: Hiçbir gerçek sanatçı, grup ya da şarkı adı anma; tarzı sadece tarif et.
6. DİL: Doğal, günlük, söylenebilir Türkçe. Zorlama devrik cümle ve yapay kafiye yok. Argo/küfür yok.
"""

SCHEMA = """SADECE şu anahtarlara sahip TEK bir JSON nesnesi döndür:
{
 "title": "Şarkı adı (Türkçe, 1-4 kelime, kapakta ve başlıkta birebir bu kullanılacak)",
 "concept": "Konsept ve Trend Analizi: bu şarkıyı neden bu tarzda yaptığımızı ve hangi video türlerinde
             patlayacağını anlatan 3-4 cümlelik samimi 'kanka' yorumu (Devrim'e hitaben)",
 "caption": "İNGİLİZCE müzik üretim promptu: tür, enstrümanlar, tempo hissi, vokal cinsiyeti ve tonu, atmosfer,
             yapı. 40-70 kelime. Sanatçı adı YOK.",
 "bpm": tamsayı,
 "keyscale": "örn. 'A minor'",
 "lyrics": "Etiketli tam Türkçe sözler, satırlar \\n ile ayrılmış",
 "hook": "Açıklamanın ilk cümlesi: merak uyandıran tek cümle, 1 emoji",
 "story": "Şarkının hikâyesi, 2-3 cümle",
 "hashtags": ["12-15 adet, '#' olmadan, Türkçe+İngilizce karışık, tarz ve video türüne uygun"],
 "cover_prompt": "İNGİLİZCE kapak fotoğrafı tarifi: şarkının hikâyesinden tek bir gerçekçi sahne (mekân, nesne ya da arkadan/uzaktan bir insan), ışık ve renk paleti. Gerçek bir analog plak kapağı fotoğrafı gibi; dijital sanat, 3D, fantastik efekt YOK; içinde YAZI/HARF OLMASIN"
}"""


def pick_style(st: dict) -> dict:
    """Önce kuyruk (yarım kalan işler), sonra son kullanılmayan tarzlardan rastgele; vokal sırayla değişir."""
    by_id = {s["id"]: s for s in STYLES}
    for sid in state.queue():
        if sid in by_id:
            return by_id[sid]
    recent = st.get("recent_styles", [])[-6:]
    last_vocal = st.get("last_vocal")
    pool = [s for s in STYLES if s["id"] not in recent] or STYLES
    alt = [s for s in pool if s["vocal"] != last_vocal] or pool
    return random.choice(alt)


def _history_block(history: list[dict]) -> str:
    titles = [h.get("title", "") for h in history][-80:]
    hooks = []
    for h in history[-25:]:
        ch = [ls for t, ls in checks.sections(h.get("lyrics", "")) if t.lower().startswith("chorus")]
        if ch:
            hooks.append(ch[0][0])
    out = "ESKİ ŞARKI ADLARI (hiçbirini ve benzerini kullanma): " + "; ".join(titles)
    if hooks:
        out += "\nESKİ NAKARAT KANCALARI (bunlara benzeme): " + " / ".join(hooks)
    return out


def _brief(style: dict, history: list[dict], trends: list[str]) -> str:
    bpm = random.randint(*style["bpm"])
    vocal = {"male": "erkek vokal", "female": "kadın vokal", "duet": "kadın-erkek düet"}[style["vocal"]]
    trend = ("\nŞU AN TÜRKİYE'DE YÜKSELEN MÜZİK SHORTS BAŞLIKLARI (sadece tema/duygu ilhamı; kopyalama): "
             + " | ".join(trends[:15])) if trends else ""
    return f"""Sen MUSİCAİ adlı Türkçe yapay zekâ müzik kanalının söz yazarı ve müzik direktörüsün.
Kanal sahibi Devrim; YouTube, TikTok ve Instagram Reels'te viral olacak, trend odaklı, %100 özgün Türkçe şarkılar
yayınlıyor.

BU ŞARKININ TARZI: {style['label']}
Ses: {style['sound']}
Vokal: {vocal} — {style['vocal_tone']}
Tempo: yaklaşık {bpm} BPM
Patlayacağı videolar: {style['videos']}
Tema yönü (ilham, zorunlu değil): {style['theme_hint']}
{trend}

{RULES}
{_history_block(history)}

{SCHEMA}"""


def _repair_prompt(song: dict, problems: list[str]) -> str:
    return f"""Aşağıdaki MUSİCAİ şarkı paketinde kural ihlalleri var. Sadece sorunlu yerleri düzelt; şarkının ruhunu,
adını (ad sorunu yoksa) ve iyi çalışan satırları koru. Hece sayısı = sesli harf sayısı; satırı kısaltıp uzatarak
ölçüyü tuttur.

{RULES}

SORUNLAR:
- """ + "\n- ".join(problems[:25]) + f"""

MEVCUT PAKET:
{json.dumps(song, ensure_ascii=False)}

Düzeltilmiş paketin tamamını aynı JSON şemasıyla döndür."""


NATURAL = ("natural human vocal performance, clear articulate Turkish diction, every word intelligible, "
           "expressive breathing, no robotic autotune, warm organic mix")


def _normalize(song: dict, style: dict) -> dict:
    song["title"] = re.sub(r"\s+", " ", str(song.get("title", ""))).strip().strip('"\'')
    song["lyrics"] = str(song.get("lyrics", "")).replace("\\n", "\n").strip()
    tags = song.get("hashtags") or []
    if isinstance(tags, str):
        tags = re.split(r"[,\s]+", tags)
    song["hashtags"] = [re.sub(r"[^\wçğıöşüÇĞİÖŞÜ]", "", t.lstrip("#")) for t in tags if t.strip("# ")][:15]
    try:
        song["bpm"] = int(song.get("bpm") or sum(style["bpm"]) // 2)
    except (TypeError, ValueError):
        song["bpm"] = sum(style["bpm"]) // 2
    song["duration"] = fit_duration(song["lyrics"], song["bpm"])
    cap = str(song.get("caption", "")).strip().rstrip(".")
    if "diction" not in cap.lower():
        cap = f"{cap}, {NATURAL}"
    song["caption"] = cap
    song["style_id"], song["style_label"], song["vocal"] = style["id"], style["label"], style["vocal"]
    return song


def fit_duration(lyrics: str, bpm: int) -> int:
    """Süreyi söz yoğunluğuna göre ayarlar: saniyede ~2 hece + giriş/ara/çıkış müziği.
    Süre kısa kalırsa model sözleri sıkıştırır ve kelimeler yutulur."""
    syl = sum(checks.syllables(ln) for ln in checks.lyric_lines(lyrics))
    rate = 2.0 if bpm < 115 else 2.4
    return int(max(150, min(240, syl / rate + 40)))


def write_song(st: dict, trends: list[str] | None = None, style_id: str | None = None) -> dict:
    style = next((s for s in STYLES if s["id"] == style_id), None) if style_id else pick_style(st)
    history = state.songs()
    log.info("Tarz: %s (%s)", style["label"], style["vocal"])
    song = _normalize(llm.ask(_brief(style, history, trends or [])), style)
    for rnd in range(1, MAX_ROUNDS + 1):
        problems = checks.check(song, history)
        if not problems:
            log.info("Sözler kurallardan geçti (%d. tur): %s", rnd, song["title"])
            break
        log.info("Tur %d: %d sorun -> düzeltiliyor\n  %s", rnd, len(problems), "\n  ".join(problems[:8]))
        if rnd == MAX_ROUNDS:
            hard = [p for p in problems if not p.startswith("[")]  # hece dışı sorunlar
            if hard or len(problems) > 4:
                raise RuntimeError("Sözler kurallardan geçemedi: " + " | ".join(problems[:6]))
            log.warning("Küçük hece sapmalarıyla kabul edildi: %s", problems)
            song["warnings"] = problems
            break
        song = _normalize(llm.ask(_repair_prompt(song, problems), temperature=0.7), style)
    return song


# ---------------------------------------------------------------- başlık ve açıklama (tek kaynak)
def full_title(song: dict) -> str:
    """Kapak, YouTube ve Shorts başlığı: harfi harfine aynı."""
    return f"{song['title']} | {song['style_label']} [AI Generated]"[:100]


def plain_lyrics(lyrics: str) -> str:
    """Açıklama için sözler: etiketler okunur başlıklara çevrilir."""
    names = {"intro": "", "outro": "", "verse": "", "pre-chorus": "", "chorus": "Nakarat", "bridge": "Köprü"}
    out = []
    for tag, lines in checks.sections(lyrics):
        if not lines:
            continue
        key = tag.lower().split()[0] if tag else ""
        head = names.get(key, "")
        if out:
            out.append("")
        if head:
            out.append(f"({head})")
        out += lines
    return "\n".join(out)


def description(song: dict, short: bool = False) -> str:
    tags = song.get("hashtags", [])
    base = ["MUSICAI", "yapayzekamuzik", "AImusic", "türkçeşarkı"]
    allt = []
    for t in tags + base + (["shorts"] if short else []):
        if t and t.lower() not in [x.lower() for x in allt]:
            allt.append(t)
    return (f"{song.get('hook', '').strip()}\n\n"
            f"{song.get('story', '').strip()}\n\n"
            "🔔 Beğendiysen 👍 bırak, en sevdiğin satırı yorumlara yaz ve yeni şarkılar için MUSİCAİ'ye abone ol!\n\n"
            f"🎤 {song['title']} — Sözler\n\n{plain_lyrics(song['lyrics'])}\n\n"
            "— Devrim\n\n"
            "ℹ️ Bu şarkının müziği ve vokali yapay zekâ ile üretilmiştir.\n\n"
            + " ".join("#" + t for t in allt[:18]))[:4900]
