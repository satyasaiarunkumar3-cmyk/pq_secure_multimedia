const socket = io();

const user = document.querySelector("h2").innerText;
let selected = null;

const chat = document.getElementById("chat");
const msgInput = document.getElementById("msg");
const receiverInput = document.getElementById("receiver");

// ---------- CONNECT ----------
socket.emit("connect_user", { username: user });

// ---------- SELECT USER ----------
function selectUser(u){
    selected = u;
    document.getElementById("header").innerText = u;
    chat.innerHTML = "";

    fetch(`/history/${u}`)
    .then(res => res.json())
    .then(data => {
        data.messages.forEach(renderMessage);
    });
}

// ---------- SEND ----------
async function send() {
    let receiver = receiverInput.value;
    let msg = msgInput.value;

    if(!receiver || !msg) return;

    socket.emit("send_message", {
        sender: user,
        receiver: receiver,
        message: msg
    });

    msgInput.value = "";
}

// ---------- RECEIVE ----------
socket.on("receive_message", data => {
    if(data.sender === selected || data.receiver === selected){
        renderMessage(data);

        // mark seen
        if(data.sender !== user){
            socket.emit("seen", {id: data.id, sender: data.sender});
        }
    }
});

// ---------- FORMAT TIME ----------
function formatTime(ts){
    let d = new Date(ts);
    return d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
}

// ---------- RENDER ----------
function renderMessage(d){
    let div = document.createElement("div");
    div.className = d.sender === user ? "msg right" : "msg left";
    div.id = "msg-" + d.id;

    let content = d.msg || "";

    // ---------- FILE PREVIEW ----------
    if(d.file && d.file.path){
        let url = "/" + d.file.path;

        if(d.file.type.startsWith("image")){
            content += `<br><img src="${url}" style="max-width:200px;border-radius:8px;">`;
        }
        else if(d.file.type.startsWith("video")){
            content += `<br><video src="${url}" width="200" controls></video>`;
        }
        else if(d.file.type.startsWith("audio")){
            content += `<br><audio src="${url}" controls></audio>`;
        }
        else{
            content += `<br><a href="${url}" download>⬇ ${d.file.name}</a>`;
        }
    }

    // ---------- TICKS ----------
    let ticks = "";
    if(d.sender === user){
        ticks = d.seen
            ? `<span style="color:#34b7f1">✔✔</span>`
            : `<span>✔</span>`;
    }

    // ---------- DELETE BUTTON ----------
    let del = "";
    if(d.sender === user){
        del = `<div onclick="deleteMsg(${d.id})" style="font-size:10px;color:red;cursor:pointer">Delete</div>`;
    }

    div.innerHTML = `
        ${content}
        ${del}
        <div class="time">${formatTime(d.time)} ${ticks}</div>
    `;

    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
}

// ---------- DELIVERED ----------
socket.on("delivered", data => {
    let el = document.querySelector(`#msg-${data.id}`);
    if(el){
        el.innerHTML = el.innerHTML.replace("✔","✔✔");
    }
});

// ---------- SEEN ----------
socket.on("seen_update", data => {
    let el = document.querySelector(`#msg-${data.id}`);
    if(el){
        el.innerHTML = el.innerHTML.replace("✔✔","<span style='color:#34b7f1'>✔✔</span>");
    }
});

// ---------- DELETE ----------
function deleteMsg(id){
    let choice = confirm("OK = Delete for everyone\nCancel = Delete for me");

    if(choice){
        fetch('/delete_for_everyone/' + id, {method:"POST"});
    } else {
        fetch('/delete_message/' + id, {method:"POST"});
        document.getElementById("msg-" + id)?.remove();
    }
}

// ---------- REAL-TIME DELETE ----------
socket.on("message_deleted", data => {
    let el = document.getElementById("msg-" + data.id);
    if(el){
        el.innerHTML = "<i>Message deleted</i>";
    }
});

// ---------- TYPING ----------
msgInput.addEventListener("input", ()=>{
    if(selected){
        socket.emit("typing", {to:selected, from:user});
    }
});

socket.on("typing", data => {
    if(data.from === selected){
        console.log(data.from + " typing...");
    }
});

// ---------- ONLINE ----------
socket.on("user_status", data => {
    let el = document.getElementById("status-" + data.user);
    if(el){
        el.innerText = data.status;
        el.style.color = data.status === "online" ? "green" : "gray";
    }
});
