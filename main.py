from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import os
from fastapi.staticfiles import StaticFiles
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
    business_pain: str        # Ожидаем строку с описанием боли бизнеса

class SubmitCodeRequest(BaseModel):
    task_id: int              # ID задачи, которую решает студент
    candidate_name: str       # Имя студента
    code: str                 # Присланный Python-код

class VerifyAnswersRequest(BaseModel):
    submission_id: int        # ID попытки (который мы выдали при отправке кода)
    answers: List[str]        # Список из 3 ответов студента на блиц-вопросы
    time_spent_sec: int = 45  # Сколько секунд потратил
    tab_switches: int = 0     # Сколько раз кандидат уходил со вкладки в ChatGPT
    paste_attempts: int = 0   # Сколько раз пытался вставить текст через Ctrl+V
    keystrokes: int = 100     # Сколько реально клавиш нажал на клавиатуре


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


# 3. Эндпоинт проверки блиц-защиты + 4-уровневый Анти-Чит Детектор ИИ
@app.post("/api/verify-answers")
def verify_answers(req: VerifyAnswersRequest):
    # Очищаем ответы от пробелов и берем только осмысленные (длиннее 5 символов)
    clean_answers = [a.strip() for a in (req.answers or []) if a and len(a.strip()) > 5]
    answered_count = len(clean_answers)
    time_spent = req.time_spent_sec if req.time_spent_sec is not None else 0

    # --- УРОВЕНЬ 1: ПРОВЕРКА НА ПУСТЫЕ ОТВЕТЫ ---
    if answered_count == 0:
        score = 0
        verdict = "Не пройдено: Кандидат отправил пустые ответы и не смог защитить свой код."
        authenticity = "None"
        ai_probability = 0

    # --- УРОВЕНЬ 2: ПОВЕДЕНЧЕСКИЙ ПРОКТОРИНГ (Переключение вкладок в ChatGPT / Попытки Ctrl+V) ---
    elif req.paste_attempts > 0 or req.tab_switches > 1:
        score = 10
        ai_probability = 95
        verdict = (
            f"🚨 AI-Детектор: Зафиксировано читерство! "
            f"Уходов со вкладки (в сторонний ИИ): {req.tab_switches}, "
            f"попыток вставки (Ctrl+V): {req.paste_attempts}."
        )
        authenticity = "Fake (Proctoring Alert)"

    # --- УРОВЕНЬ 3: КОНТРОЛЬ АНОМАЛЬНОГО ВРЕМЕНИ (< 20 сек или > 95 сек) ---
    elif time_spent < 20:
        score = 15
        ai_probability = 90
        verdict = f"🚨 Подозрение на ИИ (Анти-чит): Ответы отправлены слишком быстро ({time_spent} сек < 20 сек). Человек не успеет прочитать и напечатать."
        authenticity = "Low (Speed Anomaly)"

    elif time_spent > 95:
        score = 35
        ai_probability = 60
        verdict = f"Время вышло ({time_spent} сек): Кандидат слишком долго искал ответы в сторонних источниках."
        authenticity = "Low (Timeout)"

    # --- УРОВЕНЬ 4: ЛИНГВИСТИЧЕСКИЙ AI-ДЕТЕКТОР + ОЦЕНКА КАЧЕСТВА ОТВЕТОВ ---
    else:
        total_points = 0
        # Ключевые технические слова для проверки понимания кода
        tech_words = [
            "словар", "dict", "спис", "list", "цикл", "for", "while", "сложност",
            "o(", "none", "пуст", "ошибк", "ключ", "значен", "память", "время",
            "услов", "if", "return", "проверк", "элемент", "функц", "индекс", "алгоритм"
        ]
        # Типичные канцеляризмы и шаблоны генерации ChatGPT / LLM
        ai_cliches = [
            "таким образом", "следовательно", "резюмируя", "в заключение",
            "данный алгоритм", "во-первых", "во-вторых", "безусловно", "в контексте данной"
        ]

        ai_markers_found = 0
        total_chars = sum(len(a) for a in clean_answers)

        for ans in clean_answers:
            words_count = len(ans.split())
            ans_lower = ans.lower()

            # Проверяем текст на шаблонные фразы ИИ
            for cliche in ai_cliches:
                if cliche in ans_lower:
                    ai_markers_found += 1

            # Базовые баллы за полноту ответа
            if words_count < 4:
                q_points = 8    # Слишком короткая отписка
            elif words_count < 8:
                q_points = 15   # Средний ответ
            else:
                q_points = 22   # Развернутый ответ

            # Бонус за технические термины (до +8 баллов за вопрос)
            matched_terms = sum(1 for w in tech_words if w in ans_lower)
            q_points += min(8, matched_terms * 4)
            total_points += min(30, q_points)

        speed_bonus = 10 if (20 <= time_spent <= 55 and answered_count == 3) else 4
        raw_score = min(100, total_points + speed_bonus)

        # Штрафуем, если нажатий клавиш подозрительно мало по сравнению с длиной текста
        penalty = (req.tab_switches * 25) + (ai_markers_found * 20)
        if req.keystrokes < total_chars * 0.4:
            penalty += 35

        score = max(15, raw_score - penalty)
        ai_probability = min(98, (req.tab_switches * 35) + (ai_markers_found * 30) + (5 if score >= 80 else 20))

        # Итоговый вердикт с метриками анти-чита
        if score >= 80:
            verdict = (
                f"✓ Код написан самостоятельно ({answered_count}/3 ответов за {time_spent} сек). "
                f"Ручной ввод подтвержден ({req.keystrokes} нажатий клавиш, 0 попыток Ctrl+V, "
                f"вероятность ИИ: {ai_probability}%)."
            )
            authenticity = "High (Human Verified)"
        elif score >= 50:
            verdict = (
                f"~ Частичная защита ({answered_count}/3 ответов за {time_spent} сек). "
                f"Переключений окна: {req.tab_switches}, вероятность ИИ: {ai_probability}%."
            )
            authenticity = "Medium"
        else:
            verdict = (
                f"🚨 Подозрение на генерацию ИИ (Вероятность ИИ: {ai_probability}%). "
                f"Слабая защита или синтетические паттерны ввода."
            )
            authenticity = "Low (AI Suspected)"

    breakdown = {
        "code_quality": 95 if score > 0 else 0,
        "blitz_defense": score,
        "authenticity": authenticity,
        "ai_probability_percent": ai_probability,
        "tab_switches": req.tab_switches,
        "paste_attempts": req.paste_attempts
    }

    # Сохраняем рассчитанный балл и вердикт в базу данных SQLite
    db.update_submission_score(req.submission_id, score, verdict)

    return {
        "score": score,
        "final_score": score,
        "ai_compliance_score": score,
        "verdict": verdict,
        "feedback": verdict,
        "breakdown": breakdown,
        "time_spent_sec": time_spent
    }


# Бонусный эндпоинт для Дашборда Бизнеса: возвращает таблицу лучших кандидатов
@app.get("/api/leaderboard")
def leaderboard():
    return db.get_leaderboard()


# --- РАЗДАЧА ФРОНТЕНДА (СТАТИЧЕСКИХ ФАЙЛОВ) ---
# Проверяем, существует ли папка frontend, и монтируем её на маршрут /app
if os.path.exists("frontend"):
    app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")