(function(){
'use strict';
const P=new URLSearchParams(location.search),g=k=>P.get(k);
const CH=(g('channel')||g('twitch')||'').replace(/^#/,'').toLowerCase().trim();
const TEST=g('test')==='1',ONCE=g('once')==='1';
const BITSMIN=Math.max(1,+(g('bitsmin')||1)),RAIDS=g('raids')!=='0',BITS=g('bits')!=='0';
const FOLLOWS=g('follows')!=='0',FDUR=Math.max(2,+(g('followdur')||3.5))*1000;
const SERVER=(g('server')||'http://localhost:5000').replace(/\/+$/,''),USE_SERVER=g('server')!=='0';
const DUR=Math.max(4,+(g('duration')||6))*1000;
const stage=document.getElementById('stage'),sway=document.getElementById('sway'),talkEl=document.getElementById('talk');
const hdr=document.getElementById('hdr'),msg=document.getElementById('msg'),subEl=document.getElementById('sub'),note=document.getElementById('note');
const pos=(g('pos')||'bl').toLowerCase();stage.className=['bl','tl','l'].includes(pos)?pos:'bl';
if(g('scale'))stage.style.setProperty('--scale',+g('scale')||1);
if(g('x'))stage.style.setProperty('--x',(+g('x')||0)+'px');
if(g('y'))stage.style.setProperty('--y',(+g('y')||0)+'px');
const base=stage.className;
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const set=(...c)=>{stage.className=[base,...c].filter(Boolean).join(' ');};
const clean=s=>String(s||'').replace(/[\u0000-\u001f\u007f<>&"'`]/g,'').trim().slice(0,25)||'friend';


// ---- sounds: random mp3 from sounds/ each time he fires ----
const SOUND_ON=g('sound')!=='0',VOL=Math.min(1,Math.max(0,g('vol')==null?0.8:+g('vol')));
let sounds=(Array.isArray(window.PALADIN_SOUNDS)?window.PALADIN_SOUNDS:[]).map(f=>String(f).trim()).filter(Boolean).map(f=>'sounds/'+encodeURI(f));
if(SOUND_ON&&!sounds.length){const found=[];let pending=50;
  for(let n=1;n<=50;n++){const a=new Audio();a.preload='metadata';
    a.oncanplaythrough=a.onloadedmetadata=()=>{if(!a._ok){a._ok=1;found.push({n,src:a.src});}if(!--pending)done();};
    a.onerror=()=>{if(!--pending)done();};a.src='sounds/'+n+'.mp3';}
  function done(){found.sort((x,y)=>x.n-y.n);sounds=found.map(f=>f.src);}}
let lastSnd=-1;
function playSound(){if(!SOUND_ON||!sounds.length)return;
  let i=Math.floor(Math.random()*sounds.length);if(sounds.length>1&&i===lastSnd)i=(i+1)%sounds.length;lastSnd=i;
  const a=new Audio(sounds[i]);a.volume=VOL;a.play().catch(e=>console.warn('paladin sound',e));
  window.paladinSub&&(window.paladinSub.lastSound=sounds[i]);}

const queue=[];let busy=false;
function alertSub(ev){queue.push(ev);if(!busy)run();}
function follow(name){if(!FOLLOWS)return;alertSub({type:'follow',name});}
// merge follow floods: >3 follows waiting -> one alert
function takeFollows(first){const rest=queue.filter(e=>e.type==='follow');
  if(rest.length+1<=3)return first;
  for(const e of rest)queue.splice(queue.indexOf(e),1);
  const names=[first,...rest].map(e=>clean(e.name));return {type:'follow',name:names[0],names};}
function followSegs(ev){if(!ev.names)return [{t:'Thanks for the follow, '},{t:clean(ev.name),b:1},{t:'!'}];
  const n=ev.names,more=n.length-2;return [{t:'Thanks for the follows, '},{t:n[0],b:1},{t:', '},{t:n[1],b:1},{t:` and ${more} more!`}];}
async function typeSegs(segs,D){msg.textContent='';const total=segs.reduce((n,s)=>n+s.t.length,0),per=Math.min(55,Math.max(D<DUR?12:28,(D||DUR)*0.4/total));
  for(const s of segs){const node=s.b?msg.appendChild(document.createElement('b')):msg.appendChild(document.createTextNode(''));
    for(const ch of s.t){if(s.b)node.textContent+=ch;else node.data+=ch;
      if(/[aeiouy]/i.test(ch)){talkEl.classList.remove('syl');void talkEl.offsetWidth;talkEl.classList.add('syl');}
      await wait(per);}}}
async function run(){
  busy=true;
  while(queue.length){
    let ev=queue.shift();if(ev.type==='follow')ev=takeFollows(ev);const name=clean(ev.name),fol=ev.type==='follow',D=fol?FDUR:DUR;const gift=ev.type==='gift';
    const raid=ev.type==='raid',bits=ev.type==='bits';
    hdr.textContent=fol?'New follower!':raid?'Incoming raid!':bits?`${ev.count} bits!`:gift?(ev.count>1?`${ev.count} gifted subs!`:'Gifted sub!'):(ev.type==='resub'?'Resub!':'New sub!');
    subEl.textContent=fol?'':raid?`${ev.count} raiders!`:ev.type==='resub'&&ev.months>1?`${ev.months} months!`:'';
    msg.textContent='';
    if(!fol)playSound(); // follows are ALWAYS silent (chain follows)
    set('in','flare');await wait(fol?600:1000);
    set('in','show','talking');await wait(fol?150:350);
    const t0=Date.now();
    await typeSegs(fol?followSegs(ev):raid?[{t:'Welcome raiders! Thanks for the raid, '},{t:name,b:1},{t:'!'}]:bits?[{t:'Thanks for the bits, '},{t:name,b:1},{t:'!'}]:gift?[{t:'Thanks for the gifted subs, '},{t:name,b:1},{t:'!'}]:[{t:'Thanks for subscribing, '},{t:name,b:1},{t:'!'}],D);
    set('in','show');
    await wait(Math.max(1200,D-(fol?750:1350)-(Date.now()-t0)-(fol?800:1100)));
    set('out');await wait(850);set();await wait(300);
  }
  busy=false;
}
window.paladinSub={alert:alertSub,follow};

// ---- dedupe: same type+name within 30s never plays twice (IRC vs feed) ----
const seen=new Map();let ircUp=false;
function dup(type,name){const k=type.replace('resub','sub')+':'+String(name||'').toLowerCase(),now=Date.now();
  for(const [kk,t] of seen)if(now-t>30000)seen.delete(kk);
  if(seen.has(k))return true;seen.set(k,now);return false;}
function fromIrc(ev){dup(ev.type,ev.name);alertSub(ev);}
// ---- Production Center feed (same client as fact-gnome: GET /events?since=N) ----
function onFeed(ev){const name=ev.user||ev.login||'';
  if(ev.type==='follow'){if(!dup('follow',name))follow(name);return;}
  if(TEST||ircUp)return; // IRC is the source of truth for these when connected
  const m={sub:'sub',resub:'resub',gift:'gift',bits:'bits',raid:'raid'}[ev.type];if(!m)return;
  if(m==='raid'&&!RAIDS)return;if(m==='bits'&&(!BITS||(+ev.amount||0)<BITSMIN))return;
  if(dup(m,name))return;
  alertSub({type:m,name,count:+(ev.amount||ev.viewers||ev.count)||1,months:+ev.months||0});}
if(USE_SERVER&&!(TEST&&g('server')==null)){let since=-1,delay=1000;
  (async function poll(){
    try{const r=await fetch(SERVER+'/events?since='+since,{cache:'no-store'});const j=await r.json();
      if(since<0){since=j.last_id||0;} // first call: skip backlog, just sync the cursor
      else{for(const ev of j.events||[]){since=Math.max(since,ev.id||0);try{onFeed(ev);}catch(e){console.warn(e);}}
        since=Math.max(since,j.last_id||0);}
      delay=1000;
    }catch(e){delay=Math.min(delay*2,15000);}
    setTimeout(poll,delay);
  })();}

if(TEST){const evs=[{type:'sub',name:'Thrallbert'},{type:'resub',name:'Jainabelle',months:14},{type:'gift',name:'Murlocmaster',count:5},{type:'raid',name:'Sylvanazz',count:42},{type:'bits',name:'Goldfarmer',count:500},{type:'follow',name:'Peonwork'}];let i=0;
  alertSub(evs[i++]);if(!ONCE)setInterval(()=>alertSub(evs[i++%evs.length]),9000);return;}
if(ONCE&&!CH){alertSub({type:'sub',name:'Thrallbert'});return;}
if(!CH){if(USE_SERVER)return;note.hidden=false;note.textContent='Paladin Sub Alert: add ?channel=yourname to the URL';return;}

function parse(raw){const o={tags:{},prefix:'',cmd:'',trailing:''};let i=0;
  if(raw[0]==='@'){const sp=raw.indexOf(' ');for(const kv of raw.slice(1,sp).split(';')){const e=kv.indexOf('=');o.tags[e<0?kv:kv.slice(0,e)]=e<0?'':kv.slice(e+1).replace(/\\s/g,' ');}i=sp+1;}
  if(raw[i]===':'){const sp=raw.indexOf(' ',i);o.prefix=raw.slice(i+1,sp);i=sp+1;}
  const tr=raw.indexOf(' :',i);o.cmd=(tr<0?raw.slice(i):raw.slice(i,tr)).split(' ')[0];if(tr>=0)o.trailing=raw.slice(tr+2);return o;}
const bombs={};// gifter(lowercase) -> {until, left}
function onMsg(m,ws){
  if(m.cmd==='PING'){ws.send('PONG :'+(m.trailing||'tmi.twitch.tv'));return;}
  if(m.cmd==='RECONNECT'){ws.close();return;}
  if(m.cmd==='PRIVMSG'){const b=+m.tags.bits||0;if(BITS&&b>=BITSMIN)fromIrc({type:'bits',name:m.tags['display-name']||m.prefix.split('!')[0],count:b});return;}
  if(m.cmd!=='USERNOTICE')return;
  const t=m.tags,id=t['msg-id'],anon=/^anon/.test(id);
  const name=anon?'Anonymous':(t['display-name']||t.login||'');const key=anon?'~anon':(t.login||name).toLowerCase();
  const now=Date.now();
  if(id==='raid'){if(RAIDS)fromIrc({type:'raid',name:t['msg-param-displayName']||name,count:+t['msg-param-viewerCount']||0});}
  else if(id==='sub')fromIrc({type:'sub',name});
  else if(id==='resub')fromIrc({type:'resub',name,months:+t['msg-param-cumulative-months']||0});
  else if(id==='submysterygift'||id==='anonsubmysterygift'){const n=+t['msg-param-mass-gift-count']||1;
    bombs[key]={until:now+10000,left:n};fromIrc({type:'gift',name,count:n});}
  else if(id==='subgift'||id==='anonsubgift'){const b=bombs[key];
    if(b&&now<b.until&&b.left>0){b.left--;return;}
    fromIrc({type:'gift',name,count:1});}
}
let delay=1000;
(function connect(){
  const ws=new WebSocket('wss://irc-ws.chat.twitch.tv:443');
  ws.onopen=()=>{delay=1000;ircUp=true;ws.send('CAP REQ :twitch.tv/tags twitch.tv/commands');ws.send('PASS SCHMOOPIIE');ws.send('NICK justinfan'+(10000+Math.floor(Math.random()*89999)));ws.send('JOIN #'+CH);};
  ws.onmessage=e=>{for(const l of String(e.data).split('\r\n'))if(l)try{onMsg(parse(l),ws);}catch(err){console.warn(err);}};
  ws.onclose=()=>{ircUp=false;setTimeout(connect,delay+Math.random()*500);delay=Math.min(delay*2,30000);};
  ws.onerror=()=>{try{ws.close();}catch(_){}};
})();
})();
