(function(){
var $ = function(s){ return document.querySelector(s) };
var $$ = function(s){ return document.querySelectorAll(s) };

function getCookie(name) {
  var cookieValue = null;
  if (document.cookie && document.cookie !== "") {
    var cookies = document.cookie.split(";");
    for (var i = 0; i < cookies.length; i++) {
      var cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + "=")) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}
var csrfToken = getCookie("csrftoken") || "";

function api(url, method, data) {
  var opts = {
    method: method || "GET",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken") || csrfToken
    }
  };
  if (data && (method === "POST" || method === "PUT")) {
    opts.body = JSON.stringify(data);
  }
  return fetch(url, opts).then(function(r){
    return r.json().then(function(j){
      if (!r.ok) throw new Error(j.error || "Server error " + r.status);
      return j;
    });
  });
}

function toast(msg, bad) {
  var t = document.createElement("div");
  t.className = "toast-msg" + (bad ? " err" : "");
  t.textContent = msg;
  var cont = $("#toast") || document.body;
  cont.appendChild(t);
  setTimeout(function(){
    t.style.opacity = "0";
    setTimeout(function(){ t.remove() }, 300);
  }, 3200);
}

function esc(s){ return String(s == null ? "" : s).replace(/[<>&"']/g, "") }
function enc(p, o){ return p + btoa(unescape(encodeURIComponent(JSON.stringify(o)))) }
function dec(p, s){
  s = s.trim();
  if (s.indexOf(p) !== 0) throw 0;
  return JSON.parse(decodeURIComponent(escape(atob(s.slice(p.length)))));
}
function hash(s){
  var h = 7;
  for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h;
}
function same(a, b){ return esc(a).trim().toLowerCase() === esc(b).trim().toLowerCase() }

function tile(n, hue){
  var h = (hue !== undefined && hue !== null) ? hue : (hash(n || "?") % 360);
  return "<div class='av' style='background:linear-gradient(150deg,hsl(" + h + ",70%,78%),hsl(" + ((h + 50) % 360) + ",75%,72%))'>" + ((n && n[0]) || "?").toLowerCase() + "</div>";
}

function copy(t, b){
  try {
    navigator.clipboard.writeText(t).then(function(){
      b.textContent = "copied";
      setTimeout(function(){ b.textContent = "copy code" }, 2500);
    }, function(){ b.textContent = "select the code and copy" });
  } catch(e) { b.textContent = "select the code and copy" }
}

function empty(h, p, b){
  return "<div class='card empty'><svg viewBox='0 0 200 120'><circle cx='72' cy='60' r='44'/><circle cx='128' cy='60' r='44'/></svg><h3>" + h + "</h3><p class='sm'>" + p + "</p>" + (b || "") + "</div>";
}

var KEYS = ["sleep", "wake", "smoke", "tidy", "noise", "study", "guests", "social"];
var RANGE = {sleep: 4, wake: 4, smoke: 3, tidy: 4, noise: 4, study: 4, guests: 4, social: 4};
var BASE = {sleep: 5, smoke: 5, tidy: 4, noise: 4, wake: 3, study: 3, guests: 3, social: 2};
var MUL = {1: .5, 2: 1, 3: 2};
var SH = {sleep: "Sleep", wake: "Morning", smoke: "Smoke", tidy: "Tidy", noise: "Noise", study: "Study", guests: "Guests", social: "Social"};
var NM = {sleep: "sleep", wake: "mornings", smoke: "smoking", tidy: "tidiness", noise: "noise", study: "study habits", guests: "guests", social: "recharging"};
var GOOD = {sleep: "wind down at a similar time", wake: "have similar mornings", smoke: "share a stance on smoking", tidy: "keep a similar level of tidy", noise: "want the same noise level", study: "study in similar places", guests: "feel the same about guests", social: "recharge in a similar way"};
var BAD = {sleep: "different sleep timing", wake: "different wake-up times", smoke: "different views on smoking", tidy: "different tidiness", noise: "different noise comfort", study: "different study habits", guests: "different guest habits", social: "different ways to recharge"};

var S = {
  me: null,
  pe: [],
  rq: [],
  stats: {sent: 0, received: 0, confirmed: 0}
};

var view = (location.hash || "#home").slice(1);
window.addEventListener("hashchange", function(){
  var v = (location.hash || "#home").slice(1);
  if (["home", "quiz", "matches", "requests"].indexOf(v) > -1 && v !== view) {
    view = v;
    draw();
  }
});

if (["home", "quiz", "matches", "requests"].indexOf(view) < 0) view = "home";

function go(v, a){
  view = v;
  try { history.replaceState(null, "", "#" + v) } catch(e){}
  draw(a);
  window.scrollTo(0, 0);
}

function P(r, t){ return (150 + r * Math.cos(t)).toFixed(1) + "," + (150 + r * Math.sin(t)).toFixed(1) }
function bloom(L){
  var s = "<div class='bw'><svg class='bl' viewBox='0 0 300 300' role='img' aria-label='Trait bloom chart'>";
  [28, 56, 84, 112].forEach(function(r){ s += "<circle class='gr' cx='150' cy='150' r='" + r + "'/>" });
  KEYS.forEach(function(k, i){
    var t = -Math.PI / 2 + i * Math.PI / 4, e = P(112, t).split(","), l = P(128, t).split(","), c = Math.cos(t);
    s += "<line class='ax' x1='150' y1='150' x2='" + e[0] + "' y2='" + e[1] + "'/><text class='lb' x='" + l[0] + "' y='" + (+l[1] + 4) + "' text-anchor='" + (c > .3 ? "start" : c < -.3 ? "end" : "middle") + "'>" + SH[k] + "</text>";
  });
  L.forEach(function(e, n){
    KEYS.forEach(function(k, i){
      var ans = (e && e.p && e.p.a && e.p.a[k] != null) ? e.p.a[k] : 2;
      var imp = (e && e.p && e.p.i && e.p.i[k] != null) ? e.p.i[k] : 2;
      var t = -Math.PI / 2 + i * Math.PI / 4, len = 112 * ans / RANGE[k];
      s += "<path class='pt " + e.c + "' style='--i:" + (i + n * 3) + ";stroke-width:" + (1 + (imp - 1) * 1.4) + "' d='M150,150Q" + P(len * .62, t - .42) + " " + P(len, t) + "Q" + P(len * .62, t + .42) + " 150,150Z'/>";
    });
  });
  return s + "</svg></div>";
}

function score(p){
  var me = S.me;
  if (!me || !me.a) return {v: 50, clash: [], good: [], bad: null};
  var tot = 0, ws = 0, sims = {}, clash = [];
  KEYS.forEach(function(k){
    var myAns = (me.a && me.a[k]) ? me.a[k] : 2;
    var peAns = (p && p.a && p.a[k]) ? p.a[k] : 2;
    var s = 1 - Math.abs(myAns - peAns) / (RANGE[k] - 1);
    var myImp = (me.i && me.i[k]) ? me.i[k] : 2;
    var w = BASE[k] * (MUL[myImp] || 1);
    tot += w * s;
    ws += w;
    sims[k] = s;
    if (myImp === 3 && s < .5) clash.push(k);
    if (p && p.i && p.i[k] === 3 && s < .5 && clash.indexOf(k) < 0) clash.push(k);
  });
  var v = Math.round(tot / ws * 100);
  if (clash.length) v = Math.min(v, 59);
  return {
    v: v,
    clash: clash,
    good: KEYS.filter(function(k){ return sims[k] >= .85 }).sort(function(a, b){ return BASE[b] - BASE[a] }).slice(0, 3),
    bad: KEYS.filter(function(k){ return sims[k] < .6 }).sort(function(a, b){ return BASE[b] * (1 - sims[b]) - BASE[a] * (1 - sims[a]) })[0]
  };
}

function myCode(){
  var m = S.me;
  if (!m) return "";
  return m.profile_code || enc("KP-", {n: m.n, p: m.p, a: m.a, i: m.i});
}

function reqOf(n){
  return S.rq.filter(function(x){ return same(x.peer, n) })[0];
}

/* HOME */
function home(){
  var m = S.me;
  var pr = S.rq.filter(function(x){ return x.status === "confirmed" || x.status === "accepted" }).length;
  var isPaired = !!(m && m.is_paired);
  var partnerName = (m && m.pairing) ? m.pairing.partner_name : "";

  var st = [
    ["Take the quiz", m && m.has_quiz ? "done as " + m.n + " (" + m.p + ")" : "Five minutes, made for you.", "quiz", !!(m && m.has_quiz)],
    ["Meet your matches", S.pe.length ? S.pe.length + " student" + (S.pe.length > 1 ? "s" : "") + " compared" : "Compare real profiles.", "matches", S.pe.length > 0],
    ["Send a request", S.rq.length ? S.rq.length + " request" + (S.rq.length > 1 ? "s" : "") : "Ask someone to pair.", "requests", S.rq.length > 0],
    ["Get paired", isPaired || pr ? "Pairing confirmed" : "Two yeses make a pair.", "requests", isPaired || pr > 0]
  ];
  var nx = st.findIndex(function(x){ return !x[3] });

  var pairBanner = "";
  if (isPaired && m.pairing) {
    pairBanner = "<div class='card' style='margin:20px 0 10px;border-color:var(--lv);background:linear-gradient(135deg,var(--surface),var(--sage));text-align:left'>" +
      "<div style='display:flex;align-items:center;gap:14px;flex-wrap:wrap'>" +
        "<div style='display:flex'>" + tile(m.n, m.avatar_hue) + tile(partnerName, m.pairing.partner_avatar_hue) + "</div>" +
        "<div><span class='chip g' style='font-size:11.5px;padding:3px 10px'>Verified Roommate Pair</span>" +
          "<h2 style='font-size:26px;margin:4px 0'>Paired with " + esc(partnerName) + " (" + esc(m.pairing.partner_roll || "") + ")</h2>" +
          "<p class='sm' style='margin:0'>" + (m.pairing.room ? "Allotted Room: <b>Room " + esc(m.pairing.room) + " (" + esc(m.pairing.block || "") + ")</b>" : "Awaiting Room Key Allocation by Warden") + "</p>" +
        "</div>" +
      "</div>" +
    "</div>";
  }

  return "<header class='hero'>" + (m ? "<span class='hand'>welcome back, " + m.n + " (" + (m.roll_no || "") + ") · " + (m.block || "Hostel") + "</span>" : "<span class='hand'>a hostel roommate matcher</span>") +
  "<h1><span class='ln'><span>find the roommate</span></span><span class='ln'><span>who fits your rhythm.</span></span></h1>" +
  "<p class='sub'>Answer a short quiz about how you live, compare with real classmates in your hostel block, and send a pairing request. When both say yes, the pair goes directly to the warden for room allotment.</p>" +
  pairBanner +
  "<div class='row'><button class='btn' data-go='" + (nx < 0 ? "matches" : st[nx][2]) + "'>" + (nx < 0 ? "see my matches" : st[nx][0].toLowerCase()) + "</button>" +
  (m && m.is_paired ? "<a href='/warden/' class='btn ok' style='text-decoration:none'>view room allotment ✓</a>" : "") +
  "</div>" +
  "<div class='card rh' id='rh'><svg viewBox='0 0 1000 240' preserveAspectRatio='none' aria-hidden='true'><path id='wa'/><path id='wb'/></svg><div id='cap'>out of step</div></div></header>" +
  "<div class='jy'>" + st.map(function(x, i){ return "<button class='stp s" + i + (x[3] ? " done" : "") + (i === nx ? " next" : "") + "' data-go='" + x[2] + "'><i>" + (x[3] ? "✓" : i + 1) + "</i><h3>" + x[0] + "</h3><span>" + x[1] + "</span></button>" }).join("") + "</div>";
}

var raf;
function waves(){
  var wa = $("#wa"), wb = $("#wb"), cap = $("#cap"), box = $("#rh");
  if (!wa) return;
  cancelAnimationFrame(raf);
  var last = "", still = matchMedia("(prefers-reduced-motion:reduce)").matches;
  function y(x, t, ph, am){
    var a = x * .011 - t * 1.1 + ph;
    return 120 + am * (Math.sin(a) + .35 * Math.sin(2 * a + 1)) / 1.35;
  }
  function f(ms){
    if (!$("#wa")) return;
    var t = still ? 4.5 : ms / 1000, d = Math.PI * (.5 + .5 * Math.cos(2 * Math.PI * t / 10)), A = "", B = "";
    for (var x = 0; x <= 1000; x += 5){
      var c = (x ? "L" : "M") + x + " ";
      A += c + y(x, t, 0, 82).toFixed(1) + " ";
      B += c + y(x, t, d, 70).toFixed(1) + " ";
    }
    wa.setAttribute("d", A);
    wb.setAttribute("d", B);
    var s = d > 2 ? "out of step" : d > .7 ? "finding each other" : "in rhythm";
    if (s !== last){
      last = s;
      cap.textContent = s;
      box.classList.toggle("sync", s === "in rhythm");
    }
    if (!still) raf = requestAnimationFrame(f);
  }
  raf = requestAnimationFrame(f);
}

/* QUIZ */
var Q = [
  {id: "sleep", c: 1, t: "When does your day usually end?", o: [["Before 10 pm", 1], ["Around 11 pm", 2], ["Past midnight", 3], ["2 am or later", 4]]},
  {id: "wake", c: 1, t: "And when do you usually wake up?", o: [["Before 6 am", 1], ["Between 6 and 8", 2], ["Between 8 and 10", 3], ["Late morning", 4]]},
  {id: "light", t: "When you are up late, you…", w: function(a){ return a && a.sleep >= 3 }, o: [["Use a small desk lamp", 1], ["Just a laptop glow", 2], ["Keep the main light on", 3], ["Step out of the room", 4]]},
  {id: "early", t: "If a roommate came in at 1 am, you would…", w: function(a){ return a && (a.sleep === 1 || a.wake === 1) }, o: [["Sleep right through it", 1], ["Wake up, but be fine", 2], ["Be genuinely upset", 3]]},
  {id: "smoke", c: 1, t: "Where do you stand on smoking?", o: [["Never, and I want a smoke-free room", 1], ["Occasionally, never indoors", 2], ["Regularly", 3]]},
  {id: "sb", t: "If a roommate smoked outside the room, you would feel…", w: function(a){ return a && a.smoke === 1 }, o: [["Fine with it", 1], ["Okay if the smell stays out", 2], ["Uncomfortable", 3]]},
  {id: "sl", t: "Where would you smoke?", w: function(a){ return a && a.smoke > 1 }, o: [["Only outside the hostel", 1], ["Balcony or stairs", 2], ["In the room", 3]]},
  {id: "tidy", c: 1, t: "Your side of the room usually looks…", o: [["Spotless", 4], ["Tidy, a few things out", 3], ["Lived-in", 2], ["A creative storm", 1]]},
  {id: "mess", t: "A roommate leaves cups and clothes lying around. You…", w: function(a){ return a && a.tidy >= 3 }, o: [["Quietly tidy up", 1], ["Mention it kindly", 2], ["Would find it hard", 3]]},
  {id: "rota", t: "Would you share a cleaning rota?", w: function(a){ return a && a.tidy <= 2 }, o: [["Yes, sounds fair", 1], ["Maybe, if flexible", 2], ["I would rather not", 3]]},
  {id: "noise", c: 1, t: "While you study or sleep, the room should be…", o: [["Completely silent", 1], ["A quiet hum", 2], ["Soft music is fine", 3], ["Noise does not bother me", 4]]},
  {id: "study", c: 1, t: "Where do you do your best work?", o: [["In the room at night", 1], ["In the room by day", 2], ["The library", 3], ["Anywhere at all", 4]]},
  {id: "guests", c: 1, t: "Friends visiting the room are…", o: [["Rare", 1], ["Now and then", 2], ["Often", 3], ["An open house", 4]]},
  {id: "over", t: "And overnight guests?", w: function(a){ return a && a.guests >= 3 }, o: [["Never", 1], ["With a heads-up", 2], ["Whenever", 3]]},
  {id: "social", c: 1, t: "After a long day you recharge by…", o: [["Being alone", 1], ["One close friend", 2], ["A big group", 3], ["It depends on the day", 4]]}
];
var POOL = [
  {id: "w1", t: "A roommate borrows your charger without asking. You…", o: [["Do not mind", 1], ["Mention it kindly", 2], ["Prefer they ask", 3]]},
  {id: "w2", t: "Exam week begins. You want the room to be…", o: [["A silent library", 1], ["Calm, soft music", 2], ["Normal life", 3]]},
  {id: "w3", t: "A roommate is homesick. You would…", o: [["Sit and talk", 1], ["Give them space", 2], ["Make some tea", 3]]},
  {id: "w4", t: "Sunday morning means…", o: [["Sleeping in", 1], ["Chai and chatting", 2], ["Out early", 3]]}
];
var Z = {A: {}, I: {}, idx: 0, scr: "intro", W: [], name: ""};
function shuf(a){ a = a.slice(); for (var i = a.length - 1; i > 0; i--){ var j = Math.floor(Math.random() * (i + 1)), t = a[i]; a[i] = a[j]; a[j] = t } return a }
function vis(){ return Q.concat(Z.W).filter(function(q){ return !q.w || (Z.A && q.w(Z.A)) }) }
function persona(a){
  if (!a) return "Roommate";
  var s = (a.sleep != null ? a.sleep : 2);
  var names = ["Dawn", "Daylight", "Moonlit", "Midnight"];
  var prefix = names[s - 1] || "Dawn";
  var suffix = (a.guests >= 3 ? "Host" : a.tidy === 4 ? "Curator" : a.noise === 1 ? "Sage" : a.study === 1 || a.study === 3 ? "Scholar" : a.tidy === 1 ? "Dreamer" : "Wanderer");
  return prefix + " " + suffix;
}

function quiz(){
  var m = S.me;
  if (Z.scr === "intro"){
    return "<span class='hand'>a short quiz, made for you</span><h1>let’s learn your rhythm.</h1><p class='sub'>The questions change depending on your answers, so no two people get quite the same quiz.</p>" +
    "<div class='card' style='margin:16px 0;border-style:dashed;padding:16px 20px'>" +
      "<p class='sm' style='margin:0 0 10px;color:var(--ink)'><b>Privacy & Consent (DPDP Act, 2023):</b> We only ask about lifestyle habits (sleep, noise, tidiness) to calculate roommate harmony. Your answers are stored securely and never shared with third parties.</p>" +
      "<label style='display:flex;align-items:center;gap:8px;font-size:13.5px;cursor:pointer'><input type='checkbox' id='dpdp-consent' checked> I agree to share my lifestyle preferences for hostel allotment matching.</label>" +
    "</div>" +
    "<input type='text' id='nm' maxlength='40' placeholder='your full name' aria-label='Your full name' value='" + esc(Z.name || (m && m.n) || "") + "'><div class='row'><button class='btn' data-q='start'>" + (m && m.has_quiz ? "retake the quiz" : "begin") + "</button>" + (m && m.has_quiz ? "<button class='btn gh' data-q='res'>view my results</button>" : "") + "</div>";
  }
  if (Z.scr === "res"){
    var a = (m && m.a) ? m.a : Z.A;
    var ch = "<span class='chip l'>the " + (m ? m.p : persona(a)) + "</span>";
    KEYS.forEach(function(k){ if (m && m.i && m.i[k] === 3) ch += "<span class='chip r'>deal-breaker: " + NM[k] + "</span>" });
    return "<span class='hand'>your rhythm, " + (m ? m.n : "friend") + "</span><h1>the " + (m ? m.p : persona(a)) + ".</h1><div class='card' style='margin-top:22px'>" + bloom([{p: m || {a: a, i: Z.I}, c: "fm"}]) + "<p class='sm' style='text-align:center'>Longer petals mean a higher answer. Thicker edges mean it matters more to you.</p></div><div class='chips'>" + ch + "</div><p class='sub' style='margin-top:18px'>Your profile is saved directly to the database. Now see who fits it.</p><div class='row'><button class='btn' data-go='matches'>see my matches</button><button class='btn gh' data-q='retake'>retake the quiz</button></div>";
  }
  var v = vis(), q = v[Z.idx], sel = Z.A[q.id], hi = ["alright, ", "nice, ", "good to know, ", "one more thing, ", "lovely, ", "almost there, "];
  var o = q.o.map(function(x, i){ return "<button class='op c" + (i % 4) + (sel === x[1] ? " on" : "") + "' data-v='" + x[1] + "'>" + x[0] + "</button>" }).join("");
  var imp = q.c && sel !== undefined ? "<div class='imp'><span class='hand' style='font-size:22px'>how much does this matter to you?</span>" + [["a little", 1], ["it matters", 2], ["deal-breaker", 3]].map(function(p){ return "<button class='pill" + ((Z.I[q.id] || 2) === p[1] ? " on" : "") + "' data-imp='" + p[1] + "'>" + p[0] + "</button>" }).join("") + "</div>" : "";
  return "<div class='prog'><i style='width:" + Math.round(Z.idx / (v.length + 1) * 100) + "%'></i></div><span class='hand'>" + hi[Z.idx % 6] + (Z.name || "friend") + " · question " + (Z.idx + 1) + " of about " + v.length + "</span><h2 style='margin-top:6px'>" + q.t + "</h2><div class='ops'>" + o + "</div>" + imp + "<div class='row'><button class='btn gh' data-q='back'>back</button>" + (q.c ? "<button class='btn' data-q='next'" + (sel === undefined ? " disabled" : "") + ">continue</button>" : "") + "</div>";
}

function finish(){
  var a = {}, i = {};
  KEYS.forEach(function(k){ a[k] = Z.A[k] || 2; i[k] = Z.I[k] || 2 });
  var name = Z.name || (S.me ? S.me.n : "Friend");

  api("/api/quiz/submit/", "POST", {
    name: name,
    answers: a,
    importance: i,
    context: Z.A
  }).then(function(res){
    toast("Quiz saved successfully!");
    refreshBackend(function(){
      Z.scr = "res";
      draw();
    });
  }).catch(function(err){
    toast(err.message, true);
    S.me = {n: name, p: persona(a), a: a, i: i, has_quiz: true};
    Z.scr = "res";
    draw();
  });
}

function qnext(){
  Z.idx++;
  if (Z.idx >= vis().length) finish();
  else draw();
}

/* MATCHES */
function lines(me, pe){
  var pen = (pe && pe.n) ? pe.n : "roommate";
  if (!pe || !pe.a || !Object.keys(pe.a).length) {
    return "<div class='sm' style='margin:10px 0;padding:12px 14px;border-radius:12px;background:var(--card);color:var(--soft);border:1px dashed var(--line);text-align:left'>" +
      "🔒 <b>Protected Under DPDP Act 2023:</b> Raw trait responses are never exposed publicly. Trait slider details unlock automatically after mutual pairing confirmation." +
    "</div>";
  }
  return "<div class='sm' style='margin-bottom:8px'>lavender is you, rose is " + esc(pen) + ". A bigger dot means it matters more to them.</div>" + KEYS.map(function(k){
    var myAns = (me && me.a && me.a[k] != null) ? me.a[k] : 2;
    var peAns = (pe && pe.a && pe.a[k] != null) ? pe.a[k] : 2;
    var myImp = (me && me.i && me.i[k] != null) ? me.i[k] : 2;
    var peImp = (pe && pe.i && pe.i[k] != null) ? pe.i[k] : 2;
    var r = RANGE[k] || 4;
    var x = ((myAns - 1) / (r - 1)) * 100;
    var y = ((peAns - 1) / (r - 1)) * 100;
    return "<div class='tl'><span>" + (SH[k] || k) + "</span><div class='tk'><i class='ln2' style='left:" + Math.min(x, y) + "%;width:" + Math.abs(x - y) + "%'></i><b class='dt a' style='left:" + x + "%;--s:" + (8 + myImp * 3) + "px'></b><b class='dt b' style='left:" + y + "%;--s:" + (8 + peImp * 3) + "px'></b></div></div>";
  }).join("");
}

function matches(){
  var me = S.me;
  var h = "<span class='hand'>built from real profiles, nothing made up</span><h1>your matches.</h1>";
  if (!me || !me.has_quiz) return h + empty("take the quiz first.", "Your matches are worked out from your own answers.", "<button class='btn' data-go='quiz'>take the quiz</button>");

  h += "<p class='sub'>Each student is scored on how closely your lifestyle lines up with theirs, weighted by both of your personal deal-breakers and priorities.</p>";

  if (!S.pe.length) return h + empty("no students added yet.", "Ask a classmate to take the quiz, or switch perspective in the top menu.");

  var rows = S.pe.map(function(p){
    var r = p.serverScore ? {v: p.serverScore, clash: p.clashes || [], good: p.good || [], bad: p.friction} : score(p);
    return {p: p, r: r};
  }).sort(function(a, b){ return b.r.v - a.r.v });

  return h + rows.map(function(x, i){
    var p = x.p, r = x.r, top = i === 0 && !r.clash.length && r.v >= 70, rq = reqOf(p.n);
    var ch = r.good.map(function(k){ return "<span class='chip g'>you " + (GOOD[k] || k) + "</span>" }).join("");
    if (r.bad && !r.clash.length) ch += "<span class='chip w'>" + (BAD[r.bad] || r.bad) + "</span>";
    r.clash.forEach(function(k){
      var label = NM[k] ? ("clashes on " + NM[k]) : k;
      ch += "<span class='chip r'>" + esc(label) + "</span>";
    });
    if (!ch) ch = "<span class='chip w'>few traits line up</span>";

    var bandBadge = (p.harmony_band && p.harmony_band.title) ? "<span class='chip " + (p.harmony_band.code === "HARMONY" ? "g" : p.harmony_band.code === "ADAPTATION" ? "w" : "r") + "' style='font-size:11px;margin-left:6px'>" + esc(p.harmony_band.title) + "</span>" : "";

    var b = "";
    if (p.request_status === "confirmed" || (rq && (rq.status === "confirmed" || rq.status === "accepted"))) {
      b = "<button class='btn ok' data-go='requests'>paired ✓</button>";
    } else if (p.request_status === "sent" || (rq && rq.status === "sent")) {
      b = "<button class='btn gh' data-go='requests'>request sent, view</button>";
    } else if (p.request_status === "pending" || (rq && rq.status === "pending")) {
      b = "<button class='btn' data-go='requests'>needs your answer!</button>";
    } else {
      b = "<button class='btn' data-s='" + p.id + "' data-name='" + esc(p.n) + "'>send request</button>";
    }

    return "<article class='card pc" + (top ? " top" : "") + "' style='--i:" + i + "'>" + (top ? "<span class='rib'>best match</span>" : "") + bloom([{p: p, c: "fp"}, {p: me, c: "fm"}]) +
    "<div><div class='tr'><div class='who'>" + tile(p.n, p.avatar_hue) + "<div><h3>" + p.n + bandBadge + "</h3><span class='hand' style='font-size:21px'>the " + p.p + "</span><div class='sm'>" + (p.roll_no || "") + " · " + (p.hostel || "Hostel") + " · " + (p.major || "Student") + "</div></div></div><div class='sc'>" + r.v + "<small>/100</small></div></div><div class='chips'>" + ch + "</div>" +
    (r.clash.length ? "<p class='err sm' style='font-weight:600;margin:10px 0 0'>This pairing breaks a deal-breaker you set.</p>" : "") +
    (p.bio ? "<p class='sm' style='margin:10px 0 0;font-style:italic'>“" + esc(p.bio) + "”</p>" : "") +
    "<div class='row'>" + b + "<button class='btn gh' data-t='1'>trait lines</button><button class='btn gh' data-d='" + p.id + "'>remove</button></div></div><div class='xp'>" + lines(me, p) + "</div></article>";
  }).join("");
}

/* REQUESTS */
var ST = {
  sent: "waiting for them",
  pending: "needs your answer",
  confirmed: "paired",
  accepted: "paired",
  declined: "declined",
  expired: "expired (48h)",
  cancelled: "cancelled"
};

function rcard(r, i){
  var inn = r.dir === "in", s, f, L = inn ? ["received", "your answer", "paired"] : ["asked", "answered", "paired"];
  var isConfirmed = (r.status === "confirmed" || r.status === "accepted");
  if (isConfirmed){ s = ["done", "done", "done"]; f = 1 }
  else if (r.status === "declined" || r.status === "cancelled"){ s = ["done", "no", "off"]; f = .5 }
  else if (r.status === "expired"){ s = ["done", "no", "off"]; f = .5 }
  else { s = ["done", "act", "off"]; f = 0 }

  var mkc = {done: "✓", no: "✕", act: "", off: ""}, b = "";
  if (isConfirmed) {
    b += "<div class='pair'><div class='pv'>" + tile(S.me.n, S.me.avatar_hue) + tile(r.peer, r.peer_avatar_hue) + "</div><div><b>You and " + esc(r.peer) + " both said yes!</b><br><span class='sm' style='color:inherit;opacity:.85'>Ready for the warden to allot your hostel room together.</span></div></div>";
  }
  if (r.status === "sent"){
    b += "<p class='sm' style='margin:14px 0 0'>Waiting for " + esc(r.peer) + " to answer online. Request is active for 48 hours.</p><div class='row'><button class='btn gh' data-cancel='" + r.id + "'>cancel request</button></div>";
  }
  if (r.status === "pending"){
    b += "<div class='row'><button class='btn' data-a='" + r.id + "'>accept</button><button class='btn gh' data-x='" + r.id + "'>decline</button></div>";
  }
  if (!inn && r.status === "declined") {
    b += "<p class='sm' style='margin:14px 0 0'>" + esc(r.peer) + " chose not to pair this time. You can ask someone else.</p>";
  }
  if (r.status === "expired") {
    b += "<p class='sm' style='margin:14px 0 0'>This request expired after 48 hours without a response.</p>";
  }

  return "<article class='card rq " + r.status + "' style='--i:" + i + "'><div class='hd'><div class='who'>" + tile(r.peer, r.peer_avatar_hue) + "<div><h3>" + esc(r.peer) + "</h3><span class='sm'>" + (inn ? "asked you" : "you asked") + " on " + new Date(r.ts).toLocaleDateString(undefined, {day: "numeric", month: "short"}) + (r.score ? ", " + r.score + "/100 match" : "") + "</span></div></div><span class='st " + r.status + "'>" + (ST[r.status] || r.status) + "</span></div>" +
  (r.note ? "<p class='nt'>“" + esc(r.note) + "”</p>" : "") + "<div class='jr' style='--f:" + f + "'>" + L.map(function(l, j){ return "<div class='nd " + s[j] + "'><i>" + mkc[s[j]] + "</i><span>" + l + "</span></div>" }).join("") + "</div>" + b + "<div class='row'><button class='btn gh' data-rm='" + r.id + "'>remove</button></div></article>";
}

function requests(){
  var h = "<span class='hand'>two yeses make a pair</span><h1>your requests.</h1>";
  if (!S.me || !S.me.has_quiz) return h + empty("take the quiz first.", "Requests are sent under your name, which comes from the quiz.", "<button class='btn' data-go='quiz'>take the quiz</button>");

  var confirmedCount = S.rq.filter(function(x){ return x.status === "confirmed" || x.status === "accepted" }).length;
  var sentCount = S.rq.filter(function(x){ return x.dir === "out" && x.status === "sent" }).length;
  var receivedCount = S.rq.filter(function(x){ return x.dir === "in" && x.status === "pending" }).length;

  var pairBanner = "";
  if (S.me.is_paired && S.me.pairing) {
    var p = S.me.pairing;
    pairBanner = "<div class='card' style='margin:18px 0;border-color:var(--lv);background:linear-gradient(135deg,var(--surface),var(--sage))'>" +
      "<span class='chip g' style='font-size:12px'>Officially Paired</span>" +
      "<h2 style='font-size:26px;margin:6px 0'>Paired with " + esc(p.partner_name) + " (" + esc(p.partner_roll || "") + ")</h2>" +
      "<p class='sm'>" + (p.room ? "Allotted Room: <b>Room " + esc(p.room) + " (" + esc(p.block || "") + ")</b>" : "Awaiting Room Key Allotment by Warden in Portal") + "</p>" +
    "</div>";
  }

  h += pairBanner;
  h += "<p class='sub'>When two students both say yes, their mutual pair is confirmed and queued for the hostel warden to assign a room.</p>";
  h += "<div class='stats'>" + [["received", receivedCount], ["sent", sentCount], ["paired", confirmedCount || (S.me.is_paired ? 1 : 0)]].map(function(x){ return "<div class='card stat'><b>" + x[1] + "</b><span>" + x[0] + "</span></div>" }).join("") + "</div>";
  h += "<div class='g2'><div class='card'><h3>send a request</h3><input type='text' id='pn' maxlength='60' placeholder='classmate name or registration number (e.g. 12310266)' aria-label='Their name or registration number'><input type='text' id='pm' maxlength='150' placeholder='a short note (optional)' aria-label='Note'><button class='btn' data-mk='1'>create request</button></div><div class='card'><h3>paste an exchange code</h3><textarea id='cd' placeholder='a request (KR-) or reply code from another student' aria-label='Code'></textarea><button class='btn' data-rd='1'>read code</button></div></div><div class='msg' id='msg' role='status'></div>";

  var l = S.rq.slice().sort(function(a, b){ return b.ts - a.ts });
  return h + (l.length ? l.map(rcard).join("") : empty("no requests yet.", "Create one above, or send one from your matches!"));
}

function draw(a){
  $$(".nl button").forEach(function(b){ b.classList.toggle("on", b.dataset.go === view) });
  cancelAnimationFrame(raf);
  $("#app").innerHTML = "<div class='" + (a === false ? "" : "swap") + "'>" + ({home: home, quiz: quiz, matches: matches, requests: requests})[view]() + "</div>";
  if (view === "home") waves();
}

function find(id){ return S.rq.filter(function(x){ return x.id == id })[0] }

function refreshBackend(cb){
  api("/api/me/").then(function(me){
    S.me = {
      id: me.id,
      n: me.name,
      p: me.persona,
      roll_no: me.roll_no,
      email: me.email,
      gender: me.gender,
      gender_code: me.gender_code,
      phone: me.phone,
      year: me.year,
      major: me.branch,
      block: me.block,
      block_id: me.block_id,
      avatar_hue: me.avatar_hue,
      has_quiz: me.has_quiz,
      a: me.answers,
      i: me.importance,
      profile_code: me.profile_code,
      is_paired: me.is_paired,
      pairing: me.pairing
    };
    S.all_blocks = me.all_blocks || [];

    var navName = $("#nav-user-name");
    if (navName) navName.textContent = me.name;

    var pName = $("#profile-display-name");
    if (pName) pName.textContent = me.name;
    var pRoll = $("#profile-display-roll");
    if (pRoll) pRoll.textContent = me.roll_no;
    var pMeta = $("#profile-display-meta");
    if (pMeta) pMeta.textContent = me.branch + " · " + me.year;
    var pHostel = $("#profile-display-hostel");
    if (pHostel) pHostel.textContent = me.block;
    var pPersona = $("#profile-display-persona");
    if (pPersona) pPersona.textContent = "Persona: " + me.persona;
    var pGen = $("#profile-display-gender");
    if (pGen) pGen.textContent = me.gender;

    if (Z.scr === "intro" && me.has_quiz){
      Z.name = me.name;
      Z.A = Object.assign({}, me.answers);
      Z.I = Object.assign({}, me.importance);
    }
    return Promise.all([api("/api/matches/"), api("/api/requests/"), api("/api/students/")]);
  }).then(function(res){
    var serverMatches = (res[0] && res[0].matches) || [];
    var serverRequests = (res[1] && res[1].requests) || [];
    var studentList = (res[2] && res[2].students) || [];

    var listContainer = $("#student-list-container");
    if (listContainer && studentList.length) {
      listContainer.innerHTML = studentList.map(function(st){
        var isCurr = st.is_current;
        return "<button type='button' class='dropdown-item" + (isCurr ? " active" : "") + "' data-switch-student='" + st.id + "'>" +
          "<div><b>" + esc(st.name) + "</b><div class='dropdown-item-meta'>" + esc(st.roll_no) + " · " + esc(st.block) + (st.is_paired ? " · paired ✓" : "") + "</div></div>" +
          (isCurr ? "<span style='font-size:12px;color:var(--lv);font-weight:600'>Active</span>" : "") +
        "</button>";
      }).join("");
    }

    S.pe = serverMatches.map(function(m){
      return {
        id: m.id,
        n: m.name,
        p: m.persona,
        roll_no: m.roll_no,
        hostel: m.block,
        major: m.branch,
        avatar_hue: m.avatar_hue,
        a: m.peer_answers || {},
        i: m.peer_importance || {},
        serverScore: m.score,
        harmony_band: m.harmony_band,
        clashes: m.clashes || [],
        good: m.good || [],
        friction: m.friction,
        request_status: m.request_status,
        request_id: m.request_id
      };
    });

    S.rq = serverRequests.map(function(r){
      return {
        id: r.id,
        dir: r.dir,
        peer: r.peer,
        peer_roll: r.peer_roll,
        peer_avatar_hue: r.peer_avatar_hue,
        note: r.note,
        status: r.status,
        score: r.score,
        ts: r.ts,
        expires_at: r.expires_at,
        is_expired: r.is_expired
      };
    });

    if (cb) cb();
    else draw();
  }).catch(function(err){
    console.error("Backend sync notice:", err);
    if (cb) cb();
    else draw();
  });
}

// Global click delegation
document.addEventListener("click", function(e){
  var b = e.target.closest("button");
  if (!b) return;
  var d = b.dataset;

  if (d.switch){
    api("/api/students/switch/", "POST", {student_id: d.switch}).then(function(res){
      toast("Switched to " + res.name);
      var drop = $("#user-dropdown");
      if (drop) drop.classList.remove("open");
      refreshBackend(function(){
        Z.scr = "intro";
        draw();
      });
    }).catch(function(err){ toast(err.message, true) });
    return;
  }

  if (d.go) go(d.go);
  else if (d.q === "start"){
    Z.name = esc($("#nm").value).trim() || (S.me ? S.me.n : "Friend");
    Z.A = {}; Z.I = {}; Z.idx = 0; Z.W = shuf(POOL).slice(0, 2); Z.scr = "q";
    draw();
  }
  else if (d.q === "next") qnext();
  else if (d.q === "back"){
    if (Z.idx > 0){ Z.idx--; draw() }
    else { Z.scr = "intro"; draw() }
  }
  else if (d.q === "res"){ Z.scr = "res"; draw() }
  else if (d.q === "retake"){ Z.scr = "intro"; draw() }
  else if (d.imp){
    Z.I[vis()[Z.idx].id] = +d.imp;
    draw(false);
  }
  else if (d.v !== undefined){
    var q = vis()[Z.idx];
    Z.A[q.id] = +d.v;
    if (q.c){
      if (!Z.I[q.id]) Z.I[q.id] = 2;
      draw(false);
    } else setTimeout(qnext, 250);
  }
  else if (d.cp) copy(myCode(), b);
  else if (d.add){
    var val = $("#pe").value.trim();
    if (!val) return toast("Paste a profile code first", true);
    api("/api/code/process/", "POST", {code: val}).then(function(res){
      toast(res.message);
      refreshBackend();
    }).catch(function(err){ toast(err.message, true) });
  }
  else if (d.s){
    var targetId = d.s;
    api("/api/requests/send/", "POST", {receiver_id: targetId, note: "I noticed our lifestyle rhythms match well!"}).then(function(res){
      toast(res.message);
      refreshBackend(function(){ go("requests") });
    }).catch(function(err){ toast(err.message, true) });
  }
  else if (d.t){
    b.closest(".pc").classList.toggle("open");
  }
  else if (d.d){
    S.pe = S.pe.filter(function(x){ return x.id != d.d });
    draw(false);
  }
  else if (d.mk){
    var pn = esc($("#pn").value).trim(), pm = esc($("#pm").value).trim();
    if (!pn) return toast("Enter classmate name or registration number", true);
    if (same(pn, S.me.n) || same(pn, S.me.roll_no)) return toast("That is your own identity", true);
    api("/api/requests/send/", "POST", {peer_name: pn, note: pm}).then(function(res){
      toast(res.message);
      refreshBackend();
    }).catch(function(err){ toast(err.message, true) });
  }
  else if (d.rd){
    var cval = $("#cd").value.trim();
    if (!cval) return toast("Paste an exchange code first", true);
    api("/api/code/process/", "POST", {code: cval}).then(function(res){
      toast(res.message);
      refreshBackend();
    }).catch(function(err){ toast(err.message, true) });
  }
  else if (d.a){
    api("/api/requests/" + d.a + "/respond/", "POST", {action: "accept"}).then(function(res){
      toast(res.message);
      refreshBackend();
    }).catch(function(err){ toast(err.message, true) });
  }
  else if (d.x){
    api("/api/requests/" + d.x + "/respond/", "POST", {action: "decline"}).then(function(res){
      toast(res.message);
      refreshBackend();
    }).catch(function(err){ toast(err.message, true) });
  }
  else if (d.cancel){
    api("/api/requests/" + d.cancel + "/cancel/", "POST", {}).then(function(res){
      toast(res.message || "Request cancelled");
      refreshBackend();
    }).catch(function(err){ toast(err.message, true) });
  }
  else if (d.rm){
    S.rq = S.rq.filter(function(x){ return x.id != d.rm });
    draw(false);
  }
});

// Profile Edit Modal Controls
function openProfileModal(){
  var userDropdown = $("#user-dropdown");
  if (userDropdown) userDropdown.classList.remove("open");
  var userMenuWrapper = $("#user-menu-wrapper");
  if (userMenuWrapper) userMenuWrapper.classList.remove("open");

  if (S.me) {
    var nIn = $("#edit-name"); if (nIn) nIn.value = S.me.n || "";
    var rIn = $("#edit-roll"); if (rIn) rIn.value = S.me.roll_no || "";
    var gIn = $("#edit-gender"); if (gIn && S.me.gender_code) gIn.value = S.me.gender_code;
    var yIn = $("#edit-year"); if (yIn && S.me.year) yIn.value = S.me.year;
    var bIn = $("#edit-branch"); if (bIn && S.me.major) bIn.value = S.me.major;
    var kIn = $("#edit-block"); if (kIn && S.me.block_id) kIn.value = S.me.block_id;
    var eIn = $("#edit-email"); if (eIn) eIn.value = S.me.email || "";
    var pIn = $("#edit-phone"); if (pIn) pIn.value = S.me.phone || "";
  }
  var msg = $("#profile-edit-msg");
  if (msg) { msg.textContent = ""; msg.className = ""; }
  var modal = $("#profile-edit-modal");
  if (modal) modal.classList.add("open");
}

function closeProfileModal(){
  var modal = $("#profile-edit-modal");
  if (modal) modal.classList.remove("open");
}

function saveProfileDetails(){
  var nameEl = $("#edit-name");
  var rollEl = $("#edit-roll");
  var genderEl = $("#edit-gender");
  var yearEl = $("#edit-year");
  var branchEl = $("#edit-branch");
  var blockEl = $("#edit-block");
  var emailEl = $("#edit-email");
  var phoneEl = $("#edit-phone");
  var msgEl = $("#profile-edit-msg");
  var saveBtn = $("#save-profile-btn");

  var name = nameEl ? nameEl.value.trim() : "";
  var roll = rollEl ? rollEl.value.trim() : "";
  var gender = genderEl ? genderEl.value : "M";
  var year = yearEl ? yearEl.value : "1st Year";
  var branch = branchEl ? branchEl.value.trim() : "";
  var block_id = blockEl ? blockEl.value : null;
  var email = emailEl ? emailEl.value.trim() : "";
  var phone = phoneEl ? phoneEl.value.trim() : "";

  if (!name) {
    if (msgEl) { msgEl.textContent = "Please enter your full name."; msgEl.className = "err"; }
    if (nameEl) nameEl.focus();
    return;
  }
  if (!roll) {
    if (msgEl) { msgEl.textContent = "Please enter your university registration number."; msgEl.className = "err"; }
    if (rollEl) rollEl.focus();
    return;
  }

  if (saveBtn) {
    saveBtn.disabled = true;
    saveBtn.textContent = "Saving...";
  }
  if (msgEl) {
    msgEl.textContent = "Saving to database in real time...";
    msgEl.className = "";
  }

  api("/api/profile/update/", "POST", {
    name: name,
    roll_no: roll,
    gender: gender,
    year: year,
    branch: branch,
    block_id: block_id,
    email: email,
    phone: phone
  }).then(function(res){
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.textContent = "Save Changes";
    }
    closeProfileModal();
    toast(res.message || "Profile updated successfully!");

    var u = res.user;
    if (u) {
      if (S.me) {
        S.me.n = u.name;
        S.me.roll_no = u.roll_no;
        S.me.gender = u.gender;
        S.me.gender_code = u.gender_code;
        S.me.year = u.year;
        S.me.major = u.branch;
        S.me.block = u.block;
        S.me.block_id = u.block_id;
        S.me.email = u.email;
        S.me.phone = u.phone;
      }
      var navName = $("#nav-user-name");
      if (navName) navName.textContent = u.name;

      var pName = $("#profile-display-name");
      if (pName) pName.textContent = u.name;
      var pRoll = $("#profile-display-roll");
      if (pRoll) pRoll.textContent = u.roll_no;
      var pMeta = $("#profile-display-meta");
      if (pMeta) pMeta.textContent = u.branch + " · " + u.year;
      var pHostel = $("#profile-display-hostel");
      if (pHostel) pHostel.textContent = u.block;
      var pGen = $("#profile-display-gender");
      if (pGen) pGen.textContent = u.gender;
    }

    refreshBackend(function(){
      draw();
    });
  }).catch(function(err){
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.textContent = "Save Changes";
    }
    if (msgEl) {
      msgEl.textContent = err.message || "Failed to update profile";
      msgEl.className = "err";
    }
  });
}

// User menu dropdown toggle, modal controls, and student perspective switch
document.addEventListener("click", function(e){
  if (e.target.closest("#open-edit-profile-btn")) {
    openProfileModal();
    return;
  }
  if (e.target.closest("#close-profile-modal-btn") || e.target.closest("#cancel-profile-modal-btn") || e.target.id === "profile-edit-modal") {
    closeProfileModal();
    return;
  }
  if (e.target.closest("#save-profile-btn")) {
    saveProfileDetails();
    return;
  }

  var switchBtn = e.target.closest("[data-switch-student]");
  if (switchBtn) {
    var stId = switchBtn.dataset.switchStudent;
    api("/api/switch-student/", "POST", {student_id: stId}).then(function(res){
      toast("Switched perspective to " + res.name);
      var userDropdown = $("#user-dropdown");
      if (userDropdown) userDropdown.classList.remove("open");
      var userMenuWrapper = $("#user-menu-wrapper");
      if (userMenuWrapper) userMenuWrapper.classList.remove("open");
      refreshBackend(function(){
        draw();
      });
    }).catch(function(err){
      toast(err.message, true);
    });
    return;
  }
  var userMenuBtn = e.target.closest("#user-menu-btn");
  var userDropdown = $("#user-dropdown");
  var userMenuWrapper = $("#user-menu-wrapper");
  if (userMenuBtn && userDropdown) {
    userDropdown.classList.toggle("open");
    if (userMenuWrapper) userMenuWrapper.classList.toggle("open");
  } else if (userDropdown && !e.target.closest("#user-dropdown")) {
    userDropdown.classList.remove("open");
    if (userMenuWrapper) userMenuWrapper.classList.remove("open");
  }
});

document.addEventListener("keydown", function(e){
  if (e.key === "Escape") closeProfileModal();
  if (e.key === "Enter" && e.target.closest("#profile-edit-form") && e.target.tagName !== "TEXTAREA") {
    e.preventDefault();
    saveProfileDetails();
  }
});

refreshBackend();
})();
