from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_admin, get_current_user
from app.realtime import order_connections
from app.schemas import DisputeCreate, DisputeResolve, DisputeResponse
from app.services.dispute_service import DisputeService

router = APIRouter(prefix="/disputes", tags=["disputes"])


@router.post("/", response_model=DisputeResponse, status_code=201)
async def create_dispute(data: DisputeCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    result = DisputeService(db).create(current_user.id, data)
    await order_connections.broadcast(data.order_id, {"type": "order_updated", "status": "disputed", "reason": "dispute_opened"})
    return result


@router.get("/my", response_model=list[DisputeResponse])
def my_disputes(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return DisputeService(db).get_by_user(current_user.id)


@router.get("/order/{order_id}", response_model=list[DisputeResponse])
def disputes_by_order(order_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return DisputeService(db).get_by_order(order_id, current_user.id, current_user.is_admin)


@router.get("/{dispute_id}", response_model=DisputeResponse)
def get_dispute(dispute_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return DisputeService(db).get_for_user(dispute_id, current_user.id, current_user.is_admin)


@router.put("/{dispute_id}/resolve", response_model=DisputeResponse)
async def resolve_dispute(dispute_id: int, data: DisputeResolve, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    result = DisputeService(db).resolve(dispute_id, data.resolution, admin.id)
    await order_connections.broadcast(result.order_id, {"type": "order_updated", "status": "resolved", "reason": "dispute_resolved"})
    return result
