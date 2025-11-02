// Centralized status helpers for the bottom status bar
(function () {
  let statusTimer = null;
  let statusStartTs = null;

  function setStatus(msg) {
    const sb = document.getElementById('statusBar');
    if (sb) sb.value = msg || '';
  }

  function startStatusProgress(prefix) {
    stopStatusProgress();
    statusStartTs = Date.now();
    setStatus(`${prefix} (0.0s)...`);
    statusTimer = setInterval(() => {
      const s = ((Date.now() - statusStartTs) / 1000).toFixed(1);
      setStatus(`${prefix} (${s}s)...`);
    }, 200);
  }

  function stopStatusProgress(finalMsg) {
    if (statusTimer) {
      clearInterval(statusTimer);
      statusTimer = null;
    }
    if (typeof finalMsg === 'string') setStatus(finalMsg);
  }

  function setUIBusy(busy) {
    const ids = [
      // Applicants
      'browseBtn','refreshBtn','selectAllBtn','extractBtn','matchBtn',
      // Roles
      'roleBrowseBtn','roleRefreshBtn','roleSelectAllBtn','roleExtractBtn','roleMatchBtn',
      // Tabs
      'tabApplicants','tabRoles'
    ];
    ids.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.disabled = !!busy;
    });
    // Also toggle all buttons as a safety net (in case new buttons are added without IDs)
    document.querySelectorAll('button').forEach(btn => { btn.disabled = !!busy; });
  }

  // Expose to global scope so inline code can call them
  window.setStatus = setStatus;
  window.startStatusProgress = startStatusProgress;
  window.stopStatusProgress = stopStatusProgress;
  window.setUIBusy = setUIBusy;
})();
