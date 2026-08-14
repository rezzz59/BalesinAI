"""Onboarding API — self-service flow for a logged-in merchant.

Flow: (1) register account → (2) upload XLSX (FAQ + katalog) → (3) set
WhatsApp (Fonnte device + API key) → (4) test chat → (5) live.

Differs from /api/provision (admin-token wizard): here the tenant is created
automatically for the logged-in user, and data comes from an uploaded file
(data_source='upload') instead of a Google Sheets URL.
"""
import logging
import os
import re
import secrets
import shutil

from fastapi import APIRouter, HTTPException, Request, UploadFile, Depends
from pydantic import BaseModel

from app.api.auth import current_user
from app.config import get_settings
from app.db import local_data_repo, user_repo
from app.db.tenant_repo import (
    get_tenant,
    insert_or_update_tenant,
    update_device_status,
    update_onboarding_data,
    update_onboarding_status,
    update_tier,
)
from app.services.crypto import decrypt_api_key, encrypt_api_key
from app.services.embedding_seeder import seed_local_tenant_embeddings
from app.services.xlsx_parser import XlsxParseError, parse_workbook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/onboard", tags=["onboard"])

MEDIA_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "media")
ALLOWED_IMG = {".png", ".jpg", ".jpeg", ".webp"}


def _validate_wa_number(num: str) -> str:
    """Normalize + validate an Indonesian WhatsApp number.

    Accepts 08..., 8..., 628..., +62... and strips punctuation. Returns the
    62-prefixed digits, or raises HTTPException(400) if clearly invalid.
    """
    digits = "".join(ch for ch in (num or "").strip() if ch.isdigit())
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    elif not digits.startswith("62"):
        digits = "62" + digits
    if len(digits) < 8 or len(digits) > 16:
        raise HTTPException(status_code=400, detail="Nomor WhatsApp tidak valid. Gunakan 08xx atau 628xx (9-15 digit).")
    return digits


def _normalize_wa(num: str) -> str:
    """Normalize a number for comparison without raising."""
    digits = "".join(ch for ch in (num or "").strip() if ch.isdigit())
    if digits.startswith("0"):
        return "62" + digits[1:]
    if not digits.startswith("62"):
        return "62" + digits
    return digits


def _media_dir(tenant_id: str) -> str:
    d = os.path.join(MEDIA_ROOT, tenant_id)
    os.makedirs(d, exist_ok=True)
    return d


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return slug or "toko"


def _user_tenant(user) -> dict:
    """Resolve the user's tenant record or raise."""
    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="Akun belum punya tenant.")
    tenant = get_tenant(user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant tidak ditemukan.")
    return dict(tenant)


@router.post("/tenant")
async def create_my_tenant(request: Request):
    """Create (or claim) the merchant's tenant from their account info.

    Body: {merchant_name, business_type, owner_wa_number, fonnte_device_id?,
           fonnte_api_key?}
    """
    user = current_user(request)
    body = await request.json()
    merchant_name = (body.get("merchant_name") or "").strip()
    business_type = (body.get("business_type") or "jualan").strip().lower()
    owner_wa_number = (body.get("owner_wa_number") or "").strip()
    fonnte_device_id = (body.get("fonnte_device_id") or "").strip()
    fonnte_api_key = (body.get("fonnte_api_key") or "").strip()

    if not owner_wa_number:
        raise HTTPException(status_code=400, detail="Nomor WhatsApp owner wajib diisi.")

    tenant_id = user.tenant_id or f"{_slugify(merchant_name)}-{secrets.token_hex(2)}"

    # Encrypt Fonnte key if the user explicitly provided one; otherwise leave
    # empty so a fresh QR pairing can mint the real per-device token later.
    from app.config import get_settings

    settings = get_settings()
    existing = get_tenant(tenant_id)
    key_to_encrypt = fonnte_api_key or (
        existing.get("wa_api_key_encrypted") if existing is not None else None
    )
    encrypted: bytes = b""
    if isinstance(key_to_encrypt, bytes):
        encrypted = key_to_encrypt  # keep the already-encrypted token as-is
    elif key_to_encrypt:
        encrypted = encrypt_api_key(key_to_encrypt, settings.encryption_key)

    insert_or_update_tenant(
        tenant_id=tenant_id,
        wa_api_key_encrypted=encrypted,
        google_sheet_id="",  # upload-based; sheet field kept for compatibility
        owner_wa_number=owner_wa_number,
        business_type=business_type,
        onboarding_status="pending",
        onboarding_data={"merchant_name": merchant_name},
        fonnte_device_id=fonnte_device_id,
        data_source="upload",
    )
    user_repo.update_user_tenant(user.id, tenant_id)
    return {"status": "ok", "tenant_id": tenant_id}


@router.post("/upload")
async def upload_xlsx(request: Request, file: UploadFile):
    """Replace the tenant's FAQ + catalog from an uploaded XLSX file."""
    user = current_user(request)
    tenant = _user_tenant(user)

    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Unggah file .xlsx.")

    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File kosong.")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Ukuran file terlalu besar. Maksimal 5MB.")

    try:
        parsed = parse_workbook(content)
    except XlsxParseError as e:
        raise HTTPException(status_code=400, detail=str(e))

    faq_count = local_data_repo.replace_faq(tenant["tenant_id"], parsed["faq"])
    catalog_count = local_data_repo.replace_catalog(tenant["tenant_id"], parsed["catalog"])
    ongkir_count = local_data_repo.replace_ongkir(tenant["tenant_id"], parsed.get("ongkir", []))

    # Seed embeddings for semantic search.
    try:
        seed_local_tenant_embeddings(tenant["tenant_id"])
    except Exception as e:  # noqa: BLE001
        logger.error("upload_embed_failed", extra={"tenant_id": tenant["tenant_id"], "error": str(e)})

    update_onboarding_status(tenant["tenant_id"], "data_ready")
    return {
        "status": "ok",
        "faq_count": faq_count,
        "catalog_count": catalog_count,
        "ongkir_count": ongkir_count,
    }


@router.post("/wa")
async def save_wa_settings(request: Request):
    """Save WhatsApp/Fonnte settings for the user's tenant."""
    user = current_user(request)
    tenant = _user_tenant(user)
    body = await request.json()
    fonnte_api_key = (body.get("fonnte_api_key") or "").strip()
    fonnte_device_id = (body.get("fonnte_device_id") or "").strip()
    owner_wa_number = (body.get("owner_wa_number") or "").strip()

    from app.config import get_settings

    settings = get_settings()
    encrypted = tenant["wa_api_key_encrypted"]
    if fonnte_api_key:
        encrypted = encrypt_api_key(fonnte_api_key, settings.encryption_key)

    insert_or_update_tenant(
        tenant_id=tenant["tenant_id"],
        wa_api_key_encrypted=encrypted,
        google_sheet_id=tenant.get("google_sheet_id", ""),
        owner_wa_number=owner_wa_number or tenant["owner_wa_number"],
        business_type=tenant["business_type"],
        onboarding_status=tenant["onboarding_status"],
        onboarding_data=None,  # preserved via update below
        fonnte_device_id=fonnte_device_id or tenant["fonnte_device_id"],
        data_source=tenant["data_source"],
    )
    return {"status": "ok", "tenant_id": tenant["tenant_id"]}


@router.get("/status")
async def onboard_status(request: Request):
    """Return the user's onboarding progress."""
    user = current_user(request)
    if not user.tenant_id:
        return {"status": "no_tenant", "tenant_id": None}
    tenant = _user_tenant(user)
    import json
    try:
        onboarding_data = json.loads(tenant["onboarding_data"] or "{}")
    except Exception:
        onboarding_data = {}

    return {
        "tenant_id": tenant["tenant_id"],
        "status": tenant["onboarding_status"],
        "data_source": tenant["data_source"],
        "faq_count": len(local_data_repo.session_faq(tenant["tenant_id"])),
        "catalog_count": len(local_data_repo.session_catalog(tenant["tenant_id"])),
        "fonnte_device_id": tenant["fonnte_device_id"],
        "owner_wa_number": tenant["owner_wa_number"],
        "custom_behavior": onboarding_data.get("custom_behavior", ""),
        "knowledge_text": onboarding_data.get("knowledge_text", ""),
        "welcome_message": onboarding_data.get("welcome_message", ""),
        "followup_delay_minutes": onboarding_data.get("followup_delay_minutes", 0),
        "followup_prompt": onboarding_data.get("followup_prompt", ""),
    }


@router.post("/style")
async def extract_style(request: Request):
    """Analyze raw onboarding text into identity + style profile.

    Body: {raw_onboarding_text} — typically a paste of the merchant's own
    WhatsApp replies. The extracted profile is merged into onboarding_data
    under style_profile so compose replies can imitate the merchant's tone.
    Never blocks onboarding: on any LLM failure a conservative default is
    stored instead of failing the request.
    """
    user = current_user(request)
    tenant = _user_tenant(user)
    body = await request.json()
    raw_text = (body.get("raw_onboarding_text") or "").strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="raw_onboarding_text wajib diisi.")

    from app.services.llm import get_safe_llm_client

    profile = get_safe_llm_client().extract_style_profile(raw_text)

    import json as _json

    try:
        existing = _json.loads(tenant["onboarding_data"] or "{}")
    except (ValueError, TypeError):
        existing = {}
    existing["style_profile"] = profile
    update_onboarding_data(tenant["tenant_id"], existing)
    return {"status": "ok", **profile}


@router.post("/live")
async def go_live(request: Request):
    """Mark the tenant as live (ready to accept WhatsApp webhooks)."""
    user = current_user(request)
    tenant = _user_tenant(user)
    update_onboarding_status(tenant["tenant_id"], "ready")
    return {"status": "ok", "tenant_id": tenant["tenant_id"], "live": True}


# --- Tier & WhatsApp device (QR) ---

TIER_GATEWAY = {"basic": "lite", "pro": "super", "enterprise": "waba"}


@router.post("/tier")
async def set_tier(request: Request):
    """Choose a plan: basic (text-only) / pro (text + attachment) / enterprise."""
    user = current_user(request)
    tenant = _user_tenant(user)
    body = await request.json()
    tier = (body.get("tier") or "basic").strip().lower()
    if tier not in TIER_GATEWAY:
        raise HTTPException(status_code=400, detail="Tier tidak valid.")
    update_tier(tenant["tenant_id"], tier, TIER_GATEWAY[tier])
    return {"status": "ok", "tier": tier, "gateway_plan": TIER_GATEWAY[tier]}


@router.post("/device")
async def provision_device(request: Request):
    """Create a Fonnte device for the user's WhatsApp number and return the QR.

    Uses the platform's Fonnte ACCOUNT token (create device + QR via API) so the
    user only needs to scan the QR — no Fonnte account, no token pasting.
    Body: {device_wa} — the user's business WhatsApp number.
    """
    user = current_user(request)
    tenant = _user_tenant(user)
    body = await request.json()
    device_wa = _validate_wa_number(body.get("device_wa") or "")
    if not device_wa:
        raise HTTPException(status_code=400, detail="Nomor WhatsApp device wajib diisi.")

    settings = get_settings()
    account_token = settings.fonnte_account_token
    if not account_token:
        raise HTTPException(status_code=503, detail="Gateway belum dikonfigurasi. Hubungi admin.")

    from app.services.fonnte import FonnteGateway, FonnteError

    # get-qr requires the DEVICE token, not the account token.
    device_token = ""
    # 1. Reuse the stored per-device token if this device was already paired.
    if tenant.get("wa_api_key_encrypted"):
        try:
            device_token = decrypt_api_key(tenant["wa_api_key_encrypted"], settings.encryption_key)
        except Exception:  # noqa: BLE001
            device_token = ""

    # 2. If we don't have a device token yet, create the device (account token).
    if not device_token:
        acct_gateway = FonnteGateway(api_key=account_token)
        try:
            dev = await acct_gateway.add_device(name=tenant["tenant_id"][:30], device=device_wa)
            device_token = dev.get("token", "")
        except FonnteError as e:
            if "already exist" not in str(e).lower():
                raise HTTPException(status_code=502, detail=f"Gagal buat device: {e}")

    # 3. Fetch the pairing QR with the DEVICE token.
    device_gateway = FonnteGateway(api_key=device_token)
    try:
        qr = await device_gateway.get_qr(device_wa)
    except FonnteError as e:
        # Only "already connect" means the device is actually paired.
        if "already connect" in str(e).lower():
            update_device_status(tenant["tenant_id"], "connected")
            return {"status": "ok", "device": device_wa, "qr": "", "device_status": "connected",
                    "note": str(e)}
        # Reused token may be stale (device deleted on the dashboard). Re-mint a
        # fresh device token via the account token, then retry the QR once.
        if "token invalid" in str(e).lower() and account_token:
            acct_gateway = FonnteGateway(api_key=account_token)
            try:
                dev = await acct_gateway.add_device(name=tenant["tenant_id"][:30], device=device_wa)
                fresh_token = dev.get("token", "")
                if not fresh_token:
                    raise HTTPException(status_code=502, detail=f"Device belum terhubung: {e}")
                device_token = fresh_token
                qr = await FonnteGateway(api_key=device_token).get_qr(device_wa)
            except FonnteError as de:
                raise HTTPException(status_code=502, detail=f"Gagal sambungkan device: {de}")
            except HTTPException:
                raise
        else:
            # Any other error (device not registered) is a real problem.
            raise HTTPException(status_code=502, detail=f"Gagal ambil QR: {e}")

    # 4. Persist the per-device token + number, mark pairing pending.
    if device_token:
        encrypted = encrypt_api_key(device_token, settings.encryption_key)
    else:
        encrypted = tenant["wa_api_key_encrypted"]
    insert_or_update_tenant(
        tenant_id=tenant["tenant_id"],
        wa_api_key_encrypted=encrypted,
        google_sheet_id=tenant.get("google_sheet_id", ""),
        owner_wa_number=tenant["owner_wa_number"],
        business_type=tenant["business_type"],
        onboarding_status=tenant["onboarding_status"],
        onboarding_data=None,
        fonnte_device_id=device_wa,
        data_source=tenant["data_source"],
    )
    update_device_status(tenant["tenant_id"], "pending")

    return {
        "status": "ok",
        "device": device_wa,
        "qr": qr.get("url", ""),  # base64 PNG → data:image/png;base64,...
        "device_status": "pending",
    }


@router.get("/device/status")
async def device_status(request: Request):
    """Return the current device pairing status for the user's tenant.

    When the device is pending, queries Fonnte's device profile (via the stored
    device token) to confirm whether it has been paired — and validates that the
    REAL WhatsApp number that scanned the QR matches the intended device number.
    """
    user = current_user(request)
    tenant = _user_tenant(user)

    status = tenant.get("device_status", "fresh")
    intended = tenant.get("fonnte_device_id", "")
    real_number = intended
    valid = None  # None=unknown, True=scanned number matches, False=mismatch

    if status == "pending":
        settings = get_settings()
        account_token = settings.fonnte_account_token
        if account_token:
            try:
                from app.services.fonnte import FonnteGateway, FonnteError

                # 1. Connect state from the account (get-devices), matched by label.
                res = await FonnteGateway(api_key=account_token).get_devices()
                connected = False
                for dev in res.get("data", []):
                    if dev.get("device") == intended:
                        if dev.get("status") == "connect":
                            connected = True
                        elif dev.get("status") == "disconnect":
                            status = "disconnect"
                        break
                if connected:
                    status = "connected"
                    # 2. Validate the REAL scanned number via the device token.
                    device_token = ""
                    if tenant.get("wa_api_key_encrypted"):
                        try:
                            device_token = decrypt_api_key(tenant["wa_api_key_encrypted"], settings.encryption_key)
                        except Exception:  # noqa: BLE001
                            device_token = ""
                    if device_token:
                        profile = await FonnteGateway(api_key=device_token).device_profile()
                        scanned = str(profile.get("device", "")).replace("+", "").replace("-", "")
                        if scanned:
                            real_number = scanned
                            valid = _normalize_wa(scanned) == _normalize_wa(intended)
                            if not valid:
                                # Reject: disconnect the wrong number, reset to pending.
                                try:
                                    await FonnteGateway(api_key=device_token).disconnect()
                                except Exception:  # noqa: BLE001
                                    pass
                                update_device_status(tenant["tenant_id"], "rejected")
                                status = "rejected"
                                logger.warning(
                                    "device_number_rejected",
                                    extra={"tenant": tenant["tenant_id"], "intended": intended, "scanned": scanned},
                                )
                            else:
                                update_device_status(tenant["tenant_id"], "connected")
            except Exception:  # noqa: BLE001
                pass  # keep current status; frontend can retry

    return {
        "device": real_number,
        "device_status": status,
        "device_match": valid,
        "tier": tenant.get("tier", "basic"),
        "gateway_plan": tenant.get("gateway_plan", "lite"),
    }


@router.post("/media")
async def upload_photo(request: Request, file: UploadFile):
    """Upload a product photo. Filename = product name (nama_produk) so the bot
    can match a photo to a catalog row and send it as a real image.

    Saves to data/media/<tenant>/<slug>.<ext> and returns the public URL:
    {BASE_URL}/media/<tenant>/<slug>.<ext>
    """
    user = current_user(request)
    tenant = _user_tenant(user)
    if not file.filename:
        raise HTTPException(status_code=400, detail="File tidak valid.")

    name, ext = os.path.splitext(file.filename)
    ext = ext.lower()
    if ext not in ALLOWED_IMG:
        raise HTTPException(status_code=400, detail="Format foto harus png/jpg/jpeg/webp.")

    # Slugified, safe filename derived from the product name.
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "foto"
    safe = f"{slug}__{secrets.token_hex(3)}{ext}"
    dest = os.path.join(_media_dir(tenant["tenant_id"]), safe)

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    settings = get_settings()
    url = f"{settings.base_url}/media/{tenant['tenant_id']}/{safe}"
    return {"status": "ok", "filename": file.filename, "product": name, "url": url}
class BehaviorRequest(BaseModel):
    behavior: str

@router.put("/behavior")
async def update_behavior(req: BehaviorRequest, user=Depends(current_user)):
    """Set custom AI Agent Behavior instructions.
    
    This text is injected directly into the system prompt to customize the
    bot's tone, rules, or upselling strategies (Cekat AI parity).
    """
    tenant = _user_tenant(user)
    try:
        import json
        data = json.loads(tenant["onboarding_data"] or "{}")
    except Exception:
        data = {}
        
    data["custom_behavior"] = req.behavior.strip()
    update_onboarding_data(user.uid, data)
    
    return {"status": "ok", "message": "Behavior updated"}

class KnowledgeRequest(BaseModel):
    knowledge_text: str

@router.put("/knowledge")
async def update_knowledge(req: KnowledgeRequest, user=Depends(current_user)):
    """Set custom knowledge base text (SOP/FAQ/Company Info).
    
    This unstructured text is injected into the system prompt so the AI
    knows how to answer specific questions without needing a structured FAQ sheet.
    """
    tenant = _user_tenant(user)
    try:
        import json
        data = json.loads(tenant["onboarding_data"] or "{}")
    except Exception:
        data = {}
        
    data["knowledge_text"] = req.knowledge_text.strip()
    update_onboarding_data(user.uid, data)
    
    return {"status": "ok", "message": "Knowledge updated"}

class WelcomeMessageRequest(BaseModel):
    welcome_message: str

@router.put("/welcome")
async def update_welcome_message(req: WelcomeMessageRequest, user=Depends(current_user)):
    """Set the welcome message for new conversations."""
    tenant = _user_tenant(user)
    try:
        import json
        data = json.loads(tenant["onboarding_data"] or "{}")
    except Exception:
        data = {}
        
    data["welcome_message"] = req.welcome_message.strip()
    update_onboarding_data(user.uid, data)
    
    return {"status": "ok", "message": "Welcome message updated"}

class FollowupRequest(BaseModel):
    delay_minutes: int
    prompt: str

@router.put("/followup")
async def update_followup(req: FollowupRequest, user=Depends(current_user)):
    """Set AI Follow-up (anti-ghosting) configuration."""
    tenant = _user_tenant(user)
    try:
        import json
        data = json.loads(tenant["onboarding_data"] or "{}")
    except Exception:
        data = {}
        
    data["followup_delay_minutes"] = max(0, req.delay_minutes)
    data["followup_prompt"] = req.prompt.strip()
    update_onboarding_data(user.uid, data)
    
    return {"status": "ok", "message": "Follow-up settings updated"}
