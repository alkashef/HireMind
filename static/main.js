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
      // Show details for the first file on load (parity with Applicants)
      const firstRoleItem = document.querySelector('#roleList .item');
      if (firstRoleItem && typeof renderRoleDetailsForPath === 'function') {
        renderRoleDetailsForPath(decodeURIComponent(firstRoleItem.getAttribute('data-path')));
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
    if (!col1 || !col2) return;
    // Clear first
    col1.innerHTML = '';
    col2.innerHTML = '';
    if (!path) return;
  const basename = (path || '').toString().split(/[\\\/]/).pop().toLowerCase();

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
      // Try all possible filename keys for robust matching
      row = (applicantsTableRows || []).find(r => {
        const keys = ['cv', 'Filename', 'PersonalInformation_FullName', 'PersonalInformation_Filename', 'full_name', 'filename'];
        return keys.some(k => {
          const val = (r[k] || '').toString().toLowerCase();
          return val === basename || val.endsWith(basename);
        });
      });
    }

    const toNorm = (r) => ({
      full_name: r.full_name || r.PersonalInformation_FullName || r.PersonalInformation_Fullname || '',
      first_name: r.first_name || r.PersonalInformation_FirstName || '',
      last_name: r.last_name || r.PersonalInformation_LastName || '',
      email: r.email || r.PersonalInformation_Email || '',
      phone: r.phone || r.PersonalInformation_Phone || '',
      misspelling_count: r.misspelling_count || r.Professionalism_MisspellingCount || '',
      misspelled_words: r.misspelled_words || r.Professionalism_MisspelledWords || '',
      visual_cleanliness: r.visual_cleanliness || r.Professionalism_VisualCleanliness || '',
      professional_look: r.professional_look || r.Professionalism_ProfessionalLook || '',
      formatting_consistency: r.formatting_consistency || r.Professionalism_FormattingConsistency || '',
      years_since_graduation: r.years_since_graduation || r.Experience_YearsSinceGraduation || '',
      total_years_experience: r.total_years_experience || r.Experience_TotalYearsExperience || '',
      employer_names: r.employer_names || r.Experience_EmployerNames || '',
      employers_count: r.employers_count || r.Stability_EmployersCount || '',
      avg_years_per_employer: r.avg_years_per_employer || r.Stability_AvgYearsPerEmployer || '',
      years_at_current_employer: r.years_at_current_employer || r.Stability_YearsAtCurrentEmployer || '',
      address: r.address || r.SocioeconomicStandard_Address || '',
      alma_mater: r.alma_mater || r.SocioeconomicStandard_AlmaMater || '',
      high_school: r.high_school || r.SocioeconomicStandard_HighSchool || '',
      education_system: r.education_system || r.SocioeconomicStandard_EducationSystem || '',
      second_foreign_language: r.second_foreign_language || r.SocioeconomicStandard_SecondForeignLanguage || '',
      flag_stem_degree: r.flag_stem_degree || r.Flags_FlagSTEMDegree || '',
      military_service_status: r.military_service_status || r.Flags_MilitaryServiceStatus || '',
      worked_at_financial_institution: r.worked_at_financial_institution || r.Flags_WorkedAtFinancialInstitution || '',
      worked_for_egyptian_government: r.worked_for_egyptian_government || r.Flags_WorkedForEgyptianGovernment || '',
    });

    if (!row) {
      col1.innerHTML = `<div class="muted">No extracted data for: ${basename}</div>`;
    } else {
      const n = toNorm(row);
      const personal = [
        ['Full name', n.full_name],
        ['First name', n.first_name],
        ['Last name', n.last_name],
        ['Email', n.email],
        ['Phone', n.phone],
      ];
      const professionalism = [
        ['Misspelling count', n.misspelling_count],
        ['Misspelled words', n.misspelled_words],
        ['Visual cleanliness', n.visual_cleanliness],
        ['Professional look', n.professional_look],
        ['Formatting consistency', n.formatting_consistency],
      ];
      const experience = [
        ['Years since graduation', n.years_since_graduation],
        ['Total years experience', n.total_years_experience],
        ['Employer names', n.employer_names],
      ];
      const stability = [
        ['Employers count', n.employers_count],
        ['Avg years per employer', n.avg_years_per_employer],
        ['Years at current employer', n.years_at_current_employer],
      ];
      const socioeconomic = [
        ['Address', n.address],
        ['Alma mater', n.alma_mater],
        ['High school', n.high_school],
        ['Education system', n.education_system],
        ['Second foreign language', n.second_foreign_language],
      ];
      const flags = [
        ['STEM degree', n.flag_stem_degree],
        ['Military service status', n.military_service_status],
        ['Worked at financial institution', n.worked_at_financial_institution],
        ['Worked for Egyptian government', n.worked_for_egyptian_government],
      ];

      // Put some groups in col1 and others in col2 for layout parity
      col1.innerHTML = mkTable('Personal Information', personal) + mkTable('Professionalism', professionalism) + mkTable('Flags', flags);
      col2.innerHTML = mkTable('Experience', experience) + mkTable('Stability', stability) + mkTable('Socioeconomic Standard', socioeconomic);
    }

  // Weaviate readback column removed.
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

  // Weaviate readback renderer removed

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
      const r = await fetch('/api/applicants', { method: 'GET' });
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
    const fmtSec = (ms) => `${Math.floor(ms/1000)}s`;
    if (applicantsExtractPollTimer) clearInterval(applicantsExtractPollTimer);
    applicantsExtractPollTimer = setInterval(async () => {
      try {
        const r = await fetch('/api/extract/progress', { cache: 'no-store' });
        if (!r.ok) return;
        const j = await r.json();
        const total = Number(j.total || 0);
        const done = Number(j.done || 0);
        const elapsed = fmtSec(Date.now() - startedAt);
        if (window.setStatus) window.setStatus(`Extracting information from batch (applicants): processed ${done}/${total} files (elapsed ${elapsed})`);
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
  const matchBtn = document.getElementById('matchBtn');

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
          // Single-file pipeline progress (6 detailed steps) with filename context
          const filePath = picked[0];
          const basename = (filePath || '').toString().split(/[\\/]/).pop();
          const isDocx = /\.docx$/i.test(basename);
          const steps = [
            `Extracting information from ${basename}: STEP 1/6: Read file & compute SHA`,
            `Extracting information from ${basename}: STEP 2/6: Parse ${isDocx ? 'DOCX' : 'PDF'} text`,
            `Extracting information from ${basename}: STEP 3/6: Extract fields with OpenAI`,
            `Extracting information from ${basename}: STEP 4/6: Slice text into sections`,
            `Extracting information from ${basename}: STEP 5/6: Compute embeddings (doc + sections)`,
            `Extracting information from ${basename}: STEP 6/6: Save to Weaviate and verify readback`,
          ];
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
            body: JSON.stringify({ file: filePath }),
          });
          clearInterval(pollInterval);
          const j = await r.json();
          if (!r.ok) throw new Error(j.error || 'Pipeline failed');
          // Cache fields for this path and re-render details
          window.lastExtractFieldsPath = filePath;
          window.lastExtractFieldsRow = fieldsToRow(j.fields || {});
          renderApplicantDetailsForPath(filePath);
          // Refresh the list/markers after single-file extraction
          if (typeof refreshApplicantsExtracted === 'function') {
            await refreshApplicantsExtracted();
          }
          setStatus(`Extracting information from ${basename}: completed successfully`);
        } else {
          // Batch pipeline for multiple files
          await startApplicantsExtractPolling();
          setStatus('Extracting information from batch (applicants): starting...');
          const r = await fetch('/api/applicants/pipeline/batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ files: picked }),
          });
          const j = await r.json();
          if (!r.ok) throw new Error(j.error || 'Batch extraction failed');
          await refreshApplicantsExtracted();
          setStatus(`Extracting information from batch (applicants): completed — processed ${j.processed}, errors ${j.errors.length}.`);
        }
      } catch (e) {
        console.error(e);
        setStatus(`Error: ${e.message || e}`);
      } finally {
        if (applicantsExtractPollTimer) { clearInterval(applicantsExtractPollTimer); applicantsExtractPollTimer = null; }
        if (window.setUIBusy) window.setUIBusy(false);
      }
    });

    if (matchBtn) matchBtn.addEventListener('click', async () => {
      try {
        if (window.setUIBusy) window.setUIBusy(true);
        setStatus('Matching applicants to roles (placeholder)...');
        // After matching completes, refresh lists if needed
        if (typeof refreshApplicantsExtracted === 'function') {
          await refreshApplicantsExtracted();
        }
        if (typeof refreshRolesExtracted === 'function') {
          await refreshRolesExtracted();
        }
        setStatus('Matching complete.');
      } catch (e) {
        setStatus(`Match error: ${e.message || e}`);
      } finally {
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

    // Initial load for roles so extracted markers appear on first view
    loadRolesList();
  });
})();
