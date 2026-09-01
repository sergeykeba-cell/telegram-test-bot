"""
Smoke tests: verify the application modules can be imported cleanly.

These intentionally don't exercise bot logic (there's no live Telegram
token or database in CI) -- their job is to catch import-time breakage:
missing dependencies in requirements.txt, syntax errors, or a module
that crashes on load because of a bad top-level statement.
"""

import importlib


def test_bot_module_imports():
    module = importlib.import_module("bot")
    assert module.bot is not None
    assert module.dp is not None


def test_main_module_imports():
    module = importlib.import_module("main")
    assert module.bot is not None
