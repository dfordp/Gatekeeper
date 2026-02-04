# http_routes.py
import os
import json as _json
import asyncio
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, JSONResponse, HTMLResponse, StreamingResponse

from utils.datetime_utils import to_iso_string
from session import sessions
from ticket import Ticket

http_router = APIRouter()

# -------------------- Helpers --------------------

def _autorefresh_meta(refresh_seconds: Optional[int]) -> str:
    if not refresh_seconds or refresh_seconds <= 0:
        return ""
    return f'<meta http-equiv="refresh" content="{int(refresh_seconds)}" />'

# -------------------- Landing page --------------------

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Gatekeeper - Support Intake System</title>
  <style>
    :root { color-scheme: light dark; }
    * { box-sizing: border-box; }
    body { margin:0; font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif;
           min-height:100vh; display:grid; place-items:center; background: #f7fafc; }
    .card { background: rgba(0,0,0,0); border-radius: 20px; padding: 32px; max-width: 900px; width: 94%;
            box-shadow: 0 18px 60px rgba(0,0,0,0.25); }
    h1 { margin: 0 0 8px; color:#2d3748; }
    p  { margin: 0 0 20px; color:#4a5568; }
    .grid { display:grid; gap:14px; grid-template-columns: repeat(auto-fit,minmax(240px,1fr)); margin-top: 12px; }
    .tile { padding:18px; border: 2px solid #e2e8f0; background:#fff; border-radius: 12px; text-decoration:none; display:block; }
    .tile:hover { border-color:#667eea; box-shadow: 0 4px 14px rgba(102,126,234,0.2); transform: translateY(-1px); }
    .t1 { font-weight:700; color:#2d3748; margin:0 0 6px; }
    .t2 { color:#718096; margin:0 0 10px; }
    code { background:#f7fafc; padding: 4px 6px; border-radius:6px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>🚪 Gatekeeper</h1>
    <p>Support Intake & Ticket Management System</p>
    <div class="grid">
      <a class="tile" href="/dashboard">
        <div class="t1">📊 Dashboard</div>
        <div class="t2">View all active sessions</div>
        <code>/dashboard</code>
      </a>
      <a class="tile" href="/tickets">
        <div class="t1">🎫 Tickets</div>
        <div class="t2">All created support tickets</div>
        <code>/tickets</code>
      </a>
      <a class="tile" href="/api/sessions">
        <div class="t1">📋 Sessions JSON</div>
        <div class="t2">Current sessions feed</div>
        <code>/api/sessions</code>
      </a>
    </div>
  </div>
</body>
</html>
"""

@http_router.get("/")
def index():
    return HTMLResponse(INDEX_HTML)

# -------------------- JSON APIs --------------------

@http_router.get("/api/sessions")
def api_sessions():
    """Get all active sessions."""
    session_list = []
    for chat_id, session in sessions.items():
        session_list.append({
            "chat_id": chat_id,
            "user_name": session.user_name,
            "company_name": session.company_name,
            "issue_description": session.issue_description,
            "issue_category": session.issue_category,
            "software": session.software,
            "environment": session.environment,
            "impact": session.impact,
            "is_confirmed": session.is_confirmed,
            "ticket_id": session.ticket_id,
            "created_at": to_iso_string(session.created_at),
        })
    return JSONResponse(session_list)

@http_router.get("/api/tickets")
def api_tickets():
    """Get all tickets from tickets.log."""
    tickets_list = []
    try:
        if os.path.exists("tickets.log"):
            with open("tickets.log", "r") as f:
                for line in f:
                    try:
                        tickets_list.append(_json.loads(line))
                    except:
                        pass
    except:
        pass
    return JSONResponse(tickets_list)

# -------------------- UI Pages --------------------

def _dashboard_html(refresh: int) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Gatekeeper - Active Sessions</title>
  {_autorefresh_meta(refresh)}
  <style>
    :root {{ color-scheme: light dark; }}
    body {{ margin: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; background: #111; color:#fff; }}
    header {{ padding: 16px 24px; background: #222; border-bottom: 1px solid #333; display:flex; align-items:center; gap:10px; }}
    h1 {{ margin: 0; font-size: 22px; }}
    .muted {{ color:#aaa; font-size:12px; margin-left:auto; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; padding: 24px; }}
    .card {{ background: #1b1b1b; border: 1px solid #333; border-radius: 12px; padding: 16px; box-shadow: 0 1px 8px rgba(0,0,0,0.25); }}
    .chat-id {{ font-size: 18px; font-weight: 900; margin:0 0 12px; color:#667eea; }}
    .info-row {{ margin: 8px 0; font-size: 13px; }}
    .label {{ color:#aaa; }}
    .value {{ color:#fff; }}
    .step {{ display: inline-block; background: #667eea; color:#fff; padding: 2px 8px; border-radius: 4px; font-size: 11px; }}
    .confirmed {{ background: #48bb78; }}
  </style>
</head>
<body>
  <header>
    <h1>🚪 Active Sessions</h1>
    <div class="muted">Auto refresh: {refresh or 15}s</div>
  </header>
  <main>
    <div id="grid" class="grid"></div>
  </main>
  <script>
    const grid = document.getElementById('grid');

    function render(list){{
      grid.innerHTML = '';
      if(!list || list.length === 0){{
        const div = document.createElement('div');
        div.style.gridColumn = '1 / -1';
        div.style.color = '#aaa';
        div.style.padding = '80px 16px';
        div.style.textAlign = 'center';
        div.textContent = 'No active sessions';
        grid.appendChild(div);
        return;
      }}
      for(const s of list){{
        const card = document.createElement('div');
        card.className = 'card';
        const step_cls = s.is_confirmed ? 'confirmed' : '';
        card.innerHTML = `
          <div class="chat-id">${{s.chat_id}}</div>
          <div class="info-row"><span class="label">Name:</span> <span class="value">${{s.user_name || '—'}}</span></div>
          <div class="info-row"><span class="label">Company:</span> <span class="value">${{s.company_name || '—'}}</span></div>
          <div class="info-row"><span class="label">Issue:</span> <span class="value">${{(s.issue_description || '—').substring(0, 50)}}</span></div>
          <div class="info-row"><span class="label">Software:</span> <span class="value">${{s.software || '—'}}</span></div>
          <div class="info-row"><span class="label">Environment:</span> <span class="value">${{s.environment || '—'}}</span></div>
          <div class="info-row"><span class="label">Impact:</span> <span class="value">${{s.impact || '—'}}</span></div>
          <div class="info-row"><span class="label">Status:</span> <span class="step ${{{{s.is_confirmed ? 'confirmed' : ''}}}}">${{{{{{s.is_confirmed ? 'Confirmed' : 'Pending'}}}}}}</span></div>
          <div class="info-row"><span class="label">Ticket:</span> <span class="value">${{{{{{s.ticket_id || 'Pending'}}}}}}</span></div>
        `;
        grid.appendChild(card);
      }}
    }}

    async function load() {{
      const res = await fetch('/api/sessions', {{ cache: 'no-store' }});
      render(await res.json());
    }}

    load();
    const REFRESH = {refresh or 15};
    if (REFRESH > 0) setInterval(load, REFRESH * 1000);
  </script>
</body>
</html>"""

def _tickets_html(refresh: int) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Gatekeeper - Tickets</title>
  {_autorefresh_meta(refresh)}
  <style>
    :root {{ color-scheme: light dark; }}
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; margin:24px; background:#f7fafc; }}
    h1 {{ margin: 0 0 8px; color: #1a202c; }}
    .muted {{ color:#777; font-size: 12px; margin: 0 0 14px; }}
    table {{ width: 100%; border-collapse: collapse; background:#fff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
    th, td {{ border-bottom: 1px solid #e2e8f0; padding: 12px; text-align: left; }}
    th {{ background: #f7fafc; font-weight: 600; color: #1a202c; }}
    td {{ color: #1a202c; }}
    tr:hover {{ background: #f9fafb; }}
    .ticket-id {{ font-weight: 700; color: #667eea; }}
    .nowrap {{ white-space: nowrap; }}
    .status {{ display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
    .status-open {{ background: #bee3f8; color: #2c5aa0; }}
  </style>
</head>
<body>
  <h1>🎫 All Tickets</h1>
  <p class="muted">Support tickets created from intake conversations. Auto refresh: {refresh or 15}s</p>

  <table id="tbl">
    <thead>
      <tr>
        <th class="nowrap">Ticket ID</th>
        <th>User</th>
        <th>Company</th>
        <th>Issue</th>
        <th>Category</th>
        <th>Status</th>
        <th>Created</th>
      </tr>
    </thead>
    <tbody></tbody>
  </table>

  <script>
    const tbody = document.querySelector('#tbl tbody');

    function formatDate(isoStr) {{
      if (!isoStr) return '—';
      const d = new Date(isoStr);
      return d.toLocaleDateString() + ' ' + d.toLocaleTimeString();
    }}

    async function load() {{
      const res = await fetch('/api/tickets', {{ cache: 'no-store' }});
      const list = await res.json();
      tbody.innerHTML = '';
      for (const t of list) {{
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td class="ticket-id">${{t.ticket_id || '—'}}</td>
          <td>${{t.user_name || '—'}}</td>
          <td>${{t.company_name || '—'}}</td>
          <td>${{(t.issue_description || '—').substring(0, 40)}}</td>
          <td>${{t.issue_category || '—'}}</td>
          <td><span class="status status-${{(t.status || 'open').toLowerCase()}}">${{t.status || 'open'}}</span></td>
          <td class="nowrap">${{formatDate(t.created_at)}}</td>
        `;
        tbody.appendChild(tr);
      }}
    }}

    load();
    const REFRESH = {refresh or 15};
    if (REFRESH > 0) setInterval(load, REFRESH * 1000);
  </script>
</body>
</html>"""

@http_router.get("/dashboard")
def dashboard(refresh: Optional[int] = Query(default=15, ge=0, le=120)):
    return HTMLResponse(_dashboard_html(refresh or 15))

@http_router.get("/tickets")
def tickets(refresh: Optional[int] = Query(default=15, ge=0, le=120)):
    return HTMLResponse(_tickets_html(refresh or 15))