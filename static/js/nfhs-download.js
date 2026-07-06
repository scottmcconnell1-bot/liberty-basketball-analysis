/**
 * Shared NFHS Network login, lookup, and download UI.
 * Used on Scouting and Film Tool pages.
 */
(function () {
    function el(id) {
        return document.getElementById(id);
    }

    function initNfhsDownload(config) {
        const prefix = config.prefix || 'nfhs-';
        const ids = {
            loggedIn: prefix + 'logged-in',
            loginForm: prefix + 'login-form',
            lookupSection: prefix + 'lookup-section',
            email: prefix + 'email',
            password: prefix + 'password',
            loginStatus: prefix + 'login-status',
            userEmail: prefix + 'user-email',
            gameId: prefix + 'game-id',
            gameInfo: prefix + 'game-info',
            downloadStatus: prefix + 'download-status',
        };

        function showLoggedIn(email) {
            const loggedIn = el(ids.loggedIn);
            const loginForm = el(ids.loginForm);
            const lookupSection = el(ids.lookupSection);
            if (loggedIn) loggedIn.style.display = 'block';
            if (loginForm) loginForm.style.display = 'none';
            if (lookupSection) lookupSection.style.display = 'block';
            if (el(ids.userEmail)) el(ids.userEmail).textContent = email;
        }

        function showLoginForm() {
            const loggedIn = el(ids.loggedIn);
            const loginForm = el(ids.loginForm);
            const lookupSection = el(ids.lookupSection);
            if (loggedIn) loggedIn.style.display = 'none';
            if (loginForm) loginForm.style.display = 'block';
            if (lookupSection) lookupSection.style.display = 'none';
        }

        function checkCredentials() {
            return fetch('/api/scouting/nfhs/credentials')
                .then(r => r.json())
                .then(data => {
                    if (data.has_credentials) {
                        showLoggedIn(data.email);
                    } else {
                        showLoginForm();
                    }
                })
                .catch(() => showLoginForm());
        }

        function login() {
            const email = el(ids.email)?.value.trim();
            const password = el(ids.password)?.value || '';
            const status = el(ids.loginStatus);
            if (!email || !password) {
                if (status) status.innerHTML = '<span class="text-error">Enter email and password</span>';
                return;
            }
            if (status) status.textContent = 'Logging in...';
            fetch('/api/scouting/nfhs/credentials', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password }),
            })
                .then(r => r.json())
                .then(result => {
                    if (result.status === 'saved') {
                        if (status) status.innerHTML = '<span class="text-success">✅ ' + result.message + '</span>';
                        if (el(ids.password)) el(ids.password).value = '';
                        showLoggedIn(email);
                    } else if (status) {
                        status.innerHTML = '<span class="text-error">❌ ' + (result.error || 'Login failed') + '</span>';
                    }
                })
                .catch(err => {
                    if (status) status.innerHTML = '<span class="text-error">❌ ' + err.message + '</span>';
                });
        }

        function logout() {
            fetch('/api/scouting/nfhs/credentials', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: '', password: '' }),
            }).then(() => showLoginForm());
        }

        function lookupGame() {
            const gameId = el(ids.gameId)?.value.trim();
            if (!gameId) {
                alert('Enter an NFHS GameID or URL');
                return;
            }
            const info = el(ids.gameInfo);
            const status = el(ids.downloadStatus);
            if (info) info.innerHTML = '🔍 Looking up game...';
            if (status) status.textContent = '';

            fetch('/api/scouting/nfhs/lookup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ game_id: gameId }),
            })
                .then(r => r.json())
                .then(result => {
                    if (result.error) {
                        if (info) {
                            info.innerHTML = '<span class="text-error">❌ ' + result.error + '</span>';
                        }
                        if (result.needs_login) showLoginForm();
                        return;
                    }
                    if (!info) return;
                    let html = '<div class="game-info-box" style="background:var(--color-surface,#1a1a2e);padding:12px;border-radius:8px;margin-top:8px;border:1px solid var(--color-border,#333)">';
                    html += '<h3 style="margin:0 0 8px 0;font-size:1rem">' + (result.away_team || '?') + ' @ ' + (result.home_team || '?') + '</h3>';
                    html += '<table style="width:100%;font-size:13px">';
                    html += '<tr><td><strong>Game ID:</strong></td><td>' + result.game_id + '</td></tr>';
                    if (result.score) html += '<tr><td><strong>Score:</strong></td><td>' + result.score + '</td></tr>';
                    if (result.gender) html += '<tr><td><strong>Gender:</strong></td><td>' + result.gender + '</td></tr>';
                    if (result.level) html += '<tr><td><strong>Level:</strong></td><td>' + result.level + '</td></tr>';
                    if (result.date) html += '<tr><td><strong>Date:</strong></td><td>' + result.date + '</td></tr>';
                    if (result.status) html += '<tr><td><strong>Status:</strong></td><td>' + result.status + '</td></tr>';
                    html += '<tr><td><strong>VOD:</strong></td><td>' + (result.vod_available ? '✅ Available' : '❌ Not available') + '</td></tr>';
                    html += '</table></div>';
                    info.innerHTML = html;
                })
                .catch(err => {
                    if (info) info.innerHTML = '<span class="text-error">❌ ' + err.message + '</span>';
                });
        }

        function downloadFilm() {
            const gameId = el(ids.gameId)?.value.trim();
            if (!gameId) {
                alert('Enter an NFHS GameID or URL');
                return;
            }
            const status = el(ids.downloadStatus);
            if (status) status.innerHTML = '⏳ Downloading… this may take several minutes.';

            fetch('/api/scouting/nfhs/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ game_id: gameId }),
            })
                .then(r => r.json())
                .then(result => {
                    if (result.error) {
                        if (status) status.innerHTML = '<span class="text-error">❌ ' + result.error + '</span>';
                        if (result.needs_login) showLoginForm();
                        return;
                    }
                    const sizeMB = (result.file_size / 1024 / 1024).toFixed(1);
                    const savedNote = result.already_saved ? ' (already in library)' : '';
                    let html = '<span class="text-success">✅ Saved for review' + savedNote + '! Size: ' + sizeMB + ' MB</span>';
                    if (result.redirect_url) {
                        html += '<div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap;">';
                        html += '<a class="btn btn-sm btn-primary" href="' + result.redirect_url + '">Open in Film Tool</a>';
                        html += '<a class="btn btn-sm btn-secondary" href="' + (result.videos_url || '/videos') + '">All Videos</a>';
                        html += '</div>';
                    }
                    if (status) status.innerHTML = html;
                    if (typeof config.onDownloadComplete === 'function') {
                        config.onDownloadComplete(result);
                    }
                })
                .catch(err => {
                    if (status) status.innerHTML = '<span class="text-error">❌ ' + err.message + '</span>';
                });
        }

        el(prefix + 'login-btn')?.addEventListener('click', login);
        el(prefix + 'logout-btn')?.addEventListener('click', logout);
        el(prefix + 'lookup-btn')?.addEventListener('click', lookupGame);
        el(prefix + 'download-btn')?.addEventListener('click', downloadFilm);

        checkCredentials();

        return { checkCredentials, login, logout, lookupGame, downloadFilm };
    }

    window.initNfhsDownload = initNfhsDownload;
})();
