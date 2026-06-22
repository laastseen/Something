async function addToPlaylistLocal(select, mediaId) {
    const playlistId = select.value;
    if (!playlistId) return;
    const formData = new FormData();
    formData.append('playlist_id', playlistId);
    formData.append('media_id', mediaId);
    const res = await fetch('/api/playlist/add', { method: 'POST', body: formData });
    if (res.ok) alert('Добавлено в плейлист');
    else alert('Не удалось добавить');
    select.value = '';
}

async function submitCommentLocal(mediaId) {
    const field = document.getElementById('comment-field');
    const text = field?.value.trim();
    if (!text) return;
    const formData = new FormData();
    formData.append('media_id', mediaId);
    formData.append('text', text);
    const res = await fetch('/api/comment', { method: 'POST', body: formData });
    if (res.ok) location.reload();
    else alert('Ошибка комментария');
}

async function addTagLocal(mediaId) {
    const input = document.getElementById('new-tag-input');
    const name = input?.value.trim();
    if (!name) return;
    const formData = new FormData();
    formData.append('media_id', mediaId);
    formData.append('name', name);
    const res = await fetch('/api/tag/add', { method: 'POST', body: formData });
    if (res.ok) location.reload();
}

async function toggleAuthorTag(mediaId) {
    const res = await fetch('/api/tag/author', {
        method: 'POST',
        body: new URLSearchParams({ media_id: mediaId }),
    });
    const data = await res.json();
    if (res.ok) location.reload();
    else alert(data.message || 'Не удалось изменить персональный тег');
}

document.addEventListener('DOMContentLoaded', () => {
    const cf = document.getElementById('comment-field');
    const mediaId = document.querySelector('[data-media-id]');
    if (cf) {
        const id = window.location.pathname.split('/').pop();
        cf.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') submitCommentLocal(parseInt(id, 10));
        });
    }

    const reportModal = document.getElementById('report-modal');
    const openReport = document.getElementById('open-report-modal');
    const closeReport = document.querySelector('.close-report-modal');
    const reportForm = document.getElementById('report-form');

    if (openReport && reportModal) {
        openReport.onclick = () => { reportModal.style.display = 'block'; if (typeof lucide !== 'undefined') lucide.createIcons(); };
    }
    if (closeReport && reportModal) {
        closeReport.onclick = () => { reportModal.style.display = 'none'; };
        window.addEventListener('click', (e) => { if (e.target === reportModal) reportModal.style.display = 'none'; });
    }
    if (reportForm) {
        reportForm.onsubmit = async (e) => {
            e.preventDefault();
            const res = await fetch('/api/report', { method: 'POST', body: new FormData(reportForm) });
            const data = await res.json();
            if (res.ok) {
                alert(data.message || 'Жалоба отправлена');
                reportModal.style.display = 'none';
                reportForm.reset();
            } else {
                alert(data.message || data.detail || 'Ошибка');
            }
        };
    }
});
