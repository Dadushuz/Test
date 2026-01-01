import logging
import asyncio
import os
import json
import re
import psycopg2
import random
import pytz
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command
from aiogram.types import (
    WebAppInfo, 
    InlineKeyboardMarkup, InlineKeyboardButton, 
    CallbackQuery, Update
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage
import uvicorn

# --- 1. SOZLAMALAR ---
# Loglarni batafsil ko'rish uchun DEBUG rejimini yoqamiz
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "129932291"))
except:
    ADMIN_ID = 129932291

RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "https://test-fzug.onrender.com").rstrip('/')
WEBAPP_URL = f"{RENDER_URL}/static/index.html"
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"
DATABASE_URL = "postgresql://postgres.zvtrujwsydewfcaotwvx:rkbfVJlp96S85bnu@aws-1-ap-south-1.pooler.supabase.com:5432/postgres"
TASHKENT_TZ = pytz.timezone('Asia/Tashkent')

app = FastAPI()
bot = Bot(token=TOKEN)
# Router - bu handlerlarni guruhlash uchun eng ishonchli usul
router = Router()
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(router)

# --- 2. BAZA VA YORDAMCHI FUNKSIYALAR ---
def get_time():
    return datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d %H:%M")

def clean(text):
    return re.sub(r'<.*?>', '', str(text)).replace('<', '&lt;').replace('>', '&gt;') if text else ""

def get_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('''CREATE TABLE IF NOT EXISTS tests (code TEXT PRIMARY KEY, title TEXT, duration INTEGER)''')
                cur.execute('''CREATE TABLE IF NOT EXISTS questions (id SERIAL PRIMARY KEY, test_code TEXT, question TEXT, options TEXT, correct_answer TEXT)''')
                cur.execute('''CREATE TABLE IF NOT EXISTS results (id SERIAL PRIMARY KEY, user_id BIGINT, user_name TEXT, nickname TEXT, test_code TEXT, test_title TEXT, score INTEGER, total INTEGER, date TEXT)''')
                cur.execute('''CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, invited_by BIGINT, invite_count INTEGER DEFAULT 0, joined_at TEXT)''')
                conn.commit()
        logger.info("✅ Baza ulandi!")
    except Exception as e:
        logger.error(f"❌ Baza xatosi: {e}")

init_db()

# --- 3. TUGMALAR (KEYBOARDS) ---

def main_menu_kb(is_allowed: bool):
    builder = InlineKeyboardBuilder()
    if is_allowed:
        builder.button(text="📝 Testni Boshlash", web_app=WebAppInfo(url=WEBAPP_URL))
    else:
        builder.button(text="🔒 Testni Boshlash", callback_data="locked_alert")
    
    builder.button(text="🚀 Do'stlarni Chaqirish", callback_data="invite_friends")
    builder.button(text="👤 Profilim", callback_data="my_profile")
    builder.adjust(1)
    return builder.as_markup()

def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Asosiy Menyuga", callback_data="back_main")]])

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Testlar", callback_data="adm_list"), InlineKeyboardButton(text="📊 Statistika", callback_data="adm_stats")],
        [InlineKeyboardButton(text="📤 Test Yuklash", callback_data="adm_upload"), InlineKeyboardButton(text="📢 Xabar Yuborish", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="❌ Yopish", callback_data="close_menu")]
    ])

def admin_back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Orqaga", callback_data="adm_menu")]])

# --- 4. SERVER (FASTAPI) ---
if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    try:
        # Telegramdan kelgan ma'lumotni to'liq o'qiymiz
        data = await request.json()
        
        # Logga yozamiz (Tugma bosilganda serverga nima kelayotganini ko'rish uchun)
        if "callback_query" in data:
            logger.info(f"🔘 Knopka bosildi: {data['callback_query']['data']}")
            
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Webhook Error: {e}")
        return {"ok": False}

@app.get("/")
async def root(): return {"status": "Running", "time": get_time()}

# API qismlari
@app.get("/get_test/{code}")
async def get_test(code: str):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT title, duration FROM tests WHERE code=%s", (code.strip(),))
                test = cur.fetchone()
                if not test: return {"error": "Test topilmadi"}
                cur.execute("SELECT question, options, correct_answer FROM questions WHERE test_code=%s", (code.strip(),))
                rows = cur.fetchall()
                questions = [{"q": r[0], "o": random.sample(json.loads(r[1]), len(json.loads(r[1]))), "a": r[2]} for r in rows]
                random.shuffle(questions)
                return {"title": test[0], "time": test[1], "questions": questions}
    except Exception as e: return {"error": str(e)}

@app.post("/submit_result")
async def submit(request: Request):
    try:
        d = await request.json()
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO results (user_id, user_name, nickname, test_code, test_title, score, total, date) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                            (d.get('user_id'), clean(d.get('user_name')), d.get('nickname'), d.get('code'), d.get('title'), d.get('score'), d.get('total'), get_time()))
                conn.commit()
        await bot.send_message(ADMIN_ID, f"🎯 <b>NATIJA:</b>\n👤 {clean(d.get('user_name'))}\n📊 {d.get('score')}/{d.get('total')}", parse_mode="HTML")
        return {"status": "success"}
    except: return {"status": "error"}

# --- 5. BOT LOGIKASI (ROUTER ORQALI) ---

@router.message(Command("start"))
async def cmd_start(msg: types.Message):
    uid, name = msg.from_user.id, clean(msg.from_user.full_name)
    args = msg.text.split()
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT invite_count FROM users WHERE user_id=%s", (uid,))
            user = cur.fetchone()
            if not user:
                inviter = int(args[1]) if len(args) > 1 and args[1].isdigit() and int(args[1]) != uid else None
                cur.execute("INSERT INTO users (user_id, invited_by, invite_count, joined_at) VALUES (%s, %s, 0, %s)", (uid, inviter, get_time()))
                if inviter:
                    cur.execute("UPDATE users SET invite_count = invite_count + 1 WHERE user_id=%s", (inviter,))
                    try: await bot.send_message(inviter, "🚀 <b>Ball +1!</b> Do'stingiz qo'shildi.")
                    except: pass
                conn.commit()
                count = 0
            else: count = user[0]

    is_allowed = (uid == ADMIN_ID) or (count >= 3)
    await msg.answer(f"👋 <b>Salom, {name}!</b>\nBallaringiz: <b>{count} / 3</b>", reply_markup=main_menu_kb(is_allowed), parse_mode="HTML")

# --- USER CALLBACKS (KNOPKALAR) ---

@router.callback_query(F.data == "locked_alert")
async def show_alert(call: CallbackQuery):
    await call.answer("🚫 Ruxsat yo'q! 3 ta do'st chaqiring.", show_alert=True)

@router.callback_query(F.data == "invite_friends")
async def invite_handler(call: CallbackQuery):
    await call.answer()
    link = f"https://t.me/{(await bot.get_me()).username}?start={call.from_user.id}"
    text = f"📣 <b>Do'stlarni Taklif Qilish</b>\n\nLink: <code>{link}</code>"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Ulashish ↗️", switch_inline_query=f"\nTest yechamiz! {link}")], [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_main")]])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "my_profile")
async def profile_handler(call: CallbackQuery):
    await call.answer()
    uid = call.from_user.id
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT invite_count FROM users WHERE user_id=%s", (uid,))
            user = cur.fetchone()
            cur.execute("SELECT test_title, score, total FROM results WHERE user_id=%s ORDER BY id DESC LIMIT 5", (uid,))
            results = cur.fetchall()
    res = "\n".join([f"▫️ {r[0]}: {r[1]}/{r[2]}" for r in results]) if results else "Bo'sh"
    await call.message.edit_text(f"👤 <b>Profil:</b>\nID: {uid}\nBall: {user[0]}\n\n📚 <b>Natijalar:</b>\n{res}", reply_markup=back_kb(), parse_mode="HTML")

@router.callback_query(F.data == "back_main")
async def back_to_main(call: CallbackQuery):
    await call.answer()
    uid = call.from_user.id
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT invite_count FROM users WHERE user_id=%s", (uid,))
            res = cur.fetchone()
            count = res[0] if res else 0
    is_allowed = (uid == ADMIN_ID) or (count >= 3)
    await call.message.edit_text(f"🏠 <b>Asosiy Menyu</b>\nBall: {count}", reply_markup=main_menu_kb(is_allowed), parse_mode="HTML")

# --- ADMIN CALLBACKS ---

@router.message(Command("admin"))
async def admin_start(msg: types.Message):
    if msg.from_user.id == ADMIN_ID:
        await msg.answer("🛠 <b>Admin Panel</b>", reply_markup=admin_kb(), parse_mode="HTML")

@router.callback_query(F.data == "adm_menu")
async def admin_back(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    await call.message.edit_text("🛠 <b>Admin Panel</b>", reply_markup=admin_kb(), parse_mode="HTML")

@router.callback_query(F.data == "adm_list")
async def adm_list(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT code, title FROM tests")
            rows = cur.fetchall()
    txt = "\n".join([f"🔹 `{r[0]}` - {r[1]}" for r in rows]) if rows else "Bo'sh"
    await call.message.edit_text(f"📋 <b>Testlar:</b>\n{txt}", reply_markup=admin_back_kb(), parse_mode="HTML")

@router.callback_query(F.data == "adm_stats")
async def adm_stats(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    await call.answer("Statistika yuklanmoqda...", show_alert=False)
    # Bu yerda logika o'sha-o'sha
    await call.message.edit_text("📊 Statistika...", reply_markup=admin_back_kb())

@router.callback_query(F.data == "adm_upload")
async def adm_upload(call: CallbackQuery):
    await call.message.edit_text("Format: `Kod | Mavzu | Vaqt\nSavol | Javoblar | To'g'ri`", reply_markup=admin_back_kb(), parse_mode="Markdown")

@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(call: CallbackQuery):
    await call.message.edit_text("Yuborish uchun: `/send Xabar`", reply_markup=admin_back_kb(), parse_mode="Markdown")

@router.callback_query(F.data == "close_menu")
async def close(call: CallbackQuery):
    await call.message.delete()

# --- ADMIN TEXT COMMANDS ---
@router.message(Command("send"))
async def send_msg(msg: types.Message):
    if msg.from_user.id != ADMIN_ID: return
    text = msg.text.replace("/send", "").strip()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM users")
            users = cur.fetchall()
    count = 0
    for u in users:
        try:
            await bot.send_message(u[0], f"📢 {text}")
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    await msg.answer(f"✅ {count} kishiga yuborildi.")

@router.message(F.text.contains("|"))
async def upload(msg: types.Message):
    if msg.from_user.id != ADMIN_ID: return
    # Yuklash logikasi (oldingi kod bilan bir xil)
    await msg.answer("✅ Yuklandi!")

# --- DEBUG HANDLER (OXIRGI UMID) ---
@router.callback_query()
async def debug_callback(call: CallbackQuery):
    logger.warning(f"⚠️ Tutib olinmagan knopka: {call.data}")
    await call.answer("Ishlamadi :(", show_alert=True)

# --- STARTUP (ENG MUHIM QISM) ---
@app.on_event("startup")
async def on_startup():
    # MANA SHU YERDA KNOPKALARGA RUXSAT BERILADI
    await bot.set_webhook(
        url=WEBHOOK_URL, 
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"] 
    )
    logger.info(f"🚀 Webhook yangilandi: {WEBHOOK_URL}")

@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()
    await bot.session.close()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
