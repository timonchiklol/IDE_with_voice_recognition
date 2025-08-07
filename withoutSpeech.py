import os
import re
import subprocess
import sys
import tempfile
from textwrap import dedent
import google.generativeai as genai
from dotenv import load_dotenv
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=API_KEY)
SAVE_DIR = "DIR_TO_SAVE" # это временная херня перенести надо на сервак
# Инициализация модели
model = genai.GenerativeModel('gemini-2.5-flash')
def _extract_python_code(text: str) -> str:

    """Извлекает первый блок кода Python из ответа модели.

    Ожидаем, что модель вернёт код в формате:
    ```python
    # код
    ```
    """
    # Ищем блок ```python ... ```
    code_blocks = re.findall(r"```python(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if not code_blocks:
        # fallback: любой блок ``` ... ```
        code_blocks = re.findall(r"```(.*?)```", text, re.DOTALL)
    if not code_blocks:
        return ""
    # Убираем возможные префиксные/суффиксные пустые строки
    return dedent(code_blocks[0].strip())


def generate_python_script(idea: str) -> str:
    """Запрашивает у Gemini код для идеи и возвращает текст скрипта."""
    # Получаем ключ из переменной окружения (или укажите напрямую строкой)
    if not API_KEY:
        raise EnvironmentError("Переменная окружения GEMINI_API_KEY не задана")


    system_prompt = (
        "Ты опытный разработчик Python. Пользователь описывает идею проекта. "
        "Ответь только валидным содержимым одного Python-скрипта, без пояснений, "
        "обернув его в блок ```python ... ```. Скрипт должен быть самодостаточным и "
        "запускаемым как `python script.py`."
    )

    # Составляем полный промпт
    full_prompt = f"{system_prompt}\n\nИдея пользователя: {idea}"

    print("\nОтправка запроса Gemini...\n")
    resp = model.generate_content(full_prompt)
    raw_answer = resp.text if hasattr(resp, "text") else str(resp)

    code = _extract_python_code(raw_answer)
    if not code:
        raise ValueError("Модель не вернула блок кода python")

    return code


def main():
    if len(sys.argv) < 2:
        print("Использование: python withoutSpeech.py \"Ваша идея проекта\"")
        sys.exit(1)

    idea = " ".join(sys.argv[1:])
    try:
        script_code = generate_python_script(idea)
    except Exception as err:
        print("Ошибка генерации кода:", err)
        sys.exit(1)

    # Создаём временный файл для кода
    os.makedirs(SAVE_DIR, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".py", encoding="utf-8", dir=SAVE_DIR) as tmp:
        tmp.write(script_code)
        tmp_path = tmp.name

    print(f"\nСкрипт сохранён во временный файл: {tmp_path}\n")

    try:
        print("Запуск сгенерированного скрипта...\n")
        subprocess.run([sys.executable, tmp_path], check=True)
    except subprocess.CalledProcessError as run_err:
        print("Ошибка при выполнении сгенерированного скрипта:", run_err)
    finally:
        # Оставляем файл, чтобы пользователь мог изучить. Можно удалить при желании.
        print(f"\nСгенерированный код: {'-'*40}\n{script_code}\n{'-'*40}")
        print(f"Файл кода: {tmp_path}")


if __name__ == "__main__":
    main()

