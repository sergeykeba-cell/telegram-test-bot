# Психодіагностична платформа v2.0

🇬🇧 English version (general-purpose framework overview): see [README.md](README.md)

## 🎯 Що нового

### ✨ Основні покращення:

1. **Результати тільки для лікаря, який створив токен**
   - Через `doctor_id` у таблиці `tokens`
   - Webhook відправляє результат тільки тому лікарю, хто створив сесію

2. **Меню кнопки в боті**
   - Головне меню з inline кнопками
   - Швидкий доступ до всіх функцій
   - Команди в BotMenu

3. **Детальні результати з PDF**
   - Перегляд результатів через `/sessions`
   - Кнопка "Завершені тести" з списком
   - Генерація PDF звітів з детальною інтерпретацією
   - Кнопки для швидкого перегляду та завантаження

4. **Mini App на сервері**
   - Розміщення на власному домені
   - Автоматичне визначення API endpoints
   - Без hardcoded URL
   - HTTPS підтримка

---

## 📦 Файли в пакеті

1. **bot.py** — Telegram бот з усіма функціями (раніше `telegram_bot_updated.py`)
2. **miniapp.html** — Mini App для розміщення на сервері
3. **DEPLOYMENT.md** — повна інструкція з розгортання
4. **README.uk.md** — цей файл

---

## 🚀 Швидкий старт

### 1. Підготовка сервера

```
sudo apt update && sudo apt install -y python3 python3-pip nginx postgresql
```

### 2. База даних

```
sudo -u postgres psql
CREATE USER psycho_user WITH PASSWORD 'пароль';
CREATE DATABASE psycho_db OWNER psycho_user;
# Виконайте SQL з DEPLOYMENT.md
```

### 3. Розміщення Mini App

```
sudo mkdir -p /var/www/psycho-miniapp
sudo cp miniapp.html /var/www/psycho-miniapp/index.html
# Налаштуйте Nginx згідно DEPLOYMENT.md
```

### 4. Налаштування бота

```
cp .env.example .env
# Заповніть BOT_TOKEN, DATABASE_URL, MINI_APP_URL, ADMIN_TG_ID тощо

pip install -r requirements.txt

python3 bot.py
```

### 5. Налаштування n8n

- Імпортуйте `workflow_v8.json`
- Оновіть PostgreSQL credentials
- У вузлі "HTTP: Notify Doctor1" встановіть URL: `http://localhost:8080/result`
- Активуйте workflow

---

## 🎨 Функції бота

### Головне меню

```
➕ Новий тест          — створити тест для пацієнта
📋 Активні сесії       — переглянути непройдені тести
✅ Завершені тести     — результати з можливістю PDF
❓ Довідка            — інструкція користувача
```

### Команди

```
/start     — головне меню
/newtest   — створити новий тест
/sessions  — активні сесії
/help      — довідка
```

### Флоу створення тесту

1. Вибір типу опитувальника
2. Введення ПІБ пацієнта
3. Підтвердження даних
4. Генерація одноразового посилання/QR-коду сесії
5. Пацієнт проходить тест
6. **Автоматичне повідомлення лікарю з результатами**
7. Перегляд деталей та завантаження PDF

---

## 📊 PDF Звіт

Генерований PDF містить:

- ✅ Основна інформація (пацієнт, дата, бал)
- ✅ Рівень тяжкості з кольоровим індикатором
- ✅ Інтерпретація результатів
- ✅ Детальні показники по шкалах (якщо є)
- ✅ Рекомендації для лікаря
- ✅ Дисклеймер про необхідність професійної консультації

---

## 🔒 Безпека

### Реалізовано:

- ✅ Одноразові токени (UUID)
- ✅ Термін дії 90 днів
- ✅ Статус сесій (pending → completed)
- ✅ UNIQUE constraints на submission_id
- ✅ Foreign keys з каскадними зв'язками

### Рекомендовано:

- 🔐 HTTPS для Mini App (Let's Encrypt)
- 🔐 Firewall (ufw)
- 🔐 Rate limiting (nginx)
- 🔐 Regular backups (cron)
- 🔐 Моніторинг (Sentry/Grafana)

Якщо ви знайшли вразливість — будь ласка, повідомте через [SECURITY.md](SECURITY.md), а не публічний issue.

---

## 📈 Архітектура системи

```
┌─────────────────┐
│  Telegram Bot   │ ← Лікар створює тест
└────────┬────────┘
         │ creates session
         ↓
┌─────────────────┐
│   PostgreSQL    │ ← Зберігає tokens, results
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│    Mini App     │ ← Пацієнт проходить тест
│  (ваш сервер)   │
└────────┬────────┘
         │ POST /webhook/psychotest
         ↓
┌─────────────────┐
│   n8n Workflow  │ ← Обробка результатів
└────────┬────────┘
         │ POST /result
         ↓
┌─────────────────┐
│  Bot Webhook    │ ← Відправка результату лікарю
│   (port 8080)   │
└─────────────────┘
         │
         ↓
┌─────────────────┐
│ Telegram Message│ ← Лікар отримує результат + PDF
└─────────────────┘
```

---

## 📝 Технічні деталі

### Стек:

- **Backend:** Python 3.x (aiogram 3.7.0)
- **Frontend:** HTML5 + Vanilla JS
- **Database:** PostgreSQL
- **Workflow:** n8n
- **Web Server:** Nginx
- **PDF:** ReportLab
- **Async:** asyncio, asyncpg, aiohttp

### Вимоги:

- Ubuntu 20.04+ / Debian 11+
- Python 3.8+
- PostgreSQL 12+
- Nginx 1.18+
- 2GB+ RAM
- Публічна IP або домен

---

## 🐛 Troubleshooting

### Бот не відповідає

```
sudo systemctl status psycho-bot
sudo journalctl -u psycho-bot -n 50
```

### Mini App не відкривається

```
sudo nginx -t
sudo systemctl status nginx
curl https://ваш-домен.com
```

### Результати не надходять

```
curl -X POST http://localhost:8080/result \
  -H "Content-Type: application/json" \
  -d '{"session_token":"test"}'

docker logs n8n | grep -i error
```

### PDF не генерується

```
python3 -c "import reportlab; print('OK')"
sudo journalctl -u psycho-bot -f
```

---

## 📞 Підтримка

Повна інструкція: **DEPLOYMENT.md**

---

## 📜 Ліцензія

MIT — див. [LICENSE](LICENSE).

---

**Версія:** 2.1
**Автор:** Сергій Кеба
