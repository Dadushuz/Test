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
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, Filter
from aiogram.types import (
    WebAppInfo, 
    InlineKeyboardMarkup, InlineKeyboardButton, 
    CallbackQuery, Update
)
from aiogram.utils.keyboard import InlineKeyboardBuilder # Tugmalarni dinamik yasash uchun
from aiogram.fsm.storage.memory import MemoryStorage
import uvicorn

# --- 1. SOZLAMALAR ---
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
dp = Dispatcher(storage=MemoryStorage())

# --- 2. YORDAMCHI FUNKSIYALAR ---
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
        logger.info("✅ Baza ideal holatda!")
    except Exception as e:
        logger.error(f"❌ Baza xatosi: {e}")

init_db()

# --- 3. INLINE TUGMALAR LOYIHASI ---

def main_menu_kb(is_allowed: bool):
    """Asosiy menyu tugmalari"""
    builder = InlineKeyboardBuilder()
    
    # 1. Test boshlash tugmasi (Ruxsatga qarab o'zgaradi)
    if is_allowed:
        builder.button(text="📝 Testni Boshlash (WebApp)", web_app=WebAppInfo(url=WEBAPP_URL))
    else:
        # Agar ruxsat bo'lmasa, bosganda ogohlantirish chiqadi
        builder.button(text="🔒 Testni Boshlash", callback_data="locked_alert")
    
    # 2. Boshqa tugmalar
    builder.button(text="🚀 Do'stlarni Chaqirish", callback_data="invite_friends")
    builder.button(text="👤 Mening Profilim", callback_data="my_profile")
    builder.button(text="📞 Admin bilan aloqa", url="https://t.me/shaxsiy_profilingiz") # O'zgartiring
    
    builder.adjust(1) # Har qatorda 1 ta tugma
    return builder.as_markup()

def back_kb():
    """Orqaga qaytish tugmasi"""
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Asosiy Menyuga", callback_data="back_main")]])

def admin_kb():
    """Admin paneli tugmalari"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Testlar", callback_data="adm_tests"), InlineKeyboardButton(text="📊 Statistika", callback_data="adm_stats")],
        [InlineKeyboardButton(text="📤 Test Yuklash", callback_data="adm_upload"), InlineKeyboardButton(text="🏆 Reyting", callback_data="adm_rating_info")],
        [InlineKeyboardButton(text="❌ Menyuni yopish", callback_data="close_menu")]
    ])

# --- 4. FASTAPI & WEBHOOK ---
if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    try:
        update_data = await request.json()
        update = Update.model_validate(update_data, context={"bot": bot})
        await dp.feed_update(bot, update)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/")
async def root(): return {"status": "Active", "mode": "Inline/Smart", "time": get_time()}

# --- API (TEST UCHUN) ---
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
        await bot.send_message(ADMIN_ID, f"🎯 <b>YANGI NATIJA:</b>\n👤 {clean(d.get('user_name'))}\n📊 {d.get('score')}/{d.get('total')}", parse_mode="HTML")
        return {"status": "success"}
    except: return {"status": "error"}

# --- 5. BOT LOGIKASI (INLINE REJIM) ---

@dp.message(Command("start"))
async def cmd_start(msg: types.Message):
    uid, name = msg.from_user.id, clean(msg.from_user.full_name)
    args = msg.text.split()
    
    # Ro'yxatdan o'tkazish
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
    text = (f"👋 <b>Salom, {name}!</b>\n\n"
            f"Botga xush kelibsiz. Bu yerdan bilimizni sinashingiz mumkin.\n"
            f"📊 Sizning ballaringiz: <b>{count} / 3</b>")

    await msg.answer(text, reply_markup=main_menu_kb(is_allowed), parse_mode="HTML")

# --- CALLBACK (KNOPKA) HANDLERLAR ---

@dp.callback_query(F.data == "locked_alert")
async def show_alert(call: CallbackQuery):
    # Bu xabar ekranning o'rtasida "oynacha" bo'lib chiqadi
    await call.answer("🚫 Kechirasiz!\n\nTestni boshlash uchun kamida 3 ta do'stingizni taklif qilishingiz kerak.\n'Do'stlarni chaqirish' tugmasini bosing.", show_alert=True)

@dp.callback_query(F.data == "invite_friends")
async def invite_handler(call: CallbackQuery):
    bot_username = (await bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={call.from_user.id}"
    
    text = (
        "📣 <b>Do'stlarni Taklif Qilish</b>\n\n"
        "Quyidagi havolani do'stlaringizga yuboring. Ular botga kirsa, sizga ball beriladi!\n\n"
        f"🔗 <code>{link}</code>"
    )
    
    # Ulashish tugmasi
    share_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Do'stga yuborish ↗️", switch_inline_query=f"\nTest yechamiz! {link}")],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_main")]
    ])
    
    # Xabarni yangilash (yangi xabar yubormasdan)
    await call.message.edit_text(text, reply_markup=share_kb, parse_mode="HTML")

@dp.callback_query(F.data == "my_profile")
async def profile_handler(call: CallbackQuery):
    uid = call.from_user.id
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT invite_count, joined_at FROM users WHERE user_id=%s", (uid,))
            user = cur.fetchone()
            cur.execute("SELECT test_title, score, total FROM results WHERE user_id=%s ORDER BY id DESC LIMIT 5", (uid,))
            results = cur.fetchall()
            
    res_list = "\n".join([f"▫️ {r[0]}: <b>{r[1]}/{r[2]}</b>" for r in results]) if results else "<i>Hali test yechilmagan</i>"
    
    text = (
        f"👤 <b>Sizning Profilingiz</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"📅 Qo'shilgan: {user[1]}\n"
        f"👥 Takliflar: <b>{user[0]}</b> ta\n\n"
        f"📚 <b>Oxirgi Natijalar:</b>\n{res_list}"
    )
    await call.message.edit_text(text, reply_markup=back_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "back_main")
async def back_to_main(call: CallbackQuery):
    uid = call.from_user.id
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT invite_count FROM users WHERE user_id=%s", (uid,))
            res = cur.fetchone()
            count = res[0] if res else 0
            
    is_allowed = (uid == ADMIN_ID) or (count >= 3)
    text = f"🏠 <b>Asosiy Menyu</b>\n\n📊 Ballaringiz: <b>{count} / 3</b>\nQuyidagi bo'limlardan birini tanlang:"
    
    await call.message.edit_text(text, reply_markup=main_menu_kb(is_allowed), parse_mode="HTML")

# --- ADMIN QISMI ---

@dp.message(Command("admin"))
async def admin_start(msg: types.Message):
    if msg.from_user.id == ADMIN_ID:
        await msg.answer("🛠 <b>Admin Panel</b>\nBoshqaruv uchun tugmalardan foydalaning:", reply_markup=admin_kb(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("adm_"))
async def admin_actions(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    action = call.data.split("_")[1]
    
    if action == "tests":
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT code, title FROM tests")
                rows = cur.fetchall()
        txt = "📋 <b>Testlar:</b>\n\n" + "\n".join([f"🔹 <code>{r[0]}</code> - {r[1]}" for r in rows]) if rows else "Testlar yo'q."
        await call.message.edit_text(txt, reply_markup=admin_kb(), parse_mode="HTML")
        
    elif action == "stats":
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM users")
                u = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM results")
                r = cur.fetchone()[0]
        await call.answer(f"👥 Foydalanuvchilar: {u}\n📝 Yechilgan testlar: {r}", show_alert=True)
        
    elif action == "upload":
        await call.message.edit_text("📤 <b>Yuklash uchun format:</b>\n\n<code>Kod | Mavzu | Vaqt\nSavol | Javoblar | To'g'ri</code>\n\nShu formatda xabar yozing.", reply_markup=admin_kb(), parse_mode="HTML")

    elif action == "rating":
        await call.message.edit_text("🏆 Reytingni ko'rish uchun <b>/rating KOD</b> deb yozing.\nMasalan: <code>/rating 123</code>", reply_markup=admin_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "close_menu")
async def close_menu(call: CallbackQuery):
    await call.message.delete()

# --- YUKLASH VA REYTING (TEXT HANDLER) ---
@dp.message(F.text.contains("|"))
async def upload_text(msg: types.Message):
    if msg.from_user.id != ADMIN_ID: return
    try:
        lines = msg.text.split('\n')
        code, title, time = map(str.strip, lines[0].split('|'))
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO tests (code, title, duration) VALUES (%s, %s, %s) ON CONFLICT (code) DO UPDATE SET title=%s, duration=%s", (code, title, int(time), title, int(time)))
                cur.execute("DELETE FROM questions WHERE test_code=%s", (code,))
                count = 0
                for l in lines[1:]:
                    if '|' in l:
                        q, o, a = map(str.strip, l.split('|'))
                        cur.execute("INSERT INTO questions (test_code, question, options, correct_answer) VALUES (%s, %s, %s, %s)", (code, q.split('.', 1)[-1].strip(), json.dumps([x.strip() for x in o.split(',')]), a))
                        count += 1
                conn.commit()
        await msg.answer(f"✅ <b>{title}</b> yuklandi! ({count} savol)", parse_mode="HTML")
    except Exception as e: await msg.answer(f"❌ Xato: {e}")

@dp.message(Command("rating"))
async def show_rating(msg: types.Message):
    if msg.from_user.id != ADMIN_ID: return
    try:
        code = msg.text.split()[1]
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_name, score, total FROM results WHERE test_code=%s ORDER BY score DESC LIMIT 10", (code,))
                rows = cur.fetchall()
        res = f"🏆 <b>Reyting ({code}):</b>\n\n" + "\n".join([f"{i+1}. {r[0]} - {r[1]}/{r[2]}" for i, r in enumerate(rows)]) if rows else "Bo'sh."
        await msg.answer(res, parse_mode="HTML")
    except: await msg.answer("Kod xato!")

@dp.message(Command("tanishbilish"))
async def vip(msg: types.Message):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET invite_count=3 WHERE user_id=%s", (msg.from_user.id,))
            conn.commit()
    await msg.answer("✅ VIP status berildi!", reply_markup=main_menu_kb(True))

# --- STARTUP ---
@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
