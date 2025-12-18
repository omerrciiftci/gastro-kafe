from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timedelta
from typing import List, Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import random
import os
from dotenv import load_dotenv

load_dotenv()

# --- GÜVENLİK ---
SECRET_KEY = os.getenv("SECRET_KEY", "7d8f9g0h1j2k3l4m5n6o7p8q9r0s1t2u")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 720 # 12 Saat

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Gastro İnegöl Pro")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Bcrypt 72 bayt hatasını önlemek için sadeleştirilmiş tanım
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- VERİTABANI (Yeni Dosya: gastro_final.db) ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./gastro_final.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class OrderDB(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String)
    table_number = Column(String)
    items = Column(String)
    total_price = Column(Float)
    status = Column(String, default="preparing")
    waiter_ok = Column(Boolean, default=False)
    customer_ok = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)

class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String)

Base.metadata.create_all(bind=engine)

# --- ŞİFRELEME YARDIMCILARI (72 Bayt Sınırı Çözümü) ---
def verify_password(plain_password, hashed_password):
    # Şifreyi 72 karakterle sınırlayarak Bcrypt hatasını kökten çözer
    return pwd_context.verify(plain_password[:72], hashed_password)

def get_password_hash(password):
    # Şifreyi 72 karakterle sınırlayarak Bcrypt hatasını kökten çözer
    return pwd_context.hash(password[:72])

# --- DİĞER FONKSİYONLAR ---
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None: raise HTTPException(401)
        user = db.query(UserDB).filter(UserDB.username == username).first()
        if user is None: raise HTTPException(401)
        return user
    except JWTError: raise HTTPException(401)

class ConnectionManager:
    def __init__(self): self.active_connections = {"orders": [], "music": []}
    async def connect(self, ws: WebSocket, channel: str):
        await ws.accept()
        self.active_connections[channel].append(ws)
    def disconnect(self, ws: WebSocket, channel: str):
        if ws in self.active_connections[channel]: self.active_connections[channel].remove(ws)
    async def broadcast(self, message: dict, channel: str):
        for connection in self.active_connections[channel]:
            try: await connection.send_json(message)
            except: pass

manager = ConnectionManager()

# --- MÜZİK SİSTEMİ (RAM) ---
music_library = [
    {"id": 1, "title": "Ateşe Düştüm", "artist": "Mert Demir"},
    {"id": 2, "title": "Antidepresan", "artist": "Mabel Matiz"},
    {"id": 3, "title": "Gülpembe", "artist": "Barış Manço"}
]
current_playing = {"title": "Gastro Radyo", "artist": "Hoş Geldiniz"}
candidates = random.sample(music_library, 3)
votes = {s['id']: 0 for s in candidates}
total_votes = 0

# --- API ENDPOINTLERİ ---

@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(401, "Hatalı kullanıcı adı veya şifre")
    token = create_access_token({"sub": user.username, "role": user.role})
    return {"access_token": token, "token_type": "bearer"}

@app.get("/api/music")
def get_music():
    return {"now_playing": current_playing, "candidates": candidates, "total_votes": total_votes}

@app.post("/api/music/vote/{song_id}")
@limiter.limit("5/minute")
async def vote(song_id: int, request: Request):
    global total_votes
    if song_id in votes:
        votes[song_id] += 1
        total_votes += 1
        await manager.broadcast({"type": "update"}, "music")
        return {"status": "ok"}
    return {"status": "error"}

@app.post("/api/orders")
async def create_order(order: dict, db: Session = Depends(get_db)):
    new_order = OrderDB(**order)
    db.add(new_order)
    db.commit()
    db.refresh(new_order)
    await manager.broadcast({"type": "new_order", "id": new_order.id}, "orders")
    return {"status": "success", "order_id": new_order.id}

@app.get("/api/orders")
def get_orders(db: Session = Depends(get_db), user: UserDB = Depends(get_current_user)):
    return db.query(OrderDB).order_by(OrderDB.created_at.desc()).limit(50).all()

@app.put("/api/orders/{order_id}/status")
async def update_status(order_id: int, data: dict, db: Session = Depends(get_db), user: UserDB = Depends(get_current_user)):
    order = db.query(OrderDB).filter(OrderDB.id == order_id).first()
    order.status = data['status']
    db.commit()
    await manager.broadcast({"type": "update", "id": order.id, "status": order.status}, "orders")
    return {"status": "ok"}

@app.put("/api/orders/{order_id}/confirm")
async def confirm(order_id: int, data: dict, db: Session = Depends(get_db)):
    order = db.query(OrderDB).filter(OrderDB.id == order_id).first()
    if data['role'] == 'waiter': order.waiter_ok = True
    else: order.customer_ok = True
    if order.waiter_ok and order.customer_ok: order.status = 'completed'
    db.commit()
    await manager.broadcast({"type": "update", "id": order.id, "status": order.status}, "orders")
    return {"status": "ok"}

@app.websocket("/ws/orders")
async def ws_orders(ws: WebSocket):
    await manager.connect(ws, "orders")
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect: manager.disconnect(ws, "orders")

@app.websocket("/ws/music")
async def ws_music(ws: WebSocket):
    await manager.connect(ws, "music")
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect: manager.disconnect(ws, "music")

@app.get("/")
async def index(): return FileResponse('index.html')

@app.get("/panel")
async def panel(): return FileResponse('panel.html')

# Başlangıçta kullanıcıları oluştur
@app.on_event("startup")
def startup():
    db = SessionLocal()
    if not db.query(UserDB).first():
        db.add(UserDB(username="admin", hashed_password=get_password_hash("admin123"), role="admin"))
        db.add(UserDB(username="mutfak", hashed_password=get_password_hash("mutfak123"), role="kitchen"))
        db.add(UserDB(username="garson", hashed_password=get_password_hash("garson123"), role="waiter"))
        db.commit()
    db.close()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
