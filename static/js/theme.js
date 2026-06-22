(function () {
    const KEY = 'something-theme';
    const saved = localStorage.getItem(KEY);
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.setAttribute('data-theme', saved || (prefersDark ? 'dark' : 'light'));
})();

function refreshLucideIcons() {
    if (typeof lucide !== 'undefined') lucide.createIcons();
}

function updateThemeToggleIcon() {
    const btn = document.getElementById('theme-toggle');
    if (!btn) return;
    const dark = document.documentElement.getAttribute('data-theme') === 'dark';
    btn.innerHTML = `<i data-lucide="${dark ? 'sun' : 'moon'}" id="theme-toggle-icon"></i>`;
    refreshLucideIcons();
}

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('something-theme', theme);
    updateThemeToggleIcon();
}

document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('theme-toggle');
    if (btn) {
        btn.addEventListener('click', () => {
            const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
            setTheme(next);
        });
    }
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const sidebar = document.getElementById('sidebar');
    const sidebarBackdrop = document.getElementById('sidebar-backdrop');
    const mainContainer = document.getElementById('main-container');

    function setSidebarOpen(isOpen) {
        if (!sidebar) return;
        sidebar.classList.toggle('open', isOpen);
        if (mainContainer) mainContainer.classList.toggle('with-sidebar', isOpen);
        if (sidebarBackdrop) {
            sidebarBackdrop.classList.toggle('visible', isOpen);
            sidebarBackdrop.hidden = !isOpen;
        }
    }

    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', () => {
            setSidebarOpen(!sidebar.classList.contains('open'));
        });
    }
    if (sidebarBackdrop) {
        sidebarBackdrop.addEventListener('click', () => setSidebarOpen(false));
    }
    refreshLucideIcons();
    updateThemeToggleIcon();
});
