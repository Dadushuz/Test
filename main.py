from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3, json, uvicorn

app = FastAPI()
TOKEN = "432727459:AAFXdus6mheQm8kG50-jpFR2qHu2UUgmqDk"
ADMIN_ID = 129932291  # Telegram ID-ingiz
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Static fayllarni ulash (index.html uchun)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/get_test/{code}")
async def get_test(code: str):
    conn = sqlite3.connect('quiz.db')
    cursor = conn.cursor()
    cursor.execute("SELECT title, duration FROM tests WHERE code=?", (code,))
    test = cursor.fetchone()
    if not test: return {"error": "Not found"}
    cursor.execute("SELECT question, options, correct_answer FROM questions WHERE test_code=?", (code,))
    questions = [{"q": q[0], "o": json.loads(q[1]), "a": q[2]} for q in cursor.fetchall()]
    return {"title": test[0], "time": test[1], "questions": questions}

@dp.message(Command("start"))
async def start(message: types.Message):
    # MUHIM: URL qismiga o'z hostingingiz manzilini yozasiz
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Testni ochish", web_app=WebAppInfo(url="https://test-fzug.onrender.com/static/index.html"))
    ]])
    await message.answer("Assalomu alaykum! Test kodini kiritish uchun tugmani bosing.", reply_markup=kb)

@dp.message(Command("admin"))
async def admin(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("🛠 Admin: `kod | fan | vaqt` yoki `kod | savol | v1,v2,v3 | javob` shaklida yuboring.")

@dp.message(F.text.contains("|"))
async def add_data(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    parts = message.text.split("|")
    conn = sqlite3.connect('quiz.db')
    cursor = conn.cursor()
    if len(parts) == 3: # Test qo'shish
        cursor.execute("INSERT OR REPLACE INTO tests VALUES (?,?,?)", (parts[0].strip(), parts[1].strip(), int(parts[2])))
        await message.answer("✅ Test yaratildi.")
    elif len(parts) == 4: # Savol qo'shish
        cursor.execute("INSERT INTO questions (test_code, question, options, correct_answer) VALUES (?,?,?,?)",
                       (parts[0].strip(), parts[1].strip(), json.dumps([i.strip() for i in parts[2].split(",")]), parts[3].strip()))
        await message.answer("➕ Savol qo'shildi.")
    conn.commit()

# Botni va API-ni birga yurgizish (oddiyroq usul)
import asyncio
async def main():
    loop = asyncio.get_event_loop()
    config = uvicorn.Config(app=app, host="0.0.0.0", port=8000)
    server = uvicorn.Server(config)
    await asyncio.gather(server.serve(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())
                        
