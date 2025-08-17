import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler
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

# Статусы диалога
WAITING_FOR_PHOTO = 0
WAITING_FOR_DATE = 1
WAITING_FOR_DESCRIPTION = 2

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Отправь мне фото, а потом укажи дату и описание.\n"
        "Я сохраню всё и напомню тебе в нужный день."
    )
    return WAITING_FOR_PHOTO

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

    # Запоминаем путь к фото в контексте
    context.user_data['photo_path'] = file_path

    await update.message.reply_text(
        "✅ Фото сохранено!\nТеперь введи дату в формате: DD.MM.YYYY (например, 01.04.2025)"
    )
    return WAITING_FOR_DATE

async def handle_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    try:
        date_obj = datetime.strptime(text, "%d.%m.%Y")
        context.user_data['date'] = date_obj.strftime("%d.%m.%Y")
        context.user_data['date_timestamp'] = date_obj.timestamp()
        await update.message.reply_text("📅 Дата установлена. Теперь введи описание (например, 'Контрольная по математике')")
        return WAITING_FOR_DESCRIPTION
    except ValueError:
        await update.message.reply_text("❌ Неверный формат даты. Используй: DD.MM.YYYY (например, 01.04.2025)")
        return WAITING_FOR_DATE

async def handle_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    description = update.message.text.strip()
    if not description:
        await update.message.reply_text("❌ Описание не может быть пустым. Введи описание.")
        return WAITING_FOR_DESCRIPTION

    context.user_data['description'] = description

    # Сохраняем все данные в файл (например, в JSON)
    user_id = update.message.from_user.id
    data_file = f"data/user_{user_id}_notes.json"

    # Создаём директорию, если нет
    os.makedirs("data", exist_ok=True)

    import json
    note = {
        "photo_path": context.user_data['photo_path'],
        "date": context.user_data['date'],
        "description": description,
        "timestamp": context.user_data['date_timestamp']
    }

    # Добавляем запись в файл
    try:
        if os.path.exists(data_file):
            with open(data_file, 'r') as f:
                notes = json.load(f)
        else:
            notes = []

        notes.append(note)
        with open(data_file, 'w') as f:
            json.dump(notes, f, indent=2, ensure_ascii=False)

        logger.info(f"Заметка сохранена для пользователя {user_id}: {note}")
        await update.message.reply_text(
            f"✅ Заметка сохранена!\n"
            f"Дата: {context.user_data['date']}\n"
            f"Описание: {description}\n"
            f"Фото: {os.path.basename(context.user_data['photo_path'])}"
        )
    except Exception as e:
        logger.error(f"Ошибка при сохранении заметки: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка при сохранении заметки.")

    # Сбрасываем состояние
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f'Ошибка: {context.error}')
    if isinstance(update, Update) and update.message:
        await update.message.reply_text('⚠️ Произошла ошибка при обработке.')

def main() -> None:
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN не установлен!")
        return

    # Создаем приложение
    application = Application.builder().token(TOKEN).build()

    # Обработчик диалога
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_FOR_PHOTO: [MessageHandler(filters.PHOTO, handle_photo)],
            WAITING_FOR_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_date)],
            WAITING_FOR_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_description)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=True,
    )

    # Регистрация обработчиков
    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)

    # Запуск webhook
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
