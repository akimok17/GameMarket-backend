import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.core.dependencies import get_current_user
from app.core.security import create_order_ws_token, decode_order_ws_token
from app.models.models import Order, User
from app.realtime import order_connections
from app.schemas import OrderRoomMessageCreate
from app.services.notification_service import NotificationService
from app.services.order_room_service import OrderRoomService

router = APIRouter(prefix="/order-room", tags=["order-room"])
ws_router = APIRouter(tags=["order-room-realtime"])

ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def message_payload(row) -> dict:
    return {
        "id": row.id,
        "order_id": row.order_id,
        "sender_id": row.sender_id,
        "message": row.message,
        "attachment_url": row.attachment_url,
        "attachment_name": row.attachment_name,
        "attachment_mime": row.attachment_mime,
        "is_read": row.is_read,
        "read_at": row.read_at.isoformat() if row.read_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else datetime.now(timezone.utc).isoformat(),
    }


@router.get("/{order_id}")
def room(order_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return OrderRoomService(db).get_room(order_id, current_user.id, current_user.is_admin)


@router.post("/{order_id}/ws-token")
def ws_token(order_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    OrderRoomService(db).require_access(order_id, current_user.id, current_user.is_admin)
    return {"token": create_order_ws_token(current_user.id, order_id, current_user.token_version or 0)}


@router.post("/{order_id}/read")
async def mark_read(order_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    ids = OrderRoomService(db).mark_read(order_id, current_user.id)
    if ids:
        await order_connections.broadcast(order_id, {"type": "read", "reader_id": current_user.id, "message_ids": ids})
    return {"read": len(ids), "message_ids": ids}


@router.post("/{order_id}/messages")
async def send_message_http(order_id: int, data: OrderRoomMessageCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    service = OrderRoomService(db)
    order = service.require_access(order_id, current_user.id, current_user.is_admin)
    if current_user.id not in {order.buyer_id, order.seller_id}:
        raise HTTPException(status_code=403, detail="Only order participants can send messages")
    row = service.add_message(order_id, current_user.id, data.message)
    other_id = order.seller_id if current_user.id == order.buyer_id else order.buyer_id
    if not order_connections.is_online(order_id, other_id):
        NotificationService(db).create(other_id, "Новое сообщение по заказу", f"Новое сообщение в заказе #{order_id}.", type="order_message", link=f"/order/{order_id}")
        db.commit()
    payload = message_payload(row)
    await order_connections.broadcast(order_id, {"type": "message", "message": payload})
    return payload


@router.post("/{order_id}/attachments")
async def upload_attachment(
    order_id: int,
    file: UploadFile = File(...),
    caption: str | None = Form(default=None),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = OrderRoomService(db)
    order = service.require_access(order_id, current_user.id, current_user.is_admin)
    if current_user.id not in {order.buyer_id, order.seller_id}:
        raise HTTPException(status_code=403, detail="Only order participants can upload attachments")
    if file.content_type not in ALLOWED_IMAGE_MIMES:
        raise HTTPException(status_code=415, detail="Only JPG, PNG, WEBP and GIF images are allowed")
    max_bytes = settings.ORDER_ATTACHMENT_MAX_MB * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File is larger than {settings.ORDER_ATTACHMENT_MAX_MB} MB")
    signatures_ok = {
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/gif": content.startswith((b"GIF87a", b"GIF89a")),
        "image/webp": len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP",
    }
    if not signatures_ok.get(file.content_type, False):
        raise HTTPException(status_code=415, detail="File contents do not match the declared image type")
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}[file.content_type]
    safe_original = re.sub(r"[^A-Za-z0-9._ -]", "_", file.filename or f"image{ext}")[:180]
    filename = f"{uuid.uuid4().hex}{ext}"
    base_dir = Path(__file__).resolve().parents[2] / "storage" / "order_attachments" / str(order_id)
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / filename).write_bytes(content)
    url = f"/order-room/{order_id}/attachments/{filename}"
    row = service.add_attachment(order_id, current_user.id, url=url, name=safe_original, mime=file.content_type, caption=caption)
    other_id = order.seller_id if current_user.id == order.buyer_id else order.buyer_id
    if not order_connections.is_online(order_id, other_id):
        NotificationService(db).create(other_id, "Новое сообщение по заказу", f"В заказе #{order_id} отправлено изображение.", type="order_message", link=f"/order/{order_id}")
        db.commit()
    payload = message_payload(row)
    await order_connections.broadcast(order_id, {"type": "message", "message": payload})
    return payload


@router.get("/{order_id}/attachments/{filename}", include_in_schema=False)
def get_attachment(order_id: int, filename: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    OrderRoomService(db).require_access(order_id, current_user.id, current_user.is_admin)
    if not re.fullmatch(r"[a-f0-9]{32}\.(jpg|png|webp|gif)", filename):
        raise HTTPException(status_code=404, detail="Attachment not found")
    path = Path(__file__).resolve().parents[2] / "storage" / "order_attachments" / str(order_id) / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Attachment not found")
    media = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}[path.suffix.lower()]
    return FileResponse(path, media_type=media, headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=300"})


@ws_router.websocket("/ws/orders/{order_id}")
async def order_websocket(websocket: WebSocket, order_id: int, token: str):
    payload = decode_order_ws_token(token)
    if not payload:
        await websocket.close(code=4401)
        return
    try:
        user_id = int(payload.get("sub"))
        token_order_id = int(payload.get("order_id"))
        token_version = int(payload.get("ver", 0))
    except (TypeError, ValueError):
        await websocket.close(code=4401)
        return
    if token_order_id != order_id:
        await websocket.close(code=4403)
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not user or token_version != int(user.token_version or 0) or not order:
            await websocket.close(code=4401)
            return
        if user_id not in {order.buyer_id, order.seller_id} and not user.is_admin:
            await websocket.close(code=4403)
            return
        other_id = order.seller_id if user_id == order.buyer_id else order.buyer_id
        await order_connections.connect(order_id, user_id, websocket)
        user.last_active = datetime.now(timezone.utc)
        db.commit()
        await order_connections.broadcast(order_id, {"type": "presence", "user_id": user_id, "online": True})
        await websocket.send_json({"type": "presence", "user_id": other_id, "online": order_connections.is_online(order_id, other_id)})
    finally:
        db.close()

    try:
        while True:
            data = await websocket.receive_json()
            kind = data.get("type")
            if kind == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if kind == "typing":
                await order_connections.broadcast(order_id, {"type": "typing", "user_id": user_id, "typing": bool(data.get("typing"))}, exclude=websocket)
                continue
            if kind == "read":
                db = SessionLocal()
                try:
                    ids = OrderRoomService(db).mark_read(order_id, user_id)
                finally:
                    db.close()
                if ids:
                    await order_connections.broadcast(order_id, {"type": "read", "reader_id": user_id, "message_ids": ids})
                continue
            if kind != "message":
                continue
            text = str(data.get("message") or "").strip()
            if not text or len(text) > 4000:
                await websocket.send_json({"type": "error", "detail": "Сообщение должно содержать от 1 до 4000 символов"})
                continue
            db = SessionLocal()
            try:
                service = OrderRoomService(db)
                order = service.require_access(order_id, user_id)
                row = service.add_message(order_id, user_id, text)
                other_id = order.seller_id if user_id == order.buyer_id else order.buyer_id
                if not order_connections.is_online(order_id, other_id):
                    NotificationService(db).create(other_id, "Новое сообщение по заказу", f"Новое сообщение в заказе #{order_id}.", type="order_message", link=f"/order/{order_id}")
                    db.commit()
                msg = message_payload(row)
            finally:
                db.close()
            await order_connections.broadcast(order_id, {"type": "message", "message": msg})
    except WebSocketDisconnect:
        pass
    finally:
        order_connections.disconnect(order_id, user_id, websocket)
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.last_active = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()
        await order_connections.broadcast(order_id, {"type": "presence", "user_id": user_id, "online": False})
