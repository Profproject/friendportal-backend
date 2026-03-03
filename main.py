from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import requests

from database import SessionLocal, engine
from models import Base, User, WithdrawRequest

# =========================
# CONFIG (лучше вынести в ENV)
# =========================
CRYPTO_PAY_TOKEN = "500297:AAIVkVz3FZ2rD5UfSmiAUk5NClQEEpZPwMw"
CRYPTO_PAY_API = "https://pay.crypt.bot/api"

BOT_TOKEN = "8516580775:AAGal4FIUfn-Y822L0YX_LAi6pyBjUIIDT4"
ADMIN_TG_ID = 8445167015

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
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": ADMIN_TG_ID, "text": text},
        timeout=20
    )


def create_invoice(amount: float, payload: str):
    r = requests.post(
        f"{CRYPTO_PAY_API}/createInvoice",
        headers={"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN},
        json={"asset": "TON", "amount": amount, "payload": payload},
        timeout=20
    )
    data = r.json()
    # если криптопэй вернул ошибку — покажем её
    if "result" not in data or not data["result"]:
        return {"error": data}
    return data["result"]["pay_url"]


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

    ref_id = data.get("ref_id")

    user = db.query(User).get(uid)

    if not user:
        user = User(
            id=uid,
            referrer_id=ref_id,
            balance=0,
            activated=False
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # бонус за первый переход (если ref_id есть)
        if ref_id:
            user.balance += 0.05
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

    user = db.query(User).get(uid)
    if not user:
        user = User(id=uid, balance=0, activated=False)
        db.add(user)
        db.commit()

    pay_url = create_invoice(1, f"activate:{uid}")
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

    user = db.query(User).get(uid)
    if not user or not user.activated:
        return {"error": "not_activated"}

    address = data.get("address")
    if not address:
        return {"error": "address missing"}

    w = WithdrawRequest(
        user_id=user.id,
        address=address,
        memo=data.get("memo", "")
    )
    db.add(w)
    db.commit()

    send_admin(f"💸 Withdraw\nUser {user.id}\n{w.address}")
    return {"ok": True}


# =========================
# STATS
# =========================
@app.post("/stats")
def stats(data: dict, db: Session = Depends(get_db)):
    uid = data.get("user_id")
    if not uid:
        return {"visits": 0, "level1": 0, "level2": 0, "earned": 0}

    # прямые рефералы
    level1 = db.query(User).filter(User.referrer_id == uid).all()
    level1_activated = [u for u in level1 if u.activated]

    # второй уровень
    level2_activated = []
    for u in level1:
        refs = db.query(User).filter(User.referrer_id == u.id).all()
        level2_activated.extend([r for r in refs if r.activated])

    visits = db.query(User).filter(User.referrer_id == uid).count()

    user = db.query(User).get(uid)
    earned = round(float(user.balance or 0), 4) if user else 0

    return {
        "visits": visits,
        "level1": len(level1_activated),
        "level2": len(level2_activated),
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

    # В разных событиях payload может лежать по-разному
    payload = ""
    if isinstance(data, dict):
        if isinstance(data.get("payload"), str):
            payload = data.get("payload") or ""
        elif isinstance(data.get("payload"), dict):
            payload = data["payload"].get("payload", "") or ""
        elif isinstance(data.get("invoice"), dict):
            payload = data["invoice"].get("payload", "") or ""

    print("CRYPTOPAY EVENT:", data)
    print("CRYPTOPAY PAYLOAD:", payload)

    db = SessionLocal()
    try:
        if isinstance(payload, str) and payload.startswith("activate:"):
            uid = int(payload.split(":", 1)[1])

            user = db.query(User).get(uid)
            if user and not user.activated:
                user.activated = True

                # начисления рефералам
                if user.referrer_id:
                    ref1 = db.query(User).get(user.referrer_id)
                    if ref1:
                        ref1.balance = float(ref1.balance or 0) + 0.5

                        if ref1.referrer_id:
                            ref2 = db.query(User).get(ref1.referrer_id)
                            if ref2:
                                ref2.balance = float(ref2.balance or 0) + 0.25

                db.commit()

        elif isinstance(payload, str) and payload.startswith("ad:"):
            # ad:amount:uid:link
            _, amount, uid, link = payload.split(":", 3)
            send_admin(f"💰 Ad paid\nUser {uid}\n{amount} TON\n{link}")

        return {"ok": True}
    finally:
        db.close()
