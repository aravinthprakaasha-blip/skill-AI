from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import LearnerProfile, User

settings = get_settings()
bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except ValueError:
        return False


def create_token(user: User) -> str:
    payload = {
        "sub": user.id,
        "role": user.role,
        "iss": "skillforge",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_supabase(token: str) -> dict | None:
    if not settings.supabase_jwt_secret:
        return None
    try:
        return jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated")
    except jwt.PyJWTError:
        return None


def user_from_token(token: str, db: Session) -> User | None:
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], issuer="skillforge")
        return db.get(User, claims["sub"])
    except jwt.PyJWTError:
        pass
    claims = decode_supabase(token)
    if claims:
        return db.query(User).filter(User.supabase_id == claims.get("sub")).first()
    return None


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    user = user_from_token(creds.credentials, db) if creds else None
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


def require_role(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user

    return dep


def current_profile(user: User = Depends(current_user), db: Session = Depends(get_db)) -> LearnerProfile:
    profile = db.query(LearnerProfile).filter(LearnerProfile.user_id == user.id).first()
    if not profile:
        profile = LearnerProfile(user_id=user.id)
        db.add(profile)
        db.commit()
    return profile
