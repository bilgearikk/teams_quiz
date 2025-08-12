# server.py
import time
import random
import asyncio
import uuid
from typing import List
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import socketio

# --- Socket.IO async server ---
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
fastapi_app = FastAPI()
app = socketio.ASGIApp(sio, fastapi_app)

# serve static files (index.html)
fastapi_app.mount("/", StaticFiles(directory="static", html=True), name="static")

# --- In-memory storage (prototype) ---
meetings = {}  # meeting_id -> {participants: {pid: {...}}, questions: [...], current_round: {...}}

def ensure_meeting(mid: str):
    if mid not in meetings:
        meetings[mid] = {"participants": {}, "questions": [], "current_round": None}

class QuestionIn(BaseModel):
    text: str
    choices: List[str]
    correct_index: int

# API to add question (useful for admin or curl)
@fastapi_app.post("/meetings/{meeting_id}/questions")
async def add_question(meeting_id: str, q: QuestionIn):
    ensure_meeting(meeting_id)
    qid = str(uuid.uuid4())
    meetings[meeting_id]["questions"].append({
        "id": qid,
        "text": q.text,
        "choices": q.choices,
        "correct_index": q.correct_index
    })
    return {"ok": True, "id": qid}

# helper: broadcast participants
async def broadcast_participants(meeting_id: str):
    m = meetings[meeting_id]
    lst = [{"id": pid, "name": p["name"], "score": p["score"], "is_moderator": p.get("is_moderator", False)} for pid,p in m["participants"].items()]
    await sio.emit("participants_update", lst, room=meeting_id)

async def broadcast_leaderboard(meeting_id: str):
    m = meetings[meeting_id]
    leaderboard = sorted([{"id": pid, "name": p["name"], "score": p["score"]} for pid,p in m["participants"].items()], key=lambda x: -x["score"])
    await sio.emit("leaderboard", leaderboard, room=meeting_id)

# sid -> (meeting_id, participant_id)
sid_map = {}

@sio.event
async def connect(sid, environ):
    print("connect", sid)

@sio.event
async def disconnect(sid):
    info = sid_map.get(sid)
    if not info:
        return
    meeting_id, pid = info
    m = meetings.get(meeting_id)
    if m and pid in m["participants"]:
        del m["participants"][pid]
        await broadcast_participants(meeting_id)
    sid_map.pop(sid, None)
    print("disconnect", sid)

@sio.on("join")
async def on_join(sid, data):
    """
    data: {meeting_id: str, name: str, is_moderator: bool}
    """
    meeting_id = data.get("meeting_id") or "demo-room"
    name = data.get("name") or "Anon"
    is_mod = bool(data.get("is_moderator"))
    ensure_meeting(meeting_id)
    pid = str(uuid.uuid4())
    meetings[meeting_id]["participants"][pid] = {"name": name, "sid": sid, "score": 0, "is_moderator": is_mod}
    sid_map[sid] = (meeting_id, pid)
    await sio.enter_room(sid, meeting_id)
    await sio.emit("joined", {"participant_id": pid, "meeting_id": meeting_id}, to=sid)
    await broadcast_participants(meeting_id)
    print(f"{name} joined {meeting_id} as {pid}")

def calculate_points(elapsed_seconds: float, correct: bool) -> int:
    if not correct:
        return 0
    if elapsed_seconds <= 5:
        return 5
    if elapsed_seconds <= 10:
        return 3
    if elapsed_seconds <= 15:
        return 1
    return 0

@sio.on("start_round")
async def on_start_round(sid, data):
    """
    data: {meeting_id: str}
    only moderator should call this ideally (we check)
    """
    info = sid_map.get(sid)
    if not info:
        return
    meeting_id, pid = info
    m = meetings.get(meeting_id)
    if not m:
        return
    # check moderator
    if not m["participants"].get(pid, {}).get("is_moderator"):
        await sio.emit("error_msg", {"msg": "Sadece moderator round başlatabilir."}, to=sid)
        return
    if not m["questions"]:
        await sio.emit("error_msg", {"msg": "Toplantıda soru yok."}, to=sid)
        return

    question = random.choice(m["questions"])
    assigned_pid = random.choice(list(m["participants"].keys()))
    round_id = str(uuid.uuid4())
    start_time = time.time()
    m["current_round"] = {
        "round_id": round_id,
        "question": question,
        "assigned_pid": assigned_pid,
        "start_time": start_time,
        "answered": False
    }
    await sio.emit("start_round", {
        "round_id": round_id,
        "question": {"id": question["id"], "text": question["text"], "choices": question["choices"]},
        "assigned_pid": assigned_pid,
        "start_time": start_time
    }, room=meeting_id)

    # timeout
    async def round_timeout_checker(mid, rid):
        await asyncio.sleep(15)
        m2 = meetings.get(mid)
        if not m2:
            return
        cr = m2.get("current_round")
        if not cr or cr.get("round_id") != rid:
            return
        if not cr.get("answered"):
            cr["answered"] = True
            await sio.emit("round_result", {"round_id": rid, "correct": False, "points_awarded": 0, "elapsed": None, "by": None}, room=mid)
            await broadcast_leaderboard(mid)

    asyncio.create_task(round_timeout_checker(meeting_id, round_id))

@sio.on("answer")
async def on_answer(sid, data):
    """
    data: {round_id: str, selected_index: int}
    """
    info = sid_map.get(sid)
    if not info:
        return
    meeting_id, pid = info
    m = meetings.get(meeting_id)
    if not m:
        return
    cr = m.get("current_round")
    if not cr or cr.get("round_id") != data.get("round_id"):
        await sio.emit("error_msg", {"msg": "Aktif round yok veya yanlış round_id"}, to=sid)
        return
    if pid != cr["assigned_pid"]:
        await sio.emit("error_msg", {"msg": "Bu round için sana cevap yetkisi yok."}, to=sid)
        return
    if cr.get("answered"):
        await sio.emit("error_msg", {"msg": "Round zaten cevaplandı."}, to=sid)
        return

    elapsed = time.time() - cr["start_time"]
    correct = (data.get("selected_index") == cr["question"]["correct_index"])
    points = calculate_points(elapsed, correct)

    cr["answered"] = True
    cr["answered_by"] = pid
    cr["answered_correct"] = correct
    cr["elapsed"] = elapsed

    if correct:
        m["participants"][pid]["score"] += points

    await sio.emit("round_result", {
        "round_id": cr["round_id"],
        "correct": correct,
        "points_awarded": points,
        "elapsed": elapsed,
        "by": pid,
        "correct_index": cr["question"]["correct_index"]
    }, room=meeting_id)

    await broadcast_leaderboard(meeting_id)
