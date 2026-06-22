(function () {
    var KEY = 'something-cookie-consent';
    var banner = document.getElementById('cookie-banner');
    var btn = document.getElementById('cookie-accept');
    if (!banner || !btn) return;

    if (localStorage.getItem(KEY) === 'accepted') return;

    banner.hidden = false;
    document.body.classList.add('cookie-banner-visible');

    btn.addEventListener('click', function () {
        localStorage.setItem(KEY, 'accepted');
        banner.hidden = true;
        document.body.classList.remove('cookie-banner-visible');
    });
})();
