import asyncio
import logging
import os
import random
import sqlite3
import uuid
from datetime import date
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.types import LabeledPrice, PreCheckoutQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
import yt_dlp

TOKEN = os.environ.get("TOKEN", "9114777347:AAEIdalqbeGRl6cyqqSwCSkYTL6x7MzUx1I")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "7785533633"))
FREE_DAILY_LIMIT = int(os.environ.get("FREE_DAILY_LIMIT", "3"))
REFERRAL_BONUS = int(os.environ.get("REFERRAL_BONUS", "2"))
PREMIUM_STARS_PRICE = int(os.environ.get("PREMIUM_STARS_PRICE", "50"))
PREMIUM_PAY_URL = os.environ.get("PREMIUM_PAY_URL", "")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

async def handle(request):
    return web.Response(text="Bot is running and alive 24/7!")

app = web.Application()
app.router.add_get("/", handle)
async_runner = web.AppRunner(app)

DEFAULT_ADS = [
    {
        "title": "📢 Sponsorisé — Offre Partenaire",
        "text": "Découvre nos services exclusifs ou partage le bot à tes amis pour débloquer plus de téléchargements !",
        "url": "https://t.me",
        "btn_text": "🔗 Découvrir l'annonce"
    }
]

PENDING_URLS = {}

def store_pending_url(url: str) -> str:
    key = uuid.uuid4().hex[:12]
    if len(PENDING_URLS) > 2000:
        PENDING_URLS.clear()
    PENDING_URLS[key] = url
    return key

def init_db():
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            downloads_count INTEGER DEFAULT 0,
            daily_count INTEGER DEFAULT 0,
            bonus_credits INTEGER DEFAULT 0,
            last_reset TEXT,
            is_premium INTEGER DEFAULT 0,
            referred_by INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            text TEXT,
            url TEXT,
            btn_text TEXT
        )
    """)
    cursor.execute("SELECT COUNT(*) FROM ads")
    if cursor.fetchone()[0] == 0:
        for ad in DEFAULT_ADS:
            cursor.execute(
                "INSERT INTO ads (title, text, url, btn_text) VALUES (?, ?, ?, ?)",
                (ad["title"], ad["text"], ad["url"], ad["btn_text"])
            )
    cursor.execute("PRAGMA table_info(users)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    migrations = {
        "daily_count": "INTEGER DEFAULT 0",
        "bonus_credits": "INTEGER DEFAULT 0",
        "last_reset": "TEXT",
        "is_premium": "INTEGER DEFAULT 0",
        "referred_by": "INTEGER",
    }
    for col_name, col_def in migrations.items():
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")
    conn.commit()
    conn.close()

def register_user(user_id, username, ref_id=None):
    today_str = date.today().isoformat()
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, referred_by FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        valid_ref = ref_id if (ref_id and ref_id != user_id) else None
        cursor.execute(
            """INSERT INTO users (user_id, username, daily_count, bonus_credits, last_reset, is_premium, referred_by)
               VALUES (?, ?, 0, 0, ?, 0, ?)""",
            (user_id, username, today_str, valid_ref)
        )
        if valid_ref:
            cursor.execute(
                "UPDATE users SET bonus_credits = bonus_credits + ? WHERE user_id = ?",
                (REFERRAL_BONUS, valid_ref)
            )
    else:
        cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
    conn.commit()
    conn.close()

def refresh_daily_quota(user_id):
    today_str = date.today().isoformat()
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT last_reset FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row and row[0] != today_str:
        cursor.execute("UPDATE users SET daily_count = 0, last_reset = ? WHERE user_id = ?", (today_str, user_id))
        conn.commit()
    conn.close()

def can_user_download(user_id):
    refresh_daily_quota(user_id)
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT is_premium, daily_count, bonus_credits FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return True, FREE_DAILY_LIMIT, 0, False
    is_prem, daily_cnt, bonus = row
    if is_prem:
        return True, 999999, bonus, True
    remaining_free = max(0, FREE_DAILY_LIMIT - daily_cnt)
    allowed = (remaining_free + bonus) > 0
    return allowed, remaining_free, bonus, False

def consume_download_quota(user_id):
    refresh_daily_quota(user_id)
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT is_premium, daily_count, bonus_credits FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        is_prem, daily_cnt, bonus = row
        cursor.execute("UPDATE users SET downloads_count = downloads_count + 1 WHERE user_id = ?", (user_id,))
        if not is_prem:
            if daily_cnt < FREE_DAILY_LIMIT:
                cursor.execute("UPDATE users SET daily_count = daily_count + 1 WHERE user_id = ?", (user_id,))
            elif bonus > 0:
                cursor.execute("UPDATE users SET bonus_credits = bonus_credits - 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def set_premium_status(user_id, status_int):
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_premium = ? WHERE user_id = ?", (status_int, user_id))
    conn.commit()
    conn.close()

def get_active_ad():
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT title, text, url, btn_text FROM ads ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"title": row[0], "text": row[1], "url": row[2], "btn_text": row[3]}
    return random.choice(DEFAULT_ADS)

def save_new_ad(title, text, url, btn_text):
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM ads")
    cursor.execute("INSERT INTO ads (title, text, url, btn_text) VALUES (?, ?, ?, ?)", (title, text, url, btn_text))
    conn.commit()
    conn.close()

def get_bot_stats():
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(downloads_count) FROM users")
    total_downloads = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1")
    total_premium = cursor.fetchone()[0] or 0
    conn.close()
    return total_users, total_downloads, total_premium

init_db()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    logging.info(f"/start recu de user_id={message.from_user.id} (@{message.from_user.username})")
    ref_id = None
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 2 and parts[1].startswith("ref_"):
        try:
            ref_id = int(parts[1].replace("ref_", "", 1))
        except ValueError:
            ref_id = None
    register_user(message.from_user.id, message.from_user.username, ref_id=ref_id)
    allowed, rem_free, bonus, is_prem = can_user_download(message.from_user.id)
    quota_line = (
        "👑 Statut : Premium (Illimité, sans pub)"
        if is_prem
        else f"🎟️ Crédits restants : {rem_free} gratuits/jour + {bonus} bonus parrainage"
    )
    try:
        await message.answer(
            "👋 Bienvenue sur le bot de téléchargement !\n\n"
            "🔗 Envoie un lien (TikTok, YouTube, Instagram, Facebook, etc.) pour commencer.\n"
            f"{quota_line}\n\n"
            "💡 Tape /invite pour parrainer ou /premium pour passer sans pub."
        )
    except Exception:
        logging.exception("Erreur envoi reponse /start")

@dp.message(Command("invite"))
async def cmd_invite(message: types.Message):
    register_user(message.from_user.id, message.from_user.username)
    me = await bot.get_me()
    ref_link = f"https://t.me/{me.username}?start=ref_{message.from_user.id}"
    await message.answer(
        "🎁 Parrainage — Invite to Unlock\n\n"
        f"Partage ton lien à tes amis : chaque nouvel inscrit te rapporte +{REFERRAL_BONUS} téléchargements bonus !\n\n"
        f"{ref_link}"
    )

@dp.message(Command("premium"))
async def cmd_premium(message: types.Message):
    try:
        builder = InlineKeyboardBuilder()
        if PREMIUM_PAY_URL:
            builder.button(text="💳 Lien de paiement externe", url=PREMIUM_PAY_URL)
            builder.adjust(1)
        await message.answer_invoice(
            title="Accès Premium Sans Pub",
            description="Téléchargements illimités et suppression des publicités.",
            payload=f"premium_{message.from_user.id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="Premium", amount=PREMIUM_STARS_PRICE)],
            reply_markup=builder.as_markup() if PREMIUM_PAY_URL else None,
        )
    except Exception as e:
        logging.exception("Erreur answer_invoice /premium")
        await message.answer(f"❌ Erreur lors de l'ouverture du paiement : {e}")

@dp.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@dp.message(F.successful_payment)
async def on_successful_payment(message: types.Message):
    set_premium_status(message.from_user.id, 1)
    await message.answer("🎉 Merci ! Ton compte est maintenant Premium (sans pub et illimité).")

@dp.message(Command("setpremium"))
async def cmd_setpremium(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Commande réservée à l'administrateur.")
        return
    parts = (message.text or "").split()
    if len(parts) != 3 or parts[2] not in ("0", "1"):
        await message.answer("Usage : /setpremium <user_id> <1|0>")
        return
    target_id = int(parts[1])
    status_val = int(parts[2])
    set_premium_status(target_id, status_val)
    await message.answer(f"✅ Utilisateur {target_id} mis à jour : is_premium = {status_val}")

@dp.message(Command("setad"))
async def cmd_setad(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Commande réservée à l'administrateur.")
        return
    raw = (message.text or "").replace("/setad", "", 1).strip()
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 4:
        await message.answer("Usage : /setad Titre | Texte pub | https://lien | Texte bouton")
        return
    save_new_ad(parts[0], parts[1], parts[2], parts[3])
    await message.answer("✅ Publicité mise à jour en direct !")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Commande réservée à l'administrateur.")
        return
    users, downloads, prem = get_bot_stats()
    await message.answer(
        "📊 Statistiques en direct :\n\n"
        f"👥 Utilisateurs : {users}\n"
        f"👑 Membres Premium : {prem}\n"
        f"📥 Téléchargements : {downloads}"
    )

@dp.message(F.text.regexp(r"https?://[^\s]+"))
async def handle_url(message: types.Message):
    register_user(message.from_user.id, message.from_user.username)
    allowed, rem_free, bonus, is_prem = can_user_download(message.from_user.id)
    if not allowed:
        me = await bot.get_me()
        ref_link = f"https://t.me/{me.username}?start=ref_{message.from_user.id}"
        kb = InlineKeyboardBuilder()
        kb.button(text="🎁 Inviter des amis (/invite)", url=ref_link)
        kb.button(text="⭐ Passer Premium (/premium)", callback_data="show_premium_info")
        kb.adjust(1)
        await message.answer(
            "⛔ Quota journalier atteint !\n\n"
            f"Tu as utilisé tes {FREE_DAILY_LIMIT} téléchargements gratuits du jour et tes crédits bonus.\n"
            f"Invite des amis pour gagner +{REFERRAL_BONUS} crédits ou passe en Premium :\n{ref_link}",
            reply_markup=kb.as_markup()
        )
        return

    url = message.text.strip()
    url_key = store_pending_url(url)
    builder = InlineKeyboardBuilder()
    builder.button(text="📥 Vidéo (MP4)", callback_data=f"dl_video|{url_key}")
    builder.button(text="🎵 Audio (MP3)", callback_data=f"dl_audio|{url_key}")
    builder.button(text="📸 Image / Post", callback_data=f"dl_image|{url_key}")
    if not is_prem:
        ad = get_active_ad()
        builder.button(text=ad["btn_text"], url=ad["url"])
    builder.adjust(1)

    ad_block = ""
    if not is_prem:
        ad = get_active_ad()
        ad_block = f"\n\n━━━━━━━━━━━━━━━━━━━━\n{ad['title']}\n{ad['text']}"

    await message.answer(
        "🎯 Lien détecté ! Choisis ton format :" + ad_block,
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data == "show_premium_info")
async def cb_premium_info(callback: types.CallbackQuery):
    await callback.answer()
    await cmd_premium(callback.message)

@dp.callback_query(F.data.startswith("dl_"))
async def process_download(callback: types.CallbackQuery):
    allowed, _, _, is_prem = can_user_download(callback.from_user.id)
    if not allowed:
        await callback.answer("Quota atteint. Tape /invite ou /premium.", show_alert=True)
        return

    if not is_prem:
        ad = get_active_ad()
        await callback.message.edit_text(
            f"{ad['title']}\n{ad['text']}\n\n⏳ Annonce affichée — préparation du téléchargement..."
        )
        await asyncio.sleep(2)

    action, url_key = callback.data.split("|", 1)
    url = PENDING_URLS.get(url_key)
    if not url:
        await callback.message.edit_text("⚠️ Ce lien a expiré (redémarrage du serveur). Renvoie le lien SVP.")
        return

    await callback.message.edit_text("⏳ Téléchargement en cours...")
    file_id = str(uuid.uuid4())
    output_template = f"%(id)s_{file_id}.%(ext)s"

    if action == "dl_video":
        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=mp4]/best[ext=mp4]/best",
            "outtmpl": output_template,
            "max_filesize": 50 * 1024 * 1024,
            "noplaylist": True,
        }
    elif action == "dl_audio":
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
            "max_filesize": 50 * 1024 * 1024,
            "noplaylist": True,
        }
    else:
        ydl_opts = {
            "format": "best",
            "outtmpl": output_template,
            "writethumbnail": True,
            "skip_download": False,
            "noplaylist": True,
        }

    try:
        def download_media():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if action == "dl_audio":
                    filename = ydl.prepare_filename(info)
                    return os.path.splitext(filename)[0] + ".mp3"
                elif action == "dl_image":
                    filename = ydl.prepare_filename(info)
                    base, _ = os.path.splitext(filename)
                    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
                        if os.path.exists(base + ext):
                            return base + ext
                    return filename
                return ydl.prepare_filename(info)

        filename = await asyncio.to_thread(download_media)
        await callback.message.edit_text("📤 Envoi sur Telegram...")
        consume_download_quota(callback.from_user.id)
        file_input = types.FSInputFile(filename)
        caption = "🎥 Fichier prêt !" if is_prem else f"🎥 Fichier prêt !\n\n{get_active_ad()['title']}"
        if action == "dl_video":
            await callback.message.answer_video(video=file_input, caption=caption)
        elif action == "dl_audio":
            await callback.message.answer_audio(audio=file_input, caption=caption)
        else:
            await callback.message.answer_photo(photo=file_input, caption=caption)
        if os.path.exists(filename):
            os.remove(filename)
        await callback.message.delete()
    except Exception as e:
        await callback.message.edit_text(f"❌ Erreur : {str(e)}")
        if "filename" in locals() and os.path.exists(filename):
            os.remove(filename)

async def main():
    port = int(os.environ.get("PORT", 10000))
    await async_runner.setup()
    site = web.TCPSite(async_runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Web server started on port {port}")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
