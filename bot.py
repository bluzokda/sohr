import os
import logging
from telegram import Update
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext
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

def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text('Привет! Отправь мне фото, и я сохраню его.')

def handle_photo(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    photo_file = update.message.photo[-1].get_file()
    
    # Создаем папку для пользователя
    user_dir = f"photos/user_{user.id}"
    os.makedirs(user_dir, exist_ok=True)
    
    # Генерируем уникальное имя файла
    file_name = f"photo_{update.message.message_id}.jpg"
    file_path = os.path.join(user_dir, file_name)
    
    # Сохраняем фото
    photo_file.download(file_path)
    logger.info(f"Фото сохранено: {file_path}")
    update.message.reply_text('✅ Фото успешно сохранено!')

def error_handler(update: Update, context: CallbackContext) -> None:
    logger.error(f'Ошибка: {context.error}')
    if update.message:
        update.message.reply_text('⚠️ Произошла ошибка при обработке фото')

def main() -> None:
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN не установлен!")
        return

    updater = Updater(TOKEN)
    dp = updater.dispatcher

    # Регистрация обработчиков
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.photo, handle_photo))
    dp.add_error_handler(error_handler)

    # Настройка webhook
    updater.start_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=WEBHOOK_URL + TOKEN
    )
    logger.info(f"Бот запущен на порту {PORT} с webhook: {WEBHOOK_URL}")
    updater.idle()

if __name__ == '__main__':
    main()
