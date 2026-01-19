from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from database import SessionLocal, engine
from models import Base, User, WithdrawRequest
import requests

CRYPTO_PAY_TOKEN = "500297:AAIVkVz3FZ2rD5UfSmiAUk5NClQEEpZPwMw"
CRYPTO_PAY_API = "https://pay.crypt.bot/api"
WEBHOOK_SECRET = "friendportal_secret_123"

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
        json={"chat_id": ADMIN_TG_ID, "text": text, "parse_mode": "HTML"}
    )

def create_invoice(amount: int, payload: str):
    r = requests.post(
        f"{CRYPTO_PAY_API}/createInvoice",
        headers={"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN},
        json={"asset": "TON", "amount": amount, "payload": payload}
    )
    return r.json()["result"]["pay_url"]

@app.post("/pay")
def pay(data: dict):
    user_id = data["user_id"]
    d = db()
    user = d.query(User).get(user_id)
    if not user:
        user = User(id=user_id)
        d.add(user)
        d.commit()
    return {"pay_url": create_invoice(1, f"activate:{user_id}")}

@app.post("/withdraw")
def withdraw(data: dict):
    d = db()
    user = d.query(User).get(data["user_id"])
    if not user or not user.activated:
        return {"error": "not_activated"}

    w = WithdrawRequest(
        user_id=user.id,
        address=data["address"],
        memo=data.get("memo","")
    )
    d.add(w)
    d.commit()

    send_admin(
        f"💸 Withdraw request\n"
        f"User: {user.id}\n"
        f"Address: {w.address}\n"
        f"Memo: {w.memo}"
    )
    return {"status": "ok"}

@app.post("/force_activate")
def force_activate(data: dict):
    d = db()
    user = d.query(User).get(data["user_id"])
    if user:
        user.activated = True
        d.commit()
    return {"ok": True}


@app.post("/balance")
def balance(data: dict):
    d = db()
    uid = data["user_id"]
    ref_id = data.get("ref_id")

    user = d.query(User).get(uid)

    if not user:
        user = User(id=uid)
        d.add(user)
        d.commit()
        d.refresh(user)

        # 👇 начисление 0.05 TON за первый переход
        if ref_id:
            user.balance_locked += 0.05
            user.visit_reward_given = True
            d.commit()

    return {
        "balance": user.balance,
        "activated": user.activated
    }

@app.post("/stats")
def stats(data: dict):
    return {"level1": 0, "level2": 0, "earned": 0}

@app.post("/ad")
def ad(data: dict):
    payload = f"ad:{data['amount']}:{data['user_id']}:{data['link']}"
    return {"pay_url": create_invoice(data["amount"], payload)}

@app.post("/webhook/cryptopay")
async def webhook(request: Request):
    data = await request.json()

    payload = data.get("payload",{}).get("payload","")
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
        _, amount, uid, link = payload.split(":",3)
        send_admin(f"📣 Ad paid\nUser: {uid}\nAmount: {amount} TON\n{link}")
    return {"ok": True}


