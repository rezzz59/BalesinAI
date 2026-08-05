/* Balesin.ai — shared shell, nav, footer, reveal, demo widget, auth placeholder */
(function () {
  "use strict";

  var LOGO_SVG =
    '<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">' +
    '<path d="M18 20h28a5 5 0 0 1 5 5v15a5 5 0 0 1-5 5H30l-8 7v-7h-4a5 5 0 0 1-5-5V25a5 5 0 0 1 5-5z" fill="#fff"/>' +
    '<circle cx="27" cy="32" r="2.6" fill="#0F2A33"/><circle cx="37" cy="32" r="2.6" fill="#0F2A33"/>' +
    "</svg>";

  var NAV_LINKS = [
    ["/fitur", "Fitur"],
    ["/cara-kerja", "Cara Kerja"],
    ["/industri", "Industri"],
    ["/harga", "Harga"],
    ["/demo", "Demo"],
  ];

  var HEADER =
    '<header class="site-nav">' +
    '<div class="nav-inner">' +
    '<a class="nav-brand" href="/"><span class="nav-logo">' + LOGO_SVG + "</span>" +
    '<span class="nav-name">Balesin<em>.ai</em></span></a>' +
    '<nav class="nav-links">' +
    NAV_LINKS.map(function (l) { return '<a href="' + l[0] + '">' + l[1] + "</a>"; }).join("") +
    "</nav>" +
    '<div class="nav-cta"><a class="btn ghost btn-sm" href="/masuk">Masuk</a>' +
    '<a class="btn primary btn-sm" href="/daftar">Coba Gratis</a></div>' +
    '<button class="nav-toggle" aria-label="Buka menu" aria-expanded="false">' +
    '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg>' +
    "</button></div>" +
    '<div class="nav-mobile">' +
    NAV_LINKS.map(function (l) { return '<a href="' + l[0] + '">' + l[1] + "</a>"; }).join("") +
    '<a href="/masuk">Masuk</a>' +
    '<a class="btn primary" href="/daftar">Coba Gratis</a>' +
    "</div></header>";

  var FOOTER =
    '<footer class="site-foot">' +
    '<div class="foot-inner">' +
    '<div class="foot-brand"><a class="nav-brand" href="/"><span class="nav-logo">' + LOGO_SVG + "</span>" +
    '<span class="nav-name">Balesin<em>.ai</em></span></a>' +
    "<p>AI yang menjawab obrolan pelanggan Anda di WhatsApp — 24 jam, tanpa nambah tim.</p></div>" +
    '<div class="foot-cols"><h4>Produk</h4><ul>' +
    '<li><a href="/fitur">Fitur</a></li><li><a href="/cara-kerja">Cara Kerja</a></li>' +
    '<li><a href="/demo">Demo Langsung</a></li><li><a href="/harga">Harga</a></li></ul></div>' +
    '<div class="foot-cols"><h4>Industri</h4><ul>' +
    '<li><a href="/industri">Jualan</a></li><li><a href="/industri">Kuliner</a></li>' +
    '<li><a href="/industri">Klinik</a></li><li><a href="/industri">Fashion</a></li></ul></div>' +
    '<div class="foot-cols"><h4>Kontak</h4><ul>' +
    '<li><a href="/demo">WhatsApp Kami</a></li><li><a href="mailto:halo@balesin.ai">halo@balesin.ai</a></li>' +
    "<li><a href=\"/daftar\">Coba Gratis</a></li></ul></div>" +
    "</div>" +
    '<div class="foot-legal"><span>© 2026 Balesin.ai — Nama &amp; konten indikatif, siap produksi.</span><span>Dibuat untuk toko yang masih jalan lewat WhatsApp.</span></div>' +
    "</footer>";

  function injectShell() {
    var body = document.body;
    if (body.querySelector(".site-nav")) return;
    body.insertAdjacentHTML("afterbegin", HEADER);
    body.insertAdjacentHTML("beforeend", FOOTER);
  }

  function bindNav() {
    var path = location.pathname.replace(/\/+$/, "") || "/";
    var links = document.querySelectorAll(".nav-links a, .nav-mobile a");
    links.forEach(function (a) {
      var href = a.getAttribute("href");
      if (!href || href.charAt(0) === "#") return;
      var target = href.replace(/\/+$/, "") || "/";
      if (target === path) a.classList.add("active");
    });
    var toggle = document.querySelector(".nav-toggle");
    var mobile = document.querySelector(".nav-mobile");
    if (toggle && mobile) {
      toggle.addEventListener("click", function () {
        var open = mobile.classList.toggle("open");
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
      });
    }
  }

  function bindReveal() {
    var els = document.querySelectorAll(".reveal");
    if (!("IntersectionObserver" in window)) {
      els.forEach(function (el) { el.classList.add("in"); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      });
    }, { threshold: 0.12 });
    els.forEach(function (el) { io.observe(el); });
  }

  /* ---------- Demo chat widget ---------- */
  var DEMO_SCRIPT = [
    { re: /(halo|hai|siang|pagi|malam|assalamualaikum|permisi)/i, r: "Halo Kak, selamat datang di toko kami. Ada yang bisa dibantu? Misalnya tanya harga, cek stok, atau mau langsung order.", i: "unclear" },
    { re: /(harga|berapa|ongkir|ongkos|payment|bayar|pembayaran)/i, r: "Untuk harga dan info pembayaran bisa saya cek dulu ya Kak. Kebetulan untuk detail lengkapnya nanti owner yang follow up, biar tidak salah info.", i: "faq" },
    { re: /(ada|stok|ready|ukuran|warna|size|size)/i, r: "Ada Kak, ready! Bisa disebutkan ukuran/warnanya supaya saya siapkan. Mau langsung dipesan?", i: "check_product" },
    { re: /(order|pesan|beli|ambil|mesan)/i, r: "Terima kasih ordernya! Owner akan follow up untuk konfirmasi pembayaran ya 🙏", i: "confirm_order" },
    { re: /(sudah bayar|belum sampai|kecewa|komplain|refund|batal)/i, r: "Maaf atas kendalanya Kak, saya teruskan ke owner sekarang ya. Mohon tunggu sebentar.", i: "faq", complaint: true },
  ];

  function bindDemoChat() {
    var body = document.getElementById("chat-body");
    if (!body) return;
    var input = document.getElementById("chat-input-box");
    var sendBtn = document.getElementById("chat-send");
    var suggestWrap = document.getElementById("chat-suggest");
    var suggestions = ["Harga kaosnya berapa?", "Ada kaos hitam size L?", "Mau order 2 pcs", "Barang belum sampai 5 hari"];
    var replyCount = 0;

    function addMsg(text, who, meta) {
      var el = document.createElement("div");
      el.className = "msg " + who;
      var metaHtml = meta ? '<span class="mint">' + meta + "</span>" : "";
      el.innerHTML = "<span></span>";
      el.firstChild.textContent = text;
      if (meta) el.insertAdjacentHTML("beforeend", metaHtml);
      body.appendChild(el);
      body.scrollTop = body.scrollHeight;
    }

    var INTENT_LABEL = {
      faq: "Pertanyaan umum",
      check_product: "Pertanyaan produk",
      confirm_order: "Pemesanan",
      unclear: "Perlu bantuan Anda",
    };
    var CONFIDENCE_LABEL = function (c) {
      if (c >= 0.9) return "sangat yakin";
      if (c >= 0.7) return "cukup yakin";
      if (c >= 0.6) return "agak ragu";
      return "kurang yakin";
    };

    function humanLabel(res) {
      var intent = INTENT_LABEL[res.intent] || res.intent || "Pesan";
      var conf = res.confidence != null ? " · " + CONFIDENCE_LABEL(res.confidence) : "";
      return intent + conf;
    }

    function scriptedReply(text) {
      var hit = null;
      for (var i = 0; i < DEMO_SCRIPT.length; i++) {
        if (DEMO_SCRIPT[i].re.test(text)) { hit = DEMO_SCRIPT[i]; break; }
      }
      if (!hit) hit = { r: "Maaf Kak, saya kurang yakin. Owner akan follow up untuk bantu pastikan jawabannya ya 🙏", i: "unclear" };
      var intent = hit.i + (hit.complaint ? " · komplain" : "");
      return { reply: hit.r, intent: intent, confidence: 0.9 };
    }

    function sendToApi(text) {
      var p = fetch("/api/tenants").then(function (r) { return r.json(); });
      return p.then(function (data) {
        var tenants = (data && data.tenants) || [];
        if (!tenants.length) return null;
        var tenantId = tenants[0].tenant_id || tenants[0].id || "";
        if (!tenantId) return null;
        return fetch("/api/chat/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text, tenant_id: tenantId, thread_id: "web_demo" }),
        }).then(function (r) { return r.json(); });
      }).then(function (res) {
        if (!res || !res.response) return null;
        return { reply: res.response, intent: res.intent || "", confidence: res.confidence };
      }).catch(function () { return null; });
    }

    function handleSend() {
      var text = (input.value || "").trim();
      if (!text) return;
      input.value = "";
      addMsg(text, "user");
      var typing = document.createElement("div");
      typing.className = "typing";
      typing.innerHTML = "<i></i><i></i><i></i>";
      body.appendChild(typing);
      body.scrollTop = body.scrollHeight;
      sendToApi(text).then(function (res) {
        typing.remove();
        var out = res || scriptedReply(text);
        addMsg(out.reply, "bot", humanLabel(out));
      });
    }

    if (sendBtn) sendBtn.addEventListener("click", handleSend);
    if (input) input.addEventListener("keydown", function (e) { if (e.key === "Enter") handleSend(); });
    if (suggestWrap) {
      suggestions.forEach(function (s) {
        var b = document.createElement("button");
        b.type = "button";
        b.textContent = s;
        b.addEventListener("click", function () { input.value = s; handleSend(); });
        suggestWrap.appendChild(b);
      });
    }
    setTimeout(function () {
      addMsg("Halo! Saya AI penjual dari toko ini 👋 Coba tanya saya: harga produk, cek stok, atau mau order.", "bot", "Pertanyaan umum · sangat yakin");
      replyCount++;
    }, 600);
  }

  /* ---------- Auth placeholder ---------- */
  function bindAuth() {
    var forms = document.querySelectorAll(".auth-card form");
    forms.forEach(function (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        var note = form.parentElement.querySelector(".auth-note");
        if (note) note.style.display = "block";
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    injectShell();
    bindNav();
    bindReveal();
    bindDemoChat();
    bindAuth();
  });
})();
