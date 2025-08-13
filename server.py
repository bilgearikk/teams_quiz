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

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
fastapi_app = FastAPI()
app = socketio.ASGIApp(sio, fastapi_app)

fastapi_app.mount("/", StaticFiles(directory="static", html=True), name="static")

# --- In-memory storage ---
meetings = {}  # meeting_id -> {participants, questions, current_round, asked_questions}

def ensure_meeting(mid: str):
    if mid not in meetings:
        meetings[mid] = {"participants": {}, "questions": [], "asked_questions": [], "current_round": None}

class QuestionIn(BaseModel):
    text: str
    choices: List[str]
    correct_index: int

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

async def broadcast_participants(meeting_id: str):
    m = meetings[meeting_id]
    lst = [{"id": pid, "name": p["name"], "score": p["score"], "is_moderator": p.get("is_moderator", False)}
           for pid, p in m["participants"].items()]
    await sio.emit("participants_update", lst, room=meeting_id)

async def broadcast_leaderboard(meeting_id: str):
    m = meetings[meeting_id]
    leaderboard = sorted(
        [{"id": pid, "name": p["name"], "score": p["score"]}
         for pid, p in m["participants"].items()],
        key=lambda x: -x["score"]
    )
    await sio.emit("leaderboard", leaderboard, room=meeting_id)

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
    meeting_id = data.get("meeting_id") or "demo-room"
    name = data.get("name") or "Anon"
    is_mod = bool(data.get("is_moderator"))
    ensure_meeting(meeting_id)
    pid = str(uuid.uuid4())
    meetings[meeting_id]["participants"][pid] = {
        "name": name,
        "sid": sid,
        "score": 0,
        "is_moderator": is_mod
    }
    sid_map[sid] = (meeting_id, pid)
    await sio.enter_room(sid, meeting_id)
    await sio.emit("joined", {"participant_id": pid, "meeting_id": meeting_id}, to=sid)
    await broadcast_participants(meeting_id)
    print(f"{name} joined {meeting_id} as {pid}")

def calculate_points(elapsed_seconds: float, correct: bool) -> int:
    if not correct:
        return 0
    if elapsed_seconds <= 3:
        return 5
    if elapsed_seconds <= 7:
        return 3
    if elapsed_seconds <= 10:
        return 2
    return 0

@sio.on("start_round")
async def on_start_round(sid, data):
    info = sid_map.get(sid)
    if not info:
        return
    meeting_id, pid = info
    m = meetings.get(meeting_id)
    if not m:
        return

    if not m["participants"].get(pid, {}).get("is_moderator"):
        await sio.emit("error_msg", {"msg": "Sadece moderator round başlatabilir."}, to=sid)
        return

    if m["current_round"]:
        await sio.emit("error_msg", {"msg": "Devam eden soru var."}, to=sid)
        return

    available_questions = [q for q in m["questions"] if q["id"] not in m["asked_questions"]]
    if not available_questions:
    
        leaderboard = sorted(m["participants"].values(), key=lambda x: -x["score"])
        winner_name = leaderboard[0]["name"] if leaderboard else "Yok"
        await sio.emit("game_over", {"winner": winner_name}, room=meeting_id)
        return

    question = random.choice(available_questions)
    m["asked_questions"].append(question["id"])

    round_id = str(uuid.uuid4())
    start_time = time.time()
    m["current_round"] = {
        "round_id": round_id,
        "question": question,
        "start_time": start_time,
        "answered_players": set()
    }

    await sio.emit("start_round", {
        "round_id": round_id,
        "question": {
            "id": question["id"],
            "text": question["text"],
            "choices": question["choices"]
        },
        "start_time": start_time
    }, room=meeting_id)


    async def round_timeout_checker(mid, rid):
        await asyncio.sleep(10)
        m2 = meetings.get(mid)
        if not m2 or not m2.get("current_round") or m2["current_round"]["round_id"] != rid:
            return

        await sio.emit("round_result", {
            "round_id": rid,
            "correct_index": m2["current_round"]["question"]["correct_index"]
        }, room=mid)
        m2["current_round"] = None
        await broadcast_leaderboard(mid)

    asyncio.create_task(round_timeout_checker(meeting_id, round_id))

@sio.on("answer")
async def on_answer(sid, data):
    info = sid_map.get(sid)
    if not info:
        return
    meeting_id, pid = info
    m = meetings.get(meeting_id)
    if not m:
        return
    cr = m.get("current_round")
    if not cr or cr["round_id"] != data.get("round_id"):
        await sio.emit("error_msg", {"msg": "Geçersiz round."}, to=sid)
        return
    if pid in cr["answered_players"]:
        await sio.emit("error_msg", {"msg": "Bu round için zaten cevap verdin."}, to=sid)
        return

    elapsed = time.time() - cr["start_time"]
    correct = (data.get("selected_index") == cr["question"]["correct_index"])
    points = calculate_points(elapsed, correct)

    cr["answered_players"].add(pid)
    if correct:
        m["participants"][pid]["score"] += points

    await sio.emit("player_answered", {
        "player_id": pid,
        "correct": correct,
        "points": points,
        "elapsed": elapsed
    }, room=meeting_id)

    await broadcast_leaderboard(meeting_id)
