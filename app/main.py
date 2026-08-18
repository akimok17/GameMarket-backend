import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.core.migrations import migrate_legacy_schema
from app.models import models
from app.models.models import Category
from app.routers import admin, balance, categories, chat, disputes, favorites, notifications, order_room, orders, payments, products, profile, support, users, verification

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "frontend", "static")

DEFAULT_CATEGORIES = [
    ("Игры", "🎮"), ("Аккаунты", "👤"), ("Ключи активации", "🔑"),
    ("Софт", "💻"), ("Услуги", "🛠️"), ("Дизайн", "🎨"),
    ("SEO", "📈"), ("Контент", "📝"),
]


def seed_categories() -> None:
    db = SessionLocal()
    try:
        existing = {x.name for x in db.query(Category).all()}
        for name, icon in DEFAULT_CATEGORIES:
            if name not in existing:
                db.add(Category(name=name, icon=icon))
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.CREATE_TABLES_ON_STARTUP:
        models.Base.metadata.create_all(bind=engine)
    if settings.MIGRATE_LEGACY_SCHEMA:
        changed = migrate_legacy_schema(engine)
        if changed:
            print("[GameMarket] Legacy DB migration applied:", ", ".join(changed))
    if settings.CREATE_TABLES_ON_STARTUP:
        seed_categories()
    yield


app = FastAPI(title="GameMarket API", version="2.6.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

for router in (users.router, verification.router, products.router, orders.router, categories.router, favorites.router,
               chat.router, balance.router, payments.router, profile.router, disputes.router, notifications.router, support.router, order_room.router, order_room.ws_router, admin.router):
    app.include_router(router)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health")
def health():
    return {"status": "ok", "version": "2.6.0"}


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/login", include_in_schema=False)
def login_page():
    return FileResponse(os.path.join(STATIC_DIR, "login.html"))


@app.get("/register", include_in_schema=False)
def register_page():
    return FileResponse(os.path.join(STATIC_DIR, "register.html"))


@app.get("/profile", include_in_schema=False)
def profile_page():
    return FileResponse(os.path.join(STATIC_DIR, "profile.html"))


@app.get("/payment-return", include_in_schema=False)
def payment_return_page():
    return FileResponse(os.path.join(STATIC_DIR, "payment-return.html"))


@app.get("/support", include_in_schema=False)
def support_page():
    return FileResponse(os.path.join(STATIC_DIR, "support.html"))


@app.get("/order/{order_id}", include_in_schema=False)
def order_room_page(order_id: int):
    return FileResponse(os.path.join(STATIC_DIR, "order.html"))


@app.get("/seller/{user_id}", include_in_schema=False)
def seller_page(user_id: int):
    return FileResponse(os.path.join(STATIC_DIR, "seller.html"))


@app.get("/forgot-password", include_in_schema=False)
def forgot_password_page():
    return FileResponse(os.path.join(STATIC_DIR, "forgot-password.html"))
