"""Place comparison with configurable demonstration thresholds."""
import hashlib
import json
import os
import threading
from collections import OrderedDict

registration_lock=threading.RLock()
from pathlib import Path
from uuid import uuid4
import cv2
import numpy as np
from ..schemas import PlaceResult

cv2.setNumThreads(1)

def place_key(place_id):
    return hashlib.sha256(place_id.strip().encode()).hexdigest()

def register_place(directory, payload, raw):
    with registration_lock:
        root=directory/'places';root.mkdir(parents=True,exist_ok=True)
        destination=root/f'{place_key(payload.place_id)}.json'
        old=json.loads(destination.read_text(encoding='utf-8')) if destination.exists() else {}
        references=old.get('references',([dict(reference_id=old['reference_id'],label='기존 기준',thresholds=old['thresholds'])] if old.get('reference_id') else []))
        if payload.mode=='replace':references=[]
        if len(references)>=10:raise ValueError('장소당 기준 이미지는 최대 10장입니다')
        version=str(uuid4());(root/f'{version}.jpg').write_bytes(raw)
        thresholds=dict(min_inliers=payload.min_inliers,min_ratio=payload.min_ratio,ratio_test=payload.ratio_test,reprojection_px=payload.reprojection_px)
        references.append(dict(reference_id=version,label=payload.label or f'기준 {len(references)+1}',thresholds=thresholds))
        item=dict(place_id=payload.place_id.strip(),reference_id=version,thresholds=thresholds,references=references)
        temp=root/f'{uuid4()}.tmp';temp.write_text(json.dumps(item,ensure_ascii=False),encoding='utf-8');os.replace(temp,destination)
        return item

def feature_mask(image, polygon=None):
    mask=np.full(image.shape[:2],255,np.uint8);polygons=[]
    try:
        ok,points=cv2.QRCodeDetector().detectMulti(image)
        if ok:polygons.extend(points)
    except cv2.error:pass
    if polygon:polygons.append(np.array(polygon)*[image.shape[1],image.shape[0]])
    for points in polygons:
        points=np.array(points,dtype=np.float32);center=points.mean(axis=0)
        cv2.fillConvexPoly(mask,np.round(center+(points-center)*1.2).astype(np.int32),0)
    return mask

def verify_place(place_id: str, image_path: Path, qr_polygon=None) -> PlaceResult:
    directory=image_path.parent.parent;metadata=directory/'places'/f'{place_key(place_id)}.json'
    if not metadata.exists():return PlaceResult(status='inconclusive',decision='판정 불가',reason='기준 이미지 미등록')
    info=json.loads(metadata.read_text(encoding='utf-8'))
    references=info.get('references',[dict(reference_id=info['reference_id'],label='기준',thresholds=info['thresholds'])])
    # The query's QR mask and SIFT features are the same for every reference: compute them once.
    query=load_image(image_path)
    kp2,d2=cv2.SIFT_create(nfeatures=3000).detectAndCompute(cv2.cvtColor(query,cv2.COLOR_BGR2GRAY),feature_mask(query,qr_polygon))
    results=[];matches=[]
    for ref in references:
        try:
            result,match=compare_reference(directory,ref,kp2,d2)
        except (ValueError,OSError,cv2.error):
            result=PlaceResult(status='inconclusive',decision='판정 불가',reference_id=ref['reference_id'],reason='기준 이미지 비교 오류');match=None
        result.reference_label=ref.get('label','기준');results.append(result);matches.append(match)
    if not results:return PlaceResult(status='inconclusive',decision='판정 불가',reason='기준 이미지 미등록')
    # A passing reference always wins; rank within the class by balanced threshold margin.
    def rank(r):
        t=r.thresholds or {};score=min((r.inlier_count or 0)/max(1,t.get('min_inliers',20)),(r.inlier_ratio or 0)/max(.001,t.get('min_ratio',.4)))
        return ({'match':2,'non_match':1,'inconclusive':0}.get(r.status,0),score,r.inlier_count or 0)
    index=max(range(len(results)),key=lambda i:rank(results[i]));result=results[index]
    result.reference_count=len(results)
    result.comparisons=[dict(reference_id=r.reference_id,label=r.reference_label,status=r.status,inlier_count=r.inlier_count,inlier_ratio=r.inlier_ratio,thresholds=r.thresholds) for r in results]
    if result.status!='match' and any(r.status=='inconclusive' for r in results):
        result.status='inconclusive';result.decision='판정 불가';result.reason='일치 기준 없음 · 일부 기준은 비교 근거 부족, 다른 각도로 재촬영하세요'
    # Draw only the selected comparison; the picture is display-only and never affects the decision.
    output=None
    if matches[index] is not None:
        kp1,good,mask=matches[index]
        try:output=draw_matches(load_image(directory/'places'/f"{references[index]['reference_id']}.jpg"),kp1,query,kp2,good,mask)
        except (ValueError,OSError,cv2.error):output=None
    if output is not None:
        destination=directory/'matches';destination.mkdir(exist_ok=True)
        ok,buffer=cv2.imencode('.jpg',output)
        if ok:
            (destination/f'{image_path.stem}.jpg').write_bytes(buffer.tobytes())
            result.match_image_url=f'/api/attempts/{image_path.stem}/matches'
    return result

def load_image(path):
    image=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
    if image is None:raise ValueError('이미지를 읽을 수 없습니다')
    h,w=image.shape[:2]
    if max(h,w)>1600:image=cv2.resize(image,(round(w*1600/max(h,w)),round(h*1600/max(h,w))))
    return image

# Reference files are write-once (new uuid per registration), so their QR mask + SIFT features are reused
# across attempts. mtime/size in the key catch a hand-replaced file; at most 32 entries (~2 MB each).
reference_cache=OrderedDict();reference_cache_lock=threading.Lock()

def reference_features(path):
    stat=path.stat();key=(str(path),stat.st_mtime_ns,stat.st_size)
    with reference_cache_lock:
        if key in reference_cache:
            reference_cache.move_to_end(key);return reference_cache[key]
    image=load_image(path)
    features=cv2.SIFT_create(nfeatures=3000).detectAndCompute(cv2.cvtColor(image,cv2.COLOR_BGR2GRAY),feature_mask(image))
    with reference_cache_lock:
        reference_cache[key]=features
        while len(reference_cache)>32:reference_cache.popitem(last=False)
    return features

def compare_reference(directory,info,kp2,d2):
    kp1,d1=reference_features(directory/'places'/f"{info['reference_id']}.jpg")
    t=info['thresholds']
    result=PlaceResult(status='inconclusive',decision='판정 불가',reference_id=info['reference_id'],
        thresholds=t,reference_keypoints=len(kp1),query_keypoints=len(kp2),valid_match_count=0,inlier_count=0)
    good=[];mask=[]
    if d1 is None or d2 is None or len(kp1)<4 or len(kp2)<4:
        result.reason='특징점 부족: 주변 환경을 선명하게 다시 촬영하세요'
    else:
        pairs=cv2.BFMatcher(cv2.NORM_L2).knnMatch(d1,d2,k=2)
        candidates=[m for pair in pairs if len(pair)==2 for m,n in [pair] if m.distance<t['ratio_test']*n.distance]
        used=set()
        for m in sorted(candidates,key=lambda m:m.distance):
            if m.trainIdx not in used:used.add(m.trainIdx);good.append(m)
        result.valid_match_count=len(good)
        mask=[False]*len(good)
        if len(good)<4:result.reason='기하학적 검증에 필요한 대응점 부족'
        else:
            source=np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1,1,2)
            target=np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1,1,2)
            homography,inliers=cv2.findHomography(source,target,cv2.RANSAC,t['reprojection_px'])
            if homography is None or inliers is None or not np.isfinite(homography).all():
                result.reason='안정적인 기하학적 변환을 찾지 못했습니다'
            else:
                mask=inliers.ravel().astype(bool).tolist()
                result.inlier_count=sum(mask);result.inlier_ratio=sum(mask)/len(good)
                passed=result.inlier_count>=t['min_inliers'] and result.inlier_ratio>=t['min_ratio']
                result.status='match' if passed else 'non_match'
                result.decision='장소 일치' if passed else '장소 불일치'
                result.reason='Inlier 수·비율 기준 충족' if passed else 'Inlier 수 또는 비율 기준 미달'
    return result,(kp1,good,mask)

def draw_matches(ref,kp1,query,kp2,good,mask):
    # Display-only rescaling: analysis keypoints and thresholds remain untouched.
    height=600
    def display(image,keypoints):
        scale=height/image.shape[0]
        resized=cv2.resize(image,(round(image.shape[1]*scale),height))
        points=[cv2.KeyPoint(k.pt[0]*scale,k.pt[1]*scale,max(1,k.size*scale)) for k in keypoints]
        return resized,points
    left,lk=display(ref,kp1);right,rk=display(query,kp2)
    # Prefer inliers when limiting the displayed lines.
    order=sorted(range(len(good)),key=lambda i:not mask[i])[:100]
    shown=[good[i] for i in order];flags=[mask[i] for i in order]
    output=cv2.drawMatches(left,lk,right,rk,shown,None,matchColor=(80,170,80),matchesMask=[int(v) for v in flags],flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
    if shown:output=cv2.drawMatches(left,lk,right,rk,shown,output,matchColor=(60,70,210),matchesMask=[int(not v) for v in flags],flags=cv2.DrawMatchesFlags_DRAW_OVER_OUTIMG|cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
    return output
