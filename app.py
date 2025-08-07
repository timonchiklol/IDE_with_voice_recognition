from flask import Flask, render_template, request, jsonify
import os
from datetime import datetime
from werkzeug.utils import secure_filename
import assemblyai as aai
import google.generativeai as genai


app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def ask_gemini(user_text: str) -> str:
    """Отправляем текст в Google Gemini и возвращаем ответ.

    В файле prompt.txt должен лежать базовый промпт. Если внутри него
    присутствует строка {input}, она будет заменена на распознанный текст.
    Иначе текст пользователя будет добавлен в конец промпта.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        print("GEMINI_API_KEY не задан")
        return ""

    genai.configure(api_key=gemini_key)

    try:
        with open("prompt.txt", "r", encoding="utf-8") as f:
            base_prompt = f.read().strip()
    except FileNotFoundError:
        base_prompt = ""

    if "{input}" in base_prompt:
        final_prompt = base_prompt.replace("{input}", user_text)
    else:
        final_prompt = f"{base_prompt}\n\nПользователь: {user_text}"

    try:
        model = genai.GenerativeModel("gemini-pro")
        resp = model.generate_content(final_prompt)
        return resp.text if hasattr(resp, "text") else str(resp)
    except Exception as err:
        print("Ошибка Gemini:", err)
        return ""


def process_audio(file_path: str):
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        return {"error": "API-ключ AssemblyAI не задан"}

    aai.settings.api_key = api_key

    # Настройки модели – по умолчанию берём лучшую доступную.
    config = aai.TranscriptionConfig(speech_model=aai.SpeechModel.best)

    try:
        transcript = aai.Transcriber(config=config).transcribe(file_path)
    except Exception as err:
        return {"error": f"Ошибка запроса к AssemblyAI: {err}"}

    if transcript.status == "error":
        return {"error": transcript.error}

    print("Распознано:", transcript.text)

    gemini_answer = ask_gemini(transcript.text)
    print("Gemini ответ:", gemini_answer)

    return {
        "transcript": transcript.text,
        "gemini_answer": gemini_answer,
        "filename": os.path.basename(file_path),
    }


@app.route("/")
def index():
    """Отдаём главную страницу."""
    return render_template("index.html")


@app.route("/process", methods=["POST"])
def process():
    """Принимаем аудио-файл от клиента и возвращаем результат обработки."""
    if "audio" not in request.files:
        return jsonify({"error": "Файл 'audio' не найден в запросе"}), 400

    raw_file = request.files["audio"]
    filename = secure_filename(raw_file.filename)
    if not filename:
        filename = "recording.webm"

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    full_filename = f"{timestamp}_{filename}"
    file_path = os.path.join(UPLOAD_FOLDER, full_filename)

    raw_file.save(file_path)

    # Удаляем все старые записи, оставляя только последнюю
    try:
        files = sorted(os.listdir(UPLOAD_FOLDER), reverse=True)
        for old in files[1:]:
            old_path = os.path.join(UPLOAD_FOLDER, old)
            if os.path.isfile(old_path):
                os.remove(old_path)
    except Exception as cleanup_err:
        print(f"Не удалось очистить uploads: {cleanup_err}")

    # Обработка нейросетью
    result = process_audio(file_path)

    return jsonify(result)


if __name__ == "__main__":
    # debug=True не должен использоваться в production
    app.run(debug=True)
