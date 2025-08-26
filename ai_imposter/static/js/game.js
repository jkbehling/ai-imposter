function startTimer(timerStart, timerEnd) {
    const progress = document.querySelector('progress');
    const total = Math.max(0, timerEnd - timerStart);
    // Optional: cancel prior RAF if partial re-renders
    if (window._stageTimerRAF) cancelAnimationFrame(window._stageTimerRAF);

    function tick() {
        const now = Date.now();
        let remaining = timerEnd - now;
        if (remaining < 0) remaining = 0;
        const percent = total > 0 ? Math.round((remaining / total) * 100) : 0;
        if (progress) progress.value = percent;
        if (remaining > 0) {
            window._stageTimerRAF = requestAnimationFrame(tick);
        }
    }

    tick();
}