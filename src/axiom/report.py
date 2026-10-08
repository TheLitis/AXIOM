"""A self-contained, offline report. Input strings never become executable HTML."""

import json
from pathlib import Path


def render_report(output, timing=None, cohort=None):
    if timing is not None and cohort is not None and timing.get("challenge") != cohort.get("challenge"):
        raise ValueError("Timing and cohort challenge identities must match in a combined report")
    payload = json.dumps({"timing": timing, "cohort": cohort}, ensure_ascii=True, allow_nan=False)
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    html = TEMPLATE.replace("__AXIOM_PAYLOAD__", payload)
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:">
<title>AXIOM · Geometry Dash Difficulty Lab</title>
<style>
:root{color-scheme:dark;--bg:#0d131b;--panel:#151e29;--line:#2b394a;--text:#ecf2fa;--muted:#9baabc;--mint:#79efd0;--amber:#ffd48a;--blue:#86b4ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1200px;margin:auto;padding:36px 34px 70px}header{display:flex;align-items:center;justify-content:space-between;gap:20px;border-bottom:1px solid var(--line);padding-bottom:24px}
.brand{display:flex;align-items:center;gap:14px}.brand svg{width:42px;height:42px}.wordmark{font-size:23px;letter-spacing:6px;font-weight:800}.subtitle{font-size:11px;color:var(--muted);letter-spacing:2px;text-transform:uppercase}
.tag{display:inline-block;font:11px/1.4 ui-monospace,monospace;text-transform:uppercase;letter-spacing:1px;border:1px solid var(--line);border-radius:5px;padding:7px 11px;color:var(--amber)}
.hero{display:grid;grid-template-columns:1.7fr 1fr;align-items:center;gap:45px;margin:40px 0 28px}.eyebrow{color:var(--mint);font:12px ui-monospace,monospace;letter-spacing:2px}h1{font-size:clamp(32px,4vw,52px);letter-spacing:-1.7px;line-height:1.1;margin:15px 0 18px;max-width:700px}p{color:var(--muted);max-width:650px;margin:10px 0}.identity{border-left:2px solid var(--mint);padding:12px 20px;font:12px/1.8 ui-monospace,monospace;overflow-wrap:anywhere;color:var(--muted)}.identity strong{color:var(--text)}
.notice{padding:14px 18px;background:#332b1e;border:1px solid #68502b;border-radius:8px;color:var(--amber);margin:22px 0}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:24px 0}.metric{padding:20px;background:var(--panel);border:1px solid var(--line);border-radius:10px}.metric label{color:var(--muted);font-size:12px;display:block}.value{font:32px/1.4 ui-monospace,monospace;margin:8px 0;color:var(--text)}.detail{color:var(--muted);font-size:11px}
.grid{display:grid;grid-template-columns:1.4fr 1fr;gap:20px;margin:20px 0}.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:22px;min-width:0}.panel h2{margin:0;font-size:18px;font-weight:600}.panel h3{font-size:14px}.panel .intro{font-size:12px;color:var(--muted);margin:8px 0 18px}.route-tabs{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}button{background:transparent;color:var(--muted);border:1px solid var(--line);border-radius:6px;padding:8px 12px;cursor:pointer;font:inherit;font-size:12px}button:hover{border-color:var(--mint);color:var(--text)}button[aria-pressed=true]{background:#233c3b;color:var(--mint);border-color:#57998d}button:focus-visible,summary:focus-visible{outline:2px solid var(--mint);outline-offset:3px}
.plot{width:100%;height:auto;display:block}.plot text{font:11px ui-monospace,monospace;fill:var(--muted)}.plot .accent{fill:var(--mint)}.plot .gridline{stroke:var(--line)}.plot .axis{stroke:#78899b;stroke-dasharray:3 4}.plot .curve{stroke:var(--mint);stroke-width:2.5;fill:none}
.comparison{display:grid;grid-template-columns:1fr 1fr;gap:15px;padding:15px 0;border-top:1px solid var(--line)}.comparison label{font-size:11px;color:var(--muted)}.comparison strong{display:block;color:var(--mint);font:22px ui-monospace,monospace}.small{font-size:12px;color:var(--muted)}
.warnings{padding-left:20px;color:var(--muted);font-size:13px}.warnings li{padding:5px 0}.chips{display:flex;gap:8px;flex-wrap:wrap}.chip{padding:5px 8px;background:#1b2e32;color:var(--mint);font:11px ui-monospace,monospace;border-radius:4px}details{margin:20px 0;border:1px solid var(--line);border-radius:8px;padding:16px}summary{cursor:pointer;color:var(--muted)}pre{white-space:pre-wrap;overflow-wrap:anywhere;color:var(--muted);font:11px/1.6 ui-monospace,monospace;max-height:420px;overflow:auto}footer{color:var(--muted);font-size:12px;border-top:1px solid var(--line);padding-top:22px;margin-top:28px}.empty{color:var(--muted);padding:60px 15px;text-align:center}.caption{font:11px ui-monospace,monospace;color:var(--muted)}
@media(max-width:800px){main{padding:22px 18px}.hero,.grid{grid-template-columns:1fr;gap:20px}.metrics{grid-template-columns:repeat(2,1fr)}header{align-items:flex-start}.hero{margin-top:28px}h1{font-size:36px}}
@media(max-width:420px){.metrics{grid-template-columns:1fr}.wordmark{font-size:20px}.tag{font-size:9px}.metric{padding:16px}}
</style></head><body><main>
<header><div class="brand"><svg viewBox="0 0 44 44" aria-hidden="true"><path d="M4 38 22 6 40 38H4Z" fill="none" stroke="#79efd0" stroke-width="2.5"/><path d="M12 30h20M17 22h10" stroke="#79efd0" stroke-width="2.5"/></svg><div><div class="wordmark">AXIOM</div><div class="subtitle">Geometry Dash Difficulty Lab</div></div></div><span class="tag">Research alpha · v0.1</span></header>
<section class="hero"><div><span class="eyebrow">EVIDENCE BEFORE RATINGS</span><h1>Difficulty that can<br>be explained.</h1><p>Explore timing constraints and observed first-completion times. Every result carries its assumptions, challenge identity and limits.</p></div><div class="identity" id="identity"></div></section>
<div class="notice" id="notice" role="status"></div>
<section class="metrics" aria-label="Analysis summary"><div class="metric"><label>Axiom Rating</label><div class="value" id="ar">—</div><div class="detail" id="ar-detail"></div></div><div class="metric"><label>Scenario pass probability</label><div class="value" id="probability">—</div><div class="detail" id="prob-detail"></div></div><div class="metric"><label>Observed median · T50</label><div class="value" id="median">—</div><div class="detail" id="median-detail"></div></div><div class="metric"><label>Physical feasibility</label><div class="value" style="font-size:22px">Not assessed</div><div class="detail">No live native game oracle in this report</div></div></section>
<section class="grid"><div class="panel"><h2>Timing windows &amp; route choices</h2><p class="intro">Offsets from nominal action time, in milliseconds. Each row is one press or release; separate bands preserve disjoint windows.</p><div class="route-tabs" id="routes" aria-label="Choose a route"></div><div id="timing-plot"></div><div class="comparison"><div><label>Independent marginal baseline</label><strong id="baseline">—</strong></div><div><label>Correlated + joint constraints</label><strong id="joint">—</strong></div></div><div class="small" id="route-detail"></div></div>
<div class="panel"><h2>First-completion curve</h2><p class="intro">Kaplan–Meier estimate from participant histories. Censored players contribute follow-up, not fabricated completions.</p><div id="survival-plot"></div><div class="chips" id="cohort-chips"></div><p class="small" id="survival-detail"></p><h3>Rating scale · proposed v0</h3><p class="small">AR = 1000 + 100 × log₂(T50 / reference T50)<br>+100 AR means twice the median active practice time for the same population and protocol.</p></div></section>
<section class="panel"><h2>Evidence &amp; interpretation</h2><p class="intro">Model assumptions, sampling uncertainty and empirical validation are different layers.</p><ul class="warnings" id="warnings"></ul><div class="chips" id="noise"></div></section>
<details><summary>Inspect reproducible analysis JSON</summary><pre id="raw"></pre></details>
<footer>AXIOM · open research by TheLitis · axiom-gd 0.1.0<br>This report runs entirely offline. Synthetic examples demonstrate the pipeline; real level rankings require measured game evidence and calibrated player data.</footer>
</main><script>
'use strict';
const data=__AXIOM_PAYLOAD__;
const timing=data.timing, cohort=data.cohort;
const $=id=>document.getElementById(id);
const txt=(id,value)=>$(id).textContent=value;
const pct=value=>value===null||value===undefined?'—':(100*value).toFixed(2)+'%';
const svgNS='http://www.w3.org/2000/svg';
function node(tag,attrs={},content){const n=document.createElementNS(svgNS,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(content!==undefined)n.textContent=content;return n;}
function label(svg,x,y,text,attrs={}){svg.append(node('text',{x,y,...attrs},text));}
function chip(target,text){const n=document.createElement('span');n.className='chip';n.textContent=text;$(target).append(n);}
const identity=timing?.challenge||cohort?.challenge;
if(identity){for(const key of ['id','game_version','physics_version','input_policy','environment_id']){const line=document.createElement('div');const strong=document.createElement('strong');strong.textContent=key.replaceAll('_',' ')+': ';line.append(strong,document.createTextNode(identity[key]));$('identity').append(line);}const hash=document.createElement('div');hash.textContent='SHA256 '+identity.level_sha256.slice(0,20)+'…';$('identity').append(hash);}
const synthetic=timing?.provenance?.origin==='synthetic'||cohort?.synthetic;
txt('notice',synthetic?'SYNTHETIC LAB DATA · This report includes synthetic data; synthetic results are not measured level ratings.':'PROVISIONAL RESEARCH · Supplied evidence and model assumptions require independent verification.');
const ar=cohort?.rating?.ar;
txt('ar',ar===null||ar===undefined?'Unrated':ar.toFixed(1));
txt('ar-detail',ar===null||ar===undefined?'Compatible empirical T50 and reference required':cohort.synthetic?'SYNTHETIC example · calibration uncertainty unknown':'Provisional empirical · calibration uncertainty unknown');
txt('median',cohort?.t50_hours===null||!cohort?'Unreached':cohort.t50_hours.toFixed(1)+' h');
txt('median-detail',cohort?'Median under declared population & protocol':'Participant cohort not supplied');
function showRoute(index){const route=timing.routes[index];Array.from($('routes').children).forEach((n,i)=>n.setAttribute('aria-pressed',String(i===index)));txt('probability',pct(route.modeled_pass_probability));txt('prob-detail','MC 95%: '+route.monte_carlo_ci95.map(pct).join(' – '));txt('baseline',pct(route.independent_marginal_probability));txt('joint',pct(route.modeled_pass_probability));txt('route-detail',`${route.event_count} events · ${route.joint_constraint_count} joint constraints · ${route.successes.toLocaleString()} / ${route.trials.toLocaleString()} scenario trials. Confidence interval measures simulation error only.`);
const events=route.events.slice(0,32), height=events.length*29+55;const svg=node('svg',{viewBox:`0 0 580 ${height}`,class:'plot',role:'img','aria-label':'Acceptable timing offsets for '+route.label});let extent=2;events.forEach(e=>e.windows_ms.forEach(w=>extent=Math.max(extent,Math.abs(w[0]),Math.abs(w[1]))));extent*=1.12;const x=value=>110+(value+extent)/(2*extent)*445;
[-1,-.5,0,.5,1].forEach(f=>{const a=x(extent*f);svg.append(node('line',{x1:a,y1:15,x2:a,y2:height-30,class:f===0?'axis':'gridline'}));label(svg,a,height-8,(extent*f).toFixed(1),{'text-anchor':'middle'});});events.forEach((e,i)=>{const y=22+i*29;label(svg,4,y+5,(e.down?'↓ press':'↑ release')+' · P'+e.player);e.windows_ms.forEach(w=>svg.append(node('rect',{x:x(w[0]),y:y-6,width:Math.max(1,x(w[1])-x(w[0])),height:12,rx:2,fill:'#79efd0',opacity:.8})));});$('timing-plot').replaceChildren(svg);if(route.events.length>32){const p=document.createElement('p');p.className='caption';p.textContent='First 32 events shown; all events are included in the analysis JSON.';$('timing-plot').append(p);}}
if(timing){timing.routes.forEach((route,i)=>{const b=document.createElement('button');b.textContent=route.label;b.type='button';b.addEventListener('click',()=>showRoute(i));$('routes').append(b);});showRoute(0);for(const [key,value] of Object.entries(timing.noise))chip('noise',key+' = '+value);chip('noise','seed = '+timing.seed);}else{txt('prob-detail','Timing scenario not supplied');const p=document.createElement('p');p.className='empty';p.textContent='No timing scenario supplied';$('timing-plot').append(p);}
if(cohort){const width=430,height=275,l=45,r=15,t=15,b=40;const maximum=cohort.cohort_summary.last_observed_time_hours;const x=h=>l+h/maximum*(width-l-r),y=p=>height-b-p*(height-b-t);const svg=node('svg',{viewBox:`0 0 ${width} ${height}`,class:'plot',role:'img','aria-label':'Estimated probability of first completion over active practice hours'});[0,.25,.5,.75,1].forEach(p=>{svg.append(node('line',{x1:l,y1:y(p),x2:width-r,y2:y(p),class:'gridline'}));label(svg,l-8,y(p)+4,(100*p).toFixed(0)+'%',{'text-anchor':'end'});});[0,.25,.5,.75,1].forEach(f=>label(svg,x(maximum*f),height-17,(maximum*f).toFixed(0)+' h',{'text-anchor':'middle'}));let d=`M ${x(0)} ${y(0)}`,prev=0;for(const point of cohort.curve){d+=` L ${x(point.time_hours)} ${y(prev)} L ${x(point.time_hours)} ${y(point.completion_probability)}`;prev=point.completion_probability;if(point.censored)svg.append(node('path',{d:`M ${x(point.time_hours)-3} ${y(prev)-4} L ${x(point.time_hours)+3} ${y(prev)+4} M ${x(point.time_hours)-3} ${y(prev)+4} L ${x(point.time_hours)+3} ${y(prev)-4}`,stroke:'#ffd48a','stroke-width':1.5}));}svg.append(node('path',{d,class:'curve'}));$('survival-plot').append(svg);chip('cohort-chips',cohort.cohort_summary.participants+' participants');chip('cohort-chips',cohort.cohort_summary.completed+' completed');chip('cohort-chips',cohort.cohort_summary.censored+' censored');txt('survival-detail','× marks censoring. T50 bootstrap: '+(cohort.t50_bootstrap_ci95?cohort.t50_bootstrap_ci95.map(v=>v.toFixed(1)+' h').join(' – '):'finite interval unavailable')+'. Interval excludes calibration error and selection bias.');}else{const p=document.createElement('p');p.className='empty';p.textContent='No participant cohort supplied';$('survival-plot').append(p);}
for(const warning of [...new Set([...(timing?.warnings||[]),...(cohort?.warnings||[])])]){const li=document.createElement('li');li.textContent=warning;$('warnings').append(li);}
txt('raw',JSON.stringify(data,null,2));
</script></body></html>"""
