/** Site-wide live AI analysis progress. Updates in place — does not reload the page. */
(function () {
  const POLL_MS = 2000;
  const banner = document.getElementById('analysis-live-banner');
  if (!banner) return;

  const lastStepByKey = {};

  function esc(str) {
    return String(str ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function formatElapsed(startedAt) {
    if (!startedAt) return '';
    const started = new Date(String(startedAt).includes('T') ? startedAt : `${startedAt}Z`);
    if (Number.isNaN(started.getTime())) return '';
    const sec = Math.max(0, Math.floor((Date.now() - started.getTime()) / 1000));
    const hrs = Math.floor(sec / 3600);
    const mins = Math.floor((sec % 3600) / 60);
    const secs = sec % 60;
    if (hrs) return `${hrs}h ${mins}m elapsed`;
    if (mins) return `${mins}m ${secs}s elapsed`;
    return `${secs}s elapsed`;
  }

  function jobTone(jobs) {
    if (!jobs.length) return '';
    if (jobs.some((j) => j.status === 'failed')) return 'is-failed';
    if (jobs.every((j) => j.status === 'completed')) return 'is-done';
    return '';
  }

  function filmHref(job) {
    if (!job.stored_filename) return '/videos';
    const gameId = encodeURIComponent(job.analysis_key || '');
    return `/film/${encodeURIComponent(job.stored_filename)}?game_id=${gameId}`;
  }

  function renderJob(job) {
    const pct = Math.max(0, Math.min(100, Number(job.progress_pct) || 0));
    const waiting = job.status === 'pending' || (job.status === 'running' && pct < 1);
    const live = job.status === 'pending' || job.status === 'running';
    const barClass = [
      'analysis-live-bar',
      waiting ? 'is-indeterminate' : '',
      live ? 'is-live' : '',
    ].filter(Boolean).join(' ');
    const frameText = (job.current_frame != null && job.total_frames)
      ? `Frame ${Number(job.current_frame).toLocaleString()} / ${Number(job.total_frames).toLocaleString()}`
      : '';
    const step = job.progress_step || (
      job.status === 'pending' ? 'Queued — starting AI worker…'
        : job.status === 'completed' ? 'Analysis complete'
          : job.status === 'failed' ? (job.error_message || 'Analysis failed')
            : 'Loading AI models…'
    );
    const prev = lastStepByKey[job.analysis_key];
    if (step && step !== prev) {
      lastStepByKey[job.analysis_key] = step;
    }
    const heartbeat = live
      ? (pct < 1
        ? 'YOLO is loading. Percent appears after the first frames.'
        : 'Frame number updates about every 500 frames — the bar is live if elapsed time keeps moving.')
      : (job.status === 'completed' ? 'Finished. Open Film Tool to review events.' : '');
    const parts = [
      job.status === 'running' ? 'In progress' : job.status === 'pending' ? 'Queued' : job.status === 'completed' ? 'Finished' : 'Failed',
      formatElapsed(job.started_at),
      frameText,
      step,
      heartbeat,
    ].filter(Boolean);
    const pctLabel = job.status === 'completed' ? '100%' : (waiting ? '…' : `${Math.round(pct)}%`);
    return `<div class="analysis-live-job" data-key="${esc(job.analysis_key)}">
      <div class="analysis-live-head">
        <span class="analysis-live-title">${esc(job.display_game || 'AI analysis')}</span>
        <span class="analysis-live-pct">${esc(pctLabel)}</span>
      </div>
      <div class="${barClass}"><span style="width:${waiting ? 35 : pct}%"></span></div>
      <div class="analysis-live-meta">${esc(parts.join(' · '))}
        · <a href="${esc(filmHref(job))}">Open Film Tool</a>
        · <a href="/videos">Video Library</a>
      </div>
    </div>`;
  }

  async function poll() {
    try {
      const resp = await fetch('/api/analysis_jobs', { headers: { Accept: 'application/json' } });
      if (resp.status === 401 || resp.status === 403 || resp.status === 404) return;
      if (!resp.ok) {
        setTimeout(poll, POLL_MS * 3);
        return;
      }
      const data = await resp.json();
      const jobs = Array.isArray(data.jobs) ? data.jobs : [];
      if (!jobs.length) {
        banner.hidden = true;
        banner.className = '';
        banner.innerHTML = '';
        setTimeout(poll, POLL_MS);
        return;
      }
      banner.hidden = false;
      banner.className = `is-visible ${jobTone(jobs)}`.trim();
      banner.innerHTML = jobs.map(renderJob).join('');
    } catch (_err) {
      /* keep last paint; try again */
    }
    setTimeout(poll, POLL_MS);
  }

  poll();
})();
