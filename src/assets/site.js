(function () {
  "use strict";

  // Current year after © Ivah Sound
  document.querySelectorAll("[data-year]").forEach(function (el) {
    el.textContent = String(new Date().getFullYear());
  });

  // Top bar turns solid after the hero
  var bar = document.querySelector("[data-topbar]");
  if (bar) {
    var onScroll = function () { bar.classList.toggle("is-solid", window.scrollY > 40); };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  // Mobile menu
  var toggle = document.querySelector("[data-menu-toggle]");
  var nav = document.getElementById("site-nav");
  if (toggle && nav) {
    var setOpen = function (open) {
      toggle.setAttribute("aria-expanded", String(open));
      nav.classList.toggle("is-open", open);
      document.body.classList.toggle("menu-open", open);
    };
    toggle.addEventListener("click", function () {
      setOpen(toggle.getAttribute("aria-expanded") !== "true");
    });
    nav.addEventListener("click", function (e) {
      if (e.target.closest("a")) setOpen(false);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") setOpen(false);
    });
  }

  // YouTube: load the player only when asked (no tracking before a click)
  document.querySelectorAll("[data-yt]").forEach(function (box) {
    box.addEventListener("click", function () {
      if (box.querySelector("iframe")) return;
      var f = document.createElement("iframe");
      f.src = "https://www.youtube-nocookie.com/embed/" + box.dataset.yt + "?autoplay=1&rel=0";
      f.title = box.dataset.title || "YouTube video";
      f.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen";
      f.allowFullscreen = true;
      box.appendChild(f);
    });
  });

  // Pause background videos when off-screen, respect reduced motion
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var vids = document.querySelectorAll("video[autoplay]");
  if ("IntersectionObserver" in window) {
    var vio = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        var v = en.target;
        if (en.isIntersecting && !reduce) { var p = v.play(); if (p && p.catch) p.catch(function () {}); }
        else v.pause();
      });
    }, { threshold: 0.05 });
    vids.forEach(function (v) { vio.observe(v); });
  }
  if (reduce) vids.forEach(function (v) { v.pause(); v.removeAttribute("autoplay"); });

  // Reveal on scroll
  var revealables = document.querySelectorAll(".section-head, .tl-item, .card, .product, .post-card, .quotes blockquote, .split > *, .artist");
  if ("IntersectionObserver" in window && !reduce) {
    var rio = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("in"); rio.unobserve(en.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px" });
    revealables.forEach(function (el) { el.classList.add("reveal"); rio.observe(el); });
  }

  // Booking form: preselect from ?type= or from the card buttons
  var form = document.querySelector("[data-booking-form]");
  if (form) {
    var select = form.querySelector("#f-type");
    var pick = function (type) {
      if (!type || !select) return;
      for (var i = 0; i < select.options.length; i++) {
        if (select.options[i].value === type) { select.selectedIndex = i; break; }
      }
    };
    pick(new URLSearchParams(location.search).get("type"));
    document.querySelectorAll("[data-book]").forEach(function (a) {
      a.addEventListener("click", function (e) {
        e.preventDefault();
        pick(a.dataset.book);
        document.getElementById("booking-form").scrollIntoView({ behavior: reduce ? "auto" : "smooth" });
        setTimeout(function () { form.querySelector("#f-name").focus({ preventScroll: true }); }, reduce ? 0 : 600);
      });
    });

    var status = form.querySelector(".form-status");
    var say = function (msg, kind) { status.textContent = msg; status.className = "form-status " + (kind || ""); };

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var ok = true;
      form.querySelectorAll("[required]").forEach(function (el) {
        var bad = !el.value.trim() || (el.type === "email" && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(el.value));
        el.closest(".field").classList.toggle("invalid", bad);
        if (bad && ok) { el.focus(); ok = false; }
      });
      if (!ok) { say("Please fill in your name, a valid email and a few words about the event.", "err"); return; }
      if (form._gotcha && form._gotcha.value) return;

      var data = new FormData(form);
      data.set("interest", select.options[select.selectedIndex].text);
      data.set("_subject", "Booking request: " + (data.get("organisation") || data.get("name")));
      var endpoint = form.dataset.endpoint || "";

      // No form service connected yet: open a prefilled email instead
      if (!endpoint || endpoint.indexOf("REPLACE_WITH") !== -1) {
        var lines = [];
        data.forEach(function (v, k) { if (v && k.charAt(0) !== "_") lines.push(k.replace(/_/g, " ") + ": " + v); });
        location.href = "mailto:bookings@ivahsound.com?subject=" + encodeURIComponent(data.get("_subject")) + "&body=" + encodeURIComponent(lines.join("\n"));
        say("Your email app should open with the request filled in.", "ok");
        return;
      }

      var btn = form.querySelector("button[type=submit]");
      btn.disabled = true;
      say("Sending…");
      fetch(endpoint, { method: "POST", body: data, headers: { Accept: "application/json" } })
        .then(function (r) {
          if (!r.ok) throw new Error("bad status");
          form.reset();
          say("Thank you! Your request is in. We'll get back to you soon.", "ok");
        })
        .catch(function () {
          say("Sending failed. Please email bookings@ivahsound.com instead.", "err");
        })
        .finally(function () { btn.disabled = false; });
    });
  }

  // Journal filters
  var filters = document.querySelectorAll("[data-filter]");
  if (filters.length) {
    var apply = function (key) {
      filters.forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.filter === key)); });
      document.querySelectorAll(".year-group").forEach(function (group) {
        var any = false;
        group.querySelectorAll(".post-card").forEach(function (card) {
          var show = key === "all" || card.dataset.source === key;
          card.hidden = !show;
          if (show) any = true;
        });
        group.hidden = !any;
      });
    };
    filters.forEach(function (b) { b.addEventListener("click", function () { apply(b.dataset.filter); }); });
  }

  // Simple lightbox for galleries
  var links = Array.prototype.slice.call(document.querySelectorAll(".gallery a"));
  if (links.length) {
    var lb = document.createElement("div");
    lb.className = "lightbox";
    lb.hidden = true;
    lb.setAttribute("role", "dialog");
    lb.setAttribute("aria-modal", "true");
    lb.innerHTML = '<img alt=""><button class="lb-close" aria-label="Close">×</button><button class="lb-prev" aria-label="Previous">‹</button><button class="lb-next" aria-label="Next">›</button>';
    document.body.appendChild(lb);
    var img = lb.querySelector("img");
    var idx = 0;
    var show = function (i) {
      idx = (i + links.length) % links.length;
      img.src = links[idx].href;
      img.alt = (links[idx].querySelector("img") || {}).alt || "";
      lb.hidden = false;
    };
    links.forEach(function (a, i) { a.addEventListener("click", function (e) { e.preventDefault(); show(i); }); });
    lb.querySelector(".lb-close").onclick = function () { lb.hidden = true; };
    lb.querySelector(".lb-prev").onclick = function () { show(idx - 1); };
    lb.querySelector(".lb-next").onclick = function () { show(idx + 1); };
    lb.addEventListener("click", function (e) { if (e.target === lb) lb.hidden = true; });
    document.addEventListener("keydown", function (e) {
      if (lb.hidden) return;
      if (e.key === "Escape") lb.hidden = true;
      if (e.key === "ArrowLeft") show(idx - 1);
      if (e.key === "ArrowRight") show(idx + 1);
    });
  }
})();
