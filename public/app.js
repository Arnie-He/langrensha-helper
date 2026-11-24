/* 狼人杀面杀助手 —— 手机端
 *
 * 服务器把「这台手机现在该看到什么」整个推过来（V），这里只负责画出来、把点击发回去。
 * 房主的手机还多一件事：按顺序播放语音，每播完一条告诉服务器，服务器才会往下走。
 */
(function () {
  'use strict';

  var qs = new URLSearchParams(location.search);
  var DEV = qs.get('dev') || '';                 // ?dev=xx 让同一个浏览器能开多个身份，方便测试
  var KEY = 'lrs' + (DEV ? ':' + DEV : '');

  var app = document.getElementById('app');
  var sheetEl = document.getElementById('sheet');
  var peekEl = document.getElementById('peek');
  var toastEl = document.getElementById('toast');

  var saved = load();
  var cred = null;                               // {code, pid, token, name}
  var V = null;                                  // 服务器推来的当前画面数据
  var info = { lan: null, presets: [], roles: [] };
  var ROLE = {};                                 // 角色表，从服务器取
  var live = false;
  var ui = {
    name: saved.name || '', code: (qs.get('room') || '').replace(/\D/g, '').slice(0, 4),
    picks: [], mode: null, shot: null, sheet: null, peek: false, peeked: false, claim: null,
    ctx: '', busy: false
  };
  var fromLink = ui.code.length === 4;           // 是扫码/点链接进来的，默认动作是「加入」
  var lastHtml = '', lastSheet = '', lastPeek = '';

  // ------------------------------------------------------------ 小工具

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; }
  }
  function save(o) {
    try { localStorage.setItem(KEY, JSON.stringify(o)); } catch (e) { /* 无痕模式下存不了也能玩 */ }
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function nums(a) { return a.map(function (n) { return n + '号'; }).join('、'); }
  function seatOf(n) { return V.seats[n - 1] || {}; }
  function role(id) { return ROLE[id] || { name: id || '', team: 'good', kind: 'god', desc: '' }; }
  function has(arr, x) { return (arr || []).indexOf(x) >= 0; }
  // 角色头像（public/avatars/<角色>.svg）和界面小图（public/art/*.svg）都是 tools/sketch 画出来的手绘线稿
  function avSrc(id) { return 'avatars/' + id + '.svg'; }
  function art(name, cls) { return '<img class="art-' + (cls || name) + '" src="art/' + name + '.svg" alt="" draggable="false">'; }
  function roleIdByName(nm) {
    var hit = '';
    Object.keys(ROLE).forEach(function (id) { if (ROLE[id].name === nm) hit = id; });
    return hit;
  }
  function av(id, cls) {
    return id ? '<img class="av' + (cls ? ' ' + cls : '') + '" src="' + avSrc(id) + '" alt="" draggable="false">' : '';
  }
  // 大头像：镶在一枚圆牌里
  function medal(id) { return id ? '<span class="medal">' + av(id) + '</span>' : ''; }

  var toastT = null;
  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.hidden = false;
    clearTimeout(toastT);
    toastT = setTimeout(function () { toastEl.hidden = true; }, 2400);
  }

  function post(path, body) {
    return fetch(path, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok || j.error) {
          var e = new Error(j.error || '请求失败');
          e.status = r.status;
          throw e;
        }
        return j;
      });
    }, function () {
      throw new Error('网络不通，请稍后再试');
    });
  }

  function act(type, data, quiet) {
    if (!cred) return Promise.resolve(false);
    return post('/api/act', { code: cred.code, pid: cred.pid, token: cred.token, type: type, data: data || {} })
      .then(function () { return true; }, function (e) {
        if (!quiet) toast(e.message);
        return false;
      });
  }

  // ------------------------------------------------------------ 进房间 / 连接

  function setCred(j) {
    cred = { code: j.code, pid: j.pid, token: j.token, name: j.name };
    saved = cred;
    save(cred);
    ui.claim = null;
    var u = '?room=' + cred.code + (DEV ? '&dev=' + encodeURIComponent(DEV) : '');
    try { history.replaceState(null, '', u); } catch (e) { /* 不影响使用 */ }
    connect();
  }

  var es = null, retryT = null;
  function connect() {
    if (es) { es.close(); es = null; }
    if (!cred) return;
    es = new EventSource('/api/events?code=' + cred.code + '&pid=' + cred.pid + '&token=' + cred.token);
    es.onopen = function () { live = true; paint(); };
    es.onmessage = function (e) {
      live = true;
      V = JSON.parse(e.data);
      onView();
    };
    es.onerror = function () {
      live = false;
      paint();
      if (es && es.readyState === 2) {           // 服务器明确拒绝了：检查身份是否还有效
        es = null;
        clearTimeout(retryT);
        retryT = setTimeout(recheck, 1200);
      }
    };
  }

  function recheck() {
    if (!cred) return;
    post('/api/join', cred).then(function (j) {
      if (j.pid) setCred(j);
      else { leave(); ui.code = j.code || ''; ui.claim = j; paint(); }
    }, function (e) {
      if (e.status === 404) { leave(); toast('房间已经不存在了'); } else retryT = setTimeout(recheck, 2500);
    });
  }

  function leave() {
    if (es) { es.close(); es = null; }
    clearTimeout(retryT);
    cred = null; V = null; live = false;
    ui.sheet = null; ui.claim = null; ui.picks = []; ui.mode = null;
    save({ name: ui.name });
    try { history.replaceState(null, '', location.pathname + (DEV ? '?dev=' + encodeURIComponent(DEV) : '')); } catch (e) { /* ok */ }
    paint();
  }

  function wantName() {
    var n = (ui.name || '').trim();
    if (!n) { toast('先填一个昵称，让大家认得出你'); return null; }
    return n.slice(0, 8);
  }

  function doCreate() {
    var name = wantName();
    if (!name || ui.busy) return;
    ui.busy = true;
    post('/api/create', { name: name }).then(setCred, function (e) { toast(e.message); })
      .then(function () { ui.busy = false; });
  }

  function doJoin() {
    var name = wantName();
    if (!name || ui.busy) return;
    if (!/^\d{4}$/.test(ui.code)) { toast('房间号是 4 位数字'); return; }
    ui.busy = true;
    var old = saved.code === ui.code ? saved : {};
    post('/api/join', { code: ui.code, name: name, pid: old.pid, token: old.token }).then(function (j) {
      if (j.pid) setCred(j);
      else { ui.claim = j; paint(); }
    }, function (e) { toast(e.message); }).then(function () { ui.busy = false; });
  }

  function doClaim(seat) {
    post('/api/claim', { code: ui.claim.code, seat: seat, name: (ui.name || '').trim() })
      .then(setCred, function (e) { toast(e.message); });
  }

  // ------------------------------------------------------------ 语音播报（只有房主的手机会真的出声）

  var Speaker = {
    el: null, unlocked: false, busy: false, done: 0, text: '', urls: {}, dur: {}, loading: false,

    init: function () {
      this.el = new Audio();
      this.el.preload = 'auto';
      this.el.setAttribute('playsinline', '');
    },

    // 手机浏览器规定：必须在用户点击的那一刻播放过一次，之后才允许程序自己播放。
    unlock: function () {
      var self = this;
      if (self.unlocked || self.busy) return;
      try {
        self.el.src = silentWav();
        var p = self.el.play();
        var ok = function () { self.unlocked = true; self.pump(); paint(); };
        if (p && p.then) p.then(ok, function () { /* 下次点击再试 */ }); else ok();
      } catch (e) { /* 下次点击再试 */ }
    },

    preload: function () {
      var self = this;
      if (self.loading) return;
      self.loading = true;
      fetch('audio/manifest.json').then(function (r) { return r.json(); }).then(function (m) {
        self.dur = m;
        Object.keys(m).forEach(function (id) {
          fetch('audio/' + id + '.m4a').then(function (r) { return r.blob(); }).then(function (b) {
            self.urls[id] = URL.createObjectURL(b);
          }).catch(function () { /* 用到时再直接从网络播 */ });
        });
      }).catch(function () { self.loading = false; });
    },

    pump: function () {
      var self = this;
      if (self.busy || !V || !V.you.host) return;
      var cue = null;
      (V.cues || []).forEach(function (c) { if (!cue && c.id > self.done) cue = c; });
      if (!cue) {
        if (self.text) { self.text = ''; paint(); }
        return;
      }
      if (!self.unlocked) { paint(); return; }   // 等房主点一下屏幕
      self.busy = true;
      self.text = cue.text;
      paint();
      self.playAll(cue.clips, 0, function (blocked) {
        self.busy = false;
        if (blocked) { self.unlocked = false; paint(); return; }
        self.done = cue.id;
        act('ack', { id: cue.id }, true);
        self.pump();
      });
    },

    playAll: function (clips, i, cb) {
      var self = this;
      if (i >= clips.length) return cb(false);
      self.playOne(clips[i], function (blocked) {
        if (blocked) cb(true); else self.playAll(clips, i + 1, cb);
      });
    },

    playOne: function (id, cb) {
      var self = this, el = self.el, fin = false;
      var watchdog = setTimeout(function () { end(false); }, ((self.dur[id] || 4) + 4) * 1000);
      function end(blocked) {
        if (fin) return;
        fin = true;
        clearTimeout(watchdog);
        el.onended = el.onerror = null;
        cb(blocked);
      }
      el.onended = function () { end(false); };
      el.onerror = function () { setTimeout(function () { end(false); }, 900); };
      el.src = self.urls[id] || ('audio/' + id + '.m4a');
      try {
        var p = el.play();
        if (p && p.catch) {
          p.catch(function (e) {
            if (e && e.name === 'NotAllowedError') end(true);     // 还没被允许出声
            else setTimeout(function () { end(false); }, 900);
          });
        }
      } catch (e) { end(true); }
    }
  };

  function silentWav() {
    var n = 800, buf = new ArrayBuffer(44 + n), v = new DataView(buf);
    function str(o, s) { for (var i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); }
    str(0, 'RIFF'); v.setUint32(4, 36 + n, true); str(8, 'WAVEfmt ');
    v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
    v.setUint32(24, 8000, true); v.setUint32(28, 8000, true); v.setUint16(32, 1, true); v.setUint16(34, 8, true);
    str(36, 'data'); v.setUint32(40, n, true);
    for (var i = 0; i < n; i++) v.setUint8(44 + i, 128);
    return URL.createObjectURL(new Blob([buf], { type: 'audio/wav' }));
  }

  // 回报丢了就补发，否则游戏会卡住
  setInterval(function () {
    if (!V || !V.you.host || !Speaker.done) return;
    var stale = (V.cues || []).some(function (c) { return c.id <= Speaker.done; });
    if (stale) act('ack', { id: Speaker.done }, true);
  }, 1500);

  // 保活：免费的托管平台 15 分钟收不到新请求就让服务器休眠，一休眠所有房间都没了。
  // 实时推送是服务器单向发过来的，不算「请求」，所以发言时间一长、没人点手机就可能中招。
  // 只要有一台手机开着房间页面，每 4 分钟发一个很小的请求，服务器就不会睡。
  var KEEPALIVE_MS = 4 * 60 * 1000;
  setInterval(function () {
    if (cred) fetch('/healthz', { cache: 'no-store' }).catch(function () { /* 断网时下次再试 */ });
  }, KEEPALIVE_MS);

  // 屏幕常亮：夜里手机放在桌上不能自己锁屏
  var wake = null;
  function keepAwake() {
    try {
      if (navigator.wakeLock && document.visibilityState === 'visible' && (!wake || wake.released)) {
        navigator.wakeLock.request('screen').then(function (w) { wake = w; }, function () { /* 不支持就算了 */ });
      }
    } catch (e) { /* 不支持就算了 */ }
  }

  // ------------------------------------------------------------ 收到新画面

  function ctxKey() {
    if (!V) return '';
    if (V.phase === 'night') {
      var p = V.night.prompt;
      return 'n' + V.night_no + (p ? p.type + p.ui : '');
    }
    if (V.phase === 'day') {
      var d = V.day;
      return 'd' + d.no + d.stage + (d.vote ? d.vote.round : '') + (d.settle && d.settle.mine ? 'm' : '') +
        (d.elect ? (d.elect.mine || '') + (d.elect.vote ? d.elect.vote.round : '') : '');
    }
    return V.phase;
  }

  function onView() {
    var k = ctxKey();
    if (k !== ui.ctx) {                          // 换了环节：清掉上一环节选中的东西
      if (V.phase === 'deal' && ui.ctx !== 'deal') ui.peeked = false;
      ui.ctx = k;
      ui.picks = [];
      ui.mode = null;
      ui.shot = null;
      if (ui.sheet && ui.sheet.type === 'confirm') ui.sheet = null;
      if (ui.sheet && ui.sheet.type === 'config' && V.phase !== 'lobby') ui.sheet = null;
    }
    if (V.you.host) Speaker.preload();
    paint();
    Speaker.pump();
  }

  // ------------------------------------------------------------ 画面

  function paint() {
    var html;
    if (!cred || !V) html = ui.claim ? claimScreen() : homeScreen();
    else if (V.phase === 'lobby') html = lobbyScreen();
    else if (V.phase === 'deal') html = dealScreen();
    else if (V.phase === 'night') html = nightScreen();
    else if (V.phase === 'day') html = dayScreen();
    else html = overScreen();
    if (html !== lastHtml) {
      var m = app.querySelector('.main'), top = m ? m.scrollTop : 0;
      var keep = m ? m.getAttribute('data-k') : null;
      var focus = document.activeElement && document.activeElement.id;
      app.innerHTML = html;
      lastHtml = html;
      var m2 = app.querySelector('.main');
      if (m2 && m2.getAttribute('data-k') === keep) m2.scrollTop = top;
      var a = document.getElementById('in-name'), b = document.getElementById('in-code');
      if (a) a.value = ui.name;
      if (b) b.value = ui.code;
      if (focus && document.getElementById(focus)) document.getElementById(focus).focus();
    }
    paintSheet();
    paintPeek();
    paintSky();
  }

  // 天空跟着阶段走：首页 / 大厅 / 发牌是黄昏，夜里压暗，白天亮起来，结束看谁赢
  var lastSky = '';
  function paintSky() {
    var sky = 'dusk', home = !cred || !V;
    if (!home) {
      if (V.phase === 'night') sky = 'night';
      else if (V.phase === 'day') sky = 'day';
      else if (V.phase === 'over') sky = V.over.winner === 'wolf' ? 'blood' : 'dawn';
    }
    if (sky !== lastSky) {
      lastSky = sky;
      document.body.setAttribute('data-sky', sky);
      var tc = { dusk: '#2a2019', night: '#0e0d0c', day: '#cdbd96', blood: '#2a0d0a', dawn: '#d3bf96' }[sky];
      var meta = document.querySelector('meta[name="theme-color"]');
      if (meta) meta.setAttribute('content', tc);
    }
    document.body.classList.toggle('at-home', home);
    if (home && !ui.claim && !ui.intro) FX.dm.start(1, 30); else if (!ui.intro) FX.dm.stop();
    // 背景音乐只在首页、大厅、结束页放；这台手机正在播报语音时先让开，播完再接着放。
    // 背景音乐的开关（FX.bgm.muted）和语音播报（Speaker）是两套互不相干的东西。
    FX.bgm.want((home || V.phase === 'lobby' || V.phase === 'over') && !Speaker.text);
  }

  function frame(o) {
    var banners = '';
    if (!live) banners += '<div class="banner warn">连接断开了，正在重连…</div>';
    if (V.you.host && !Speaker.unlocked && (V.cues || []).length) {
      banners += '<div class="banner act" data-act="unlock"><span>点一下这里，开启语音播报</span></div>';
    }
    if (!V.host_online && !V.you.host) {
      banners += '<div class="banner warn act"><span>房主' + (V.host_seat ? '（' + V.host_seat + '号）' : '') +
        '掉线了，播报暂停</span><button class="btn sm" data-act="take-host">用我的手机播报</button></div>';
    }
    var bar = '';
    if (V.you.host && Speaker.text) bar += '<div class="say">正在播报：' + esc(Speaker.text) + '</div>';
    if (o.peek && V.me) bar += '<div class="peekrow"><button class="peekbtn" data-hold="1">按住看我的身份</button></div>';
    bar += o.bar || '';
    return '<div class="screen ' + (o.cls || '') + '">' +
      '<header class="top"><button class="code" data-act="qr">房间<b>' + V.code + '</b></button>' +
      '<div class="ttl">' + (o.title || '') + '</div>' +
      '<button class="more" data-act="menu" aria-label="菜单"><i></i><i></i><i></i></button></header>' +
      banners +
      '<main class="main" data-k="' + (o.key || V.phase) + '">' + o.main + '</main>' +
      (bar ? '<footer class="bar">' + bar + '</footer>' : '') + '</div>';
  }

  function btn(label, a, cls, off, data) {
    return '<button class="btn ' + (cls || '') + '" data-act="' + a + '"' + (data || '') + (off ? ' disabled' : '') + '>' + label + '</button>';
  }
  function row() { return '<div class="row">' + Array.prototype.join.call(arguments, '') + '</div>'; }
  function wait(t) { return '<div class="wait">' + t + '</div>'; }
  function ask(title, hint) { return '<div class="ask"><h2>' + title + '</h2>' + (hint ? '<p>' + hint + '</p>' : '') + '</div>'; }
  function stage(title, body) { return '<div class="stage"><h2>' + title + '</h2>' + (body || '') + '</div>'; }

  // 座位围成一圈：1 号在正上方，顺时针排下去，和大家实际围坐的样子一致。
  // center 是圆桌中间显示的内容。
  function grid(fn, center) {
    var n = V.seats.length;
    var sz = n <= 6 ? 62 : n <= 9 ? 56 : n <= 12 ? 50 : n <= 15 ? 44 : 40;
    var rx = 40, ry = 41;
    var slots = V.seats.map(function (s, i) {
      var a = i / n * Math.PI * 2;
      var x = 50 + rx * Math.sin(a), y = 50 - ry * Math.cos(a);
      return '<div class="slot" style="left:' + x.toFixed(2) + '%;top:' + y.toFixed(2) + '%">' + fn(s) + '</div>';
    }).join('');
    var minw = n <= 9 ? '250px' : n <= 12 ? '300px' : '100%';
    return '<div class="ring" style="--sz:' + sz + 'px;--minw:' + minw + '"><div class="table">' + (center || tableDefault()) + '</div>' + slots + '</div>';
  }
  function tableDefault() {
    if (V.phase === 'night') return '<div class="moon"></div><div class="sm">第 ' + V.night_no + ' 夜</div>';
    if (V.phase === 'day') {
      var alive = V.seats.filter(function (s) { return s.alive; }).length;
      return '<div class="sun"></div><div class="big">' + alive + '<small>/' + V.seats.length + '</small></div><div class="sm">存活</div>';
    }
    return '<div class="big">' + V.seats.length + '</div><div class="sm">人局</div>';
  }

  // 一个座位格子。o.act 有值时可以点。
  function tile(s, o) {
    o = o || {};
    var cls = ['seat'];
    if (!s.taken) cls.push('empty');
    if (s.seat === V.you.seat) cls.push('me');
    if (!s.alive) cls.push('dead');
    if (s.taken && !s.online) cls.push('off');
    if (o.sel) cls.push('sel');
    if (o.dis) cls.push('dis');
    if (o.cls) cls.push(o.cls);
    if (s.shown) cls.push('hasav');
    var name = s.taken ? esc(s.name) : '空位';
    var corner = s.seat === V.you.seat ? '我' : (s.host ? '房主' : '');
    var tag = o.tag || (s.shown ? role(s.shown).name : (!s.alive ? '出局' :
      (s.taken && !s.online ? '掉线' : (s.can_vote === false ? '无票' : ''))));
    var inner = '<span class="tk">' + (s.sheriff ? '<i class="star" title="警长"></i>' : '') +
      (corner ? '<i class="corner">' + corner + '</i>' : '') + (s.shown ? av(s.shown) : '') + '<b>' + s.seat + '</b></span>' +
      '<span class="nm">' + name + '</span>' + (tag ? '<i class="tg">' + tag + '</i>' : '') + (o.extra || '');
    if (o.act && !o.dis) {
      return '<button class="' + cls.join(' ') + '" data-act="' + o.act + '" data-seat="' + s.seat + '">' + inner + '</button>';
    }
    return '<div class="' + cls.join(' ') + '">' + inner + '</div>';
  }

  // 选人用的格子：targets 之外的不能点，picks 里的高亮
  function pickGrid(targets, red, marks) {
    return grid(function (s) {
      return tile(s, {
        act: 'pick', dis: !has(targets, s.seat), sel: has(ui.picks, s.seat),
        cls: red ? 'kill' : '', tag: marks && marks[s.seat] ? esc(marks[s.seat]) : ''
      });
    });
  }

  function order() { return info.roles.map(function (r) { return r.id; }); }

  function boardText(roles) {
    return order().filter(function (r) { return roles[r]; }).map(function (r) {
      return role(r).name + (roles[r] > 1 ? '×' + roles[r] : '');
    }).join(' ');
  }
  function lineup(roles) {
    return '<div class="lineup">' + order().filter(function (r) { return roles[r]; }).map(function (r) {
      return '<span>' + av(r) + role(r).name + (roles[r] > 1 ? '<em>×' + roles[r] + '</em>' : '') + '</span>';
    }).join('') + '</div>';
  }
  function rulesText() {
    var c = V.config;
    var w = { first: '女巫仅首夜可自救', never: '女巫不可自救', always: '女巫可自救' }[c.witch_self_save];
    return (c.sheriff ? '有警长竞选，' : '无警长，') + (c.roles.witch ? w + '，' : '') + (c.win === 'all' ? '屠城' : '屠边');
  }

  function joinUrl() {
    var base = location.origin;
    if (/^(localhost|127\.|\[::1\])/.test(location.hostname) && info.lan) base = info.lan;
    return base + '/?room=' + V.code;
  }
  function qrSrc() { return '/api/qr?t=' + encodeURIComponent(joinUrl()); }

  // 从 start 开始按方向把活着的人排出来（发言顺序预览）
  function ring(start, dir) {
    var n = V.seats.length, out = [], s = start;
    for (var i = 0; i < n; i++) {
      if (seatOf(s).alive) out.push(s);
      s = ((s - 1 + dir) % n + n) % n + 1;
    }
    return out;
  }
  function seq(list) {
    return list.length > 7 ? list.slice(0, 5).join(' → ') + ' → … → ' + list[list.length - 1] : list.join(' → ');
  }

  // ---------- 首页

  // 首页那一手牌（开场动画最后也收成这一手）
  var FAN = [['seer', '预言家', 'god'], ['witch', '女巫', 'god'], ['wolf', '狼人', 'wolf'],
    ['hunter', '猎人', 'god'], ['villager', '村民', 'villager']];
  function fanCards() {
    return FAN.map(function (r, i) { return { id: r[0], name: r[1], team: r[2], k: i - (FAN.length - 1) / 2 }; });
  }
  var SND = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" fill="currentColor"/>' +
    '<path class="wave" d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11"/><path class="x" d="M16 9.5l5 5M21 9.5l-5 5"/></svg>';

  function homeScreen() {
    var fan = '<div class="fan">' + fanCards().map(function (c) {
      return '<div class="fc ' + c.team + '" style="--k:' + c.k + '">' + av(c.id) + '</div>';
    }).join('') + '</div>';
    var hero = '<div class="hero">' +
      '<button class="snd' + (FX.bgm.muted ? ' off' : '') + '" data-act="snd" aria-label="背景音乐">' + SND + '</button>' +
      fan + '<h1 class="title" data-act="replay"><span class="tt">狼人杀</span><i class="claw"></i><em>面杀助手</em></h1></div>';
    if (cred) return '<div class="screen home"><main class="main" data-k="home">' + hero + '<p class="hint center" style="margin-top:24px">正在进入房间…</p></main></div>';
    var name = '<label class="field"><span>你的昵称</span><input id="in-name" maxlength="8" placeholder="最多 8 个字" autocomplete="off" enterkeyhint="done"></label>';
    var code = '<label class="field"><span>房间号</span><input id="in-code" class="codein" inputmode="numeric" pattern="[0-9]*" maxlength="4" placeholder="····" autocomplete="off" enterkeyhint="done"></label>';
    var body = fromLink
      ? name + code + '<div class="stack">' + btn('加入房间', 'join', 'pri') + '</div>' +
        '<div class="or">或者</div><div class="stack">' + btn('创建新房间，我当房主', 'create') + '</div>'
      : name + '<div class="stack">' + btn('创建房间，我当房主', 'create', 'pri') + '</div>' +
        '<div class="or">已经有房间了</div>' + code + '<div class="stack">' + btn('加入房间', 'join') + '</div>';
    return '<div class="screen home"><main class="main" data-k="home">' + hero +
      '<div class="card panel">' + body + '</div></main></div>';
  }

  function playIntro() {
    ui.intro = true;
    FX.dm.stop();
    FX.intro(fanCards(), function () { ui.intro = false; paintSky(); });
  }

  function claimScreen() {
    var c = ui.claim, list = c.claim || [];
    var body = list.length
      ? '<p class="hint" style="margin-bottom:12px">如果你是中途换了手机或浏览器，点你原来的座位就能回到游戏。</p>' +
        '<div class="stack">' + list.map(function (s) {
          return btn(s.seat + ' 号　' + esc(s.name), 'claim', '', false, ' data-seat="' + s.seat + '"');
        }).join('') + '</div>'
      : '<p class="hint">这一局已经开始，而且没有掉线的座位。等这局结束再进来吧。</p>';
    return '<div class="screen home"><main class="main" data-k="claim">' +
      '<div class="logo"><h1>房间 ' + esc(c.code) + '</h1><p>游戏已经开始了</p></div>' + body +
      '<div class="stack" style="margin-top:20px">' + btn('返回', 'claim-back') + '</div></main></div>';
  }

  // ---------- 大厅：入座

  function lobbyScreen() {
    var me = V.you, n = V.n;
    var taken = V.seats.filter(function (s) { return s.taken; }).length;
    var off = V.seats.filter(function (s) { return s.taken && !s.online; }).length;
    var others = V.standing - (me.seat ? 0 : 1);
    var main =
      '<div class="card lobbyhd"><button class="qrbtn" data-act="qr" aria-label="放大二维码"><img class="qr" src="' + qrSrc() + '" alt="进房二维码"></button>' +
      '<button class="txt" data-act="qr"><div class="lbl">房间号 · 扫码进房</div><div class="digits">' + V.code + '</div></button>' +
      btn(me.host ? '改板子' : '看规则', me.host ? 'config' : 'menu', 'sm') +
      '<div class="brd">' + lineup(V.config.roles) + '<div class="hint">' + n + ' 人局，' + rulesText() + '</div>' +
      (V.err ? '<div class="warn-t">' + esc(V.err) + '</div>' : '') + '</div></div>' +
      grid(function (s) {
        if (!s.taken) return tile(s, { act: 'sit' });
        if (s.seat === me.seat) return tile(s, { act: 'stand' });
        return tile(s, me.host ? { act: 'kick' } : {});
      }, '<div class="big">' + taken + '<small>/' + n + '</small></div><div class="sm">' +
        (taken < n ? (me.seat ? '等人入座' : '点空位坐下') : '人齐了') + '</div>') +
      '<p class="hint center">按实际围坐的顺序坐：1 号旁边是 2 号，依次排下去。' +
      (others ? '<br>还有 ' + others + ' 人进了房间没入座。' : '') + '</p>';
    var bar;
    if (me.host) {
      var why = V.err ? '板子还不能开局' : taken < n ? '还差 ' + (n - taken) + ' 人入座' : off ? '有人掉线了' : '';
      bar = row(btn('试音', 'test'), btn(why || '发牌', 'deal', 'pri', !!why));
    } else {
      bar = wait(me.seat ? '你坐在 ' + me.seat + ' 号，等房主发牌' : '点一个空位坐下');
    }
    return frame({ title: '等待入座', main: main, bar: bar });
  }

  // ---------- 发牌：看身份

  function dealScreen() {
    var d = V.deal, n = V.seats.length, main, bar;
    if (!V.me) {
      main = '<div class="sleep"><h1>本局旁观</h1><p>你没有入座，这一局只能看</p></div>';
      bar = '';
    } else {
      main = '<button class="idcard" data-hold="1"><span class="art"></span><div class="lbl">你是 ' + V.you.seat + ' 号</div>' +
        '<div class="big">按住这里看身份</div><div class="hint">用手挡一下屏幕，松手就会藏起来</div></button>' +
        '<div class="progress">已看完身份 ' + d.count + ' / ' + n + '</div>';
      if (!d.seen) {
        bar = btn(ui.peeked ? '我记住了' : '先按住上面看身份', 'seen', 'pri', !ui.peeked);
      } else if (V.you.host) {
        var all = d.count >= n;
        bar = btn(all ? '天黑请闭眼' : '还有 ' + (n - d.count) + ' 人没看完', 'start-night', 'pri', !all) +
          (all ? '' : '<button class="link" data-act="force-night">不等了，直接开始</button>');
      } else {
        bar = wait('等其他人看完，房主会宣布天黑');
      }
    }
    return frame({ title: '查看身份', main: main, bar: bar });
  }

  // ---------- 夜晚

  function nightScreen() {
    var p = V.night.prompt, me = V.you.seat, title = '第 ' + V.night_no + ' 夜', main, bar = '';
    if (!p) {
      main = '<div class="sleep"><div class="moon"></div><h1>天黑请闭眼</h1><p>' +
        (V.me && !V.me.alive ? '你已出局，也请闭眼，不要出声' : '听到语音叫你的身份，再睁眼看手机') + '</p>' +
        (V.you.host ? '<div class="hostnote">你的手机负责播报：放在桌子中间，音量调大，保持亮屏。</div>' : '') + '</div>';
      return frame({ title: title, main: main, cls: 'night', peek: true, key: 'sleep' });
    }
    var red = p.tone === 'red';

    if (p.ui === 'info') {
      main = ask(esc(p.title)) + '<div class="card infoc">' +
        p.lines.map(function (l) { return '<p>' + esc(l) + '</p>'; }).join('') + '</div>';
      bar = btn(esc(p.ok), 'night-ok', 'pri');
    }

    if (p.ui === 'result') {
      var rid = roleIdByName(p.big);
      var pic = rid ? medal(rid) : p.tone === 'bad' ? art('emblem_wolf', 'emblem') : p.tone === 'good' ? art('emblem_good', 'emblem') : '';
      main = '<div class="result ' + (p.tone || 'plain') + '"><div class="lbl">' + esc(p.title) + '</div>' + pic + '<div class="big">' + esc(p.big) + '</div>' +
        (p.lines || []).map(function (l) { return '<p>' + esc(l) + '</p>'; }).join('') + '</div>';
      bar = btn(esc(p.ok), 'night-ok', 'pri');
    }

    if (p.ui === 'pick') {
      var picks = ui.picks.filter(function (s) { return has(p.targets, s); });
      var ready = picks.length === p.count;
      var label = ready ? esc(p.verb) + ' ' + picks.join(' 号和 ') + ' 号' : (p.count === 2 ? '选两名玩家' : '先选一名玩家');
      main = ask(esc(p.title), esc(p.hint)) + pickGrid(p.targets, red, p.marks);
      var go = btn(label, 'night-go', red ? 'red' : 'pri', !ready);
      bar = p.skip ? row(btn(esc(p.skip), 'night-skip'), go) : go;
    }

    if (p.ui === 'wolf') {
      var mine = p.picks[me];
      var chips = p.wolves.map(function (w) {
        var k = p.picks[w];
        var t = k === undefined ? '还没选' : k === 0 ? '空刀' : '刀 ' + k + ' 号';
        return '<span class="' + (k === undefined ? 'none' : '') + '">' + (w === me ? '我' : w + '号') + '：' + t + '</span>';
      }).join('');
      var extra = '';
      if (p.double) {
        extra = '<div class="card opt"><div class="txt"><div class="lbl">双刀（整局一次）</div><div class="t">' +
          (ui.mode === 'extra' ? '点一名玩家作为第二刀' : p.extra ? '第二刀：<em>' + p.extra + ' 号</em>' : '今晚不用') +
          '</div><div class="hint">两刀砍同一人，可以无视解药和守护。</div></div>' +
          btn(ui.mode === 'extra' ? '取消' : p.extra ? '撤回' : '选第二刀', 'wolf-extra', 'sm') + '</div>';
      }
      var solo = p.wolves.length === 1;
      main = ask(solo ? '由你选今晚的目标' : '狼人，选今晚的目标',
        solo ? '选好后点确认。' : '所有狼人选中同一个人，再由任意一人确认。') +
        '<div class="picks">' + chips + '</div>' + extra +
        grid(function (s) {
          var marks = p.wolves.filter(function (w) { return p.picks[w] === s.seat; })
            .map(function (w) { return '<i>' + w + '</i>'; }).join('');
          if (p.extra === s.seat) marks += '<i>双</i>';
          var mate = has(p.wolves, s.seat) && s.seat !== me;
          var r = p.roles[s.seat];
          var can = ui.mode === 'extra' ? s.alive : has(p.targets, s.seat);
          return tile(s, {
            act: 'wolf-pick', dis: !can,
            sel: ui.mode !== 'extra' && mine === s.seat,
            cls: (has(p.wolves, s.seat) ? 'mate ' : '') + 'kill',
            tag: mate ? (r && r !== 'wolf' ? role(r).name : '同伴') : '',
            extra: marks ? '<span class="marks">' + marks + '</span>' : ''
          });
        });
      var lab = p.agreed === null ? (solo ? '先选一名玩家' : '等所有狼人选同一目标') :
        p.agreed === 0 ? '确认空刀' : '确认击杀 ' + p.agreed + ' 号';
      bar = row(btn(mine === 0 ? '已选空刀' : '空刀', 'wolf-none'), btn(lab, 'wolf-ok', 'red', p.agreed === null));
    }

    if (p.ui === 'witch') {
      if (ui.mode === 'poison') {
        main = ask('选一名玩家下毒', '毒药只有一瓶，用了就没有了。') + pickGrid(p.targets, true);
        bar = row(btn('返回', 'witch-back'), btn(ui.picks.length ? '确认毒 ' + ui.picks[0] + ' 号' : '先选一名玩家', 'witch-poison-ok', 'red', !ui.picks.length));
      } else {
        var a;
        if (!p.antidote) {
          a = '<div class="card opt gone">' + art('potion_save', 'potion') + '<div class="txt"><div class="lbl">解药</div><div class="t">已经用掉了，所以不知道今晚谁倒牌</div></div></div>';
        } else if (!p.victim) {
          a = '<div class="card opt gone">' + art('potion_save', 'potion') + '<div class="txt"><div class="lbl">解药</div><div class="t">今晚没有人倒牌</div></div></div>';
        } else {
          a = '<div class="card opt">' + art('potion_save', 'potion') + '<div class="txt"><div class="lbl">解药</div><div class="t">今晚倒牌的是 <em>' + p.victim + ' 号' +
            (p.victim === me ? '（你自己）' : ' ' + esc(seatOf(p.victim).name)) + '</em></div>' +
            (p.can_save ? '' : '<div class="hint">按本局规则，你不能自救。</div>') + '</div>' +
            (p.can_save ? btn('救人', 'witch-save', 'sm pri') : '') + '</div>';
        }
        var b = p.poison
          ? '<div class="card opt">' + art('potion_poison', 'potion') + '<div class="txt"><div class="lbl">毒药</div><div class="t">还有一瓶</div></div>' + btn('下毒', 'witch-poison', 'sm red') + '</div>'
          : '<div class="card opt gone">' + art('potion_poison', 'potion') + '<div class="txt"><div class="lbl">毒药</div><div class="t">已经用掉了</div></div></div>';
        main = ask('女巫，决定是否用药', '同一晚只能用一瓶。') + a + b;
        bar = btn('今晚不用药', 'witch-none');
      }
    }
    return frame({ title: title, main: main, bar: bar, cls: 'night', key: p.type + p.ui + (ui.mode || '') });
  }

  // ---------- 白天

  function votesHtml(res) {
    var by = {}, abst = [];
    Object.keys(res.ballots).forEach(function (voter) {
      var t = res.ballots[voter];
      if (t) (by[t] = by[t] || []).push(+voter); else abst.push(+voter);
    });
    var most = Math.max.apply(null, [1].concat(Object.keys(by).map(function (t) { return res.counts[t]; })));
    var rows = Object.keys(by).map(Number).sort(function (a, b) { return res.counts[b] - res.counts[a] || a - b; })
      .map(function (t) {
        var who = by[t].sort(function (a, b) { return a - b; }).map(function (x) {
          return x + (res.sheriff && x === res.sheriff ? '（警长 1.5 票）' : '');
        }).join('、');
        return '<div class="vr' + (has(res.top, t) ? ' top' : '') + '"><i class="vbar" style="width:' +
          Math.round(res.counts[t] / most * 100) + '%"></i><b>' + t + ' 号</b><span>' + res.counts[t] +
          ' 票 ← ' + who + '</span></div>';
      }).join('');
    if (abst.length) rows += '<div class="vr"><b>弃票</b><span>' + abst.sort(function (a, b) { return a - b; }).join('、') + '</span></div>';
    var ttl = (res.kind === 'elect' ? '警长竞选' : '放逐') + (res.round === 2 ? ' PK 投票' : '投票');
    return '<div class="card votes"><div class="vt">' + ttl + '</div>' + rows + '</div>';
  }

  function dayScreen() {
    var d = V.day, me = V.you, host = me.host, e = d.elect, head = '', bar = '', pick = null;
    var names = { wait: '播报中', settle: '出局确认', discuss: '发言', vote: '投票', pk: 'PK 发言', dusk: '天黑前',
      e_signup: '警长竞选', e_speech: '竞选发言', e_withdraw: '退水', e_vote: '警长投票', e_pk: '警长 PK' };

    if (d.stage === 'wait') head = stage('请听播报');

    // ---- 自己要用白天技能：白狼王自爆带人 / 骑士决斗
    if (ui.mode === 'ww' || ui.mode === 'duel') {
      var alive = V.seats.filter(function (s) { return s.alive && s.seat !== me.seat; }).map(function (s) { return s.seat; });
      var t0 = ui.picks[0];
      if (ui.mode === 'ww') {
        head = stage('白狼王自爆', '<p>选一名玩家带走，也可以不带人。自爆后直接进入黑夜。</p>');
        bar = row(btn('取消', 'mode-cancel'), btn(t0 ? '自爆并带走 ' + t0 + ' 号' : '不带人，直接自爆', 'ww-ok', 'red'));
      } else {
        head = stage('骑士决斗', '<p>选一名玩家决斗：他是狼人则他出局并立刻天黑；他是好人则你出局。整局只有一次。</p>');
        bar = row(btn('取消', 'mode-cancel'), btn(t0 ? '和 ' + t0 + ' 号决斗' : '先选一名玩家', 'duel-ok', 'red', !t0));
      }
      return frame({ title: '第 ' + d.no + ' 天', main: head + pickGrid(alive, true), bar: bar, key: 'daymode' });
    }

    // ---- 警长竞选
    if (d.stage === 'e_signup') {
      var left1 = e.players.filter(function (s) { return !has(e.decided, s); });
      if (e.mine === 'signup') {
        head = stage('警长竞选：你要上警吗？', '<p>大家同时选择，全部选完才会公布谁上警。上警的人不参加第一轮投票。</p>');
        bar = row(btn('不上警', 'elect-run', '', false, ' data-v="0"'), btn('上警', 'elect-run', 'pri', false, ' data-v="1"'));
      } else {
        head = stage('警长竞选', '<p>已选择 ' + e.decided.length + ' / ' + e.players.length + '。' + (left1.length ? '还没选：' + nums(left1) + '。' : '') + '</p>');
        bar = host ? btn('不等了（没选的算不上警）', 'elect-close') : wait('等所有人选完');
      }
    }
    if (d.stage === 'e_speech' || d.stage === 'e_pk') {
      var pk = d.stage === 'e_pk';
      head = stage(pk ? '警长竞选平票 PK' : '竞选发言',
        '<p>' + (pk ? 'PK 玩家' : '上警玩家') + '：<b>' + nums(e.cands) + '</b></p>' +
        '<p>发言顺序：<b>' + seq(e.order) + '</b></p>' +
        '<p>' + (pk ? '发言结束后，警下和退水的玩家再投一轮。' : '发言结束后进入退水环节。') + '狼人可以在右上角菜单里自爆。</p>');
      bar = host ? btn(pk ? '发言结束，开始 PK 投票' : '发言结束，进入退水环节', 'elect-next', 'pri') : wait('等房主推进到下一步');
    }
    if (d.stage === 'e_withdraw') {
      var left2 = e.cands.filter(function (s) { return !has(e.decided, s); });
      if (e.mine === 'withdraw') {
        head = stage('退水环节：你要退水吗？', '<p>退水就是退出竞选。退水后第一轮不能投票，平票 PK 时可以投。大家同时选择。</p>');
        bar = row(btn('退水', 'elect-wd', '', false, ' data-v="1"'), btn('留在警上', 'elect-wd', 'pri', false, ' data-v="0"'));
      } else {
        head = stage('退水环节', '<p>警上玩家正在决定是否退水。' + (left2.length ? '还没选：' + nums(left2) + '。' : '') + '狼人可以在右上角菜单里自爆。</p>');
        bar = host ? btn('不等了（没选的算不退水）', 'elect-close') : wait('等警上玩家选完');
      }
    }
    if (d.stage === 'e_vote') {
      var ev = e.vote, left3 = ev.voters.filter(function (s) { return !has(ev.voted, s); });
      if (e.mine === 'vote') {
        head = stage((ev.round === 2 ? 'PK 投票' : '警长投票') + '：你选谁当警长？', '<p>投出后不能改。</p>');
        pick = function (s) { return { act: 'pick', dis: !has(ev.cands, s.seat), sel: has(ui.picks, s.seat) }; };
        bar = row(btn('弃票', 'elect-vote-none'), btn(ui.picks.length ? '投给 ' + ui.picks[0] + ' 号' : '先选一名玩家', 'elect-vote-ok', 'pri', !ui.picks.length));
      } else {
        head = stage('警长投票中 ' + ev.voted.length + ' / ' + ev.voters.length,
          '<p>候选人：<b>' + nums(ev.cands) + '</b>。' + (ev.round === 2 ? '警下和退水的玩家投票。' : '只有警下玩家投票。') +
          (left3.length ? '还没投：' + nums(left3) + '。' : '') + '</p>');
        bar = host ? btn('结束投票（没投的算弃票）', 'elect-close') : wait(ev.round === 2 ? '等大家投完' : '等警下玩家投完');
      }
    }

    // ---- 出局确认
    if (d.stage === 'settle') {
      var st = d.settle, mine = st.mine;
      if (mine && mine.can_shoot && ui.shot === null) {
        head = stage('你出局了，可以发动技能', '<p>选一名玩家带走，或者选择不发动。</p>');
        pick = function (s) { return { act: 'pick', dis: !has(st.targets, s.seat), sel: has(ui.picks, s.seat), cls: 'kill' }; };
        bar = row(btn('不发动', 'shot-none'), btn(ui.picks.length ? '带走 ' + ui.picks[0] + ' 号' : '先选一名玩家', 'shot-ok', 'red', !ui.picks.length));
      } else if (mine && mine.badge) {
        head = stage('你是警长：警徽交给谁？', '<p>选一名活着的玩家接任警长，或者撕掉警徽。</p>');
        pick = function (s) { return { act: 'pick', dis: !has(st.targets, s.seat) || s.seat === ui.shot, sel: has(ui.picks, s.seat) }; };
        bar = row(btn('撕掉警徽', 'badge-tear'), btn(ui.picks.length ? '移交给 ' + ui.picks[0] + ' 号' : '先选一名玩家', 'badge-ok', 'pri', !ui.picks.length));
      } else if (mine) {
        var gun = V.me && (V.me.role === 'hunter' || V.me.role === 'wolfking');
        head = stage('你出局了', '<p>' + (gun ? '这次你不能发动技能。' : '') + '点下面的按钮确认，游戏才会继续。</p>');
        bar = btn('确认', 'settle-ok', 'pri');
      } else {
        head = stage('等待出局玩家确认', '<p>' + nums(st.waiting) + ' 正在手机上确认。</p>');
      }
    }

    // ---- 发言 / 天黑前
    if (d.stage === 'discuss' || d.stage === 'dusk') {
      var lw = d.last_words.length ? '<p>请 <b>' + nums(d.last_words) + '</b> 发表遗言。</p>' : '';
      if (d.stage === 'dusk') {
        head = stage('今天结束了', lw);
        bar = host ? btn('天黑请闭眼', 'start-night', 'pri') : wait('等房主宣布天黑');
      } else if (d.order && d.order.mine) {
        head = stage('警长，请决定发言顺序', lw + '<p>点一个顺序。你最后一个发言。</p>') +
          '<div class="stack" style="margin-bottom:14px">' + d.order.opts.map(function (o, i) {
            return btn(seq(ring(o.start, o.dir)), 'order', '', false, ' data-i="' + i + '"');
          }).join('') + '</div>';
        bar = host ? btn('发言结束，开始投票', 'start-vote', 'pri') : wait('发言结束后，房主会发起投票');
      } else {
        var sp = d.speak;
        head = stage('发言时间', lw +
          (d.order ? '<p>等警长（' + d.sheriff + ' 号）决定发言顺序。</p>' : '') +
          (sp ? '<p>发言顺序：<b>' + seq(ring(sp.start, sp.dir)) + '</b></p>' : ''));
        bar = host ? btn('发言结束，开始投票', 'start-vote', 'pri') : wait('发言结束后，房主会发起投票');
      }
    }

    if (d.stage === 'pk') {
      head = stage('平票 PK', '<p>请 <b>' + nums(d.pk) + '</b> 依次发言，然后其他人再投一轮。</p>');
      bar = host ? btn('开始 PK 投票', 'start-vote', 'pri') : wait('PK 发言结束后，房主会发起投票');
    }

    if (d.stage === 'vote') {
      var v = d.vote, left = v.voters.filter(function (s) { return !has(v.voted, s); });
      if (v.can) {
        head = stage((v.round === 2 ? 'PK 投票' : '投票') + '：你要放逐谁？', '<p>投出后不能改。' + (d.sheriff === me.seat ? '你是警长，这一票算 1.5 票。' : '') + '</p>');
        pick = function (s) { return { act: 'pick', dis: !has(v.cands, s.seat), sel: has(ui.picks, s.seat), cls: 'kill' }; };
        bar = row(btn('弃票', 'vote-none'), btn(ui.picks.length ? '投给 ' + ui.picks[0] + ' 号' : '先选一名玩家', 'vote-ok', 'red', !ui.picks.length));
      } else {
        var why = !has(v.voters, me.seat) ? '你这一轮不投票。' : '你已经投了。';
        head = stage('投票中 ' + v.voted.length + ' / ' + v.voters.length, '<p>' + why + (left.length ? '还没投：' + nums(left) + '。' : '') + '</p>');
        bar = host ? btn('结束投票（没投的算弃票）', 'end-vote') : wait('等所有人投完');
      }
    }

    var all = ((e && e.results) || []).concat(d.results);
    var res = all.length ? votesHtml(all[all.length - 1]) : '';
    var feed = '<div class="card feed">' + d.feed.map(function (t) { return '<p>' + esc(t) + '</p>'; }).join('') + '</div>';
    var inElection = e && d.stage.indexOf('e_') === 0;
    // 重要的东西不用往下滑：最新一条消息紧跟在标题下面；刚投完票时，票型排在座位前面
    var latest = d.feed.length ? '<div class="latest">' + esc(d.feed[d.feed.length - 1]) + '</div>' : '';
    var resFirst = !pick && res && has(['wait', 'settle', 'e_pk', 'pk', 'dusk'], d.stage);
    var main = head + latest + (resFirst ? res : '') + grid(function (s) {
      var o = pick ? pick(s) : {};
      if (inElection && !o.tag) o.tag = has(e.cands, s.seat) ? '警上' : has(e.withdrawn, s.seat) ? '已退水' : '';
      return tile(s, o);
    }) + (d.feed.length > 1 ? '<div class="sec-t">今天发生的事</div>' + feed : '') + (resFirst ? '' : res);
    return frame({ title: '第 ' + d.no + ' 天 · ' + (names[d.stage] || ''), main: main, bar: bar, peek: true, key: 'day' + d.stage });
  }

  // ---------- 结束

  function overScreen() {
    var o = V.over, w = o.winner;
    var ttl = { good: '好人阵营获胜', wolf: '狼人阵营获胜', third: '情侣阵营获胜' }[w];
    var mine = V.me ? o.camps[V.you.seat] : null;
    var main = '<div class="verdict ' + w + '">' + (w === 'wolf' ? art('emblem_wolf', 'emblem') : w === 'good' ? art('emblem_good', 'emblem') : '') + '<h1>' + ttl + '</h1>' +
      '<p>' + (V.me ? '你是' + role(V.me.role).name + '，' + (mine === w ? '赢了' : '输了') : '') + '</p></div>' +
      grid(function (s) {
        var c = o.causes[s.seat], love = has(o.lovers, s.seat);
        return tile(s, {
          cls: s.shown && role(s.shown).team === 'wolf' ? 'wolfrole' : '',
          tag: role(s.shown).name + (love ? '·情侣' : '') + (c ? '<br>' + esc(c) : '')
        });
      }) +
      '<div class="sec-t">复盘</div><div class="card log">' + o.log.map(function (t) { return '<p>' + esc(t) + '</p>'; }).join('') + '</div>';
    var bar = V.you.host ? btn('再来一局', 'again', 'pri') : wait('等房主开下一局');
    return frame({ title: '游戏结束', main: main, bar: bar });
  }

  // ---------- 按住看身份

  function paintPeek() {
    var html = '';
    if (ui.peek && V && V.me) {
      var me = V.me, r = role(me.role), notes = [];
      if (me.mates) {
        notes.push(me.mates.length ? '你的同伴：' + me.mates.map(function (m) {
          return '<b>' + m.seat + '号</b>' + (m.role !== 'wolf' ? '（' + role(m.role).name + '）' : '');
        }).join('、') : '你没有同伴');
      }
      (me.notes || []).forEach(function (t) { notes.push(esc(t)); });
      html = '<div class="pk ' + r.team + '"><div class="who">' + V.you.seat + ' 号 ' + esc(V.you.name) + '</div>' +
        medal(me.role) + '<div class="role">' + r.name + '</div><div class="team">' + art(r.team === 'wolf' ? 'emblem_wolf' : 'emblem_good', 'chip') + (r.team === 'wolf' ? '狼人阵营' : '好人阵营') + '</div>' +
        '<div class="desc">' + esc(r.desc) + '</div>' +
        (notes.length ? '<div class="notes">' + notes.join('<br>') + '</div>' : '') + '</div>';
    }
    if (html !== lastPeek) { peekEl.innerHTML = html; lastPeek = html; }
    peekEl.hidden = !html;
  }

  // ---------- 底部弹层

  function paintSheet() {
    var s = ui.sheet, html = '';
    if (s && (V || s.type === 'confirm')) {
      var body = '';
      if (s.type === 'qr') {
        body = '<h2>扫码进房间</h2><img class="qrbig" src="' + qrSrc() + '" alt="进房二维码">' +
          '<div class="url">' + esc(joinUrl()) + '<br>房间号 ' + V.code + '</div>' + btn('关闭', 'close');
      } else if (s.type === 'confirm') {
        body = '<h2>' + s.title + '</h2><div class="body">' + (s.text || '') + '</div>' +
          (s.run ? '<div class="bar" style="padding:0;background:none">' + row(btn('取消', 'close'), btn(s.ok, 'confirm-ok', s.danger ? 'red' : 'pri')) + '</div>'
            : btn('知道了', 'close', 'pri'));
      } else if (s.type === 'menu') {
        body = menuHtml();
      } else if (s.type === 'config') {
        body = configHtml();
      }
      html = '<div class="mask" data-act="close"></div><div class="wrap"><i class="torn"></i><div class="box">' + body + '</div></div>';
    }
    if (html !== lastSheet) {
      var box = sheetEl.querySelector('.box'), top = box ? box.scrollTop : 0;
      var same = s && s.type === sheetEl.getAttribute('data-t');
      sheetEl.innerHTML = html;
      lastSheet = html;
      sheetEl.setAttribute('data-t', s ? s.type : '');
      var box2 = sheetEl.querySelector('.box');
      if (box2 && same) box2.scrollTop = top;    // 调板子时不要每点一下就跳回顶部
      else if (box2 && s && s.type === 'config' && ui.cfgTop) box2.scrollTop = ui.cfgTop;
      if (s && s.type === 'config') ui.cfgTop = 0;
    }
    sheetEl.hidden = !html;
  }

  function nightOrderText() {
    var roles = V.config.roles;
    var steps = ['cupid', 'nightmare', 'magician', 'dreamer', 'guard', 'mech', 'wolf', 'beauty', 'gargoyle',
      'witch', 'seer', 'psychic', 'gravekeeper', 'witcher'];
    return steps.filter(function (r) { return r === 'wolf' || roles[r]; })
      .map(function (r) { return r === 'wolf' ? '狼人' : role(r).name; }).join(' → ');
  }

  function menuHtml() {
    var items = '', host = V.you.host, ph = V.phase, d = V.day;
    items += '<div class="body"><b>' + V.seats.length + ' 人局</b>　' + boardText(V.config.roles) + '<br>' + rulesText() +
      '<br>夜晚顺序：' + nightOrderText() + '</div>';
    if (ph === 'day' && V.me && V.me.alive) {
      if (has(['discuss', 'pk', 'e_speech', 'e_withdraw', 'e_pk'], d.stage)) items += btn('自爆（仅狼人可用）', 'boom');
      if (d.stage === 'discuss') items += btn('骑士决斗（仅骑士可用）', 'duel');
    }
    items += btn(FX.bgm.muted ? '打开背景音乐' : '关闭背景音乐', 'snd');
    if (host && ph === 'lobby') items += btn('试音', 'test');
    if (host && ph === 'night') items += btn('跳过当前环节（有人没反应时用）', 'skip');
    if (host && ph !== 'lobby') items += btn('结束本局，回到大厅', 'abort');
    items += btn('离开房间', 'leave');
    items += btn('关闭', 'close', 'pri');
    return '<h2>菜单</h2><div class="menu stack">' + items + '</div>';
  }

  function configHtml() {
    var c = V.config, roles = c.roles, ids = order();
    var cur = JSON.stringify(ids.map(function (r) { return roles[r] || 0; }));
    var chips = info.presets.map(function (p, i) {
      var same = JSON.stringify(ids.map(function (r) { return p.roles[r] || 0; })) === cur;
      return '<button class="chip' + (same ? ' on' : '') + '" data-act="preset" data-i="' + i + '">' + esc(p.name) + '</button>';
    }).join('');
    function group(title, pred) {
      var list = info.roles.filter(pred);
      var count = list.reduce(function (a, r) { return a + (roles[r.id] || 0); }, 0);
      return '<div class="grp">' + title + '<span>' + count + ' 人</span></div>' + list.map(function (r) {
        var v = roles[r.id] || 0, multi = r.id === 'wolf' || r.id === 'villager';
        return '<div class="step' + (v ? ' on' : '') + '"><button class="nm" data-act="role-info" data-r="' + r.id + '">' + av(r.id) + '<span>' + r.name + '<small>点名字看技能</small></span></button>' +
          '<div class="ctl"><button data-act="step" data-r="' + r.id + '" data-d="-1"' + (v <= 0 ? ' disabled' : '') + '>−</button><b>' + v + '</b>' +
          '<button data-act="step" data-r="' + r.id + '" data-d="1"' + ((!multi && v >= 1) || V.n >= 18 ? ' disabled' : '') + '>+</button></div></div>';
      }).join('');
    }
    function seg(key, opts) {
      return '<div class="seg">' + opts.map(function (o) {
        return '<button class="' + (String(c[key]) === o[0] ? 'on' : '') + '" data-act="opt" data-k="' + key + '" data-v="' + o[0] + '">' + o[1] + '</button>';
      }).join('') + '</div>';
    }
    return '<h2>板子：共 ' + V.n + ' 人</h2>' +
      (V.err ? '<div class="warn-t" style="margin-bottom:10px">' + esc(V.err) + '</div>' : '<div class="hint" style="margin-bottom:10px">' + boardText(roles) + '</div>') +
      '<div class="seg-t">常规板子（点一下直接套用）</div><div class="chips">' + chips + '</div>' +
      '<div class="seg-t">自定义：每个身份几张</div>' +
      group('狼人阵营', function (r) { return r.team === 'wolf'; }) +
      group('平民', function (r) { return r.kind === 'villager'; }) +
      group('神职', function (r) { return r.kind === 'god'; }) +
      '<div class="seg-t">警长竞选（上警）</div>' + seg('sheriff', [['true', '有'], ['false', '没有']]) +
      '<div class="seg-t">女巫自救</div>' + seg('witch_self_save', [['first', '仅首夜'], ['never', '不可以'], ['always', '可以']]) +
      '<div class="seg-t">狼人获胜条件</div>' + seg('win', [['side', '屠边（神或民死光）'], ['all', '屠城（好人死光）']]) +
      '<div style="height:16px"></div>' + btn('完成', 'close', 'pri');
  }

  function confirm(o) { ui.sheet = { type: 'confirm', title: o.title, text: o.text, ok: o.ok || '确定', danger: o.danger, run: o.run }; paint(); }
  // 只是给人看一段说明；关掉以后回到原来的弹层
  function note(title, text) {
    var box = sheetEl.querySelector('.box');
    ui.cfgTop = box ? box.scrollTop : 0;
    ui.sheet = { type: 'confirm', title: title, text: text, back: ui.sheet };
    paint();
  }

  // ------------------------------------------------------------ 点击处理

  function settle(target, badge) {
    var data = { target: target || 0 };
    if (badge !== undefined) data.badge = badge;
    return act('settle', data);
  }

  function onAct(a, ds) {
    var seat = +ds.seat || 0, d = V && V.day, p = V && V.night && V.night.prompt, t = ui.picks[0];
    switch (a) {
      // 首页
      case 'create': return doCreate();
      case 'join': return doJoin();
      case 'claim': return doClaim(seat);
      case 'claim-back': ui.claim = null; return paint();

      // 通用
      case 'unlock': return;                     // 全局点击已经处理了解锁
      case 'snd': FX.bgm.toggle(); lastHtml = ''; lastSheet = ''; return paint();
      case 'replay': return playIntro();
      case 'close': ui.sheet = (ui.sheet && ui.sheet.back) || null; return paint();
      case 'qr': ui.sheet = { type: 'qr' }; return paint();
      case 'menu': ui.sheet = { type: 'menu' }; return paint();
      case 'confirm-ok': var run = ui.sheet && ui.sheet.run; ui.sheet = null; paint(); return run && run();
      case 'pick':
        var max = p && p.ui === 'pick' ? p.count : 1;
        if (has(ui.picks, seat)) ui.picks = ui.picks.filter(function (x) { return x !== seat; });
        else if (max === 1) ui.picks = [seat];
        else if (ui.picks.length < max) ui.picks = ui.picks.concat([seat]);
        else ui.picks = [ui.picks[1], seat];
        return paint();
      case 'mode-cancel': ui.mode = null; ui.picks = []; return paint();
      case 'take-host': return act('take_host');
      case 'leave':
        return confirm({ title: '离开房间？', text: '游戏进行中离开，其他人会卡住。', ok: '离开', danger: true, run: function () {
          if (V && V.phase === 'lobby') act('stand', {}, true);
          leave();
        } });

      // 大厅
      case 'sit': return act('sit', { seat: seat });
      case 'stand': return confirm({ title: '离开 ' + seat + ' 号座位？', ok: '离座', run: function () { act('stand'); } });
      case 'kick':
        return confirm({ title: '请 ' + seat + ' 号 ' + esc(seatOf(seat).name) + ' 离座？', text: '他可以重新选座位。', ok: '请离', run: function () { act('kick', { seat: seat }); } });
      case 'config': ui.sheet = { type: 'config' }; return paint();
      case 'preset': return act('config', { roles: info.presets[+ds.i].roles });
      case 'step':
        var roles = JSON.parse(JSON.stringify(V.config.roles));
        roles[ds.r] = Math.max(0, (roles[ds.r] || 0) + (+ds.d));
        return act('config', { roles: roles });
      case 'opt':
        var o = {};
        o[ds.k] = ds.k === 'sheriff' ? ds.v === 'true' : ds.v;
        return act('config', o);
      case 'role-info': return note(role(ds.r).name, medal(ds.r) + esc(role(ds.r).desc));
      case 'test': ui.sheet = null; paint(); return act('test');
      case 'deal': return act('deal');

      // 发牌
      case 'seen': return act('seen');
      case 'start-night': return act('start_night');
      case 'force-night':
        return confirm({ title: '不等了，直接天黑？', text: '还有人没确认看过身份。', ok: '直接开始', run: function () { act('start_night', { force: true }); } });

      // 夜晚
      case 'night-ok': return act('night', { ok: true });
      case 'night-go': return ui.picks.length === p.count && act('night', { targets: ui.picks });
      case 'night-skip': return confirm({ title: esc(p.skip) + '？', ok: esc(p.skip), run: function () { act('night', { skip: true }); } });
      case 'wolf-pick':
        if (ui.mode === 'extra') { ui.mode = null; return act('wolf_extra', { target: seat }); }
        return act('wolf_pick', { target: seat });
      case 'wolf-none': return act('wolf_pick', { target: 0 });
      case 'wolf-ok': return act('wolf_confirm');
      case 'wolf-extra':
        if (ui.mode === 'extra') { ui.mode = null; return paint(); }
        if (p.extra) return act('wolf_extra', { target: 0 });
        ui.mode = 'extra';
        return paint();
      case 'witch-save':
        return confirm({ title: '用解药救 ' + p.victim + ' 号？', text: '解药只有一瓶。', ok: '救他', run: function () { act('witch', { save: true }); } });
      case 'witch-poison': ui.mode = 'poison'; ui.picks = []; return paint();
      case 'witch-back': ui.mode = null; ui.picks = []; return paint();
      case 'witch-poison-ok': return t && act('witch', { poison: t });
      case 'witch-none': return confirm({ title: '今晚不用药？', ok: '不用', run: function () { act('witch', {}); } });
      case 'skip':
        return confirm({ title: '跳过当前环节？', text: '只在有人睡着了或手机出问题时用。被跳过的角色今晚视为没有行动。', ok: '跳过', danger: true, run: function () { act('skip'); } });

      // 警长竞选
      case 'elect-run': return act('elect_run', { run: ds.v === '1' });
      case 'elect-wd': return act('elect_withdraw', { out: ds.v === '1' });
      case 'elect-next': return act('elect_next');
      case 'elect-close':
        return confirm({ title: '不等了？', text: '还没操作的人按默认处理。', ok: '继续', run: function () { act('elect_close'); } });
      case 'elect-vote-ok': return t && act('elect_vote', { target: t });
      case 'elect-vote-none': return confirm({ title: '确定弃票？', ok: '弃票', run: function () { act('elect_vote', { target: 0 }); } });
      case 'order': return act('order', { i: +ds.i });

      // 出局确认
      case 'settle-ok': return settle(0);
      case 'shot-ok':
        return t && confirm({ title: '带走 ' + t + ' 号？', ok: '开枪', danger: true, run: function () {
          if (d.settle.mine.badge) { ui.shot = t; ui.picks = []; paint(); } else settle(t);
        } });
      case 'shot-none':
        return confirm({ title: '不发动技能？', ok: '不发动', run: function () {
          if (d.settle.mine.badge) { ui.shot = 0; ui.picks = []; paint(); } else settle(0);
        } });
      case 'badge-ok': return t && settle(ui.shot || 0, t);
      case 'badge-tear':
        return confirm({ title: '撕掉警徽？', text: '之后本局没有警长。', ok: '撕掉', danger: true, run: function () { settle(ui.shot || 0, 0); } });

      // 白天
      case 'start-vote': return act('start_vote');
      case 'vote-ok': return t && act('vote', { target: t });
      case 'vote-none': return confirm({ title: '确定弃票？', ok: '弃票', run: function () { act('vote', { target: 0 }); } });
      case 'end-vote':
        return confirm({ title: '现在结束投票？', text: '还没投的人算弃票。', ok: '结束投票', run: function () { act('end_vote'); } });
      case 'boom':
        ui.sheet = null;
        if (V.me && V.me.role === 'whitewolf') { ui.mode = 'ww'; ui.picks = []; return paint(); }
        return confirm({ title: '确定自爆？', text: '你会亮出狼人身份并出局，今天直接进入黑夜。只有狼人能自爆。', ok: '自爆', danger: true, run: function () { act('boom'); } });
      case 'ww-ok':
        return confirm({ title: t ? '自爆并带走 ' + t + ' 号？' : '不带人，直接自爆？', ok: '自爆', danger: true, run: function () {
          act('boom', { target: t || 0 }).then(function () { ui.mode = null; ui.picks = []; paint(); });
        } });
      case 'duel':
        ui.sheet = null;
        if (!V.me || V.me.role !== 'knight') { paint(); return toast('只有骑士可以决斗'); }
        ui.mode = 'duel'; ui.picks = [];
        return paint();
      case 'duel-ok':
        return t && confirm({ title: '和 ' + t + ' 号决斗？', text: '整局只有一次机会。', ok: '决斗', danger: true, run: function () {
          act('duel', { target: t }).then(function () { ui.mode = null; ui.picks = []; paint(); });
        } });

      // 结束
      case 'again': return act('again');
      case 'abort':
        return confirm({ title: '结束本局？', text: '所有人回到大厅，座位保留。', ok: '结束本局', danger: true, run: function () { act('abort'); } });
    }
  }

  document.addEventListener('click', function (e) {
    Speaker.unlock();
    FX.bgm.unlock();
    keepAwake();
    var el = e.target.closest ? e.target.closest('[data-act]') : null;
    if (!el || el.disabled) return;
    onAct(el.getAttribute('data-act'), el.dataset);
  });

  document.addEventListener('input', function (e) {
    if (e.target.id === 'in-name') ui.name = e.target.value;
    if (e.target.id === 'in-code') {
      var v = e.target.value.replace(/\D/g, '').slice(0, 4);
      if (v !== e.target.value) e.target.value = v;
      ui.code = v;
    }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT') e.target.blur();
  });

  // 按住看身份：按下显示，松手、手指滑走、切到后台都会立刻藏起来
  document.addEventListener('pointerdown', function (e) {
    var el = e.target.closest ? e.target.closest('[data-hold]') : null;
    if (!el) return;
    ui.peek = true;
    ui.peeked = true;
    paintPeek();
  });
  function unpeek() {
    if (!ui.peek) return;
    ui.peek = false;
    paint();
  }
  ['pointerup', 'pointercancel'].forEach(function (t) { document.addEventListener(t, unpeek); });
  window.addEventListener('blur', unpeek);
  document.addEventListener('contextmenu', function (e) { e.preventDefault(); });

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState !== 'visible') return unpeek();
    keepAwake();
    if (cred && (!es || es.readyState !== 1)) connect();    // 手机从后台回来，立刻重连
  });

  // 微信安卓版会按系统字号放大网页，这里固定回标准大小
  function fixWeixinFont() {
    try {
      window.WeixinJSBridge.invoke('setFontSizeCallback', { fontSize: 0 });
      window.WeixinJSBridge.on('menu:setfont', function () {
        window.WeixinJSBridge.invoke('setFontSizeCallback', { fontSize: 0 });
      });
    } catch (e) { /* 不在微信里 */ }
  }
  if (window.WeixinJSBridge) fixWeixinFont(); else document.addEventListener('WeixinJSBridgeReady', fixWeixinFont);

  // ------------------------------------------------------------ 启动

  Speaker.init();
  fetch('/api/info').then(function (r) { return r.json(); }).then(function (j) {
    info = j;
    j.roles.forEach(function (r) { ROLE[r.id] = r; new Image().src = avSrc(r.id); });
    ['cardback', 'frame_dark', 'frame_red', 'frame_gold', 'token_dim', 'token_red', 'ring_red', 'ring_gold', 'cross', 'sun',
      'potion_save', 'potion_poison', 'emblem_good', 'emblem_wolf', 'badge_sheriff', 'stamp_red', 'stamp_green', 'torn']
      .forEach(function (f) { new Image().src = 'art/' + f + '.svg'; });
    lastHtml = ''; lastSheet = '';
    paint();
  }).catch(function () { /* 稍后刷新页面即可 */ });

  if (saved.pid && saved.code && (!ui.code || ui.code === saved.code)) {
    cred = { code: saved.code, pid: saved.pid, token: saved.token, name: saved.name };
    ui.code = saved.code;
    recheck();                                   // 刷新页面或手机杀掉浏览器后，自动回到原来的座位
  }
  // 开场动画：每个标签页第一次打开首页时播一次，点标题可以重播
  var seen = false;
  try { seen = sessionStorage.getItem('lrs:intro') === '1'; sessionStorage.setItem('lrs:intro', '1'); } catch (e) { /* 无痕模式 */ }
  if (!cred && !seen) playIntro();
  paint();
})();
