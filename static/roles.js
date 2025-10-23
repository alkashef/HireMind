// Roles tab logic for UI parity with applicants
// Handles UI for roles: selection, extraction, table rendering

const rolesSelected = new Set();
let roleLastSelectedIndex = null;
let rolesDuplicateCount = 0;
let rolesTableRows = [];

function updateRolesFooter(total) {
  const countEl = document.getElementById('roleFileCount');
  const totalNum = Number(total) || 0;
  const selNum = rolesSelected.size || 0;
  const extractedNum = document.querySelectorAll('#roleList .item.extracted').length || 0;
  const dupText = rolesDuplicateCount > 0 ? ` | ${rolesDuplicateCount} duplicates found` : '';
  countEl.textContent = `${totalNum} file${totalNum === 1 ? '' : 's'} | ${selNum} selected | ${extractedNum} extracted${dupText}`;
}

function markExtractedInRolesList() {
  try {
    // Use only 'filename' key from get_public_rows, compare case-insensitively
    const extractedSet = new Set((rolesTableRows || []).map(r => (r.filename || '').toString().toLowerCase()));
    document.querySelectorAll('#roleList .item').forEach(el => {
      const p = decodeURIComponent(el.getAttribute('data-path') || '');
      const name = p.split(/[\\/]/).pop().toLowerCase();
      el.classList.toggle('extracted', extractedSet.has(name));
    });
  } catch (_) {}
}

async function highlightRolesDuplicates(files) {
  try {
    const r = await fetch('/api/hashes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ files }),
    });
    const j = await r.json();
    const list = Array.isArray(j.duplicates_all) ? j.duplicates_all : (j.duplicates || []);
    const dups = new Set(list.map(f => {
      // Normalize to basename for matching
      return (f || '').toString().split(/[\\/]/).pop();
    }));
    rolesDuplicateCount = Number(j.duplicate_count || list.length || 0);
    document.querySelectorAll('#roleList .item').forEach(el => {
      const p = decodeURIComponent(el.getAttribute('data-path'));
      const name = p.split(/[\\/]/).pop();
      el.classList.toggle('duplicate', dups.has(name));
    });
  } catch (e) {
    rolesDuplicateCount = 0;
  } finally {
    const items = Array.from(document.querySelectorAll('#roleList .item'));
    updateRolesFooter(items.length);
  }
}

document.getElementById('roleExtractBtn').addEventListener('click', async () => {
  const picked = Array.from(rolesSelected);
  if (picked.length === 0) {
    setStatus('Select one or more role files to extract.');
    alert('Select one or more role files to extract.');
    return;
  }
  try {
    setUIBusy(true);
    setStatus('Extracting roles...');
    const r = await fetch('/api/roles/extract', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ files: picked }),
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'Roles extraction failed');
    await refreshRolesExtracted();
    if (Array.isArray(j.errors) && j.errors.length) {
      setStatus(`Roles extraction completed with ${j.errors.length} error${j.errors.length === 1 ? '' : 's'}; saved ${j.saved}.`);
    } else {
      setStatus(`Roles extraction completed successfully; saved ${j.saved}.`);
    }
  } catch (e) {
    setStatus(`Error: ${e.message || e}`);
  } finally {
    setUIBusy(false);
  }
});

async function refreshRolesExtracted() {
  try {
    setStatus('Loading extracted roles...');
    const r = await fetch('/api/roles/extract', { method: 'GET' });
    const j = await r.json();
    rolesTableRows = Array.isArray(j.rows) ? j.rows : [];
    markExtractedInRolesList();
    const items = Array.from(document.querySelectorAll('#roleList .item'));
    // Re-highlight duplicates after extraction
    const files = items.map(el => decodeURIComponent(el.getAttribute('data-path')));
    await highlightRolesDuplicates(files);
    updateRolesFooter(items.length);
    // If there's a single selected role, render its details in the right pane
    const selected = Array.from(rolesSelected);
    if (selected.length === 1) {
      renderRoleDetailsForPath(selected[0]);
    } else {
      renderRoleDetailsForPath(null);
    }
    setStatus('Ready');
  } catch (e) {
    setStatus(`Error loading extracted roles: ${e.message || e}`);
  }
}

// tab activation is handled centrally in static/main.js

function renderRolesList(folder, files) {
  const box = document.getElementById('roleList');
  document.getElementById('roleFolderPath').value = folder || '';
  rolesSelected.clear();
  updateRolesFooter(0);
  if (!folder) {
    box.innerHTML = '<div class="muted">No folder selected.</div>';
    updateRolesFooter(0);
    return;
  }
  if (!files || files.length === 0) {
    box.innerHTML = `<div class="muted">No .pdf or .docx files in: ${folder}</div>`;
    updateRolesFooter(0);
    return;
  }
  box.innerHTML = files.map((f, i) => {
    const name = (f || '').toString().split(/[\\/]/).pop();
    return `<div class="item" data-index="${i}" data-path="${encodeURIComponent(f)}">${name}</div>`;
  }).join('');
  updateRolesFooter(files.length);
  markExtractedInRolesList();
  highlightRolesDuplicates(files);
  const items = Array.from(box.querySelectorAll('.item'));
  const clearAll = () => {
    items.forEach(node => node.classList.remove('selected'));
    rolesSelected.clear();
  };
  const toggleOne = (node) => {
    const p = decodeURIComponent(node.getAttribute('data-path'));
    if (node.classList.contains('selected')) {
      node.classList.remove('selected');
      rolesSelected.delete(p);
    } else {
      node.classList.add('selected');
      rolesSelected.add(p);
    }
  };
  const selectOne = (node) => {
    clearAll();
    const p = decodeURIComponent(node.getAttribute('data-path'));
    node.classList.add('selected');
    rolesSelected.add(p);
  };
  const selectRange = (startIdx, endIdx) => {
    clearAll();
    const [a, b] = startIdx <= endIdx ? [startIdx, endIdx] : [endIdx, startIdx];
    for (let i = a; i <= b; i++) {
      const node = items[i];
      const p = decodeURIComponent(node.getAttribute('data-path'));
      node.classList.add('selected');
      rolesSelected.add(p);
    }
  };
  items.forEach(el => {
    el.addEventListener('click', (ev) => {
      const idx = Number(el.getAttribute('data-index'));
      if (ev.shiftKey && roleLastSelectedIndex !== null && !Number.isNaN(idx)) {
        selectRange(roleLastSelectedIndex, idx);
      } else if (ev.ctrlKey || ev.metaKey) {
        toggleOne(el);
      } else {
        selectOne(el);
      }
      roleLastSelectedIndex = idx;
      updateRolesFooter(files.length);
      // Render details pane when a single file is selected
      if (rolesSelected.size === 1) {
        renderRoleDetailsForPath(Array.from(rolesSelected)[0]);
      } else {
        renderRoleDetailsForPath(null);
      }
    });
  });
}

// Render details for a single role into the two detail columns to match applicants UI
function renderRoleDetailsForPath(path) {
  const col1 = document.getElementById('roleTablesCol1');
  if (!col1) return;
  col1.innerHTML = '';
  if (!path) return;
  const basename = (path || '').toString().split(/[\\/]/).pop();
  const row = (rolesTableRows || []).find(r => {
    const fn = (r.filename || '').toString();
    return fn === basename || fn.endsWith(basename);
  });
  if (!row) {
    col1.innerHTML = `<div class="muted">No extracted data for: ${basename}</div>`;
    return;
  }

  function mkTable(title, pairs) {
    const th = `<div class="table-title">${title}</div>`;
    const rows = pairs.map(([k, v]) => `<tr><td>${k}</td><td>${v || ''}</td></tr>`).join('');
    return `${th}<div class="table-wrap"><table class="data-table"><tbody>${rows}</tbody></table></div>`;
  }

  const meta = [
    ['ID', row.id || ''],
    ['Filename', row.filename || ''],
    ['Timestamp', row.timestamp || ''],
  ];
  const title = [['Role title', row.role_title || '']];

  col1.innerHTML = mkTable('Role', title) + mkTable('Metadata', meta) + mkTable('Additional', [['Note', 'No additional extracted fields']]);
}
