from flask import Flask, render_template, request, jsonify, send_file
import os
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import assemblyai as aai
import google.generativeai as genai
import sys
import subprocess
import json


app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
IMPROVED_TEXTS_FOLDER = "improved_texts"
LOGS_FOLDER = "logs"
WEBSITES_FOLDER = "generated_websites"
SAVED_WEBSITES_FOLDER = "saved_websites"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(IMPROVED_TEXTS_FOLDER, exist_ok=True)
os.makedirs(LOGS_FOLDER, exist_ok=True)
os.makedirs(WEBSITES_FOLDER, exist_ok=True)
os.makedirs(SAVED_WEBSITES_FOLDER, exist_ok=True)


def log_operation(operation: str, details: dict = None, status: str = "success"):
    """Log operation with timestamp and details."""
    try:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        log_entry = {
            "timestamp": timestamp,
            "operation": operation,
            "status": status,
            "details": details or {}
        }
        
        # Save to daily log file
        date_str = datetime.utcnow().strftime("%Y%m%d")
        log_file_path = os.path.join(LOGS_FOLDER, f"log_{date_str}.json")
        
        # Read existing logs or create empty list
        logs = []
        if os.path.exists(log_file_path):
            try:
                with open(log_file_path, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                logs = []
        
        # Add new log entry
        logs.append(log_entry)
        
        # Keep only last 100 entries per day
        if len(logs) > 100:
            logs = logs[-100:]
        
        # Save updated logs
        with open(log_file_path, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)
            
        print(f"[LOG] {operation}: {status}")
        
    except Exception as e:
        print(f"Failed to log operation: {e}")


def get_recent_logs(days: int = 7) -> list:
    """Get recent logs from the last N days."""
    all_logs = []
    
    try:
        for i in range(days):
            date = datetime.utcnow() - timedelta(days=i)
            date_str = date.strftime("%Y%m%d")
            log_file_path = os.path.join(LOGS_FOLDER, f"log_{date_str}.json")
            
            if os.path.exists(log_file_path):
                try:
                    with open(log_file_path, "r", encoding="utf-8") as f:
                        daily_logs = json.load(f)
                        all_logs.extend(daily_logs)
                except (json.JSONDecodeError, FileNotFoundError):
                    continue
        
        # Sort by timestamp (newest first)
        all_logs.sort(key=lambda x: x["timestamp"], reverse=True)
        return all_logs[:50]  # Return last 50 logs
        
    except Exception as e:
        print(f"Failed to get logs: {e}")
        return []


def save_improved_text(improved_text: str) -> str:
    """Save only the improved text to a file and return the file path."""
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"improved_text_{timestamp}.txt"
    file_path = os.path.join(IMPROVED_TEXTS_FOLDER, filename)
    
    # Save only the clean improved text without any additional info
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(improved_text)
        
        log_operation("save_text", {
            "filename": filename,
            "text_length": len(improved_text),
            "text_preview": improved_text[:100] + "..." if len(improved_text) > 100 else improved_text
        })
        
        return file_path
    except Exception as e:
        log_operation("save_text", {"error": str(e), "filename": filename}, "error")
        print(f"Error saving improved text: {e}")
        return ""


def ask_gemini(user_text: str) -> str:
    """Send text to Google Gemini to improve dictated text quality."""
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        log_operation("gemini_request", {"error": "API key not set"}, "error")
        print("GEMINI_API_KEY is not set")
        return user_text  # Return original text if Gemini is not available

    genai.configure(api_key=gemini_key)

    try:
        with open("prompt.txt", "r", encoding="utf-8") as f:
            base_prompt = f.read().strip()
    except FileNotFoundError:
        # Default prompt if file not found
        base_prompt = "Please improve the following dictated text by correcting grammar, adding punctuation, and making it more readable: {input}"

    if "{input}" in base_prompt:
        final_prompt = base_prompt.replace("{input}", user_text)
    else:
        final_prompt = f"{base_prompt}\n\nText to improve: {user_text}"

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        resp = model.generate_content(final_prompt)
        improved_text = resp.text if hasattr(resp, "text") else str(resp)
        
        log_operation("gemini_request", {
            "original_length": len(user_text),
            "improved_length": len(improved_text.strip()),
            "original_preview": user_text[:50] + "..." if len(user_text) > 50 else user_text
        })
        
        return improved_text.strip()
    except Exception as err:
        log_operation("gemini_request", {"error": str(err)}, "error")
        print("Gemini error:", err)
        return user_text  # Return original text if error occurs


def _extract_html_code(text: str) -> str:
    """Extracts the first HTML code block from the model response."""
    import re
    from textwrap import dedent
    
    # Looking for ```html ... ``` blocks
    code_blocks = re.findall(r"```html(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if not code_blocks:
        # fallback: any ``` ... ``` block
        code_blocks = re.findall(r"```(.*?)```", text, re.DOTALL)
    if not code_blocks:
        return ""
    # Remove possible prefix/suffix empty lines
    return dedent(code_blocks[0].strip())


def edit_website(website_path: str, edit_instructions: str) -> dict:
    """Edit existing website using Gemini with new instructions."""
    try:
        # Read existing website
        with open(website_path, "r", encoding="utf-8") as f:
            current_html = f.read()
        
        # Create prompt for editing
        edit_prompt = f"""You are an experienced web developer. I have an existing website and need you to modify it based on new instructions.

Current website HTML:
```html
{current_html}
```

Modification instructions: {edit_instructions}

Please provide the updated HTML code with all the requested changes. Respond only with the complete HTML code wrapped in ```html ... ``` block. The site should remain functional and beautiful."""

        # Send to Gemini
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            return {"success": False, "error": "GEMINI_API_KEY not set"}
        
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel("gemini-pro")
        resp = model.generate_content(edit_prompt)
        
        # Extract HTML code
        updated_html = _extract_html_code(resp.text)
        
        if not updated_html:
            return {"success": False, "error": "No valid HTML returned from Gemini"}
        
        # Save updated website
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        new_filename = f"edited_website_{timestamp}.html"
        new_path = os.path.join(WEBSITES_FOLDER, new_filename)
        
        with open(new_path, "w", encoding="utf-8") as f:
            f.write(updated_html)
        
        log_operation("edit_website", {
            "original_file": os.path.basename(website_path),
            "new_file": new_filename,
            "edit_instructions": edit_instructions[:100] + "..." if len(edit_instructions) > 100 else edit_instructions
        })
        
        return {
            "success": True,
            "new_file": new_filename,
            "new_path": new_path,
            "updated_html": updated_html
        }
        
    except Exception as e:
        log_operation("edit_website", {"error": str(e)}, "error")
        return {"success": False, "error": str(e)}


def generate_website_from_text_file(text_file_path: str) -> dict:
    """Generate website using TextToCode.py with the saved text file."""
    try:
        # Run TextToCode.py with the text file
        script_path = os.path.join(os.path.dirname(__file__), "TextToCode.py")
        cmd = [sys.executable, script_path, "--file", text_file_path]
        
        print(f"Running: {' '.join(cmd)}")
        
        # Start the process in background and return immediately
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        log_operation("generate_website", {
            "text_file": os.path.basename(text_file_path),
            "process_id": process.pid
        })
        
        return {
            "success": True,
            "message": "Website generation started! Check your browser.",
            "process_id": process.pid
        }
        
    except Exception as e:
        log_operation("generate_website", {"error": str(e)}, "error")
        return {
            "success": False,
            "error": f"Failed to start website generation: {str(e)}"
        }


def process_audio(file_path: str):
    log_operation("audio_processing_start", {"file": os.path.basename(file_path)})
    
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        log_operation("audio_processing", {"error": "AssemblyAI API key not set"}, "error")
        return {"error": "AssemblyAI API key is not set"}

    aai.settings.api_key = api_key

    # Model settings - by default we take the best available.
    config = aai.TranscriptionConfig(speech_model=aai.SpeechModel.best)

    try:
        transcript = aai.Transcriber(config=config).transcribe(file_path)
    except Exception as err:
        log_operation("audio_processing", {"error": f"AssemblyAI request: {str(err)}"}, "error")
        return {"error": f"AssemblyAI request error: {err}"}

    if transcript.status == "error":
        log_operation("audio_processing", {"error": f"Transcription failed: {transcript.error}"}, "error")
        return {"error": transcript.error}

    original_text = transcript.text
    print("Original dictated text:", original_text)
    
    log_operation("speech_recognition", {
        "text_length": len(original_text),
        "text_preview": original_text[:100] + "..." if len(original_text) > 100 else original_text
    })

    # Improve the text using Gemini
    improved_text = ask_gemini(original_text)
    print("Improved text:", improved_text)

    # Save only the improved text to file
    saved_file_path = save_improved_text(improved_text)
    
    # Delete the audio file after processing
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Audio file deleted: {file_path}")
            log_operation("audio_cleanup", {"deleted_file": os.path.basename(file_path)})
    except Exception as delete_err:
        log_operation("audio_cleanup", {"error": str(delete_err)}, "error")
        print(f"Failed to delete audio file: {delete_err}")
    
    # Clean up old text files, keeping only the last 10
    try:
        files = sorted(os.listdir(IMPROVED_TEXTS_FOLDER), reverse=True)
        for old_file in files[10:]:  # Keep last 10 files
            old_path = os.path.join(IMPROVED_TEXTS_FOLDER, old_file)
            if os.path.isfile(old_path):
                os.remove(old_path)
        if len(files) > 10:
            log_operation("text_cleanup", {"deleted_files": len(files) - 10})
    except Exception as cleanup_err:
        log_operation("text_cleanup", {"error": str(cleanup_err)}, "error")
        print(f"Failed to clean improved_texts folder: {cleanup_err}")

    log_operation("audio_processing_complete", {
        "original_length": len(original_text),
        "improved_length": len(improved_text),
        "saved_file": os.path.basename(saved_file_path) if saved_file_path else None
    })

    return {
        "original_text": original_text,
        "improved_text": improved_text,
        "saved_file": os.path.basename(saved_file_path) if saved_file_path else "",
        "file_path": saved_file_path,
        "audio_deleted": True,
    }


def get_saved_websites_metadata():
    """Get metadata for all saved websites."""
    metadata_file = os.path.join(SAVED_WEBSITES_FOLDER, "metadata.json")
    
    if os.path.exists(metadata_file):
        try:
            with open(metadata_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {"websites": []}
    else:
        return {"websites": []}


def save_websites_metadata(metadata):
    """Save metadata for all saved websites."""
    metadata_file = os.path.join(SAVED_WEBSITES_FOLDER, "metadata.json")
    
    try:
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Failed to save metadata: {e}")
        return False


def get_latest_website_file():
    """Get the path to the most recently generated website."""
    try:
        # Check DIR_TO_SAVE first (from TextToCode.py)
        if os.path.exists("DIR_TO_SAVE"):
            files = [f for f in os.listdir("DIR_TO_SAVE") if f.endswith('.html')]
            if files:
                files.sort(reverse=True)  # newest first
                return os.path.join("DIR_TO_SAVE", files[0])
        
        # Check generated_websites folder
        if os.path.exists(WEBSITES_FOLDER):
            files = [f for f in os.listdir(WEBSITES_FOLDER) if f.endswith('.html')]
            if files:
                files.sort(reverse=True)
                return os.path.join(WEBSITES_FOLDER, files[0])
        
        return None
        
    except Exception as e:
        print(f"Error finding latest website: {e}")
        return None


@app.route("/")
def index():
    """Return the main page."""
    return render_template("index.html")


@app.route("/files")
def list_files():
    """Return list of saved improved text files."""
    try:
        files = []
        if os.path.exists(IMPROVED_TEXTS_FOLDER):
            file_names = sorted(os.listdir(IMPROVED_TEXTS_FOLDER), reverse=True)
            for filename in file_names:
                if filename.endswith('.txt'):
                    file_path = os.path.join(IMPROVED_TEXTS_FOLDER, filename)
                    file_size = os.path.getsize(file_path)
                    file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                    files.append({
                        "name": filename,
                        "size": file_size,
                        "modified": file_time.strftime("%Y-%m-%d %H:%M:%S")
                    })
        return jsonify({"files": files})
    except Exception as e:
        return jsonify({"error": f"Failed to list files: {e}"}), 500


@app.route("/files/<filename>")
def get_file(filename):
    """Return content of a specific saved text file."""
    try:
        safe_filename = secure_filename(filename)
        file_path = os.path.join(IMPROVED_TEXTS_FOLDER, safe_filename)
        
        if not os.path.exists(file_path) or not file_path.endswith('.txt'):
            return jsonify({"error": "File not found"}), 404
            
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        return jsonify({"filename": safe_filename, "content": content})
    except Exception as e:
        return jsonify({"error": f"Failed to read file: {e}"}), 500


@app.route("/process", methods=["POST"])
def process():
    """Accept audio file from client and return text improvement result."""
    if "audio" not in request.files:
        return jsonify({"error": "Audio file not found in request"}), 400

    raw_file = request.files["audio"]
    filename = secure_filename(raw_file.filename)
    if not filename:
        filename = "recording.webm"

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    full_filename = f"{timestamp}_{filename}"
    file_path = os.path.join(UPLOAD_FOLDER, full_filename)

    raw_file.save(file_path)

    # Process audio and improve text (audio will be deleted inside process_audio)
    result = process_audio(file_path)

    return jsonify(result)


@app.route("/generate-website", methods=["POST"])
def generate_website():
    """Generate website from the latest saved text file."""
    try:
        data = request.get_json() or {}
        filename = data.get("filename")
        
        if filename:
            # Use specific file
            file_path = os.path.join(IMPROVED_TEXTS_FOLDER, secure_filename(filename))
        else:
            # Use latest file
            files = sorted(os.listdir(IMPROVED_TEXTS_FOLDER), reverse=True)
            text_files = [f for f in files if f.endswith('.txt')]
            if not text_files:
                return jsonify({"error": "No text files found"}), 400
            file_path = os.path.join(IMPROVED_TEXTS_FOLDER, text_files[0])
        
        if not os.path.exists(file_path):
            return jsonify({"error": "Text file not found"}), 404
            
        result = generate_website_from_text_file(file_path)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"error": f"Failed to generate website: {str(e)}"}), 500


@app.route("/logs")
def get_logs():
    """Return recent logs."""
    try:
        logs = get_recent_logs(days=7)
        return jsonify({"logs": logs})
    except Exception as e:
        return jsonify({"error": f"Failed to get logs: {str(e)}"}), 500


@app.route("/edit-website", methods=["POST"])
def edit_website_endpoint():
    """Edit existing website with new instructions."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        edit_instructions = data.get("instructions", "").strip()
        website_file = data.get("website_file", "").strip()
        
        if not edit_instructions:
            return jsonify({"error": "Edit instructions are required"}), 400
        
        # Find the website file to edit
        if website_file:
            # Use specific file from generated websites
            website_path = os.path.join(WEBSITES_FOLDER, secure_filename(website_file))
            if not os.path.exists(website_path):
                # Try DIR_TO_SAVE folder
                website_path = os.path.join("DIR_TO_SAVE", secure_filename(website_file))
        else:
            # Use the most recent website
            try:
                # Check DIR_TO_SAVE first (from TextToCode.py)
                if os.path.exists("DIR_TO_SAVE"):
                    files = [f for f in os.listdir("DIR_TO_SAVE") if f.endswith('.html')]
                    if files:
                        files.sort(reverse=True)  # newest first
                        website_path = os.path.join("DIR_TO_SAVE", files[0])
                    else:
                        return jsonify({"error": "No website files found to edit"}), 400
                else:
                    return jsonify({"error": "No website files found to edit"}), 400
            except Exception as e:
                return jsonify({"error": f"Error finding website files: {str(e)}"}), 400
        
        if not os.path.exists(website_path):
            return jsonify({"error": "Website file not found"}), 404
        
        # Edit the website
        result = edit_website(website_path, edit_instructions)
        
        if result["success"]:
            # Start local server with the new website
            try:
                script_path = os.path.join(os.path.dirname(__file__), "TextToCode.py")
                # Create a simple launcher for the new website
                cmd = [sys.executable, "-c", f"""
import webbrowser
import http.server
import socketserver
import threading
import time
import os

def start_server():
    os.chdir('{WEBSITES_FOLDER}')
    with socketserver.TCPServer(('', 8001), http.server.SimpleHTTPRequestHandler) as httpd:
        httpd.serve_forever()

server_thread = threading.Thread(target=start_server, daemon=True)
server_thread.start()
time.sleep(1)
webbrowser.open('http://localhost:8001/{result["new_file"]}')
server_thread.join()
                """]
                
                subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
                result["browser_url"] = f"http://localhost:8001/{result['new_file']}"
                
            except Exception as e:
                print(f"Failed to start server for edited website: {e}")
        
        return jsonify(result)
        
    except Exception as e:
        log_operation("edit_website_endpoint", {"error": str(e)}, "error")
        return jsonify({"error": f"Failed to edit website: {str(e)}"}), 500


@app.route("/saved-websites")
def get_saved_websites():
    """Return list of saved websites."""
    try:
        metadata = get_saved_websites_metadata()
        # Sort by creation date (newest first)
        websites = sorted(metadata.get("websites", []), 
                         key=lambda x: x.get("created_at", ""), reverse=True)
        return jsonify({"websites": websites})
    except Exception as e:
        log_operation("get_saved_websites", {"error": str(e)}, "error")
        return jsonify({"error": f"Failed to get saved websites: {str(e)}"}), 500


@app.route("/save-website", methods=["POST"])
def save_website():
    """Save current website with a name."""
    try:
        data = request.get_json()
        if not data or not data.get("name"):
            return jsonify({"error": "Website name is required"}), 400
        
        website_name = data["name"].strip()
        if not website_name:
            return jsonify({"error": "Website name cannot be empty"}), 400
        
        # Find the latest website file
        latest_website = get_latest_website_file()
        if not latest_website or not os.path.exists(latest_website):
            return jsonify({"error": "No website found to save"}), 400
        
        # Generate unique ID
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        website_id = f"site_{timestamp}"
        
        # Read current website content
        with open(latest_website, "r", encoding="utf-8") as f:
            website_content = f.read()
        
        # Save website file
        saved_file_path = os.path.join(SAVED_WEBSITES_FOLDER, f"{website_id}.html")
        with open(saved_file_path, "w", encoding="utf-8") as f:
            f.write(website_content)
        
        # Update metadata
        metadata = get_saved_websites_metadata()
        new_website = {
            "id": website_id,
            "name": website_name,
            "created_at": datetime.utcnow().isoformat(),
            "file_path": f"{website_id}.html"
        }
        
        metadata["websites"].append(new_website)
        
        if save_websites_metadata(metadata):
            log_operation("save_website", {
                "website_id": website_id,
                "name": website_name
            })
            
            return jsonify({
                "success": True,
                "id": website_id,
                "name": website_name,
                "message": f"Website '{website_name}' saved successfully"
            })
        else:
            return jsonify({"error": "Failed to save website metadata"}), 500
        
    except Exception as e:
        log_operation("save_website", {"error": str(e)}, "error")
        return jsonify({"error": f"Failed to save website: {str(e)}"}), 500


def find_free_port(start_port=8000, max_port=8100):
    """Find a free port starting from start_port."""
    import socket
    for port in range(start_port, max_port):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            continue
    return None


@app.route("/load-website/<website_id>")
def load_website(website_id):
    """Load a saved website."""
    try:
        print(f"Loading website with ID: {website_id}")
        
        # Get metadata
        metadata = get_saved_websites_metadata()
        websites = metadata.get("websites", [])
        
        print(f"Found {len(websites)} saved websites")
        
        # Find the website
        website = None
        for site in websites:
            if site["id"] == website_id:
                website = site
                break
        
        if not website:
            print(f"Website {website_id} not found")
            return jsonify({"error": "Website not found"}), 404
        
        print(f"Found website: {website['name']}")
        
        # Check if file exists
        website_file = os.path.join(SAVED_WEBSITES_FOLDER, website["file_path"])
        print(f"Looking for file: {website_file}")
        
        if not os.path.exists(website_file):
            print(f"Website file not found: {website_file}")
            return jsonify({"error": "Website file not found"}), 404
        
        # Copy website to DIR_TO_SAVE so it can be opened
        if not os.path.exists("DIR_TO_SAVE"):
            os.makedirs("DIR_TO_SAVE", exist_ok=True)
        
        # Read saved website
        with open(website_file, "r", encoding="utf-8") as f:
            website_content = f.read()
        
        # Save to DIR_TO_SAVE with simple name  
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        new_filename = f"current_website.html"
        new_path = os.path.join("DIR_TO_SAVE", new_filename)
        
        with open(new_path, "w", encoding="utf-8") as f:
            f.write(website_content)
        
        print(f"Website copied to: {new_path}")
        
        # Find free port
        port = find_free_port()
        if not port:
            port = 8000  # fallback
        
        print(f"Using port: {port}")
        
        # Start server using TextToCode logic
        try:
            # Use direct webbrowser opening first
            import webbrowser
            file_url = f"file://{os.path.abspath(new_path)}"
            webbrowser.open(file_url)
            print(f"Opened file directly: {file_url}")
            
            # Also try to start HTTP server
            server_script = f"""
import http.server
import socketserver
import webbrowser
import threading
import time
import os

os.chdir(r'{os.path.abspath("DIR_TO_SAVE")}')

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.path = "/{new_filename}"
        return super().do_GET()

try:
    with socketserver.TCPServer(("", {port}), Handler) as httpd:
        print(f"HTTP Server started at http://localhost:{port}")
        threading.Thread(target=lambda: (time.sleep(2), webbrowser.open(f"http://localhost:{port}")), daemon=True).start()
        httpd.serve_forever()
except Exception as e:
    print(f"Server error: {{e}}")
"""
            
            # Write and run server script
            script_file = os.path.join("DIR_TO_SAVE", "temp_server.py")
            with open(script_file, "w", encoding="utf-8") as f:
                f.write(server_script)
            
            subprocess.Popen([sys.executable, script_file], 
                           stdout=subprocess.PIPE, 
                           stderr=subprocess.PIPE)
            
            print("HTTP server process started")
            
        except Exception as e:
            print(f"Failed to start server: {e}")
        
        log_operation("load_website", {
            "website_id": website_id,
            "name": website["name"],
            "port": port
        })
        
        return jsonify({
            "success": True,
            "name": website["name"],
            "id": website_id,
            "port": port,
            "message": f"Website '{website['name']}' loaded successfully"
        })
        
    except Exception as e:
        print(f"Error loading website: {e}")
        import traceback
        traceback.print_exc()
        log_operation("load_website", {"error": str(e), "website_id": website_id}, "error")
        return jsonify({"error": f"Failed to load website: {str(e)}"}), 500


@app.route("/download-website/<website_id>")
def download_website(website_id):
    """Download a saved website file."""
    try:
        # Get metadata
        metadata = get_saved_websites_metadata()
        websites = metadata.get("websites", [])
        
        # Find the website
        website = None
        for site in websites:
            if site["id"] == website_id:
                website = site
                break
        
        if not website:
            return jsonify({"error": "Website not found"}), 404
        
        # Check if file exists
        website_file = os.path.join(SAVED_WEBSITES_FOLDER, website["file_path"])
        if not os.path.exists(website_file):
            return jsonify({"error": "Website file not found"}), 404
        
        # Clean filename for download
        safe_name = "".join(c for c in website["name"] if c.isalnum() or c in (' ', '-', '_')).rstrip()
        download_filename = f"{safe_name}.html"
        
        log_operation("download_website", {
            "website_id": website_id,
            "name": website["name"]
        })
        
        return send_file(
            website_file, 
            as_attachment=True, 
            download_name=download_filename,
            mimetype='text/html'
        )
        
    except Exception as e:
        log_operation("download_website", {"error": str(e), "website_id": website_id}, "error")
        return jsonify({"error": f"Failed to download website: {str(e)}"}), 500


@app.route("/delete-website/<website_id>", methods=["DELETE"])
def delete_website(website_id):
    """Delete a saved website."""
    try:
        # Get metadata
        metadata = get_saved_websites_metadata()
        websites = metadata.get("websites", [])
        
        # Find the website
        website = None
        website_index = None
        for i, site in enumerate(websites):
            if site["id"] == website_id:
                website = site
                website_index = i
                break
        
        if not website:
            return jsonify({"error": "Website not found"}), 404
        
        # Delete website file
        website_file = os.path.join(SAVED_WEBSITES_FOLDER, website["file_path"])
        if os.path.exists(website_file):
            os.remove(website_file)
        
        # Update metadata - remove website from list
        websites.pop(website_index)
        metadata["websites"] = websites
        
        if save_websites_metadata(metadata):
            log_operation("delete_website", {
                "website_id": website_id,
                "name": website["name"]
            })
            
            return jsonify({
                "success": True,
                "message": f"Website '{website['name']}' deleted successfully"
            })
        else:
            return jsonify({"error": "Failed to update metadata"}), 500
        
    except Exception as e:
        log_operation("delete_website", {"error": str(e), "website_id": website_id}, "error")
        return jsonify({"error": f"Failed to delete website: {str(e)}"}), 500


@app.route("/debug/websites")
def debug_websites():
    """Debug endpoint to check saved websites state."""
    try:
        debug_info = {}
        
        # Check folders
        debug_info["folders"] = {
            "SAVED_WEBSITES_FOLDER": {
                "path": SAVED_WEBSITES_FOLDER,
                "exists": os.path.exists(SAVED_WEBSITES_FOLDER),
                "files": os.listdir(SAVED_WEBSITES_FOLDER) if os.path.exists(SAVED_WEBSITES_FOLDER) else []
            },
            "DIR_TO_SAVE": {
                "path": "DIR_TO_SAVE",
                "exists": os.path.exists("DIR_TO_SAVE"), 
                "files": os.listdir("DIR_TO_SAVE") if os.path.exists("DIR_TO_SAVE") else []
            }
        }
        
        # Check metadata
        metadata = get_saved_websites_metadata()
        debug_info["metadata"] = metadata
        
        # Check latest website
        latest = get_latest_website_file()
        debug_info["latest_website"] = {
            "path": latest,
            "exists": os.path.exists(latest) if latest else False
        }
        
        return jsonify(debug_info)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # debug=True should not be used in production
    app.run(debug=True)
