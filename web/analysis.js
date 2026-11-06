"use strict";
/* Deep analysis page in the Universe look: what the company is building (thesis) and the claims we attacked (court).
   /analysis.html?company=NAME. Reuses a finished run for that company when one exists, otherwise starts one. */
var $ = function(id){ return document.getElementById(id); };
function esc(s){ return String(s == null ? "" : s).replace(/[&<>"]/g, function(c){ return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
function nf(x){ return x == null ? "n/a" : Number(x).toLocaleString(); }
var STEPS = [["parse", "Parse"], ["resolve", "Resolve"], ["context", "Context"], ["people", "People"], ["jobs", "Jobs"], ["exits", "Exits"], ["analyse", "Analyse"], ["thesis", "Thesis"], ["court", "Court"], ["brief", "Brief"]];
var name = (new URLSearchParams(location.search).get("company") || "").trim(), runId = null, es = null;

function build(){ $("pnodes").innerHTML = STEPS.map(function(s){ return '<div class="pn" id="pn-' + s[0] + '"><i></i>' + s[1] + '</div>'; }).join(""); }
function pn(step, cls){ var e = $("pn-" + step); if(e) e.className = "pn " + cls; }
function say(m, err){ $("pmsg").textContent = m; $("pmsg").className = "pmsg" + (err ? " err" : ""); }

function tilt(el){
  el.addEventListener("pointermove", function(e){
    var r = el.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5;
    el.style.setProperty("--ry", (x * 8).toFixed(2) + "deg"); el.style.setProperty("--rx", (-y * 8).toFixed(2) + "deg");
    el.style.setProperty("--gx", ((x + .5) * 100) + "%"); el.style.setProperty("--gy", ((y + .5) * 100) + "%");
  });
  el.addEventListener("pointerleave", function(){ el.style.setProperty("--rx", "0deg"); el.style.setProperty("--ry", "0deg"); });
}
function list(a){ return (a || []).map(function(x){ return '<li>' + esc(typeof x === "string" ? x : (x.text || x.action || x.title || JSON.stringify(x))) + '</li>'; }).join(""); }
var MARK = {pass: "✓", warn: "!", fail: "✗"};

function render(res){
  $("run").classList.add("done");
  var c = res.company, b = res.brief || {}, sm = (res.court || {}).summary || {}, th = (res.thesis || {}).theses || [], claims = (res.court || {}).claims || [];
  document.title = c.name + " · deep analysis"; $("ctag").textContent = "window " + res.window.start + " to " + res.window.end;
  var killed = claims.filter(function(x){ return x.verdict === "killed"; }).length, weak = claims.filter(function(x){ return x.verdict === "weakened"; }).length, ok = claims.filter(function(x){ return x.verdict === "survived"; }).length;
  var h = '<section class="chero"><div><div class="k">Deep analysis</div><h1>' + esc(c.name) + '</h1><p>' + esc(b.tldr || b.headline || "") + '</p>' +
    '<div class="links"><a href="/company.html?id=' + c.id + '">Company profile</a><a href="/">Market Universe</a></div></div>' +
    '<div class="stat3"><div><b style="color:var(--bad)">' + killed + '</b><span>claims killed</span></div><div><b style="color:var(--warn)">' + weak + '</b><span>weakened</span></div><div><b style="color:var(--ok)">' + ok + '</b><span>survived</span></div></div></section>';

  h += '<h2 class="ch2">What they are building<small>Read from hiring. Each idea is judged by six independent checks and says what would change our mind.</small></h2><div class="tgrid">' +
    (th.length ? th.slice(0, 6).map(function(t){
      return '<div class="tc ' + t.confidence + '"><span class="vt ' + t.confidence + '">' + esc(t.confidence) + ' · ' + t.passes + ' of ' + t.judged + ' checks</span><h3>' + esc(t.statement) + '</h3>' +
        (t.signals || []).map(function(s){ return '<div class="tst2 ' + s.result + '"><em>' + (MARK[s.result] || "") + '</em><div><b>' + esc(s.name) + '</b><span>' + esc(s.detail) + '</span></div></div>'; }).join("") +
        (t.falsifier ? '<div class="fal"><b>What would change our mind.</b> ' + esc(t.falsifier) + '</div>' : "") + '</div>'; }).join("") : '<p class="sub">Not enough people-level data to state a thesis.</p>') + '</div>';

  h += '<h2 class="ch2">The claim court<small>The easy numbers a tool would show, attacked with tests. The audited number is the one to trust.</small></h2><div class="tgrid">' +
    claims.map(function(x){
      return '<div class="tc ' + x.verdict + '"><span class="vt ' + x.verdict + '">' + x.verdict + '</span> <span class="by">' + esc(x.by) + '</span><h3>' + esc(x.title) + '</h3>' +
        (x.naive && x.audited ? '<div class="swapx"><s>' + nf(x.naive.value) + '</s><i>→</i><b>' + nf(x.audited.value) + '</b><small>' + esc(x.naive.label) + ' → ' + esc(x.audited.label) + (x.audited.note ? ' · ' + esc(x.audited.note) : "") + '</small></div>' : '<p class="sub">' + esc(x.claim) + '</p>') +
        (x.why ? '<p style="margin:6px 0 10px;font-size:14px">' + esc(x.why) + '</p>' : "") +
        (x.tests || []).map(function(s){ return '<div class="tst2 ' + s.result + '"><em>' + (MARK[s.result] || "") + '</em><div><b>' + esc(s.name) + '</b><span>' + esc(s.detail) + '</span></div></div>'; }).join("") + '</div>'; }).join("") + '</div>';

  if((b.actions && b.actions.length) || (b.caveats && b.caveats.length))
    h += '<h2 class="ch2">What to do, and what to doubt</h2><div class="lists"><section class="sec"><h2>Actions</h2><ul>' + list(b.actions) + '</ul></section><section class="sec"><h2>Caveats</h2><ul>' + list(b.caveats) + '</ul></section></div>';
  h += '<div class="dl"><a href="/api/export/' + runId + '?format=md">Download brief (.md)</a><a href="/api/export/' + runId + '?format=html" target="_blank">Printable one-pager</a></div>' +
    '<p class="fine">Source: Crustdata people and job data. ' + res.credits + ' credits, ' + res.seconds + 's. Counts come from public profiles, so recent months can lag; every number above is computed in code, not written by a model.</p>';
  $("out").innerHTML = h; document.querySelectorAll(".tc").forEach(tilt);
}

function watch(id){
  runId = id; if(es) es.close(); es = new EventSource("/api/stream/" + id);
  es.onmessage = function(m){
    var ev = JSON.parse(m.data), d = ev.data, k = ev.kind;
    if(k === "step_start" || k === "progress"){ pn(d.step, "run"); say(d.message || ""); }
    else if(k === "step_done" || k === "step_skipped"){ pn(d.step, "done"); say(d.message || ""); }
    else if(k === "warning") say(d.message);
    else if(k === "error"){ pn(d.step, "fail"); say((d.message || "") + " " + (d.hint || ""), true); $("resume").style.display = "inline-block"; }
    else if(k === "needs_input"){ pn(d.step, "fail"); say("Needs your input: " + d.message, true); }
  };
  es.addEventListener("end", function(){
    es.close();
    fetch("/api/run/" + id).then(function(r){ return r.json(); }).then(function(run){ if(run.status === "done") render(run.result); else $("resume").style.display = "inline-block"; });
  });
  es.onerror = function(){};
}
$("resume").onclick = function(){ if(!runId) return; $("resume").style.display = "none"; fetch("/api/resume/" + runId, {method: "POST"}).then(function(){ watch(runId); }); };

build();
if(!name){ say("No company in the link. Open this page from the Market Universe.", true); }
else {
  $("runtitle").textContent = "Reading " + name;
  fetch("/api/companies").then(function(r){ return r.json(); }).then(function(list){
    var hit = list.filter(function(c){ return (c.name || "").toLowerCase().indexOf(name.toLowerCase()) === 0 || name.toLowerCase().indexOf((c.name || "").toLowerCase()) === 0; })[0];
    if(hit){ runId = hit.run_id; return fetch("/api/run/" + hit.run_id).then(function(r){ return r.json(); }).then(function(run){ if(run.status === "done") render(run.result); else watch(hit.run_id); }); }
    return fetch("/api/run", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({request: "Which teams at " + name + " are growing fastest?", company: name})})
      .then(function(r){ return r.json(); }).then(function(j){ if(j.error){ say(j.error, true); return; } watch(j.run_id); });
  });
}
