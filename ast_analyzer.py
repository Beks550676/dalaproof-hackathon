import ast
import hashlib
from typing import Dict, Any, List

def analyze_submission(source: str) -> Any:
    """Главная функция анализа: превращает исходный текст кода на Python в структурированный отчет."""
    if not isinstance(source, str):
        # Если пришел не текст (например, число или None), возвращаем ошибку
        class FakeReport:
            ok = False
            error = "Source code must be a string"
        return FakeReport()

    # Проверка на синтаксические ошибки с помощью встроенного модуля ast.parse
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        class SyntaxErrorReport:
            ok = False
            syntax_error = e
            error = f"Syntax error at line {e.lineno}: {e.msg}"
        return SyntaxErrorReport()

    # Если синтаксис верный, запускаем обход дерева узлов (Visitor)
    visitor = CodeVisitor()
    visitor.visit(tree)

    class SuccessReport:
        ok = True
        error = None
        functions = visitor.functions
        classes = visitor.classes
        warnings = visitor.warnings
        static_signals = {
            "solution_state": "substantive" if visitor.functions else "stub",
            "function_count": len(visitor.functions),
            "module_has_logic": len(tree.body) > 0
        }
        # Создаем уникальный «отпечаток» (fingerprint) кода, чтобы ловить списывания
        fingerprint = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]

    return SuccessReport()


class CodeVisitor(ast.NodeVisitor):
    """Класс-обходчик абстрактного синтаксического дерева (AST). 
    Читает код как программу, находя функции, циклы, условия и вызовы."""
    def __init__(self):
        self.functions = []
        self.classes = []
        self.warnings = []
        self._current_class = None

    def visit_FunctionDef(self, node: ast.FunctionDef):
        # Находим определение каждой функции (def ...)
        func_name = node.name
        qualname = f"{self._current_class}.{func_name}" if self._current_class else func_name
        
        # Считаем цикломатическую сложность (количество ветвлений if/for/while)
        complexity = 1
        branches = []
        exceptions_raised = []

        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.ExceptHandler)):
                complexity += 1
                if isinstance(child, ast.If):
                    # Сохраняем условие ветвления для вопросов от ИИ
                    test_str = ast.unparse(child.test) if hasattr(ast, "unparse") else "condition"
                    branches.append({"test": test_str})
            elif isinstance(child, ast.Raise):
                exceptions_raised.append("Exception raised")

        class FunctionFact:
            pass
            
        FunctionFact.name = func_name
        FunctionFact.qualname = func_name
        FunctionFact.complexity = complexity
        FunctionFact.branches = branches
        FunctionFact.exceptions_raised = exceptions_raised
        FunctionFact.is_stub = len(node.body) == 1 and isinstance(node.body[0], ast.Pass)
        FunctionFact.is_trivial = len(node.body) == 1 and isinstance(node.body[0], ast.Return)
        FunctionFact.is_method = self._current_class is not None

        self.functions.append(FunctionFact())
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        # Находим определение классов (class ...)
        self._current_class = node.name
        methods = []
        for body_item in node.body:
            if isinstance(body_item, ast.FunctionDef):
                methods.append(body_item.name)
        
        class ClassFact:
            name = node.name
            methods = methods
        self.classes.append(ClassFact())
        self.generic_visit(node)
        self._current_class = None

    def visit_Call(self, node: ast.Call):
        # Проверяем опасные функции вроде exec() или eval()
        if isinstance(node.func, ast.Name) and node.func.id in ("exec", "eval"):
            self.warnings.append(f"Dangerous function used: {node.func.id}")
        self.generic_visit(node)


def analyze_code(code: str) -> dict:
    """⚙️ ЭТО ГЛАВНЫЙ МОСТ ДЛЯ УЧАСТНИКА 1 (main.py):
    Приводит отчет нашего AST-анализатора к тому формату словаря, который ждет сервер FastAPI.
    """
    report = analyze_submission(code)
    
    # Если код с синтаксической ошибкой — возвращаем алерты
    if not report.ok:
        return {
            "ast_valid": False,
            "error": getattr(report, "error", "Синтаксическая ошибка в коде"),
            "detected_structures": []
        }

    structures = []
    # Собираем все найденные функции и их сложность в удобный список для ИИ и фронтенда
    for fn in getattr(report, "functions", []):
        if fn.name != "<module>":
            structures.append(f"function: {fn.qualname} (complexity={fn.complexity})")
        for branch in fn.branches:
            structures.append(f"branch: if {branch.get('test', '')}")

    # Дополнительно через стандартный ast проверяем наличие базовых конструкций (словарей, циклов)
    try:
        tree = ast.parse(code)
        if any(isinstance(n, (ast.Dict, ast.DictComp)) for n in ast.walk(tree)):
            structures.append("dict")
        if any(isinstance(n, ast.For) for n in ast.walk(tree)):
            structures.append("for_loop")
    except Exception:
        pass

    return {
        "ast_valid": True,
        "detected_structures": structures or ["basic_script"],
        "fingerprint": getattr(report, "fingerprint", ""),
        "solution_state": report.static_signals.get("solution_state", "substantive")
    }


def run_self_check() -> None:
    """Офлайн-тест для самопроверки презентера перед защитой."""
    sample = "def check_inv(stock):\n    if not stock:\n        return []\n    return [k for k in stock if stock[k] <= 0]\n"
    res = analyze_code(sample)
    assert res["ast_valid"] is True
    assert any("check_inv" in s for s in res["detected_structures"])
    print("ast_analyzer self-check passed successfully!")

if __name__ == "__main__":
    run_self_check()