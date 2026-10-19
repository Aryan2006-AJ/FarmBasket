/* FarmBasket behaviour. Runs only what the page needs. */
(function () {
  "use strict";

  // Confirm before destructive actions: <form data-confirm="Are you sure?">
  document.addEventListener("submit", function (event) {
    var message = event.target.getAttribute && event.target.getAttribute("data-confirm");
    if (message && !window.confirm(message)) {
      event.preventDefault();
    }
  });

  // Live notifications over WebSocket (only when logged in).
  var body = document.body;
  if (body.getAttribute("data-auth") === "1" && typeof window.io === "function") {
    var socket = window.io();
    var badge = document.getElementById("notif-count");
    var toast = document.getElementById("live-toast");
    var timer = null;
    socket.on("notification", function (data) {
      if (badge) {
        badge.textContent = String((parseInt(badge.textContent, 10) || 0) + 1);
        badge.hidden = false;
        badge.classList.remove("pop");
        void badge.offsetWidth; // restart the one-time pop
        badge.classList.add("pop");
      }
      if (toast) {
        toast.textContent = data.message;
        toast.hidden = false;
        window.clearTimeout(timer);
        timer = window.setTimeout(function () { toast.hidden = true; }, 6000);
      }
    });
  }

  // Search suggestions on the marketplace.
  var input = document.getElementById("search-input");
  var box = document.getElementById("search-suggestions");
  if (input && box) {
    var url = input.getAttribute("data-suggest-url");
    var base = input.getAttribute("data-search-url");
    var wait = null;
    input.addEventListener("input", function () {
      window.clearTimeout(wait);
      var q = input.value.trim();
      if (q.length < 2) { box.hidden = true; box.textContent = ""; return; }
      wait = window.setTimeout(function () {
        fetch(url + "?q=" + encodeURIComponent(q), { credentials: "same-origin" })
          .then(function (r) { return r.json(); })
          .then(function (items) {
            box.textContent = "";
            if (!items.length) { box.hidden = true; return; }
            items.forEach(function (item) {
              var a = document.createElement("a");
              a.href = base + "?q=" + encodeURIComponent(item.name);
              a.textContent = item.name + " (" + item.category + ")";
              box.appendChild(a);
            });
            box.hidden = false;
          });
      }, 200);
    });
    document.addEventListener("click", function (e) {
      if (e.target !== input && !box.contains(e.target)) { box.hidden = true; }
    });
  }

  // Coupon check on checkout.
  var couponButton = document.getElementById("check-coupon");
  if (couponButton) {
    couponButton.addEventListener("click", function () {
      var code = document.getElementById("coupon_code").value.trim();
      var out = document.getElementById("coupon-feedback");
      if (!code) { out.textContent = ""; return; }
      var data = new FormData();
      data.append("code", code);
      data.append("csrf_token", document.querySelector("input[name=csrf_token]").value);
      fetch(couponButton.getAttribute("data-url"), { method: "POST", body: data, credentials: "same-origin" })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          out.textContent = d.message;
          out.className = d.valid ? "help" : "error";
        });
    });
  }

  // Charts: <canvas data-chart="line|bar|doughnut" data-url="...">
  document.querySelectorAll("canvas[data-chart]").forEach(function (canvas) {
    if (typeof window.Chart !== "function") { return; }
    var kind = canvas.getAttribute("data-chart");
    var money = canvas.getAttribute("data-money") === "1";
    var palette = ["#1b5e3a", "#ae4a12", "#1f5fbf", "#d99a1e", "#5b4a8c", "#b42318"];
    var ink = "#ffffff";
    fetch(canvas.getAttribute("data-url"), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var dataset = { data: d.values, label: canvas.getAttribute("data-label") || "" };
        if (kind === "doughnut") {
          dataset.backgroundColor = palette; dataset.borderColor = ink; dataset.borderWidth = 2;
        } else if (kind === "line") {
          dataset.borderColor = "#1b5e3a"; dataset.backgroundColor = "#1b5e3a"; dataset.pointBorderColor = ink;
          dataset.pointRadius = 4; dataset.tension = 0; dataset.borderWidth = 3;
        } else {
          dataset.backgroundColor = palette; dataset.borderColor = ink; dataset.borderWidth = 2;
        }
        var options = {
          responsive: true, maintainAspectRatio: false, animation: { duration: 500 },
          plugins: { legend: { display: kind === "doughnut" } },
          scales: kind === "doughnut" ? {} : { y: { beginAtZero: true, ticks: { precision: money ? 2 : 0 } } },
        };
        if (canvas.getAttribute("data-horizontal") === "1") { options.indexAxis = "y"; }
        new window.Chart(canvas, { type: kind, data: { labels: d.labels, datasets: [dataset] }, options: options });
      });
  });
})();
