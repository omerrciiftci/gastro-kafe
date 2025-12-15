"""
================================================================
 PROJE ADI: Gastro İnegöl - Dijital Menü ve Sipariş Sistemi (API)
================================================================
 GELİŞTİRİCİ: Ömer Çiftçi
 TARİH: 2023-2024
 MÜŞTERİ: İnegöl Belediyesi Sosyal Tesisleri
 
 AÇIKLAMA:
 Bu yazılım, FastAPI ve SQLAlchemy kullanılarak geliştirilmiş
 gerçek zamanlı bir restoran sipariş yönetim backend servisidir.
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
import os

app = FastAPI(title="Gastro İnegöl API", description="Developed by Ömer Çiftçi", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# VERİTABANI AYARLARI
SQLALCHEMY_DATABASE_URL = "sqlite:///./kafe_sistemi.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# TABLO YAPISI
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

# VERİ MODELLERİ
class OrderSchema(BaseModel):
    customer_name: str
    table_number: str
    items: str
    total_price: float

class StatusUpdate(BaseModel):
    status: str

class ConfirmSchema(BaseModel):
    role: str

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- API ENDPOINTLERİ ---

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

@app.get("/api/orders")
def get_orders(db: Session = Depends(get_db)):
    return db.query(OrderDB).order_by(OrderDB.created_at.desc()).limit(100).all()

@app.get("/api/orders/history")
def get_history(date_str: str, db: Session = Depends(get_db)):
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        return db.query(OrderDB).filter(func.date(OrderDB.created_at) == target_date).all()
    except:
        return []

@app.get("/api/orders/{order_id}")
def get_single_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(OrderDB).filter(OrderDB.id == order_id).first()
    if not order: raise HTTPException(404, "Sipariş bulunamadı")
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
    
    if data.role == 'waiter':
        order.waiter_ok = True
    elif data.role == 'customer':
        order.customer_ok = True
    
    # İKİ TARAF DA ONAYLADIYSA SİPARİŞİ TAMAMLA
    if order.waiter_ok and order.customer_ok:
        order.status = 'completed'
    
    db.commit()
    return {"status": order.status, "waiter": order.waiter_ok, "customer": order.customer_ok}

@app.get("/")
async def read_index(): return FileResponse('index.html')

@app.get("/panel")
async def read_panel(): return FileResponse('panel.html')

app.mount("/static", StaticFiles(directory="."), name="static")
