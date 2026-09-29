from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import init_db, get_db, User, Chat, Message
import rag_engine

app = FastAPI(title="FCCP Judgments RAG Chatbot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()


@app.get("/")
def read_root():
    import os
    index_path = os.path.join(os.path.dirname(__file__), "index.html")
    return FileResponse(index_path)


# ---------- Schemas ----------

class UserCreate(BaseModel):
    username: str


class AuthPayload(BaseModel):
    username: str


class ChatCreate(BaseModel):
    user_id: str
    title: str | None = "New Chat"


class MessageCreate(BaseModel):
    content: str


# ---------- Authentication & Users ----------

@app.post("/auth/signup")
def signup(payload: AuthPayload, db: Session = Depends(get_db)):
    username_clean = payload.username.strip()
    if not username_clean:
        raise HTTPException(400, "Username cannot be empty")
    
    user = db.query(User).filter(User.username == username_clean).first()
    if user:
        raise HTTPException(400, "Username already exists. Please login instead.")
    
    new_user = User(username=username_clean)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"id": new_user.id, "username": new_user.username}


@app.post("/auth/login")
def login(payload: AuthPayload, db: Session = Depends(get_db)):
    username_clean = payload.username.strip()
    if not username_clean:
        raise HTTPException(400, "Username cannot be empty")
    
    user = db.query(User).filter(User.username == username_clean).first()
    if not user:
        raise HTTPException(404, "Username not found. Please sign up first.")
    return {"id": user.id, "username": user.username}


@app.post("/users")
def create_or_get_user(payload: UserCreate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if user:
        return {"id": user.id, "username": user.username}
    user = User(username=payload.username)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username}


# ---------- Chats ----------

@app.get("/users/{user_id}/chats")
def list_chats(user_id: str, db: Session = Depends(get_db)):
    chats = db.query(Chat).filter(Chat.user_id == user_id).order_by(Chat.created_at.desc()).all()
    return [{"id": c.id, "title": c.title, "created_at": c.created_at} for c in chats]


@app.post("/chats")
def create_chat(payload: ChatCreate, db: Session = Depends(get_db)):
    chat = Chat(user_id=payload.user_id, title=payload.title or "New Chat")
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return {"id": chat.id, "title": chat.title}


@app.delete("/chats/{chat_id}")
def delete_chat(chat_id: str, db: Session = Depends(get_db)):
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(404, "Chat not found")
    db.delete(chat)
    db.commit()
    return {"deleted": True}


# ---------- Messages ----------

@app.get("/chats/{chat_id}/messages")
def get_messages(chat_id: str, db: Session = Depends(get_db)):
    msgs = db.query(Message).filter(Message.chat_id == chat_id).order_by(Message.created_at).all()
    return [{"role": m.role, "content": m.content, "created_at": m.created_at} for m in msgs]


@app.post("/chats/{chat_id}/messages")
def send_message(chat_id: str, payload: MessageCreate, db: Session = Depends(get_db)):
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(404, "Chat not found")

    user_msg = Message(chat_id=chat_id, role="user", content=payload.content)
    db.add(user_msg)
    db.commit()

    history_rows = db.query(Message).filter(Message.chat_id == chat_id).order_by(Message.created_at).all()
    history = [{"role": m.role, "content": m.content} for m in history_rows]

    # agar yeh chat ka pehla message hai, title auto-set karo
    if chat.title == "New Chat":
        chat.title = payload.content[:50]
        db.commit()

    answer = rag_engine.generate_answer(payload.content, history[:-1])

    assistant_msg = Message(chat_id=chat_id, role="assistant", content=answer)
    db.add(assistant_msg)
    db.commit()

    return {"role": "assistant", "content": answer}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)