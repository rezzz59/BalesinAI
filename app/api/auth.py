"""Authentication API — register, login, logout, me. Cookie session auth."""
import logging

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app.db import user_repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

SESSION_COOKIE = "balesin_session"


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=user_repo.SESSION_TTL_HOURS * 3600,
        httponly=True,
        samesite="lax",
        path="/",
    )


def current_user(request: Request):
    """Dependency: resolve the logged-in user from the session cookie."""
    token = request.cookies.get(SESSION_COOKIE) or ""
    user = user_repo.get_session_user(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Silakan masuk terlebih dahulu.")
    return user


@router.post("/register")
async def register(request: Request):
    body = await request.json()
    email = (body.get("email") or "").strip()
    password = body.get("password") or ""
    full_name = (body.get("full_name") or "").strip()

    try:
        user = user_repo.create_user(email=email, password=password, full_name=full_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    session = user_repo.create_session(user.id)
    response = JSONResponse({"status": "ok", "user_id": user.id, "email": user.email})
    _set_session_cookie(response, session.token)
    return response


@router.post("/login")
async def login(request: Request):
    body = await request.json()
    email = (body.get("email") or "").strip()
    password = body.get("password") or ""
    user = user_repo.validate_login(email, password)
    if user is None:
        raise HTTPException(status_code=401, detail="Email atau kata sandi salah.")

    session = user_repo.create_session(user.id)
    response = JSONResponse({"status": "ok", "user_id": user.id, "email": user.email})
    _set_session_cookie(response, session.token)
    return response


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE) or ""
    user_repo.delete_session(token)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "ok"}


@router.get("/me")
async def me(request: Request):
    token = request.cookies.get(SESSION_COOKIE) or ""
    user = user_repo.get_session_user(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Belum masuk.")
    from app.db.tenant_repo import get_tenant

    tenant = get_tenant(user.tenant_id) if user.tenant_id else None
    public_tenant = None
    if tenant:
        import json as _json
        onboarding = {}
        try:
            onboarding = _json.loads(tenant.get("onboarding_data") or "{}")
        except Exception:  # noqa: BLE001
            onboarding = {}
        public_tenant = {
            "tenant_id": tenant["tenant_id"],
            "business_type": tenant["business_type"],
            "onboarding_status": tenant["onboarding_status"],
            "owner_wa_number": tenant["owner_wa_number"],
            "fonnte_device_id": tenant["fonnte_device_id"],
            "data_source": tenant["data_source"],
            "onboarding_data": onboarding,
        }
    return {
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name},
        "tenant": public_tenant,
    }