'use strict';

const video   = document.getElementById('video');
const canvas  = document.getElementById('canvas');
const btnCapture = document.getElementById('btn-capture');
const btnLabel   = document.getElementById('btn-label');
const spinner    = document.getElementById('spinner');
const statusEl   = document.getElementById('status');

let stream = null;
let cameraReady = false;

// ── Start camera on load ───────────────────────────────────────────────────
async function startCamera() {
  setStatus('info', 'Starting camera…');
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: { ideal: 'environment' }, // rear camera on iPad
        width: { ideal: 1920 },
        height: { ideal: 1080 },
      },
      audio: false,
    });
    video.srcObject = stream;
    await video.play();
    cameraReady = true;
    btnCapture.disabled = false;
    btnLabel.textContent = 'Scan Barcode';
    document.getElementById('btn-icon').textContent = '📷';
    setStatus('', '');
  } catch (err) {
    console.error('Camera error:', err);
    if (err.name === 'NotAllowedError') {
      setStatus('error', 'Camera access denied. Please allow camera access in your browser settings, then reload.');
    } else if (err.name === 'NotFoundError') {
      setStatus('error', 'No camera found on this device.');
    } else {
      setStatus('error', `Camera error: ${err.message}`);
    }
  }
}

// ── Capture frame + POST to /api/scan ─────────────────────────────────────
async function captureAndScan() {
  if (!cameraReady) return;

  // Grab frame
  canvas.width  = video.videoWidth  || 1280;
  canvas.height = video.videoHeight || 720;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  const imageDataUrl = canvas.toDataURL('image/jpeg', 0.98);

  // UI: loading state
  btnCapture.disabled = true;
  spinner.style.display = 'block';
  btnLabel.textContent = 'Scanning…';
  setStatus('info', 'Reading license — please hold still…');

  try {
    const resp = await fetch('/api/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image: imageDataUrl }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || 'Scan failed');
    }

    const data = await resp.json();
    if (!data.fields) throw new Error('Unexpected response from server');

    // Persist parsed fields for the form page
    sessionStorage.setItem('dl_fields', JSON.stringify(data.fields));

    setStatus('success', 'License scanned! Redirecting…');
    // Stop camera before leaving
    stream?.getTracks().forEach(t => t.stop());

    setTimeout(() => { window.location.href = '/form.html'; }, 600);
  } catch (err) {
    console.error('Scan error:', err);
    setStatus('error', `Could not read license: ${err.message}. Please try again.`);
    btnCapture.disabled = false;
    spinner.style.display = 'none';
    btnLabel.textContent = 'Try Again — aim at barcode';
  }
}

// ── Button click ───────────────────────────────────────────────────────────
btnCapture.addEventListener('click', () => {
  if (!cameraReady) {
    startCamera();
  } else {
    captureAndScan();
  }
});

// ── Helpers ────────────────────────────────────────────────────────────────
function setStatus(type, msg) {
  statusEl.className = `status ${type}`;
  statusEl.textContent = msg;
  statusEl.style.display = msg ? 'block' : 'none';
}

// Auto-start camera
startCamera();
