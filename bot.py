import os
import logging
from dotenv import load_dotenv
import requests
import random
import re  # Добавлено для работы с регулярными выражениями

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.helpers import escape_markdown
from telegram.constants import ParseMode

# Загрузка переменных окружения
load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
NEWS_API_KEY = os.getenv('NEWS_API_KEY')
LLM_API_URL = os.getenv('LLM_API_URL')

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Определение состояний для ConversationHandler
TYPING_LEVEL = range(1)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("beginner"), KeyboardButton("intermediate"), KeyboardButton("advanced")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(
        "Привет! Я ваш Языковой Тренер.\n"
        "Пожалуйста, выберите свой уровень владения языком:",
        reply_markup=reply_markup
    )
    return TYPING_LEVEL

def fetch_news():
    # Запрос к API новостей
    url = f'https://newsapi.org/v2/top-headlines?language=en&apiKey={NEWS_API_KEY}'
    response = requests.get(url)
    data = response.json()
    articles = data.get('articles', [])
    if articles:
        # Выбираем случайную статью
        article = random.choice(articles)
        title = article.get('title', '')
        description = article.get('description', '')
        content = f"{title}\n\n{description}"
        return content
    else:
        return "Не удалось получить новости."

def adapt_text(level, text):
    # Формируем сообщение для LLM
    messages = [
        {"role": "system", "content": "You are an English teacher."},
        {"role": "user", "content": f"Please adapt the following text to a {level} level English learner:\n\n{text}"}
    ]
    payload = {
        'messages': messages,
        'max_tokens': 1000
    }
    headers = {'Content-Type': 'application/json'}
    response = requests.post(LLM_API_URL, json=payload, headers=headers)
    if response.status_code == 200:
        result = response.json()
        adapted_text = result['choices'][0]['message']['content']
        return adapted_text
    else:
        return f"Error adapting text: {response.status_code} - {response.text}"
        
def explain_grammar(text):
    messages = [
        {"role": "system", "content": "You are an English teacher who explains grammar and idioms in Russian."},
        {"role": "user", "content": f"Объясни грамматику и идиомы в следующем английском тексте, предоставив объяснения на русском языке:\n\n{text}"}
    ]
    payload = {
        'messages': messages,
        'max_tokens': 1000
    }
    headers = {'Content-Type': 'application/json'}
    response = requests.post(LLM_API_URL, json=payload, headers=headers)
    if response.status_code == 200:
        result = response.json()
        explanation = result['choices'][0]['message']['content']
        return explanation
    else:
        return f"Ошибка при объяснении грамматики: {response.status_code} - {response.text}"

def create_exercises(text):
    messages = [
        {"role": "system", "content": "You are an English teacher creating exercises."},
        {"role": "user", "content": (
            f"Create exercises based on the following English text suitable for the student's level. "
            f"Number each exercise and provide multiple-choice options or fill-in-the-blank questions, as appropriate. "
            f"After listing all the exercises, provide the correct answers under the heading 'Answers:'. "
            f"Ensure that the answers correspond to the exercises by using the same numbering.\n\n{text}"
        )}
    ]
    payload = {
        'messages': messages,
        'max_tokens': 1500
    }
    headers = {'Content-Type': 'application/json'}
    response = requests.post(LLM_API_URL, json=payload, headers=headers)
    if response.status_code == 200:
        result = response.json()
        exercises_and_answers = result['choices'][0]['message']['content']
        # Разделяем упражнения и ответы с помощью регулярного выражения
        match = re.search(r'(Answers:)', exercises_and_answers, re.IGNORECASE)
        if match:
            split_index = match.start()
            exercises = exercises_and_answers[:split_index].strip()
            answers = exercises_and_answers[split_index:].strip()
            # Удаляем заголовок 'Answers:'
            answers = re.sub(r'Answers:\s*', '', answers, flags=re.IGNORECASE)
        else:
            exercises = exercises_and_answers.strip()
            answers = ''
        return exercises, answers
    else:
        return f"Ошибка при создании упражнений: {response.status_code} - {response.text}", ''

async def received_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    level = update.message.text.lower()
    if level not in ['beginner', 'intermediate', 'advanced']:
        await update.message.reply_text("Пожалуйста, выберите уровень из предложенных вариантов.")
        return TYPING_LEVEL
    context.user_data['level'] = level
    await update.message.reply_text(f"Ваш уровень: {level}. Получаю новости...")
    await process_news(update, context)
    return ConversationHandler.END

async def process_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    level = context.user_data.get('level', 'intermediate')
    news_content = fetch_news()
    adapted_text = adapt_text(level, news_content)
    
    # Определяем, откуда взять объект Message
    if update.message:
        message = update.message
    elif update.callback_query and update.callback_query.message:
        message = update.callback_query.message
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Не могу обработать запрос.")
        return

    await message.reply_text("Адаптированный текст новости:\n")
    await message.reply_text(adapted_text)
    
    # Объяснение грамматики и идиом
    grammar_explanation = explain_grammar(adapted_text)
    await message.reply_text("Объяснение грамматики и идиом:\n")
    await message.reply_text(grammar_explanation)
    
    # Создание упражнений
    exercises, answers = create_exercises(adapted_text)
    await message.reply_text("Упражнения на основе новости:\n")
    await message.reply_text(exercises)
    
    if answers:
        # Разбиваем ответы на отдельные ответы и отправляем каждый в отдельном сообщении под своим спойлером
        answers_list = re.findall(r'^\s*\d+[\).]?\s*.*(?:\n(?!\d+[\).]).*)*', answers, re.MULTILINE)
        if not answers_list:
            # Если не удалось разбить по номерам, то разбиваем по линиям
            answers_list = answers.strip().split('\n')
        
        for answer in answers_list:
            if answer.strip():
                escaped_answer = escape_markdown(answer.strip(), version=2)
                spoiler_answer = f"||{escaped_answer}||"
                await message.reply_text(spoiler_answer, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await message.reply_text("Ответы не были предоставлены.")
    
    # Добавляем кнопку для получения новой новости
    keyboard = [
        [InlineKeyboardButton("Получить новую новость", callback_data='new_article')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(
        "Вы можете получить новую новость, нажав на кнопку ниже.",
        reply_markup=reply_markup
    )

async def new_article_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Получаю новую новость...")
    await process_news(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('До свидания!')
    return ConversationHandler.END

def main():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            TYPING_LEVEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_level)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(new_article_callback, pattern='new_article'))

    application.run_polling()

if __name__ == '__main__':
    main()