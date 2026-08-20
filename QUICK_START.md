# Швидка шпаргалка з налаштування

## ⚡ Експрес-налаштування (30 хвилин)

### Крок 1: Підготовка (5 хв)
```bash
# Оновлення системи
sudo apt update && sudo apt upgrade -y

# Встановлення пакетів
sudo apt install -y python3 python3-pip python3-venv nginx postgresql postgresql-contrib git
```

### Крок 2: База даних (5 хв)
```bash
# Створення користувача та бази
sudo -u postgres psql << EOF
CREATE USER psycho_user WITH PASSWORD 'ВАШ_ПАРОЛЬ';
CREATE DATABASE psycho_db OWNER psycho_user;
GRANT ALL PRIVILEGES ON DATABASE psycho_db TO psycho_user;
\q
EOF

# Створення таблиць
psql -U psycho_user -d psycho_db << 'EOF'
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

CREATE INDEX idx_tokens_doctor_id ON tokens(doctor_id);
CREATE INDEX idx_tokens_status ON tokens(status);
CREATE INDEX idx_results_token ON results(token);
CREATE INDEX idx_results_submission_id ON results(submission_id);
EOF
```

### Крок 3: Mini App (5 хв)
```bash
# Створення директорії
sudo mkdir -p /var/www/psycho-miniapp

# Копіювання файлу (замініть шлях на реальний)
sudo cp miniapp.html /var/www/psycho-miniapp/index.html

# Налаштування прав
sudo chown -R www-data:www-data /var/www/psycho-miniapp
sudo chmod -R 755 /var/www/psycho-miniapp

# Створення конфігурації Nginx
sudo tee /etc/nginx/sites-available/psycho-miniapp > /dev/null << 'EOF'
server {
    listen 80;
    server_name ВАШ_ДОМЕН_АБО_IP;

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
EOF

# Активація
sudo ln -s /etc/nginx/sites-available/psycho-miniapp /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Крок 4: n8n через Docker (5 хв)
```bash
# Встановлення Docker (якщо немає)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Запуск n8n
docker run -d \
  --name n8n \
  --restart always \
  -p 5678:5678 \
  -v /opt/n8n-data:/home/node/.n8n \
  -e N8N_BASIC_AUTH_ACTIVE=true \
  -e N8N_BASIC_AUTH_USER=admin \
  -e N8N_BASIC_AUTH_PASSWORD=ВАШ_ПАРОЛЬ \
  -e WEBHOOK_URL=http://ВАШ_IP_АБО_ДОМЕН \
  -e GENERIC_TIMEZONE=Europe/Kiev \
  n8nio/n8n

# Відкрийте http://ВАШ_IP:5678 та імпортуйте workflow_v8.json
# Оновіть PostgreSQL credentials у вузлах
# Активуйте workflow
```

### Крок 5: Telegram бот (10 хв)
```bash
# Створення директорії
sudo mkdir -p /opt/psycho-bot

# Створення віртуального середовища
python3 -m venv /opt/psycho-bot/venv

# Активація та встановлення залежностей
source /opt/psycho-bot/venv/bin/activate
pip install aiogram==3.7.0 asyncpg python-dotenv aiohttp reportlab

# Копіювання бота
sudo cp telegram_bot_updated.py /opt/psycho-bot/bot.py

# Створення .env файлу
sudo tee /opt/psycho-bot/.env > /dev/null << 'EOF'
BOT_TOKEN=ВАШ_ТОКЕН_ВІД_BOTFATHER
DATABASE_URL=postgresql://psycho_user:ВАШ_ПАРОЛЬ_БД@localhost/psycho_db
MINI_APP_URL=http://ВАШ_ДОМЕН_АБО_IP
WEBHOOK_PORT=8080
ADMIN_TG_ID=ВАШ_TELEGRAM_ID
EOF

# Створення systemd сервісу
sudo tee /etc/systemd/system/psycho-bot.service > /dev/null << 'EOF'
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
EOF

# Запуск
sudo systemctl daemon-reload
sudo systemctl enable psycho-bot
sudo systemctl start psycho-bot

# Перевірка
sudo systemctl status psycho-bot
```

---

## ✅ Перевірка працездатності

### 1. База даних
```bash
psql -U psycho_user -d psycho_db -c "SELECT COUNT(*) FROM doctors;"
# Має виконатись без помилок
```

### 2. Mini App
```bash
curl http://localhost/
# Має повернути HTML
```

### 3. n8n
```bash
curl http://localhost:5678
# Має повернути сторінку входу
```

### 4. Telegram бот
- Надішліть `/start` вашому боту
- Має прийти відповідь з меню

---

## 🔧 Фінальні налаштування

### 1. HTTPS (рекомендовано)
```bash
# Встановлення Certbot
sudo apt install -y certbot python3-certbot-nginx

# Отримання сертифіката
sudo certbot --nginx -d ВАШ_ДОМЕН

# Оновіть .env файл бота:
MINI_APP_URL=https://ВАШ_ДОМЕН

# Перезапустіть бота
sudo systemctl restart psycho-bot
```

### 2. BotFather Menu Button
1. Відкрийте @BotFather
2. `/mybots` → оберіть бота
3. Bot Settings → Menu Button → Configure menu button
4. Name: `Тести`
5. URL: `https://ВАШ_ДОМЕН` (або `http://ВАШ_IP`)

### 3. Налаштування n8n
1. Відкрийте n8n: `http://ВАШ_IP:5678`
2. Увійдіть (admin / ВАШ_ПАРОЛЬ)
3. Імпортуйте `workflow_v8.json`
4. Оновіть усі PostgreSQL вузли:
   - Host: `localhost`
   - Database: `psycho_db`
   - User: `psycho_user`
   - Password: `ВАШ_ПАРОЛЬ_БД`
5. У вузлі "HTTP: Notify Doctor1":
   - URL: `http://localhost:8080/result`
6. Збережіть та активуйте workflow

---

## 🎯 Тестування

### Створення тестового тесту:
1. У Telegram боті: `/start`
2. "➕ Новий тест"
3. Оберіть "PCL-5 (ПТСР)"
4. ПІБ: "Тестовий Пацієнт"
5. Підтвердіть
6. Отримаєте QR-код та посилання

### Проходження тесту:
1. Відкрийте посилання у браузері
2. Має відкритись інтро-екран
3. "Розпочати тест"
4. Відповідайте на питання
5. "Надіслати лікарю"

### Перевірка результату:
1. Бот має надіслати повідомлення: "🟢 Тест завершено!"
2. Натисніть "📊 Переглянути результат"
3. Натисніть "📥 Завантажити PDF"
4. PDF має завантажитись

---

## 📊 Моніторинг

### Перегляд логів у реальному часі:
```bash
# Бот
sudo journalctl -u psycho-bot -f

# Nginx
sudo tail -f /var/log/nginx/error.log

# n8n
docker logs -f n8n

# PostgreSQL
sudo tail -f /var/log/postgresql/postgresql-*-main.log
```

### Перевірка статусу:
```bash
# Всі сервіси
sudo systemctl status psycho-bot nginx postgresql
docker ps

# Підключення до БД
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity WHERE datname='psycho_db';"
```

---

## 🚨 Швидке вирішення проблем

### Бот не запускається:
```bash
sudo systemctl status psycho-bot
sudo journalctl -u psycho-bot -n 50
# Перевірте .env файл
cat /opt/psycho-bot/.env
```

### Mini App не відкривається:
```bash
sudo nginx -t
sudo systemctl restart nginx
curl http://localhost/
```

### Результати не приходять:
```bash
# Перевірка webhook бота
curl -X POST http://localhost:8080/result \
  -H "Content-Type: application/json" \
  -d '{"session_token":"test"}'

# Має відповісти про помилку (це нормально - перевіряє чи працює endpoint)
```

### n8n не обробляє:
```bash
docker logs n8n | grep -i error
# Перевірте чи активований workflow
```

---

## 📝 Корисні команди

```bash
# Перезапуск усіх сервісів
sudo systemctl restart psycho-bot nginx
docker restart n8n
sudo systemctl restart postgresql

# Backup бази даних
pg_dump -U psycho_user psycho_db > backup_$(date +%Y%m%d).sql

# Очищення логів
sudo journalctl --vacuum-time=7d

# Перевірка використання диску
df -h
du -sh /opt/n8n-data
du -sh /var/log/

# Перевірка портів
sudo netstat -tlnp | grep -E '(80|443|5678|8080|5432)'
```

---

## 🎉 Готово!

Ваша система психодіагностики налаштована та готова до роботи!

Повна документація: **DEPLOYMENT.md**  
Огляд функцій: **README.md**

---

**Час налаштування:** ~30 хвилин  
**Підтримка:** перевіряйте логи та статуси сервісів
