"""Self-contained HTML shown while the documentation is not servable.

This page must work before MkDocs has ever run, so it carries no assets and
builds every URL from the ingress prefix it is given.
"""

from __future__ import annotations

import html
import time

from .state import Phase, Status

_PHASE_LABEL = {
    Phase.STARTING: "Starting up",
    Phase.SYNCING: "Syncing the documentation repository",
    Phase.BUILDING: "Building the documentation",
    Phase.READY: "Ready",
    Phase.ERROR: "Something needs your attention",
}

_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
{refresh}
<style>
  :root {{ color-scheme: light dark; --fg: #1f2329; --bg: #fbfbfd; --muted: #5b6472;
           --line: #d9dde3; --card: #ffffff; --accent: #3f51b5; --error: #b3261e; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --fg: #e6e8eb; --bg: #15181c; --muted: #9aa3af;
             --line: #303640; --card: #1d2127; --accent: #9fa8da; --error: #f2b8b5; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 24px 16px; background: var(--bg); color: var(--fg);
          font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                sans-serif; }}
  main {{ max-width: 46rem; margin: 0 auto; }}
  h1 {{ font-size: 1.5rem; margin: 0 0 4px; }}
  h2 {{ font-size: 1.05rem; margin: 0 0 8px; }}
  p {{ margin: 0 0 12px; }}
  .muted {{ color: var(--muted); font-size: .9rem; }}
  section {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px;
             padding: 16px 18px; margin: 16px 0; }}
  section.error {{ border-color: var(--error); }}
  section.error h2 {{ color: var(--error); }}
  pre {{ background: rgba(127,127,127,.12); border-radius: 8px; padding: 12px;
         overflow-x: auto; white-space: pre-wrap; word-break: break-all;
         font-size: .85rem; margin: 0 0 12px; }}
  dl {{ display: grid; grid-template-columns: minmax(8rem, auto) 1fr;
        gap: 4px 16px; margin: 0; }}
  dt {{ color: var(--muted); }}
  dd {{ margin: 0; word-break: break-word; }}
  button {{ font: inherit; padding: 8px 14px; border-radius: 8px; cursor: pointer;
            border: 1px solid var(--line); background: var(--card); color: var(--fg); }}
  button.primary {{ background: var(--accent); border-color: var(--accent);
                    color: #fff; }}
  .spinner {{ display: inline-block; width: .8em; height: .8em; margin-right: .5em;
              border: 2px solid currentColor; border-right-color: transparent;
              border-radius: 50%; animation: spin .8s linear infinite;
              vertical-align: -1px; }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
</style>
</head>
<body>
<main>
  <h1>Domácí manuál</h1>
  <p class="muted">{status_line}</p>
  {body}
  <p class="muted">Add-on log: Settings &rarr; Add-ons &rarr;
     Domácí manuál &rarr; Log.</p>
</main>
<script>
function copyKey(button) {{
  const text = document.getElementById('public-key').textContent.trim();
  navigator.clipboard.writeText(text).then(function () {{
    button.textContent = 'Copied';
    setTimeout(function () {{ button.textContent = 'Copy public key'; }}, 2000);
  }});
}}
function syncNow(button) {{
  button.disabled = true;
  button.textContent = 'Syncing…';
  fetch({sync_url}, {{ method: 'POST' }}).then(function () {{
    setTimeout(function () {{ location.reload(); }}, 1500);
  }});
}}
</script>
</body>
</html>
"""


def render(status: Status, ingress_prefix: str) -> str:
    """Render the status page. ``ingress_prefix`` may be an empty string."""
    sections: list[str] = []

    if status.phase is Phase.ERROR:
        sections.append(_error_section(status))
    else:
        sections.append(
            "<section><h2><span class=\"spinner\"></span>"
            f"{html.escape(_PHASE_LABEL[status.phase])}</h2>"
            "<p>This page refreshes automatically.</p></section>"
        )

    if status.deploy_key_source and status.public_key:
        sections.append(_deploy_key_section(status))

    sections.append(_facts_section(status, ingress_prefix))

    refresh = (
        '<meta http-equiv="refresh" content="5">'
        if status.phase is not Phase.ERROR
        else ""
    )
    return _TEMPLATE.format(
        title=html.escape(f"Domácí manuál — {_PHASE_LABEL[status.phase]}"),
        refresh=refresh,
        status_line=html.escape(status.message),
        body="\n".join(sections),
        sync_url=_js_string(f"{ingress_prefix}/_app/sync"),
    )


def _error_section(status: Status) -> str:
    detail = (
        f"<pre>{html.escape(status.detail)}</pre>" if status.detail else ""
    )
    return (
        '<section class="error">'
        f"<h2>{html.escape(_PHASE_LABEL[Phase.ERROR])}</h2>"
        f"<p>{html.escape(status.message)}</p>"
        f"{detail}"
        '<button class="primary" onclick="syncNow(this)">Try again</button>'
        "</section>"
    )


def _deploy_key_section(status: Status) -> str:
    if status.deploy_key_source == "generated":
        intro = (
            "This add-on generated its own SSH key. Add the public key below to "
            "your documentation repository on GitHub under "
            "<strong>Settings &rarr; Deploy keys &rarr; Add deploy key</strong>, "
            "and leave <em>Allow write access</em> unchecked."
        )
    else:
        intro = "Public key of the SSH private key you supplied."
    return (
        "<section><h2>Deploy key</h2>"
        f"<p>{intro}</p>"
        f'<pre id="public-key">{html.escape(status.public_key)}</pre>'
        '<button onclick="copyKey(this)">Copy public key</button> '
        '<button class="primary" onclick="syncNow(this)">Sync now</button>'
        "</section>"
    )


def _facts_section(status: Status, ingress_prefix: str) -> str:
    rows = {
        "Repository": status.repository or "not configured",
        "Branch": status.branch or "-",
        "Commit": f"{status.commit[:8]} {status.commit_subject}".strip() or "-",
        "Last successful sync": _ago(status.last_success_at),
        "Next attempt": _ago(status.next_attempt_at, future=True),
    }
    items = "".join(
        f"<dt>{html.escape(key)}</dt><dd>{html.escape(str(value))}</dd>"
        for key, value in rows.items()
    )
    return f"<section><h2>Status</h2><dl>{items}</dl></section>"


def _ago(timestamp: float | None, future: bool = False) -> str:
    if not timestamp:
        return "never" if not future else "-"
    delta = int(abs(time.time() - timestamp))
    if delta < 60:
        value = f"{delta}s"
    elif delta < 3600:
        value = f"{delta // 60}m"
    else:
        value = f"{delta // 3600}h {(delta % 3600) // 60}m"
    return f"in {value}" if future else f"{value} ago"


def _js_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
