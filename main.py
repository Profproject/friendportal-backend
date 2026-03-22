from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import requests

from database import SessionLocal, engine
from models import Base, User, WithdrawRequest

# =========================
# CONFIG
# =========================
CRYPTO_PAY_TOKEN = "500297:AAIVkVz3FZ2rD5UfSmiAUk5NClQEEpZPwMw"
CRYPTO_PAY_API = "https://pay.crypt.bot/api"

BOT_TOKEN = "8516580775:AAGal4FIUfn-Y822L0YX_LAi6pyBjUIIDT4"
ADMIN_TG_ID = 8445167015

MIN_WITHDRAW_BALANCE = 10
ACTIVATION_PRICE = 25
LEVEL1_REWARD = 0.025
LEVEL2_REWARD = 0.0125

app = FastAPI()

# =========================
# CORS
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# DB init
# =========================
Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def send_admin(text: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": ADMIN_TG_ID, "text": text},
            timeout=20
        )
    except Exception as e:
        print("send_admin error:", e)


def create_invoice(amount: float, payload: str):
    try:
        r = requests.post(
            f"{CRYPTO_PAY_API}/createInvoice",
            headers={"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN},
            json={"asset": "TON", "amount": amount, "payload": payload},
            timeout=20
        )
        data = r.json()

        if "result" not in data or not data["result"]:
            return {"error": data}

        return data["result"]["pay_url"]
    except Exception as e:
        return {"error": str(e)}


# =========================
# ROOT
# =========================
@app.get("/")
def root():
    return {"status": "ok"}


# =========================
# BALANCE + FIRST VISIT
# =========================
@app.post("/balance")
def balance(data: dict, db: Session = Depends(get_db)):
    uid = data.get("user_id")
    if not uid:
        return {"error": "user_id missing"}

    try:
        uid = int(uid)
    except Exception:
        return {"error": "invalid user_id"}

    ref_id = data.get("ref_id")
    safe_ref_id = None

    if ref_id is not None:
        try:
            ref_id = int(ref_id)
            if ref_id != uid:
                safe_ref_id = ref_id
        except Exception:
            safe_ref_id = None

    user = db.query(User).get(uid)

    if not user:
        user = User(
            id=uid,
            referrer_id=safe_ref_id,
            balance=0,
            activated=False,
            ref_rewarded=False
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # если юзер уже есть, но referrer_id не был записан, можно записать один раз
    if user.referrer_id is None and safe_ref_id and safe_ref_id != uid:
        user.referrer_id = safe_ref_id
        db.commit()
        db.refresh(user)

    # начисление только один раз за первого вошедшего юзера
    if user.referrer_id and not user.ref_rewarded:
        ref1 = db.query(User).get(user.referrer_id)

        if ref1 and ref1.id != user.id:
            ref1.balance = float(ref1.balance or 0) + LEVEL1_REWARD

            if ref1.referrer_id and ref1.referrer_id != user.id:
                ref2 = db.query(User).get(ref1.referrer_id)
                if ref2 and ref2.id not in [user.id, ref1.id]:
                    ref2.balance = float(ref2.balance or 0) + LEVEL2_REWARD

        user.ref_rewarded = True
        db.commit()
        db.refresh(user)

    return {
        "balance": round(float(user.balance or 0), 4),
        "activated": bool(user.activated)
    }


# =========================
# PAY / ACTIVATE
# =========================
@app.post("/pay")
def pay(data: dict, db: Session = Depends(get_db)):
    uid = data.get("user_id")
    if not uid:
        return {"error": "user_id missing"}

    try:
        uid = int(uid)
    except Exception:
        return {"error": "invalid user_id"}

    user = db.query(User).get(uid)
    if not user:
        user = User(
            id=uid,
            balance=0,
            activated=False,
            ref_rewarded=False
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    if float(user.balance or 0) < MIN_WITHDRAW_BALANCE:
        return {"error": "min_10_required"}

    if user.activated:
        return {"error": "already_activated"}

    pay_url = create_invoice(ACTIVATION_PRICE, f"activate:{uid}")
    if isinstance(pay_url, dict) and pay_url.get("error"):
        return pay_url

    return {"pay_url": pay_url}


# =========================
# WITHDRAW
# =========================
@app.post("/withdraw")
def withdraw(data: dict, db: Session = Depends(get_db)):
    uid = data.get("user_id")
    if not uid:
        return {"error": "user_id missing"}

    try:
        uid = int(uid)
    except Exception:
        return {"error": "invalid user_id"}

    user = db.query(User).get(uid)
    if not user:
        return {"error": "user_not_found"}

    if float(user.balance or 0) < MIN_WITHDRAW_BALANCE:
        return {"error": "min_withdraw_10"}

    if not user.activated:
        return {"error": "activation_required"}

    address = (data.get("address") or "").strip()
    if not address:
        return {"error": "address missing"}

    memo = (data.get("memo") or "").strip()

    w = WithdrawRequest(
        user_id=user.id,
        address=address,
        memo=memo,
        amount=float(user.balance or 0),
        status="pending"
    )
    db.add(w)
    db.commit()
    db.refresh(w)

    send_admin(
        f"💸 Withdraw request\n"
        f"User: {user.id}\n"
        f"Address: {w.address}\n"
        f"Memo: {w.memo if w.memo else '-'}\n"
        f"Amount: {w.amount} TON\n"
        f"Request ID: {w.id}"
    )

    return {"ok": True}


# =========================
# STATS
# =========================
@app.post("/stats")
def stats(data: dict, db: Session = Depends(get_db)):
    uid = data.get("user_id")
    if not uid:
        return {"visits": 0, "level1": 0, "level2": 0, "earned": 0}

    try:
        uid = int(uid)
    except Exception:
        return {"visits": 0, "level1": 0, "level2": 0, "earned": 0}

    level1 = db.query(User).filter(User.referrer_id == uid).all()
    level1_count = len(level1)

    level2_count = 0
    for u in level1:
        refs = db.query(User).filter(User.referrer_id == u.id).all()
        level2_count += len(refs)

    visits = level1_count

    user = db.query(User).get(uid)
    earned = round(float(user.balance or 0), 4) if user else 0

    return {
        "visits": visits,
        "level1": level1_count,
        "level2": level2_count,
        "earned": earned
    }


# =========================
# ADS
# =========================
@app.post("/ad")
def ad(data: dict):
    amount = data.get("amount")
    uid = data.get("user_id")
    link = data.get("link")

    if amount is None or uid is None or not link:
        return {"error": "amount/user_id/link missing"}

    payload = f"ad:{amount}:{uid}:{link}"
    pay_url = create_invoice(amount, payload)
    if isinstance(pay_url, dict) and pay_url.get("error"):
        return pay_url

    return {"pay_url": pay_url}


# =========================
# CRYPTOPAY WEBHOOK
# =========================
@app.post("/webhook/cryptopay")
async def webhook(request: Request):
    data = await request.json()
    print("CRYPTOPAY EVENT:", data)

    payload = ""
    status = ""

    if isinstance(data, dict):
        invoice = data.get("invoice", {})

        if isinstance(invoice, dict):
            payload = invoice.get("payload", "") or ""
            status = invoice.get("status", "") or ""

        if not payload and isinstance(data.get("payload"), str):
            payload = data.get("payload") or ""

        if not status and isinstance(data.get("status"), str):
            status = data.get("status") or ""

    print("CRYPTOPAY PAYLOAD:", payload)
    print("CRYPTOPAY STATUS:", status)

    # принимаем только реально оплаченные счета
    if status not in ["paid", "confirmed", "completed"]:
        return {"ok": True}

    db = SessionLocal()
    try:
        if isinstance(payload, str) and payload.startswith("activate:"):
            uid = int(payload.split(":", 1)[1])

            user = db.query(User).get(uid)
            if user and not user.activated:
                user.activated = True
                db.commit()

                send_admin(f"✅ Activation paid\nUser: {uid}\nAmount: {ACTIVATION_PRICE} TON")

        elif isinstance(payload, str) and payload.startswith("ad:"):
            _, amount, uid, link = payload.split(":", 3)
            send_admin(f"💰 Ad paid\nUser {uid}\n{amount} TON\n{link}")

        return {"ok": True}
    finally:
        db.close()
