from flask import Flask, render_template, request, session, jsonify
import random
import requests
import sqlite3
from dotenv import load_dotenv
from cryptography.fernet import Fernet
import os

app = Flask(__name__)
app.secret_key = "supersecretkey"

load_dotenv()
encryption_key = os.getenv("ENCRYPTION_KEY")

if not encryption_key:
    encryption_key = Fernet.generate_key().decode()
    with open(".env", "w") as f:
        f.write(f"ENCRYPTION_KEY={encryption_key}")

fernet = Fernet(encryption_key.encode())

# Database setup
conn = sqlite3.connect("game_data.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT NOT NULL UNIQUE
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS games (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL,
        target_word TEXT NOT NULL,
        mode TEXT NOT NULL,
        success INTEGER NOT NULL,
        attempts_used INTEGER NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
""")
conn.commit()

# APIs and Hardcoded Word List
EASY_WORDS_API = "https://api.datamuse.com/words?sp=?????&max=1000"
HARD_WORDS = [
    "CRYPT", "JAZZY", "SPHYN", "NYMPH", "WHISK", "ZEBRA", "FLUX", "VEXED", "PIXEL", "EXULT"
]

# Fetch words from API
def fetch_words(api_url):
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        words = response.json()
        return [word['word'].upper() for word in words if len(word['word']) == 5 and word['word'].isalpha()]
    except requests.RequestException as e:
        print(f"Error fetching words: {e}")
        return []

# Choose word based on mode
def choose_word():
    mode = session.get("mode", "easy")
    if mode == "easy":
        words = fetch_words(EASY_WORDS_API)
    else:
        words = HARD_WORDS
    return random.choice(words) if words else "ERROR"

# Encrypt data
def encrypt_data(data: str) -> str:
    return fernet.encrypt(data.encode()).decode()

# Decrypt data
def decrypt_data(encrypted_data: str) -> str:
    return fernet.decrypt(encrypted_data.encode()).decode()

@app.route("/")
def index():
    if "mode" not in session:
        session["mode"] = "easy"
    if "target" not in session or session["target"] == "ERROR":
        session["target"] = choose_word()
    if "attempts" not in session:
        session["attempts"] = 6
    if "used_letters" not in session:
        session["used_letters"] = []
    return render_template("index.html", mode=session["mode"])

@app.route("/game", methods=["POST"])
def game():
    data = request.get_json()
    if not data or "guess" not in data:
        return jsonify({"error": "Missing 'guess' in request data"}), 400

    guess = data["guess"].strip().upper()
    target = session.get("target", "")
    result = []

    if len(guess) == len(target):
        for i, letter in enumerate(guess):
            if letter == target[i]:
                result.append("green")
            elif letter in target:
                result.append("orange")
            else:
                result.append("red")

    session["used_letters"] = session.get("used_letters", []) + [l for l in guess if l not in session.get("used_letters", [])]
    session["attempts"] -= 1
    game_over = session["attempts"] == 0 or guess == target

    return jsonify({
        "result": result,
        "game_over": game_over,
        "target": target if game_over else None,
        "attempts_left": session["attempts"],
        "used_letters": session["used_letters"]
    })

@app.route("/set_mode")
def set_mode():
    mode = request.args.get("mode", "easy")
    session["mode"] = mode
    session["target"] = choose_word()
    session["attempts"] = 6
    session["used_letters"] = []
    return "", 200

@app.route("/stats")
def stats():
    attempts_left = session.get("attempts", 6)
    used_letters = session.get("used_letters", [])
    return jsonify({
        "attempts_left": attempts_left,
        "used_letters": used_letters
    })

@app.route("/reset")
def reset():
    session.clear()
    return jsonify({"message": "Game reset successfully. Start a new game!"})

@app.route("/add_user", methods=["POST"])
def add_user():
    username = request.form.get("username")
    word = session.get("target")
    mode = session.get("mode", "easy")
    success = int(request.form.get("success", 0))  # 1 for success, 0 for failure
    attempts_used = 6 - session.get("attempts", 6)

    if not username or not word:
        return jsonify({"error": "Username or target word missing"}), 400

    # Encrypt the word
    encrypted_word = encrypt_data(word)

    # Add user if not already present
    cursor.execute("INSERT OR IGNORE INTO users (username) VALUES (?)", (username,))
    conn.commit()

    # Get user ID
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    user_id = cursor.fetchone()[0]

    # Add game details with the encrypted word
    cursor.execute(
        "INSERT INTO games (user_id, target_word, mode, success, attempts_used) VALUES (?, ?, ?, ?, ?)",
        (user_id, encrypted_word, mode, success, attempts_used)
    )
    conn.commit()
    return jsonify({"message": "Game details saved successfully!"})

@app.route("/get_user/<username>")
def get_user(username):
    try:
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({"error": "User not found"}), 404

        user_id = user[0]
        cursor.execute(
            "SELECT target_word, mode, success, attempts_used FROM games WHERE user_id = ?", (user_id,)
        )
        games = cursor.fetchall()
        if games:
            game_data = []
            for game in games:
                try:
                    decrypted_word = decrypt_data(game[0])  # Decrypt the word
                except Exception as e:
                    decrypted_word = f"Error decrypting word: {e}"
                game_data.append({
                    "word": decrypted_word,
                    "mode": game[1],
                    "success": bool(game[2]),
                    "attempts_used": game[3]
                })
            return jsonify({"username": username, "games": game_data})
        return jsonify({"username": username, "games": []})
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {e}"}), 500

if __name__ == "__main__":
    app.run(debug=True)
