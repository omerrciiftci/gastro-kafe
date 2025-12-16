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
import os

app = FastAPI(title="Gastro İnegöl API", description="Developed by Ömer Faruk Çiftci", version="3.0.0")

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

# --- API ENDPOINTLERİ ---

# 1. MÜZİK VERİLERİNİ ÇEK
@app.get("/api/music")
def get_music_status():
    candidate_list = []
    for song in candidates:
        v = votes.get(song['id'], 0)
        # Yüzdelik hesapla
        percent = int((v / total_votes * 100)) if total_votes > 0 else 0
        candidate_list.append({
            "id": song['id'],
            "title": song['title'],
            "artist": song['artist'],
            "percent": percent
        })
    
    # Yüzdeye göre sırala (En yüksek en üstte dursun)
    candidate_list.sort(key=lambda x: x['percent'], reverse=True)

    return {
        "now_playing": current_playing,
        "candidates": candidate_list,
        "total_votes": total_votes
    }

# 2. OY VERME İŞLEMİ
@app.post("/api/music/vote/{song_id}")
def vote_song(song_id: int):
    global total_votes
    if song_id in votes:
        votes[song_id] += 1
        total_votes += 1
        
        # DEMO MANTIĞI: Her 5 oyda bir şarkı değişsin ki sunumda hareket olsun
        if total_votes >= 5:
            rotate_songs()
            return {"status": "rotated", "message": "Oylama bitti, yeni şarkı çalıyor!"}
            
        return {"status": "voted", "total": total_votes}
    return {"status": "error"}

# 3. SİPARİŞ OLUŞTUR
@app.post("/api/orders")
def create_order(order: OrderSchema, db: Session = Depends(get_db)):
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
    return {"status": "success", "order_id": new_order.id}

# 4. SİPARİŞLERİ LİSTELE (Mutfak İçin)
@app.get("/api/orders")
def get_orders(db: Session = Depends(get_db)):
    return db.query(OrderDB).order_by(OrderDB.created_at.desc()).limit(100).all()

# 5. GEÇMİŞ CİRO SORGULA
@app.get("/api/orders/history")
def get_history(date_str: str, db: Session = Depends(get_db)):
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        return db.query(OrderDB).filter(func.date(OrderDB.created_at) == target_date).all()
    except:
        return []

# 6. TEK SİPARİŞ DURUMU (Müşteri Polling İçin)
@app.get("/api/orders/{order_id}")
def get_single_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(OrderDB).filter(OrderDB.id == order_id).first()
    if not order: raise HTTPException(404, "Sipariş bulunamadı")
    return order

# 7. DURUM GÜNCELLE (Hazırla / Tamamla)
@app.put("/api/orders/{order_id}/status")
def update_status(order_id: int, data: StatusUpdate, db: Session = Depends(get_db)):
    order = db.query(OrderDB).filter(OrderDB.id == order_id).first()
    order.status = data.status
    db.commit()
    return {"status": "updated"}

# 8. TESLİM ONAYI (Garson / Müşteri)
@app.put("/api/orders/{order_id}/confirm")
def confirm_order(order_id: int, data: ConfirmSchema, db: Session = Depends(get_db)):
    order = db.query(OrderDB).filter(OrderDB.id == order_id).first()
    
    if data.role == 'waiter':
        order.waiter_ok = True
    elif data.role == 'customer':
        order.customer_ok = True
    
    # İki taraf da onayladıysa sipariş "completed" (bitti) olur
    if order.waiter_ok and order.customer_ok:
        order.status = 'completed'
    
    db.commit()
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
