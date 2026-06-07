from http.server import BaseHTTPRequestHandler
import json, httpx, asyncio

OR_KEY = "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"

async def call_llm(msgs):
    try:
        async with httpx.AsyncClient(timeout=90.0) as c:
            r = await c.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": "Bearer " + OR_KEY,
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek/deepseek-chat",
                    "messages": msgs,
                    "temperature": 0.6,
                    "max_tokens": 2500
                }
            )
            if r.status_code == 200:
                content = r.json()["choices"][0]["message"]["content"]
                if content and len(content) > 50:
                    return content
    except:
        pass
    return None

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        msgs = body.get("messages", [])
        
        async def process():
            result = await call_llm(msgs)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            
            if result:
                words = result.split()
                acc = ""
                for i in range(0, len(words), 6):
                    acc += " ".join(words[i:i+6]) + " "
                    chunk = json.dumps({"content": acc.strip()})
                    self.wfile.write(("data: " + chunk + "\n\n").encode())
                self.wfile.write(("data: " + json.dumps({"done": True}) + "\n\n").encode())
            else:
                self.wfile.write(("data: " + json.dumps({"content": "Unable to connect. Please try again."}) + "\n\n").encode())
        
        asyncio.run(process())
    
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok"}).encode())
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()
