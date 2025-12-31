import logging
import asyncio
import os
import sqlite3
import json
import re
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
# Admin ID raqam ekanligini ta'minlaymiz
ADMIN_ID = int(os.getenv("ADMIN_ID", "129932291")) 
WEBAPP_URL = "https://test-fzug.onrender.com/static/index.html"

app = FastAPI()
bot = Bot(token=TOKEN)
dp = Dispatcher()

# HTML belgilarni tozalash (Xatolikni oldini olish uchun)
def clean_html(text):
    """Matn ichidagi < va > belgilarini va HTML teglarni tozalaydi"""
    if not text: return ""
    text = str(text)
    # Xavfli belgilarni olib tashlash
    clean = re.compile('<.*?>')
    text = re.sub(clean, '', text)
    return text.replace("<", "&lt;").replace(">", "&gt;")

# 2. BAZANI TAYYORLASH
def init_db():
    with sqlite3.connect('quiz.db') as conn:
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS tests (code TEXT PRIMARY KEY, title TEXT, duration INTEGER)')
        cursor.execute('CREATE TABLE IF NOT EXISTS questions (id INTEGER PRIMARY KEY AUTOINCREMENT, test_code TEXT, question TEXT, options TEXT, correct_answer TEXT)')
        cursor.execute('CREATE TABLE IF NOT EXISTS results (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, user_name TEXT, nickname TEXT, test_code TEXT, test_title TEXT, score INTEGER, total INTEGER, date TEXT)')
        cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, invited_by INTEGER, invite_count INTEGER DEFAULT 0, joined_at TEXT)')
        conn.commit()

init_db()

# 3. SERVER VA API
if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return {"status": "🚀 Bot va Server ishlamoqda!"}

@app.get("/get_test/{code}")
async def get_test(code: str):
    try:
        with sqlite3.connect('quiz.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT title, duration FROM tests WHERE code=?", (code.strip(),))
            test = cursor.fetchone()
            
            if not test:
                return {"error": "Bunday kodli test topilmadi!"}
            
            cursor.execute("SELECT question, options, correct_answer FROM questions WHERE test_code=?", (code.strip(),))
            questions = [{"q": q[0], "o": json.loads(q[1]), "a": q[2]} for q in cursor.fetchall()]
            
        return {"title": test[0], "time": test[1], "questions": questions}
    except Exception as e:
        logging.error(f"Test olishda xato: {e}")
        return {"error": "Server xatosi"}

@app.post("/submit_result")
async def submit_result(request: Request):
    try:
        data = await request.json()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        with sqlite3.connect('quiz.db') as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO results (user_id, user_name, nickname, test_code, test_title, score, total, date) VALUES (?,?,?,?,?,?,?,?)",
                           (data.get('user_id'), 
                            clean_html(data.get('user_name')), 
                            data.get('nickname'), 
                            data.get('code'), 
                            data.get('title'), 
                            data.get('score'), 
                            data.get('total'), 
                            now))
            conn.commit()
        
        # Adminga chiroyli xabar
        report = (f"🏆 <b>YANGI NATIJA</b>\n\n"
                  f"👤 <b>O'quvchi:</b> {clean_html(data.get('user_name'))}\n"
                  f"📚 <b>Test:</b> {clean_html(data.get('title'))}\n"
                  f"🔢 <b>Kod:</b> {data.get('code')}\n"
                  f"🎯 <b>Natija:</b> {data.get('score')} / {data.get('total')}\n"
                  f"📅 <b>Vaqt:</b> {now}")
        
        await bot.send_message(ADMIN_ID, report, parse_mode="HTML")
        return {"status": "success"}
    except Exception as e:
        logging.error(f"Natija yuborishda xato: {e}")
        return {"status": "error"}

# 4. BOT BUYRUQLARI
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    full_name = clean_html(message.from_user.full_name)
    username = f"@{message.from_user.username}" if message.from_user.username else "Mavjud emas"
    args = message.text.split()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    with sqlite3.connect('quiz.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
        user_exists = cursor.fetchone()

        if not user_exists:
            # Yangi foydalanuvchi haqida adminni ogohlantirish
            admin_msg = (f"👤 <b>YANGI FOYDALANUVCHI</b>\n\n"
                         f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
                         f"📛 <b>Ism:</b> {full_name}\n"
                         f"🔗 <b>Username:</b> {username}\n"
                         f"📅 <b>Qo'shildi:</b> {now}")
            try:
                await bot.send_message(ADMIN_ID, admin_msg, parse_mode="HTML")
            except: pass

            # Taklif qiluvchini aniqlash
            invited_by = int(args[1]) if len(args) > 1 and args[1].isdigit() and int(args[1]) != user_id else None
            
            cursor.execute("INSERT INTO users (user_id, invited_by, invite_count, joined_at) VALUES (?, ?, 0, ?)", 
                           (user_id, invited_by, now))
            
            if invited_by:
                cursor.execute("UPDATE users SET invite_count = invite_count + 1 WHERE user_id=?", (invited_by,))
                try: await bot.send_message(invited_by, "🎉 <b>Tabriklaymiz!</b> Do'stingiz havola orqali qo'shildi.", parse_mode="HTML")
                except: pass
            conn.commit()

        # Admin uchun menyu
        if user_id == ADMIN_ID:
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Testni Boshlash (Admin) 📝", web_app=WebAppInfo(url=WEBAPP_URL))]])
            await message.answer(f"👑 <b>Xush kelibsiz, Admin!</b>\nSizga cheklovlar yo'q.", reply_markup=kb, parse_mode="HTML")
        else:
            # Oddiy foydalanuvchi uchun
            cursor.execute("SELECT invite_count FROM users WHERE user_id=?", (user_id,))
            invite_count = cursor.fetchone()[0]
            
            if invite_count < 3:
                bot_info = await bot.get_me()
                ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
                
                text = (f"👋 <b>Assalomu alaykum, {full_name}!</b>\n\n"
                        f"Testlarni yechish uchun kamida <b>3 ta</b> do'stingizni taklif qilishingiz kerak.\n\n"
                        f"📊 <b>Sizning takliflaringiz:</b> {invite_count} / 3\n"
                        f"🔗 <b>Sizning havolangiz:</b>\n<code>{ref_link}</code>")
                
                kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Do'stlarga ulashish 🚀", switch_inline_query=f"\nBiologiya testini yechish uchun botga kiring! {ref_link}")]])
                await message.answer(text, reply_markup=kb, parse_mode="HTML")
            else:
                kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Testni Boshlash 📝", web_app=WebAppInfo(url=WEBAPP_URL))]])
                await message.answer(f"✅ <b>Tabriklaymiz!</b> Shart bajarildi.\nTestni boshlashingiz mumkin:", reply_markup=kb, parse_mode="HTML")

@dp.message(Command("tests"))
async def tests_list(message: types.Message):
    # Faqat admin ko'ra oladi
    if message.from_user.id != ADMIN_ID: return
    
    with sqlite3.connect('quiz.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT code, title FROM tests")
        rows = cursor.fetchall()
        
    if not rows:
        return await message.answer("📭 <b>Baza hozircha bo'sh.</b>", parse_mode="HTML")
        
    res = "📋 <b>MAVJUD TESTLAR RO'YXATI:</b>\n\n"
    for r in rows:
        res += f"🔹 <code>{r[0]}</code> - {clean_html(r[1])}\n"
    
    await message.answer(res, parse_mode="HTML")

@dp.message(Command("rating"))
async def rating(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("⚠️ <b>Xato!</b> Kodni kiriting.\nMasalan: <code>/rating 001</code>", parse_mode="HTML")
    
    t_code = args[1].strip()
    
    with sqlite3.connect('quiz.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_name, score, total FROM results WHERE test_code=? ORDER BY score DESC, date ASC LIMIT 10", (t_code,))
        rows = cursor.fetchall()
        
    if not rows:
        return await message.answer("❌ <b>Natijalar yo'q.</b>", parse_mode="HTML")
        
    res = f"🏆 <b>TEST {t_code} — TOP REYTING:</b>\n\n"
    rewards = ["🥇", "🥈", "🥉"]
    
    for i, r in enumerate(rows, 1):
        medal = rewards[i-1] if i <= 3 else f"{i}."
        res += f"{medal} <b>{clean_html(r[0])}</b> — {r[1]}/{r[2]}\n"
        
    await message.answer(res, parse_mode="HTML")

@dp.message(Command("tanishbilish"))
async def tanish_bilish(message: types.Message):
    user_id = message.from_user.id
    
    with sqlite3.connect('quiz.db') as conn:
        cursor = conn.cursor()
        # Foydalanuvchi takliflarini sun'iy ravishda 3 taga yetkazamiz
        cursor.execute("INSERT OR REPLACE INTO users (user_id, invite_count) VALUES (?, 3)", (user_id,))
        conn.commit()
        
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Testni Boshlash 📝", web_app=WebAppInfo(url=WEBAPP_URL))]])
    await message.answer("🤫 <b>Maxsus ruxsat berildi!</b>\nBemalol testga kirishingiz mumkin.", reply_markup=kb, parse_mode="HTML")

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    text = (
        "🛠 <b>ADMIN PANEL</b>\n\n"
        "📋 /tests - Testlar ro'yxati\n"
        "👥 /users_count - Foydalanuvchilar soni\n"
        "🏆 /rating [kod] - Reytingni ko'rish\n"
        "📥 <b>Test yuklash:</b> Menga quyidagi formatda fayl yoki matn yuboring:\n"
        "<code>kod | mavzu | vaqt</code>\n"
        "<code>1. Savol | A, B, C | A</code>"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("users_count"))
async def users_count(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    with sqlite3.connect('quiz.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        
    await message.answer(f"📊 <b>Jami foydalanuvchilar:</b> {count} nafar", parse_mode="HTML")

@dp.message(F.text.contains("|"))
async def upload_test(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    lines = message.text.split('\n')
    header = lines[0].split('|')
    
    if len(header) != 3:
        return await message.answer("⚠️ <b>Format xato!</b>\nBirinchi qator: <code>kod | mavzu | vaqt</code> bo'lishi shart.", parse_mode="HTML")
    
    t_code = header[0].strip()
    t_title = header[1].strip()
    t_time = header[2].strip()
    
    try:
        with sqlite3.connect('quiz.db') as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO tests VALUES (?,?,?)", (t_code, t_title, int(t_time)))
            cursor.execute("DELETE FROM questions WHERE test_code=?", (t_code,))
            
            count = 0
            for line in lines[1:]:
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) == 3:
                        q_text = parts[0].split('.', 1)[-1].strip()
                        opts = json.dumps([i.strip() for i in parts[1].split(",")])
                        correct = parts[2].strip()
                        
                        cursor.execute("INSERT INTO questions (test_code, question, options, correct_answer) VALUES (?,?,?,?)", 
                                       (t_code, q_text, opts, correct))
                        count += 1
            conn.commit()
            
        await message.answer(f"✅ <b>{clean_html(t_title)}</b> muvaffaqiyatli saqlandi!\n📝 Jami savollar: {count} ta", parse_mode="HTML")
        
    except Exception as e:
        await message.answer(f"❌ Xatolik yuz berdi: {e}")

# 5. ISHGA TUSHIRISH
async def main():
    # Eski webhooklarni o'chirish (Conflict xatosini yo'qotadi)
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Serverni sozlash
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
    server = uvicorn.Server(config)
    
    # Bot va Serverni birga ishga tushirish
    await asyncio.gather(dp.start_polling(bot), server.serve())

if __name__ == "__main__":
    asyncio.run(main())
