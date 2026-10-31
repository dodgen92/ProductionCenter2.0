(function(){
'use strict';
// Pandaren Counselor. Data: Production Center GET /events (redemptions), GET /counsel, GET /tts. No secrets here.
const P=new URLSearchParams(location.search),g=k=>P.get(k);
const TEST=g('test')==='1',ONCE=g('once')==='1';
const SERVER=(g('server')||'http://localhost:5000').replace(/\/+$/,'');
const REWARD=(g('reward')||'Ask the Monk').trim().toLowerCase(),REWARD_ID=(g('rewardid')||'').trim();
const MAXLEN=200,HOLD=Math.max(4,+(g('duration')||6))*1000;
const MUTE=g('tts')==='0',BROWSER_TTS=!MUTE&&'speechSynthesis' in window,LIVE=!MUTE&&g('livetts')!=='0';
const VOICE=g('voice')||'en-HK-SamNeural',RATE=g('rate')||'-5%',PITCH=g('pitch')||'+0Hz';
const VOL=Math.min(1,Math.max(0,+(g('vol')||1)));
const SAY_NAME=g('sayname')!=='0';
const stage=document.getElementById('stage'),$=id=>document.getElementById(id);
const side=(g('side')||'left').toLowerCase()==='right'?'right':'left';
if(g('scale'))stage.style.setProperty('--scale',+g('scale')||1);
const set=(...c)=>{stage.className=[side,...c].filter(Boolean).join(' ');};set();
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const pick=a=>a[Math.floor(Math.random()*a.length)];
const log=window.__monkLog=[];const mark=s=>log.push([s,Math.round(performance.now())]);

// ---- local fallback sayings (used when /counsel is down) ----
const SAYINGS=['A cup poured in a hurry spills on the table. Slow down, friend, and the answer will steep.',
 'Even the strongest brew starts as plain water and patience.','When the path is foggy, take the next small step. The mist clears for walkers, not worriers.',
 'Balance is not standing still. It is a hundred tiny wobbles, corrected with a smile.','Rest is part of the training. The bamboo grows in the quiet, too.',
 'If the problem is too big to lift, share the load. Even a monk calls friends to carry the keg.',
 'You cannot pour from an empty kettle. Refill yourself first.','Mistakes are just practice wearing a disguise.',
 'The loudest thought in your head is not always the wisest one. Let it cool like tea.','Laugh at your stumbles. The ground is a patient teacher.'];
const CLOUDY=['The tea leaves are cloudy right now... but an old monk always has a saying in his pocket.',
 'Hmm, the spirits of the brew are napping. Here is some old wisdom instead.'];
const EMPTY='You came to the monk with an empty cup! Ask me a question next time, friend.';

// ---- backend ----
async function getJSON(url,ms){const ac=new AbortController(),to=setTimeout(()=>ac.abort(),ms);
 try{const r=await fetch(url,{signal:ac.signal,cache:'no-store'});if(!r.ok)throw new Error('http '+r.status);return await r.json();}finally{clearTimeout(to);}}
async function counsel(q,user){
 if(TEST&&g('server')==null)return{answer:pick(SAYINGS),source:'mock'};
 const j=await getJSON(SERVER+'/counsel?'+new URLSearchParams({q,user}),12000);
 if(!j||typeof j.answer!=='string'||!j.answer.trim())throw new Error('bad counsel');return j;}

// ---- voice: live /tts (lip-sync bounce), else browser voice, else timer ----
const talkEl=$('talk');let actx=null;
async function speakLive(text,el){
 const q=new URLSearchParams({text,voice:VOICE,rate:RATE,pitch:PITCH});
 const ac=new AbortController(),to=setTimeout(()=>ac.abort(),6000);
 let blob;try{const r=await fetch(SERVER+'/tts?'+q,{signal:ac.signal,cache:'no-store'});if(!r.ok)throw new Error('tts http '+r.status);blob=await r.blob();if(!blob.size)throw new Error('empty audio');}finally{clearTimeout(to);}
 const url=URL.createObjectURL(blob),a=new Audio(url);a.volume=VOL;
 await new Promise((ok,bad)=>{a.onloadedmetadata=ok;a.onerror=()=>bad(new Error('bad audio'));setTimeout(()=>bad(new Error('metadata timeout')),4000);});
 let an=null,buf=null;
 try{actx=actx||new (window.AudioContext||window.webkitAudioContext)();if(actx.state==='suspended')await actx.resume();
  const src=actx.createMediaElementSource(a);an=actx.createAnalyser();an.fftSize=1024;buf=new Uint8Array(an.fftSize);src.connect(an);an.connect(actx.destination);}catch(e){an=null;}
 return new Promise((resolve,reject)=>{
  let done=false,raf=0,lvl=0;
  const fin=()=>{if(done)return;done=true;cancelAnimationFrame(raf);if(el)el.textContent=text;stage.classList.remove('talk','lips');talkEl.style.transform='';URL.revokeObjectURL(url);resolve();};
  stage.classList.add('talk');if(an)stage.classList.add('lips');
  const frame=()=>{if(done)return;const dur=a.duration&&isFinite(a.duration)?a.duration:text.length*.07;
   if(el)el.textContent=text.slice(0,Math.ceil(text.length*Math.min(1,a.currentTime/(dur*.92))));
   if(an){an.getByteTimeDomainData(buf);let s=0;for(let i=0;i<buf.length;i++){const v=(buf[i]-128)/128;s+=v*v;}
    const t=Math.min(1,Math.sqrt(s/buf.length)*6);lvl+=(t-lvl)*(t>lvl?.6:.25);window.__monkLip=(window.__monkLip||0)+1;
    talkEl.style.transform=`translateY(${-lvl*7}px) scale(${1+lvl*.025},${1+lvl*.02}) rotate(${Math.sin(a.currentTime*5)*lvl*1.4}deg)`;}
   raf=requestAnimationFrame(frame);};
  a.onended=fin;a.onerror=()=>{if(!done){done=true;stage.classList.remove('talk','lips');reject(new Error('play error'));}};
  a.play().then(()=>{raf=requestAnimationFrame(frame);},e=>{done=true;stage.classList.remove('talk','lips');reject(e);});
  setTimeout(fin,(a.duration||25)*1000+3000);
 });
}
function speakBrowser(text,el){
 return new Promise(resolve=>{
  const est=Math.max(1800,text.length*72);let done=false;const t0=Date.now();
  const fin=()=>{if(done)return;done=true;clearInterval(tk);clearTimeout(sf);if(el)el.textContent=text;stage.classList.remove('talk');resolve();};
  stage.classList.add('talk');
  const tk=setInterval(()=>{const n=Math.floor(text.length*(Date.now()-t0)/est);if(el)el.textContent=text.slice(0,n);if(!BROWSER_TTS&&n>=text.length)fin();},40);
  const sf=setTimeout(fin,est*2+3000);if(!BROWSER_TTS)return;
  try{speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(text);u.lang='en-GB';u.rate=.92;u.volume=VOL;
   const vs=speechSynthesis.getVoices()||[];const v=vs.find(v=>/en-(HK|SG|IN|GB)/i.test(v.lang))||vs.find(v=>/^en/i.test(v.lang));if(v)u.voice=v;
   u.onend=fin;u.onerror=()=>setTimeout(fin,Math.max(0,est-(Date.now()-t0)));speechSynthesis.speak(u);
   setTimeout(()=>{if(!done&&!speechSynthesis.speaking&&!speechSynthesis.pending)setTimeout(fin,Math.max(0,est-(Date.now()-t0)));},1500);
  }catch(e){setTimeout(fin,est);}
 });
}
async function speak(text,el,tag){
 mark(tag+':start');
 try{
  if(MUTE){window.__monkMode='muted';return await speakBrowser(text,el);}
  if(LIVE){try{await speakLive(text,el);window.__monkMode='live';return;}catch(e){console.warn('live TTS failed, falling back',e&&e.message);}}
  window.__monkMode='browser';return await speakBrowser(text,el);
 }finally{mark(tag+':end');}
}

// ---- one redemption ----
const clip=s=>{s=String(s||'').replace(/\s+/g,' ').trim();return s.length>MAXLEN?s.slice(0,MAXLEN-1)+'…':s;};
async function handle(job){
 const who=clip(job.user).slice(0,25)||'Someone',q=clip(job.input);
 $('who').textContent=who;$('a').textContent='';
 const qEl=$('q');qEl.innerHTML='';const b=document.createElement('b');b.textContent=who+' asks: ';const qs=document.createElement('span');qEl.append(b,qs);
 set('in');await wait(1000);set('in','show');await wait(400);
 if(!q){$('hdr').textContent='Hmm?';qs.textContent='';await speak(EMPTY,$('a'),'empty');}
 else{
  $('hdr').textContent='Ask the Monk';
  qs.textContent=q;
  await speak((SAY_NAME?who+' asks: ':'')+q,null,'question');   // 1) read the question first
  set('in','show','ponder');mark('ponder');                      // 2) hmm: tilt, steam, dots
  const p0=Date.now();let ans;
  mark('counsel:fetch');
  try{const r=await counsel(q,who);ans=clip(r.answer);window.__monkSource=r.source||'?';}
  catch(e){ans=pick(CLOUDY)+' '+pick(SAYINGS);window.__monkSource='local';}
  mark('counsel:done');
  await wait(Math.max(0,1800-(Date.now()-p0)));
  set('in','show');
  await speak(ans,$('a'),'answer');                              // 3) answer, bubble types along
 }
 await wait(HOLD);
 set('out');await wait(850);set();await wait(400);
}
const queue=[];let busy=false;
function fire(user,input){if(queue.length>=20)return;queue.push({user:String(user||''),input:String(input||'').slice(0,1000)});if(!busy)run();}
async function run(){busy=true;while(queue.length){const j=queue.shift();try{await handle(j);}catch(e){console.warn(e);set();}}busy=false;}
window.monkCounselor={fire,queue};

if(TEST){const demo=[['Jainabelle','How do I stop tilting after a bad wipe?'],['Thrallbert','Should I main a tank or a healer?'],['Murlocmaster','Any tips for staying focused while studying?']];
 let i=0;const go=()=>{if(!busy&&!queue.length){const d=demo[i++%demo.length];fire(d[0],d[1]);}};go();if(!ONCE)setInterval(go,6000);if(g('server')==null)return;}

// ---- Production Center feed: GET /events?since=N (since=-1 first = sync cursor, skip backlog) ----
const seen=new Set();
const match=(t,id)=>(REWARD_ID&&id===REWARD_ID)||String(t||'').trim().toLowerCase()===REWARD;
let since=-1,delay=1000;
(async function poll(){
 try{const j=await getJSON(SERVER+'/events?since='+since,5000);
  if(since<0)since=j.last_id||0;
  else{for(const ev of j.events||[]){since=Math.max(since,ev.id||0);
    if(ev.type!=='redemption'||!match(ev.reward,ev.reward_id))continue;
    const k=ev.redemption_id||('id:'+ev.id);if(seen.has(k))continue;seen.add(k);
    fire(ev.user||ev.login,ev.input);}
   since=Math.max(since,j.last_id||0);}
  delay=1000;
 }catch(e){delay=Math.min(delay*2,15000);}
 setTimeout(poll,delay);
})();
})();
