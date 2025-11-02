// Main UI wiring: tab switching, folder list loads, and tiny helpers
(function () {
  async function fetchJSON(url, opts) {
    const r = await fetch(url, opts || {});
    if (!r.ok) {
      const txt = await r.text().catch(() => '');
      throw new Error(txt || `${r.status} ${r.statusText}`);
    }
    return r.json();
  }

  function activateTab(tabId) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    const btn = document.getElementById(tabId);
    if (!btn) return;
    btn.classList.add('active');
    const pane = document.getElementById(btn.getAttribute('aria-controls'));
    if (pane) pane.classList.add('active');
  }

  async function loadRolesList() {
    try {
      if (window.setStatus) window.setStatus('Loading roles list...');
      const j = await fetchJSON('/api/roles/list-files');
      if (typeof renderRolesList === 'function') {
        renderRolesList(j.folder, j.files || []);
      }
      // Ensure extracted rows are loaded and marked
      if (typeof refreshRolesExtracted === 'function') {
        await refreshRolesExtracted();
      }
      if (window.setStatus) window.setStatus('Ready');
    } catch (e) {
      console.error(e);
      if (window.setStatus) window.setStatus(`Error loading roles list: ${e.message || e}`);
    }
  }

  // Applicants UI state and helpers (moved from inline HTML)
  const applicantsSelected = new Set();
  let applicantLastSelectedIndex = null;
  let applicantsDuplicateCount = 0;
  let applicantsTableRows = [];
  let applicantsExtractPollTimer = null;

  function updateApplicantsFooter(total) {
    const countEl = document.getElementById('fileCount');
    const totalNum = Number(total) || 0;
    const selNum = applicantsSelected.size || 0;
    const extractedNum = document.querySelectorAll('#list .item.extracted').length || 0;
    const dupText = applicantsDuplicateCount > 0 ? ` | ${applicantsDuplicateCount} duplicates found` : '';
    if (countEl) countEl.textContent = `${totalNum} file${totalNum === 1 ? '' : 's'} | ${selNum} selected | ${extractedNum} extracted${dupText}`;
  }

  function markExtractedInApplicantsList() {
    try {
      const extractedSet = new Set((applicantsTableRows || []).map(r => (r.cv || '').toString().toLowerCase()));
      document.querySelectorAll('#list .item').forEach(el => {
        const p = decodeURIComponent(el.getAttribute('data-path') || '');
        const name = p.split(/[\\/]/).pop().toLowerCase();
        el.classList.toggle('extracted', extractedSet.has(name));
      });
    } catch (_) {}
  }

  // Render details for a single applicant into the two detail columns
  function renderApplicantDetailsForPath(path) {
    const col1 = document.getElementById('tablesCol1');
    const col2 = document.getElementById('tablesCol2');
    const col3 = document.getElementById('weaviateCol');
    if (!col1 || !col2 || !col3) return;
    // Clear first
    col1.innerHTML = '';
    col2.innerHTML = '';
    col3.innerHTML = '';
    if (!path) return;
    const basename = (path || '').toString().split(/[\\/]/).pop();

    function mkTable(title, pairs) {
      const th = `<div class="table-title">${title}</div>`;
      const rows = pairs.map(([k, v]) => `<tr><td>${k}</td><td>${v || ''}</td></tr>`).join('');
      return `${th}<div class="table-wrap"><table class="data-table"><tbody>${rows}</tbody></table></div>`;
    }

    // If we have recent pipeline fields for this path, prefer them
    const useOverride = window.lastExtractFieldsPath === path && window.lastExtractFieldsRow;
    let row = null;
    if (useOverride) {
      row = window.lastExtractFieldsRow;
    } else {
      // Find matching row by cv (filename) or id
      row = (applicantsTableRows || []).find(r => {
        const cv = (r.cv || '').toString();
        return cv === basename || cv.endsWith(basename);
      });
    }

    if (!row) {
      col1.innerHTML = `<div class="muted">No extracted data for: ${basename}</div>`;
    } else {
      const personal = [
        ['Full name', row.full_name || row.fullname || ''],
        ['First name', row.first_name || ''],
        ['Last name', row.last_name || ''],
        ['Email', row.email || ''],
        ['Phone', row.phone || ''],
      ];
      const professionalism = [
        ['Misspelling count', row.misspelling_count || ''],
        ['Misspelled words', row.misspelled_words || ''],
        ['Visual cleanliness', row.visual_cleanliness || ''],
        ['Professional look', row.professional_look || ''],
        ['Formatting consistency', row.formatting_consistency || ''],
      ];
      const experience = [
        ['Years since graduation', row.years_since_graduation || ''],
        ['Total years experience', row.total_years_experience || ''],
        ['Employer names', row.employer_names || ''],
      ];
      const stability = [
        ['Employers count', row.employers_count || ''],
        ['Avg years per employer', row.avg_years_per_employer || ''],
        ['Years at current employer', row.years_at_current_employer || ''],
      ];
      const socioeconomic = [
        ['Address', row.address || ''],
        ['Alma mater', row.alma_mater || ''],
        ['High school', row.high_school || ''],
        ['Education system', row.education_system || ''],
        ['Second foreign language', row.second_foreign_language || ''],
      ];
      const flags = [
        ['STEM degree', row.flag_stem_degree || ''],
        ['Military service status', row.military_service_status || ''],
        ['Worked at financial institution', row.worked_at_financial_institution || ''],
        ['Worked for Egyptian government', row.worked_for_egyptian_government || ''],
      ];

      // Put some groups in col1 and others in col2 for layout parity
      col1.innerHTML = mkTable('Personal Information', personal) + mkTable('Professionalism', professionalism) + mkTable('Flags', flags);
      col2.innerHTML = mkTable('Experience', experience) + mkTable('Stability', stability) + mkTable('Socioeconomic Standard', socioeconomic);
    }

    // Always attempt to populate Weaviate column for the selected path
    renderWeaviateForPath(path, col3, mkTable);
  }

  function fieldsToRow(fields) {
    const f = fields || {};
    const get = (k) => (f[k] == null ? '' : f[k]);
    return {
      full_name: get('full_name'),
      first_name: get('first_name'),
      last_name: get('last_name'),
      email: get('email'),
      phone: get('phone'),
      misspelling_count: get('misspelling_count'),
      misspelled_words: get('misspelled_words'),
      visual_cleanliness: get('visual_cleanliness'),
      professional_look: get('professional_look'),
      formatting_consistency: get('formatting_consistency'),
      years_since_graduation: get('years_since_graduation'),
      total_years_experience: get('total_years_experience'),
      employer_names: get('employer_names'),
      employers_count: get('employers_count'),
      avg_years_per_employer: get('avg_years_per_employer'),
      years_at_current_employer: get('years_at_current_employer'),
      address: get('address'),
      alma_mater: get('alma_mater'),
      high_school: get('high_school'),
      education_system: get('education_system'),
      second_foreign_language: get('second_foreign_language'),
      flag_stem_degree: get('flag_stem_degree'),
      military_service_status: get('military_service_status'),
      worked_at_financial_institution: get('worked_at_financial_institution'),
      worked_for_egyptian_government: get('worked_for_egyptian_government'),
    };
  }

  async function renderWeaviateForPath(path, col3, mkTable) {
    try {
      const url = '/api/weaviate/cv_by_path?path=' + encodeURIComponent(path);
      const j = await fetchJSON(url);
      const doc = j.document || {};
      const sections = Array.isArray(j.sections) ? j.sections : [];
      const props = doc.attributes || {};
      const docPairs = [
        ['SHA', doc.sha || ''],
        ['Filename', doc.filename || ''],
        ['Full text chars', (doc.full_text || '').length],
      ];
      const attrPairs = Object.entries(props).map(([k,v]) => [k, (Array.isArray(v)||typeof v==='object') ? JSON.stringify(v) : (v||'')]);
      const secPairs = sections.map((s,i) => [s.section_type || `Section ${i+1}`, (s.section_text || '').slice(0, 200) + ((s.section_text||'').length>200?'...':'')]);
      col3.innerHTML = mkTable('Weaviate Document', docPairs) + mkTable('Weaviate Attributes', attrPairs) + mkTable('Weaviate Sections', secPairs);
    } catch (e) {
      col3.innerHTML = `<div class="muted">Weaviate read error: ${e.message || e}</div>`;
    }
  }

  async function highlightApplicantsDuplicates(files) {
    try {
      const r = await fetch('/api/hashes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ files }),
      });
      const j = await r.json();
      const list = Array.isArray(j.duplicates_all) ? j.duplicates_all : (j.duplicates || []);
      const dups = new Set(list.map(f => (f || '').toString().split(/[\\/]/).pop()));
      applicantsDuplicateCount = Number(j.duplicate_count || list.length || 0);
      document.querySelectorAll('#list .item').forEach(el => {
        const p = decodeURIComponent(el.getAttribute('data-path')) || '';
        const name = p.split(/[\\/]/).pop();
        el.classList.toggle('duplicate', dups.has(name));
      });
    } catch (e) {
      applicantsDuplicateCount = 0;
    } finally {
      const items = Array.from(document.querySelectorAll('#list .item'));
      updateApplicantsFooter(items.length);
    }
  }

  function renderApplicantsList(folder, files) {
    const box = document.getElementById('list');
    if (!document.getElementById('folderPath')) return;
    document.getElementById('folderPath').value = folder || '';
    applicantsSelected.clear();
    updateApplicantsFooter(0);
    if (!folder) {
      box.innerHTML = '<div class="muted">No folder selected.</div>';
      updateApplicantsFooter(0);
      return;
    }
    if (!files || files.length === 0) {
      box.innerHTML = `<div class="muted">No .pdf or .docx files in: ${folder}</div>`;
      updateApplicantsFooter(0);
      return;
    }
    box.innerHTML = files.map((f, i) => {
      const name = (f || '').toString().split(/[\\/]/).pop();
      return `<div class="item" data-index="${i}" data-path="${encodeURIComponent(f)}">${name}</div>`;
    }).join('');
    updateApplicantsFooter(files.length);
    markExtractedInApplicantsList();
    highlightApplicantsDuplicates(files);

    const items = Array.from(box.querySelectorAll('.item'));
    const clearAll = () => { items.forEach(n => n.classList.remove('selected')); applicantsSelected.clear(); };
    const toggleOne = (node) => { const p = decodeURIComponent(node.getAttribute('data-path')); if (node.classList.contains('selected')) { node.classList.remove('selected'); applicantsSelected.delete(p); } else { node.classList.add('selected'); applicantsSelected.add(p); } };
    const selectOne = (node) => { clearAll(); const p = decodeURIComponent(node.getAttribute('data-path')); node.classList.add('selected'); applicantsSelected.add(p); };
    const selectRange = (a, b) => { clearAll(); const [s,e] = a<=b?[a,b]:[b,a]; for (let i=s;i<=e;i++){ const n=items[i]; const p=decodeURIComponent(n.getAttribute('data-path')); n.classList.add('selected'); applicantsSelected.add(p);} };
    items.forEach(el => {
      el.addEventListener('click', (ev) => {
        const idx = Number(el.getAttribute('data-index'));
        if (ev.shiftKey && applicantLastSelectedIndex !== null && !Number.isNaN(idx)) {
          selectRange(applicantLastSelectedIndex, idx);
        } else if (ev.ctrlKey || ev.metaKey) {
          toggleOne(el);
        } else {
          selectOne(el);
        }
        applicantLastSelectedIndex = idx;
        updateApplicantsFooter(files.length);
        // If single selection, render details; otherwise clear
        if (applicantsSelected.size === 1) {
          const p = Array.from(applicantsSelected)[0];
          renderApplicantDetailsForPath(p);
        } else {
          renderApplicantDetailsForPath(null);
        }
      });
    });
  }

  async function refreshApplicantsExtracted() {
    try {
      setStatus('Loading extracted applicants...');
      const r = await fetch('/api/extract', { method: 'GET' });
      const j = await r.json();
      applicantsTableRows = Array.isArray(j.rows) ? j.rows : [];
      markExtractedInApplicantsList();
      const items = Array.from(document.querySelectorAll('#list .item'));
      const files = items.map(el => decodeURIComponent(el.getAttribute('data-path')));
      await highlightApplicantsDuplicates(files);
      updateApplicantsFooter(items.length);
      setStatus('Ready');
    } catch (e) {
      setStatus(`Error loading extracted applicants: ${e.message || e}`);
    }
  }

  async function startApplicantsExtractPolling() {
    const startedAt = Date.now();
    const fmtSec = (ms) => `(${Math.floor(ms/1000)} sec) ...`;
    if (applicantsExtractPollTimer) clearInterval(applicantsExtractPollTimer);
    applicantsExtractPollTimer = setInterval(async () => {
      try {
        const r = await fetch('/api/extract/progress', { cache: 'no-store' });
        if (!r.ok) return;
        const j = await r.json();
        const total = Number(j.total || 0);
        const done = Number(j.done || 0);
        const elapsed = fmtSec(Date.now() - startedAt);
        if (window.setStatus) window.setStatus(`extracted ${done} out of ${total} files ${elapsed}`);
        if (!j.active) { clearInterval(applicantsExtractPollTimer); applicantsExtractPollTimer = null; }
      } catch (_) { /* ignore */ }
    }, 500);
  }

  // Applicants button handlers
  document.addEventListener('DOMContentLoaded', () => {
    const browse = document.getElementById('browseBtn');
    const refresh = document.getElementById('refreshBtn');
    const selectAll = document.getElementById('selectAllBtn');
    const extractBtn = document.getElementById('extractBtn');

    if (browse) browse.addEventListener('click', async () => {
      try {
        if (window.setStatus) window.setStatus('Opening folder picker...');
        const d = await fetchJSON('/api/pick-folder');
        if (typeof renderApplicantsList === 'function') renderApplicantsList(d.folder, d.files || []);
        if (typeof refreshApplicantsExtracted === 'function') await refreshApplicantsExtracted();
        if (window.setStatus) window.setStatus('Ready');
      } catch (e) {
        console.error(e);
        if (window.setStatus) window.setStatus(`Error picking folder: ${e.message || e}`);
      }
    });

    if (refresh) refresh.addEventListener('click', async () => { if (window.setStatus) window.setStatus('Refreshing...'); await loadApplicantsList(); });
    if (selectAll) selectAll.addEventListener('click', () => {
      const items = Array.from(document.querySelectorAll('#list .item'));
      applicantsSelected.clear();
      items.forEach(el => { const p = decodeURIComponent(el.getAttribute('data-path')); el.classList.add('selected'); applicantsSelected.add(p); });
      updateApplicantsFooter(items.length);
      if (applicantsSelected.size === 1) {
        renderApplicantDetailsForPath(Array.from(applicantsSelected)[0]);
      } else {
        renderApplicantDetailsForPath(null);
      }
    });

    if (extractBtn) extractBtn.addEventListener('click', async () => {
      const picked = Array.from(applicantsSelected);
      if (picked.length === 0) {
        setStatus('Select one or more files to extract.');
        alert('Select one or more files to extract.');
        return;
      }
      try {
        if (window.setUIBusy) window.setUIBusy(true);
        if (picked.length === 1) {
          // Run the 7-step pipeline for a single selected CV and update UI with step progress
          const steps = ['1/6: Extracting text', '2/6: OpenAI fields', '3/6: Slicing sections', '4/6: OpenAI embeddings', '5/6: Writing to Weaviate', '6/6: Reading back'];
          let currentStep = 0;
          const pollInterval = setInterval(() => {
            if (currentStep < steps.length) {
              setStatus(steps[currentStep]);
              currentStep++;
            }
          }, 1500);
          
          const r = await fetch('/api/applicants/pipeline', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file: picked[0] }),
          });
          clearInterval(pollInterval);
          const j = await r.json();
          if (!r.ok) throw new Error(j.error || 'Pipeline failed');
          // Cache fields for this path and re-render details
          window.lastExtractFieldsPath = picked[0];
          window.lastExtractFieldsRow = fieldsToRow(j.fields || {});
          renderApplicantDetailsForPath(picked[0]);
          setStatus('Pipeline completed. Displaying extracted fields and Weaviate readback.');
        } else {
          // Fallback to CSV extract for multiple files
          await startApplicantsExtractPolling();
          setStatus('Extracting (CSV-only) ...');
          const r = await fetch('/api/extract', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ files: picked }),
          });
          const j = await r.json();
          if (!r.ok) throw new Error(j.error || 'Extraction failed');
          await refreshApplicantsExtracted();
          setStatus(`Extraction completed; saved ${j.saved}.`);
        }
      } catch (e) {
        console.error(e);
        setStatus(`Error: ${e.message || e}`);
      } finally {
        if (applicantsExtractPollTimer) { clearInterval(applicantsExtractPollTimer); applicantsExtractPollTimer = null; }
        if (window.setUIBusy) window.setUIBusy(false);
      }
    });
  });

  async function loadApplicantsList() {
    try {
      if (window.setStatus) window.setStatus('Loading applicants list...');
      const j = await fetchJSON('/api/list-files');
      if (typeof renderApplicantsList === 'function') {
        renderApplicantsList(j.folder, j.files || []);
      }
      if (typeof refreshApplicantsExtracted === 'function') {
        await refreshApplicantsExtracted();
      }
        // show details for first file if it is already selected/extracted
        const firstItem = document.querySelector('#list .item');
        if (firstItem) renderApplicantDetailsForPath(decodeURIComponent(firstItem.getAttribute('data-path')));
      if (window.setStatus) window.setStatus('Ready');
    } catch (e) {
      console.error(e);
      if (window.setStatus) window.setStatus(`Error loading applicants list: ${e.message || e}`);
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    // Tab buttons
    const tabApplicants = document.getElementById('tabApplicants');
    const tabRoles = document.getElementById('tabRoles');
  if (tabApplicants) tabApplicants.addEventListener('click', async () => { activateTab('tabApplicants'); await loadApplicantsList(); });
  if (tabRoles) tabRoles.addEventListener('click', async () => { activateTab('tabRoles'); await loadRolesList(); });

    // Roles controls
    const roleBrowse = document.getElementById('roleBrowseBtn');
    const roleRefresh = document.getElementById('roleRefreshBtn');
    if (roleBrowse) roleBrowse.addEventListener('click', async () => {
      try {
        if (window.setStatus) window.setStatus('Picking roles folder...');
        const d = await fetchJSON('/api/roles/pick-folder');
        if (typeof renderRolesList === 'function') renderRolesList(d.folder, d.files || []);
        if (typeof refreshRolesExtracted === 'function') await refreshRolesExtracted();
        if (window.setStatus) window.setStatus('Ready');
      } catch (e) {
        console.error(e);
        if (window.setStatus) window.setStatus(`Error picking roles folder: ${e.message || e}`);
      }
    });
    if (roleRefresh) roleRefresh.addEventListener('click', loadRolesList);

    // Initial load for applicants so extracted markers appear on first view
    loadApplicantsList();
  });
})();
