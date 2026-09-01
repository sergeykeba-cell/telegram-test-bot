#!/usr/bin/env python3
"""
Telegram Bot — Психодіагностична платформа
Оновлена версія з меню, обробкою результатів та PDF звітами

Залежності:
    pip install aiogram==3.7.0 asyncpg python-dotenv aiohttp reportlab
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime
from io import BytesIO

import aiohttp
import asyncpg
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonCommands,
    Message,
)
from aiohttp import web
from dotenv import load_dotenv
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

load_dotenv()

# ══════════════════════════════════════════════════════════════
# КОНФІГУРАЦІЯ
# ══════════════════════════════════════════════════════════════

BOT_TOKEN     = os.getenv("BOT_TOKEN")
DATABASE_URL  = os.getenv("DATABASE_URL")      # postgresql://user:pass@host/db
MINI_APP_URL  = os.getenv("MINI_APP_URL")      # https://your-domain.com/miniapp.html
WEBHOOK_PORT  = int(os.getenv("WEBHOOK_PORT", "8080"))
WEBHOOK_PATH  = "/result"
ADMIN_TG_ID   = int(os.getenv("ADMIN_TG_ID", "0"))

# ── Тести ──────────────────────────────────────────────────────
TESTS = {
    "pcl5":     {"name": "PCL-5 (ПТСР)",              "emoji": "🧠"},
    "minmult":  {"name": "Міні-Мульт (скор. MMPI)",   "emoji": "📋"},
    "schmishek":{"name": "Шмішек (акцентуації)",      "emoji": "🔍"},
}

# ── Логування ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger(__name__)

# ── FSM стани ──────────────────────────────────────────────────
class NewTest(StatesGroup):
    choosing_test   = State()
    entering_name   = State()
    confirming      = State()

# ── Ініціалізація ──────────────────────────────────────────────
bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)
db_pool: asyncpg.Pool = None


# ══════════════════════════════════════════════════════════════
# БАЗА ДАНИХ
# ══════════════════════════════════════════════════════════════

async def get_db() -> asyncpg.Pool:
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    return db_pool


async def ensure_doctor(telegram_id: int, full_name: str) -> int:
    """Повертає doctor.id, створює запис якщо не існує."""
    pool = await get_db()
    row = await pool.fetchrow(
        """
        INSERT INTO doctors (telegram_id, full_name)
        VALUES ($1, $2)
        ON CONFLICT (telegram_id) DO UPDATE
            SET full_name = EXCLUDED.full_name
        RETURNING id
        """,
        telegram_id, full_name
    )
    return row["id"]


async def create_session(doctor_id: int, patient_name: str, test_type: str) -> str:
    """Створює сесію тестування. Повертає token (UUID)."""
    pool = await get_db()
    token = str(uuid.uuid4())
    await pool.execute(
        """
        INSERT INTO tokens
            (token, doctor_id, full_name, test_type, status)
        VALUES ($1, $2, $3, $4, 'pending')
        """,
        token, doctor_id, patient_name, test_type
    )
    return token


async def get_session(token: str):
    """Повертає сесію за токеном."""
    pool = await get_db()
    return await pool.fetchrow(
        "SELECT *, full_name AS patient_name FROM tokens WHERE token = $1",
        token
    )


async def get_result(token: str):
    """Повертає результат тесту за токеном."""
    pool = await get_db()
    return await pool.fetchrow(
        """
        SELECT r.*, t.doctor_id, t.full_name as patient_name
        FROM results r
        JOIN tokens t ON t.token = r.token
        WHERE r.token = $1
        ORDER BY r.completed_at DESC
        LIMIT 1
        """,
        token
    )


async def get_doctor_sessions(doctor_id: int, status: str = None):
    """Повертає сесії лікаря."""
    pool = await get_db()
    
    if status:
        query = """
            SELECT t.token, t.full_name AS patient_name, t.test_type, 
                   t.created_at, t.status, r.score, r.severity
            FROM tokens t
            LEFT JOIN results r ON r.token = t.token
            WHERE t.doctor_id = $1 AND t.status = $2
            ORDER BY t.created_at DESC
            LIMIT 20
        """
        return await pool.fetch(query, doctor_id, status)
    else:
        query = """
            SELECT t.token, t.full_name AS patient_name, t.test_type, 
                   t.created_at, t.status, r.score, r.severity
            FROM tokens t
            LEFT JOIN results r ON r.token = t.token
            WHERE t.doctor_id = $1
            ORDER BY t.created_at DESC
            LIMIT 20
        """
        return await pool.fetch(query, doctor_id)


# ══════════════════════════════════════════════════════════════
# QR-ГЕНЕРАЦІЯ
# ══════════════════════════════════════════════════════════════

async def generate_qr_bytes(url: str) -> bytes:
    """Генерує QR код через api.qrserver.com"""
    qr_url = (
        f"https://api.qrserver.com/v1/create-qr-code/"
        f"?size=400x400&data={url}&format=png&ecc=M"
    )
    async with aiohttp.ClientSession() as session:
        async with session.get(qr_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            resp.raise_for_status()
            return await resp.read()


# ══════════════════════════════════════════════════════════════
# PDF ГЕНЕРАЦІЯ
# ══════════════════════════════════════════════════════════════

def generate_pdf_report(result_data: dict) -> BytesIO:
    """Генерує PDF звіт з результатами тестування"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, 
                           rightMargin=2*cm, leftMargin=2*cm,
                           topMargin=2*cm, bottomMargin=2*cm)
    
    story = []
    styles = getSampleStyleSheet()
    
    # Стилі
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=30,
        alignment=1  # CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#2563eb'),
        spaceAfter=12,
        spaceBefore=12
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=11,
        leading=14
    )
    
    # Заголовок
    test_name = TESTS.get(result_data.get('test_type', ''), {}).get('name', result_data.get('test_type', ''))
    story.append(Paragraph("ЗВІТ ПРО ТЕСТУВАННЯ", title_style))
    story.append(Paragraph(f"{test_name}", heading_style))
    story.append(Spacer(1, 0.5*cm))
    
    # Основна інформація
    info_data = [
        ['Пацієнт:', result_data.get('patient_name', '—')],
        ['Дата проходження:', result_data.get('completed_at', datetime.now()).strftime('%d.%m.%Y %H:%M')],
        ['Загальний бал:', str(result_data.get('score', '—'))],
        ['Рівень тяжкості:', result_data.get('severity', '—').upper()],
    ]
    
    info_table = Table(info_data, colWidths=[5*cm, 10*cm])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f4f4f5')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    
    story.append(info_table)
    story.append(Spacer(1, 1*cm))
    
    # Інтерпретація
    story.append(Paragraph("ІНТЕРПРЕТАЦІЯ РЕЗУЛЬТАТІВ", heading_style))
    
    severity = result_data.get('severity', 'low')
    score = result_data.get('score', 0)
    test_type = result_data.get('test_type', '')
    
    # Інтерпретація в залежності від тесту
    if test_type == 'pcl5':
        if severity == 'low':
            interp = f"Загальний бал {score} вказує на мінімальний рівень симптомів ПТСР. Результат в межах норми."
        elif severity == 'moderate':
            interp = f"Загальний бал {score} свідчить про легкий рівень симптомів ПТСР. Рекомендується моніторинг стану."
        elif severity == 'high':
            interp = f"Загальний бал {score} вказує на помірний рівень симптомів ПТСР. Рекомендована консультація спеціаліста."
        else:
            interp = f"Загальний бал {score} свідчить про важкий рівень симптомів ПТСР. Необхідна психотерапевтична допомога."
    elif test_type == 'minmult':
        if severity == 'low':
            interp = "Результати в межах норми. Профіль особистості без виражених відхилень."
        elif severity == 'moderate':
            interp = "Виявлено окремі акцентуації особистості (субнорма). Рекомендується уточнююча діагностика."
        elif severity == 'high':
            interp = "Виявлено відхилення в профілі особистості. Необхідна консультація психолога."
        else:
            interp = "Виражені відхилення в профілі особистості. Рекомендована психологічна допомога."
    else:  # schmishek
        if severity == 'low':
            interp = "Акцентуації характеру не виявлено. Профіль особистості в межах норми."
        elif severity == 'moderate':
            interp = "Виявлено акцентуації характеру (варіант норми). Рекомендується врахування при побудові комунікації."
        elif severity == 'high':
            interp = "Виявлено виражені акцентуації характеру. Рекомендована консультація психолога."
        else:
            interp = "Виявлено дуже виражені акцентуації характеру. Необхідна психологічна допомога."
    
    story.append(Paragraph(interp, normal_style))
    story.append(Spacer(1, 0.5*cm))
    
    # Субшкали (якщо є)
    subscales = result_data.get('subscales')
    if subscales:
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph("Детальні показники по шкалах:", heading_style))
        
        subscale_data = [['Шкала', 'Бал']]
        for scale_name, scale_value in subscales.items():
            subscale_data.append([scale_name, str(scale_value)])
        
        subscale_table = Table(subscale_data, colWidths=[12*cm, 3*cm])
        subscale_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
        ]))
        story.append(subscale_table)
    
    # Додаткова інформація
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph("ВАЖЛИВО", heading_style))
    story.append(Paragraph(
        "Цей звіт носить інформаційний характер і не є медичним діагнозом. "
        "Для отримання професійної консультації та інтерпретації результатів "
        "зверніться до кваліфікованого спеціаліста.",
        normal_style
    ))
    
    # Генерація
    doc.build(story)
    buffer.seek(0)
    return buffer


# ══════════════════════════════════════════════════════════════
# КЛАВІАТУРИ
# ══════════════════════════════════════════════════════════════

def kb_main_menu() -> InlineKeyboardMarkup:
    """Головне меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Новий тест", callback_data="menu:newtest")],
        [InlineKeyboardButton(text="📋 Активні сесії", callback_data="menu:sessions")],
        [InlineKeyboardButton(text="✅ Завершені тести", callback_data="menu:completed")],
        [InlineKeyboardButton(text="❓ Довідка", callback_data="menu:help")],
    ])


def kb_test_selection() -> InlineKeyboardMarkup:
    """Вибір тесту"""
    buttons = [
        [InlineKeyboardButton(
            text=f"{info['emoji']} {info['name']}",
            callback_data=f"test:{key}"
        )]
        for key, info in TESTS.items()
    ]
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def kb_confirm(test_type: str, patient_name: str) -> InlineKeyboardMarkup:
    """Підтвердження даних"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Підтвердити", callback_data="confirm:yes"),
            InlineKeyboardButton(text="✏️ Змінити ПІБ",  callback_data="confirm:rename"),
        ],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="confirm:cancel")],
    ])


def kb_session_item(token: str, has_result: bool = False) -> InlineKeyboardMarkup:
    """Кнопки для окремої сесії"""
    buttons = []
    if has_result:
        buttons.append([InlineKeyboardButton(text="📄 Переглянути результат", callback_data=f"result:{token}")])
        buttons.append([InlineKeyboardButton(text="📥 Завантажити PDF", callback_data=f"pdf:{token}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад до списку", callback_data="menu:sessions")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ══════════════════════════════════════════════════════════════
# ХЕНДЛЕРИ
# ══════════════════════════════════════════════════════════════

@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    """Команда /start"""
    await state.clear()
    name = msg.from_user.full_name
    await ensure_doctor(msg.from_user.id, name)
    
    await msg.answer(
        f"👋 Вітаю, *{name}*!\n\n"
        "Це бот для психодіагностики пацієнтів.\n\n"
        "Оберіть дію з меню нижче:",
        reply_markup=kb_main_menu(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(cb: CallbackQuery, state: FSMContext):
    """Головне меню"""
    await state.clear()
    await cb.message.edit_text(
        "📋 *Головне меню*\n\n"
        "Оберіть дію:",
        reply_markup=kb_main_menu(),
        parse_mode="Markdown"
    )
    await cb.answer()


@router.callback_query(F.data == "menu:newtest")
@router.message(Command("newtest"))
async def cmd_newtest(event, state: FSMContext):
    """Створення нового тесту"""
    await state.set_state(NewTest.choosing_test)
    
    text = "📋 *Оберіть тест для пацієнта:*"
    markup = kb_test_selection()
    
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=markup, parse_mode="Markdown")
        await event.answer()
    else:
        await event.answer(text, reply_markup=markup, parse_mode="Markdown")


@router.callback_query(F.data.startswith("test:"), NewTest.choosing_test)
async def cb_test_selected(cb: CallbackQuery, state: FSMContext):
    """Обробка вибору тесту"""
    test_type = cb.data.split(":")[1]
    if test_type not in TESTS:
        await cb.answer("Невідомий тест", show_alert=True)
        return

    await state.update_data(test_type=test_type)
    await state.set_state(NewTest.entering_name)

    test_name = TESTS[test_type]["name"]
    await cb.message.edit_text(
        f"✅ Обрано: *{test_name}*\n\n"
        "👤 Введіть *ПІБ пацієнта* (повністю):\n"
        "_Наприклад: Іваненко Петро Сергійович_",
        parse_mode="Markdown"
    )
    await cb.answer()


@router.message(NewTest.entering_name)
async def handle_patient_name(msg: Message, state: FSMContext):
    """Обробка введення ПІБ"""
    name = msg.text.strip()

    if len(name.split()) < 2:
        await msg.answer(
            "⚠️ Введіть повне ПІБ (мінімум прізвище та ім'я).\n"
            "Спробуйте ще раз:"
        )
        return

    data = await state.get_data()
    test_type = data["test_type"]
    test_name = TESTS[test_type]["name"]

    await state.update_data(patient_name=name)
    await state.set_state(NewTest.confirming)

    await msg.answer(
        f"📝 *Підтвердіть дані:*\n\n"
        f"👤 Пацієнт: *{name}*\n"
        f"🧪 Тест: *{test_name}*\n\n"
        "Все вірно?",
        reply_markup=kb_confirm(test_type, name),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("confirm:"), NewTest.confirming)
async def cb_confirm(cb: CallbackQuery, state: FSMContext):
    """Обробка підтвердження"""
    action = cb.data.split(":")[1]

    if action == "cancel":
        await state.clear()
        await cb.message.edit_text(
            "❌ Скасовано.",
            reply_markup=kb_main_menu()
        )
        await cb.answer()
        return

    if action == "rename":
        await state.set_state(NewTest.entering_name)
        data = await state.get_data()
        test_name = TESTS[data["test_type"]]["name"]
        await cb.message.edit_text(
            f"✅ Обрано: *{test_name}*\n\n"
            "👤 Введіть *ПІБ пацієнта* ще раз:",
            parse_mode="Markdown"
        )
        await cb.answer()
        return

    # Створення сесії
    await cb.message.edit_text("⏳ Генерую QR-код...")
    await cb.answer()

    data = await state.get_data()
    test_type    = data["test_type"]
    patient_name = data["patient_name"]

    try:
        doctor_id = await ensure_doctor(cb.from_user.id, cb.from_user.full_name)
        token     = await create_session(doctor_id, patient_name, test_type)

        # Посилання на Mini App
        test_url = f"{MINI_APP_URL}?token={token}"

        # Генерація QR
        qr_bytes = await generate_qr_bytes(test_url)
        qr_file  = BufferedInputFile(qr_bytes, filename=f"test_{token[:8]}.png")

        test_name = TESTS[test_type]["name"]

        await cb.message.answer_photo(
            photo=qr_file,
            caption=(
                f"✅ *QR-код готовий!*\n\n"
                f"👤 Пацієнт: *{patient_name}*\n"
                f"🧪 Тест: *{test_name}*\n\n"
                f"📱 Покажіть QR пацієнту або надішліть посилання:\n"
                f"`{test_url}`\n\n"
                f"⚠️ _Посилання одноразове — після проходження стає недійсним_"
            ),
            parse_mode="Markdown"
        )

        await cb.message.delete()

    except Exception as e:
        log.error(f"Помилка створення сесії: {e}", exc_info=True)
        await cb.message.edit_text(
            "❌ Виникла помилка. Спробуйте ще раз.",
            reply_markup=kb_main_menu()
        )
        if ADMIN_TG_ID:
            await bot.send_message(
                ADMIN_TG_ID,
                f"🚨 Помилка /newtest\n"
                f"Лікар: {cb.from_user.id}\n"
                f"Error: {e}"
            )
    finally:
        await state.clear()


@router.callback_query(F.data == "menu:sessions")
@router.message(Command("sessions"))
async def cmd_sessions(event, state: FSMContext):
    """Активні сесії"""
    await state.clear()
    
    # Отримання ID лікаря
    if isinstance(event, CallbackQuery):
        user_id = event.from_user.id
    else:
        user_id = event.from_user.id
    
    pool = await get_db()
    doctor = await pool.fetchrow(
        "SELECT id FROM doctors WHERE telegram_id = $1",
        user_id
    )
    
    if not doctor:
        text = "❌ Помилка: лікаря не знайдено"
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text)
            await event.answer()
        else:
            await event.answer(text)
        return
    
    rows = await get_doctor_sessions(doctor['id'], status='pending')

    if not rows:
        text = "📭 Немає активних сесій.\n\nСтворіть новий тест через меню."
        markup = kb_main_menu()
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text, reply_markup=markup)
            await event.answer()
        else:
            await event.answer(text, reply_markup=markup)
        return

    text = "📋 *Активні сесії (тест не пройдено):*\n\n"
    for r in rows:
        test_name = TESTS.get(r["test_type"], {}).get("name", r["test_type"])
        created   = r["created_at"].strftime("%d.%m %H:%M")
        short_token = str(r["token"])[:8]
        text += f"• *{r['patient_name']}* — {test_name}\n"
        text += f"  `{short_token}...` · {created}\n\n"

    markup = kb_main_menu()
    
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=markup, parse_mode="Markdown")
        await event.answer()
    else:
        await event.answer(text, reply_markup=markup, parse_mode="Markdown")


@router.callback_query(F.data == "menu:completed")
async def cmd_completed(cb: CallbackQuery, state: FSMContext):
    """Завершені тести"""
    await state.clear()
    
    pool = await get_db()
    doctor = await pool.fetchrow(
        "SELECT id FROM doctors WHERE telegram_id = $1",
        cb.from_user.id
    )
    
    if not doctor:
        await cb.message.edit_text("❌ Помилка: лікаря не знайдено")
        await cb.answer()
        return
    
    rows = await get_doctor_sessions(doctor['id'], status='completed')

    if not rows:
        await cb.message.edit_text(
            "📭 Немає завершених тестів.",
            reply_markup=kb_main_menu()
        )
        await cb.answer()
        return

    text = "✅ *Завершені тести:*\n\n"
    buttons = []
    
    for r in rows:
        test_name = TESTS.get(r["test_type"], {}).get("name", r["test_type"])
        created = r["created_at"].strftime("%d.%m")
        score = r.get("score", "—")  # noqa: F841 -- TODO: decide whether to surface score in btn_text
        severity = r.get("severity", "—")
        
        severity_emoji = {
            "low": "🟢",
            "moderate": "🟡", 
            "high": "🟠",
            "severe": "🔴"
        }.get(severity, "⚪")
        
        btn_text = f"{severity_emoji} {r['patient_name']} — {test_name} ({created})"
        buttons.append([InlineKeyboardButton(
            text=btn_text,
            callback_data=f"view:{r['token']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")])
    
    await cb.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="Markdown"
    )
    await cb.answer()


@router.callback_query(F.data.startswith("view:"))
async def cb_view_result(cb: CallbackQuery):
    """Перегляд результату"""
    token = cb.data.split(":")[1]
    result = await get_result(token)
    
    if not result:
        await cb.answer("❌ Результат не знайдено", show_alert=True)
        return
    
    test_name = TESTS.get(result['test_type'], {}).get('name', result['test_type'])
    severity_labels = {
        'low': 'Мінімальний/Норма',
        'moderate': 'Легкий/Субнорма',
        'high': 'Помірний/Відхилення',
        'severe': 'Важкий/Виражений'
    }
    
    text = (
        f"📊 *Результат тестування*\n\n"
        f"👤 Пацієнт: *{result['patient_name']}*\n"
        f"🧪 Тест: {test_name}\n"
        f"📅 Дата: {result['completed_at'].strftime('%d.%m.%Y %H:%M')}\n\n"
        f"📈 Загальний бал: *{result['score']}*\n"
        f"🎯 Рівень: *{severity_labels.get(result['severity'], result['severity'])}*\n"
    )
    
    await cb.message.edit_text(
        text,
        reply_markup=kb_session_item(token, has_result=True),
        parse_mode="Markdown"
    )
    await cb.answer()


@router.callback_query(F.data.startswith("result:"))
async def cb_result_detail(cb: CallbackQuery):
    """Детальний результат"""
    token = cb.data.split(":")[1]
    result = await get_result(token)
    
    if not result:
        await cb.answer("❌ Результат не знайдено", show_alert=True)
        return
    
    # Те саме що view, можна додати більше деталей
    await cb_view_result(cb)


@router.callback_query(F.data.startswith("pdf:"))
async def cb_download_pdf(cb: CallbackQuery):
    """Генерація та відправка PDF"""
    await cb.answer("📄 Генерую PDF...")
    
    token = cb.data.split(":")[1]
    result = await get_result(token)
    
    if not result:
        await cb.answer("❌ Результат не знайдено", show_alert=True)
        return
    
    try:
        # Підготовка даних для PDF
        result_dict = dict(result)
        
        # Парсинг subscales з jsonb
        import json
        if result_dict.get('answers'):
            if isinstance(result_dict['answers'], str):
                result_dict['answers'] = json.loads(result_dict['answers'])
        
        # Генерація PDF
        pdf_buffer = generate_pdf_report(result_dict)
        
        # Відправка
        test_name = TESTS.get(result['test_type'], {}).get('name', result['test_type']).replace(' ', '_')
        patient_name = result['patient_name'].replace(' ', '_')
        filename = f"Звіт_{patient_name}_{test_name}_{datetime.now().strftime('%d%m%Y')}.pdf"
        
        pdf_file = BufferedInputFile(pdf_buffer.read(), filename=filename)
        
        await bot.send_document(
            cb.from_user.id,
            document=pdf_file,
            caption=f"📄 Звіт по тестуванню\n{result['patient_name']} — {test_name}"
        )
        
        await cb.answer("✅ PDF надіслано")
        
    except Exception as e:
        log.error(f"Помилка генерації PDF: {e}", exc_info=True)
        await cb.answer("❌ Помилка генерації PDF", show_alert=True)


@router.callback_query(F.data == "menu:help")
@router.message(Command("help"))
async def cmd_help(event, state: FSMContext):
    """Довідка"""
    await state.clear()
    
    text = (
        "📖 *Довідка*\n\n"
        "*Основні команди:*\n"
        "• /start — головне меню\n"
        "• /newtest — створити новий тест\n"
        "• /sessions — активні сесії\n"
        "• /help — ця довідка\n\n"
        "*Як працює система:*\n"
        "1️⃣ Створіть тест для пацієнта\n"
        "2️⃣ Оберіть методику тестування\n"
        "3️⃣ Введіть ПІБ пацієнта\n"
        "4️⃣ Отримайте QR-код або посилання\n"
        "5️⃣ Пацієнт проходить тест\n"
        "6️⃣ Ви отримуєте результат автоматично\n"
        "7️⃣ Переглядайте та завантажуйте PDF звіти\n\n"
        "*Підтримка:*\n"
        "При виникненні проблем зверніться до адміністратора."
    )
    
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb_main_menu(), parse_mode="Markdown")
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb_main_menu(), parse_mode="Markdown")


# ══════════════════════════════════════════════════════════════
# WEBHOOK ДЛЯ ОТРИМАННЯ РЕЗУЛЬТАТІВ ВІД N8N
# ══════════════════════════════════════════════════════════════

async def handle_result_webhook(request):
    """Обробка результатів від n8n"""
    try:
        data = await request.json()
        
        token = data.get('session_token')
        if not token:
            return web.json_response({'error': 'Missing session_token'}, status=400)
        
        # Отримання інформації про сесію
        session = await get_session(token)
        if not session:
            return web.json_response({'error': 'Session not found'}, status=404)
        
        doctor_id = session['doctor_id']
        
        # Отримання telegram_id лікаря
        pool = await get_db()
        doctor = await pool.fetchrow(
            "SELECT telegram_id FROM doctors WHERE id = $1",
            doctor_id
        )
        
        if not doctor:
            return web.json_response({'error': 'Doctor not found'}, status=404)
        
        # Формування повідомлення
        test_name = TESTS.get(data.get('test_type', ''), {}).get('name', data.get('test_type', ''))
        patient_name = data.get('patient_name', session['patient_name'])
        score = data.get('score', '—')
        severity = data.get('severity_ua', data.get('severity', '—'))
        
        severity_emoji = {
            'low': '🟢',
            'moderate': '🟡',
            'high': '🟠',
            'severe': '🔴'
        }.get(data.get('severity', ''), '⚪')
        
        message = (
            f"{severity_emoji} *Тест завершено!*\n\n"
            f"👤 Пацієнт: *{patient_name}*\n"
            f"🧪 Тест: {test_name}\n"
            f"📈 Бал: *{score}*\n"
            f"🎯 Рівень: *{severity}*\n\n"
            f"📊 Переглянути детальні результати та завантажити PDF можна через меню:\n"
            f"/sessions або кнопка \"Завершені тести\""
        )
        
        # Кнопка для швидкого перегляду
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Переглянути результат", callback_data=f"view:{token}")],
            [InlineKeyboardButton(text="📥 Завантажити PDF", callback_data=f"pdf:{token}")],
        ])
        
        # Відправка повідомлення лікарю
        await bot.send_message(
            doctor['telegram_id'],
            message,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        log.info(f"Result notification sent to doctor {doctor['telegram_id']} for token {token}")
        
        return web.json_response({'status': 'ok'})
        
    except Exception as e:
        log.error(f"Error handling result webhook: {e}", exc_info=True)
        return web.json_response({'error': str(e)}, status=500)


# ══════════════════════════════════════════════════════════════
# ЗАПУСК
# ══════════════════════════════════════════════════════════════

async def setup_bot_menu():
    """Налаштування меню бота"""
    commands = [
        BotCommand(command="start", description="🏠 Головне меню"),
        BotCommand(command="newtest", description="➕ Створити новий тест"),
        BotCommand(command="sessions", description="📋 Активні сесії"),
        BotCommand(command="help", description="❓ Довідка"),
    ]
    await bot.set_my_commands(commands)
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())


async def on_startup():
    """Ініціалізація при запуску"""
    log.info("Initializing bot...")
    await get_db()  # Ініціалізація пулу з'єднань
    await setup_bot_menu()
    log.info("Bot initialized successfully")


async def on_shutdown():
    """Очищення при зупинці"""
    log.info("Shutting down bot...")
    if db_pool:
        await db_pool.close()
    await bot.session.close()
    log.info("Bot shut down")


async def main():
    """Головна функція"""
    # Налаштування webhook сервера для результатів
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_result_webhook)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', WEBHOOK_PORT)
    
    # Запуск
    await on_startup()
    
    log.info(f"Starting webhook server on port {WEBHOOK_PORT}")
    await site.start()
    
    log.info("Starting bot polling...")
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await on_shutdown()
        await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Bot stopped by user")
