"use strict";
/* Market Universe: Past / Present / Future as a place you move through. Positions encode real fields:
   Present: distance = size ratio vs you, colour = 12-month growth, size = headcount.
   Future:  x = share of team already on your strategy, height = 12-month growth, size = headcount.
   Past:    dashed outline = peak headcount, red = headcount now. */
var $ = function(id){ return document.getElementById(id); };
function esc(s){ return String(s == null ? "" : s).replace(/[&<>"]/g, function(c){ return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
function sgn(x){ return x == null ? "n/a" : (x > 0 ? "+" : "") + Math.round(x) + "%"; }
function nf(x){ return x == null ? "n/a" : Number(x).toLocaleString(); }
function usd(x){ return x ? "$" + Math.round(x / 1e6) + "M" : "n/a"; }
function ym(d){ return (d || "").slice(0, 7); }
function clamp(v, a, b){ return Math.max(a, Math.min(b, v)); }
var STEPS = [["resolve", "Find you"], ["self", "Read your hiring"], ["rivals", "Rivals"], ["future", "Future"], ["past", "Past"]];
var lastRun = null, es = null, R = null, world = 1, WORLDS = ["past", "present", "future"], sel = null;

/* ---------------- landing and run ---------------- */
function buildProg(){
  $("pnodes").innerHTML = STEPS.map(function(s){ return '<div class="pn" id="pn-' + s[0] + '"><i></i>' + s[1] + '</div>'; }).join("");
  $("pmsg").textContent = ""; $("pmsg").className = "pmsg"; $("resume").style.display = "none";
}
function pn(step, cls){ var e = $("pn-" + step); if(e) e.className = "pn " + cls; }
function say(msg, err){ $("pmsg").textContent = msg; $("pmsg").className = "pmsg" + (err ? " err" : ""); }
function start(name){
  name = (name || $("co").value).trim(); if(!name) return;
  $("co").value = name; $("go").disabled = true; $("prog").classList.add("on"); buildProg();
  fetch("/api/market", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({company: name})})
    .then(function(r){ return r.json(); }).then(function(j){
      if(j.error){ say(j.error, true); $("go").disabled = false; return; }
      lastRun = j.run_id; watch(j.run_id);
    });
}
function watch(id){
  if(es) es.close();
  es = new EventSource("/api/stream/" + id);
  es.onmessage = function(m){
    var ev = JSON.parse(m.data), d = ev.data, k = ev.kind;
    if(k === "step_start" || k === "progress"){ pn(d.step, "run"); say(d.message || ""); }
    else if(k === "step_done" || k === "step_skipped"){ pn(d.step, "done"); say(d.message || ""); }
    else if(k === "warning") say(d.message);
    else if(k === "error"){ pn(d.step, "fail"); say((d.message || "") + " " + (d.hint || ""), true); $("resume").style.display = "inline-block"; }
    else if(k === "needs_input"){ pn(d.step, "fail"); say("Needs your input: " + d.message, true); }
  };
  es.addEventListener("end", function(){
    es.close(); $("go").disabled = false;
    fetch("/api/run/" + id).then(function(r){ return r.json(); }).then(function(run){
      if(run.status === "done") render(run.result); else $("resume").style.display = "inline-block";
    });
  });
  es.onerror = function(){};
}
$("ask").onsubmit = function(e){ e.preventDefault(); start(); };
document.querySelectorAll(".eg a").forEach(function(a){ a.onclick = function(){ $("co").value = a.getAttribute("data-c"); $("co").focus(); }; });
$("resume").onclick = function(){ if(!lastRun) return; buildProg(); fetch("/api/resume/" + lastRun, {method: "POST"}).then(function(){ watch(lastRun); }); };
$("last").onclick = function(){
  fetch("/api/last?kind=market").then(function(r){ return r.json(); }).then(function(j){
    if(j.error){ $("prog").classList.add("on"); buildProg(); say("No finished market run yet.", true); return; }
    lastRun = j.id; render(j.result);
  });
};
$("again").onclick = function(){
  closeHud(); $("uni").classList.remove("on", "go"); $("top").hidden = true; $("hint").hidden = true; $("land").classList.remove("gone");
  $("prog").classList.remove("on"); $("co").focus();
};

/* ---------------- colours and geometry ---------------- */
function gcolor(g){
  if(g == null) return "#9aa3b8";
  var t = clamp((g + 25) / 65, 0, 1), h = (350 + t * 165) % 360;
  return "hsl(" + h.toFixed(0) + ",95%,60%)";
}
function verdictOf(g){ return g == null ? "unknown" : g >= 30 ? "surging" : g >= 8 ? "growing" : g > -8 ? "steady" : g > -25 ? "shrinking" : "contracting"; }
function ringFrac(k){ return clamp(0.28 + 0.72 * Math.log(Math.max(k, 1)) / Math.log(4), 0.28, 1); }

/* ---------------- build the three worlds ---------------- */
function cap(kind, k, h, p){ return '<div class="cap"><div class="k">' + k + '</div><h2>' + h + '</h2><p>' + p + '</p></div>'; }

function renderPresent(res){
  var me = res.company, mine = me.headcount || 1, rivals = res.present.rivals.slice().sort(function(a, b){ return (b.g12 == null ? -99 : b.g12) - (a.g12 == null ? -99 : a.g12); });
  var meG = (res.present.me && res.present.me.g12 != null) ? res.present.me.g12 : (me.stats ? me.stats.g12 : null);
  var D = Math.min(innerWidth * 0.7, innerHeight * 1.2), maxhc = Math.max.apply(null, [mine].concat(rivals.map(function(r){ return r.headcount || 0; })));
  var faster = meG == null ? null : rivals.filter(function(r){ return r.g12 != null && r.g12 > meG; }).length;
  var h = cap("present", "Present · " + rivals.length + " rivals", "Who you<br>fight now",
    "Distance from you is how different they are in <b>size</b>. Colour is <b>12-month growth</b>, red to green. Clockwise from the top: fastest growing first." +
    (faster != null ? " <b>" + faster + " of " + rivals.length + "</b> are growing faster than you." : ""));
  var rings = [[ringFrac(4), "4x size gap"], [ringFrac(2), "2x"], [0.28, "similar size"]].map(function(r, i){
    return '<div class="ring" style="width:' + (D * r[0]) + 'px;height:' + (D * r[0]) + 'px"><em>' + r[1] + '</em></div>'; }).join("");
  var orbs = rivals.map(function(r, i){
    var ratio = (r.headcount || mine) / mine, k = ratio >= 1 ? ratio : 1 / ratio, rad = ringFrac(k) * D / 2 * 0.97, a = -Math.PI / 2 + 2 * Math.PI * i / rivals.length;
    var s = 30 + 46 * Math.sqrt((r.headcount || 1) / maxhc);
    return '<div class="orb" data-k="rival" data-i="' + i + '" style="--i:' + (i + 1) + ';--s:' + s.toFixed(0) + 'px;--c:' + gcolor(r.g12) + ';--x:' + (Math.cos(a) * rad).toFixed(0) + 'px;--y:' + (Math.sin(a) * rad).toFixed(0) + 'px">' +
      '<div class="ball"></div><div class="nm">' + esc(r.name) + '<small>' + sgn(r.g12) + '</small></div></div>';
  }).join("");
  var meOrb = '<div class="orb me" data-k="me" style="--i:0;--s:72px;--c:var(--accent);--x:0px;--y:0px"><div class="ball"></div><div class="nm">' + esc(me.name) + '<small style="color:#fff">you · ' + sgn(meG) + '</small></div></div>';
  $("w-present").innerHTML = h + '<div class="stage"><div class="disk" style="--D:' + D + 'px"><div class="sweep"></div>' + rings + '<div class="ring r0" style="width:' + (D * 0.2) + 'px;height:' + (D * 0.2) + 'px"></div>' + orbs + meOrb + '</div></div>';
  R._rivals = rivals; R._meG = meG;
}

function renderFuture(res){
  var list = res.future.companies, themes = res.self.themes || [];
  var h = cap("future", "Future · " + list.length + " coming", "Who is<br>coming",
    "None of these is your rival yet, but each already builds what <b>you</b> are building" + (themes.length ? " (" + esc(themes.map(function(t){ return t.theme; }).join(", ")) + ")" : "") +
    ". Left to right: how much of their team is on it. Higher: faster growing.");
  if(!list.length){
    $("w-future").innerHTML = h + '<div class="wall"><div class="plane"></div><div class="axl" style="left:0;right:0;top:46%;text-align:center;font-size:13px">' +
      (themes.length ? "No company outside your rivals matched strongly enough. That is a real result." : "Not enough people-level data to say what you are building.") + '</div></div>';
    return;
  }
  var maxS = Math.max(0.2, Math.max.apply(null, list.map(function(c){ return c.share || 0; }))) * 1.15, maxhc = Math.max.apply(null, list.map(function(c){ return c.headcount || 1; }));
  var bubbles = list.map(function(c, i){
    var fx = 8 + 84 * (c.share || 0) / maxS, fy = c.g12 == null ? 50 : 90 - 80 * clamp((c.g12 + 20) / 80, 0, 1), s = 36 + 36 * Math.sqrt((c.headcount || 1) / maxhc);
    return '<div class="fb" data-k="future" data-i="' + i + '" style="--i:' + i + ';--s:' + s.toFixed(0) + 'px;--fx:' + fx.toFixed(1) + '%;--fy:' + fy.toFixed(1) + '%;--z:' + ((i % 3) * 34) + 'px"><div class="ball"></div>' +
      '<div class="nm">' + esc(c.name) + '<small>' + (c.share != null ? Math.round(100 * c.share) + "% on it" : "") + '</small></div></div>';
  }).join("");
  $("w-future").innerHTML = h + '<div class="wall"><div class="plane"></div><div class="axl x">share of their team already on your strategy &rarr;</div><div class="axl y">12-month headcount growth &rarr;</div>' + bubbles + '</div>';
}

function renderPast(res){
  var list = res.past.companies, cr = res.past.criteria;
  var h = cap("past", "Past · " + list.length + " fell", "Who<br>fell",
    "Dashed outline is their <b>peak headcount</b>, red is <b>now</b>. Each lost " + Math.round(100 * cr.min_drop) + "% or more from a peak of " + cr.min_peak + "+ people. Click one for the curve and what the press says.");
  if(!list.length){ $("w-past").innerHTML = h + '<div class="ruins"><div class="axl" style="position:static;font-size:13px">None found. Fallen giants are rare in a narrow space.</div></div>'; return; }
  var maxp = Math.max.apply(null, list.map(function(c){ return c.stats.peak; })), H = Math.min(innerHeight * 0.5, 430);
  var pil = list.map(function(c, i){
    var ph = 90 + (H - 90) * c.stats.peak / maxp, nh = 100 * c.stats.now / c.stats.peak;
    return '<div class="pil" data-k="past" data-i="' + i + '" style="--i:' + i + ';--ph:' + ph.toFixed(0) + 'px;--nh:' + nh.toFixed(1) + '%"><div class="ghost"></div><div class="now"></div>' +
      '<div class="pk">' + nf(c.stats.peak) + '</div><div class="nm">' + esc(c.name) + '<small>−' + Math.round(100 * c.stats.drop) + '%</small></div></div>';
  }).join("");
  $("w-past").innerHTML = h + '<div class="floor"></div><div class="ruins">' + pil + '</div>';
}

function render(res){
  R = res; sel = null; closeHud();
  renderPast(res); renderPresent(res); renderFuture(res);
  var me = res.company, g = R._meG;
  $("who").innerHTML = '<b>' + esc(me.name) + '</b><br>' + nf(me.headcount) + ' people · ' + sgn(g) + ' in 12 months · ' + res.credits + ' credits';
  $("land").classList.add("gone"); $("top").hidden = false; $("hint").hidden = false;
  $("uni").classList.remove("go"); $("uni").classList.add("on"); go(1, true);
  void $("uni").offsetWidth; setTimeout(function(){ $("uni").classList.add("go"); }, 60);
}

/* ---------------- moving through time ---------------- */
function go(i, instant){
  world = clamp(i, 0, 2);
  var t = $("track"); if(instant){ t.style.transition = "none"; }
  t.style.transform = "translateX(" + (-world * 100) + "vw)";
  if(instant){ void t.offsetWidth; t.style.transition = ""; }
  document.querySelectorAll("#nav button").forEach(function(b){ b.classList.toggle("on", b.getAttribute("data-w") === WORLDS[world]); });
  closeHud();
}
document.querySelectorAll("#nav button").forEach(function(b){ b.onclick = function(){ go(WORLDS.indexOf(b.getAttribute("data-w"))); }; });
document.addEventListener("keydown", function(e){
  if(!$("uni").classList.contains("on")) return;
  if(e.key === "ArrowRight") go(world + 1); else if(e.key === "ArrowLeft") go(world - 1); else if(e.key === "Escape"){ closeHud(); closeDossier(); }
});
document.addEventListener("pointermove", function(e){
  var x = e.clientX / innerWidth - .5, y = e.clientY / innerHeight - .5, r = document.documentElement.style;
  r.setProperty("--py", (x * 6).toFixed(2) + "deg"); r.setProperty("--px", (-y * 4).toFixed(2) + "deg");
  $("sky").style.setProperty("--mx", (e.clientX / innerWidth * 100) + "%"); $("sky").style.setProperty("--my", (e.clientY / innerHeight * 100) + "%");
});
var onResize; window.addEventListener("resize", function(){ clearTimeout(onResize); onResize = setTimeout(function(){ if(R){ renderPast(R); renderPresent(R); renderFuture(R); $("uni").classList.add("go"); } }, 250); });

/* ---------------- selection HUD ---------------- */
function closeHud(){ $("hud").classList.remove("on"); document.querySelectorAll(".sel").forEach(function(e){ e.classList.remove("sel"); }); }
function row(pairs){ return '<div class="row">' + pairs.map(function(p){ return '<div><span>' + p[0] + '</span><b>' + p[1] + '</b></div>'; }).join("") + '</div>'; }
function hud(html, el){
  closeHud(); if(el) el.classList.add("sel");
  $("hud").innerHTML = '<button class="close" aria-label="Close">&times;</button>' + html; $("hud").classList.add("on");
  $("hud").querySelector(".close").onclick = closeHud;
  var pf = $("hud").querySelector(".pf"); if(pf){ pf.onclick = function(){ openDossier(pf.getAttribute("data-id"), pf.getAttribute("data-name")); }; loadRail(pf.getAttribute("data-id"), pf.getAttribute("data-name"), false); }
}
var TAGC = {surging: "var(--ok)", growing: "var(--ok)", steady: "#9aa3b8", unknown: "#9aa3b8", shrinking: "var(--warn)", contracting: "var(--bad)"};
function pfBtn(it){ return it.id ? '<button class="pf" data-id="' + it.id + '" data-name="' + esc(it.name) + '">Pin full profile &rarr;</button>' : ""; }

document.addEventListener("click", function(e){
  var el = e.target.closest && e.target.closest("[data-k]"); if(!el || !R) return;
  var k = el.getAttribute("data-k"), i = +el.getAttribute("data-i");
  if(k === "me"){
    var m = R.present.me || {}, c = R.company;
    hud('<h3>' + esc(c.name) + '</h3><span class="tag" style="background:var(--accent)">you</span><div class="big">' + sgn(R._meG) + '</div><div class="sub">12-month headcount change</div>' +
      row([["People", nf(c.headcount)], ["Open roles", nf(m.open_roles)], ["Rating", m.rating ? m.rating + "/5" : "n/a"]]) +
      '<p class="why"><b>What you are building now</b> (read from your hiring): ' + (R.self.themes.length ? esc(R.self.themes.map(function(t){ return t.theme + " (" + t.confidence + ")"; }).join(", ")) : "not enough data to say") + '.</p>' + pfBtn(m.id ? m : {id: c.id, name: c.name}), el);
  } else if(k === "rival"){
    var r = R._rivals[i], v = r.verdict || verdictOf(r.g12), d = (r.g12 != null && R._meG != null) ? Math.round(r.g12 - R._meG) : null;
    hud('<h3>' + esc(r.name) + '</h3><span class="tag" style="background:' + TAGC[v] + '">' + v + '</span><div class="big" style="color:' + gcolor(r.g12) + '">' + sgn(r.g12) + '</div>' +
      '<div class="sub">12 months' + (d != null ? " · " + (d >= 0 ? "+" : "") + d + " pts vs you" : "") + '</div>' +
      row([["People", nf(r.headcount)], ["Open roles", nf(r.open_roles)], ["Rating", r.rating ? r.rating + "/5" : "n/a"], ["6 months", sgn(r.g6)], ["Raised", usd(r.raised_usd)], ["Followers", sgn(r.followers_yoy)]]) + pfBtn(r), el);
  } else if(k === "future"){
    var c2 = R.future.companies[i];
    hud('<h3>' + esc(c2.name) + '</h3><span class="tag" style="background:var(--accent2)">building: ' + esc(c2.theme) + '</span><div class="big" style="color:var(--accent2)">' + (c2.share != null ? Math.round(100 * c2.share) + "%" : nf(c2.staff)) + '</div>' +
      '<div class="sub">of their team has "' + esc(c2.keyword) + '" in the title (' + nf(c2.staff) + ' of ' + nf(c2.headcount) + ')</div>' +
      row([["Open roles for it", nf(c2.posts)], ["Growth 12m", sgn(c2.g12)], ["Funding", c2.funding ? esc(String(c2.funding).replace(/_/g, " ")) : "n/a"]]) +
      '<p class="why"><b>Not a rival yet because:</b> ' + esc(c2.why_not_rival) + '.</p>' + pfBtn(c2), el);
  } else if(k === "past"){
    var p = R.past.companies[i], s = p.stats, st = s.steepest;
    var cov = (p.coverage || []).map(function(x){ return '<a class="src" href="' + esc(x.url) + '" target="_blank" rel="noopener">' + esc(x.title) + '<small>' + esc(x.snippet) + '</small></a>'; }).join("");
    hud('<h3>' + esc(p.name) + '</h3><span class="tag" style="background:var(--bad)">' + (p.acquired ? "acquired" : p.same_industry ? "your space" : "adjacent") + '</span>' +
      '<div class="big" style="color:var(--bad)">−' + Math.round(100 * s.drop) + '%</div><div class="sub">' + nf(s.peak) + ' (' + ym(s.peak_date) + ') → ' + nf(s.now) + ' now</div>' +
      row([["Peak", nf(s.peak)], ["Now", nf(s.now)], ["Raised", usd(p.raised_usd)]]) +
      (st ? '<p class="why">Steepest half-year: <b>−' + Math.round(100 * st.drop) + '%</b> (' + ym(st.from) + ' to ' + ym(st.to) + ').</p>' : "") +
      (p.acquired ? '<p class="why" style="color:var(--warn)">Marked as acquired: part of the drop may be integration, not failure.</p>' : "") +
      '<span class="sub">Reported coverage (links, not verified by us)</span>' + (cov || '<p class="why">No coverage found by our search.</p>') + pfBtn(p), el);
  }
});

/* ---------------- full profile panel (one API call on demand, cached) ---------------- */
var dosCache = {};
function spark(a, color){
  if(!a || a.length < 3) return "";
  var mx = Math.max.apply(null, a), mn = Math.min.apply(null, a), W = 240, H = 40;
  var pts = a.map(function(v, i){ return (i * W / (a.length - 1)).toFixed(1) + "," + (H - 3 - (H - 8) * (v - mn) / Math.max(1, mx - mn)).toFixed(1); }).join(" ");
  return '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none"><polyline fill="none" stroke="' + (color || "var(--accent2)") + '" stroke-width="2.2" points="' + pts + '"/></svg>';
}
function bar(pct, max){ return '<span class="bar"><i style="width:' + Math.min(100, 100 * pct / max) + '%"></i></span>'; }
function dossierHtml(d){
  var h = '<div class="dos-head"><div><h2>' + esc(d.name) + '</h2><div class="sub">' + [d.hq, d.founded ? "founded " + d.founded : "", d.type].filter(Boolean).map(esc).join(" · ") + '</div></div><button class="dos-x" aria-label="Close">&times;</button></div>';
  if(d.reads && d.reads.length) h += '<div class="reads"><span class="t-l">What this tells you</span><ul>' + d.reads.map(function(x){ return '<li>' + esc(x) + '</li>'; }).join("") + '</ul></div>';
  if(d.description) h += '<p class="fs">' + esc(d.description) + '</p>';
  var kp = [["People", nf(d.headcount)], ["Added in 12 months", d.added_12m != null ? (d.added_12m > 0 ? "+" : "") + nf(d.added_12m) + " (" + sgn(d.g12) + ")" : "n/a"],
    ["Open roles", nf(d.open_roles)], ["Raised", usd(d.raised_usd) + (d.round_count ? " in " + d.round_count + " rounds" : "")],
    ["Revenue (estimate)", d.revenue_band ? usd(d.revenue_band[0]) + " to " + usd(d.revenue_band[1]) : "n/a"], ["Employee rating", d.rating ? d.rating + " / 5 (" + nf(d.reviews) + ")" : "n/a"]];
  h += '<div class="kp">' + kp.map(function(x){ return '<div><span>' + x[0] + '</span><b>' + x[1] + '</b></div>'; }).join("") + '</div>';
  if(d.stats && d.stats.spark && d.stats.spark.length > 3) h += '<div class="dos-spark">' + spark(d.stats.spark) + '<span class="t-l">headcount, weekly (peak ' + nf(d.stats.peak) + ', now ' + nf(d.stats.now) + ')</span></div>';
  if(d.teams.length) h += '<span class="t-l" style="margin-top:10px">Where the people are (share of staff, 6-month change)</span>' + d.teams.map(function(t){
    return '<div class="rowb"><span>' + esc(t.name) + '</span>' + bar(t.share, d.teams[0].share) + '<b>' + t.share + '%</b><em>' + sgn(t.g6) + '</em></div>'; }).join("");
  if(d.cities.length) h += '<span class="t-l" style="margin-top:10px">Main cities</span><div class="chips">' + d.cities.map(function(c){ return '<span class="chp">' + esc(c.name) + ' ' + c.share + '%</span>'; }).join("") + '</div>';
  if(d.ratings.length) h += '<span class="t-l" style="margin-top:10px">What employees say (out of 5)</span>' + d.ratings.map(function(r){
    return '<div class="rowb"><span>' + esc(r.label) + '</span>' + bar(r.value, 5) + '<b>' + r.value + '</b></div>'; }).join("");
  if(d.rounds.length) h += '<span class="t-l" style="margin-top:10px">Recent funding</span>' + d.rounds.map(function(r){
    return '<div class="mini-row"><span>' + esc(r.date) + ' · ' + esc(r.type) + (r.investors ? ' · ' + esc(r.investors) : '') + '</span><b>' + (r.amount_usd ? usd(r.amount_usd) : "n/a") + '</b></div>'; }).join("");
  if(d.role_titles.length) h += '<span class="t-l" style="margin-top:10px">Roles open right now (sample)</span><div class="chips">' + d.role_titles.map(function(t){ return '<span class="chp">' + esc(t) + '</span>'; }).join("") + '</div>';
  if(d.news.length) h += '<span class="t-l" style="margin-top:10px">Recent news (links, not verified by us)</span>' + d.news.map(function(n){
    return '<a class="lnk" href="' + esc(n.url) + '" target="_blank" rel="noopener">' + esc(n.title) + '<small>' + esc(n.publisher || "") + ' · ' + esc((n.date || "").slice(0, 10)) + '</small></a>'; }).join("");
  h += '<div class="dos-foot">' + (d.website ? '<a class="go" href="' + esc(d.website) + '" target="_blank" rel="noopener">Website</a>' : '') +
    '<a class="go" href="/index.html?company=' + encodeURIComponent(d.name) + '&auto=1" target="_blank">Deep analysis &rarr;</a></div>';
  return h;
}
var railFor = null;
function paintRail(html){ $("dosBody").innerHTML = html; }
function loadRail(id, name, pin){
  $("rail").hidden = false; $("railName").textContent = name; if(pin) $("rail").classList.add("pinned");
  railFor = id;
  if(dosCache[id]){ paintRail(railHtml(dosCache[id])); return; }
  paintRail('<div class="dos-head"><h2>' + esc(name) + '</h2></div><p class="sub">Fetching the full profile (about 2 credits)...</p>');
  fetch("/api/dossier?id=" + encodeURIComponent(id)).then(function(r){ return r.json(); }).then(function(d){
    if(railFor !== id) return;
    if(d.error){ paintRail('<div class="dos-head"><h2>' + esc(name) + '</h2></div><div class="warnbox">' + esc(d.error) + '</div>'); return; }
    dosCache[id] = d; paintRail(railHtml(d));
  }).catch(function(){ paintRail('<div class="warnbox">Could not reach the server.</div>'); });
}
function railHtml(d){
  return dossierHtml(d).replace('<button class="dos-x" aria-label="Close">&times;</button>', "").replace('</div></div>', '</div></div><a class="full" href="/company.html?id=' + d.id + '" target="_blank">Open the full page &#8599;</a>');
}
function openDossier(id, name){ loadRail(id, name, true); }
function closeDossier(){ $("rail").classList.remove("pinned"); }
$("railTab").onclick = function(){ $("rail").classList.toggle("pinned"); };
