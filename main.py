import asyncio
import logging
import os
import uuid
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from dotenv import load_dotenv
import asyncpg

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

BOT_TOKEN    = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://psyho-test-bot.vercel.app")
ADMIN_TG_ID  = int(os.getenv("ADMIN_TG_ID", "0"))
RESULT_PORT  = int(os.getenv("RESULT_PORT", "8080"))

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())
db_pool = None

async def get_db():
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    return db_pool

async def ensure_doctor(tg_id: int, full_name: str) -> int:
    pool = await get_db()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO doctors (telegram_id, full_name) VALUES ($1, $2) "
            "ON CONFLICT (telegram_id) DO UPDATE SET full_name=$2 RETURNING id",
            tg_id, full_name
        )
    return row['id']

class NewTest(StatesGroup):
    choose_test = State()
    enter_name  = State()
    confirm     = State()

TESTS = {
    "pcl5":      ("PCL-5 (ПТСР)",            "🧠", "20 питань • 5-8 хв"),
    "minmult":   ("Міні-Мульт (скор. MMPI)", "📋", "70 питань • 10-15 хв"),
    "schmishek": ("Шмішек (акцентуації)",     "🔍", "88 питань • 8-12 хв"),
}

SEV_MAP = {
    'low':      '🟢',
    'moderate': '🟡',
    'high':     '🟠',
    'severe':   '🔴',
}

def test_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{e} {n}", callback_data=f"test:{k}")]
        for k, (n, e, _) in TESTS.items()
    ])

def confirm_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Підтвердити", callback_data="confirm:yes"),
        InlineKeyboardButton(text="✏️ Змінити",    callback_data="confirm:no"),
    ]])

@dp.message(Command("start"))
async def cmd_start(msg: Message):
    await msg.answer(
        "👋 Вітаю! Це бот для психодіагностики.\n\n"
        "📋 /newtest — створити тест для пацієнта\n"
        "📊 /sessions — активні сесії\n"
        "❓ /help — довідка"
    )

@dp.message(Command("newtest"))
async def cmd_newtest(msg: Message, state: FSMContext):
    await state.set_state(NewTest.choose_test)
    await msg.answer("🧪 Оберіть тест для пацієнта:", reply_markup=test_keyboard())

@dp.callback_query(F.data.startswith("test:"), NewTest.choose_test)
async def cb_choose_test(cb: CallbackQuery, state: FSMContext):
    key = cb.data.split(":")[1]
    if key not in TESTS:
        await cb.answer("Невідомий тест")
        return
    await state.update_data(test_type=key)
    name, emoji, info = TESTS[key]
    await cb.message.edit_text(
        f"{emoji} <b>{name}</b>\n{info}\n\n👤 Введіть ПІБ пацієнта:",
        parse_mode="HTML"
    )
    await state.set_state(NewTest.enter_name)
    await cb.answer()

@dp.message(NewTest.enter_name)
async def enter_name(msg: Message, state: FSMContext):
    name = msg.text.strip()
    if len(name) < 3:
        await msg.answer("❌ Введіть повне ПІБ (мінімум 3 символи):")
        return
    await state.update_data(patient_name=name)
    data = await state.get_data()
    test_name, emoji, _ = TESTS[data['test_type']]
    await msg.answer(
        f"📋 Підтвердіть:\n\n{emoji} Тест: <b>{test_name}</b>\n👤 Пацієнт: <b>{name}</b>",
        parse_mode="HTML",
        reply_markup=confirm_keyboard()
    )
    await state.set_state(NewTest.confirm)

@dp.callback_query(F.data.startswith("confirm:"), NewTest.confirm)
async def cb_confirm(cb: CallbackQuery, state: FSMContext):
    if cb.data == "confirm:no":
        await state.set_state(NewTest.choose_test)
        await cb.message.edit_text("🧪 Оберіть тест:", reply_markup=test_keyboard())
        await cb.answer()
        return

    data         = await state.get_data()
    test_type    = data['test_type']
    patient_name = data['patient_name']
    token        = str(uuid.uuid4())

    try:
        doctor_id = await ensure_doctor(cb.from_user.id, cb.from_user.full_name)
        pool = await get_db()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO tokens (token, doctor_id, full_name, test_type, status, created_at) "
                "VALUES ($1, $2, $3, $4, 'active', NOW())",
                token, doctor_id, patient_name, test_type
            )
        link  = f"{MINI_APP_URL}?token={token}"
        qr    = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={link}"
        name, emoji, info = TESTS[test_type]
        await cb.message.edit_text(
            f"✅ Тест створено!\n\n{emoji} <b>{name}</b>\n👤 {patient_name}\n\n"
            f"📱 Посилання:\n<code>{link}</code>\n\n📷 QR-код нижче:",
            parse_mode="HTML"
        )
        await cb.message.answer_photo(
            photo=qr,
            caption=f"🔗 QR для {patient_name}\n🔑 <code>{token[:8]}...</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        log.error(f"cb_confirm error: {e}")
        await cb.message.edit_text(f"❌ Помилка.\n<code>{e}</code>", parse_mode="HTML")
        if ADMIN_TG_ID:
            await bot.send_message(ADMIN_TG_ID, f"🚨 /newtest error\n{e}")
    await state.clear()
    await cb.answer()

@dp.message(Command("sessions"))
async def cmd_sessions(msg: Message):
    try:
        doctor_id = await ensure_doctor(msg.from_user.id, msg.from_user.full_name)
        pool = await get_db()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT t.token, t.full_name, t.test_type, t.status, "
                "r.score, r.severity "
                "FROM tokens t "
                "LEFT JOIN results r ON r.token = t.token::text "
                "WHERE t.doctor_id=$1 ORDER BY r.score DESC NULLS LAST, t.created_at DESC LIMIT 10",
                doctor_id
            )
        if not rows:
            await msg.answer("📭 Немає сесій.")
            return
        s = {"active": "🟡", "completed": "✅", "expired": "⏰"}
        for r in rows:
            n = TESTS.get(r['test_type'], (r['test_type'], "", ""))[0]
            icon = s.get(r['status'], '⚪')
            score_line = ""
            if r['status'] == 'completed' and r['score'] is not None:
                sev_icon = SEV_MAP.get(r['severity'], '⚪')
                score_line = f"   {sev_icon} Бал: <b>{r['score']}</b>\n"
            text = (
                f"{icon} <b>{r['full_name']}</b>\n"
                f"   {n} • {r['status']}\n"
                f"{score_line}"
                f"   <code>{str(r['token'])[:8]}...</code>"
            )
            kb = None
            if r['status'] == 'completed':
                token_str = str(r['token'])
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text="📋 Детальний результат",
                        callback_data=f"result:{token_str}"
                    )
                ]])
            await msg.answer(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        await msg.answer(f"❌ Помилка: {e}")

@dp.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "📖 <b>Довідка:</b>\n\n/newtest — створити тест\n/sessions — сесії\n\n"
        "Після проходження тесту ви отримаєте результат автоматично.",
        parse_mode="HTML"
    )

def format_pcl5(data: dict) -> str:
    score  = data.get('score', 0)
    sev    = data.get('severity', '')
    sev_ua = data.get('severity_ua', '')
    subs   = data.get('subscales', {})
    probable = data.get('ptsd_probable', False)
    icon = SEV_MAP.get(sev, '⚪')
    lines = [
        f"🎯 Загальний бал: <b>{score}/80</b>",
        f"📈 Рівень: {icon} <b>{sev_ua}</b>",
        "",
        "📊 <b>Кластери DSM-5:</b>",
        f"  B — Вторгнення:      <b>{subs.get('B_intrusion','-')}/20</b>",
        f"  C — Уникнення:       <b>{subs.get('C_avoidance','-')}/8</b>",
        f"  D — Негативні когн.: <b>{subs.get('D_cognition','-')}/28</b>",
        f"  E — Гіперзбудження:  <b>{subs.get('E_arousal','-')}/24</b>",
        "",
        f"{'⚠️ <b>Ймовірний ПТСР (за порогами кластерів)</b>' if probable else '✅ Порогів ПТСР не досягнуто'}",
    ]
    return "\n".join(lines)

def format_minmult(data: dict) -> str:
    sev    = data.get('severity', '')
    sev_ua = data.get('severity_ua', '')
    subs   = data.get('subscales', {})
    peak   = data.get('peak_scale', '—')
    val    = data.get('validity', {})
    icon   = SEV_MAP.get(sev, '⚪')
    clinical = ['Hs','D','Hy','Pd','Pa','Pt','Sc','Ma','Si']
    names = {
        'Hs':'Іпохондрія','D':'Депресія','Hy':'Істерія',
        'Pd':'Психопатія','Pa':'Параноя','Pt':'Психастенія',
        'Sc':'Шизофренія','Ma':'Гіпоманія','Si':'Соціальна інтровер.',
    }
    bar_max = 15
    lines = [
        f"📈 Рівень: {icon} <b>{sev_ua}</b>",
        f"🏆 Пікова шкала: <b>{peak} — {names.get(peak,'?')}</b>",
        "", "📊 <b>Клінічні шкали:</b>",
    ]
    for sc in clinical:
        v = subs.get(sc, 0)
        bar = '█' * min(v, bar_max) + '░' * max(0, bar_max - v)
        lines.append(f"  {sc:2} {names[sc]:22} {bar} <b>{v}</b>")
    lines += ["", "🔎 <b>Шкали валідності:</b>",
              f"  L={val.get('L','?')}  F={val.get('F','?')}  K={val.get('K','?')}"]
    return "\n".join(lines)

def format_schmishek(data: dict) -> str:
    sev    = data.get('severity', '')
    sev_ua = data.get('severity_ua', '')
    subs   = data.get('subscales', {})
    acc    = data.get('accentuated_types', [])
    peak   = data.get('peak_type', '—')
    icon   = SEV_MAP.get(sev, '⚪')
    bar_max = 24
    lines = [
        f"📈 Рівень: {icon} <b>{sev_ua}</b>",
        f"🏆 Пікова акцентуація: <b>{peak}</b>",
        "", "📊 <b>Шкали акцентуацій:</b>",
    ]
    for name, v in sorted(subs.items(), key=lambda x: -x[1]):
        bar = '█' * min(v, bar_max) + '░' * max(0, bar_max - v)
        mark = ' ⚠️' if v >= 19 else ''
        lines.append(f"  {name:20} {bar} <b>{v}</b>{mark}")
    if acc:
        lines += ["", f"⚠️ <b>Акцентуйовані типи:</b> {', '.join(acc)}"]
    else:
        lines += ["", "✅ Акцентуацій не виявлено"]
    return "\n".join(lines)

FORMATTERS = {
    'pcl5':      format_pcl5,
    'minmult':   format_minmult,
    'schmishek': format_schmishek,
}

@dp.callback_query(F.data.startswith("result:"))
async def cb_show_result(cb: CallbackQuery):
    token_str = cb.data.split(":", 1)[1]
    try:
        pool = await get_db()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT r.score, r.severity, r.ai_interpretation, "
                "r.answers, t.full_name, t.test_type, t.created_at "
                "FROM results r "
                "JOIN tokens t ON t.token::text = r.token "
                "WHERE t.token = $1 "
                "ORDER BY r.id DESC LIMIT 1",
                token_str
            )
        if not row:
            await cb.answer("Результат не знайдено", show_alert=True)
            return
        ttype  = row['test_type']
        pname  = row['full_name']
        score  = row['score']
        sev    = row['severity']
        ai_txt = row['ai_interpretation'] or ""
        tlabel, temoji, _ = TESTS.get(ttype, (ttype, "📋", ""))
        from datetime import datetime
        dt = row['created_at']
        date_str = dt.strftime("%d.%m.%Y %H:%M") if dt else "—"
        import json as _json
        answers_raw = row['answers']
        answers = []
        if answers_raw:
            try:
                answers = _json.loads(answers_raw) if isinstance(answers_raw, str) else list(answers_raw)
            except Exception:
                answers = []
        sev_labels = {
            'low':'Мінімальний/Норма','moderate':'Легкий/Субнорма',
            'high':'Помірний/Відхилення','severe':'Важкий/Виражений'
        }
        data_for_fmt = {'score': score, 'severity': sev, 'severity_ua': sev_labels.get(sev, sev)}
        if answers and ttype == 'pcl5' and len(answers) >= 20:
            a = [int(x) for x in answers[:20]]
            data_for_fmt['subscales'] = {
                'B_intrusion': sum(a[0:5]), 'C_avoidance': sum(a[5:7]),
                'D_cognition': sum(a[7:14]), 'E_arousal': sum(a[14:20]),
            }
            B,C,D,E = data_for_fmt['subscales'].values()
            data_for_fmt['ptsd_probable'] = (B>=10 and C>=4 and D>=14 and E>=12)
        formatter = FORMATTERS.get(ttype)
        detail = formatter(data_for_fmt) if formatter else f"🎯 Бал: <b>{score}</b>"
        header = (
            f"📋 <b>Детальний результат</b>\n🗓 {date_str}\n\n"
            f"{temoji} <b>{tlabel}</b>\n👤 {pname}\n{'─'*28}\n"
        )
        ai_block = f"\n{'─'*28}\n🤖 <b>AI:</b>\n{ai_txt}" if ai_txt else ""
        full = header + detail + ai_block
        if len(full) > 4096:
            full = full[:4090] + "\n..."
        await cb.message.answer(full, parse_mode="HTML")
        await cb.answer()
    except Exception as e:
        log.error(f"cb_show_result error: {e}")
        await cb.answer(f"Помилка: {e}", show_alert=True)

async def handle_result(request: web.Request) -> web.Response:
    try:
        data          = await request.json()
        session_token = data.get('session_token')
        score         = data.get('score', 0)
        severity      = data.get('severity', '')
        ai_text       = data.get('ai_interpretation', '')
        patient_name  = data.get('patient_name', '')
        test_type     = data.get('test_type', '')
        if not session_token:
            return web.json_response({'error': 'session_token required'}, status=400)
        pool = await get_db()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT d.telegram_id, t.full_name, t.test_type "
                "FROM tokens t JOIN doctors d ON d.id = t.doctor_id "
                "WHERE t.token = $1", session_token
            )
        if not row:
            return web.json_response({'error': 'token not found'}, status=404)
        doctor_tg_id = row['telegram_id']
        pname  = row['full_name'] or patient_name
        ttype  = row['test_type'] or test_type
        tlabel, temoji, _ = TESTS.get(ttype, (ttype, "📋", ""))
        from datetime import datetime
        now = datetime.now().strftime("%d.%m.%Y %H:%M")
        sev_labels = {
            'low':'Мінімальний/Норма','moderate':'Легкий/Субнорма',
            'high':'Помірний/Відхилення','severe':'Важкий/Виражений'
        }
        data['severity_ua'] = sev_labels.get(severity, severity)
        formatter = FORMATTERS.get(ttype)
        detail = formatter(data) if formatter else f"🎯 Бал: <b>{score}</b>"
        header = (
            f"📊 <b>Результат тесту</b>\n🗓 {now}\n\n"
            f"{temoji} <b>{tlabel}</b>\n👤 Пацієнт: <b>{pname}</b>\n{'─'*28}\n"
        )
        ai_block = f"\n{'─'*28}\n🤖 <b>AI-інтерпретація:</b>\n{ai_text}" if ai_text else ""
        full = header + detail + ai_block
        if len(full) > 4096:
            full = full[:4090] + "\n..."
        await bot.send_message(doctor_tg_id, full, parse_mode="HTML")
        log.info(f"Result sent to doctor {doctor_tg_id}")
        return web.json_response({'ok': True})
    except Exception as e:
        log.error(f"handle_result error: {e}")
        return web.json_response({'error': str(e)}, status=500)

async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({'status': 'ok'})

async def main():
    app = web.Application()
    app.router.add_post('/result', handle_result)
    app.router.add_get('/health',  handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', RESULT_PORT)
    await site.start()
    log.info(f"HTTP server started on port {RESULT_PORT}")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
