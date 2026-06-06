from http.server import BaseHTTPRequestHandler
import json,httpx,asyncio
from datetime import datetime
OR_KEY='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'
async def call_llm(msgs):
    try:
        async with httpx.AsyncClient(timeout=90.0)as c:
            r=await c.post('https://openrouter.ai/api/v1/chat/completions',headers={'Authorization':f'Bearer {OR_KEY}','Content-Type':'application/json'},json={'model':'anthropic/claude-3.5-sonnet','messages':msgs,'temperature':0.6,'max_tokens':3000})
            if r.status_code==200:
                content=r.json()['choices'][0]['message']['content']
                if content and len(content)>100:return content
    except:pass
    return None
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
        prompt=body.get('prompt','')
        title=body.get('title','CAPITAN AI Report')
        system='You are CAPITAN AI. Generate a professional research report. Structure impeccably.'
        content=asyncio.run(call_llm([{'role':'system','content':system},{'role':'user','content':prompt}]))
        resp={'title':title,'content':content or'Generation failed.','category':body.get('category','general')}
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Access-Control-Allow-Origin','*')
        self.end_headers()
        self.wfile.write(json.dumps(resp).encode())
