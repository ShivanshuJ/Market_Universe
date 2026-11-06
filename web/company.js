"use strict";
/* Complete one-company page: /company.html?id=<crustdata id>. One API call (cached after the first). */
var $ = function(id){ return document.getElementById(id); };
function esc(s){ return String(s == null ? "" : s).replace(/[&<>"]/g, function(c){ return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
function sgn(x){ return x == null ? "n/a" : (x > 0 ? "+" : "") + Math.round(x) + "%"; }
function nf(x){ return x == null ? "n/a" : Number(x).toLocaleString(); }
function usd(x){ return x ? "$" + Math.round(x / 1e6).toLocaleString() + "M" : "n/a"; }
function bar(pct, max){ return '<span class="bar"><i style="width:' + Math.min(100, 100 * pct / max) + '%"></i></span>'; }

function chart(series, stats){
  if(!series || series.length < 4) return '<p class="sub">Not enough history to draw a curve.</p>';
  var W = 1000, H = 260, pl = 46, pr = 14, pt = 16, pb = 30, vals = series.map(function(p){ return p[1]; });
  var mx = Math.max.apply(null, vals), mn = Math.min.apply(null, vals), lo = Math.max(0, mn - (mx - mn) * 0.1), hi = mx + (mx - mn) * 0.1 || mx + 1;
  var X = function(i){ return pl + (W - pl - pr) * i / (series.length - 1); }, Y = function(v){ return pt + (H - pt - pb) * (1 - (v - lo) / (hi - lo)); };
  var pts = series.map(function(p, i){ return X(i).toFixed(1) + "," + Y(p[1]).toFixed(1); }), pi = vals.indexOf(mx);
  var grid = [0, .5, 1].map(function(t){ var v = lo + (hi - lo) * t; return '<line x1="' + pl + '" x2="' + (W - pr) + '" y1="' + Y(v) + '" y2="' + Y(v) + '" stroke="rgba(255,255,255,.08)"/><text x="' + (pl - 6) + '" y="' + (Y(v) + 4) + '" text-anchor="end">' + Math.round(v).toLocaleString() + '</text>'; }).join("");
  return '<svg class="chart" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none"><defs><linearGradient id="ga" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#27e8ff" stop-opacity=".35"/><stop offset="1" stop-color="#27e8ff" stop-opacity="0"/></linearGradient></defs>' + grid +
    '<polygon class="area" points="' + pl + "," + (H - pb) + " " + pts.join(" ") + " " + (W - pr) + "," + (H - pb) + '"/><polyline class="line" points="' + pts.join(" ") + '"/>' +
    '<circle class="peak" cx="' + X(pi) + '" cy="' + Y(mx) + '" r="5"/><text x="' + (X(pi) > W * 0.85 ? X(pi) - 12 : X(pi)) + '" y="' + (Y(mx) - 10) + '" text-anchor="' + (X(pi) > W * 0.85 ? "end" : "middle") + '">peak ' + mx.toLocaleString() + '</text>' +
    '<circle class="now" cx="' + X(series.length - 1) + '" cy="' + Y(vals[vals.length - 1]) + '" r="5"/>' +
    '<text x="' + pl + '" y="' + (H - 8) + '">' + esc(series[0][0].slice(0, 7)) + '</text><text x="' + (W - pr) + '" y="' + (H - 8) + '" text-anchor="end">' + esc(series[series.length - 1][0].slice(0, 7)) + ' (now ' + vals[vals.length - 1].toLocaleString() + ')</text></svg>';
}

function page(d){
  document.title = d.name + " · profile"; $("ctag").textContent = "Crustdata · " + (d.acquired ? "marked as acquired" : "live data");
  var h = '<section class="chero"><div>' + (d.logo ? '<img class="logo-b" src="' + esc(d.logo) + '" alt="" onerror="this.remove()">' : "") +
    '<div class="k">Company profile</div><h1>' + esc(d.name) + '</h1><div class="meta">' + [d.hq, d.founded ? "founded " + d.founded : "", d.type, (d.categories || []).slice(0, 3).join(", ")].filter(Boolean).map(esc).join(" · ") + '</div>' +
    '<p>' + esc(d.description) + '</p><div class="links">' + (d.website ? '<a href="' + esc(d.website) + '" target="_blank" rel="noopener">Website</a>' : "") + (d.linkedin ? '<a href="' + esc(d.linkedin) + '" target="_blank" rel="noopener">LinkedIn</a>' : "") +
    '<a href="/analysis.html?company=' + encodeURIComponent(d.name) + '" target="_blank">Deep analysis (claims, thesis) &rarr;</a></div></div>' +
    '<div class="stat3"><div><b>' + nf(d.headcount) + '</b><span>people</span></div><div><b style="color:' + (d.g12 != null && d.g12 < 0 ? "var(--bad)" : "var(--ok)") + '">' + sgn(d.g12) + '</b><span>12 months</span></div><div><b>' + nf(d.open_roles) + '</b><span>open roles</span></div></div></section>';
  if(d.reads && d.reads.length) h += '<section class="sec"><h2>What this tells you</h2><div class="reads2">' + d.reads.map(function(x){ return '<div>' + esc(x) + '</div>'; }).join("") + '</div></section>';
  h += '<section class="sec"><h2>Headcount over time</h2>' + chart(d.series, d.stats) + '</section>';
  h += '<section class="sec"><h2>The numbers</h2><div class="kv">' + [["Added in 12 months", d.added_12m != null ? (d.added_12m > 0 ? "+" : "") + nf(d.added_12m) : "n/a"], ["Added in 6 months", d.added_6m != null ? (d.added_6m > 0 ? "+" : "") + nf(d.added_6m) : "n/a"],
    ["Raised", usd(d.raised_usd)], ["Funding rounds", nf(d.round_count)], ["Revenue (estimate)", d.revenue_band ? usd(d.revenue_band[0]) + " to " + usd(d.revenue_band[1]) : "n/a"],
    ["Employee rating", d.rating ? d.rating + " / 5" : "n/a"], ["Reviews", nf(d.reviews)], ["Followers", nf(d.followers)], ["Follower growth", sgn(d.followers_yoy)]].map(function(x){ return '<div><span>' + x[0] + '</span><b>' + x[1] + '</b></div>'; }).join("") + '</div></section>';
  h += '<div class="cols"><section class="sec"><h2>Where the people are (share, 6-month change)</h2>' + (d.teams.length ? d.teams.map(function(t){
      return '<div class="rowb"><span>' + esc(t.name) + '</span>' + bar(t.share, d.teams[0].share) + '<b>' + t.share + '%</b><em>' + sgn(t.g6) + '</em></div>'; }).join("") : '<p class="sub">n/a</p>') +
    (d.cities.length ? '<h2 style="margin-top:18px">Main cities</h2><div class="chips">' + d.cities.map(function(c){ return '<span class="chp">' + esc(c.name) + ' ' + c.share + '%</span>'; }).join("") + '</div>' : "") + '</section>' +
    '<section class="sec"><h2>What employees say (out of 5)</h2>' + (d.ratings.length ? d.ratings.map(function(r){ return '<div class="rowb"><span>' + esc(r.label) + '</span>' + bar(r.value, 5) + '<b>' + r.value + '</b></div>'; }).join("") : '<p class="sub">n/a</p>') +
    (d.role_titles.length ? '<h2 style="margin-top:18px">Roles open right now (sample of ' + nf(d.open_roles) + ')</h2><div class="chips">' + d.role_titles.map(function(t){ return '<span class="chp">' + esc(t) + '</span>'; }).join("") + '</div>' : "") + '</section></div>';
  h += '<div class="cols"><section class="sec"><h2>Funding timeline</h2>' + (d.rounds.length ? '<div class="tl">' + d.rounds.map(function(r){
      return '<div class="it"><b>' + (r.amount_usd ? usd(r.amount_usd) : "undisclosed") + '</b> · ' + esc(r.type) + '<small>' + esc(r.date) + (r.investors ? ' · ' + esc(r.investors) : '') + '</small></div>'; }).join("") + '</div>' : '<p class="sub">No rounds on record.</p>') + '</section>' +
    '<section class="sec"><h2>Recent news (links, not verified by us)</h2><div class="newsl">' + (d.news.length ? d.news.map(function(n){
      return '<a href="' + esc(n.url) + '" target="_blank" rel="noopener">' + esc(n.title) + '<small>' + esc(n.publisher || "") + ' · ' + esc((n.date || "").slice(0, 10)) + '</small></a>'; }).join("") : '<p class="sub">No recent news found.</p>') + '</div></section></div>';
  h += '<p class="fine">Source: Crustdata company data (headcount from profile counts, so recent months can lag), open roles from live job search, news as reported links. Estimates such as revenue are bands, not facts.</p>';
  $("main").innerHTML = h;
}

var id = new URLSearchParams(location.search).get("id");
if(!id){ $("main").innerHTML = '<p class="sub" style="padding:80px 0">No company id in the link. Open this page from the Market Universe.</p>'; }
else fetch("/api/dossier?full=1&id=" + encodeURIComponent(id)).then(function(r){ return r.json(); }).then(function(d){
  if(d.error){ $("main").innerHTML = '<div class="warnbox">' + esc(d.error) + '</div>'; return; }
  page(d);
}).catch(function(){ $("main").innerHTML = '<div class="warnbox">Could not reach the server.</div>'; });
