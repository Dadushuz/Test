import logging
import asyncio
import os
import json
import re
import psycopg2
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
import uvicorn

# --- SOZLAMALAR ---
logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("BOT_TOKEN")
# Agar Admin ID raqam bo'lmasa, xato bermasligi uchun try-except
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "129932291"))
except:
    ADMIN_ID = 129932291

WEBAPP_URL = "https://test-fzug.onrender.com/static/index.html"

# ✅ TO'G'RI HAVOLA (Port 6543 - IPv4)
# Bu havola Renderda muammosiz va tez ishlaydi
DATABASE_URL = "postgresql://postgres.zvtrujwsydewfcaotwvx:rkbfVJlp96S85bnu@aws-1-ap-south-1.pooler.supabase.com:6543/postgres"

app = FastAPI()
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- YORDAMCHI FUNKSIYALAR ---
def clean(text):
    """HTML belgilarni tozalash"""
    if not text: return ""
    text = str(text)
    return re.sub(r'<.*?>', '', text).replace('<', '&lt;').replace('>', '&gt;')

def get_db():
    """Bazaga ulanish"""
    return psycopg2.connect(DATABASE_URL)

def init_db():
    """Jadvallarni yaratish"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS tests (code TEXT PRIMARY KEY, title TEXT, duration INTEGER)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS questions (id SERIAL PRIMARY KEY, test_code TEXT, question TEXT, options TEXT, correct_answer TEXT)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS results (id SERIAL PRIMARY KEY, user_id BIGINT, user_name TEXT, nickname TEXT, test_code TEXT, test_title TEXT, score INTEGER, total INTEGER, date TEXT)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, invited_by BIGINT, invite_count INTEGER DEFAULT 0, joined_at TEXT)''')
        conn.commit()
        conn.close()
        logging.info("✅ Baza ulandi!")
    except Exception as e:
        logging.error(f"❌ Baza xatosi: {e}")

init_db()

# --- SERVER (WEBAPP) ---
if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root(): return {"status": "🚀 Bot ishlayapti!"}

@app.get("/get_test/{code}")
async def get_test(code: str):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT title, duration FROM tests WHERE code=%s", (code.strip(),))
        test = cur.fetchone()
        if not test: return {"error": "Test topilmadi"}
        
        cur.execute("SELECT question, options, correct_answer FROM questions WHERE test_code=%s", (code.strip(),))
        questions = [{"q": r[0], "o": json.loads(r[1]), "a": r[2]} for r in cur.fetchall()]
        conn.close()
        return {"title": test[0], "time": test[1], "questions": questions}
    except Exception as e:
        return {"error": f"Xato: {e}"}

@app.post("/submit_result")
async def submit(request: Request):
    try:
        d = await request.json()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO results (user_id, user_name, nickname, test_code, test_title, score, total, date) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (d.get('user_id'), clean(d.get('user_name')), d.get('nickname'), d.get('code'), d.get('title'), d.get('score'), d.get('total'), now))
        conn.commit()
        conn.close()
        
        # Admin xabari
        await bot.send_message(ADMIN_ID, f"🏆 <b>YANGI NATIJA</b>\n\n👤 {clean(d.get('user_name'))}\n📚 {clean(d.get('title'))}\n🎯 {d.get('score')} / {d.get('total')}", parse_mode="HTML")
        return {"status": "success"}
    except: return {"status": "error"}

# --- BOT KOMANDALARI ---
@dp.message(Command("start"))
async def start(msg: types.Message):
    uid, name = msg.from_user.id, clean(msg.from_user.full_name)
    args = msg.text.split()
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT invite_count FROM users WHERE user_id=%s", (uid,))
    user = cur.fetchone()
    
    if not user:
        # Yangi foydalanuvchi
        inviter = int(args[1]) if len(args) > 1 and args[1].isdigit() and int(args[1]) != uid else None
        cur.execute("INSERT INTO users (user_id, invited_by, invite_count, joined_at) VALUES (%s, %s, 0, %s)", 
                    (uid, inviter, datetime.now().strftime("%Y-%m-%d %H:%M")))
        
        if inviter:
            cur.execute("UPDATE users SET invite_count = invite_count + 1 WHERE user_id=%s", (inviter,))
            try: await bot.send_message(inviter, "🎉 <b>Do'stingiz qo'shildi!</b>", parse_mode="HTML")
            except: pass
        
        conn.commit()
        count = 0
        try: await bot.send_message(ADMIN_ID, f"👤 <b>Yangi a'zo:</b> {name} (`{uid}`)", parse_mode="HTML")
        except: pass
    else:
        count = user[0]
    conn.close()

    if uid == ADMIN_ID or count >= 3:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Testni Boshlash 📝", web_app=WebAppInfo(url=WEBAPP_URL))]])
        await msg.answer("✅ <b>Xush kelibsiz!</b> Testga kirishingiz mumkin.", reply_markup=kb, parse_mode="HTML")
    else:
        link = f"https://t.me/{(await bot.get_me()).username}?start={uid}"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Ulashish", switch_inline_query=f"\nTest yechamiz! {link}")]])
        await msg.answer(f"👋 <b>Salom {name}!</b>\n\nTest yechish uchun <b>3 ta</b> do'stingizni chaqiring.\n📊 Sizda: <b>{count} / 3</b>\n🔗 Link: <code>{link}</code>", reply_markup=kb, parse_mode="HTML")

@dp.message(Command("tests"))
async def tests(msg: types.Message):
    if msg.from_user.id != ADMIN_ID: return
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT code, title FROM tests")
    rows = cur.fetchall()
    conn.close()
    text = "📋 <b>Mavjud Testlar:</b>\n\n" + "\n".join([f"🔹 `{r[0]}` - {clean(r[1])}" for r in rows]) if rows else "📭 Testlar yo'q."
    await msg.answer(text, parse_mode="HTML")

@dp.message(Command("rating"))
async def rating(msg: types.Message):
    try: code = msg.text.split()[1]
    except: return await msg.answer("⚠️ Kodni yozing: `/rating 001`", parse_mode="Markdown")
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_name, score, total FROM results WHERE test_code=%s ORDER BY score DESC, date ASC LIMIT 10", (code,))
    rows = cur.fetchall()
    conn.close()
    
    res = f"🏆 <b>Reyting {code}:</b>\n\n" + "\n".join([f"{i+1}. {clean(r[0])} — {r[1]}/{r[2]}" for i, r in enumerate(rows)]) if rows else "❌ Natijalar yo'q."
    await msg.answer(res, parse_mode="HTML")

@dp.message(Command("users_count"))
async def stats(msg: types.Message):
    if msg.from_user.id != ADMIN_ID: return
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    cnt = cur.fetchone()[0]
    conn.close()
    await msg.answer(f"📊 <b>Jami a'zolar:</b> {cnt}", parse_mode="HTML")

@dp.message(Command("tanishbilish"))
async def vip(msg: types.Message):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, invite_count) VALUES (%s, 3) ON CONFLICT (user_id) DO UPDATE SET invite_count=3", (msg.from_user.id,))
    conn.commit()
    conn.close()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Testni Boshlash 📝", web_app=WebAppInfo(url=WEBAPP_URL))]])
    await msg.answer("🤫 <b>VIP ruxsat berildi!</b>", reply_markup=kb, parse_mode="HTML")

@dp.message(Command("admin"))
async def admin(msg: types.Message):
    if msg.from_user.id != ADMIN_ID: return
    await msg.answer("🛠 <b>Admin Panel:</b>\n/tests - Testlar\n/users_count - Statistika\n/rating [kod] - Reyting\n\n📥 <b>Yuklash:</b> `Kod | Mavzu | Vaqt`", parse_mode="HTML")

@dp.message(F.text.contains("|"))
async def upload(msg: types.Message):
    if msg.from_user.id != ADMIN_ID: return
    lines = msg.text.split('\n')
    try:
        code, title, time = map(str.strip, lines[0].split('|'))
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO tests (code, title, duration) VALUES (%s, %s, %s) ON CONFLICT (code) DO UPDATE SET title=%s, duration=%s", (code, title, int(time), title, int(time)))
        cur.execute("DELETE FROM questions WHERE test_code=%s", (code,))
        for l in lines[1:]:
            if '|' in l:
                q, o, a = map(str.strip, l.split('|'))
                cur.execute("INSERT INTO questions (test_code, question, options, correct_answer) VALUES (%s, %s, %s, %s)", (code, q.split('.', 1)[-1].strip(), json.dumps([x.strip() for x in o.split(',')]), a))
        conn.commit()
        conn.close()
        await msg.answer(f"✅ <b>{title}</b> yuklandi!", parse_mode="HTML")
    except Exception as e: await msg.answer(f"❌ Xato: {e}")

# --- ISHGA TUSHIRISH ---
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
    server = uvicorn.Server(config)
    await asyncio.gather(dp.start_polling(bot), server.serve())

if __name__ == "__main__":
    asyncio.run(main())
