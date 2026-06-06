from http.server import BaseHTTPRequestHandler
import json,httpx,asyncio

OR_KEY='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'
OAI_KEY='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'
MIS_KEY='sIF6bOCJ8N2fI80Kax7uUfiGpHMSPtXy'
GRQ_KEY='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'

async def call_llm(msgs):
    for key,url,model in [(OR_KEY,'https://openrouter.ai/api/v1/chat/completions','anthropic/claude-3.5-sonnet'),(OAI_KEY,'https://api.openai.com/v1/chat/completions','gpt-4o-mini'),(MIS_KEY,'https://api.mistral.ai/v1/chat/completions','mistral-large-latest'),(GRQ_KEY,'https://api.groq.com/openai/v1/chat/completions','llama-3.3-70b-versatile')]:
        if not key:continue
        try:
            async with httpx.AsyncClient(timeout=90.0)as c:
                r=await c.post(url,headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'},json={'model':model,'messages':msgs,'temperature':0.6,'max_tokens':2500})
                if r.status_code==200:
                    content=r.json()['choices'][0]['message']['content']
                    if content and len(content)>50:return content
        except:continue
    return None

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
        msgs=body.get('messages',[])
        async def process():
            result=await call_llm(msgs)
            if result:
                words=result.split()
                acc=''
                self.send_response(200)
                self.send_header('Content-Type','text/event-stream')
                self.send_header('Cache-Control','no-cache')
                self.end_headers()
                for i in range(0,len(words),6):
                    acc+=' '.join(words[i:i+6])+' '
                    self.wfile.write(f"data: {json.dumps({'content':acc.strip()})}\n\n".encode())
                self.wfile.write(f"data: {json.dumps({'done':True})}\n\n".encode())
            else:
                self.send_response(200)
                self.send_header('Content-Type','text/event-stream')
                self.end_headers()
                self.wfile.write(f"data: {json.dumps({'content':'Unable to connect. Please try again.'})}\n\n".encode())
        asyncio.run(process())
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'status':'ok'}).encode())
