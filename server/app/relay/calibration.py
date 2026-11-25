import math
from uuid import uuid4
from ..store import now

def calculate(samples):
    direct=[s['rtt_ms'] for s in samples if s['label']=='direct']
    relay=sorted(s['rtt_ms'] for s in samples if s['label']=='relay')
    result=dict(target_percent=90,direct_count=len(direct),relay_count=len(relay),
                threshold_ms=None,detection_percent=None,frr_percent=None)
    if not relay:return result
    # Strict x>T rule: use the largest representable threshold below the boundary.
    required=(9*len(relay)+9)//10
    threshold=math.nextafter(relay[len(relay)-required],-math.inf)
    result.update(threshold_ms=threshold,
                  detection_percent=100*sum(x>threshold for x in relay)/len(relay),
                  frr_percent=100*sum(x>threshold for x in direct)/len(direct) if direct else None)
    return result

def apply(store):
    samples=store.calibration_samples()
    value=calculate(samples)
    if value['threshold_ms'] is None:raise ValueError('Relay 표본을 등록하세요')
    value.update(id=str(uuid4()),applied_at=now(),sample_ids=[s['attempt_id'] for s in samples])
    store.save_calibration(value)
    return value
