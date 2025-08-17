import os
import logging
import json
from datetime import datetime
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
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
WEBHOOK_URL_BASE = os.environ.get('WEBHOOK_URL', '').rstrip('/')

if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN не установлен в переменных окружения!")

if not WEBHOOK_URL_BASE:
    raise RuntimeError("WEBHOOK_URL не установлен в переменных окружения!")

# Статусы диалога
WAITING_FOR_PHOTO = 0
WAITING_FOR_DATE = 1
WAITING_FOR_DESCRIPTION = 2

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📸 Привет! Отправь мне фото, которое нужно запомнить."
    )
    return WAITING_FOR_PHOTO

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.from_user
    photo_file = await update.message.photo[-1].get_file()

    # Путь: photos/user_12345/photo_67890.jpg
    user_dir = f"photos/user_{user.id}"
    os.makedirs(user_dir, exist_ok=True)

    file_name = f"photo_{update.message.message_id}.jpg"
    file_path = os.path.join(user_dir, file_name)

    await photo_file.download_to_drive(file_path)
    logger.info(f"Фото сохранено: {file_path}")

    context.user_data['photo_path'] = file_path

    await update.message.reply_text(
        "✅ Фото сохранено!\n"
        "📅 Введи дату напоминания в формате: DD.MM.YYYY (например, 01.04.2025)"
    )
    return WAITING_FOR_DATE

async def handle_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        date_obj = datetime.strptime(text, "%d.%m.%Y")
        # Проверим, не в прошлом ли дата
        today = datetime.now().date()
        if date_obj.date() < today:
            await update.message.reply_text("⚠️ Дата уже прошла. Укажи будущую дату.")
            return WAITING_FOR_DATE

        context.user_data['date'] = date_obj.strftime("%d.%m.%Y")
        context.user_data['timestamp'] = date_obj.timestamp()

        await update.message.reply_text("📝 Теперь введи описание (например, 'Контрольная по математике')")
        return WAITING_FOR_DESCRIPTION

    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат даты. Используй: DD.MM.YYYY (например, 01.04.2025)"
        )
        return WAITING_FOR_DATE

async def handle_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    description = update.message.text.strip()
    if len(description) == 0:
        await update.message.reply_text("❌ Описание не может быть пустым. Попробуй ещё раз.")
        return WAITING_FOR_DESCRIPTION

    user_id = update.message.from_user.id
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)
    data_file = os.path.join(data_dir, f"user_{user_id}_notes.json")

    note = {
        "photo_path": context.user_data['photo_path'],
        "date": context.user_data['date'],
        "description": description,
        "timestamp": context.user_data['timestamp']
    }

    # Загружаем старые заметки
    notes = []
    if os.path.exists(data_file):
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                notes = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Не удалось прочитать файл заметок: {e}")

    # Добавляем новую
    notes.append(note)

    # Сохраняем
    try:
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(notes, f, indent=2, ensure_ascii=False)
        logger.info(f"Заметка добавлена: {note}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении заметки: {e}")
        await update.message.reply_text("⚠️ Ошибка при сохранении. Попробуй позже.")
        return ConversationHandler.END

    await update.message.reply_text(
        "🎉 Заметка успешно сохранена!\n"
        f"📅 Дата: {context.user_data['date']}\n"
        f"📄 Описание: {description}\n"
        f"📎 Фото: {os.path.basename(context.user_data['photo_path'])}"
    )

    # Очистка
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Операция отменена.")
    context.user_data.clear()
    return ConversationHandler.END

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"❗ Произошла ошибка: {context.error}", exc_info=True)
    if isinstance(update, Update) and update.message:
        try:
            await update.message.reply_text(
                "❌ Произошла ошибка при обработке. Попробуй начать с /start"
            )
        except:
            pass  # Игнорируем, если не можем отправить

def main() -> None:
    # Проверка токена и URL
    if not TOKEN:
        logger.error("❌ TELEGRAM_TOKEN не установлен!")
        return
    if not WEBHOOK_URL_BASE:
        logger.error("❌ WEBHOOK_URL не установлен!")
        return

    # Создаём приложение
    application = Application.builder().token(TOKEN).build()

    # Диалог: фото → дата → описание
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_FOR_PHOTO: [
                MessageHandler(filters.PHOTO, handle_photo),
                CommandHandler("cancel", cancel)
            ],
            WAITING_FOR_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_date),
                CommandHandler("cancel", cancel)
            ],
            WAITING_FOR_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_description),
                CommandHandler("cancel", cancel)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=True,
    )

    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)

    # Формируем URL вебхука: https://your-app.onrender.com/BOT_TOKEN
    webhook_url = f"{WEBHOOK_URL_BASE}/{TOKEN}"

    logger.info(f"🌍 Webhook URL: {webhook_url}")
    logger.info(f"🔌 Порт: {PORT}")

    # Запуск вебхука
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=webhook_url,
        drop_pending_updates=True,
    )

if __name__ == '__main__':
    main()
