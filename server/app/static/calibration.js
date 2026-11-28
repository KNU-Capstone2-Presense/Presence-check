const calibrationBox=document.createElement('details');
calibrationBox.innerHTML=`<summary>RTT 기준 설정</summary>
<p class="hint">인증 1건 = 10회 중앙값 1개 · 임계값 직접 지정</p>
<label for="sample-attempt">인증 선택</label><select id="sample-attempt"><option value="">선택</option></select>
<div class="actions"><button id="tag-direct">Direct 추가</button><button id="tag-relay">Relay 추가</button><button id="untag">제외</button></div>
<pre id="calibration-summary"></pre><button id="apply-calibration" disabled>임계값 적용</button>
<p class="hint">등록 표본 기준 비율 · 적용 후 인증부터 반영</p><p id="calibration-message" class="hint"></p>`;
document.querySelector('.layout section').append(calibrationBox);
let calibrationState=null,attemptOptionsStamp='',sampleOptionsStamp='',manualThreshold=null,chartMaximum=1;
function updateAttemptOptions(){
 const complete=items.filter(a=>a.status==='complete'&&a.result?.relay?.sample_count===10);
 const labels=new Map((calibrationState?.samples||[]).map(s=>[s.attempt_id,s.label]));
 const stamp=JSON.stringify([complete.map(a=>a.attempt_id),[...labels]]);if(stamp===attemptOptionsStamp)return;attemptOptionsStamp=stamp;
 const select=$('sample-attempt'),previous=select.value;select.replaceChildren(new Option('선택',''));
 for(const a of complete){const label=labels.get(a.attempt_id);select.append(new Option(`${a.student_id} · ${a.result.relay.rtt_ms.toFixed(3)}ms · ${new Date(a.created_at).toLocaleTimeString()}${label?' ['+label+']':''}`,a.attempt_id))}select.value=previous;
}
// Registered samples incl. batch-collected ones; grouped by label, largest RTT first so outliers are on top.
function updateSampleOptions(){
 const samples=calibrationState?.samples||[],stamp=JSON.stringify(samples);if(stamp===sampleOptionsStamp)return;sampleOptionsStamp=stamp;
 const select=$('remove-sample'),previous=select.value;select.replaceChildren(new Option('선택',''));
 for(const [label,title] of [['direct','Direct'],['relay','Relay']]){
  const group=document.createElement('optgroup');group.label=title;
  for(const s of samples.filter(s=>s.label===label).sort((a,b)=>b.rtt_ms-a.rtt_ms))group.append(new Option(`${s.rtt_ms.toFixed(3)} ms · ${s.attempt_id.slice(0,8)}`,s.attempt_id));
  if(group.childElementCount)select.append(group);
 }
 select.value=samples.some(s=>s.attempt_id===previous)?previous:'';
}
function showCalibration(data){
 calibrationState=data;const c=data.candidate,a=data.active;const fmt=n=>n==null?'—':n.toFixed(6);
 $('calibration-summary').textContent=`Direct ${c.direct_count}개 · Relay ${c.relay_count}개\n선택값: ${fmt(manualThreshold)} ms\n적용값: ${fmt(a?.threshold_ms)} ms`;
 if(manualThreshold===null&&a)manualThreshold=a.threshold_ms;$('apply-calibration').disabled=manualThreshold===null;updateAttemptOptions();updateSampleOptions();
}
async function tag(label,attempt_id=$('sample-attempt').value,empty='인증을 선택하세요'){try{if(!attempt_id)throw Error(empty);showCalibration(await api('/api/calibration/samples',{attempt_id,label}));$('calibration-message').textContent=label==='remove'?'표본 제외 완료':'표본 반영 완료'}catch(e){$('calibration-message').textContent=e.message}}
$('tag-direct').onclick=()=>tag('direct');$('tag-relay').onclick=()=>tag('relay');$('untag').onclick=()=>tag('remove');
$('apply-calibration').onclick=async()=>{try{await api('/api/calibration/apply',{threshold_ms:manualThreshold});showCalibration(await api('/api/calibration'));$('calibration-message').textContent='이후 인증에 적용됩니다'}catch(e){$('calibration-message').textContent=e.message}};
api('/api/calibration').then(showCalibration).catch(e=>$('calibration-message').textContent=e.message);
setInterval(updateAttemptOptions,1000);
const batch=document.createElement('div');
batch.innerHTML=`<hr><label>대기 중인 앱</label><select id="batch-client"></select>
<div class="actions"><select id="batch-label"><option value="direct">Direct</option><option value="relay">Relay</option></select><select id="batch-purpose"><option value="calibration">기준 설정</option><option value="evaluation">별도 평가</option></select></div>
<label>표본 수 (1개 = 10회 중앙값)</label><input id="batch-count" type="number" min="1" max="10000" value="20">
<div class="actions"><button id="batch-start">반복 수집</button><button id="batch-stop" disabled>중지</button></div><p id="batch-progress" class="hint"></p>
<button id="open-chart">표본·임계값 그래프</button>
<p id="evaluation-summary" class="hint"></p><label for="remove-sample">등록 표본 제외 · 라벨별 RTT 큰 순</label><select id="remove-sample"><option value="">선택</option></select>
<div class="actions"><button id="remove-collected">선택 표본 제외</button><button id="reset-samples">표본 초기화</button></div>`;
calibrationBox.append(batch);let currentRun=null;
const chartDialog=document.createElement('dialog');
chartDialog.innerHTML=`<div class="dialog-head"><h2>중계 판정 임계값</h2><button id="close-chart">닫기</button></div><p id="chart-summary" class="metrics"></p><canvas id="batch-chart" width="960" height="420" style="width:100%" aria-label="실측 RTT 표본 분포와 임계값"></canvas><p class="hint">파랑 Direct · 주황 Relay · 초록 점선 선택값 · 보라 실선 적용값</p><p class="hint">곡선은 KDE 근사 · 아래 눈금은 실제 표본 · RTT가 임계값을 초과하면 의심</p><label>임계값 (ms) · 그래프 클릭/드래그 또는 숫자 입력</label><input id="manual-threshold" type="number" min="0" step="0.001"><p id="manual-rates" class="hint"></p><button id="chart-apply">이 임계값 적용</button>`;
document.body.append(chartDialog);
$('open-chart').onclick=async()=>{chartDialog.showModal();await refreshBatch();drawSamples()};
$('close-chart').onclick=()=>chartDialog.close();
$('chart-apply').onclick=async()=>{await $('apply-calibration').onclick();drawSamples()};
function drawSamples(){
 const samples=calibrationState?.samples||[],c=$('batch-chart'),ctx=c.getContext('2d');ctx.clearRect(0,0,960,420);
 const applied=calibrationState?.active?.threshold_ms,threshold=manualThreshold;
 const fmt=n=>n==null?'미설정':n.toFixed(3)+' ms';
 const groups={direct:samples.filter(s=>s.label==='direct').map(s=>s.rtt_ms),relay:samples.filter(s=>s.label==='relay').map(s=>s.rtt_ms)};
 $('chart-summary').textContent=`Direct ${groups.direct.length}개 · Relay ${groups.relay.length}개 | 선택 ${fmt(threshold)} | 적용 ${fmt(applied)}`;
 $('chart-apply').disabled=threshold===null;$('apply-calibration').disabled=threshold===null;
 if(document.activeElement!==$('manual-threshold'))$('manual-threshold').value=threshold??'';
 const rate=xs=>threshold===null||!xs.length?'—':(100*xs.filter(x=>x>threshold).length/xs.length).toFixed(1)+'%';
 $('manual-rates').textContent=`현재 표본 기준 · Relay 탐지 ${rate(groups.relay)} · Direct 오판 ${rate(groups.direct)}`;
 chartMaximum=Math.max(.001,...samples.map(s=>s.rtt_ms),applied||0)*1.08;
 const maximum=chartMaximum,left=60,top=38,w=860,h=320;
 ctx.font='14px sans-serif';ctx.fillStyle='#405968';
 const curves=[];
 for(const [label,color] of [['direct','#277ec2'],['relay','#d98428']]){
  const xs=groups[label];if(!xs.length)continue;
  const sorted=[...xs].sort((a,b)=>a-b),mean=xs.reduce((a,b)=>a+b,0)/xs.length;
  const sd=Math.sqrt(xs.reduce((a,b)=>a+(b-mean)**2,0)/Math.max(1,xs.length-1));
  const iqr=sorted[Math.floor((xs.length-1)*.75)]-sorted[Math.floor((xs.length-1)*.25)];
  const scale=iqr>0?Math.min(sd,iqr/1.34):sd;
  const bw=Math.max(maximum/500,.9*scale*Math.pow(xs.length,-.2));
  const values=Array.from({length:501},(_,i)=>{const x=i/500*maximum;return xs.reduce((a,v)=>a+Math.exp(-.5*((x-v)/bw)**2)+Math.exp(-.5*((x+v)/bw)**2),0)/(xs.length*bw*Math.sqrt(2*Math.PI))});
  curves.push({xs,color,values});
 }
 const ymax=Math.max(.001,...curves.flatMap(c=>c.values))*1.1;
 ctx.strokeStyle='#dce5e8';for(let i=0;i<=4;i++){const y=top+h-i*h/4;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(left+w,y);ctx.stroke();ctx.fillText((ymax*i/4).toFixed(3),5,y+5)}
 for(const {xs,color,values} of curves){ctx.strokeStyle=color;ctx.lineWidth=2;ctx.beginPath();values.forEach((v,i)=>{const x=left+i/500*w,y=top+h-v/ymax*h;i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke();ctx.lineWidth=1;for(const v of xs){const x=left+v/maximum*w;ctx.beginPath();ctx.moveTo(x,top+h);ctx.lineTo(x,top+h+7);ctx.stroke()}}
 ctx.fillStyle='#405968';for(let i=0;i<=5;i++)ctx.fillText((maximum*i/5).toFixed(2),left+i*w/5-15,385);
 ctx.fillText('확률밀도 (1/ms)',10,20);ctx.fillText('RTT (ms)',445,414);
 for(const [v,color,dash] of [[applied,'#8254bc',[]],[threshold,'#13886c',[7,5]]])if(v!=null&&v<=maximum){const x=left+v/maximum*w;ctx.strokeStyle=color;ctx.lineWidth=2;ctx.setLineDash(dash);ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,top+h);ctx.stroke()}
 ctx.setLineDash([]);ctx.lineWidth=1;
 if(!samples.length)ctx.fillText('표본을 수집한 후 임계값을 선택하세요',280,200);
}
$('manual-threshold').oninput=()=>{const value=$('manual-threshold').value;manualThreshold=value!==''&&Number.isFinite(Number(value))&&Number(value)>=0?Number(value):null;drawSamples()};
function pickThreshold(e){const rect=$('batch-chart').getBoundingClientRect(),x=(e.clientX-rect.left)/rect.width*960;manualThreshold=Math.max(0,Math.min(1,(x-60)/860))*chartMaximum;drawSamples()}
$('batch-chart').style.touchAction='none';
$('batch-chart').onpointerdown=e=>{$('batch-chart').setPointerCapture(e.pointerId);pickThreshold(e)};
$('batch-chart').onpointermove=e=>{if($('batch-chart').hasPointerCapture(e.pointerId))pickThreshold(e)};
$('batch-chart').onpointerup=e=>{if($('batch-chart').hasPointerCapture(e.pointerId))$('batch-chart').releasePointerCapture(e.pointerId)};
async function refreshBatch(){
 if(!calibrationBox.open&&!chartDialog.open)return;
 try{
 const data=await api('/api/collection'),s=$('batch-client'),old=s.value;s.replaceChildren();for(const c of data.clients)s.append(new Option(c.student_id+(c.busy?' · 측정 중':''),c.id));if([...s.options].some(o=>o.value===old))s.value=old;
 const run=data.runs.find(r=>r.id===currentRun)||data.runs.at(-1);
 if(run){currentRun=run.id;$('batch-progress').textContent=`${run.label} ${run.completed}/${run.requested} · ${ {running:'수집 중',complete:'완료',stopped:'중지',error:'오류'}[run.status]}${run.message?' · '+run.message:''}`;$('batch-stop').disabled=run.status!=='running'}
 showCalibration(await api('/api/calibration'));drawSamples();
 const e=await api('/api/evaluation'),fmt=n=>n==null?'—':n.toFixed(1)+'%';$('evaluation-summary').textContent=`별도 평가: Direct ${e.direct.count}개 / FRR ${fmt(e.direct.percent)} · Relay ${e.relay.count}개 / 탐지율 ${fmt(e.relay.percent)}`;
 }catch(e){$('calibration-message').textContent=e.message}
}
$('batch-start').onclick=async()=>{try{const r=await api('/api/collection/start',{client_id:$('batch-client').value,label:$('batch-label').value,count:Number($('batch-count').value),purpose:$('batch-purpose').value});currentRun=r.id;await refreshBatch()}catch(e){$('calibration-message').textContent=e.message}};
$('batch-stop').onclick=async()=>{if(currentRun){await api('/api/collection/'+currentRun+'/stop',{});$('batch-progress').textContent='현재 표본 측정 후 중지'}};
$('remove-collected').onclick=()=>tag('remove',$('remove-sample').value,'제외할 표본을 선택하세요');
calibrationBox.addEventListener('toggle',refreshBatch);setInterval(refreshBatch,2000);

$('reset-samples').onclick=async()=>{
 if(!confirm('Direct·Relay 표본, 별도 평가와 적용 임계값을 모두 초기화할까요? 인증 현황과 장소 이미지는 유지됩니다.'))return;
 try{
  const data=await api('/api/calibration/reset',{});
  manualThreshold=null;currentRun=null;showCalibration(data);drawSamples();
  $('batch-progress').textContent='';$('batch-stop').disabled=true;
  $('evaluation-summary').textContent='별도 평가: Direct 0개 · Relay 0개';
  $('calibration-message').textContent='표본 초기화 완료';
 }catch(e){$('calibration-message').textContent=e.message}
};
