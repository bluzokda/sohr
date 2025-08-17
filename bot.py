import os
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = os.environ.get('TELEGRAM_TOKEN')
PORT = int(os.environ.get('PORT', 8443))
WEBHOOK_URL = os.environ.get('WEBHOOK_URL') + '/'

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Привет! Отправь мне фото, и я сохраню его.')

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.message.from_user
    photo_file = await update.message.photo[-1].get_file()
    
    # Создаем папку для пользователя
    user_dir = f"photos/user_{user.id}"
    os.makedirs(user_dir, exist_ok=True)
    
    # Генерируем уникальное имя файла
    file_name = f"photo_{update.message.message_id}.jpg"
    file_path = os.path.join(user_dir, file_name)
    
    # Сохраняем фото
    await photo_file.download_to_drive(file_path)
    logger.info(f"Фото сохранено: {file_path}")
    await update.message.reply_text('✅ Фото успешно сохранено!')

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f'Ошибка: {context.error}')
    if isinstance(update, Update) and update.message:
        await update.message.reply_text('⚠️ Произошла ошибка при обработке фото')

def main() -> None:
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN не установлен!")
        return

    # Создаем приложение без JobQueue
    application = Application.builder().token(TOKEN).build()
    
    # Отключаем JobQueue
    application.job_queue.scheduler = None
    application.job_queue.start = lambda: None
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_error_handler(error_handler)

    # Настройка webhook
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=WEBHOOK_URL + TOKEN,
        drop_pending_updates=True
    )
    logger.info(f"Бот запущен на порту {PORT} с webhook: {WEBHOOK_URL}")

if __name__ == '__main__':
    main()
