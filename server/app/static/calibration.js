const calibrationBox=document.createElement('details');
calibrationBox.innerHTML=`<summary>RTT 기준 설정</summary>
<p class="hint">인증 1건 = 10회 중앙값 1개 · 탐지 목표 90%</p>
<label for="sample-attempt">인증 선택</label><select id="sample-attempt"><option value="">선택</option></select>
<div class="actions"><button id="tag-direct">Direct 추가</button><button id="tag-relay">Relay 추가</button><button id="untag">제외</button></div>
<pre id="calibration-summary"></pre><button id="apply-calibration" disabled>임계값 적용</button>
<p class="hint">등록 표본 기준 비율 · 적용 후 인증부터 반영</p><p id="calibration-message" class="hint"></p>`;
document.querySelector('.layout section').append(calibrationBox);
let calibrationState=null,attemptOptionsStamp='';
function updateAttemptOptions(){
 const complete=items.filter(a=>a.status==='complete'&&a.result?.relay?.sample_count===10);
 const labels=new Map((calibrationState?.samples||[]).map(s=>[s.attempt_id,s.label]));
 const stamp=JSON.stringify([complete.map(a=>a.attempt_id),[...labels]]);if(stamp===attemptOptionsStamp)return;attemptOptionsStamp=stamp;
 const select=$('sample-attempt'),previous=select.value;select.replaceChildren(new Option('선택',''));
 for(const a of complete){const label=labels.get(a.attempt_id);select.append(new Option(`${a.student_id} · ${a.result.relay.rtt_ms.toFixed(3)}ms · ${new Date(a.created_at).toLocaleTimeString()}${label?' ['+label+']':''}`,a.attempt_id))}select.value=previous;
}
function showCalibration(data){
 calibrationState=data;const c=data.candidate,a=data.active;const fmt=n=>n==null?'—':n.toFixed(6);
 $('calibration-summary').textContent=`Direct ${c.direct_count}개 · Relay ${c.relay_count}개\n산출값: ${fmt(c.threshold_ms)} ms\n등록 Relay 탐지: ${c.detection_percent==null?'—':c.detection_percent.toFixed(1)+'%'}\n등록 Direct 오판: ${c.frr_percent==null?'—':c.frr_percent.toFixed(1)+'%'}\n적용값: ${fmt(a?.threshold_ms)} ms`;
 $('apply-calibration').disabled=c.threshold_ms==null;updateAttemptOptions();
}
async function tag(label){try{const attempt_id=$('sample-attempt').value;if(!attempt_id)throw Error('인증을 선택하세요');showCalibration(await api('/api/calibration/samples',{attempt_id,label}));$('calibration-message').textContent='표본 반영 완료'}catch(e){$('calibration-message').textContent=e.message}}
$('tag-direct').onclick=()=>tag('direct');$('tag-relay').onclick=()=>tag('relay');$('untag').onclick=()=>tag('remove');
$('apply-calibration').onclick=async()=>{try{await api('/api/calibration/apply',{});showCalibration(await api('/api/calibration'));$('calibration-message').textContent='이후 인증에 적용됩니다'}catch(e){$('calibration-message').textContent=e.message}};
api('/api/calibration').then(showCalibration).catch(e=>$('calibration-message').textContent=e.message);
setInterval(updateAttemptOptions,1000);
const batch=document.createElement('div');
batch.innerHTML=`<hr><label>대기 중인 앱</label><select id="batch-client"></select>
<div class="actions"><select id="batch-label"><option value="direct">Direct</option><option value="relay">Relay</option></select><select id="batch-purpose"><option value="calibration">기준 설정</option><option value="evaluation">별도 평가</option></select></div>
<label>표본 수 (1개 = 10회 중앙값)</label><input id="batch-count" type="number" min="1" max="10000" value="20">
<div class="actions"><button id="batch-start">반복 수집</button><button id="batch-stop" disabled>중지</button></div><p id="batch-progress" class="hint"></p>
<button id="open-chart">표본·임계값 그래프</button>
<p id="evaluation-summary" class="hint"></p><label>등록 표본 제외</label><select id="remove-sample"></select><button id="remove-collected">선택 표본 제외</button>`;
calibrationBox.append(batch);let currentRun=null;
const chartDialog=document.createElement('dialog');
chartDialog.innerHTML=`<div class="dialog-head"><h2>중계 판정 임계값</h2><button id="close-chart">닫기</button></div><p id="chart-summary" class="metrics"></p><canvas id="batch-chart" width="960" height="420" style="width:100%" aria-label="실측 RTT 표본 분포와 임계값"></canvas><p class="hint">파랑 Direct · 주황 Relay · 초록 점선 산출값 · 보라 실선 적용값</p><p class="hint">산출값: 등록 Relay의 최소 90%가 초과하는 경계 · RTT가 적용값을 초과하면 의심</p><button id="chart-apply">이 임계값 적용</button>`;
document.body.append(chartDialog);
$('open-chart').onclick=async()=>{chartDialog.showModal();await refreshBatch();drawSamples()};
$('close-chart').onclick=()=>chartDialog.close();
$('chart-apply').onclick=async()=>{await $('apply-calibration').onclick();drawSamples()};
function drawSamples(){
 const samples=calibrationState?.samples||[],c=$('batch-chart'),ctx=c.getContext('2d');ctx.clearRect(0,0,960,420);
 const candidate=calibrationState?.candidate,threshold=candidate?.threshold_ms,applied=calibrationState?.active?.threshold_ms;
 const fmt=n=>n==null?'미설정':n.toFixed(6)+' ms';
 $('chart-summary').textContent=`Direct ${candidate?.direct_count||0}개 · Relay ${candidate?.relay_count||0}개 | 산출 ${fmt(threshold)} | 적용 ${fmt(applied)}`;
 $('chart-apply').disabled=threshold==null;
 ctx.font='15px sans-serif';ctx.fillStyle='#405968';
 if(!samples.length){ctx.fillText('수집한 표본이 없습니다',350,210)}else{
 const maximum=samples.reduce((v,s)=>Math.max(v,s.rtt_ms),Math.max(.001,threshold||0,applied||0))*1.08;
 const bins=24,counts={direct:Array(bins).fill(0),relay:Array(bins).fill(0)};
 for(const s of samples)counts[s.label][Math.min(bins-1,Math.floor(s.rtt_ms/maximum*bins))]++;
 const ymax=Math.max(1,...counts.direct,...counts.relay),left=60,top=38,w=860,h=320;
 ctx.strokeStyle='#dce5e8';
 for(let i=0;i<=4;i++){const y=top+h-i*h/4;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(left+w,y);ctx.stroke();ctx.fillText((ymax*i/4).toFixed(ymax<4?1:0),10,y+5)}
 for(const [label,color,offset] of [['direct','#277ec2',0],['relay','#d98428',.5]]){
 ctx.fillStyle=color;counts[label].forEach((n,i)=>ctx.fillRect(left+(i+offset)*w/bins,top+h-n/ymax*h,w/bins*.46,n/ymax*h));}
 for(let i=0;i<=5;i++){ctx.fillStyle='#405968';ctx.fillText((maximum*i/5).toFixed(2),left+i*w/5-15,385)}
 ctx.fillText('표본 수',10,20);ctx.fillText('RTT (ms)',445,414);
 for(const [v,color,dash] of [[applied,'#8254bc',[]],[threshold,'#13886c',[7,5]]])if(v!=null){const x=left+v/maximum*w;ctx.strokeStyle=color;ctx.lineWidth=2;ctx.setLineDash(dash);ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,top+h);ctx.stroke()}
 ctx.setLineDash([]);ctx.lineWidth=1;
 }
 const select=$('remove-sample'),old=select.value;select.replaceChildren(new Option('선택',''));for(const s of samples)select.append(new Option(`${s.label} · ${s.rtt_ms.toFixed(3)} ms · ${s.attempt_id.slice(0,8)}`,s.attempt_id));select.value=old;
}
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
$('remove-collected').onclick=async()=>{if($('remove-sample').value){await api('/api/calibration/samples',{attempt_id:$('remove-sample').value,label:'remove'});await refreshBatch()}};
calibrationBox.addEventListener('toggle',refreshBatch);setInterval(refreshBatch,2000);
