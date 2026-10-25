// Yealink contacts card: search the phonebook, tap a number to dial it on the desk phone.
// Served and auto-loaded by the yealink integration, no resource to add.
//
// type: custom:yealink-contacts-card
// title: Contacts          (optional)
// config_entry_id: abc123  (optional, only needed with several phones)
// max_height: 420px        (optional, list scrolls beyond this)

const REFRESH_MS = 10 * 60 * 1000;

// case and accent insensitive: "muller" finds "Müller"
const fold = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const digits = (s) => s.replace(/[^\d]/g, "");

class YealinkContactsCard extends HTMLElement {
  setConfig(config) {
    this._config = { title: "Contacts", max_height: "420px", ...config };
    this._query = "";
    if (this._root) this._build();
  }

  static getStubConfig() {
    return {};
  }

  getCardSize() {
    return 6;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: 6, min_rows: 4 };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._root) {
      this._root = this.attachShadow({ mode: "open" });
      this._build();
    }
    if (!this._people && !this._loading) this._load();
    this._renderCall();
  }

  connectedCallback() {
    this._timer = setInterval(() => this._load(), REFRESH_MS);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
  }

  async _load() {
    if (!this._hass) return;
    this._loading = true;
    try {
      const { phones } = await this._hass.connection.sendMessagePromise({ type: "yealink/contacts" });
      const wanted = this._config.config_entry_id;
      const phone = wanted ? phones.find((p) => p.entry_id === wanted) : phones[0];
      if (!phone) {
        this._error = wanted ? `No Yealink phone with config_entry_id ${wanted}` : "No Yealink phone set up";
      } else if (!phone.phonebook) {
        this._error = "No phonebook URL set (Yealink integration → Configure)";
      } else {
        this._error = phones.length > 1 && !wanted ? "Several phones: set config_entry_id in the card" : null;
        this._phone = phone;
        this._people = this._group(phone.contacts);
      }
    } catch (err) {
      this._error = `Can't load contacts: ${err.message || err}`;
    }
    this._loading = false;
    this._renderList();
    this._renderCall();
  }

  // one row per person, their numbers as buttons; contacts arrive sorted by name
  _group(contacts) {
    const people = new Map();
    for (const c of contacts) {
      if (!people.has(c.name)) people.set(c.name, { name: c.name, words: fold(c.name).split(/\s+/), numbers: [] });
      people.get(c.name).numbers.push({ kind: c.kind, number: c.number, digits: digits(c.number) });
    }
    return [...people.values()];
  }

  _build() {
    this._root.innerHTML = `
      <style>
        ha-card { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
        .head { display: flex; align-items: center; gap: 8px; padding: 12px 16px 8px; }
        .title { flex: 1; font-size: 20px; font-weight: 500; color: var(--primary-text-color); }
        .count { color: var(--secondary-text-color); font-size: 13px; }
        .search { margin: 0 16px 8px; position: relative; }
        .search input {
          box-sizing: border-box; width: 100%; padding: 10px 12px 10px 38px; font: inherit; font-size: 15px;
          color: var(--primary-text-color); background: var(--secondary-background-color, #f2f2f2);
          border: 1px solid transparent; border-radius: 10px; outline: none;
        }
        .search input:focus { border-color: var(--primary-color); }
        .search ha-icon { position: absolute; left: 10px; top: 50%; transform: translateY(-50%);
          --mdc-icon-size: 20px; color: var(--secondary-text-color); }
        .call { display: none; align-items: center; gap: 12px; margin: 0 16px 8px; padding: 8px 8px 8px 14px;
          border-radius: 10px; background: var(--success-color, #43a047); color: #fff; }
        .call.on { display: flex; }
        .call.ringing { background: var(--warning-color, #ffa600); }
        .call .what { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .hangup { border: 0; border-radius: 50%; width: 36px; height: 36px; cursor: pointer;
          background: var(--error-color, #db4437); color: #fff; display: grid; place-items: center; }
        .list { overflow-y: auto; padding: 0 8px 8px; flex: 1; }
        .person { display: flex; align-items: center; gap: 12px; padding: 8px; border-radius: 10px; }
        .person:hover { background: var(--secondary-background-color); }
        .avatar { flex: none; width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center;
          font-weight: 500; color: var(--text-primary-color, #fff); background: var(--primary-color); }
        .info { flex: 1; min-width: 0; }
        .name { color: var(--primary-text-color); font-size: 15px;
          overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .nums { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
        .num { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px 4px 8px; font: inherit;
          font-size: 13px; cursor: pointer; border-radius: 16px; color: var(--primary-text-color);
          border: 1px solid var(--divider-color); background: var(--card-background-color); }
        .num:hover { border-color: var(--primary-color); color: var(--primary-color); }
        .num:disabled { opacity: .5; cursor: progress; }
        .num ha-icon { --mdc-icon-size: 16px; color: var(--primary-color); }
        .kind { font-weight: 500; }
        .nr { color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
        .msg { padding: 16px; color: var(--secondary-text-color); text-align: center; }
        .msg.err { color: var(--error-color); }
        .toast { min-height: 0; padding: 0 16px; font-size: 13px; color: var(--secondary-text-color); }
      </style>
      <ha-card>
        <div class="head"><div class="title"></div><div class="count"></div></div>
        <div class="search">
          <ha-icon icon="mdi:magnify"></ha-icon>
          <input type="search" placeholder="Search name or number" autocomplete="off" />
        </div>
        <div class="call"><ha-icon icon="mdi:phone"></ha-icon><div class="what"></div>
          <button class="hangup" title="Hang up"><ha-icon icon="mdi:phone-hangup"></ha-icon></button></div>
        <div class="toast"></div>
        <div class="list"></div>
      </ha-card>`;
    const $ = (s) => this._root.querySelector(s);
    $(".title").textContent = this._config.title;
    $(".list").style.maxHeight = this._config.max_height;
    const input = $("input");
    input.value = this._query;
    input.addEventListener("input", () => {
      this._query = input.value;
      this._renderList();
    });
    // Enter dials when exactly one number is left
    input.addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter") return;
      const hits = this._matches();
      if (hits.length === 1 && hits[0].numbers.length === 1) this._dial(hits[0], hits[0].numbers[0]);
    });
    $(".hangup").addEventListener("click", () => this._service("hangup", {}));
    this._renderList();
  }

  _matches() {
    const q = fold(this._query.trim());
    if (!q) return this._people;
    // every typed word starts a word of the name: "max web" finds "Dr. Max Peter Weber", "oma" not "Roma"
    const words = q.split(/\s+/);
    // leading 0 dropped so "0761" also finds "+49761..."
    const qd = digits(q).replace(/^0+/, "");
    return this._people.filter(
      (p) =>
        words.every((w) => p.words.some((pw) => pw.startsWith(w))) ||
        (qd.length >= 3 && p.numbers.some((n) => n.digits.includes(qd)))
    );
  }

  _renderList() {
    if (!this._root) return;
    const list = this._root.querySelector(".list");
    const count = this._root.querySelector(".count");
    list.replaceChildren();
    if (this._error && !this._people) {
      list.append(this._msg(this._error, true));
      return;
    }
    if (!this._people) {
      list.append(this._msg("Loading…"));
      return;
    }
    const hits = this._matches();
    count.textContent = this._query ? `${hits.length} / ${this._people.length}` : `${this._people.length}`;
    if (this._error) list.append(this._msg(this._error, true));
    if (!hits.length) list.append(this._msg("No match"));
    for (const p of hits) list.append(this._row(p));
  }

  _row(person) {
    const row = document.createElement("div");
    row.className = "person";
    const avatar = document.createElement("div");
    avatar.className = "avatar";
    // first + last name, titles like "Dr." skipped
    const initials = person.name.split(/\s+/).filter((w) => /^\p{L}/u.test(w) && !w.endsWith("."));
    avatar.textContent =
      [initials[0], initials.length > 1 ? initials.at(-1) : ""].map((w) => w?.[0]?.toUpperCase() ?? "").join("") ||
      "#";
    const info = document.createElement("div");
    info.className = "info";
    const name = document.createElement("div");
    name.className = "name";
    name.textContent = person.name;
    name.title = person.name;
    const nums = document.createElement("div");
    nums.className = "nums";
    for (const n of person.numbers) {
      const b = document.createElement("button");
      b.className = "num";
      b.title = `Call ${person.name}${n.kind ? ` (${n.kind})` : ""}`;
      b.innerHTML = `<ha-icon icon="mdi:phone"></ha-icon>`;
      if (n.kind) {
        const k = document.createElement("span");
        k.className = "kind";
        k.textContent = n.kind;
        b.append(k);
      }
      const nr = document.createElement("span");
      nr.className = "nr";
      nr.textContent = n.number;
      b.append(nr);
      b.addEventListener("click", async () => {
        b.disabled = true;
        await this._dial(person, n);
        b.disabled = false;
      });
      nums.append(b);
    }
    info.append(name, nums);
    row.append(avatar, info);
    return row;
  }

  _msg(text, err = false) {
    const d = document.createElement("div");
    d.className = err ? "msg err" : "msg";
    d.textContent = text;
    return d;
  }

  async _dial(person, n) {
    const who = `${person.name}${n.kind ? ` (${n.kind})` : ""}`;
    if (await this._service("dial", { number: n.number })) this._toast(`Calling ${who}…`);
  }

  async _service(name, data) {
    try {
      await this._hass.callService("yealink", name, { ...data, config_entry_id: this._phone?.entry_id });
      return true;
    } catch (err) {
      this._toast(err.message || String(err), true);
      return false;
    }
  }

  _toast(text, err = false) {
    const t = this._root.querySelector(".toast");
    t.textContent = text;
    t.style.color = err ? "var(--error-color)" : "";
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => (t.textContent = ""), 4000);
  }

  // live call bar with hang-up, from this phone's call_state sensor
  _renderCall() {
    if (!this._root || !this._phone) return;
    const bar = this._root.querySelector(".call");
    const find = (key) =>
      Object.values(this._hass.entities || {}).find(
        (e) =>
          e.platform === "yealink" &&
          e.translation_key === key &&
          this._hass.devices?.[e.device_id]?.config_entries?.includes(this._phone.entry_id)
      )?.entity_id;
    const state = this._hass.states[find("call_state")]?.state;
    const caller = this._hass.states[find("last_caller")]?.state;
    const on = state && state !== "idle" && state !== "unavailable" && state !== "unknown";
    bar.classList.toggle("on", !!on);
    bar.classList.toggle("ringing", state === "ringing");
    if (on) {
      const label = { ringing: "Ringing", dialing: "Dialing", active: "In call" }[state] || state;
      bar.querySelector(".what").textContent =
        state === "ringing" && caller ? `${label}: ${caller}` : label;
    }
  }
}

if (!customElements.get("yealink-contacts-card")) {
  customElements.define("yealink-contacts-card", YealinkContactsCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "yealink-contacts-card",
    name: "Yealink contacts",
    description: "Search the phonebook and dial on the Yealink phone",
    preview: false,
  });
}
