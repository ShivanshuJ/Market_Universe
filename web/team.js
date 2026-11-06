"use strict";
/* Team page: the team name and the four members. Names, roles and GitHub come from team.json (public).
   Roll numbers and emails come from team.local.json, which git ignores, so they show on this machine
   and are not published with the repo. If that file is missing, only the public fields are drawn. */
function esc(s){ return String(s == null ? "" : s).replace(/[&<>"]/g, function(c){ return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
function load(u){ return fetch(u).then(function(r){ return r.ok ? r.json() : null; }).catch(function(){ return null; }); }
var HUES = [["#2dffc4", "#27e8ff"], ["#8a6bff", "#27e8ff"], ["#ffbd4a", "#ff4d6d"], ["#ff4d6d", "#8a6bff"]];

Promise.all([load("/team.json"), load("/team.local.json")]).then(function(a){
  var pub = a[0] || {}, loc = a[1] || {};
  var members = (pub.members || []).slice(0, 4).map(function(m, i){ return Object.assign({}, m, (loc.members || [])[i] || {}); });
  document.title = "Team " + (pub.team_name || "");
  var h = '<a class="back" href="/">&larr; Market Universe</a><div class="kick">Team</div><h1>' + esc(pub.team_name || "Team") + '</h1>' +
    '<p class="line">' + esc(pub.one_line || "") + '</p><div class="tgrid">' + members.map(function(m, i){
      var rows = [["Roll", m.roll], ["IITK", m.iitk_email], ["Email", m.personal_email]].filter(function(r){ return r[1]; });
      return '<div class="card" style="--i:' + i + ';--c1:' + HUES[i % 4][0] + ';--c2:' + HUES[i % 4][1] + '"><div class="av">' + esc((m.name || "?").charAt(0).toUpperCase()) + '</div>' +
        '<h2>' + esc(m.name) + '</h2>' + (m.github ? '<a class="gh" href="https://github.com/' + esc(m.github) + '" target="_blank" rel="noopener">@' + esc(m.github) + '</a>' : "") +
        rows.map(function(r){ return '<div class="f"><span>' + r[0] + '</span><b>' + esc(r[1]) + '</b></div>'; }).join("") + '</div>'; }).join("") + '</div>' +
    '<div class="foot"><a href="/">Open the product</a>' + (pub.repo ? '<a href="' + esc(pub.repo) + '" target="_blank" rel="noopener">GitHub repo</a>' : "") + '</div>';
  document.getElementById("main").innerHTML = h;
  document.querySelectorAll(".card").forEach(function(el){
    el.addEventListener("pointermove", function(e){
      var r = el.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5;
      el.style.setProperty("--ry", (x * 9).toFixed(2) + "deg"); el.style.setProperty("--rx", (-y * 9).toFixed(2) + "deg");
      el.style.setProperty("--gx", ((x + .5) * 100) + "%"); el.style.setProperty("--gy", ((y + .5) * 100) + "%");
    });
    el.addEventListener("pointerleave", function(){ el.style.setProperty("--rx", "0deg"); el.style.setProperty("--ry", "0deg"); });
  });
});
