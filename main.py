import asyncio
import glob
import logging
import os
import random
import sqlite3
import uuid
from datetime import date

import yt_dlp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.types import LabeledPrice, PreCheckoutQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web

TOKEN = os.environ["TOKEN"]
ADMIN_ID = int(os.environ.get("ADMIN_ID", "7785533633") or "7785533633")
FREE_DAILY_LIMIT = int(os.environ.get("FREE_DAILY_LIMIT", "3"))
REFERRAL_BONUS = int(os.environ.get("REFERRAL_BONUS", "2"))
PREMIUM_STARS_PRICE = int(os.environ.get("PREMIUM_STARS_PRICE", "50"))
PREMIUM_PAY_URL = os.environ.get("PREMIUM_PAY_URL", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
INSTAGRAM_COOKIES_FILE = os.environ.get("INSTAGRAM_COOKIES_FILE", "").strip()
TIKTOK_PROXY = os.environ.get("TIKTOK_PROXY", "").strip()

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
        "btn_text": "🔗 Découvrir l'annonce",
    }
]

TEXTS = {
    "fr": {
        "welcome": (
            "👋 Bienvenue sur le bot de téléchargement !\n\n"
            "🔗 Envoie un lien (TikTok sans filigrane, YouTube, Instagram, Facebook, etc.) pour commencer.\n"
            "{quota_line}\n\n"
            "💡 Tape /invite pour parrainer, /premium pour passer sans pub ou /lang pour changer de langue."
        ),
        "quota_free": "🎟️ Crédits restants : {rem_free} gratuits/jour + {bonus} bonus parrainage",
        "quota_prem": "👑 Statut : Premium (Illimité, sans pub)",
        "myplan_title": "📋 Mon Espace & Quota",
        "myplan_prem": (
            "👑 Statut : Premium (Actif)\n"
            "♾️ Téléchargements : Illimités & sans publicité"
        ),
        "myplan_free": (
            "🎟️ Statut : Gratuit (Freemium)\n"
            "📉 Utilisés aujourd'hui : {used_today}/{limit}\n"
            "🆓 Gratuits restants aujourd'hui : {rem_free}\n"
            "🎁 Crédits bonus (parrainage) : {bonus}\n"
            "▶️ Peut télécharger maintenant : {can_dl}"
        ),
        "yes": "Oui",
        "no_quota": "Non (quota atteint)",
        "total_dl": "📥 Total téléchargé : {total_dl}",
        "myplan_footer": "💡 /invite pour gagner des crédits bonus • /premium pour passer sans pub",
        "invite_text": (
            "🎁 Parrainage — Invite to Unlock\n\n"
            "Partage ton lien à tes amis : chaque nouvel inscrit te rapporte +{bonus} téléchargements bonus !\n\n"
            "{ref_link}"
        ),
        "prem_title": "Accès Premium Sans Pub",
        "prem_desc": "Téléchargements illimités et suppression des publicités.",
        "prem_ext_btn": "💳 Lien de paiement externe",
        "prem_error": "❌ Erreur lors de l'ouverture du paiement : {err}",
        "prem_success": "🎉 Merci ! Ton compte est maintenant Premium (sans pub et illimité).",
        "quota_reached": (
            "⛔ Quota journalier atteint !\n\n"
            "Tu as utilisé tes {limit} téléchargements gratuits du jour et tes crédits bonus.\n"
            "Invite des amis pour gagner +{bonus} crédits ou passe en Premium :\n{ref_link}"
        ),
        "btn_invite": "🎁 Inviter des amis (/invite)",
        "btn_premium": "⭐ Passer Premium (/premium)",
        "choose_format": "🎯 Lien détecté ! Choisis ton format :",
        "btn_video": "📥 Vidéo (MP4)",
        "btn_audio": "🎵 Audio (MP3)",
        "btn_image": "📸 Image / Post",
        "quota_alert": "Quota atteint. Tape /invite ou /premium.",
        "ad_preparing": "{ad_title}\n{ad_text}\n\n⏳ Annonce affichée — préparation du téléchargement...",
        "link_expired": "⚠️ Ce lien a expiré (redémarrage du serveur). Renvoie le lien SVP.",
        "downloading": "⏳ Téléchargement en cours...",
        "uploading": "📤 Envoi sur Telegram...",
        "file_ready": "🎥 Fichier prêt !",
        "file_not_found": "Fichier téléchargé introuvable.",
        "file_too_large": (
            "Le fichier fait {size_mb} Mo (limite Telegram Bot API : 50 Mo). "
            "Essaie le format Audio (MP3) ou un lien plus court."
        ),
        "tiktok_blocked": (
            "⚠️ TikTok a bloqué temporairement cette requête (protection anti-bot ou IP serveur).\n\n"
            "Réessaie avec un autre lien TikTok ou teste un autre lien (YouTube, Instagram, etc.), "
            "ou réessaie plus tard."
        ),
        "error_prefix": "❌ Erreur : {err}",
        "lang_prompt": "🌐 Choisis ta langue / Choose your language :",
        "lang_updated": "✅ Langue mise à jour : Français.",
    },
    "en": {
        "welcome": (
            "👋 Welcome to the video downloader bot!\n\n"
            "🔗 Send a link (watermark-free TikTok, YouTube, Instagram, Facebook, etc.) to get started.\n"
            "{quota_line}\n\n"
            "💡 Type /invite to earn bonus credits, /premium to go ad-free, or /lang to switch language."
        ),
        "quota_free": "🎟️ Remaining credits: {rem_free} free/day + {bonus} referral bonus",
        "quota_prem": "👑 Status: Premium (Unlimited, ad-free)",
        "myplan_title": "📋 My Space & Quota",
        "myplan_prem": (
            "👑 Status: Premium (Active)\n"
            "♾️ Downloads: Unlimited & ad-free"
        ),
        "myplan_free": (
            "🎟️ Status: Free (Freemium)\n"
            "📉 Used today: {used_today}/{limit}\n"
            "🆓 Free left today: {rem_free}\n"
            "🎁 Bonus credits (referrals): {bonus}\n"
            "▶️ Can download now: {can_dl}"
        ),
        "yes": "Yes",
        "no_quota": "No (quota reached)",
        "total_dl": "📥 Total downloaded: {total_dl}",
        "myplan_footer": "💡 /invite to earn bonus credits • /premium to go ad-free",
        "invite_text": (
            "🎁 Referrals — Invite to Unlock\n\n"
            "Share your link with friends: every new user earns you +{bonus} bonus downloads!\n\n"
            "{ref_link}"
        ),
        "prem_title": "Ad-Free Premium Access",
        "prem_desc": "Unlimited downloads and ads removed.",
        "prem_ext_btn": "💳 External payment link",
        "prem_error": "❌ Error opening checkout: {err}",
        "prem_success": "🎉 Thank you! Your account is now Premium (unlimited & ad-free).",
        "quota_reached": (
            "⛔ Daily quota reached!\n\n"
            "You have used your {limit} daily free downloads and your bonus credits.\n"
            "Invite friends to earn +{bonus} credits or upgrade to Premium:\n{ref_link}"
        ),
        "btn_invite": "🎁 Invite friends (/invite)",
        "btn_premium": "⭐ Go Premium (/premium)",
        "choose_format": "🎯 Link detected! Choose your format:",
        "btn_video": "📥 Video (MP4)",
        "btn_audio": "🎵 Audio (MP3)",
        "btn_image": "📸 Image / Post",
        "quota_alert": "Quota reached. Type /invite or /premium.",
        "ad_preparing": "{ad_title}\n{ad_text}\n\n⏳ Ad shown — preparing download...",
        "link_expired": "⚠️ This link expired (server restarted). Please send the link again.",
        "downloading": "⏳ Downloading...",
        "uploading": "📤 Uploading to Telegram...",
        "file_ready": "🎥 File ready!",
        "file_not_found": "Downloaded file not found.",
        "file_too_large": (
            "The file is {size_mb} MB (Telegram Bot API limit: 50 MB). "
            "Try Audio (MP3) or a shorter link."
        ),
        "tiktok_blocked": (
            "⚠️ TikTok temporarily blocked this request (anti-bot protection or server IP).\n\n"
            "Try another TikTok link or test another platform (YouTube, Instagram, etc.), "
            "or try again later."
        ),
        "error_prefix": "❌ Error: {err}",
        "lang_prompt": "🌐 Choisis ta langue / Choose your language:",
        "lang_updated": "✅ Language updated: English.",
    },
}

USER_LANG_OVERRIDE: dict[int, str] = {}


def get_user_lang(user: types.User | None) -> str:
    if user and user.id in USER_LANG_OVERRIDE:
        return USER_LANG_OVERRIDE[user.id]
    code = ((user.language_code if user else None) or "en")[:2].lower()
    return code if code in TEXTS else "en"


def tr(lang: str, key: str, **kwargs) -> str:
    template = TEXTS.get(lang, TEXTS["en"]).get(key) or TEXTS["en"].get(key, key)
    return template.format(**kwargs) if kwargs else template


PENDING_URLS = {}
MAX_TELEGRAM_BYTES = 50 * 1024 * 1024


def store_pending_url(url: str) -> str:
    key = uuid.uuid4().hex[:12]
    if len(PENDING_URLS) > 2000:
        PENDING_URLS.clear()
    PENDING_URLS[key] = url
    return key


def cleanup_temp_files(file_token: str):
    for path in glob.glob(f"*{file_token}*"):
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            logging.warning(f"Impossible de supprimer le fichier temporaire : {path}")


def ensure_under_telegram_limit(filepath: str, lang: str = "en"):
    if not filepath or not os.path.exists(filepath):
        raise FileNotFoundError(tr(lang, "file_not_found"))
    size = os.path.getsize(filepath)
    if size > MAX_TELEGRAM_BYTES:
        size_mb = round(size / (1024 * 1024), 1)
        raise ValueError(tr(lang, "file_too_large", size_mb=size_mb))


def format_download_error(err_msg: str, lang: str = "en") -> str:
    lowered = (err_msg or "").lower()
    is_tiktok_block = (
        "[tiktok]" in lowered or "tiktok" in lowered
    ) and (
        "unexpected response from webpage request" in lowered
        or "confirm you are on the latest version" in lowered
        or "unable to extract" in lowered
        or "captcha" in lowered
        or "blocked" in lowered
        or "403" in lowered
    )
    if is_tiktok_block:
        return tr(lang, "tiktok_blocked")
    return tr(lang, "error_prefix", err=err_msg)


def build_ydl_opts(action: str, url: str, output_template: str) -> dict:
    opts = {
        "outtmpl": output_template,
        "max_filesize": MAX_TELEGRAM_BYTES,
        "noplaylist": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 20,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
            ),
            "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
        },
    }

    if "youtube.com" in url or "youtu.be" in url:
        opts["extractor_args"] = {"youtube": {"player_client": ["web_safari", "mweb"]}}

    if "instagram.com" in url and INSTAGRAM_COOKIES_FILE and os.path.exists(INSTAGRAM_COOKIES_FILE):
        opts["cookiefile"] = INSTAGRAM_COOKIES_FILE

    if "tiktok.com" in url:
        opts.pop("http_headers", None)
        opts["verbose"] = True
        opts["quiet"] = False
        opts["no_warnings"] = False

        logging.info(
            "TikTok diagnostic: verbose=True, proxy_configured=%s",
            bool(TIKTOK_PROXY)
        )

        if TIKTOK_PROXY:
            opts["proxy"] = TIKTOK_PROXY

    if action == "dl_video":
        opts["format"] = (
            "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo[height<=720]+bestaudio/"
            "best[height<=720]/best"
        )
        opts["merge_output_format"] = "mp4"
    elif action == "dl_audio":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
    else:
        opts["format"] = "best"
        opts["writethumbnail"] = True
        opts["skip_download"] = False

    return opts


def has_postgres() -> bool:
    return DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")


def get_pg_connection():
    import psycopg

    conn_str = DATABASE_URL
    if "sslmode=" not in conn_str:
        sep = "&" if "?" in conn_str else "?"
        conn_str = f"{conn_str}{sep}sslmode=require"
    return psycopg.connect(conn_str)


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


def _is_valid_http_url(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def init_pg_db():
    with get_pg_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    is_premium INTEGER DEFAULT 0,
                    downloads_count INTEGER DEFAULT 0,
                    daily_count INTEGER DEFAULT 0,
                    last_reset TEXT,
                    bonus_credits INTEGER DEFAULT 0,
                    referred_by BIGINT
                )
                """
            )
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS bonus_credits INTEGER DEFAULT 0")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ads (
                    id SERIAL PRIMARY KEY,
                    title TEXT,
                    text TEXT,
                    url TEXT,
                    btn_text TEXT
                )
                """
            )
            cur.execute("ALTER TABLE ads ADD COLUMN IF NOT EXISTS text TEXT")
            cur.execute("ALTER TABLE ads ADD COLUMN IF NOT EXISTS btn_text TEXT")
            cur.execute("SELECT COUNT(*) FROM ads")
            if cur.fetchone()[0] == 0:
                for ad in DEFAULT_ADS:
                    cur.execute(
                        "INSERT INTO ads (title, text, url, btn_text) VALUES (%s, %s, %s, %s)",
                        (ad["title"], ad["text"], ad["url"], ad["btn_text"]),
                    )
        conn.commit()


def init_sqlite_db():
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute(
        """
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
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            text TEXT,
            url TEXT,
            btn_text TEXT
        )
        """
    )
    cursor.execute("SELECT COUNT(*) FROM ads")
    if cursor.fetchone()[0] == 0:
        for ad in DEFAULT_ADS:
            cursor.execute(
                "INSERT INTO ads (title, text, url, btn_text) VALUES (?, ?, ?, ?)",
                (ad["title"], ad["text"], ad["url"], ad["btn_text"]),
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


def init_db():
    if has_postgres():
        init_pg_db()
    else:
        init_sqlite_db()


def register_user(user_id, username, ref_id=None):
    today_str = date.today().isoformat()
    row = db_fetchone("SELECT user_id, referred_by FROM users WHERE user_id = ?", (user_id,))
    if not row:
        valid_ref = ref_id if (ref_id and ref_id != user_id) else None
        db_execute(
            """
            INSERT INTO users (user_id, username, daily_count, bonus_credits, last_reset, is_premium, referred_by)
            VALUES (?, ?, 0, 0, ?, 0, ?)
            """,
            (user_id, username, today_str, valid_ref),
        )
        if valid_ref:
            db_execute(
                "UPDATE users SET bonus_credits = bonus_credits + ? WHERE user_id = ?",
                (REFERRAL_BONUS, valid_ref),
            )
    else:
        db_execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))


def refresh_daily_quota(user_id):
    today_str = date.today().isoformat()
    row = db_fetchone("SELECT last_reset FROM users WHERE user_id = ?", (user_id,))
    if row and row[0] != today_str:
        db_execute(
            "UPDATE users SET daily_count = 0, last_reset = ? WHERE user_id = ?",
            (today_str, user_id),
        )


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
    db_execute("UPDATE users SET is_premium = ? WHERE user_id = ?", (status_int, user_id))


def save_new_ad(title, text, url, btn_text):
    safe_url = url if _is_valid_http_url(url) else "https://t.me"
    db_execute("DELETE FROM ads")
    db_execute(
        "INSERT INTO ads (title, text, url, btn_text) VALUES (?, ?, ?, ?)",
        (title, text, safe_url, btn_text),
    )


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
    rows = db_fetchall("SELECT title, text, url, btn_text FROM ads")
    if rows:
        chosen = random.choice(rows)
        safe_url = chosen[2] if _is_valid_http_url(chosen[2] or "") else "https://t.me"
        return {
            "title": chosen[0],
            "text": chosen[1],
            "url": safe_url,
            "btn_text": chosen[3] or "🔗 Découvrir l'annonce",
        }
    return random.choice(DEFAULT_ADS)


def get_bot_stats():
    r_users = db_fetchone("SELECT COUNT(*) FROM users")
    r_dl = db_fetchone("SELECT SUM(downloads_count) FROM users")
    r_prem = db_fetchone("SELECT COUNT(*) FROM users WHERE is_premium = 1")
    total_users = r_users[0] if r_users else 0
    total_downloads = (r_dl[0] if r_dl and r_dl[0] is not None else 0)
    total_premium = r_prem[0] if r_prem else 0
    return total_users, total_downloads, total_premium


@dp.message(Command("lang"))
async def cmd_lang(message: types.Message):
    lang = get_user_lang(message.from_user)
    kb = InlineKeyboardBuilder()
    kb.button(text="🇫🇷 Français", callback_data="setlang_fr")
    kb.button(text="🇬🇧 English", callback_data="setlang_en")
    kb.adjust(2)
    await message.answer(tr(lang, "lang_prompt"), reply_markup=kb.as_markup())


@dp.callback_query(F.data.startswith("setlang_"))
async def cb_setlang(callback: types.CallbackQuery):
    chosen = callback.data.split("_", 1)[1]
    if chosen in TEXTS and callback.from_user:
        USER_LANG_OVERRIDE[callback.from_user.id] = chosen
    lang = get_user_lang(callback.from_user)
    await callback.answer()
    await callback.message.edit_text(tr(lang, "lang_updated"))


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    lang = get_user_lang(message.from_user)
    logging.info(f"/start recu de user_id={message.from_user.id} (@{message.from_user.username}) lang={lang}")
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
        tr(lang, "quota_prem")
        if is_prem
        else tr(lang, "quota_free", rem_free=rem_free, bonus=bonus)
    )
    try:
        await message.answer(tr(lang, "welcome", quota_line=quota_line))
    except Exception:
        logging.exception("Erreur envoi reponse /start")


@dp.message(Command("myplan"))
async def cmd_myplan(message: types.Message):
    lang = get_user_lang(message.from_user)
    register_user(message.from_user.id, message.from_user.username)
    allowed, rem_free, bonus, is_prem = can_user_download(message.from_user.id)

    row = db_fetchone(
        "SELECT downloads_count, daily_count FROM users WHERE user_id = ?",
        (message.from_user.id,),
    )
    total_dl = row[0] if row else 0
    used_today = row[1] if row else 0

    if is_prem:
        status_block = tr(lang, "myplan_prem")
    else:
        can_dl_str = tr(lang, "yes") if allowed else tr(lang, "no_quota")
        status_block = tr(
            lang,
            "myplan_free",
            used_today=used_today,
            limit=FREE_DAILY_LIMIT,
            rem_free=rem_free,
            bonus=bonus,
            can_dl=can_dl_str,
        )

    await message.answer(
        f"{tr(lang, 'myplan_title')}\n\n"
        f"{status_block}\n"
        f"{tr(lang, 'total_dl', total_dl=total_dl)}\n\n"
        f"{tr(lang, 'myplan_footer')}"
    )


@dp.message(Command("invite"))
async def cmd_invite(message: types.Message):
    lang = get_user_lang(message.from_user)
    register_user(message.from_user.id, message.from_user.username)
    me = await bot.get_me()
    ref_link = f"https://t.me/{me.username}?start=ref_{message.from_user.id}"
    await message.answer(tr(lang, "invite_text", bonus=REFERRAL_BONUS, ref_link=ref_link))


@dp.message(Command("premium"))
async def cmd_premium(message: types.Message):
    lang = get_user_lang(message.from_user)
    try:
        builder = InlineKeyboardBuilder()
        if PREMIUM_PAY_URL:
            builder.button(text=tr(lang, "prem_ext_btn"), url=PREMIUM_PAY_URL)
            builder.adjust(1)
        await message.answer_invoice(
            title=tr(lang, "prem_title"),
            description=tr(lang, "prem_desc"),
            payload=f"premium_{message.from_user.id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="Premium", amount=PREMIUM_STARS_PRICE)],
            reply_markup=builder.as_markup() if PREMIUM_PAY_URL else None,
        )
    except Exception as e:
        logging.exception("Erreur answer_invoice /premium")
        await message.answer(tr(lang, "prem_error", err=e))


@dp.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@dp.message(F.successful_payment)
async def on_successful_payment(message: types.Message):
    lang = get_user_lang(message.from_user)
    set_premium_status(message.from_user.id, 1)
    await message.answer(tr(lang, "prem_success"))


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
        await message.answer("❌ Commande réservée à l'administrateur.")
        return
    raw = (message.text or "").replace("/addad", "", 1).strip()
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 4:
        await message.answer("Usage : /addad Titre | Texte pub | https://lien | Texte bouton")
        return
    add_ad_entry(parts[0], parts[1], parts[2], parts[3])
    await message.answer("✅ Nouvelle publicité ajoutée à la rotation !")


@dp.message(Command("listads"))
async def cmd_listads(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Commande réservée à l'administrateur.")
        return
    rows = list_ad_entries()
    if not rows:
        await message.answer("📭 Aucune publicité en base (rotation sur DEFAULT_ADS).")
        return
    lines = [f"#{r[0]} • {r[1]} ({r[2]})" for r in rows]
    await message.answer("📢 Publicités actives :\n\n" + "\n".join(lines))


@dp.message(Command("delad"))
async def cmd_delad(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Commande réservée à l'administrateur.")
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Usage : /delad <id>")
        return
    ok = delete_ad_entry(int(parts[1]))
    await message.answer("✅ Publicité supprimée." if ok else "⚠️ ID de publicité introuvable.")


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
    lang = get_user_lang(message.from_user)
    register_user(message.from_user.id, message.from_user.username)
    allowed, _, _, is_prem = can_user_download(message.from_user.id)
    if not allowed:
        me = await bot.get_me()
        ref_link = f"https://t.me/{me.username}?start=ref_{message.from_user.id}"
        kb = InlineKeyboardBuilder()
        kb.button(text=tr(lang, "btn_invite"), url=ref_link)
        kb.button(text=tr(lang, "btn_premium"), callback_data="show_premium_info")
        kb.adjust(1)
        await message.answer(
            tr(lang, "quota_reached", limit=FREE_DAILY_LIMIT, bonus=REFERRAL_BONUS, ref_link=ref_link),
            reply_markup=kb.as_markup(),
        )
        return

    url = message.text.strip()
    url_key = store_pending_url(url)
    builder = InlineKeyboardBuilder()
    builder.button(text=tr(lang, "btn_video"), callback_data=f"dl_video|{url_key}")
    builder.button(text=tr(lang, "btn_audio"), callback_data=f"dl_audio|{url_key}")
    builder.button(text=tr(lang, "btn_image"), callback_data=f"dl_image|{url_key}")
    ad_block = ""
    if not is_prem:
        ad = get_rotating_ad()
        builder.button(text=ad["btn_text"], url=ad["url"])
        ad_block = f"\n\n━━━━━━━━━━━━━━━━━━━━\n{ad['title']}\n{ad['text']}"
    builder.adjust(1)

    await message.answer(
        tr(lang, "choose_format") + ad_block,
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data == "show_premium_info")
async def cb_premium_info(callback: types.CallbackQuery):
    await callback.answer()
    await cmd_premium(callback.message)


@dp.callback_query(F.data.startswith("dl_"))
async def process_download(callback: types.CallbackQuery):
    lang = get_user_lang(callback.from_user)
    allowed, _, _, is_prem = can_user_download(callback.from_user.id)
    if not allowed:
        await callback.answer(tr(lang, "quota_alert"), show_alert=True)
        return

    if not is_prem:
        ad = get_rotating_ad()
        await callback.message.edit_text(
            tr(lang, "ad_preparing", ad_title=ad["title"], ad_text=ad["text"])
        )
        await asyncio.sleep(2)

    action, url_key = callback.data.split("|", 1)
    url = PENDING_URLS.get(url_key)
    if not url:
        await callback.message.edit_text(tr(lang, "link_expired"))
        return

    await callback.message.edit_text(tr(lang, "downloading"))
    file_id = str(uuid.uuid4())
    output_template = f"%(id)s_{file_id}.%(ext)s"
    ydl_opts = build_ydl_opts(action, url, output_template)

    try:
        def download_media():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if action == "dl_audio":
                    filename = ydl.prepare_filename(info)
                    return os.path.splitext(filename)[0] + ".mp3"
                if action == "dl_image":
                    filename = ydl.prepare_filename(info)
                    base, _ = os.path.splitext(filename)
                    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
                        if os.path.exists(base + ext):
                            return base + ext
                    return filename
                return ydl.prepare_filename(info)

        filename = await asyncio.to_thread(download_media)
        ensure_under_telegram_limit(filename, lang=lang)
        await callback.message.edit_text(tr(lang, "uploading"))
        consume_download_quota(callback.from_user.id)
        file_input = types.FSInputFile(filename)
        ready_text = tr(lang, "file_ready")
        caption = ready_text if is_prem else f"{ready_text}\n\n{get_rotating_ad()['title']}"
        if action == "dl_video":
            await callback.message.answer_video(video=file_input, caption=caption)
        elif action == "dl_audio":
            await callback.message.answer_audio(audio=file_input, caption=caption)
        else:
            await callback.message.answer_photo(photo=file_input, caption=caption)
        await callback.message.delete()
    except Exception as e:
        logging.exception("Erreur pendant le t?l?chargement (file_id=%s)", file_id)
        await callback.message.edit_text(format_download_error(str(e), lang=lang))
    finally:
        cleanup_temp_files(file_id)


async def main():
    init_db()
    port = int(os.environ.get("PORT", 10000))
    await async_runner.setup()
    site = web.TCPSite(async_runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Web server started on port {port}")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
