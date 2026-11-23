# MUSİCAİ 🎵

Yapay zekâ ile üretilen, trend odaklı Türkçe şarkılar için **tamamen ücretsiz** otomatik üretim hattı.
Pipaloo ile aynı iskelet: GitHub Actions üretir → Telegram'a "✅ Yayınla / ❌ Atla" ile gelir → onaylarsan YouTube'a yüklenir.

Haftada 2 kez (Salı ve Cuma ~16:20, Türkiye saati) şunlar olur:

1. **Tarz seçimi:** `data/styles.json`daki 13 tarzdan (Anadolu Rock, Slap House, Akustik Pop, Phonk…) son kullanılmayan
   biri seçilir, vokal sırayla değişir (erkek / kadın / düet). `data/queue.json`daki tarzlar önce gelir.
2. **Trend radarı** (isteğe bağlı): Türkiye'de son 10 günde en çok izlenen müzik Shorts başlıkları ilham olarak alınır.
3. **Sözler:** Gemini (ücretsiz) 5 bölümlük paketi yazar. `ANTHROPIC_API_KEY` eklersen Claude yazar.
4. **Söz bekçisi** (`musicai/checks.py`) her paketi denetler, geçemeyeni modele düzelttirir (en fazla 5 tur):
   - Yasaklı kelimeler: asfalt, beton, labirent, silüet, karanlık kuyu (ekli halleri dahil)
   - Sıfır tekrar: eski şarkılarla tek bir ortak 4 kelimelik dizi bile olamaz, başlık tekrar edemez
   - Hece ölçüsü: her satır 6-11 hece (ACE-Step önerisi; kelimeler yutulmasın), aynı bölümde ±2
   - Yapı: [Intro] [Verse 1] [Pre-Chorus] [Chorus] [Verse 2] [Bridge] [Outro]
5. **Müzik:** [ACE-Step 1.5](https://github.com/ACE-Step/ACE-Step-1.5) (açık kaynak, MIT lisansı, ticari kullanım
   serbest, Türkçe destekli) şarkıyı GitHub'ın ücretsiz makinesinde üretir. GPU gerekmez.
6. **Kapak:** Görseli Pollinations çizer, başlığı kod basar. Kapaktaki yazı, YouTube başlığı ve Shorts başlığı
   tek kaynaktan gelir: `Şarkı Adı | Tarz [AI Generated]`. Çelişmeleri imkânsız.
7. **Videolar:** Tam şarkı (1920×1080) + şarkının en enerjik 40 saniyesi (1080×1920, Shorts/TikTok/Reels).
8. **Telegram:** Kapak, tam şarkı (MP3), 5 bölümlük paket (TikTok/Reels için kopyala-yapıştır) ve butonlu Short.
9. **Onay:** ✅ basınca saatlik onay işi tam şarkıyı ve Short'u YouTube'a "yapay içerik" etiketiyle yükler.

Maliyet: **0 TL**. Gemini ücretsiz katmanı, ACE-Step açık kaynak, GitHub Actions herkese açık repoda ücretsiz,
Pollinations ücretsiz, Zernio ücretsiz planı 2 hesap kapsıyor (Pipaloo + MUSİCAİ).

## Kurulum

### 1. GitHub Secrets

Repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

| Secret | Zorunlu mu | Nereden |
| --- | --- | --- |
| `GEMINI_API_KEY` | Evet | Pipaloo'daki anahtarın aynısı (aistudio.google.com → Get API key) |
| `TELEGRAM_BOT_TOKEN` | Evet | Telegram'da @BotFather → `/newbot`. **Pipaloo botundan ayrı yeni bir bot** aç; sonra bota `/start` yaz |
| `ZERNIO_API_KEY` | Otomatik yükleme için | Pipaloo'daki anahtarın aynısı |
| `ZERNIO_ACCOUNT_ID` | Otomatik yükleme için | Zernio panelinde MUSİCAİ YouTube kanalını bağla → Actions → **MUSİCAİ bilgi** işini çalıştır, logdaki YouTube ID'sini yaz |
| `YOUTUBE_API_KEY` | Hayır (trend radarı) | Pipaloo'daki anahtarın aynısı |
| `POLLINATIONS_TOKEN` | Hayır | Pipaloo'daki anahtarın aynısı |
| `ANTHROPIC_API_KEY` | Hayır (ücretli) | Sözleri Claude yazsın istersen: console.anthropic.com |

`ZERNIO_ACCOUNT_ID` verilmezse otomatik yükleme kapalı kalır (Zernio'da Pipaloo kanalı da olduğu için şarkılar
yanlış kanala gitmesin diye). O zaman videolar Telegram'a gelir, elle yüklersin.

### 2. İlk deneme

1. Actions → **MUSİCAİ bilgi** → Run workflow: Telegram'a "bot bağlandı" mesajı gelmeli.
2. Actions → **ACE-Step hız testi** → Run workflow: 45 saniyelik Türkçe deneme şarkısı Telegram'a gelir,
   üretim süresini de yazar. Türkçe vokali buradan dinleyip karar verirsin.
3. Actions → **MUSİCAİ üretim** → Run workflow (tarz: `anadolu-rock-70s`): ilk gerçek şarkı.

## Ayarlar

- Gün ve saat: `.github/workflows/produce.yml` → `cron` (UTC; `20 13 * * 2,5` = Salı ve Cuma 16:20 TR)
- Yeni tarz: `data/styles.json`a ekle. Sanatçı adı yazma, sesi tarif et.
- Sırada bekleyen tarz: `data/queue.json` (ör. `["phonk", "akustik-pop"]`)
- Dil modeli: varsayılan `1.7B`. Hızlı mod için üretimi elle başlatırken `lm` = `0.6B` ya da `none`

## Yerel deneme (model ve Telegram olmadan)

```bash
pip install -r requirements.txt   # ayrıca ffmpeg
MUSICAI_NO_ART=1 python -m musicai.main --song ornek.json --fake-audio --dry
```

## Dosyalar

- `musicai/writer.py`: söz yazarı, başlık ve açıklama (tek kaynak)
- `musicai/checks.py`: söz bekçisi (yasaklılar, tekrar, hece)
- `musicai/music.py`: ACE-Step ile şarkı üretimi
- `musicai/cover.py`, `musicai/video.py`: kapak ve videolar
- `musicai/telegram.py`, `musicai/approve.py`, `musicai/publish.py`: onay ve YouTube
- `state/songs/`: her şarkının tam paketi (tekrar denetiminin hafızası)

Poppins yazı tipi SIL Open Font License ile dağıtılır (`assets/fonts/OFL.txt`).
