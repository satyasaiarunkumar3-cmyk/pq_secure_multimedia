from flask import Flask, render_template, request, redirect, session, send_file
import sqlite3, os, hashlib, time

from kyber_kem import kyber_keygen
from crypto_utils import encrypt_data, decrypt_data

app = Flask(__name__)
app.secret_key = "secure_chat_key"

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "chat.db")
MSG_DIR = os.path.join(BASE, "messages")
UPLOAD_DIR = os.path.join(BASE, "uploads")

os.makedirs(MSG_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------- DATABASE ----------
def check_user(u, p):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT * FROM users WHERE username=? AND password=?", (u, p))
    r = cur.fetchone()
    con.close()
    return r

def add_user(u, p):
    try:
        con = sqlite3.connect(DB)
        cur = con.cursor()
        cur.execute("INSERT INTO users(username,password) VALUES(?,?)", (u, p))
        con.commit()
        con.close()
        return True
    except:
        return False

def all_users():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT username FROM users")
    users = [u[0] for u in cur.fetchall()]
    con.close()
    return users

# ---------- POST-QUANTUM KEY ----------
pub, priv = kyber_keygen()
shared_key = hashlib.sha256(pub).digest()

# ---------- LOGIN ----------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if check_user(request.form["username"], request.form["password"]):
            session["user"] = request.form["username"]
            return redirect("/users")
        return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")

# ---------- REGISTER ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        if add_user(request.form["username"], request.form["password"]):
            return redirect("/")
        return render_template("register.html", error="User already exists")
    return render_template("register.html")

# ---------- USERS ----------
@app.route("/users")
def users():
    if "user" not in session:
        return redirect("/")
    me = session["user"]
    contacts = [u for u in all_users() if u != me]
    return render_template("users.html", users=contacts, me=me)

# ---------- CHAT ----------
@app.route("/chat/<peer>", methods=["GET", "POST"])
def chat(peer):
    if "user" not in session:
        return redirect("/")

    me = session["user"]
    chat_id = "__".join(sorted([me, peer]))
    chat_dir = os.path.join(MSG_DIR, chat_id)
    os.makedirs(chat_dir, exist_ok=True)

    # SEND MESSAGE
    if request.method == "POST":
        msg = request.form.get("message", "")
        file = request.files.get("file")

        payload = msg.encode()
        filename = ""

        if file and file.filename:
            filename = file.filename
            payload += b"\n---FILE---\n" + file.read()

        nonce, cipher, tag = encrypt_data(payload, shared_key)
        ts = str(int(time.time() * 1000))  # ✅ FIXED HERE

        with open(os.path.join(chat_dir, f"{ts}.bin"), "wb") as f:
            f.write(nonce + tag + cipher)

        with open(os.path.join(chat_dir, f"{ts}.meta"), "w") as f:
            f.write(f"{me}|{filename}")

        return redirect(f"/chat/{peer}")

    # LOAD HISTORY
    messages = []
    for f in sorted(os.listdir(chat_dir)):
        if f.endswith(".bin"):
            ts = f.split(".")[0]
            blob = open(os.path.join(chat_dir, f), "rb").read()
            plain = decrypt_data(blob[:16], blob[32:], blob[16:32], shared_key)

            meta = os.path.join(chat_dir, f"{ts}.meta")
            sender, filename = open(meta).read().split("|")

            text = plain
            filelink = None

            if b"\n---FILE---\n" in plain:
                text, filedata = plain.split(b"\n---FILE---\n")
                path = os.path.join(UPLOAD_DIR, filename)
                open(path, "wb").write(filedata)
                filelink = filename

            messages.append({
                "sender": sender,
                "text": text.decode(),
                "file": filelink
            })

    return render_template("chat.html", peer=peer, messages=messages, me=me)

# ---------- DOWNLOAD ----------
@app.route("/uploads/<filename>")
def download(filename):
    return send_file(os.path.join(UPLOAD_DIR, filename), as_attachment=True)

# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    print("🚀 Secure WhatsApp-like Chat running at http://127.0.0.1:5000")
    app.run(debug=True)
