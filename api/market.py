from http.server import BaseHTTPRequestHandler
import json,httpx,asyncio,time
GNEWS='aade9f017c54d05388429a803e99018b'
_cache={}
_ctime=0
async def prices():
    global _cache,_ctime
    now=time.time()
    if _cache and (now-_ctime)<30:return _cache
    tickers={'^GSPC':'S&P 500','^IXIC':'NASDAQ','AAPL':'Apple','MSFT':'Microsoft','NVDA':'Nvidia','TSLA':'Tesla','GC=F':'Gold','SI=F':'Silver','CL=F':'Crude Oil WTI','EURUSD=X':'EUR/USD','GBPUSD=X':'GBP/USD'}
    syms=list(tickers.keys())
    results={}
    try:
        async with httpx.AsyncClient(timeout=10.0)as c:
            for i in range(0,len(syms),10):
                batch=','.join(syms[i:i+10])
                r=await c.get(f'https://query1.finance.yahoo.com/v7/finance/quote?symbols={batch}',headers={'User-Agent':'Mozilla/5.0'})
                if r.status_code==200:
                    for item in r.json().get('quoteResponse',{}).get('result',[]):
                        pr=item.get('regularMarketPrice');pv=item.get('regularMarketPreviousClose')
                        if pr and pv and pr>0 and pv>0:
                            sym=item.get('symbol','')
                            if sym in tickers:results[tickers[sym]]={'price':pr,'change_pct':round(((pr-pv)/pv)*100,2)}
    except:pass
    try:
        async with httpx.AsyncClient(timeout=8.0)as c:
            r=await c.get('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd&include_24hr_change=true')
            if r.status_code==200:
                cg=r.json()
                for n,cid in[('Bitcoin','bitcoin'),('Ethereum','ethereum'),('Solana','solana')]:
                    if cid in cg and'usd'in cg[cid]:results[n]={'price':cg[cid]['usd'],'change_pct':round(cg[cid].get('usd_24h_change',0),2)}
    except:pass
    _cache=results;_ctime=now
    return results
class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data=asyncio.run(prices())
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Access-Control-Allow-Origin','*')
        self.end_headers()
        self.wfile.write(json.dumps({'data':data}).encode())
