(function(){
'use strict';
// Night Elf Translator. Data: Production Center GET /events (redemptions), GET /translate, GET /tts. No secrets here.
const P=new URLSearchParams(location.search),g=k=>P.get(k);
const TEST=g('test')==='1',ONCE=g('once')==='1';
const SERVER=(g('server')||'http://localhost:5000').replace(/\/+$/,'');
const R_TO=(g('rewardto')||'Translate to English').trim().toLowerCase(),R_FROM=(g('rewardfrom')||'Translate from English').trim().toLowerCase();
const R_TO_ID=(g('rewardtoid')||'').trim(),R_FROM_ID=(g('rewardfromid')||'').trim();
const MAXLEN=200,HOLD=Math.max(5,+(g('duration')||9))*1000;
const MUTE=g('tts')==='0',BROWSER_TTS=!MUTE&&'speechSynthesis' in window,LIVE=!MUTE&&g('livetts')!=='0';
const RATE=g('rate')||'+0%',PITCH=g('pitch')||'+0Hz',VOL=Math.min(1,Math.max(0,+(g('vol')||1)));
const stage=document.getElementById('stage'),$=id=>document.getElementById(id);
const side=(g('side')||'left').toLowerCase()==='right'?'right':'left';stage.className=side;
if(g('scale'))stage.style.setProperty('--scale',g('scale'));
const set=(...c)=>{stage.className=[side,...c].join(' ');};
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const pick=a=>a[Math.floor(Math.random()*a.length)];

// ---- code-drawn flags (viewBox 30x20) ----
const S=b=>`<svg viewBox="0 0 30 20" preserveAspectRatio="none">${b}</svg>`;
const V3=(a,b,c)=>S(`<rect width="10" height="20" fill="${a}"/><rect x="10" width="10" height="20" fill="${b}"/><rect x="20" width="10" height="20" fill="${c}"/>`);
const H3=(a,b,c)=>S(`<rect width="30" height="7" fill="${a}"/><rect y="6.6" width="30" height="7" fill="${b}"/><rect y="13.3" width="30" height="6.7" fill="${c}"/>`);
const FLAGS={
 es:V3('#006847','#fff','#ce1126').replace('</svg>','<circle cx="15" cy="10" r="2.6" fill="#8c5a2b"/></svg>'), // Mexico (es-MX voice)
 pt:S('<rect width="30" height="20" fill="#009c3b"/><polygon points="15,2.5 27.5,10 15,17.5 2.5,10" fill="#ffdf00"/><circle cx="15" cy="10" r="4.6" fill="#002776"/><path d="M10.6 9.2q4.4-1.6 8.8 1" stroke="#fff" stroke-width=".9" fill="none"/>'),
 fr:V3('#0055a4','#fff','#ef4135'),
 ja:S('<rect width="30" height="20" fill="#fff"/><circle cx="15" cy="10" r="6" fill="#bc002d"/>'),
 ko:S('<rect width="30" height="20" fill="#fff"/><path d="M10 10a5 5 0 0 1 10 0z" fill="#cd2e3a"/><path d="M10 10a5 5 0 0 0 10 0z" fill="#0047a0"/><g stroke="#000" stroke-width="1.1"><path d="M3 4l3-2.2M3.8 5.1l3-2.2M4.6 6.2l3-2.2M22.4 13.8l3 2.2M23.2 12.7l3 2.2M24 11.6l3 2.2M23 4l3 2.2M22.2 5.1l3 2.2M21.4 6.2l3 2.2M6 18.2l3-2.2M5.2 17.1l3-2.2M4.4 16l3-2.2"/></g>'),
 'zh-Hans':S('<rect width="30" height="20" fill="#de2910"/><polygon points="6,2.5 7.2,6 10.8,6 7.9,8.1 9,11.6 6,9.4 3,11.6 4.1,8.1 1.2,6 4.8,6" fill="#ffde00"/><g fill="#ffde00"><circle cx="12" cy="2.4" r=".9"/><circle cx="14" cy="4.6" r=".9"/><circle cx="14" cy="7.6" r=".9"/><circle cx="12" cy="9.8" r=".9"/></g>'),
 'zh-Hant':S('<rect width="30" height="20" fill="#7a1f2b"/><rect x="1" y="1" width="28" height="18" rx="2" fill="none" stroke="#e8c26a" stroke-width="1"/><text x="15" y="15" font-size="13" text-anchor="middle" fill="#ffe7a0" font-family="serif">繁</text>'),
 de:H3('#000','#dd0000','#ffce00'),
 nl:H3('#ae1c28','#fff','#21468b'),
 en:S('<rect width="30" height="20" fill="#b22234"/><g fill="#fff"><rect y="1.54" width="30" height="1.54"/><rect y="4.62" width="30" height="1.54"/><rect y="7.7" width="30" height="1.54"/><rect y="10.78" width="30" height="1.54"/><rect y="13.86" width="30" height="1.54"/><rect y="16.94" width="30" height="1.54"/></g><rect width="13" height="10.8" fill="#3c3b6e"/>'),
 xx:S('<rect width="30" height="20" fill="#2c3a6b"/><circle cx="15" cy="10" r="6" fill="none" stroke="#bcd0ff" stroke-width="1.2"/><path d="M9 10h12M15 4v12M11 5.5q4 4.5 0 9M19 5.5q-4 4.5 0 9" stroke="#bcd0ff" stroke-width=".8" fill="none"/>')
};
const flag=c=>`<span class="flag" data-l="${c}">${FLAGS[c]||FLAGS.xx}</span>`;

// ---- languages: code -> name, edge-tts voice, aliases (case-insensitive) ----
const LANGS={
 es:{name:'Spanish',voice:'es-MX-DaliaNeural',a:['spanish','español','espanol','esp','es','sp','mx','mexican','castellano']},
 pt:{name:'Portuguese',voice:'pt-BR-FranciscaNeural',a:['portuguese','português','portugues','pt','pt-br','ptbr','br','brazilian','brasil','brazil','por']},
 fr:{name:'French',voice:'fr-FR-DeniseNeural',a:['french','français','francais','fr','fra']},
 ja:{name:'Japanese',voice:'ja-JP-NanamiNeural',a:['japanese','日本語','nihongo','ja','jp','jpn']},
 ko:{name:'Korean',voice:'ko-KR-SunHiNeural',a:['korean','한국어','hangul','ko','kr','kor']},
 'zh-Hans':{name:'Chinese (Simplified)',voice:'zh-CN-XiaoxiaoNeural',a:['simplified chinese','chinese simplified','chinese (simplified)','simplified','mandarin','chinese','中文','简体','简体中文','zh','zh-cn','zh-hans','zhs','cn','chs']},
 'zh-Hant':{name:'Chinese (Traditional)',voice:'zh-TW-HsiaoChenNeural',a:['traditional chinese','chinese traditional','chinese (traditional)','traditional','繁體','繁體中文','繁体','zh-tw','zh-hant','zht','tw','cht']},
 de:{name:'German',voice:'de-DE-KatjaNeural',a:['german','deutsch','de','ger','deu']},
 nl:{name:'Dutch',voice:'nl-NL-ColetteNeural',a:['dutch','nederlands','netherlands','holland','nl','nld']}
};
const EN={name:'English',voice:g('envoice')||'en-GB-SoniaNeural',rate:g('enrate')||'-8%',pitch:g('enpitch')||'-4Hz'};
const FLAG_EMOJI={MX:'es',ES:'es',AR:'es',CO:'es',CL:'es',PE:'es',BR:'pt',PT:'pt',FR:'fr',JP:'ja',KR:'ko',CN:'zh-Hans',TW:'zh-Hant',HK:'zh-Hant',DE:'de',AT:'de',NL:'nl'};
const ALIASES=[];for(const[c,l]of Object.entries(LANGS))for(const a of l.a)ALIASES.push([a,c]);
ALIASES.sort((x,y)=>y[0].length-x[0].length);
const esc=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
const ALIAS_RE=ALIASES.map(([a])=>esc(a)).join('|');
const HEAD=new RegExp(`^(?:(?:to|in|into)\\s+)?(${ALIAS_RE})(?:\\s*[:>\\-–—,|]+\\s*|\\s+)([\\s\\S]+)$`,'i');
const TAIL=new RegExp(`^([\\s\\S]+?)\\s*(?:(?:\\s(?:in|to|into)\\s+)|\\s*(?:->|→|\\|)\\s*)(${ALIAS_RE})\\s*[.!?]?$`,'i');
const byAlias=s=>{s=s.toLowerCase();const f=ALIASES.find(([a])=>a===s);return f?f[1]:null;};
// "spanish: hello" / "es hello" / "jp: gg" / "🇫🇷 bonjour" / "hello chat in german"
// "Translate to English" optional source tag: "jp: konnichiwa" / "fr: bonjour" / "🇰🇷 annyeong". Needs a separator (or flag) so "es un buen día" isn't misread.
const TAG=new RegExp(`^(${ALIAS_RE})\\s*[:>|\\-–—]+\\s*([\\s\\S]+)$`,'i');
function parseTag(raw){const t=raw.trim();
 const fm=t.match(/^((?:\uD83C[\uDDE6-\uDDFF]){2})\s*[:>\-–—,|]?\s*([\s\S]*)$/);
 if(fm){const cc=[...fm[1]].map(ch=>String.fromCharCode(ch.codePointAt(0)-0x1F1E6+65)).join('');return{lang:FLAG_EMOJI[cc]||null,text:fm[2].trim()};}
 const m=t.match(TAG);if(m&&m[2].trim())return{lang:byAlias(m[1]),text:m[2].trim()};
 return{lang:null,text:t};}
function parseFrom(raw){
 let t=raw.trim();
 const fm=t.match(/^((?:\uD83C[\uDDE6-\uDDFF]){2})\s*[:>\-–—,|]?\s*([\s\S]*)$/);
 if(fm){const cc=[...fm[1]].map(ch=>String.fromCharCode(ch.codePointAt(0)-0x1F1E6+65)).join('');const c=FLAG_EMOJI[cc];return c&&fm[2].trim()?{lang:c,text:fm[2].trim()}:{lang:null,text:fm[2].trim()};}
 let m=t.match(HEAD);if(m&&m[2].trim())return{lang:byAlias(m[1]),text:m[2].trim()};
 m=t.match(TAIL);if(m&&m[1].trim())return{lang:byAlias(m[2]),text:m[1].trim()};
 return{lang:null,text:t};
}
// detected code from backend -> our code (DeepL/MyMemory send ZH, PT-BR, EN-US, etc.)
const TRAD=/[們這個說來為對時會國語學們麼們嗎還點過開關後無與誰應該讓實現經體]/;
function normLang(d,text){d=String(d||'').toLowerCase();
 if(d.startsWith('zh'))return /hant|tw|hk/.test(d)?'zh-Hant':/hans|cn/.test(d)?'zh-Hans':(TRAD.test(text)?'zh-Hant':'zh-Hans');
 const b=d.split(/[-_]/)[0];return LANGS[b]?b:(b==='en'?'en':(b||'xx'));}

// ---- personality ----
const Q={
 to:['Ooh, a linguist in chat. I like that.','Translated and only slightly flustered.','My tome says this is worth reading out loud.','Language nerds are the best kind of nerds.','Ishnu-alah, darling.'],
 from:['Elune guide your accent, darling.','Practice it with me sometime?','Polyglot mode: engaged.','Fresh from my moonlit grimoire.','I did the hard part, you do the flirting.'],
 remy:['Remy, if you\'re reading this... nice armor.','Don\'t tell Remy I practiced this one twice.','Remy, I could teach you this in private tutoring. Strictly academic.','*adjusts glasses* Is Remy watching? Asking for a friend.'],
 english:['That was already English, sweetie. I translated it anyway: still English.','English to English? Bold choice. I respect it.'],
 unknown:l=>`${l}? Not in my tome yet. Best guess, darling.`,
 which:'Which language, darling? Try "spanish: hello chat".',
 opts:'Spanish · Portuguese · French · Japanese · Korean · Chinese (simplified / traditional) · German · Dutch',
 closed:['My tome is closed right now. Try again in a moment, darling.','Ugh, the moonwell connection dropped. My tome is closed for now.'],
 empty:'You redeemed me and said... nothing? Cute. Type something next time.'
};
const quip=kind=>Math.random()<.18?pick(Q.remy):pick(Q[kind]);

// ---- pins on her collar ----
const pinsEl=$('pins');pinsEl.innerHTML=Object.keys(LANGS).map(flag).join('');
const lightPin=c=>{for(const el of pinsEl.children)el.classList.toggle('on',el.dataset.l===c);};

// ---- backend ----
async function getJSON(url,ms){const ac=new AbortController(),to=setTimeout(()=>ac.abort(),ms);
 try{const r=await fetch(url,{signal:ac.signal,cache:'no-store'});if(!r.ok)throw new Error('http '+r.status);return await r.json();}finally{clearTimeout(to);}}
async function translate(text,target,source){const q=new URLSearchParams({text,target});if(source)q.set('source',source);
 const j=await getJSON(SERVER+'/translate?'+q,8000);if(!j||typeof j.text!=='string'||!j.text.trim())throw new Error('bad translate');return j;}

// ---- voice: live /tts (lip-sync bounce), else browser voice, else timer ----
const transEl=$('transText'),talkEl=$('talk');let actx=null;
async function speakLive(text,voice){
 const en=voice===EN.voice,q=new URLSearchParams({text,voice,rate:en&&!g('rate')?EN.rate:RATE,pitch:en&&!g('pitch')?EN.pitch:PITCH});
 const ac=new AbortController(),to=setTimeout(()=>ac.abort(),5000);
 let blob;try{const r=await fetch(SERVER+'/tts?'+q,{signal:ac.signal,cache:'no-store'});if(!r.ok)throw new Error('tts http '+r.status);blob=await r.blob();if(!blob.size)throw new Error('empty audio');}finally{clearTimeout(to);}
 const url=URL.createObjectURL(blob),a=new Audio(url);a.volume=VOL;
 await new Promise((ok,bad)=>{a.onloadedmetadata=ok;a.onerror=()=>bad(new Error('bad audio'));setTimeout(()=>bad(new Error('metadata timeout')),4000);});
 let an=null,buf=null;
 try{actx=actx||new (window.AudioContext||window.webkitAudioContext)();if(actx.state==='suspended')await actx.resume();
  const src=actx.createMediaElementSource(a);an=actx.createAnalyser();an.fftSize=1024;buf=new Uint8Array(an.fftSize);src.connect(an);an.connect(actx.destination);}catch(e){an=null;}
 return new Promise((resolve,reject)=>{
  let done=false,raf=0,lvl=0;window.__elfLip=0;
  const fin=()=>{if(done)return;done=true;cancelAnimationFrame(raf);transEl.textContent=text;stage.classList.remove('talk','lips');talkEl.style.transform='';URL.revokeObjectURL(url);resolve();};
  stage.classList.add('talk');if(an)stage.classList.add('lips');
  const frame=()=>{if(done)return;const dur=a.duration&&isFinite(a.duration)?a.duration:text.length*.07;
   transEl.textContent=text.slice(0,Math.ceil(text.length*Math.min(1,a.currentTime/(dur*.92))));
   if(an){an.getByteTimeDomainData(buf);let s=0;for(let i=0;i<buf.length;i++){const v=(buf[i]-128)/128;s+=v*v;}
    const t=Math.min(1,Math.sqrt(s/buf.length)*6);lvl+=(t-lvl)*(t>lvl?.6:.25);window.__elfLip++;
    talkEl.style.transform=`translateY(${-lvl*6}px) scale(${1+lvl*.02},${1+lvl*.02}) rotate(${Math.sin(a.currentTime*5)*lvl*1.2}deg)`;}
   raf=requestAnimationFrame(frame);};
  a.onended=fin;a.onerror=()=>{if(!done){done=true;stage.classList.remove('talk','lips');reject(new Error('play error'));}};
  a.play().then(()=>{raf=requestAnimationFrame(frame);},e=>{done=true;stage.classList.remove('talk','lips');reject(e);});
  setTimeout(fin,(a.duration||20)*1000+3000);
 });
}
function speakBrowser(text,bcp){
 return new Promise(resolve=>{
  const est=Math.max(1800,text.length*70);let done=false;const t0=Date.now();
  const fin=()=>{if(done)return;done=true;clearInterval(tk);clearTimeout(sf);transEl.textContent=text;stage.classList.remove('talk');resolve();};
  stage.classList.add('talk');
  const tk=setInterval(()=>{const n=Math.floor(text.length*(Date.now()-t0)/est);transEl.textContent=text.slice(0,n);if(!BROWSER_TTS&&n>=text.length)fin();},40);
  const sf=setTimeout(fin,est*2+3000);if(!BROWSER_TTS)return;
  try{speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(text);u.lang=bcp;u.volume=VOL;
   const v=(speechSynthesis.getVoices()||[]).find(v=>v.lang&&v.lang.toLowerCase().startsWith(bcp.slice(0,2).toLowerCase()));if(v)u.voice=v;
   u.onend=fin;u.onerror=()=>setTimeout(fin,Math.max(0,est-(Date.now()-t0)));speechSynthesis.speak(u);
   setTimeout(()=>{if(!done&&!speechSynthesis.speaking&&!speechSynthesis.pending)setTimeout(fin,Math.max(0,est-(Date.now()-t0)));},1500);
  }catch(e){setTimeout(fin,est);}
 });
}
async function speak(text,code){
 const voice=code==='en'?EN.voice:(LANGS[code]||{}).voice||EN.voice;
 if(MUTE){window.__elfMode='muted';return speakBrowser(text,voice.slice(0,5));}
 if(LIVE){try{await speakLive(text,voice);window.__elfMode='live';return;}catch(e){console.warn('live TTS failed, falling back',e&&e.message);}}
 window.__elfMode='browser';return speakBrowser(text,voice.slice(0,5));
}

// ---- show one job ----
function paint({who,hdr,origCode,orig,transCode,trans,q}){
 $('who').textContent=who||'';$('hdr').textContent=hdr;
 $('pinFrom').innerHTML=origCode?flag(origCode):'';$('origText').textContent=orig||'';
 $('pinTo').innerHTML=transCode?flag(transCode):'';transEl.textContent=trans||'';$('quip').textContent=q||'';
}
async function present(card,sayText,sayCode){
 const extra=[!card.orig&&'noorig',!card.transCode&&'notrans'].filter(Boolean);
 paint({...card,trans:sayText?'':card.trans});lightPin(card.transCode==='en'?card.origCode:card.transCode);
 set('in',...extra);await wait(950);set('in','show',...extra);await wait(350);
 const t=Date.now();
 if(sayText)await speak(sayText,sayCode);
 await wait(Math.max(2500,HOLD-(Date.now()-t)));
 set('out',...extra);await wait(800);set();lightPin(null);await wait(350);
}
const clip=s=>{s=String(s||'').replace(/\s+/g,' ').trim();return s.length>MAXLEN?s.slice(0,MAXLEN-1)+'…':s;};
async function handle(job){
 const who=job.user||'';
 if(job.mode==='to'){
  const tg=parseTag(String(job.input||''));const text=clip(tg.text);
  if(!text)return present({who,hdr:'Hmm?',trans:Q.empty},null);
  let r;try{r=await translate(text,'en',tg.lang||undefined);}catch(e){return present({who,hdr:'Tome closed',trans:pick(Q.closed)},null);}
  const src=tg.lang||normLang(r.detected||r.source,text);
  const q=src==='en'?pick(Q.english):LANGS[src]?quip('to'):Q.unknown(String(r.detected||'That').toUpperCase());
  return present({who,hdr:(LANGS[src]?LANGS[src].name:'Mystery tongue')+' → English',origCode:src,orig:text,transCode:'en',trans:clip(r.text),q},clip(r.text),'en');
 }
 const p=parseFrom(String(job.input||''));const text=clip(p.text);
 if(!p.lang||!text)return present({who,hdr:'Which language, darling?',trans:Q.which,q:Q.opts},null);
 let r;try{r=await translate(text,p.lang,'en');}catch(e){return present({who,hdr:'Tome closed',trans:pick(Q.closed)},null);}
 return present({who,hdr:'English → '+LANGS[p.lang].name,origCode:'en',orig:text,transCode:p.lang,trans:clip(r.text),q:quip('from')},clip(r.text),p.lang);
}
const queue=[];let busy=false;
function fire(mode,user,input){if(queue.length>=20)return;queue.push({mode,user:String(user||''),input:String(input||'').slice(0,1000)});if(!busy)run();}
async function run(){busy=true;while(queue.length){const j=queue.shift();try{await handle(j);}catch(e){console.warn(e);set();}}busy=false;}
window.elfTranslator={fire,parseFrom,parseTag};

if(TEST){const demo=[['to','Jainabelle','¡Hola chat! ¿Cómo están todos esta noche?'],['from','RemyFriend','japanese: thanks for the raid, you are all legends'],
  ['to','Kaldorei_Kat','Bonjour à tous, je suis nouveau ici'],['from','Murlocmaster','🇩🇪 good game everyone'],['from','Thrallbert','hello chat'],['to','Sylvana_W','오늘 방송 너무 재밌어요']];
 let i=0;const go=()=>{const d=demo[i++%demo.length];fire(d[0],d[1],d[2]);};go();if(!ONCE)setInterval(go,14000);return;}

// ---- Production Center feed ----
const seen=new Set();
const kind=(t,id)=>{t=(t||'').trim().toLowerCase();
 if((R_TO_ID&&id===R_TO_ID)||t===R_TO)return 'to';if((R_FROM_ID&&id===R_FROM_ID)||t===R_FROM)return 'from';return null;};
let since=-1,delay=1000;
(async function poll(){
 try{const j=await getJSON(SERVER+'/events?since='+since,5000);
  if(since<0)since=j.last_id||0;
  else{for(const ev of j.events||[]){since=Math.max(since,ev.id||0);
    if(ev.type!=='redemption')continue;const k=kind(ev.reward,ev.reward_id);if(!k)continue;
    if(ev.redemption_id){if(seen.has(ev.redemption_id))continue;seen.add(ev.redemption_id);}
    fire(k,ev.user||ev.login,ev.input);}
   since=Math.max(since,j.last_id||0);}
  delay=1000;
 }catch(e){delay=Math.min(delay*2,15000);}
 setTimeout(poll,delay);
})();
})();
