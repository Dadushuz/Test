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
# ADMIN_ID ni Render panelidan olish yoki shu yerga raqam yozish
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

# 3. STATIC FAYLLAR VA SERVER
if not os.path.exists("static"): 
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

# 4. API ENDPOINTLAR
@app.get("/")
async def root(): 
    return {"status": "IKRAMOV BIOLOGIYA server ishlayapti"}

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
        logging.error(f"Natija yuborishda xato: {e}")
        return {"status": "error"}

# 5. BOT BUYRUQLARI
@dp.message(Command("start"))
async def start(message: types.Message):
    # O'zingizning Render manzilingizni tekshiring
    web_url = "https://test-fzug.onrender.com/static/index.html"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Testni Boshlash 📝", web_app=WebAppInfo(url=web_url))
    ]])
    await message.answer(
        f"Assalomu alaykum <b>{message.from_user.first_name}</b>!\n"
        "IKRAMOV BIOLOGIYA platformasiga xush kelibsiz!", 
        reply_markup=kb, 
        parse_mode="HTML"
    )

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    text = "<b>🛠 ADMIN PANEL</b>\n\n/tests - Ro'yxat\n/stat - Natijalar\n/del_test [kod]"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text.contains("|"))
async def handle_bulk_data(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    lines = message.text.split('\n')
    header = lines[0].split('|')
    if len(header) != 3: return
    test_code, title, time = header[0].strip(), header[1].strip(), header[2].strip()
    conn = sqlite3.connect('quiz.db')
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR REPLACE INTO tests VALUES (?, ?, ?)", (test_code, title, int(time)))
        cursor.execute("DELETE FROM questions WHERE test_code=?", (test_code,))
        for line in lines[1:]:
            if '|' in line:
                q_p = line.split('|')
                if len(q_p) == 3:
                    q_text = q_p[0].split('.', 1)[-1].strip()
                    opts = json.dumps([i.strip() for i in q_p[1].split(",")])
                    cursor.execute("INSERT INTO questions (test_code, question, options, correct_answer) VALUES (?,?,?,?)",
                                   (test_code, q_text, opts, q_p[2].strip()))
        conn.commit()
        await message.answer(f"✅ <b>{title}</b> saqlandi!", parse_mode="HTML")
    finally: conn.close()

@dp.message(Command("stat"))
async def show_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect('quiz.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_name, test_title, score, total FROM results ORDER BY id DESC LIMIT 15")
    rows = cursor.fetchall()
    conn.close()
    if not rows: return await message.answer("Natijalar yo'q.")
    res = "📊 <b>Oxirgi natijalar:</b>\n\n" + "\n".join([f"👤 {r[0]} | {r[1]}: {r[2]}/{r[3]}" for r in rows])
    await message.answer(res, parse_mode="HTML")

# 6. ASOSIY ISHGA TUSHIRISH
async def run_bot():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

async def run_server():
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    await asyncio.gather(
        run_bot(),
        run_server()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("To'xtatildi")
