document.addEventListener('DOMContentLoaded', () => {
    if (typeof Feed !== 'undefined' && typeof feedConfig !== 'undefined') {
        Feed.init(feedConfig);
    }

    // Поиск
    const searchInput = document.getElementById('search-input');
    const searchBtn = document.getElementById('search-button');

    function performSearch() {
        const query = searchInput.value.trim();
        const urlParams = new URLSearchParams(window.location.search);
        const type = urlParams.get('type');
        
        let url = '/';
        if (query) {
            url += `?q=${encodeURIComponent(query)}`;
            if (type) url += `&type=${type}`;
        } else if (type) {
            url += `?type=${type}`;
        }
        window.location.href = url;
    }

    if (searchBtn && searchInput) {
        searchBtn.addEventListener('click', performSearch);
        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') performSearch();
        });
    }

    // Логика модального окна загрузки
    const modal = document.getElementById('upload-modal');
    const openBtn = document.getElementById('open-upload-modal');
    const closeBtn = document.querySelector('.close-modal');
    const form = document.getElementById('upload-form');

    if (openBtn && modal && closeBtn) {
        openBtn.onclick = () => modal.style.display = 'block';
        closeBtn.onclick = () => modal.style.display = 'none';
        window.onclick = (event) => {
            if (event.target == modal) modal.style.display = 'none';
        }
    }

    const thumbInput = document.getElementById('upload-thumbnail');
    const thumbPreview = document.getElementById('thumbnail-preview');
    const thumbPreviewImg = document.getElementById('thumbnail-preview-img');
    const uploadType = document.getElementById('upload-type');
    const uploadFile = document.getElementById('upload-file');
    let mainFilePreviewUrl = null;

    function updateThumbnailHint() {
        const hint = document.getElementById('thumbnail-hint');
        const thumbGroup = document.getElementById('thumbnail-group');
        if (!uploadType) return;
        const t = uploadType.value;
        if (thumbGroup) {
            thumbGroup.hidden = t === 'document';
        }
        if (!hint) return;
        if (t === 'image') {
            hint.textContent = 'Необязательно: если не выбрать, превью = само изображение.';
        } else if (t === 'video') {
            hint.textContent = 'Обложка для карточки в ленте (JPG, PNG, WebP, GIF).';
        } else if (t === 'audio') {
            hint.textContent = 'Обложка альбома для аудио — отображается в ленте (JPG, PNG, WebP, GIF).';
        } else if (t === 'document') {
            hint.textContent = 'PDF, TXT, MD, JSON и изображения откроются на странице просмотра. Остальные форматы — только скачивание.';
            if (uploadFile) {
                uploadFile.accept = '.pdf,.txt,.md,.markdown,.json,.csv,.xml,.yaml,.yml,.log,.html,.htm,.png,.jpg,.jpeg,.gif,.webp,.svg';
            }
        } else {
            hint.textContent = 'Для документов в ленте используется стандартная иконка.';
        }
        if (t !== 'document' && uploadFile) {
            uploadFile.removeAttribute('accept');
        }
    }

    function showThumbPreview(url) {
        if (!thumbPreview || !thumbPreviewImg) return;
        thumbPreviewImg.src = url;
        thumbPreview.hidden = false;
    }

    if (uploadType) {
        uploadType.addEventListener('change', () => {
            updateThumbnailHint();
            if (uploadType.value === 'image' && mainFilePreviewUrl) {
                showThumbPreview(mainFilePreviewUrl);
            }
        });
        updateThumbnailHint();
    }

    if (uploadFile) {
        uploadFile.addEventListener('change', (e) => {
            if (mainFilePreviewUrl) URL.revokeObjectURL(mainFilePreviewUrl);
            mainFilePreviewUrl = null;
            const file = e.target.files[0];
            if (file && file.type.startsWith('image/') && uploadType?.value === 'image' && !thumbInput?.files?.length) {
                mainFilePreviewUrl = URL.createObjectURL(file);
                showThumbPreview(mainFilePreviewUrl);
            }
        });
    }

    if (thumbInput) {
        thumbInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file && file.type.startsWith('image/')) {
                showThumbPreview(URL.createObjectURL(file));
            } else if (thumbPreview) {
                thumbPreview.hidden = true;
            }
        });
    }

    if (form) {
        form.onsubmit = async (e) => {
            e.preventDefault();
            const formData = new FormData(form);
            const t = uploadType?.value;
            const hasThumb = thumbInput?.files?.length > 0;
            if (t === 'video' && !hasThumb) {
                if (!confirm('Без обложки будет стандартная иконка видео. Продолжить?')) return;
            }
            if (t === 'audio' && !hasThumb) {
                if (!confirm('Без обложки будет стандартная иконка аудио. Продолжить?')) return;
            }
            try {
                const response = await fetch('/upload', { method: 'POST', body: formData });
                const result = await response.json();
                if (response.ok) {
                    alert('Успешно загружено!');
                    location.reload();
                } else {
                    alert(result.message || 'Ошибка при загрузке');
                }
            } catch (error) {
                alert('Произошла ошибка');
            }
        };
    }

});

// Глобальные функции для страниц просмотра
async function submitLike(mediaId, isLike) {
    const res = await fetch("/api/like", { 
        method: "POST", 
        body: new URLSearchParams({'media_id': mediaId, 'is_like': isLike}) 
    });
    const data = await res.json();
    if (res.ok) {
        document.getElementById("likes-count").innerText = data.likes.likes;
        document.getElementById("dislikes-count").innerText = data.likes.dislikes;
        
        const likeBtn = document.getElementById("like-btn");
        const dislikeBtn = document.getElementById("dislike-btn");
        
        if (data.action === "added" || data.action === "updated") {
            if (isLike === 1) {
                likeBtn.classList.add("active-like");
                dislikeBtn.classList.remove("active-dislike");
            } else {
                dislikeBtn.classList.add("active-dislike");
                likeBtn.classList.remove("active-like");
            }
        } else if (data.action === "removed") {
            likeBtn.classList.remove("active-like");
            dislikeBtn.classList.remove("active-dislike");
        }
    } else {
        alert(data.message || "Нужна авторизация");
        if (res.status === 403) window.location.href = "/login";
    }
}

async function voteTag(mediaId, tagId, delta) {
    const res = await fetch('/api/tag/vote', { 
        method: 'POST', 
        body: new URLSearchParams({'media_id': mediaId, 'tag_id': tagId, 'delta': delta}) 
    });
    if (res.ok) {
        location.reload();
    } else {
        const data = await res.json();
        alert(data.message || "Ошибка (возможно, нужна авторизация)");
    }
}
