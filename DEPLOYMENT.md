# Інструкція з розгортання психодіагностичної платформи

## Зміст
1. Підготовка сервера
2. Встановлення залежностей
3. Налаштування бази даних
4. Налаштування n8n
5. Розгортання Mini App
6. Запуск Telegram бота
7. Тестування системи

---

## 1. Підготовка сервера

### Вимоги
- Ubuntu 20.04+ або Debian 11+
- Мінімум 2GB RAM
- 20GB вільного місця на диску
- Публічна IP адреса
- Домен (рекомендовано) або використання IP

### Встановлення базових пакетів
```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv nginx postgresql postgresql-contrib certbot python3-certbot-nginx git curl
```

---

## 2. Встановлення залежностей

### Python залежності для бота
```bash
# Створення віртуального середовища
python3 -m venv /opt/psycho-bot/venv
source /opt/psycho-bot/venv/bin/activate

# Встановлення пакетів
pip install aiogram==3.7.0 asyncpg python-dotenv aiohttp reportlab
```

---

## 3. Налаштування бази даних

### Створення користувача та бази PostgreSQL
```bash
sudo -u postgres psql

-- В консолі PostgreSQL:
CREATE USER psycho_user WITH PASSWORD 'ваш_надійний_пароль';
CREATE DATABASE psycho_db OWNER psycho_user;
GRANT ALL PRIVILEGES ON DATABASE psycho_db TO psycho_user;
\q
```

### Створення таблиць
```sql
-- Підключення до бази
psql -U psycho_user -d psycho_db

-- Створення таблиць
CREATE TABLE doctors (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    email TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE tokens (
    token TEXT PRIMARY KEY,
    doctor_id INTEGER REFERENCES doctors(id),
    full_name TEXT NOT NULL,
    test_type TEXT NOT NULL,
    test_version VARCHAR NOT NULL DEFAULT '1.0',
    status VARCHAR NOT NULL DEFAULT 'pending',
    used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    opened_at TIMESTAMPTZ,
    used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '90 days')
);

CREATE TABLE results (
    id BIGSERIAL PRIMARY KEY,
    submission_id UUID UNIQUE,
    token TEXT REFERENCES tokens(token),
    full_name TEXT NOT NULL,
    test_type TEXT NOT NULL,
    score INTEGER,
    severity TEXT,
    answers JSONB,
    status VARCHAR NOT NULL DEFAULT 'notified',
    ai_interpretation TEXT,
    scoring_time_ms INTEGER,
    ai_time_ms INTEGER,
    n8n_execution_id TEXT,
    completed_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE error_logs (
    id BIGSERIAL PRIMARY KEY,
    n8n_execution_id TEXT,
    workflow_name TEXT,
    node_name TEXT,
    error_message TEXT NOT NULL,
    error_stack TEXT,
    input_data JSONB,
    session_token TEXT,
    submission_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Індекси для оптимізації
CREATE INDEX idx_tokens_doctor_id ON tokens(doctor_id);
CREATE INDEX idx_tokens_status ON tokens(status);
CREATE INDEX idx_results_token ON results(token);
CREATE INDEX idx_results_submission_id ON results(submission_id);
```

---

## 4. Налаштування n8n

### Встановлення n8n через Docker
```bash
# Встановлення Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Створення директорії для n8n
mkdir -p /opt/n8n-data

# Запуск n8n
docker run -d \
  --name n8n \
  --restart always \
  -p 5678:5678 \
  -v /opt/n8n-data:/home/node/.n8n \
  -e N8N_BASIC_AUTH_ACTIVE=true \
  -e N8N_BASIC_AUTH_USER=admin \
  -e N8N_BASIC_AUTH_PASSWORD=ваш_пароль \
  -e WEBHOOK_URL=https://ваш-домен.com \
  -e GENERIC_TIMEZONE=Europe/Kiev \
  n8nio/n8n
```

### Імпорт workflow
1. Відкрийте n8n у браузері: `http://ваш-сервер:5678`
2. Увійдіть з обліковими даними (admin / ваш_пароль)
3. Імпортуйте файл `workflow_v8.json`
4. Оновіть PostgreSQL credentials у вузлах:
   - Host: localhost (або IP вашого сервера)
   - Database: psycho_db
   - User: psycho_user
   - Password: ваш_пароль

5. Активуйте workflow

---

## 5. Розгортання Mini App

### Налаштування Nginx
```bash
# Створення директорії для Mini App
sudo mkdir -p /var/www/psycho-miniapp

# Копіювання HTML файлу
sudo cp miniapp.html /var/www/psycho-miniapp/index.html

# Створення конфігурації Nginx
sudo nano /etc/nginx/sites-available/psycho-miniapp
```

Вміст конфігурації:
```nginx
server {
    listen 80;
    server_name ваш-домен.com;  # або IP адреса

    root /var/www/psycho-miniapp;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }

    # Proxy для n8n webhooks
    location /webhook/ {
        proxy_pass http://localhost:5678/webhook/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

### Активація конфігурації
```bash
sudo ln -s /etc/nginx/sites-available/psycho-miniapp /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Налаштування HTTPS (рекомендовано)
```bash
sudo certbot --nginx -d ваш-домен.com
```

---

## 6. Запуск Telegram бота

### Створення .env файлу
```bash
sudo mkdir -p /opt/psycho-bot
sudo nano /opt/psycho-bot/.env
```

Вміст `.env`:
```env
BOT_TOKEN=ваш_токен_від_BotFather
DATABASE_URL=postgresql://psycho_user:ваш_пароль@localhost/psycho_db
MINI_APP_URL=https://ваш-домен.com
WEBHOOK_PORT=8080
ADMIN_TG_ID=ваш_telegram_id
```

### Копіювання бота
```bash
sudo cp telegram_bot_updated.py /opt/psycho-bot/bot.py
```

### Створення systemd сервісу
```bash
sudo nano /etc/systemd/system/psycho-bot.service
```

Вміст сервісу:
```ini
[Unit]
Description=Psycho Diagnostics Telegram Bot
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/psycho-bot
Environment="PATH=/opt/psycho-bot/venv/bin"
ExecStart=/opt/psycho-bot/venv/bin/python /opt/psycho-bot/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Запуск бота
```bash
sudo systemctl daemon-reload
sudo systemctl enable psycho-bot
sudo systemctl start psycho-bot

# Перевірка статусу
sudo systemctl status psycho-bot

# Перегляд логів
sudo journalctl -u psycho-bot -f
```

---

## 7. Тестування системи

### Перевірка компонентів

1. **База даних:**
```bash
psql -U psycho_user -d psycho_db -c "SELECT * FROM doctors LIMIT 1;"
```

2. **n8n:**
- Відкрийте `http://ваш-сервер:5678`
- Перевірте статус workflow (має бути активний)

3. **Mini App:**
- Відкрийте `https://ваш-домен.com`
- Має відобразитись екран завантаження

4. **Telegram бот:**
- Надішліть `/start` вашому боту
- Має відобразитись головне меню

### Створення тестового тесту

1. У Telegram боті:
   - Натисніть "➕ Новий тест"
   - Оберіть будь-який тест (наприклад, PCL-5)
   - Введіть тестове ПІБ: "Тестовий Пацієнт"
   - Підтвердіть дані

2. Отримаєте QR-код та посилання

3. Відкрийте посилання у браузері:
   - Має відобразитись інтро-екран з інформацією про тест
   - Пройдіть тест
   - Надішліть результати

4. Перевірте отримання результату:
   - Бот має надіслати повідомлення з результатами
   - Натисніть "📊 Переглянути результат"
   - Натисніть "📥 Завантажити PDF"

---

## Налаштування n8n для відправки результатів боту

### Оновлення HTTP вузла у workflow

У вузлі "HTTP: Notify Doctor1" змініть URL на:
```
http://localhost:8080/result
```

Це підключить n8n до webhook сервера бота для відправки результатів.

---

## Моніторинг та обслуговування

### Перегляд логів
```bash
# Логи бота
sudo journalctl -u psycho-bot -f

# Логи Nginx
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log

# Логи n8n
docker logs -f n8n

# Логи PostgreSQL
sudo tail -f /var/log/postgresql/postgresql-*-main.log
```

### Резервне копіювання бази даних
```bash
# Створення backup
pg_dump -U psycho_user psycho_db > backup_$(date +%Y%m%d).sql

# Відновлення з backup
psql -U psycho_user psycho_db < backup_20260313.sql
```

### Оновлення компонентів
```bash
# Оновлення бота
sudo systemctl stop psycho-bot
sudo cp telegram_bot_updated.py /opt/psycho-bot/bot.py
sudo systemctl start psycho-bot

# Оновлення Mini App
sudo cp miniapp.html /var/www/psycho-miniapp/index.html
sudo systemctl reload nginx

# Оновлення n8n
docker pull n8nio/n8n
docker stop n8n
docker rm n8n
# Запустіть заново з командою вище
```

---

## Налаштування Telegram Mini App у BotFather

1. Відкрийте @BotFather у Telegram
2. Надішліть `/mybots`
3. Оберіть вашого бота
4. Натисніть "Bot Settings" → "Menu Button"
5. Натисніть "Configure menu button"
6. Введіть:
   - Button name: `Тести`
   - URL: `https://ваш-домен.com`

---

## Troubleshooting

### Бот не запускається
```bash
# Перевірка логів
sudo journalctl -u psycho-bot -n 50

# Перевірка підключення до БД
psql -U psycho_user -d psycho_db -c "SELECT 1;"

# Перевірка змінних середовища
cat /opt/psycho-bot/.env
```

### Mini App не відкривається
```bash
# Перевірка Nginx
sudo nginx -t
sudo systemctl status nginx

# Перевірка файлу
ls -la /var/www/psycho-miniapp/

# Перевірка логів
sudo tail -f /var/log/nginx/error.log
```

### Результати не надходять
```bash
# Перевірка n8n workflow
docker logs n8n | grep -i error

# Перевірка webhook endpoint
curl -X POST http://localhost:8080/result \
  -H "Content-Type: application/json" \
  -d '{"test":"data"}'

# Має відповісти з помилкою про відсутність session_token
```

### База даних
```bash
# Перевірка підключень
sudo -u postgres psql -c "SELECT * FROM pg_stat_activity WHERE datname='psycho_db';"

# Перевірка розміру бази
sudo -u postgres psql -c "SELECT pg_size_pretty(pg_database_size('psycho_db'));"
```

---

## Безпека

### Рекомендації:
1. ✅ Завжди використовуйте HTTPS
2. ✅ Налаштуйте firewall (ufw)
3. ✅ Регулярно оновлюйте систему
4. ✅ Використовуйте складні паролі
5. ✅ Налаштуйте автоматичні backup
6. ✅ Обмежте доступ до PostgreSQL тільки з localhost
7. ✅ Налаштуйте fail2ban для захисту від brute force

### Налаштування firewall
```bash
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw allow 8080/tcp # Bot webhook (тільки з localhost)
sudo ufw enable
```

---

## Підтримка

При виникненні проблем перевірте:
1. Логи всіх компонентів
2. Статус сервісів (`systemctl status`)
3. Підключення до бази даних
4. Доступність webhook endpoint
5. Налаштування n8n workflow

---

**Автори:** Система психодіагностики v2.0  
**Дата:** 13.03.2026
