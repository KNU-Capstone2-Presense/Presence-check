import math
from uuid import uuid4
from ..store import now

def calculate(samples):
    direct=[s['rtt_ms'] for s in samples if s['label']=='direct']
    relay=sorted(s['rtt_ms'] for s in samples if s['label']=='relay')
    result=dict(target_percent=None,direct_count=len(direct),relay_count=len(relay),
                threshold_ms=None,detection_percent=None,frr_percent=None)
    return result

def apply(store, threshold_ms):
    samples=store.calibration_samples()
    value=calculate(samples)
    if not math.isfinite(threshold_ms) or threshold_ms<0:raise ValueError('유효한 임계값을 입력하세요')
    value.update(threshold_ms=threshold_ms,target_percent=None,method='manual')
    for label,key in [('direct','frr_percent'),('relay','detection_percent')]:
        xs=[s['rtt_ms'] for s in samples if s['label']==label]
        value[key]=100*sum(x>threshold_ms for x in xs)/len(xs) if xs else None
    value.update(id=str(uuid4()),applied_at=now(),sample_ids=[s['attempt_id'] for s in samples])
    store.save_calibration(value)
    return value
