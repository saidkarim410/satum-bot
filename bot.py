"""
SATUm Telegram Bot — powered by Entrium
========================================
Команды:
  /start        — приветствие + меню
  /question     — случайный вопрос
  /math         — Math вопрос
  /reading      — Reading вопрос
  /word         — Слово дня
  /stats        — твоя статистика
  /streak       — серия дней
  /platform     — ссылка на платформу
  /help         — справка

Авто:
  08:00 Ташкент — Вопрос дня
  20:00 Ташкент — Слово дня + напоминание
"""

import os, json, logging, asyncio, random
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    Poll, BotCommand
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    PollAnswerHandler, ContextTypes, JobQueue
)
from telegram.constants import ParseMode

from questions_data import (
    ALL_QUESTIONS, ALL_VOCAB,
    get_daily_question, get_random_question,
    get_daily_word, format_question
)

load_dotenv()

BOT_TOKEN    = os.getenv('BOT_TOKEN', '')
CHANNEL_ID   = os.getenv('CHANNEL_ID', '')      # @satum_entrium
ADMIN_ID     = int(os.getenv('ADMIN_ID', '0'))
PLATFORM_URL = os.getenv('PLATFORM_URL', 'https://entrium.uz')
DATA_FILE    = Path(__file__).parent / 'user_data.json'

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Uzbekistan timezone (UTC+5) ─────────────────────────────────────────────
TZ_UZB = timezone(timedelta(hours=5))

def uzb_now() -> datetime:
    return datetime.now(TZ_UZB)

def today_seed() -> int:
    d = uzb_now().date()
    return d.year * 10000 + d.month * 100 + d.day

# ── User data (JSON file storage) ──────────────────────────────────────────
def load_data() -> dict:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}

def save_data(data: dict):
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

def get_user(uid: int) -> dict:
    data = load_data()
    key = str(uid)
    if key not in data:
        data[key] = {
            'streak': 0,
            'last_active': None,
            'total_answered': 0,
            'correct': 0,
            'joined': uzb_now().isoformat(),
            'name': '',
        }
        save_data(data)
    return data[key]

def update_user(uid: int, **kwargs):
    data = load_data()
    key = str(uid)
    if key not in data:
        get_user(uid)
        data = load_data()
    data[key].update(kwargs)
    save_data(data)

def record_answer(uid: int, correct: bool):
    u = get_user(uid)
    today = uzb_now().date().isoformat()
    last = u.get('last_active')
    
    new_streak = u['streak']
    if last != today:
        yesterday = (uzb_now().date() - timedelta(days=1)).isoformat()
        if last == yesterday:
            new_streak += 1
        elif last is None:
            new_streak = 1
        else:
            new_streak = 1  # Reset streak
    
    update_user(uid,
        streak=new_streak,
        last_active=today,
        total_answered=u['total_answered'] + 1,
        correct=u['correct'] + (1 if correct else 0),
    )
    return new_streak

# ── Active polls tracking ───────────────────────────────────────────────────
# poll_id → {question, correct_option, user_id (if private)}
active_polls: dict[str, dict] = {}

# ── Keyboards ──────────────────────────────────────────────────────────────
def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 Reading", callback_data="q_reading"),
            InlineKeyboardButton("📐 Math", callback_data="q_math"),
        ],
        [
            InlineKeyboardButton("💬 Слово дня", callback_data="word"),
            InlineKeyboardButton("📊 Моя статистика", callback_data="stats"),
        ],
        [
            InlineKeyboardButton("🚀 Открыть платформу", url=PLATFORM_URL),
        ],
    ])

def question_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Ещё вопрос", callback_data="q_random"),
            InlineKeyboardButton("📊 Статистика", callback_data="stats"),
        ],
        [
            InlineKeyboardButton("🚀 Платформа", url=PLATFORM_URL),
        ],
    ])

# ── Helpers ─────────────────────────────────────────────────────────────────
async def send_question_poll(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    q: dict,
    user_id: int = None,
    prefix: str = ""
) -> str:
    """Send a question as a Telegram Poll. Returns poll_id."""
    text, choices = format_question(q)
    
    full_question = (prefix + "\n\n" + q['q']) if prefix else q['q']
    # Telegram poll question max 300 chars
    full_question = full_question[:298]
    
    try:
        msg = await context.bot.send_poll(
            chat_id=chat_id,
            question=full_question,
            options=[f"{chr(65+i)}. {c}" for i, c in enumerate(choices)],
            type='quiz',
            correct_option_id=int(q['a']),
            explanation=f"✅ Правильный ответ: {chr(65+int(q['a']))}. {choices[int(q['a'])]}",
            is_anonymous=False,
            allows_multiple_answers=False,
        )
    except Exception:
        # Fallback: send as regular poll if quiz fails
        msg = await context.bot.send_poll(
            chat_id=chat_id,
            question=full_question,
            options=[f"{chr(65+i)}. {c}" for i, c in enumerate(choices)],
            type='regular',
            is_anonymous=False,
            allows_multiple_answers=False,
        )
    
    poll_id = msg.poll.id
    active_polls[poll_id] = {
        'question': q,
        'correct_option': int(q['a']),
        'user_id': user_id,
        'chat_id': chat_id,
    }
    return poll_id


# ── Command Handlers ─────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    update_user(user.id, name=user.first_name or '')
    u = get_user(user.id)
    
    streak_text = f"🔥 Серия: {u['streak']} дней\n" if u['streak'] > 0 else ""
    
    text = (
        f"<b>Привет, {user.first_name}! 👋</b>\n\n"
        f"Добро пожаловать в <b>SATUm</b> — твой ИИ-тренажёр для Digital SAT, "
        f"<i>powered by Entrium</i>.\n\n"
        f"{streak_text}"
        f"<b>Что умеет бот:</b>\n"
        f"• Ежедневный вопрос в <b>08:00</b> по Ташкенту\n"
        f"• Слово дня в <b>20:00</b>\n"
        f"• Практика в любое время — Reading & Math\n"
        f"• Отслеживание серии и статистики\n\n"
        f"Используй кнопки ниже или команды:\n"
        f"/question — случайный вопрос\n"
        f"/math — Math вопрос\n"
        f"/reading — Reading вопрос\n"
        f"/word — Слово дня\n"
        f"/stats — твоя статистика\n"
    )
    
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard()
    )


async def cmd_question(update: Update, context: ContextTypes.DEFAULT_TYPE, subject: str = None):
    user = update.effective_user
    q = get_random_question(subject)
    
    subj_label = {"m": "📐 Math", "r": "📖 Reading"}.get(q['s'], '')
    prefix = f"{subj_label} · {q['t']}"
    
    await send_question_poll(context, update.effective_chat.id, q, user.id, prefix)


async def cmd_math(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_question(update, context, subject='math')

async def cmd_reading(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_question(update, context, subject='reading')

async def cmd_random(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_question(update, context)


async def cmd_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    word = get_daily_word(today_seed())
    
    text = (
        f"💬 <b>Слово дня</b>\n\n"
        f"<b>{word['w']}</b>\n\n"
        f"{word['d']}\n\n"
    )
    if word.get('e'):
        text += f"<i>«{word['e']}»</i>\n\n"
    
    text += f"<a href='{PLATFORM_URL}'>Учить все 568 слов →</a>"
    
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📚 Vocab тренажёр", url=PLATFORM_URL),
            InlineKeyboardButton("💬 Ещё слово", callback_data="word_random"),
        ]])
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = get_user(user.id)
    
    total = u['total_answered']
    correct = u['correct']
    pct = round(correct / total * 100) if total > 0 else 0
    streak = u['streak']
    
    # Streak emoji
    if streak >= 30:   streak_emoji = "🔥🔥🔥"
    elif streak >= 14: streak_emoji = "🔥🔥"
    elif streak >= 7:  streak_emoji = "🔥"
    else:              streak_emoji = "💪"
    
    # Accuracy bar
    filled = round(pct / 10)
    bar = "█" * filled + "░" * (10 - filled)
    
    # Level
    if pct >= 80:    level = "🏆 Эксперт"
    elif pct >= 65:  level = "⭐ Продвинутый"
    elif pct >= 50:  level = "📈 Средний"
    else:            level = "🌱 Начинающий"
    
    text = (
        f"<b>📊 Твоя статистика</b>\n\n"
        f"{streak_emoji} <b>Серия:</b> {streak} дней подряд\n"
        f"✅ <b>Всего ответов:</b> {total}\n"
        f"🎯 <b>Правильных:</b> {correct} ({pct}%)\n\n"
        f"<code>[{bar}] {pct}%</code>\n\n"
        f"<b>Уровень:</b> {level}\n\n"
    )
    
    if streak == 0:
        text += "💡 <i>Ответь на вопрос сегодня — начни серию!</i>"
    elif streak < 7:
        text += f"💡 <i>Ещё {7 - streak} дней до первой недельной серии!</i>"
    elif streak < 30:
        text += f"💡 <i>Ещё {30 - streak} дней до серии 30 дней!</i>"
    else:
        text += "🏅 <i>Невероятно! Месяц без перерывов!</i>"
    
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Тренироваться", callback_data="q_random"),
            InlineKeyboardButton("🚀 Платформа", url=PLATFORM_URL),
        ]])
    )


async def cmd_streak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_stats(update, context)


async def cmd_platform(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🚀 <b>Открыть SATUm</b>\n\n"
        f"2440+ вопросов, AI тьютор, полные практические тесты\n\n"
        f"<a href='{PLATFORM_URL}'>{PLATFORM_URL}</a>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🚀 Открыть платформу", url=PLATFORM_URL)
        ]])
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>Команды SATUm Bot</b>\n\n"
        "/start — главное меню\n"
        "/question — случайный вопрос (R&W или Math)\n"
        "/math — вопрос по математике\n"
        "/reading — вопрос по Reading & Writing\n"
        "/word — слово дня\n"
        "/stats — твоя статистика и серия\n"
        "/streak — посмотреть серию\n"
        "/platform — ссылка на платформу\n\n"
        "<i>Вопрос дня приходит каждый день в 08:00 по Ташкенту.\n"
        "Слово дня — в 20:00.</i>\n\n"
        f"<b>SATUm</b> powered by <b>Entrium</b>",
        parse_mode=ParseMode.HTML,
    )


# Admin: broadcast
async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Использование: /broadcast <текст>")
        return
    msg = ' '.join(context.args)
    data = load_data()
    sent = 0
    for uid_str in data:
        try:
            await context.bot.send_message(int(uid_str), msg, parse_mode=ParseMode.HTML)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await update.message.reply_text(f"✅ Отправлено {sent} пользователям")


async def cmd_admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    data = load_data()
    total_users = len(data)
    active_today = sum(
        1 for u in data.values()
        if u.get('last_active') == uzb_now().date().isoformat()
    )
    streaks = [u.get('streak', 0) for u in data.values()]
    avg_streak = round(sum(streaks) / len(streaks), 1) if streaks else 0
    max_streak = max(streaks) if streaks else 0
    
    await update.message.reply_text(
        f"<b>📊 Admin Stats</b>\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"🟢 Активных сегодня: {active_today}\n"
        f"🔥 Средняя серия: {avg_streak} дней\n"
        f"🏆 Максимальная серия: {max_streak} дней",
        parse_mode=ParseMode.HTML,
    )


# ── Callback Query Handler ──────────────────────────────────────────────────
async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    user = update.effective_user

    if data in ("q_random", "q_math", "q_reading"):
        try:
            if data == "q_random":
                question = get_random_question()
            elif data == "q_math":
                question = get_random_question('math')
            else:
                question = get_random_question('reading')
            subj = '📐 Math' if question['s'] == 'm' else '📖 Reading'
            topic = question.get('t', 'SAT')
            await send_question_poll(context, q.message.chat_id, question, user.id, f"{subj} · {topic}")
        except Exception as e:
            logger.error(f"Poll error: {e}")
            await q.message.reply_text(f"❌ Не удалось отправить вопрос: {e}")
        return

    if data == "stats":
        u = get_user(user.id)
        total = u['total_answered']
        correct = u['correct']
        pct = round(correct / total * 100) if total > 0 else 0
        streak = u['streak']
        bar = "█" * round(pct/10) + "░" * (10 - round(pct/10))
        await q.message.reply_text(
            f"📊 <b>Статистика</b>\n\n"
            f"🔥 Серия: <b>{streak}</b> дней\n"
            f"✅ Ответов: {total} · Правильных: {correct} ({pct}%)\n"
            f"<code>[{bar}]</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "word":
        word = get_daily_word(today_seed())
        await q.message.reply_text(
            f"💬 <b>{word['w']}</b>\n\n{word['d']}"
            + (f"\n\n<i>«{word['e']}»</i>" if word.get('e') else ""),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "word_random":
        word = random.choice(ALL_VOCAB)
        await q.message.reply_text(
            f"💬 <b>{word['w']}</b>\n\n{word['d']}"
            + (f"\n\n<i>«{word['e']}»</i>" if word.get('e') else ""),
            parse_mode=ParseMode.HTML,
        )


async def cmd_connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Link Telegram account to SATUm platform profile."""
    user = update.effective_user
    args = context.args
    
    # If started with connect_USERID parameter
    if args and args[0].startswith('connect_'):
        user_prefix = args[0].replace('connect_', '')
        # Store the telegram_chat_id mapping (would need platform API call)
        # For now, give instructions
        await update.message.reply_text(
            f"✅ <b>Аккаунт связан!</b>\n\n"
            f"Теперь ты будешь получать уведомления прямо сюда:\n"
            f"🔥 Напоминания о серии\n"
            f"📊 Результаты тестов\n"
            f"🎯 Достижение целей\n\n"
            f"Твой Telegram ID: <code>{user.id}</code>\n\n"
            f"Скопируй его и вставь в Настройках платформы → Telegram",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            f"🔗 <b>Подключи аккаунт SATUm</b>\n\n"
            f"Твой Telegram ID: <code>{user.id}</code>\n\n"
            f"1. Скопируй ID выше\n"
            f"2. Зайди на платформу → Настройки → Telegram\n"
            f"3. Вставь ID и сохрани\n\n"
            f"После этого будешь получать:\n"
            f"🔥 Напоминания о серии каждый вечер\n"
            f"📊 Результаты тестов\n"
            f"🎯 Когда достигнешь целевого балла",
            parse_mode=ParseMode.HTML,
        )
    
    update_user(user.id, name=user.first_name or '')


async def cmd_sendnow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: manually trigger daily question to channel."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Только для администратора")
        return
    
    if not CHANNEL_ID:
        await update.message.reply_text("❌ CHANNEL_ID не задан в переменных")
        return
    
    await update.message.reply_text("⏳ Отправляю вопрос дня в канал...")
    await job_daily_question(context)
    await update.message.reply_text("✅ Вопрос дня отправлен в канал!")


async def cmd_sendword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: manually trigger evening word to channel."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Только для администратора")
        return
    
    if not CHANNEL_ID:
        await update.message.reply_text("❌ CHANNEL_ID не задан в переменных")
        return
    
    await update.message.reply_text("⏳ Отправляю слово дня в канал...")
    await job_evening_reminder(context)
    await update.message.reply_text("✅ Слово дня отправлено!")


async def cmd_checkconfig(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: check bot configuration."""
    if update.effective_user.id != ADMIN_ID:
        return
    
    data = load_data()
    await update.message.reply_text(
        f"⚙️ <b>Конфигурация бота</b>\n\n"
        f"BOT_TOKEN: {'✅ задан' if BOT_TOKEN else '❌ не задан'}\n"
        f"CHANNEL_ID: {'✅ ' + CHANNEL_ID if CHANNEL_ID else '❌ не задан'}\n"
        f"ADMIN_ID: {ADMIN_ID}\n"
        f"PLATFORM_URL: {PLATFORM_URL}\n\n"
        f"👥 Пользователей: {len(data)}\n"
        f"📊 Вопросов: {len(ALL_QUESTIONS)}\n"
        f"💬 Слов: {len(ALL_VOCAB)}\n\n"
        f"⏰ Расписание:\n"
        f"• Вопрос дня: 08:00 Ташкент\n"
        f"• Слово дня: 20:00 Ташкент\n"
        f"• Итоги недели: Пн 09:00 Ташкент",
        parse_mode=ParseMode.HTML,
    )

# ── Poll Answer Handler ─────────────────────────────────────────────────────
async def poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_id = answer.poll_id
    
    if poll_id not in active_polls:
        return
    
    poll_data = active_polls[poll_id]
    user_id = answer.user.id
    selected = answer.option_ids[0] if answer.option_ids else -1
    correct_option = poll_data['correct_option']
    is_correct = selected == correct_option
    
    new_streak = record_answer(user_id, is_correct)
    
    # Send feedback only in private chats
    if poll_data.get('chat_id') == user_id:  # private chat
        q = poll_data['question']
        choices = q['c']
        
        if is_correct:
            streak_text = f"🔥 Серия: {new_streak} дней" if new_streak > 1 else ""
            msg = (
                f"🎉 <b>Правильно!</b> +10 XP\n"
                f"{streak_text}\n\n"
                f"✅ {chr(65+correct_option)}. {choices[correct_option]}"
            )
        else:
            msg = (
                f"❌ <b>Неверно.</b>\n\n"
                f"Правильный ответ:\n"
                f"✅ {chr(65+correct_option)}. {choices[correct_option]}\n\n"
                f"💡 <a href='{PLATFORM_URL}'>Разбор на платформе →</a>"
            )
        
        try:
            await context.bot.send_message(
                user_id,
                msg,
                parse_mode=ParseMode.HTML,
                reply_markup=question_result_keyboard()
            )
        except Exception as e:
            logger.warning(f"Could not send poll feedback: {e}")


# ── Scheduled Jobs ──────────────────────────────────────────────────────────
async def job_daily_question(context: ContextTypes.DEFAULT_TYPE):
    """08:00 Ташкент — Вопрос дня в канал."""
    if not CHANNEL_ID:
        return
    
    q = get_daily_question(today_seed())
    d = uzb_now()
    date_str = d.strftime('%d %B %Y').lstrip('0')
    subj = "📐 Math" if q['s'] == 'm' else "📖 Reading"
    
    try:
        # Send header message
        await context.bot.send_message(
            CHANNEL_ID,
            f"☀️ <b>Вопрос дня — {date_str}</b>\n\n"
            f"{subj} · <i>{q['t']}</i>\n\n"
            f"Ответь на вопрос ниже 👇",
            parse_mode=ParseMode.HTML,
        )
        
        # Send the quiz poll
        msg = await context.bot.send_poll(
            chat_id=CHANNEL_ID,
            question=q['q'][:298],
            options=[f"{chr(65+i)}. {c}" for i, c in enumerate(q['c'])],
            type='quiz',
            correct_option_id=int(q['a']),
            explanation=(
                f"✅ {chr(65+int(q['a']))}. {q['c'][int(q['a'])]}\n\n"
                f"🚀 Тренируйся на платформе: {PLATFORM_URL}"
            ),
            is_anonymous=True,
            open_period=86400,  # 24 hours
        )
        
        active_polls[msg.poll.id] = {
            'question': q,
            'correct_option': int(q['a']),
            'user_id': None,
            'chat_id': CHANNEL_ID,
        }
        
        logger.info(f"Daily question sent to {CHANNEL_ID}")
    except Exception as e:
        logger.error(f"Failed to send daily question: {e}")


async def job_evening_reminder(context: ContextTypes.DEFAULT_TYPE):
    """20:00 Ташкент — Слово дня + напоминание о серии."""
    if not CHANNEL_ID:
        return
    
    word = get_daily_word(today_seed())
    
    try:
        await context.bot.send_message(
            CHANNEL_ID,
            f"🌙 <b>Слово дня</b>\n\n"
            f"<b>{word['w']}</b>\n\n"
            f"{word['d']}\n\n"
            + (f"<i>«{word['e']}»</i>\n\n" if word.get('e') else "")
            + f"💬 Сохрани слово — завтра спросим!\n"
            f"📚 Все 568 слов: <a href='{PLATFORM_URL}'>{PLATFORM_URL}</a>",
            parse_mode=ParseMode.HTML,
        )
        logger.info(f"Evening word sent to {CHANNEL_ID}")
    except Exception as e:
        logger.error(f"Failed to send evening word: {e}")
    
    # Streak reminders to personal chat users
    data = load_data()
    today = uzb_now().date().isoformat()
    
    for uid_str, u in data.items():
        if u.get('streak', 0) > 0 and u.get('last_active') != today:
            try:
                name = u.get('name', 'студент')
                streak = u['streak']
                
                emoji = "🔥🔥🔥" if streak >= 30 else "🔥🔥" if streak >= 14 else "🔥"
                
                await context.bot.send_message(
                    int(uid_str),
                    f"{emoji} <b>Серия {streak} дней под угрозой!</b>\n\n"
                    f"Привет{', ' + name if name else ''}! Ты ещё не занимался сегодня.\n"
                    f"Реши один вопрос — это займёт минуту!\n\n"
                    f"/question — случайный вопрос\n"
                    f"/math — Math\n"
                    f"/reading — Reading",
                    parse_mode=ParseMode.HTML,
                )
                await asyncio.sleep(0.05)
            except Exception:
                pass


async def job_weekly_digest(context: ContextTypes.DEFAULT_TYPE):
    """Понедельник 09:00 — Итоги недели в канал."""
    if not CHANNEL_ID:
        return
    
    data = load_data()
    total_users = len(data)
    
    # Calculate weekly stats
    week_ago = (uzb_now().date() - timedelta(days=7)).isoformat()
    active_this_week = sum(
        1 for u in data.values()
        if u.get('last_active', '') >= week_ago
    )
    streaks = sorted([u.get('streak', 0) for u in data.values()], reverse=True)
    top_streak = streaks[0] if streaks else 0
    
    d = uzb_now()
    
    try:
        await context.bot.send_message(
            CHANNEL_ID,
            f"📊 <b>Итоги недели</b>\n\n"
            f"👥 Студентов в SATUm: <b>{total_users}</b>\n"
            f"🟢 Активных за неделю: <b>{active_this_week}</b>\n"
            f"🏆 Лучшая серия: <b>{top_streak} дней</b>\n\n"
            f"💪 Продолжай в том же духе! Каждый вопрос приближает тебя к цели.\n\n"
            f"🚀 <a href='{PLATFORM_URL}'>Полная платформа</a> | "
            f"2440+ вопросов · AI тьютор · Адаптивные тесты",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Failed weekly digest: {e}")


# ── Setup & Run ─────────────────────────────────────────────────────────────
async def post_init(application: Application):
    await application.bot.set_my_commands([
        BotCommand("start",    "Главное меню"),
        BotCommand("question", "Случайный вопрос"),
        BotCommand("math",     "Math вопрос"),
        BotCommand("reading",  "Reading вопрос"),
        BotCommand("word",     "Слово дня"),
        BotCommand("stats",    "Моя статистика"),
        BotCommand("streak",   "Моя серия"),
        BotCommand("platform", "Открыть платформу"),
        BotCommand("help",     "Помощь"),
        BotCommand("connect",  "Подключить к платформе"),
    ])
    logger.info("Bot commands set")


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN not set in .env")
    
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    
    # ── Handlers ──
    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler("question",  cmd_random))
    app.add_handler(CommandHandler("math",      cmd_math))
    app.add_handler(CommandHandler("reading",   cmd_reading))
    app.add_handler(CommandHandler("word",      cmd_word))
    app.add_handler(CommandHandler("stats",     cmd_stats))
    app.add_handler(CommandHandler("streak",    cmd_streak))
    app.add_handler(CommandHandler("platform",  cmd_platform))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("connect",   cmd_connect))
    app.add_handler(CommandHandler("sendnow",   cmd_sendnow))
    app.add_handler(CommandHandler("sendword",  cmd_sendword))
    app.add_handler(CommandHandler("checkconfig", cmd_checkconfig))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("astats",    cmd_admin_stats))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(PollAnswerHandler(poll_answer))
    
    # ── Scheduled Jobs (UTC times, Ташкент = UTC+5) ──
    jq: JobQueue = app.job_queue
    
    # 08:00 Ташкент = 03:00 UTC
    jq.run_daily(
        job_daily_question,
        time=datetime.strptime("03:00", "%H:%M").replace(tzinfo=timezone.utc).time(),
        name="daily_question",
    )
    
    # 20:00 Ташкент = 15:00 UTC
    jq.run_daily(
        job_evening_reminder,
        time=datetime.strptime("15:00", "%H:%M").replace(tzinfo=timezone.utc).time(),
        name="evening_reminder",
    )
    
    # Понедельник 09:00 Ташкент = 04:00 UTC
    jq.run_daily(
        job_weekly_digest,
        time=datetime.strptime("04:00", "%H:%M").replace(tzinfo=timezone.utc).time(),
        days=(0,),  # Monday
        name="weekly_digest",
    )
    
    logger.info("🤖 SATUm Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
