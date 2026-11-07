'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Gain = require('../widgets/audio-gain.js');

const PAGE = 'http://localhost:5000/widgets/orc-clip/index.html';
const ORIGIN = 'http://localhost:5000';

function FakeNode(kind) {
  this.kind = kind;
  this.connections = [];
  this.gain = { value: 1 };
  this.fftSize = 0;
}
FakeNode.prototype.connect = function (dest) {
  this.connections.push(dest);
  return dest;
};
FakeNode.prototype.disconnect = function () {
  this.connections.length = 0;
};

function FakeContext() {
  this.destination = new FakeNode('destination');
  this.state = 'running';
  this.sourceCount = 0;
  this.resumes = 0;
}
FakeContext.prototype.createMediaElementSource = function (element) {
  if (element._srcCreated) {
    const err = new Error('InvalidStateError');
    err.name = 'InvalidStateError';
    throw err;
  }
  element._srcCreated = true;
  this.sourceCount += 1;
  return new FakeNode('source');
};
FakeContext.prototype.createGain = function () {
  return new FakeNode('gain');
};
FakeContext.prototype.createAnalyser = function () {
  return new FakeNode('analyser');
};
FakeContext.prototype.resume = function () {
  this.resumes += 1;
  this.state = 'running';
  return Promise.resolve();
};

function routeOpts(ctx, extra) {
  return Object.assign({
    pageHref: PAGE,
    pageOrigin: ORIGIN,
    context: ctx
  }, extra || {});
}

test('missing, blank, and invalid gain stay at 1', function () {
  assert.equal(Gain.DEFAULT, 1);
  assert.equal(Gain.parseGain(undefined), 1);
  assert.equal(Gain.parseGain(null), 1);
  assert.equal(Gain.parseGain(''), 1);
  assert.equal(Gain.parseGain('   '), 1);
  assert.equal(Gain.parseGain('foo'), 1);
  assert.equal(Gain.parseGain('2.5abc'), 1);
  assert.equal(Gain.parseGain('NaN'), 1);
  assert.equal(Gain.gainFromParams(new URLSearchParams('')), 1);
  assert.equal(Gain.gainFromParams(new URLSearchParams('vol=2.5&vvol=2.5')), 1);
});

test('explicit gain passes through and clamps to 0..4', function () {
  assert.equal(Gain.parseGain('1.6'), 1.6);
  assert.equal(Gain.parseGain(2.5), 2.5);
  assert.equal(Gain.parseGain('0'), 0);
  assert.equal(Gain.parseGain('4'), 4);
  assert.equal(Gain.parseGain('9'), 4);
  assert.equal(Gain.parseGain('-3'), 0);
  assert.equal(Gain.parseGain('+1.6'), 1.6);
  assert.equal(Gain.gainFromParams(new URLSearchParams('gain=1.6')), 1.6);
  assert.equal(Gain.gainFromParams(new URLSearchParams('gain=2.5')), 2.5);
  assert.equal(Gain.gainFromParams(new URLSearchParams('gain=9')), 4);
  assert.equal(Gain.gainFromParams(new URLSearchParams('gain=nope')), 1);
});

test('same-origin and blob media can be routed; cross-origin and file pages cannot', function () {
  assert.equal(Gain.routable('audio/WoW1.mp3', PAGE, ORIGIN), true);
  assert.equal(Gain.routable('/clips/raid.mp4', PAGE, ORIGIN), true);
  assert.equal(Gain.routable('http://localhost:5000/voice_lines/orc/a.mp3', PAGE, ORIGIN), true);
  assert.equal(Gain.routable('blob:http://localhost:5000/11111111-2222-3333-4444-555555555555', PAGE, ORIGIN), true);
  assert.equal(Gain.routable('https://clips.twitch.tv/embed?clip=abc', PAGE, ORIGIN), false);
  assert.equal(Gain.routable('https://cdn.example/clip.mp4', PAGE, ORIGIN), false);
  assert.equal(Gain.routable('audio/Dono1.mp3', 'file:///widgets/paladin-sub/index.html', 'null'), false);
  assert.equal(Gain.routable('', PAGE, ORIGIN), false);
});

test('routed audio has one speaker path and a silent analyser tap', function () {
  const ctx = new FakeContext();
  const el = {};
  const handle = Gain.attach(el, '1.6', routeOpts(ctx, {
    url: 'http://localhost:5000/clips/a.mp4',
    analyse: true
  }));
  assert.equal(handle.routed, true);
  assert.equal(handle.reason, 'routed');
  assert.equal(handle.gain.gain.value, 1.6);
  assert.equal(ctx.sourceCount, 1);
  assert.ok(handle.source.connections.includes(handle.gain));
  assert.ok(handle.source.connections.includes(handle.analyser));
  assert.equal(handle.analyser.connections.includes(ctx.destination), false);
  assert.equal(handle.analyser.connections.length, 0);
  assert.deepEqual(handle.gain.connections, [ctx.destination]);
  assert.equal(handle.source.connections.includes(ctx.destination), false);
});

test('a reused video element is armed once and the gain can change', function () {
  const ctx = new FakeContext();
  const el = {};
  const opts = routeOpts(ctx, { url: '/clips/a.mp4', analyse: false });
  const first = Gain.attach(el, 1, opts);
  const second = Gain.attach(el, 2.5, opts);
  assert.equal(first, second);
  assert.equal(ctx.sourceCount, 1);
  assert.equal(second.gain.gain.value, 2.5);
  assert.equal(second.analyser, null);
  assert.equal(el._srcCreated, true);
});

test('a cross-origin URL does not call createMediaElementSource', function () {
  const ctx = new FakeContext();
  let calls = 0;
  ctx.createMediaElementSource = function () {
    calls += 1;
    throw new Error('should not route');
  };
  const el = {};
  const handle = Gain.attach(el, 2.5, routeOpts(ctx, {
    url: 'https://clips.twitch.tv/embed?clip=abc'
  }));
  assert.equal(handle.routed, false);
  assert.equal(handle.reason, 'not-routable');
  assert.equal(calls, 0);
  assert.equal(el._widgetGain, undefined);
  assert.equal(el._srcCreated, undefined);
});

test('createMediaElementSource refusal leaves native output', function () {
  const ctx = new FakeContext();
  ctx.createMediaElementSource = function () {
    throw new Error('denied');
  };
  const el = {};
  const handle = Gain.attach(el, 1.6, routeOpts(ctx, { url: '/clips/a.mp4' }));
  assert.equal(handle.routed, false);
  assert.equal(handle.reason, 'native');
  assert.equal(el._widgetGain, undefined);
});

test('a connect failure after capture still reaches the speakers once', function () {
  const ctx = new FakeContext();
  const realGain = FakeContext.prototype.createGain;
  let gainNodes = 0;
  ctx.createGain = function () {
    gainNodes += 1;
    const node = realGain.call(ctx);
    if (gainNodes === 1) {
      node.connect = function () { throw new Error('connect failed'); };
    }
    return node;
  };
  const el = {};
  const first = Gain.attach(el, 1.6, routeOpts(ctx, { url: '/clips/a.mp4', analyse: true }));
  assert.equal(first.routed, false);
  assert.equal(first.reason, 'unity-fallback');
  assert.equal(ctx.sourceCount, 1);
  assert.ok(first.source.connections.includes(ctx.destination));
  assert.equal(first.analyser, null);
  const second = Gain.attach(el, 4, routeOpts(ctx, { url: '/clips/b.mp4' }));
  assert.equal(second, first);
  assert.equal(ctx.sourceCount, 1);
});

test('chat mask is solid black and opacity cannot fade it', function () {
  const root = path.join(__dirname, '..');
  const css = fs.readFileSync(path.join(root, 'widgets/wow-chat/style.css'), 'utf8');
  const js = fs.readFileSync(path.join(root, 'widgets/wow-chat/chat.js'), 'utf8');
  assert.match(css, /html,body\{[^}]*background:transparent/);
  assert.match(css, /#frame::before\{[^}]*background:#000/);
  const tab = css.match(/\.tab\{[^}]*\}/)[0];
  assert.match(tab, /background:#000/);
  assert.match(tab, /opacity:1/);
  assert.match(css, /#panel\{[^}]*background:#000/);
  assert.equal(css.includes('rgba(var(--bg)'), false);
  assert.equal(css.includes('--opacity'), false);
  assert.equal(css.includes('opacity:.45'), false);
  assert.equal(js.includes("setProperty('--opacity'"), false);
  assert.match(js, /opacity/);
  assert.match(css, /\.line\{[^}]*color:#fff/);
});

test('scene avol stays unclamped and gain only multiplies the master', function () {
  const scenes = fs.readFileSync(path.join(__dirname, '../widgets/scenes/scenes.js'), 'utf8');
  const brb = fs.readFileSync(path.join(__dirname, '../widgets/scenes/brb.html'), 'utf8');
  assert.match(scenes, /var vol=Q\.has\('avol'\)\?\+Q\.get\('avol'\):\.35;/);
  assert.match(scenes, /var master=vol\*boost/);
  assert.equal(/Math\.min\([^;\n]*avol/.test(scenes), false);
  assert.match(brb, /v\.volume=Math\.max\(0,Math\.min\(1,vol\)\)/);
  const boost = Gain.gainFromParams(new URLSearchParams('gain=1.6'));
  const untouched = Gain.gainFromParams(new URLSearchParams('avol=2.5'));
  assert.ok(Math.abs(0.35 * boost - 0.56) < 1e-12);
  assert.equal(untouched, 1);
  assert.equal(2.5 * untouched, 2.5);
});

test('speechSynthesis volume stays the 0-1 trim', function () {
  const root = path.join(__dirname, '..', 'widgets');
  for (const file of ['fact-gnome/fact.js', 'translator/translator.js', 'monk-counselor/monk.js']) {
    const src = fs.readFileSync(path.join(root, file), 'utf8');
    assert.match(src, /u\.volume=VOL/);
    assert.equal(src.includes('u.volume=GAIN'), false);
    assert.equal(src.includes('u.volume=VOL*GAIN'), false);
    assert.match(src, /WidgetGain\.attach\(/);
  }
});

test('orc iframe is not given a gain node', function () {
  const src = fs.readFileSync(path.join(__dirname, '../widgets/orc-clip/orc.js'), 'utf8');
  assert.match(src, /u\.searchParams\.set\('muted'/);
  assert.equal(src.includes("searchParams.set('gain'"), false);
  assert.equal(src.includes("searchParams.set('volume'"), false);
  assert.match(src, /armMedia\(a,src,true\)/);
  assert.match(src, /captured-cross-origin/);
});
