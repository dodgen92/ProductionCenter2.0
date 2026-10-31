// Shared scene engine. Background: bg/tavern.jpg if present, else CSS/canvas. Overlays from SCENE_FX (scenes-config.js).
var Q=new URLSearchParams(location.search),TEST=Q.get('test')==='1';
function esc(s){return String(s).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
function $(id){return document.getElementById(id)}
function setText(id,v){var e=$(id);if(e&&v!=null)e.innerHTML=esc(v)}
(function(){
 var b=document.body;
 b.insertAdjacentHTML('afterbegin','<div id="bg"><div id="bgimg"></div><div id="rune"></div><div id="fx"></div></div><canvas id="cv" width="1920" height="1080"></canvas><div id="vig"></div>');
 var bgsrc=Q.get('bg')||'bg/tavern.jpg',im=new Image();
 im.onload=function(){$('bgimg').style.backgroundImage='url("'+bgsrc.replace(/"/g,'')+'")';$('bg').classList.add('img');b.classList.add('hasimg');tav()};im.src=bgsrc;
 var C=window.SCENE_FX||{},fx=$('fx');
 function glow(cls,f,i){fx.insertAdjacentHTML('beforeend','<div class="'+cls+'" style="left:'+(+f.x)+'px;top:'+(+f.y)+'px;width:'+(+f.r*2)+'px;height:'+(+f.r*2)+'px;animation-delay:-'+(i*.7)+'s"></div>')}
 function tav(){var T=window.TAVERN_FX||{};if(Q.get('bg')&&!T.always)return;
  (T.wall||[]).forEach(function(f,i){glow('wall',f,i)});(T.lanterns||[]).forEach(function(f,i){glow('lantern',f,i*3)});
  (T.sprites||[]).forEach(function(s,i){fx.insertAdjacentHTML('beforeend','<img class="spr '+String(s.anim).replace(/\W/g,'')+'" src="'+String(s.src).replace(/"/g,'')+'" style="left:'+(+s.x)+'px;top:'+(+s.y)+'px;width:'+(+s.w)+'px;animation-delay:-'+(i*1.3)+'s">')});
  (T.glints||[]).forEach(function(f,i){fx.insertAdjacentHTML('beforeend','<div class="glint" style="left:'+(+f.x)+'px;top:'+(+f.y)+'px;animation-delay:-'+(i*1.7)+'s"></div>')});}
 (C.fires||[]).forEach(function(f){glow('fire',f,0)});
 (C.candles||[]).forEach(function(f,i){glow('candle',f,i)});
 // embers + dust motes
 var cv=$('cv'),g=cv.getContext('2d'),P=[],ne=+(Q.get('embers')||C.embers||60),nd=+(Q.get('dust')||C.dust||40);
 var src=C.emberFrom||{x:960,y:1080,w:1920};
 var L=((window.TAVERN_FX||{}).lanterns)||[],i0; function mk(t,init){var e=t==='e';return{t:t,x:e?src.x-src.w/2+Math.random()*src.w:(L.length&&Math.random()<.6?L[i0=Math.floor(Math.random()*L.length)].x+(Math.random()-.5)*400:Math.random()*1920),y:init&&e?src.y-Math.random()*500:(e?src.y:(L.length&&Math.random()<.6?L[Math.floor(Math.random()*L.length)].y+Math.random()*350:Math.random()*1080)),vx:(Math.random()-.5)*(e?.6:.15),vy:e?-(.4+Math.random()*1.2):(Math.random()-.5)*.12,r:e?1+Math.random()*2:.8+Math.random()*1.6,l:0,L:e?300+Math.random()*400:600+Math.random()*600,p:Math.random()*6}}
 for(var i=0;i<ne;i++)P.push(mk('e',1));for(i=0;i<nd;i++)P.push(mk('d',1));
 function f(){g.clearRect(0,0,1920,1080);for(var i=0;i<P.length;i++){var p=P[i];p.l++;p.p+=.03;p.x+=p.vx+Math.sin(p.p)*.3;p.y+=p.vy;var a=Math.sin(Math.PI*p.l/p.L);
  if(p.l>p.L||p.y<-10){P[i]=mk(p.t,0);continue}
  g.globalAlpha=Math.max(0,a)*(p.t==='e'?.9:.35);g.fillStyle=p.t==='e'?'#ffb040':'#f0e0c0';g.beginPath();g.arc(p.x,p.y,p.r,0,7);g.fill()}
  requestAnimationFrame(f)}f();
 setText('title',Q.get('title'));setText('subtitle',Q.get('sub'));
})();
function rotate(id,lines,ms){var e=$(id),i=0;if(!e||!lines||!lines.length)return;lines=lines.slice().sort(function(){return Math.random()-.5});e.innerHTML=esc(lines[0]);
 setInterval(function(){e.classList.add('out');setTimeout(function(){i=(i+1)%lines.length;e.innerHTML=esc(lines[i]);e.classList.remove('out')},600)},ms||8000)}

// Procedural tavern ambience (WebAudio, no audio files). ?ambience=0 mutes, ?avol=0.35
var AMB=(function(){if(Q.get('ambience')==='0')return{duck:function(){}};
 var A;try{A=new (window.AudioContext||window.webkitAudioContext)()}catch(e){return{duck:function(){}}}
 var vol=Q.has('avol')?+Q.get('avol'):.35,M=A.createGain();M.gain.value=vol;M.connect(A.destination);
 var nb=A.createBuffer(1,A.sampleRate*2,A.sampleRate),d=nb.getChannelData(0),l=0;for(var i=0;i<d.length;i++){var w=Math.random()*2-1;l=(l+.02*w)/1.02;d[i]=l*3.5}
 function noise(){var s=A.createBufferSource();s.buffer=nb;s.loop=true;return s}
 // fire bed: brown noise lowpassed
 var f=noise(),lp=A.createBiquadFilter();lp.type='lowpass';lp.frequency.value=500;var fg=A.createGain();fg.gain.value=.5;f.connect(lp).connect(fg).connect(M);f.start();
 // room tone hum
 var o=A.createOscillator(),og=A.createGain();o.frequency.value=58;og.gain.value=.025;o.connect(og).connect(M);o.start();
 var wb=A.createBuffer(1,A.sampleRate*.05,A.sampleRate),wd=wb.getChannelData(0);for(i=0;i<wd.length;i++)wd[i]=(Math.random()*2-1)*Math.pow(1-i/wd.length,4);
 function pop(){var s=A.createBufferSource(),bp=A.createBiquadFilter(),g=A.createGain();s.buffer=wb;bp.type='bandpass';bp.frequency.value=1500+Math.random()*3000;g.gain.value=.15+Math.random()*.5;s.playbackRate.value=.6+Math.random();s.connect(bp).connect(g).connect(M);s.start()}
 function clink(){var t=A.currentTime,base=1800+Math.random()*900;[1,2.76,5.4].forEach(function(m,k){var os=A.createOscillator(),g=A.createGain();os.frequency.value=base*m;g.gain.setValueAtTime(.05/(k+1),t);g.gain.exponentialRampToValueAtTime(.0001,t+.6);os.connect(g).connect(M);os.start(t);os.stop(t+.7)})}
 function slosh(){var s=noise(),bp=A.createBiquadFilter(),g=A.createGain(),t=A.currentTime;bp.type='bandpass';bp.frequency.setValueAtTime(400,t);bp.frequency.linearRampToValueAtTime(900,t+.4);bp.Q.value=3;g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(.25,t+.15);g.gain.linearRampToValueAtTime(0,t+.6);s.connect(bp).connect(g).connect(M);s.start(t);s.stop(t+.7)}
 (function cr(){if(Math.random()<.7)pop();if(Math.random()<.2)setTimeout(pop,40);setTimeout(cr,80+Math.random()*600)})();
 (function ev(){setTimeout(function(){Math.random()<.6?clink():slosh();ev()},9000+Math.random()*14000)})();
 function resume(){if(A.state!=='running')A.resume().catch(function(){})}resume();setInterval(resume,2000);
 return{duck:function(on){M.gain.setTargetAtTime(on?vol*.3:vol,A.currentTime,.4)},ctx:A}})();
