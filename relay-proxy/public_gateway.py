"""Public student assets + a single relay WebSocket; no administrator routes."""
import argparse
import asyncio
import logging
import ssl
from pathlib import Path
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from websockets.asyncio.client import connect

def create_app(upstream_url, ca=None, trace=False):
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    root=Path(__file__).resolve().parents[1]
    app.mount('/student',StaticFiles(directory=root/'student-app'/'dist',html=True),name='student')
    @app.get('/')
    async def home():return RedirectResponse('/student/')
    @app.websocket('/ws')
    async def relay(client:WebSocket):
        await client.accept()
        kwargs={}
        if upstream_url.startswith('wss:'):kwargs['ssl']=ssl.create_default_context(cafile=ca)
        try:
            async with connect(upstream_url,max_size=8*1024*1024,compression=None,ping_interval=None,**kwargs) as upstream:
                async def outbound():
                    while True:
                        msg=await client.receive()
                        if msg['type']=='websocket.disconnect':return
                        await upstream.send(msg.get('text') if msg.get('text') is not None else msg['bytes'])
                        if trace:logging.info('APP -> SERVER | forwarded')
                async def inbound():
                    async for msg in upstream:
                        if isinstance(msg,str):await client.send_text(msg)
                        else:await client.send_bytes(msg)
                        if trace:logging.info('SERVER -> APP | forwarded')
                tasks=[asyncio.create_task(outbound()),asyncio.create_task(inbound())]
                try:
                    done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
                    for task in done:task.result()
                finally:
                    for task in tasks:task.cancel()
                    await asyncio.gather(*tasks,return_exceptions=True)
        except Exception as exc:logging.info('Relay connection ended: %s',type(exc).__name__)
        finally:
            try:await client.close()
            except RuntimeError:pass
    return app

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--upstream',default='wss://localhost:8443/ws')
    p.add_argument('--ca',default='certs/ca.pem')
    p.add_argument('--port',type=int,default=8766)
    p.add_argument('--trace',action='store_true')
    args=p.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
    uvicorn.run(create_app(args.upstream,args.ca,args.trace),host='127.0.0.1',port=args.port,proxy_headers=False,ws_max_size=8*1024*1024,ws_per_message_deflate=False)
