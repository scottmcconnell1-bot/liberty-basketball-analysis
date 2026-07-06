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
            downloadProgress: prefix + 'download-progress',
            downloadProgressBar: prefix + 'download-progress-bar',
            downloadProgressPct: prefix + 'download-progress-pct',
            downloadProgressPhase: prefix + 'download-progress-phase',
            downloadProgressText: prefix + 'download-progress-text',
            downloadCancelBtn: prefix + 'download-cancel-btn',
            downloadBtn: prefix + 'download-btn',
            downloadFullBtn: prefix + 'download-full-btn',
            downloadOptions: prefix + 'download-options',
            downloadHelp: prefix + 'download-help',
            downloadStart: prefix + 'download-start',
            downloadEnd: prefix + 'download-end',
        };
        let activePoll = null;
        let activeJobId = null;
        let lookupReady = false;
        let lastSiteUrl = null;

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

        function setDownloadBusy(isBusy) {
            const btn = el(ids.downloadBtn);
            const fullBtn = el(ids.downloadFullBtn);
            if (btn) {
                btn.disabled = isBusy || !lookupReady;
                btn.textContent = isBusy ? '⏳ Downloading…' : '📥 Step 3: Download Game Clip';
            }
            if (fullBtn) {
                fullBtn.disabled = isBusy || !lookupReady;
            }
        }

        function setLookupReady(ready, siteUrl) {
            lookupReady = !!ready;
            lastSiteUrl = siteUrl || null;
            const options = el(ids.downloadOptions);
            if (options) options.style.display = ready ? 'block' : 'none';
            setDownloadOptionsVisible(ready && !activeJobId);
            setDownloadBusy(false);
            if (ready) {
                const startInput = el(ids.downloadStart);
                if (startInput) startInput.focus();
            }
        }

        function setDownloadOptionsVisible(show) {
            const options = el(ids.downloadOptions);
            if (options && lookupReady) {
                options.style.display = show ? 'block' : 'none';
            }
        }

        function isTechnicalStatus(text) {
            const value = (text || '').trim();
            if (!value) return false;
            if (value.startsWith('[')) return true;
            const lowered = value.toLowerCase();
            return lowered.includes('cloudfront') || lowered.includes('.ts') || lowered.includes('ffmpeg');
        }

        function friendlyPhase(text, percent) {
            if (!isTechnicalStatus(text)) {
                return text || (percent > 0 ? 'Downloading…' : 'Connecting to NFHS…');
            }
            return percent > 0 ? 'Downloading…' : 'Connecting to NFHS…';
        }

        function formatElapsed(seconds) {
            const mins = Math.floor(seconds / 60);
            const secs = seconds % 60;
            if (mins) return `${mins}m ${secs}s`;
            return `${secs}s`;
        }

        function showProgress(percent, phase, speed, eta, segments, elapsedSec) {
            const shell = el(ids.downloadProgress);
            const bar = el(ids.downloadProgressBar);
            const pctLabel = el(ids.downloadProgressPct);
            const phaseLabel = el(ids.downloadProgressPhase);
            const detail = el(ids.downloadProgressText);
            const cancelBtn = el(ids.downloadCancelBtn);
            const pct = Math.max(0, Math.min(100, percent || 0));
            const indeterminate = pct === 0 && !!activeJobId;
            let phaseText = friendlyPhase(phase, pct);
            if (indeterminate && segments > 0) {
                phaseText = `Downloading segments… (${segments} received)`;
            }

            setDownloadOptionsVisible(false);
            if (shell) {
                shell.style.display = 'block';
                shell.classList.toggle('nfhs-progress-indeterminate', indeterminate);
            }
            if (bar) bar.style.width = indeterminate ? '40%' : `${pct}%`;
            if (pctLabel) pctLabel.textContent = indeterminate ? '—' : `${Math.round(pct)}%`;
            if (phaseLabel) phaseLabel.textContent = phaseText;
            if (detail) {
                const parts = [];
                if (speed) parts.push(speed);
                if (eta) parts.push(`ETA ${eta}`);
                if (indeterminate && elapsedSec != null) parts.push(formatElapsed(elapsedSec));
                detail.textContent = parts.join(' • ');
            }
            if (cancelBtn) cancelBtn.style.display = activeJobId ? 'inline-block' : 'none';
        }

        function hideProgress() {
            const shell = el(ids.downloadProgress);
            const cancelBtn = el(ids.downloadCancelBtn);
            if (shell) shell.style.display = 'none';
            if (cancelBtn) cancelBtn.style.display = 'none';
            activeJobId = null;
            setDownloadOptionsVisible(true);
        }

        function renderDownloadComplete(result) {
            const status = el(ids.downloadStatus);
            const sizeMB = result.file_size ? (result.file_size / 1024 / 1024).toFixed(1) : null;
            const savedNote = result.already_saved ? ' (already in library)' : '';
            let html = '<span class="text-success">✅ Saved for review' + savedNote;
            if (sizeMB) html += '! Size: ' + sizeMB + ' MB';
            html += '</span>';
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
            setLookupReady(false);
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
                        setLookupReady(false);
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
                    html += '</table>';
                    if (result.site_url) {
                        html += '<div style="margin-top:8px;"><a class="btn btn-sm btn-secondary" href="' + result.site_url + '" target="_blank" rel="noopener">▶ Preview on NFHS</a></div>';
                    }
                    html += '</div>';
                    info.innerHTML = html;
                    setLookupReady(true, result.site_url);
                })
                .catch(err => {
                    if (info) info.innerHTML = '<span class="text-error">❌ ' + err.message + '</span>';
                });
        }

        function cancelDownload() {
            if (!activeJobId) return;
            const cancelBtn = el(ids.downloadCancelBtn);
            if (cancelBtn) cancelBtn.disabled = true;
            fetch('/api/scouting/nfhs/download/' + encodeURIComponent(activeJobId) + '/cancel', {
                method: 'POST',
            })
                .then(r => r.json())
                .then(data => {
                    if (data.error) throw new Error(data.error);
                    const status = el(ids.downloadStatus);
                    if (status) status.innerHTML = '<span class="text-muted">Cancelling download…</span>';
                })
                .catch(err => {
                    if (cancelBtn) cancelBtn.disabled = false;
                    const status = el(ids.downloadStatus);
                    if (status) status.innerHTML = '<span class="text-error">❌ ' + err.message + '</span>';
                });
        }

        function pollDownloadJob(jobId) {
            activeJobId = jobId;
            const startedAt = Date.now();
            if (activePoll) clearInterval(activePoll);
            activePoll = setInterval(() => {
                fetch('/api/scouting/nfhs/download/' + encodeURIComponent(jobId))
                    .then(r => r.json())
                    .then(job => {
                        if (job.error && !job.status) {
                            throw new Error(job.error);
                        }
                        const pct = job.percent || 0;
                        const elapsedSec = Math.floor((Date.now() - startedAt) / 1000);
                        showProgress(pct, job.message, job.speed, job.eta, job.segments || 0, elapsedSec);

                        if (job.status === 'complete') {
                            clearInterval(activePoll);
                            activePoll = null;
                            setDownloadBusy(false);
                            hideProgress();
                            renderDownloadComplete(job);
                        } else if (job.status === 'cancelled') {
                            clearInterval(activePoll);
                            activePoll = null;
                            setDownloadBusy(false);
                            hideProgress();
                            const status = el(ids.downloadStatus);
                            if (status) status.innerHTML = '<span class="text-muted">Download cancelled. Set start/end times and try again.</span>';
                        } else if (job.status === 'error') {
                            clearInterval(activePoll);
                            activePoll = null;
                            setDownloadBusy(false);
                            hideProgress();
                            const status = el(ids.downloadStatus);
                            if (status) status.innerHTML = '<span class="text-error">❌ ' + (job.error || 'Download failed') + '</span>';
                        }
                    })
                    .catch(err => {
                        clearInterval(activePoll);
                        activePoll = null;
                        setDownloadBusy(false);
                        hideProgress();
                        const status = el(ids.downloadStatus);
                        if (status) status.innerHTML = '<span class="text-error">❌ ' + err.message + '</span>';
                    });
            }, 1500);
        }

        function parseTimeInput(value) {
            const raw = (value || '').trim();
            if (!raw) return null;
            if (/^\d+(\.\d+)?$/.test(raw)) return Math.round(parseFloat(raw) * 1000);
            const parts = raw.split(':').map((p) => parseFloat(p));
            if (parts.some((n) => Number.isNaN(n))) return null;
            if (parts.length === 2) return Math.round((parts[0] * 60 + parts[1]) * 1000);
            if (parts.length === 3) return Math.round((parts[0] * 3600 + parts[1] * 60 + parts[2]) * 1000);
            return null;
        }

        function downloadFilm(requireTimes) {
            const gameId = el(ids.gameId)?.value.trim();
            if (!gameId) {
                alert('Enter an NFHS GameID or URL');
                return;
            }
            if (activeJobId) {
                alert('A download is already running. Use Cancel Download or wait for it to finish.');
                return;
            }
            if (!lookupReady) {
                alert('Click "Step 1: Look Up Game" first, preview on NFHS, then enter start/end times.');
                return;
            }

            const startMs = parseTimeInput(el(ids.downloadStart)?.value);
            const endMs = parseTimeInput(el(ids.downloadEnd)?.value);
            if (requireTimes) {
                if (startMs == null || endMs == null) {
                    alert('Enter both game start and game end times before downloading.\n\nUse Preview on NFHS to find tip-off and final buzzer.');
                    el(ids.downloadStart)?.focus();
                    return;
                }
                if (endMs <= startMs) {
                    alert('Game end must be after game start.');
                    return;
                }
            } else if (startMs != null || endMs != null) {
                alert('Enter both start and end times, or clear both fields to download the full file.');
                return;
            } else {
                const ok = confirm(
                    'Download the FULL NFHS file?\n\n' +
                    'This is often 2–3 hours and several GB. For a smaller game-only file, click Cancel and enter Start/End times instead.'
                );
                if (!ok) {
                    el(ids.downloadStart)?.focus();
                    return;
                }
            }

            const status = el(ids.downloadStatus);
            if (status) status.innerHTML = '<span class="text-muted">Download runs on the server. You can stay on this page for progress, or check Videos later.</span>';
            setDownloadBusy(true);
            showProgress(0, 'Starting download…', null, null, 0, 0);

            const payload = { game_id: gameId };
            if (startMs != null) payload.start_ms = startMs;
            if (endMs != null) payload.end_ms = endMs;

            fetch('/api/scouting/nfhs/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            })
                .then(r => r.json())
                .then(result => {
                    if (result.error) {
                        setDownloadBusy(false);
                        hideProgress();
                        if (status) status.innerHTML = '<span class="text-error">❌ ' + result.error + '</span>';
                        if (result.needs_login) showLoginForm();
                        return;
                    }
                    if (!result.job_id) {
                        throw new Error('Download did not start');
                    }
                    pollDownloadJob(result.job_id);
                })
                .catch(err => {
                    setDownloadBusy(false);
                    hideProgress();
                    if (status) status.innerHTML = '<span class="text-error">❌ ' + err.message + '</span>';
                });
        }

        el(prefix + 'login-btn')?.addEventListener('click', login);
        el(prefix + 'logout-btn')?.addEventListener('click', logout);
        el(prefix + 'lookup-btn')?.addEventListener('click', lookupGame);
        el(prefix + 'download-btn')?.addEventListener('click', () => downloadFilm(true));
        el(prefix + 'download-full-btn')?.addEventListener('click', () => downloadFilm(false));
        el(prefix + 'download-cancel-btn')?.addEventListener('click', cancelDownload);

        checkCredentials();

        return { checkCredentials, login, logout, lookupGame, downloadFilm };
    }

    window.initNfhsDownload = initNfhsDownload;
})();
