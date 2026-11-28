import asyncio
import base64
import binascii
import io
import json
import logging
import secrets
import warnings
from dataclasses import replace
from datetime import datetime, timezone
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect
from .schemas import AuthRequest, PlaceResult, CollectionReady
from .place.service import verify_place
from .relay.service import measure_rtt

log = logging.getLogger(__name__)

def decode_image(payload):
    try:
        raw = base64.b64decode(payload.data_base64, validate=True)
        if len(raw) > 4_000_000:
            raise ValueError('이미지가 너무 큽니다')
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format != 'JPEG' or max(image.size)>4096 or min(image.size)<1:
                    raise ValueError('지원하지 않는 이미지입니다')
                image.verify()
        return raw
    except (binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('이미지 파일을 확인하세요')

def valid_session(store, request):
    item = store.session(request.session_id)
    if not item or not item['active']:
        raise ValueError('종료된 세션입니다')
    if request.place_id != item['place_id'] or not secrets.compare_digest(request.token, item['token']):
        raise ValueError('QR 정보가 일치하지 않습니다')

async def authenticate(ws, store, settings):
    await ws.accept()
    while True:
        attempt_id = None
        reserved = False
        try:
            text = await ws.receive_text()
            if len(text)>6_100_000:
                await ws.close(code=1009)
                return
            data = json.loads(text)
            if isinstance(data,dict) and data.get('type')=='collection_ready':
                request=CollectionReady.model_validate(data)
                valid_session(store,request)
                await ws.app.state.collections.connect(ws,request,store,settings,valid_session)
                await ws.close()
                return
            if isinstance(data, dict) and isinstance(data.get('attempt_id'), str):
                attempt_id = data['attempt_id'][:80]
            request = AuthRequest.model_validate(data)
            attempt_id = str(request.attempt_id)
            valid_session(store, request)
            raw = await asyncio.to_thread(decode_image, request.image)
            reserved = store.reserve(attempt_id, request.session_id, request.student_id.strip())
            if not reserved:
                raise ValueError('이미 처리 중이거나 처리된 인증 요청입니다')
            image_path = store.images / f'{attempt_id}.jpg'
            await asyncio.to_thread(image_path.write_bytes, raw)
            await ws.send_json(dict(type='auth_received', attempt_id=attempt_id))
            calibration = store.active_calibration(request.place_id)
            current_settings = replace(settings, threshold_ms=calibration['threshold_ms'] if calibration else None)
            relay = await measure_rtt(ws, attempt_id, current_settings)
            relay['calibration_id'] = calibration['id'] if calibration else None
            try:
                place = await asyncio.wait_for(asyncio.to_thread(verify_place, request.place_id, image_path, request.qr_polygon), timeout=60)
                place = PlaceResult.model_validate(place)
            except Exception:
                log.exception('Place verification failed')
                place = PlaceResult(status='inconclusive', decision='장소 판정 불가', reason='장소 검증 오류 또는 시간 초과')
            # Recheck expiry/closure before any approval.
            valid_session(store, request)
            approved = place.status == 'match' and relay['status'] == 'within_bound'
            result = dict(type='auth_result', attempt_id=attempt_id,
                          decision='approved' if approved else 'review',
                          place=place.model_dump(), relay=relay)
            store.complete(attempt_id, 'complete', result)
            reserved = False
            await ws.send_json(result)
        except WebSocketDisconnect:
            if reserved:
                store.complete(attempt_id, 'interrupted', {'message':'연결 종료'})
            return
        except (ValueError, ValidationError, asyncio.TimeoutError) as exc:
            message = '측정 응답 시간이 초과되었습니다' if isinstance(exc, asyncio.TimeoutError) else (
                '인증 요청 형식을 확인하세요' if isinstance(exc, ValidationError) else str(exc))
            if reserved:
                store.complete(attempt_id, 'error', {'message':message})
            await ws.send_json(dict(type='error', attempt_id=attempt_id, message=message))
            # Discard late echoes by closing failed measurement connections.
            if reserved:
                await ws.close(code=1000)
                return
        except Exception:
            log.exception('Authentication failed')
            if reserved:
                store.complete(attempt_id, 'error', {'message':'서버 처리 오류'})
            try:
                await ws.close(code=1011)
            except RuntimeError:
                pass
            return
