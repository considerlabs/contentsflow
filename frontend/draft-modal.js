(function () {
  // ── CSS ────────────────────────────────────────────────────────
  var styleEl = document.createElement('style');
  styleEl.textContent = [
    '.dm-overlay{position:fixed;inset:0;background:rgba(15,23,42,.42);z-index:200;display:none;align-items:center;justify-content:center;padding:24px}',
    '.dm-overlay.open{display:flex}',
    '.dm-modal{background:#fff;border-radius:14px;width:100%;max-width:780px;max-height:90vh;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 24px 80px rgba(15,23,42,.24)}',
    '.dm-header{padding:18px 22px;border-bottom:1px solid #e7ebf3;display:flex;align-items:center;gap:10px}',
    '.dm-header h2{flex:1;font-size:16px;font-weight:900;margin:0}',
    '.dm-body{padding:18px 22px;overflow-y:auto;flex:1}',
    '.dm-body pre{white-space:pre-wrap;font-family:"Courier New",monospace;font-size:13px;line-height:1.75;background:#f8fafc;border:1px solid #edf1f7;border-radius:9px;padding:16px;margin:0}',
    '.dm-footer{padding:15px 22px;border-top:1px solid #e7ebf3;display:flex;gap:9px;align-items:flex-end}',
    '.dm-footer textarea{flex:1;min-height:64px;resize:none;font-size:13px;border:1.5px solid #dce2ee;border-radius:8px;padding:8px 12px;font-family:inherit;outline:none}',
    '.dm-actions{display:flex;flex-direction:column;gap:7px}',
    '.dm-btn-close{background:#f0f2f8;color:#445;padding:7px 14px;border-radius:7px;border:none;cursor:pointer;font-size:13px;font-weight:600;flex-shrink:0}',
    '.dm-btn-close:hover{background:#e4e8f0}',
    '.dm-btn-approve{background:#dcfce7;color:#15803d;padding:8px 14px;border-radius:8px;border:none;cursor:pointer;font-size:13px;font-weight:800}',
    '.dm-btn-approve:hover{background:#bbf7d0}',
    '.dm-btn-revise{background:#fef9c3;color:#854d0e;padding:8px 14px;border-radius:8px;border:none;cursor:pointer;font-size:13px;font-weight:800}',
    '.dm-btn-revise:hover{background:#fef08a}',
    '.dm-btn-reject{background:#fee2e2;color:#dc2626;padding:8px 14px;border-radius:8px;border:none;cursor:pointer;font-size:13px;font-weight:800}',
    '.dm-btn-reject:hover{background:#fecaca}',
    '.dm-toast{position:fixed;bottom:24px;right:24px;background:#111827;color:#fff;padding:12px 18px;border-radius:10px;font-size:13px;font-weight:800;transform:translateY(80px);opacity:0;transition:all .25s;z-index:999;pointer-events:none}',
    '.dm-toast.show{transform:translateY(0);opacity:1}',
  ].join('');
  document.head.appendChild(styleEl);

  // ── HTML ───────────────────────────────────────────────────────
  var wrap = document.createElement('div');
  wrap.innerHTML =
    '<div class="dm-overlay" id="dm-overlay">' +
      '<div class="dm-modal">' +
        '<div class="dm-header">' +
          '<span id="dm-badge"></span>' +
          '<h2 id="dm-title">초안 검수</h2>' +
          '<button class="dm-btn-close" id="dm-close-btn">닫기</button>' +
        '</div>' +
        '<div class="dm-body"><pre id="dm-body-text">로딩 중...</pre></div>' +
        '<div class="dm-footer" id="dm-footer" style="display:none">' +
          '<textarea id="dm-memo" placeholder="수정 요청 내용"></textarea>' +
          '<div class="dm-actions">' +
            '<button class="dm-btn-approve" id="dm-btn-approve">승인·발행</button>' +
            '<button class="dm-btn-revise" id="dm-btn-revise">수정 요청</button>' +
            '<button class="dm-btn-reject" id="dm-btn-reject">반려</button>' +
          '</div>' +
        '</div>' +
      '</div>' +
    '</div>' +
    '<div class="dm-toast" id="dm-toast"></div>';
  document.body.appendChild(wrap);

  // ── State ──────────────────────────────────────────────────────
  var _id = null;
  var _onReview = null;
  var CH_LABEL = { blog: '블로그', newsletter: '뉴스레터', youtube: '유튜브', shortform: '인스타그램' };

  // ── Helpers (function declarations — hoisted, safe to reference anywhere) ──
  function _toast(msg) {
    var el = document.getElementById('dm-toast');
    el.textContent = msg;
    el.classList.add('show');
    setTimeout(function () { el.classList.remove('show'); }, 2500);
  }

  function _close() {
    document.getElementById('dm-overlay').classList.remove('open');
    _id = null;
    _onReview = null;
  }

  function _open(id, chType, title, opts) {
    opts = opts || {};
    _id = id;
    _onReview = opts.onReview || null;

    var badge = document.getElementById('dm-badge');
    badge.className = 'ch-badge ' + chType;
    badge.textContent = CH_LABEL[chType] || chType;
    document.getElementById('dm-title').textContent = title || '초안 검수';
    document.getElementById('dm-body-text').textContent = '로딩 중...';
    document.getElementById('dm-memo').value = '';
    document.getElementById('dm-footer').style.display = 'none';
    document.getElementById('dm-overlay').classList.add('open');

    var token = localStorage.getItem('cf_access_token') || '';
    fetch('/api/drafts/' + id, {
      headers: Object.assign(
        { 'Content-Type': 'application/json' },
        token ? { Authorization: 'Bearer ' + token } : {}
      )
    })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        document.getElementById('dm-body-text').textContent = data.body_md || '(내용 없음)';
        if (data.status === 'review') {
          document.getElementById('dm-footer').style.display = 'flex';
        }
      })
      .catch(function (e) {
        document.getElementById('dm-body-text').textContent = '로드 실패: ' + e.message;
      });
  }

  function _review(action) {
    if (!_id) return;
    var memo = document.getElementById('dm-memo').value.trim();
    if (action === 'revision' && !memo) { _toast('수정 요청 내용을 입력해 주세요.'); return; }
    var token = localStorage.getItem('cf_access_token') || '';
    fetch('/api/sessions/drafts/' + _id + '/review', {
      method: 'POST',
      headers: Object.assign(
        { 'Content-Type': 'application/json' },
        token ? { Authorization: 'Bearer ' + token } : {}
      ),
      body: JSON.stringify({ action: action, memo: memo || null }),
    })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function () {
        var labels = { approved: '승인·발행됐습니다', revision: '수정 요청을 보냈습니다', rejected: '반려됐습니다' };
        _toast(labels[action]);
        _close();
        if (_onReview) _onReview(action);
      })
      .catch(function (e) { _toast(e.message); });
  }

  // ── Event listeners (all functions defined above — safe) ────────
  document.getElementById('dm-overlay').addEventListener('click', function (e) {
    if (e.target === this) _close();
  });
  document.getElementById('dm-close-btn').addEventListener('click', _close);
  document.getElementById('dm-btn-approve').addEventListener('click', function () { _review('approved'); });
  document.getElementById('dm-btn-revise').addEventListener('click', function () { _review('revision'); });
  document.getElementById('dm-btn-reject').addEventListener('click', function () { _review('rejected'); });

  // ── Public API ─────────────────────────────────────────────────
  window.openDraftModal = _open;
  window.closeDraftModal = _close;
})();
