from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import database as db  # Импортируем наш файл database.py, чтобы вызывать функции БД

# Пытаемся подключить файлы Участника 2 (AST-парсер и ИИ-сервис).
# Конструкция try-except нужна, чтобы твой сервер работал ПРЯМО СЕЙЧАС, даже пока Участник 2 еще пишет свой код.
try:
    import ast_analyzer
    import ai_service
    USE_MOCKS = False
except ImportError:
    USE_MOCKS = True
    print("⚠️ Модули Участника 2 пока не найдены. Работаем на встроенных заглушках (Mocks)!")

# Создаем само приложение FastAPI
app = FastAPI(title="DalaProof Anti-Resume API", version="1.0")

# --- НАСТРОЙКА CORS ---
# Браузеры по умолчанию блокируют запросы с фронтенда (index.html) на локальный сервер.
# Этот блок разрешает фронтенду Участников 3 и 4 свободно отправлять нам fetch()-запросы.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # Разрешаем запросы с любых адресов
    allow_credentials=True,
    allow_methods=["*"],      # Разрешаем любые методы (GET, POST и т.д.)
    allow_headers=["*"],      # Разрешаем любые заголовки
)

# При каждом запуске сервера проверяем, что таблицы в dalaproof.db существуют
@app.on_event("startup")
def startup():
    db.init_db()


# --- PYDANTIC СХЕМЫ (Валидация входных JSON от фронтенда) ---
# Если фронтенд пришлет неправильные типы данных, Pydantic автоматически вернет понятную ошибку 422.

class GenerateTaskRequest(BaseModel):
    business_pain: str  # Ожидаем строку с описанием боли бизнеса

class SubmitCodeRequest(BaseModel):
    task_id: int        # ID задачи, которую решает студент
    candidate_name: str # Имя студента
    code: str           # Присланный Python-код

class VerifyAnswersRequest(BaseModel):
    submission_id: int  # ID попытки (который мы выдали при отправке кода)
    answers: List[str]  # Список из 3 ответов студента на блиц-вопросы
    time_spent_sec: int = 45  # Сколько секунд потратил (по умолчанию 45)


# --- МАРШРУТЫ (ЭНДПОИНТЫ API) ---

# 1. Эндпоинт для Бизнеса: превращает описание проблемы в техническое задание (микро-кейс)
@app.post("/api/generate-task")
def generate_task(req: GenerateTaskRequest):
    # Проверяем, что предприниматель не отправил пустую строку
    if not req.business_pain.strip():
        raise HTTPException(status_code=400, detail="Опишите проблему бизнеса")

    # Если модуль Участника 2 подключен — вызываем реальный ИИ Groq
    if not USE_MOCKS and hasattr(ai_service, "generate_task_from_pain"):
        task_data = ai_service.generate_task_from_pain(req.business_pain)
    else:
        # Иначе отдаем заготовленный демо-кейс (сеть донерных в Шымкенте)
        task_data = {
            "title": "Алгоритм контроля критических остатков сырья (Донерная)",
            "description": (
                f"На основе запроса бизнеса: '{req.business_pain}'. "
                "Напишите функцию check_inventory(stock, norms), которая принимает словарь текущих "
                "остатков на складе и словарь минимальных норм. Функция должна возвращать список "
                "продуктов, которые нужно срочно дозаказать (остаток меньше или равен норме)."
            ),
            "input_example": "stock = {'lavash': 15, 'meat_kg': 4.5, 'sauce_l': 10}, norms = {'lavash': 20, 'meat_kg': 5.0, 'sauce_l': 3}",
            "expected_output": "['lavash', 'meat_kg']"
        }

    # Сохраняем сгенерированную задачу в SQLite (файл dalaproof.db) и получаем её ID
    task_id = db.create_task(
        title=task_data["title"],
        description=task_data["description"],
        input_example=task_data["input_example"],
        expected_output=task_data["expected_output"]
    )

    # Возвращаем фронтенду ID задачи и само ТЗ
    return {
        "task_id": task_id,
        **task_data
    }


# Бонусный эндпоинт: отдает список всех задач для экрана Кандидата
@app.get("/api/tasks")
def list_tasks():
    return db.get_all_tasks()


# 2. Эндпоинт для Кандидата: принимает код, разбирает через AST и возвращает 3 вопроса для блица
@app.post("/api/submit-code")
def submit_code(req: SubmitCodeRequest):
    if not req.code.strip():
        raise HTTPException(status_code=400, detail="Код не может быть пустым")

    # Если Участник 2 уже написал ast_analyzer и ai_service — используем их
    if not USE_MOCKS and hasattr(ast_analyzer, "analyze_code") and hasattr(ai_service, "generate_questions"):
        ast_res = ast_analyzer.analyze_code(req.code)
        if not ast_res.get("ast_valid", False):
            return {
                "submission_id": None,
                "ast_valid": False,
                "error": ast_res.get("error", "Синтаксическая ошибка в коде"),
                "detected_structures": [],
                "questions": []
            }
        questions = ai_service.generate_questions(req.code, ast_res["detected_structures"])
        structures = ast_res["detected_structures"]
    else:
        # Заглушка: проверяем синтаксис Python встроенной функцией compile()
        try:
            compile(req.code, "<string>", "exec")
        except SyntaxError as e:
            # Если студент прислал сломанный код — сразу ловим ошибку и не пускаем на блиц
            return {
                "submission_id": None,
                "ast_valid": False,
                "error": f"Синтаксическая ошибка на строке {e.lineno}: {e.msg}",
                "detected_structures": [],
                "questions": []
            }

        # Структуры и вопросы по контракту Точки сборки №1
        structures = ["function: check_inventory", "dict", "for_loop"]
        questions = [
            "В функции check_inventory ты используешь словарь. Почему выбран именно он, а не список?",
            "Что вернет цикл в строке 12, если остаток товара уйдет в минус?",
            "Как изменится время работы функции при росте склада до 100 000 позиций?"
        ]

    # Сохраняем попытку кандидата в БД
    sub_id = db.create_submission(
        task_id=req.task_id,
        candidate_name=req.candidate_name,
        code=req.code,
        ast_valid=True,
        structures=structures,
        questions=questions
    )

    return {
        "submission_id": sub_id,
        "ast_valid": True,
        "detected_structures": structures,
        "questions": questions
    }


# 3. Эндпоинт проверки блиц-защиты: принимает 3 ответа кандидата и выдает финальный AI-Compliance Score
@app.post("/api/verify-answers")
def verify_answers(req: VerifyAnswersRequest):
    if not USE_MOCKS and hasattr(ai_service, "evaluate_answers"):
        eval_res = ai_service.evaluate_answers(req.submission_id, req.answers, req.time_spent_sec)
        score = eval_res["ai_compliance_score"]
        verdict = eval_res["verdict"]
        breakdown = eval_res.get("breakdown", {"code_quality": 95, "blitz_defense": score, "authenticity": "High"})
    else:
        # Заглушка: если студент написал осмысленные ответы (длиннее 5 символов), ставим высокий балл
        filled_answers = [a for a in req.answers if len(a.strip()) > 5]
        if len(filled_answers) >= 2:
            score = 92
            verdict = "Код написан самостоятельно. Кандидат понимает алгоритмическую сложность."
            authenticity = "High"
        else:
            score = 25
            verdict = "Подозрение на копипаст из ИИ. Кандидат не смог защитить логику своего кода."
            authenticity = "Low"

        breakdown = {
            "code_quality": 95,
            "blitz_defense": score,
            "authenticity": authenticity
        }

    # Обновляем финальный балл кандидата в базе данных
    db.update_submission_score(req.submission_id, score, verdict)

    return {
        "ai_compliance_score": score,
        "verdict": verdict,
        "breakdown": breakdown
    }


# Бонусный эндпоинт для Дашборда Бизнеса: возвращает таблицу лучших кандидатов
@app.get("/api/leaderboard")
def leaderboard():
    return db.get_leaderboard()

from fastapi.staticfiles import StaticFiles
app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")