import os
import logging
import asyncio
import tempfile
import yt_dlp
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

# Настройки для yt-dlp
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'ignoreerrors': True,
}


class YouTubeMusicBot:
    """Бот для поиска и скачивания музыки с YouTube"""

    def __init__(self):
        self.ydl = yt_dlp.YoutubeDL(YDL_OPTIONS)

    def search_youtube(self, query, max_results=10):
        """
        Поиск видео на YouTube
        """
        try:
            search_query = f"ytsearch{max_results}:{query} music audio"

            with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True, 'force_generic_extractor': True}) as ydl:
                results = ydl.extract_info(search_query, download=False)

                tracks = []
                if results and 'entries' in results:
                    for entry in results['entries']:
                        if entry:
                            duration = entry.get('duration', 0)
                            # Пропускаем слишком длинные видео (больше 10 минут)
                            if duration and duration > 600:
                                continue

                            tracks.append({
                                'id': entry.get('id'),
                                'title': entry.get('title'),
                                'artist': self.extract_artist(entry.get('title')),
                                'duration': self.format_duration(duration),
                                'url': f"https://youtube.com/watch?v={entry.get('id')}",
                                'thumbnail': entry.get('thumbnail')
                            })

                return tracks
        except Exception as e:
            logger.error(f"Ошибка при поиске на YouTube: {e}")
            return []

    def extract_artist(self, title):
        """
        Пытается извлечь имя исполнителя из названия
        """
        # Простая эвристика: часто формат "Исполнитель - Название"
        if ' - ' in title:
            parts = title.split(' - ', 1)
            return parts[0].strip()
        return "Unknown Artist"

    def format_duration(self, seconds):
        """
        Форматирует длительность в читаемый вид
        """
        if not seconds:
            return "?:??"
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}:{seconds:02d}"

    def download_audio(self, url):
        """
        Скачивает аудио с YouTube и конвертирует в MP3
        """
        temp_file = None
        try:
            # Создаем временный файл
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp:
                temp_file = tmp.name

            # Настройки для скачивания
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'outtmpl': temp_file.replace('.mp3', ''),
                'quiet': True,
                'no_warnings': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            # Проверяем, существует ли файл
            mp3_file = temp_file
            if os.path.exists(mp3_file):
                return mp3_file
            else:
                # Пробуем найти файл с другим расширением
                base = temp_file.replace('.mp3', '')
                for ext in ['.mp3', '.m4a', '.webm']:
                    if os.path.exists(base + ext):
                        os.rename(base + ext, mp3_file)
                        return mp3_file

            return None

        except Exception as e:
            logger.error(f"Ошибка при скачивании: {e}")
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except:
                    pass
            return None


# Инициализация бота
music_bot = YouTubeMusicBot()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    welcome_message = """
🎵 Добро пожаловать в YouTube Music Bot!

Я помогу вам найти и скачать музыку с YouTube.

Доступные команды:
/search [название] - поиск музыки
/help - показать эту справку

Просто отправьте мне название трека или исполнителя, и я найду музыку!

⚠️ Примечание: Я скачиваю только аудио треки длительностью до 10 минут.
    """
    await update.message.reply_text(welcome_message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """
🎵 YouTube Music Bot - Помощь

Как пользоваться:
1. Отправьте название трека или исполнителя
2. Выберите нужный трек из списка
3. Нажмите на название трека для скачивания

Команды:
/start - начать работу
/search [запрос] - поиск музыки
/help - показать это сообщение

Ограничения:
• Максимальная длительность трека: 10 минут
• Формат: MP3 (192 kbps)
• Размер файла не должен превышать 20 MB

Если бот не отвечает, подождите немного - скачивание может занять время.
    """
    await update.message.reply_text(help_text)


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /search"""
    # Получаем поисковый запрос
    query = ' '.join(context.args) if context.args else None

    if not query:
        await update.message.reply_text(
            "Пожалуйста, укажите поисковый запрос.\n"
            "Пример: /search Imagine Dragons"
        )
        return

    # Отправляем сообщение о начале поиска
    status_message = await update.message.reply_text(f"🔍 Ищу на YouTube: {query}")

    try:
        # Выполняем поиск
        tracks = music_bot.search_youtube(query)

        if not tracks:
            await status_message.edit_text(
                "😕 Ничего не найдено. Попробуйте другой запрос."
            )
            return

        # Сохраняем результаты поиска
        if 'search_results' not in context.user_data:
            context.user_data['search_results'] = {}
        context.user_data['search_results'][query] = tracks

        # Создаем клавиатуру с результатами
        keyboard = []
        for i, track in enumerate(tracks):
            button_text = f"{track['artist']} - {track['title']}"
            if len(button_text) > 40:
                button_text = button_text[:37] + "..."
            callback_data = f"track_{query}_{i}"
            keyboard.append([InlineKeyboardButton(
                f"{button_text} [{track['duration']}]",
                callback_data=callback_data
            )])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await status_message.edit_text(
            f"🔍 Найдено треков: {len(tracks)}\n"
            f"Выберите трек для скачивания:",
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Ошибка в search: {e}")
        await status_message.edit_text(
            "❌ Произошла ошибка при поиске. Попробуйте позже."
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    query = update.message.text.strip()

    if len(query) < 2:
        await update.message.reply_text("Слишком короткий запрос. Минимум 2 символа.")
        return

    # Отправляем статус "печатает"
    await update.message.chat.send_action(action="typing")

    # Перенаправляем на поиск
    context.args = [query]
    await search(update, context)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()

    try:
        data = query.data.split('_')
        action = data[0]

        if action == "track":
            # Пользователь выбрал трек
            search_query = '_'.join(data[1:-1])
            track_index = int(data[-1])

            # Получаем информацию о треке
            search_results = context.user_data.get('search_results', {})
            tracks = search_results.get(search_query)

            if not tracks or track_index >= len(tracks):
                await query.edit_message_text(
                    "❌ Информация о треке устарела. Выполните поиск заново."
                )
                return

            track = tracks[track_index]

            # Отправляем сообщение о начале загрузки
            await query.edit_message_text(
                f"📥 Скачиваю с YouTube:\n"
                f"🎵 {track['artist']} - {track['title']}\n"
                f"⏱ Длительность: {track['duration']}\n"
                f"⏳ Пожалуйста, подождите... Это может занять до минуты."
            )

            # Отправляем статус "загружает аудио"
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action="upload_audio"
            )

            # Скачиваем аудио
            file_path = music_bot.download_audio(track['url'])

            if file_path and os.path.exists(file_path):
                try:
                    # Отправляем аудиофайл
                    with open(file_path, 'rb') as audio_file:
                        await context.bot.send_audio(
                            chat_id=update.effective_chat.id,
                            audio=audio_file,
                            title=track['title'],
                            performer=track['artist'],
                            caption=f"🎵 {track['artist']} - {track['title']}\n"
                                    f"⏱ Длительность: {track['duration']}\n"
                                    f"🔗 Источник: YouTube"
                        )

                    # Возвращаем результаты поиска
                    await query.delete()

                except Exception as e:
                    logger.error(f"Ошибка при отправке аудио: {e}")
                    await query.edit_message_text(
                        "❌ Ошибка при отправке файла. Попробуйте другой трек."
                    )
                finally:
                    # Удаляем временный файл
                    try:
                        os.unlink(file_path)
                    except:
                        pass
            else:
                await query.edit_message_text(
                    "❌ Ошибка при скачивании. Возможно, трек слишком длинный или защищен авторскими правами.\n"
                    "Попробуйте другой трек."
                )

    except Exception as e:
        logger.error(f"Ошибка в button_callback: {e}")
        await query.edit_message_text(
            "❌ Произошла ошибка. Попробуйте еще раз."
        )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")

    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Произошла внутренняя ошибка. Попробуйте позже."
            )
        except:
            pass


def main():
    """Главная функция запуска бота"""
    if not TELEGRAM_TOKEN:
        logger.error("❌ Не указан TELEGRAM_TOKEN в переменных окружения!")
        logger.error("Создайте файл .env и добавьте строку: TELEGRAM_TOKEN=ваш_токен")
        return

    # Проверяем наличие ffmpeg
    import shutil
    if not shutil.which('ffmpeg'):
        logger.warning("⚠️ FFmpeg не найден! Установите FFmpeg для конвертации аудио.")
        logger.warning("Скачайте с: https://ffmpeg.org/download.html")
        logger.warning("Или используйте: pip install ffmpeg-python")

    # Создаем приложение
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("search", search))

    # Обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Обработчик нажатий на кнопки
    application.add_handler(CallbackQueryHandler(button_callback))

    # Обработчик ошибок
    application.add_error_handler(error_handler)

    # Запускаем бота
    logger.info("✅ Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()