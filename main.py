import os
import json
import re
import asyncio
import logging
import asyncpg
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
import uvicorn

# --- SOZLAMALAR ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "129932291"))
DATABASE_URL = os.getenv("DATABASE_URL") # Renderda Environment Variablega qo'shing!
WEBAPP_URL = "https://test-fzug.onrender.com/static/index.html"

# --- OBYEKTLAR ---
app = FastAPI()
bot = Bot(token=TOKEN)
dp = Dispatcher()
db_pool = None # Baza hovuzi

# --- YORDAMCHI FUNKSIYALAR ---
def clean(text):
    return re.sub(r'<.*?>', '', str(text)).replace('<', '&lt;').replace('>', '&gt;') if text else ""

@app.on_event("startup")
async def startup():
    global db_pool
    # Bazaga ulanish va jadvallarni yaratish
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute('''CREATE TABLE IF NOT EXISTS tests (code TEXT PRIMARY KEY, title TEXT, duration INTEGER)''')
        await conn.execute('''CREATE TABLE IF NOT EXISTS questions (id SERIAL PRIMARY KEY, test_code TEXT, question TEXT, options TEXT, correct_answer TEXT)''')
        await conn.execute('''CREATE TABLE IF NOT EXISTS results (id SERIAL PRIMARY KEY, user_id BIGINT, user_name TEXT, nickname TEXT, test_code TEXT, test_title TEXT, score INTEGER, total INTEGER, date TEXT)''')
        await conn.execute('''CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, invited_by BIGINT, invite_count INTEGER DEFAULT 0, joined_at TEXT)''')

@app.on_event("shutdown")
async def shutdown():
    if db_pool: await db_pool.close()

# --- API (WEBAPP UCHUN) ---
if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root(): return {"status": "🚀 Bot is working!"}

@app.get("/get_test/{code}")
async def get_test(code: str):
    async with db_pool.acquire() as conn:
        test = await conn.fetchrow("SELECT title, duration FROM tests WHERE code=$1", code)
        if not test: return {"error": "Test topilmadi"}
        rows = await conn.fetch("SELECT question, options, correct_answer FROM questions WHERE test_code=$1", code)
        questions = [{"q": r['question'], "o": json.loads(r['options']), "a": r['correct_answer']} for r in rows]
        return {"title": test['title'], "time": test['duration'], "questions": questions}

@app.post("/submit_result")
async def submit(request: Request):
    d = await request.json()
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO results (user_id, user_name, nickname, test_code, test_title, score, total, date) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                           d.get('user_id'), clean(d.get('user_name')), d.get('nickname'), d.get('code'), d.get('title'), d.get('score'), d.get('total'), datetime.now().strftime("%Y-%m-%d %H:%M"))
    
    await bot.send_message(ADMIN_ID, f"🏆 <b>YANGI NATIJA</b>\n\n👤 {clean(d.get('user_name'))}\n📚 {clean(d.get('title'))}\n🎯 {d.get('score')} / {d.get('total')}", parse_mode="HTML")
    return {"status": "success"}

# --- BOT KOMANDALARI ---
@dp.message(Command("start"))
async def cmd_start(msg: types.Message):
    uid, name = msg.from_user.id, clean(msg.from_user.full_name)
    args = msg.text.split()
    
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT invite_count FROM users WHERE user_id=$1", uid)
        if not user:
            inviter = int(args[1]) if len(args) > 1 and args[1].isdigit() and int(args[1]) != uid else None
            await conn.execute("INSERT INTO users (user_id, invited_by, invite_count, joined_at) VALUES ($1, $2, 0, $3)", uid, inviter, datetime.now().strftime("%Y-%m-%d %H:%M"))
            if inviter: 
                await conn.execute("UPDATE users SET invite_count = invite_count + 1 WHERE user_id=$1", inviter)
                try: await bot.send_message(inviter, "🎉 <b>Do'stingiz qo'shildi!</b>", parse_mode="HTML")
                except: pass
            try: await bot.send_message(ADMIN_ID, f"👤 <b>Yangi a'zo:</b> {name} (`{uid}`)", parse_mode="HTML")
            except: pass
            count = 0
        else: count = user['invite_count']

    if uid == ADMIN_ID or count >= 3:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Testni Boshlash 📝", web_app=WebAppInfo(url=WEBAPP_URL))]])
        await msg.answer("✅ <b>Xush kelibsiz!</b> Testga kirishingiz mumkin.", reply_markup=kb, parse_mode="HTML")
    else:
        link = f"https://t.me/{(await bot.get_me()).username}?start={uid}"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Ulashish", switch_inline_query=f"\nTest yechamiz! {link}")]])
        await msg.answer(f"👋 <b>Salom {name}!</b>\n\nTest yechish uchun <b>3 ta</b> do'stingizni chaqiring.\n📊 Sizda: <b>{count} / 3</b>\n🔗 Link: <code>{link}</code>", reply_markup=kb, parse_mode="HTML")

@dp.message(Command("tests"))
async def cmd_tests(msg: types.Message):
    if msg.from_user.id != ADMIN_ID: return
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT code, title FROM tests")
    text = "📋 <b>Mavjud Testlar:</b>\n\n" + "\n".join([f"🔹 `{r['code']}` - {clean(r['title'])}" for r in rows]) if rows else "📭 Testlar yo'q."
    await msg.answer(text, parse_mode="HTML")

@dp.message(Command("rating"))
async def cmd_rating(msg: types.Message):
    try: code = msg.text.split()[1]
    except: return await msg.answer("⚠️ Kodni yozing: `/rating 001`", parse_mode="Markdown")
    
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_name, score, total FROM results WHERE test_code=$1 ORDER BY score DESC, date ASC LIMIT 10", code)
    
    res = f"🏆 <b>Reyting {code}:</b>\n\n" + "\n".join([f"{i+1}. {clean(r['user_name'])} — {r['score']}/{r['total']}" for i, r in enumerate(rows)]) if rows else "❌ Natijalar yo'q."
    await msg.answer(res, parse_mode="HTML")

@dp.message(Command("users_count"))
async def cmd_stats(msg: types.Message):
    if msg.from_user.id != ADMIN_ID: return
    async with db_pool.acquire() as conn:
        cnt = await conn.fetchval("SELECT COUNT(*) FROM users")
    await msg.answer(f"📊 <b>Jami a'zolar:</b> {cnt}", parse_mode="HTML")

@dp.message(Command("tanishbilish"))
async def cmd_vip(msg: types.Message):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO users (user_id, invite_count) VALUES ($1, 3) ON CONFLICT (user_id) DO UPDATE SET invite_count=3", msg.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Testni Boshlash 📝", web_app=WebAppInfo(url=WEBAPP_URL))]])
    await msg.answer("🤫 <b>VIP ruxsat berildi!</b>", reply_markup=kb, parse_mode="HTML")

@dp.message(Command("admin"))
async def cmd_admin(msg: types.Message):
    if msg.from_user.id != ADMIN_ID: return
    await msg.answer("🛠 <b>Admin Panel:</b>\n/tests - Testlar\n/users_count - Statistika\n/rating [kod] - Reyting\n\n📥 <b>Yuklash:</b> `Kod | Mavzu | Vaqt`", parse_mode="HTML")

@dp.message(F.text.contains("|"))
async def upload_test(msg: types.Message):
    if msg.from_user.id != ADMIN_ID: return
    lines = msg.text.split('\n')
    try:
        code, title, time = map(str.strip, lines[0].split('|'))
        async with db_pool.acquire() as conn:
            await conn.execute("INSERT INTO tests (code, title, duration) VALUES ($1, $2, $3) ON CONFLICT (code) DO UPDATE SET title=$2, duration=$3", code, title, int(time))
            await conn.execute("DELETE FROM questions WHERE test_code=$1", code)
            for l in lines[1:]:
                if '|' in l:
                    q, o, a = map(str.strip, l.split('|'))
                    await conn.execute("INSERT INTO questions (test_code, question, options, correct_answer) VALUES ($1, $2, $3, $4)", code, q.split('.', 1)[-1].strip(), json.dumps([x.strip() for x in o.split(',')]), a)
        await msg.answer(f"✅ <b>{title}</b> yuklandi!", parse_mode="HTML")
    except Exception as e: await msg.answer(f"❌ Xato: {e}")

# --- START ---
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
    await asyncio.gather(dp.start_polling(bot), uvicorn.Server(config).serve())

if __name__ == "__main__":
    asyncio.run(main())
