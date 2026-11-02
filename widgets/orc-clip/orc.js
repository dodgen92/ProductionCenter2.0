(function(){
'use strict';
// Orc Clip Presenter. Data: Production Center GET /events (type:'clip').
// A ranked clip plays the matching mp3 from audio/ (see lines.js).
// Anything else still uses voice_line from the server (voice_lines/orc/). No secrets here.
const P=new URLSearchParams(location.search),g=k=>P.get(k);
const TESTKEY=(g('test')||'').toLowerCase();
// test=1 is the old cycle. test=wow and test=twitch preview one rank.
const TEST=TESTKEY==='1'||TESTKEY==='wow'||TESTKEY==='twitch',ONCE=g('once')==='1';
const SERVER=(g('server')||'http://localhost:5000').replace(/\/+$/,''),USE_SERVER=g('server')!=='0';
const REWARD=(g('reward')||'Play a Clip').trim().toLowerCase();
const VVOL=Math.min(1,Math.max(0,g('vvol')==null?0.9:+g('vvol')));
const MUTED=g('muted')==='1';
const CVOL=Math.min(1,Math.max(0,g('cvol')==null?1:+g('cvol')));
const MAXDUR=Math.max(5,+(g('maxdur')||60));
const BUFFER=Math.max(0,+(g('buffer')||5)); // seconds added for the embed to load + start (measured ~5-7s in headless Chrome)
// parent= must match the page's hostname. Over http(s) use our own hostname; from file:// fall back to localhost (see README).
const PARENTS=(g('parent')||(/^https?:$/.test(location.protocol)&&location.hostname)||'localhost').split(',').map(s=>s.trim()).filter(Boolean);
const stage=document.getElementById('stage'),$=id=>document.getElementById(id);
const side=(g('side')||'left').toLowerCase()==='right'?'right':'left';
if(g('scale'))stage.style.setProperty('--scale',+g('scale')||1);
const SC=g('scale')?'scaled':'';
const set=(...c)=>{stage.className=[side,SC,...c].filter(Boolean).join(' ');};set();
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const clean=(s,n=25)=>String(s||'').replace(/[\u0000-\u001f\u007f<>&"'`]/g,'').trim().slice(0,n);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pick=a=>a[Math.floor(Math.random()*a.length)];
const LINES={intro:['<b>{u}</b> wants a clip! Lok\'tar!','Clip time, courtesy of <b>{u}</b>!','From the war archives, for <b>{u}</b>!'],
 none:['No clips in the vault yet, <b>{u}</b>. Next time!','The archives are empty, <b>{u}</b>. Zug zug.']};
const line=(k,u)=>pick(LINES[k]).replace('{u}',esc(u));

// resolve voice_line: absolute URL, "/voice_lines/orc/x.mp3", or bare "x.mp3"
function voiceUrl(v){v=String(v||'').trim();if(!v)return '';
  if(/^(https?:|file:|data:|blob:)/i.test(v))return v;
  if(TEST&&/^test\//.test(v))return v;
  if(v[0]==='/')return SERVER+v;
  return SERVER+'/voice_lines/orc/'+encodeURIComponent(v);}
// build the clip embed URL with OUR parent(s); ignores any parent the backend put in
function embedUrl(ev){let u;
  try{u=new URL(ev.embed_url||'https://clips.twitch.tv/embed');}catch(e){u=new URL('https://clips.twitch.tv/embed');}
  if(!/(^|\.)twitch\.tv$/i.test(u.hostname))return '';
  if(!u.searchParams.get('clip')){const id=clean(ev.clip_id,120)||((String(ev.clip_url||'').match(/(?:clips\.twitch\.tv\/|\/clip\/)([\w-]+)/)||[])[1]);if(!id)return '';u.searchParams.set('clip',id);}
  u.searchParams.delete('parent');for(const p of PARENTS)u.searchParams.append('parent',p);
  u.searchParams.set('autoplay','true');u.searchParams.set('muted',MUTED?'true':'false');return u.toString();}
// resolve video_url: absolute http(s), "/clips/x.mp4" (server-relative), or test/ file in test mode
function videoUrl(v){v=String(v||'').trim();if(!v)return '';
  if(/^https?:\/\//i.test(v))return v;
  if(TEST&&/^test\//.test(v))return v;
  if(v[0]==='/')return SERVER+v;
  return SERVER+'/clips/'+encodeURIComponent(v);}
// play a local mp4 in #vid; resolves 'ended'|'timeout'|'error'
function playVideo(src,evDur){return new Promise(res=>{const v=$('vid');let done=false,cap=0;const bar=$('bar').firstElementChild;
  const fin=r=>{if(done)return;done=true;clearTimeout(lt);clearTimeout(cap);v.onended=v.onerror=v.onloadedmetadata=null;res(r);};
  const lt=setTimeout(()=>{if(!(v.readyState>=2&&!v.paused))fin('error');},8000);
  v.onerror=()=>{console.warn('orc clip video failed',src);fin('error');};
  v.onended=()=>fin('ended');
  v.onloadedmetadata=()=>{const real=isFinite(v.duration)&&v.duration>0?v.duration:0;
    const d=Math.min(MAXDUR,(+evDur>0?+evDur:real||30))+BUFFER;cap=setTimeout(()=>fin('timeout'),d*1000);
    const bd=Math.min(MAXDUR,real||+evDur||30);bar.style.transition='none';bar.style.width='0';void bar.offsetWidth;bar.style.transition='width '+bd+'s linear';bar.style.width='100%';};
  v.muted=MUTED;v.volume=CVOL;v.src=src;
  const pr=v.play();if(pr)pr.then(()=>{window.orcClip.vplay='ok';}).catch(e=>{window.orcClip.vplay=String(e.name||e);console.warn('orc clip play',e);
    // autoplay with sound refused: retry muted so at least the picture plays
    if(e&&e.name==='NotAllowedError'){v.muted=true;v.play().catch(()=>fin('error'));}else fin('error');});
  });}
function stopVideo(){const v=$('vid');try{v.pause();}catch(_){}v.removeAttribute('src');v.load();}
// Load the mp4 and pause on the first frame. The clip stays held until the orc finishes.
function holdVideo(src){return new Promise(res=>{const v=$('vid');let done=false;
  const fin=ok=>{if(done)return;done=true;clearTimeout(timer);v.onloadeddata=v.onerror=null;res(ok);};
  const timer=setTimeout(()=>fin(false),8000);
  v.onerror=()=>{console.warn('orc clip hold failed',src);fin(false);};
  v.onloadeddata=()=>{
    // A muted play/pause is what actually paints frame 0. Always pause again,
    // even if the play promise comes back late, so the clip cannot start early.
    v.muted=true;let settled=false;
    const snap=()=>{try{v.pause();}catch(e){}if(v.currentTime>0.05){try{v.currentTime=0;}catch(e){}}v.muted=MUTED;v.volume=CVOL;if(settled)return;settled=true;fin(true);};
    const pr=v.play();setTimeout(snap,500);
    if(pr&&pr.then)pr.then(snap).catch(snap);else snap();
  };
  v.volume=0;v.muted=true;v.preload='auto';v.src=src;
});}
// Same ending rules as playVideo, but the file is already loaded and paused.
function startHeldVideo(evDur){return new Promise(res=>{const v=$('vid');let done=false,cap=0;const bar=$('bar').firstElementChild;
  const fin=r=>{if(done)return;done=true;clearTimeout(cap);v.onended=v.onerror=null;res(r);};
  v.onerror=()=>fin('error');
  v.onended=()=>fin('ended');
  const real=isFinite(v.duration)&&v.duration>0?v.duration:0;
  const d=Math.min(MAXDUR,(+evDur>0?+evDur:real||30))+BUFFER;cap=setTimeout(()=>fin('timeout'),d*1000);
  const bd=Math.min(MAXDUR,real||+evDur||30);bar.style.transition='none';bar.style.width='0';void bar.offsetWidth;bar.style.transition='width '+bd+'s linear';bar.style.width='100%';
  v.muted=MUTED;v.volume=CVOL;
  const pr=v.play();if(pr)pr.then(()=>{window.orcClip.vplay='ok';}).catch(e=>{window.orcClip.vplay=String(e.name||e);console.warn('orc clip play',e);
    if(e&&e.name==='NotAllowedError'){v.muted=true;v.play().catch(()=>fin('error'));}else fin('error');});
});}
let actx=null;
function sameOrigin(u){try{return new URL(u,location.href).origin===location.origin&&location.origin!=='null';}catch(e){return false;}}
// Drop the music-bed tail quickly so it does not sit on top of the clip.
function fadeTail(a){const from=a.volume;let step=0;const id=setInterval(()=>{step+=1;
  try{a.volume=Math.max(0,from*(1-step/8));}catch(e){}
  if(step>=8){clearInterval(id);try{a.pause();}catch(e){}}
},40);}
function playVoice(src,opts){opts=opts||{};return new Promise(res=>{if(!src)return res(false);
  const a=new Audio(src);a.volume=VVOL;let done=false,raf=0,lvl=0,endTimer=0;const lip=$('lip');
  const voiceEnd=+opts.voiceEnd;
  const fin=ok=>{if(done)return;done=true;clearTimeout(t);clearTimeout(endTimer);cancelAnimationFrame(raf);lip.style.transform='';stage.classList.remove('lips');res(ok);};
  const t=setTimeout(()=>{try{a.pause();}catch(_){}fin(true);},20000); // hard cap on a voice line
  // audio-synced bounce: only when the mp3 is same-origin (served by the Production Center), else CSS sway
  let an=null,buf=null;
  if(sameOrigin(src)){try{actx=actx||new (window.AudioContext||window.webkitAudioContext)();if(actx.state==='suspended')actx.resume();
    const s=actx.createMediaElementSource(a);an=actx.createAnalyser();an.fftSize=1024;buf=new Uint8Array(an.fftSize);s.connect(an);an.connect(actx.destination);}catch(e){an=null;}}
  const frame=()=>{if(done)return;an.getByteTimeDomainData(buf);let s=0;for(let i=0;i<buf.length;i++){const v=(buf[i]-128)/128;s+=v*v;}
    const v=Math.min(1,Math.sqrt(s/buf.length)*6);lvl+=(v-lvl)*(v>lvl?.6:.25);window.orcClip.lip=(window.orcClip.lip||0)+1;
    lip.style.transform=`translateY(${-lvl*9}px) scale(${1+lvl*.025},${1+lvl*.02}) rotate(${Math.sin(a.currentTime*5)*lvl*1.5}deg)`;raf=requestAnimationFrame(frame);};
  // 'ended' is the safety net: if the file stops before voice_end_s, start the clip anyway.
  a.onended=()=>{stopCountdown();fin(true);};
  a.onerror=()=>{console.warn('orc voice line failed',src);stopCountdown();fin(false);};
  a.play().then(()=>{
    window.orcClip.voiceAt=performance.now();
    if(an){stage.classList.add('lips');raf=requestAnimationFrame(frame);}
    if(!(voiceEnd>0))return;
    const doneTalking=()=>{window.orcClip.voiceEndAt=performance.now();fadeTail(a);fin(true);};
    if(opts.countdown)startCountdown(voiceEnd,doneTalking);
    else endTimer=setTimeout(doneTalking,voiceEnd*1000);
  }).catch(e=>{console.warn('orc voice play',e);stopCountdown();fin(false);});
  window.orcClip.lastVoice=src;});}

// lines.js: one recorded take per rank. No match means use the server voice_line.
function findLine(source,rank){
  const table=window.ORC_LINES||{};
  const key=String(source||'').toLowerCase();
  const pool=Array.isArray(table[key])?table[key]:[];
  const n=Math.floor(+rank);
  if(!(n>0))return null;
  for(let i=0;i<pool.length;i++){
    const row=pool[i];
    if(!row||!row.file||!row.text)continue;
    if(Math.floor(+row.rank)===n)return row;
  }
  return null;
}
function rankText(source,rank){
  const n=Math.floor(+rank);
  if(!(n>0))return '';
  const s=String(source||'').toLowerCase();
  if(s==='wow')return 'WoW #'+n;
  if(s==='twitch')return 'Twitch #'+n;
  return '';
}
function viewsText(value){
  if(value==null||value==='')return '';
  const n=Math.floor(+value);
  if(!isFinite(n)||n<0)return '';
  return n.toLocaleString('en-US')+(n===1?' view':' views');
}
function fillCard(ev,user){
  const bc=clean(ev.broadcaster_name||ev.broadcaster),tt=String(ev.title||'').replace(/[\u0000-\u001f\u007f]/g,'').trim().slice(0,90)||'Clip';
  $('title').textContent=bc?bc+': '+tt:tt;const T=$('title');T.style.fontSize=T.textContent.length>44?'22px':T.textContent.length>34?'25px':'';
  $('creator').innerHTML=ev.creator?'clipped by <b>'+esc(clean(ev.creator))+'</b>':'';
  $('redeemer').innerHTML='redeemed by <b>'+esc(user)+'</b>';
  const th=String(ev.thumbnail_url||'');if(/^https:\/\//.test(th))$('thumb').src=th;else $('thumb').removeAttribute('src');
  const rank=rankText(ev.source,ev.rank),views=viewsText(ev.view_count);
  $('rank').textContent=rank;$('views').textContent=views;
  $('stats').hidden=!rank&&!views;
}

// Film countdown. Length is voice_end_s, measured from when the mp3 starts.
// The big number hits 0 at that moment. A short beat later the caller starts the clip.
let countRaf=0,countTimer=0,countHold=0;
function clearCountTimers(){cancelAnimationFrame(countRaf);countRaf=0;clearTimeout(countTimer);countTimer=0;clearTimeout(countHold);countHold=0;}
function stopCountdown(){clearCountTimers();stage.classList.remove('held');}
function prepareLeader(seconds){
  const n=Math.max(0,Math.ceil(+seconds||0));
  $('count').textContent=String(n);
  $('hand').style.transform='rotate(0deg)';
  stage.classList.add('held');
}
function startCountdown(seconds,onZero){
  clearCountTimers();
  const total=Math.max(0,+seconds||0);
  const num=$('count'),hand=$('hand');
  const t0=performance.now();
  let fired=false;
  function fire(){
    if(fired)return;fired=true;
    cancelAnimationFrame(countRaf);countRaf=0;clearTimeout(countTimer);countTimer=0;
    num.textContent='0';hand.style.transform='rotate(0deg)';
    countHold=setTimeout(()=>{countHold=0;if(onZero)onZero();},150);
  }
  function draw(now){
    if(fired)return;
    const left=(t0+total*1000-now)/1000;
    hand.style.transform='rotate('+(((now-t0)/1000)%1)*360+'deg)';
    if(left<=0){fire();return;}
    num.textContent=String(Math.ceil(left));
    countRaf=requestAnimationFrame(draw);
  }
  stage.classList.add('held');
  if(total<=0){fire();return;}
  num.textContent=String(Math.ceil(total));
  hand.style.transform='rotate(0deg)';
  countTimer=setTimeout(fire,total*1000);
  countRaf=requestAnimationFrame(draw);
}

const queue=[];let busy=false;
function present(ev){queue.push(ev);if(!busy)run();}
// Play the clip. frameUp means the gold frame is already on screen (countdown just ended).
// armed means the mp4 is paused on its first frame and only needs play().
// away slides the orc off. The next alert adds "in", which walks him back.
// classList keeps the gold frame's animation running. set() would rebuild
// every class and could start that animation over.
function parkOrc(extra){
  stage.classList.remove('in','say','talking');
  if(extra!=='isvid')stage.classList.remove('isvid');
  stage.classList.add('clip','away');
  if(extra)stage.classList.add(extra);
}
async function presentClip(ev,user,opts){opts=opts||{};
 const vsrc=videoUrl(ev.video_url),emb=(ev.embed_url||ev.clip_id||ev.clip_url)?embedUrl(ev):'';
 fillCard(ev,user);
 const f=$('clip');let shown=false;
 if(vsrc){
  if(!opts.frameUp){set('in','clip','isvid');await wait(750);}
  parkOrc('isvid');
  window.orcClip.clipAt=performance.now();
  const r=opts.armed?await startHeldVideo(ev.duration):await playVideo(vsrc,ev.duration);
  window.orcClip.vresult=r;
  stopVideo();shown=r!=='error';
  if(!shown&&!emb){set('in','clipout');await wait(500);$('msg').innerHTML=line('none',user);set('in','say');await wait(2600);}
 }
 if(!shown&&emb){
  const dur=Math.min(MAXDUR,(+ev.duration>0?+ev.duration:30))+BUFFER;
  // Twitch refuses autoplay if the iframe was hidden, or if anything overlaps it.
  // The countdown is gone before we get here. A frame that just animated in still waits.
  // A failed mp4 already slid him off. Do not walk him back in for the iframe.
  // The wait before the iframe src is what Twitch needs for autoplay. Leave it.
  if(!vsrc)set('in','clip');
  await wait(opts.frameUp?100:750);
  parkOrc();
  window.orcClip.clipAt=performance.now();
  f.src=emb;
  const bar=$('bar').firstElementChild;bar.style.transition='none';bar.style.width='0';void bar.offsetWidth;bar.style.transition='width '+dur+'s linear';bar.style.width='100%';
  await wait(dur*1000);shown=true;}
 if(shown){
  stage.classList.remove('in','say','talking','clip');
  stage.classList.add('clipout','away');
  if(vsrc&&!String(f.src||'').includes('twitch'))stage.classList.add('isvid');
  else stage.classList.remove('isvid');
  await wait(500);
 }
 f.src='about:blank';$('thumb').removeAttribute('src');
}
async function run(){busy=true;
 while(queue.length){const ev=queue.shift();
  const user=clean(ev.user||ev.login)||'someone';
  const vsrc=videoUrl(ev.video_url),emb=(ev.embed_url||ev.clip_id||ev.clip_url)?embedUrl(ev):'';
  const hasClip=!!(vsrc||emb);
  // A ranked line only makes sense when we actually have that clip to show.
  const ranked=hasClip?findLine(ev.source,ev.rank):null;
  const voiceEnd=ranked?+ranked.voice_end_s:0;
  const hold=!!(ranked&&voiceEnd>0);
  const fallback=voiceUrl(ev.voice_line);
  window.orcClip.last={user,voice:ranked?('audio/'+ranked.file):fallback,embed:emb,source:ev.source||'',rank:+ev.rank||0};
  if(ranked)$('msg').textContent=ranked.text;
  else $('msg').innerHTML=line(hasClip?'intro':'none',user);
  set('in');
  // Fetch the first frame while the orc slides in, so the countdown has a picture under it.
  const holding=hold&&vsrc?holdVideo(vsrc):null;
  await wait(1000);
  let playedRanked=false,armed=false;
  if(ranked){
   if(hold){
    fillCard(ev,user);
    armed=holding?await holding:false;
    if(!armed&&vsrc)stopVideo();
    set('in','say','talking','clip',armed?'isvid':'');
    prepareLeader(voiceEnd);
   }else set('in','say','talking');
   playedRanked=await playVoice('audio/'+encodeURI(ranked.file),{voiceEnd:voiceEnd,countdown:hold});
   if(!playedRanked){
    // The ranked mp3 failed. Do what the widget used to do: the server voice line, or a short pause.
    stopCountdown();stage.classList.remove('isvid');stopVideo();armed=false;
    set('in','say','talking');
    const spoke=fallback?await playVoice(fallback):false;
    if(!spoke)await wait(hasClip?1400:2600);
   }
  }else{
   set('in','say','talking');
   const spoke=await playVoice(fallback);
   if(!spoke)await wait(hasClip?1400:2600); // no line: show him briefly
  }
  stopCountdown();
  if(hasClip)await presentClip(ev,user,{frameUp:!!(playedRanked&&hold),armed:!!(playedRanked&&armed)});
  else{set('in','say');await wait(800);}
  // popOut starts on screen. Skip it when he already slid off for the clip.
  if(!stage.classList.contains('away')){set('out');await wait(850);}
  set();await wait(400);
 }
 busy=false;}
window.orcClip={present,queue,parents:PARENTS,embedUrl,videoUrl,findLine,rankText,viewsText};

// ---- Production Center feed: GET /events?since=N (since=-1 first = sync cursor, skip backlog) ----
const seen=new Set();
function onFeed(ev){if(ev.type!=='clip')return;
  if(ev.reward&&String(ev.reward).trim().toLowerCase()!==REWARD)return;
  const k=ev.id!=null?'id:'+ev.id:'';if(k){if(seen.has(k))return;seen.add(k);}
  present(ev);}
if(USE_SERVER&&!(TEST&&g('server')==null)){let since=-1,delay=1000;
 (async function poll(){
  try{const r=await fetch(SERVER+'/events?since='+since,{cache:'no-store'});const j=await r.json();
   if(since<0)since=j.last_id||0;
   else{for(const ev of j.events||[]){since=Math.max(since,ev.id||0);try{onFeed(ev);}catch(e){console.warn(e);}}since=Math.max(since,j.last_id||0);}
   delay=1000;
  }catch(e){delay=Math.min(delay*2,15000);}
  setTimeout(poll,delay);})();}

if(TESTKEY==='1'){const clip=g('clip')||'IncredulousAbstemiousFennelImGlitch';
 const evs=[{type:'clip',user:'Thrallbert',voice_line:'test/voice-test.mp3',video_url:'test/clip-test.mp4',title:'Lok\'tar ogar!',creator:'Peonwork',broadcaster_name:'Durotan_Live',duration:0},
  {type:'clip',user:'Garroshka',voice_line:'test/voice-test.mp3',clip_id:clip,embed_url:'https://clips.twitch.tv/embed?clip='+clip,title:'Test clip: Lok\'tar ogar!',creator:'Peonwork',broadcaster_name:'Durotan_Live',duration:+(g('testdur')||8)},
  {type:'clip',user:'Jainabelle',voice_line:'',clip_id:''}];
 let i=0;present(evs[i++]);if(!ONCE)setInterval(()=>{if(!busy&&!queue.length)present(evs[i++%evs.length]);},4000);}
else if(TESTKEY==='wow'||TESTKEY==='twitch'){
 // Preview one rank with the local test clip. A rank with no line falls back to a silent orc, then the clip.
 let rank=Math.floor(+g('rank'));if(!(rank>0))rank=1;
 const ev={type:'clip',user:'Thrallbert',voice_line:'',video_url:'test/clip-test.mp4',
  title:TESTKEY==='wow'?'Test clip from Azeroth':'Test clip from Twitch',
  creator:'Peonwork',broadcaster_name:'Durotan_Live',duration:5,
  source:TESTKEY,rank:rank,view_count:12345};
 present(ev);if(!ONCE)setInterval(()=>{if(!busy&&!queue.length)present(Object.assign({},ev));},4000);}
})();
