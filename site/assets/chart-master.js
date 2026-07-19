/* chart-master.js: the Chart Master's games. All client-side, all for fun, never advice.
 *
 * The Oracle Challenge: call BTC higher or lower by ~this time tomorrow. The record lives
 * in localStorage; the point of the game IS the lesson (prediction is hard; the record
 * proves it). Prices from CoinGecko's keyless API, fetched by the visitor's own browser.
 *
 * The Wizard's Exam: eight questions drawn from the desks' 101 sections. Score, rank,
 * share line. Pure DOM, no network.
 */
(function () {
  "use strict";
  var PRICE_URL = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd";
  var KEY = "cc_oracle_v1";
  var RESOLVE_AFTER = 20 * 3600 * 1000; // resolvable after ~20h, "by this time tomorrow"

  function $(id) { return document.getElementById(id); }
  function fmt(p) { return "$" + Math.round(p).toLocaleString("en-US"); }
  function load() { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; } }
  function save(s) { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) {} }

  // ---- The Oracle Challenge ----
  var status = $("oracle-status"), record = $("oracle-record"), buttons = $("oracle-buttons");
  function showRecord(s) {
    var w = s.wins || 0, l = s.losses || 0, n = w + l;
    if (!record) return;
    if (!n) { record.textContent = "No calls on the books yet."; return; }
    var pct = Math.round(100 * w / n);
    record.textContent = "Your record: " + w + " right, " + l + " wrong (" + pct + "%). " +
      (pct > 60 ? "Suspiciously good. The Master is watching."
        : pct < 40 ? "The Master admires the confidence."
        : "Right around a coin flip, which is rather the point.");
  }
  function setButtons(disabled) {
    if (!buttons) return;
    Array.prototype.forEach.call(buttons.querySelectorAll("button"), function (b) {
      b.disabled = disabled;
    });
  }
  function oracle() {
    if (!status) return;
    var s = load();
    fetch(PRICE_URL).then(function (r) { return r.json(); }).then(function (d) {
      var price = d.bitcoin && d.bitcoin.usd;
      if (!price) throw new Error("no price");
      // resolve a due call
      if (s.pending && Date.now() - s.pending.ts >= RESOLVE_AFTER) {
        var won = s.pending.guess === "up" ? price > s.pending.price : price < s.pending.price;
        s[won ? "wins" : "losses"] = (s[won ? "wins" : "losses"] || 0) + 1;
        var verdict = "Your last call: BTC " + (s.pending.guess === "up" ? "higher" : "lower") +
          " from " + fmt(s.pending.price) + ". It is now " + fmt(price) + ". " +
          (won ? "The Oracle smiles: correct." : "The tape disagreed: wrong.");
        s.pending = null; s.lastVerdict = verdict;
        save(s);
      }
      if (s.pending) {
        var hrs = Math.max(0, Math.ceil((RESOLVE_AFTER - (Date.now() - s.pending.ts)) / 3600000));
        status.textContent = "Call on the books: BTC " + (s.pending.guess === "up" ? "higher" : "lower") +
          " from " + fmt(s.pending.price) + ". Verdict in about " + hrs + "h. BTC now: " + fmt(price) + ".";
        setButtons(true);
      } else {
        status.textContent = (s.lastVerdict ? s.lastVerdict + " " : "") +
          "BTC is " + fmt(price) + " right now. Make your call.";
        setButtons(false);
        if (buttons) buttons.onclick = function (e) {
          var g = e.target && e.target.getAttribute("data-guess");
          if (!g) return;
          s.pending = { guess: g, price: price, ts: Date.now() };
          s.lastVerdict = null;
          save(s);
          oracle();
        };
      }
      showRecord(s);
    }).catch(function () {
      status.textContent = "The tape is unreachable at the moment. The Oracle rests.";
      setButtons(true);
      showRecord(s);
    });
  }

  // ---- The Wizard's Exam ----
  var QUESTIONS = [
    { q: "To sell a large amount of crypto, a whale usually first has to...",
      a: ["Move coins onto an exchange", "Move coins into cold storage", "Burn the coins"], c: 0,
      why: "Coins must usually sit on an exchange to be sold at scale, which is why big inflows can precede selling." },
    { q: "Stablecoins flooding ONTO exchanges historically reads as...",
      a: ["Sell pressure building", "Buying power arriving", "A network outage"], c: 1,
      why: "Stablecoins are staged dollars: arriving on an exchange, they are ready to buy, not to sell." },
    { q: "An RSI above 70 means the asset is running...",
      a: ["Cold (oversold)", "Hot (overbought)", "Exactly at fair value"], c: 1,
      why: "Above 70 reads as overbought (hot); below 30 as oversold (cold)." },
    { q: "A golden cross is when...",
      a: ["Price crosses $50,000", "The 50-day average crosses ABOVE the 200-day",
          "Two candles form an X"], c: 1,
      why: "The 50-day crossing above the 200-day is the golden cross; crossing below is the death cross." },
    { q: "Extreme fear on the sentiment gauge has historically appeared near...",
      a: ["Local tops", "Local bottoms", "Exchange listings"], c: 1,
      why: "Crowds overreact; extreme fear has often marked local bottoms. A tendency, never a law." },
    { q: "A 20% pump on a coin with no news behind it is usually...",
      a: ["Free money", "Noise, or someone's exit", "A sign of strong fundamentals"], c: 1,
      why: "A move with no story behind it is usually thin liquidity or someone selling into the pump." },
    { q: "Market cap equals...",
      a: ["Price times circulating supply", "Price times trading volume",
          "Whatever the founder says"], c: 0,
      why: "Price times circulating supply is the only fair way to compare a big coin to a cheap one." },
    { q: "Falling mining difficulty means...",
      a: ["More machines are joining", "Some miners are switching off", "Fees must rise"], c: 1,
      why: "Difficulty falls when machines leave the network and rises when miners plug more in." },
  ];
  var RANKS = [
    [8, "Chart Master", "The wizard tips his hat. The tower is yours."],
    [7, "Wizard's Apprentice", "One rune short of mastery."],
    [5, "Journeyman of the Tape", "Solid reading. The runes are coming into focus."],
    [3, "Apprentice", "The 101 sections await you."],
    [0, "Exit Liquidity", "Please, for your own sake, read the Spellbook."],
  ];
  function exam() {
    var body = $("exam-body"), start = $("exam-start");
    if (!body || !start) return;
    start.onclick = function () {
      var i = 0, score = 0, missed = [];
      function ask() {
        if (i >= QUESTIONS.length) { return grade(); }
        var q = QUESTIONS[i];
        var html = '<p style="margin:0 0 10px"><b>Question ' + (i + 1) + " of " +
          QUESTIONS.length + '.</b> ' + q.q + "</p>" + '<div class="pc-chips">';
        q.a.forEach(function (opt, j) {
          html += '<button class="cm-btn" data-j="' + j + '">' + opt + "</button>";
        });
        body.innerHTML = html + "</div>";
        body.onclick = function (e) {
          var j = e.target && e.target.getAttribute("data-j");
          if (j == null) return;
          if (parseInt(j, 10) === q.c) { score++; }
          else { missed.push({ q: q.q, chose: q.a[parseInt(j, 10)], right: q.a[q.c], why: q.why || "" }); }
          i++; ask();
        };
      }
      function grade() {
        var r = RANKS.find(function (x) { return score >= x[0]; });
        var share = "I ranked " + r[1] + " (" + score + "/8) on the Chart Master's Exam at gocheckmycrypto.com";
        var card = '<div class="exam-result">' +
          '<span class="lab">The Master\'s verdict</span>' +
          '<div class="exam-rank">' + r[1] + "</div>" +
          '<div class="exam-score">' + score + ' / 8</div>' +
          '<p class="pc-note" style="margin:4px 0 0">' + r[2] + "</p></div>";
        var review = missed.length
          ? '<div class="exam-review"><p style="margin:14px 0 8px"><b>The lessons:</b></p>' +
            missed.map(function (m) {
              return '<div class="miss"><span class="miss-q">' + m.q + "</span>" +
                '<span class="miss-you">&#10007; You said: ' + m.chose + "</span>" +
                '<span class="miss-ans">&#10003; The tape says: ' + m.right + "</span>" +
                '<span class="miss-why">' + m.why + "</span></div>";
            }).join("") + "</div>"
          : '<p class="pc-note" style="margin:14px 0 8px">A perfect reading. The Master has nothing to teach you today.</p>';
        body.innerHTML = card + review +
          '<div class="pc-chips" style="margin-top:12px"><button class="cm-btn" id="exam-share">Copy your result</button>' +
          '<button class="cm-btn" id="exam-again">Take it again</button></div>' +
          '<p class="pc-note" id="exam-note"></p>';
        $("exam-share").onclick = function () {
          (navigator.clipboard ? navigator.clipboard.writeText(share) : Promise.reject())
            .then(function () { $("exam-note").textContent = "Copied. Go forth and boast."; })
            .catch(function () { $("exam-note").textContent = share; });
        };
        $("exam-again").onclick = function () { start.onclick(); };
      }
      ask();
    };
  }

  oracle();
  exam();
})();
