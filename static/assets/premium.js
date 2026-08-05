/* Balesin.ai — premium landing shell, reveal, and micro-interactions */
(function () {
  "use strict";

  var LOGO_SVG =
    '<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">' +
    '<path d="M18 20h28a5 5 0 0 1 5 5v15a5 5 0 0 1-5 5H30l-8 7v-7h-4a5 5 0 0 1-5-5V25a5 5 0 0 1 5-5z" fill="#fff"/>' +
    '<circle cx="27" cy="32" r="2.6" fill="#0D2B33"/><circle cx="37" cy="32" r="2.6" fill="#0D2B33"/>' +
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
    '<div class="nav-cta">' +
    '<a class="btn ghost" href="/masuk">Masuk</a>' +
    '<a class="btn primary" href="/daftar">Coba Gratis</a>' +
    "</div>" +
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
    '<div class="foot-brand">' +
    '<a class="nav-brand" href="/"><span class="nav-logo">' + LOGO_SVG + "</span>" +
    '<span class="nav-name">Balesin<em>.ai</em></span></a>' +
    "<p>Pelanggan terus mengobrol. Balesin.ai terus membantu.</p></div>" +
    '<div class="foot-cols"><h4>Produk</h4><ul>' +
    '<li><a href="/fitur">Fitur</a></li><li><a href="/cara-kerja">Cara Kerja</a></li>' +
    '<li><a href="/demo">Coba Langsung</a></li><li><a href="/harga">Harga</a></li></ul></div>' +
    '<div class="foot-cols"><h4>Perusahaan</h4><ul>' +
    '<li><a href="/industri">Industri</a></li><li><a href="/daftar">Coba Gratis</a></li>' +
    '<li><a href="/masuk">Masuk</a></li></ul></div>' +
    '<div class="foot-cols"><h4>Kontak</h4><ul>' +
    '<li><a href="/demo">WhatsApp Kami</a></li><li><a href="mailto:halo@balesin.ai">halo@balesin.ai</a></li>' +
    '<li><a href="/daftar">Mulai 14 hari gratis</a></li></ul></div>' +
    "</div>" +
    '<div class="foot-legal"><span>© 2026 Balesin.ai</span><span>Dibuat untuk toko yang masih jalan lewat WhatsApp.</span></div>' +
    "</footer>";

  function injectShell() {
    var body = document.body;
    if (body.querySelector(".site-nav")) return;
    body.insertAdjacentHTML("afterbegin", HEADER);
    body.insertAdjacentHTML("beforeend", FOOTER);
  }

  function bindNav() {
    var path = location.pathname.replace(/\/+$/, "") || "/";
    document.querySelectorAll(".nav-links a, .nav-mobile a").forEach(function (a) {
      var href = a.getAttribute("href");
      if (!href || href.charAt(0) === "#") return;
      if ((href.replace(/\/+$/, "") || "/") === path) a.classList.add("active");
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
      document.querySelectorAll(".mini-chat").forEach(function (c) { c.classList.add("play"); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      });
    }, { threshold: 0.15, rootMargin: "0px 0px -8% 0px" });
    els.forEach(function (el) { io.observe(el); });

    var chat = document.querySelector(".mini-chat");
    if (chat) {
      var cio = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting) { chat.classList.add("play"); cio.disconnect(); }
        });
      }, { threshold: 0.35 });
      cio.observe(chat);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    injectShell();
    bindNav();
    bindReveal();
  });
})();
