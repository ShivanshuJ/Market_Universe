"use strict";
/* Team and submission page, following the ContextCon handbook's "what the form asks for".
   Public details come from team.json. Private ones (emails, roll number) are read from team.local.json,
   which is git-ignored, and are never drawn on the page: only their presence is shown. */
var $ = function(id){ return document.getElementById(id); };
function esc(s){ return String(s == null ? "" : s).replace(/[&<>"]/g, function(c){ return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
var PRIVATE = [["registered_email", "YC-registered email"], ["iitk_email", "IIT Kanpur email"], ["roll", "Roll number"], ["personal_email", "Personal email"], ["github", "GitHub username"]];
var CHECK = [
  "Repo is public and its commit history starts at 11:00 PM on 5 November",
  "README is in the repo",
  "Demo video is one link (Loom, unlisted YouTube or Drive), two minutes, plays in a private window",
  "Diagram link opens for anyone",
  "Every member's name and email match the YC event registration; everyone used their @iitk.ac.in address for credits",
  "Rotate the Crustdata key after the event (it was pasted in chat)"
];
function load(u){ return fetch(u).then(function(r){ return r.ok ? r.json() : null; }).catch(function(){ return null; }); }

Promise.all([load("/team.json"), load("/team.local.json")]).then(function(a){
  var pub = a[0] || {}, loc = a[1] || {}, members = (pub.members || []).map(function(m, i){ return Object.assign({}, m, (loc.members || [])[i] || {}); });
  var team = loc.team_name || pub.team_name || "";
  function g(k){ return loc[k] || pub[k] || ""; }
  var h = '<section class="chero"><div><div class="k">Team and submission</div><h1>' + esc(team || "Your team name") + '</h1><p>' + esc(g("one_line")) + '</p>' +
    '<div class="links"><a href="/">Open the product</a>' + (g("repo") ? '<a href="' + esc(g("repo")) + '" target="_blank" rel="noopener">GitHub repo</a>' : "") +
    (g("video") ? '<a href="' + esc(g("video")) + '" target="_blank" rel="noopener">Demo video</a>' : "") + (g("diagram") ? '<a href="' + esc(g("diagram")) + '" target="_blank" rel="noopener">Diagram</a>' : "") + '</div></div>' +
    '<div class="stat3" style="grid-template-columns:1fr"><div><b class="clock" id="clock">--</b><span>until code freeze, 7:00 AM IST on 6 Nov</span></div></div></section>';

  h += '<section class="sec"><h2>Members (up to four)</h2><div class="mem">' + members.slice(0, 4).map(function(m){
    var chips = PRIVATE.map(function(p){ return '<span class="' + (m[p[0]] ? "ok" : "no") + '">' + (m[p[0]] ? "✓ " : "add ") + p[1] + '</span>'; }).join("");
    return '<div class="mc"><div class="av">' + esc((m.name || "?").trim().charAt(0).toUpperCase()) + '</div><h3>' + esc(m.name || "Member") + '</h3><div class="r">' + esc(m.role || "Builder") + '</div><div class="st">' + chips + '</div></div>';
  }).join("") + (members.length < 4 ? '<div class="mc empty">Add up to ' + (4 - members.length) + ' more in team.json</div>' : "") + '</div>' +
    '<p class="fine">Private fields live in <code>web/team.local.json</code>, which git ignores. They are never shown on this page, only counted. The form wants, per member: name and email as on the YC event registration, IIT Kanpur email, roll number, personal email, GitHub username.</p></section>';

  var fields = [["Team name", team], ["One line", g("one_line")], ["Theme", g("theme")], ["GitHub repo", g("repo")], ["Demo video", g("video")],
    ["The service it replaces", g("service")], ["Engineering approach and models", g("approach")], ["What we would build next", g("next")], ["High-level diagram", g("diagram")]];
  h += '<section class="sec"><h2>Submission answers (what the form asks for)</h2>' + fields.map(function(f){
    return '<div class="field"><span>' + f[0] + '</span><b' + (f[1] ? "" : ' class="miss"') + '>' + (f[1] ? esc(f[1]) : "Fill this in team.json") + '</b></div>'; }).join("") +
    '<button class="copy" id="copy">Copy all answers</button> <span class="sub" id="copied"></span></section>';

  var saved = {}; try { saved = JSON.parse(localStorage.getItem("xray-submit-check") || "{}"); } catch(e) {}
  h += '<section class="sec"><h2>Before you press submit</h2><ul class="chk">' + CHECK.map(function(c, i){
    return '<li class="' + (saved[i] ? "done" : "") + '"><input type="checkbox" data-i="' + i + '"' + (saved[i] ? " checked" : "") + '><span>' + esc(c) + '</span></li>'; }).join("") + '</ul></section>';
  h += '<p class="fine">Built under the theme "' + esc(g("theme")) + '". Data from Crustdata. This page follows the handbook\'s submission section.</p>';
  $("main").innerHTML = h;

  $("copy").onclick = function(){
    var txt = fields.map(function(f){ return f[0] + ": " + (f[1] || "(missing)"); }).join("\n\n");
    (navigator.clipboard ? navigator.clipboard.writeText(txt) : Promise.reject()).then(function(){ $("copied").textContent = "Copied."; }, function(){ $("copied").textContent = "Copy blocked by the browser."; });
  };
  document.querySelectorAll(".chk input").forEach(function(cb){
    cb.onchange = function(){
      cb.parentNode.classList.toggle("done", cb.checked);
      var s = {}; document.querySelectorAll(".chk input").forEach(function(x){ if(x.checked) s[x.getAttribute("data-i")] = 1; });
      try { localStorage.setItem("xray-submit-check", JSON.stringify(s)); } catch(e) {}
    };
  });
  function tick(){
    var t = new Date("2026-11-06T07:00:00+05:30") - new Date(), el = $("clock");
    if(t <= 0){ el.textContent = "Freeze passed"; return; }
    var m = Math.floor(t / 60000); el.textContent = Math.floor(m / 60) + "h " + String(m % 60).padStart(2, "0") + "m";
  }
  tick(); setInterval(tick, 20000);
});
