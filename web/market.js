"use strict";
/* Market view: Present / Future / Past as flip cards. */
var STEPS = ["resolve", "self", "rivals", "future", "past"];
var lastRun = null, es = null, M = null;

function resetSteps(){
  $("steps").innerHTML = STEPS.map(function(s){ return '<li><span class="dot" id="d-' + s + '"></span><span class="sname">' + s + '</span><span class="smsg" id="m-' + s + '"></span></li>'; }).join("");
  $("stepwarn").innerHTML = "";
}
function setStep(step, cls, msg){ var d = $("d-" + step); if(!d) return; d.className = "dot " + cls; if(msg != null) $("m-" + step).textContent = msg; }
function addWarn(msg){ var p = document.createElement("div"); p.className = "warnbox"; p.textContent = msg; $("stepwarn").appendChild(p); }
resetSteps();

function start(){
  var company = $("co").value.trim(); if(!company){ addWarn("Type your company name first."); return; }
  resetSteps(); $("out").hidden = true; $("go").disabled = true; $("stepsdet").open = true;
  fetch("/api/market", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({company: company})})
    .then(function(r){ return r.json(); }).then(function(j){
      if(j.error){ addWarn(j.error); $("go").disabled = false; return; }
      lastRun = j.run_id; watch(j.run_id);
    });
}
function watch(id){
  if(es) es.close();
  $("runmeta").textContent = "run " + id; $("resume").disabled = true;
  es = new EventSource("/api/stream/" + id);
  es.onmessage = function(m){
    var ev = JSON.parse(m.data), d = ev.data, k = ev.kind;
    if(k === "step_start") setStep(d.step, "running", "working...");
    else if(k === "step_done") setStep(d.step, "done", d.message + (d.seconds != null ? "  (" + d.seconds + "s)" : ""));
    else if(k === "step_skipped") setStep(d.step, "skipped", d.message);
    else if(k === "progress") setStep(d.step, "running", d.message);
    else if(k === "warning") addWarn(d.message);
    else if(k === "error"){ setStep(d.step, "failed", d.message); addWarn(d.hint || ""); $("resume").disabled = false; }
    else if(k === "needs_input"){ setStep(d.step, "needs_input", d.message); addWarn("Needs your input: " + d.message); }
  };
  es.addEventListener("end", function(){
    es.close(); $("go").disabled = false;
    fetch("/api/run/" + id).then(function(r){ return r.json(); }).then(function(run){
      if(run.status === "done"){ render(run.result); $("stepsdet").open = false; } else if(run.status === "failed") $("resume").disabled = false;
    });
  });
  es.onerror = function(){};
}
$("go").onclick = start;
$("co").addEventListener("keydown", function(e){ if(e.key === "Enter") start(); });
$("resume").onclick = function(){
  if(!lastRun) return; resetSteps(); $("resume").disabled = true;
  fetch("/api/resume/" + lastRun, {method: "POST"}).then(function(){ watch(lastRun); });
};
$("last").onclick = function(){
  fetch("/api/last?kind=market").then(function(r){ return r.json(); }).then(function(j){
    if(j.error){ addWarn("No finished market run yet."); return; }
    lastRun = j.id; $("runmeta").textContent = "saved run " + j.id; render(j.result);
  });
};

/* ---------------- formatting ---------------- */
function sgn(x){ return x == null ? "n/a" : (x > 0 ? "+" : "") + Math.round(x) + "%"; }
function nf(x){ return x == null ? "n/a" : Number(x).toLocaleString(); }
function usd(x){ return x ? "$" + Math.round(x / 1e6) + "M" : "n/a"; }
function ym(d){ return (d || "").slice(0, 7); }
function spark(a, color){
  if(!a || a.length < 3) return "";
  var mx = Math.max.apply(null, a), mn = Math.min.apply(null, a), W = 240, H = 40;
  var pts = a.map(function(v, i){ return (i * W / (a.length - 1)).toFixed(1) + "," + (H - 3 - (H - 8) * (v - mn) / Math.max(1, mx - mn)).toFixed(1); }).join(" ");
  return '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none"><polyline fill="none" stroke="' + (color || "var(--accent)") + '" stroke-width="2.2" points="' + pts + '"/></svg>';
}
function more(id, name){ return '<button class="pf-btn" data-id="' + id + '" data-name="' + esc(name) + '">Load full profile &rarr;</button>'; }
function deep(name){ return '<a class="go" href="/index.html?company=' + encodeURIComponent(name) + '&auto=1" target="_blank">Deep analysis of ' + esc(name) + ' &rarr;</a>'; }

/* ---------------- the page ---------------- */
function render(res){
  M = res; $("out").hidden = false;
  var me = res.company, themes = res.self.themes || [];
  var chips = themes.length ? themes.map(function(t){
    return '<span class="chp ' + (t.confidence === "strong" ? "ok" : t.confidence === "moderate" ? "warn" : "bad") + '" title="' + esc(t.statement) + '">' + esc(t.theme) + ' · ' + esc(t.confidence) + '</span>'; }).join("") :
    '<span class="chp">not enough profile data to say</span>';
  var g = me.stats && me.stats.g12 != null ? me.stats.g12 : null;
  $("me").innerHTML = '<div class="herogrid"><div><div class="kicker">Your company</div><p class="tldr">' + esc(me.name) + '</p>' +
    '<div class="sub">' + esc(me.industry || "industry unknown") + (me.country ? " · " + esc(me.country) : "") + '</div>' +
    '<div style="margin-top:14px"><span class="t-l">What you are building now, read from your own hiring</span><div class="chips">' + chips + '</div></div>' +
    (res.assumed ? '<div class="warnbox">' + esc(res.assumed) + '</div>' : "") + '</div>' +
    '<div class="orbs"><div class="orb"><b>' + nf(me.headcount) + '</b><span>people</span></div><div class="orb"><b style="color:' + (g != null && g < 0 ? "var(--bad)" : "var(--ok)") + '">' + sgn(g) + '</b><span>12 months</span></div>' +
    '<div class="orb"><b>' + res.present.rivals.length + '</b><span>rivals found</span></div></div></div>' +
    '<div class="sub" style="margin-top:14px">Direction is read from what you hire for, not from stated strategy. Tap any card to flip it.</div>';
  var P = res.present.rivals.length, F = res.future.companies.length, A = res.past.companies.length;
  $("tabs").innerHTML = [["present", "Present", P + " rivals", "who you compete with now"], ["future", "Future", F + " companies", "heading where you are heading"], ["past", "Past", A + " fallen", "big once, much smaller now"]].map(function(t, i){
    return '<button class="tab' + (i === 0 ? " on" : "") + '" data-t="' + t[0] + '"><b>' + t[1] + '</b><span>' + t[2] + ' · ' + t[3] + '</span></button>'; }).join("");
  document.querySelectorAll(".tab").forEach(function(b){ b.onclick = function(){ showTab(b.getAttribute("data-t")); }; });
  renderPresent(res); renderFuture(res); renderPast(res); stagger($("out"));
  $("foot").textContent = "Credits this run: " + res.credits + " · " + res.seconds + "s";
  showTab("present");
}
function stagger(root){ root.querySelectorAll(".grid3").forEach(function(g){ Array.prototype.forEach.call(g.children, function(c, i){ c.style.setProperty("--i", Math.min(i, 10)); }); }); }
function showTab(t){
  ["present", "future", "past"].forEach(function(x){ $("p-" + x).hidden = x !== t; });
  document.querySelectorAll(".tab").forEach(function(b){ b.classList.toggle("on", b.getAttribute("data-t") === t); });
  window.scrollTo({top: $("tabs").offsetTop - 10, behavior: "smooth"});
}

function rivalCard(r, mine, isMe){
  var color = r.verdict === "contracting" || r.verdict === "shrinking" ? "var(--bad)" : r.verdict === "steady" ? "var(--muted)" : "var(--ok)";
  var vs = (!isMe && mine && mine.g12 != null && r.g12 != null) ? (r.g12 - mine.g12 >= 0 ? "+" : "") + Math.round(r.g12 - mine.g12) + " pts vs you" : "";
  var front = '<div class="mc-name">' + esc(r.name) + (isMe ? ' <span class="vb steady" style="background:var(--accent)">you</span>' : '') + '</div>' +
    '<span class="vb ' + r.verdict + '">' + r.verdict + '</span>' +
    '<div class="mc-big" style="margin-top:8px;color:' + color + '">' + sgn(r.g12) + '</div><div class="mc-sub">12 months · ' + nf(r.headcount) + ' people' + (vs ? ' · ' + vs : '') + '</div>' +
    '<div class="mc-spark">' + spark(r.spark, color) + '</div><i class="t-h">tap for the detail</i>';
  var rows = [["6 months", sgn(r.g6)], ["Open roles", nf(r.open_roles)], ["Employee rating", r.rating ? r.rating + " / 5 (" + nf(r.reviews) + " reviews)" : "n/a"],
    ["Last round", r.last_round ? esc(r.last_round) + (r.last_round_date ? " · " + ym(r.last_round_date) : "") : "n/a"], ["Raised", usd(r.raised_usd)], ["Follower growth", sgn(r.followers_yoy)]];
  var back = '<div class="back-scroll"><span class="t-l">How they are performing</span>' + rows.map(function(x){ return '<div class="mini-row"><span>' + x[0] + '</span><b>' + x[1] + '</b></div>'; }).join("") +
    (r.flags && r.flags.length ? '<div class="sub" style="margin-top:6px">Data notes: ' + esc(r.flags.join("; ")) + '</div>' : '') + (r.id ? more(r.id, r.name) : "") + '</div>';
  return fcard(front, back, {h: 276, cls: (isMe ? "you " : "") + "v-" + r.verdict});
}
function renderPresent(res){
  var el = $("p-present"), rivals = res.present.rivals, me = res.present.me;
  if(!rivals.length){ el.innerHTML = '<div class="empty">No rivals found of a similar size. Try the full name or website.</div>'; return; }
  var faster = me && me.g12 != null ? rivals.filter(function(r){ return r.g12 != null && r.g12 > me.g12; }).length : null;
  el.innerHTML = '<div class="page-note"><b>' + rivals.length + ' companies like you</b>, found by what they do and how big they are' +
    (faster != null ? '. <b>' + faster + ' of ' + rivals.length + '</b> are growing faster than you (you: ' + sgn(me.g12) + ' over 12 months)' : '') + '.</div>' +
    '<div class="grid3">' + (me ? rivalCard(me, me, true) : "") + rivals.map(function(r){ return rivalCard(r, me, false); }).join("") + '</div>';
  wireCards(el);
}

function futureCard(c){
  var front = '<div class="mc-name">' + esc(c.name) + '</div><span class="chp warn">building: ' + esc(c.theme) + '</span>' +
    '<div class="mc-big" style="margin-top:10px">' + (c.share != null ? Math.round(100 * c.share) + '%' : nf(c.staff)) + '</div>' +
    '<div class="mc-sub">of the team has "' + esc(c.keyword) + '" in their title (' + nf(c.staff) + ' of ' + nf(c.headcount) + ')</div>' +
    '<div class="mc-sub" style="margin-top:6px">' + nf(c.posts) + ' open roles for it · ' + sgn(c.g12) + ' headcount over 12 months</div><i class="t-h">tap: why they are not a rival yet</i>';
  var back = '<div class="back-scroll"><span class="t-l">The evidence</span>' +
    '<div class="mini-row"><span>Staff with "' + esc(c.keyword) + '" in title</span><b>' + nf(c.staff) + '</b></div>' +
    '<div class="mini-row"><span>Open roles with it in the title</span><b>' + nf(c.posts) + '</b></div>' +
    '<div class="mini-row"><span>Headcount, 12 months</span><b>' + sgn(c.g12) + '</b></div>' +
    '<div class="mini-row"><span>Funding</span><b>' + (c.funding ? esc(c.funding) + " · " + usd(c.raised_usd) : "n/a") + '</b></div>' +
    '<p class="fs" style="margin-top:8px"><b>Not a current rival because:</b> ' + esc(c.why_not_rival) + '.</p>' +
    '<p class="fs"><b>How we found it:</b> its description matches "' + esc(c.theme_query) + '", and its team and open roles agree.</p>' + more(c.id, c.name) + '</div>';
  return fcard(front, back, {h: 276, cls: "v-rising"});
}
function renderFuture(res){
  var el = $("p-future"), list = res.future.companies, themes = res.self.themes || [];
  if(!themes.length){ el.innerHTML = '<div class="empty">We cannot tell what you are building yet: there are not enough people-level profiles to read your direction from. Run a deep analysis of your company first.</div>'; return; }
  if(!list.length){ el.innerHTML = '<div class="empty">No company outside your rivals matched your direction strongly enough. That is a real result, not an error.</div>'; return; }
  var by = {}; list.forEach(function(c){ (by[c.theme] = by[c.theme] || []).push(c); });
  el.innerHTML = '<div class="page-note">Companies <b>outside your current rivals</b> that are building what you are building. Each needs both the team and the open roles to match.</div>' +
    Object.keys(by).map(function(t){ return '<h2 style="margin:14px 0 8px">You are building: ' + esc(t) + '</h2><div class="grid3">' + by[t].map(futureCard).join("") + '</div>'; }).join("");
  wireCards(el);
}

function pastCard(c){
  var s = c.stats, st = s.steepest;
  var front = '<div class="mc-name">' + esc(c.name) + '</div><div class="chips" style="margin:0 0 6px">' +
    (c.same_industry ? '<span class="chp ok">your space</span>' : '<span class="chp">adjacent</span>') + (c.acquired ? '<span class="chp warn">acquired</span>' : '') + '</div>' +
    '<div class="swap"><s>' + nf(s.peak) + '</s><span>&rarr;</span><b>' + nf(s.now) + '</b></div>' +
    '<div class="mc-sub">&minus;' + Math.round(100 * s.drop) + '% since the peak in ' + ym(s.peak_date) + '</div>' +
    '<div class="mc-spark">' + spark(s.spark, "var(--bad)") + '</div><i class="t-h">tap: what the data and the press say</i>';
  var cov = (c.coverage || []).length ? c.coverage.map(function(x){ return '<a class="lnk" href="' + esc(x.url) + '" target="_blank" rel="noopener">' + esc(x.title) + '<small>' + esc(x.snippet) + '</small></a>'; }).join("") :
    '<p class="fs">No coverage found by our search.</p>';
  var back = '<div class="back-scroll"><span class="t-l">The shape of the fall (from the data)</span>' +
    '<div class="mini-row"><span>Peak</span><b>' + nf(s.peak) + ' · ' + ym(s.peak_date) + '</b></div>' +
    '<div class="mini-row"><span>Now</span><b>' + nf(s.now) + ' · ' + ym(s.now_date) + '</b></div>' +
    (st ? '<div class="mini-row"><span>Steepest half-year</span><b>&minus;' + Math.round(100 * st.drop) + '% (' + ym(st.from) + ' to ' + ym(st.to) + ')</b></div>' : '') +
    '<div class="mini-row"><span>Raised</span><b>' + usd(c.raised_usd) + '</b></div>' +
    (c.acquired ? '<p class="fs warnbox">Marked as acquired: part of the drop may be integration, not failure.</p>' : '') +
    '<span class="t-l" style="margin-top:8px">Reported coverage (links; not verified by us)</span>' + cov + more(c.id, c.name) + '</div>';
  return fcard(front, back, {h: 360, cls: "v-fallen"});
}
function renderPast(res){
  var el = $("p-past"), list = res.past.companies, cr = res.past.criteria;
  var note = '<div class="page-note">Companies that <b>fell by ' + Math.round(100 * cr.min_drop) + '% or more from a peak of ' + cr.min_peak + '+ people</b>, among those that raised ' + usd(cr.min_raised_usd) + ' or more. ' +
    'The curve is from the data. The reasons are only what linked reports say; we do not guess a cause.</div>';
  if(!list.length){ el.innerHTML = note + '<div class="empty">None found that match. Fallen giants are rare in a narrow space.</div>'; return; }
  el.innerHTML = note + '<div class="grid3">' + list.map(pastCard).join("") + '</div>';
  wireCards(el);
}


/* ---------------- full profile panel: one API call when a card asks for it ---------------- */
var dosCache = {};
function bar(pct, max){ return '<span class="bar"><i style="width:' + Math.min(100, 100 * pct / max) + '%"></i></span>'; }
function dossierHtml(d){
  var h = '<div class="dos-head"><div><h2>' + esc(d.name) + '</h2><div class="sub">' + [d.hq, d.founded ? "founded " + d.founded : "", d.type].filter(Boolean).map(esc).join(" · ") + '</div></div>' +
    '<button class="dos-x" aria-label="Close">&times;</button></div>';
  if(d.reads && d.reads.length) h += '<div class="reads"><span class="t-l">What this tells you</span><ul>' + d.reads.map(function(x){ return '<li>' + esc(x) + '</li>'; }).join("") + '</ul></div>';
  if(d.description) h += '<p class="fs">' + esc(d.description) + '</p>';
  var kp = [["People", nf(d.headcount)], ["Added in 12 months", d.added_12m != null ? (d.added_12m > 0 ? "+" : "") + nf(d.added_12m) + " (" + sgn(d.g12) + ")" : "n/a"],
    ["Open roles", nf(d.open_roles)], ["Raised", usd(d.raised_usd) + (d.round_count ? " in " + d.round_count + " rounds" : "")],
    ["Revenue (estimate)", d.revenue_band ? usd(d.revenue_band[0]) + " to " + usd(d.revenue_band[1]) : "n/a"], ["Employee rating", d.rating ? d.rating + " / 5 (" + nf(d.reviews) + ")" : "n/a"]];
  h += '<div class="kp">' + kp.map(function(x){ return '<div><span>' + x[0] + '</span><b>' + x[1] + '</b></div>'; }).join("") + '</div>';
  if(d.stats && d.stats.spark && d.stats.spark.length > 3) h += '<div class="dos-spark">' + spark(d.stats.spark) + '<span class="t-l">headcount, weekly (peak ' + nf(d.stats.peak) + ', now ' + nf(d.stats.now) + ')</span></div>';
  if(d.teams.length) h += '<span class="t-l">Where the people are (share of staff, 6-month change)</span>' + d.teams.map(function(t){
    return '<div class="rowb"><span>' + esc(t.name) + '</span>' + bar(t.share, d.teams[0].share) + '<b>' + t.share + '%</b><em>' + sgn(t.g6) + '</em></div>'; }).join("");
  if(d.cities.length) h += '<span class="t-l" style="margin-top:8px">Main cities</span><div class="chips">' + d.cities.map(function(c){ return '<span class="chp">' + esc(c.name) + ' ' + c.share + '%</span>'; }).join("") + '</div>';
  if(d.ratings.length) h += '<span class="t-l" style="margin-top:10px">What employees say (out of 5)</span>' + d.ratings.map(function(r){
    return '<div class="rowb"><span>' + esc(r.label) + '</span>' + bar(r.value, 5) + '<b>' + r.value + '</b></div>'; }).join("");
  if(d.rounds.length) h += '<span class="t-l" style="margin-top:10px">Recent funding</span>' + d.rounds.map(function(r){
    return '<div class="mini-row"><span>' + esc(r.date) + ' · ' + esc(r.type) + (r.investors ? ' · ' + esc(r.investors) : '') + '</span><b>' + (r.amount_usd ? usd(r.amount_usd) : "n/a") + '</b></div>'; }).join("");
  if(d.role_titles.length) h += '<span class="t-l" style="margin-top:10px">Roles open right now (sample)</span><div class="chips">' + d.role_titles.map(function(t){ return '<span class="chp">' + esc(t) + '</span>'; }).join("") + '</div>';
  if(d.news.length) h += '<span class="t-l" style="margin-top:10px">Recent news (links, not verified by us)</span>' + d.news.map(function(n){
    return '<a class="lnk" href="' + esc(n.url) + '" target="_blank" rel="noopener">' + esc(n.title) + '<small>' + esc(n.publisher || "") + ' · ' + esc((n.date || "").slice(0, 10)) + '</small></a>'; }).join("");
  h += '<div class="dos-foot">' + (d.website ? '<a class="go" href="' + esc(d.website) + '" target="_blank" rel="noopener">Website</a> ' : '') + deep(d.name) + '</div>';
  return h;
}
function openDossier(id, name){
  var box = $("dos"), body = $("dosBody"); box.hidden = false; document.body.classList.add("dos-open");
  var paint = function(html){ body.innerHTML = html; var x = body.querySelector(".dos-x"); if(x) x.onclick = closeDossier; };
  if(dosCache[id]){ paint(dossierHtml(dosCache[id])); return; }
  paint('<div class="dos-head"><h2>' + esc(name) + '</h2><button class="dos-x" aria-label="Close">&times;</button></div><p class="sub">Fetching the full profile (about 2 credits)...</p>');
  fetch("/api/dossier?id=" + encodeURIComponent(id)).then(function(r){ return r.json(); }).then(function(d){
    if(d.error){ paint('<div class="dos-head"><h2>' + esc(name) + '</h2><button class="dos-x">&times;</button></div><div class="warnbox">' + esc(d.error) + '</div>'); return; }
    dosCache[id] = d; paint(dossierHtml(d));
  }).catch(function(){ paint('<div class="warnbox">Could not reach the server.</div>'); });
}
function closeDossier(){ $("dos").hidden = true; document.body.classList.remove("dos-open"); }
document.addEventListener("click", function(e){
  var b = e.target.closest && e.target.closest(".pf-btn");
  if(b){ e.stopPropagation(); e.preventDefault(); openDossier(b.getAttribute("data-id"), b.getAttribute("data-name")); return; }
  if(e.target.id === "dos") closeDossier();
}, true);
document.addEventListener("keydown", function(e){ if(e.key === "Escape") closeDossier(); });
