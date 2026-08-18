import getpass

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.models import User


def main():
    username = input("Admin username: ").strip()
    email = input("Admin email: ").strip().lower()
    password = getpass.getpass("Admin password: ")
    db = SessionLocal()
    try:
        if db.query(User).filter((User.username == username) | (User.email == email)).first():
            raise SystemExit("User already exists")
        user = User(username=username, email=email, password_hash=hash_password(password), is_admin=True, is_seller=True)
        db.add(user)
        db.commit()
        print(f"Admin #{user.id} created")
    finally:
        db.close()


if __name__ == "__main__":
    main()
