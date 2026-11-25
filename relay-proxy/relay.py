"""One upstream connection per student; forward payloads without interpreting them."""
import argparse
import asyncio
import logging
import json
import ssl
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

log = logging.getLogger('relay')

async def forward(source, destination, direction, trace):
    async for message in source:
        await destination.send(message)
        if trace:
            kind='binary'
            if isinstance(message,str):
                try:
                    data=json.loads(message)
                    kind=data.get('type','text') if isinstance(data,dict) else 'text'
                    if kind not in ('auth_request','auth_received','rtt_probe','rtt_echo','auth_result','error'):kind='text'
                except ValueError:kind='text'
            log.info('%s | %s | forwarded',direction,kind)

async def run(args):
    tls = None
    if args.cert:
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(args.cert, args.key)

    async def handle(client):
        log.info('Client connected: %s', client.remote_address)
        try:
            async with connect(args.upstream, max_size=8*1024*1024,
                               compression=None, ping_interval=None,
                               open_timeout=10) as upstream:
                tasks = [asyncio.create_task(forward(client, upstream, 'APP -> SERVER', args.trace)),
                         asyncio.create_task(forward(upstream, client, 'SERVER -> APP', args.trace))]
                try:
                    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        except ConnectionClosed:
            pass
        except Exception as exc:
            log.warning('Relay disconnected: %s', type(exc).__name__)
            await client.close(code=1011, reason='Upstream unavailable')
        finally:
            await client.close()
            log.info('Client disconnected')

    async with serve(handle, args.host, args.port, ssl=tls,
                     max_size=8*1024*1024, compression=None, ping_interval=None):
        log.info('Listening %s:%s -> %s', args.host, args.port, args.upstream)
        await asyncio.Future()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Attendance WebSocket relay')
    parser.add_argument('--upstream', required=True, help='ws://server:8000/ws or wss://...')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--cert')
    parser.add_argument('--key')
    parser.add_argument('--trace',action='store_true',help='Show forwarded message types for demo recording; adds logging overhead')
    args = parser.parse_args()
    if bool(args.cert) != bool(args.key):
        parser.error('--cert and --key must be supplied together')
    if not args.upstream.startswith(('ws://','wss://')):
        parser.error('--upstream must use ws:// or wss://')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass
