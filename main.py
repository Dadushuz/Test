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
    except: return {"status": "error"}

# 4. BOT BUYRUQLARI
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    if user_id == ADMIN_ID:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Testni Boshlash (Admin) 📝", web_app=WebAppInfo(url=WEBAPP_URL))]])
        return await message.answer(f"👑 <b>Xush kelibsiz, Admin!</b>", reply_markup=kb, parse_mode="HTML")
    
    # Taklif tizimi (Siz xohlagandek)
    # ... (taklif mantiqi shu yerda)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Testni Boshlash 📝", web_app=WebAppInfo(url=WEBAPP_URL))]])
    await message.answer("✅ <b>Testni boshlashingiz mumkin:</b>", reply_markup=kb, parse_mode="HTML")

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Testlar", callback_data="list_tests"), 
         InlineKeyboardButton(text="📊 Statistika", callback_data="show_stat")]
    ])
    await message.answer("🛠 <b>Admin Panel:</b>", reply_markup=kb, parse_mode="HTML")

# STATISTIKANI CHIQARISH (TO'G'RILANGAN)
@dp.callback_query(F.data == "show_stat")
async def cb_stat(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect('quiz.db', timeout=20)
    cursor = conn.cursor()
    cursor.execute("SELECT user_name, test_title, score, total, date FROM results ORDER BY id DESC LIMIT 15")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return await callback.message.answer("📊 <b>Hozircha natijalar yo'q.</b>", parse_mode="HTML")

    res = "📊 <b>Oxirgi 15 ta natija:</b>\n\n"
    for r in rows:
        res += f"👤 {r[0]}\n📚 {r[1]}: <b>{r[2]}/{r[3]}</b>\n📅 {r[4]}\n" + "-"*15 + "\n"
    
    await callback.message.answer(res, parse_mode="HTML")
    await callback.answer()

# 5. ISHGA TUSHIRISH
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    # SERVERNI ISHGA TUSHIRISH
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
    server = uvicorn.Server(config)
    
    await asyncio.gather(
        dp.start_polling(bot),
        server.serve()
    )

if __name__ == "__main__":
    asyncio.run(main())
