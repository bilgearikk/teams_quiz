# server.py
import time
import random
import asyncio
import uuid
from typing import List, Dict, Any
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import socketio

# --- Socket.IO + FastAPI (ASGI) ---
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
fastapi_app = FastAPI()
app = socketio.ASGIApp(sio, fastapi_app)

# Static index.html
fastapi_app.mount("/", StaticFiles(directory="static", html=True), name="static")

# =========================================================
# Kahoot tarzı oyun durumu (in-memory)
# =========================================================
TOTAL_QUESTIONS = 10  # oyunda sorulacak soru sayısı (varsa daha fazlası da seed'li)

QUESTIONS = [
    {
        "id": "q1",
        "text": "SAP'nin açılımı nedir?",
        "choices": ["System Application and Products", "Software and Process", "Services and Automated Processes", "Strategic and Planning"],
        "correct_index": 0
    },
    {
        "id": "q2",
        "text": "Aşağıdakilerden hangisi SAP'nin temel ERP modüllerinden biri DEĞİLDİR?",
        "choices": ["FI (Finansal Muhasebe)", "CO (Maliyet Muhasebesi)", "SD (Satış ve Dağıtım)", "HRM (İnsan Kaynakları Yönetimi)"],
        "correct_index": 3
    },
    {
        "id": "q3",
        "text": "SAP'de 'Master Data' (Ana Veri) ne anlama gelir?",
        "choices": ["Sadece bir kez girilen ve sık sık değişmeyen verilerdir (örn: müşteri, malzeme).", "Günlük finansal hareketleri içeren verilerdir.", "Sistem ayarlarını ve konfigürasyonlarını içeren verilerdir.", "Sadece raporlama için kullanılan verilerdir."],
        "correct_index": 0
    },
    {
        "id": "q4",
        "text": "SAP'de bir kullanıcıya erişim yetkisi vermek için hangi nesne kullanılır?",
        "choices": ["Profil", "Role", "Transaksiyon Kodu", "Rapor"],
        "correct_index": 1
    },
    {
        "id": "q5",
        "text": "SAP'de bir işlemin kısa yolu olan ve harf ile rakamlardan oluşan koda ne denir?",
        "choices": ["Transaksiyon Kodu", "Modül Kodu", "İşlem Kodu", "Sistem Kodu"],
        "correct_index": 0
    },
    {
        "id": "q6",
        "text": "SAP'nin standart programlama dili hangisidir?",
        "choices": ["Java", "C++", "ABAP", "Python"],
        "correct_index": 2
    },
    {
        "id": "q7",
        "text": "SAP'de 'ERP' ne anlama gelir?",
        "choices": ["Enterprise Resource Planning", "Employee Recruitment Platform", "Electronic Reporting and Processing", "Effective Resource Production"],
        "correct_index": 0
    },
    {
        "id": "q8",
        "text": "SAP sistemlerinde kullanılan veri tabanları arasında hangisi en yaygın olanıdır?",
        "choices": ["SQL Server", "Oracle", "HANA", "MySQL"],
        "correct_index": 2
    },
    {
        "id": "q9",
        "text": "Aşağıdakilerden hangisi, bir şirketin finansal verilerini yöneten SAP modülüdür?",
        "choices": ["MM (Malzeme Yönetimi)", "SD (Satış ve Dağıtım)", "PP (Üretim Planlama)", "FI (Finansal Muhasebe)"],
        "correct_index": 3
    },
    {
        "id": "q10",
        "text": "SAP S/4HANA, 'S' ve '4' ne anlama gelir?",
        "choices": ["Simple ve 4. versiyon", "Sales ve 4 modül", "Standard ve 4 bileşen", "Secure ve 4 platform"],
        "correct_index": 0
    },
    {
        "id": "q11",
        "text": "SAP danışmanlığı hangi alanda uzmanlaşmış danışmanlık türüdür?",
        "choices": ["İnsan kaynakları", "Finansal hizmetler", "Kurumsal kaynak planlaması", "Pazarlama ve satış"],
        "correct_index": 2
    },
    {
        "id": "q12",
        "text": "SAP'deki 'MM' modülü ne işe yarar?",
        "choices": ["Müşteri ilişkilerini yönetir.", "Üretim süreçlerini yönetir.", "Malzeme tedarik ve envanter süreçlerini yönetir.", "İnsan kaynakları süreçlerini yönetir."],
        "correct_index": 2
    },
    {
        "id": "q13",
        "text": "SAP'de en üst seviye organizasyonel birim nedir?",
        "choices": ["Şirket Kodu", "Müşteri (Client)", "Maliyet Merkezi", "Organizasyon Birimi"],
        "correct_index": 1
    },
    {
        "id": "q14",
        "text": "FI ve CO modüllerinin temel ilişkisi nedir?",
        "choices": ["FI, sadece CO'nun verilerini kaydeder.", "CO, sadece FI'ın verilerini kaydeder.", "FI dışa dönük, CO içe dönük raporlama yapar.", "Her ikisi de aynı amaca hizmet eder."],
        "correct_index": 2
    },
    {
        "id": "q15",
        "text": "R/3'te 'R' ve '3' ne anlama gelir?",
        "choices": ["Raporlama ve 3 modül", "Rasyonel ve 3 platform", "Gerçek zamanlı ve 3 katmanlı mimari", "Rakam ve 3 versiyon"],
        "correct_index": 2
    },
    {
        "id": "q16",
        "text": "SAP sisteminin grafik arayüzü?",
        "choices": ["SAP Fiori", "SAP Web Dynpro", "SAP GUI", "SAP NetWeaver"],
        "correct_index": 2
    },
    {
        "id": "q17",
        "text": "Şirket ihtiyaçlarına göre yapılan ayarlar?",
        "choices": ["Geliştirme (Development)", "Test", "Raporlama", "Özelleştirme (Customizing)"],
        "correct_index": 3
    }
]

meetings: Dict[str, Dict[str, Any]] = {}
sid_map: Dict[str, tuple] = {}  # sid -> (meeting_id, participant_id)

def ensure_meeting(mid: str):
    if mid not in meetings:
        # Soru sırasını karışık başlat (istenirse sabit)
        order = list(range(len(QUESTIONS)))
        random.shuffle(order)
        meetings[mid] = {
            "participants": {},          # pid -> {name, score, sid}
            "questions": [QUESTIONS[i] for i in order],
            "question_ptr": 0,           # sıradaki soru index'i
            "current_round": None,       # aktif round bilgisi
            "game_started": False,       # oyun başladı mı
            "asked_count": 0             # sorulan soru sayısı
        }

def calc_points(elapsed: float, correct: bool) -> int:
    if not correct:
        return 0
    if elapsed <= 3:
        return 5
    if elapsed <= 7:
        return 3
    if elapsed <= 10:
        return 2
    return 0

async def broadcast_participants(mid: str):
    m = meetings[mid]
    lst = [{"id": pid, "name": p["name"], "score": p["score"], "is_moderator": p.get("is_moderator", False)}
           for pid, p in m["participants"].items()]
    await sio.emit("participants_update", lst, room=mid)

async def broadcast_leaderboard(mid: str):
    m = meetings[mid]
    board = sorted(
        [{"id": pid, "name": p["name"], "score": p["score"]} for pid, p in m["participants"].items()],
        key=lambda x: -x["score"]
    )
    await sio.emit("leaderboard", board, room=mid)

async def maybe_autostart(mid: str):
    """3+ kişi varsa ve oyun başlamadıysa otomatik başlat."""
    m = meetings[mid]
    if not m["game_started"] and len(m["participants"]) >= 3 and len(m["questions"]) > 0:
        m["game_started"] = True
        m["asked_count"] = 0
        m["question_ptr"] = 0
        await start_round(mid)

async def start_round(mid: str):
    m = meetings[mid]
    # Oyun bitti mi?
    if m["asked_count"] >= min(TOTAL_QUESTIONS, len(m["questions"])):
        await end_game(mid)
        return

    q = m["questions"][m["question_ptr"] % len(m["questions"])]
    m["question_ptr"] += 1
    m["asked_count"] += 1

    rid = str(uuid.uuid4())
    m["current_round"] = {
        "round_id": rid,
        "question": q,
        "start_time": time.time(),
        "answers": {},         # pid -> {selected, elapsed, correct, points}
        "done": False,
    }

    await sio.emit("start_round", {
        "round_id": rid,
        "question": {"id": q["id"], "text": q["text"], "choices": q["choices"]}
    }, room=mid)

    # 10 sn sonra otomatik bitir
    async def timeout():
        await asyncio.sleep(10)
        cr = m.get("current_round")
        if cr and cr["round_id"] == rid and not cr["done"]:
            await finish_round(mid)
    asyncio.create_task(timeout())

async def finish_round(mid: str):
    m = meetings[mid]
    cr = m.get("current_round")
    if not cr or cr["done"]:
        return
    cr["done"] = True

    # Round sonucu: doğru şık ve puanlar zaten işlendi
    await sio.emit("round_result", {
        "round_id": cr["round_id"],
        "correct_index": cr["question"]["correct_index"]
    }, room=mid)

    await broadcast_leaderboard(mid)

    # Kısa bekleme, sonra bir sonraki soru
    await asyncio.sleep(1.5)
    await start_round(mid)

async def end_game(mid: str):
    m = meetings[mid]
    # Kazanan(lar)ı bul
    if not m["participants"]:
        winner_str = "Katılımcı yok"
    else:
        max_score = max(p["score"] for p in m["participants"].values()) if m["participants"] else 0
        winners = [p["name"] for p in m["participants"].values() if p["score"] == max_score]
        winner_str = ", ".join(winners) if winners else "—"
    await sio.emit("game_over", {"winner": winner_str}, room=mid)

    # oyunu yeni tura hazırlayalım (skorları sıfırlamayalım, istenirse sıfırlanır)
    m["game_started"] = False
    m["current_round"] = None
    m["asked_count"] = 0
    m["question_ptr"] = 0

# =========================================================
# Socket.IO eventleri
# =========================================================
@sio.event
async def connect(sid, environ):
    print("connect", sid)

@sio.event
async def disconnect(sid):
    info = sid_map.pop(sid, None)
    if not info:
        return
    mid, pid = info
    m = meetings.get(mid)
    if not m:
        return
    if pid in m["participants"]:
        del m["participants"][pid]
    await broadcast_participants(mid)
    print("disconnect", sid)

@sio.on("join")
async def on_join(sid, data):
    """
    data: {meeting_id?: str, name: str, is_moderator?: bool}
    """
    mid = data.get("meeting_id") or "demo-room"
    name = (data.get("name") or "Anon").strip()
    is_mod = bool(data.get("is_moderator"))

    ensure_meeting(mid)

    pid = str(uuid.uuid4())
    meetings[mid]["participants"][pid] = {
        "name": name or "Anon",
        "sid": sid,
        "score": 0,
        "is_moderator": is_mod
    }
    sid_map[sid] = (mid, pid)
    await sio.enter_room(sid, mid)
    await sio.emit("joined", {"participant_id": pid, "meeting_id": mid}, to=sid)

    await broadcast_participants(mid)
    await broadcast_leaderboard(mid)
    await maybe_autostart(mid)

@sio.on("start_round")
async def on_start_round(sid, data):
    """İstersen moderatör manuel de başlatabilir."""
    info = sid_map.get(sid)
    if not info:
        return
    mid, pid = info
    ensure_meeting(mid)
    m = meetings[mid]
    # sadece moderatör kontrolü (istersen kaldır)
    if not m["participants"].get(pid, {}).get("is_moderator"):
        await sio.emit("error_msg", {"msg": "Sadece moderatör soru başlatabilir."}, to=sid)
        return
    if not m["questions"]:
        await sio.emit("error_msg", {"msg": "Soru seti boş."}, to=sid)
        return
    if not m["game_started"]:
        m["game_started"] = True
    await start_round(mid)

@sio.on("answer")
async def on_answer(sid, data):
    """
    data: {round_id: str, selected_index: int}
    """
    info = sid_map.get(sid)
    if not info:
        return
    mid, pid = info
    m = meetings.get(mid)
    if not m:
        return
    cr = m.get("current_round")
    if not cr or cr["round_id"] != data.get("round_id"):
        return
    if cr["done"]:
        return
    # Aynı oyuncu ikinci kere cevaplamasın
    if pid in cr["answers"]:
        return

    elapsed = time.time() - cr["start_time"]
    selected = int(data.get("selected_index"))
    correct = (selected == cr["question"]["correct_index"])
    points = calc_points(elapsed, correct)

    cr["answers"][pid] = {
        "selected": selected,
        "elapsed": elapsed,
        "correct": correct,
        "points": points
    }

    # puanı hemen ekle
    if points > 0:
        m["participants"][pid]["score"] += points

    await sio.emit("player_answered", {
        "player_id": pid,
        "correct": correct,
        "points": points,
        "elapsed": elapsed
    }, room=mid)

    # herkes cevapladıysa turu erkenden bitir
    active_players = len(m["participants"])
    if len(cr["answers"]) >= active_players:
        await finish_round(mid)
