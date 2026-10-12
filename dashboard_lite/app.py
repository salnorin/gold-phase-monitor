# dashboard_lite/app.py
"""
داشبورد سبک ارگانیسم طلا — فقط Flask و sqlite3 (بدون pandas/pyarrow/streamlit).
فایل SQLite همان core.recorder را می‌خواند (جدول trades + جدول ticks) و فایل JSON حساب کنارش (پوزیشن باز، سرمایه).
    python -m dashboard_lite                       # http://127.0.0.1:5000
    python -m dashboard_lite --db PATH --port 5001 --host 0.0.0.0
    GOLD_DB=PATH python -m dashboard_lite
فقط خواندنی؛ چیزی نمی‌نویسد.
"""
import argparse
import json
import os
import sqlite3
from pathlib import Path

from flask import Flask, jsonify, render_template_string

DEFAULT_DB = Path.home() / ".local" / "share" / "gold-phase-monitor" / "live_account_gold.sqlite"
CREDIT = "این ارگانیسم توسط سالار خانبابا و با همفکری گروک بات خلق شده است"


def _rows(con, sql):
    try:
        return [dict(r) for r in con.execute(sql)]
    except sqlite3.OperationalError:          # جدول هنوز ساخته نشده
        return []


def load_state(db):
    db = Path(db).expanduser()
    out = dict(db=str(db), exists=db.exists(), trades=[], ticks=[], latest=None, position=None,
               start_equity=None, equity=None)
    if db.exists():
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        out["trades"] = _rows(con, "SELECT * FROM trades ORDER BY exit_time DESC")
        out["ticks"] = list(reversed(_rows(con, "SELECT * FROM ticks ORDER BY time DESC LIMIT 1440")))
        con.close()
    js = db.with_suffix(".json")
    if js.exists():
        try:
            st = json.loads(js.read_text(encoding="utf-8"))
            out.update(start_equity=st.get("start_equity"), equity=st.get("equity"), position=st.get("position"))
        except Exception:
            pass
    for t in out["ticks"]:
        if isinstance(t.get("reason"), str):
            try:
                t["reason"] = json.loads(t["reason"])
            except ValueError:
                t["reason"] = None
    out["latest"] = out["ticks"][-1] if out["ticks"] else None
    out["why"] = (out["latest"] or {}).get("reason")
    pnl = [float(t["pnl"] or 0) for t in out["trades"]]
    n, wins = len(pnl), sum(1 for p in pnl if p > 0)
    s0 = out["start_equity"]
    if s0 is None and out["equity"] is not None:
        s0 = out["equity"] - sum(pnl)
    eq = out["latest"]["equity"] if out["latest"] else out["equity"]
    out["stats"] = dict(n=n, wins=wins, losses=n - wins, win_rate=(wins / n) if n else None, realized=sum(pnl),
                        start=s0, equity=eq,
                        change_pct=((eq / s0 - 1) if (s0 and eq is not None) else None),
                        mood="neutral" if n == 0 else ("bull" if sum(pnl) > 0 else "bear"))
    return out


PAGE = r"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="60">
<title>Gold Organism</title><style>
body{font-family:system-ui,Tahoma,sans-serif;background:#111;color:#eee;margin:0;padding:12px}
.card{background:#1d1d1d;border-radius:10px;padding:12px;margin:10px 0}.bull{border-right:6px solid #2e7d32}
.bear{border-right:6px solid #c62828}.neutral{border-right:6px solid #777}.k{color:#aaa;font-size:.85em}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px}.v{font-size:1.3em;font-weight:bold}
table{width:100%;border-collapse:collapse;font-size:.85em}td,th{padding:4px;border-bottom:1px solid #333;text-align:center}
.pos{color:#66bb6a}.neg{color:#ef5350}button{background:#333;color:#eee;border:0;border-radius:6px;padding:4px 10px}
.credit{color:#d4af37;text-align:center;margin:18px 0;font-size:.9em}svg{width:100%;height:160px;background:#161616}
</style></head><body>
<div style="display:flex;justify-content:space-between;align-items:center"><h2 data-t="title"></h2>
<div><button onclick="L('fa')">FA</button><button onclick="L('de')">DE</button><button onclick="L('en')">EN</button></div></div>
<div class="card grid">
 <div><div class="k" data-t="price"></div><div class="v">{{ fmt(latest.price) if latest else '—' }}</div></div>
 <div><div class="k" data-t="decision"></div><div class="v">{{ latest.decision if latest else '—' }}{{ ' 💤' if latest and latest.asleep else '' }}</div></div>
 <div><div class="k" data-t="equity"></div><div class="v">{{ fmt(st.equity) }} $</div></div>
 <div><div class="k" data-t="updated"></div><div>{{ latest.time[:19] if latest else '—' }}</div></div>
</div>
<div class="card"><b data-t="why"></b>{% if why and why.profile %} <span class="k">[{{ why.profile }}]</span>{% endif %}
<ul id="why" style="margin:6px 0;padding-inline-start:18px"></ul>
<div class="k" data-t="neutral_note"></div></div>
<script>const WHY={{ why_json|safe }};</script>
<div class="card {{ st.mood }}"><b data-t="success"></b> — <span data-t="{{ st.mood }}"></span>
<div class="grid">
 <div><div class="k" data-t="start"></div><div class="v">{{ fmt(st.start) }} $</div></div>
 <div><div class="k" data-t="equity"></div><div class="v">{{ fmt(st.equity) }} $</div></div>
 <div><div class="k">%</div><div class="v {{ 'pos' if (st.change_pct or 0) >= 0 else 'neg' }}">{{ '%+.2f%%'|format(st.change_pct*100) if st.change_pct is not none else '—' }}</div></div>
 <div><div class="k" data-t="winrate"></div><div class="v">{{ '%.0f%%'|format(st.win_rate*100) if st.win_rate is not none else '—' }}</div></div>
 <div><div class="k" data-t="trades"></div><div class="v">{{ st.n }} ({{ st.wins }}/{{ st.losses }})</div></div>
</div></div>
<div class="card"><b data-t="open"></b>:
{% if pos %} {{ 'LONG' if pos.direction > 0 else 'SHORT' }} @ {{ fmt(pos.entry) }} · SL {{ fmt(pos.stop) }} · TP {{ fmt(pos.target) }}
{% else %}<span data-t="none"></span>{% endif %}</div>
<div class="card"><b data-t="chart"></b> <span class="k">(<span style="color:#d4af37">PAXG</span> / <span style="color:#4fc3f7">equity</span>)</span>
{{ svg|safe }}</div>
<div class="card" style="overflow-x:auto"><b data-t="trades"></b>
<table><tr><th data-t="dir"></th><th data-t="entry_t"></th><th data-t="exit_t"></th><th data-t="entry"></th><th data-t="exit"></th><th>SL</th><th>TP</th><th>P&amp;L</th><th>R</th><th data-t="reason"></th></tr>
{% for t in trades %}<tr><td>{{ t.direction }}</td><td>{{ (t.entry_time or '')[:16] }}</td><td>{{ (t.exit_time or '')[:16] }}</td>
<td>{{ t.entry }}</td><td>{{ t.exit }}</td><td>{{ t.stop }}</td><td>{{ t.target }}</td>
<td class="{{ 'pos' if (t.pnl or 0) > 0 else 'neg' }}">{{ t.pnl }}</td><td>{{ t.R }}</td><td>{{ t.reason }}</td></tr>
{% else %}<tr><td colspan="10" data-t="notrades"></td></tr>{% endfor %}</table></div>
{% if not exists %}<div class="card neg">DB: {{ db }} — <span data-t="nodb"></span></div>{% endif %}
<div class="credit">{{ credit }}</div>
<script>
const T={fa:{why:"چرا این تصمیم؟",neutral_note:"«خنثی» در کارت موفقیت یعنی هنوز هیچ معامله‌ای بسته نشده؛ تصمیم جداست.",nowhy:"هنوز دلیلی ثبت نشده (ضبط‌کننده‌ی جدید را اجرا کنید)",move_1h:"قیمت {v} در ۶۰ دقیقه‌ی اخیر",move_24h:"قیمت {v} در ۲۴ ساعت اخیر",market:"بازار: {v}",organ_score:"توافق ارگان‌ها {v} {op} {thr} لازم",confidence:"اطمینان {v} {op} {thr} لازم",energy:"انرژی (ATP) {v} {op} {thr}",stress:"استرس {v} (سقف {thr})",dominance:"غلبه‌ی حالت {v} {op} {thr} لازم",doubt:"تردید {v} (سقف {thr})",whale:"ردپای نهنگ در {v} کندل اخیر (احتیاط {thr} کندل)",volatility:"نوسان {v}× عادی (سقف {thr})",cooldown:"استراحت اجباری",in_position:"در پوزیشن",oxygen:"اکسیژن/نقدینگی {v} (کف {thr})",momentum:"بازده {n} کندل {v} (آستانه ±{thr})",okw:"✅",bad:"⛔",title:"ارگانیسم طلا",price:"قیمت PAXG",decision:"تصمیم",equity:"سرمایه",updated:"به‌روزرسانی",success:"کارت موفقیت",
bull:"گاوی (سود)",bear:"خرسی (زیان)",neutral:"خنثی",start:"سرمایه‌ی شروع",winrate:"نرخ برد",trades:"معاملات",open:"پوزیشن باز",
none:"ندارد",chart:"نمودار",dir:"جهت",entry_t:"ورود",exit_t:"خروج",entry:"قیمت ورود",exit:"قیمت خروج",reason:"دلیل",
notrades:"هنوز معامله‌ای بسته نشده",nodb:"فایل پیدا نشد؛ اول core.recorder را اجرا کنید"},
de:{why:"Warum diese Entscheidung?",neutral_note:"„Neutral“ auf der Erfolgskarte heißt: noch kein geschlossener Trade; die Entscheidung ist davon getrennt.",nowhy:"Noch kein Grund gespeichert (neuen Recorder starten)",move_1h:"Preis {v} in den letzten 60 Min",move_24h:"Preis {v} in 24 Std",market:"Markt: {v}",organ_score:"Organ-Einigkeit {v} {op} {thr} nötig",confidence:"Konfidenz {v} {op} {thr} nötig",energy:"Energie (ATP) {v} {op} {thr}",stress:"Stress {v} (max {thr})",dominance:"Regime-Dominanz {v} {op} {thr} nötig",doubt:"Zweifel {v} (max {thr})",whale:"Wal-Spur in {v} der letzten Kerzen (Vorsicht {thr})",volatility:"Volatilität {v}× normal (max {thr})",cooldown:"Zwangspause",in_position:"In Position",oxygen:"Liquidität {v} (min {thr})",momentum:"Rendite über {n} Kerzen {v} (Schwelle ±{thr})",okw:"✅",bad:"⛔",title:"Gold-Organismus",price:"PAXG-Preis",decision:"Entscheidung",equity:"Kapital",updated:"Aktualisiert",success:"Erfolgskarte",
bull:"Bulle (Gewinn)",bear:"Bär (Verlust)",neutral:"Neutral",start:"Startkapital",winrate:"Trefferquote",trades:"Trades",open:"Offene Position",
none:"keine",chart:"Diagramm",dir:"Richtung",entry_t:"Einstieg",exit_t:"Ausstieg",entry:"Einstiegspreis",exit:"Ausstiegspreis",reason:"Grund",
notrades:"Noch keine geschlossenen Trades",nodb:"Datei fehlt; zuerst core.recorder starten"},
en:{why:"Why this decision?",neutral_note:"\"Neutral\" on the success card just means no closed trades yet; the decision is separate.",nowhy:"No reason logged yet (run the new recorder)",move_1h:"price {v} in last 60 min",move_24h:"price {v} in last 24 h",market:"market: {v}",organ_score:"organ agreement {v} {op} {thr} needed",confidence:"confidence {v} {op} {thr} needed",energy:"energy (ATP) {v} {op} {thr}",stress:"stress {v} (max {thr})",dominance:"regime dominance {v} {op} {thr} needed",doubt:"doubt {v} (max {thr})",whale:"whale footprint in {v} recent bars (caution {thr})",volatility:"volatility {v}× normal (max {thr})",cooldown:"forced rest",in_position:"in position",oxygen:"oxygen/liquidity {v} (floor {thr})",momentum:"{n}-bar return {v} (threshold ±{thr})",okw:"✅",bad:"⛔",title:"Gold Organism",price:"PAXG price",decision:"Decision",equity:"Equity",updated:"Updated",success:"Success card",
bull:"Bull (profit)",bear:"Bear (loss)",neutral:"Neutral",start:"Start capital",winrate:"Win rate",trades:"Trades",open:"Open position",
none:"none",chart:"Chart",dir:"Dir",entry_t:"Entry time",exit_t:"Exit time",entry:"Entry",exit:"Exit",reason:"Reason",
notrades:"No closed trades yet",nodb:"File not found; run core.recorder first"}};
function L(l){localStorage.lang=l;document.documentElement.lang=l;document.documentElement.dir=l=="fa"?"rtl":"ltr";
document.querySelectorAll("[data-t]").forEach(e=>{e.textContent=T[l][e.dataset.t]??e.dataset.t})}
function pct(x){return (x>=0?"+":"")+(x*100).toFixed(2)+"%"}
function W(l){const u=document.getElementById("why");if(!u)return;u.innerHTML="";
if(!WHY||!WHY.items){u.innerHTML="<li>"+T[l].nowhy+"</li>";return}
const top=document.createElement("li");top.textContent=WHY.action+" — "+(WHY.reason||"");u.appendChild(top);
for(const it of WHY.items){let tpl=T[l][it.k];if(!tpl)continue;
 const isP=["move_1h","move_24h","momentum"].includes(it.k);
 const v=it.v==null?"—":(isP?pct(it.v):it.v),thr=it.thr==null?"":(it.k=="momentum"?(it.thr*100).toFixed(2)+"%":it.thr);
 const op=it.ok?"≥":"<";
 const li=document.createElement("li");li.textContent=(it.ok?"":"⛔ ")+tpl.replace("{v}",v).replace("{thr}",thr).replace("{op}",op).replace("{n}",it.n||"");
 if(!it.ok)li.className="neg";u.appendChild(li)}}
const _L=L;L=function(l){_L(l);W(l)};
L(localStorage.lang||"fa");
</script></body></html>"""


def _fmt(x):
    try:
        return f"{float(x):,.2f}"
    except (TypeError, ValueError):
        return "—"


def svg_chart(ticks, w=600, h=160):
    """نمودار خطی ساده (SVG داخلی، بدون CDN): قیمت و سرمایه، هر کدام با مقیاس خودش."""
    def line(vals, color):
        vals = [v for v in vals if v is not None]
        if len(vals) < 2:
            return ""
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or 1
        pts = " ".join(f"{i * w / (len(vals) - 1):.1f},{h - 8 - (v - lo) / span * (h - 16):.1f}" for i, v in enumerate(vals))
        return f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{pts}"/>'
    body = line([t.get("price") for t in ticks], "#d4af37") + line([t.get("equity") for t in ticks], "#4fc3f7")
    if not body:
        body = f'<text x="{w / 2}" y="{h / 2}" fill="#777" text-anchor="middle">…</text>'
    return f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none">{body}</svg>'


def _ns(d):
    class N(dict):
        __getattr__ = dict.get
    return N(d) if d else None


def create_app(db=None):
    app = Flask(__name__)
    app.config["DB"] = str(db or os.getenv("GOLD_DB") or DEFAULT_DB)

    @app.get("/api/state")
    def api_state():
        return jsonify(load_state(app.config["DB"]))

    @app.get("/")
    def index():
        s = load_state(app.config["DB"])
        return render_template_string(PAGE, latest=_ns(s["latest"]), st=_ns(s["stats"]), pos=_ns(s["position"]),
                                      trades=[_ns(t) for t in s["trades"]], svg=svg_chart(s["ticks"]), why=_ns(s["why"]),
                                      why_json=json.dumps(s["why"], ensure_ascii=False).replace("</", "<\\/"),
                                      exists=s["exists"], db=s["db"], credit=CREDIT, fmt=_fmt)

    return app


def main(argv=None):
    ap = argparse.ArgumentParser(description="Lightweight Flask dashboard for core.recorder SQLite")
    ap.add_argument("--db", default=None, help="SQLite path (env GOLD_DB; default ~/.local/share/gold-phase-monitor/live_account_gold.sqlite)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5000)
    a = ap.parse_args(argv)
    app = create_app(a.db)
    print(f"dashboard: http://{a.host}:{a.port}  db={app.config['DB']}", flush=True)
    app.run(host=a.host, port=a.port, debug=False)
    return 0
