import asyncio
import json
import secrets
import statistics
import time

async def measure_rtt(ws, attempt_id, settings):
    records = []
    for i in range(settings.warmups + settings.samples):
        nonce = secrets.token_hex(16)
        probe_id = str(i)
        # Serialize before starting the timer. WebSocket send/receive is included.
        payload = json.dumps(dict(type='rtt_probe', attempt_id=attempt_id,
                                  probe_id=probe_id, nonce=nonce))
        started = time.perf_counter_ns()
        await ws.send_text(payload)
        raw = await asyncio.wait_for(ws.receive_text(), settings.probe_timeout)
        finished = time.perf_counter_ns()
        try:
            echo = json.loads(raw)
        except ValueError:
            raise ValueError('측정 응답 형식이 올바르지 않습니다')
        if not isinstance(echo, dict) or any(echo.get(k) != v for k, v in
            dict(type='rtt_echo', attempt_id=attempt_id, probe_id=probe_id, nonce=nonce).items()):
            raise ValueError('측정 응답이 현재 요청과 일치하지 않습니다')
        records.append(dict(probe_id=probe_id, warmup=i < settings.warmups,
                            rtt_ms=(finished-started)/1_000_000))
        if i < settings.warmups + settings.samples - 1:
            await asyncio.sleep(settings.interval)
    samples = [item['rtt_ms'] for item in records if not item['warmup']]
    median = statistics.median(samples)
    threshold = settings.threshold_ms
    status = 'not_configured' if threshold is None else ('suspected' if median > threshold else 'within_bound')
    return dict(status=status, decision={'not_configured':'기준 미설정','suspected':'중계 의심','within_bound':'지연 기준 충족'}[status],
                rtt_ms=median, statistic='median', mean_ms=statistics.mean(samples),
                threshold_ms=threshold, sample_count=len(samples), samples=records)
