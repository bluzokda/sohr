import os
import logging
import json
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
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

# Функция для загрузки заметок пользователя
def load_user_notes(user_id: int) -> list:
    data_dir = "data"
    data_file = os.path.join(data_dir, f"user_{user_id}_notes.json")
    
    if not os.path.exists(data_file):
        return []
    
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Ошибка загрузки заметок: {e}")
        return []

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
        "timestamp": context.user_data['timestamp'],
        "created_at": datetime.now().strftime("%d.%m.%Y %H:%M")
    }

    # Загружаем старые заметки
    notes = load_user_notes(user_id)

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

# Обработчик команды /archive
async def show_archive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    notes = load_user_notes(user_id)
    
    if not notes:
        await update.message.reply_text("📭 У вас пока нет сохраненных напоминаний.")
        return
    
    # Сортируем по дате напоминания
    notes = sorted(notes, key=lambda x: x['timestamp'])
    
    # Формируем список для отображения
    archive_list = []
    for i, note in enumerate(notes, 1):
        archive_list.append(
            f"{i}. 📅 {note['date']}\n"
            f"   📝 {note['description']}\n"
            f"   🕒 Сохранено: {note['created_at']}"
        )
    
    # Добавляем кнопку для просмотра фото
    keyboard = [
        [InlineKeyboardButton("👀 Просмотреть фото", callback_data="view_photos")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📚 Ваш архив напоминаний:\n\n" + "\n\n".join(archive_list),
        reply_markup=reply_markup
    )

# Обработчик кнопки просмотра фото
async def view_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    notes = load_user_notes(user_id)
    
    if not notes:
        await query.edit_message_text("📭 У вас пока нет сохраненных напоминаний.")
        return
    
    # Отправляем первое фото
    context.user_data['archive_index'] = 0
    context.user_data['archive_notes'] = notes
    
    await send_photo_from_archive(query.message, context)

# Функция отправки фото из архива
async def send_photo_from_archive(message, context: ContextTypes.DEFAULT_TYPE):
    notes = context.user_data['archive_notes']
    index = context.user_data['archive_index']
    note = notes[index]
    
    # Создаем клавиатуру навигации
    keyboard = []
    if index > 0:
        keyboard.append(InlineKeyboardButton("⬅️ Назад", callback_data="prev_photo"))
    
    keyboard.append(InlineKeyboardButton(f"{index+1}/{len(notes)}", callback_data="counter"))
    
    if index < len(notes) - 1:
        keyboard.append(InlineKeyboardButton("Вперед ➡️", callback_data="next_photo"))
    
    keyboard_rows = [keyboard]
    keyboard_rows.append([InlineKeyboardButton("❌ Закрыть просмотр", callback_data="close_viewer")])
    
    reply_markup = InlineKeyboardMarkup(keyboard_rows)
    
    try:
        with open(note['photo_path'], 'rb') as photo:
            await message.reply_photo(
                photo=photo,
                caption=f"📅 Дата: {note['date']}\n"
                        f"📝 Описание: {note['description']}\n"
                        f"🕒 Сохранено: {note['created_at']}",
                reply_markup=reply_markup
            )
    except FileNotFoundError:
        await message.reply_text("⚠️ Фото не найдено. Возможно, оно было удалено.")

# Обработчик навигации по фото
async def handle_photo_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    notes = context.user_data['archive_notes']
    index = context.user_data['archive_index']
    
    if data == "prev_photo" and index > 0:
        context.user_data['archive_index'] -= 1
    elif data == "next_photo" and index < len(notes) - 1:
        context.user_data['archive_index'] += 1
    elif data == "close_viewer":
        await query.message.delete()
        return
    
    # Удаляем предыдущее сообщение с фото
    try:
        await query.message.delete()
    except Exception as e:
        logger.error(f"Ошибка при удалении сообщения: {e}")
    
    # Отправляем новое фото
    await send_photo_from_archive(query.message, context)

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
    application.add_handler(CommandHandler("archive", show_archive))
    application.add_handler(CallbackQueryHandler(view_photos, pattern="^view_photos$"))
    application.add_handler(CallbackQueryHandler(handle_photo_navigation, pattern="^(prev_photo|next_photo|close_viewer)$"))
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
