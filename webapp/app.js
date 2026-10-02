(() => {
  "use strict";

  const tg = window.Telegram && window.Telegram.WebApp;
  const initData = (tg && tg.initData) || "";
  const devUser = new URLSearchParams(location.search).get("dev_user");
  const API = ((window.YG_CONFIG && window.YG_CONFIG.api) || "").replace(/\/$/, "");

  const state = {
    lang: "uz",
    texts: {},
    categories: [],
    products: {},          // id -> product
    settings: { is_open: true, accepting: true, delivery_fee: 0, min_order: 0, delivery_enabled: true, pickup_enabled: true },
    slots: [],
    cart: loadCart(),      // [{pid, v, qty}]
    me: null,
    view: "menu",
    history: [],
    currentOrder: null,
    pollTimer: null,
    query: "",
    co: { type: "delivery", time: "asap", day: 0, slot: "", promo: "", quote: null },
  };

  // ---------------- utils ----------------
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const L = (key, vars) => {
    let s = state.texts[key] ?? key;
    if (vars) Object.entries(vars).forEach(([k, v]) => { s = s.split("{" + k + "}").join(v); });
    return s;
  };
  const money = (n) => Math.round(n).toLocaleString("ru-RU").replace(/ |,/g, " ") + (state.lang === "ru" ? " сум" : " so'm");
  const imgUrl = (p) => (p ? (API && !/^https?:/.test(p) ? API + "/" + p : p) : "");
  const haptic = (type = "light") => { try { tg && tg.HapticFeedback.impactOccurred(type); } catch (e) {} };
  const notifyHaptic = (type) => { try { tg && tg.HapticFeedback.notificationOccurred(type); } catch (e) {} };

  function loadCart() {
    try { const c = JSON.parse(localStorage.getItem("yg_cart") || "[]"); return Array.isArray(c) ? c : []; }
    catch (e) { return []; }
  }
  function saveCart() {
    try { localStorage.setItem("yg_cart", JSON.stringify(state.cart)); } catch (e) {}
  }

  let toastTimer;
  function toast(text) {
    const t = $("#toast");
    t.textContent = text;
    t.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.add("hidden"), 2200);
  }

  async function api(path, opts = {}) {
    const headers = { "Content-Type": "application/json" };
    if (initData) headers["X-Telegram-Init-Data"] = initData;
    else if (devUser) headers["X-Dev-User"] = devUser;
    let res;
    try {
      res = await fetch(API + path, { ...opts, headers });
    } catch (e) {
      throw new Error(L("network"));
    }
    const data = await res.json().catch(() => ({ ok: false, error: "Server error" }));
    if (!res.ok || !data.ok) throw new Error(data.error || "Error");
    return data;
  }

  function applyTexts() {
    document.documentElement.lang = state.lang;
    document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = L(el.dataset.i18n); });
    document.querySelectorAll("[data-i18n-ph]").forEach((el) => { el.placeholder = L(el.dataset.i18nPh); });
    document.querySelectorAll("#lang-switch button").forEach((b) => b.classList.toggle("active", b.dataset.lang === state.lang));
  }

  // ---------------- navigation ----------------
  const TABS = { menu: "menu", cart: "cart", checkout: "cart", success: "orders", orders: "orders", order: "orders" };

  function go(view, push = true) {
    if (view === state.view) { window.scrollTo({ top: 0, behavior: "smooth" }); return; }
    if (push && !["menu", "cart", "orders"].includes(view)) state.history.push(state.view);
    if (["menu", "cart", "orders"].includes(view)) state.history = [];
    state.view = view;
    document.querySelectorAll(".view").forEach((el) => el.classList.toggle("active", el.id === "view-" + view));
    document.querySelectorAll(".tabbar button").forEach((b) => b.classList.toggle("active", b.dataset.go === TABS[view]));
    window.scrollTo(0, 0);
    stopPolling();
    if (view === "cart") renderCart();
    if (view === "checkout") renderCheckout();
    if (view === "orders") loadOrders();
    updateCartUI();
    updateBackButton();
  }

  function back() {
    if ($("#sheet").classList.contains("open")) return closeSheet();
    go(state.history.pop() || "menu", false);
  }

  function updateBackButton() {
    if (!tg || !tg.BackButton) return;
    const show = state.history.length > 0 || $("#sheet").classList.contains("open") || state.view !== "menu";
    show ? tg.BackButton.show() : tg.BackButton.hide();
  }

  document.addEventListener("click", (e) => {
    const g = e.target.closest("[data-go]");
    if (g) { haptic(); go(g.dataset.go); }
  });

  // ---------------- language ----------------
  $("#lang-switch").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-lang]");
    if (!b || b.dataset.lang === state.lang) return;
    haptic();
    try { await api("/api/me/lang", { method: "POST", body: JSON.stringify({ lang: b.dataset.lang }) }); } catch (err) {}
    await loadMenu();
  });

  // ---------------- menu ----------------
  async function loadMenu() {
    try {
      const data = await api("/api/menu");
      state.lang = data.lang || "uz";
      state.texts = data.texts || {};
      state.categories = data.categories;
      state.settings = data.settings;
      state.slots = data.slots || [];
      state.products = {};
      data.categories.forEach((c) => c.products.forEach((p) => (state.products[p.id] = { ...p, category: c.name })));
      state.cart = state.cart.filter((i) => state.products[i.pid] && state.products[i.pid].variants[i.v]);
      saveCart();
      applyTexts();
      renderMenu();
      updateCartUI();
      if (state.view === "cart") renderCart();
    } catch (e) {
      $("#menu-list").innerHTML = `<div class="empty"><div class="e-ico">⚠️</div><p>${esc(e.message)}</p>
        <button class="primary-btn" id="retry">${esc(L("retry"))}</button></div>`;
      $("#retry").onclick = loadMenu;
    }
  }

  function minVariant(p) { return p.variants.reduce((m, v) => (v.price < m.price ? v : m), p.variants[0]); }
  function qtyInCart(pid) { return state.cart.filter((i) => i.pid === pid).reduce((s, i) => s + i.qty, 0); }
  function imgStyle(p) { return p.image ? `style="background-image:url('${esc(imgUrl(p.image))}')"` : ""; }
  const BADGE_ICONS = { hit: "🔥 Hit", new: "🆕", top: "⭐ Top", spicy: "🌶" };
  function badgesHTML(p) {
    const b = (p.badges || []).map((k) => `<span class="badge-chip ${k}">${esc(BADGE_ICONS[k] || k)}</span>`);
    if (p.discount) b.unshift(`<span class="badge-chip sale">-${p.discount}%</span>`);
    return b.length ? `<div class="badges">${b.join("")}</div>` : "";
  }
  function priceHTML(v, prefix) {
    const pre = prefix ? `<small>${esc(L("from"))} </small>` : "";
    if (v.old_price) return `<span class="old">${money(v.old_price)}</span><span class="new">${pre}${money(v.price)}</span>`;
    return `<span>${pre}${money(v.price)}</span>`;
  }

  function closedText() {
    const s = state.settings;
    if (!s.accepting) return L("notAccepting");
    if (s.is_open) return "";
    let t = L("closed");
    if (s.next_open) t += " " + L("opensAt", { time: s.next_open });
    if (state.slots.length) t += " " + L("laterOnly");
    return t;
  }

  function renderMenu() {
    const banner = $("#closed-banner");
    const ct = closedText();
    banner.textContent = ct;
    banner.classList.toggle("hidden", !ct);

    $("#cats").innerHTML = state.categories
      .map((c, i) => `<button class="cat-chip ${i === 0 ? "active" : ""}" data-cat="${c.id}">${esc(c.emoji)} ${esc(c.name)}</button>`)
      .join("");
    $("#cats").classList.toggle("hidden", !!state.query);

    if (!state.categories.length) {
      $("#menu-list").innerHTML = `<div class="empty"><div class="e-ico">🍽</div><p>${esc(L("emptyMenu"))}</p></div>`;
      return;
    }
    if (state.query) {
      const q = state.query.toLowerCase();
      const found = Object.values(state.products).filter((p) => p.search.includes(q) || p.name.toLowerCase().includes(q));
      $("#menu-list").innerHTML = found.length
        ? `<div class="grid">${found.map(productCard).join("")}</div>`
        : `<div class="empty"><div class="e-ico">🔍</div><p>${esc(L("searchEmpty"))}</p></div>`;
      return;
    }
    $("#menu-list").innerHTML = state.categories.map((c) => `
      <section class="cat-section" id="cat-${c.id}" data-cat="${c.id}">
        <div class="cat-title">${esc(c.emoji)} ${esc(c.name)}</div>
        <div class="grid">${c.products.map(productCard).join("")}</div>
      </section>`).join("");
    observeSections();
  }

  function productCard(p) {
    const q = qtyInCart(p.id);
    return `
      <div class="product" data-pid="${p.id}">
        <div class="img" ${imgStyle(p)}>${badgesHTML(p)}${q ? `<span class="qty-pill">${q}</span>` : ""}</div>
        <div class="body">
          <div class="name">${esc(p.name)}</div>
          ${p.description ? `<div class="desc">${esc(p.description)}</div>` : ""}
          <div class="foot">
            <div class="price">${priceHTML(minVariant(p), p.variants.length > 1)}</div>
            <button class="add-btn" data-quick="${p.id}" aria-label="+">+</button>
          </div>
        </div>
      </div>`;
  }

  $("#menu-list").addEventListener("click", (e) => {
    const quick = e.target.closest("[data-quick]");
    const card = e.target.closest(".product");
    if (quick) {
      e.stopPropagation();
      const p = state.products[+quick.dataset.quick];
      if (p.variants.length === 1) { addToCart(p.id, 0, 1); return; }
      openSheet(p.id);
      return;
    }
    if (card) openSheet(+card.dataset.pid);
  });

  $("#cats").addEventListener("click", (e) => {
    const chip = e.target.closest(".cat-chip");
    if (!chip) return;
    haptic();
    const sec = document.getElementById("cat-" + chip.dataset.cat);
    window.scrollTo({ top: sec.getBoundingClientRect().top + window.scrollY - 64, behavior: "smooth" });
    setActiveChip(chip.dataset.cat);
  });

  let searchTimer;
  $("#search").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.query = e.target.value.trim();
      $("#search-clear").classList.toggle("hidden", !state.query);
      renderMenu();
    }, 150);
  });
  $("#search-clear").addEventListener("click", () => {
    $("#search").value = ""; state.query = "";
    $("#search-clear").classList.add("hidden");
    renderMenu();
  });

  function setActiveChip(id) {
    document.querySelectorAll(".cat-chip").forEach((c) => {
      const on = c.dataset.cat === String(id);
      c.classList.toggle("active", on);
      if (on) c.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
    });
  }

  let observer;
  function observeSections() {
    if (!("IntersectionObserver" in window)) return;
    observer && observer.disconnect();
    observer = new IntersectionObserver((entries) => {
      entries.forEach((en) => { if (en.isIntersecting) setActiveChip(en.target.dataset.cat); });
    }, { rootMargin: "-30% 0px -60% 0px" });
    document.querySelectorAll(".cat-section").forEach((s) => observer.observe(s));
  }

  // ---------------- product sheet ----------------
  let sheetState = null;

  function openSheet(pid) {
    sheetState = { pid, v: 0, qty: 1 };
    renderSheet();
    $("#sheet-backdrop").classList.remove("hidden");
    requestAnimationFrame(() => $("#sheet").classList.add("open"));
    haptic();
    updateBackButton();
  }

  function renderSheet() {
    const p = state.products[sheetState.pid];
    const v = p.variants[sheetState.v];
    $("#sheet").innerHTML = `
      <div class="s-img" ${imgStyle(p)}>${badgesHTML(p)}<button class="s-close" data-close>✕</button></div>
      <div class="s-body">
        <h3>${esc(p.name)}</h3>
        <p class="s-desc">${esc(p.description || p.category)}</p>
        ${p.variants.length > 1 ? `<div class="variants">${p.variants.map((x, i) => `
          <button class="variant ${i === sheetState.v ? "active" : ""}" data-v="${i}">
            <b>${esc(x.name || "Standart")}</b><small class="vprice">${priceHTML(x)}</small>
          </button>`).join("")}</div>` : `<div class="sheet-price">${priceHTML(v)}</div>`}
        <div class="sheet-actions">
          <div class="stepper">
            <button data-step="-1">−</button><span>${sheetState.qty}</span><button data-step="1">+</button>
          </div>
          <button class="primary-btn" data-add>${esc(L("add"))} · ${money(v.price * sheetState.qty)}</button>
        </div>
      </div>`;
  }

  $("#sheet").addEventListener("click", (e) => {
    if (e.target.closest("[data-close]")) return closeSheet();
    const v = e.target.closest("[data-v]");
    if (v) { sheetState.v = +v.dataset.v; haptic(); return renderSheet(); }
    const st = e.target.closest("[data-step]");
    if (st) { sheetState.qty = Math.max(1, Math.min(50, sheetState.qty + +st.dataset.step)); haptic(); return renderSheet(); }
    if (e.target.closest("[data-add]")) { addToCart(sheetState.pid, sheetState.v, sheetState.qty); closeSheet(); }
  });
  $("#sheet-backdrop").addEventListener("click", closeSheet);

  function closeSheet() {
    $("#sheet").classList.remove("open");
    $("#sheet-backdrop").classList.add("hidden");
    setTimeout(updateBackButton, 0);
  }

  // ---------------- cart ----------------
  function addToCart(pid, v, qty) {
    const ex = state.cart.find((i) => i.pid === pid && i.v === v);
    if (ex) ex.qty = Math.min(50, ex.qty + qty);
    else state.cart.push({ pid, v, qty });
    saveCart();
    notifyHaptic("success");
    toast(L("added"));
    refreshCardBadge(pid);
    updateCartUI();
  }

  function refreshCardBadge(pid) {
    document.querySelectorAll(`.product[data-pid="${pid}"]`).forEach((card) => { card.outerHTML = productCard(state.products[pid]); });
  }

  function cartTotals() {
    const subtotal = state.cart.reduce((s, i) => s + state.products[i.pid].variants[i.v].price * i.qty, 0);
    const count = state.cart.reduce((s, i) => s + i.qty, 0);
    return { subtotal, count };
  }

  function updateCartUI() {
    const { count, subtotal } = cartTotals();
    const badge = $("#cart-badge");
    badge.textContent = count;
    badge.classList.toggle("hidden", !count);
    const showBar = count > 0 && state.view === "menu";
    $("#cart-bar").classList.toggle("hidden", !showBar);
    if (showBar) {
      $("#cart-bar-count").textContent = count + " " + L("pcs");
      $("#cart-bar-total").textContent = money(subtotal);
    }
  }
  $("#cart-bar").addEventListener("click", () => { haptic(); go("cart"); });

  function canCheckout() {
    return cartTotals().count > 0 && state.settings.accepting && (state.settings.is_open || state.slots.length > 0);
  }

  function renderCart() {
    const list = $("#cart-list");
    $("#clear-cart").classList.toggle("hidden", !state.cart.length);
    if (!state.cart.length) {
      list.innerHTML = `<div class="empty"><div class="e-ico">🛒</div><p>${esc(L("emptyCart"))}</p>
        <button class="primary-btn" data-go="menu">${esc(L("toMenu"))}</button></div>`;
      $("#cart-summary").innerHTML = "";
      $("#to-checkout").classList.add("hidden");
      return;
    }
    list.innerHTML = state.cart.map((i, idx) => {
      const p = state.products[i.pid];
      const v = p.variants[i.v];
      return `
        <div class="cart-item">
          <div class="thumb" ${imgStyle(p)}></div>
          <div class="info">
            <b>${esc(p.name)}</b>${v.name ? `<small>${esc(v.name)}</small>` : ""}
            <div class="p">${v.old_price ? `<span class="old">${money(v.old_price * i.qty)}</span>` : ""}${money(v.price * i.qty)}</div>
          </div>
          <div class="stepper sm">
            <button data-cq="${idx}" data-d="-1">−</button><span>${i.qty}</span><button data-cq="${idx}" data-d="1">+</button>
          </div>
        </div>`;
    }).join("");
    const { subtotal } = cartTotals();
    const s = state.settings;
    let html = `<div class="row total"><span>${esc(L("items"))}</span><b>${money(subtotal)}</b></div>`;
    if (s.delivery_enabled && s.min_order && subtotal < s.min_order) {
      html += `<div class="note">${esc(L("minOrder", { sum: money(s.min_order), left: money(s.min_order - subtotal) }))}</div>`;
    }
    const ct = closedText();
    if (ct) html += `<div class="note">${esc(ct)}</div>`;
    $("#cart-summary").innerHTML = html;
    const btn = $("#to-checkout");
    btn.classList.remove("hidden");
    btn.disabled = !canCheckout();
  }
  $("#to-checkout").addEventListener("click", () => { haptic(); go("checkout"); });

  $("#cart-list").addEventListener("click", (e) => {
    const b = e.target.closest("[data-cq]");
    if (!b) return;
    const item = state.cart[+b.dataset.cq];
    item.qty = Math.min(50, item.qty + +b.dataset.d);
    if (item.qty <= 0) state.cart.splice(+b.dataset.cq, 1);
    haptic();
    saveCart(); renderCart(); updateCartUI(); refreshCardBadge(item.pid);
  });

  function confirmDialog(text, cb) {
    if (tg && tg.showConfirm && initData) tg.showConfirm(text, (ok) => ok && cb());
    else if (confirm(text)) cb();
  }

  $("#clear-cart").addEventListener("click", () => confirmDialog(L("clearConfirm"), () => {
    const pids = state.cart.map((i) => i.pid);
    state.cart = []; saveCart(); renderCart(); updateCartUI();
    pids.forEach(refreshCardBadge);
  }));

  // ---------------- checkout ----------------
  function formatLocal(digits) {
    const d = digits.slice(0, 9);
    return [d.slice(0, 2), d.slice(2, 5), d.slice(5, 7), d.slice(7, 9)].filter(Boolean).join(" ");
  }
  function localDigits(stored) {
    const d = String(stored || "").replace(/\D/g, "");
    return d.length === 12 && d.startsWith("998") ? d.slice(3) : d.slice(-9);
  }
  const phoneInput = $("#f-phone");
  phoneInput.addEventListener("input", () => {
    const el = phoneInput;
    const caret = el.selectionStart ?? el.value.length;
    const digitsBefore = el.value.slice(0, caret).replace(/\D/g, "").length;
    const formatted = formatLocal(el.value.replace(/\D/g, ""));
    el.value = formatted;
    let pos = 0, seen = 0;
    while (pos < formatted.length && seen < digitsBefore) { if (/\d/.test(formatted[pos])) seen++; pos++; }
    try { el.setSelectionRange(pos, pos); } catch (e) {}
  });
  phoneInput.addEventListener("paste", (e) => {
    const text = (e.clipboardData || window.clipboardData).getData("text") || "";
    let d = text.replace(/\D/g, "");
    if (d.length === 12 && d.startsWith("998")) d = d.slice(3);
    if (d.length > 9) d = d.slice(-9);
    e.preventDefault();
    phoneInput.value = formatLocal(d);
  });
  const phoneValue = () => "+998" + phoneInput.value.replace(/\D/g, "");

  function rawItems() { return state.cart.map((i) => ({ product_id: i.pid, variant: i.v, qty: i.qty })); }

  function renderCheckout() {
    if (!state.cart.length) return go("cart", false);
    const s = state.settings;
    const me = state.me || {};
    const tgUser = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
    if (!$("#f-name").value) $("#f-name").value = me.full_name || (tgUser ? [tgUser.first_name, tgUser.last_name].filter(Boolean).join(" ") : "");
    if (!phoneInput.value && me.phone) phoneInput.value = formatLocal(localDigits(me.phone));
    if (!$("#f-address").value && me.address) $("#f-address").value = me.address;

    // buyurtma turi
    if (!s[state.co.type + "_enabled"]) state.co.type = s.delivery_enabled ? "delivery" : "pickup";
    $("#type-seg").classList.toggle("hidden", !(s.delivery_enabled && s.pickup_enabled));
    // vaqt
    if (!s.is_open) state.co.time = "later";
    renderType();
    renderTime();
    $("#form-error").classList.add("hidden");
    refreshQuote();
  }

  function renderType() {
    document.querySelectorAll("#type-seg button").forEach((b) => b.classList.toggle("active", b.dataset.type === state.co.type));
    const pickup = state.co.type === "pickup";
    $("#delivery-block").classList.toggle("hidden", pickup);
    const box = $("#pickup-block");
    box.classList.toggle("hidden", !pickup);
    if (pickup) box.innerHTML = `<b>${esc(L("pickupFrom"))}</b>${state.settings.cafe_address ? `<div>📍 ${esc(state.settings.cafe_address)}</div>` : ""}`;
  }

  $("#type-seg").addEventListener("click", (e) => {
    const b = e.target.closest("[data-type]");
    if (!b) return;
    haptic();
    state.co.type = b.dataset.type;
    renderType();
    refreshQuote();
  });

  function renderTime() {
    const asapBtn = document.querySelector('#time-seg [data-time="asap"]');
    asapBtn.disabled = !state.settings.is_open;
    document.querySelectorAll("#time-seg button").forEach((b) => b.classList.toggle("active", b.dataset.time === state.co.time));
    const picker = $("#slot-picker");
    picker.classList.toggle("hidden", state.co.time !== "later");
    if (state.co.time !== "later") return;
    if (!state.slots.length) {
      $("#slot-days").innerHTML = `<span class="muted">${esc(L("noSlots"))}</span>`;
      $("#slot-times").innerHTML = "";
      return;
    }
    if (state.co.day >= state.slots.length) state.co.day = 0;
    $("#slot-days").innerHTML = state.slots.map((d, i) =>
      `<button type="button" class="chip ${i === state.co.day ? "active" : ""}" data-day="${i}">${esc(L(d.day))}</button>`).join("");
    const day = state.slots[state.co.day];
    $("#slot-times").innerHTML = day.times.map((t) =>
      `<button type="button" class="chip ${t.value === state.co.slot ? "active" : ""}" data-slot="${esc(t.value)}">${esc(t.label)}</button>`).join("");
  }

  $("#time-seg").addEventListener("click", (e) => {
    const b = e.target.closest("[data-time]");
    if (!b || b.disabled) return;
    haptic();
    state.co.time = b.dataset.time;
    renderTime();
  });
  $("#slot-picker").addEventListener("click", (e) => {
    const d = e.target.closest("[data-day]");
    if (d) { state.co.day = +d.dataset.day; state.co.slot = ""; haptic(); return renderTime(); }
    const s = e.target.closest("[data-slot]");
    if (s) { state.co.slot = s.dataset.slot; haptic(); renderTime(); }
  });

  // promo-kod
  function promoMsg(text, ok) {
    const el = $("#promo-msg");
    el.textContent = text;
    el.className = "promo-msg " + (ok ? "ok" : "err");
    el.classList.toggle("hidden", !text);
  }
  $("#promo-apply").addEventListener("click", async () => {
    if (state.co.promo) {
      state.co.promo = ""; $("#f-promo").value = ""; $("#f-promo").disabled = false;
      $("#promo-apply").textContent = L("apply");
      promoMsg("");
      return refreshQuote();
    }
    const code = $("#f-promo").value.trim().toUpperCase();
    if (!code) return;
    try {
      const { quote } = await api("/api/quote", { method: "POST", body: JSON.stringify({ items: rawItems(), order_type: state.co.type, promo_code: code }) });
      state.co.promo = quote.promo_code;
      $("#f-promo").value = quote.promo_code; $("#f-promo").disabled = true;
      $("#promo-apply").textContent = L("remove");
      promoMsg("✓ " + quote.promo_label, true);
      notifyHaptic("success");
      renderSummary(quote);
    } catch (e) {
      promoMsg(e.message, false);
      notifyHaptic("error");
    }
  });

  let quoteSeq = 0;
  async function refreshQuote() {
    const seq = ++quoteSeq;
    try {
      const { quote } = await api("/api/quote", { method: "POST", body: JSON.stringify({ items: rawItems(), order_type: state.co.type, promo_code: state.co.promo }) });
      if (seq === quoteSeq) renderSummary(quote);
    } catch (e) {
      if (state.co.promo) { // promo endi mos emas (masalan olib ketishga o'tildi)
        promoMsg(e.message, false);
        state.co.promo = ""; $("#f-promo").disabled = false; $("#promo-apply").textContent = L("apply");
        return refreshQuote();
      }
      showFormError(e.message);
    }
  }

  function renderSummary(q) {
    state.co.quote = q;
    let html = `<div class="row"><span>${esc(L("items"))}</span><span>${money(q.subtotal)}</span></div>`;
    if (q.promo_code) html += `<div class="row disc"><span>🎁 ${esc(L("discount"))} (${esc(q.promo_code)})</span><span>${q.discount ? "−" + money(q.discount) : esc(q.promo_label)}</span></div>`;
    if (state.co.type === "delivery") html += `<div class="row"><span>${esc(L("deliveryFee"))}</span><span>${q.delivery_fee ? money(q.delivery_fee) : esc(L("free"))}</span></div>`;
    html += `<div class="row total"><span>${esc(L("total"))}</span><b>${money(q.total)}</b></div>`;
    if (q.min_order && q.subtotal < q.min_order) {
      html += `<div class="note">${esc(L("minOrder", { sum: money(q.min_order), left: money(q.min_order - q.subtotal) }))}</div>`;
    }
    $("#checkout-summary").innerHTML = html;
    $("#submit-btn").disabled = !!(q.min_order && q.subtotal < q.min_order);
  }

  document.querySelector(".pay-option.disabled").addEventListener("click", (e) => {
    e.preventDefault();
    notifyHaptic("warning");
    toast(L("cardSoon"));
  });

  $("#geo-btn").addEventListener("click", () => {
    const btn = $("#geo-btn");
    const done = (lat, lon) => {
      const link = `📍 https://maps.google.com/?q=${lat.toFixed(6)},${lon.toFixed(6)}`;
      const a = $("#f-address");
      a.value = (a.value.replace(/📍 \S+/g, "").trim() + " " + link).trim();
      btn.textContent = L("geoAdded");
      notifyHaptic("success");
    };
    const fail = () => { btn.textContent = L("geo"); toast(L("geoFail")); };
    btn.textContent = L("geoLoading");
    const lm = tg && tg.LocationManager;
    if (lm && tg.isVersionAtLeast && tg.isVersionAtLeast("8.0")) {
      lm.init(() => {
        if (!lm.isLocationAvailable) return browserGeo(done, fail);
        lm.getLocation((loc) => (loc ? done(loc.latitude, loc.longitude) : fail()));
      });
    } else browserGeo(done, fail);
  });

  function browserGeo(done, fail) {
    if (!navigator.geolocation) return fail();
    navigator.geolocation.getCurrentPosition((p) => done(p.coords.latitude, p.coords.longitude), fail, { enableHighAccuracy: true, timeout: 10000 });
  }

  function showFormError(msg) {
    const el = $("#form-error");
    el.textContent = msg;
    el.classList.remove("hidden");
    notifyHaptic("error");
    el.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  $("#checkout-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = $("#f-name").value.trim();
    const phone = phoneValue();
    const address = $("#f-address").value.trim();
    document.querySelectorAll(".field").forEach((f) => f.classList.remove("invalid"));
    const invalid = (id, msg) => { $(id).closest(".field").classList.add("invalid"); showFormError(msg); };
    if (name.length < 2) return invalid("#f-name", L("errName"));
    if (!/^\+998\d{9}$/.test(phone)) return invalid("#f-phone", L("errPhone"));
    if (state.co.type === "delivery" && address.length < 5) return invalid("#f-address", L("errAddress"));
    if (state.co.time === "later" && !state.co.slot) return showFormError(L("errTime"));

    const btn = $("#submit-btn");
    btn.disabled = true;
    btn.textContent = L("sending");
    try {
      const data = await api("/api/orders", {
        method: "POST",
        body: JSON.stringify({
          name, phone, address,
          order_type: state.co.type,
          scheduled_at: state.co.time === "later" ? state.co.slot : "",
          comment: $("#f-comment").value.trim(),
          promo_code: state.co.promo,
          payment_method: document.querySelector("input[name=payment]:checked").value,
          items: rawItems(),
        }),
      });
      const pids = state.cart.map((i) => i.pid);
      state.cart = [];
      saveCart();
      pids.forEach(refreshCardBadge);
      state.me = { ...(state.me || {}), full_name: name, phone, address: address || (state.me || {}).address };
      $("#f-comment").value = "";
      state.co.promo = ""; $("#f-promo").value = ""; $("#f-promo").disabled = false;
      $("#promo-apply").textContent = L("apply"); promoMsg("");
      state.co.slot = "";
      state.currentOrder = data.order;
      $("#success-code").textContent = data.order.code;
      notifyHaptic("success");
      state.history = [];
      go("success", false);
    } catch (err) {
      showFormError(err.message);
      loadMenu();
    } finally {
      btn.disabled = false;
      btn.textContent = L("confirm");
    }
  });

  $("#track-btn").addEventListener("click", () => { state.history = ["orders"]; openOrder(state.currentOrder.code); });

  // ---------------- orders ----------------
  const STEPS = [["new", "📝"], ["accepted", "✅"], ["cooking", "👨‍🍳"], ["delivering", "🛵"], ["delivered", "🎉"]];
  const isActive = (s) => !["delivered", "cancelled"].includes(s);
  const fmtDate = (s) => (s || "").slice(0, 16).replace(/^(\d{4})-(\d\d)-(\d\d)/, "$3.$2.$1");
  const shortStatus = (label) => (label || "").replace(/^\S+\s/, "");

  async function loadOrders(silent) {
    const list = $("#orders-list");
    if (!silent) list.innerHTML = `<div class="skeleton" style="height:90px"></div><div class="skeleton" style="height:90px"></div>`;
    try {
      const { orders } = await api("/api/orders");
      if (state.view !== "orders") return;
      if (!orders.length) {
        list.innerHTML = `<div class="empty"><div class="e-ico">📦</div><p>${esc(L("noOrders"))}</p>
          <button class="primary-btn" data-go="menu">${esc(L("orderNow"))}</button></div>`;
        return;
      }
      list.innerHTML = orders.map((o) => `
        <button class="order-card" data-code="${esc(o.code)}">
          <div class="top"><span class="code">${o.order_type === "pickup" ? "🏃" : "🛵"} ${esc(o.code)}</span><span class="pill ${o.status}">${esc(shortStatus(o.status_label))}</span></div>
          <div class="meta"><span>${fmtDate(o.created_at)}${o.scheduled_at ? " · ⏰ " + esc(fmtDate(o.scheduled_at)) : ""}</span><b>${money(o.total)}</b></div>
        </button>`).join("");
      if (orders.some((o) => isActive(o.status))) startPolling(() => loadOrders(true));
    } catch (e) {
      list.innerHTML = `<div class="empty"><div class="e-ico">⚠️</div><p>${esc(e.message)}</p></div>`;
    }
  }

  $("#orders-list").addEventListener("click", (e) => {
    const c = e.target.closest("[data-code]");
    if (c) { haptic(); openOrder(c.dataset.code); }
  });

  async function openOrder(code) {
    go("order");
    $("#order-detail").innerHTML = `<div class="skeleton" style="height:300px;margin-top:20px"></div>`;
    await refreshOrder(code);
  }

  async function refreshOrder(code) {
    try {
      const { order } = await api("/api/orders/" + encodeURIComponent(code));
      if (state.view !== "order") return;
      renderOrder(order);
      if (isActive(order.status)) startPolling(() => refreshOrder(code));
      else stopPolling();
    } catch (e) {
      $("#order-detail").innerHTML = `<div class="empty"><div class="e-ico">⚠️</div><p>${esc(e.message)}</p></div>`;
    }
  }

  function stepLabel(key, o) {
    if (key === "new") return L("stepNew");
    if (key === o.status) return shortStatus(o.status_label);
    // boshqa bosqichlar nomi — joriy holat yorlig'i formatida serverdan kelmaydi, shuning uchun qisqa nomlar
    const names = state.lang === "ru"
      ? { accepted: "Принят", cooking: "Готовится", delivering: o.order_type === "pickup" ? "Готов — можно забрать" : "В пути", delivered: o.order_type === "pickup" ? "Выдан" : "Доставлен" }
      : { accepted: "Qabul qilindi", cooking: "Tayyorlanmoqda", delivering: o.order_type === "pickup" ? "Tayyor — olib keting" : "Yetkazilmoqda", delivered: o.order_type === "pickup" ? "Berildi" : "Yetkazildi" };
    return names[key];
  }

  function renderOrder(o) {
    const reached = STEPS.findIndex((s) => s[0] === o.status);
    const steps = STEPS.map(([k, ico]) => [k, k === "delivering" && o.order_type === "pickup" ? "🛍" : ico]);
    const timeline = o.status === "cancelled"
      ? `<div class="cancel-box"><b>${esc(L("cancelledTitle"))}</b>${o.cancel_reason ? `<div class="muted">${esc(L("reason"))}: ${esc(o.cancel_reason)}</div>` : ""}</div>`
      : `<div class="timeline">${steps.map(([key, ico], i) => `
          <div class="step ${i <= reached ? "done" : ""} ${i === reached && isActive(o.status) ? "current" : ""}">
            <div class="dot">${ico}</div>
            <div class="label"><b>${esc(stepLabel(key, o))}</b>${o.timeline[key] ? `<small>${o.timeline[key].slice(11, 16)}</small>` : ""}</div>
          </div>`).join("")}</div>`;

    let rating = "";
    if (o.status === "delivered") {
      rating = o.review
        ? `<div class="summary rate-box"><b>${esc(L("yourRating"))}:</b> <span class="stars static">${"★".repeat(o.review.rating)}${"☆".repeat(5 - o.review.rating)}</span>${o.review.comment ? `<div class="muted">💬 ${esc(o.review.comment)}</div>` : ""}</div>`
        : `<div class="summary rate-box" id="rate-box">
            <b>${esc(L("rateTitle"))}</b>
            <div class="stars" id="stars">${[1, 2, 3, 4, 5].map((n) => `<button type="button" data-star="${n}">★</button>`).join("")}</div>
            <textarea id="rate-comment" rows="2" maxlength="500" placeholder="${esc(L("ratePh"))}"></textarea>
            <button class="primary-btn" id="rate-send" disabled>${esc(L("rateSend"))}</button>
          </div>`;
    }

    $("#order-detail").innerHTML = `
      <div class="od-head">
        <button class="back" id="od-back">${esc(L("ordersBack"))}</button>
        <h2>${esc(o.code)}</h2>
        <p>${fmtDate(o.created_at)} · ${esc(L(o.order_type === "pickup" ? "pickup" : "delivery"))}${o.scheduled_at ? " · ⏰ " + esc(fmtDate(o.scheduled_at)) : ""}</p>
      </div>
      ${timeline}
      ${rating}
      <div class="summary od-items">
        ${o.items.map((i) => `<div class="it"><span>${esc(i.name)}${i.variant ? ` (${esc(i.variant)})` : ""} × ${i.qty}</span><span>${money(i.price * i.qty)}</span></div>`).join("")}
        ${o.discount ? `<div class="row disc"><span>🎁 ${esc(L("discount"))} (${esc(o.promo_code)})</span><span>−${money(o.discount)}</span></div>` : ""}
        ${o.order_type === "delivery" ? `<div class="row"><span>${esc(L("deliveryFee"))}</span><span>${o.delivery_fee ? money(o.delivery_fee) : esc(L("free"))}</span></div>` : ""}
        <div class="row total"><span>${esc(L("total"))}</span><b>${money(o.total)}</b></div>
      </div>
      <div class="summary od-info">
        <div>👤 <b>${esc(o.customer_name)}</b></div>
        <div>📞 <b>+998 ${esc(formatLocal(localDigits(o.phone)))}</b></div>
        ${o.order_type === "delivery" ? `<div>📍 <b>${esc(o.address)}</b></div>` : (state.settings.cafe_address ? `<div>🏃 <b>${esc(state.settings.cafe_address)}</b></div>` : "")}
        ${o.comment ? `<div>💬 ${esc(o.comment)}</div>` : ""}
        <div>${esc(L("cash"))}</div>
      </div>
      ${o.status === "new" ? `<button class="danger-btn" id="cancel-order">${esc(L("cancelOrder"))}</button>` : ""}
      ${state.settings.phone ? `<p class="muted" style="text-align:center;font-size:13px">${esc(L("questions"))}: ${esc(state.settings.phone)}</p>` : ""}`;

    $("#od-back").onclick = () => go("orders");
    const cb = $("#cancel-order");
    if (cb) cb.onclick = () => confirmDialog(L("cancelConfirm"), async () => {
      try {
        const { order } = await api(`/api/orders/${encodeURIComponent(o.code)}/cancel`, { method: "POST" });
        renderOrder(order); stopPolling(); toast(L("cancelledToast"));
      } catch (e) { toast(e.message); }
    });

    const stars = $("#stars");
    if (stars) {
      let rating = 0;
      stars.addEventListener("click", (e) => {
        const b = e.target.closest("[data-star]");
        if (!b) return;
        rating = +b.dataset.star;
        haptic();
        stars.querySelectorAll("button").forEach((x) => x.classList.toggle("on", +x.dataset.star <= rating));
        $("#rate-send").disabled = false;
      });
      $("#rate-send").onclick = async () => {
        try {
          const { order } = await api(`/api/orders/${encodeURIComponent(o.code)}/review`, {
            method: "POST", body: JSON.stringify({ rating, comment: $("#rate-comment").value.trim() }),
          });
          notifyHaptic("success");
          toast(L("rateThanks"));
          renderOrder(order);
        } catch (e) { toast(e.message); }
      };
    }
  }

  function startPolling(fn) { stopPolling(); state.pollTimer = setInterval(fn, 8000); }
  function stopPolling() { if (state.pollTimer) clearInterval(state.pollTimer); state.pollTimer = null; }

  // ---------------- init ----------------
  async function init() {
    if (tg) {
      tg.ready();
      tg.expand();
      try { tg.setHeaderColor("#071a10"); tg.setBackgroundColor("#071a10"); tg.setBottomBarColor && tg.setBottomBarColor("#071a10"); } catch (e) {}
      try { tg.disableVerticalSwipes && tg.disableVerticalSwipes(); } catch (e) {}
      tg.BackButton.onClick(back);
    }
    const tgLang = tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.language_code;
    state.lang = tgLang && tgLang.startsWith("ru") ? "ru" : "uz";
    if (!initData && !devUser) {
      state.texts = { openInTg: state.lang === "ru" ? "Пожалуйста, откройте приложение через Telegram-бота." : "Iltimos, ushbu ilovani Telegram bot orqali oching." };
      $("#menu-list").innerHTML = `<div class="empty"><div class="e-ico">📱</div><p>${esc(L("openInTg"))}</p></div>`;
      return;
    }
    await loadMenu();
    api("/api/me").then((d) => (state.me = d.user)).catch(() => {});
    const hash = location.hash.replace("#", "");
    if (["orders", "cart"].includes(hash)) go(hash);
  }

  init();
})();
