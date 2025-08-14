const recordBtn = document.getElementById("record-btn");
const websiteBtn = document.getElementById("website-btn");
const editBtn = document.getElementById("edit-btn");
const statusEl = document.getElementById("status");

let mediaRecorder;
let audioChunks = [];
let lastSavedFile = null;
let websiteGenerated = false;

// Modal functions
function openModal(modalId) {
  document.getElementById(modalId).style.display = "block";
}

function closeModal(modalId) {
  document.getElementById(modalId).style.display = "none";
}

// Submit website edit
async function submitWebsiteEdit() {
  const instructions = document.getElementById("edit-instructions").value.trim();
  
  if (!instructions) {
    alert("Please enter edit instructions!");
    return;
  }
  
  try {
    editBtn.disabled = true;
    statusEl.textContent = "Editing website...";
    closeModal("edit-modal");
    
    const response = await fetch("/edit-website", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        instructions: instructions
      }),
    });
    
    const data = await response.json();
    
    if (data.success) {
      statusEl.innerHTML = `
✅ Website edited successfully!<br>
📁 New file: ${data.new_file}<br>
🌐 Check your browser - the updated website should open automatically<br>
✏️ Applied changes: "${instructions}"
      `;
      
      // Clear the textarea for next use
      document.getElementById("edit-instructions").value = "";
      editBtn.disabled = false;
    } else {
      statusEl.textContent = `Error editing website: ${data.error}`;
      editBtn.disabled = false;
    }
    
  } catch (err) {
    console.error("Failed to edit website:", err);
    statusEl.textContent = "Failed to edit website. Check console for details.";
    editBtn.disabled = false;
  }
}

recordBtn.addEventListener("click", async () => {
  try {
    if (!mediaRecorder || mediaRecorder.state === "inactive") {
      // Request permission and start recording
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);

      mediaRecorder.addEventListener("dataavailable", (event) => {
        if (event.data.size > 0) {
          audioChunks.push(event.data);
        }
      });

      mediaRecorder.addEventListener("stop", async () => {
        // Create Blob from collected chunks
        const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
        audioChunks = []; // clear just in case

        statusEl.textContent = "Processing and improving your text...";

        // Send audio to server
        const formData = new FormData();
        formData.append("audio", audioBlob, "recording.webm");

        try {
          const resp = await fetch("/process", {
            method: "POST",
            body: formData,
          });

          if (!resp.ok) {
            const errText = await resp.text();
            statusEl.textContent = `Error: ${errText}`;
            return;
          }

          const data = await resp.json();
          
          if (data.error) {
            statusEl.textContent = `Error: ${data.error}`;
            return;
          }

          // Save the filename for website generation
          lastSavedFile = data.saved_file;

          // Display the improved text and file info
          const message = `
✅ Text processed and saved!<br>
📁 File: ${data.saved_file}<br>

📝 Improved text:<br>
"${data.improved_text}"<br><br>

💡 Now you can generate a website from this text!
          `.trim();
          
          statusEl.innerHTML = message;

          // Enable website generation button
          websiteBtn.disabled = false;
          
        } catch (err) {
          console.error(err);
          statusEl.textContent = "Network error. Open console for details.";
        }
      });

      mediaRecorder.start();
      recordBtn.textContent = "🛑 Stop";
      statusEl.textContent = "🎙️ Recording... Speak clearly!";
    } else if (mediaRecorder.state === "recording") {
      mediaRecorder.stop();
      recordBtn.textContent = "🎙️ Record";
    }
  } catch (err) {
    console.error(err);
    statusEl.textContent = "Failed to access microphone.";
  }
});

websiteBtn.addEventListener("click", async () => {
  try {
    websiteBtn.disabled = true;
    statusEl.textContent = "🌐 Generating website from your text...";

    const response = await fetch("/generate-website", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        filename: lastSavedFile
      }),
    });

    const data = await response.json();

    if (data.success) {
      websiteGenerated = true;
      editBtn.disabled = false; // Enable edit button after website is generated
      
      statusEl.innerHTML = `
🎉 Website generation started!<br>
🌐 Check your browser - the website should open automatically<br>
📝 Based on text from: ${lastSavedFile}<br><br>
✏️ You can now edit the website if needed!
      `;
    } else {
      statusEl.textContent = `Error: ${data.error}`;
      websiteBtn.disabled = false;
    }

  } catch (err) {
    console.error(err);
    statusEl.textContent = "Failed to generate website. Check console for details.";
    websiteBtn.disabled = false;
  }
});

editBtn.addEventListener("click", () => {
  openModal("edit-modal");
});

// Close modals when clicking outside
window.addEventListener("click", (event) => {
  const modals = document.querySelectorAll(".modal");
  modals.forEach(modal => {
    if (event.target === modal) {
      modal.style.display = "none";
    }
  });
});
