// Shared playback gain for same-origin and blob media.
// Default is 1, so a URL with no gain= sounds like it did before.
// 1.6 (~+4 dB) is the starting point to put in an OBS URL. Values above 1
// amplify and can clip. The helper clamps the boost to 0..4.
// Twitch iframes, cross-origin media, and speechSynthesis never come through here.
(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.WidgetGain = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  var MIN = 0, MAX = 4, DEFAULT_GAIN = 1;

  function parseGain(raw) {
    if (raw == null) return DEFAULT_GAIN;
    var text = typeof raw === 'number' ? String(raw) : String(raw).trim();
    if (text === '') return DEFAULT_GAIN;
    if (!/^[+-]?(?:\d+\.?\d*|\.\d+)$/.test(text)) return DEFAULT_GAIN;
    var n = Number(text);
    if (!isFinite(n)) return DEFAULT_GAIN;
    if (n < MIN) return MIN;
    if (n > MAX) return MAX;
    return n;
  }

  function gainFromParams(params) {
    if (!params || typeof params.get !== 'function' || !params.has || !params.has('gain')) return DEFAULT_GAIN;
    return parseGain(params.get('gain'));
  }

  // blob: URLs from this page are readable. Same-origin http(s) files are readable.
  // A null origin (file://) and any other host are not. Routing those through
  // createMediaElementSource plays silence, so callers leave native output in place.
  function routable(url, pageHref, pageOrigin) {
    if (url == null || url === '') return false;
    var value = String(url);
    if (/^blob:/i.test(value)) return true;
    var origin = pageOrigin == null ? '' : String(pageOrigin);
    if (!origin || origin === 'null') return false;
    var abs;
    try { abs = new URL(value, pageHref || (origin + '/')); }
    catch (e) { return false; }
    if (!abs.origin || abs.origin === 'null') return false;
    return abs.origin === origin;
  }

  function remember(element, handle) {
    try { element._widgetGain = handle; } catch (e) {}
    return handle;
  }

  // One MediaElementSource per element. A second call only updates the gain.
  // The analyser is a silent tap. Only the gain node feeds the speakers.
  function attach(element, gainValue, options) {
    options = options || {};
    var gain = parseGain(gainValue);
    if (!element) return { routed: false, reason: 'no-element', gainValue: gain };
    var prev = element._widgetGain;
    if (prev && prev.source) {
      if (prev.routed && prev.gain && prev.gain.gain) {
        prev.gain.gain.value = gain;
        prev.gainValue = gain;
      }
      return prev;
    }
    var src = options.url != null ? options.url : (element.currentSrc || element.src || '');
    var pageHref = options.pageHref;
    var pageOrigin = options.pageOrigin;
    if (pageOrigin == null && typeof location !== 'undefined') pageOrigin = location.origin;
    if (pageHref == null && typeof location !== 'undefined') pageHref = location.href;
    if (!routable(src, pageHref, pageOrigin)) {
      return { routed: false, reason: 'not-routable', gainValue: gain };
    }
    var ctx = options.context || null;
    var source = null;
    try {
      if (!ctx) {
        var Ctor = options.AudioContext || globalThis.AudioContext || globalThis.webkitAudioContext;
        if (!Ctor) return { routed: false, reason: 'no-audio-context', gainValue: gain };
        ctx = new Ctor();
      }
      if (ctx.state === 'suspended' && typeof ctx.resume === 'function') {
        try { ctx.resume(); } catch (e) {}
      }
      source = ctx.createMediaElementSource(element);
      var node = ctx.createGain();
      node.gain.value = gain;
      var analyser = null;
      if (options.analyse) {
        analyser = ctx.createAnalyser();
        analyser.fftSize = options.fftSize || 1024;
        source.connect(analyser);
      }
      source.connect(node);
      node.connect(ctx.destination);
      return remember(element, {
        routed: true,
        reason: 'routed',
        ctx: ctx,
        source: source,
        gain: node,
        analyser: analyser,
        gainValue: gain
      });
    } catch (err) {
      // The element is already pulled off its native output once a source node exists.
      // Put that source on the speakers at unity so a later connect error is not silence.
      if (source && ctx) {
        try { source.disconnect(); } catch (e2) {}
        try { source.connect(ctx.destination); } catch (e3) {}
        return remember(element, {
          routed: false,
          reason: 'unity-fallback',
          ctx: ctx,
          source: source,
          gain: null,
          analyser: null,
          gainValue: 1,
          error: err
        });
      }
      return { routed: false, reason: 'native', gainValue: gain, error: err };
    }
  }

  return {
    MIN: MIN,
    MAX: MAX,
    DEFAULT: DEFAULT_GAIN,
    parseGain: parseGain,
    gainFromParams: gainFromParams,
    routable: routable,
    attach: attach
  };
});
