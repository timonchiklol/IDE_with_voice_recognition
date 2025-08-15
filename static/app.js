// State machine for the main button
const STATES = {
    RECORD: 'record',
    STOP: 'stop', 
    WAIT: 'wait',
    EDIT: 'edit'
};

// Global variables
let currentState = STATES.RECORD;
let mediaRecorder = null;
let audioChunks = [];
let lastSavedFile = null;
let currentWebsiteId = null;

// DOM elements
const mainBtn = document.getElementById('main-btn');
const saveBtn = document.getElementById('save-btn');
const savesBtn = document.getElementById('saves-btn');
const savesMenu = document.getElementById('saves-menu');
const savesList = document.getElementById('saves-list');
const statusEl = document.getElementById('status');

// State management
function setState(newState) {
    currentState = newState;
    updateUI();
}

function updateUI() {
    // Reset all classes
    mainBtn.className = 'main-btn';
    
    switch (currentState) {
        case STATES.RECORD:
            mainBtn.classList.add('record');
            mainBtn.textContent = '🎙️ Record';
            mainBtn.disabled = false;
            saveBtn.disabled = true;
            statusEl.textContent = 'Press "Record" to start creating your website';
            break;
            
        case STATES.STOP:
            mainBtn.classList.add('stop');
            mainBtn.textContent = '🛑 Stop';
            mainBtn.disabled = false;
            saveBtn.disabled = true;
            statusEl.textContent = '🎙️ Recording... Speak clearly!';
            break;
            
        case STATES.WAIT:
            mainBtn.classList.add('wait');
            mainBtn.textContent = '⏳ Wait';
            mainBtn.disabled = true;
            saveBtn.disabled = true;
            break;
            
        case STATES.EDIT:
            mainBtn.classList.add('edit');
            mainBtn.textContent = '✏️ Edit';
            mainBtn.disabled = false;
            saveBtn.disabled = false;
            break;
    }
}

// Main button click handler
mainBtn.addEventListener('click', async () => {
    switch (currentState) {
        case STATES.RECORD:
            await startRecording();
            break;
            
        case STATES.STOP:
            await stopRecording();
            break;
            
        case STATES.EDIT:
            await startEditRecording();
            break;
    }
});

// Recording functions
async function startRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];

        mediaRecorder.addEventListener('dataavailable', (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        });

        mediaRecorder.addEventListener('stop', async () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            
            if (currentState === STATES.EDIT) {
                await processEditAudio(audioBlob);
            } else {
                await processNewAudio(audioBlob);
            }
        });

        mediaRecorder.start();
        setState(STATES.STOP);
        
    } catch (err) {
        console.error('Failed to access microphone:', err);
        statusEl.textContent = 'Failed to access microphone. Please check permissions.';
    }
}

async function stopRecording() {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
        setState(STATES.WAIT);
        statusEl.textContent = '⏳ Processing and improving your text...';
    }
}

async function startEditRecording() {
    setState(STATES.RECORD);
    statusEl.textContent = 'Record your edit instructions...';
    // Small delay to update UI
    setTimeout(() => {
        startRecording();
    }, 100);
}

// Audio processing functions
async function processNewAudio(audioBlob) {
    try {
        statusEl.textContent = '⏳ Processing and improving your text...';
        
        const formData = new FormData();
        formData.append('audio', audioBlob, 'recording.webm');

        const response = await fetch('/process', {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        lastSavedFile = data.saved_file;
        statusEl.textContent = '⏳ Generating website...';

        // Auto-generate website
        await generateWebsite();

    } catch (err) {
        console.error('Processing error:', err);
        statusEl.textContent = `Error: ${err.message}`;
        setState(STATES.RECORD);
    }
}

async function processEditAudio(audioBlob) {
    try {
        statusEl.textContent = '⏳ Processing edit instructions...';
        
        const formData = new FormData();
        formData.append('audio', audioBlob, 'recording.webm');

        const response = await fetch('/process', {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        statusEl.textContent = '⏳ Applying changes to website...';

        // Apply edits to website
        await editWebsite(data.improved_text);

    } catch (err) {
        console.error('Edit processing error:', err);
        statusEl.textContent = `Error: ${err.message}`;
        setState(STATES.EDIT);
    }
}

async function generateWebsite() {
    try {
        const response = await fetch('/generate-website', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                filename: lastSavedFile
            }),
        });

        const data = await response.json();

        if (data.success) {
            setState(STATES.EDIT);
            statusEl.innerHTML = `
🎉 Website generated successfully!<br>
🌐 Check your browser - the website should open automatically<br><br>
✏️ You can now edit the website or save it!
            `;
        } else {
            throw new Error(data.error || 'Failed to generate website');
        }

    } catch (err) {
        console.error('Website generation error:', err);
        statusEl.textContent = `Error generating website: ${err.message}`;
        setState(STATES.RECORD);
    }
}

async function editWebsite(instructions) {
    try {
        const response = await fetch('/edit-website', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                instructions: instructions
            }),
        });

        const data = await response.json();

        if (data.success) {
            setState(STATES.EDIT);
            statusEl.innerHTML = `
✅ Website updated successfully!<br>
🌐 Check your browser for the updated website<br><br>
✏️ You can continue editing or save your changes!
            `;
        } else {
            throw new Error(data.error || 'Failed to edit website');
        }

    } catch (err) {
        console.error('Website edit error:', err);
        statusEl.textContent = `Error editing website: ${err.message}`;
        setState(STATES.EDIT);
    }
}

// Save system
saveBtn.addEventListener('click', () => {
    if (currentState === STATES.EDIT) {
        openModal('save-modal');
    }
});

savesBtn.addEventListener('click', () => {
    console.log('Saves button clicked');
    
    // Add debug info
    fetch('/debug/websites')
        .then(response => response.json())
        .then(data => {
            console.log('Debug info:', data);
        })
        .catch(err => {
            console.error('Debug request failed:', err);
        });
    
    toggleSavesMenu();
});

function toggleSavesMenu() {
    if (savesMenu.classList.contains('show')) {
        savesMenu.classList.remove('show');
    } else {
        loadSavedWebsites();
        savesMenu.classList.add('show');
    }
}

async function loadSavedWebsites() {
    try {
        const response = await fetch('/saved-websites');
        const data = await response.json();
        
        savesList.innerHTML = '';
        
        if (data.websites && data.websites.length > 0) {
            data.websites.forEach(website => {
                const item = document.createElement('div');
                item.className = 'saved-item';
                item.innerHTML = `
                    <div class="saved-name">${website.name}</div>
                    <div class="saved-actions">
                        <button class="start-btn" onclick="loadWebsite('${website.id}')">Start</button>
                        <button class="edit-saved-btn" onclick="loadWebsiteForEdit('${website.id}')">Edit</button>
                        <button class="download-btn" onclick="downloadWebsite('${website.id}')">📥</button>
                        <button class="delete-btn" onclick="confirmDeleteWebsite('${website.id}', '${website.name}')">🗑️</button>
                    </div>
                `;
                savesList.appendChild(item);
            });
        } else {
            savesList.innerHTML = '<div style="padding: 20px; text-align: center; color: #718096;">No saved websites yet</div>';
        }
        
    } catch (err) {
        console.error('Failed to load saved websites:', err);
        savesList.innerHTML = '<div style="padding: 20px; text-align: center; color: #e53e3e;">Error loading saves</div>';
    }
}

async function confirmSave() {
    const name = document.getElementById('website-name').value.trim();
    
    if (!name) {
        alert('Please enter a website name!');
        return;
    }
    
    try {
        const response = await fetch('/save-website', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                name: name
            }),
        });

        const data = await response.json();

        if (data.success) {
            closeModal('save-modal');
            document.getElementById('website-name').value = '';
            statusEl.textContent = `✅ Website saved as "${name}"!`;
            currentWebsiteId = data.id;
        } else {
            throw new Error(data.error || 'Failed to save website');
        }

    } catch (err) {
        console.error('Save error:', err);
        alert(`Error saving website: ${err.message}`);
    }
}

async function loadWebsite(websiteId) {
    try {
        console.log(`Loading website: ${websiteId}`);
        setState(STATES.WAIT);
        statusEl.textContent = '⏳ Loading website...';
        savesMenu.classList.remove('show');
        
        const response = await fetch(`/load-website/${websiteId}`);
        console.log(`Response status: ${response.status}`);
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error(`HTTP Error ${response.status}: ${errorText}`);
            throw new Error(`HTTP ${response.status}: ${errorText}`);
        }

        const data = await response.json();
        console.log('Response data:', data);

        if (data.success) {
            currentWebsiteId = websiteId;
            setState(STATES.EDIT);
            statusEl.innerHTML = `
🎉 Website "${data.name}" loaded successfully!<br>
🌐 Check your browser - it should open automatically<br><br>
✏️ You can now edit this website!
            `;
            console.log(`Website ${data.name} loaded successfully`);
        } else {
            throw new Error(data.error || 'Failed to load website');
        }

    } catch (err) {
        console.error('Load error:', err);
        statusEl.innerHTML = `
❌ Error loading website: ${err.message}<br><br>
🔄 Please try again or check the console for details.
        `;
        setState(STATES.RECORD);
    }
}

async function loadWebsiteForEdit(websiteId) {
    console.log(`Loading website for edit: ${websiteId}`);
    await loadWebsite(websiteId);
}

async function downloadWebsite(websiteId) {
    try {
        const response = await fetch(`/download-website/${websiteId}`);
        
        if (response.ok) {
            // Create blob and download
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            
            // Get filename from Content-Disposition header or use default
            const disposition = response.headers.get('Content-Disposition');
            let filename = 'website.html';
            if (disposition && disposition.includes('filename=')) {
                filename = disposition.split('filename=')[1].replace(/"/g, '');
            }
            
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            
            statusEl.textContent = `✅ Website downloaded successfully!`;
        } else {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Download failed');
        }
        
    } catch (err) {
        console.error('Download error:', err);
        statusEl.textContent = `Error downloading website: ${err.message}`;
    }
}

async function confirmDeleteWebsite(websiteId, websiteName) {
    if (confirm(`Are you sure you want to delete "${websiteName}"?\n\nThis action cannot be undone.`)) {
        await deleteWebsite(websiteId, websiteName);
    }
}

async function deleteWebsite(websiteId, websiteName) {
    try {
        const response = await fetch(`/delete-website/${websiteId}`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (data.success) {
            statusEl.textContent = `✅ Website "${websiteName}" deleted successfully!`;
            // Refresh the saves list
            loadSavedWebsites();
        } else {
            throw new Error(data.error || 'Failed to delete website');
        }

    } catch (err) {
        console.error('Delete error:', err);
        statusEl.textContent = `Error deleting website: ${err.message}`;
    }
}

// Modal functions
function openModal(modalId) {
    document.getElementById(modalId).style.display = 'block';
}

function closeModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}

// Close saves menu when clicking outside
document.addEventListener('click', (event) => {
    if (!savesBtn.contains(event.target) && !savesMenu.contains(event.target)) {
        savesMenu.classList.remove('show');
    }
});

// Close modals when clicking outside
window.addEventListener('click', (event) => {
    const modals = document.querySelectorAll('.modal');
    modals.forEach(modal => {
        if (event.target === modal) {
            modal.style.display = 'none';
        }
    });
});

// Initialize UI
updateUI();
