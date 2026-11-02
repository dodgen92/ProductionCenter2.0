(function(){
'use strict';
const P=new URLSearchParams(location.search),g=k=>P.get(k);
const CH=(g('channel')||g('twitch')||'').replace(/^#/,'').toLowerCase().trim();
const TESTKEY=(g('test')||'').toLowerCase(),ONCE=g('once')==='1';
// test=1 cycles every kind. test=follow (or sub, resub, gift, bits, cheer, raid) fires that one.
const TESTONE={sub:1,resub:1,gift:1,bits:1,cheer:1,raid:1,follow:1};
const TEST=TESTKEY==='1'||TESTKEY==='all'||!!TESTONE[TESTKEY];
const BITSMIN=Math.max(1,+(g('bitsmin')||1)),RAIDS=g('raids')!=='0',BITS=g('bits')!=='0';
const FOLLOWS=g('follows')!=='0',FDUR=Math.max(2,+(g('followdur')||3.5))*1000;
const SERVER=(g('server')||'http://localhost:5000').replace(/\/+$/,''),USE_SERVER=g('server')!=='0';
const DUR=Math.max(4,+(g('duration')||6))*1000;
const stage=document.getElementById('stage'),sway=document.getElementById('sway'),talkEl=document.getElementById('talk');
const hdr=document.getElementById('hdr'),msg=document.getElementById('msg'),subEl=document.getElementById('sub'),lineEl=document.getElementById('line'),note=document.getElementById('note');
const pos=(g('pos')||'bl').toLowerCase();stage.className=['bl','tl','l'].includes(pos)?pos:'bl';
if(g('scale'))stage.style.setProperty('--scale',+g('scale')||1);
if(g('x'))stage.style.setProperty('--x',(+g('x')||0)+'px');
if(g('y'))stage.style.setProperty('--y',(+g('y')||0)+'px');
const base=stage.className;
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const set=(...c)=>{stage.className=[base,...c].filter(Boolean).join(' ');};
const clean=s=>String(s||'').replace(/[\u0000-\u001f\u007f<>&"'`]/g,'').trim().slice(0,25)||'friend';


// ---- sounds: mp3 from sounds/ under the voice line ----
// The recorded line used to replace this bed, so playSound never ran once a
// line existed. Play both. The bed stays quieter so the words stay clear.
// Follows do not play the bed. They never did.
const SOUND_ON=g('sound')!=='0',VOL=Math.min(1,Math.max(0,g('vol')==null?0.8:+g('vol')));
const BED=0.35;
let sounds=(Array.isArray(window.PALADIN_SOUNDS)?window.PALADIN_SOUNDS:[]).map(f=>String(f).trim()).filter(Boolean).map(f=>'sounds/'+encodeURI(f));
// A listed file is ready now. Numbered files (1.mp3, 2.mp3, ...) are found
// after the page loads, so an alert that fires immediately waits for that.
let soundsReady=sounds.length>0;
if(SOUND_ON&&!sounds.length){const found=[];let pending=50;
  for(let n=1;n<=50;n++){const a=new Audio();a.preload='metadata';
    a.oncanplaythrough=a.onloadedmetadata=()=>{if(!a._ok){a._ok=1;found.push({n,src:a.src});}if(!--pending)done();};
    a.onerror=()=>{if(!--pending)done();};a.src='sounds/'+n+'.mp3';}
  function done(){found.sort((x,y)=>x.n-y.n);sounds=found.map(f=>f.src);soundsReady=true;}}
let lastSnd=-1,bed=null,bedGen=0;
function playSound(underVoice,gen){if(!SOUND_ON)return;
  if(gen==null)gen=bedGen;
  if(gen!==bedGen)return; // this alert already finished
  if(!soundsReady){setTimeout(()=>playSound(underVoice,gen),250);return;}
  if(!sounds.length)return;
  if(bed){try{bed.pause();}catch(e){}}
  let i=Math.floor(Math.random()*sounds.length);if(sounds.length>1&&i===lastSnd)i=(i+1)%sounds.length;lastSnd=i;
  const a=new Audio(sounds[i]);bed=a;
  a.volume=underVoice?Math.min(1,VOL*BED):VOL;
  a.play().catch(e=>console.warn('paladin sound',e));
  if(window.paladinSub){window.paladinSub.lastBed=sounds[i];if(!underVoice)window.paladinSub.lastSound=sounds[i];}}

// ---- voice lines (lines.js): one recorded take per alert ----
// dono = sub, resub, gift, bits. follow = follows. raid = raids.
// Pick at random, but not the same file as last time (a pool of one always repeats).
const LINES=window.PALADIN_LINES||{};
const lastLine={dono:'',follow:'',raid:''};
function linePool(type){
  if(type==='follow')return 'follow';
  if(type==='raid')return 'raid';
  if(type==='sub'||type==='resub'||type==='gift'||type==='bits')return 'dono';
  return '';
}
function pickLine(type){
  const key=linePool(type);
  const pool=(Array.isArray(LINES[key])?LINES[key]:[]).filter(row=>row&&row.file&&row.text);
  if(!pool.length)return null;
  let i=Math.floor(Math.random()*pool.length);
  if(pool.length>1&&pool[i].file===lastLine[key])i=(i+1)%pool.length;
  lastLine[key]=pool[i].file;
  return pool[i];
}
// Resolves when the mp3 ends. If it never loads, give up after a few seconds
// so the queue can move on. The long timer is only for a clip that starts and never ends.
function playVoice(entry){
  if(!entry||!SOUND_ON)return Promise.resolve();
  return new Promise(resolve=>{
    let settled=false;
    const audio=new Audio('audio/'+encodeURI(entry.file));
    audio.volume=VOL;
    let cap=setTimeout(finish,90000);
    function finish(){
      if(settled)return;
      settled=true;
      clearTimeout(cap);
      try{audio.pause();}catch(e){}
      resolve();
    }
    function fail(){
      clearTimeout(cap);
      cap=setTimeout(finish,6000);
    }
    audio.addEventListener('ended',finish);
    audio.addEventListener('error',fail);
    audio.play().then(()=>{
      window.paladinSub&&(window.paladinSub.lastSound='audio/'+entry.file);
    }).catch(fail);
  });
}

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
    let ev=queue.shift();
    if(ev.type==='follow')ev=takeFollows(ev);
    const name=clean(ev.name),fol=ev.type==='follow',D=fol?FDUR:DUR;
    const gift=ev.type==='gift',raid=ev.type==='raid',bits=ev.type==='bits';
    const line=pickLine(ev.type);
    hdr.textContent=fol?'New follower!':raid?'Incoming raid!':bits?`${ev.count} bits!`:gift?(ev.count>1?`${ev.count} gifted subs!`:'Gifted sub!'):(ev.type==='resub'?'Resub!':'New sub!');
    subEl.textContent=fol?'':raid?`${ev.count} raiders!`:ev.type==='resub'&&ev.months>1?`${ev.months} months!`:'';
    msg.textContent='';
    if(lineEl)lineEl.textContent=line?line.text:'';
    // Voice and the bed together. A follow stays without the bed.
    let voice=Promise.resolve();
    if(line)voice=playVoice(line);
    if(!fol)playSound(!!line);
    set('in','flare');await wait(fol?600:1000);
    set('in','show','talking');await wait(fol?150:350);
    const t0=Date.now();
    await typeSegs(fol?followSegs(ev):raid?[{t:'Welcome raiders! Thanks for the raid, '},{t:name,b:1},{t:'!'}]:bits?[{t:'Thanks for the bits, '},{t:name,b:1},{t:'!'}]:gift?[{t:'Thanks for the gifted subs, '},{t:name,b:1},{t:'!'}]:[{t:'Thanks for subscribing, '},{t:name,b:1},{t:'!'}],D);
    const minLeft=Math.max(1200,D-(fol?750:1350)-(Date.now()-t0)-(fol?800:1100));
    // Stay up until the spoken line ends, and at least as long as the old timer.
    await Promise.all([voice,wait(minLeft)]);
    bedGen++;
    if(bed){try{bed.pause();}catch(e){}bed=null;}
    set('in','show');
    await wait(200);
    set('out');await wait(850);set();
    if(lineEl)lineEl.textContent='';
    await wait(300);
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

if(TEST){
  const samples={
    sub:{type:'sub',name:'Thrallbert'},
    resub:{type:'resub',name:'Jainabelle',months:14},
    gift:{type:'gift',name:'Murlocmaster',count:5},
    raid:{type:'raid',name:'Sylvanazz',count:42},
    bits:{type:'bits',name:'Goldfarmer',count:500},
    cheer:{type:'bits',name:'Cal',count:100},
    follow:{type:'follow',name:'Peonwork'}
  };
  const order=['sub','resub','gift','raid','bits','follow'];
  const keys=samples[TESTKEY]?[TESTKEY]:order;
  let i=0;
  const fire=()=>alertSub(Object.assign({},samples[keys[i++%keys.length]]));
  fire();
  if(!ONCE)setInterval(fire,9000);
  return;
}
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
