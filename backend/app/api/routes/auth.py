import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.portfolio import Portfolio
from app.models.user import User, UserProfile
from app.schemas.auth import Token, UserLogin, UserOut, UserPreferences, UserRegister
from app.services.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(email=payload.email, hashed_password=hash_password(payload.password), full_name=payload.full_name)
    db.add(user)
    db.flush()

    db.add(UserProfile(user_id=user.id))
    db.add(Portfolio(user_id=user.id, name="My Portfolio"))
    db.commit()
    db.refresh(user)

    token = create_access_token(subject=user.email)
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=Token)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(subject=user.email)
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)


@router.get("/me/preferences", response_model=UserPreferences)
def get_preferences(current_user: User = Depends(get_current_user)):
    raw = current_user.profile.preferences if current_user.profile else None
    if not raw:
        return UserPreferences()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return UserPreferences()
    return UserPreferences(excluded_sectors=data.get("excluded_sectors", []))


@router.put("/me/preferences", response_model=UserPreferences)
def set_preferences(
    payload: UserPreferences,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.profile:
        current_user.profile = UserProfile(user_id=current_user.id)
        db.add(current_user.profile)
    current_user.profile.preferences = json.dumps({"excluded_sectors": payload.excluded_sectors})
    db.commit()
    return payload
