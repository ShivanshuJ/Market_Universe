"use strict";
/* Small API call log pinned to the bottom. Hover (or focus) to enlarge. Shows path, what was asked, live or cached, credits, time. */
(function(){
  var box = document.createElement("div");
  box.id = "clog"; box.tabIndex = 0;
  box.innerHTML = '<div class="cl-head"><b>API calls</b><span id="clSum">no calls yet</span><i>hover to enlarge</i></div><div class="cl-body" id="clBody"></div>';
  document.body.appendChild(box);
  var body = box.querySelector("#clBody"), sum = box.querySelector("#clSum"), last = 0, n = 0, live = 0, cached = 0, credits = 0;
  function e(s){ return String(s == null ? "" : s).replace(/[&<>"]/g, function(c){ return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
  function poll(){
    fetch("/api/calllog?after=" + last).then(function(r){ return r.json(); }).then(function(rows){
      if(!Array.isArray(rows) || !rows.length) return;
      rows.forEach(function(r){
        last = r.id; n++; if(r.source === "cache") cached++; else live++; credits += r.credits || 0;
        var row = document.createElement("div");
        row.className = "cl-row " + (r.source === "cache" ? "c" : String(r.status).indexOf("error") === 0 ? "x" : "l");
        row.innerHTML = '<span class="t">' + e(r.ts) + '</span><span class="s">' + (r.source === "cache" ? "cache" : "live") + '</span><span class="p">' + e(r.path) + '</span><span class="w">' + e(r.what) + '</span><span class="m">' +
          (r.source === "cache" ? "" : r.ms + " ms · " + r.credits + " cr") + (String(r.status).indexOf("error") === 0 ? " · " + e(r.status) : "") + '</span>';
        body.insertBefore(row, body.firstChild);
      });
      while(body.children.length > 200) body.removeChild(body.lastChild);
      sum.textContent = n + " calls · " + live + " live · " + cached + " cached · " + credits.toFixed(1) + " credits";
    }).catch(function(){});
  }
  poll(); setInterval(poll, 1500);
})();
