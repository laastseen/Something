/**
 * Лента: пагинация, превью при наведении, карточки контента.
 */
const Feed = (() => {
    const TYPE_MAP = { videos: 'video', images: 'image', audio: 'audio', documents: 'document' };
    const PREVIEW_MS = 3000;

    let state = {
        grid: null,
        sentinel: null,
        page: 1,
        loading: false,
        hasMore: true,
        config: {},
        gridType: 'videos',
    };

    function escapeHtml(s) {
        const d = document.createElement('div');
        d.textContent = s ?? '';
        return d.innerHTML;
    }

    function metaLine(item, gridType) {
        const views = item.views || 0;
        if (gridType === 'documents') return `Документ · ${item.upload_date || ''}`;
        if (gridType === 'audio') return `${item.author_name || 'Артист'} · Аудио`;
        if (gridType === 'images') return `${item.author_name || 'Автор'} · ${views} просмотров`;
        return `${item.author_name || 'Неизвестный'} · ${views} просмотров`;
    }

    function createCard(item, gridType) {
        const div = document.createElement('article');
        div.className = `content-item vibe-card ${gridType}`;
        const thumb = item.thumbnail || '/static/img/cover-video.svg';
        const iconClass = thumb.includes('/static/img/cover-') ? ' thumbnail-icon' : '';
        const authorLink = item.author_id
            ? `<a href="/author/${item.author_id}" class="card-author-link" onclick="event.stopPropagation()">@${escapeHtml(item.owner_username || item.author_name)}</a>`
            : `<span>@${escapeHtml(item.author_name || 'author')}</span>`;

        div.innerHTML = `
            <div class="thumbnail-wrap">
                <div class="thumbnail${iconClass}" style="background-image:url('${thumb.replace(/'/g, "%27")}')"></div>
            </div>
            <div class="content-info">
                <div class="user-avatar-initial card-avatar">${(item.author_name || 'A')[0].toUpperCase()}</div>
                <div class="content-text">
                    <h3 class="content-title">${escapeHtml(item.title)}</h3>
                    <p class="content-meta card-author">${authorLink}</p>
                    <p class="content-meta">${escapeHtml(metaLine(item, gridType))}</p>
                </div>
            </div>
        `;
        if (item.media_type === 'video' && item.preview_url) {
            div.dataset.previewUrl = item.preview_url;
        }
        div.addEventListener('click', (e) => {
            if (e.target.closest('a')) return;
            window.location.href = `/view/${item.id}`;
        });
        setupHoverPreview(div, item);
        return div;
    }

    function setupHoverPreview(card, item) {
        if (item.media_type !== 'video' || !item.preview_url) return;
        const wrap = card.querySelector('.thumbnail-wrap');
        if (!wrap) return;

        let video = null;
        let stopTimer = null;

        const clearPreview = () => {
            if (stopTimer) clearTimeout(stopTimer);
            stopTimer = null;
            if (video) {
                video.pause();
                video.remove();
                video = null;
            }
            wrap.classList.remove('is-previewing');
        };

        card.addEventListener('mouseenter', () => {
            clearPreview();
            video = document.createElement('video');
            video.className = 'hover-preview-video';
            video.src = item.preview_url;
            video.muted = true;
            video.playsInline = true;
            video.setAttribute('playsinline', '');
            video.preload = 'metadata';
            wrap.appendChild(video);
            wrap.classList.add('is-previewing');
            video.play().catch(() => {});
            stopTimer = setTimeout(() => {
                if (video) {
                    video.pause();
                    try { video.currentTime = 0; } catch (_) {}
                }
            }, PREVIEW_MS);
        });
        card.addEventListener('mouseleave', clearPreview);
    }

    async function fetchPage(page) {
        const cfg = state.config;
        const params = new URLSearchParams({
            type: TYPE_MAP[state.gridType] || 'video',
            page: String(page),
        });
        if (cfg.q) params.set('q', cfg.q);
        if (cfg.tag) params.set('tag', cfg.tag);
        if (cfg.authorId) params.set('author_id', String(cfg.authorId));
        const res = await fetch(`/api/feed?${params}`);
        if (!res.ok) throw new Error('feed error');
        return res.json();
    }

    async function loadMore(append = true) {
        if (!state.grid || state.loading || !state.hasMore) return;
        state.loading = true;
        state.grid.classList.add('is-loading');
        try {
            const data = await fetchPage(state.page);
            if (!append) state.grid.innerHTML = '';
            if (!data.items.length && state.page === 1) {
                state.grid.innerHTML = '<div class="empty-state">Контент пока не найден</div>';
                state.hasMore = false;
                return;
            }
            const empty = state.grid.querySelector('.empty-state');
            if (empty) empty.remove();
            data.items.forEach((item) => state.grid.appendChild(createCard(item, state.gridType)));
            state.hasMore = data.has_more;
            state.page += 1;
        } catch (_) {
            if (state.page === 1) {
                state.grid.innerHTML = '<div class="empty-state">Не удалось загрузить ленту</div>';
            }
        } finally {
            state.loading = false;
            state.grid.classList.remove('is-loading');
        }
    }

    function observeSentinel() {
        if (!state.sentinel || !('IntersectionObserver' in window)) return;
        const obs = new IntersectionObserver((entries) => {
            if (entries[0].isIntersecting) loadMore(true);
        }, { rootMargin: '200px' });
        obs.observe(state.sentinel);
    }

    function bindTabs(buttons) {
        buttons.forEach((btn) => {
            btn.addEventListener('click', () => {
                buttons.forEach((b) => b.classList.remove('active'));
                btn.classList.add('active');
                state.gridType = btn.getAttribute('data-type') || 'videos';
                state.page = 1;
                state.hasMore = true;
                const urlParams = new URLSearchParams(window.location.search);
                const q = urlParams.get('q');
                if (q && !state.config.authorId) {
                    const t = (TYPE_MAP[state.gridType] || 'video');
                    window.location.href = `/?q=${encodeURIComponent(q)}&type=${t}`;
                    return;
                }
                if (state.config.authorId) {
                    const t = TYPE_MAP[state.gridType] || 'video';
                    const base = `/author/${state.config.authorId}`;
                    window.location.href = `${base}?type=${t}`;
                    return;
                }
                loadMore(false);
            });
        });
    }

    const REVERSE_TYPE = { video: 'videos', image: 'images', audio: 'audio', document: 'documents' };

    function init(config, gridId = 'content-grid', sentinelId = 'feed-sentinel') {
        state.config = config || {};
        state.grid = document.getElementById(gridId);
        state.sentinel = document.getElementById(sentinelId);
        state.page = 1;
        state.hasMore = true;
        const fromConfig = REVERSE_TYPE[config?.type] || null;
        if (fromConfig) {
            state.gridType = fromConfig;
            document.querySelectorAll('.category-btn').forEach((btn) => {
                btn.classList.toggle('active', btn.getAttribute('data-type') === fromConfig);
            });
        } else {
            const active = document.querySelector('.category-btn.active');
            state.gridType = active?.getAttribute('data-type') || 'videos';
        }
        if (!state.grid) return;
        loadMore(false);
        observeSentinel();
        bindTabs(document.querySelectorAll('.category-btn'));
        document.querySelectorAll('.rec-section .content-item').forEach((card) => {
            const preview = card.dataset.previewUrl;
            if (preview) setupHoverPreview(card, { media_type: 'video', preview_url: preview });
        });
    }

    return { init, createCard, setupHoverPreview };
})();

async function toggleSubscribe(authorId, btn) {
    const res = await fetch('/api/subscribe', {
        method: 'POST',
        body: new URLSearchParams({ author_id: authorId }),
    });
    const data = await res.json();
    if (!res.ok) {
        alert(data.message || data.detail || 'Войдите, чтобы подписаться');
        if (res.status === 403) window.location.href = '/login';
        return;
    }
    const sub = data.subscribed;
    if (btn) {
        btn.classList.toggle('subscribed', sub);
        btn.innerHTML = sub
            ? '<i data-lucide="bell-off"></i> Отписаться'
            : '<i data-lucide="bell"></i> Подписаться';
        if (typeof lucide !== 'undefined') lucide.createIcons();
    }
    const countEl = document.getElementById('subscriber-count');
    if (countEl) {
        const strong = countEl.querySelector('strong');
        if (strong) strong.textContent = String(data.subscriber_count);
        else countEl.textContent = `${data.subscriber_count} подписчиков`;
    }
}
