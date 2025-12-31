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

# 1. SOZLAMALAR
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
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, invited_by INTEGER, invite_count INTEGER DEFAULT 0)')
    conn.commit()
    conn.close()

init_db()

# 3. SERVER VA API
if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/get_test/{code}")
async def get_test(code: str):
    conn = sqlite3.connect('quiz.db', timeout=20)
    cursor = conn.cursor()
    cursor.execute("SELECT title, duration FROM tests WHERE code=?", (code,))
    test = cursor.fetchone()
    if not test: 
        conn.close()
        return {"error": "Topilmadi"}
    cursor.execute("SELECT question, options, correct_answer FROM questions WHERE test_code=?", (code,))
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
        
        report = (f"🏆 <b>YANGI NATIJA</b>\n\n👤 <b>O'quvchi:</b> {data.get('user_name')}\n"
                  f"📚 <b>Test:</b> {data.get('title')}\n🎯 <b>Natija:</b> {data.get('score')} / {data.get('total')}\n📅 {now}")
        await bot.send_message(ADMIN_ID, report, parse_mode="HTML")
        return {"status": "success"}
    except: return {"status": "error"}

# 4. BOT BUYRUQLARI
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    
    if user_id == ADMIN_ID:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Testni Boshlash (Admin) 📝", web_app=WebAppInfo(url=WEBAPP_URL))]])
        return await message.answer(f"👑 <b>Xush kelibsiz, Admin!</b>", reply_markup=kb, parse_mode="HTML")

    conn = sqlite3.connect('quiz.db', timeout=20)
    cursor = conn.cursor()
    cursor.execute("SELECT invite_count FROM users WHERE user_id=?", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        invited_by = int(args[1]) if len(args) > 1 and args[1].isdigit() and int(args[1]) != user_id else None
        cursor.execute("INSERT INTO users (user_id, invited_by, invite_count) VALUES (?, ?, 0)", (user_id, invited_by, 0))
        if invited_by:
            cursor.execute("UPDATE users SET invite_count = invite_count + 1 WHERE user_id=?", (invited_by,))
            try: await bot.send_message(invited_by, "🎉 Do'stingiz qo'shildi!", parse_mode="HTML")
            except: pass
        conn.commit()
        invite_count = 0
    else:
        invite_count = user[0]
    conn.close()

    if invite_count < 3:
        bot_info = await bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
        text = (f"👋 <b>Assalomu alaykum!</b>\n\nTestga kirish uchun 3 ta do'st taklif qiling.\n"
                f"Takliflar: <b>{invite_count} / 3</b>\n<code>{ref_link}</code>")
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Ulashish 🚀", switch_inline_query=f"\nBiologiya testi: {ref_link}")]])
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Testni Boshlash 📝", web_app=WebAppInfo(url=WEBAPP_URL))]])
        await message.answer(f"✅ <b>Ruxsat berildi!</b>", reply_markup=kb, parse_mode="HTML")

# --- YANGI KOMANDA: /tanishbilish ---
@dp.message(Command("tanishbilish"))
async def vip_access(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect('quiz.db', timeout=20)
    cursor = conn.cursor()
    # Foydalanuvchini bazada yangilash yoki qo'shish, taklifni 3 taga tenglash
    cursor.execute("INSERT OR REPLACE INTO users (user_id, invited_by, invite_count) VALUES (?, ?, 3)", (user_id, None))
    conn.commit()
    conn.close()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Testni Boshlash 📝", web_app=WebAppInfo(url=WEBAPP_URL))]])
    await message.answer("🤫 <b>Tanish-bilish ishga tushdi!</b>\nSizga testga kirish uchun maxsus ruxsat berildi.", reply_markup=kb, parse_mode="HTML")

@dp.message(Command("tests"))
async def list_tests(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect('quiz.db', timeout=20)
    cursor = conn.cursor()
    cursor.execute("SELECT code, title FROM tests")
    rows = cursor.fetchall()
    conn.close()
    if not rows: return await message.answer("Baza bo'sh.")
    res = "📋 <b>Testlar:</b>\n" + "\n".join([f"🔹 <code>{r[0]}</code> - {r[1]}" for r in rows])
    await message.answer(res, parse_mode="HTML")

@dp.message(Command("stat"))
async def show_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect('quiz.db', timeout=20)
    cursor = conn.cursor()
    cursor.execute("SELECT user_name, test_title, score, total FROM results ORDER BY id DESC LIMIT 15")
    rows = cursor.fetchall()
    conn.close()
    if not rows: return await message.answer("Natijalar yo'q.")
    res = "📊 <b>Natijalar:</b>\n" + "\n".join([f"👤 {r[0]} | {r[1]}: {r[2]}/{r[3]}" for r in rows])
    await message.answer(res, parse_mode="HTML")

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
        await message.answer(f"✅ <b>{t_title}</b> saqlandi!", parse_mode="HTML")
    except Exception as e: await message.answer(f"Xato: {e}")
    finally: conn.close()

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
    server = uvicorn.Server(config)
    await asyncio.gather(dp.start_polling(bot), server.serve())

if __name__ == "__main__":
    asyncio.run(main())
