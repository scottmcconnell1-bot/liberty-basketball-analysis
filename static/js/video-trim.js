(function () {
    const cfg = window.VIDEO_TRIM || {};
    const video = document.getElementById('trimVideo');
    const trimStart = document.getElementById('trimStart');
    const trimEnd = document.getElementById('trimEnd');
    const trimLabel = document.getElementById('trimLabel');
    const trimCurrentTime = document.getElementById('trimCurrentTime');
    const trimDuration = document.getElementById('trimDuration');
    const trimSelectedLength = document.getElementById('trimSelectedLength');
    const trimStatus = document.getElementById('trimStatus');
    const trimProgressShell = document.getElementById('trimProgressShell');
    const trimProgressBar = document.getElementById('trimProgressBar');
    const trimProgressText = document.getElementById('trimProgressText');
    const trimSaveBtn = document.getElementById('trimSaveBtn');
    const trimPreviewBtn = document.getElementById('trimPreviewBtn');

    let durationMs = null;
    let previewing = false;
    let activePoll = null;

    function formatTime(seconds) {
        if (!Number.isFinite(seconds) || seconds < 0) seconds = 0;
        const hrs = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        const secs = (seconds % 60).toFixed(1);
        if (hrs > 0) return `${hrs}:${String(mins).padStart(2, '0')}:${String(secs).padStart(4, '0')}`;
        return `${mins}:${String(secs).padStart(4, '0')}`;
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

    function getRangeMs() {
        const startMs = parseTimeInput(trimStart.value);
        const endMs = parseTimeInput(trimEnd.value);
        return { startMs, endMs };
    }

    function updateSelectedLength() {
        const { startMs, endMs } = getRangeMs();
        if (startMs == null || endMs == null || endMs <= startMs) {
            trimSelectedLength.textContent = '—';
            return;
        }
        trimSelectedLength.textContent = formatTime((endMs - startMs) / 1000);
    }

    function setStatus(message, isError) {
        if (!trimStatus) return;
        trimStatus.textContent = message || '';
        trimStatus.style.color = isError ? '#991b1b' : 'var(--color-text-muted)';
    }

    function setCurrentFromVideo() {
        if (trimCurrentTime && video) trimCurrentTime.textContent = formatTime(video.currentTime || 0);
    }

    function applyDuration(ms) {
        durationMs = ms;
        if (trimDuration) {
            trimDuration.textContent = ms ? `Duration: ${formatTime(ms / 1000)}` : 'Duration: —';
        }
        if (ms && !trimEnd.value) {
            trimEnd.value = formatTime(ms / 1000);
            updateSelectedLength();
        }
    }

    async function loadMeta() {
        try {
            const resp = await fetch(`/api/videos/${encodeURIComponent(cfg.videoId)}/meta`);
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || 'Failed to load video metadata');
            if (data.duration_ms) applyDuration(data.duration_ms);
            if (video && data.video_url) {
                video.src = data.video_url;
                video.load();
            }
        } catch (err) {
            setStatus(err.message, true);
        }
    }

    function setInputFromCurrent(targetInput) {
        if (!video || !targetInput) return;
        targetInput.value = formatTime(video.currentTime || 0);
        updateSelectedLength();
    }

    function startPreview() {
        const { startMs, endMs } = getRangeMs();
        if (startMs == null || endMs == null || endMs <= startMs) {
            alert('Set a valid start and end time first.');
            return;
        }
        previewing = true;
        video.currentTime = startMs / 1000;
        video.play();
        setStatus('Previewing selected range…');
    }

    function stopPreview() {
        previewing = false;
        setStatus('');
    }

    function showProgress(active, text) {
        if (trimProgressShell) trimProgressShell.style.display = active ? 'block' : 'none';
        if (trimProgressText && text) trimProgressText.textContent = text;
        if (trimProgressBar && active) trimProgressBar.style.width = '35%';
    }

    function pollTrimJob(jobId) {
        if (activePoll) clearInterval(activePoll);
        activePoll = setInterval(async () => {
            try {
                const resp = await fetch(`/api/videos/trim/${encodeURIComponent(jobId)}`);
                const job = await resp.json();
                if (!resp.ok) throw new Error(job.error || 'Trim status failed');
                showProgress(true, job.message || 'Trimming…');

                if (job.status === 'complete') {
                    clearInterval(activePoll);
                    activePoll = null;
                    showProgress(true, 'Trim complete! Redirecting…');
                    if (trimProgressBar) trimProgressBar.style.width = '100%';
                    if (trimSaveBtn) trimSaveBtn.disabled = false;
                    setTimeout(() => {
                        window.location.href = job.redirect_url || '/videos';
                    }, 1200);
                } else if (job.status === 'error') {
                    clearInterval(activePoll);
                    activePoll = null;
                    showProgress(false);
                    if (trimSaveBtn) trimSaveBtn.disabled = false;
                    setStatus(job.error || 'Trim failed', true);
                }
            } catch (err) {
                clearInterval(activePoll);
                activePoll = null;
                showProgress(false);
                if (trimSaveBtn) trimSaveBtn.disabled = false;
                setStatus(err.message, true);
            }
        }, 1500);
    }

    async function saveTrim() {
        const { startMs, endMs } = getRangeMs();
        if (startMs == null || endMs == null) {
            alert('Enter or set both start and end times.');
            return;
        }
        if (endMs <= startMs) {
            alert('End time must be after start time.');
            return;
        }
        if (!cfg.ffmpegAvailable) {
            alert('ffmpeg is not installed on this server.');
            return;
        }

        if (trimSaveBtn) trimSaveBtn.disabled = true;
        setStatus('Starting trim…');
        showProgress(true, 'Starting trim…');

        try {
            const resp = await fetch(`/api/videos/${encodeURIComponent(cfg.videoId)}/trim`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    start_ms: startMs,
                    end_ms: endMs,
                    label: trimLabel?.value || 'trimmed',
                }),
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || 'Trim failed to start');
            if (!data.job_id) throw new Error('Trim did not start');
            pollTrimJob(data.job_id);
        } catch (err) {
            showProgress(false);
            if (trimSaveBtn) trimSaveBtn.disabled = false;
            setStatus(err.message, true);
        }
    }

    document.getElementById('trimSetStartBtn')?.addEventListener('click', () => setInputFromCurrent(trimStart));
    document.getElementById('trimSetEndBtn')?.addEventListener('click', () => setInputFromCurrent(trimEnd));
    trimStart?.addEventListener('input', updateSelectedLength);
    trimEnd?.addEventListener('input', updateSelectedLength);
    trimSaveBtn?.addEventListener('click', saveTrim);
    trimPreviewBtn?.addEventListener('click', startPreview);

    video?.addEventListener('timeupdate', () => {
        setCurrentFromVideo();
        if (!previewing) return;
        const { endMs } = getRangeMs();
        if (endMs != null && video.currentTime * 1000 >= endMs - 200) {
            video.pause();
            stopPreview();
        }
    });
    video?.addEventListener('loadedmetadata', () => {
        if (!durationMs && video.duration) applyDuration(Math.round(video.duration * 1000));
    });

    if (video && cfg.videoUrl) {
        video.src = cfg.videoUrl;
        video.load();
    }
    loadMeta();
    updateSelectedLength();
})();
