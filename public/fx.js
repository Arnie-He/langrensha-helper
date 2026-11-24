/* 狼人杀面杀助手 —— 背景音乐
 *
 * 和游戏逻辑无关，app.js 通过 window.FX 调用：
 *   FX.bgm.want(on)    需要 / 不需要背景音乐（受静音开关控制，第一次点屏幕后才能出声）
 *   FX.bgm.toggle()    开 / 关背景音乐
 */
(function () {
  'use strict';

  function store(k, v) {
    try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; }
  }

  // ------------------------------------------------------------ 背景音乐
  // 优先播放 audio/bgm.m4a（如果有人放了一首进去）；没有就用 WebAudio 现场合成一段夜晚小调。

  var bgm = {
    muted: store('lrs:bgm') === 'off', wanted: false, ctx: null, out: null, timer: null, step: 0, next: 0,
    file: null, fileChecked: false, playing: false,

    // 必须在用户点击时调用一次，手机浏览器才允许出声
    unlock: function () {
      var self = this;
      if (!self.fileChecked) {
        self.fileChecked = true;
        fetch('audio/bgm.m4a', { method: 'HEAD' }).then(function (r) {
          if (r.ok) {
            self.file = new Audio('audio/bgm.m4a');
            self.file.loop = true;
            self.file.volume = 0;
            if (self.playing) { self.stopSynth(); self.playing = false; self.sync(); }
          }
        }, function () { /* 没有就合成 */ });
      }
      if (!self.ctx) {
        var AC = window.AudioContext || window.webkitAudioContext;
        if (!AC) return;
        self.ctx = new AC();
      }
      if (self.ctx.state === 'suspended') self.ctx.resume();
      self.sync();
    },

    want: function (on) { this.wanted = !!on; this.sync(); },

    toggle: function () {
      this.muted = !this.muted;
      store('lrs:bgm', this.muted ? 'off' : 'on');
      this.sync();
      return !this.muted;
    },

    sync: function () {
      var on = this.wanted && !this.muted;
      if (on && !this.playing) this.start();
      else if (!on && this.playing) this.stop();
    },

    start: function () {
      if (this.file) {
        var a = this.file;
        this.playing = true;
        var p = a.play();
        if (p && p.catch) p.catch(function () { bgm.playing = false; });
        fade(a, .38, 1500);
        return;
      }
      if (!this.ctx || this.ctx.state !== 'running') return;
      this.playing = true;
      this.buildSynth();
    },

    stop: function () {
      this.playing = false;
      if (this.file) { var a = this.file; fade(a, 0, 900, function () { if (!bgm.playing) a.pause(); }); return; }
      this.stopSynth();
    },

    // ---- 合成器：A 小调，78 拍，四小节循环（Am → F → Dm → E）
    buildSynth: function () {
      var c = this.ctx, self = this;
      self.out = c.createGain();
      self.out.gain.setValueAtTime(0, c.currentTime);
      self.out.gain.linearRampToValueAtTime(.2, c.currentTime + 2.5);
      var verb = c.createConvolver();
      verb.buffer = impulse(c, 2.8);
      var wet = c.createGain();
      wet.gain.value = .55;
      self.bus = c.createGain();
      self.bus.connect(self.out);
      self.bus.connect(verb);
      verb.connect(wet);
      wet.connect(self.out);
      self.out.connect(c.destination);
      self.step = 0;
      self.next = c.currentTime + .1;
      self.timer = setInterval(function () { self.tick(); }, 60);
    },

    stopSynth: function () {
      clearInterval(this.timer);
      if (this.out && this.ctx) {
        var g = this.out, t = this.ctx.currentTime;
        g.gain.cancelScheduledValues(t);
        g.gain.setValueAtTime(g.gain.value, t);
        g.gain.linearRampToValueAtTime(0, t + .8);
        setTimeout(function () { try { g.disconnect(); } catch (e) { /* 已断开 */ } }, 1000);
      }
      this.out = null;
    },

    tick: function () {
      var c = this.ctx, eighth = 60 / 78 / 2;
      while (this.next < c.currentTime + .25) {
        this.note(this.step, this.next);
        this.next += eighth;
        this.step = (this.step + 1) % 32;
      }
    },

    note: function (step, t) {
      // 和弦：根音 + 三个音（MIDI）
      var CH = [[45, 57, 60, 64], [41, 57, 60, 65], [38, 57, 62, 65], [40, 56, 59, 64]];
      var bar = Math.floor(step / 8), i = step % 8, ch = CH[bar];
      var c = this.ctx, bus = this.bus;
      if (i === 0) pad(c, bus, ch.slice(1), t, 60 / 78 * 4);
      if (i === 0 || i === 5) pluck(c, bus, ch[0] + 12, t, .22, 'triangle', 1.2);
      // 拨弦琶音
      var ARP = [1, 2, 3, 2, 1, 3, 2, 3];
      var n = ch[ARP[i]] + 12;
      pluck(c, bus, n, t, i % 2 ? .05 : .08, 'triangle', .5);
      // 心跳：每小节第一拍「咚咚」
      if (i === 0) thump(c, this.out, t, .5);
      if (i === 1) thump(c, this.out, t + .02, .32);
      // 最后一小节结尾一声八音盒
      if (bar === 3 && i === 6) pluck(c, bus, 88, t, .05, 'sine', 2.4);
    }
  };

  function hz(m) { return 440 * Math.pow(2, (m - 69) / 12); }

  function pluck(c, dest, m, t, vol, type, len) {
    var o = c.createOscillator(), g = c.createGain();
    o.type = type;
    o.frequency.value = hz(m);
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(vol, t + .008);
    g.gain.exponentialRampToValueAtTime(.0001, t + len);
    o.connect(g); g.connect(dest);
    o.start(t); o.stop(t + len + .05);
  }

  function pad(c, dest, notes, t, len) {
    var f = c.createBiquadFilter(), g = c.createGain();
    f.type = 'lowpass';
    f.frequency.value = 700;
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(.035, t + .9);
    g.gain.setValueAtTime(.035, t + len - .6);
    g.gain.linearRampToValueAtTime(0, t + len + .3);
    f.connect(g); g.connect(dest);
    notes.forEach(function (m) {
      [-6, 6].forEach(function (cents) {
        var o = c.createOscillator();
        o.type = 'sawtooth';
        o.frequency.value = hz(m);
        o.detune.value = cents;
        o.connect(f);
        o.start(t); o.stop(t + len + .4);
      });
    });
  }

  function thump(c, dest, t, vol) {
    var o = c.createOscillator(), g = c.createGain();
    o.frequency.setValueAtTime(95, t);
    o.frequency.exponentialRampToValueAtTime(42, t + .16);
    g.gain.setValueAtTime(vol, t);
    g.gain.exponentialRampToValueAtTime(.0001, t + .22);
    o.connect(g); g.connect(dest);
    o.start(t); o.stop(t + .25);
  }

  function impulse(c, secs) {
    var len = Math.floor(c.sampleRate * secs), buf = c.createBuffer(2, len, c.sampleRate);
    for (var ch = 0; ch < 2; ch++) {
      var d = buf.getChannelData(ch);
      for (var i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 3);
    }
    return buf;
  }

  function fade(a, to, ms, cb) {
    var from = a.volume, t0 = Date.now();
    (function f() {
      var k = Math.min(1, (Date.now() - t0) / ms);
      a.volume = from + (to - from) * k;
      if (k < 1) requestAnimationFrame(f); else if (cb) cb();
    })();
  }

  window.FX = { bgm: bgm };
})();
