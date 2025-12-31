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

app = FastAPI()
bot = Bot(token=TOKEN)
dp = Dispatcher()

# 2. BAZANI TAYYORLASH
def init_db():
    conn = sqlite3.connect('quiz.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS tests (code TEXT PRIMARY KEY, title TEXT, duration INTEGER)')
    cursor.execute('CREATE TABLE IF NOT EXISTS questions (id INTEGER PRIMARY KEY AUTOINCREMENT, test_code TEXT, question TEXT, options TEXT, correct_answer TEXT)')
    cursor.execute('''CREATE TABLE IF NOT EXISTS results 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, user_name TEXT, 
         nickname TEXT, test_code TEXT, test_title TEXT, score INTEGER, total INTEGER, date TEXT)''')
    conn.commit()
    conn.close()

init_db()

# 3. STATIC FAYLLAR
if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

# 4. API ENDPOINTLAR
@app.get("/get_test/{code}")
async def get_test(code: str):
    conn = sqlite3.connect('quiz.db')
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
        
        # Bazaga saqlash
        conn = sqlite3.connect('quiz.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO results (user_id, user_name, nickname, test_code, test_title, score, total, date) VALUES (?,?,?,?,?,?,?,?)",
                       (data.get('user_id'), data.get('user_name'), data.get('nickname'), data.get('code'), data.get('title'), data.get('score'), data.get('total'), now))
        conn.commit()
        conn.close()

        # Adminga yuborish
        report = (
            f"🏆 <b>YANGI NATIJA</b>\n\n"
            f"👤 <b>O'quvchi:</b> {data.get('user_name')}\n"
            f"🆔 <b>Username:</b> {data.get('nickname')}\n"
            f"📚 <b>Test:</b> {data.get('title')}\n"
            f"🎯 <b>Natija:</b> {data.get('score')} / {data.get('total')}\n"
            f"📅 <b>Sana:</b> {now}"
        )
        await bot.send_message(ADMIN_ID, report, parse_mode="HTML")
        return {"status": "success"}
    except Exception as e:
        logging.error(f"Natija qabul qilishda xato: {e}")
        return {"status": "error", "message": str(e)}

# 5. BOT BUYRUQLARI
@dp.message(Command("start"))
async def start(message: types.Message):
    web_url = "https://test-fzug.onrender.com/static/index.html"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Testni Boshlash 📝", web_app=WebAppInfo(url=web_url))
    ]])
    await message.answer(f"Assalomu alaykum <b>{message.from_user.first_name}</b>!\nIKRAMOV BIOLOGIYA testiga xush kelibsiz!", reply_markup=kb, parse_mode="HTML")

# ... (Admin buyruqlari: /admin, /tests, /stat avvalgi kod bilan bir xil)

# 6. ISHGA TUSHIRISH
async def run_bot():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

async def run_server():
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    await asyncio.gather(run_bot(), run_server())

if __name__ == "__main__":
    asyncio.run(main())
