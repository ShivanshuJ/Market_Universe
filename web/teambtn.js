"use strict";
/* A Team button that stays visible on every page and opens the team and submission page. */
(function(){
  if(location.pathname === "/team.html") return;
  var st = document.createElement("style");
  st.textContent = '#teambtn{position:fixed;top:12px;right:16px;z-index:90;display:flex;align-items:center;gap:8px;border:1px solid rgba(255,255,255,.18);border-radius:99px;padding:8px 16px 8px 10px;background:rgba(10,12,20,.82);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);color:#f3f6ff;text-decoration:none;font:700 13px "Space Grotesk",system-ui,sans-serif;box-shadow:0 10px 30px -10px rgba(0,0,0,.7);transition:transform .2s,border-color .2s}' +
    '#teambtn:hover{transform:translateY(-2px);border-color:#27e8ff}#teambtn i{width:22px;height:22px;border-radius:50%;display:grid;place-items:center;font:700 11px "JetBrains Mono",monospace;color:#04050a;background:linear-gradient(120deg,#2dffc4,#27e8ff);font-style:normal}' +
    '.top,.ctop,body.legacy header{padding-right:130px!important}@media(max-width:760px){#teambtn span{display:none}#teambtn{padding:8px}.top,.ctop{padding-right:64px!important}}';
  document.head.appendChild(st);
  var a = document.createElement("a"); a.id = "teambtn"; a.href = "/team.html"; a.title = "Team and submission";
  a.innerHTML = '<i>Z</i><span>Team</span>';
  document.body.appendChild(a);
})();
