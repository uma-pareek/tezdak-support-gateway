#!/usr/bin/env python3
"""Small local viewer for the Tezdak support assistant (standard library only).

    PYTHONPATH=vendor:. python3 tools/visualizer.py            # then open http://127.0.0.1:8800

What it does
  * Browse: replay any chat as a conversation, with the tool calls the assistant made. Sources are the dev chats
    (`data/dev`) and last month's traces (`data/traces`). Runs you make under `runs/` show up inside each dev chat.
  * Try it: pick a dev shipment and talk to the assistant yourself, as the customer. Each reply shows the tool calls.
  * Run: play one dev chat with its scripted customer and watch it.

The model key stays on the server. It is read from OPENAI_API_KEY / OPENAI_BASE_URL (or .env.prorated), exactly as
the assistant does when you run the eval; it is never sent to the browser. Use LLM_MODE=mock to try the page
without any model calls. The page only shows what happened. It does not say whether it was good.
"""
import argparse
import json
import os
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "vendor"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from eval import run_eval as RE  # noqa: E402
from eval.trace import Trace, read_trace  # noqa: E402

_LOCK = threading.Lock()
SESSIONS: dict = {}
ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")


def _safe(name: str) -> bool:
    return bool(name) and set(name) <= ID_CHARS and ".." not in name


def _load_env_file():
    for name in (".env.prorated",):
        f = ROOT / name
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip().removeprefix("export ").strip(), v.strip().strip("'\""))


def _dev_scenarios() -> dict:
    out = {}
    for s in RE.load_scenarios(ROOT / "data" / "dev"):
        out[s["id"]] = s
    return out


def listing() -> dict:
    dev = []
    for sid, s in sorted(_dev_scenarios().items()):
        opening = ((s.get("customer") or {}).get("script") or {}).get("opening") or ""
        dev.append({"id": sid, "status": s["world"]["shipment"]["status"], "mode": s["world"]["shipment"]["payment_mode"],
                    "opening": str(opening)[:100]})
    tr = sorted(p.stem for p in (ROOT / "data" / "traces").glob("*.jsonl"))
    runs = {}
    for d in sorted((ROOT / "runs").glob("*/traces")) if (ROOT / "runs").exists() else []:
        runs[d.parent.name] = sorted(p.stem for p in d.glob("*.jsonl"))
    return {"dev": dev, "traces": tr, "runs": runs}


def load_events(src: str, sid: str):
    if not (_safe(sid) and (src in ("traces",) or (src.startswith("runs/") and _safe(src[5:])))):
        raise ValueError("bad source")
    path = ROOT / ("data/traces" if src == "traces" else src + "/traces") / (sid + ".jsonl")
    return read_trace(path)


def _text_of(turn):
    return RE._field(turn, "text", "reply", "message") or (turn if isinstance(turn, str) else "")


def _new_session(sid: str) -> dict:
    s = _dev_scenarios()[sid]
    sim = RE.default_carrier_factory(s)
    trace = Trace(sid, clock=lambda: sim.now.isoformat())
    carrier = RE.TracingCarrier(sim, trace)
    carrier.awb = s["world"]["shipment"]["awb"]
    carrier.scenario = s
    trace.add("session_start", {"channel": "chat", "scenario": sid})
    agent = RE.default_agent_factory(carrier)
    return {"scenario": s, "sim": sim, "trace": trace, "agent": agent, "conversation": [], "sent": 0}


def chat(body: dict) -> dict:
    token = body.get("session") or uuid.uuid4().hex
    with _LOCK:
        if token not in SESSIONS:
            SESSIONS[token] = _new_session(body["scenario"])
        st = SESSIONS[token]
        msg = str(body.get("message", "")).strip()
        if not msg:
            raise ValueError("empty message")
        st["conversation"].append({"role": "user", "content": msg})
        st["trace"].add("customer_msg", {"text": msg})
        try:
            turn = st["agent"].handle(st["conversation"])
        except Exception as exc:  # shown to the person trying it
            st["trace"].add("agent_msg", {"text": "", "commitments": [], "error": f"{type(exc).__name__}: {exc}"})
            st["conversation"].pop()
            ev = st["trace"].events[st["sent"]:]
            st["sent"] = len(st["trace"].events)
            return {"session": token, "events": ev, "error": f"{type(exc).__name__}: {exc}"}
        text = _text_of(turn)
        st["conversation"].append({"role": "assistant", "content": text})
        st["trace"].add("agent_msg", {"text": text, "commitments": RE._field(turn, "commitments") or []})
        ev = st["trace"].events[st["sent"]:]
        st["sent"] = len(st["trace"].events)
        return {"session": token, "events": ev}


def run_scripted(sid: str) -> dict:
    s = _dev_scenarios()[sid]
    res = RE.run_scenario(s, RE.default_agent_factory)
    return {"events": res.trace, "error": res.error}


def status() -> dict:
    mode = os.environ.get("LLM_MODE", "").strip().lower()
    have = bool(os.environ.get("OPENAI_API_KEY")) and bool(os.environ.get("OPENAI_BASE_URL"))
    return {"model": "mock (no model calls)" if mode == "mock" else ("live (key set on the server)" if have else "not set"),
            "hint": "" if (mode == "mock" or have) else
            "Set OPENAI_BASE_URL and OPENAI_API_KEY (or LLM_MODE=mock) before starting this page."}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, payload, ctype="application/json"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/":
                return self._send(200, PAGE.encode(), "text/html")
            if u.path == "/api/list":
                return self._send(200, listing())
            if u.path == "/api/status":
                return self._send(200, status())
            if u.path == "/api/trace":
                return self._send(200, {"events": load_events(q.get("src", ""), q.get("id", ""))})
            if u.path == "/api/world":
                s = _dev_scenarios()[q.get("id", "")]
                return self._send(200, {"now": s["world"]["now"], "shipment": s["world"]["shipment"], "scans": s["world"]["scans"]})
            self._send(404, {"error": "not found"})
        except Exception as exc:
            self._send(400, {"error": f"{type(exc).__name__}: {exc}"})

    def do_POST(self):
        u = urlparse(self.path)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            if u.path == "/api/chat":
                return self._send(200, chat(body))
            if u.path == "/api/run":
                return self._send(200, run_scripted(body.get("id", "")))
            self._send(404, {"error": "not found"})
        except Exception as exc:
            self._send(400, {"error": f"{type(exc).__name__}: {exc}"})


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tezdak chat viewer</title>
<style>
:root{--bg:#f6f5f1;--card:#fff;--ink:#1d2330;--mut:#6b7280;--line:#e3e1d9;--me:#e8efe6;--bot:#fff;--tool:#f1f0ea;--bad:#b42318;--acc:#2f5d50}
@media (prefers-color-scheme:dark){:root{--bg:#14171c;--card:#1b1f26;--ink:#e8e9ec;--mut:#9aa1ac;--line:#2b303a;--me:#23362f;--bot:#1b1f26;--tool:#232831;--bad:#f97066;--acc:#7fc2ac}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,sans-serif}
header{padding:12px 16px;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}
header h1{font-size:16px;margin:0}header span{color:var(--mut);font-size:13px}
main{display:grid;grid-template-columns:300px 1fr;height:calc(100vh - 50px)}
@media(max-width:760px){main{grid-template-columns:1fr;height:auto}}
aside{border-right:1px solid var(--line);overflow:auto;padding:8px}
.tab{display:flex;gap:6px;margin-bottom:8px}.tab button{flex:1}
button{font:inherit;padding:6px 10px;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;cursor:pointer}
button.on{border-color:var(--acc);color:var(--acc)}
.item{padding:6px 8px;border-radius:8px;cursor:pointer;font-size:13px}.item:hover,.item.sel{background:var(--card)}
.item small{display:block;color:var(--mut)}
section{overflow:auto;padding:16px;display:flex;flex-direction:column;gap:8px}
.b{max-width:78%;padding:8px 12px;border-radius:12px;border:1px solid var(--line);white-space:pre-wrap}
.me{align-self:flex-end;background:var(--me)}.bot{align-self:flex-start;background:var(--bot)}
.tool{align-self:flex-start;background:var(--tool);font:12px/1.4 ui-monospace,Menlo,monospace;border-radius:8px;padding:6px 10px;max-width:90%;border:1px solid var(--line)}
.tool.timeout{border-color:var(--bad);color:var(--bad)}.note{align-self:center;color:var(--mut);font-size:12px}
details summary{cursor:pointer}pre{margin:4px 0 0;white-space:pre-wrap;word-break:break-word}
form{display:flex;gap:8px;margin-top:8px}input[type=text]{flex:1;font:inherit;padding:8px 10px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink)}
.world{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 12px;font-size:12.5px}
.err{color:var(--bad)}
button.q{flex:0 0 auto;width:28px;height:28px;padding:0;border-radius:50%;font-weight:600}
.help{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 12px;font-size:13px;margin:6px 16px}
aside .help{margin:0 0 8px}
.runs{display:flex;gap:6px;flex-wrap:wrap;align-items:center;font-size:12.5px;color:var(--mut)}
</style></head><body>
<header><h1>Tezdak chat viewer</h1><button class="q" id="hq" title="What is this page?">?</button><span id="st"></span></header>
<div id="hhelp" class="help" hidden><b>What is this page?</b> Tezdak is a made-up parcel delivery company. Its support assistant answers customers who write about late or failed deliveries. This page lets you watch the assistant work. The grey boxes are what it looked up or did (finding the parcel, reading the tracking scans, booking, escalating). The page shows what happened. It does not say whether it was right: judging that is your job.</div>
<main><aside><div class="tab"><button id="t1" class="on">Dev chats</button><button class="q" id="q1" title="What are dev chats?">?</button><button id="t2">Traces</button><button class="q" id="q2" title="What are traces?">?</button></div><div id="thelp" class="help" hidden></div><div id="list"></div></aside>
<section id="view"><div class="note">Pick a chat on the left. Start with a dev chat: type as the customer and watch what the assistant does.</div></section></main>
<script>
const $=s=>document.querySelector(s);let L=null,tab=1,session=null,cur=null;
const esc=t=>String(t).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
async function api(u,b){const r=await fetch(u,b?{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(b)}:{});return r.json()}
function toolCard(e){const d=e.data,k=e.kind;if(k==='tool_call')return `<div class="tool"><details><summary>call ${esc(d.name)}${d.attempt?` (retry ${d.attempt})`:''}</summary><pre>${esc(JSON.stringify(d.args,null,1))}</pre></details></div>`;
if(k==='tool_result')return `<div class="tool"><details><summary>result ${esc(d.name)}</summary><pre>${esc(JSON.stringify(d.result,null,1))}</pre></details></div>`;
if(k==='tool_timeout')return `<div class="tool timeout">timeout on ${esc(d.name)} (after ${esc(d.timeout_s)}s)</div>`;
if(k==='ledger')return `<div class="tool"><details><summary>world: ${esc(d.type||'change')}</summary><pre>${esc(JSON.stringify(d,null,1))}</pre></details></div>`;
if(k==='feature_call'||k==='feature_result')return `<div class="tool"><details><summary>${k.replace('_',' ')} ${esc(d.name||'')}</summary><pre>${esc(JSON.stringify(d,null,1))}</pre></details></div>`;
if(k==='llm_usage')return `<div class="note">model calls ${d.calls??'?'}, spend about $${d.spend_usd??'?'}${d.error?` <span class="err">${esc(d.error)}</span>`:''}</div>`;
return ''}
function evHtml(e){if(e.kind==='customer_msg')return `<div class="b me">${esc(e.data.text)}</div>`;
if(e.kind==='agent_msg')return `<div class="b bot">${esc(e.data.text)||'<i>(no reply)</i>'}${e.data.error?`<div class="err">${esc(e.data.error)}</div>`:''}</div>`;
if(e.kind==='session_start')return `<div class="note">chat started</div>`;return toolCard(e)}
function show(events,head){$('#view').innerHTML=(head||'')+events.map(evHtml).join('')}
function renderList(){const el=$('#list');el.innerHTML='';let rows=[];
if(tab===1)rows=L.dev.map(d=>({k:'dev',id:d.id,t:d.id,s:`${d.status} · ${d.mode} · ${d.opening}`}));
if(tab===2)rows=L.traces.map(i=>({k:'traces',id:i,t:i,s:'last month'}));
if(!rows.length)el.innerHTML='<div class="note">nothing here yet</div>';
rows.forEach(r=>{const d=document.createElement('div');d.className='item';d.innerHTML=`${esc(r.t)}<small>${esc(r.s)}</small>`;d.onclick=()=>{document.querySelectorAll('.item').forEach(x=>x.classList.remove('sel'));d.classList.add('sel');open(r)};el.appendChild(d)})}
async function open(r){cur=r;session=null;if(r.k==='dev')return openDev(r.id);const j=await api(`/api/trace?src=${encodeURIComponent(r.k)}&id=${encodeURIComponent(r.id)}`);if(j.error)return $('#view').innerHTML=`<div class="err">${esc(j.error)}</div>`;show(j.events)}
async function openDev(id){const w=await api('/api/world?id='+id);const s=w.shipment;
const head=`<div class="world"><b>${esc(id)}</b> · ${esc(s.awb)} · ${esc(s.status)} · ${esc(s.payment_mode)} ₹${esc(s.amount_inr)} · ${esc(s.tier)} · attempts used ${esc(s.attempts_used)}<br>clock: ${esc(w.now)}<details><summary>scans (${w.scans.length})</summary><pre>${esc(JSON.stringify(w.scans,null,1))}</pre></details></div>`;
const mine=[];for(const r in L.runs)if(L.runs[r].includes(id))mine.push(r);
const runsRow=mine.length?`<div class="runs">Earlier runs of this chat (from your <code>runs/</code> folder): ${mine.map(r=>`<button data-run="${esc(r)}">${esc(r)}</button>`).join('')}</div>`:'';
$('#view').innerHTML=head+runsRow+`<div id="log" style="display:flex;flex-direction:column;gap:8px"></div><form id="f"><input type="text" id="m" placeholder="Write as the customer, e.g. my parcel was not delivered" autocomplete="off"><button>Send</button><button type="button" id="run">Run scripted chat</button></form>`;
$('#f').onsubmit=async ev=>{ev.preventDefault();const m=$('#m').value.trim();if(!m)return;$('#m').value='';$('#log').insertAdjacentHTML('beforeend',`<div class="b me">${esc(m)}</div><div class="note" id="wait">thinking…</div>`);
const j=await api('/api/chat',{session,scenario:id,message:m});$('#wait')?.remove();if(j.error&&!j.events)return $('#log').insertAdjacentHTML('beforeend',`<div class="err">${esc(j.error)}</div>`);session=j.session;
$('#log').insertAdjacentHTML('beforeend',j.events.filter(e=>e.kind!=='customer_msg').map(evHtml).join(''));if(j.error)$('#log').insertAdjacentHTML('beforeend',`<div class="err">${esc(j.error)}</div>`)};
document.querySelectorAll('[data-run]').forEach(b=>b.onclick=async()=>{const j=await api(`/api/trace?src=${encodeURIComponent('runs/'+b.dataset.run)}&id=${encodeURIComponent(id)}`);$('#log').innerHTML=j.error?`<div class="err">${esc(j.error)}</div>`:`<div class="note">run: ${esc(b.dataset.run)}</div>`+j.events.map(evHtml).join('')});
$('#run').onclick=async()=>{$('#log').innerHTML='<div class="note">running the scripted chat…</div>';const j=await api('/api/run',{id});$('#log').innerHTML=(j.events||[]).map(evHtml).join('')+(j.error?`<div class="err">${esc(j.error)}</div>`:'')}}
[1,2].forEach(n=>$('#t'+n).onclick=()=>{tab=n;[1,2].forEach(k=>$('#t'+k).classList.toggle('on',k===n));$('#thelp').hidden=true;renderList()});
const HELP={1:'<b>Dev chats</b> are 15 practice situations that come with the task: each one is a made-up parcel with its tracking history, plus a made-up customer. They are the chats the eval runs again and again. Click one, then write as the customer, or press <i>Run scripted chat</i> to let the made-up customer play it. They are examples, not the full picture of real traffic.',2:'<b>Traces</b> are recordings of how the old assistant handled chats last month. They are read-only: you cannot re-run them, and they carry no answers. Read them to find out what went wrong in real use.'};
[1,2].forEach(n=>$('#q'+n).onclick=()=>{const h=$('#thelp');h.innerHTML=HELP[n];h.hidden=!h.hidden});
$('#hq').onclick=()=>{$('#hhelp').hidden=!$('#hhelp').hidden};
(async()=>{const s=await api('/api/status');$('#st').textContent='model: '+s.model+(s.hint?' — '+s.hint:'');L=await api('/api/list');renderList()})();
</script></body></html>"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Local chat viewer for the Tezdak assistant")
    ap.add_argument("--port", type=int, default=8800)
    args = ap.parse_args(argv)
    _load_env_file()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Tezdak chat viewer on http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
