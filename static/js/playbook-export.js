(function () {
  function delay(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function pickRecorderMimeType() {
    const candidates = [
      'video/webm;codecs=vp9',
      'video/webm;codecs=vp8',
      'video/webm',
      'video/mp4',
    ];
    return candidates.find((type) => window.MediaRecorder && MediaRecorder.isTypeSupported(type)) || '';
  }

  function fileExtensionForMime(mime) {
    if (mime.includes('mp4')) return 'mp4';
    return 'webm';
  }

  async function svgToCanvas(svg, canvas, ctx) {
    const svgData = new XMLSerializer().serializeToString(svg);
    const svgBlob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(svgBlob);
    try {
      await new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => {
          ctx.fillStyle = '#fff';
          ctx.fillRect(0, 0, canvas.width, canvas.height);
          ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
          resolve();
        };
        img.onerror = reject;
        img.src = url;
      });
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  async function recordPlayAnimation(options) {
    const {
      svg,
      steps,
      isFullCourt,
      playName,
      animateToStep,
      renderStep,
      updateStepList,
      setCurrentStep,
      getCurrentStep,
      restorePositions,
      stepPauseMs = 500,
      stepDurationMs = 800,
    } = options;

    if (!window.MediaRecorder) {
      throw new Error('Video recording is not supported in this browser.');
    }
    if (!svg || !steps || steps.length === 0) {
      throw new Error('Nothing to record.');
    }

    const mimeType = pickRecorderMimeType();
    if (!mimeType) {
      throw new Error('No supported video format found for recording.');
    }

    const baseW = 500;
    const baseH = isFullCourt ? 940 : 470;
    const scale = 2;
    const canvas = document.createElement('canvas');
    canvas.width = baseW * scale;
    canvas.height = baseH * scale;
    const ctx = canvas.getContext('2d');

    const stream = canvas.captureStream(30);
    const recorder = new MediaRecorder(stream, { mimeType, videoBitsPerSecond: 4_000_000 });
    const chunks = [];

    const recordingDone = new Promise((resolve) => {
      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) chunks.push(event.data);
      };
      recorder.onstop = () => resolve();
    });

    recorder.start(100);
    const savedStep = getCurrentStep();
    const savedPositions = restorePositions();

    setCurrentStep(0);
    renderStep();
    updateStepList();
    await svgToCanvas(svg, canvas, ctx);
    await delay(450);

    for (let i = 1; i < steps.length; i++) {
      await animateToStep(i, stepDurationMs, async () => {
        await svgToCanvas(svg, canvas, ctx);
      });
      await delay(stepPauseMs);
      await svgToCanvas(svg, canvas, ctx);
    }

    recorder.stop();
    await recordingDone;

    savedPositions();
    setCurrentStep(savedStep);
    renderStep();
    updateStepList();

    const ext = fileExtensionForMime(mimeType);
    const safeName = (playName || 'play').replace(/[^a-z0-9]/gi, '_');
    const blob = new Blob(chunks, { type: mimeType });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `${safeName}.${ext}`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 2000);
    return { mimeType, extension: ext };
  }

  async function copyShareLink(playId, existingUrl) {
    let url = existingUrl;
    if (!url) {
      const resp = await fetch(`/api/playbook/play/${playId}/share`, { method: 'POST' });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.error || 'Could not create share link');
      url = data.url;
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(url);
    } else {
      const input = document.createElement('input');
      input.value = url;
      document.body.appendChild(input);
      input.select();
      document.execCommand('copy');
      input.remove();
    }
    return url;
  }

  window.PlaybookExport = {
    recordPlayAnimation,
    copyShareLink,
  };
})();
