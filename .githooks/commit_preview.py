#!/usr/bin/env python3
"""
commit_preview.py — Show an HTML diff preview with Approve/Abort buttons.
Starts a local HTTP server, opens the browser, blocks until the user clicks.
No terminal TTY required — works from Claude Code and other non-interactive callers.
Exit 0 = approved, Exit 1 = aborted/timed out.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

DECISION_TIMEOUT = 120  # seconds before auto-abort


# ── Git data ──────────────────────────────────────────────────────────────────

def _run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode("utf-8", errors="replace")
    except subprocess.CalledProcessError:
        return ""


def get_git_info() -> tuple[str, str, str, str]:
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip()
    stat   = _run(["git", "diff", "--cached", "--stat"])
    diff   = _run(["git", "diff", "--cached"])
    files  = _run(["git", "diff", "--cached", "--name-status"])
    return branch, stat, diff, files


# ── HTML rendering ────────────────────────────────────────────────────────────

def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _render_files(files_text: str) -> str:
    rows = []
    for line in files_text.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        status, path = parts[0].strip(), parts[1].strip()
        cls   = {"A": "add", "M": "mod", "D": "del"}.get(status[0], "mod")
        label = {"A": "Added", "M": "Modified", "D": "Deleted"}.get(status[0], status)
        rows.append(
            f'<tr><td><span class="badge {cls}">{label}</span></td>'
            f'<td class="path">{_esc(path)}</td></tr>'
        )
    return "".join(rows) or '<tr><td colspan="2" style="color:#6b7280">No staged files.</td></tr>'


def _render_diff(diff_text: str) -> str:
    if not diff_text.strip():
        return '<span style="color:#6b7280">No diff to display.</span>'
    out = []
    for line in diff_text.splitlines():
        e = _esc(line)
        if line.startswith("diff --git") or line.startswith("index ") \
                or line.startswith("--- ") or line.startswith("+++ "):
            out.append(f'<span class="df">{e}</span>')
        elif line.startswith("@@"):
            out.append(f'<span class="hunk">{e}</span>')
        elif line.startswith("+"):
            out.append(f'<span class="add">{e}</span>')
        elif line.startswith("-"):
            out.append(f'<span class="del">{e}</span>')
        else:
            out.append(e)
    return "\n".join(out)


def build_html(branch: str, stat: str, diff: str, files: str, timeout: int) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Commit Preview</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d1117;color:#e6edf3;padding:24px 28px 100px}}
h1{{font-size:1.3rem;font-weight:700;margin-bottom:10px}}
.branch{{display:inline-flex;align-items:center;gap:6px;background:#21262d;border:1px solid #30363d;border-radius:20px;padding:4px 14px;font-size:.82rem;color:#79c0ff;margin-bottom:22px}}
.section{{margin-bottom:22px}}
.stitle{{font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#8b949e;margin-bottom:8px}}
table{{width:100%;border-collapse:collapse}}
td{{padding:5px 10px;font-size:.88rem}}
tr:nth-child(even) td{{background:#161b22}}
.badge{{font-size:.68rem;font-weight:700;padding:2px 8px;border-radius:4px;text-transform:uppercase}}
.badge.add{{background:#1a4731;color:#3fb950}}
.badge.mod{{background:#2d2a14;color:#d29922}}
.badge.del{{background:#3d1a1a;color:#f85149}}
.path{{font-family:'SFMono-Regular',Consolas,monospace;font-size:.83rem}}
.stat{{font-family:monospace;font-size:.78rem;color:#8b949e;background:#161b22;border:1px solid #30363d;border-radius:6px;padding:12px;white-space:pre-wrap;word-break:break-all}}
.diff-wrap{{background:#161b22;border:1px solid #30363d;border-radius:6px;overflow:auto;max-height:55vh}}
pre{{font-family:'SFMono-Regular',Consolas,monospace;font-size:.76rem;line-height:1.55;padding:16px;tab-size:4}}
.df  {{color:#79c0ff;font-weight:600;display:block}}
.hunk{{color:#a5d6ff;background:#1b2a3b;display:block}}
.add {{color:#3fb950;background:#0d2818;display:block}}
.del {{color:#f85149;background:#2d0f0f;display:block}}

/* Fixed action bar */
.action-bar{{position:fixed;bottom:0;left:0;right:0;background:#161b22;border-top:1px solid #30363d;padding:14px 28px;display:flex;align-items:center;gap:12px;z-index:10}}
.btn{{padding:10px 28px;border:none;border-radius:8px;font-size:.95rem;font-weight:600;cursor:pointer;transition:opacity .15s}}
.btn:disabled{{opacity:.4;cursor:not-allowed}}
.btn-approve{{background:#238636;color:#fff}}
.btn-approve:hover:not(:disabled){{background:#2ea043}}
.btn-abort{{background:#21262d;color:#f85149;border:1px solid #f85149}}
.btn-abort:hover:not(:disabled){{background:#3d1a1a}}
.countdown{{margin-left:auto;font-size:.8rem;color:#8b949e}}

/* Result overlay */
#overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.82);align-items:center;justify-content:center;z-index:99}}
#overlay.show{{display:flex}}
.toast{{background:#161b22;border:2px solid #30363d;border-radius:14px;padding:36px 56px;text-align:center}}
.toast.ok{{border-color:#3fb950}}
.toast.err{{border-color:#f85149}}
.ti{{font-size:3rem;margin-bottom:12px}}
.tm{{font-size:1.2rem;font-weight:700}}
</style>
</head>
<body>
  <h1>Commit Preview</h1>
  <div class="branch">⎇&nbsp;{_esc(branch)}</div>

  <div class="section">
    <div class="stitle">Changed Files</div>
    <table>{_render_files(files)}</table>
  </div>

  <div class="section">
    <div class="stitle">Stat</div>
    <div class="stat">{_esc(stat.strip()) or "No stat available."}</div>
  </div>

  <div class="section">
    <div class="stitle">Diff</div>
    <div class="diff-wrap"><pre>{_render_diff(diff)}</pre></div>
  </div>

  <!-- Fixed action bar -->
  <div class="action-bar">
    <button class="btn btn-approve" id="btn-approve" onclick="decide(true)">Approve Commit</button>
    <button class="btn btn-abort"   id="btn-abort"   onclick="decide(false)">Abort</button>
    <span class="countdown" id="countdown">Auto-abort in {timeout}s</span>
  </div>

  <!-- Result overlay -->
  <div id="overlay">
    <div class="toast" id="toast">
      <div class="ti" id="ti"></div>
      <div class="tm" id="tm"></div>
    </div>
  </div>

  <script>
    let remaining = {timeout};
    const countdownEl = document.getElementById('countdown');

    const timer = setInterval(() => {{
      remaining--;
      countdownEl.textContent = remaining > 0
        ? `Auto-abort in ${{remaining}}s`
        : 'Timed out — aborting…';
      if (remaining <= 0) {{
        clearInterval(timer);
        decide(false);
      }}
    }}, 1000);

    function decide(proceed) {{
      clearInterval(timer);
      document.getElementById('btn-approve').disabled = true;
      document.getElementById('btn-abort').disabled   = true;
      countdownEl.textContent = '';

      fetch('/decide', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{proceed}})
      }}).then(() => {{
        const overlay = document.getElementById('overlay');
        const toast   = document.getElementById('toast');
        overlay.classList.add('show');
        if (proceed) {{
          toast.classList.add('ok');
          document.getElementById('ti').textContent = '✅';
          document.getElementById('tm').textContent = 'Committed!';
        }} else {{
          toast.classList.add('err');
          document.getElementById('ti').textContent = '🚫';
          document.getElementById('tm').textContent = 'Commit aborted.';
        }}
        setTimeout(() => window.close(), 2000);
      }});
    }}
  </script>
</body>
</html>"""


# ── HTTP server ───────────────────────────────────────────────────────────────

def find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def make_handler(html: str, state: dict, decided: threading.Event):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                body = html.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path == "/decide":
                length = int(self.headers.get("Content-Length", 0))
                data   = json.loads(self.rfile.read(length))
                proceed = bool(data.get("proceed", False))
                state["proceed"] = proceed
                state["result"]  = "committed" if proceed else "aborted"
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
                decided.set()
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):
            pass

    return Handler


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    branch, stat, diff, files = get_git_info()
    html    = build_html(branch, stat, diff, files, DECISION_TIMEOUT)
    port    = find_free_port()
    state   = {"proceed": False, "result": "aborted"}
    decided = threading.Event()

    server = HTTPServer(("127.0.0.1", port), make_handler(html, state, decided))
    t = threading.Thread(target=server.serve_forever)
    t.daemon = True
    t.start()

    webbrowser.open(f"http://127.0.0.1:{port}/")

    # Block until button clicked or timeout
    decided.wait(timeout=DECISION_TIMEOUT + 2)

    proceed = state.get("proceed", False)

    # Give the browser a moment to show the toast before we shut down
    time.sleep(2.5)
    server.shutdown()

    sys.exit(0 if proceed else 1)


if __name__ == "__main__":
    main()
