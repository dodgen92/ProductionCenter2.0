(function(){
'use strict';
// Orc Clip Presenter. Data: Production Center GET /events (type:'clip'), voice lines from GET /voice_lines/orc/<file>. No secrets here.
const P=new URLSearchParams(location.search),g=k=>P.get(k);
const TEST=g('test')==='1',ONCE=g('once')==='1';
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
let actx=null;
function sameOrigin(u){try{return new URL(u,location.href).origin===location.origin&&location.origin!=='null';}catch(e){return false;}}
function playVoice(src){return new Promise(res=>{if(!src)return res(false);
  const a=new Audio(src);a.volume=VVOL;let done=false,raf=0,lvl=0;const lip=$('lip');
  const fin=ok=>{if(done)return;done=true;clearTimeout(t);cancelAnimationFrame(raf);lip.style.transform='';stage.classList.remove('lips');res(ok);};
  const t=setTimeout(()=>{try{a.pause();}catch(_){}fin(true);},20000); // hard cap on a voice line
  // audio-synced bounce: only when the mp3 is same-origin (served by the Production Center), else CSS sway
  let an=null,buf=null;
  if(sameOrigin(src)){try{actx=actx||new (window.AudioContext||window.webkitAudioContext)();if(actx.state==='suspended')actx.resume();
    const s=actx.createMediaElementSource(a);an=actx.createAnalyser();an.fftSize=1024;buf=new Uint8Array(an.fftSize);s.connect(an);an.connect(actx.destination);}catch(e){an=null;}}
  const frame=()=>{if(done)return;an.getByteTimeDomainData(buf);let s=0;for(let i=0;i<buf.length;i++){const v=(buf[i]-128)/128;s+=v*v;}
    const v=Math.min(1,Math.sqrt(s/buf.length)*6);lvl+=(v-lvl)*(v>lvl?.6:.25);window.orcClip.lip=(window.orcClip.lip||0)+1;
    lip.style.transform=`translateY(${-lvl*9}px) scale(${1+lvl*.025},${1+lvl*.02}) rotate(${Math.sin(a.currentTime*5)*lvl*1.5}deg)`;raf=requestAnimationFrame(frame);};
  a.onended=()=>fin(true);a.onerror=()=>{console.warn('orc voice line failed',src);fin(false);};
  a.play().then(()=>{if(an){stage.classList.add('lips');raf=requestAnimationFrame(frame);}}).catch(e=>{console.warn('orc voice play',e);fin(false);});
  window.orcClip.lastVoice=src;});}

const queue=[];let busy=false;
function present(ev){queue.push(ev);if(!busy)run();}
async function run(){busy=true;
 while(queue.length){const ev=queue.shift();
  const user=clean(ev.user||ev.login)||'someone',src=voiceUrl(ev.voice_line),emb=(ev.embed_url||ev.clip_id||ev.clip_url)?embedUrl(ev):'';
  window.orcClip.last={user,voice:src,embed:emb};
  $('msg').innerHTML=line((emb||ev.video_url)?'intro':'none',user);
  set('in');await wait(1000);
  set('in','say','talking');
  const spoke=await playVoice(src);
  if(!spoke)await wait((emb||ev.video_url)?1400:2600); // no line: show him briefly
  set('in','say');
  const vsrc=videoUrl(ev.video_url);
  if(vsrc||emb){
   const bc=clean(ev.broadcaster_name||ev.broadcaster),tt=String(ev.title||'').replace(/[\u0000-\u001f\u007f]/g,'').trim().slice(0,90)||'Clip';
   $('title').textContent=bc?bc+': '+tt:tt;const T=$('title');T.style.fontSize=T.textContent.length>44?'22px':T.textContent.length>34?'25px':'';
   $('creator').innerHTML=ev.creator?'clipped by <b>'+esc(clean(ev.creator))+'</b>':'';
   $('redeemer').innerHTML='redeemed by <b>'+esc(user)+'</b>';
   const th=String(ev.thumbnail_url||'');if(/^https:\/\//.test(th))$('thumb').src=th;else $('thumb').removeAttribute('src');
   const f=$('clip');let shown=false;
   if(vsrc){stage.classList.add('isvid');set('in','clip','isvid');await wait(750);
    const r=await playVideo(vsrc,ev.duration);window.orcClip.vresult=r;stopVideo();shown=r!=='error';
    if(!shown&&!emb){set('in','clipout');await wait(500);$('msg').innerHTML=line('none',user);set('in','say');await wait(2600);}}
   if(!shown&&emb){
    const dur=Math.min(MAXDUR,(+ev.duration>0?+ev.duration:30))+BUFFER;
    set('in','clip');await wait(750); // frame fully visible first: Twitch refuses autoplay on hidden/transparent iframes
    f.src=emb;
    const bar=$('bar').firstElementChild;bar.style.transition='none';bar.style.width='0';void bar.offsetWidth;bar.style.transition='width '+dur+'s linear';bar.style.width='100%';
    await wait(dur*1000);shown=true;}
   if(shown){set('in','clipout'+(vsrc&&!f.src.includes('twitch')?' isvid':''));await wait(500);}
   f.src='about:blank';$('thumb').removeAttribute('src');
  }else await wait(800);
  set('out');await wait(850);set();await wait(400);
 }
 busy=false;}
window.orcClip={present,queue,parents:PARENTS,embedUrl,videoUrl};

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

if(TEST){const clip=g('clip')||'IncredulousAbstemiousFennelImGlitch';
 const evs=[{type:'clip',user:'Thrallbert',voice_line:'test/voice-test.mp3',video_url:'test/clip-test.mp4',title:'Lok\'tar ogar!',creator:'Peonwork',broadcaster_name:'Durotan_Live',duration:0},
  {type:'clip',user:'Garroshka',voice_line:'test/voice-test.mp3',clip_id:clip,embed_url:'https://clips.twitch.tv/embed?clip='+clip,title:'Test clip: Lok\'tar ogar!',creator:'Peonwork',broadcaster_name:'Durotan_Live',duration:+(g('testdur')||8)},
  {type:'clip',user:'Jainabelle',voice_line:'',clip_id:''}];
 let i=0;present(evs[i++]);if(!ONCE)setInterval(()=>{if(!busy&&!queue.length)present(evs[i++%evs.length]);},4000);}
})();
