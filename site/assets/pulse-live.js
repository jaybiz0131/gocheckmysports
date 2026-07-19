/* pulse-live.js: the live layer for the Crypto Cronkite data desks.
 *
 * Progressive enhancement only: every value on the page is server-rendered at build time,
 * and this script refreshes the CURRENT numbers in the visitor's browser from the same
 * free, keyless APIs the build uses (CoinGecko, mempool.space). If anything fails, the
 * built values simply stand. Polling pauses while the tab is hidden.
 *
 * Conventions: elements opt in via data-live attributes.
 *   data-live="price:BTC"        text becomes (data-prefix +) formatted live price
 *   data-live="pill:BTC"         SVG chart pill text, live price
 *   data-live="chg:BTC"          24h change, signed and colored (+1.23% (24h))
 *   data-live="fee:fastest|hour" text becomes data-prefix + sats + data-suffix
 *   data-live="movers:gainers|losers"  tbody rebuilt with live top-5 rows
 *   data-live="top100"           tbody rows updated in place (price/24h/mcap), sortable
 *   data-live="stamp"            "updated HH:MM" after each successful fetch
 */
(function () {
  "use strict";
  var CG = "https://api.coingecko.com/api/v3";
  var IDS = { bitcoin: "BTC", ethereum: "ETH", solana: "SOL", ripple: "XRP" };

  function $all(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  if (!$all("[data-live]").length) return;

  // ---- formatters (mirror site_build.py) ----
  function fmtPrice(p) {
    if (!p && p !== 0) return "?";
    if (p >= 100) return "$" + Math.round(p).toLocaleString("en-US");
    if (p >= 1) return "$" + p.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return "$" + p.toFixed(6).replace(/0+$/, "").replace(/\.$/, "");
  }
  function fmtTick(n) {
    var a = Math.abs(n), s = n < 0 ? "-" : "";
    function g(x) { return parseFloat(x.toPrecision(4)).toString(); }
    if (a >= 1e12) return s + "$" + g(a / 1e12) + "T";
    if (a >= 1e9) return s + "$" + g(a / 1e9) + "B";
    if (a >= 1e6) return s + "$" + g(a / 1e6) + "M";
    if (a >= 1e3) return s + "$" + g(a / 1e3) + "K";
    return s + "$" + g(a);
  }
  function fmtUsd(n) {
    var a = Math.abs(n), s = n < 0 ? "-" : "";
    if (a >= 1e12) return s + "$" + (a / 1e12).toFixed(2) + "T";
    if (a >= 1e9) return s + "$" + (a / 1e9).toFixed(2) + "B";
    if (a >= 1e6) return s + "$" + (a / 1e6).toFixed(1) + "M";
    return s + "$" + Math.round(a).toLocaleString("en-US");
  }
  function esc(t) {
    var d = document.createElement("div"); d.textContent = t == null ? "" : String(t);
    return d.innerHTML;
  }

  function setText(el, value) {
    var next = (el.getAttribute("data-prefix") || "") + value + (el.getAttribute("data-suffix") || "");
    if (el.textContent !== next) {
      // flash on the market scale: green when the number went up, red when it went down
      var prev = parseFloat((el.textContent || "").replace(/[^0-9.eE-]/g, ""));
      var cur = parseFloat(String(value).replace(/[^0-9.eE-]/g, ""));
      var down = !isNaN(prev) && !isNaN(cur) && cur < prev;
      el.textContent = next;
      el.classList.remove("flash", "flash-dn");
      void el.offsetWidth; // restart the animation
      el.classList.add(down ? "flash-dn" : "flash");
      // fast number-roll on update (transform/opacity only; skipped for reduced motion)
      if (el.animate && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
        el.animate([{transform: "translateY(-6px)", opacity: 0.2},
                    {transform: "translateY(0)", opacity: 1}], {duration: 160, easing: "ease-out"});
      }
    }
  }

  function stamp() {
    var t = new Date();
    var hh = ("0" + t.getHours()).slice(-2), mm = ("0" + t.getMinutes()).slice(-2);
    $all('[data-live="stamp"]').forEach(function (el) {
      el.textContent = "· updated " + hh + ":" + mm;
    });
  }

  function getJSON(url, cb) {
    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) { cb(d); stamp(); })
      .catch(function () { /* silent: built values stand */ });
  }

  // ---- loop A: prices (60s) ----
  var priceEls = $all('[data-live^="price:"], [data-live^="pill:"], [data-live^="chg:"]');
  function pollPrices() {
    if (document.hidden || !priceEls.length) return;
    getJSON(CG + "/simple/price?ids=" + Object.keys(IDS).join(",") +
            "&vs_currencies=usd&include_24hr_change=true", function (d) {
      Object.keys(IDS).forEach(function (id) {
        var sym = IDS[id], p = d[id] && d[id].usd;
        if (p == null) return;
        $all('[data-live="price:' + sym + '"]').forEach(function (el) { setText(el, fmtPrice(p)); });
        $all('[data-live="pill:' + sym + '"]').forEach(function (el) { el.textContent = fmtPrice(p); });
        var c = d[id].usd_24h_change;
        if (c == null) return;
        $all('[data-live="chg:' + sym + '"]').forEach(function (el) {
          el.textContent = (c >= 0 ? "+" : "") + c.toFixed(2) + "% (24h)";
          el.className = "pc-chg " + (c >= 0 ? "up" : "down");
        });
      });
    });
  }

  // ---- loop B: top-100 markets (300s) -> movers tables + top100 table ----
  var gainersBody = document.querySelector('[data-live="movers:gainers"]');
  var losersBody = document.querySelector('[data-live="movers:losers"]');
  var top100Body = document.querySelector('[data-live="top100"]');

  function moverRow(c) {
    var chg = c.price_change_percentage_24h;
    var cls = chg >= 0 ? "chip-up" : "chip-down";
    return '<tr><td class="mut">#' + esc(c.market_cap_rank || "?") + "</td>" +
      '<td class="sym2">' + esc((c.symbol || "").toUpperCase()) +
      '<span class="mut"> · ' + esc((c.name || "").slice(0, 14)) + "</span></td>" +
      '<td class="pnum">' + esc(fmtPrice(c.current_price)) + "</td>" +
      '<td><span class="chip ' + cls + '">' + (chg >= 0 ? "+" : "") + chg.toFixed(1) + "%</span></td>" +
      '<td class="mut">' + esc(fmtUsd(c.market_cap || 0)) + " cap</td></tr>";
  }

  function pollMarkets() {
    if (document.hidden || (!gainersBody && !losersBody && !top100Body)) return;
    getJSON(CG + "/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1" +
            "&price_change_percentage=24h", function (d) {
      var rows = d.filter(function (c) { return c.price_change_percentage_24h != null; })
        .sort(function (a, b) { return a.price_change_percentage_24h - b.price_change_percentage_24h; });
      if (gainersBody) gainersBody.innerHTML = rows.slice(-5).reverse().map(moverRow).join("");
      if (losersBody) losersBody.innerHTML = rows.slice(0, 5).map(moverRow).join("");
      if (top100Body) {
        var bySym = {};
        d.forEach(function (c) { bySym[(c.symbol || "").toUpperCase()] = c; });
        $all('[data-live="top100"] tr').forEach(function (tr) {
          var c = bySym[tr.getAttribute("data-sym")];
          if (!c) return;
          var cells = {
            price: tr.querySelector('[data-cell="price"]'),
            chg: tr.querySelector('[data-cell="chg"]'),
            mcap: tr.querySelector('[data-cell="mcap"]'),
            rank: tr.querySelector('[data-cell="rank"]'),
          };
          if (cells.price) {
            cells.price.setAttribute("data-val", c.current_price || 0);
            setText(cells.price, fmtPrice(c.current_price));
          }
          var chg = c.price_change_percentage_24h;
          if (cells.chg && chg != null) {
            cells.chg.setAttribute("data-val", chg);
            cells.chg.innerHTML = '<span class="chip ' + (chg >= 0 ? "chip-up" : "chip-down") +
              '">' + (chg >= 0 ? "+" : "") + chg.toFixed(1) + "%</span>";
          }
          if (cells.mcap) {
            cells.mcap.setAttribute("data-val", c.market_cap || 0);
            cells.mcap.textContent = fmtUsd(c.market_cap || 0);
          }
          if (cells.rank) {
            cells.rank.setAttribute("data-val", c.market_cap_rank || 999);
            cells.rank.textContent = "#" + (c.market_cap_rank || "?");
          }
        });
        applySort(); // keep the user's chosen order after refresh
      }
    });
  }

  // ---- loop C: fees (60s) ----
  var feeEls = $all('[data-live^="fee:"]');
  function pollFees() {
    if (document.hidden || !feeEls.length) return;
    getJSON("https://mempool.space/api/v1/fees/recommended", function (d) {
      var map = { fastest: d.fastestFee, hour: d.hourFee };
      feeEls.forEach(function (el) {
        var k = el.getAttribute("data-live").split(":")[1];
        if (map[k] != null) setText(el, map[k]);
      });
    });
  }

  // ---- sortable top-100 table ----
  var sortKey = "rank", sortAsc = true;
  function applySort() {
    if (!top100Body) return;
    var rows = $all('[data-live="top100"] tr');
    rows.sort(function (a, b) {
      var av = parseFloat((a.querySelector('[data-cell="' + sortKey + '"]') || {}).getAttribute
        ? a.querySelector('[data-cell="' + sortKey + '"]').getAttribute("data-val") : 0) || 0;
      var bv = parseFloat((b.querySelector('[data-cell="' + sortKey + '"]') || {}).getAttribute
        ? b.querySelector('[data-cell="' + sortKey + '"]').getAttribute("data-val") : 0) || 0;
      return sortAsc ? av - bv : bv - av;
    });
    rows.forEach(function (r) { top100Body.appendChild(r); });
  }
  $all("th[data-sort]").forEach(function (th) {
    th.addEventListener("click", function () {
      var key = th.getAttribute("data-sort");
      if (sortKey === key) { sortAsc = !sortAsc; }
      else { sortKey = key; sortAsc = key === "rank"; }
      $all("th[data-sort]").forEach(function (t) { t.classList.remove("sorted-asc", "sorted-desc"); });
      th.classList.add(sortAsc ? "sorted-asc" : "sorted-desc");
      applySort();
    });
  });

  // ---- schedule ----
  pollPrices(); pollMarkets(); pollFees();
  setInterval(pollPrices, 60000);
  setInterval(pollMarkets, 300000);
  setInterval(pollFees, 60000);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) { pollPrices(); pollFees(); }
  });
})();
