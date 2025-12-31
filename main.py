import logging
import asyncio
import os
import sqlite3
import json
# Buni importlardan keyin qo'shing
def setup_db():
    conn = sqlite3.connect('quiz.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS tests 
        (code TEXT PRIMARY KEY, title TEXT, duration INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS questions 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, test_code TEXT, 
         question TEXT, options TEXT, correct_answer TEXT)''')
    conn.commit()
    conn.close()

# Buni esa main_loop yoki startup_event ichida chaqiring
setup_db()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

# LOGLARNI SOZLASH (Xatolarni Render Logs'da ko'rish uchun)
logging.basicConfig(level=logging.INFO)

# SIZNING MA'LUMOTLARINGIZ
TOKEN = "432727459:AAFXdus6mheQm8kG50-jpFR2qHu2UUgmqDk" 
ADMIN_ID = 129932291

app = FastAPI()
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Static papkani tekshirish va ulash
if not os.path.exists("static"):
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return {"status": "Server ishlayapti"}

@app.get("/get_test/{code}")
async def get_test(code: str):
    try:
        conn = sqlite3.connect('quiz.db')
        cursor = conn.cursor()
        cursor.execute("SELECT title, duration FROM tests WHERE code=?", (code,))
        test = cursor.fetchone()
        if not test: 
            return {"error": "Test topilmadi"}
        
        cursor.execute("SELECT question, options, correct_answer FROM questions WHERE test_code=?", (code,))
        questions = []
        for q in cursor.fetchall():
            questions.append({
                "q": q[0],
                "o": json.loads(q[1]),
                "a": q[2]
            })
        conn.close()
        return {"title": test[0], "time": test[1], "questions": questions}
    except Exception as e:
        return {"error": str(e)}

@dp.message(Command("start"))
async def start(message: types.Message):
    # DIQQAT: Pastdagi havolani Render'dagi o'z havolangizga almashtiring!
    web_url = "https://test-fzug.onrender.com/static/index.html"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Testni Boshlash 📝", web_app=WebAppInfo(url=web_url))
    ]])
    await message.answer(f"Assalomu alaykum {message.from_user.first_name}!\nTest kodini kiritish uchun pastdagi tugmani bosing.", reply_markup=kb)

@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        text = (
            "🛠 **Admin Panel**\n\n"
            "1. Test yaratish: `kod | fan | vaqt` (minutda)\n"
            "2. Savol qo'shish: `kod | savol | var1,var2,var3 | to'g'ri_javob`"
        )
        await message.answer(text, parse_mode="Markdown")
    else:
        await message.answer("Siz admin emassiz!")

@dp.message(F.text.contains("|"))
async def handle_admin_data(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    parts = message.text.split("|")
    conn = sqlite3.connect('quiz.db')
    cursor = conn.cursor()
    
    try:
        if len(parts) == 3: # Test qo'shish
            cursor.execute("INSERT OR REPLACE INTO tests VALUES (?, ?, ?)", 
                           (parts[0].strip(), parts[1].strip(), int(parts[2].strip())))
            await message.answer("✅ Yangi test bazaga qo'shildi.")
        elif len(parts) == 4: # Savol qo'shish
            options = json.dumps([i.strip() for i in parts[2].split(",")])
            cursor.execute("INSERT INTO questions (test_code, question, options, correct_answer) VALUES (?,?,?,?)",
                           (parts[0].strip(), parts[1].strip(), options, parts[3].strip()))
            await message.answer("➕ Savol muvaffaqiyatli qo'shildi.")
        conn.commit()
    except Exception as e:
        await message.answer(f"❌ Xatolik yuz berdi: {e}")
    finally:
        conn.close()

# Botni fonda ishga tushirish
async def run_bot():
    await dp.start_polling(bot)

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(run_bot())

if __name__ == "__main__":
    import uvicorn
    # Render PORTni avtomatik beradi, agar bermasa 8000 dan foydalanadi
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
