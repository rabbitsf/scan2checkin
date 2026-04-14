#!/usr/bin/env python3
"""
commit_preview.py — Show a HTML diff preview before every git commit.
Starts a local HTTP server, opens the browser, waits for terminal approval.
Exit 0 = proceed, Exit 1 = abort.
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
        escaped = _esc(line)
        if line.startswith("diff --git") or line.startswith("index ") \
                or line.startswith("--- ") or line.startswith("+++ "):
            out.append(f'<span class="df">{escaped}</span>')
        elif line.startswith("@@"):
            out.append(f'<span class="hunk">{escaped}</span>')
        elif line.startswith("+"):
            out.append(f'<span class="add">{escaped}</span>')
        elif line.startswith("-"):
            out.append(f'<span class="del">{escaped}</span>')
        else:
            out.append(escaped)
    return "\n".join(out)


def build_html(branch: str, stat: str, diff: str, files: str) -> str:
    files_html = _render_files(files)
    diff_html  = _render_diff(diff)
    stat_html  = _esc(stat.strip()) or "No stat available."

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Commit Preview</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d1117;color:#e6edf3;padding:24px 28px}}
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
.diff-wrap{{background:#161b22;border:1px solid #30363d;border-radius:6px;overflow:auto;max-height:62vh}}
pre{{font-family:'SFMono-Regular',Consolas,monospace;font-size:.76rem;line-height:1.55;padding:16px;tab-size:4}}
.df  {{color:#79c0ff;font-weight:600;display:block}}
.hunk{{color:#a5d6ff;background:#1b2a3b;display:block}}
.add {{color:#3fb950;background:#0d2818;display:block}}
.del {{color:#f85149;background:#2d0f0f;display:block}}
#overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.78);align-items:center;justify-content:center;z-index:99}}
#overlay.show{{display:flex}}
.toast{{background:#161b22;border:2px solid #30363d;border-radius:14px;padding:36px 56px;text-align:center}}
.toast.ok {{border-color:#3fb950}}
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
    <table>{files_html}</table>
  </div>

  <div class="section">
    <div class="stitle">Stat</div>
    <div class="stat">{stat_html}</div>
  </div>

  <div class="section">
    <div class="stitle">Diff</div>
    <div class="diff-wrap"><pre>{diff_html}</pre></div>
  </div>

  <div id="overlay">
    <div class="toast" id="toast">
      <div class="ti" id="ti"></div>
      <div class="tm" id="tm"></div>
    </div>
  </div>

  <script>
    const overlay = document.getElementById('overlay');
    const toast = document.getElementById('toast');
    function poll() {{
      fetch('/status').then(r => r.json()).then(d => {{
        if (d.done) {{
          overlay.classList.add('show');
          if (d.result === 'committed') {{
            toast.classList.add('ok');
            document.getElementById('ti').textContent = '✅';
            document.getElementById('tm').textContent = 'Committed!';
          }} else {{
            toast.classList.add('err');
            document.getElementById('ti').textContent = '🚫';
            document.getElementById('tm').textContent = 'Commit aborted.';
          }}
          setTimeout(() => window.close(), 2000);
        }} else {{
          setTimeout(poll, 800);
        }}
      }}).catch(() => setTimeout(poll, 1000));
    }}
    poll();
  </script>
</body>
</html>"""


# ── HTTP server ───────────────────────────────────────────────────────────────

def find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def make_handler(html: str, state: dict):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/status":
                body = json.dumps(state).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/":
                body = html.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):
            pass  # suppress access logs

    return Handler


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    branch, stat, diff, files = get_git_info()
    html  = build_html(branch, stat, diff, files)
    port  = find_free_port()
    state = {"done": False, "result": None}

    server = HTTPServer(("127.0.0.1", port), make_handler(html, state))
    t = threading.Thread(target=server.serve_forever)
    t.daemon = True
    t.start()

    webbrowser.open(f"http://127.0.0.1:{port}/")

    # Read from /dev/tty so the prompt works even when stdin is redirected
    sys.stdout.write("\nReview commit in browser. Proceed? [y/N] ")
    sys.stdout.flush()
    try:
        with open("/dev/tty") as tty:
            answer = tty.readline().strip().lower()
    except Exception:
        answer = "n"

    proceed = answer == "y"
    state["done"]   = True
    state["result"] = "committed" if proceed else "aborted"

    time.sleep(2.5)  # Let browser poll, show toast, and close
    server.shutdown()

    sys.exit(0 if proceed else 1)


if __name__ == "__main__":
    main()
