"use strict";
/* Flip cards, the 3D claim deck, presentation mode, pointer parallax and the privacy / theme toggles.
   Loaded after the page's main script; it defines renderHero, renderCourt and renderSenior. */
var reduceMotion = !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);

/* ---------- small helpers ---------- */
function tilt(el, max){
  if(reduceMotion) return;
  max = max || 6;
  el.addEventListener("pointermove", function(e){
    var r = el.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5;
    el.style.setProperty("--ry", (x * max * 2).toFixed(2) + "deg");
    el.style.setProperty("--rx", (-y * max * 2).toFixed(2) + "deg");
  });
  el.addEventListener("pointerleave", function(){ el.style.setProperty("--rx", "0deg"); el.style.setProperty("--ry", "0deg"); });
}
function fcard(front, back, o){
  o = o || {};
  return '<div class="fc ' + (o.cls || "") + '" style="--h:' + (o.h || 140) + 'px" tabindex="0" role="button" aria-pressed="false">' +
    '<div class="fc-inner"><div class="fc-face fc-front">' + front + '</div><div class="fc-face fc-back">' + back + '</div></div></div>';
}
function wireCards(root){
  (root || document).querySelectorAll(".fc:not([data-w])").forEach(function(el){
    el.setAttribute("data-w", "1");
    el.addEventListener("click", function(e){
      if(e.target.closest("button,a")) return;
      el.classList.toggle("flipped"); el.setAttribute("aria-pressed", el.classList.contains("flipped"));
    });
    el.addEventListener("keydown", function(e){ if(e.key === "Enter" || e.key === " "){ e.preventDefault(); el.click(); } });
    tilt(el, 7);
  });
}
function countUp(el, to, dec){
  if(reduceMotion){ el.textContent = dec ? to.toFixed(dec) : Math.round(to).toLocaleString(); return; }
  var t0 = null;
  function step(ts){
    if(t0 === null) t0 = ts;
    var p = Math.min(1, (ts - t0) / 700), v = to * (1 - Math.pow(1 - p, 3));
    el.textContent = dec ? v.toFixed(dec) : Math.round(v).toLocaleString();
    if(p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}
function fv(v){ return typeof v === "number" ? v.toLocaleString() : String(v); }

/* ---------- the findings of the brief, as cards (4 up front, the rest on request) ---------- */
function findingCard(f){
  var ids = f.fact_ids || [], fact = ((R && R.facts) || []).filter(function(x){ return x.id === ids[0]; })[0] || {}, n = (fact.evidence || []).length;
  var front = '<div class="ft">' + esc(f.text) + '</div><div class="fchips">' + ids.map(chip).join("") + '</div><i class="t-h">tap for the source</i>';
  var back = '<span class="t-l">Where this comes from</span><p class="fs">' + esc(fact.source || "computed from the saved records") + '</p>' +
    (n ? '<p class="fs"><b>' + n + '</b> people behind it</p><button class="chip" data-f="' + esc(ids[0]) + '">Show people</button>' : '<p class="fs">A count over the whole result.</p>');
  return fcard(front, back, {h: 176});
}
function findingCards(findings){
  var head = findings.slice(0, 4), rest = findings.slice(4);
  return '<div class="fgrid">' + head.map(findingCard).join("") + '</div>' +
    (rest.length ? '<div class="fgrid" id="fmore" hidden>' + rest.map(findingCard).join("") + '</div><button class="btn small" id="fshow" style="margin-top:8px">Show all ' + findings.length + ' findings</button>' : "");
}
document.addEventListener("click", function(e){
  var b = e.target.closest && e.target.closest("#fshow"); if(!b) return;
  var m = $("fmore"); m.hidden = !m.hidden; b.textContent = m.hidden ? "Show all " + (m.children.length + 4) + " findings" : "Show fewer";
  wireCards(m);
  document.querySelectorAll("#fmore .chip").forEach(function(c){ c.onclick = function(){ showFact(c.getAttribute("data-f")); }; });
});

/* ---------- hero: one sentence and three numbers ---------- */
function renderHero(res){
  var a = res.analysis, b = res.brief, c = a.counts, om = a.overall_momentum, ex = a.exits;
  var sn = (a.senior && a.senior.list) || [], audit = (a.senior && a.senior.audit) || {};
  var paceCls = om.label === "growing" ? "pos" : om.label === "fading" ? "neg" : "";
  var T = [];
  T.push({l: "Real hires", v: c.external, s: c.in_window + ' raw "joiners", ' + c.relisted + " re-recorded removed",
    w: "Everyone whose current role here started since " + a.window.start + ", minus people who already held an earlier role here that ended within " + a.thresholds.relist_gap_days + " days. Source: Person Search. The Claim Court below tests this number."});
  T.push({l: "Pace", t: om.label.indexOf("not comparable") === 0 ? "capped" : om.label, cls: paceCls, s: om.last6 + " in the last 6 months vs " + om.prev + " before",
    w: "Real hires in the last 6 months against the 6 months before. Growing is 1.5x or more, fading is 0.5x or less. The court re-tests it ignoring the latest months, because profiles update late."});
  if(ex) T.push({l: "People who left", v: ex.left, s: "+ " + ex.internal_moves + " moved inside the company",
    w: "Roles here that ended in the window, minus people who still hold a role here. Recent exits are under-counted for the same lag reason as hires."});
  else T.push({l: "Senior hires", v: sn.length, s: "Director, VP and C-level",
    w: "Hires tagged Director, VP or C-level whose titles read as senior" + (audit.tagged > audit.kept ? " (" + (audit.tagged - audit.kept) + " assistant, intern or advisor titles removed)" : "") + "."});
  var tiles = T.map(function(t){
    var front = '<span class="t-l">' + t.l + '</span><b class="t-v ' + (t.cls || "") + '"' + (t.v != null ? ' data-count="' + t.v + '"' : '') +
      (t.t ? ' style="font-size:26px;padding-top:6px"' : '') + '>' + (t.t || 0) + '</b><small>' + esc(t.s) + '</small><i class="t-h">tap: how it is computed</i>';
    var back = '<span class="t-l">How this is computed</span><p class="fs">' + esc(t.w) + '</p>';
    return fcard(front, back, {h: 176});
  }).join("");
  $("hero").innerHTML = '<div class="kicker">' + esc(res.company.name) + ' · ' + esc(a.window.start) + ' to ' + esc(a.window.end) + '</div>' +
    '<p class="tldr">' + esc(b.tldr || b.headline) + '</p><div class="tiles three">' + tiles + '</div>';
  document.querySelectorAll("#hero [data-count]").forEach(function(el){ countUp(el, parseFloat(el.getAttribute("data-count")), 0); });
  wireCards($("hero"));
}

/* ---------- what X-Ray thinks they are building: a claim, six independent checks, and what would change our mind ---------- */
function thesisCard(t){
  var ico = {pass: "✓", fail: "✕", skip: "–"};
  var ticks = t.signals.map(function(s){ return '<span class="sgn ' + s.result + '" title="' + esc(s.name) + ': ' + esc(s.detail) + '"><i>' + ico[s.result] + '</i>' + esc(s.name) + '</span>'; }).join("");
  var cls = t.confidence === "strong" ? "ok" : t.confidence === "moderate" ? "warn" : "bad";
  var front = '<span class="pill ' + cls + '">' + esc(t.confidence) + ' · ' + t.passes + ' of ' + t.judged + ' checks</span>' +
    '<p class="th-st">' + esc(t.statement) + '</p><div class="sgns">' + ticks + '</div>' +
    (t.lift ? '<div class="sub" style="margin-top:6px"><b>' + t.lift + 'x</b> as common as at the other companies run</div>' : '') + '<i class="t-h">tap for the evidence chain</i>';
  var back = '<span class="t-l">Evidence chain</span>' + t.signals.map(function(s){
    return '<div class="tst ' + (s.result === "skip" ? "warn" : s.result) + '"><i>' + ico[s.result] + '</i><span><b>' + esc(s.name) + '.</b> ' + esc(s.detail) + '</span></div>'; }).join("") +
    '<p class="fs" style="margin-top:6px"><b>What would change our mind.</b> ' + esc(t.falsifier) + '</p>' +
    (t.feeders && t.feeders.length ? '<p class="fs"><b>Draws talent from:</b> ' + esc(t.feeders.join(", ")) + '</p>' : '');
  return fcard(front, '<div class="dscroll2">' + back + '</div>', {h: 300, cls: "thesis"});
}
function renderInsight(res){
  var el = $("insight"), th = (res.thesis && res.thesis.theses) || [], inf = res.brief && res.brief.inference;
  if(!th.length && !inf){ el.hidden = true; return; }
  el.hidden = false;
  if(!th.length){
    el.innerHTML = '<h2>What this suggests</h2><p class="insight">' + esc(inf.text) + '</p>'; return;
  }
  var peers = (res.thesis.peers || []);
  el.innerHTML = '<h2>What X-Ray thinks they are building</h2>' +
    '<div class="sub">A team is only named if it stands out from the other companies run' + (peers.length ? ' (' + esc(peers.join(", ")) + ')' : '') +
    ' and survives independent checks. Public profile data only, so a lean and not a plan. Tap a card for the evidence chain.</div>' +
    '<div class="tgrid">' + th.slice(0, 2).map(thesisCard).join("") + '</div>';
  wireCards(el);
}

/* ---------- Claim Court: a 3D deck. Demo mode shows the few killed claims that matter. ---------- */
var D = {cur: 0, all: [], demo: [], mode: "demo", filter: {killed: false, weakened: false, survived: false}, present: false, res: null, dragged: false, bound: false};
var TI = {pass: "✓", warn: "!", fail: "✕"};

function mergeClaims(ct){
  var kills = ct.claims.filter(function(c){ return c.verdict === "killed"; });
  var by = function(id){ return kills.filter(function(c){ return c.id === id; })[0]; };
  var spikes = kills.filter(function(c){ return /^C2/.test(c.id); }), out = [];
  if(by("C1")) out.push(by("C1"));
  if(spikes.length){
    var raw = 0, real = 0, months = spikes.map(function(s){ raw += s.naive.value; real += s.audited.value; return s.title.replace(/^A hiring spike in /, "").replace("?", ""); });
    out.push({id: "C2m", title: "Were there hiring spikes?", by: "naive tool", verdict: "killed",
      claim: months.join(" and ") + " were hiring spikes (" + raw + ' "hires")',
      tests: spikes.map(function(s, i){ return {name: months[i], result: s.tests[0].result, detail: s.tests[0].detail}; }),
      naive: {label: "raw hires in the spike months", value: raw}, audited: {label: "real hires in those months", value: real},
      why: "The spikes are mostly profile restructuring, not hiring.", cols: spikes[0].cols, rows: spikes[0].rows});
  }
  if(by("C7")) out.push(by("C7"));
  var parts = [by("C8"), by("C9")].filter(Boolean);
  if(parts.length) out.push({id: "C89", title: "Do the company's own records agree?", by: "naive tool", verdict: "killed",
    claim: parts.map(function(p){ return p.claim; }).join(". "), tests: [].concat.apply([], parts.map(function(p){ return p.tests; })),
    naive: {label: "company record says", value: parts.map(function(p){ return fv(p.naive.value); }).join(" · ")},
    audited: {label: "the data says", value: parts.map(function(p){ return fv(p.audited.value); }).join(" · ")},
    why: "The headcount series and job search are used instead.", cols: [], rows: []});
  kills.forEach(function(k){ if(out.indexOf(k) < 0 && !/^C2/.test(k.id) && k.id !== "C8" && k.id !== "C9" && out.length < 4) out.push(k); });
  return (out.length ? out : ct.claims.slice(0, 3)).slice(0, 4);
}
function visibleClaims(){ return D.mode === "demo" ? D.demo : D.all.filter(function(c){ return D.filter[c.verdict]; }); }

function dcardHTML(c, i, n){
  var big = "";
  if(c.naive && c.naive.value != null) big = '<div class="d-big' + (String(c.naive.value).length > 6 ? " sm" : "") + '">' + fv(c.naive.value) + '</div><div class="d-bl">' + esc(c.naive.label) + '</div>';
  var front = '<div class="d-top"><span>' + esc(c.by) + ' says</span><span>' + (i + 1) + ' / ' + n + '</span></div><h4>' + esc(c.title) + '</h4><p class="d-claim">' + esc(c.claim) + '</p>' + big +
    '<div class="d-hint">Tap the card to put it on trial ⟳</div>';
  var swap = c.naive && c.audited && c.naive.value != null && c.audited.value != null ?
    '<div class="d-swap"><s>' + fv(c.naive.value) + '</s><span>→</span><b>' + fv(c.audited.value) + '</b><small>' + esc(c.naive.label) + ' → ' + esc(c.audited.label) + (c.audited.note ? ' (' + esc(c.audited.note) + ')' : '') + '</small></div>' : "";
  var person = c.cols && c.cols[0] === "Person";
  var rows = c.rows && c.rows.length ? '<table style="margin-top:8px"><tr>' + c.cols.map(function(x){ return '<th>' + esc(x) + '</th>'; }).join("") + '</tr>' +
    c.rows.map(function(r){ return '<tr><td' + (person ? ' class="pn"' : '') + '>' + esc(r.a) + '</td>' + (r.b != null ? '<td>' + esc(r.b) + '</td>' : '') + (r.c != null ? '<td>' + esc(r.c) + '</td>' : '') + '</tr>'; }).join("") + '</table>' : "";
  var back = '<div class="stamp ' + c.verdict + '">' + c.verdict.toUpperCase() + '</div><h4>' + esc(c.title) + '</h4>' + swap +
    '<div class="dscroll' + (swap ? "" : " noswap") + '">' + c.tests.map(function(t){
      return '<div class="tst ' + t.result + '"><i>' + TI[t.result] + '</i><span><b>' + esc(t.name) + '.</b> ' + esc(t.detail) + '</span></div>'; }).join("") +
    (c.why ? '<div class="sub" style="margin-top:8px">' + esc(c.why) + '</div>' : "") + rows + '</div>';
  return '<div class="dcard ' + c.verdict + '" data-i="' + i + '"><div class="fc-inner"><div class="fc-face fc-front">' + front + '</div><div class="fc-face fc-back">' + back + '</div></div></div>';
}

function positionDeck(){
  var cards = document.querySelectorAll(".dcard");
  cards.forEach(function(el, i){
    var off = i - D.cur, a = Math.abs(off), step = D.present ? 52 : 58;
    el.style.zIndex = 100 - a;
    el.style.opacity = a > 3 ? 0 : 1 - a * 0.2;
    el.style.pointerEvents = a > 3 ? "none" : "auto";
    el.style.transform = "translateX(-50%) translateX(" + (off * step) + "%) translateZ(" + (-a * 180) + "px) rotateY(" + (-off * 30) + "deg) scale(" + (1 - a * 0.05) + ")";
    el.classList.toggle("active", off === 0);
  });
  var n = cards.length, cnt = $("dCount"); if(cnt) cnt.textContent = n ? (D.cur + 1) + " / " + n : "none";
  document.querySelectorAll("#dDots i").forEach(function(d, i){ d.classList.toggle("on", i === D.cur); });
}
function goDeck(i){ var n = document.querySelectorAll(".dcard").length; if(!n) return; D.cur = Math.max(0, Math.min(n - 1, i)); positionDeck(); }
function flipCurrent(){ var el = document.querySelectorAll(".dcard")[D.cur]; if(el) el.classList.toggle("flipped"); }
function setPresent(on){
  D.present = on; var w = $("deckwrap"); if(!w) return;
  w.classList.toggle("present", on); document.body.classList.toggle("presenting", on);
  $("dPresent").textContent = on ? "Exit (Esc)" : "Present";
  positionDeck();
}
function syncChips(){
  document.querySelectorAll(".cbtn").forEach(function(b){
    var v = b.getAttribute("data-v"), on = D.mode === "demo" ? v === "killed" : D.filter[v];
    b.classList.toggle("off", !on);
  });
  var m = $("dMode"); if(m) m.textContent = D.mode === "demo" ? "Show all " + D.all.length + " claims" : "Show the key " + D.demo.length;
}
function buildDeck(){
  var list = visibleClaims();
  $("dstage").innerHTML = list.map(function(c, i){ return dcardHTML(c, i, list.length); }).join("");
  $("dDots").innerHTML = list.map(function(c, i){ return '<i class="' + c.verdict + '" data-i="' + i + '" title="' + esc(c.title) + '"></i>'; }).join("");
  D.cur = Math.min(D.cur, Math.max(0, list.length - 1));
  document.querySelectorAll(".dcard").forEach(function(el, i){
    el.addEventListener("click", function(){
      if(D.dragged){ D.dragged = false; return; }
      if(i === D.cur) el.classList.toggle("flipped"); else goDeck(i);
    });
  });
  document.querySelectorAll("#dDots i").forEach(function(d){ d.addEventListener("click", function(){ goDeck(+d.getAttribute("data-i")); }); });
  syncChips(); positionDeck();
}
function deckKey(e){
  if(e.key === "ArrowRight") { e.preventDefault(); goDeck(D.cur + 1); }
  else if(e.key === "ArrowLeft") { e.preventDefault(); goDeck(D.cur - 1); }
  else if(e.key === " " || e.key === "Enter") { e.preventDefault(); flipCurrent(); }
  else if(e.key === "p" || e.key === "P") setPresent(!D.present);
  else if(e.key === "Escape" && D.present) setPresent(false);
}

function renderCourt(res){
  var el = $("courtcard"), ct = res.court, more = $("courtmore");
  if(!ct || !ct.claims){ el.hidden = true; more.hidden = true; return; }
  el.hidden = false; D.all = ct.claims; D.demo = mergeClaims(ct); D.mode = "demo"; D.filter = {killed: false, weakened: false, survived: false};
  D.cur = 0; D.res = res; D.present = false; document.body.classList.remove("presenting");
  var s = ct.summary;
  el.innerHTML = '<div class="kicker sub" style="letter-spacing:.8px;text-transform:uppercase">Claim Court</div>' +
    '<h3 style="margin:0 0 4px;font-size:22px">X-Ray put ' + s.tried + ' claims on trial. ' + s.killed + ' did not survive.</h3>' +
    '<div class="sub">Each card is something a straightforward tool would tell you. Tap a card for the verdict. ← → move, Space flips, P presents.</div>' +
    '<div class="deckwrap" id="deckwrap" tabindex="0"><div class="dctl"><div class="cnt">' +
    ["killed", "weakened", "survived"].map(function(v){ return '<button class="cbtn ' + v + '" data-v="' + v + '"><b>' + s[v] + '</b><span>' + v + '</span></button>'; }).join("") +
    '</div><div class="dnav"><button class="btn" id="dPrev" aria-label="Previous">‹</button><span id="dCount"></span><button class="btn" id="dNext" aria-label="Next">›</button>' +
    '<button class="btn" id="dFlip">Flip ⟳</button><button class="btn" id="dMode"></button><button class="btn primary" id="dPresent">Present</button></div></div>' +
    '<div class="deck" id="deck"><div class="dstage" id="dstage"></div></div><div class="dots" id="dDots"></div></div>';
  buildDeck();
  el.querySelectorAll(".cbtn").forEach(function(b){
    b.addEventListener("click", function(){
      var v = b.getAttribute("data-v");
      if(D.mode === "demo"){ D.mode = "all"; D.filter = {killed: false, weakened: false, survived: false}; D.filter[v] = true; }
      else D.filter[v] = !D.filter[v];
      D.cur = 0; buildDeck();
    });
  });
  $("dMode").onclick = function(){
    if(D.mode === "demo"){ D.mode = "all"; D.filter = {killed: true, weakened: true, survived: true}; } else { D.mode = "demo"; }
    D.cur = 0; buildDeck();
  };
  $("dPrev").onclick = function(){ goDeck(D.cur - 1); };
  $("dNext").onclick = function(){ goDeck(D.cur + 1); };
  $("dFlip").onclick = flipCurrent;
  $("dPresent").onclick = function(){ setPresent(!D.present); };
  $("deckwrap").addEventListener("keydown", deckKey);
  var stage = $("deck"), x0 = null;
  stage.addEventListener("pointerdown", function(e){ x0 = e.clientX; D.dragged = false; });
  stage.addEventListener("pointerup", function(e){ if(x0 === null) return; var dx = e.clientX - x0; x0 = null; if(Math.abs(dx) > 60){ D.dragged = true; goDeck(D.cur + (dx < 0 ? 1 : -1)); } });
  stage.addEventListener("pointercancel", function(){ x0 = null; });

  // the detail that does not belong on the demo screen
  var cal = ct.calibration || {}, h = '<h2>Court detail</h2>';
  if(ct.table && ct.table.length){
    h += '<h2 style="margin-top:6px">Naive vs audited</h2><table><tr><th>Question</th><th>Naive answer</th><th>Audited answer</th><th></th></tr>' +
      ct.table.map(function(r){ return '<tr><td>' + esc(r.metric) + '</td><td><s>' + fv(r.naive.value) + '</s> <span class="sub">' + esc(r.naive.label) + '</span></td><td><b>' + fv(r.audited.value) + '</b> <span class="sub">' + esc(r.audited.label) + '</span></td><td><span class="vchip ' + r.verdict + '">' + r.verdict + '</span></td></tr>'; }).join("") + '</table>';
  }
  h += '<h2 style="margin-top:16px">Calls on the record <span class="sub">(fixed by hash now, scored later against fresh data; tap to flip)</span></h2><div class="pgrid">' +
    (ct.predictions || []).map(function(p){
      var front = '<span class="pill">pending</span><p class="fs" style="font-size:15px;font-weight:700;margin-top:8px">' + esc(p.statement) + '</p><i class="t-h">tap for the proof</i>';
      var back = '<span class="t-l">Fixed by hash</span><p class="fs"><code style="font-size:11.5px;word-break:break-all">' + esc(p.hash || "") + '</code></p><p class="fs">Due ' + esc(p.due) + '. Scored with <code>python -m app.cli score</code>. Nothing has been scored yet.</p>';
      return fcard(front, back, {h: 150});
    }).join("") + '</div>' +
    (cal.windows ? '<div class="sub" style="margin-top:8px">Method check on this company\'s own history: the headcount rule landed within ±4% in <b>' + Math.round(100 * cal.trend_rate) + '%</b> of ' + cal.windows + ' past 8-week windows, against <b>' + Math.round(100 * cal.flat_rate) + '%</b> for "nothing changes".</div>' : "");
  more.hidden = false; more.innerHTML = h; wireCards(more);
}
if(!D.bound){ D.bound = true; document.addEventListener("keydown", function(e){ if(D.present && !(e.target && e.target.closest && e.target.closest("#deckwrap"))) deckKey(e); }); }

/* ---------- senior hires: a timeline, then flip-cards ---------- */
function renderSenior(a){
  var sn = a.senior || {list: [], counts: {}}, el = $("seniorcard"), c = sn.counts || {};
  var head = '<h2>Senior hires radar <span class="sub">Director, VP and C-level who joined in the window</span></h2>';
  if(!sn.list.length){ el.innerHTML = head + '<div class="sub">No senior hires found in the window.</div>'; return; }
  var sub = ["CXO", "Vice President", "Director"].filter(function(k){ return c[k]; }).map(function(k){ return c[k] + " " + k + (c[k] > 1 && k !== "CXO" ? "s" : ""); }).join(" · ");
  var short = {"CXO": "CXO", "Vice President": "VP", "Director": "Director"};
  var cards = sn.list.slice(0, 12).map(function(s){
    var front = '<span class="vtag ' + short[s.level] + '">' + short[s.level] + '</span><div class="ft" style="font-weight:700;max-height:62px">' + esc(s.title) + '</div><small style="position:absolute;left:14px;bottom:10px">joined ' + esc(s.start) + '</small><i class="t-h">tap: who and from where</i>';
    var back = '<span class="t-l">Who</span><p class="fs pn"><b>' + esc(s.name) + '</b></p><p class="fs">from <b>' + esc(s.prev || "unknown") + '</b></p><p class="fs">' + esc(s.dept) + '</p>';
    return fcard(front, back, {h: 132});
  }).join("");
  var aud = (sn.audit && sn.audit.tagged > sn.audit.kept) ? '<div class="sub" style="margin-top:6px">Audit: ' + (sn.audit.tagged - sn.audit.kept) + ' of ' + sn.audit.tagged + ' tagged-senior titles were assistants, interns or advisors and were removed.</div>' : "";
  el.innerHTML = head + '<div class="sub" style="margin-bottom:6px">' + esc(sub) + '. A new senior leader says more about direction than a dozen junior hires.</div>' + seniorTimeline(a) +
    '<div class="legend"><span><i class="sw" style="background:var(--bad);border-radius:50%"></i>C-level</span><span><i class="sw" style="background:var(--accent);border-radius:50%"></i>VP</span><span><i class="sw" style="background:var(--ok);border-radius:50%"></i>Director</span><span>hover a dot, or tap a card</span></div>' +
    '<div class="sgrid">' + cards + '</div>' + (sn.list.length > 12 ? '<div class="sub" style="margin-top:6px">first 12 of ' + sn.list.length + '</div>' : "") + aud;
  wireCards(el);
}

/* ---------- pointer parallax, privacy and theme toggles ---------- */
(function(){
  var bg = document.createElement("div"); bg.className = "bg3d"; bg.innerHTML = "<i></i><i></i><i></i>"; document.body.insertBefore(bg, document.body.firstChild);
  if(!reduceMotion){
    document.addEventListener("pointermove", function(e){
      var x = e.clientX / innerWidth - .5, y = e.clientY / innerHeight - .5;
      bg.children[0].style.transform = "translate(" + (x * 50) + "px," + (y * 40) + "px)";
      bg.children[1].style.transform = "translate(" + (-x * 70) + "px," + (y * 50) + "px)";
      bg.children[2].style.transform = "translate(" + (x * 30) + "px," + (-y * 60) + "px)";
    });
  }
  function store(k, v){ try{ if(v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); }catch(e){ return null; } }
  var tools = $("hdrTools"); if(!tools) return;
  var names = store("xray-names") === "show"; document.body.classList.toggle("hide-names", !names);
  tools.innerHTML = '<button class="btn small" id="btnNames"></button><button class="btn small" id="btnTheme">Light / dark</button>';
  function label(){ $("btnNames").textContent = document.body.classList.contains("hide-names") ? "Names hidden: show" : "Names shown: hide"; }
  label();
  $("btnNames").onclick = function(){ var h = document.body.classList.toggle("hide-names"); store("xray-names", h ? "hide" : "show"); label(); };
  var t = store("xray-theme"); if(t) document.documentElement.setAttribute("data-theme", t);
  $("btnTheme").onclick = function(){
    var dark = window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches;
    var cur = document.documentElement.getAttribute("data-theme") || (dark ? "dark" : "light"), nxt = cur === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", nxt); store("xray-theme", nxt);
  };
})();
