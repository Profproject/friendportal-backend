from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from database import SessionLocal, engine
from models import Base, User, WithdrawRequest
import requests

CRYPTO_PAY_TOKEN = "500297:AAIVkVz3FZ2rD5UfSmiAUk5NClQEEpZPwMw"
CRYPTO_PAY_API = "https://pay.crypt.bot/api"

BOT_TOKEN = "8516580775:AAGal4FIUfn-Y822L0YX_LAi6pyBjUIIDT4"
ADMIN_TG_ID = 8445167015

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

def db():
    return SessionLocal()

def send_admin(text: str):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": ADMIN_TG_ID, "text": text}
    )

def create_invoice(amount: int, payload: str):
    r = requests.post(
        f"{CRYPTO_PAY_API}/createInvoice",
        headers={"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN},
        json={"asset": "TON", "amount": amount, "payload": payload}
    )
    return r.json()["result"]["pay_url"]

# =========================
# BALANCE + REF VISIT
# =========================
@app.post("/balance")
def balance(data: dict):
    d = db()
    uid = data["user_id"]
    ref_id = data.get("ref_id")

    user = d.query(User).get(uid)

    if not user:
        user = User(
            id=uid,
            referrer_id=ref_id,
            balance=0,
            balance_locked=0,
            visit_reward_given=False,
            activated=False
        )
        d.add(user)
        d.commit()
        d.refresh(user)

        # 🔹 0.05 TON за первый переход
        if ref_id:
            user.balance_locked += 0.05
            user.visit_reward_given = True
            d.commit()

    total = round(user.balance + user.balance_locked, 4)

    return {
        "balance": total,
        "available": round(user.balance, 4),
        "locked": round(user.balance_locked, 4),
        "activated": user.activated
    }

# =========================
# PAY / ACTIVATE
# =========================
@app.post("/pay")
def pay(data: dict):
    uid = data["user_id"]
    d = db()
    user = d.query(User).get(uid)
    if not user:
        user = User(id=uid)
        d.add(user)
        d.commit()
    return {"pay_url": create_invoice(1, f"activate:{uid}")}

# =========================
# WITHDRAW
# =========================
@app.post("/withdraw")
def withdraw(data: dict):
    d = db()
    user = d.query(User).get(data["user_id"])
    if not user or not user.activated:
        return {"error": "not_activated"}

    w = WithdrawRequest(
        user_id=user.id,
        address=data["address"],
        memo=data.get("memo", "")
    )
    d.add(w)
    d.commit()

    send_admin(f"💸 Withdraw\nUser {user.id}\n{w.address}")
    return {"ok": True}

# =========================
# STATS (РЕАЛЬНЫЕ)
# =========================
@app.post("/stats")
def stats(data: dict):
    d = db()
    uid = data["user_id"]

    # прямые рефералы
    level1_users = d.query(User).filter(User.referrer_id == uid).all()
    level1_activated = [u for u in level1_users if u.activated]

    # второй уровень
    level2_activated = []
    for u in level1_users:
        refs = d.query(User).filter(User.referrer_id == u.id).all()
        level2_activated.extend([r for r in refs if r.activated])

    # переходы по ссылке
    visits = d.query(User).filter(
        User.referrer_id == uid,
        User.visit_reward_given == True
    ).count()

    user = d.query(User).get(uid)
    earned = round(user.balance + user.balance_locked, 4) if user else 0

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
    payload = f"ad:{data['amount']}:{data['user_id']}:{data['link']}"
    return {"pay_url": create_invoice(data["amount"], payload)}

# =========================
# CRYPTOPAY WEBHOOK
# =========================
@app.post("/webhook/cryptopay")
async def webhook(request: Request):
    data = await request.json()
    payload = data.get("payload", {}).get("payload", "")

    if payload.startswith("activate:"):
        uid = int(payload.split(":")[1])
        d = db()
        user = d.query(User).get(uid)
        if user and not user.activated:
            user.balance += user.balance_locked
            user.balance_locked = 0
            user.activated = True
            d.commit()

    if payload.startswith("ad:"):
        _, amount, uid, link = payload.split(":", 3)
        send_admin(f"📣 Ad paid\nUser {uid}\n{amount} TON\n{link}")

    return {"ok": True}
