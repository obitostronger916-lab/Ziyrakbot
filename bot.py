import os
import re
import requests
import tempfile
from flask import Flask, request

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})

def send_typing(chat_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction"
    requests.post(url, json={"chat_id": chat_id, "action": "upload_video"})

def send_video(chat_id, video_path, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendVideo"
    with open(video_path, "rb") as f:
        requests.post(url, data={"chat_id": chat_id, "caption": caption}, files={"video": f})

def send_audio(chat_id, audio_path, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendAudio"
    with open(audio_path, "rb") as f:
        requests.post(url, data={"chat_id": chat_id, "caption": caption}, files={"audio": f})

def detect_platform(url):
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    elif "instagram.com" in url:
        return "instagram"
    elif "tiktok.com" in url:
        return "tiktok"
    elif "twitter.com" in url or "x.com" in url:
        return "twitter"
    elif "facebook.com" in url or "fb.watch" in url:
        return "facebook"
    return None

def download_video(url, audio_only=False):
    """yt-dlp orqali video yuklab olish"""
    import yt_dlp

    with tempfile.TemporaryDirectory() as tmpdir:
        if audio_only:
            opts = {
                "format": "bestaudio/best",
                "outtmpl": f"{tmpdir}/%(title)s.%(ext)s",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
                "quiet": True,
                "no_warnings": True,
            }
        else:
            opts = {
                "format": "best[filesize<45M]/best[height<=720]/best",
                "outtmpl": f"{tmpdir}/%(title)s.%(ext)s",
                "quiet": True,
                "no_warnings": True,
                "merge_output_format": "mp4",
            }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get("title", "Video")

                # Fayl topish
                import glob
                files = glob.glob(f"{tmpdir}/*")
                if not files:
                    return None, None

                file_path = files[0]
                file_size = os.path.getsize(file_path)

                # 45MB dan katta bo'lsa
                if file_size > 45 * 1024 * 1024:
                    return None, "size_error"

                # Faylni /tmp ga ko'chirish
                ext = os.path.splitext(file_path)[1]
                dest = f"/tmp/video_{os.getpid()}{ext}"
                import shutil
                shutil.copy2(file_path, dest)
                return dest, title

        except Exception as e:
            error = str(e).lower()
            if "private" in error:
                return None, "private"
            elif "not available" in error:
                return None, "not_available"
            return None, "error"


@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.json
    if "message" not in update:
        return "ok"

    message = update["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    if not text:
        return "ok"

    # /start
    if text == "/start":
        send_message(chat_id,
            "🎬 <b>Video Yuklovchi Bot</b>\n\n"
            "Quyidagi platformalardan video yuklab beraman:\n\n"
            "▶️ YouTube\n"
            "📸 Instagram\n"
            "🎵 TikTok\n"
            "🐦 Twitter / X\n"
            "📘 Facebook\n\n"
            "Shunchaki video linkini yuboring!\n\n"
            "🎵 Faqat audio: /mp3 [link]"
        )
        return "ok"

    # /help
    if text == "/help":
        send_message(chat_id,
            "📖 <b>Yordam</b>\n\n"
            "🔹 Video yuklab olish — linkni yuboring\n"
            "🔹 /mp3 [link] — faqat audio (mp3)\n"
            "🔹 /start — boshlash\n\n"
            "⚠️ Max fayl hajmi: 45MB\n"
            "⚠️ Shaxsiy/yopiq akkaunt videolari yuklanmaydi"
        )
        return "ok"

    # /mp3 buyrug'i
    if text.startswith("/mp3"):
        url = text.replace("/mp3", "").strip()
        if not url:
            send_message(chat_id, "❗ Misol: /mp3 https://youtube.com/...")
            return "ok"

        platform = detect_platform(url)
        if not platform:
            send_message(chat_id, "❌ Noto'g'ri link. YouTube, Instagram, TikTok linklarini yuboring.")
            return "ok"

        send_typing(chat_id)
        send_message(chat_id, "🎵 Audio yuklanmoqda... ⏳")

        file_path, result = download_video(url, audio_only=True)

        if file_path and os.path.exists(file_path):
            try:
                send_audio(chat_id, file_path, f"🎵 {result}")
                os.remove(file_path)
            except Exception:
                send_message(chat_id, "❌ Audio yuborishda xatolik.")
        elif result == "size_error":
            send_message(chat_id, "❌ Fayl juda katta (45MB dan oshiq).")
        elif result == "private":
            send_message(chat_id, "❌ Bu video yopiq/shaxsiy. Yuklab bo'lmadi.")
        else:
            send_message(chat_id, "❌ Yuklab bo'lmadi. Linkni tekshiring.")
        return "ok"

    # Link tekshirish
    url_pattern = re.compile(r'https?://\S+')
    urls = url_pattern.findall(text)

    if not urls:
        send_message(chat_id,
            "📎 Video linkini yuboring!\n\n"
            "Misol:\n"
            "• https://youtube.com/watch?v=...\n"
            "• https://www.tiktok.com/@...\n"
            "• https://www.instagram.com/reel/..."
        )
        return "ok"

    url = urls[0]
    platform = detect_platform(url)

    if not platform:
        send_message(chat_id, "❌ Noto'g'ri link. YouTube, Instagram, TikTok linklarini yuboring.")
        return "ok"

    platform_names = {
        "youtube": "YouTube ▶️",
        "instagram": "Instagram 📸",
        "tiktok": "TikTok 🎵",
        "twitter": "Twitter 🐦",
        "facebook": "Facebook 📘"
    }

    send_typing(chat_id)
    send_message(chat_id, f"⏳ {platform_names[platform]} dan video yuklanmoqda...")

    file_path, result = download_video(url)

    if file_path and os.path.exists(file_path):
        try:
            send_video(chat_id, file_path, f"🎬 {result}")
            os.remove(file_path)
        except Exception:
            send_message(chat_id, "❌ Video yuborishda xatolik. Fayl juda katta bo'lishi mumkin.")
    elif result == "size_error":
        send_message(chat_id, "❌ Video juda katta (45MB dan oshiq).\n\n💡 Sifatini pastroq versiyasini sinab ko'ring.")
    elif result == "private":
        send_message(chat_id, "❌ Bu video yopiq/shaxsiy akkauntda. Yuklab bo'lmadi.")
    elif result == "not_available":
        send_message(chat_id, "❌ Bu video mavjud emas yoki o'chirilgan.")
    else:
        send_message(chat_id, "❌ Yuklab bo'lmadi. Boshqa link bilan sinab ko'ring.")

    return "ok"


@app.route("/")
def index():
    return "Video Yuklovchi Bot ishlamoqda! ✅"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
        
