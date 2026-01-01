import logging
import asyncio
import os
import json
import re
import psycopg2
import random
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton, Update
import uvicorn

# --- LOGGING SOZLAMALARI ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- ENV O'ZGARUVCHILARI ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "129932291"))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "https://test-fzug.onrender.com")

# URL-larni shakllantirish (oxiridagi slashlarni olib tashlaymiz)
RENDER_EXTERNAL_URL = RENDER_EXTERNAL_URL.rstrip('/')
WEBAPP_URL = f"{RENDER_EXTERNAL_URL}/static/index.html"
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

# Supabase ulanishi (Pooler manzili)
DATABASE_URL = "postgresql://postgres.zvtrujwsydewfcaotwvx:rkbfVJlp96S85bnu@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"

# --- OBYEKTLAR ---
app = FastAPI()
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- BAZA BILAN ISHLASH ---
def clean(text):
    if not text: return ""
    text = str(text)
    return re.sub(r'<.*?>', '', text).replace('<', '&lt;').replace('>', '&gt;')

def get_db():
    return psycopg2.connect(DATABASE_URL, connect_timeout=10)

def init_db():
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('''CREATE TABLE IF NOT EXISTS tests (code TEXT PRIMARY KEY, title TEXT, duration INTEGER)''')
                cur.execute('''CREATE TABLE IF NOT EXISTS questions (id SERIAL PRIMARY KEY, test_code TEXT, question TEXT, options TEXT, correct_answer TEXT)''')
                cur.execute('''CREATE TABLE IF NOT EXISTS results (id SERIAL PRIMARY KEY, user_id BIGINT, user_name TEXT, nickname TEXT, test_code TEXT, test_title TEXT, score INTEGER, total INTEGER, date TEXT)''')
                cur.execute('''CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, invited_by BIGINT, invite_count INTEGER DEFAULT 0, joined_at TEXT)''')
                conn.commit()
        logger.info("✅ Baza muvaffaqiyatli ulandi!")
    except Exception as e:
        logger.error(f"❌ Baza ulanishida xatolik: {e}")

init_db()

# --- STATIC FAYLLAR ---
if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- FASTAPI ENDPOINTLARI ---
@app.get("/")
async def root(): 
    return {"status": "🚀 Bot Webhook rejimida ishlayapti!", "url": WEBHOOK_URL}

@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    try:
        update_data = await request.json()
        update = Update.model_validate(update_data, context={"bot": bot})
        await dp.feed_update(bot, update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"⚠️ Webhook error: {e}")
        return {"ok": False}

# --- TEST API-LARI ---
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

# --- BOT HANDLERLARI (YANGILANGAN) ---

# 1. Echo Handler (Bot ishlayotganini tekshirish uchun - ENG TEPADA)
@dp.message(F.text & ~F.text.startswith('/'))
async def echo_handler(msg: types.Message):
    logger.info(f"📩 Xabar keldi: {msg.text} (ID: {msg.from_user.id})")
    # Bu qism bot har qanday matnga javob berishini ta'minlaydi
    await msg.answer(f"🤖 Bot ishlayapti!\nSizning ID: <code>{msg.from_user.id}</code>\nXabaringiz: {msg.text}", parse_mode="HTML")

# 2. Start komandasi
@dp.message(Command("start"))
async def start(msg: types.Message):
    uid, name = msg.from_user.id, clean(msg.from_user.full_name)
    args = msg.text.split()
    
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT invite_count FROM users WHERE user_id=%s", (uid,))
                user = cur.fetchone()
                
                if not user:
                    inviter = int(args[1]) if len(args) > 1 and args[1].isdigit() and int(args[1]) != uid else None
                    cur.execute("INSERT INTO users (user_id, invited_by, invite_count, joined_at) VALUES (%s, %s, 0, %s)", 
                                (uid, inviter, datetime.now().strftime("%Y-%m-%d %H:%M")))
                    if inviter:
                        cur.execute("UPDATE users SET invite_count = invite_count + 1 WHERE user_id=%s", (inviter,))
                        try: await bot.send_message(inviter, "🎉 <b>Do'stingiz qo'shildi!</b>", parse_mode="HTML")
                        except: pass
                    conn.commit()
                    count = 0
                else:
                    count = user[0]

        if uid == ADMIN_ID or count >= 3:
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Testni Boshlash 📝", web_app=WebAppInfo(url=WEBAPP_URL))]])
            await msg.answer(f"✅ <b>Xush kelibsiz!</b>\nSizda {count} ta taklif bor. Testga kirishingiz mumkin.", reply_markup=kb, parse_mode="HTML")
        else:
            link = f"https://t.me/{(await bot.get_me()).username}?start={uid}"
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Ulashish", switch_inline_query=f"\nTest yechamiz! {link}")]])
            await msg.answer(f"👋 <b>Salom {name}!</b>\n\nTest yechish uchun <b>3 ta</b> do'stingizni chaqiring.\n📊 Sizda: <b>{count} / 3</b>\n🔗 Link: <code>{link}</code>", reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Start error: {e}")
        await msg.answer("⚠️ Bazada texnik uzilish. Birozdan so'ng urinib ko'ring.")

# 3. Admin buyruqlari
@dp.message(Command("admin"))
async def admin_panel(msg: types.Message):
    if msg.from_user.id == ADMIN_ID:
        await msg.answer("🛠 <b>Admin Panel:</b>\n/tests - Ro'yxat\n/users_count - Statistika", parse_mode="HTML")

@dp.message(F.text.contains("|"))
async def upload_test(msg: types.Message):
    if msg.from_user.id != ADMIN_ID: return
    try:
        lines = msg.text.split('\n')
        code, title, time = map(str.strip, lines[0].split('|'))
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO tests (code, title, duration) VALUES (%s, %s, %s) ON CONFLICT (code) DO UPDATE SET title=%s, duration=%s", (code, title, int(time), title, int(time)))
                cur.execute("DELETE FROM questions WHERE test_code=%s", (code,))
                for l in lines[1:]:
                    if '|' in l:
                        q, o, a = map(str.strip, l.split('|'))
                        cur.execute("INSERT INTO questions (test_code, question, options, correct_answer) VALUES (%s, %s, %s, %s)", (code, q.split('.', 1)[-1].strip(), json.dumps([x.strip() for x in o.split(',')]), a))
                conn.commit()
        await msg.answer(f"✅ <b>{title}</b> muvaffaqiyatli yuklandi!")
    except Exception as e:
        await msg.answer(f"❌ Yuklashda xato: {e}")

# --- STARTUP / SHUTDOWN ---
@app.on_event("startup")
async def on_startup():
    logger.info("Setting webhook...")
    await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)

@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Closing bot session...")
    await bot.session.close()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
