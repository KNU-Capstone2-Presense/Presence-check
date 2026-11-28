import io
import json
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4
import qrcode
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse, JSONResponse, Response
from .auth import authenticate
from .config import load_settings
from .schemas import SessionCreate, PlaceRegistration, CalibrationSample, CalibrationApply
from .relay.calibration import calculate, apply as apply_calibration
from .auth import decode_image
from .place.service import register_place
from .store import Store
from .relay.collection import Collections
from .schemas import CollectionStart
from fastapi.staticfiles import StaticFiles

@asynccontextmanager
async def lifespan(app):
    app.state.settings = load_settings()
    app.state.store = Store(app.state.settings.data_dir)
    app.state.collections = Collections()
    yield

app = FastAPI(title='AttendanceDemo 서버', version='0.1.0', lifespan=lifespan)

@app.middleware('http')
async def local_admin(request: Request, call_next):
    # Administrator HTTP endpoints are restricted to this PC in the initial build.
    # /ws is the separate student endpoint and does not use this middleware.
    public_student=request.url.path.startswith('/student/')
    if not public_student and (request.client is None or request.client.host not in ('127.0.0.1', '::1', 'testclient')):
        return JSONResponse({'detail':'관리자 화면은 서버 PC에서 접속하세요'}, status_code=403)
    if request.method not in ('GET','HEAD','OPTIONS') and request.headers.get('x-attendance-admin') != '1':
        return JSONResponse({'detail':'관리자 요청 헤더가 필요합니다'}, status_code=403)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

student_dist=Path(__file__).resolve().parents[2]/'student-app'/'dist'
app.mount('/student',StaticFiles(directory=str(student_dist),html=True,check_dir=False),name='student')

@app.get('/api/collection')
def collection_status(request:Request):
    return request.app.state.collections.status()

@app.post('/api/collection/start')
async def collection_start(payload:CollectionStart,request:Request):
    try:return request.app.state.collections.start(payload,request.app.state.store)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.post('/api/collection/{run_id}/stop')
async def collection_stop(run_id:str,request:Request):
    run=request.app.state.collections.runs.get(run_id)
    if not run:raise HTTPException(404,'수집 기록 없음')
    run['stop']=True
    return run

@app.get('/api/evaluation')
def evaluation(request:Request):
    active=request.app.state.store.active_calibration()
    records=request.app.state.store.collection_records()
    rows=[r for r in records if r['purpose']=='evaluation' and active and r['result'].get('calibration_id')==active['id']]
    def rate(label):
        values=[r for r in rows if r['label']==label]
        return dict(count=len(values),percent=100*sum(r['result']['status']=='suspected' for r in values)/len(values) if values else None)
    return dict(direct=rate('direct'),relay=rate('relay'))

@app.get('/', include_in_schema=False)
def admin():
    return FileResponse(Path(__file__).parent / 'static' / 'index.html')

@app.get('/api/health')
def health(request: Request):
    s = request.app.state.settings
    active = request.app.state.store.active_calibration()
    return dict(status='ok', place_status='ready', rtt_samples=s.samples,
                rtt_warmups=s.warmups, threshold_ms=active['threshold_ms'] if active else s.threshold_ms, statistic='median')

@app.get('/admin-place.js', include_in_schema=False)
def admin_place_script():
    return FileResponse(Path(__file__).parent/'static'/'place.js',media_type='application/javascript')

@app.get('/admin-calibration.js', include_in_schema=False)
def admin_calibration_script():
    return FileResponse(Path(__file__).parent/'static'/'calibration.js',media_type='application/javascript')

@app.get('/api/calibration')
def calibration(request: Request):
    store=request.app.state.store
    samples=store.calibration_samples()
    return dict(samples=samples,candidate=calculate(samples),active=store.active_calibration())

@app.post('/api/calibration/samples')
def calibration_sample(payload: CalibrationSample, request: Request):
    try:request.app.state.store.tag_sample(str(payload.attempt_id),payload.label)
    except ValueError as exc:raise HTTPException(400,str(exc))
    return calibration(request)

@app.post('/api/calibration/apply')
def calibration_apply(payload: CalibrationApply, request: Request):
    try:return apply_calibration(request.app.state.store,payload.threshold_ms)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.get('/api/sessions')
def sessions(request: Request):
    return request.app.state.store.sessions()

@app.post('/api/sessions', status_code=201)
def create_session(payload: SessionCreate, request: Request):
    now = datetime.now(timezone.utc)
    item = dict(session_id=str(uuid4()), place_id=payload.place_id.strip(),
                token=secrets.token_urlsafe(24), created_at=now.isoformat(),
                expires_at='')
    closed = request.app.state.store.create_session(item)
    return dict(qr_payload(item), closed_sessions=closed)

def qr_payload(item):
    return {key:item[key] for key in ('session_id','place_id','token')}

@app.get('/api/sessions/{session_id}/qr')
def session_qr(session_id: UUID, request: Request):
    item = request.app.state.store.session(str(session_id))
    if not item:
        raise HTTPException(404, '세션을 찾을 수 없습니다')
    if not item['active']:
        raise HTTPException(410, '종료된 세션입니다')
    image = qrcode.make(json.dumps(qr_payload(item), ensure_ascii=False, separators=(',',':')))
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    return Response(stream.getvalue(), media_type='image/png')

@app.post('/api/sessions/{session_id}/close')
def close_session(session_id: UUID, request: Request):
    request.app.state.store.close_session(str(session_id))
    return {'status':'closed'}

@app.get('/api/attempts')
def attempts(request: Request, session_id: UUID | None = None):
    return request.app.state.store.attempts(str(session_id) if session_id else None)

@app.get('/api/attempts/{attempt_id}/image')
def attempt_image(attempt_id: UUID, request: Request):
    path = request.app.state.store.images / f'{attempt_id}.jpg'
    if not path.is_file():
        raise HTTPException(404, '이미지를 찾을 수 없습니다')
    return FileResponse(path, media_type='image/jpeg')

@app.websocket('/ws')
async def student(ws: WebSocket):
    await authenticate(ws, ws.app.state.store, ws.app.state.settings)

@app.post('/api/places', status_code=201)
def create_place(payload: PlaceRegistration, request: Request):
    try:raw=decode_image(payload.image)
    except ValueError as exc:raise HTTPException(400,str(exc))
    try:return register_place(request.app.state.settings.data_dir,payload,raw)
    except ValueError as exc:raise HTTPException(400,str(exc))

@app.get('/api/places')
def places(request: Request):
    root=request.app.state.settings.data_dir/'places'
    return [json.loads(p.read_text(encoding='utf-8')) for p in root.glob('*.json')]

@app.get('/api/references/{reference_id}')
def reference(reference_id: UUID, request: Request):
    path=request.app.state.settings.data_dir/'places'/f'{reference_id}.jpg'
    if not path.is_file():raise HTTPException(404,'기준 이미지가 없습니다')
    return FileResponse(path,media_type='image/jpeg')

@app.get('/api/attempts/{attempt_id}/matches')
def matches(attempt_id: UUID, request: Request):
    path=request.app.state.settings.data_dir/'matches'/f'{attempt_id}.jpg'
    if not path.is_file():raise HTTPException(404,'매칭 이미지가 없습니다')
    return FileResponse(path,media_type='image/jpeg')

@app.post('/api/sessions/{session_id}/clear')
def clear_session_attempts(session_id: UUID, request: Request):
    store=request.app.state.store
    if not store.session(str(session_id)):raise HTTPException(404,'세션 없음')
    store.clear_attempts(str(session_id))
    return {'status':'cleared'}

@app.post('/api/calibration/reset')
async def reset_calibration(request: Request):
    collections=request.app.state.collections
    if any(r['status']=='running' for r in collections.runs.values()):
        raise HTTPException(409,'반복 수집을 중지한 뒤 초기화하세요')
    request.app.state.store.reset_samples()
    collections.runs.clear()
    return calibration(request)
