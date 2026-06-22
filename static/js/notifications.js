(function () {
    const wrap = document.getElementById('notifications-wrap');
    const btn = document.getElementById('notifications-btn');
    const panel = document.getElementById('notifications-panel');
    const list = document.getElementById('notifications-list');
    const badge = document.getElementById('notifications-badge');
    const markAllBtn = document.getElementById('notifications-mark-read');
    if (!wrap || !btn || !panel || !list) return;

    let open = false;
    let pollTimer = null;

    const TYPE_LABELS = {
        channel_upload: 'Новая публикация',
    };

    function escapeHtml(s) {
        const d = document.createElement('div');
        d.textContent = s || '';
        return d.innerHTML;
    }

    function formatTime(iso) {
        if (!iso) return '';
        const d = new Date(iso.replace(' ', 'T'));
        if (Number.isNaN(d.getTime())) return iso.slice(0, 16);
        const now = new Date();
        const diff = (now - d) / 1000;
        if (diff < 60) return 'только что';
        if (diff < 3600) return `${Math.floor(diff / 60)} мин назад`;
        if (diff < 86400) return `${Math.floor(diff / 3600)} ч назад`;
        return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
    }

    function setBadge(count) {
        if (!badge) return;
        if (count > 0) {
            badge.hidden = false;
            badge.textContent = count > 99 ? '99+' : String(count);
        } else {
            badge.hidden = true;
        }
    }

    function renderItems(items) {
        if (!items.length) {
            list.innerHTML = '<p class="notifications-empty">Пока нет уведомлений. Подпишитесь на каналы — мы сообщим о новых публикациях.</p>';
            return;
        }
        list.innerHTML = items.map((item) => `
            <a href="/view/${item.media_id}" class="notification-item${item.is_read ? '' : ' unread'}" data-id="${item.id}" role="menuitem">
                <div class="notification-thumb" style="background-image:url('${escapeHtml(item.thumbnail || '')}')"></div>
                <div class="notification-body">
                    <div class="notification-title">${escapeHtml(item.media_title)}</div>
                    <div class="notification-meta">${escapeHtml(item.author_name)} · ${escapeHtml(TYPE_LABELS[item.type] || 'Обновление')}</div>
                    <div class="notification-time">${escapeHtml(formatTime(item.created_at))}</div>
                </div>
            </a>
        `).join('');
        list.querySelectorAll('.notification-item').forEach((el) => {
            el.addEventListener('click', () => {
                const id = el.dataset.id;
                if (id) markRead([parseInt(id, 10)]);
            });
        });
    }

    async function fetchCount() {
        try {
            const res = await fetch('/api/notifications/unread-count');
            if (res.status === 401) {
                wrap.hidden = true;
                return null;
            }
            if (!res.ok) return null;
            wrap.hidden = false;
            const data = await res.json();
            setBadge(data.unread || 0);
            return data.unread || 0;
        } catch (_) {
            return null;
        }
    }

    async function fetchList() {
        list.innerHTML = '<p class="notifications-empty">Загрузка…</p>';
        try {
            const res = await fetch('/api/notifications');
            if (!res.ok) {
                list.innerHTML = '<p class="notifications-empty">Не удалось загрузить</p>';
                return;
            }
            const data = await res.json();
            renderItems(data.items || []);
            setBadge(data.unread || 0);
        } catch (_) {
            list.innerHTML = '<p class="notifications-empty">Ошибка сети</p>';
        }
    }

    async function markRead(ids) {
        try {
            const body = ids && ids.length ? new URLSearchParams({ ids: ids.join(',') }) : new URLSearchParams();
            const res = await fetch('/api/notifications/read', { method: 'POST', body });
            if (res.ok) {
                const data = await res.json();
                setBadge(data.unread || 0);
                if (open) fetchList();
            }
        } catch (_) {}
    }

    function closePanel() {
        open = false;
        panel.hidden = true;
        btn.setAttribute('aria-expanded', 'false');
    }

    function openPanel() {
        open = true;
        panel.hidden = false;
        btn.setAttribute('aria-expanded', 'true');
        fetchList().then(() => markRead());
        if (typeof lucide !== 'undefined') lucide.createIcons();
    }

    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (open) closePanel();
        else openPanel();
    });

    if (markAllBtn) {
        markAllBtn.addEventListener('click', (e) => {
            e.preventDefault();
            markRead();
        });
    }

    document.addEventListener('click', (e) => {
        if (open && !wrap.contains(e.target)) closePanel();
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && open) closePanel();
    });

    async function init() {
        const unread = await fetchCount();
        if (unread !== null) {
            if (typeof lucide !== 'undefined') lucide.createIcons();
            pollTimer = setInterval(fetchCount, 60000);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
