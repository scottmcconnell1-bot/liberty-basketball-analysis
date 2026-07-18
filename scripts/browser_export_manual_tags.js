// Paste into browser Console on http://127.0.0.1:8080/film (same browser you used for tagging).
(function () {
  const payload = {
    exportedAt: new Date().toISOString(),
    savedGames: JSON.parse(localStorage.getItem('filmToolSavedGamesV20260423final') || '[]'),
    autosave: JSON.parse(localStorage.getItem('filmToolCurrentAutosaveV20260423final') || 'null'),
    lastGameId: localStorage.getItem('filmToolLastGameIdV20260423final'),
  };
  const tagCount = (payload.savedGames || []).reduce((n, g) => n + (g.rows || []).length, 0)
    + (payload.autosave && payload.autosave.rows ? payload.autosave.rows.length : 0);
  if (!tagCount) {
    alert('No manual tags in THIS browser. Try Chrome vs Edge, then run again.');
    return;
  }
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'liberty-manual-tags-backup.json';
  a.click();
  alert('Downloaded liberty-manual-tags-backup.json with ' + tagCount + ' tags.\nMove it to Desktop\\Liberty-Transfer\\tag-exports\\');
})();
