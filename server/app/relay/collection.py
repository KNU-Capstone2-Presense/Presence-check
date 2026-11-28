import asyncio
from dataclasses import replace
from uuid import uuid4
from .service import measure_rtt

class Collections:
    def __init__(self):
        self.clients={}
        self.runs={}

    def status(self, place_id):
        return dict(clients=[dict(id=k,student_id=v['request'].student_id,busy=v['busy']) for k,v in self.clients.items() if v['request'].place_id==place_id],runs=[r for r in self.runs.values() if r['place_id']==place_id][-20:])

    def start(self, payload, store):
        client=self.clients.get(payload.client_id)
        if not client or client['request'].place_id!=payload.place_id or client['busy']:raise ValueError('대기 중인 학생 앱을 선택하세요')
        active=store.active_calibration(payload.place_id)
        if payload.purpose=='evaluation' and active is None:raise ValueError('임계값을 먼저 적용하세요')
        run=dict(place_id=payload.place_id,id=str(uuid4()),client_id=payload.client_id,label=payload.label,purpose=payload.purpose,
                 requested=payload.count,completed=0,status='running',stop=False,calibration_id=active['id'] if active else None)
        client['busy']=True;self.runs[run['id']]=run
        client['queue'].put_nowait((run,active))
        return run

    async def connect(self, ws, request, store, settings, validate):
        client_id=str(uuid4());client=dict(request=request,busy=False,queue=asyncio.Queue())
        self.clients[client_id]=client
        await ws.send_json(dict(type='collection_ready',client_id=client_id))
        try:
            while True:
                job=asyncio.create_task(client['queue'].get())
                incoming=asyncio.create_task(ws.receive_text())
                try:
                    done,_=await asyncio.wait([job,incoming],return_when=asyncio.FIRST_COMPLETED)
                    if incoming in done:
                        incoming.result()
                        return
                    incoming.cancel();await asyncio.gather(incoming,return_exceptions=True)
                    run,active=job.result()
                finally:
                    for task in (job,incoming):
                        if not task.done():task.cancel()
                    await asyncio.gather(job,incoming,return_exceptions=True)
                current=replace(settings,threshold_ms=active['threshold_ms'] if active else None)
                try:
                    for i in range(run['requested']):
                        if run['stop']:break
                        validate(store,request)
                        record_id=str(uuid4())
                        result=await measure_rtt(ws,record_id,current)
                        result['calibration_id']=run['calibration_id']
                        store.add_collection_record(record_id,run['id'],run['label'],run['purpose'],result,request.place_id)
                        run['completed']+=1
                        await ws.send_json(dict(type='collection_progress',completed=run['completed'],total=run['requested']))
                    run['status']='stopped' if run['stop'] else 'complete'
                    await ws.send_json(dict(type='collection_done',completed=run['completed']))
                except Exception:
                    run['status']='error'
                    run['message']='연결 종료 또는 측정 응답 실패'
                    raise
                finally:client['busy']=False
        finally:
            self.clients.pop(client_id,None)
            for run in self.runs.values():
                if run['client_id']==client_id and run['status']=='running':run['status']='error'
