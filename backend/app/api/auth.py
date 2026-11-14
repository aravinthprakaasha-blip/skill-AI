from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import LearnerProfile, User
from ..schemas import LoginIn, RegisterIn
from ..security import bearer, create_token, current_user, decode_supabase, hash_password, verify_password
from .common import user_out

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(409, "An account with this email already exists")
    user = User(email=body.email.lower(), display_name=body.display_name.strip(), role=body.role,
                password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    if user.role == "learner":
        db.add(LearnerProfile(user_id=user.id))
    db.commit()
    return {"token": create_token(user), "user": user_out(db, user)}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    return {"token": create_token(user), "user": user_out(db, user)}


@router.post("/supabase")
def supabase_exchange(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)):
    """Exchange a Supabase Auth access token for a SkillForge session (links or creates the user)."""
    claims = decode_supabase(creds.credentials) if creds else None
    if not claims:
        raise HTTPException(401, "Invalid or unconfigured Supabase token")
    user = db.query(User).filter(User.supabase_id == claims["sub"]).first()
    if not user:
        email = (claims.get("email") or f"{claims['sub']}@supabase.local").lower()
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.supabase_id = claims["sub"]
        else:
            meta = claims.get("user_metadata") or {}
            role = meta.get("role") if meta.get("role") in ("learner", "recruiter") else "learner"
            user = User(email=email, supabase_id=claims["sub"], role=role,
                        display_name=str(meta.get("full_name") or email.split("@")[0])[:120])
            db.add(user)
            db.flush()
            if role == "learner":
                db.add(LearnerProfile(user_id=user.id))
        db.commit()
    return {"token": create_token(user), "user": user_out(db, user)}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return user_out(db, user)
