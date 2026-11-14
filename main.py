import asyncio
import logging
import os
import sqlite3
import uuid
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
import yt_dlp

TOKEN = "9114777347:AAEQzO4hWNGH4JGCVDt8FEto8vq5btWjXXU"  # Ton vrai token BotFather
ADMIN_ID = 7785533633        # ⚠️ Ton ID Telegram (celui qui apparaît dans les logs de polling)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- BASE DE DONNÉES UTILISATEURS & STATS ---
def init_db():
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            downloads_count INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def register_user(user_id, username):
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()

def increment_download(user_id):
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET downloads_count = downloads_count + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_bot_stats():
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(downloads_count) FROM users")
    total_downloads = cursor.fetchone()[0] or 0
    conn.close()
    return total_users, total_downloads

init_db()

# --- COMMANDE START ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    register_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "👋 **Bienvenue sur le meilleur bot de téléchargement universel !**\n\n"
        "🔗 Envoie-moi un lien *(TikTok, YouTube, Instagram, Facebook, etc.)* et choisis ton format :\n\n"
        "💡 *Service gratuit propulsé par nos partenaires.*"
    )

# --- COMMANDE ADMIN /stats ---
@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Commande réservée à l'administrateur.")
        return
    
    users, downloads = get_bot_stats()
    await message.answer(
        f"📊 **Statistiques en direct du Bot :**\n\n"
        f"👥 **Utilisateurs totaux :** `{users}`\n"
        f"📥 **Téléchargements totaux :** `{downloads}`\n\n"
        f"🚀 *Le service tourne à pleine capacité.*"
    )

# --- DETECTION DE LIEN ---
@dp.message(F.text.regexp(r'https?://[^\s]+'))
async def handle_url(message: types.Message):
    register_user(message.from_user.id, message.from_user.username)
    url = message.text.strip()
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📥 Télécharger en Vidéo (MP4)", callback_data=f"dl_video|{url}")
    builder.button(text="🎵 Extraire l'Audio (MP3)", callback_data=f"dl_audio|{url}")
    builder.button(text="📸 Télécharger les Images / Post", callback_data=f"dl_image|{url}")
    builder.adjust(1)

    await message.answer(
        "🎯 **Lien détecté avec succès !**\n\n"
        "Que souhaitez-vous faire ?",
        reply_markup=builder.as_markup()
    )

# --- TRAITEMENT DU TELECHARGEMENT ---
@dp.callback_query(F.data.startswith("dl_"))
async def process_download(callback: types.CallbackQuery):
    action, url = callback.data.split("|", 1)
    await callback.message.edit_text("⏳ **Analyse et téléchargement en cours...**\n*(Patientez quelques secondes)*")
    
    file_id = str(uuid.uuid4())
    output_template = f"%(id)s_{file_id}.%(ext)s"
    
    if action == "dl_video":
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=mp4]/best[ext=mp4]/best',
            'outtmpl': output_template,
            'max_filesize': 50 * 1024 * 1024,
            'noplaylist': True,
        }
    elif action == "dl_audio":
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_template,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'max_filesize': 50 * 1024 * 1024,
            'noplaylist': True,
        }
    else:
        ydl_opts = {
            'format': 'best',
            'outtmpl': output_template,
            'writethumbnail': True,
            'skip_download': False,
            'noplaylist': True,
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
                    for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                        if os.path.exists(base + ext):
                            return base + ext
                    return filename
                return ydl.prepare_filename(info)

        filename = await asyncio.to_thread(download_media)

        await callback.message.edit_text("📤 **Envoi du fichier sur Telegram...**")
        increment_download(callback.from_user.id)
        
        file_input = types.FSInputFile(filename)
        
        ad_caption = (
            "🎥 **Fichier récupéré avec succès !**\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📢 **Annonce Sponsorisée :**\n"
            "Découvrez nos services exclusifs ou partagez ce bot à vos amis pour soutenir le projet !"
        )

        if action == "dl_video":
            await callback.message.answer_video(video=file_input, caption=ad_caption)
        elif action == "dl_audio":
            await callback.message.answer_audio(audio=file_input, caption=ad_caption)
        else:
            await callback.message.answer_photo(photo=file_input, caption=ad_caption)

        if os.path.exists(filename):
            os.remove(filename)
            
        await callback.message.delete()

    except Exception as e:
        await callback.message.edit_text(f"❌ **Impossible de traiter ce lien :** {str(e)}")
        if 'filename' in locals() and os.path.exists(filename):
            os.remove(filename)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())