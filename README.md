# Telegram Test Bot

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![aiogram 3.7](https://img.shields.io/badge/aiogram-3.7-blue.svg)](https://docs.aiogram.dev/)

A Telegram bot + Mini App for running **structured, session-based questionnaires**: create a test session in the bot, share a one-time link (or QR code) with a respondent, they complete it in a Telegram Mini App, and the session creator automatically receives the results — including an auto-generated PDF report.

Originally built for a clinical assessment use case, but the architecture is domain-agnostic: it works equally well for HR surveys, educational quizzes, or any workflow where one person creates a session and another completes it.

> 🇺🇦 Розгорнута версія українською, з оригінальним контекстом проєкту (клінічне застосування): see [README.uk.md](README.uk.md)

---

## How it works

```
┌─────────────────┐
│  Telegram Bot   │ ← Session creator starts a new test
└────────┬────────┘
         │ creates session (token, expiry)
         ↓
┌─────────────────┐
│   PostgreSQL    │ ← Stores tokens, results
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│    Mini App     │ ← Respondent completes the test
│  (your domain)  │
└────────┬────────┘
         │ POST /webhook/result
         ↓
┌─────────────────┐
│   n8n Workflow  │ ← Result processing / routing
└────────┬────────┘
         │ POST /result
         ↓
┌─────────────────┐
│  Bot Webhook    │ ← Delivers result to the session creator
└─────────────────┘
         │
         ↓
┌─────────────────┐
│ Telegram Message│ ← Creator gets result + PDF report
└─────────────────┘
```

## Features

- **One-time, scoped tokens** — each session is tied to its creator; results go only to whoever created that session
- **Inline-button main menu** — no need to remember commands
- **PDF reports** — auto-generated with a severity indicator and interpretation
- **Self-hosted Mini App** — no hardcoded URLs, works on your own domain over HTTPS
- **Session tracking** — `pending → completed` status, with a list of active/completed sessions in the bot

## Tech stack

- **Backend:** Python 3.8+, [aiogram 3.7](https://docs.aiogram.dev/) (async, fully typed)
- **Frontend:** HTML5 + vanilla JS (Telegram Mini App)
- **Database:** PostgreSQL
- **Workflow automation:** n8n
- **Web server:** Nginx
- **PDF generation:** ReportLab
- **Async stack:** asyncio, asyncpg, aiohttp

## Quick start

```bash
# 1. Server prerequisites
sudo apt update && sudo apt install -y python3 python3-pip nginx postgresql

# 2. Database
sudo -u postgres psql
CREATE USER app_user WITH PASSWORD 'your_password';
CREATE DATABASE app_db OWNER app_user;
# run the schema from DEPLOYMENT.md

# 3. Configure environment
cp .env.example .env
# fill in BOT_TOKEN, DATABASE_URL, MINI_APP_URL, etc.

# 4. Install dependencies
pip install -r requirements.txt

# 5. Run
python3 bot.py
```

Full deployment instructions (Nginx config, systemd service, n8n workflow import) are in [DEPLOYMENT.md](DEPLOYMENT.md).

## Security

**Implemented:**
- One-time UUID tokens, 90-day expiry
- Session status tracking (`pending → completed`)
- Unique constraints + cascading foreign keys

**Recommended for production:**
- HTTPS via Let's Encrypt
- Firewall (ufw)
- Rate limiting (Nginx)
- Regular backups
- Monitoring (Sentry/Grafana)

If you find a security issue, please see [SECURITY.md](SECURITY.md) instead of opening a public issue.

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for setup, coding style, and PR guidelines.

## License

MIT — see [LICENSE](LICENSE).
