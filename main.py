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
# ADMIN_ID raqam ekanligiga ishonch hosil qiling
ADMIN_ID = int(os.getenv("ADMIN_ID", "129932291"))

app = FastAPI()
bot = Bot(token=TOKEN)
dp = Dispatcher()

# 2. BAZANI TAYYORLASH (XAVFSIZLIK BILAN)
def init_db():
    conn = sqlite3.connect('quiz.db', timeout=20)
    cursor = conn.cursor()
    # Testlar jadvali
    cursor.execute('''CREATE TABLE IF NOT EXISTS tests 
        (code TEXT PRIMARY KEY, title TEXT, duration INTEGER)''')
    # Savollar jadvali
    cursor.execute('''CREATE TABLE IF NOT EXISTS questions 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, test_code TEXT, 
         question TEXT, options TEXT, correct_answer TEXT)''')
    # Natijalar jadvali
    cursor.execute('''CREATE TABLE IF NOT EXISTS results 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, user_name TEXT, 
         nickname TEXT, test_code TEXT, test_title TEXT, score INTEGER, total INTEGER, date TEXT)''')
    conn.commit()
    conn.close()

init_db()

# 3. STATIC FAYLLAR VA SERVER
if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root(): 
    return {"status": "🚀 IKRAMOV BIOLOGIYA serveri muvaffaqiyatli ishlayapti"}

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

# NATIJANI QABUL QILISH API
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

        # Adminga chiroyli xabar yuborish
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
        return {"status": "error"}

# 4. BOT BUYRUQLARI
@dp.message(Command("start"))
async def start(message: types.Message):
    web_url = "https://test-fzug.onrender.com/static/index.html"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Testni Boshlash 📝", web_app=WebAppInfo(url=web_url))
    ]])
    await message.answer(
        f"Assalomu alaykum <b>{message.from_user.first_name}</b>! 🌿\n\n"
        "<b>IKRAMOV BIOLOGIYA</b> platformasiga xush kelibsiz.\n"
        "Bilimingizni sinash uchun quyidagi tugmani bosing:", 
        reply_markup=kb, 
        parse_mode="HTML"
    )

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    text = (
        "<b>🛠 ADMIN PANELIGA XUSH KELIBSIZ!</b>\n\n"
        "📋 /tests - Mavjud testlar ro'yxati\n"
        "📊 /stat - Oxirgi natijalarni ko'rish\n"
        "🗑 <code>/del_test kod</code> - Testni o'chirish\n\n"
        "📥 <b>Yangi test yuklash uchun quyidagicha yuboring:</b>\n"
        "<code>kod | Fan nomi | Vaqt</code>\n"
        "<code>1. Savol matni | A, B, C | To'g'ri javob</code>"
    )
    await message.answer(text, parse_mode="HTML")

# 5. TESTLARNI YUKLASH VA SAQLASH
@dp.message(F.text.contains("|"))
async def handle_bulk_data(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    lines = message.text.split('\n')
    header = lines[0].split('|')
    if len(header) != 3: return

    test_code, title, time = header[0].strip(), header[1].strip(), header[2].strip()
    conn = sqlite3.connect('quiz.db', timeout=20)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR REPLACE INTO tests VALUES (?, ?, ?)", (test_code, title, int(time)))
        cursor.execute("DELETE FROM questions WHERE test_code=?", (test_code,))
        count = 0
        for line in lines[1:]:
            if '|' in line:
                parts = line.split('|')
                if len(parts) == 3:
                    q_text = parts[0].split('.', 1)[-1].strip()
                    opts = json.dumps([i.strip() for i in parts[1].split(",")])
                    cursor.execute("INSERT INTO questions (test_code, question, options, correct_answer) VALUES (?,?,?,?)",
                                   (test_code, q_text, opts, parts[2].strip()))
                    count += 1
        conn.commit()
        await message.answer(f"✅ <b>{title}</b> muvaffaqiyatli saqlandi!\n📝 Jami savollar: {count} ta.", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Xatolik yuz berdi: {e}")
    finally: conn.close()

@dp.message(Command("tests"))
async def list_tests(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect('quiz.db', timeout=20)
    cursor = conn.cursor()
    cursor.execute("SELECT code, title FROM tests")
    rows = cursor.fetchall()
    conn.close()
    if not rows: return await message.answer("📭 <b>Baza hozircha bo'sh.</b>", parse_mode="HTML")
    
    msg = "📋 <b>MAVJUD TESTLAR RO'YXATI:</b>\n\n"
    for r in rows:
        msg += f"🔹 <code>{r[0]}</code> - {r[1]}\n"
    await message.answer(msg, parse_mode="HTML")

@dp.message(Command("stat"))
async def show_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect('quiz.db', timeout=20)
    cursor = conn.cursor()
    cursor.execute("SELECT user_name, test_title, score, total FROM results ORDER BY id DESC LIMIT 20")
    rows = cursor.fetchall()
    conn.close()
    if not rows: return await message.answer("📊 <b>Hozircha natijalar yo'q.</b>", parse_mode="HTML")
    
    text = "📊 <b>SO'NGGI 20 TA NATIJA:</b>\n\n"
    for r in rows:
        text += f"👤 {r[0]}\n📚 {r[1]}: <b>{r[2]}/{r[3]}</b>\n" + "-"*15 + "\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text.startswith("/del_test"))
async def delete_test(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        code = message.text.split()[-1]
        conn = sqlite3.connect('quiz.db', timeout=20)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tests WHERE code=?", (code,))
        cursor.execute("DELETE FROM questions WHERE test_code=?", (code,))
        conn.commit()
        conn.close()
        await message.answer(f"🗑 Test <code>{code}</code> o'chirildi.", parse_mode="HTML")
    except:
        await message.answer("⚠️ Format: <code>/del_test kod</code>", parse_mode="HTML")

# 6. ASOSIY ISHGA TUSHIRISH
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
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot to'xtatildi")
