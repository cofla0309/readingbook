/* 화면 동작. 페이지는 서버에서 렌더링하고, 여기서는
   진도 갱신 · 알라딘 검색 · 별점 · 세션 편집처럼 새로고침 없이
   끝나야 자연스러운 것만 처리한다. */

/* ── 공용 ────────────────────────────────────────────────── */

export async function api(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch { /* 본문 없는 응답 */ }
  if (!res.ok) {
    const d = data && data.detail;
    const msg = (d && (d.message || d)) || `요청 실패 (${res.status})`;
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    err.payload = d;
    throw err;
  }
  return data;
}

let toastTimer = null;
export function toast(message) {
  let t = document.querySelector('.toast');
  if (!t) {
    t = document.createElement('div');
    t.className = 'toast';
    document.body.appendChild(t);
  }
  t.textContent = message;
  t.classList.add('on');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('on'), 2200);
}

export const esc = (s) =>
  String(s ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const fmt = (n) => Number(n || 0).toLocaleString('ko-KR');

/* ── 진도 갱신 ───────────────────────────────────────────── */
/* 폼 하나가 곧 "오늘 읽은 만큼" 기록이다. 별도 세션 입력 화면이 없다. */

function wireProgressForms(scope = document) {
  scope.querySelectorAll('form[data-progress]').forEach((form) => {
    if (form.dataset.wired) return;
    form.dataset.wired = '1';

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const bookId = form.dataset.progress;
      const input = form.querySelector('input[name="current_page"]');
      const minutesEl = form.querySelector('input[name="minutes"]');
      const btn = form.querySelector('button[type="submit"]');
      const page = parseInt(input.value, 10);
      if (Number.isNaN(page) || page < 0) {
        toast('페이지 수를 숫자로 입력해 주세요.');
        return;
      }

      btn.disabled = true;
      try {
        const book = await api('PATCH', `/api/books/${bookId}/progress`, {
          current_page: page,
          minutes: minutesEl && minutesEl.value ? parseInt(minutesEl.value, 10) : null,
        });
        if (minutesEl) minutesEl.value = '';
        input.value = book.current_page;
        paintProgress(form.closest('[data-book-card]'), book);

        const delta = book.logged_pages;
        toast(
          delta > 0 ? `+${fmt(delta)}p 기록했습니다.`
          : delta < 0 ? `${fmt(delta)}p 로 되돌렸습니다.`
          : '기록했습니다.'
        );

        if (book.completion_suggested) askFinish(book);
        else if (form.dataset.reload) setTimeout(() => location.reload(), 700);
      } catch (err) {
        toast(err.message);
      } finally {
        btn.disabled = false;
      }
    });
  });
}

/** 진도바·남은 쪽수처럼 카드 안에서 바로 바뀌어야 하는 것만 다시 칠한다. */
function paintProgress(card, book) {
  if (!card) return;
  const meter = card.querySelector('.meter > span');
  if (meter && book.progress_pct !== null) meter.style.width = book.progress_pct + '%';
  const now = card.querySelector('[data-now]');
  if (now) now.textContent = fmt(book.current_page);
  const left = card.querySelector('[data-left]');
  if (left && book.pages_left !== null) {
    left.textContent = book.pages_left > 0 ? `${fmt(book.pages_left)}p 남음` : '다 읽었습니다';
  }
  const pct = card.querySelector('[data-pct]');
  if (pct && book.progress_pct !== null) pct.textContent = book.progress_pct + '%';
}

/* ── 완독 확인 ───────────────────────────────────────────── */
/* 마지막 쪽에 닿아도 자동으로 끝내지 않는다. 물어보고 별점을 받는다. */

function askFinish(book) {
  const dlg = document.getElementById('finish-modal');
  if (!dlg) { location.reload(); return; }

  dlg.querySelector('[data-finish-title]').textContent = book.title;
  dlg.dataset.bookId = book.id;
  const dateEl = dlg.querySelector('input[name="finished_on"]');
  if (dateEl) dateEl.value = document.body.dataset.today;
  setStars(dlg.querySelector('.stars'), 0);
  const memo = dlg.querySelector('textarea[name="memo"]');
  if (memo) memo.value = book.memo || '';
  dlg.showModal();
}

function wireFinishModal() {
  const dlg = document.getElementById('finish-modal');
  if (!dlg) return;

  dlg.querySelectorAll('[data-close]').forEach((b) =>
    b.addEventListener('click', () => dlg.close()));

  dlg.querySelector('[data-finish-save]').addEventListener('click', async () => {
    const rating = parseInt(dlg.querySelector('.stars').dataset.value || '0', 10);
    const memo = dlg.querySelector('textarea[name="memo"]').value.trim();
    const finished = dlg.querySelector('input[name="finished_on"]').value;
    try {
      await api('POST', `/api/books/${dlg.dataset.bookId}/finish`, {
        rating: rating || null,
        memo: memo || null,
        finished_on: finished || null,
      });
      dlg.close();
      toast('완독으로 기록했습니다. 축하합니다!');
      setTimeout(() => location.reload(), 600);
    } catch (err) {
      toast(err.message);
    }
  });
}

/* ── 별점 ────────────────────────────────────────────────── */

function setStars(widget, value) {
  if (!widget) return;
  widget.dataset.value = value;
  widget.querySelectorAll('button').forEach((b, i) => {
    b.classList.toggle('on', i < value);
    b.textContent = i < value ? '★' : '☆';
  });
}

function wireStars(scope = document) {
  scope.querySelectorAll('.stars:not(.ro)').forEach((widget) => {
    if (widget.dataset.wired) return;
    widget.dataset.wired = '1';
    setStars(widget, parseInt(widget.dataset.value || '0', 10));

    widget.querySelectorAll('button').forEach((btn, i) => {
      btn.addEventListener('click', async () => {
        // 같은 별을 다시 누르면 별점 해제.
        const next = parseInt(widget.dataset.value || '0', 10) === i + 1 ? 0 : i + 1;
        setStars(widget, next);
        const bookId = widget.dataset.book;
        if (!bookId) return;
        try {
          await api('PATCH', `/api/books/${bookId}`, { rating: next || null });
          toast(next ? `★ ${next}점` : '별점을 지웠습니다.');
        } catch (err) {
          toast(err.message);
        }
      });
    });
  });
}

/* ── 자동 저장되는 입력 (메모·마감일·카테고리 등) ────────── */

function wireAutosave(scope = document) {
  scope.querySelectorAll('[data-autosave]').forEach((input) => {
    if (input.dataset.wired) return;
    input.dataset.wired = '1';

    let timer = null;
    const save = async () => {
      const field = input.dataset.autosave;
      const bookId = input.dataset.book;
      let value = input.value;
      if (input.type === 'number') value = value === '' ? null : parseInt(value, 10);
      try {
        await api('PATCH', `/api/books/${bookId}`, { [field]: value === '' ? null : value });
        input.dataset.dirty = '';
        toast('저장했습니다.');
      } catch (err) {
        toast(err.message);
      }
    };

    const trigger = input.tagName === 'SELECT' || input.type === 'date' ? 'change' : 'input';
    input.addEventListener(trigger, () => {
      clearTimeout(timer);
      timer = setTimeout(save, trigger === 'input' ? 900 : 0);
    });
    input.addEventListener('blur', () => { clearTimeout(timer); if (input.dataset.dirty !== '') save(); });
    input.addEventListener('input', () => { input.dataset.dirty = '1'; });
  });
}

/* ── 상태 전환 / 삭제 ────────────────────────────────────── */

function wireBookActions(scope = document) {
  scope.querySelectorAll('[data-set-status]').forEach((btn) => {
    if (btn.dataset.wired) return;
    btn.dataset.wired = '1';
    btn.addEventListener('click', async () => {
      try {
        await api('PATCH', `/api/books/${btn.dataset.book}`, {
          status: btn.dataset.setStatus,
        });
        location.reload();
      } catch (err) { toast(err.message); }
    });
  });

  scope.querySelectorAll('[data-delete-book]').forEach((btn) => {
    if (btn.dataset.wired) return;
    btn.dataset.wired = '1';
    btn.addEventListener('click', async () => {
      if (!confirm(`"${btn.dataset.title}" 을(를) 기록째 삭제합니다. 되돌릴 수 없습니다.`)) return;
      try {
        await api('DELETE', `/api/books/${btn.dataset.deleteBook}`);
        location.href = '/library';
      } catch (err) { toast(err.message); }
    });
  });
}

/* ── 세션 편집 ───────────────────────────────────────────── */

function wireSessions(scope = document) {
  scope.querySelectorAll('[data-session-save]').forEach((btn) => {
    if (btn.dataset.wired) return;
    btn.dataset.wired = '1';
    btn.addEventListener('click', async () => {
      const row = btn.closest('tr');
      const get = (n) => row.querySelector(`[name="${n}"]`).value;
      try {
        await api('PATCH', `/api/sessions/${btn.dataset.sessionSave}`, {
          log_date: get('log_date'),
          start_page: parseInt(get('start_page'), 10),
          end_page: parseInt(get('end_page'), 10),
          minutes: get('minutes') === '' ? null : parseInt(get('minutes'), 10),
        });
        toast('기록을 고쳤습니다.');
        setTimeout(() => location.reload(), 500);
      } catch (err) { toast(err.message); }
    });
  });

  scope.querySelectorAll('[data-session-delete]').forEach((btn) => {
    if (btn.dataset.wired) return;
    btn.dataset.wired = '1';
    btn.addEventListener('click', async () => {
      if (!confirm('이 날짜 기록을 지웁니다.')) return;
      try {
        await api('DELETE', `/api/sessions/${btn.dataset.sessionDelete}`);
        toast('지웠습니다.');
        setTimeout(() => location.reload(), 400);
      } catch (err) { toast(err.message); }
    });
  });
}

/* ── 책 추가 모달 (알라딘 검색 + 수동 입력) ──────────────── */

function wireAddBook() {
  const dlg = document.getElementById('add-modal');
  if (!dlg) return;

  const openBtns = document.querySelectorAll('[data-open-add]');
  const searchInput = dlg.querySelector('input[name="aladin_q"]');
  const searchBtn = dlg.querySelector('[data-aladin-search]');
  const results = dlg.querySelector('[data-aladin-results]');
  const notice = dlg.querySelector('[data-aladin-notice]');
  const manual = dlg.querySelector('form[data-manual]');
  const toggleManual = dlg.querySelector('[data-toggle-manual]');
  const manualWrap = dlg.querySelector('[data-manual-wrap]');
  const searchWrap = dlg.querySelector('[data-search-wrap]');
  const aladinReady = document.body.dataset.aladinReady === '1';

  const showManual = (prefill = null) => {
    manualWrap.hidden = false;
    if (searchWrap) searchWrap.hidden = true;
    toggleManual.textContent = '← 검색으로 돌아가기';
    toggleManual.dataset.mode = 'manual';
    if (prefill) {
      for (const [k, v] of Object.entries(prefill)) {
        const f = manual.querySelector(`[name="${k}"]`);
        if (f && v != null) f.value = v;
      }
      const pagesField = manual.querySelector('[name="total_pages"]');
      if (!prefill.total_pages && pagesField) {
        notice.hidden = false;
        notice.className = 'notice warn';
        notice.textContent = '알라딘에 이 책의 페이지 수가 없습니다. 책 뒤쪽을 보고 직접 입력해 주세요.';
        manualWrap.appendChild(notice);
        pagesField.focus();
      }
    }
    manual.querySelector('[name="title"]').focus();
  };

  const showSearch = () => {
    manualWrap.hidden = true;
    if (searchWrap) searchWrap.hidden = false;
    toggleManual.textContent = '직접 입력하기';
    toggleManual.dataset.mode = 'search';
  };

  openBtns.forEach((b) => b.addEventListener('click', () => {
    dlg.showModal();
    if (aladinReady) { showSearch(); searchInput.focus(); }
    else showManual();
  }));

  dlg.querySelectorAll('[data-close]').forEach((b) =>
    b.addEventListener('click', () => dlg.close()));

  toggleManual.addEventListener('click', () => {
    if (toggleManual.dataset.mode === 'manual') showSearch();
    else showManual();
  });

  const runSearch = async () => {
    const q = searchInput.value.trim();
    if (!q) return;
    results.innerHTML = '<div class="tiny dim">알라딘에서 찾는 중…</div>';
    notice.hidden = true;

    let data;
    try {
      data = await api('GET', `/api/aladin/search?q=${encodeURIComponent(q)}`);
    } catch (err) {
      data = { ok: false, message: err.message, items: [] };
    }

    if (!data.ok) {
      // 조회가 안 되면 앱을 막지 않고 수동 입력으로 넘긴다.
      results.innerHTML = '';
      notice.hidden = false;
      notice.className = 'notice warn';
      notice.textContent = data.message + ' 직접 입력으로 계속할 수 있습니다.';
      showManual({ title: q });
      return;
    }
    if (!data.items.length) {
      results.innerHTML = '<div class="tiny dim">검색 결과가 없습니다. 직접 입력해 주세요.</div>';
      return;
    }

    results.innerHTML = data.items.map((it, i) => `
      <div class="result-row">
        ${it.cover_url
          ? `<img class="cover" src="${esc(it.cover_url)}" alt="" loading="lazy">`
          : '<div class="cover cover-ph">📕</div>'}
        <div class="body">
          <div class="strong">${esc(it.title)}</div>
          <div class="tiny dim">${esc(it.author || '저자 미상')} · ${esc(it.publisher || '')}</div>
          <div class="tiny dim">
            ${it.total_pages ? `${fmt(it.total_pages)}p` : '<span class="bad">페이지 수 없음 — 직접 입력</span>'}
            ${it.category ? ' · ' + esc(it.category) : ''}
          </div>
        </div>
        <div>
          ${it.owned_book_id
            ? `<a class="btn btn-sm" href="/books/${it.owned_book_id}">서재에 있음</a>`
            : `<button class="btn-sm primary" data-pick="${i}">담기</button>`}
        </div>
      </div>`).join('');

    results.querySelectorAll('[data-pick]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const it = data.items[parseInt(btn.dataset.pick, 10)];
        showManual({
          title: it.title,
          author: it.author,
          publisher: it.publisher,
          isbn13: it.isbn13,
          cover_url: it.cover_url,
          category: it.category,
          total_pages: it.total_pages,
        });
      });
    });
  };

  if (searchBtn) searchBtn.addEventListener('click', runSearch);
  if (searchInput) {
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); runSearch(); }
    });
  }

  manual.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(manual);
    const payload = {};
    for (const [k, v] of fd.entries()) payload[k] = v === '' ? null : v;
    payload.total_pages = payload.total_pages ? parseInt(payload.total_pages, 10) : null;
    payload.current_page = payload.current_page ? parseInt(payload.current_page, 10) : 0;

    const btn = manual.querySelector('button[type="submit"]');
    btn.disabled = true;
    try {
      const book = await api('POST', '/api/books', payload);
      toast(`"${book.title}" 을(를) 담았습니다.`);
      location.href = `/books/${book.id}`;
    } catch (err) {
      notice.hidden = false;
      notice.className = 'notice err';
      notice.textContent = err.message;
      manualWrap.appendChild(notice);
      if (err.payload && err.payload.book_id) {
        notice.innerHTML += ` <a href="/books/${err.payload.book_id}">그 책 보기 →</a>`;
      }
    } finally {
      btn.disabled = false;
    }
  });
}

/* ── 설정 화면 ───────────────────────────────────────────── */

function wireSettings() {
  const form = document.getElementById('goal-form');
  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(form);
      const jobs = [];
      for (const kind of ['yearly_books', 'daily_pages', 'daily_minutes']) {
        const raw = (fd.get(kind) || '').toString().trim();
        if (raw === '' || parseInt(raw, 10) <= 0) {
          jobs.push(api('DELETE', `/api/goals/${kind}`));
        } else {
          jobs.push(api('PUT', '/api/goals', {
            kind,
            target: parseInt(raw, 10),
            period: kind === 'yearly_books' ? (fd.get('year') || null) : null,
          }));
        }
      }
      try {
        await Promise.all(jobs);
        toast('목표를 저장했습니다.');
        setTimeout(() => location.reload(), 600);
      } catch (err) { toast(err.message); }
    });
  }

  const keyForm = document.getElementById('key-form');
  if (keyForm) {
    keyForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const key = keyForm.querySelector('[name="aladin_ttb_key"]').value.trim();
      try {
        await api('PUT', '/api/settings', { aladin_ttb_key: key });
        toast(key ? 'TTB키를 저장했습니다.' : 'TTB키를 지웠습니다.');
        setTimeout(() => location.reload(), 600);
      } catch (err) { toast(err.message); }
    });
  }

  const backupBtn = document.getElementById('backup-btn');
  if (backupBtn) {
    backupBtn.addEventListener('click', async () => {
      backupBtn.disabled = true;
      try {
        const r = await api('POST', '/api/backup');
        const out = document.getElementById('backup-result');
        out.hidden = false;
        out.textContent = `백업 완료 (${r.size_kb} KB) → ${r.path}`;
        toast('백업했습니다.');
      } catch (err) { toast(err.message); }
      finally { backupBtn.disabled = false; }
    });
  }
}

/* ── 서재 필터 ───────────────────────────────────────────── */

function wireLibrary() {
  const sort = document.getElementById('sort-select');
  if (sort) sort.addEventListener('change', () => sort.form.submit());
}

/* ── 부팅 ────────────────────────────────────────────────── */

function boot() {
  wireProgressForms();
  wireFinishModal();
  wireStars();
  wireAutosave();
  wireBookActions();
  wireSessions();
  wireAddBook();
  wireSettings();
  wireLibrary();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
