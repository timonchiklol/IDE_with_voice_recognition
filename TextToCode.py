import os
import re
import subprocess
import sys
import tempfile
import webbrowser
import http.server
import socketserver
import threading
import time
from textwrap import dedent
import google.generativeai as genai
from dotenv import load_dotenv
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=API_KEY)
SAVE_DIR = "generated_websites" # websites will be saved here
# Model initialization
model = genai.GenerativeModel('gemini-2.5-flash')

def _extract_html_code(text: str) -> str:
    """Extracts the first HTML code block from the model response.

    We expect the model to return code in the format:
    ```html
    # code
    ```
    """
    # Looking for ```html ... ``` blocks
    code_blocks = re.findall(r"```html(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if not code_blocks:
        # fallback: any ``` ... ``` block
        code_blocks = re.findall(r"```(.*?)```", text, re.DOTALL)
    if not code_blocks:
        return ""
    # Remove possible prefix/suffix empty lines
    return dedent(code_blocks[0].strip())


def generate_html_website(idea: str) -> str:
    """Requests HTML/CSS code from Gemini for the idea and returns the page text."""
    # Get key from environment variable (or specify directly as string)
    if not API_KEY:
        raise EnvironmentError("Environment variable GEMINI_API_KEY is not set")


    system_prompt = (
        "You are an experienced web developer. The user describes a website idea. "
        "Respond only with valid HTML code with embedded CSS, without explanations, "
        "wrapping it in a ```html ... ``` block. The site should be fully ready to work, "
        "beautiful, modern and responsive. Include all necessary styles directly in HTML."
    )

    # Compose full prompt
    full_prompt = f"{system_prompt}\n\nUser idea: {idea}"

    print("\nSending request to Gemini...\n")
    resp = model.generate_content(full_prompt)
    raw_answer = resp.text if hasattr(resp, "text") else str(resp)

    code = _extract_html_code(raw_answer)
    if not code:
        raise ValueError("Model did not return HTML code block")

    return code


def start_local_server(html_file_path: str, port: int = 8000):
    """Starts a local HTTP server to display HTML file."""
    
    class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/" or self.path == "/index.html":
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                try:
                    with open(html_file_path, "rb") as f:
                        self.wfile.write(f.read())
                except Exception as e:
                    self.wfile.write(f"File loading error: {e}".encode('utf-8'))
            else:
                super().do_GET()
    
    try:
        with socketserver.TCPServer(("", port), CustomHTTPRequestHandler) as httpd:
            print(f"Server started at http://localhost:{port}")
            print("Press Ctrl+C to stop the server")
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped")
    except Exception as e:
        print(f"Server startup error: {e}")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print('  python TextToCode.py "Your website idea"')
        print('  python TextToCode.py --file path/to/textfile.txt')
        sys.exit(1)

    # Check if user wants to read from file
    if sys.argv[1] == "--file" and len(sys.argv) >= 3:
        file_path = sys.argv[2]
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                idea = f.read().strip()
            print(f"Reading idea from file: {file_path}")
            print(f"Content: {idea[:100]}{'...' if len(idea) > 100 else ''}")
        except FileNotFoundError:
            print(f"Error: File '{file_path}' not found")
            sys.exit(1)
        except Exception as e:
            print(f"Error reading file: {e}")
            sys.exit(1)
    else:
        # Direct text from command line
        idea = " ".join(sys.argv[1:])
    
    if not idea.strip():
        print("Error: Empty idea provided")
        sys.exit(1)

    try:
        html_code = generate_html_website(idea)
    except Exception as err:
        print("Code generation error:", err)
        sys.exit(1)

    # Create temporary file for code
    os.makedirs(SAVE_DIR, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".html", encoding="utf-8", dir=SAVE_DIR) as tmp:
        tmp.write(html_code)
        tmp_path = tmp.name

    print(f"\nWebsite saved to temporary file: {tmp_path}\n")

    try:
        # Open website in browser
        time.sleep(1)  # Small pause for file creation
        
        # Start HTTP server in separate thread
        server_thread = threading.Thread(
            target=start_local_server, 
            args=(tmp_path, 8000), 
            daemon=True
        )
        server_thread.start()
        
        # Give server time to start
        time.sleep(2)
        
        # Open browser
        webbrowser.open("http://localhost:8000")
        
        print("Starting generated website...\n")
        print("Website available at: http://localhost:8000")
        
        # Wait for server completion
        server_thread.join()
        
    except Exception as err:
        print("Website startup error:", err)
    finally:
        # Keep file so user can study it. Can be deleted if desired.
        print(f"\nGenerated code: {'-'*40}\n{html_code}\n{'-'*40}")
        print(f"Code file: {tmp_path}")


if __name__ == "__main__":
    main()

