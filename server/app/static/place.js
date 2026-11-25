// Extend the existing admin screen without replacing its session controls.
const registration=document.createElement('details');
registration.innerHTML=`<summary>기준 이미지 등록</summary>
<label for="ref-file">기준 사진</label><input id="ref-file" type="file" accept="image/*" multiple>
<select id="ref-mode"><option value="append">기존 기준에 추가</option><option value="replace">기존 기준 전체 교체</option></select><div id="ref-list" class="hint"></div><label for="min-inliers">최소 Inlier 수</label><input id="min-inliers" type="number" min="4" max="5000" value="20">
<label for="min-ratio">최소 Inlier 비율</label><input id="min-ratio" type="number" min="0.01" max="1" step="0.05" value="0.4">
<p class="hint">초기 시연값 · 표본으로 조정 필요</p><button id="register-place">선택 사진 저장</button><p id="ref-status" class="hint"></p>`;
document.querySelector('.layout section').append(registration);
document.getElementById('register-place').onclick=async()=>{
 const button=document.getElementById('register-place');button.disabled=true;
 try{
  const files=[...$('ref-file').files];if(!files.length)throw Error('기준 사진을 선택하세요');if(files.length>10)throw Error('최대 10장까지 선택하세요');
  const place=$('place').value.trim(),mode=$('ref-mode').value;
  const places=await api('/api/places'),existing=places.find(p=>p.place_id===place);
  if(mode==='append'&&files.length+(existing?(existing.references?.length||1):0)>10)throw Error('장소당 최대 10장입니다. 전체 교체를 선택하거나 사진 수를 줄이세요');
  const prepared=[];
  for(const file of files){
   if(file.size>20*1024*1024)throw Error('사진은 각각 20MB 이하여야 합니다');
   const image=await createImageBitmap(file),scale=Math.min(1,1600/Math.max(image.width,image.height));
   const canvas=document.createElement('canvas');canvas.width=Math.round(image.width*scale);canvas.height=Math.round(image.height*scale);
   canvas.getContext('2d').drawImage(image,0,0,canvas.width,canvas.height);image.close();
   prepared.push({mime_type:'image/jpeg',data_base64:canvas.toDataURL('image/jpeg',.9).split(',')[1]});
  }
  for(let i=0;i<prepared.length;i++){
   await api('/api/places',{place_id:place,mode:i===0?mode:'append',label:files[i].name.slice(0,80),image:prepared[i],min_inliers:Number($('min-inliers').value),min_ratio:Number($('min-ratio').value)});
   $('ref-status').textContent=`${i+1}/${prepared.length}장 저장 완료`;
  }
  await refreshReferences();
 }catch(e){$('ref-status').textContent=e.message}finally{button.disabled=false}
};
const placeDialog=document.createElement('dialog');
placeDialog.innerHTML=`<div class="dialog-head"><h2>장소 검증 상세</h2><button id="close-place">닫기</button></div><strong id="place-result"></strong><p id="selected-reference" class="hint"></p><div class="image-pair"><div><p>기준 이미지</p><img id="reference-original" alt="기준 이미지"><p id="no-reference" hidden>기준 이미지 없음</p></div><div><p>인증 이미지</p><img id="query-original" alt="인증 이미지"></div></div><div id="place-boundary" class="metrics"></div><p id="place-reason" class="hint"></p><details open><summary>특징점 연결 보기</summary><img id="match-view" style="width:100%" alt="특징점 매칭"><p class="hint">초록 Inlier · 빨강 Outlier · 동일 높이 표시 · 최대 100개 연결선</p></details>`;
document.body.append(placeDialog);let placeStamp='';
$('close-place').onclick=()=>placeDialog.close();
function openPlaceDetail(a){placeStamp='';if(!placeDialog.open)placeDialog.showModal();updatePlaceDetail(a)}
function updatePlaceDetail(a){
 if(!placeDialog.open)return;const stamp=JSON.stringify(a);if(stamp===placeStamp)return;placeStamp=stamp;
 const p=a.result?.place;$('place-result').textContent=p?.decision||'판정 대기';
 $('query-original').src='/api/attempts/'+a.attempt_id+'/image';
 $('reference-original').hidden=!p?.reference_id;$('no-reference').hidden=!!p?.reference_id;
 if(p?.reference_id)$('reference-original').src='/api/references/'+p.reference_id;
 $('selected-reference').textContent=p?`기준 ${p.reference_count||1}장 비교 · 선택: ${p.reference_label||'기준 이미지'}`:'';
 const t=p?.thresholds;
 $('place-boundary').textContent=t?`Inlier ${p.inlier_count??'—'}개 / 기준 ≥ ${t.min_inliers}개 · 비율 ${p.inlier_ratio==null?'—':(p.inlier_ratio*100).toFixed(1)+'%'} / 기준 ≥ ${(t.min_ratio*100).toFixed(1)}%`:'판정 기준 없음';
 $('place-reason').textContent=p?.status==='inconclusive'?(p.reason||'판정에 필요한 정보 부족'):t?'두 기준을 모두 충족하면 일치, 하나라도 미달하면 불일치.':a.result?.message||'';
 $('match-view').parentElement.hidden=!p?.match_image_url;if(p?.match_image_url)$('match-view').src=p.match_image_url;
}

async function refreshReferences(){try{const all=await api('/api/places'),p=all.find(p=>p.place_id===$('place').value.trim());const refs=p?(p.references||[{reference_id:p.reference_id,label:'기존 기준'}]):[];$('ref-list').replaceChildren();const count=document.createElement('p');count.textContent=`등록 기준 ${refs.length}/10장`;$('ref-list').append(count);for(const ref of refs){const img=document.createElement('img');img.src='/api/references/'+ref.reference_id;img.alt=ref.label;img.title=ref.label;img.style.cssText='width:65px;height:65px;object-fit:cover;margin:3px;border-radius:5px';$('ref-list').append(img)}}catch(e){$('ref-status').textContent=e.message}}
$('place').addEventListener('change',refreshReferences);registration.addEventListener('toggle',()=>{if(registration.open)refreshReferences()});refreshReferences();
