#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Bot — Психодіагностична платформа v3.0
З Supabase, детальними PDF з українською мовою та локальною генерацією QR

Залежності:
    pip install aiogram==3.7.0 supabase python-dotenv aiohttp reportlab qrcode[pil]
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime
from io import BytesIO
from typing import Optional, Dict, Any, List

import aiohttp
import qrcode
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile, BotCommand, MenuButtonCommands
)
from aiohttp import web
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image as RLImage
)
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from supabase import create_client, Client

load_dotenv()

# ══════════════════════════════════════════════════════════════
# КОНФІГУРАЦІЯ
# ══════════════════════════════════════════════════════════════

BOT_TOKEN       = os.getenv("BOT_TOKEN")
SUPABASE_URL    = os.getenv("SUPABASE_URL")
SUPABASE_KEY    = os.getenv("SUPABASE_KEY")
MINI_APP_URL    = os.getenv("MINI_APP_URL")
WEBHOOK_PORT    = int(os.getenv("WEBHOOK_PORT", "8080"))
WEBHOOK_PATH    = "/result"
ADMIN_TG_ID     = int(os.getenv("ADMIN_TG_ID", "0"))

# ── Тести ──────────────────────────────────────────────────────
TESTS = {
    "pcl5": {
        "name": "PCL-5 (ПТСР)",
        "name_full": "Перелік симптомів посттравматичного стресу",
        "emoji": "🧠",
        "description": "Оцінка симптомів посттравматичного стресового розладу згідно критеріїв DSM-5"
    },
    "minmult": {
        "name": "Міні-Мульт",
        "name_full": "Скорочений багатофакторний особистісний опитувальник (Mini-MMPI)",
        "emoji": "📋",
        "description": "Експрес-діагностика особистісних характеристик та психологічних відхилень"
    },
    "schmishek": {
        "name": "Шмішек",
        "name_full": "Опитувальник акцентуацій характеру за Леонгардом-Шмішеком",
        "emoji": "🔍",
        "description": "Визначення типів акцентуацій характеру та особистісних особливостей"
    }
}

# Інтерпретації для кожного тесту
INTERPRETATIONS = {
    "pcl5": {
        "low": {
            "title": "Мінімальний рівень симптомів ПТСР",
            "description": "Результати вказують на відсутність або мінімальну вираженість симптомів посттравматичного стресового розладу. Показники в межах норми.",
            "recommendations": [
                "Психологічне втручання не потрібне",
                "Рекомендується підтримка здорового способу життя",
                "При необхідності - профілактичні консультації"
            ]
        },
        "moderate": {
            "title": "Легкий рівень симптомів ПТСР",
            "description": "Виявлено легкі симптоми посттравматичного стресу. Рекомендується моніторинг стану та профілактична робота.",
            "recommendations": [
                "Консультація психолога для оцінки стану",
                "Можливе проведення підтримуючої психотерапії",
                "Моніторинг динаміки симптомів"
            ]
        },
        "high": {
            "title": "Помірний рівень симптомів ПТСР",
            "description": "Виявлено помірно виражені симптоми ПТСР, які можуть суттєво впливати на якість життя. Рекомендована психотерапевтична допомога.",
            "recommendations": [
                "Консультація психотерапевта обов'язкова",
                "Розгляд можливості травма-фокусованої терапії (EMDR, CPT)",
                "Регулярний моніторинг стану"
            ]
        },
        "severe": {
            "title": "Важкий рівень симптомів ПТСР",
            "description": "Виявлено виражені симптоми посттравматичного стресового розладу, які значно впливають на функціонування. Необхідна спеціалізована допомога.",
            "recommendations": [
                "Термінова консультація психіатра/психотерапевта",
                "Комплексна терапія (психотерапія + можлива медикаментозна підтримка)",
                "Регулярний моніторинг стану під наглядом спеціаліста"
            ]
        }
    },
    "minmult": {
        "low": {
            "title": "Показники в межах норми",
            "description": "Профіль особистості без виражених відхилень. Психологічні захисти адаптивні, емоційний стан стабільний.",
            "recommendations": [
                "Спеціалізована допомога не потрібна",
                "За бажання - консультації для особистісного розвитку"
            ]
        },
        "moderate": {
            "title": "Субнормативні показники",
            "description": "Виявлено окремі акцентуації особистості, які можуть проявлятися в стресових ситуаціях. Рекомендується уточнююча діагностика.",
            "recommendations": [
                "Консультація психолога для детальної оцінки",
                "Можлива короткострокова психологічна підтримка",
                "Робота над підвищенням стресостійкості"
            ]
        },
        "high": {
            "title": "Виявлено відхилення в профілі особистості",
            "description": "Профіль особистості містить виражені відхилення, які можуть впливати на адаптацію та якість життя.",
            "recommendations": [
                "Консультація клінічного психолога обов'язкова",
                "Розгляд можливості психотерапевтичної роботи",
                "Регулярний моніторинг стану"
            ]
        },
        "severe": {
            "title": "Виражені відхилення особистісного профілю",
            "description": "Виявлено значні відхилення в профілі особистості, які потребують професійної допомоги.",
            "recommendations": [
                "Консультація психіатра/клінічного психолога обов'язкова",
                "Комплексна психотерапія",
                "Можлива необхідність медикаментозної підтримки"
            ]
        }
    },
    "schmishek": {
        "low": {
            "title": "Акцентуації не виявлено",
            "description": "Профіль особистості гармонійний, без виражених акцентуацій характеру. Адаптаційні можливості в межах норми.",
            "recommendations": [
                "Спеціалізована допомога не потрібна",
                "Підтримка гармонійного розвитку особистості"
            ]
        },
        "moderate": {
            "title": "Помірні акцентуації характеру",
            "description": "Виявлено окремі акцентуації характеру, які є варіантом норми. Можуть проявлятися в специфічних ситуаціях.",
            "recommendations": [
                "Врахування особливостей при побудові комунікації",
                "За бажання - консультації для кращого самопізнання",
                "Розвиток компенсаторних механізмів"
            ]
        },
        "high": {
            "title": "Виражені акцентуації характеру",
            "description": "Виявлено виражені акцентуації, які можуть ускладнювати адаптацію в певних ситуаціях.",
            "recommendations": [
                "Консультація психолога для роботи з акцентуаціями",
                "Розвиток стратегій компенсації",
                "Можлива короткострокова психотерапія"
            ]
        },
        "severe": {
            "title": "Дуже виражені акцентуації характеру",
            "description": "Виявлено множинні виражені акцентуації, які можуть суттєво впливати на соціальну адаптацію.",
            "recommendations": [
                "Консультація клінічного психолога обов'язкова",
                "Психотерапевтична робота з акцентуаціями",
                "Розвиток адаптивних стратегій поведінки"
            ]
        }
    }
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

# Supabase клієнт
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ══════════════════════════════════════════════════════════════
# SUPABASE ФУНКЦІЇ
# ══════════════════════════════════════════════════════════════

async def ensure_doctor(telegram_id: int, full_name: str) -> int:
    """Повертає doctor.id, створює запис якщо не існує."""
    try:
        # Спробувати знайти існуючого
        result = supabase.table("doctors")\
            .select("id")\
            .eq("telegram_id", telegram_id)\
            .execute()
        
        if result.data:
            # Оновити ім'я
            supabase.table("doctors")\
                .update({"full_name": full_name})\
                .eq("telegram_id", telegram_id)\
                .execute()
            return result.data[0]["id"]
        else:
            # Створити нового
            result = supabase.table("doctors")\
                .insert({"telegram_id": telegram_id, "full_name": full_name})\
                .execute()
            return result.data[0]["id"]
    except Exception as e:
        log.error(f"Error in ensure_doctor: {e}")
        raise


async def create_session(doctor_id: int, patient_name: str, test_type: str) -> str:
    """Створює сесію тестування. Повертає token (UUID)."""
    try:
        token = str(uuid.uuid4())
        supabase.table("tokens").insert({
            "token": token,
            "doctor_id": doctor_id,
            "full_name": patient_name,
            "test_type": test_type,
            "status": "pending"
        }).execute()
        return token
    except Exception as e:
        log.error(f"Error in create_session: {e}")
        raise


async def get_session(token: str) -> Optional[Dict]:
    """Повертає сесію за токеном."""
    try:
        result = supabase.table("tokens")\
            .select("*, doctor_id")\
            .eq("token", token)\
            .single()\
            .execute()
        
        if result.data:
            # Додати patient_name як alias для full_name
            result.data["patient_name"] = result.data.get("full_name")
            return result.data
        return None
    except Exception as e:
        log.error(f"Error in get_session: {e}")
        return None


async def get_result(token: str) -> Optional[Dict]:
    """Повертає результат тесту за токеном."""
    try:
        result = supabase.table("results")\
            .select("*, tokens!inner(doctor_id, full_name)")\
            .eq("token", token)\
            .order("completed_at", desc=True)\
            .limit(1)\
            .execute()
        
        if result.data:
            data = result.data[0]
            # Flatten структуру
            data["doctor_id"] = data["tokens"]["doctor_id"]
            data["patient_name"] = data["tokens"]["full_name"]
            return data
        return None
    except Exception as e:
        log.error(f"Error in get_result: {e}")
        return None


async def get_doctor_sessions(doctor_id: int, status: str = None) -> List[Dict]:
    """Повертає сесії лікаря."""
    try:
        query = supabase.table("tokens")\
            .select("token, full_name, test_type, created_at, status")\
            .eq("doctor_id", doctor_id)
        
        if status:
            query = query.eq("status", status)
        
        result = query.order("created_at", desc=True)\
            .limit(20)\
            .execute()
        
        # Для кожної completed сесії додати результат
        sessions = result.data if result.data else []
        
        for session in sessions:
            if session["status"] == "completed":
                res = await get_result(session["token"])
                if res:
                    session["score"] = res.get("score")
                    session["severity"] = res.get("severity")
        
        return sessions
    except Exception as e:
        log.error(f"Error in get_doctor_sessions: {e}")
        return []


async def get_doctor_by_telegram_id(telegram_id: int) -> Optional[Dict]:
    """Повертає лікаря за telegram_id."""
    try:
        result = supabase.table("doctors")\
            .select("*")\
            .eq("telegram_id", telegram_id)\
            .single()\
            .execute()
        return result.data if result.data else None
    except Exception as e:
        log.error(f"Error in get_doctor_by_telegram_id: {e}")
        return None


# ══════════════════════════════════════════════════════════════
# QR-ГЕНЕРАЦІЯ (ЛОКАЛЬНО)
# ══════════════════════════════════════════════════════════════

def generate_qr_bytes(url: str) -> bytes:
    """Генерує QR код локально через qrcode"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Зберегти в BytesIO
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer.read()


# ══════════════════════════════════════════════════════════════
# PDF ГЕНЕРАЦІЯ З УКРАЇНСЬКОЮ МОВОЮ
# ══════════════════════════════════════════════════════════════

# Реєстрація українського шрифту
def register_fonts():
    """Реєстрація TTF шрифтів з підтримкою Unicode"""
    try:
        # Спробувати знайти DejaVuSans в системі
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Supplemental/DejaVuSans.ttf",
            "C:\\Windows\\Fonts\\DejaVuSans.ttf",
            "./fonts/DejaVuSans.ttf"
        ]
        
        font_bold_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
            "/System/Library/Fonts/Supplemental/DejaVuSans-Bold.ttf",
            "C:\\Windows\\Fonts\\DejaVuSans-Bold.ttf",
            "./fonts/DejaVuSans-Bold.ttf"
        ]
        
        # Знайти перший доступний шрифт
        font_path = None
        for path in font_paths:
            if os.path.exists(path):
                font_path = path
                break
        
        font_bold_path = None
        for path in font_bold_paths:
            if os.path.exists(path):
                font_bold_path = path
                break
        
        if font_path:
            pdfmetrics.registerFont(TTFont('DejaVuSans', font_path))
            log.info(f"Registered DejaVuSans from {font_path}")
        
        if font_bold_path:
            pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', font_bold_path))
            log.info(f"Registered DejaVuSans-Bold from {font_bold_path}")
        
        return font_path is not None
    except Exception as e:
        log.error(f"Error registering fonts: {e}")
        return False


# Реєструємо шрифти при запуску
FONTS_REGISTERED = register_fonts()


def generate_pdf_report(result_data: Dict) -> BytesIO:
    """Генерує детальний PDF звіт з результатами"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    
    story = []
    
    # Вибір шрифту
    if FONTS_REGISTERED:
        normal_font = 'DejaVuSans'
        bold_font = 'DejaVuSans-Bold'
    else:
        normal_font = 'Helvetica'
        bold_font = 'Helvetica-Bold'
        log.warning("Using Helvetica (non-Unicode) - Ukrainian text may not display correctly")
    
    # Стилі
    title_style = ParagraphStyle(
        'CustomTitle',
        fontName=bold_font,
        fontSize=20,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=10*mm,
        alignment=TA_CENTER,
        leading=24
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        fontName=normal_font,
        fontSize=14,
        textColor=colors.HexColor('#4a5568'),
        spaceAfter=15*mm,
        alignment=TA_CENTER,
        leading=18
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        fontName=bold_font,
        fontSize=14,
        textColor=colors.HexColor('#2563eb'),
        spaceAfter=5*mm,
        spaceBefore=8*mm,
        leading=18
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        fontName=normal_font,
        fontSize=11,
        leading=16,
        alignment=TA_JUSTIFY,
        spaceAfter=3*mm
    )
    
    bold_normal_style = ParagraphStyle(
        'CustomBoldNormal',
        fontName=bold_font,
        fontSize=11,
        leading=16,
        spaceAfter=3*mm
    )
    
    # Отримання даних
    test_type = result_data.get('test_type', '')
    test_info = TESTS.get(test_type, {})
    test_name = test_info.get('name_full', test_info.get('name', test_type))
    
    # Заголовок
    story.append(Paragraph("ПСИХОДІАГНОСТИЧНИЙ ЗВІТ", title_style))
    story.append(Paragraph(test_name, subtitle_style))
    
    # Основна інформація
    story.append(Paragraph("Загальна інформація", heading_style))
    
    info_data = [
        ['Пацієнт:', result_data.get('patient_name', '—')],
        ['Дата проходження:', 
         result_data.get('completed_at', datetime.now()).strftime('%d.%m.%Y о %H:%M') 
         if isinstance(result_data.get('completed_at'), datetime) 
         else datetime.now().strftime('%d.%m.%Y о %H:%M')],
        ['Загальний бал:', str(result_data.get('score', '—'))],
    ]
    
    # Додаємо рівень тяжкості з кольором
    severity = result_data.get('severity', 'low')
    severity_colors = {
        'low': colors.HexColor('#16a34a'),
        'moderate': colors.HexColor('#ca8a04'),
        'high': colors.HexColor('#ea580c'),
        'severe': colors.HexColor('#dc2626')
    }
    severity_labels = {
        'low': 'Низький/Норма',
        'moderate': 'Помірний/Субнорма',
        'high': 'Високий/Відхилення',
        'severe': 'Дуже високий/Виражений'
    }
    
    info_table = Table(info_data, colWidths=[5*cm, 11*cm])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), bold_font),
        ('FONTNAME', (1, 0), (1, -1), normal_font),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f4f4f5')),
    ]))
    
    story.append(info_table)
    story.append(Spacer(1, 5*mm))
    
    # Рівень тяжкості окремо з кольором
    severity_table = Table(
        [['Рівень тяжкості:', severity_labels.get(severity, severity)]],
        colWidths=[5*cm, 11*cm]
    )
    severity_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, 0), bold_font),
        ('FONTNAME', (1, 0), (1, 0), bold_font),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#f4f4f5')),
        ('TEXTCOLOR', (1, 0), (1, 0), severity_colors.get(severity, colors.black)),
        ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#fafafa')),
    ]))
    story.append(severity_table)
    story.append(Spacer(1, 10*mm))
    
    # Інтерпретація результатів
    story.append(Paragraph("Інтерпретація результатів", heading_style))
    
    interp = INTERPRETATIONS.get(test_type, {}).get(severity, {})
    
    if interp:
        # Заголовок інтерпретації
        story.append(Paragraph(interp.get('title', ''), bold_normal_style))
        story.append(Spacer(1, 3*mm))
        
        # Опис
        story.append(Paragraph(interp.get('description', ''), normal_style))
        story.append(Spacer(1, 5*mm))
        
        # Рекомендації
        story.append(Paragraph("Рекомендації:", bold_normal_style))
        for rec in interp.get('recommendations', []):
            story.append(Paragraph(f"• {rec}", normal_style))
    
    story.append(Spacer(1, 10*mm))
    
    # Субшкали (якщо є в даних)
    subscales = result_data.get('subscales')
    if subscales and isinstance(subscales, dict):
        story.append(Paragraph("Детальні показники по шкалах", heading_style))
        
        subscale_data = [['Шкала', 'Бал']]
        for scale_name, scale_value in subscales.items():
            subscale_data.append([scale_name, str(scale_value)])
        
        subscale_table = Table(subscale_data, colWidths=[13*cm, 3*cm])
        subscale_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), bold_font),
            ('FONTNAME', (0, 1), (0, -1), normal_font),
            ('FONTNAME', (1, 1), (1, -1), bold_font),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), 
             [colors.white, colors.HexColor('#f9fafb')]),
        ]))
        story.append(subscale_table)
        story.append(Spacer(1, 10*mm))
    
    # Важлива інформація
    story.append(PageBreak())
    story.append(Paragraph("Важлива інформація", heading_style))
    
    disclaimer = [
        "Цей звіт носить інформаційно-діагностичний характер і НЕ є медичним діагнозом.",
        "",
        "Результати психодіагностичного тестування повинні інтерпретуватися "
        "кваліфікованим спеціалістом (психологом, психотерапевтом, психіатром) "
        "з урахуванням клінічного контексту, анамнезу та додаткових методів обстеження.",
        "",
        "Для отримання професійної консультації та інтерпретації результатів "
        "зверніться до кваліфікованого спеціаліста в галузі психічного здоров'я.",
    ]
    
    for line in disclaimer:
        if line:
            story.append(Paragraph(line, normal_style))
        else:
            story.append(Spacer(1, 3*mm))
    
    story.append(Spacer(1, 10*mm))
    
    # Примітки про конфіденційність
    story.append(Paragraph("Конфіденційність", heading_style))
    confidentiality = [
        "Цей звіт містить конфіденційну медичну інформацію та призначений "
        "виключно для використання лікарем та пацієнтом.",
        "",
        "Будь-яке розголошення, копіювання або передача третім особам без "
        "письмової згоди пацієнта заборонено."
    ]
    
    for line in confidentiality:
        if line:
            story.append(Paragraph(line, normal_style))
        else:
            story.append(Spacer(1, 3*mm))
    
    # Генерація PDF
    try:
        doc.build(story)
        buffer.seek(0)
        return buffer
    except Exception as e:
        log.error(f"Error building PDF: {e}")
        raise


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


def kb_result_actions(token: str) -> InlineKeyboardMarkup:
    """Кнопки для результату"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Завантажити PDF", callback_data=f"pdf:{token}")],
        [InlineKeyboardButton(text="◀️ Назад до списку", callback_data="menu:completed")],
    ])


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

        # Генерація QR локально
        qr_bytes = generate_qr_bytes(test_url)
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
    
    if isinstance(event, CallbackQuery):
        user_id = event.from_user.id
    else:
        user_id = event.from_user.id
    
    doctor = await get_doctor_by_telegram_id(user_id)
    
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
        created   = r["created_at"]
        # Парсинг дати якщо це строка
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created.replace('Z', '+00:00'))
            except:
                pass
        created_str = created.strftime("%d.%m %H:%M") if isinstance(created, datetime) else str(created)
        short_token = str(r["token"])[:8]
        text += f"• *{r['full_name']}* — {test_name}\n"
        text += f"  `{short_token}...` · {created_str}\n\n"

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
    
    doctor = await get_doctor_by_telegram_id(cb.from_user.id)
    
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
        created = r["created_at"]
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created.replace('Z', '+00:00'))
            except:
                pass
        created_str = created.strftime("%d.%m") if isinstance(created, datetime) else "—"
        score = r.get("score", "—")
        severity = r.get("severity", "—")
        
        severity_emoji = {
            "low": "🟢",
            "moderate": "🟡", 
            "high": "🟠",
            "severe": "🔴"
        }.get(severity, "⚪")
        
        btn_text = f"{severity_emoji} {r['full_name']} — {test_name} ({created_str})"
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
    """Детальний перегляд результату"""
    token = cb.data.split(":")[1]
    result = await get_result(token)
    
    if not result:
        await cb.answer("❌ Результат не знайдено", show_alert=True)
        return
    
    # Формування детального повідомлення
    test_type = result['test_type']
    test_info = TESTS.get(test_type, {})
    test_name = test_info.get('name_full', test_info.get('name', test_type))
    
    severity = result.get('severity', 'low')
    score = result.get('score', 0)
    
    severity_labels = {
        'low': 'Низький/Норма 🟢',
        'moderate': 'Помірний/Субнорма 🟡',
        'high': 'Високий/Відхилення 🟠',
        'severe': 'Дуже високий/Виражений 🔴'
    }
    
    completed_at = result.get('completed_at')
    if isinstance(completed_at, str):
        try:
            completed_at = datetime.fromisoformat(completed_at.replace('Z', '+00:00'))
        except:
            completed_at = datetime.now()
    elif not isinstance(completed_at, datetime):
        completed_at = datetime.now()
    
    # Основна інформація
    text = (
        f"📊 *Детальні результати тестування*\n\n"
        f"🧪 *Тест:* {test_name}\n"
        f"👤 *Пацієнт:* {result.get('patient_name', '—')}\n"
        f"📅 *Дата:* {completed_at.strftime('%d.%m.%Y о %H:%M')}\n\n"
        f"📈 *Загальний бал:* {score}\n"
        f"🎯 *Рівень:* {severity_labels.get(severity, severity)}\n\n"
    )
    
    # Додаємо інтерпретацію
    interp = INTERPRETATIONS.get(test_type, {}).get(severity, {})
    if interp:
        text += f"*Інтерпретація:*\n"
        text += f"_{interp.get('title', '')}_\n\n"
        text += f"{interp.get('description', '')}\n\n"
        
        if interp.get('recommendations'):
            text += f"*Рекомендації:*\n"
            for rec in interp.get('recommendations', [])[:3]:  # Перші 3 рекомендації
                text += f"• {rec}\n"
    
    # Додаємо субшкали якщо є (топ-5)
    subscales = result.get('subscales')
    if subscales and isinstance(subscales, dict):
        text += f"\n*Топ-5 шкал:*\n"
        sorted_scales = sorted(subscales.items(), key=lambda x: x[1], reverse=True)[:5]
        for scale_name, scale_value in sorted_scales:
            text += f"• {scale_name}: {scale_value}\n"
    
    text += f"\n📥 Повний звіт доступний у форматі PDF"
    
    await cb.message.edit_text(
        text,
        reply_markup=kb_result_actions(token),
        parse_mode="Markdown"
    )
    await cb.answer()


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
        # Генерація PDF
        pdf_buffer = generate_pdf_report(result)
        
        # Відправка
        test_name = TESTS.get(result['test_type'], {}).get('name', result['test_type']).replace(' ', '_')
        patient_name = result['patient_name'].replace(' ', '_')
        filename = f"Звіт_{patient_name}_{test_name}_{datetime.now().strftime('%d%m%Y')}.pdf"
        
        pdf_file = BufferedInputFile(pdf_buffer.read(), filename=filename)
        
        await bot.send_document(
            cb.from_user.id,
            document=pdf_file,
            caption=f"📄 Психодіагностичний звіт\n\n{result['patient_name']} — {TESTS.get(result['test_type'], {}).get('name_full', '')}"
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
        "7️⃣ Переглядайте деталі та завантажуйте PDF\n\n"
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
        doctor = supabase.table("doctors")\
            .select("telegram_id")\
            .eq("id", doctor_id)\
            .single()\
            .execute()
        
        if not doctor.data:
            return web.json_response({'error': 'Doctor not found'}, status=404)
        
        # Формування повідомлення
        test_name = TESTS.get(data.get('test_type', ''), {}).get('name', data.get('test_type', ''))
        patient_name = data.get('patient_name', session.get('patient_name', '—'))
        score = data.get('score', '—')
        severity = data.get('severity', 'low')
        
        severity_emoji = {
            'low': '🟢',
            'moderate': '🟡',
            'high': '🟠',
            'severe': '🔴'
        }.get(severity, '⚪')
        
        severity_labels = {
            'low': 'Низький/Норма',
            'moderate': 'Помірний/Субнорма',
            'high': 'Високий/Відхилення',
            'severe': 'Дуже високий/Виражений'
        }
        
        message = (
            f"{severity_emoji} *Тест завершено!*\n\n"
            f"👤 *Пацієнт:* {patient_name}\n"
            f"🧪 *Тест:* {test_name}\n"
            f"📈 *Бал:* {score}\n"
            f"🎯 *Рівень:* {severity_labels.get(severity, severity)}\n\n"
            f"Переглянути детальні результати та завантажити PDF:"
        )
        
        # Кнопка для швидкого перегляду
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Переглянути детально", callback_data=f"view:{token}")],
            [InlineKeyboardButton(text="📥 Завантажити PDF", callback_data=f"pdf:{token}")],
            [InlineKeyboardButton(text="📋 Всі тести", callback_data="menu:completed")],
        ])
        
        # Відправка повідомлення лікарю
        await bot.send_message(
            doctor.data['telegram_id'],
            message,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        log.info(f"Result notification sent to doctor {doctor.data['telegram_id']} for token {token}")
        
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
    await setup_bot_menu()
    log.info("Bot initialized successfully")


async def on_shutdown():
    """Очищення при зупинці"""
    log.info("Shutting down bot...")
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
