import os
import logging
import json
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
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
WAITING_FOR_DELETE_NUMBER = 3

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
    keyboard = [
        [InlineKeyboardButton("🆘 Помощь", callback_data="help_command")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📸 Привет! Отправь мне фото, которое нужно запомнить.\n\n"
        "ℹ️ Для справки используй /help",
        reply_markup=reply_markup
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
        today = datetime.now().date()
        
        context.user_data['date'] = date_obj.strftime("%d.%m.%Y")
        context.user_data['timestamp'] = date_obj.timestamp()
        context.user_data['is_past'] = date_obj.date() < today

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
        "created_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "is_past": context.user_data.get('is_past', False)
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

    # Определяем статус даты для сообщения
    date_status = "📅 Дата: " + context.user_data['date']
    if note['is_past']:
        date_status += " (прошедшая дата)"

    await update.message.reply_text(
        "🎉 Заметка успешно сохранена!\n"
        f"{date_status}\n"
        f"📄 Описание: {description}\n"
        f"📎 Фото: {os.pathasename(context.user_data['photo_path'])}"
    )

    # Очистка
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Операция отменена.")
    context.user_data.clear()
    return ConversationHandler.END

# Обработчик команды /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📚 <b>Справка по командам бота:</b>\n\n"
        "🆘 /help - Показать эту справку\n"
        "📸 /start - Начать сохранение нового фото\n"
        "📚 /archive - Показать архив сохраненных фото\n"
        "🗑️ /delete - Удалить фото по номеру\n\n"
        "ℹ️ <b>Как использовать:</b>\n"
        "1. Отправь фото с помощью /start\n"
        "2. Укажи дату напоминания в формате ДД.ММ.ГГГГ\n"
        "3. Добавь описание\n\n"
        "📚 В архиве (/archive) ты можешь:\n"
        "- Просматривать все сохраненные фото\n"
        "- Удалять ненужные фото\n"
        "- Переключаться между фото\n\n"
        "⚙️ Бот автоматически напомнит о событии в указанную дату!"
    )
    
    keyboard = [
        [InlineKeyboardButton("🆘 Помощь", callback_data="help_command"),
         InlineKeyboardButton("📚 Архив", callback_data="view_archive")],
        [InlineKeyboardButton("📸 Начать сохранение", callback_data="start_saving")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(help_text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(help_text, parse_mode="HTML", reply_markup=reply_markup)

# Обработчик команды /archive
async def show_archive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    notes = load_user_notes(user_id)
    
    if not notes:
        keyboard = [
            [InlineKeyboardButton("📸 Начать сохранение", callback_data="start_saving")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📭 У вас пока нет сохраненных напоминаний.",
            reply_markup=reply_markup
        )
        return
    
    # Сортируем по дате напоминания (от новых к старым)
    notes = sorted(notes, key=lambda x: x['timestamp'], reverse=True)
    
    # Сохраняем заметки для навигации
    context.user_data['archive_notes'] = notes
    
    # Формируем список для отображения с отметкой о прошедших датах
    archive_list = []
    for i, note in enumerate(notes, 1):
        status = "✅" if not note.get('is_past', False) else "⌛"
        date_info = f"{note['date']} {status}"
        
        archive_list.append(
            f"{i}. {date_info}\n"
            f"   📝 {note['description']}\n"
            f"   🕒 Сохранено: {note['created_at']}"
        )
    
    # Добавляем кнопки для просмотра фото и удаления
    keyboard = [
        [InlineKeyboardButton("👀 Просмотреть фото", callback_data="view_photos")],
        [InlineKeyboardButton("🗑️ Удалить фото", callback_data="delete_photo_prompt")],
        [InlineKeyboardButton("🆘 Помощь", callback_data="help_command")]
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
    notes = context.user_data.get('archive_notes', load_user_notes(user_id))
    
    if not notes:
        keyboard = [
            [InlineKeyboardButton("📸 Начать сохранение", callback_data="start_saving")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📭 У вас пока нет сохраненных напоминаний.",
            reply_markup=reply_markup
        )
        return
    
    # Сортируем по дате (от новых к старым)
    notes = sorted(notes, key=lambda x: x['timestamp'], reverse=True)
    
    # Сохраняем заметки и создаем меню выбора
    context.user_data['archive_notes'] = notes
    
    # Создаем клавиатуру с номерами фото
    keyboard = []
    row = []
    for i in range(len(notes)):
        row.append(InlineKeyboardButton(str(i+1), callback_data=f"select_photo_{i}"))
        if len(row) == 5:  # 5 кнопок в строке
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([
        InlineKeyboardButton("🆘 Помощь", callback_data="help_command"),
        InlineKeyboardButton("❌ Закрыть", callback_data="close_viewer")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📸 Выберите номер фото для просмотра:",
        reply_markup=reply_markup
    )

# Обработчик выбора конкретной фотки
async def select_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    photo_index = int(data.split('_')[-1])
    notes = context.user_data['archive_notes']
    
    if photo_index < 0 or photo_index >= len(notes):
        await query.answer("⚠️ Неверный номер фото!")
        return
    
    context.user_data['archive_index'] = photo_index
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
    
    keyboard.append(InlineKeyboardButton(f"{index+1}/{len(notes)}", callback_data="photo_index"))
    
    if index < len(notes) - 1:
        keyboard.append(InlineKeyboardButton("Вперед ➡️", callback_data="next_photo"))
    
    keyboard_rows = [keyboard]
    keyboard_rows.append([
        InlineKeyboardButton("🗑️ Удалить", callback_data="delete_current_photo"),
        InlineKeyboardButton("🆘 Помощь", callback_data="help_command"),
        InlineKeyboardButton("❌ Закрыть", callback_data="close_viewer")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard_rows)
    
    # Добавляем статус даты в описание
    date_status = "📅 Дата: " + note['date']
    if note.get('is_past', False):
        date_status += " (прошедшая)"
    
    try:
        with open(note['photo_path'], 'rb') as photo:
            # Удаляем предыдущее сообщение с фото, если есть
            if 'photo_message_id' in context.user_data:
                try:
                    await context.bot.delete_message(
                        chat_id=message.chat_id,
                        message_id=context.user_data['photo_message_id']
                    )
                except:
                    pass
            
            # Отправляем новое фото
            sent_message = await message.reply_photo(
                photo=photo,
                caption=f"{date_status}\n"
                        f"📝 Описание: {note['description']}\n"
                        f"🕒 Сохранено: {note['created_at']}",
                reply_markup=reply_markup
            )
            context.user_data['photo_message_id'] = sent_message.message_id
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
        try:
            await query.message.delete()
        except:
            pass
        return
    
    await send_photo_from_archive(query.message, context)

# Обработчик команды /delete
async def delete_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    notes = load_user_notes(user_id)
    
    if not notes:
        await update.message.reply_text("📭 У вас пока нет сохраненных фото.")
        return
    
    # Сохраняем заметки для удаления
    context.user_data['delete_notes'] = notes
    
    # Формируем список для выбора
    archive_list = []
    for i, note in enumerate(notes, 1):
        archive_list.append(f"{i}. {note['description']} ({note['date']})")
    
    keyboard = [
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_delete")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🗑️ Введите номер фото для удаления:\n\n" + "\n".join(archive_list),
        reply_markup=reply_markup
    )
    
    return WAITING_FOR_DELETE_NUMBER

# Обработчик ввода номера для удаления
async def handle_delete_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    user_id = update.message.from_user.id
    
    try:
        note_index = int(text) - 1
        notes = context.user_data['delete_notes']
        
        if note_index < 0 or note_index >= len(notes):
            await update.message.reply_text("❌ Неверный номер. Попробуйте снова.")
            return WAITING_FOR_DELETE_NUMBER
        
        # Удаляем файл фото
        photo_path = notes[note_index]['photo_path']
        try:
            os.remove(photo_path)
            logger.info(f"Фото удалено: {photo_path}")
        except OSError as e:
            logger.error(f"Ошибка удаления фото: {e}")
        
        # Удаляем заметку
        deleted_note = notes.pop(note_index)
        
        # Сохраняем обновленный список
        data_file = os.path.join("data", f"user_{user_id}_notes.json")
        try:
            with open(data_file, 'w', encoding='utf-8') as f:
                json.dump(notes, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Ошибка сохранения после удаления: {e}")
            await update.message.reply_text("⚠️ Ошибка при удалении. Попробуйте позже.")
            return ConversationHandler.END
        
        await update.message.reply_text(
            f"✅ Фото удалено:\n"
            f"📅 Дата: {deleted_note['date']}\n"
            f"📝 Описание: {deleted_note['description']}"
        )
        
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("❌ Пожалуйста, введите число.")
        return WAITING_FOR_DELETE_NUMBER

# Обработчик удаления текущей фотки из просмотра
async def delete_current_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    notes = context.user_data['archive_notes']
    index = context.user_data['archive_index']
    
    if index < 0 or index >= len(notes):
        await query.answer("⚠️ Неверный номер фото!")
        return
    
    # Удаляем файл фото
    photo_path = notes[index]['photo_path']
    try:
        os.remove(photo_path)
        logger.info(f"Фото удалено: {photo_path}")
    except OSError as e:
        logger.error(f"Ошибка удаления фото: {e}")
    
    # Удаляем заметку
    deleted_note = notes.pop(index)
    
    # Сохраняем обновленный список
    data_file = os.path.join("data", f"user_{user_id}_notes.json")
    try:
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(notes, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Ошибка сохранения после удаления: {e}")
        await query.answer("⚠️ Ошибка при удалении. Попробуйте позже.")
        return
    
    # Обновляем контекст
    context.user_data['archive_notes'] = notes
    
    if not notes:
        await query.message.delete()
        keyboard = [
            [InlineKeyboardButton("📸 Начать сохранение", callback_data="start_saving")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="✅ Фото удалено. В архиве больше нет фото.",
            reply_markup=reply_markup
        )
        return
    
    # Корректируем индекс
    if index >= len(notes):
        context.user_data['archive_index'] = len(notes) - 1
    
    # Показываем следующее фото или закрываем просмотр
    if notes:
        await send_photo_from_archive(query.message, context)
    else:
        await query.message.delete()
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="✅ Фото удалено. В архиве больше нет фото."
        )

# Обработчик кнопки отмены удаления
async def cancel_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    await query.message.reply_text("❌ Удаление отменено.")

# Обработчик кнопки "Начать сохранение"
async def start_saving(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context)

# Обработчик кнопки "Просмотреть архив"
async def view_archive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_archive(update, context)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"❗ Произошла ошибка: {context.error}", exc_info=True)
    if isinstance(update, Update) and update.message:
        try:
            await update.message.reply_text(
                "❌ Произошла ошибка при обработке. Попробуй начать с /help"
            )
        except:
            pass

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
            WAITING_FOR_DELETE_NUMBER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_delete_number),
                CommandHandler("cancel", cancel)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=True,
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("archive", show_archive))
    application.add_handler(CommandHandler("delete", delete_photo))
    
    # Обработчики callback-кнопок
    application.add_handler(CallbackQueryHandler(help_command, pattern="^help_command$"))
    application.add_handler(CallbackQueryHandler(view_photos, pattern="^view_photos$"))
    application.add_handler(CallbackQueryHandler(select_photo, pattern=r"^select_photo_\d+$"))
    application.add_handler(CallbackQueryHandler(handle_photo_navigation, pattern="^(prev_photo|next_photo|close_viewer)$"))
    application.add_handler(CallbackQueryHandler(delete_current_photo, pattern="^delete_current_photo$"))
    application.add_handler(CallbackQueryHandler(delete_photo, pattern="^delete_photo_prompt$"))
    application.add_handler(CallbackQueryHandler(cancel_delete, pattern="^cancel_delete$"))
    application.add_handler(CallbackQueryHandler(start_saving, pattern="^start_saving$"))
    application.add_handler(CallbackQueryHandler(view_archive, pattern="^view_archive$"))
    
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
