(function(){
'use strict';
const P=new URLSearchParams(location.search),g=k=>P.get(k);
const CH=(g('channel')||g('twitch')||'').replace(/^#/,'').toLowerCase().trim();
const TEST=g('test')==='1',ONCE=g('once')==='1',LEARN=g('learn')==='1';
const REWARD=(g('reward')||'Gnome Fact').trim(),REWARD_LC=REWARD.toLowerCase();
const REWARD_ID=(g('rewardid')||'').trim();
const SERVER=(g('server')||'http://localhost:5000').replace(/\/+$/,''),USE_SERVER=g('server')!=='0';
const CMD=(g('cmd')||'').toLowerCase(),CMDMODS=g('cmdmods')==='1';
const DUR=Math.max(6,+(g('duration')||12))*1000;
const MUTE=g('tts')==='0',TTS=!MUTE&&'speechSynthesis' in window;
// live TTS via Production Center /tts (edge-tts neural voices). ?voice= ?rate= ?pitch= are passed through as-is.
const LIVE=!MUTE&&USE_SERVER&&g('livetts')!=='0',LIVE_VOICE=g('voice')||'en-US-AriaNeural',LIVE_RATE=g('rate')||'+8%',LIVE_PITCH=g('pitch')||'+10Hz';
const num=(v,d)=>{const n=parseFloat(v);return isFinite(n)&&!/[%a-z]/i.test(v||'')?n:d;};
const VOICE=(g('voice')||'').toLowerCase().replace(/^[a-z]{2}-[a-z]{2}-/,'').replace(/neural$/,''),RATE=num(g('rate'),1),PITCH=num(g('pitch'),1.3),VOL=Math.min(1,Math.max(0,+(g('vol')||1)));
const stage=document.getElementById('stage');
const factEl=document.getElementById('fact'),whoEl=document.getElementById('who'),learnEl=document.getElementById('learn');
const pos=(g('pos')||'br').toLowerCase();if(['bl','br','tl','tr'].includes(pos))stage.className=pos;
if(g('scale'))stage.style.setProperty('--scale',g('scale'));
const base=stage.className;
const FACTS=(window.GNOME_FACTS||window.FACTS||[]).filter(f=>typeof f==='string'&&f.trim());
if(!FACTS.length)FACTS.push('My fact list is empty! Add some facts to facts/facts.js.');
// no-repeat shuffle: every fact plays once before any repeats (and no back-to-back across decks)
let deck=[],last='';
function next(){if(!deck.length){deck=[...FACTS];for(let i=deck.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[deck[i],deck[j]]=[deck[j],deck[i]];}
  if(deck.length>1&&deck[deck.length-1]===last)[deck[0],deck[deck.length-1]]=[deck[deck.length-1],deck[0]];}
  return last=deck.pop();}
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const set=(...c)=>{stage.className=[base,...c].join(' ');};

// ---- voice selection (voices can load late: voiceschanged) ----
let voice=null;
function pickVoice(){if(!TTS)return;const vs=speechSynthesis.getVoices()||[];if(!vs.length)return;
  const en=vs.filter(v=>/^en/i.test(v.lang));
  const fem=/female|zira|aria|jenny|hazel|susan|samantha|victoria|karen|moira|tessa|libby|sonia|emma|michelle|serena|fiona|catherine|eva|linda|heera/i;
  voice=(VOICE&&vs.find(v=>v.name.toLowerCase().includes(VOICE)))||en.find(v=>fem.test(v.name))||en[0]||vs[0]||null;}
if(TTS){pickVoice();speechSynthesis.addEventListener?speechSynthesis.addEventListener('voiceschanged',pickVoice):(speechSynthesis.onvoiceschanged=pickVoice);}

// speak + sync bubble text and talk animation; resolves when done (timer fallback)
function speakBrowser(fact){
  return new Promise(resolve=>{
    const estMs=Math.max(1800,fact.length*62/Math.max(.3,RATE));
    let done=false,typed=0,boundary=false;
    const show=n=>{if(n>typed){typed=Math.min(fact.length,n);factEl.textContent=fact.slice(0,typed);}};
    const finish=()=>{if(done)return;done=true;clearInterval(tick);clearTimeout(safety);show(fact.length);stage.classList.remove('talk');resolve();};
    stage.classList.add('talk');
    const t0=Date.now();
    // typewriter at estimated speech pace; boundary events pull it forward to the spoken word
    const tick=setInterval(()=>{const n=Math.floor(fact.length*(Date.now()-t0)/estMs);show(boundary?Math.min(n,typed+12):n);if(!TTS&&n>=fact.length)finish();},40);
    let safety=setTimeout(finish,estMs*2+4000);
    if(!TTS)return;
    try{
      speechSynthesis.cancel();
      const u=new SpeechSynthesisUtterance(fact);
      if(voice){u.voice=voice;u.lang=voice.lang;}else u.lang='en-US';
      u.rate=RATE;u.pitch=PITCH;u.volume=VOL;
      u.onboundary=e=>{boundary=true;const ci=e.charIndex||0,m=fact.slice(ci).match(/^\S+/);show(ci+(m?m[0].length:0));};
      u.onend=finish;u.onerror=()=>{clearTimeout(safety);safety=setTimeout(finish,Math.max(0,estMs-(Date.now()-t0)));};
      speechSynthesis.speak(u);
      // if speech never starts (no voices / blocked), fall back to the timer
      setTimeout(()=>{if(!done&&!speechSynthesis.speaking&&!speechSynthesis.pending){clearTimeout(safety);safety=setTimeout(finish,Math.max(0,estMs-(Date.now()-t0)));}},1500);
    }catch(err){console.warn('TTS failed',err);clearTimeout(safety);safety=setTimeout(finish,estMs);}
  });
}

// ---- live TTS: fetch mp3 from the server, lip-sync to real loudness, type bubble over audio duration ----
const talkEl=document.getElementById('talk');let actx=null;
async function fetchAudio(src,ms){
  const ac=new AbortController(),to=setTimeout(()=>ac.abort(),ms);
  try{const r=await fetch(src,{signal:ac.signal,cache:'no-store'});
    if(!r.ok)throw new Error('audio http '+r.status);const b=await r.blob();if(!b.size)throw new Error('empty audio');return b;}finally{clearTimeout(to);}
}
async function speakLive(fact){
  const q=new URLSearchParams({text:fact,voice:LIVE_VOICE,rate:LIVE_RATE,pitch:LIVE_PITCH});
  return playBlob(fact,await fetchAudio(SERVER+'/tts?'+q,4000));
}
// pre-recorded Kokoro lines: voice/voices.js maps exact fact text -> wav path (relative to this folder). ?prerec=0 skips.
const PREREC=!MUTE&&g('prerec')!=='0';
function prerecPath(fact){const m=window.GNOME_VOICES;return m&&typeof m==='object'&&typeof m[fact]==='string'&&m[fact]?m[fact]:'';}
async function speakPrerec(fact){
  const p=prerecPath(fact);if(!p)throw new Error('no prerec line');
  return playBlob(fact,await fetchAudio(new URL(p,location.href).href,6000));
}
async function playBlob(fact,blob){
  const url=URL.createObjectURL(blob),a=new Audio(url);a.volume=VOL;
  await new Promise((ok,bad)=>{a.onloadedmetadata=ok;a.onerror=()=>bad(new Error('bad audio'));setTimeout(()=>bad(new Error('metadata timeout')),4000);});
  let an=null,buf=null;
  try{actx=actx||new (window.AudioContext||window.webkitAudioContext)();if(actx.state==='suspended')await actx.resume();
    const src=actx.createMediaElementSource(a);an=actx.createAnalyser();an.fftSize=1024;buf=new Uint8Array(an.fftSize);src.connect(an);an.connect(actx.destination);}catch(e){console.warn('analyser off',e);an=null;}
  return new Promise((resolve,reject)=>{
    let done=false,raf=0,lvl=0;window.__gnomeLip=0;
    const fin=()=>{if(done)return;done=true;cancelAnimationFrame(raf);factEl.textContent=fact;stage.classList.remove('talk','lips');talkEl.style.transform='';URL.revokeObjectURL(url);resolve();};
    stage.classList.add('talk');if(an)stage.classList.add('lips');
    const frame=()=>{if(done)return;const dur=a.duration&&isFinite(a.duration)?a.duration:fact.length*.06;
      factEl.textContent=fact.slice(0,Math.ceil(fact.length*Math.min(1,a.currentTime/(dur*.92))));
      if(an){an.getByteTimeDomainData(buf);let s=0;for(let i=0;i<buf.length;i++){const v=(buf[i]-128)/128;s+=v*v;}
        const rms=Math.sqrt(s/buf.length),t=Math.min(1,rms*6);lvl+=(t-lvl)*(t>lvl?.6:.25);window.__gnomeLip++;
        talkEl.style.transform=`translateY(${-lvl*7}px) scale(${1+lvl*.03},${1-lvl*.025+lvl*.05}) rotate(${Math.sin(a.currentTime*5)*lvl*1.5}deg)`;}
      raf=requestAnimationFrame(frame);};
    a.onended=fin;a.onerror=()=>{if(!done){done=true;stage.classList.remove('talk','lips');reject(new Error('play error'));}};
    a.play().then(()=>{raf=requestAnimationFrame(frame);},e=>{done=true;stage.classList.remove('talk','lips');reject(e);});
    setTimeout(fin,(a.duration||20)*1000+3000);
  });
}
async function speakFact(fact){
  if(PREREC&&prerecPath(fact)){try{await speakPrerec(fact);window.__gnomeMode='prerec';return;}catch(e){console.warn('pre-recorded line failed, falling back',e&&e.message);}}
  if(LIVE){try{await speakLive(fact);window.__gnomeMode='live';return;}catch(e){console.warn('live TTS failed, falling back',e&&e.message);}}
  window.__gnomeMode='browser';return speakBrowser(fact);
}

const queue=[];let busy=false;
function fire(name){queue.push(String(name||''));if(!busy)run();}
async function run(){
  busy=true;
  while(queue.length){
    const name=queue.shift(),fact=next();
    factEl.textContent='';whoEl.textContent=name?'requested by '+name:'';
    set('in');await wait(1000);
    set('in','show');await wait(350);
    const t=Date.now();
    await speakFact(fact);
    await wait(Math.max(2500,DUR-1350-1200-(Date.now()-t)));
    set('out');await wait(900);set();await wait(400);
  }
  busy=false;
}
window.factGnome={fire,trigger:fire,facts:FACTS};

if(TEST){const names=['Remy','Thrallbert','NewbieNelf','Jainabelle','Murlocmaster','Sylvana_W'];let i=0;
  fire(names[i++]);if(!ONCE)setInterval(()=>fire(names[i++%names.length]),12000);return;}
if(ONCE&&!CH&&!USE_SERVER){fire('');return;}

// ---- dedupe: the same redemption can arrive via the server feed AND IRC ----
const seen=new Map();
function onRedeem(name,title,id){
  const key=(name||'').toLowerCase();const now=Date.now();
  if(id&&seen.has('id:'+id))return;
  if(seen.has('u:'+key)&&now-seen.get('u:'+key)<4000)return; // same viewer within 4s = same redemption from both sources
  if(id)seen.set('id:'+id,now);seen.set('u:'+key,now);fire(name);
}
const matches=(title,id)=>(REWARD_ID&&id===REWARD_ID)||(!!title&&title.trim().toLowerCase()===REWARD_LC);

// ---- Production Center feed (GET /events?since=N on the existing Flask server) ----
if(USE_SERVER){let since=-1,delay=1000;
  (async function poll(){
    try{const r=await fetch(SERVER+'/events?since='+since,{cache:'no-store'});const j=await r.json();
      if(since<0){since=j.last_id||0;} // first call: skip backlog, just sync the cursor
      else{for(const ev of j.events||[]){since=Math.max(since,ev.id||0);
        if(ev.type==='redemption'&&matches(ev.reward,ev.reward_id))onRedeem(ev.user,ev.reward,ev.redemption_id);}
        since=Math.max(since,j.last_id||0);}
      delay=1000;
    }catch(e){delay=Math.min(delay*2,15000);}
    setTimeout(poll,delay);
  })();}

// ---- anonymous IRC fallback: sees redemptions WITH viewer text only (custom-reward-id tag) ----
if(!CH){if(!USE_SERVER){learnEl.hidden=false;learnEl.textContent='Fact Gnome: add ?channel=yourname to the URL';}return;}
function parse(raw){const o={tags:{},prefix:'',cmd:'',trailing:''};let i=0;
  if(raw[0]==='@'){const sp=raw.indexOf(' ');for(const kv of raw.slice(1,sp).split(';')){const e=kv.indexOf('=');o.tags[e<0?kv:kv.slice(0,e)]=e<0?'':kv.slice(e+1).replace(/\\s/g,' ');}i=sp+1;}
  if(raw[i]===':'){const sp=raw.indexOf(' ',i);o.prefix=raw.slice(i+1,sp);i=sp+1;}
  const tr=raw.indexOf(' :',i);o.cmd=(tr<0?raw.slice(i):raw.slice(i,tr)).split(' ')[0];if(tr>=0)o.trailing=raw.slice(tr+2);return o;}
const learned=[];
function onMsg(m,ws){
  if(m.cmd==='PING'){ws.send('PONG :'+(m.trailing||'tmi.twitch.tv'));return;}
  if(m.cmd==='RECONNECT'){ws.close();return;}
  if(m.cmd!=='PRIVMSG')return;
  const t=m.tags,name=t['display-name']||m.prefix.split('!')[0],rid=t['custom-reward-id'],text=m.trailing||'';
  if(rid){
    if(LEARN){learned.unshift(`${name} redeemed reward id:\n  ${rid}`);learnEl.hidden=false;learnEl.textContent='LEARN MODE (copy into ?rewardid=)\n'+learned.slice(0,5).join('\n');}
    // IRC has no reward title, so it only fires when ?rewardid= is set
    if(REWARD_ID&&rid===REWARD_ID&&!text.trim().startsWith('?'))onRedeem(name,'',null);
    return;
  }
  if(CMD&&text.trim().toLowerCase().split(/\s+/)[0]===CMD){
    const b=t.badges||'';if(CMDMODS&&!/(^|,)(broadcaster|moderator)\//.test(b))return;fire(name);
  }
}
let delay=1000;
(function connect(){
  const ws=new WebSocket('wss://irc-ws.chat.twitch.tv:443');
  ws.onopen=()=>{delay=1000;ws.send('CAP REQ :twitch.tv/tags twitch.tv/commands');ws.send('PASS SCHMOOPIIE');ws.send('NICK justinfan'+(10000+Math.floor(Math.random()*89999)));ws.send('JOIN #'+CH);};
  ws.onmessage=e=>{for(const l of String(e.data).split('\r\n'))if(l)try{onMsg(parse(l),ws);}catch(err){console.warn(err);}};
  ws.onclose=()=>{setTimeout(connect,delay+Math.random()*500);delay=Math.min(delay*2,30000);};
  ws.onerror=()=>{try{ws.close();}catch(_){}};
})();
})();
