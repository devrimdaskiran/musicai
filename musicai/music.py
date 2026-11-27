"""Şarkıyı üretir: ACE-Step 1.5 (açık kaynak, MIT lisanslı, ticari kullanım serbest, Türkçe destekli).

Ücretsiz çalışır: GitHub Actions'ın CPU makinesinde (GPU yoksa) ya da GPU'lu bir bilgisayarda.
ACESTEP_DIR: ACE-Step kaynak kodunun klasörü (model dosyaları onun checkpoints/ klasörüne iner).
MUSICAI_LM : "0.6B" (varsayılan; ücretsiz CPU makinesinde ~5 dk/45 sn), "1.7B" (CPU için çok yavaş) ya da "none".
MUSICAI_STEPS: difüzyon adımı (turbo için 8 yeterli).
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

log = logging.getLogger(__name__)

_dit = None
_llm = None


def _ace_dir() -> Path:
    d = Path(os.environ.get("ACESTEP_DIR", "ace")).resolve()
    if not (d / "acestep").exists():
        raise RuntimeError(f"ACE-Step bulunamadı: {d} (workflow 'ACE-Step kur' adımı çalıştı mı?)")
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))
    return d


def _load():
    global _dit, _llm
    if _dit is not None:
        return _dit, _llm
    root = _ace_dir()
    import torch
    # Bir çekirdeği GitHub'ın kendi ajanına bırak: tüm CPU'yu kaplamak "runner lost communication" hatasına yol açtı
    torch.set_num_threads(max(1, (os.cpu_count() or 4) - 1))
    from acestep.handler import AceStepHandler
    from acestep.llm_inference import LLMHandler

    t0 = time.time()
    dit = AceStepHandler()
    msg, ok = dit.initialize_service(project_root=str(root), config_path=os.environ.get("MUSICAI_DIT", "acestep-v15-turbo"),
                                     device="auto", offload_to_cpu=False)
    if not ok:
        raise RuntimeError(f"ACE-Step modeli yüklenemedi: {msg}")
    log.info("ACE-Step DiT hazır (%.0f sn): %s", time.time() - t0, msg[:200])

    llm = LLMHandler()
    lm = os.environ.get("MUSICAI_LM", "0.6B")
    if lm.lower() != "none":
        t0 = time.time()
        try:  # 1.7B ana paketle gelir; 0.6B/4B ayrıca indirilir
            from acestep.model_downloader import ensure_lm_model
            ok, msg = ensure_lm_model(f"acestep-5Hz-lm-{lm}", checkpoints_dir=root / "checkpoints")
            log.info("LM indirme: %s", str(msg)[:150])
        except Exception as e:
            log.warning("LM indirilemedi: %s", e)
        msg, ok = llm.initialize(checkpoint_dir=str(root / "checkpoints"), lm_model_path=f"acestep-5Hz-lm-{lm}",
                                 backend="pt", device="auto", offload_to_cpu=False)
        if ok:
            log.info("ACE-Step LM hazır (%.0f sn)", time.time() - t0)
        else:
            log.warning("LM yüklenemedi, LM'siz devam: %s", msg[:200])
    _dit, _llm = dit, llm
    return dit, llm


def generate(song: dict, out_dir: Path, seed: int = -1, duration: float | None = None) -> Path:
    """Sözleri ve tarifi ACE-Step'e verir, WAV dosyasının yolunu döndürür."""
    dit, llm = _load()
    from acestep.inference import GenerationConfig, GenerationParams, generate_music

    vocal = {"male": "male vocal", "female": "female vocal", "duet": "male and female duet vocals"}.get(song.get("vocal"), "")
    caption = song["caption"]
    if vocal and vocal.split()[0] not in caption.lower():
        caption = f"{caption}, {vocal}"
    params = GenerationParams(
        task_type="text2music",
        thinking=bool(llm and llm.llm_initialized),
        caption=caption,
        lyrics=song["lyrics"],
        bpm=song.get("bpm"),
        keyscale=song.get("keyscale", ""),
        timesignature="4",
        vocal_language="tr",
        duration=float(duration or song.get("duration", 170)),
        inference_steps=int(os.environ.get("MUSICAI_STEPS", 8)),
        seed=seed,
    )
    config = GenerationConfig(batch_size=1, audio_format="wav", use_random_seed=seed < 0)
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    res = generate_music(dit, llm, params=params, config=config, save_dir=str(out_dir))
    if not res.success or not res.audios:
        raise RuntimeError(f"Şarkı üretilemedi: {res.error or res.status_message}")
    path = Path(res.audios[0]["path"])
    log.info("Şarkı üretildi (%.0f sn): %s", time.time() - t0, path.name)
    return path


def to_mp3(wav: Path, mp3: Path) -> Path:
    """Sesi -14 LUFS'a (YouTube/TikTok seviyesi) getirip 320k MP3 yapar."""
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
                    "-ar", "44100", "-b:a", "320k", str(mp3)], check=True)
    return mp3
