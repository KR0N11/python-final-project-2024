import sqlite3

def init_db():
    conn = sqlite3.connect("wordle_game.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS games (id INTEGER PRIMARY KEY, word TEXT, attempts INTEGER)''')
    conn.commit()
    conn.close()

def save_game(word, attempts):
    conn = sqlite3.connect("wordle_game.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO games (word, attempts) VALUES (?, ?)", (word, attempts))
    conn.commit()
    conn.close()
