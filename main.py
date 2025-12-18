"""
================================================================
 PROJE ADI: Gastro İnegöl - Dijital Menü ve Sipariş Sistemi (API)
================================================================
 GELİŞTİRİCİ: Ömer Faruk Çiftci
 TARİH: 2023-2025
 MÜŞTERİ: İnegöl Belediyesi Sosyal Tesisleri
 
 AÇIKLAMA:
 Bu yazılım, FastAPI ve SQLAlchemy kullanılarak geliştirilmiş
 gerçek zamanlı bir restoran sipariş yönetim backend servisidir.
 İçerisinde "Gastro Radyo" müzik oylama sistemi mevcuttur.
 
 Tüm hakları saklıdır.
================================================================
"""

from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, func, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
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

# .env yükle
load_dotenv()

# --- GÜVENLİK AYARLARI ---
SECRET_KEY = os.getenv("SECRET_KEY", "gizli_anahtar_degistir_bunu_cok_guvenli_yap_32_karakter")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12 # 12 Saat

# Rate Limiter
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Gastro İnegöl API", description="Pro Sürüm - Developed by Ömer Faruk Çiftci", version="4.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Şifreleme
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# CORS AYARLARI (Her yerden erişim için)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- VERİTABANI AYARLARI (SQLite) ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./kafe_sistemi.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Sipariş Tablosu
class OrderDB(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String)
    table_number = Column(String)
    items = Column(String)
    total_price = Column(Float)
    status = Column(String, default="preparing") # preparing, ready, completed
    waiter_ok = Column(Boolean, default=False)
    customer_ok = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)

# Kullanıcılar (Admin/Garson/Mutfak)
class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String) # admin, kitchen, waiter

Base.metadata.create_all(bind=engine)

# Pydantic Modelleri (Veri Doğrulama)
class OrderSchema(BaseModel):
    customer_name: str
    table_number: str
    items: str
    total_price: float

class StatusUpdate(BaseModel):
    status: str

class ConfirmSchema(BaseModel):
    role: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None

# --- DJ / MÜZİK SİSTEMİ (RAM Tabanlı Demo) ---
# Gerçek veritabanı yerine sunumda hızlı çalışsın diye RAM'de tutuyoruz.
music_library = [
    {"id": 1, "title": "Ateşe Düştüm", "artist": "Mert Demir"},
    {"id": 2, "title": "Antidepresan", "artist": "Mabel Matiz"},
    {"id": 3, "title": "Senden Daha Güzel", "artist": "Duman"},
    {"id": 4, "title": "Bi Tek Ben Anlarım", "artist": "KÖFN"},
    {"id": 5, "title": "Hercai", "artist": "Çelik"},
    {"id": 6, "title": "Pusulam Rüzgar", "artist": "Melike Şahin"},
    {"id": 7, "title": "Dön Desem", "artist": "Semicenk"},
    {"id": 8, "title": "Gülpembe", "artist": "Barış Manço"},
    {"id": 9, "title": "Ele Güne Karşı", "artist": "MFÖ"}
]

current_playing = {"title": "Keyifli Dakikalar", "artist": "Gastro Radyo"}
# Başlangıçta rastgele 5 şarkı seç
candidates = random.sample(music_library, 5) 
votes = {song['id']: 0 for song in candidates}
total_votes = 0

def rotate_songs():
    """Oylama bitince en çok oy alanı çalan şarkı yap ve listeyi yenile"""
    global current_playing, candidates, votes, total_votes
    
    # En çok oy alanı bul (Eşitlik varsa ilkini alır)
    if votes:
        winner_id = max(votes, key=votes.get)
        winner_song = next((s for s in candidates if s['id'] == winner_id), music_library[0])
        current_playing = winner_song
    
    # Yeni adaylar belirle (Sonsuz döngü için rastgele)
    candidates = random.sample(music_library, 5)
    votes = {song['id']: 0 for song in candidates}
    total_votes = 0

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- AUTH YARDIMCILARI ---
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Kimlik doğrulanamadı",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username, role=role)
    except JWTError:
        raise credentials_exception
    user = db.query(UserDB).filter(UserDB.username == token_data.username).first()
    if user is None:
        raise credentials_exception
    return user

# --- WEBSOCKET YÖNETİCİSİ ---
class ConnectionManager:
    def __init__(self):
        # aktif bağlantılar: {"orders": [ws1, ws2], "music": [ws3]}
        self.active_connections: dict = {"orders": [], "music": []}

    async def connect(self, websocket: WebSocket, channel: str):
        await websocket.accept()
        if channel not in self.active_connections:
            self.active_connections[channel] = []
        self.active_connections[channel].append(websocket)

    def disconnect(self, websocket: WebSocket, channel: str):
        if channel in self.active_connections:
            if websocket in self.active_connections[channel]:
                self.active_connections[channel].remove(websocket)

    async def broadcast(self, message: dict, channel: str):
        if channel in self.active_connections:
            for connection in self.active_connections[channel]:
                try:
                    await connection.send_json(message)
                except:
                    pass

manager = ConnectionManager()

# Başlangıçta Kullanıcı Oluştur
def create_initial_users():
    db = SessionLocal()
    if not db.query(UserDB).first():
        users = [
            ("admin", "admin123", "admin"),
            ("mutfak", "mutfak123", "kitchen"),
            ("garson", "garson123", "waiter")
        ]
        for u in users:
            db.add(UserDB(username=u[0], hashed_password=get_password_hash(u[1]), role=u[2]))
        db.commit()
    db.close()

create_initial_users()

# --- API ENDPOINTLERİ ---

# 0. KİMLİK DOĞRULAMA (LOGIN)
@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kullanıcı adı veya şifre hatalı",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# 1. MÜZİK WEBSOCKET
@app.websocket("/ws/music")
async def websocket_music(websocket: WebSocket):
    await manager.connect(websocket, "music")
    try:
        while True:
            await websocket.receive_text() # Keep alive
    except WebSocketDisconnect:
        manager.disconnect(websocket, "music")

# 2. MÜZİK VERİLERİNİ ÇEK
@app.get("/api/music")
def get_music_status(request: Request):
    # Rate Limit Check (İsteğe bağlı, burada pas geçtim)
    candidate_list = []
    for song in candidates:
        v = votes.get(song['id'], 0)
        percent = int((v / total_votes * 100)) if total_votes > 0 else 0
        candidate_list.append({
            "id": song['id'],
            "title": song['title'],
            "artist": song['artist'],
            "percent": percent
        })
    candidate_list.sort(key=lambda x: x['percent'], reverse=True)
    return {
        "now_playing": current_playing,
        "candidates": candidate_list,
        "total_votes": total_votes
    }

# 3. OY VERME İŞLEMİ (Limitli)
@app.post("/api/music/vote/{song_id}")
@limiter.limit("5/minute")
async def vote_song(song_id: int, request: Request):
    global total_votes
    if song_id in votes:
        votes[song_id] += 1
        total_votes += 1
        
        status_msg = "voted"
        if total_votes >= 5:
            rotate_songs()
            status_msg = "rotated"
        
        # WebSocket ile herkese yeni durumu bildir
        await manager.broadcast({"type": "update", "status": status_msg}, "music")
                     
        return {"status": status_msg, "total": total_votes}
    return {"status": "error"}

# 4. SİPARİŞ WEBSOCKET (Mutfak & Garson)
@app.websocket("/ws/orders")
async def websocket_orders(websocket: WebSocket):
    await manager.connect(websocket, "orders")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, "orders")

# 5. SİPARİŞ OLUŞTUR (Müşteri)
@app.post("/api/orders")
async def create_order(order: OrderSchema, db: Session = Depends(get_db)):
    new_order = OrderDB(
        customer_name=order.customer_name,
        table_number=order.table_number,
        items=order.items,
        total_price=order.total_price,
        status="preparing",
        waiter_ok=False,
        customer_ok=False
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)
    
    # Mutfak ekranına anlık bildirim gönder
    await manager.broadcast({"type": "new_order", "id": new_order.id}, "orders")
    
    return {"status": "success", "order_id": new_order.id}

# 6. SİPARİŞLERİ LİSTELE (Mutfak İçin - Korumalı)
@app.get("/api/orders")
def get_orders(db: Session = Depends(get_db), current_user: UserDB = Depends(get_current_user)):
    return db.query(OrderDB).order_by(OrderDB.created_at.desc()).limit(100).all()

# 7. GEÇMİŞ CİRO SORGULA (Admin Only)
@app.get("/api/orders/history")
def get_history(date_str: str, db: Session = Depends(get_db), current_user: UserDB = Depends(get_current_user)):
    if current_user.role not in ['admin', 'kitchen']:
        raise HTTPException(403, "Yetkiniz yok")
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        return db.query(OrderDB).filter(func.date(OrderDB.created_at) == target_date).all()
    except:
        return []

# 8. TEK SİPARİŞ DURUMU (Müşteri Polling/WS)
@app.get("/api/orders/{order_id}")
def get_single_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(OrderDB).filter(OrderDB.id == order_id).first()
    if not order: raise HTTPException(404, "Sipariş bulunamadı")
    return order

# 9. DURUM GÜNCELLE (Hazırla / Tamamla - Mutfak Only)
@app.put("/api/orders/{order_id}/status")
async def update_status(order_id: int, data: StatusUpdate, db: Session = Depends(get_db), current_user: UserDB = Depends(get_current_user)):
    order = db.query(OrderDB).filter(OrderDB.id == order_id).first()
    order.status = data.status
    db.commit()
    
    # Güncelleme bildirimi
    await manager.broadcast({"type": "update", "id": order.id, "status": order.status}, "orders")
    
    return {"status": "updated"}

# 10. TESLİM ONAYI (Garson / Müşteri)
@app.put("/api/orders/{order_id}/confirm")
async def confirm_order(order_id: int, data: ConfirmSchema, db: Session = Depends(get_db)):
    order = db.query(OrderDB).filter(OrderDB.id == order_id).first()
    
    # Garson ise güvenliğe takılabilir ama şimdilik hibrit bırakıyorum
    # Çünkü Waiter panelinde token olacak ama müşteri tarafında yok.
    # Burası karmaşık olmasın diye açık bırakıp rol kontrolü yapıyoruz.
    
    if data.role == 'waiter':
        order.waiter_ok = True
    elif data.role == 'customer':
        order.customer_ok = True
    
    if order.waiter_ok and order.customer_ok:
        order.status = 'completed'
    
    db.commit()
    
    await manager.broadcast({"type": "update", "id": order.id, "status": order.status}, "orders")
    
    return {"status": order.status, "waiter": order.waiter_ok, "customer": order.customer_ok}

# --- STATİK DOSYALAR (HTML) ---

@app.get("/")
async def read_index():
    return FileResponse('index.html')

@app.get("/panel")
async def read_panel():
    return FileResponse('panel.html')

# Gerekirse resimler vb. için static klasörü
app.mount("/static", StaticFiles(directory="."), name="static")

if __name__ == "__main__":
    import uvicorn
    # Render.com'un atadığı portu kullan, yoksa 8000
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
