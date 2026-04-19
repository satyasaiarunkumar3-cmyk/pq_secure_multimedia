from flask import Flask, render_template, request, redirect, session, send_from_directory
from flask_socketio import SocketIO, emit, join_room
import sqlite3, json, os, hashlib
from datetime import datetime
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "secret123"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

DB_NAME = "db.db"
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

online_users = set()

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    db.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)")
    db.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT,
        receiver TEXT,
        ciphertext TEXT,
        file TEXT,
        time TEXT,
        seen INTEGER DEFAULT 0,
        deleted_for_everyone INTEGER DEFAULT 0
    )""")
    db.commit()
    db.close()

init_db()

def shared_key(a,b):
    return hashlib.sha256("|".join(sorted([a,b])).encode()).digest()

def encrypt(msg,s,r):
    key=shared_key(s,r)
    aes=AESGCM(key)
    nonce=os.urandom(12)
    ct=aes.encrypt(nonce,msg.encode(),None)
    return {"ciphertext":ct.hex(),"nonce":nonce.hex()}

def decrypt(data,s,r):
    try:
        key=shared_key(s,r)
        aes=AESGCM(key)
        return aes.decrypt(bytes.fromhex(data["nonce"]),bytes.fromhex(data["ciphertext"]),None).decode()
    except:
        return "[error]"

@app.route('/')
def login_page():
    return render_template("login.html")

@app.route('/login',methods=['POST'])
def login():
    u=request.form['username']
    p=request.form['password']
    db=get_db()
    user=db.execute("SELECT * FROM users WHERE username=? AND password=?",(u,p)).fetchone()
    if user:
        session['user']=u
        return redirect('/chat')
    return render_template("login.html")

@app.route('/register',methods=['GET','POST'])
def register():
    if request.method=='POST':
        u=request.form['username']
        p=request.form['password']
        db=get_db()
        try:
            db.execute("INSERT INTO users VALUES (?,?)",(u,p))
            db.commit()
            session['user']=u
            return redirect('/chat')
        except:
            return render_template("register.html")
    return render_template("register.html")

@app.route('/logout')
def logout():
    user=session.get('user')
    if user:
        online_users.discard(user)
        socketio.emit("user_status",{"user":user,"status":"offline"})
    session.clear()
    return redirect('/')

@app.route('/chat')
def chat():
    if 'user' not in session:
        return redirect('/')
    return render_template("chat.html",user=session['user'])

@app.route('/users')
def users():
    db=get_db()
    me=session['user']
    users=db.execute("SELECT username FROM users").fetchall()
    return {"users":[u[0] for u in users if u[0]!=me]}

@app.route('/upload',methods=['POST'])
def upload():
    f=request.files['file']
    name=str(datetime.now().timestamp()).replace(".","")+"_"+secure_filename(f.filename)
    f.save(os.path.join(UPLOAD_FOLDER,name))
    return {"name":f.filename,"path":name,"type":f.content_type}

@app.route('/download/<path:filename>')
def download_file(filename):
    return send_from_directory(UPLOAD_FOLDER,filename,as_attachment=True)

@app.route('/clear_chat/<user>',methods=['POST'])
def clear_chat(user):
    me=session['user']
    db=get_db()
    db.execute("""DELETE FROM messages WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?)""",(me,user,user,me))
    db.commit()
    return {"status":"cleared"}

@app.route('/history/<r>')
def history(r):
    s=session['user']
    db=get_db()
    rows=db.execute("""SELECT * FROM messages WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?) ORDER BY id""",(s,r,r,s)).fetchall()
    out=[]
    for row in rows:
        msg="[deleted]" if row["deleted_for_everyone"] else decrypt(json.loads(row["ciphertext"]),row["sender"],row["receiver"])
        file=json.loads(row["file"]) if row["file"] else None
        out.append({"id":row["id"],"sender":row["sender"],"msg":msg,"file":file,"time":row["time"],"seen":row["seen"]})
    return {"messages":out}

@app.route('/delete_message/<int:id>',methods=['POST'])
def delete_msg(id):
    db=get_db()
    db.execute("DELETE FROM messages WHERE id=? AND sender=?",(id,session['user']))
    db.commit()
    return {"status":"deleted"}

@app.route('/delete_for_everyone/<int:id>',methods=['POST'])
def delete_all(id):
    db=get_db()
    db.execute("UPDATE messages SET deleted_for_everyone=1 WHERE id=? AND sender=?",(id,session['user']))
    db.commit()
    socketio.emit("message_deleted",{"id":id})
    return {"status":"deleted"}

@socketio.on('connect')
def connect(auth=None):
    user=session.get('user')
    if user:
        online_users.add(user)
        join_room(user)
        socketio.emit("user_status",{"user":user,"status":"online"})

@socketio.on('disconnect')
def disconnect():
    user=session.get('user')
    if user:
        online_users.discard(user)
        socketio.emit("user_status",{"user":user,"status":"offline"})

@socketio.on('typing')
def typing(d):
    emit("typing",d,room=d['to'])

@socketio.on('seen')
def seen(d):
    db=get_db()
    db.execute("UPDATE messages SET seen=1 WHERE id=?",(d['id'],))
    db.commit()
    emit("seen_update",d,room=d['sender'])

@socketio.on('send_message')
def send(d):
    s,r=d['sender'],d['receiver']
    enc=encrypt(d.get('message',"") , s,r)
    db=get_db()
    db.execute("INSERT INTO messages (sender,receiver,ciphertext,file,time,seen,deleted_for_everyone) VALUES (?,?,?,?,?,0,0)",
               (s,r,json.dumps(enc),json.dumps(d.get('file')),datetime.now().isoformat()))
    db.commit()
    id=db.execute("SELECT last_insert_rowid()").fetchone()[0]

    payload={"id":id,"sender":s,"receiver":r,"msg":d.get('message'),"file":d.get('file'),"time":datetime.now().isoformat(),"seen":0}

    emit("receive_message",payload,room=r)
    emit("receive_message",payload,room=s)
    emit("delivered",{"id":id},room=s)

if __name__=="__main__":
    socketio.run(app,debug=True)
