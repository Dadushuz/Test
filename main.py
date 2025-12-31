import logging
import asyncio
import os
import sqlite3
import json
from datetime import datetime
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

# 1. LOGLAR VA SOZLAMALAR
logging.basicConfig(level=logging.INFO)
TOKEN = "432727459:AAFXdus6mheQm8kG50-jpFR2qHu2UUgmqDk" 
ADMIN_ID = 129932291

app = FastAPI()
bot = Bot(token=TOKEN)
dp = Dispatcher()

# 2. BAZANI TAYYORLASH
def init_db():
    conn = sqlite3.connect('quiz.db')
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
async def root(): return {"status": "IKRAMOV BIOLOGIYA server ishlayapti"}

@app.get("/get_test/{code}")
async def get_test(code: str):
    conn = sqlite3.connect('quiz.db')
    cursor = conn.cursor()
    cursor.execute("SELECT title, duration FROM tests WHERE code=?", (code,))
    test = cursor.fetchone()
    if not test: return {"error": "Topilmadi"}
    cursor.execute("SELECT question, options, correct_answer FROM questions WHERE test_code=?", (code,))
    questions = [{"q": q[0], "o": json.loads(q[1]), "a": q[2]} for q in cursor.fetchall()]
    conn.close()
    return {"title": test[0], "time": test[1], "questions": questions}

# 4. ADMIN VA USER BUYRUQLARI
@dp.message(Command("start"))
async def start(message: types.Message):
    # SIZNING YANGI MANZILINGIZ:
    web_url = "https://test-fzug.onrender.com/static/index.html"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Testni Boshlash 📝", web_app=WebAppInfo(url=web_url))
    ]])
    await message.answer(
        f"Assalomu alaykum {message.from_user.first_name}!\n\n"
        "IKRAMOV BIOLOGIYA test platformasiga xush kelibsiz. "
        "Testni boshlash uchun quyidagi tugmani bosing:", 
        reply_markup=kb
    )

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    text = (
        "🛠 **IKRAMOV BIOLOGIYA | ADMIN PANEL**\n\n"
        "🔸 **Test yuklash (Bulk):**\n`kod | fan | vaqt` (keyingi qatordan savollar)\n\n"
        "🔸 **Buyruqlar:**\n"
        "/tests - Barcha testlar ro'yxati\n"
        "/stat - Oxirgi natijalarni ko'rish\n"
        "/del_test [kod] - Testni o'chirish"
    )
    await message.answer(text, parse_mode="Markdown")

# 5. TESTLARNI YUKLASH VA YANGILASH
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
        count = 0
        for line in lines[1:]:
            if '|' in line:
                q_p = line.split('|')
                if len(q_p) == 3:
                    q_text = q_p[0].split('.', 1)[-1].strip()
                    opts = json.dumps([i.strip() for i in q_p[1].split(",")])
                    cursor.execute("INSERT INTO questions (test_code, question, options, correct_answer) VALUES (?,?,?,?)",
                                   (test_code, q_text, opts, q_p[2].strip()))
                    count += 1
        conn.commit()
        await message.answer(f"✅ **{title}** muvaffaqiyatli saqlandi!\n📝 Jami savollar: {count} ta.")
    except Exception as e: await message.answer(f"❌ Xato yuz berdi: {e}")
    finally: conn.close()

# 6. TESTLARNI BOSHQARISH (RO'YXAT VA O'CHIRISH)
@dp.message(Command("tests"))
async def list_tests(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect('quiz.db')
    cursor = conn.cursor()
    cursor.execute("SELECT code, title FROM tests")
    rows = cursor.fetchall()
    conn.close()
    if not rows: return await message.answer("Bazangiz hozircha bo'sh.")
    msg = "📋 **Mavjud testlar:**\n" + "\n".join([f"`{r[0]}` - {r[1]}" for r in rows])
    await message.answer(msg, parse_mode="Markdown")

@dp.message(F.text.startswith("/del_test"))
async def delete_test(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        code = message.text.split()[-1]
        conn = sqlite3.connect('quiz.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tests WHERE code=?", (code,))
        cursor.execute("DELETE FROM questions WHERE test_code=?", (code,))
        conn.commit()
        conn.close()
        await message.answer(f"🗑 Test `{code}` va uning savollari bazadan o'chirildi.")
    except:
        await message.answer("Format: `/del_test kod`")

# 7. NATIJALARNI KO'RISH
@dp.message(Command("stat"))
async def show_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect('quiz.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_name, nickname, test_title, score, total, date FROM results ORDER BY id DESC LIMIT 20")
    rows = cursor.fetchall()
    conn.close()
    if not rows: return await message.answer("Natijalar hali mavjud emas.")
    
    text = "📊 **So'nggi 20 ta natija:**\n\n"
    for r in rows:
        text += f"👤 {r[0]} ({r[1]})\n📚 {r[2]}: {r[3]}/{r[4]}\n📅 {r[5]}\n" + "-"*15 + "\n"
    await message.answer(text)

# 8. WEB APP NATIJALARINI QABUL QILISH
@dp.message(F.web_app_data)
async def result_handler(message: types.Message):
    data = json.loads(message.web_app_data.data)
    user_name = message.from_user.full_name
    nickname = f"@{message.from_user.username}" if message.from_user.username else "Mavjud emas"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    conn = sqlite3.connect('quiz.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO results (user_id, user_name, nickname, test_code, test_title, score, total, date) VALUES (?,?,?,?,?,?,?,?)",
                   (message.from_user.id, user_name, nickname, data['code'], data['title'], data['score'], data['total'], now))
    conn.commit()
    conn.close()

    admin_report = (
        f"🔔 **YANGI NATIJA**\n\n"
        f"👤 O'quvchi: {user_name}\n"
        f"🆔 Username: {nickname}\n"
        f"📚 Test: {data['title']} ({data['code']})\n"
        f"🎯 Ball: {data['score']} / {data['total']}\n"
        f"📅 Sana: {now}"
    )
    await bot.send_message(ADMIN_ID, admin_report, parse_mode="Markdown")
    await message.answer(f"🏁 Test tugadi! Ballingiz: {data['score']}/{data['total']}")

# 9. ASOSIY QISIM
async def main():
    # Botni ishga tushirish (xatoliklarni ko'rsatish bilan)
    try:
        logging.info("Bot polling boshlanmoqda...")
        # Webhook bor bo'lsa o'chirib, keyin polling boshlaydi
        await bot.delete_webhook(drop_pending_updates=True)
        asyncio.create_task(dp.start_polling(bot))
    except Exception as e:
        logging.error(f"Botni ishga tushirishda xato: {e}")

    import uvicorn
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
    server = uvicorn.Server(config)
    await server.serve()
    
    
