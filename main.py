from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import random
import asyncio
import json
from typing import List

app = FastAPI()


app.mount("/static", StaticFiles(directory="static"), name="static")

with open("static/index.html", "r", encoding="utf-8") as f:
    html_content = f.read()

@app.get("/")
async def get():
    return HTMLResponse(html_content)

questions = [
    {
        "question": "SAP'nin açılımı nedir?",
        "answers": ["System Application and Products", "Software and Process", "Services and Automated Processes", "Strategic and Planning"],
        "correct": 0
    },
    {
        "question": "Aşağıdakilerden hangisi SAP'nin temel ERP modüllerinden biri DEĞİLDİR?",
        "answers": ["FI (Finansal Muhasebe)", "CO (Maliyet Muhasebesi)", "SD (Satış ve Dağıtım)", "HRM (İnsan Kaynakları Yönetimi)"],
        "correct": 3
    },
    {
        "question": "SAP'de 'Master Data' (Ana Veri) ne anlama gelir?",
        "answers": ["Sadece bir kez girilen ve sık sık değişmeyen verilerdir (örn: müşteri, malzeme).", "Günlük finansal hareketleri içeren verilerdir.", "Sistem ayarlarını ve konfigürasyonlarını içeren verilerdir.", "Sadece raporlama için kullanılan verilerdir."],
        "correct": 0
    },
    {
        "question": "SAP'de bir kullanıcıya erişim yetkisi vermek için hangi nesne kullanılır?",
        "answers": ["Profil", "Role", "Transaksiyon Kodu", "Rapor"],
        "correct": 1
    },
    {
        "question": "SAP'de bir işlemin kısa yolu olan ve harf ile rakamlardan oluşan koda ne denir?",
        "answers": ["Transaksiyon Kodu", "Modül Kodu", "İşlem Kodu", "Sistem Kodu"],
        "correct": 0
    },
    {
        "question": "SAP'nin standart programlama dili hangisidir?",
        "answers": ["Java", "C++", "ABAP", "Python"],
        "correct": 2
    },
    {
        "question": "SAP'de 'ERP' ne anlama gelir?",
        "answers": ["Enterprise Resource Planning", "Employee Recruitment Platform", "Electronic Reporting and Processing", "Effective Resource Production"],
        "correct": 0
    },
    {
        "question": "SAP sistemlerinde kullanılan veri tabanları arasında hangisi en yaygın olanıdır?",
        "answers": ["SQL Server", "Oracle", "HANA", "MySQL"],
        "correct": 2
    },
    {
        "question": "Aşağıdakilerden hangisi, bir şirketin finansal verilerini yöneten SAP modülüdür?",
        "answers": ["MM (Malzeme Yönetimi)", "SD (Satış ve Dağıtım)", "PP (Üretim Planlama)", "FI (Finansal Muhasebe)"],
        "correct": 3
    },
    {
        "question": "SAP S/4HANA, 'S' ve '4' ne anlama gelir?",
        "answers": ["Simple ve 4. versiyon", "Sales ve 4 modül", "Standard ve 4 bileşen", "Secure ve 4 platform"],
        "correct": 0
    },
    {
        "question": "SAP danışmanlığı hangi alanda uzmanlaşmış danışmanlık türüdür?",
        "answers": ["İnsan kaynakları", "Finansal hizmetler", "Kurumsal kaynak planlaması", "Pazarlama ve satış"],
        "correct": 2
    },
    {
        "question": "SAP'deki 'MM' modülü ne işe yarar?",
        "answers": ["Müşteri ilişkilerini yönetir.", "Üretim süreçlerini yönetir.", "Malzeme tedarik ve envanter süreçlerini yönetir.", "İnsan kaynakları süreçlerini yönetir."],
        "correct": 2
    },
    {
        "question": "SAP'de farklı iş birimlerini, sistem ayarlarını ve verileri birbirinden izole eden en üst seviye organizasyonel birim nedir?",
        "answers": ["Şirket Kodu", "Müşteri (Client)", "Maliyet Merkezi", "Organizasyon Birimi"],
        "correct": 1
    },
    {
        "question": "FI (Finansal Muhasebe) ve CO (Maliyet Muhasebesi) modüllerinin temel ilişkisi nedir?",
        "answers": ["FI, sadece CO'nun verilerini kaydeder.", "CO, sadece FI'ın verilerini kaydeder.", "FI dışa dönük, CO içe dönük raporlama yapar.", "Her ikisi de aynı amaca hizmet eder."],
        "correct": 2
    },
    {
        "question": "SAP'nin klasik ERP ürünü olan R/3'teki 'R' ve '3' ne anlama gelir?",
        "answers": ["Raporlama ve 3 modül", "Rasyonel ve 3 platform", "Gerçek zamanlı ve 3 katmanlı mimari", "Rakam ve 3 versiyon"],
        "correct": 2
    },
    {
        "question": "SAP sisteminin görünümü ve etkileşimi için kullanılan grafik arayüzüne ne ad verilir?",
        "answers": ["SAP Fiori", "SAP Web Dynpro", "SAP GUI", "SAP NetWeaver"],
        "correct": 2
    },
    {
        "question": "SAP sisteminde iş süreçlerini şirketin gereksinimlerine göre uyarlamak için yapılan ayarlara ne ad verilir?",
        "answers": ["Geliştirme (Development)", "Test", "Raporlama", "Özelleştirme (Customizing)"],
        "correct": 3
    }
]


TOTAL_QUESTIONS = 10  

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.usernames: List[str] = []  
        self.scores = {}

    async def connect(self, websocket: WebSocket, username: str):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.usernames.append(username)
        self.scores[username] = 0

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            idx = self.active_connections.index(websocket)
            user = self.usernames[idx]
            del self.usernames[idx]
            del self.active_connections[idx]
            if user in self.scores:
                del self.scores[user]

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)

manager = ConnectionManager()

current_question = None
current_answerer = None
question_start_time = None
asked_questions_count = 0  
question_index = 0  

async def ask_question():
    global current_question, current_answerer, question_start_time, asked_questions_count, question_index

    if asked_questions_count >= TOTAL_QUESTIONS:
        
        if len(manager.scores) == 0:
            winner_message = "Oyun bitti! Katılımcı yok."
        else:
            max_score = max(manager.scores.values())
            winners = [user for user, score in manager.scores.items() if score == max_score]
            if len(winners) == 1:
                winner_message = f"Oyun bitti! Kazanan: {winners[0]} ({max_score} puan)"
            else:
                winner_message = f"Oyun bitti! Berabere kazananlar: {', '.join(winners)} ({max_score} puan)"

        await manager.broadcast({
            "type": "game_over",
            "message": winner_message,
            "scores": manager.scores
        })
        reset_game()
        return

    if len(manager.active_connections) == 0:
        return


    current_question = questions[question_index % len(questions)]
    question_index += 1
    asked_questions_count += 1


    current_answerer = random.choice(manager.usernames)
    question_start_time = asyncio.get_event_loop().time()


    await manager.broadcast({
        "type": "scores",
        "scores": manager.scores
    })


    await manager.broadcast({
        "type": "question",
        "question": current_question["question"],
        "answers": current_question["answers"],
        "answerer": current_answerer,
        "scores": manager.scores,
        "question_number": asked_questions_count,
        "total_questions": TOTAL_QUESTIONS
    })

def reset_game():
    global current_question, current_answerer, question_start_time, asked_questions_count, question_index
    current_question = None
    current_answerer = None
    question_start_time = None
    asked_questions_count = 0
    question_index = 0
    manager.scores = {user: 0 for user in manager.usernames}


@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    global current_question

    await manager.connect(websocket, username)


    await manager.broadcast({
        "type": "info",
        "message": f"{username} katıldı. Toplam katılımcı: {len(manager.active_connections)}",
        "scores": manager.scores
    })


    if len(manager.active_connections) >= 3 and current_question is None:
        await ask_question()

    try:
        while True:
            data = await websocket.receive_text()
            data_json = json.loads(data)

            if data_json["type"] == "answer":
                if username != current_answerer:
                    await manager.send_personal_message({
                        "type": "error",
                        "message": "Senin sıran değil!"
                    }, websocket)
                    continue

                answer_time = asyncio.get_event_loop().time() - question_start_time
                selected = data_json["answer"]
                correct = current_question["correct"]

                if selected == correct:
                    if answer_time <= 5:
                        points = 5
                    elif answer_time <= 10:
                        points = 3
                    else:
                        points = 1

                    manager.scores[username] += points

                    await manager.broadcast({
                        "type": "correct",
                        "user": username,
                        "points": points,
                        "scores": manager.scores
                    })
                else:
                    await manager.broadcast({
                        "type": "wrong",
                        "user": username,
                        "scores": manager.scores
                    })

                await asyncio.sleep(1)
                await ask_question()

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast({
            "type": "info",
            "message": f"{username} ayrıldı. Kalan katılımcı: {len(manager.active_connections)}",
            "scores": manager.scores
        })
