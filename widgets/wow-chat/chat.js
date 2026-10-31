(function(){
'use strict';
const P=new URLSearchParams(location.search), g=k=>P.get(k);
const CHANNEL=(g('channel')||g('twitch')||'').replace(/^#/,'').toLowerCase().trim();
const TEST=g('test')==='1', MAX=+(g('max')||12), FADE=+(g('fade')??30), SHOWTS=g('ts')==='1';
const HIDECMDS=g('hidecmds')==='1';
const BOTS=new Set((g('hidebots')??'nightbot,streamelements').toLowerCase().split(',').map(s=>s.trim()).filter(Boolean));
const root=document.getElementById('frame').style, px=v=>/^\d+$/.test(v)?v+'px':v;
if(g('x'))root.setProperty('--x',px(g('x')));
if(g('y')){root.setProperty('--y',px(g('y')));root.setProperty('--b','auto');}
if(g('w'))root.setProperty('--w',px(g('w')));
if(g('h'))root.setProperty('--h',px(g('h')));
if(g('size'))root.setProperty('--size',px(g('size')));
if(g('opacity'))root.setProperty('--opacity',g('opacity'));
if(g('tab1'))document.getElementById('tab1').textContent=g('tab1');
if(g('tab2'))document.getElementById('tab2').textContent=g('tab2');
const lines=document.getElementById('lines');

const C={raid:'#FF7F1A',officer:'#40C040',party:'#AAAAFF',guild:'#40FF40',whisper:'#FF80FF',say:'#FFFFFF',general:'#FFC0C0',emote:'#FF7F50',system:'#FFFF00',loot:'#A335EE'};
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function hash(s){let h=2166136261;for(const ch of s){h^=ch.codePointAt(0);h=Math.imul(h,16777619);}return h>>>0;}
function now(){const d=new Date();return String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');}

// emotes tag "25:0-4,12-16/1902:6-10" -> rendered HTML (indices are codepoints)
function render(text,emotes){
  const cp=[...text], r=[];
  if(emotes)for(const part of emotes.split('/')){const [id,rs]=part.split(':');if(!/^[\w-]+$/.test(id||'')||!rs)continue;
    for(const x of rs.split(',')){const [a,b]=x.split('-').map(Number);if(b>=a)r.push({a,b,id});}}
  r.sort((p,q)=>p.a-q.a);let o='',i=0;
  for(const e of r){if(e.a<i)continue;const n=cp.slice(e.a,e.b+1).join('');o+=esc(cp.slice(i,e.a).join(''));
    o+=`<img src="https://static-cdn.jtvnw.net/emoticons/v2/${e.id}/default/dark/1.0" alt="${esc(n)}">`;i=e.b+1;}
  return o+esc(cp.slice(i).join(''));
}
function add(html,color,meta={}){
  const d=document.createElement('div');d.className='line';d.style.color=color;
  if(meta.id)d.dataset.id=meta.id;if(meta.uid)d.dataset.uid=meta.uid;
  d.innerHTML=(SHOWTS?`<span class="ts">[${now()}]</span> `:'')+html;lines.appendChild(d);
  while(lines.children.length>MAX)lines.firstChild.remove();
  if(FADE>0)setTimeout(()=>{d.classList.add('out');setTimeout(()=>d.remove(),1000)},FADE*1000);
}
const system=t=>add(esc(t),C.system);

function role(t){const b=t.badges||'';const has=k=>new RegExp('(^|,)'+k+'/').test(b);
  if(has('broadcaster'))return'raid';if(has('moderator'))return'officer';if(has('vip'))return'party';
  if(has('subscriber')||has('founder'))return'guild';if(t['first-msg']==='1')return'whisper';return'viewer';}
const PREFIX={raid:'[Raid Leader] ',officer:'[Officer] ',party:'[Party] ',guild:'[Guild] '};

function privmsg(t,login,text){
  const name=t['display-name']||login, uid=t['user-id'], id=t.id;
  if(BOTS.has(login))return; if(HIDECMDS&&text.startsWith('!'))return;
  let action=false;const m=/^\x01ACTION (.*)\x01$/.exec(text);if(m){action=true;text=m[1];}
  const body=render(text,t.emotes), N=esc(name), meta={id,uid};
  if(t.bits){const b=+t.bits;add(`${N} receives loot: [${b} Bit${b===1?'':'s'}]. ${body}`,C.loot,meta);return;}
  if(action){add(`${N} ${body}`,C.emote,meta);return;}
  const r=role(t), hl=t['msg-id']==='highlighted-message'||!!t['custom-reward-id'];
  let html,color;
  if(PREFIX[r]){html=`${PREFIX[r]}[${N}]: ${body}`;color=C[r];}
  else if(r==='whisper'){html=`[${N}] whispers: ${body}`;color=C.whisper;}
  else if(hash(login)%2){html=`[1. General] [${N}]: ${body}`;color=C.general;}
  else{html=`[${N}] says: ${body}`;color=C.say;}
  if(hl)color=C.whisper;
  add(html,color,meta);
}
function usernotice(t,text){
  const n=t['display-name']||t.login||'Someone', id=t['msg-id'];
  const months=t['msg-param-cumulative-months'];
  let s=null;
  if(id==='sub')s=`${n} has joined the guild!`;
  else if(id==='resub')s=`${n} renewed guild membership (${months||'?'} months)!`;
  else if(id==='subgift')s=`${n} gifted a guild membership to ${t['msg-param-recipient-display-name']||'someone'}!`;
  else if(id==='submysterygift')s=`${n} gifted ${t['msg-param-mass-gift-count']||'some'} guild memberships!`;
  else if(id==='raid')s=`${t['msg-param-displayName']||n} is raiding with a party of ${t['msg-param-viewerCount']||'?'}!`;
  if(s){system(s);if(text)privmsg(t,(t.login||'').toLowerCase(),text);}
}
function clearchat(t){const u=t['target-user-id'];
  if(!u){lines.innerHTML='';return;}lines.querySelectorAll(`.line[data-uid="${CSS.escape(u)}"]`).forEach(l=>l.remove());}
function clearmsg(t){const id=t['target-msg-id'];if(id)lines.querySelectorAll(`.line[data-id="${CSS.escape(id)}"]`).forEach(l=>l.remove());}

// IRC line parser: @tags :prefix COMMAND params :trailing
function unesc(v){return v.replace(/\\(.)/g,(_,c)=>({s:' ',':':';','\\':'\\',r:'\r',n:'\n'}[c]??c));}
function parse(raw){let i=0;const o={tags:{},prefix:'',cmd:'',params:[],trailing:null};
  if(raw[0]==='@'){const sp=raw.indexOf(' ');for(const kv of raw.slice(1,sp).split(';')){const e=kv.indexOf('=');o.tags[e<0?kv:kv.slice(0,e)]=e<0?'':unesc(kv.slice(e+1));}i=sp+1;}
  if(raw[i]===':'){const sp=raw.indexOf(' ',i);o.prefix=raw.slice(i+1,sp);i=sp+1;}
  const tr=raw.indexOf(' :',i);const head=tr<0?raw.slice(i):raw.slice(i,tr);if(tr>=0)o.trailing=raw.slice(tr+2);
  const parts=head.split(' ').filter(Boolean);o.cmd=parts.shift()||'';o.params=parts;return o;}
function handleRaw(raw,ws){
  const m=parse(raw);
  switch(m.cmd){
    case'PING':ws&&ws.send('PONG :'+(m.trailing||'tmi.twitch.tv'));break;
    case'PRIVMSG':privmsg(m.tags,m.prefix.split('!')[0],m.trailing||'');break;
    case'USERNOTICE':usernotice(m.tags,m.trailing);break;
    case'CLEARCHAT':clearchat(m.tags);break;
    case'CLEARMSG':clearmsg(m.tags);break;
    case'RECONNECT':ws&&ws.close();break;
  }
}
window.wowChat={handleRaw,parse};

if(TEST){runTest();return;}
if(!CHANNEL){document.getElementById('hint').hidden=false;return;}
let delay=1000;
function connect(){
  const ws=new WebSocket('wss://irc-ws.chat.twitch.tv:443');let ok=false;
  ws.onopen=()=>{ws.send('CAP REQ :twitch.tv/tags twitch.tv/commands');ws.send('PASS SCHMOOPIIE');
    ws.send('NICK justinfan'+(10000+Math.floor(Math.random()*89999)));ws.send('JOIN #'+CHANNEL);};
  ws.onmessage=e=>{for(const l of String(e.data).split('\r\n'))if(l){if(!ok&&/ 001 /.test(l)){ok=true;delay=1000;}try{handleRaw(l,ws);}catch(err){console.warn(err);}}};
  ws.onclose=()=>{setTimeout(connect,delay+Math.random()*500);delay=Math.min(delay*2,30000);};
  ws.onerror=()=>{try{ws.close();}catch(_){}}; 
}
connect();

function runTest(){
  const T=(tags,login,text,cmd='PRIVMSG')=>{const t=Object.entries(tags).map(([k,v])=>k+'='+String(v).replace(/ /g,'\\s').replace(/;/g,'\\:')).join(';');
    return `@${t} :${login}!${login}@${login}.tmi.twitch.tv ${cmd} #remy${text!=null?' :'+text:''}`;};
  let n=0;const id=()=>'m'+(++n);
  const S=[
   ()=>T({badges:'broadcaster/1','display-name':'Remy','user-id':'1',id:id()},'remy','Pull in 10, healers drink up'),
   ()=>T({badges:'moderator/1','display-name':'Thrallbert','user-id':'2',id:id()},'thrallbert','No spoilers for the new raid tier pls'),
   ()=>T({badges:'vip/1','display-name':'Jainabelle','user-id':'3',id:id()},'jainabelle','Portals up to Stormwind'),
   ()=>T({badges:'subscriber/12','display-name':'Lokdar','user-id':'4',id:id(),emotes:'425618:25-27'},'lokdar','need a tank for M+ after LUL'),
   ()=>T({'first-msg':'1','display-name':'NewbieNelf','user-id':'5',id:id()},'newbienelf','hi! first time here, love the UI'),
   ()=>T({'display-name':'Leeroyy','user-id':'6',id:'kill-me'},'leeroyy','WTS [Thunderfury, Blessed Blade of the Windseeker]'),
   ()=>T({'display-name':'Moonfirebabe','user-id':'7',id:id()},'moonfirebabe','where is the flight master?'),
   ()=>T({'display-name':'Murlocmaster','user-id':'8',id:id()},'murlocmaster','\x01ACTION dances on the mailbox\x01'),
   ()=>T({'display-name':'Goldfarmer','user-id':'9',id:id(),bits:'500'},'goldfarmer','Cheer500 for repairs'),
   ()=>T({'msg-id':'resub','display-name':'Sylvana_W',login:'sylvana_w','msg-param-cumulative-months':'14'},'tmi.twitch.tv',null,'USERNOTICE'),
   ()=>T({badges:'subscriber/3','msg-id':'highlighted-message','display-name':'Sylvana_W','user-id':'10',id:id()},'sylvana_w','Remy has to /dance for 10s'),
   ()=>T({'display-name':'xXgankerXx','user-id':'11',id:id()},'xxgankerxx','<img src=x onerror=alert(1)> is this layer full?'),
   ()=>T({'msg-id':'raid','msg-param-displayName':'Kungen','msg-param-viewerCount':'25',login:'kungen'},'tmi.twitch.tv',null,'USERNOTICE'),
   ()=>'@target-msg-id=kill-me :tmi.twitch.tv CLEARMSG #remy :WTS',
   ()=>T({'msg-id':'subgift','display-name':'Bolvar',login:'bolvar','msg-param-recipient-display-name':'NewbieNelf'},'tmi.twitch.tv',null,'USERNOTICE'),
   ()=>T({'display-name':'Hogger','user-id':'12',id:id()},'hogger','this message gets nuked by a timeout'),
   ()=>'@target-user-id=12 :tmi.twitch.tv CLEARCHAT #remy :hogger',
  ];
  let k=0;setInterval(()=>{const i=k++;if(i>0&&i%(S.length*3)===0){lines.innerHTML='';system('Chat was cleared by a moderator.');}handleRaw(S[i%S.length]());},1500);
  handleRaw(S[k++]());
}
})();
