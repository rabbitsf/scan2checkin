'use strict';

const statusEl  = document.getElementById('status');
const btnSubmit = document.getElementById('btn-submit');
const btnLabel  = document.getElementById('btn-label');
const spinner   = document.getElementById('spinner');

// ── Pre-fill from sessionStorage ───────────────────────────────────────────
const raw = sessionStorage.getItem('dl_fields');
let dlFields = {};

if (raw) {
  try {
    dlFields = JSON.parse(raw);
  } catch (_) {}
}

document.getElementById('first-name').value = dlFields.first_name || '';
document.getElementById('last-name').value  = dlFields.last_name  || '';
document.getElementById('dob').value        = dlFields.dob        || '';
document.getElementById('state').value      = dlFields.state      || '';

// ── Submit ─────────────────────────────────────────────────────────────────
btnSubmit.addEventListener('click', async () => {
  const visitingWhom = document.getElementById('visiting-whom').value.trim();
  const purpose      = document.getElementById('purpose').value;
  const firstName    = document.getElementById('first-name').value.trim();
  const lastName     = document.getElementById('last-name').value.trim();

  if (!visitingWhom) {
    setStatus('error', 'Please enter who you are visiting.');
    return;
  }
  if (!purpose) {
    setStatus('error', 'Please select the purpose of your visit.');
    return;
  }
  if (!firstName && !lastName) {
    setStatus('error', 'Please enter your name.');
    return;
  }

  btnSubmit.disabled = true;
  spinner.style.display = 'block';
  btnLabel.textContent = 'Checking in…';
  setStatus('info', 'Saving your details…');

  const payload = {
    ...dlFields,
    first_name:    firstName,
    last_name:     lastName,
    full_name:     `${firstName} ${lastName}`.trim(),
    visiting_whom: visitingWhom,
    purpose:       purpose,
  };

  try {
    const resp = await fetch('/api/checkin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || 'Check-in failed');
    }

    const { visit_id } = await resp.json();
    setStatus('success', 'Checked in! Preparing your badge…');
    setTimeout(() => {
      window.location.href = `/badge.html?visit_id=${encodeURIComponent(visit_id)}`;
    }, 500);
  } catch (err) {
    console.error('Checkin error:', err);
    setStatus('error', `Check-in failed: ${err.message}`);
    btnSubmit.disabled = false;
    spinner.style.display = 'none';
    btnLabel.textContent = 'Check In & Print Badge';
  }
});

// ── Back button ────────────────────────────────────────────────────────────
document.getElementById('btn-back').addEventListener('click', () => {
  window.location.href = '/';
});

// ── Helpers ────────────────────────────────────────────────────────────────
function setStatus(type, msg) {
  statusEl.className = `status ${type}`;
  statusEl.textContent = msg;
  statusEl.style.display = msg ? 'block' : 'none';
}
