(() => {
  "use strict";

  const tg = window.Telegram && window.Telegram.WebApp;
  const initData = (tg && tg.initData) || "";
  const devUser = new URLSearchParams(location.search).get("dev_user");

  const state = {
    categories: [],
    products: {},          // id -> product
    settings: { is_open: true, delivery_fee: 0, min_order: 0, phone: "", work_hours: "" },
    cart: loadCart(),      // [{pid, v, qty}]
    me: null,
    view: "menu",
    history: [],
    currentOrder: null,
    pollTimer: null,
  };

  // ---------------- utils ----------------
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const money = (n) => Math.round(n).toLocaleString("ru-RU").replace(/ |,/g, " ") + " so'm";
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
      res = await fetch(path, { ...opts, headers });
    } catch (e) {
      throw new Error("Internet aloqasini tekshiring");
    }
    const data = await res.json().catch(() => ({ ok: false, error: "Server xatosi" }));
    if (!res.ok || !data.ok) throw new Error(data.error || "Xatolik yuz berdi");
    return data;
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
    if (!$("#sheet").classList.contains("open")) {
      const prev = state.history.pop() || "menu";
      go(prev, false);
    } else closeSheet();
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

  // ---------------- menu ----------------
  async function loadMenu() {
    try {
      const data = await api("/api/menu");
      state.categories = data.categories;
      state.settings = data.settings;
      state.products = {};
      data.categories.forEach((c) => c.products.forEach((p) => (state.products[p.id] = { ...p, category: c.name })));
      // mavjud bo'lmagan mahsulotlarni savatdan olib tashlash
      state.cart = state.cart.filter((i) => state.products[i.pid] && state.products[i.pid].variants[i.v]);
      saveCart();
      renderMenu();
      updateCartUI();
    } catch (e) {
      $("#menu-list").innerHTML = `<div class="empty"><div class="e-ico">⚠️</div><p>${esc(e.message)}</p>
        <button class="primary-btn" id="retry">Qayta urinish</button></div>`;
      $("#retry").onclick = loadMenu;
    }
  }

  function minPrice(p) { return Math.min(...p.variants.map((v) => v.price)); }
  function qtyInCart(pid) { return state.cart.filter((i) => i.pid === pid).reduce((s, i) => s + i.qty, 0); }
  function imgStyle(p) { return p.image ? `style="background-image:url('${esc(p.image)}')"` : ""; }

  function renderMenu() {
    const banner = $("#closed-banner");
    if (!state.settings.is_open) {
      banner.textContent = "⏸ Hozir buyurtma qabul qilinmayapti. Ish vaqti: " + state.settings.work_hours;
      banner.classList.remove("hidden");
    } else banner.classList.add("hidden");

    $("#cats").innerHTML = state.categories
      .map((c, i) => `<button class="cat-chip ${i === 0 ? "active" : ""}" data-cat="${c.id}">${esc(c.emoji)} ${esc(c.name)}</button>`)
      .join("");

    if (!state.categories.length) {
      $("#menu-list").innerHTML = `<div class="empty"><div class="e-ico">🍽</div><p>Menyu hozircha bo'sh</p></div>`;
      return;
    }
    $("#menu-list").innerHTML = state.categories.map((c) => `
      <section class="cat-section" id="cat-${c.id}" data-cat="${c.id}">
        <div class="cat-title">${esc(c.emoji)} ${esc(c.name)}</div>
        <div class="grid">
          ${c.products.map((p) => productCard(p)).join("")}
        </div>
      </section>`).join("");
    observeSections();
  }

  function productCard(p) {
    const q = qtyInCart(p.id);
    const multi = p.variants.length > 1;
    return `
      <div class="product" data-pid="${p.id}">
        <div class="img" ${imgStyle(p)}>${q ? `<span class="qty-pill">${q}</span>` : ""}</div>
        <div class="body">
          <div class="name">${esc(p.name)}</div>
          ${p.description ? `<div class="desc">${esc(p.description)}</div>` : ""}
          <div class="foot">
            <div class="price">${multi ? "<small>dan </small>" : ""}${money(minPrice(p))}</div>
            <button class="add-btn" data-quick="${p.id}" aria-label="Savatga qo'shish">+</button>
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
    const y = sec.getBoundingClientRect().top + window.scrollY - 64;
    window.scrollTo({ top: y, behavior: "smooth" });
    setActiveChip(chip.dataset.cat);
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
    const p = state.products[pid];
    sheetState = { pid, v: 0, qty: 1 };
    renderSheet();
    $("#sheet-backdrop").classList.remove("hidden");
    requestAnimationFrame(() => $("#sheet").classList.add("open"));
    haptic();
    updateBackButton();
  }

  function renderSheet() {
    const p = state.products[sheetState.pid];
    const price = p.variants[sheetState.v].price * sheetState.qty;
    $("#sheet").innerHTML = `
      <div class="s-img" ${imgStyle(p)}><button class="s-close" data-close>✕</button></div>
      <div class="s-body">
        <h3>${esc(p.name)}</h3>
        <p class="s-desc">${esc(p.description || p.category)}</p>
        ${p.variants.length > 1 ? `<div class="variants">${p.variants.map((v, i) => `
          <button class="variant ${i === sheetState.v ? "active" : ""}" data-v="${i}">
            <b>${esc(v.name || "Standart")}</b><small>${money(v.price)}</small>
          </button>`).join("")}</div>` : ""}
        <div class="sheet-actions">
          <div class="stepper">
            <button data-step="-1">−</button><span>${sheetState.qty}</span><button data-step="1">+</button>
          </div>
          <button class="primary-btn" data-add>Qo'shish · ${money(price)}</button>
        </div>
      </div>`;
  }

  $("#sheet").addEventListener("click", (e) => {
    if (e.target.closest("[data-close]")) return closeSheet();
    const v = e.target.closest("[data-v]");
    if (v) { sheetState.v = +v.dataset.v; haptic(); return renderSheet(); }
    const st = e.target.closest("[data-step]");
    if (st) { sheetState.qty = Math.max(1, Math.min(50, sheetState.qty + +st.dataset.step)); haptic(); return renderSheet(); }
    if (e.target.closest("[data-add]")) {
      addToCart(sheetState.pid, sheetState.v, sheetState.qty);
      closeSheet();
    }
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
    toast("✓ Savatga qo'shildi");
    refreshCardBadge(pid);
    updateCartUI();
  }

  function refreshCardBadge(pid) {
    const card = document.querySelector(`.product[data-pid="${pid}"]`);
    if (card) card.outerHTML = productCard(state.products[pid]);
  }

  function cartTotals() {
    const subtotal = state.cart.reduce((s, i) => s + state.products[i.pid].variants[i.v].price * i.qty, 0);
    const count = state.cart.reduce((s, i) => s + i.qty, 0);
    const delivery = count ? state.settings.delivery_fee : 0;
    return { subtotal, count, delivery, total: subtotal + delivery };
  }

  function updateCartUI() {
    const { count, total } = cartTotals();
    const badge = $("#cart-badge");
    badge.textContent = count;
    badge.classList.toggle("hidden", !count);
    const bar = $("#cart-bar");
    const showBar = count > 0 && state.view === "menu";
    bar.classList.toggle("hidden", !showBar);
    if (showBar) {
      $("#cart-bar-count").textContent = count + " ta";
      $("#cart-bar-total").textContent = money(total);
    }
  }
  $("#cart-bar").addEventListener("click", () => { haptic(); go("cart"); });

  function summaryHTML(withNote) {
    const { subtotal, delivery, total } = cartTotals();
    const min = state.settings.min_order;
    let note = "";
    if (withNote && min && subtotal < min) note = `<div class="note">Minimal buyurtma: ${money(min)}. Yana ${money(min - subtotal)} qo'shing.</div>`;
    if (withNote && !state.settings.is_open) note += `<div class="note">⏸ Hozir buyurtma qabul qilinmayapti (${esc(state.settings.work_hours)})</div>`;
    return `
      <div class="row"><span>Mahsulotlar</span><span>${money(subtotal)}</span></div>
      <div class="row"><span>Yetkazib berish</span><span>${delivery ? money(delivery) : "bepul"}</span></div>
      <div class="row total"><span>Jami</span><b>${money(total)}</b></div>${note}`;
  }

  function canCheckout() {
    const { subtotal, count } = cartTotals();
    return count > 0 && state.settings.is_open && subtotal >= state.settings.min_order;
  }

  function renderCart() {
    const list = $("#cart-list");
    $("#clear-cart").classList.toggle("hidden", !state.cart.length);
    if (!state.cart.length) {
      list.innerHTML = `<div class="empty"><div class="e-ico">🛒</div><p>Savatingiz bo'sh</p>
        <button class="primary-btn" data-go="menu">Menyuga o'tish</button></div>`;
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
            <div class="p">${money(v.price * i.qty)}</div>
          </div>
          <div class="stepper sm">
            <button data-cq="${idx}" data-d="-1">−</button><span>${i.qty}</span><button data-cq="${idx}" data-d="1">+</button>
          </div>
        </div>`;
    }).join("");
    $("#cart-summary").innerHTML = summaryHTML(true);
    const btn = $("#to-checkout");
    btn.classList.remove("hidden");
    btn.disabled = !canCheckout();
  }
  $("#to-checkout").addEventListener("click", () => { haptic(); go("checkout"); });

  $("#cart-list").addEventListener("click", (e) => {
    const b = e.target.closest("[data-cq]");
    if (!b) return;
    const item = state.cart[+b.dataset.cq];
    item.qty += +b.dataset.d;
    if (item.qty <= 0) state.cart.splice(+b.dataset.cq, 1);
    if (item.qty > 50) item.qty = 50;
    haptic();
    saveCart();
    renderCart();
    updateCartUI();
    refreshCardBadge(item.pid);
  });

  $("#clear-cart").addEventListener("click", () => {
    const doClear = () => {
      const pids = state.cart.map((i) => i.pid);
      state.cart = []; saveCart(); renderCart(); updateCartUI();
      pids.forEach(refreshCardBadge);
    };
    if (tg && tg.showConfirm && initData) tg.showConfirm("Savatni tozalaysizmi?", (ok) => ok && doClear());
    else if (confirm("Savatni tozalaysizmi?")) doClear();
  });

  // ---------------- checkout ----------------
  // Telefon: "+998" doimiy prefiks, foydalanuvchi faqat 9 ta raqam kiritadi -> "90 123 45 67"
  function formatLocal(digits) {
    const d = digits.slice(0, 9);
    return [d.slice(0, 2), d.slice(2, 5), d.slice(5, 7), d.slice(7, 9)].filter(Boolean).join(" ");
  }
  function localDigits(stored) {
    // saqlangan "+998901234567" -> "901234567"
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
    // kursorni o'sha raqam ortida saqlash
    let pos = 0, seen = 0;
    while (pos < formatted.length && seen < digitsBefore) { if (/\d/.test(formatted[pos])) seen++; pos++; }
    try { el.setSelectionRange(pos, pos); } catch (e) {}
  });
  phoneInput.addEventListener("paste", (e) => {
    // to'liq raqam joylansa (+998 90 ... yoki 998 90 ...) — prefiksni olib tashlaymiz
    const text = (e.clipboardData || window.clipboardData).getData("text") || "";
    let d = text.replace(/\D/g, "");
    if (d.length === 12 && d.startsWith("998")) d = d.slice(3);
    if (d.length > 9) d = d.slice(-9);
    e.preventDefault();
    phoneInput.value = formatLocal(d);
  });
  const phoneValue = () => "+998" + phoneInput.value.replace(/\D/g, "");

  function renderCheckout() {
    if (!state.cart.length) return go("cart", false);
    const me = state.me || {};
    const tgUser = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
    if (!$("#f-name").value) $("#f-name").value = me.full_name || (tgUser ? [tgUser.first_name, tgUser.last_name].filter(Boolean).join(" ") : "");
    if (!phoneInput.value && me.phone) phoneInput.value = formatLocal(localDigits(me.phone));
    if (!$("#f-address").value && me.address) $("#f-address").value = me.address;
    $("#checkout-summary").innerHTML = summaryHTML(true);
    $("#submit-btn").disabled = !canCheckout();
    $("#form-error").classList.add("hidden");
  }

  document.querySelector(".pay-option.disabled").addEventListener("click", (e) => {
    e.preventDefault();
    notifyHaptic("warning");
    toast("💳 Karta orqali to'lov tez kunda!");
  });

  $("#geo-btn").addEventListener("click", () => {
    const btn = $("#geo-btn");
    const done = (lat, lon) => {
      const link = `📍 https://maps.google.com/?q=${lat.toFixed(6)},${lon.toFixed(6)}`;
      const c = $("#f-comment");
      c.value = (c.value.replace(/📍 \S+/g, "").trim() + " " + link).trim();
      btn.textContent = "✓ Joylashuv qo'shildi";
      notifyHaptic("success");
    };
    const fail = () => { btn.textContent = "📍 Joriy joylashuvimni qo'shish"; toast("Joylashuvni aniqlab bo'lmadi"); };
    btn.textContent = "⏳ Aniqlanmoqda...";
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
    if (name.length < 2) return invalid("#f-name", "Qabul qiluvchi ismini kiriting");
    if (!/^\+998\d{9}$/.test(phone)) return invalid("#f-phone", "Telefon raqamni to'liq kiriting: +998 90 123 45 67");
    if (address.length < 5) return invalid("#f-address", "Yetkazish manzilini to'liqroq kiriting");

    const btn = $("#submit-btn");
    btn.disabled = true;
    btn.textContent = "Yuborilmoqda...";
    try {
      const data = await api("/api/orders", {
        method: "POST",
        body: JSON.stringify({
          name, phone, address,
          comment: $("#f-comment").value.trim(),
          payment_method: document.querySelector("input[name=payment]:checked").value,
          items: state.cart.map((i) => ({ product_id: i.pid, variant: i.v, qty: i.qty })),
        }),
      });
      const pids = state.cart.map((i) => i.pid);
      state.cart = [];
      saveCart();
      pids.forEach(refreshCardBadge);
      state.me = { ...(state.me || {}), full_name: name, phone, address };
      $("#f-comment").value = "";
      state.currentOrder = data.order;
      $("#success-code").textContent = data.order.code;
      notifyHaptic("success");
      state.history = [];
      go("success", false);
    } catch (err) {
      showFormError(err.message);
      if (/mavjud emas|o'lchami/.test(err.message)) loadMenu();
    } finally {
      btn.disabled = !canCheckout() && state.cart.length > 0;
      btn.textContent = "Buyurtmani tasdiqlash";
    }
  });

  $("#track-btn").addEventListener("click", () => { state.history = ["orders"]; openOrder(state.currentOrder.code); });

  // ---------------- orders ----------------
  const STEPS = [
    ["new", "📝", "Buyurtma berildi"],
    ["accepted", "✅", "Qabul qilindi"],
    ["cooking", "👨‍🍳", "Tayyorlanmoqda"],
    ["delivering", "🛵", "Yetkazilmoqda"],
    ["delivered", "🎉", "Yetkazildi"],
  ];
  const SHORT = { new: "Kutilmoqda", accepted: "Qabul qilindi", cooking: "Tayyorlanmoqda", delivering: "Yetkazilmoqda", delivered: "Yetkazildi", cancelled: "Bekor qilindi" };
  const isActive = (s) => !["delivered", "cancelled"].includes(s);
  const fmtDate = (s) => (s || "").slice(0, 16).replace(/^(\d{4})-(\d\d)-(\d\d)/, "$3.$2.$1");

  async function loadOrders(silent) {
    const list = $("#orders-list");
    if (!silent) list.innerHTML = `<div class="skeleton" style="height:90px"></div><div class="skeleton" style="height:90px"></div>`;
    try {
      const { orders } = await api("/api/orders");
      if (state.view !== "orders") return;
      if (!orders.length) {
        list.innerHTML = `<div class="empty"><div class="e-ico">📦</div><p>Hali buyurtmalar yo'q</p>
          <button class="primary-btn" data-go="menu">Buyurtma berish</button></div>`;
        return;
      }
      list.innerHTML = orders.map((o) => `
        <button class="order-card" data-code="${esc(o.code)}">
          <div class="top"><span class="code">${esc(o.code)}</span><span class="pill ${o.status}">${SHORT[o.status]}</span></div>
          <div class="meta"><span>${fmtDate(o.created_at)} · ${o.items.reduce((s, i) => s + i.qty, 0)} ta</span><b>${money(o.total)}</b></div>
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

  function renderOrder(o) {
    const reached = STEPS.findIndex((s) => s[0] === o.status);
    const timeline = o.status === "cancelled"
      ? `<div class="cancel-box"><b>❌ Buyurtma bekor qilindi</b>${o.cancel_reason ? `<div class="muted">Sabab: ${esc(o.cancel_reason)}</div>` : ""}</div>`
      : `<div class="timeline">${STEPS.map(([key, ico, label], i) => `
          <div class="step ${i <= reached ? "done" : ""} ${i === reached && isActive(o.status) ? "current" : ""}">
            <div class="dot">${ico}</div>
            <div class="label"><b>${label}</b>${o.timeline[key] ? `<small>${o.timeline[key].slice(11, 16)}</small>` : ""}</div>
          </div>`).join("")}</div>`;

    $("#order-detail").innerHTML = `
      <div class="od-head">
        <button class="back" id="od-back">← Buyurtmalar</button>
        <h2>${esc(o.code)}</h2>
        <p>${fmtDate(o.created_at)}</p>
      </div>
      ${timeline}
      <div class="summary od-items">
        ${o.items.map((i) => `<div class="it"><span>${esc(i.name)}${i.variant ? ` (${esc(i.variant)})` : ""} × ${i.qty}</span><span>${money(i.price * i.qty)}</span></div>`).join("")}
        <div class="row"><span>Yetkazib berish</span><span>${o.delivery_fee ? money(o.delivery_fee) : "bepul"}</span></div>
        <div class="row total"><span>Jami</span><b>${money(o.total)}</b></div>
      </div>
      <div class="summary od-info">
        <div>👤 <b>${esc(o.customer_name)}</b></div>
        <div>📞 <b>+998 ${esc(formatLocal(localDigits(o.phone)))}</b></div>
        <div>📍 <b>${esc(o.address)}</b></div>
        ${o.comment ? `<div>💬 ${esc(o.comment)}</div>` : ""}
        <div>💵 To'lov: <b>${o.payment_method === "cash" ? "Naqd" : "Karta"}</b></div>
      </div>
      ${o.status === "new" ? `<button class="danger-btn" id="cancel-order">Buyurtmani bekor qilish</button>` : ""}
      ${state.settings.phone ? `<p class="muted" style="text-align:center;font-size:13px">Savollar uchun: ${esc(state.settings.phone)}</p>` : ""}`;

    $("#od-back").onclick = () => go("orders");
    const cb = $("#cancel-order");
    if (cb) cb.onclick = () => {
      const doCancel = async () => {
        try { const { order } = await api(`/api/orders/${encodeURIComponent(o.code)}/cancel`, { method: "POST" }); renderOrder(order); stopPolling(); toast("Buyurtma bekor qilindi"); }
        catch (e) { toast(e.message); }
      };
      if (tg && tg.showConfirm && initData) tg.showConfirm("Buyurtmani bekor qilasizmi?", (ok) => ok && doCancel());
      else if (confirm("Buyurtmani bekor qilasizmi?")) doCancel();
    };
  }

  function startPolling(fn) {
    stopPolling();
    state.pollTimer = setInterval(fn, 8000);
  }
  function stopPolling() {
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollTimer = null;
  }

  // ---------------- init ----------------
  async function init() {
    if (tg) {
      tg.ready();
      tg.expand();
      try { tg.setHeaderColor("#0d2318"); tg.setBackgroundColor("#0d2318"); tg.setBottomBarColor && tg.setBottomBarColor("#0d2318"); } catch (e) {}
      try { tg.disableVerticalSwipes && tg.disableVerticalSwipes(); } catch (e) {}
      tg.BackButton.onClick(back);
    }
    if (!initData && !devUser) {
      $("#menu-list").innerHTML = `<div class="empty"><div class="e-ico">📱</div>
        <p>Iltimos, ushbu ilovani Telegram bot orqali oching.</p></div>`;
      return;
    }
    await loadMenu();
    api("/api/me").then((d) => (state.me = d.user)).catch(() => {});
    const hash = location.hash.replace("#", "");
    if (["orders", "cart"].includes(hash)) go(hash);
  }

  init();
})();
