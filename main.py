from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# VERİTABANI BAĞLANTISI
SQLALCHEMY_DATABASE_URL = "sqlite:///./kafe_sistemi.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# SİPARİŞ TABLOSU (Masa No ve Durum Eklendi)
class OrderDB(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String)
    table_number = Column(String)  # MASA NUMARASI
    items = Column(String)
    total_price = Column(Float)
    status = Column(String, default="preparing") # preparing (hazırlanıyor), ready (hazır), completed (teslim edildi)
    created_at = Column(DateTime, default=datetime.now)

Base.metadata.create_all(bind=engine)

# VERİ MODELLERİ
class OrderSchema(BaseModel):
    customer_name: str
    table_number: str
    items: str
    total_price: float

class OrderStatusUpdate(BaseModel):
    status: str

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- API UÇLARI ---

# Sipariş Oluştur
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

# Tüm Siparişleri Çek (Garson İçin)
@app.get("/api/orders")
def get_orders(db: Session = Depends(get_db)):
    return db.query(OrderDB).order_by(OrderDB.created_at.desc()).all()

# Tek Bir Siparişi Çek (Müşteri Bildirimi İçin)
@app.get("/api/orders/{order_id}")
def get_single_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(OrderDB).filter(OrderDB.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş yok")
    return order

# Sipariş Durumunu Güncelle (Hazır veya Tamamlandı Yap)
@app.put("/api/orders/{order_id}")
def update_order_status(order_id: int, status_update: OrderStatusUpdate, db: Session = Depends(get_db)):
    order = db.query(OrderDB).filter(OrderDB.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Bulunamadı")
    
    order.status = status_update.status
    db.commit()
    return {"status": "success", "new_status": order.status}

# --- HTML SAYFALARI ---
@app.get("/")
async def read_index():
    return FileResponse('index.html')

@app.get("/panel")
async def read_panel():
    return FileResponse('panel.html')

app.mount("/static", StaticFiles(directory="."), name="static")