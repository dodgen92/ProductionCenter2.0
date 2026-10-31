(function(){
'use strict';
const P=new URLSearchParams(location.search),g=k=>P.get(k);
const CH=(g('channel')||'').replace(/^#/,'').toLowerCase().trim();
const TEST=g('test')==='1';
const SH={'16x9':[1280,720],'1x1':[720,720],'9x16':[540,960]}[g('shape')||'16x9']||[1280,720];
const W=+g('w')||SH[0],H=Math.round(W*SH[1]/SH[0]);
const fr=document.getElementById('frame'),bar=document.getElementById('bar'),fill=document.getElementById('fill'),fx=document.getElementById('fx'),al=document.getElementById('alert'),cnt=document.getElementById('cnt'),note=document.getElementById('note');
fr.style.setProperty('--w',W+'px');fr.style.setProperty('--h',H+'px');
fr.style.setProperty('--x',(g('x')!=null?+g('x'):Math.round((1920-W)/2))+'px');
fr.style.setProperty('--y',(g('y')!=null?+g('y'):Math.max(10,Math.round((1080-H-64)/2)))+'px');
const BASE=Math.max(1,+g('base')||(TEST?20:100)),GROW=(g('growth')||'linear').toLowerCase();
const need=L=>Math.max(1,Math.round(GROW==='flat'?BASE:GROW==='exp'?BASE*Math.pow(1.5,L-1):BASE*L));
const num=(k,d)=>{const v=g(k);return v==null||v===''||isNaN(+v)?d:Math.max(0,+v);};
const XP={follow:num('xpfollow',10),sub:num('xpsub',50),resub:num('xpresub',num('xpsub',50)),gift:num('xpgift',num('xpsub',50)),bits:num('xpbits',0.1),raid:num('xpraid',2),raidmin:num('xpraidmin',20),chat:num('xpchat',0)};
const RESET_MS=num('resetafter',6)*3600000,KEY='camframe:'+(CH||'none');
let level=1,xp=0;
if(!TEST){try{const st=JSON.parse(localStorage.getItem(KEY)||'null');
  if(st&&g('reset')!=='1'&&Date.now()-(st.t||0)<RESET_MS){level=Math.max(1,st.level|0);xp=Math.max(0,+st.xp||0);}}catch(_){}}
const save=()=>{if(!TEST)try{localStorage.setItem(KEY,JSON.stringify({level,xp,t:Date.now()}));}catch(_){}};save();
setInterval(save,600000);
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const clean=s=>String(s||'').replace(/[\u0000-\u001f\u007f<>&"'`]/g,'').trim().slice(0,25)||'friend';
const el=(c,css,p=fx)=>{const e=document.createElement('div');e.className=c;Object.assign(e.style,css||{});p.appendChild(e);return e;};
const badge=document.getElementById('badge'),bnum=document.getElementById('bnum'),lbl=document.getElementById('lbl');
if(g('badge')==='0')fr.classList.add('nobadge');
function draw(){const n=need(level);lbl.textContent='Stream Level '+level;cnt.textContent=Math.floor(xp)+' / '+n+' XP';
  fill.style.width=Math.min(100,xp/n*100)+'%';bnum.textContent=level;badge.classList.toggle('big',level>99);}
draw();
const camX=()=>{const r=fr.getBoundingClientRect();return r.left+r.width/2;};
function pillar(gold){const p=el('pillar'+(gold?' gold':''),{left:camX()+'px'},document.body);setTimeout(()=>p.remove(),2600);}
function confetti(n){const cs=['#ff4d6d','#ffd100','#4ad66d','#4aa8ff','#c58cff'];for(let i=0;i<n;i++){const c=el('conf',{left:Math.random()*100+'%',background:cs[i%5],animationDelay:Math.random()*.8+'s'});setTimeout(()=>c.remove(),3000);}}
const Q=[{min:5000,c:'#ff8000'},{min:1000,c:'#a335ee'},{min:500,c:'#0070dd'},{min:100,c:'#1eff00'},{min:1,c:'#ffffff'},{min:0,c:'#9d9d9d'}];
const queue=[];let busy=false,ups=0;
function push(ev){queue.push(ev);if(!busy)run();}
function show(html){al.innerHTML=html;bar.classList.add('alerting');}
function pop(n,cls){const p=el('plus'+(cls?' '+cls:''),{left:Math.min(88,Math.max(10,xp/need(level)*100))+'%'});p.textContent='+'+n+' XP';setTimeout(()=>p.remove(),1700);}
function gain(n,chat){n=Math.round(n);if(n<=0)return;xp+=n;while(xp>=need(level)){xp-=need(level);level++;ups++;}save();
  if(ups){fill.style.width='100%';pop(n,chat?'xp':'');if(chat&&!busy)push({type:'_lvl'});}else{draw();pop(n,chat?'xp':'');}}
async function levelUps(){while(ups>0){const L=level-(--ups);
  bnum.textContent=L;lbl.textContent='Stream Level '+L;badge.classList.toggle('big',L>99);
  badge.classList.remove('pop');void badge.offsetWidth;badge.classList.add('pop');
  pillar(true);setTimeout(()=>pillar(true),300);confetti(60);bar.classList.add('done');
  show('<span style="font-size:36px;color:#ffe680">★ LEVEL UP! Stream Level '+L+'! ★</span>');
  await wait(4200);bar.classList.remove('done','alerting');
  fill.style.transition='none';fill.style.width='0';void fill.offsetWidth;fill.style.transition='';await wait(400);}
  draw();}
async function run(){busy=true;
  while(queue.length){const ev=queue.shift(),name=clean(ev.name);
    if(ev.type==='sub'){pillar();show('<b>'+name+'</b> subscribed!');gain(XP.sub);await wait(3500);}
    else if(ev.type==='resub'){const m=Math.max(1,ev.months|0);pillar();show('<span class="lvl">'+m+'</span> <b>'+name+'</b> resubbed × '+m+' month'+(m>1?'s':''));gain(XP.resub);await wait(3800);}
    else if(ev.type==='gift'){const n=Math.max(1,ev.count|0),nb=Math.min(24,Math.max(2,Math.round(Math.sqrt(n)*3)));
      const cs=['#c0283c','#2a6fd0','#2f9e44','#7a2fd0'];
      for(let i=0;i<nb;i++){const b=el('box',{left:(3+i*(94/nb))+'%','--c':cs[i%4],animationDelay:i*0.06+'s'});setTimeout(()=>b.remove(),4500);}
      confetti(Math.min(80,15+n*3));show('<b>'+name+'</b> gifted '+(n>1?n+' subs!':'a sub!'));gain(XP.gift*n);await wait(4000);}
    else if(ev.type==='bits'){const q=Q.find(q=>ev.amount>=q.min);
      show('<span class="gemi" style="--q:'+q.c+'"></span><b>'+name+'</b> <span style="color:'+q.c+'">['+ev.amount+' bits]</span>');gain(ev.amount*XP.bits);await wait(4000);}
    else if(ev.type==='raid'){const n=Math.min(40,Math.max(5,Math.round(Math.sqrt(ev.viewers||1)*3)));
      for(let i=0;i<n;i++){const r=el('runner',{'--d':(2.4+Math.random()*1.6)+'s',animationDelay:Math.random()*1.5+'s',transform:'scale('+(0.7+Math.random()*.5)+')'});setTimeout(()=>r.remove(),6000);}
      show('<b>'+name+'</b> raids with '+(ev.viewers||0)+'!');gain(Math.max(XP.raidmin,(ev.viewers||0)*XP.raid));await wait(5000);}
    else if(ev.type==='follow'){show('<b>'+name+'</b> followed!');bar.classList.add('shimmer');gain(XP.follow);await wait(3500);bar.classList.remove('shimmer');}
    if(ups){bar.classList.remove('alerting');await wait(500);await levelUps();}
    bar.classList.remove('alerting');fx.querySelectorAll('.box').forEach(b=>b.remove());await wait(900);}
  busy=false;}
function trigger(ev){if(!ev||typeof ev!=='object')return;const t=String(ev.type||'').toLowerCase();
  if(t==='follow')push({type:'follow',name:ev.user||ev.name||ev.user_name});}
window.camFrame={push,trigger,follow:n=>trigger({type:'follow',user:n})};
const WS=g('ws');
if(WS&&/^wss?:\/\//i.test(WS)){let d=1000;(function c(){let s;try{s=new WebSocket(WS);}catch(_){return;}
  s.onopen=()=>{d=1000;};s.onmessage=e=>{try{trigger(JSON.parse(e.data));}catch(_){}};
  s.onclose=()=>{setTimeout(c,d+Math.random()*500);d=Math.min(d*2,30000);};s.onerror=()=>{try{s.close();}catch(_){}};})();}
if(TEST){const evs=[{type:'bits',name:'Goldfarmer',amount:250},{type:'sub',name:'Thrallbert'},{type:'raid',name:'Leeroyy',viewers:120},{type:'follow',name:'Newbiepally'},{type:'bits',name:'Whale',amount:5000},{type:'resub',name:'Jainabelle',months:14},{type:'gift',name:'Murlocmaster',count:10},{type:'bits',name:'Peon',amount:50}];
  let i=0;const tick=()=>{if(!busy&&!queue.length)push(evs[i++%evs.length]);};tick();setInterval(tick,1000);return;}
if(!CH){note.hidden=false;note.textContent='Cam Frame: add ?channel=yourname to the URL';return;}
function parse(raw){const o={tags:{},prefix:'',cmd:'',trailing:''};let i=0;
  if(raw[0]==='@'){const sp=raw.indexOf(' ');for(const kv of raw.slice(1,sp).split(';')){const e=kv.indexOf('=');o.tags[e<0?kv:kv.slice(0,e)]=e<0?'':kv.slice(e+1).replace(/\\s/g,' ');}i=sp+1;}
  if(raw[i]===':'){const sp=raw.indexOf(' ',i);o.prefix=raw.slice(i+1,sp);i=sp+1;}
  const tr=raw.indexOf(' :',i);o.cmd=(tr<0?raw.slice(i):raw.slice(i,tr)).split(' ')[0];if(tr>=0)o.trailing=raw.slice(tr+2);return o;}
const bombs={},chatCd={};
function onMsg(m,ws){
  if(m.cmd==='PING'){ws.send('PONG :'+(m.trailing||'tmi.twitch.tv'));return;}
  if(m.cmd==='RECONNECT'){ws.close();return;}
  const t=m.tags;
  if(m.cmd==='PRIVMSG'){const u=(m.prefix.split('!')[0]||'').toLowerCase();
    if(t.bits){push({type:'bits',name:t['display-name']||u,amount:+t.bits||0});return;}
    if(XP.chat>0&&u){const now=Date.now();if(!(chatCd[u]>now)){chatCd[u]=now+60000;gain(XP.chat,true);}}return;}
  if(m.cmd!=='USERNOTICE')return;
  const id=t['msg-id'],anon=/^anon/.test(id);
  const name=anon?'Anonymous':(t['display-name']||t.login||'');const key=anon?'~anon':(t.login||name).toLowerCase();const now=Date.now();
  if(id==='sub')push({type:'sub',name});
  else if(id==='resub')push({type:'resub',name,months:+t['msg-param-cumulative-months']||1});
  else if(id==='raid')push({type:'raid',name:t['msg-param-displayName']||name,viewers:+t['msg-param-viewerCount']||0});
  else if(id==='submysterygift'||id==='anonsubmysterygift'){const n=+t['msg-param-mass-gift-count']||1;bombs[key]={until:now+10000,left:n};push({type:'gift',name,count:n});}
  else if(id==='subgift'||id==='anonsubgift'){const b=bombs[key];if(b&&now<b.until&&b.left>0){b.left--;return;}push({type:'gift',name,count:1});}
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
