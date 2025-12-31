import sqlite3
import json

def init_db():
    conn = sqlite3.connect('quiz.db')
    cursor = conn.cursor()
    # Testlar: kodi, nomi, vaqti
    cursor.execute('''CREATE TABLE IF NOT EXISTS tests 
        (code TEXT PRIMARY KEY, title TEXT, duration INTEGER)''')
    # Savollar: qaysi testga tegishli, savol, variantlar (JSON), javob
    cursor.execute('''CREATE TABLE IF NOT EXISTS questions 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, test_code TEXT, 
         question TEXT, options TEXT, correct_answer TEXT)''')
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Baza tayyor!")
  
