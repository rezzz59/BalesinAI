"""End-to-end walkthrough from a user's POV against the LIVE server.

Flow:
1. Register a fresh account
2. Login (get session cookie)
3. Create tenant (onboard)
4. Upload XLSX data
5. Set welcome message
6. Set followup
7. Go live
8. Simulate customer messages via test-chat (buyer POV)
9. Verify inbox / conversation

Run: python scripts/walkthrough_e2e.py
"""
import httpx
import uuid
import sys

BASE = "http://127.0.0.1:8000"
STEP = 0


def hdr(title):
    global STEP
    STEP += 1
    print(f"\n{'='*70}\n[{STEP}] {title}\n{'='*70}")


def ok(r, label=""):
    tag = f" {label}" if label else ""
    print(f"  -> {r.status_code}{tag}")
    if r.status_code >= 400:
        print("  !!!", r.text[:300])


c = httpx.Client(base_url=BASE, timeout=180, follow_redirects=False)

email = f"e2e-{uuid.uuid4().hex[:8]}@balesin.ai"
pwd = "rahasia123"
owner_wa = "+6281388880000"

# 1. Register
hdr("Daftar akun baru")
r = c.post("/api/auth/register", json={"email": email, "password": pwd, "full_name": "Budi E2E"})
ok(r, f"user_id={r.json().get('user_id') if r.status_code == 200 else '?'}")

# 2. Me (should be logged in via cookie)
hdr("Cek sesi /api/auth/me")
r = c.get("/api/auth/me")
ok(r)
if r.status_code == 200:
    print("  user:", r.json().get("user", {}).get("email"))

# 3. Create tenant
hdr("Buat tenant (onboard)")
r = c.post("/api/onboard/tenant", json={
    "merchant_name": "Toko Kaos Budi",
    "business_type": "fashion",
    "owner_wa_number": owner_wa,
})
ok(r)
tenant_id = r.json().get("tenant_id") if r.status_code == 200 else None
print("  tenant_id:", tenant_id)

# 4. Upload XLSX
hdr("Upload data (FAQ + katalog .xlsx)")
with open("fixtures/sample_faq_katalog.xlsx", "rb") as f:
    r = c.post("/api/onboard/upload", files={"file": ("katalog.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
ok(r)
if r.status_code == 200:
    print("  faq:", r.json().get("faq_count"), "| catalog:", r.json().get("catalog_count"))

# 5. Set welcome message
hdr("Set welcome message")
r = c.put("/api/onboard/welcome", json={"welcome_message": "Halo! Selamat datang di Toko Kaos Budi. Ada yang bisa kami bantu?"})
ok(r)

# 6. Set followup
hdr("Set followup anti-ghosting")
r = c.put("/api/onboard/followup", json={"delay_minutes": 15, "prompt": "Masih minat Kak? Stok terbatas lho 😊"})
ok(r)

# 7. Go live
hdr("Go live")
r = c.post("/api/onboard/live")
ok(r)

# 8. Simulate customer messages (buyer POV)
hdr("POV pembeli — test chat")
if not tenant_id:
    print("  SKIP: tenant tidak dibuat")
    sys.exit(1)

msgs = [
    "halo kak",
    "ada kaos polos warna apa aja?",
    "berapa harga kaosnya?",
    "saya mau pesan kaos hitam size L 2 pcs",
]
for m in msgs:
    print(f"\n  PEMBELI: {m!r}")
    r = c.post("/api/provision/test-chat", json={"tenant_id": tenant_id, "message": m})
    if r.status_code == 200:
        d = r.json()
        print(f"  BOT    : {d.get('reply','')!r}"[:220])
        print(f"           (intent={d.get('intent')}, action={d.get('action')})")
    else:
        print("  ERR", r.status_code, r.text[:200])

# 9. Merchant dashboard (user-session auth; test-chat is dry-run so no logs yet)
hdr("Cek dashboard merchant")
r = c.get(f"/api/dashboard/conversations?tenant_id={tenant_id}")
ok(r)
if r.status_code == 200:
    d = r.json()
    conv = d.get("conversations", [])
    print(f"  {len(conv)} conversation(s) — (test-chat = dry-run, tidak menulis log)")
