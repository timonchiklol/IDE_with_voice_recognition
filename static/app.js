const recordBtn = document.getElementById("record-btn");
const statusEl = document.getElementById("status");

let mediaRecorder;
let audioChunks = [];

recordBtn.addEventListener("click", async () => {
  try {
    if (!mediaRecorder || mediaRecorder.state === "inactive") {
      // Запрашиваем разрешение и начинаем запись
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);

      mediaRecorder.addEventListener("dataavailable", (event) => {
        if (event.data.size > 0) {
          audioChunks.push(event.data);
        }
      });

      mediaRecorder.addEventListener("stop", async () => {
        // Формируем Blob из собранных чанков
        const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
        audioChunks = []; // очищаем на всякий случай

        statusEl.textContent = "Отправка файла на сервер...";

        // Отправляем аудио на сервер
        const formData = new FormData();
        formData.append("audio", audioBlob, "recording.webm");

        try {
          const resp = await fetch("/process", {
            method: "POST",
            body: formData,
          });

          if (!resp.ok) {
            const errText = await resp.text();
            statusEl.textContent = `Ошибка: ${errText}`;
            return;
          }

          const data = await resp.json();
          statusEl.textContent = data.gemini_answer || data.message || JSON.stringify(data);
        } catch (err) {
          console.error(err);
          statusEl.textContent = "Ошибка сети. Откройте консоль для деталей.";
        }
      });

      mediaRecorder.start();
      recordBtn.textContent = "Стоп";
      statusEl.textContent = "Запись...";
    } else if (mediaRecorder.state === "recording") {
      mediaRecorder.stop();
      recordBtn.textContent = "Записать";
    }
  } catch (err) {
    console.error(err);
    statusEl.textContent = "Не удалось получить доступ к микрофону.";
  }
});
