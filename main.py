from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import FileResponse
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.hash import sha256_crypt
import os

# --- AYARLAR ---
SECRET_KEY = "gastro_inegol_2026_security_key"
ALGORITHM = "HS256"
app = FastAPI()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- VERİTABANI ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./gastro_v5.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class OrderDB(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String); table_number = Column(String)
    items = Column(String); total_price = Column(Float)
    status = Column(String, default="preparing")
    waiter_ok = Column(Boolean, default=False); customer_ok = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)

class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True); hashed_password = Column(String)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# --- MÜZİK VERİSİ ---
music_data = {
    "now_playing": {"title": "İnegöl Marşı", "artist": "Belediye Bandosu"},
    "candidates": [
        {"id": 1, "title": "Mihriban", "artist": "Musa Eroğlu", "votes": 0},
        {"id": 2, "title": "Erik Dalı", "artist": "Ömer Faruk Bostan", "votes": 0},
        {"id": 3, "title": "Beyaz ve Sen", "artist": "Bülent Ortaçgil", "votes": 0}
    ]
}

# --- WEBSOCKET YÖNETİCİSİ ---
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

# --- AUTH ---
@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.username == form_data.username).first()
    if not user or not sha256_crypt.verify(form_data.password, user.hashed_password):
        raise HTTPException(401, "Hatalı giriş")
    token = jwt.encode({"sub": user.username, "exp": datetime.utcnow() + timedelta(days=1)}, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user = db.query(UserDB).filter(UserDB.username == payload.get("sub")).first()
        return user
    except: raise HTTPException(401)

# --- SİPARİŞ API ---
@app.post("/api/orders")
async def create_order(order: dict, db: Session = Depends(get_db)):
    new_order = OrderDB(**order)
    db.add(new_order); db.commit(); db.refresh(new_order)
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
    if data.get('role') == 'waiter': order.waiter_ok = True
    else: order.customer_ok = True
    if order.waiter_ok and order.customer_ok: order.status = 'completed'
    db.commit()
    await manager.broadcast({"type": "update", "id": order.id, "status": order.status}, "orders")
    return {"status": "ok"}

# --- MÜZİK API ---
@app.get("/api/music")
async def get_music():
    total_votes = sum(s['votes'] for s in music_data['candidates']) or 1
    for s in music_data['candidates']:
        s['percent'] = int((s['votes'] / total_votes) * 100)
    return music_data

@app.post("/api/music/vote/{song_id}")
async def vote_song(song_id: int):
    for s in music_data['candidates']:
        if s['id'] == song_id:
            s['votes'] += 1
            await manager.broadcast({"type": "update"}, "music")
            return {"status": "ok"}
    raise HTTPException(404)

# --- WEBSOCKET ---
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

# --- STATİK VE STARTUP ---
@app.get("/")
async def index(): return FileResponse('index.html')
@app.get("/panel")
async def panel(): return FileResponse('panel.html')

@app.on_event("startup")
def startup():
    db = SessionLocal()
    if not db.query(UserDB).first():
        db.add(UserDB(username="admin", hashed_password=sha256_crypt.hash("admin123")))
        db.commit()
    db.close()
