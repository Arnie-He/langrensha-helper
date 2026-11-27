// 手机端脚本（public/app.js）的模拟测试。
//
// 这台机器没有 Node，但 macOS 自带一个 JavaScript 引擎（jsc）。这里把 app.js 原封不动地在 jsc 里跑起来，
// 浏览器提供的东西——页面、长连接、音频、定时器、网络——全部换成假的，由测试来控制时间和网络。
// 测的是最容易在真实聚会里出问题、又没法在一台电脑上手工复现的部分：连接假活着、换房间、
// 声音被系统打断、浏览器不让出声、轮询兜底。
//
// 运行（在仓库根目录）：
//   /System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc tests/client_sim.js
// 平时不用手动跑：tests/test_client.py 会调用它（找不到 jsc 的机器上自动跳过）。

'use strict';

// ---------------------------------------------------------------- 假的时间

var NOW = 0, timers = [], tid = 0;
Date.now = function () { return NOW; };
globalThis.setTimeout = function (fn, ms) { timers.push({ id: ++tid, at: NOW + (ms || 0), fn: fn }); return tid; };
globalThis.setInterval = function (fn, ms) { timers.push({ id: ++tid, at: NOW + ms, fn: fn, every: ms }); return tid; };
globalThis.clearTimeout = globalThis.clearInterval = function (id) { timers = timers.filter(function (t) { return t.id !== id; }); };

function drain() { drainMicrotasks(); }

// 时间往前走 ms 毫秒：到点的定时器依次触发，正在播的声音跟着往前播
function advance(ms) {
  var end = NOW + ms;
  for (;;) {
    var next = Math.min(end, NOW + 50);
    timers.forEach(function (t) { if (t.at < next) next = Math.max(t.at, NOW); });
    AUD.tick(next - NOW);
    NOW = next;
    drain();
    for (;;) {
      var due = timers.filter(function (t) { return t.at <= NOW; }).sort(function (a, b) { return a.at - b.at || a.id - b.id; })[0];
      if (!due) break;
      if (due.every) due.at += due.every; else timers = timers.filter(function (t) { return t !== due; });
      due.fn();
      drain();
    }
    if (NOW >= end) break;
  }
}

// ---------------------------------------------------------------- 假的浏览器

var RENDER, docL, winL, store, ES, AUD, SERVER, fetchLog, acts;

function El(kind) { this.kind = kind; this.childNodes = []; this.attributes = []; this.hidden = false; this.dataset = {}; this.textContent = ''; this._h = ''; this.scrollTop = 0; }
El.prototype.querySelector = function () { return null; };
El.prototype.querySelectorAll = function () { return []; };
El.prototype.getAttribute = function () { return null; };
El.prototype.setAttribute = El.prototype.removeAttribute = El.prototype.addEventListener = El.prototype.focus = function () {};
El.prototype.appendChild = function (c) { return c; };
Object.defineProperty(El.prototype, 'innerHTML', { get: function () { return this._h; }, set: function (v) { this._h = v; RENDER[this.kind] = v; } });

function FakeES(url) { this.url = url; this.readyState = 1; this.closed = false; this.listeners = {}; this.at = NOW; ES.list.push(this); }
FakeES.prototype.addEventListener = function (t, fn) { this.listeners[t] = fn; };
FakeES.prototype.close = function () { this.closed = true; this.readyState = 2; };

function FakeAudio() { this._src = ''; this._dur = 0; this.loop = false; this.paused = true; this.ended = false; this.currentTime = 0; this.onended = null; this.onerror = null; AUD.list.push(this); }
FakeAudio.prototype.setAttribute = function () {};
FakeAudio.prototype.play = function () {
  AUD.calls.push(this._src);
  if (AUD.interrupted) return new Promise(function () {});   // 来电、别的 App 占着声音：play() 没反应，也不报错
  if (AUD.blocked) return Promise.reject({ name: 'NotAllowedError' });
  if (this.ended) { this.ended = false; this.currentTime = 0; }
  this.paused = false;
  return Promise.resolve();
};
FakeAudio.prototype.pause = function () { this.paused = true; };
Object.defineProperty(FakeAudio.prototype, 'src', {
  get: function () { return this._src; },
  set: function (v) {
    var self = this;
    this._src = v; this.currentTime = 0; this.ended = false; this.paused = true; this._dur = AUD.dur(v);
    if (AUD.bad(v)) setTimeout(function () { if (self._src === v && self.onerror) self.onerror(); }, 50);
  }
});

function clipOf(src) { var m = /audio\/([a-z0-9_]+)\.m4a/.exec(src); return m ? m[1] : null; }

function reset(o) {
  o = o || {};
  NOW = 1e12; timers = []; tid = 0;
  RENDER = { app: '', sheet: '', peek: '', toast: '' };
  docL = {}; winL = {}; fetchLog = []; acts = [];
  store = {};
  if (o.saved) store.lrs = JSON.stringify(o.saved);
  ES = { list: [] };
  AUD = {
    list: [], calls: [], blocked: false, interrupted: false, bad: function () { return false; },
    dur: function (src) {
      var m = /^blob:wav-(\d+)/.exec(src);
      if (m) return (+m[1] - 44) / 8000;                       // 静音：按长度算
      var id = clipOf(src);
      return id && SERVER.manifest[id] ? SERVER.manifest[id] : 1;
    },
    tick: function (ms) {
      AUD.list.forEach(function (el) {
        if (el.paused || el.ended || AUD.bad(el._src)) return;
        el.currentTime += ms / 1000;
        if (el.currentTime < el._dur) return;
        if (el.loop) { el.currentTime = el.currentTime % el._dur; return; }
        el.currentTime = el._dur; el.ended = true; el.paused = true;
        if (el.onended) el.onended();
      });
    }
  };
  SERVER = { join: 'join' in o ? o.join : (o.saved || null), view: null, manifest: o.manifest || { a: 1, b: 1, c: 1, test: 1 }, beatStatus: 200, down: false, badAudio: false, onAct: null,
    slow: {}, claims: [], claimResult: null, info: o.info || null };

  var els = { app: new El('root'), sheet: new El('sheet'), peek: new El('peek'), toast: new El('toast') };
  globalThis.document = {
    visibilityState: 'visible', body: new El('body'), activeElement: null,
    getElementById: function (id) { return els[id] || null; },
    createElement: function () { return new El('app'); },
    querySelector: function () { return null; },
    addEventListener: function (t, fn) { (docL[t] = docL[t] || []).push(fn); }
  };
  globalThis.window = globalThis;
  globalThis.addEventListener = function (t, fn) { (winL[t] = winL[t] || []).push(fn); };
  globalThis.location = { search: o.search || '', pathname: '/', origin: 'http://test', hostname: 'test' };
  globalThis.history = { replaceState: function () {} };
  globalThis.localStorage = { getItem: function (k) { return k in store ? store[k] : null; }, setItem: function (k, v) { store[k] = String(v); } };
  globalThis.navigator = {};
  globalThis.FX = { bgm: { muted: false, want: function () {}, unlock: function () {}, toggle: function () {} } };
  globalThis.URLSearchParams = function (s) {
    var m = {};
    String(s || '').replace(/^\?/, '').split('&').forEach(function (kv) { if (kv) { var p = kv.split('='); m[p[0]] = decodeURIComponent(p[1] || ''); } });
    this.get = function (k) { return k in m ? m[k] : null; };
  };
  var blobs = 0;
  globalThis.Blob = function (parts) { this.size = parts && parts[0] && parts[0].byteLength || 0; };
  globalThis.URL = { createObjectURL: function (b) { return b.size ? 'blob:wav-' + b.size + '-' + (++blobs) : 'blob:clip:' + b.from; } };
  globalThis.Image = function () {};
  globalThis.EventSource = FakeES;
  globalThis.Audio = FakeAudio;
  globalThis.fetch = function (url, opts) {
    opts = opts || {};
    var body = opts.body ? JSON.parse(opts.body) : null;
    fetchLog.push({ url: url, path: url.split('?')[0], method: opts.method || 'GET', body: body, at: NOW });
    if (SERVER.down) return Promise.reject(new Error('net'));
    var r = route(url.split('?')[0], body);                 // 答复在发出请求的那一刻就定了
    var resp = {
      ok: r.status >= 200 && r.status < 300, status: r.status,
      json: function () { return Promise.resolve(JSON.parse(JSON.stringify(r.json))); },
      blob: function () { return Promise.resolve({ size: 0, from: url }); }
    };
    var slow = SERVER.slow[url.split('?')[0]];
    if (!slow) return Promise.resolve(resp);
    return new Promise(function (ok) { setTimeout(function () { ok(resp); }, slow); });   // 慢网络：过一会儿才回来
  };
}

function route(path, body) {
  function ok(j) { return { status: 200, json: j }; }
  if (path === '/api/info') return ok(SERVER.info || { lan: null, presets: [], roles: [] });
  if (path === '/healthz') return ok({});
  if (path === 'audio/manifest.json') return ok(SERVER.manifest);
  if (/^audio\//.test(path)) return SERVER.badAudio ? { status: 404, json: {} } : ok({});
  if (path === '/api/join' || path === '/api/create') return SERVER.join ? ok(SERVER.join) : { status: 404, json: { error: '房间不存在' } };
  if (path === '/api/beat') return { status: SERVER.beatStatus, json: SERVER.beatStatus === 200 ? { ok: true } : { error: 'x' } };
  if (path === '/api/view') return SERVER.view ? ok(SERVER.view) : { status: 404, json: { error: 'x' } };
  if (path === '/api/claim') {
    SERVER.claims.push(body);
    if (body.cancel) return ok({ rid: body.rid, state: 'no' });
    if (body.rid) return ok(SERVER.claimResult || { rid: body.rid, state: 'wait' });
    return ok({ rid: 'r9', state: 'wait' });
  }
  if (path === '/api/act') {
    acts.push({ type: body.type, data: body.data, code: body.code, at: NOW });
    if (SERVER.onAct) SERVER.onAct(body);
    return ok({ ok: true });
  }
  return { status: 404, json: {} };
}

var CRED = { code: '1111', pid: 'p1', token: 't1', name: '房主' };

// 启动页面。默认是「之前进过 1111 房间，现在重新打开页面」
function boot(o) {
  o = o || {};
  if (!('saved' in o)) o.saved = CRED;
  reset(o);
  load('public/app.js');
  drain();
}

// ---------------------------------------------------------------- 测试里用的小动作

function es() { return ES.list[ES.list.length - 1]; }
function push(v) { var e = es(); if (e.closed) throw new Error('这条连接已经关了'); e.onmessage({ data: JSON.stringify(v) }); drain(); }
function ping() { es().listeners.ping({}); drain(); }
function fire(type, ev) { ev = ev || {}; ev.type = type; (docL[type] || []).slice().forEach(function (fn) { fn(ev); }); drain(); }
function fireWin(type) { (winL[type] || []).slice().forEach(function (fn) { fn({}); }); drain(); }
function btn(act, data, text) {
  var d = act ? { act: act } : {};
  for (var k in (data || {})) d[k] = data[k];
  var el = { dataset: d, disabled: false, textContent: text || act };
  el.getAttribute = function (k) { return k.indexOf('data-') === 0 && d[k.slice(5)] != null ? String(d[k.slice(5)]) : null; };
  el.closest = function (sel) {
    if (sel === '[data-act]') return d.act ? el : null;
    if (sel === '[data-hold]') return d.hold ? el : null;
    return d.act || d.hold ? el : null;                    // '[data-act], [data-hold]'
  };
  return el;
}
function tap(el) { fire('pointerdown', { target: el }); fire('pointerup', { target: el }); fire('click', { target: el }); }
function tapBlank() { tap({ closest: function () { return null; } }); }      // 点一下空白处：浏览器从此允许出声
function seen(text) { return RENDER.app.indexOf(text) >= 0; }
function count(path, since) { return fetchLog.filter(function (f) { return f.path === path && f.at >= (since || 0); }).length; }
function acks(code) { return acts.filter(function (a) { return a.type === 'ack' && (!code || a.code === code); }); }
function playedClips() { return AUD.calls.map(clipOf).filter(Boolean); }
function el0() { return AUD.list[0]; }

function view(o) {
  var v = {
    code: '1111', phase: 'lobby', n: 3, config: { roles: {}, sheriff: false, witch_self_save: 'never', win: 'side' },
    you: { id: 'p1', name: '房主', seat: 1, host: true }, host_seat: 1, host_name: '房主', host_online: true, stalled: false,
    seats: [1, 2, 3].map(function (s) { return { seat: s, name: 'P' + s, taken: true, online: true, host: s === 1, alive: true, can_vote: true, shown: null, sheriff: false }; }),
    cues: [], err: null, standing: 0
  };
  for (var k in (o || {})) v[k] = o[k];
  if (!v.you.host) delete v.cues;
  return v;
}
function night(o) {
  var v = view({ phase: 'night', night_no: 1, badge: 'off', me: { role: 'guard', alive: true, team: 'good', notes: [] }, night: { prompt: null } });
  for (var k in (o || {})) v[k] = o[k];
  if (!v.you.host) delete v.cues;
  return v;
}
function cue(id, clips) { return { id: id, clips: clips || ['a'], text: '第' + id + '句' }; }
var GUARD = { type: 'guard', ui: 'pick', title: '守卫，选一名玩家守护', hint: '', targets: [1, 2, 3], verb: '守护', count: 1, skip: '空守', tone: 'gold', marks: {} };

// 一个会「收到回报就把那句话划掉、再把新画面推回来」的服务器
function liveServer(v) {
  SERVER.view = v;
  SERVER.onAct = function (b) {
    if (b.type !== 'ack' || b.code !== SERVER.view.code) return;
    SERVER.view.cues = (SERVER.view.cues || []).filter(function (c) { return c.id > b.data.id; });
    setTimeout(function () { if (!es().closed) push(SERVER.view); }, 20);
  };
}

// ---------------------------------------------------------------- 断言

var failures = 0, total = 0;
function test(name, fn) {
  total++;
  try { fn(); print('ok    ' + name); }
  catch (e) { failures++; print('FAIL  ' + name + '\n        ' + (e && e.message ? e.message : e) + (e && e.stack ? '\n        ' + e.stack.split('\n').slice(0, 3).join(' <- ') : '')); }
}
function ok(c, msg) { if (!c) throw new Error(msg || '条件不成立'); }
function eq(a, b, msg) { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error((msg ? msg + '：' : '') + '应该是 ' + JSON.stringify(b) + '，实际是 ' + JSON.stringify(a)); }

// ================================================================ 进房间和画面

test('重新打开页面：用保存的身份回到房间，画面来自长连接', function () {
  boot();
  eq(count('/api/join'), 1);
  eq(ES.list.length, 1);
  ok(es().url.indexOf('hb=1') > 0 && es().url.indexOf('pid=p1') > 0, '连接地址：' + es().url);
  push(view());
  ok(seen('1111') && seen('发牌'), '应该看到大厅');
});

test('房间不存在了：回到首页并提示', function () {
  boot({ join: null });                              // 服务器重启过，房间没了
  eq(ES.list.length, 0);
  ok(seen('创建房间'), '应该回到首页');
  eq(JSON.parse(store.lrs), { name: '房主' }, '保存的身份要清掉，只留名字');
});

test('不是房主：看得到「播报停了」并可以接手；房主自己看到的是「点一下这里继续」', function () {
  boot();
  push(view({ you: { id: 'p1', name: '乙', seat: 2, host: false }, stalled: true }));
  ok(seen('播报停了') && seen('data-act="take-host"'), '别人应该看到接手按钮');
  boot();
  tapBlank();
  push(view({ stalled: true, cues: [cue(1)] }));
  ok(seen('播报停了，点一下这里继续'), '房主应该看到提示');
  ok(!seen('data-act="take-host"'));
});

// ================================================================ 连接

test('心跳：听到一次回应一次；一直有心跳就不重连', function () {
  boot();
  push(view());
  var t0 = NOW;
  for (var i = 0; i < 8; i++) { advance(5000); ping(); }
  eq(ES.list.length, 1, '连接数');
  ok(count('/api/beat', t0) >= 7 && count('/api/beat', t0) <= 9, '回应次数 ' + count('/api/beat', t0));
  ok(!seen('连接断开了'));
});

test('连接假活着：12 秒什么都听不到，自己换一条连接', function () {
  boot();
  liveServer(view());
  push(SERVER.view);
  advance(5000); ping();
  advance(11000);
  eq(ES.list.length, 1, '还没到 12 秒');
  advance(1500);
  eq(ES.list.length, 2, '该换连接了');
  ok(ES.list[0].closed, '旧连接要关掉');
  ok(seen('连接断开了'), '期间提示正在重连');
  push(SERVER.view);
  ok(!seen('连接断开了'), '连上以后提示消失');
});

test('从后台回来：连接可疑就立刻重连，不等定时器', function () {
  boot();
  push(view());
  advance(5000); ping();
  NOW += 90000;                                      // 页面被系统冻住一分半钟：这期间定时器一个都不会跑
  fire('visibilitychange');
  eq(ES.list.length, 2);
  ok(ES.list[0].closed);
});

test('换了网络：直接换一条新连接', function () {
  boot();
  push(view());
  advance(1000);
  fireWin('online');
  eq(ES.list.length, 2);
});

test('房主抽到守卫，「守卫请睁眼」播完但推送漏了：两三秒后自己取回守卫界面', function () {
  boot();
  tapBlank();
  var v = night({ cues: [cue(7)] });
  SERVER.view = v;
  SERVER.onAct = function (b) {                      // 服务器收到「播完了」，往下走；但这条连接已经哑了，新画面推不到
    if (b.type === 'ack') SERVER.view = night({ night: { prompt: GUARD }, cues: [] });
  };
  push(v);
  ok(seen('天黑请闭眼'));
  advance(1100);
  eq(acks().length, 1, '播完要回报');
  ok(seen('天黑请闭眼') && !seen('守卫，选一名玩家守护'), '这时画面还是旧的');
  advance(2600);
  ok(seen('守卫，选一名玩家守护'), '应该已经自己取回了守卫的操作界面');
  eq(ES.list.length, 2, '并且换了一条连接');
});

test('长连接根本不通：4 秒先取到画面，8 秒改成定时取，之后操作照常', function () {
  boot();
  SERVER.view = view();
  advance(4100);
  ok(seen('1111'), '4 秒后应该已经看到房间');
  ok(!seen('连接断开了'), '取得到画面就不该提示断线');
  advance(4100);
  var t0 = NOW, n = ES.list.length;
  ok(es().closed, '不再守着哑掉的长连接');
  advance(6000);
  ok(count('/api/view', t0) >= 3 && count('/api/view', t0) <= 5, '6 秒里应该取 4 次左右，实际 ' + count('/api/view', t0));
  eq(ES.list.length, n, '轮询期间不再反复开长连接');
  SERVER.view = view({ err: '板子不能开局' });
  advance(1600);
  ok(seen('板子不能开局'), '服务器那边变了，下一轮就能看到');
});

test('轮询时连点几下：仍然只有一条轮询链，而且点完马上取一次', function () {
  boot();
  SERVER.view = view();
  advance(8300);
  ok(es().closed, '已经在轮询');
  var t0 = NOW;
  for (var i = 0; i < 6; i++) tap(btn('test', {}, '试音'));
  eq(acts.filter(function (a) { return a.type === 'test'; }).length, 6);
  ok(count('/api/view', t0) >= 1, '点完应该马上取一次');
  advance(10);
  var t1 = NOW;
  advance(15000);
  ok(count('/api/view', t1) <= 11, '15 秒最多取 10 次左右，实际 ' + count('/api/view', t1));
});

test('轮询两分钟后再试一次长连接，通了就不再轮询', function () {
  boot();
  SERVER.view = view();
  advance(8300);
  var n = ES.list.length;
  advance(121000);
  eq(ES.list.length, n + 1, '该再试一次长连接了');
  push(SERVER.view);
  var t0 = NOW;
  for (var i = 0; i < 4; i++) { advance(5000); ping(); }
  eq(count('/api/view', t0), 0, '长连接通了就不该再轮询');
});

test('身份被别人认领走了（心跳回 403）：重新确认身份', function () {
  boot();
  push(view());
  var n = count('/api/join');
  SERVER.beatStatus = 403;
  advance(5000); ping();
  eq(count('/api/join'), n + 1);
});

test('服务器停了一阵又回来：自己恢复，不用刷新', function () {
  boot();
  liveServer(view());
  push(SERVER.view);
  SERVER.down = true;
  advance(40000);
  ok(seen('连接断开了'), '断着的时候要有提示');
  SERVER.down = false;
  advance(8000);
  if (!es().closed) push(SERVER.view);               // 新开的长连接通了（如果当时正在轮询，轮询自己会取到）
  advance(3000);
  ok(!seen('连接断开了'), '恢复以后提示消失');
  ok(seen('1111'));
});

// ================================================================ 语音

test('房主：一句一句播，每句播完才回报', function () {
  boot();
  tapBlank();
  liveServer(view({ cues: [cue(1), cue(2, ['b', 'c'])] }));
  push(SERVER.view);
  ok(seen('播报中'));
  advance(900);
  eq(acks().length, 0, '第一句还没播完');
  advance(300);
  eq(acks().map(function (a) { return a.data.id; }), [1]);
  advance(1500);
  eq(acks().length, 1, '第二句有两段，还没播完');
  advance(600);
  eq(acks().map(function (a) { return a.data.id; }), [1, 2]);
  eq(playedClips(), ['a', 'b', 'c']);
});

test('换了房间：新房间里编号小的语音照样播出来，播完才回报', function () {
  boot();
  tapBlank();
  liveServer(view({ cues: [cue(1), cue(2), cue(3)] }));
  push(SERVER.view);
  advance(4000);
  eq(acks('1111').map(function (a) { return a.data.id; }), [1, 2, 3], '第一个房间播了三句');
  tap(btn('leave'));
  tap(btn('confirm-ok'));
  ok(seen('创建房间'), '回到首页');
  fire('input', { target: { id: 'in-name', value: '房主' } });
  SERVER.join = { code: '2222', pid: 'p9', token: 't9', name: '房主' };
  SERVER.view = null; SERVER.onAct = null;
  tap(btn('create'));
  ok(es().url.indexOf('code=2222') > 0, '连到新房间');
  var before = AUD.calls.length;
  liveServer(view({ code: '2222', cues: [cue(1)] }));
  push(SERVER.view);
  advance(500);
  eq(acks('2222').length, 0, '新房间的第 1 句不能没播就回报');
  ok(AUD.calls.slice(before).map(clipOf).indexOf('a') >= 0, '应该真的在播');
  advance(700);
  eq(acks('2222').map(function (a) { return a.data.id; }), [1]);
});

test('播到一半离开房间：这一句不回报，声音停掉，也不会在首页又播一遍', function () {
  boot({ manifest: { a: 5 } });
  tapBlank();
  liveServer(view({ cues: [cue(1)] }));
  push(SERVER.view);
  advance(1000);
  tap(btn('leave'));
  var n = AUD.calls.length;
  tap(btn('confirm-ok'));
  advance(8000);
  eq(acks().length, 0);
  ok(el0().paused, '声音应该停了');
  eq(AUD.calls.slice(n).map(clipOf).filter(Boolean), [], '离开以后不能再出声');
});

test('回报丢了：补发，而且不会把同一句再播一遍', function () {
  boot();
  tapBlank();
  var v = view({ cues: [cue(1)] });
  SERVER.view = v;                                   // 这个服务器收到回报也不理：那句话一直挂在队首
  push(v);
  advance(1200);
  eq(acks().length, 1);
  push(v);                                           // 画面又来了一次，那句话还在
  advance(4000);
  ok(acks().length >= 3, '应该一直补发，实际 ' + acks().length);
  eq(playedClips(), ['a'], '不能重播');
});

test('预先下好的语音文件是坏的：改从网络直接取，播完才回报', function () {
  boot();
  tapBlank();
  liveServer(view());
  push(SERVER.view);                                 // 当上房主以后开始预下载
  advance(200);
  AUD.bad = function (src) { return src.indexOf('blob:clip') === 0; };
  SERVER.view.cues = [cue(1)];
  push(SERVER.view);
  ok(el0().src.indexOf('blob:clip') === 0, '先用的是预先下好的那份：' + el0().src);
  advance(1300);
  eq(acks().length, 0, '第一次失败后正在重试');
  advance(500);
  eq(acks().length, 1);
  ok(AUD.calls.indexOf('audio/a.m4a') >= 0, '应该改成直接从网络播');
});

test('语音播不出来：先不回报，请房主点一下；点了以后又失败一轮才跳过，游戏不会卡死', function () {
  boot();
  tapBlank();
  AUD.bad = function (src) { return /audio\/a\.m4a/.test(src); };
  liveServer(view({ cues: [cue(1), cue(2, ['b'])] }));
  push(SERVER.view);
  advance(6000);
  eq(acks().length, 0, '没播出来就不能当成播完了');
  eq(AUD.calls.filter(function (s) { return /audio\/a\.m4a/.test(s); }).length, 3, '先试三次');
  ok(seen('点一下这里，开启语音播报'), '房主应该看到提示');
  tapBlank();
  advance(6000);
  eq(acks().map(function (a) { return a.data.id; }), [1, 2], '又失败一轮：多半是文件坏了，跳过它，后面的照常播');
  ok(document.getElementById('toast').textContent.indexOf('跳过') >= 0, '告诉房主跳过了一句');
  ok(playedClips().indexOf('b') >= 0);
});

test('来电打断（播放没反应也不报错）：不回报；电话挂了点一下就整句重播', function () {
  boot();
  tapBlank();
  AUD.interrupted = true;
  liveServer(view({ cues: [cue(1)] }));
  push(SERVER.view);
  advance(40000);
  eq(acks().length, 0, '一个字都没播出来，不能回报');
  ok(seen('点一下这里，开启语音播报'));
  AUD.interrupted = false;
  tapBlank();
  advance(1500);
  eq(acks().length, 1);
});

test('页面被冻住好几分钟：醒过来以后接着播完才回报，而不是直接算播完', function () {
  boot({ manifest: { a: 4 } });
  tapBlank();
  liveServer(view({ cues: [cue(1)] }));
  push(SERVER.view);
  advance(1000);                                     // 播了一秒
  el0().paused = true;                               // 锁屏：声音停了，页面也冻住了
  NOW += 180000;                                     // 三分钟里定时器一个都没跑
  advance(1000);
  eq(acks().length, 0, '醒过来不能直接算播完');
  advance(7000);
  eq(acks().length, 1, '接着播完剩下的三秒以后才回报');
});

test('断网时加载失败不算失败：一直等到网回来，接着播', function () {
  boot();
  SERVER.badAudio = true;                            // 预先下载也失败了：手上没有现成的文件
  tapBlank();
  liveServer(view());
  push(SERVER.view);
  advance(500);
  navigator.onLine = false;
  AUD.bad = function () { return true; };
  SERVER.view.cues = [cue(1)];
  push(SERVER.view);
  advance(30000);
  eq(acks().length, 0, '断网期间不能跳过');
  ok(!seen('点一下这里，开启语音播报'), '断网不是房主的问题，不用提示他点');
  navigator.onLine = true;
  AUD.bad = function () { return false; };
  advance(3500);
  eq(acks().length, 1, '网回来就接着播');
});

test('播到一半被别人接手播报：这台手机马上停下，不会接着把旧的话说完', function () {
  boot({ manifest: { a: 5 } });
  tapBlank();
  liveServer(view({ cues: [cue(1)] }));
  push(SERVER.view);
  advance(1000);
  ok(!el0().paused, '正在播');
  push(view({ you: { id: 'p1', name: '房主', seat: 1, host: false } }));
  ok(el0().paused, '应该马上停');
  var n = AUD.calls.length;
  advance(10000);
  eq(AUD.calls.length, n, '之后不再出声');
  eq(acks().length, 0);
});

test('播到一半被系统暂停（来电、别的 App 抢了声音）：自己接着播，播完才回报', function () {
  boot({ manifest: { a: 4 } });
  tapBlank();
  liveServer(view({ cues: [cue(1)] }));
  push(SERVER.view);
  advance(1000);
  el0().paused = true;                               // 系统把声音停了，页面不会收到任何通知
  advance(1500);
  eq(acks().length, 0, '不能当成播完了');
  advance(6000);
  eq(acks().length, 1, '接着播完以后回报');
  ok(acks()[0].at - 1e12 >= 5000, '总共应该花了 5 秒以上，实际 ' + (acks()[0].at - 1e12));
});

test('浏览器不让出声：不回报，提示房主点一下；点了以后整句重播', function () {
  boot();
  tapBlank();
  AUD.blocked = true;
  liveServer(view({ cues: [cue(1)] }));
  push(SERVER.view);
  advance(8000);
  eq(acks().length, 0, '没出声就不能回报');
  ok(seen('点一下这里，开启语音播报'));
  AUD.blocked = false;
  tapBlank();
  advance(1200);
  eq(acks().length, 1);
});

test('不是房主的手机不出声；接手播报以后从没播完的那一句开始', function () {
  boot();
  tapBlank();
  push(view({ you: { id: 'p1', name: '乙', seat: 2, host: false } }));
  advance(3000);
  eq(playedClips(), []);
  liveServer(view({ you: { id: 'p1', name: '乙', seat: 2, host: true }, cues: [cue(41), cue(42)] }));
  push(SERVER.view);
  advance(2500);
  eq(acks().map(function (a) { return a.data.id; }), [41, 42]);
});

test('静音保活：房主手机没话要播时循环放静音，来了话就让位，播完再接上', function () {
  boot();
  tapBlank();
  liveServer(view());
  push(SERVER.view);
  advance(500);
  ok(el0().loop && !el0().paused && /^blob:wav-40044/.test(el0().src), '空闲时应该在循环放静音：' + el0().src);
  SERVER.view.cues = [cue(1)];
  push(SERVER.view);
  ok(!el0().loop && clipOf(el0().src) === 'a', '有话要播时让位');
  advance(1500);
  eq(acks().length, 1);
  ok(el0().loop && !el0().paused, '播完接着放静音');
  advance(30000);
  eq(acks().length, 1, '静音不会被当成语音回报');
});

test('不是房主的手机不放静音（不打断他手机上别的声音）', function () {
  boot();
  tapBlank();
  push(view({ you: { id: 'p1', name: '乙', seat: 2, host: false } }));
  advance(3000);
  ok(!el0().loop && el0().paused, '应该是安静的');
});

test('?ka=0 可以关掉静音保活', function () {
  boot({ search: '?ka=0' });
  tapBlank();
  liveServer(view());
  push(SERVER.view);
  advance(3000);
  ok(!el0().loop, '不应该循环');
});

// ================================================================ 点击

test('按下以后按钮变成了别的：这一下不算；正常的点击照常', function () {
  boot();
  push(view({ phase: 'deal', night_no: 0, badge: 'off', me: { role: 'guard', alive: true, team: 'good', notes: [] }, deal: { seen: false, count: 2, ready: [2, 3] } }));
  var b = btn('seen', {}, '我记住了');
  fire('pointerdown', { target: b });
  b.dataset.act = 'start-night'; b.textContent = '天黑请闭眼';       // 手指还没抬起来，画面更新了
  fire('pointerup', { target: b });
  fire('click', { target: b });
  eq(acts.filter(function (a) { return a.type === 'start_night'; }).length, 0, '不能替用户开始夜晚');
  tap(b);
  eq(acts.filter(function (a) { return a.type === 'start_night'; }).length, 1, '看清楚以后再点就算数');
});

test('座位牌上的字变了（比如别人掉线）不影响点击', function () {
  boot();
  push(view());
  var b = btn('sit', { seat: '2' }, '2 P2');
  fire('pointerdown', { target: b });
  b.textContent = '2 P2 掉线';
  fire('pointerup', { target: b });
  fire('click', { target: b });
  eq(acts.filter(function (a) { return a.type === 'sit'; }).length, 1);
});

// ================================================================ 第二轮审查：防误触、确认框、认领座位、连接

test('手机上补发的 mousedown 不会让防误触失效', function () {
  boot();
  push(view({ phase: 'deal', night_no: 0, badge: 'off', me: { role: 'guard', alive: true, team: 'good', notes: [] }, deal: { seen: true, count: 2, ready: [1, 2] } }));
  function straddle(downType) {
    var b = btn('seen', {}, '我记住了');
    fire(downType, { target: b });
    b.dataset.act = 'start-night'; b.textContent = '天黑请闭眼';     // 手指还按着，画面更新了
    fire('touchend', { target: b });
    fire('mousedown', { target: b });                               // 手指抬起后浏览器补发的，紧接着就是 click
    fire('click', { target: b });
  }
  straddle('touchstart');                                           // 不支持 pointer 事件的老手机
  globalThis.PointerEvent = function () {};
  straddle('pointerdown');
  delete globalThis.PointerEvent;
  eq(acts.filter(function (a) { return a.type === 'start_night'; }).length, 0, '不能替房主宣布天黑');
});

test('按住看身份时狼人界面刚好出来：松手不会变成「空刀」', function () {
  boot();
  push(night({ me: { role: 'wolf', alive: true, team: 'wolf', notes: [] } }));
  var b = btn(null, { hold: '1' }, '按住看身份');
  fire('pointerdown', { target: b });
  delete b.dataset.hold; b.dataset.act = 'wolf-none'; b.textContent = '空刀';
  fire('pointerup', { target: b });
  fire('click', { target: b });
  eq(acts.filter(function (a) { return a.type === 'wolf_pick'; }).length, 0);
});

test('跳过：只跳过点开时的那个环节；换了环节确认框自动关掉；没有可跳的环节就不显示', function () {
  boot();
  push(night({ skip_key: '1-0' }));
  tap(btn('menu'));
  ok(RENDER.sheet.indexOf('跳过当前环节') >= 0);
  tap(btn('skip'));
  ok(RENDER.sheet.indexOf('跳过当前环节？') >= 0, '弹出确认框');
  push(night({ skip_key: '1-1' }));                  // 守卫自己做完了，已经轮到狼人
  ok(RENDER.sheet.indexOf('跳过当前环节？') < 0, '确认框应该关掉');
  tap(btn('menu'));
  tap(btn('skip'));
  tap(btn('confirm-ok'));
  eq(acts.filter(function (a) { return a.type === 'skip'; })[0].data, { key: '1-1' });
  push(night({}));                                   // 正在播报：没有可以跳过的环节
  tap(btn('menu'));
  ok(RENDER.sheet.indexOf('跳过当前环节') < 0);
});

test('请离：只请确认框里写的那个人', function () {
  boot();
  push(view());
  tap(btn('kick', { seat: '2' }));
  tap(btn('confirm-ok'));
  eq(acts.filter(function (a) { return a.type === 'kick'; })[0].data, { seat: 2, name: 'P2' });
});

function settleView(waiting) {
  var v = night({});
  v.phase = 'day';
  delete v.night;
  v.day = { no: 1, stage: 'settle', feed: [], night_deaths: [], last_words: [], speak: null, results: [], pk: [], sheriff: 0,
            settle: { waiting: waiting, done: [], mine: null, targets: [1, 2, 3] } };
  return v;
}

test('出局确认「不等了」：只处理当时屏幕上那几个人；要等的人变了确认框自动关掉', function () {
  boot();
  push(settleView([3]));
  tap(btn('settle-close'));
  ok(RENDER.sheet.indexOf('不等了？') >= 0);
  push(settleView([2]));                             // 3 号刚开枪带走了 2 号
  ok(RENDER.sheet.indexOf('不等了？') < 0, '确认框应该关掉');
  tap(btn('settle-close'));
  tap(btn('confirm-ok'));
  eq(acts.filter(function (a) { return a.type === 'settle_close'; })[0].data, { seats: [2] });
});

test('没入座的房主：大家看完身份以后照样能宣布天黑', function () {
  boot();
  push(view({ phase: 'deal', night_no: 0, badge: 'off', you: { id: 'p1', name: '播报', seat: 0, host: true }, deal: { seen: false, count: 3, ready: [1, 2, 3] } }));
  ok(seen('本局旁观'));
  ok(seen('data-act="start-night"') && seen('天黑请闭眼'), '应该有「天黑请闭眼」按钮');
});

test('换手机回到座位：先等房主同意，同意了才进得去；可以取消', function () {
  boot({ join: { claim: [{ seat: 2, name: 'P2' }], code: '1111' } });     // 这台手机上的身份已经作废
  ok(seen('2 号'), '应该看到可以认领的座位');
  tap(btn('claim', { seat: '2' }));
  ok(seen('等房主同意'), '提交以后等房主同意');
  tap(btn('claim-cancel'));
  ok(!seen('等房主同意'), '取消以后回到座位列表');
  ok(SERVER.claims.some(function (c) { return c.cancel && c.rid === 'r9'; }), '并且告诉服务器撤回申请');
  tap(btn('claim', { seat: '2' }));
  advance(4100);
  ok(seen('等房主同意'));
  eq(ES.list.length, 0, '房主同意之前进不去');
  SERVER.claimResult = { code: '1111', pid: 'p2', token: 'new', name: 'P2' };
  advance(2100);
  eq(ES.list.length, 1, '同意以后进房间');
  ok(es().url.indexOf('pid=p2') > 0 && es().url.indexOf('token=new') > 0);
});

test('房主：有人申请换手机回到座位时出现横幅，点同意还要再确认一次', function () {
  boot();
  push(night({ claims: [{ rid: 'r1', seat: 2, name: '新手机' }] }));
  ok(seen('有人要用新手机回到 2 号（新手机）'));
  tap(btn('claim-ok', { rid: 'r1', n: '2' }, '同意'));
  eq(acts.filter(function (a) { return a.type === 'claim_ok'; }).length, 0, '先弹确认框');
  tap(btn('confirm-ok'));
  eq(acts.filter(function (a) { return a.type === 'claim_ok'; })[0].data, { rid: 'r1' });
});

test('长连接每次都被直接拒绝：两次以后改成定时取画面，不再一秒一次地重连', function () {
  boot();
  SERVER.view = view();
  push(SERVER.view);
  function refuse() { var e = es(); e.readyState = 2; e.onerror(); drain(); }
  refuse();
  advance(1300);
  eq(ES.list.length, 2, '先确认身份，再试一次');
  refuse();
  advance(1300);
  var n = ES.list.length, t0 = NOW;
  advance(10000);
  eq(ES.list.length, n, '不再反复开长连接');
  ok(count('/api/view', t0) >= 5, '改成定时取画面了：' + count('/api/view', t0));
  ok(count('/api/join', t0) <= 1, '也不再反复确认身份');
  ok(!seen('连接断开了'), '取得到画面就不该提示断线');
});

test('身份确认的答复来晚了：已经换了房间，就不能再被拉回旧房间', function () {
  boot();
  push(view());
  SERVER.slow['/api/join'] = 3000;
  var e = es(); e.readyState = 2; e.onerror(); drain();         // 长连接被拒绝，1.2 秒后去确认身份，答复 3 秒后才回来
  advance(1500);
  tap(btn('leave'));
  tap(btn('confirm-ok'));
  fire('input', { target: { id: 'in-name', value: '房主' } });
  SERVER.join = { code: '2222', pid: 'p9', token: 't9', name: '房主' };
  tap(btn('create'));
  ok(es().url.indexOf('code=2222') > 0);
  advance(4000);                                                 // 旧的答复这时才到
  ok(es().url.indexOf('code=2222') > 0, '还在新房间：' + es().url);
  eq(JSON.parse(store.lrs).code, '2222');
});

// ================================================================ 第三轮审查

test('认领座位时手快点了两下：只发一个申请', function () {
  boot({ join: { claim: [{ seat: 2, name: 'P2' }], code: '1111' } });
  SERVER.slow['/api/claim'] = 300;
  tap(btn('claim', { seat: '2' }));
  advance(150);
  tap(btn('claim', { seat: '2' }));                  // 第一个申请还没回来，又点了一下
  advance(400);
  eq(SERVER.claims.filter(function (c) { return !c.rid; }).length, 1, '申请的次数');
  ok(seen('等房主同意'));
});

test('别的出局玩家先确认了：猎人已经选好的目标和打开的确认框都还在', function () {
  boot();
  function hunter(waiting) {
    var v = settleView(waiting);
    v.me = { role: 'hunter', alive: false, team: 'good', notes: [] };
    v.day.settle.mine = { can_shoot: true, badge: false };
    return v;
  }
  push(hunter([1, 3]));
  tap(btn('pick', { seat: '2' }));
  tap(btn('shot-ok'));
  ok(RENDER.sheet.indexOf('带走 2 号？') >= 0);
  push(hunter([1]));                                 // 3 号在自己手机上点了确认
  ok(RENDER.sheet.indexOf('带走 2 号？') >= 0, '确认框应该还在');
  tap(btn('confirm-ok'));
  eq(acts.filter(function (a) { return a.type === 'settle'; })[0].data, { target: 2 });
});

test('夜里换环节时，房主打开的「结束本局」确认框不会自己关掉', function () {
  boot();
  push(night({}));
  tap(btn('menu'));
  tap(btn('abort'));
  ok(RENDER.sheet.indexOf('结束本局？') >= 0);
  push(night({ skip_key: '1-0' }));                  // 播报完了，轮到守卫行动
  ok(RENDER.sheet.indexOf('结束本局？') >= 0, '轮到下一个角色时还在');
  push(night({}));                                   // 守卫做完了，又在播报
  ok(RENDER.sheet.indexOf('结束本局？') >= 0, '又开始播报时还在');
  tap(btn('confirm-ok'));
  eq(acts.filter(function (a) { return a.type === 'abort'; }).length, 1);
});

test('按下的按钮被整块重画了：手指下面还是同一个按钮就算数，换成了别的按钮就不算', function () {
  boot();
  push(view());
  var a = btn('sit', { seat: '2' }, '2 P2');
  fire('pointerdown', { target: a });
  a.isConnected = false;                             // 整块重画（比如改板子时连点「+」）：按下的那个节点没了
  var b = btn('sit', { seat: '2' }, '2 P2');         // 原地是一模一样的新按钮
  fire('pointerup', { target: b });
  fire('click', { target: b });
  eq(acts.filter(function (x) { return x.type === 'sit'; }).length, 1, '一模一样的按钮应该算数');
  var c = btn('sit', { seat: '2' }, '2 P2');
  fire('pointerdown', { target: c });
  c.isConnected = false;
  var d = btn('sit', { seat: '3' }, '3 P3');         // 重画以后手指下面换成了别的座位
  fire('pointerup', { target: d });
  fire('click', { target: d });
  eq(acts.filter(function (x) { return x.type === 'sit'; }).length, 1, '换成别的按钮不应该算数');
});

// ================================================================ 混血儿

var INFO = { lan: null, presets: [], roles: [
  { id: 'wolf', name: '狼人', team: 'wolf', kind: 'wolf', desc: '' },
  { id: 'villager', name: '村民', team: 'good', kind: 'villager', desc: '' },
  { id: 'seer', name: '预言家', team: 'good', kind: 'god', desc: '' },
  { id: 'mixed', name: '混血儿', team: 'good', kind: 'none', desc: '第一夜选一名其他玩家做榜样' }
] };
var MIXED = { type: 'mixed', ui: 'pick', title: '混血儿，选一名玩家做榜样', hint: '你和他同一阵营、同输同赢，但看不到他的身份。',
  targets: [2, 3], verb: '跟随', count: 1, skip: null, tone: 'gold', marks: {} };

test('混血儿第一夜选榜样：没有「跳过」，按钮写「跟随 2 号」，发出去的就是 2 号', function () {
  boot({ info: INFO });
  push(night({ me: { role: 'mixed', alive: true, team: 'good', notes: [] }, night: { prompt: MIXED } }));
  ok(seen('混血儿，选一名玩家做榜样'));
  ok(seen('先选一名玩家'));
  ok(!seen('night-skip'), '必须选，不能跳过');
  tap(btn('pick', { seat: '2' }));
  ok(seen('跟随 2 号'));
  tap(btn('night-go'));
  eq(acts.filter(function (a) { return a.type === 'night'; }).map(function (a) { return a.data; }), [{ targets: [2] }]);
});

test('混血儿按住看身份：写「阵营跟随榜样」和榜样是几号，不写「好人阵营」；狼人照旧写狼人阵营', function () {
  boot({ info: INFO });
  push(night({ me: { role: 'mixed', alive: true, team: 'good', notes: ['你的榜样是 2号'] } }));
  var b = btn(null, { hold: '1' }, '按住看身份');
  fire('pointerdown', { target: b });
  ok(RENDER.peek.indexOf('阵营跟随榜样') >= 0, RENDER.peek);
  ok(RENDER.peek.indexOf('你的榜样是 2号') >= 0);
  ok(RENDER.peek.indexOf('好人阵营') < 0);
  fire('pointerup', { target: b });
  push(night({ me: { role: 'wolf', alive: true, team: 'wolf', notes: [] } }));
  fire('pointerdown', { target: b });
  ok(RENDER.peek.indexOf('狼人阵营') >= 0, RENDER.peek);
  fire('pointerup', { target: b });
});

test('改板子：混血儿单独一组「其他」，不算平民也不算神职；夜晚顺序里排第一', function () {
  boot({ info: INFO });
  push(view({ config: { roles: { wolf: 1, villager: 1, seer: 1, mixed: 1 }, sheriff: false, witch_self_save: 'never', win: 'side' }, n: 4 }));
  tap(btn('config'));
  var sh = RENDER.sheet;
  ok(sh.indexOf('平民<span>1 人</span>') >= 0, '平民只有村民');
  ok(sh.indexOf('神职<span>1 人</span>') >= 0, '神职只有预言家');
  ok(sh.indexOf('其他<span>1 人</span>') >= 0, sh);
  ok(sh.slice(sh.indexOf('其他<span>')).indexOf('混血儿') >= 0, '混血儿在「其他」这一组');
  ok(sh.slice(sh.indexOf('平民<span>'), sh.indexOf('其他<span>')).indexOf('混血儿') < 0, '不在平民和神职里');
  tap(btn('close'));
  tap(btn('menu'));
  ok(RENDER.sheet.indexOf('夜晚顺序：混血儿 → 狼人 → 预言家') >= 0, RENDER.sheet);
});

test('结束亮牌：混血儿写上跟的是几号，跟了狼就标成狼人那边，输赢跟着榜样', function () {
  boot({ info: INFO });
  var v = view({ phase: 'over', night_no: 2, badge: 'off', you: { id: 'p3', name: 'P3', seat: 3, host: false },
    me: { role: 'mixed', alive: true, team: 'good', notes: [] } });
  v.seats[0].shown = 'wolf'; v.seats[1].shown = 'villager'; v.seats[2].shown = 'mixed';
  v.over = { winner: 'good', log: ['混血儿 3号 的榜样是 1号，属于狼人阵营', '好人阵营获胜'], lovers: [], third: false, model: 1,
    camps: { 1: 'wolf', 2: 'good', 3: 'wolf' }, causes: {} };
  push(v);
  ok(seen('你是混血儿，输了'), RENDER.app);
  ok(seen('混血儿·跟1号'));
  eq(RENDER.app.split('wolfrole').length - 1, 2, '1 号狼人和跟狼的 3 号都标成狼人那边');
  ok(seen('混血儿 3号 的榜样是 1号，属于狼人阵营'));
  v.over.camps = { 1: 'wolf', 2: 'good', 3: 'good' };
  v.over.model = 2;
  push(v);
  ok(seen('你是混血儿，赢了'));
  eq(RENDER.app.split('wolfrole').length - 1, 1);
  v.over.model = 0;                                  // 房主跳过了他的环节：没有榜样
  push(v);
  ok(seen('你是混血儿，赢了'));
  ok(!seen('·跟'), '没有榜样就不写跟几号');
  v.over.model = 2; v.over.lovers = [2, 3];          // 被连成情侣：按情侣算，不写跟几号
  push(v);
  ok(seen('混血儿·情侣'), RENDER.app);
  ok(!seen('·跟'));
});

print('\n' + (total - failures) + ' / ' + total + ' 通过');
if (failures) quit(1);
