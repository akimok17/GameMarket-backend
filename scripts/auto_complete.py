from app.core.database import SessionLocal
from app.services.order_service import OrderService


def main():
    db = SessionLocal()
    try:
        print(OrderService(db).auto_complete())
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
