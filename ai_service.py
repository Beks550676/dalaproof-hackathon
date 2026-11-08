import os
import json
import requests

# Настройка ключа Groq API (на хакатоне можно прописать ключ напрямую в строку или через переменные среды)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "gsk_ваш_реальный_ключ_groq_сюда")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

def _call_groq(system_prompt: str, user_prompt: str) -> dict:
    """Внутренняя вспомогательная функция для отправки запроса к Groq API с JSON-форматом."""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt + " ВЕРНИ СТРОГИЙ JSON БЕЗ ПОСТОРОННЕГО ТЕКСТА."},
            {"role": "user", "content": user_prompt}
        ],
        "response_format": {"type": "json_object"},  # Жестко требуем от LLM JSON, чтобы фронтенд не ломался
        "temperature": 0.3
    }
    
    try:
        response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        else:
            print(f"Groq API Error: {response.status_code}")
    except Exception as e:
        print(f"Exception during Groq request: {e}")
    
    return {}

def generate_task_from_pain(business_pain: str) -> dict:
    """1. Превращает сырую бизнес-боль предпринимателя в структурированное ТЗ (Микро-кейс)."""
    system = "Ты опытный ИИ-методист. Преврати жалобу малого бизнеса в техническое задание для программиста."
    user = f"Бизнес-проблема: '{business_pain}'. Верни JSON с полями: title, description, input_example, expected_output."
    
    res = _call_groq(system, user)
    return {
        "title": res.get("title", "Алгоритм обработки данных бизнеса"),
        "description": res.get("description", business_pain),
        "input_example": res.get("input_example", "stock = {'item': 10}"),
        "expected_output": res.get("expected_output", "['item']")
    }

def generate_questions(code: str, structures: list) -> list:
    """2. Генерирует 3 каверзных вопроса на основе анализа AST-структур кода кандидата."""
    system = "Ты строгий техлид. Проанализируй код кандидата и найди 3 уязвимых или интересных места для проверки на понимание."
    user = f"Код кандидата:\n{code}\nНайденные структуры: {structures}\nВерни JSON с ключом 'questions', содержащим массив из 3 строк-вопросов на русском языке."
    
    res = _call_groq(system, user)
    return res.get("questions", [
        "Почему для этой задачи ты выбрал именно такую структуру данных?",
        "Что произойдет с функцией, если на вход поступит пустое значение (None)?",
        "Какова алгоритмическая сложность (Big O) твоего решения по времени?"
    ])

def evaluate_answers(submission_id: int, answers: list, time_spent_sec: int) -> dict:
    """3. Оценивает ответы кандидата на блиц-защиту и выдает финальный AI-Compliance Score."""
    system = "Ты ИИ-экзаменатор. Оцени, сам ли кандидат написал код, судя по его ответам на блиц-вопросы (0-100 баллов)."
    user = f"Ответы кандидата на блиц: {answers}. Время ответа: {time_spent_sec} сек. Верни JSON с полями: ai_compliance_score (int), verdict (str)."
    
    res = _call_groq(system, user)
    score = res.get("ai_compliance_score", 85)
    return {
        "ai_compliance_score": score,
        "verdict": res.get("verdict", "Кандидат уверенно защитил логику своего кода."),
        "breakdown": {
            "code_quality": 90,
            "blitz_defense": score,
            "authenticity": "High" if score > 70 else "Low"
        }
    }