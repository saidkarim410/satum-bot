# SATUm Telegram Bot
### powered by Entrium

Бот для подготовки к Digital SAT — ежедневные вопросы, слово дня, статистика и серии.

## Функции
- **Вопрос дня** — каждый день в 08:00 по Ташкенту в канал
- **Слово дня** — каждый день в 20:00 + напоминания о серии
- **Итоги недели** — каждый понедельник в 09:00
- **1640 вопросов** — Reading & Writing + Math
- **568 слов** — College Panda + SATashkent
- **Статистика** — серия, точность, уровень

## Команды
```
/start    — главное меню
/question — случайный вопрос
/math     — Math вопрос  
/reading  — Reading вопрос
/word     — слово дня
/stats    — статистика и серия
/platform — ссылка на платформу
```

## Деплой за 10 минут (Railway — бесплатно)

### 1. Создать бота
1. Открой [@BotFather](https://t.me/BotFather)
2. `/newbot` → дай имя (например "SATUm by Entrium") → username (например `satum_entrium_bot`)
3. Скопируй токен

### 2. Создать канал
1. Создай канал в Telegram, например `@satum_entrium`  
2. Добавь бота как **администратора** с правом публикации
3. Узнай ID канала: перешли любое сообщение каналу боту @userinfobot

### 3. Задеплоить на Railway
```bash
# Установить Railway CLI
npm install -g @railway/cli

# Залогиниться
railway login

# Создать проект
railway init

# Загрузить файлы
railway up

# Установить переменные окружения
railway variables set BOT_TOKEN="1234567890:AAF..."
railway variables set CHANNEL_ID="@satum_entrium"
railway variables set ADMIN_ID="123456789"
railway variables set PLATFORM_URL="https://entrium.uz"
```

### Или через веб-интерфейс
1. [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. Загрузи папку как GitHub репозиторий
3. Settings → Variables → добавь переменные

## Локальный запуск
```bash
pip install -r requirements.txt
cp .env.example .env
# Заполни .env
python bot.py
```

## Admin команды
```
/astats    — статистика пользователей
/broadcast <текст> — рассылка всем пользователям
```

## Структура файлов
```
satum-bot/
├── bot.py              — основной код бота
├── questions_data.py   — работа с вопросами
├── questions.json      — 1640 вопросов SAT
├── vocab.json          — 568 слов
├── user_data.json      — данные пользователей (auto-created)
├── requirements.txt
├── .env.example
├── Procfile
└── railway.json
```

---
**SATUm** powered by **Entrium** · Ташкент, Узбекистан
