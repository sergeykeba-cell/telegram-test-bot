"""
Shared pytest fixtures/config.

bot.py and main.py construct a real aiogram Bot() instance and read
DATABASE_URL at import time, so we set safe dummy values before any
test module imports them. These are never used to make real network
or database calls in the test suite.
"""

import os
import sys
from pathlib import Path

# Repo root (parent of tests/) needs to be on sys.path so `import bot`
# and `import main` find bot.py / main.py at the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("BOT_TOKEN", "123456789:AAHqM5vHZ5x0123456789abcdefghijklm")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
os.environ.setdefault("MINI_APP_URL", "https://example.com")
os.environ.setdefault("ADMIN_TG_ID", "0")
