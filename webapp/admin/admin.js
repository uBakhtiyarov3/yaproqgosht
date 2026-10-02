/* Yaproq go'sht — admin web panel */
(() => {
  "use strict";

  const API = ((window.YG_CONFIG && window.YG_CONFIG.api) || "").replace(/\/$/, "");
  const tg = window.Telegram && window.Telegram.WebApp;
  const qs = new URLSearchParams(location.search);
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch (e) { /* */ } },
  };

  let TOKEN = store.get("yg_admin_token");
  const S = { page: "", menu: null, texts: null, textGroup: null, textQuery: "", cat: "all", ordersTab: "active",
    ordersQ: "", period: "today", lastOrderId: 0, timers: [] };

  // ---------------- yordamchilar ----------------
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (n) => String(Math.round(Number(n) || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  const money = (n) => num(n) + " so'm";
  const imgUrl = (p) => (p ? (/^https?:/.test(p) ? p : API + "/" + p) : "");
  const dt = (s) => (s ? String(s).slice(0, 16).replace(/^(\d{4})-(\d\d)-(\d\d)/, "$3.$2.$1") : "");
  const phone = (p) => {
    const d = String(p || "").replace(/\D/g, "");
    return d.length === 12 ? `+${d.slice(0, 3)} ${d.slice(3, 5)} ${d.slice(5, 8)} ${d.slice(8, 10)} ${d.slice(10)}` : (p || "");
  };
  const stars = (n) => "★".repeat(n) + "☆".repeat(5 - n);

  function toast(msg, kind = "ok") {
    const el = document.createElement("div");
    el.className = "toast " + kind;
    el.textContent = msg;
    $("#toasts").appendChild(el);
    setTimeout(() => el.remove(), kind === "bad" ? 6000 : 3000);
  }

  function headers() {
    if (TOKEN) return { "X-Admin-Token": TOKEN };
    if (tg && tg.initData) return { "X-Telegram-Init-Data": tg.initData };
    if (qs.get("dev_user")) return { "X-Dev-User": qs.get("dev_user") };
    return {};
  }

  async function api(path, { method = "GET", body, form, blob } = {}) {
    const opts = { method, headers: headers() };
    if (form) opts.body = form;
    else if (body !== undefined) {
      opts.body = JSON.stringify(body);
      opts.headers["Content-Type"] = "application/json";
    }
    let r;
    try {
      r = await fetch(API + "/api/admin/" + path, opts);
    } catch (e) {
      throw new Error("Server bilan aloqa yo'q. Internetni tekshiring.");
    }
    if (r.status === 401) {
      const data = await r.json().catch(() => ({}));
      showLogin(data.error);
      throw new Error(data.error || "Kirish kerak");
    }
    if (blob) {
      if (!r.ok) throw new Error("Yuklab bo'lmadi");
      return r;
    }
    const data = await r.json().catch(() => ({ ok: false, error: "Server javobi noto'g'ri (" + r.status + ")" }));
    if (!data.ok) throw new Error(data.error || "Xatolik");
    return data;
  }

  async function run(fn, okMsg) {
    try {
      const res = await fn();
      if (okMsg) toast(okMsg);
      return res;
    } catch (e) {
      toast(e.message, "bad");
      return null;
    }
  }

  async function download(path) {
    const r = await run(() => api(path, { blob: true }));
    if (!r) return;
    const cd = r.headers.get("Content-Disposition") || "";
    const name = (cd.match(/filename="?([^"]+)"?/) || [])[1] || "fayl";
    const url = URL.createObjectURL(await r.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: name });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  }

  // ---------------- modal ----------------
  function openModal(html, wide = false) {
    const m = $("#modal");
    m.className = "modal glass" + (wide ? " wide" : "");
    m.innerHTML = html;
    $("#modal-backdrop").classList.remove("hidden");
    document.body.style.overflow = "hidden";
    $$("[data-close]", m).forEach((b) => (b.onclick = closeModal));
    return m;
  }
  function closeModal() {
    $("#modal-backdrop").classList.add("hidden");
    $("#modal").innerHTML = "";
    document.body.style.overflow = "";
  }
  $("#modal-backdrop").addEventListener("mousedown", (e) => { if (e.target.id === "modal-backdrop") closeModal(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
  const modalHead = (title) => `<div class="modal-head"><h2>${title}</h2><button class="icon-btn" data-close>✕</button></div>`;

  // ---------------- Telegram HTML ko'rinishi ----------------
  const TG_TAGS = new Set(["b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code", "pre", "a", "tg-spoiler", "blockquote", "span"]);
  const vars = (s) => s.replace(/\{(\w+)\}/g, '<span class="var">{$1}</span>');
  function tgPreview(text, plain) {
    if (plain) return vars(esc(text));
    const doc = new DOMParser().parseFromString("<div>" + text + "</div>", "text/html");
    const walk = (node) => [...node.childNodes].map((n) => {
      if (n.nodeType === 3) return vars(esc(n.textContent));
      if (n.nodeType !== 1) return "";
      const tag = n.tagName.toLowerCase();
      const inner = walk(n);
      if (!TG_TAGS.has(tag)) return inner;
      let attrs = "";
      if (tag === "a") {
        const href = n.getAttribute("href") || "";
        attrs = /^(https?|tg):/i.test(href) ? ` href="${esc(href)}" target="_blank" rel="noopener"` : "";
      }
      if (tag === "span") return n.getAttribute("class") === "tg-spoiler" ? `<span class="tg-spoiler">${inner}</span>` : inner;
      return `<${tag}${attrs}>${inner}</${tag}>`;
    }).join("");
    return walk(doc.body.firstChild);
  }

  const TOOLS = [
    ["b", "<b>B</b>", "Qalin"], ["i", "<i>I</i>", "Kursiv"], ["u", "<u>U</u>", "Tagiga chizilgan"],
    ["s", "<s>S</s>", "Ustiga chizilgan"], ["code", "&lt;/&gt;", "Kod (nusxa olinadigan)"],
    ["tg-spoiler", "▒", "Yashirin (spoiler)"], ["blockquote", "❝", "Iqtibos"], ["a", "🔗", "Havola"],
  ];
  const toolbarHtml = (target) => `<div class="toolbar" data-target="${target}">` +
    TOOLS.map(([t, label, title]) => `<button type="button" data-tag="${t}" title="${title}">${label}</button>`).join("") + "</div>";

  function wrapSelection(ta, tag) {
    const { selectionStart: a, selectionEnd: b, value } = ta;
    const sel = value.slice(a, b) || "matn";
    let open = `<${tag}>`;
    if (tag === "a") {
      const url = prompt("Havola manzili (https://...)", "https://");
      if (!url || !/^(https?|tg):\/\/\S+$/.test(url)) return;
      open = `<a href="${url.replace(/"/g, "%22")}">`;
    }
    const ins = open + sel + `</${tag}>`;
    ta.setRangeText(ins, a, b, "end");
    ta.focus();
    ta.dispatchEvent(new Event("input", { bubbles: true }));
  }
  function insertAtCursor(ta, text) {
    ta.setRangeText(text, ta.selectionStart, ta.selectionEnd, "end");
    ta.focus();
    ta.dispatchEvent(new Event("input", { bubbles: true }));
  }
  document.addEventListener("click", (e) => {
    const tb = e.target.closest(".toolbar button[data-tag]");
    if (tb) {
      const ta = document.getElementById(tb.parentElement.dataset.target);
      if (ta) wrapSelection(ta, tb.dataset.tag);
      return;
    }
    const chip = e.target.closest(".chip[data-ins]");
    if (chip) {
      const ta = document.getElementById(chip.dataset.target);
      if (ta) insertAtCursor(ta, chip.dataset.ins);
    }
  });

  // ---------------- kirish ----------------
  function showLogin(msg) {
    S.timers.forEach(clearInterval);
    S.timers = [];
    $("#shell").classList.add("hidden");
    $("#login").classList.remove("hidden");
    $("#login-msg").textContent = msg || "";
    const bot = store.get("yg_bot");
    if (bot) {
      const a = $("#login-bot");
      a.href = "https://t.me/" + bot;
      a.classList.remove("hidden");
    }
  }

  async function boot() {
    if (tg) { try { tg.ready(); tg.expand(); } catch (e) { /* */ } }
    const code = (location.hash.match(/code=([\w-]+)/) || [])[1];
    if (code) {
      history.replaceState(null, "", location.pathname + location.search + "#dashboard");
      try {
        const r = await fetch(API + "/api/admin/login", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code }),
        });
        const data = await r.json();
        if (!data.ok) return showLogin(data.error);
        TOKEN = data.token;
        store.set("yg_admin_token", TOKEN);
      } catch (e) {
        return showLogin("Server bilan aloqa yo'q");
      }
    }
    if (!TOKEN && !(tg && tg.initData) && !qs.get("dev_user")) return showLogin();
    let me;
    try { me = await api("me"); } catch (e) { return; }
    if (me.bot_username) store.set("yg_bot", me.bot_username);
    $("#login").classList.add("hidden");
    $("#shell").classList.remove("hidden");
    $("#me").innerHTML = `<div><b>${esc(me.user.name)}</b><div class="muted small">👑 Menejer</div></div>
      <button class="btn sm" id="logout">Chiqish</button>`;
    $("#logout").onclick = async () => {
      await api("logout", { method: "POST" }).catch(() => {});
      TOKEN = null;
      store.set("yg_admin_token", null);
      showLogin("Siz paneldan chiqdingiz.");
    };
    route();
    pollOrders();
    S.timers.push(setInterval(pollOrders, 20000));
  }

  // yangi buyurtma ovozi
  function beep() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      [0, 0.18].forEach((t) => {
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.frequency.value = 880; g.gain.value = 0.08;
        o.connect(g).connect(ctx.destination);
        o.start(ctx.currentTime + t); o.stop(ctx.currentTime + t + 0.12);
      });
    } catch (e) { /* */ }
  }

  async function pollOrders() {
    let data;
    try { data = await api("orders?status=active"); } catch (e) { return; }
    const pill = $("#nav-active");
    const newCount = data.orders.filter((o) => o.status === "new").length;
    pill.textContent = data.orders.length;
    pill.classList.toggle("hidden", !data.orders.length);
    pill.style.background = newCount ? "var(--red)" : "var(--gold-3)";
    const maxId = Math.max(0, ...data.orders.map((o) => o.id));
    if (S.lastOrderId && maxId > S.lastOrderId) {
      toast("🔔 Yangi buyurtma keldi!");
      beep();
      if (S.page === "orders" || S.page === "dashboard") route();
    }
    S.lastOrderId = Math.max(S.lastOrderId, maxId);
    try {
      const st = (await api("settings")).status;
      const chip = $("#status-chip");
      chip.textContent = (st.accepting ? "🟢 Buyurtma qabul qilinmoqda" : "🔴 Yopiq") +
        (st.mode !== "auto" ? (st.mode === "open" ? " · doim ochiq" : " · qo'lda yopilgan") : "");
      chip.onclick = () => go("settings");
      chip.style.cursor = "pointer";
    } catch (e) { /* */ }
  }

  // ---------------- marshrut ----------------
  const PAGES = {};
  function go(page) { location.hash = page; }
  window.addEventListener("hashchange", route);
  $("#menu-toggle").onclick = () => { $("#sidebar").classList.add("open"); $("#sidebar-backdrop").classList.remove("hidden"); };
  $("#sidebar-backdrop").onclick = closeSidebar;
  function closeSidebar() { $("#sidebar").classList.remove("open"); $("#sidebar-backdrop").classList.add("hidden"); }
  $$("#nav a").forEach((a) => (a.onclick = () => { go(a.dataset.page); closeSidebar(); }));

  async function route() {
    if ($("#shell").classList.contains("hidden")) return;
    let page = location.hash.replace("#", "").split("?")[0];
    if (!PAGES[page]) page = "dashboard";
    if (S.pageTimer) { clearInterval(S.pageTimer); S.pageTimer = null; }
    S.page = page;
    $$("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.page === page));
    $("#page-title").textContent = $(`#nav a[data-page="${page}"] span`).textContent;
    const root = $("#page");
    if (root.dataset.page !== page) root.innerHTML = '<div class="loader">Yuklanmoqda…</div>';
    root.dataset.page = page;
    try {
      await PAGES[page](root);
    } catch (e) {
      root.innerHTML = `<div class="card glass empty">⚠️ ${esc(e.message)}<br><br><button class="btn" onclick="location.reload()">Qayta urinish</button></div>`;
    }
  }

  // ================= STATISTIKA =================
  const STATUS = {
    new: "🕐 Yangi", accepted: "✅ Qabul qilindi", cooking: "👨‍🍳 Tayyorlanmoqda",
    delivering: "🛵 Yetkazilmoqda", delivered: "🎉 Yetkazildi", cancelled: "❌ Bekor qilingan",
  };
  const PERIODS = { today: "Bugun", week: "7 kun", month: "30 kun", all: "Hammasi" };
  const periodTabs = (cur, attr = "data-period") =>
    `<div class="tabs">${Object.entries(PERIODS).map(([k, v]) => `<button ${attr}="${k}" class="${k === cur ? "active" : ""}">${v}</button>`).join("")}</div>`;

  PAGES.dashboard = async (root) => {
    const d = await api("dashboard?period=" + S.period);
    const s = d.stats;
    const daily = [...d.daily].reverse();
    const maxDay = Math.max(1, ...daily.map((x) => x.amount));
    const totalStatus = Math.max(1, s.total_orders);
    const kpi = (label, value, sub = "") => `<div class="kpi glass"><small>${label}</small><b>${value}</b>${sub ? `<span class="sub">${sub}</span>` : ""}</div>`;
    root.innerHTML = `
      <div class="card-head">${periodTabs(S.period)}<span class="sp"></span>
        <button class="btn sm" id="dash-refresh">↻ Yangilash</button></div>
      <div class="grid k">
        ${kpi("💰 Tushum (yetkazilgan)", money(s.revenue), `${s.by_status.delivered || 0} ta buyurtma`)}
        ${kpi("📦 Buyurtmalar", num(s.total_orders), `bekor: ${s.by_status.cancelled || 0}`)}
        ${kpi("🧾 O'rtacha chek", money(s.avg_check))}
        ${kpi("⏳ Hozir faol", num(d.active_orders), money(s.pending_sum))}
        ${kpi("🙋 Buyurtmachilar", num(s.customers), `yangi foydalanuvchi: ${s.new_users}`)}
        ${kpi("👥 Jami foydalanuvchi", num(s.users_total))}
        ${kpi("⭐ O'rtacha baho", s.rating.count ? s.rating.avg.toFixed(1) + " / 5" : "—", `${s.rating.count} ta baho`)}
        ${kpi("🎁 Promo chegirmalar", money(s.promo_sum))}
      </div>
      <div class="grid two" style="margin-top:16px">
        <div class="card glass"><h3>📈 Kunlik tushum</h3>
          ${daily.length ? `<div class="bars">${daily.map((x) => `<div class="bar" title="${x.day}: ${money(x.amount)}, ${x.orders} ta">
            <em>${x.amount >= 1e6 ? (x.amount / 1e6).toFixed(1) + "M" : Math.round(x.amount / 1000) + "k"}</em>
            <i style="height:${Math.max(2, (x.amount / maxDay) * 140)}px"></i><small>${x.day.slice(8)}.${x.day.slice(5, 7)}</small></div>`).join("")}</div>`
            : '<div class="empty">Hali yetkazilgan buyurtma yo\'q</div>'}
        </div>
        <div class="card glass"><h3>📊 Holatlar bo'yicha</h3>
          ${Object.keys(STATUS).map((k) => `<div style="margin-bottom:10px"><div class="btn-row" style="justify-content:space-between">
            <span>${STATUS[k]}</span><b>${s.by_status[k] || 0}</b></div>
            <div class="meter"><i style="width:${((s.by_status[k] || 0) / totalStatus) * 100}%"></i></div></div>`).join("")}
          <div class="muted small">🛵 Yetkazish: ${s.by_type.delivery || 0} · 🏃 Olib ketish: ${s.by_type.pickup || 0}</div>
        </div>
        <div class="card glass"><h3>🏆 Eng ko'p sotilganlar</h3>
          ${s.top.length ? `<table class="t"><tr><th>Mahsulot</th><th class="right">Soni</th><th class="right">Summa</th></tr>
            ${s.top.map((x) => `<tr><td>${esc(x.name)}</td><td class="right">${x.qty}</td><td class="right nowrap">${money(x.amount)}</td></tr>`).join("")}</table>`
            : '<div class="empty">Ma\'lumot yo\'q</div>'}
        </div>
        <div class="card glass"><h3>👷 Xodimlar natijasi</h3>
          ${d.staff.length ? `<table class="t"><tr><th>Xodim</th><th class="right">Buyurtma</th><th class="right">Summa</th></tr>
            ${d.staff.map((x) => `<tr><td>${esc(x.name)}</td><td class="right">${x.c}</td><td class="right nowrap">${money(x.amount)}</td></tr>`).join("")}</table>`
            : '<div class="empty">Ma\'lumot yo\'q</div>'}
        </div>
      </div>`;
    $$("[data-period]", root).forEach((b) => (b.onclick = () => { S.period = b.dataset.period; route(); }));
    $("#dash-refresh").onclick = route;
  };

  // ================= BUYURTMALAR =================
  const ORDER_TABS = { active: "⏳ Faol", new: "🕐 Yangi", delivered: "🎉 Yetkazilgan", cancelled: "❌ Bekor", all: "📋 Hammasi" };

  PAGES.orders = async (root) => {
    if (!$("#orders-list", root)) {
      root.innerHTML = `
        <div class="card-head">
          <div class="tabs" id="order-tabs">${Object.entries(ORDER_TABS).map(([k, v]) => `<button data-tab="${k}">${v}</button>`).join("")}</div>
          <span class="sp"></span>
          <input class="search-in" id="order-q" placeholder="🔍 YG-123456, telefon yoki ism" value="${esc(S.ordersQ)}">
        </div>
        <div id="orders-list" class="order-cards"></div>`;
      $$("#order-tabs button", root).forEach((b) => (b.onclick = () => { S.ordersTab = b.dataset.tab; loadOrders(); }));
      let tmr;
      $("#order-q", root).oninput = (e) => { clearTimeout(tmr); tmr = setTimeout(() => { S.ordersQ = e.target.value.trim(); loadOrders(); }, 350); };
    }
    await loadOrders();
    S.pageTimer = setInterval(() => { if (!$("#modal-backdrop").classList.contains("hidden")) return; loadOrders(); }, 15000);
  };

  async function loadOrders() {
    $$("#order-tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === S.ordersTab));
    const data = await api(`orders?status=${S.ordersTab}&q=${encodeURIComponent(S.ordersQ)}`);
    const list = $("#orders-list");
    if (!list) return;
    if (!data.orders.length) { list.innerHTML = '<div class="card glass empty">Buyurtmalar yo\'q</div>'; return; }
    list.innerHTML = data.orders.map((o) => `
      <div class="order-card glass" data-id="${o.id}">
        <div>
          <span class="code">${esc(o.code)}</span> <span class="badge ${o.status}">${esc(o.status_label)}</span>
          ${o.order_type === "pickup" ? '<span class="badge">🏃 Olib ketish</span>' : ""}
          ${o.scheduled_at ? `<span class="badge gold">⏰ ${esc(dt(o.scheduled_at))}</span>` : ""}
          <div class="meta">${esc(o.customer_name)} · ${esc(phone(o.phone))} · ${esc(dt(o.created_at))}</div>
          ${o.order_type === "delivery" ? `<div class="meta">📍 ${esc(o.address)}</div>` : ""}
          ${o.comment ? `<div class="meta">💬 ${esc(o.comment)}</div>` : ""}
        </div>
        <div class="right"><b class="gold">${money(o.total)}</b><div class="meta">${esc(o.payment_label)}</div>
          ${o.staff_name ? `<div class="meta">👷 ${esc(o.staff_name)}</div>` : ""}</div>
        <div class="actions">${orderActions(o)}</div>
      </div>`).join("");
    bindOrderActions(list);
  }

  const orderActions = (o) =>
    (o.next ? `<button class="btn sm success" data-act="next" data-id="${o.id}" data-st="${o.next[0]}">${esc(o.next[1])}</button>` : "") +
    (["new", "accepted", "cooking", "delivering"].includes(o.status) ? `<button class="btn sm danger" data-act="cancel" data-id="${o.id}">Bekor qilish</button>` : "");

  function bindOrderActions(root, after) {
    $$("[data-act]", root).forEach((b) => (b.onclick = async (e) => {
      e.stopPropagation();
      const id = b.dataset.id;
      let body;
      if (b.dataset.act === "cancel") {
        const reason = prompt("Bekor qilish sababi (mijozga yuboriladi):", "Kafe tomonidan bekor qilindi");
        if (reason === null) return;
        body = { status: "cancelled", reason };
      } else body = { status: b.dataset.st };
      b.disabled = true;
      const r = await run(() => api(`orders/${id}/status`, { method: "POST", body }), "Holat yangilandi, mijozga xabar yuborildi");
      b.disabled = false;
      if (r) { after ? after() : loadOrders(); pollOrders(); }
    }));
    $$(".order-card", root).forEach((c) => (c.onclick = () => orderModal(c.dataset.id)));
  }

  async function orderModal(id) {
    const d = await run(() => api("orders/" + id));
    if (!d) return;
    const o = d.order;
    const m = openModal(modalHead(`Buyurtma ${esc(o.code)} <span class="badge ${o.status}">${esc(o.status_label)}</span>`) + `
      <dl class="kv">
        <dt>Turi</dt><dd>${esc(o.type_label)}${o.scheduled_at ? ` · <b class="gold">⏰ ${esc(dt(o.scheduled_at))} ga</b>` : " · imkon qadar tez"}</dd>
        <dt>Mijoz</dt><dd>${esc(o.customer_name)} ${o.lang === "ru" ? "🇷🇺" : ""}</dd>
        <dt>Telefon</dt><dd><a href="tel:${esc(o.phone)}">${esc(phone(o.phone))}</a></dd>
        ${o.order_type === "delivery" ? `<dt>Manzil</dt><dd>${esc(o.address)}</dd>` : ""}
        ${o.comment ? `<dt>Izoh</dt><dd>${esc(o.comment)}</dd>` : ""}
        <dt>To'lov</dt><dd>${esc(o.payment_label)}</dd>
        <dt>Yaratilgan</dt><dd>${esc(dt(o.created_at))}</dd>
        ${o.staff_name ? `<dt>Xodim</dt><dd>${esc(o.staff_name)}</dd>` : ""}
        ${o.cancel_reason ? `<dt>Bekor sababi</dt><dd class="red">${esc(o.cancel_reason)}</dd>` : ""}
      </dl>
      <div class="section-title">Mahsulotlar</div>
      <ul class="items-list">${d.items.map((i) => `<li><span>${esc(i.name)}${i.variant ? ` (${esc(i.variant)})` : ""} × ${i.qty}</span><b>${money(i.price * i.qty)}</b></li>`).join("")}
        <li><span class="muted">Mahsulotlar</span><span>${money(o.subtotal)}</span></li>
        ${o.discount ? `<li><span class="muted">Chegirma ${o.promo_code ? `(${esc(o.promo_code)})` : ""}</span><span class="green">−${money(o.discount)}</span></li>` : ""}
        ${o.order_type === "delivery" ? `<li><span class="muted">Yetkazish</span><span>${o.delivery_fee ? money(o.delivery_fee) : "bepul"}</span></li>` : ""}
        <li><b>Jami</b><b class="gold">${money(o.total)}</b></li></ul>
      ${d.review ? `<div class="section-title">Mijoz bahosi</div><div><span class="stars">${stars(d.review.rating)}</span> ${esc(d.review.comment || "")}</div>` : ""}
      <div class="section-title">Tarix</div>
      <ul class="timeline">${d.log.map((l) => `<li>${esc(dt(l.at))} — ${STATUS[l.status] || esc(l.status)}</li>`).join("")}</ul>
      <div class="modal-foot"><button class="btn danger" id="o-del" title="Keraksiz/test buyurtmani butunlay o'chirish">🗑 O'chirish</button>
        <span style="flex:1"></span>${orderActions(o)}<button class="btn" data-close>Yopish</button></div>`);
    $("#o-del", m).onclick = async () => {
      if (!confirm(`${o.code} buyurtmasi butunlay o'chirilsinmi?\n\nStatistika va hisobotlardan ham o'chadi. Qaytarib bo'lmaydi.`)) return;
      if (await run(() => api("orders/" + o.id, { method: "DELETE" }), "Buyurtma o'chirildi")) {
        closeModal();
        pollOrders();
        if (S.page === "orders") loadOrders(); else route();
      }
    };
    bindOrderActions(m, () => { closeModal(); if (S.page === "orders") loadOrders(); });
  }

  // ================= MENYU =================
  async function loadMenu() { S.menu = await api("menu"); return S.menu; }

  PAGES.menu = async (root) => {
    const M = await loadMenu();
    if (S.cat !== "all" && !M.categories.some((c) => String(c.id) === String(S.cat))) S.cat = "all";
    const count = (cid) => M.products.filter((p) => p.category_id === cid).length;
    const prods = M.products.filter((p) => S.cat === "all" || String(p.category_id) === String(S.cat));
    const curCat = M.categories.find((c) => String(c.id) === String(S.cat));
    root.innerHTML = `
      <div class="card glass">
        <div class="card-head"><h3>📂 Kategoriyalar</h3>
          <button class="btn sm" id="cat-order">↕ Tartiblash</button>
          <button class="btn sm primary" id="cat-add">＋ Kategoriya</button></div>
        <div class="cat-list">
          <span class="cat-chip ${S.cat === "all" ? "active" : ""}" data-cat="all">Hammasi <small>${M.products.length}</small></span>
          ${M.categories.map((c) => `<span class="cat-chip ${String(c.id) === String(S.cat) ? "active" : ""} ${c.is_active ? "" : "off"}" data-cat="${c.id}">
            ${esc(c.emoji || "")} ${esc(c.name)} <small>${count(c.id)}</small>${c.is_active ? "" : ' <small>(yashirin)</small>'}</span>`).join("")}
        </div>
      </div>
      <div class="card-head">
        <h3 style="font-size:18px">${curCat ? esc((curCat.emoji || "") + " " + curCat.name) : "Barcha mahsulotlar"}</h3>
        ${curCat ? `<button class="btn sm" id="cat-edit">✏️ Kategoriyani tahrirlash</button>` : ""}
        <button class="btn primary" id="prod-add">＋ Mahsulot qo'shish</button>
      </div>
      <div class="products">${prods.length ? prods.map(productCard).join("") : '<div class="card glass empty">Bu kategoriyada mahsulot yo\'q</div>'}</div>`;

    $$("[data-cat]", root).forEach((c) => (c.onclick = () => { S.cat = c.dataset.cat; PAGES.menu(root); }));
    $("#cat-add").onclick = () => categoryModal(null);
    $("#cat-order").onclick = categoryOrderModal;
    if (curCat) $("#cat-edit").onclick = () => categoryModal(curCat);
    $("#prod-add").onclick = () => productModal(null);
    $$(".p-card", root).forEach((card) => {
      const id = +card.dataset.id;
      const p = M.products.find((x) => x.id === id);
      $("[data-edit]", card).onclick = () => productModal(p);
      $("[data-avail]", card).onchange = async (e) => {
        const r = await run(() => api("products/" + id, { method: "PATCH", body: { is_available: e.target.checked } }),
          e.target.checked ? "Sotuvda" : "Sotuvdan olindi (botda ko'rinmaydi)");
        if (r) PAGES.menu(root); else e.target.checked = !e.target.checked;
      };
      $$("[data-move]", card).forEach((b) => (b.onclick = () => moveProduct(p, +b.dataset.move, root)));
    });
  };

  function priceHtml(p) {
    return p.variants.map((v, i) => {
      const now = p.prices_now[i];
      const label = v.name ? `<span class="muted">${esc(v.name)}:</span> ` : "";
      return `<div>${label}${now !== v.price ? `<s>${num(v.price)}</s><strong>${num(now)}</strong>` : `<strong>${num(v.price)}</strong>`} so'm</div>`;
    }).join("");
  }

  function productCard(p) {
    const cat = S.menu.categories.find((c) => c.id === p.category_id);
    return `<div class="p-card glass ${p.is_available ? "" : "off"}" data-id="${p.id}">
      <div class="p-img" style="${p.image ? `background-image:url('${esc(imgUrl(p.image))}')` : ""}">${p.image ? "" : "📷"}
        <div class="badges">${p.badges.map((b) => `<span class="badge gold">${esc(S.menu.badges[b] || b)}</span>`).join("")}</div>
        ${p.discount_active ? `<span class="disc">−${p.discount_percent}%</span>` : ""}
      </div>
      <div class="p-body">
        <b>${esc(p.name)}</b>
        ${p.name_ru ? `<span class="muted small">🇷🇺 ${esc(p.name_ru)}</span>` : '<span class="small red">🇷🇺 ruscha nomi yo\'q</span>'}
        ${S.cat === "all" && cat ? `<span class="muted small">${esc((cat.emoji || "") + " " + cat.name)}</span>` : ""}
        <div class="p-price">${priceHtml(p)}</div>
        <div class="p-actions">
          <label class="switch"><input type="checkbox" data-avail ${p.is_available ? "checked" : ""}><i></i>Sotuvda</label>
          <button class="icon-btn" data-move="-1" title="Oldinga">↑</button>
          <button class="icon-btn" data-move="1" title="Orqaga">↓</button>
          <button class="btn sm" data-edit>✏️</button>
        </div>
      </div></div>`;
  }

  async function moveProduct(p, dir, root) {
    const list = S.menu.products.filter((x) => x.category_id === p.category_id);
    const i = list.findIndex((x) => x.id === p.id), j = i + dir;
    if (j < 0 || j >= list.length) return;
    [list[i], list[j]] = [list[j], list[i]];
    if (await run(() => api("products/order", { method: "POST", body: { ids: list.map((x) => x.id) } }))) PAGES.menu(root);
  }

  function categoryModal(c) {
    const m = openModal(modalHead(c ? "Kategoriyani tahrirlash" : "Yangi kategoriya") + `
      <div class="row">
        <label class="f"><span>Emoji</span><input id="c-emoji" maxlength="8" value="${esc(c ? c.emoji : "")}" placeholder="🍔"></label>
        <label class="f"><span>Nomi (o'zbekcha) *</span><input id="c-name" maxlength="40" value="${esc(c ? c.name : "")}"></label>
        <label class="f"><span>Nomi (ruscha)</span><input id="c-name-ru" maxlength="40" value="${esc(c ? c.name_ru || "" : "")}"></label>
      </div>
      ${c ? `<label class="switch"><input type="checkbox" id="c-active" ${c.is_active ? "checked" : ""}><i></i>Botda ko'rinadi</label>` : ""}
      <div class="modal-foot">
        ${c ? '<button class="btn danger" id="c-del">🗑 O\'chirish</button><span style="flex:1"></span>' : ""}
        <button class="btn" data-close>Bekor</button><button class="btn primary" id="c-save">💾 Saqlash</button>
      </div>`);
    $("#c-save", m).onclick = async () => {
      const body = { name: $("#c-name", m).value, name_ru: $("#c-name-ru", m).value, emoji: $("#c-emoji", m).value };
      if (c) body.is_active = $("#c-active", m).checked;
      const r = await run(() => api(c ? "categories/" + c.id : "categories", { method: c ? "PATCH" : "POST", body }), "Saqlandi — botda yangilandi");
      if (r) { closeModal(); if (!c) S.cat = String(r.category.id); route(); }
    };
    if (c) $("#c-del", m).onclick = async () => {
      if (!confirm(`«${c.name}» kategoriyasini o'chirasizmi?`)) return;
      if (await run(() => api("categories/" + c.id, { method: "DELETE" }), "O'chirildi")) { closeModal(); S.cat = "all"; route(); }
    };
  }

  function categoryOrderModal() {
    let cats = [...S.menu.categories];
    const m = openModal(modalHead("Kategoriyalar tartibi") + '<div id="co-list"></div><div class="modal-foot"><button class="btn" data-close>Bekor</button><button class="btn primary" id="co-save">💾 Saqlash</button></div>');
    const draw = () => {
      $("#co-list", m).innerHTML = cats.map((c, i) => `<div class="btn-row" style="padding:6px 0;border-bottom:1px solid var(--border)">
        <span style="flex:1">${i + 1}. ${esc((c.emoji || "") + " " + c.name)}</span>
        <button class="icon-btn" data-up="${i}">↑</button><button class="icon-btn" data-down="${i}">↓</button></div>`).join("");
      $$("[data-up]", m).forEach((b) => (b.onclick = () => { const i = +b.dataset.up; if (i > 0) { [cats[i - 1], cats[i]] = [cats[i], cats[i - 1]]; draw(); } }));
      $$("[data-down]", m).forEach((b) => (b.onclick = () => { const i = +b.dataset.down; if (i < cats.length - 1) { [cats[i + 1], cats[i]] = [cats[i], cats[i + 1]]; draw(); } }));
    };
    draw();
    $("#co-save", m).onclick = async () => {
      if (await run(() => api("categories/order", { method: "POST", body: { ids: cats.map((c) => c.id) } }), "Tartib saqlandi")) { closeModal(); route(); }
    };
  }

  const IMG_GUIDE = `<div class="guide"><b>📸 Ideal rasm talablari</b><ul>
    <li>Nisbat: <b>4:3</b> (gorizontal). Boshqa nisbat avtomatik markazdan kesiladi</li>
    <li>O'lcham: <b>1200×900 px</b> yoki kattaroq (kamida 800×600)</li>
    <li>Format: <b>JPG, PNG yoki WebP</b>, hajmi 10 MB gacha</li>
    <li>Mahsulot <b>markazda</b>, chetlarda bo'sh joy qoldiring</li>
    <li>Hamma rasmlarda <b>bir xil fon</b> va yorug'lik — menyu chiroyli ko'rinadi</li>
    <li>Rasm ustiga <b>matn/narx yozmang</b> — narx avtomatik chiqadi</li></ul>
    <div class="small" style="margin-top:6px">Yuklangan rasm avtomatik 1200×900 JPG ga optimallashtiriladi.</div></div>`;

  function productModal(p) {
    const M = S.menu;
    const variants = p ? p.variants.map((v) => ({ ...v })) : [{ name: "", price: "" }];
    let image = p ? p.image : "";
    const catId = p ? p.category_id : (S.cat !== "all" ? +S.cat : (M.categories[0] || {}).id);
    const m = openModal(modalHead(p ? "Mahsulotni tahrirlash" : "Yangi mahsulot") + `
      <div class="section-title" style="margin-top:0">Rasm</div>
      <div class="uploader">
        <div>
          <div class="drop ${image ? "has" : ""}" id="p-drop" style="${image ? `background-image:url('${esc(imgUrl(image))}')` : ""}">
            <span>📷<br>Rasmni shu yerga tashlang<br>yoki bosing</span></div>
          <input type="file" id="p-file" accept="image/jpeg,image/png,image/webp" hidden>
          <div class="btn-row" style="margin-top:8px"><button class="btn sm" id="p-pick">📤 Rasm tanlash</button>
            <button class="btn sm danger ${image ? "" : "hidden"}" id="p-img-del">Olib tashlash</button></div>
          <div class="ind" id="p-ind"></div><div class="warn-box" id="p-warn"></div>
        </div>
        ${IMG_GUIDE}
      </div>
      <div class="section-title">Asosiy</div>
      <label class="f"><span>Kategoriya *</span><select id="p-cat">${M.categories.map((c) => `<option value="${c.id}" ${c.id === catId ? "selected" : ""}>${esc((c.emoji || "") + " " + c.name)}</option>`).join("")}</select></label>
      <div class="row">
        <label class="f"><span>Nomi (o'zbekcha) *</span><input id="p-name" maxlength="60" value="${esc(p ? p.name : "")}"></label>
        <label class="f"><span>Nomi (ruscha)</span><input id="p-name-ru" maxlength="60" value="${esc(p ? p.name_ru : "")}"></label>
      </div>
      <div class="row">
        <label class="f"><span>Tavsif (o'zbekcha)</span><textarea id="p-desc" maxlength="500" rows="3">${esc(p ? p.description : "")}</textarea></label>
        <label class="f"><span>Tavsif (ruscha)</span><textarea id="p-desc-ru" maxlength="500" rows="3">${esc(p ? p.description_ru : "")}</textarea></label>
      </div>
      <div class="section-title">Narx va o'lchamlar</div>
      <div id="p-variants"></div>
      <button class="btn sm" id="p-var-add">＋ O'lcham qo'shish</button>
      <div class="hint">Bitta narx bo'lsa nomini bo'sh qoldiring. Bir nechta bo'lsa: masalan «O'rta» va «Katta» (ruschasi avtomatik).</div>
      <div class="section-title">Belgilar (badge)</div>
      <div>${Object.entries(M.badges).map(([k, v]) => `<label class="check"><input type="checkbox" data-badge="${k}" ${p && p.badges.includes(k) ? "checked" : ""}>${esc(v)}</label>`).join("")}</div>
      <div class="section-title">Chegirma</div>
      <div class="row">
        <label class="f"><span>Chegirma, %</span><input id="p-disc" type="number" min="0" max="95" value="${p ? p.discount_percent || "" : ""}" placeholder="0 — chegirma yo'q"></label>
        <label class="f"><span>Tugash sanasi (ixtiyoriy)</span><input id="p-disc-until" type="date" value="${p && p.discount_until ? p.discount_until.slice(0, 10) : ""}"></label>
      </div>
      <div class="hint" id="p-disc-prev"></div>
      <div style="margin-top:12px"><label class="switch"><input type="checkbox" id="p-avail" ${!p || p.is_available ? "checked" : ""}><i></i>Sotuvda (botda ko'rinadi)</label></div>
      <div class="modal-foot">
        ${p ? '<button class="btn danger" id="p-del">🗑 O\'chirish</button><span style="flex:1"></span>' : ""}
        <button class="btn" data-close>Bekor</button><button class="btn primary" id="p-save">💾 Saqlash</button>
      </div>`, true);

    const drawVariants = () => {
      $("#p-variants", m).innerHTML = variants.map((v, i) => `<div class="variant-row">
        <input data-vn="${i}" placeholder="${variants.length > 1 ? "O'lcham nomi *" : "O'lcham nomi (ixtiyoriy)"}" maxlength="30" value="${esc(v.name)}">
        <input data-vp="${i}" type="number" min="100" step="100" placeholder="Narx, so'm" value="${esc(v.price)}">
        <button class="icon-btn" data-vdel="${i}" ${variants.length < 2 ? "disabled" : ""}>✕</button></div>`).join("");
      $$("[data-vn]", m).forEach((x) => (x.oninput = () => (variants[+x.dataset.vn].name = x.value)));
      $$("[data-vp]", m).forEach((x) => (x.oninput = () => { variants[+x.dataset.vp].price = x.value; discPreview(); }));
      $$("[data-vdel]", m).forEach((x) => (x.onclick = () => { variants.splice(+x.dataset.vdel, 1); drawVariants(); }));
      discPreview();
    };
    const discPreview = () => {
      const pct = +$("#p-disc", m).value || 0;
      $("#p-disc-prev", m).innerHTML = pct > 0 ? "Yangi narx: " + variants.filter((v) => +v.price).map((v) =>
        `<s>${num(v.price)}</s> → <b class="gold">${num(Math.round((v.price * (100 - pct)) / 100 / 100) * 100)}</b>`).join(", ") + " so'm" : "";
    };
    drawVariants();
    $("#p-disc", m).oninput = discPreview;
    $("#p-var-add", m).onclick = () => { if (variants.length < 6) { variants.push({ name: "", price: "" }); drawVariants(); } };

    // rasm
    const drop = $("#p-drop", m), file = $("#p-file", m);
    const setImage = (path) => {
      image = path;
      drop.classList.toggle("has", !!path);
      drop.style.backgroundImage = path ? `url('${imgUrl(path)}')` : "";
      $("#p-img-del", m).classList.toggle("hidden", !path);
    };
    $("#p-pick", m).onclick = () => file.click();
    drop.onclick = () => file.click();
    $("#p-img-del", m).onclick = () => { setImage(""); $("#p-ind", m).innerHTML = ""; $("#p-warn", m).innerHTML = ""; };
    drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
    drop.ondragleave = () => drop.classList.remove("over");
    drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); if (e.dataTransfer.files[0]) uploadImage(e.dataTransfer.files[0]); };
    file.onchange = () => { if (file.files[0]) uploadImage(file.files[0]); file.value = ""; };

    async function uploadImage(f) {
      const ind = $("#p-ind", m), warn = $("#p-warn", m);
      warn.innerHTML = "";
      if (!/^image\/(jpeg|png|webp)$/.test(f.type)) { warn.textContent = "⚠️ Faqat JPG, PNG yoki WebP"; return; }
      if (f.size > 10 * 1024 * 1024) { warn.textContent = `⚠️ Fayl juda katta (${(f.size / 1048576).toFixed(1)} MB). Maks. 10 MB`; return; }
      const dims = await new Promise((res) => {
        const im = new Image();
        im.onload = () => res([im.naturalWidth, im.naturalHeight]);
        im.onerror = () => res([0, 0]);
        im.src = URL.createObjectURL(f);
      });
      const [w, h] = dims, ratio = h ? w / h : 0;
      const okRatio = Math.abs(ratio - 4 / 3) <= 0.04, okSize = w >= 1200 && h >= 900, minSize = w >= 800 && h >= 600;
      ind.innerHTML = `<span class="badge ${okRatio ? "okk" : "warn"}">${okRatio ? "✔" : "⚠"} Nisbat ${ratio ? ratio.toFixed(2) : "?"} ${okRatio ? "(4:3)" : "→ 4:3 ga kesiladi"}</span>
        <span class="badge ${okSize ? "okk" : "warn"}">${okSize ? "✔" : "⚠"} ${w}×${h}px</span>
        <span class="badge okk">✔ ${(f.size / 1024).toFixed(0)} KB</span>`;
      if (!minSize) warn.textContent = "⚠️ Rasm sifati past bo'lishi mumkin (kamida 800×600 tavsiya qilinadi).";
      drop.insertAdjacentHTML("beforeend", '<div class="busy">Yuklanmoqda…</div>');
      const fd = new FormData();
      fd.append("file", f);
      const r = await run(() => api("upload", { method: "POST", form: fd }));
      $(".busy", drop) && $(".busy", drop).remove();
      if (!r) return;
      setImage(r.path);
      ind.insertAdjacentHTML("beforeend", `<span class="badge okk">✔ Tayyor: ${r.width}×${r.height} JPG, ${(r.size / 1024).toFixed(0)} KB</span>`);
      if (r.warnings.length) warn.innerHTML = r.warnings.map((x) => "⚠️ " + esc(x)).join("<br>");
    }

    $("#p-save", m).onclick = async () => {
      const body = {
        category_id: +$("#p-cat", m).value, name: $("#p-name", m).value, name_ru: $("#p-name-ru", m).value,
        description: $("#p-desc", m).value, description_ru: $("#p-desc-ru", m).value,
        variants: variants.map((v) => ({ name: v.name.trim(), price: +v.price })),
        badges: $$("[data-badge]", m).filter((x) => x.checked).map((x) => x.dataset.badge),
        discount_percent: +$("#p-disc", m).value || 0, discount_until: $("#p-disc-until", m).value,
        is_available: $("#p-avail", m).checked, image,
      };
      const btn = $("#p-save", m);
      btn.disabled = true;
      const r = await run(() => api(p ? "products/" + p.id : "products", { method: p ? "PATCH" : "POST", body }), "Saqlandi — bot va mini ilovada yangilandi");
      btn.disabled = false;
      if (r) { closeModal(); route(); }
    };
    if (p) $("#p-del", m).onclick = async () => {
      if (!confirm(`«${p.name}» o'chirilsinmi? (Eski buyurtmalar tarixida qoladi)`)) return;
      if (await run(() => api("products/" + p.id, { method: "DELETE" }), "O'chirildi")) { closeModal(); route(); }
    };
  }

  // ================= BOT XABARLARI =================
  PAGES.texts = async (root) => {
    if (!S.texts) S.texts = (await api("texts")).texts;
    const groups = [...new Set(S.texts.map((x) => x.group))];
    if (!S.textGroup || !groups.includes(S.textGroup)) S.textGroup = groups[0];
    const changed = (g) => S.texts.filter((x) => x.group === g && (x.uz.value != null || x.ru.value != null)).length;
    root.innerHTML = `
      <div class="card glass" style="padding:14px">
        <div class="btn-row"><input id="tx-q" class="search-in" placeholder="🔍 Matn ichidan qidirish…" value="${esc(S.textQuery)}" style="max-width:420px">
        <span class="muted small" style="flex:1">Har bir xabarni o'zbek va rus tilida tahrirlang. <b>Saqlash</b> bosilishi bilan bot darhol yangi matnni ishlatadi.
          <code>{name}</code> kabi o'zgaruvchilar avtomatik qiymat bilan almashtiriladi.</span></div>
      </div>
      <div class="texts-layout">
        <div class="groups glass" id="tx-groups">${groups.map((g) => `<button data-g="${esc(g)}" class="${g === S.textGroup && !S.textQuery ? "active" : ""}">
          <span>${esc(g)}</span><small>${changed(g) ? "✎" + changed(g) + " · " : ""}${S.texts.filter((x) => x.group === g).length}</small></button>`).join("")}</div>
        <div id="tx-list"></div>
      </div>`;
    $$("#tx-groups button", root).forEach((b) => (b.onclick = () => { S.textGroup = b.dataset.g; S.textQuery = ""; PAGES.texts(root); }));
    let tmr;
    $("#tx-q", root).oninput = (e) => { clearTimeout(tmr); tmr = setTimeout(() => { S.textQuery = e.target.value.trim(); drawTexts(); }, 300); };
    drawTexts();
  };

  function drawTexts() {
    const q = S.textQuery.toLowerCase();
    const items = q ? S.texts.filter((x) => [x.key, x.uz.default, x.ru.default, x.uz.value, x.ru.value].some((s) => s && s.toLowerCase().includes(q)))
      : S.texts.filter((x) => x.group === S.textGroup);
    $$("#tx-groups button").forEach((b) => b.classList.toggle("active", !q && b.dataset.g === S.textGroup));
    const list = $("#tx-list");
    if (!items.length) { list.innerHTML = '<div class="card glass empty">Hech narsa topilmadi</div>'; return; }
    list.innerHTML = items.slice(0, 120).map(textItem).join("") + (items.length > 120 ? '<div class="empty">Qidiruvni aniqlashtiring…</div>' : "");
    $$(".text-item", list).forEach(bindTextItem);
  }

  const kind = (x) => (x.key.startsWith("b_") ? "⌨️ Tugma" : x.key.startsWith("w_") ? "📱 Mini ilova" : x.plain ? "🔤 Oddiy matn" : "📝 Formatlanadigan xabar");

  function textItem(x) {
    const side = (lang) => {
      const id = `tx-${x.key}-${lang}`, val = x[lang].value ?? x[lang].default;
      return `<div>
        <div class="text-head"><span class="lang-tag">${lang.toUpperCase()}</span>
          ${x[lang].value != null ? '<span class="badge gold">o\'zgartirilgan</span>' : '<span class="badge off">asl</span>'}
          <span class="sp"></span><span class="muted small" data-count="${lang}">${val.length}/${x.max}</span></div>
        ${x.plain ? "" : toolbarHtml(id)}
        <textarea id="${id}" data-lang="${lang}" rows="${Math.min(10, Math.max(2, val.split("\n").length + 1))}" maxlength="${x.max}">${esc(val)}</textarea>
        ${x.vars.length ? `<div class="chips">${x.vars.map((v) => `<button type="button" class="chip" data-target="${id}" data-ins="{${v}}" title="Kursor joyiga qo'yish">{${v}}</button>`).join("")}</div>` : ""}
        <div class="f-label" style="margin-top:8px">Ko'rinishi:</div>
        <div class="preview ${x.plain ? "plain" : ""}" data-prev="${lang}">${tgPreview(val, x.plain)}</div>
        <div class="err" data-err="${lang}"></div>
        <div class="btn-row" style="margin-top:8px">
          <button class="btn sm primary" data-save="${lang}">💾 Saqlash</button>
          <button class="btn sm ${x[lang].value != null ? "" : "hidden"}" data-reset="${lang}" title="Asl matnga qaytarish">↺ Asl holiga</button>
        </div></div>`;
    };
    return `<div class="text-item glass ${x.uz.value != null || x.ru.value != null ? "changed" : ""}" data-key="${esc(x.key)}">
      <div class="text-head"><code>${esc(x.key)}</code><span class="badge">${kind(x)}</span>${S.textQuery ? `<span class="muted small">${esc(x.group)}</span>` : ""}</div>
      <div class="editor-grid">${side("uz")}${side("ru")}</div></div>`;
  }

  function bindTextItem(el) {
    const x = S.texts.find((t) => t.key === el.dataset.key);
    ["uz", "ru"].forEach((lang) => {
      const ta = $(`textarea[data-lang="${lang}"]`, el);
      ta.oninput = () => {
        $(`[data-prev="${lang}"]`, el).innerHTML = tgPreview(ta.value, x.plain);
        $(`[data-count="${lang}"]`, el).textContent = `${ta.value.length}/${x.max}`;
        const unknown = (ta.value.match(/\{(\w+)\}/g) || []).map((s) => s.slice(1, -1)).filter((v) => !x.vars.includes(v));
        $(`[data-err="${lang}"]`, el).textContent = unknown.length ? "Noma'lum o'zgaruvchi: " + unknown.map((v) => `{${v}}`).join(", ") : "";
      };
      $(`[data-save="${lang}"]`, el).onclick = () => saveText(x, lang, ta.value, el);
      $(`[data-reset="${lang}"]`, el).onclick = () => { if (confirm("Asl matnga qaytarilsinmi?")) saveText(x, lang, "", el); };
    });
  }

  async function saveText(x, lang, value, el) {
    const errEl = $(`[data-err="${lang}"]`, el);
    const isDefault = value === x[lang].default;
    try {
      await api("texts", { method: "PUT", body: { key: x.key, lang, value: isDefault ? "" : value } });
    } catch (e) {
      errEl.textContent = "⚠️ " + e.message;
      return toast("Saqlanmadi: " + e.message, "bad");
    }
    x[lang].value = value && !isDefault ? value : null;
    toast(x[lang].value == null ? "Asl matn tiklandi" : "Saqlandi — bot darhol yangilandi");
    const fresh = document.createElement("div");
    fresh.innerHTML = textItem(x);
    el.replaceWith(fresh.firstElementChild);
    bindTextItem($(`.text-item[data-key="${CSS.escape(x.key)}"]`));
  }

  // ================= SOZLAMALAR =================
  const DAYS = [["mon", "Dushanba"], ["tue", "Seshanba"], ["wed", "Chorshanba"], ["thu", "Payshanba"], ["fri", "Juma"], ["sat", "Shanba"], ["sun", "Yakshanba"]];

  PAGES.settings = async (root) => {
    const { settings: s, status } = await api("settings");
    root.innerHTML = `
      <div class="card glass">
        <h3>🚦 Buyurtma qabul qilish</h3>
        <div class="tabs" id="mode-tabs">
          <button data-mode="auto">🕐 Ish vaqti bo'yicha (avto)</button>
          <button data-mode="open">🟢 Doim ochiq</button>
          <button data-mode="closed">🔴 Vaqtincha yopiq</button></div>
        <p class="muted small">Hozir: <b>${status.accepting ? "🟢 buyurtma qabul qilinmoqda" : "🔴 yopiq"}</b>${!status.accepting && status.next_open ? " · ochilish: " + esc(status.next_open) : ""}.
          Yopiq paytda ham mijozlar ish vaqti ichidagi vaqtga oldindan buyurtma bera oladi.</p>
      </div>
      <div class="card glass">
        <div class="card-head"><h3>🕐 Ish vaqti</h3><button class="btn sm" id="sch-copy">Dushanba vaqtini hamma kunlarga</button></div>
        <div class="sched" id="sched">${DAYS.map(([d, name]) => {
          const v = s.schedule[d];
          return `<div class="sched-row ${v ? "" : "closed"}" data-day="${d}"><b>${name}</b>
            <label class="check" style="margin:0"><input type="checkbox" data-off ${v ? "" : "checked"}>Dam olish</label>
            <input type="time" data-open value="${v ? v[0] : "10:00"}"><input type="time" data-close value="${v ? v[1] : "23:00"}"></div>`;
        }).join("")}</div>
        <div class="hint">Yarim tundan keyin yopilsa (masalan 10:00 – 02:00) shunchaki yopilish vaqtini 02:00 qilib qo'ying.</div>
      </div>
      <div class="card glass">
        <h3>🛵 Yetkazib berish va olib ketish</h3>
        <div class="btn-row" style="gap:24px;margin-bottom:14px">
          <label class="switch"><input type="checkbox" id="s-deliv" ${s.delivery_enabled ? "checked" : ""}><i></i>Yetkazib berish</label>
          <label class="switch"><input type="checkbox" id="s-pick" ${s.pickup_enabled ? "checked" : ""}><i></i>Olib ketish</label>
        </div>
        <div class="row">
          <label class="f"><span>Yetkazish narxi, so'm</span><input type="number" id="s-fee" min="0" step="1000" value="${s.delivery_fee}"><div class="hint">0 — bepul</div></label>
          <label class="f"><span>Minimal buyurtma, so'm</span><input type="number" id="s-min" min="0" step="1000" value="${s.min_order}"><div class="hint">Faqat yetkazishga. 0 — cheklovsiz</div></label>
          <label class="f"><span>Tayyorlash vaqti, daqiqa</span><input type="number" id="s-prep" min="10" max="600" value="${s.prep_time}"><div class="hint">Eng yaqin vaqt-slot shundan keyin</div></label>
          <label class="f"><span>Vaqt-slot qadami, daqiqa</span><input type="number" id="s-step" min="10" max="120" value="${s.slot_step}"><div class="hint">Masalan 30 → 12:00, 12:30…</div></label>
        </div>
      </div>
      <div class="card glass">
        <h3>📞 Aloqa</h3>
        <div class="row">
          <label class="f"><span>Telefon raqam</span><input id="s-phone" maxlength="40" value="${esc(s.phone)}" placeholder="+998 90 123 45 67"></label>
          <label class="f"><span>Kafe manzili (olib ketish uchun)</span><input id="s-addr" maxlength="200" value="${esc(s.cafe_address)}"></label>
        </div>
      </div>
      <div class="btn-row"><button class="btn primary" id="s-save">💾 Sozlamalarni saqlash</button>
        <span class="muted small">Saqlangach bot va mini ilova darhol yangi sozlamalar bilan ishlaydi.</span></div>`;

    let mode = s.mode;
    const drawMode = () => $$("#mode-tabs button", root).forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
    drawMode();
    $$("#mode-tabs button", root).forEach((b) => (b.onclick = async () => {
      mode = b.dataset.mode;
      drawMode();
      if (await run(() => api("settings", { method: "PUT", body: { mode } }), "Rejim o'zgartirildi")) { pollOrders(); route(); }
    }));
    $$(".sched-row [data-off]", root).forEach((c) => (c.onchange = () => c.closest(".sched-row").classList.toggle("closed", c.checked)));
    $("#sch-copy", root).onclick = () => {
      const first = $(".sched-row", root);
      $$(".sched-row", root).forEach((r) => {
        ["[data-open]", "[data-close]"].forEach((sel) => ($(sel, r).value = $(sel, first).value));
        $("[data-off]", r).checked = $("[data-off]", first).checked;
        r.classList.toggle("closed", $("[data-off]", first).checked);
      });
    };
    $("#s-save", root).onclick = async () => {
      const schedule = {};
      $$(".sched-row", root).forEach((r) => {
        schedule[r.dataset.day] = $("[data-off]", r).checked ? null : [$("[data-open]", r).value, $("[data-close]", r).value];
      });
      const body = {
        schedule, delivery_enabled: $("#s-deliv", root).checked, pickup_enabled: $("#s-pick", root).checked,
        delivery_fee: +$("#s-fee", root).value || 0, min_order: +$("#s-min", root).value || 0,
        prep_time: +$("#s-prep", root).value || 40, slot_step: +$("#s-step", root).value || 30,
        phone: $("#s-phone", root).value, cafe_address: $("#s-addr", root).value,
      };
      if (await run(() => api("settings", { method: "PUT", body }), "Saqlandi — bot darhol yangilandi")) { pollOrders(); route(); }
    };
  };

  // ================= PROMO-KODLAR =================
  const PROMO_KIND = { percent: "Foiz (%)", fixed: "Qat'iy summa (so'm)", free_delivery: "Bepul yetkazish" };
  const promoValue = (p) => (p.kind === "percent" ? `−${p.value}%${p.max_discount ? ` (maks. ${money(p.max_discount)})` : ""}` : p.kind === "fixed" ? "−" + money(p.value) : "🚚 Bepul yetkazish");

  PAGES.promos = async (root) => {
    const { promos } = await api("promos");
    root.innerHTML = `
      <div class="card-head"><p class="muted" style="flex:1;margin:0">Mijoz kodni savatda yoki rasmiylashtirishda kiritadi. Shartlar avtomatik tekshiriladi.</p>
        <button class="btn primary" id="pr-add">＋ Yangi promo-kod</button></div>
      <div class="card glass table-wrap">${promos.length ? `<table class="t">
        <tr><th>Kod</th><th>Chegirma</th><th>Shartlar</th><th>Ishlatilgan</th><th>Muddat</th><th>Faol</th><th></th></tr>
        ${promos.map((p) => `<tr>
          <td><b class="gold mono">${esc(p.code)}</b></td>
          <td class="nowrap">${promoValue(p)}</td>
          <td class="small">${[p.min_order ? `min. ${money(p.min_order)}` : "", p.first_order_only ? "faqat 1-buyurtma" : "",
            p.per_user_limit ? `har kishi ${p.per_user_limit} marta` : "cheksiz"].filter(Boolean).join(" · ")}</td>
          <td class="nowrap">${p.used}${p.usage_limit ? " / " + p.usage_limit : ""}</td>
          <td class="small nowrap">${p.starts_at ? esc(dt(p.starts_at)) : "—"}<br>${p.ends_at ? esc(dt(p.ends_at)) : "muddatsiz"}</td>
          <td><label class="switch"><input type="checkbox" data-toggle="${p.id}" ${p.is_active ? "checked" : ""}><i></i></label></td>
          <td><button class="btn sm" data-edit="${p.id}">✏️</button></td></tr>`).join("")}</table>`
        : '<div class="empty">Hali promo-kod yo\'q. «Yangi promo-kod» tugmasini bosing.</div>'}</div>`;
    $("#pr-add", root).onclick = () => promoModal(null);
    $$("[data-edit]", root).forEach((b) => (b.onclick = () => promoModal(promos.find((p) => p.id === +b.dataset.edit))));
    $$("[data-toggle]", root).forEach((c) => (c.onchange = () =>
      run(() => api("promos/" + c.dataset.toggle, { method: "PATCH", body: { is_active: c.checked } }), c.checked ? "Yoqildi" : "O'chirildi")));
  };

  function promoModal(p) {
    const dtl = (s) => (s ? s.slice(0, 16).replace(" ", "T") : "");
    const m = openModal(modalHead(p ? "Promo-kod: " + esc(p.code) : "Yangi promo-kod") + `
      ${p ? `<p class="muted small">Ishlatilgan: <b>${p.used}</b> marta · jami chegirma: <b>${money(p.discount_sum || 0)}</b></p>` : ""}
      <div class="row">
        <label class="f"><span>Kod *</span><input id="pm-code" maxlength="20" value="${esc(p ? p.code : "")}" placeholder="YOZ20" style="text-transform:uppercase"></label>
        <label class="f"><span>Turi *</span><select id="pm-kind">${Object.entries(PROMO_KIND).map(([k, v]) => `<option value="${k}" ${p && p.kind === k ? "selected" : ""}>${v}</option>`).join("")}</select></label>
        <label class="f" id="pm-value-wrap"><span id="pm-value-label">Qiymat</span><input id="pm-value" type="number" min="0" value="${p ? p.value : ""}"></label>
        <label class="f" id="pm-max-wrap"><span>Maks. chegirma, so'm</span><input id="pm-max" type="number" min="0" value="${p ? p.max_discount || "" : ""}" placeholder="0 — cheklovsiz"></label>
      </div>
      <div class="section-title">Shartlar</div>
      <div class="row">
        <label class="f"><span>Minimal buyurtma, so'm</span><input id="pm-min" type="number" min="0" value="${p ? p.min_order || "" : ""}" placeholder="0"></label>
        <label class="f"><span>Umumiy limit (necha marta)</span><input id="pm-limit" type="number" min="0" value="${p ? p.usage_limit || "" : ""}" placeholder="0 — cheklovsiz"></label>
        <label class="f"><span>Har bir mijozga</span><input id="pm-per" type="number" min="0" value="${p ? p.per_user_limit : 1}"><div class="hint">0 — cheklovsiz</div></label>
      </div>
      <div class="row">
        <label class="f"><span>Boshlanish</span><input id="pm-start" type="datetime-local" value="${dtl(p && p.starts_at)}"></label>
        <label class="f"><span>Tugash</span><input id="pm-end" type="datetime-local" value="${dtl(p && p.ends_at)}"></label>
      </div>
      <label class="check"><input type="checkbox" id="pm-first" ${p && p.first_order_only ? "checked" : ""}>Faqat birinchi buyurtma uchun</label>
      <label class="check"><input type="checkbox" id="pm-active" ${!p || p.is_active ? "checked" : ""}>Faol</label>
      <div class="modal-foot">${p ? '<button class="btn danger" id="pm-del">🗑 O\'chirish</button><span style="flex:1"></span>' : ""}
        <button class="btn" data-close>Bekor</button><button class="btn primary" id="pm-save">💾 Saqlash</button></div>`);
    const syncKind = () => {
      const k = $("#pm-kind", m).value;
      $("#pm-value-wrap", m).classList.toggle("hidden", k === "free_delivery");
      $("#pm-max-wrap", m).classList.toggle("hidden", k !== "percent");
      $("#pm-value-label", m).textContent = k === "percent" ? "Foiz, % *" : "Summa, so'm *";
    };
    $("#pm-kind", m).onchange = syncKind;
    syncKind();
    $("#pm-save", m).onclick = async () => {
      const body = {
        code: $("#pm-code", m).value, kind: $("#pm-kind", m).value, value: +$("#pm-value", m).value || 0,
        max_discount: +$("#pm-max", m).value || 0, min_order: +$("#pm-min", m).value || 0,
        usage_limit: +$("#pm-limit", m).value || 0, per_user_limit: +$("#pm-per", m).value || 0,
        starts_at: $("#pm-start", m).value, ends_at: $("#pm-end", m).value,
        first_order_only: $("#pm-first", m).checked, is_active: $("#pm-active", m).checked,
      };
      if (await run(() => api(p ? "promos/" + p.id : "promos", { method: p ? "PATCH" : "POST", body }), "Saqlandi")) { closeModal(); route(); }
    };
    if (p) $("#pm-del", m).onclick = async () => {
      if (confirm(`${p.code} o'chirilsinmi?`) && await run(() => api("promos/" + p.id, { method: "DELETE" }), "O'chirildi")) { closeModal(); route(); }
    };
  }

  // ================= BAHOLAR =================
  PAGES.reviews = async (root) => {
    const low = S.reviewsLow ? "1" : "0";
    const d = await api("reviews?low=" + low);
    const dist = (st) => [5, 4, 3, 2, 1].map((n) => `<div class="btn-row" style="gap:8px;margin-bottom:4px"><span class="stars" style="width:70px">${n} ★</span>
      <div class="meter" style="flex:1"><i style="width:${st.count ? ((st.dist[n] || 0) / st.count) * 100 : 0}%"></i></div><span class="muted small" style="width:30px">${st.dist[n] || 0}</span></div>`).join("");
    root.innerHTML = `
      <div class="grid two">
        <div class="card glass"><h3>Umumiy: ${d.total.count ? d.total.avg.toFixed(2) : "—"} ★ <span class="muted small">(${d.total.count} ta)</span></h3>${dist(d.total)}</div>
        <div class="card glass"><h3>Oxirgi 30 kun: ${d.month.count ? d.month.avg.toFixed(2) : "—"} ★ <span class="muted small">(${d.month.count} ta)</span></h3>${dist(d.month)}</div>
      </div>
      <div class="card-head"><div class="tabs"><button data-low="0" class="${low === "0" ? "active" : ""}">Hammasi</button>
        <button data-low="1" class="${low === "1" ? "active" : ""}">⚠️ Past baholar (1–3)</button></div></div>
      <div class="card glass">${d.reviews.length ? `<table class="t"><tr><th>Baho</th><th>Izoh</th><th>Buyurtma</th><th>Mijoz</th><th>Sana</th></tr>
        ${d.reviews.map((r) => `<tr><td class="stars nowrap">${stars(r.rating)}</td><td>${esc(r.comment) || '<span class="muted">—</span>'}</td>
          <td><a href="javascript:void 0" data-order="${r.order_id}">${esc(r.code)}</a></td><td>${esc(r.name || "")}</td><td class="nowrap small">${esc(dt(r.created_at))}</td></tr>`).join("")}</table>`
        : '<div class="empty">Baholar yo\'q</div>'}</div>`;
    $$("[data-low]", root).forEach((b) => (b.onclick = () => { S.reviewsLow = b.dataset.low === "1"; route(); }));
    $$("[data-order]", root).forEach((a) => (a.onclick = () => orderModal(a.dataset.order)));
  };

  // ================= RASSILKA =================
  PAGES.broadcast = async (root) => {
    const st = await api("broadcast");
    const buttons = [];
    let photo = null;
    root.innerHTML = `
      <div class="grid two">
        <div class="card glass">
          <h3>✍️ Xabar</h3>
          <label class="f"><span>Rasm (ixtiyoriy)</span><input type="file" id="bc-photo" accept="image/jpeg,image/png,image/webp"></label>
          <div class="f-label">Matn</div>
          ${toolbarHtml("bc-text")}
          <textarea id="bc-text" rows="8" placeholder="Masalan: 🔥 <b>Bugun barcha burgerlarga -20%!</b>"></textarea>
          <div class="hint" id="bc-count"></div>
          <div class="section-title">Tugmalar (havola)</div>
          <div id="bc-buttons"></div>
          <button class="btn sm" id="bc-btn-add">＋ Havola tugmasi</button>
          <div style="margin-top:12px"><label class="check"><input type="checkbox" id="bc-order" checked>«📋 Buyurtma berish» tugmasini qo'shish</label></div>
        </div>
        <div class="card glass">
          <h3>👁 Ko'rinishi</h3>
          <div style="max-width:380px">
            <img id="bc-prev-img" class="hidden" style="width:100%;border-radius:14px 14px 0 0;display:block">
            <div class="preview" id="bc-prev">…</div>
            <div id="bc-prev-btns"></div>
          </div>
          <div class="section-title">Yuborish</div>
          <p class="muted small">Qabul qiluvchilar: <b>${st.users}</b> ta foydalanuvchi (botni bloklaganlardan tashqari).</p>
          <div class="btn-row"><button class="btn" id="bc-test">🧪 Avval o'zimga test</button>
            <button class="btn primary" id="bc-send">📢 Hammaga yuborish</button></div>
          <div id="bc-status" style="margin-top:14px"></div>
        </div>
      </div>`;
    const ta = $("#bc-text", root);
    const draw = () => {
      $("#bc-prev", root).innerHTML = ta.value ? tgPreview(ta.value) : '<span class="muted">Matn kiriting…</span>';
      $("#bc-count", root).textContent = `${ta.value.length} / ${photo ? 1024 : 4000} belgi`;
      const btns = buttons.filter((b) => b.text).map((b) => b.text);
      if ($("#bc-order", root).checked) btns.push("📋 Buyurtma berish");
      $("#bc-prev-btns", root).innerHTML = btns.map((t) => `<div class="btn sm" style="width:100%;margin-top:4px">${esc(t)}</div>`).join("");
    };
    const drawButtons = () => {
      $("#bc-buttons", root).innerHTML = buttons.map((b, i) => `<div class="btn-edit-row">
        <input data-bt="${i}" placeholder="Tugma matni" maxlength="40" value="${esc(b.text)}">
        <input data-bu="${i}" placeholder="https://..." value="${esc(b.url)}"><button class="icon-btn" data-bd="${i}">✕</button></div>`).join("");
      $$("[data-bt]", root).forEach((x) => (x.oninput = () => { buttons[+x.dataset.bt].text = x.value; draw(); }));
      $$("[data-bu]", root).forEach((x) => (x.oninput = () => (buttons[+x.dataset.bu].url = x.value)));
      $$("[data-bd]", root).forEach((x) => (x.onclick = () => { buttons.splice(+x.dataset.bd, 1); drawButtons(); draw(); }));
    };
    ta.oninput = draw;
    $("#bc-order", root).onchange = draw;
    $("#bc-btn-add", root).onclick = () => { if (buttons.length < 5) { buttons.push({ text: "", url: "" }); drawButtons(); } };
    $("#bc-photo", root).onchange = (e) => {
      photo = e.target.files[0] || null;
      const img = $("#bc-prev-img", root);
      img.classList.toggle("hidden", !photo);
      if (photo) img.src = URL.createObjectURL(photo);
      draw();
    };
    draw();
    const send = async (test) => {
      if (!test && !confirm(`Xabar ${st.users} ta foydalanuvchiga yuborilsinmi?`)) return;
      const fd = new FormData();
      fd.append("text", ta.value);
      fd.append("buttons", JSON.stringify(buttons.filter((b) => b.text && b.url)));
      fd.append("order_btn", $("#bc-order", root).checked ? "1" : "0");
      fd.append("test", test ? "1" : "0");
      if (photo) fd.append("photo", photo, photo.name);
      const r = await run(() => api("broadcast", { method: "POST", form: fd }), test ? "Test xabar sizga yuborildi — Telegramni tekshiring" : "Rassilka boshlandi");
      if (r && !test) watchBroadcast(root);
    };
    $("#bc-test", root).onclick = () => send(true);
    $("#bc-send", root).onclick = () => send(false);
    if (st.running || st.finished_at) watchBroadcast(root, st);
  };

  function watchBroadcast(root, first) {
    const show = (st) => {
      const box = $("#bc-status", root);
      if (!box) return false;
      const done = st.sent + st.failed;
      box.innerHTML = `<div class="progress"><i style="width:${st.total ? (done / st.total) * 100 : 0}%"></i></div>
        <div class="small">${st.running ? "⏳ Yuborilmoqda…" : "✅ Yakunlandi " + esc(st.finished_at || "")} · yuborildi: <b class="green">${st.sent}</b> · xato/bloklagan: <b class="red">${st.failed}</b> · jami: ${st.total}</div>`;
      return st.running;
    };
    if (first && !show(first)) return;
    if (S.pageTimer) clearInterval(S.pageTimer);
    S.pageTimer = setInterval(async () => {
      const st = await api("broadcast").catch(() => null);
      if (!st || !show(st)) { clearInterval(S.pageTimer); S.pageTimer = null; }
    }, 2000);
  }

  // ================= MIJOZLAR =================
  PAGES.customers = async (root) => {
    if (!$("#cu-list", root)) {
      root.innerHTML = `<div class="card-head"><input id="cu-q" class="search-in" placeholder="🔍 ID, @username, telefon yoki ism"><span class="muted small" id="cu-total"></span></div>
        <div class="card glass table-wrap" id="cu-list"></div>`;
      let tmr;
      $("#cu-q", root).oninput = (e) => { clearTimeout(tmr); tmr = setTimeout(() => loadCustomers(e.target.value.trim()), 350); };
    }
    await loadCustomers("");
  };
  async function loadCustomers(q) {
    const d = await api("customers?q=" + encodeURIComponent(q));
    $("#cu-total").textContent = `Jami foydalanuvchilar: ${d.total}`;
    $("#cu-list").innerHTML = d.customers.length ? `<table class="t"><tr><th>Mijoz</th><th>Telefon</th><th>Til</th><th class="right">Buyurtma</th><th class="right">Xarid</th><th>Ro'yxatdan o'tgan</th></tr>
      ${d.customers.map((u) => `<tr><td><b>${esc(u.full_name || u.first_name || "—")}</b>${u.username ? ` <a href="https://t.me/${esc(u.username)}" target="_blank" rel="noopener">@${esc(u.username)}</a>` : ""}
        <div class="muted small">ID ${u.id}${u.role !== "user" ? ` · ${u.role === "manager" ? "👑 menejer" : "👷 xodim"}` : ""}${u.is_blocked ? ' · <span class="red">botni bloklagan</span>' : ""}</div></td>
        <td class="nowrap">${esc(phone(u.phone))}</td><td>${u.lang === "ru" ? "🇷🇺" : "🇺🇿"}</td><td class="right">${u.orders}</td>
        <td class="right nowrap">${money(u.spent)}</td><td class="small nowrap">${esc(dt(u.created_at))}</td></tr>`).join("")}</table>`
      : '<div class="empty">Topilmadi</div>';
  }

  // ================= XODIMLAR =================
  PAGES.staff = async (root) => {
    const d = await api("staff");
    root.innerHTML = `
      <div class="card glass"><h3>➕ Xodim yoki menejer qo'shish</h3>
        <div class="row" style="align-items:end">
          <label class="f"><span>Telegram ID, @username yoki telefon</span><input id="st-q" placeholder="123456789 yoki @username"></label>
          <label class="f"><span>Rol</span><select id="st-role"><option value="staff">👷 Xodim — buyurtmalarni qabul qiladi</option><option value="manager">👑 Menejer — to'liq boshqaruv</option></select></label>
          <div class="f"><button class="btn primary" id="st-add" style="width:100%">Qo'shish</button></div>
        </div>
        <div class="hint">Odam avval botga /start bosgan bo'lishi kerak (yoki aniq Telegram ID kiriting). Telegram ID ni @userinfobot orqali bilish mumkin.</div>
      </div>
      <div class="card glass table-wrap"><h3>👥 Jamoa</h3>
        <table class="t"><tr><th>Ism</th><th>Rol</th><th>ID</th><th></th></tr>
        ${d.admins.map((id) => `<tr><td>Bosh admin (.env)</td><td>👑 Menejer</td><td class="mono">${id}</td><td class="muted small">serverda o'zgaradi</td></tr>`).join("")}
        ${d.staff.filter((u) => !d.admins.includes(u.id)).map((u) => `<tr><td><b>${esc(u.full_name || u.first_name || "—")}</b> ${u.username ? "@" + esc(u.username) : ""}<div class="muted small">${esc(phone(u.phone))}</div></td>
          <td>${u.role === "manager" ? "👑 Menejer" : "👷 Xodim"}</td><td class="mono">${u.id}</td>
          <td class="right"><button class="btn sm danger" data-rm="${u.id}">Olib tashlash</button></td></tr>`).join("")}</table></div>`;
    $("#st-add", root).onclick = async () => {
      if (await run(() => api("staff", { method: "POST", body: { query: $("#st-q", root).value, role: $("#st-role", root).value } }), "Qo'shildi va unga xabar yuborildi")) route();
    };
    $$("[data-rm]", root).forEach((b) => (b.onclick = async () => {
      if (confirm("Bu odamdan huquq olib tashlansinmi?") && await run(() => api("staff/" + b.dataset.rm, { method: "DELETE" }), "Olib tashlandi")) route();
    }));
  };

  // ================= HISOBOT VA ZAXIRA =================
  PAGES.tools = async (root) => {
    root.innerHTML = `
      <div class="grid two">
        <div class="card glass"><h3>📥 Buyurtmalar hisoboti (Excel / CSV)</h3>
          <p class="muted small">Barcha buyurtmalar: mahsulotlar, summa, chegirma, mijoz, xodim, izoh. Excel'da ochiladi.</p>
          ${periodTabs("month", "data-exp")}
        </div>
        <div class="card glass"><h3>💾 Zaxira nusxa</h3>
          <p class="muted small">Butun baza (menyu, buyurtmalar, mijozlar, sozlamalar, matnlar) va yuklangan rasmlar bitta ZIP faylda.
            Har kuni 04:00 da bosh adminga Telegram orqali ham avtomatik yuboriladi.</p>
          <button class="btn primary" id="bk">💾 Zaxira nusxani yuklab olish</button>
        </div>
      </div>`;
    $$("[data-exp]", root).forEach((b) => (b.onclick = () => download("export.csv?period=" + b.dataset.exp)));
    $("#bk", root).onclick = () => download("backup");
  };

  boot();
})();
