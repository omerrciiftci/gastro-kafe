"""
================================================================
 PROJE ADI: Gastro İnegöl - Dijital Menü ve Sipariş Sistemi (API)
================================================================
 GELİŞTİRİCİ: Ömer Çiftçi
 TARİH: 2023-2024
 AÇIKLAMA: Müzik Oylama Sistemi Eklendi (Demokratik DJ)
================================================================
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
import random

app = FastAPI(title="Gastro İnegöl API", description="Developed by Ömer Çiftçi", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- VERİTABANI ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./kafe_sistemi.db"
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

Base.metadata.create_all(bind=engine)

# --- ŞEMALAR ---
class OrderSchema(BaseModel):
    customer_name: str
    table_number: str
    items: str
    total_price: float

class StatusUpdate(BaseModel):
    status: str

class ConfirmSchema(BaseModel):
    role: str

# --- MÜZİK SİSTEMİ (RAM TABANLI - DEMO İÇİN) ---
# Gerçek veritabanı yerine sunumda hızlı çalışsın diye RAM'de tutuyoruz.
music_library = [
    {"id": 1, "title": "Ateşe Düştüm", "artist": "Mert Demir"},
    {"id": 2, "title": "Antidepresan", "artist": "Mabel Matiz"},
    {"id": 3, "title": "Senden Daha Güzel", "artist": "Duman"},
    {"id": 4, "title": "Bi Tek Ben Anlarım", "artist": "KÖFN"},
    {"id": 5, "title": "Hercai", "artist": "Çelik"},
    {"id": 6, "title": "Pusulam Rüzgar", "artist": "Melike Şahin"},
    {"id": 7, "title": "Dön Desem", "artist": "Semicenk"}
]

current_playing = {"title": "Keyifli Dakikalar", "artist": "Gastro Radyo"}
candidates = random.sample(music_library, 5) # Rastgele 5 şarkı seç
votes = {song['id']: 0 for song in candidates}
total_votes = 0

def rotate_songs():
    global current_playing, candidates, votes, total_votes
    # En çok oy alanı bul
    winner_id = max(votes, key=votes.get)
    winner_song = next(s for s in candidates if s['id'] == winner_id)
    
    # Kazananı çalmaya başla
    current_playing = winner_song
    
    # Yeni adaylar belirle
    candidates = random.sample(music_library, 5)
    votes = {song['id']: 0 for song in candidates}
    total_votes = 0

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# --- API ENDPOINTLERİ ---

@app.get("/api/music")
def get_music_status():
    # Adayları ve oy oranlarını hazırla
    candidate_list = []
    for song in candidates:
        v = votes[song['id']]
        percent = (v / total_votes * 100) if total_votes > 0 else 0
        candidate_list.append({
            "id": song['id'],
            "title": song['title'],
            "artist": song['artist'],
            "percent": int(percent)
        })
    
    return {
        "now_playing": current_playing,
        "candidates": candidate_list,
        "total_votes": total_votes
    }

@app.post("/api/music/vote/{song_id}")
def vote_song(song_id: int):
    global total_votes
    if song_id in votes:
        votes[song_id] += 1
        total_votes += 1
        
        # DEMO MANTIĞI: Her 5 oyda bir şarkı değişsin (Sunumda hızlı göstermek için)
        if total_votes >= 5:
            rotate_songs()
            return {"status": "rotated", "message": "Oylama bitti, yeni şarkı çalıyor!"}
            
        return {"status": "voted", "total": total_votes}
    return {"status": "error"}

@app.post("/api/orders")
def create_order(order: OrderSchema, db: Session = Depends(get_db)):
    new_order = OrderDB(
        customer_name=order.customer_name,
        table_number=order.table_number,
        items=order.items,
        total_price=order.total_price,
        status="preparing"
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)
    return {"status": "success", "order_id": new_order.id}

@app.get("/api/orders")
def get_orders(db: Session = Depends(get_db)):
    return db.query(OrderDB).order_by(OrderDB.created_at.desc()).limit(100).all()

@app.get("/api/orders/history")
def get_history(date_str: str, db: Session = Depends(get_db)):
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        return db.query(OrderDB).filter(func.date(OrderDB.created_at) == target_date).all()
    except: return []

@app.get("/api/orders/{order_id}")
def get_single_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(OrderDB).filter(OrderDB.id == order_id).first()
    return order

@app.put("/api/orders/{order_id}/status")
def update_status(order_id: int, data: StatusUpdate, db: Session = Depends(get_db)):
    order = db.query(OrderDB).filter(OrderDB.id == order_id).first()
    order.status = data.status
    db.commit()
    return {"status": "updated"}

@app.put("/api/orders/{order_id}/confirm")
def confirm_order(order_id: int, data: ConfirmSchema, db: Session = Depends(get_db)):
    order = db.query(OrderDB).filter(OrderDB.id == order_id).first()
    if data.role == 'waiter': order.waiter_ok = True
    elif data.role == 'customer': order.customer_ok = True
    if order.waiter_ok and order.customer_ok: order.status = 'completed'
    db.commit()
    return {"status": order.status}

@app.get("/")
async def read_index(): return FileResponse('index.html')

@app.get("/panel")
async def read_panel(): return FileResponse('panel.html')

app.mount("/static", StaticFiles(directory="."), name="static")
