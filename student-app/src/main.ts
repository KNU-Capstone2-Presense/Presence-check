import jsQR from 'jsqr';
import './style.css';

document.querySelector('#app')!.innerHTML = `<main>
<header><div><span class="eyebrow">ATTENDANCE</span><h1>출석 인증</h1></div><span id="connection">미연결</span></header>
<label for="student">학생 ID</label><input id="student" placeholder="학번" autocomplete="username" maxlength="80">
<div class="camera"><span id="placeholder">QR과 주변을 촬영하세요</span><video id="video" autoplay muted playsinline hidden></video><img id="preview" alt="촬영 이미지" hidden></div>
<p class="session">QR과 주변 공간이 함께 보이도록 비춰주세요</p><button id="camera" class="primary">카메라 시작 / 다시 인증</button><div id="session" class="session">QR 미인식</div><p id="status" role="status" aria-live="polite"></p><section id="result" hidden></section>
<details><summary>연결 설정</summary><label for="endpoint">서버 주소</label><input id="endpoint" placeholder="wss://서버주소/ws" spellcheck="false"><button id="connect" class="primary">연결</button></details>
<details><summary>RTT 표본 수집</summary><button id="collect">QR 인식 후 수집 대기</button><button id="end-collect">대기 종료</button></details></main>`;
const el = <T extends HTMLElement>(id:string) => document.getElementById(id) as T;
const student=el<HTMLInputElement>('student'), endpoint=el<HTMLInputElement>('endpoint');
const video=el<HTMLVideoElement>('video'), preview=el<HTMLImageElement>('preview');
let scanPurpose:'auth'|'collection'='auth';
let qrPolygon:number[][]|undefined;
type Session={session_id:string;place_id:string;token?:string;expires_at?:string};
let session:Session|null=null, picture='', stream:MediaStream|null=null, socket:WebSocket|null=null;
let collecting=false,openingCamera=false;
let pending:string|null=null, timer:ReturnType<typeof setTimeout>|undefined, scanTimer:ReturnType<typeof setInterval>|undefined;
student.value=localStorage.getItem('student_id')||''; endpoint.value=location.pathname.startsWith('/student/')?`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws`:localStorage.getItem('endpoint')||'';
function status(text:string,error=false){el('status').textContent=text;el('status').classList.toggle('error',error)}
function ready(){el<HTMLButtonElement>('camera').disabled=!!pending||collecting||openingCamera;el<HTMLButtonElement>('collect').disabled=!!pending||collecting||openingCamera}

function parseQR(raw:string){
 try{
  let q:any;
  try{q=JSON.parse(raw)}catch{const u=new URL(raw);q=Object.fromEntries(u.searchParams)}
  if(typeof q.session_id!=='string'||!q.session_id||typeof q.place_id!=='string'||!q.place_id)throw Error();
  session={session_id:q.session_id,place_id:q.place_id,...(typeof q.token==='string'?{token:q.token}:{}),...(q.expires_at?{expires_at:q.expires_at}:{})};
  el('session').textContent=`${q.place_id} · QR 인식 완료`;ready();return true;
 }catch{status('QR 형식을 확인하세요',true);return false}
}
function readQR(canvas:HTMLCanvasElement){
 if(pending||collecting||socket?.readyState!==WebSocket.OPEN||!student.value.trim())return;
 const c=canvas.getContext('2d',{willReadFrequently:true})!,d=c.getImageData(0,0,canvas.width,canvas.height),qr=jsQR(d.data,d.width,d.height);
 if(!qr||!parseQR(qr.data))return;
 qrPolygon=[qr.location.topLeftCorner,qr.location.topRightCorner,qr.location.bottomRightCorner,qr.location.bottomLeftCorner].map(p=>[Math.max(0,Math.min(1,p.x/canvas.width)),Math.max(0,Math.min(1,p.y/canvas.height))]);
 setPicture(canvas);
 if(scanPurpose==='collection')beginCollection();else authenticate();
}

function canvasOf(source:CanvasImageSource,w:number,h:number){const c=document.createElement('canvas');const ratio=Math.min(1,1600/Math.max(w,h));c.width=Math.round(w*ratio);c.height=Math.round(h*ratio);c.getContext('2d')!.drawImage(source,0,0,c.width,c.height);return c}
function stopCamera(){if(scanTimer)clearInterval(scanTimer);stream?.getTracks().forEach(t=>t.stop());stream=null;video.srcObject=null;video.hidden=true}
function setPicture(c:HTMLCanvasElement){picture=c.toDataURL('image/jpeg',.88);preview.src=picture;preview.hidden=false;el('placeholder').hidden=true;stopCamera();ready()}
async function startCamera(purpose:'auth'|'collection'){
 if(pending||collecting||openingCamera)return;
 if(!student.value.trim()){status('학생 ID를 입력하세요',true);student.focus();return}
 if(socket?.readyState!==WebSocket.OPEN){status('서버 연결을 확인하세요',true);return}
 openingCamera=true;ready();scanPurpose=purpose;session=null;picture='';el('session').textContent='QR 미인식';el('result').hidden=true;
 try{stopCamera();if(!navigator.mediaDevices)throw Error('HTTPS로 접속하세요');stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1920},height:{ideal:1080}},audio:false});video.srcObject=stream;video.hidden=false;preview.hidden=true;el('placeholder').hidden=true;await video.play();
 scanTimer=setInterval(()=>{if(video.videoWidth)readQR(canvasOf(video,video.videoWidth,video.videoHeight))},400);status(purpose==='collection'?'QR 인식 후 표본 수집 대기':'QR 인식 시 자동 인증');
 }catch(e){status(e instanceof Error?e.message:'카메라를 열 수 없습니다',true)}finally{openingCamera=false;ready()}
}
el('camera').onclick=()=>startCamera('auth');
student.oninput=ready;
function finish(){pending=null;if(timer)clearTimeout(timer);ready()}
el('connect').onclick=()=>{
 if(pending)return;
 try{const url=new URL(endpoint.value.trim());if(!['ws:','wss:'].includes(url.protocol))throw Error();if(location.protocol==='https:'&&url.protocol!=='wss:'){status('HTTPS에서는 wss 주소를 사용하세요',true);return}
 socket?.close();collecting=false;const ws=new WebSocket(url);socket=ws;el('connection').textContent='연결 중';
 const timeout=setTimeout(()=>{if(ws.readyState!==WebSocket.OPEN)ws.close()},10000);
 ws.onopen=()=>{clearTimeout(timeout);if(socket!==ws)return;localStorage.setItem('endpoint',url.toString());el('connection').textContent='연결됨';status('');ready()};
 ws.onclose=()=>{clearTimeout(timeout);if(socket!==ws)return;el('connection').textContent='미연결';if(pending||collecting)status('연결이 끊겼습니다. 결과를 확인한 뒤 다시 시도하세요',true);collecting=false;finish()};
 ws.onerror=()=>{if(socket===ws)status('서버에 연결할 수 없습니다',true)};
 ws.onmessage=(event)=>{
  if(socket!==ws||typeof event.data!=='string')return;
  try{const m=JSON.parse(event.data);
   if(m.type==='rtt_probe'&&(collecting||(pending&&m.attempt_id===pending))&&typeof m.attempt_id==='string'&&typeof m.probe_id==='string'&&typeof m.nonce==='string'){
    ws.send(JSON.stringify({type:'rtt_echo',attempt_id:m.attempt_id,probe_id:m.probe_id,nonce:m.nonce}));return;
   }
   if(collecting){
    if(m.type==='collection_ready')status('수집 대기 · 관리자 화면에서 시작');
    if(m.type==='collection_progress')status(`수집 ${m.completed} / ${m.total}`);
    if(m.type==='collection_done')status(`수집 완료 ${m.completed}개 · 대기 중`);
    if(m.type==='error'){status(m.message||'수집 오류',true);socket?.close()}
    return;
   }
   if(!pending||m.attempt_id!==pending)return;
   if(m.type==='auth_received'){status('인증 중…');return}
   if(m.type==='auth_result'){
    const box=el('result');box.replaceChildren();box.hidden=false;
    const title=document.createElement('strong');title.textContent=m.decision==='approved'?'출석 승인':m.decision==='rejected'?'인증 실패':'추가 확인';box.append(title);
    for(const [label,value] of [['장소',m.place?.decision],['통신',m.relay?.decision],['RTT',typeof m.relay?.rtt_ms==='number'?`${m.relay.rtt_ms.toFixed(3)} ms`:undefined]]){if(value!==undefined){const p=document.createElement('p');p.textContent=`${label}: ${String(value)}`;box.append(p)}}status('완료');finish();
   }
   if(m.type==='error'){status(typeof m.message==='string'?m.message:'인증 오류',true);finish()}
  }catch{/* Ignore malformed messages; never fabricate a result. */}
 };
 }catch{status('ws:// 또는 wss:// 주소를 입력하세요',true)}
};
function authenticate(){
 if(!session||!picture||socket?.readyState!==WebSocket.OPEN||pending)return;
 pending=crypto.randomUUID();localStorage.setItem('student_id',student.value.trim());el('result').hidden=true;ready();
 socket.send(JSON.stringify({type:'auth_request',attempt_id:pending,student_id:student.value.trim(),...session,image:{mime_type:'image/jpeg',data_base64:picture.split(',')[1]},qr_polygon:qrPolygon}));status('인증 중…');
 timer=setTimeout(()=>{status('응답 시간이 초과되었습니다. 결과를 확인하세요',true);finish()},90000);
};
window.addEventListener('pagehide',()=>{stopCamera();socket?.close()});
function beginCollection(){
 if(!session||socket?.readyState!==WebSocket.OPEN)return;
 collecting=true;ready();socket.send(JSON.stringify({type:'collection_ready',student_id:student.value.trim(),...session}));status('수집 대기 · 관리자에서 시작');
}
el('collect').onclick=()=>startCamera('collection');
el('end-collect').onclick=()=>{if(collecting){collecting=false;socket?.close();ready();status('대기 종료 · 다시 연결하세요')}};
if(location.pathname.startsWith('/student/'))el('connect').click();
