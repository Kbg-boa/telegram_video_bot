import asyncio
import logging
import glob
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

MAX_TELEGRAM_BYTES = 50 * 1024 * 1024

def cleanup_temp_files(file_token: str):
    for path in glob.glob(f"*{file_token}*"):
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            logging.warning(f"Impossible de supprimer le fichier temporaire : {path}")

def ensure_under_telegram_limit(filepath: str):
    if not filepath or not os.path.exists(filepath):
        raise FileNotFoundError("Fichier t?l?charg? introuvable.")
    size = os.path.getsize(filepath)
    if size > MAX_TELEGRAM_BYTES:
        size_mb = round(size / (1024 * 1024), 1)
        raise ValueError(
            f"Le fichier fait {size_mb} Mo (limite Telegram Bot API : 50 Mo). Essaie le format Audio (MP3) ou un lien plus court."
        )

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

def has_postgres() -> bool:
    return DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")

def get_pg_connection():
    import psycopg
    conn_str = DATABASE_URL
    if "sslmode=" not in conn_str:
        sep = "&" if "?" in conn_str else "?"
        conn_str = f"{conn_str}{sep}sslmode=require"
    return psycopg.connect(conn_str)

def init_pg_db():
    if not has_postgres():
        return
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    is_premium INTEGER DEFAULT 0,
                    downloads_count INTEGER DEFAULT 0,
                    daily_count INTEGER DEFAULT 0,
                    last_reset TEXT,
                    bonus_credits INTEGER DEFAULT 0
                )
            ''')
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS bonus_credits INTEGER DEFAULT 0")
            cur.execute('''
                CREATE TABLE IF NOT EXISTS ads (
                    id SERIAL PRIMARY KEY,
                    title TEXT,
                    text TEXT,
                    url TEXT,
                    btn_text TEXT
                )
            ''')
        conn.commit()

def _sql(query: str) -> str:
    return query.replace("?", "%s") if has_postgres() else query

def db_fetchall(query: str, params: tuple = ()):
    q = _sql(query)
    if has_postgres():
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(q, params)
                return cur.fetchall()
    conn = sqlite3.connect("bot_users.db")
    cur = conn.cursor()
    cur.execute(q, params)
    rows = cur.fetchall()
    conn.close()
    return rows

def db_fetchone(query: str, params: tuple = ()):
    rows = db_fetchall(query, params)
    return rows[0] if rows else None

def db_execute(query: str, params: tuple = ()) -> int:
    q = _sql(query)
    if has_postgres():
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(q, params)
                rc = cur.rowcount
            conn.commit()
            return rc
    conn = sqlite3.connect("bot_users.db")
    cur = conn.cursor()
    cur.execute(q, params)
    rc = cur.rowcount
    conn.commit()
    conn.close()
    return rc

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
    row = db_fetchone("SELECT is_premium, daily_count, bonus_credits FROM users WHERE user_id = ?", (user_id,))
    if not row:
        return True, FREE_DAILY_LIMIT, 0, False
    is_prem, daily_cnt, bonus = row
    bonus = bonus or 0
    daily_cnt = daily_cnt or 0
    if is_prem:
        return True, 999999, bonus, True
    remaining_free = max(0, FREE_DAILY_LIMIT - daily_cnt)
    allowed = (remaining_free + bonus) > 0
    return allowed, remaining_free, bonus, False

def consume_download_quota(user_id):
    refresh_daily_quota(user_id)
    row = db_fetchone("SELECT is_premium, daily_count, bonus_credits FROM users WHERE user_id = ?", (user_id,))
    if row:
        is_prem, daily_cnt, bonus = row
        bonus = bonus or 0
        daily_cnt = daily_cnt or 0
        db_execute("UPDATE users SET downloads_count = downloads_count + 1 WHERE user_id = ?", (user_id,))
        if not is_prem:
            if daily_cnt < FREE_DAILY_LIMIT:
                db_execute("UPDATE users SET daily_count = daily_count + 1 WHERE user_id = ?", (user_id,))
            elif bonus > 0:
                db_execute("UPDATE users SET bonus_credits = bonus_credits - 1 WHERE user_id = ?", (user_id,))

def set_premium_status(user_id, status_int):
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_premium = ? WHERE user_id = ?", (status_int, user_id))
    conn.commit()
    conn.close()

def get_rotating_ad():
    rows = db_fetchall("SELECT title, text, url, btn_text FROM ads")
    if rows:
        chosen = random.choice(rows)
        safe_url = chosen[2] if _is_valid_http_url(chosen[2] or "") else "https://t.me"
        return {
            "title": chosen[0],
            "text": chosen[1],
            "url": safe_url,
            "btn_text": chosen[3],
        }
    return random.choice(DEFAULT_ADS)

def save_new_ad(title, text, url, btn_text):
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM ads")
    cursor.execute("INSERT INTO ads (title, text, url, btn_text) VALUES (?, ?, ?, ?)", (title, text, url, btn_text))
    conn.commit()
    conn.close()

def _is_valid_http_url(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")

def add_ad_entry(title: str, text: str, url: str, btn_text: str):
    safe_url = url if _is_valid_http_url(url) else "https://t.me"
    db_execute(
        "INSERT INTO ads (title, text, url, btn_text) VALUES (?, ?, ?, ?)",
        (title, text, safe_url, btn_text),
    )

def list_ad_entries():
    return db_fetchall("SELECT id, title, url FROM ads ORDER BY id ASC")

def delete_ad_entry(ad_id: int) -> bool:
    return db_execute("DELETE FROM ads WHERE id = ?", (ad_id,)) > 0

def get_rotating_ad():
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT title, text, url, btn_text FROM ads")
    rows = cursor.fetchall()
    conn.close()
    if rows:
        chosen = random.choice(rows)
        safe_url = chosen[2] if _is_valid_http_url(chosen[2] or "") else "https://t.me"
        return {
            "title": chosen[0],
            "text": chosen[1],
            "url": safe_url,
            "btn_text": chosen[3],
        }
    return random.choice(DEFAULT_ADS)

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

@dp.message(Command("myplan"))
async def cmd_myplan(message: types.Message):
    register_user(message.from_user.id, message.from_user.username)
    allowed, rem_free, bonus, is_prem = can_user_download(message.from_user.id)

    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT downloads_count, daily_count FROM users WHERE user_id = ?",
        (message.from_user.id,),
    )
    row = cursor.fetchone()
    conn.close()

    total_dl = row[0] if row else 0
    used_today = row[1] if row else 0

    if is_prem:
        status_block = (
            "?? Statut : Premium (Actif)\n"
            "? T?l?chargements : Illimit?s & sans publicit?"
        )
    else:
        status_block = (
            "🎟️ Statut : Gratuit (Freemium)\n"
            f"📉 Utilis?s aujourd'hui : {used_today}/{FREE_DAILY_LIMIT}\n"
            f"🆓 Gratuits restants aujourd'hui : {rem_free}\n"
            f"🎁 Cr?dits bonus (parrainage) : {bonus}\n"
            f"▶️ Peut t?l?charger maintenant : {'Oui' if allowed else 'Non (quota atteint)'}"
        )

    await message.answer(
        "📋 Mon Espace & Quota\n\n"
        f"{status_block}\n"
        f"📥 Total t?l?charg? : {total_dl}\n\n"
        "💡 /invite pour gagner des cr?dits bonus ? /premium pour passer sans pub"
    )

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

@dp.message(Command("addad"))
async def cmd_addad(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("? Commande r?serv?e ? l'administrateur.")
        return
    raw = (message.text or "").replace("/addad", "", 1).strip()
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 4:
        await message.answer("Usage : /addad Titre | Texte pub | https://lien | Texte bouton")
        return
    add_ad_entry(parts[0], parts[1], parts[2], parts[3])
    await message.answer("? Nouvelle publicit? ajout?e ? la rotation !")

@dp.message(Command("listads"))
async def cmd_listads(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("? Commande r?serv?e ? l'administrateur.")
        return
    rows = list_ad_entries()
    if not rows:
        await message.answer("?? Aucune publicit? en base (rotation sur DEFAULT_ADS).")
        return
    lines = [f"#{r[0]} ? {r[1]} ({r[2]})" for r in rows]
    await message.answer("?? Publicit?s actives :\n\n" + "\n".join(lines))

@dp.message(Command("delad"))
async def cmd_delad(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("? Commande r?serv?e ? l'administrateur.")
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Usage : /delad <id>")
        return
    ok = delete_ad_entry(int(parts[1]))
    await message.answer("? Publicit? supprim?e." if ok else "?? ID de publicit? introuvable.")

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
        ad = get_rotating_ad()
        builder.button(text=ad["btn_text"], url=ad["url"])
    builder.adjust(1)

    ad_block = ""
    if not is_prem:
        ad = get_rotating_ad()
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
        ad = get_rotating_ad()
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
        caption = "🎥 Fichier prêt !" if is_prem else f"🎥 Fichier prêt !\n\n{get_rotating_ad()['title']}"
        if action == "dl_video":
            await callback.message.answer_video(video=file_input, caption=caption)
        elif action == "dl_audio":
            await callback.message.answer_audio(audio=file_input, caption=caption)
        else:
            await callback.message.answer_photo(photo=file_input, caption=caption)
        cleanup_temp_files(file_id)
        await callback.message.delete()
    except Exception as e:
        await callback.message.edit_text(f"❌ Erreur : {str(e)}")
        cleanup_temp_files(file_id)

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
