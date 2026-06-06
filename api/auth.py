from http.server import BaseHTTPRequestHandler
import json
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Access-Control-Allow-Origin','*')
        self.end_headers()
        self.wfile.write(json.dumps({'status':'ok','user':{'id':'demo','email':body.get('email','')}}).encode())
