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
  if (countEl) countEl.textContent = `${totalNum} file${totalNum === 1 ? '' : 's'} | ${selNum} selected | ${extractedNum} extracted${dupText}`;
}

function markExtractedInRolesList() {
  try {
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
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ files }),
          });
          const j = await r.json();
          const list = Array.isArray(j.duplicates_all) ? j.duplicates_all : (j.duplicates || []);
          const dups = new Set(list.map(f => (f || '').toString().split(/[\\/]/).pop()));
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
          if (picked.length === 1) {
            const steps = ['1/6: Extracting text', '2/6: OpenAI fields', '3/6: Slicing sections', '4/6: OpenAI embeddings', '5/6: Writing to Weaviate', '6/6: Reading back'];
            let currentStep = 0;
            const pollInterval = setInterval(() => { if (currentStep < steps.length) { setStatus(steps[currentStep]); currentStep++; } }, 1500);
            const r = await fetch('/api/roles/pipeline', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ file: picked[0] }) });
            clearInterval(pollInterval);
            const j = await r.json();
            if (!r.ok) throw new Error(j.error || 'Roles pipeline failed');
            window.lastRoleExtractFieldsPath = picked[0];
            window.lastRoleExtractFieldsRow = fieldsToRoleRow(j.fields || {});
            renderRoleDetailsForPath(picked[0]);
            setStatus('Role pipeline completed. Displaying extracted fields.');
            await refreshRolesExtracted();
          } else {
            const startedAt = Date.now();
            const fmtSec = (ms) => `(${Math.floor(ms/1000)} sec) ...`;
            const timer = setInterval(async () => {
              try {
                const r = await fetch('/api/roles/extract/progress', { cache: 'no-store' });
                if (!r.ok) return;
                const j = await r.json();
                const total = Number(j.total || 0);
                const done = Number(j.done || 0);
                setStatus(`extracted ${done} out of ${total} roles ${fmtSec(Date.now() - startedAt)}`);
                if (!j.active) clearInterval(timer);
              } catch (_) {}
            }, 500);
            const r = await fetch('/api/roles/pipeline/batch', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ files: picked }) });
            const j = await r.json();
            if (!r.ok) throw new Error(j.error || 'Roles batch failed');
            await refreshRolesExtracted();
            setStatus(`Batch completed: ${j.processed} processed, ${j.errors.length} errors.`);
          }
        } catch (e) {
          setStatus(`Error: ${e.message || e}`);
        } finally {
          setUIBusy(false);
        }
      });

      // Placeholder match button: refresh lists when matching completes
      const roleMatchBtn = document.getElementById('roleMatchBtn');
      if (roleMatchBtn) roleMatchBtn.addEventListener('click', async () => {
        try {
          if (window.setUIBusy) window.setUIBusy(true);
          setStatus('Matching roles to applicants (placeholder)...');
          if (typeof refreshRolesExtracted === 'function') {
            await refreshRolesExtracted();
          }
          if (typeof refreshApplicantsExtracted === 'function') {
            await refreshApplicantsExtracted();
          }
          setStatus('Matching complete.');
        } catch (e) {
          setStatus(`Match error: ${e.message || e}`);
        } finally {
          if (window.setUIBusy) window.setUIBusy(false);
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
          const files = items.map(el => decodeURIComponent(el.getAttribute('data-path')));
          await highlightRolesDuplicates(files);
          updateRolesFooter(items.length);
          const selected = Array.from(rolesSelected);
          if (selected.length === 1) renderRoleDetailsForPath(selected[0]); else renderRoleDetailsForPath(null);
          setStatus('Ready');
        } catch (e) {
          setStatus(`Error loading extracted roles: ${e.message || e}`);
        }
      }

      function renderRolesList(folder, files) {
        const box = document.getElementById('roleList');
        document.getElementById('roleFolderPath').value = folder || '';
        rolesSelected.clear();
        updateRolesFooter(0);
        if (!folder) { box.innerHTML = '<div class="muted">No folder selected.</div>'; updateRolesFooter(0); return; }
        if (!files || files.length === 0) { box.innerHTML = `<div class="muted">No .pdf or .docx files in: ${folder}</div>`; updateRolesFooter(0); return; }
  box.innerHTML = files.map((f, i) => { const name = (f || '').toString().split(/[\\/]/).pop(); return `<div class="item" data-index="${i}" data-path="${encodeURIComponent(f)}">${name}</div>`; }).join('');
        updateRolesFooter(files.length);
        markExtractedInRolesList();
        highlightRolesDuplicates(files);
        const items = Array.from(box.querySelectorAll('.item'));
        const clearAll = () => { items.forEach(node => node.classList.remove('selected')); rolesSelected.clear(); };
        const toggleOne = (node) => { const p = decodeURIComponent(node.getAttribute('data-path')); if (node.classList.contains('selected')) { node.classList.remove('selected'); rolesSelected.delete(p); } else { node.classList.add('selected'); rolesSelected.add(p); } };
        const selectOne = (node) => { clearAll(); const p = decodeURIComponent(node.getAttribute('data-path')); node.classList.add('selected'); rolesSelected.add(p); };
        const selectRange = (startIdx, endIdx) => { clearAll(); const [a,b]=startIdx<=endIdx?[startIdx,endIdx]:[endIdx,startIdx]; for (let i=a;i<=b;i++){ const node=items[i]; const p=decodeURIComponent(node.getAttribute('data-path')); node.classList.add('selected'); rolesSelected.add(p);} };
        items.forEach(el => {
          el.addEventListener('click', (ev) => {
            const idx = Number(el.getAttribute('data-index'));
            if (ev.shiftKey && roleLastSelectedIndex !== null && !Number.isNaN(idx)) selectRange(roleLastSelectedIndex, idx);
            else if (ev.ctrlKey || ev.metaKey) toggleOne(el);
            else selectOne(el);
            roleLastSelectedIndex = idx;
            updateRolesFooter(files.length);
            if (rolesSelected.size === 1) renderRoleDetailsForPath(Array.from(rolesSelected)[0]); else renderRoleDetailsForPath(null);
          });
        });
        // Auto-select the first item on initial render for immediate details
        if (items.length > 0 && rolesSelected.size === 0) {
          const first = items[0];
          const p0 = decodeURIComponent(first.getAttribute('data-path'));
          first.classList.add('selected');
          rolesSelected.add(p0);
          roleLastSelectedIndex = 0;
          updateRolesFooter(files.length);
          renderRoleDetailsForPath(p0);
        }
      }

      async function renderRoleDetailsForPath(path) {
        const col1 = document.getElementById('roleTablesCol1');
        const col2 = document.getElementById('roleTablesCol2');
        if (!col1) return;
        col1.innerHTML = '';
        if (col2) col2.innerHTML = '';
        if (!path) return;
        const basename = (path || '').toString().split(/[\\/]/).pop();

        let row = (rolesTableRows || []).find(r => {
          const fn = (r.filename || '').toString();
          return fn === basename || fn.endsWith(basename);
        }) || {};

        if (window.lastRoleExtractFieldsPath === path && window.lastRoleExtractFieldsRow) {
          row = { ...row, ...window.lastRoleExtractFieldsRow };
        } else {
          // Prefer resolving by file path; if that fails (e.g., file moved), fall back to DB by sha from list
          let resolved = false;
          try {
            const r = await fetch(`/api/weaviate/role_by_path?path=${encodeURIComponent(path)}`);
            const j = await r.json();
            if (r.ok && j && j.document) {
              const attrs = ((j.document || {}).attributes) || {};
              row = { ...row, ...attrs, id: (j.document || {}).id, sha: (j.document || {}).sha, filename: basename };
              resolved = true;
            }
          } catch (_) { /* ignore */ }

          if (!resolved) {
            // Fallback: find sha for this filename from rolesTableRows and query by sha
            const rec = (rolesTableRows || []).find(r => {
              const fn = (r.filename || '').toString();
              return fn === basename || fn.endsWith(basename);
            });
            const sha = rec && rec.sha;
            if (sha) {
              try {
                const r2 = await fetch(`/api/weaviate/role_all/${encodeURIComponent(sha)}`);
                const j2 = await r2.json();
                if (r2.ok && j2 && j2.document) {
                  const attrs2 = ((j2.document || {}).attributes) || {};
                  row = { ...row, ...attrs2, id: (j2.document || {}).id, sha: (j2.document || {}).sha, filename: basename };
                }
              } catch (_) { /* ignore */ }
            }
          }
        }

        function mkTable(title, pairs) {
          const th = `<div class="table-title">${title}</div>`;
          const rows = pairs.map(([k, v]) => `<tr><td>${k}</td><td>${v || ''}</td></tr>`).join('');
          return `${th}<div class="table-wrap"><table class="data-table"><tbody>${rows}</tbody></table></div>`;
        }

        const n = {
          role_title: row.role_title || row.job_title || '',
          job_title: row.job_title || row.role_title || '',
          employer: row.employer || '',
          job_location: row.job_location || '',
          language_requirement: row.language_requirement || '',
          onsite_requirement_percentage: row.onsite_requirement_percentage || '',
          onsite_requirement_mandatory: row.onsite_requirement_mandatory || '',
          serves_government: row.serves_government || '',
          serves_financial_institution: row.serves_financial_institution || '',
          min_years_experience: row.min_years_experience || '',
          must_have_skills: row.must_have_skills || '',
          should_have_skills: row.should_have_skills || '',
          nice_to_have_skills: row.nice_to_have_skills || '',
          min_must_have_degree: row.min_must_have_degree || '',
          preferred_universities: row.preferred_universities || '',
          responsibilities: row.responsibilities || '',
          technical_qualifications: row.technical_qualifications || '',
          non_technical_qualifications: row.non_technical_qualifications || '',
          id: row.id || '',
          filename: row.filename || basename,
          timestamp: row.timestamp || '',
        };

        const core = [
          ['Role title', n.role_title],
          ['Employer', n.employer],
          ['Location', n.job_location],
          ['Language requirement', n.language_requirement],
          ['Min years experience', n.min_years_experience],
          ['On-site %', n.onsite_requirement_percentage],
          ['On-site mandatory', n.onsite_requirement_mandatory],
          ['Serves government', n.serves_government],
          ['Serves financial institution', n.serves_financial_institution],
          ['Min must-have degree', n.min_must_have_degree],
        ];
        const skills = [
          ['Must-have skills', n.must_have_skills],
          ['Should-have skills', n.should_have_skills],
          ['Nice-to-have skills', n.nice_to_have_skills],
          ['Preferred universities', n.preferred_universities],
        ];
        const qual = [
          ['Technical qualifications', n.technical_qualifications],
          ['Non-technical qualifications', n.non_technical_qualifications],
          ['Responsibilities', n.responsibilities],
        ];
        const meta = [
          ['ID', n.id],
          ['Filename', n.filename],
          ['Timestamp', n.timestamp],
        ];

        const leftHtml = mkTable('Role', core) + mkTable('Skills', skills);
        const rightHtml = mkTable('Qualifications', qual) + mkTable('Metadata', meta);
        if (col2) {
          col1.innerHTML = leftHtml;
          col2.innerHTML = rightHtml;
        } else {
          col1.innerHTML = leftHtml + rightHtml;
        }
      }

      function fieldsToRoleRow(fields) {
        const f = fields || {};
        const get = (k, d='') => (f[k] == null ? d : f[k]);
        return {
          role_title: get('job_title', ''),
          job_title: get('job_title', ''),
          employer: get('employer', ''),
          job_location: get('job_location', ''),
          language_requirement: get('language_requirement', ''),
          onsite_requirement_percentage: get('onsite_requirement_percentage', ''),
          onsite_requirement_mandatory: get('onsite_requirement_mandatory', ''),
          serves_government: get('serves_government', ''),
          serves_financial_institution: get('serves_financial_institution', ''),
          min_years_experience: get('min_years_experience', ''),
          must_have_skills: get('must_have_skills', ''),
          should_have_skills: get('should_have_skills', ''),
          nice_to_have_skills: get('nice_to_have_skills', ''),
          min_must_have_degree: get('min_must_have_degree', ''),
          preferred_universities: get('preferred_universities', ''),
          responsibilities: get('responsibilities', ''),
          technical_qualifications: get('technical_qualifications', ''),
          non_technical_qualifications: get('non_technical_qualifications', ''),
        };
      }

      // Wire up Roles "Select All" button
      document.addEventListener('DOMContentLoaded', () => {
        const selectAll = document.getElementById('roleSelectAllBtn');
        if (selectAll) selectAll.addEventListener('click', () => {
          const items = Array.from(document.querySelectorAll('#roleList .item'));
          rolesSelected.clear();
          items.forEach(el => {
            const p = decodeURIComponent(el.getAttribute('data-path'));
            el.classList.add('selected');
            rolesSelected.add(p);
          });
          updateRolesFooter(items.length);
          const selected = Array.from(rolesSelected);
          if (selected.length === 1) renderRoleDetailsForPath(selected[0]);
          else renderRoleDetailsForPath(null);
        });
      });

