import logging
import asyncio
import os
import sqlite3
import json
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
import uvicorn

# 1. LOGLAR VA SOZLAMALAR
logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "129932291"))
WEBAPP_URL = "https://test-fzug.onrender.com/static/index.html"

app = FastAPI()
bot = Bot(token=TOKEN)
dp = Dispatcher()

# 2. BAZANI TAYYORLASH
def init_db():
    conn = sqlite3.connect('quiz.db', timeout=20)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS tests (code TEXT PRIMARY KEY, title TEXT, duration INTEGER)')
    cursor.execute('CREATE TABLE IF NOT EXISTS questions (id INTEGER PRIMARY KEY AUTOINCREMENT, test_code TEXT, question TEXT, options TEXT, correct_answer TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS results (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, user_name TEXT, nickname TEXT, test_code TEXT, test_title TEXT, score INTEGER, total INTEGER, date TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, invited_by INTEGER, invite_count INTEGER DEFAULT 0, joined_at TEXT)')
    conn.commit()
    conn.close()

init_db()

# 3. SERVER VA API
if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return {"status": "running"}

@app.get("/get_test/{code}")
async def get_test(code: str):
    conn = sqlite3.connect('quiz.db', timeout=20)
    cursor = conn.cursor()
    cursor.execute("SELECT title, duration FROM tests WHERE code=?", (code.strip(),))
    test = cursor.fetchone()
    if not test: 
        conn.close()
        return {"error": "Test topilmadi"}
    cursor.execute("SELECT question, options, correct_answer FROM questions WHERE test_code=?", (code.strip(),))
    questions = [{"q": q[0], "o": json.loads(q[1]), "a": q[2]} for q in cursor.fetchall()]
    conn.close()
    return {"title": test[0], "time": test[1], "questions": questions}

@app.post("/submit_result")
async def submit_result(request: Request):
    try:
        data = await request.json()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        conn = sqlite3.connect('quiz.db', timeout=20)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO results (user_id, user_name, nickname, test_code, test_title, score, total, date) VALUES (?,?,?,?,?,?,?,?)",
                       (data.get('user_id'), data.get('user_name'), data.get('nickname'), data.get('code'), data.get('title'), data.get('score'), data.get('total'), now))
        conn.commit()
        conn.close()
        
        report = (f"🏆 <b>YANGI NATIJA</b>\n\n"
                  f"👤 <b>O'quvchi:</b> {data.get('user_name')}\n"
                  f"📚 <b>Test:</b> {data.get('title')}\n"
                  f"🎯 <b>Natija:</b> {data.get('score')} / {data.get('total')}\n"
                  f"📅 <b>Sana:</b> {now}")
        await bot.send_message(ADMIN_ID, report, parse_mode="HTML")
        return {"status": "success"}
    except Exception as e:
        logging.error(f"Xato: {e}")
        return {"status": "error"}

# 4. BOT BUYRUQLARI
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    user_name = message.from_user.full_name
    username = f"@{message.from_user.username}" if message.from_user.username else "Yo'q"
    args = message.text.split()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn = sqlite3.connect('quiz.db', timeout=20)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    is_new_user = cursor.fetchone() is None
    
    if is_new_user:
        # Yangi foydalanuvchi haqida adminga xabar yuborish
        admin_msg = (f"👤 <b>YANGI FOYDALANUVCHI</b>\n\n"
                     f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
                     f"📛 <b>Ism:</b> {user_name}\n"
                     f"🔗 <b>Username:</b> {username}\n"
                     f"📅 <b>Vaqt:</b> {now}")
        await bot.send_message(ADMIN_ID, admin_msg, parse_mode="HTML")
        
        invited_by = int(args[1]) if len(args) > 1 and args[1].isdigit() and int(args[1]) != user_id else None
        cursor.execute("INSERT INTO users (user_id, invited_by, invite_count, joined_at) VALUES (?, ?, 0, ?)", 
                       (user_id, invited_by, now))
        if invited_by:
            cursor.execute("UPDATE users SET invite_count = invite_count + 1 WHERE user_id=?", (invited_by,))
            try: await bot.send_message(invited_by, "🎉 <b>Yangi taklif!</b> Do'stingiz qo'shildi.", parse_mode="HTML")
            except: pass
        conn.commit()

    # ADMIN UCHUN RUXSAT
    if user_id == ADMIN_ID:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Testni Boshlash (Admin) 📝", web_app=WebAppInfo(url=WEBAPP_URL))]])
        await message.answer(f"👑 <b>Admin xush kelibsiz!</b>", reply_markup=kb, parse_mode="HTML")
    else:
        cursor.execute("SELECT invite_count FROM users WHERE user_id=?", (user_id,))
        invite_count = cursor.fetchone()[0]
        
        if invite_count < 3:
            bot_info = await bot.get_me()
            ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
            text = (f"👋 <b>Assalomu alaykum!</b>\n\nTestni boshlash uchun <b>3 ta</b> do'stingizni taklif qiling.\n"
                    f"Siz taklif qilganlar: <b>{invite_count} / 3</b>\n\nLink: <code>{ref_link}</code>")
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Ulashish", switch_inline_query=f"\nBiologiya testini birga yechamiz! {ref_link}")]])
            await message.answer(text, reply_markup=kb, parse_mode="HTML")
        else:
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Testni Boshlash 📝", web_app=WebAppInfo(url=WEBAPP_URL))]])
            await message.answer(f"✅ <b>Ruxsat berildi!</b>", reply_markup=kb, parse_mode="HTML")
    
    conn.close()

@dp.message(Command("tanishbilish"))
async def tanish_bilish(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect('quiz.db', timeout=20)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (user_id, invite_count) VALUES (?, 3)", (user_id,))
    conn.commit()
    conn.close()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Testni Boshlash 📝", web_app=WebAppInfo(url=WEBAPP_URL))]])
    await message.answer("🤫 <b>Maxsus ruxsat berildi!</b>", reply_markup=kb, parse_mode="HTML")

@dp.message(Command("rating"))
async def show_rating(message: types.Message):
    args = message.text.split()
    if len(args) < 2: return await message.answer("⚠️ Kodni kiriting. Masalan: <code>/rating 001</code>", parse_mode="HTML")
    t_code = args[1].strip()
    conn = sqlite3.connect('quiz.db', timeout=20)
    cursor = conn.cursor()
    cursor.execute("SELECT user_name, score, total FROM results WHERE test_code=? ORDER BY score DESC, date ASC LIMIT 10", (t_code,))
    rows = cursor.fetchall()
    conn.close()
    if not rows: return await message.answer("❌ Bu test bo'yicha natijalar yo'q.")
    res = f"🏆 <b>TEST {t_code} NATIJALARI</b>\n\n"
    rewards = ["🥇 50.000", "🥈 30.000", "🥉 20.000"]
    for i, r in enumerate(rows, 1):
        medal = f"({rewards[i-1]} so'm)" if i <= 3 else "🔹"
        res += f"{i}. <b>{r[0]}</b> — {r[1]}/{r[2]} ball {medal}\n"
    await message.answer(res, parse_mode="HTML")

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("🛠 <b>ADMIN PANEL</b>\n/tests - Ro'yxat\n/users_count - Foydalanuvchilar soni")

@dp.message(Command("users_count"))
async def users_count(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect('quiz.db', timeout=20)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    await message.answer(f"📊 <b>Botdagi jami foydalanuvchilar:</b> {count}")

@dp.message(F.text.contains("|"))
async def handle_upload(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    lines = message.text.split('\n')
    header = lines[0].split('|')
    if len(header) != 3: return
    t_code, t_title, t_time = header[0].strip(), header[1].strip(), header[2].strip()
    conn = sqlite3.connect('quiz.db', timeout=20)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR REPLACE INTO tests VALUES (?,?,?)", (t_code, t_title, int(t_time)))
        cursor.execute("DELETE FROM questions WHERE test_code=?", (t_code,))
        for line in lines[1:]:
            if '|' in line:
                p = line.split('|')
                if len(p) == 3:
                    q_text = p[0].split('.', 1)[-1].strip()
                    opts = json.dumps([i.strip() for i in p[1].split(",")])
                    cursor.execute("INSERT INTO questions (test_code, question, options, correct_answer) VALUES (?,?,?,?)", (t_code, q_text, opts, p[2].strip()))
        conn.commit()
        await message.answer(f"✅ <b>{t_title}</b> muvaffaqiyatli saqlandi!", parse_mode="HTML")
    finally: conn.close()

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
    server = uvicorn.Server(config)
    await asyncio.gather(dp.start_polling(bot), server.serve())

if __name__ == "__main__":
    asyncio.run(main())
