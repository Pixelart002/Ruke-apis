# ai_server.py
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests

# ========== CONFIG ==========
HOST = "0.0.0.0"
PORT = 8000
MISTRAL_BASE = "https://mistral-ai-three.vercel.app/"
TIMEOUT = 25
# ============================

def call_mistral(fullname: str, question: str) -> str:
    """Call your Mistral endpoint and return response text."""
    try:
        encoded_name = urllib.parse.quote_plus(fullname)
        encoded_q = urllib.parse.quote_plus(question)
        url = f"{MISTRAL_BASE}?id={encoded_name}&question={encoded_q}"

        res = requests.get(url, timeout=TIMEOUT)
        res.raise_for_status()

        if "application/json" in res.headers.get("Content-Type", ""):
            data = res.json()
            # try common response fields
            if isinstance(data, dict):
                for key in ("answer", "response", "text", "result"):
                    if key in data:
                        return str(data[key])
            return json.dumps(data)
        return res.text

    except Exception as e:
        return f"Error calling Mistral: {e}"

class SimpleAIHandler(BaseHTTPRequestHandler):
    """Minimal handler with one endpoint /ai"""

    def _set_headers(self, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def do_GET(self):
        """Handle GET /ai?fullname=...&question=..."""
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/ai":
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not Found"}).encode("utf-8"))
            return

        params = urllib.parse.parse_qs(parsed.query)
        fullname = params.get("fullname", [""])[0]
        question = params.get("question", [""])[0]

        if not fullname or not question:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "Missing fullname or question"}).encode("utf-8"))
            return

        answer = call_mistral(fullname, question)
        resp = {"fullname": fullname, "question": question, "answer": answer}

        self._set_headers(200)
        self.wfile.write(json.dumps(resp, ensure_ascii=False, indent=2).encode("utf-8"))

def run_server():
    """Run the HTTP server"""
    server_address = (HOST, PORT)
    httpd = HTTPServer(server_address, SimpleAIHandler)
    print(f"✅ Simple AI endpoint running at http://{HOST}:{PORT}/ai?fullname=John+Doe&question=Hello")
    httpd.serve_forever()

if __name__ == "__main__":
    run_server()