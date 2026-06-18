// Shared picks storage + card rendering used by both the picker page and the
// search page's right sidebar. Picks live in localStorage under
// `fabric-colors:picks` as [{hex, name}, ...] (with migration from the legacy
// bare-hex format). Mutations dispatch a `picks-changed` window event so all
// listeners (e.g. the index page's sidebar) stay in sync.
(function (global) {
  const STORAGE_KEY = 'fabric-colors:picks';
  const HISTORY_KEY = 'fabric-colors:history';
  const HISTORY_MAX = 100;

  function load() {
    try {
      const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
      return raw.map(p => (typeof p === 'string' ? { hex: p, name: '' } : p));
    } catch (_) { return []; }
  }
  function save(picks, { silent = false } = {}) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(picks));
    // Skip the broadcast for in-place edits (e.g. typing in a name field) so
    // listeners don't re-render the list and yank the input out from under
    // the cursor.
    if (!silent) window.dispatchEvent(new CustomEvent('picks-changed'));
  }
  function add(hex, max) {
    let picks = load().filter(p => p.hex !== hex);
    picks.unshift({ hex, name: '' });
    if (max && picks.length > max) picks = picks.slice(0, max);
    save(picks);
  }
  function remove(hex) {
    save(load().filter(p => p.hex !== hex));
  }
  function clear() {
    localStorage.removeItem(STORAGE_KEY);
    window.dispatchEvent(new CustomEvent('picks-changed'));
  }
  function pushHistory(entry) {
    let entries = [];
    try { entries = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); }
    catch (_) {}
    entries = entries.filter(e => e.hex !== entry.hex);
    entries.unshift(entry);
    if (entries.length > HISTORY_MAX) entries = entries.slice(0, HISTORY_MAX);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(entries));
    window.dispatchEvent(new CustomEvent('history-changed'));
  }
  function renameHistory(hex, name) {
    let entries = [];
    try { entries = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); }
    catch (_) {}
    let changed = false;
    for (const e of entries) {
      if (e.hex === hex) { e.name = name; changed = true; }
    }
    if (changed) {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(entries));
      window.dispatchEvent(new CustomEvent('history-changed'));
    }
  }

  function createCard(pick) {
    const card = document.createElement('div');
    card.className = 'card pick';
    card.dataset.hex = pick.hex;

    const swatch = document.createElement('a');
    swatch.className = 'swatch';
    swatch.style.background = pick.hex;
    swatch.href = '/?color=' + encodeURIComponent(pick.hex);
    swatch.dataset.hex = pick.hex;
    swatch.dataset.name = pick.name || '';
    swatch.title = 'Find similar colors';
    swatch.addEventListener('click', () => {
      pushHistory({ hex: pick.hex, name: pick.name || pick.hex, brand: '' });
    });

    const meta = document.createElement('div');
    meta.className = 'pick-meta';
    const nameInput = document.createElement('input');
    nameInput.className = 'pick-name';
    nameInput.type = 'text';
    nameInput.placeholder = 'Add a name…';
    nameInput.value = pick.name || '';
    nameInput.addEventListener('input', () => {
      const list = load();
      const entry = list.find(x => x.hex === pick.hex);
      if (entry) {
        entry.name = nameInput.value;
        save(list, { silent: true });
        swatch.dataset.name = nameInput.value;
      }
    });
    // Only push the rename into history once the user is done editing —
    // updating on every keystroke would re-render the history sidebar
    // continuously. `change` fires on blur (incl. Enter → blur below).
    nameInput.addEventListener('change', () => {
      renameHistory(pick.hex, nameInput.value);
    });
    nameInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); nameInput.blur(); }
    });
    const hexLine = document.createElement('button');
    hexLine.type = 'button';
    hexLine.className = 'hex';
    hexLine.textContent = pick.hex;
    hexLine.title = 'Copy hex code';
    // Click the hex to copy it to the clipboard. Briefly flash "Copied" as
    // feedback, then restore the code. Falls back silently if the Clipboard
    // API is unavailable (e.g. non-secure context).
    hexLine.addEventListener('click', () => {
      const restore = () => { hexLine.textContent = pick.hex; };
      const flash = () => {
        hexLine.textContent = 'Copied!';
        hexLine.classList.add('copied');
        setTimeout(() => { restore(); hexLine.classList.remove('copied'); }, 900);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(pick.hex).then(flash).catch(() => {});
      }
    });
    meta.append(nameInput, hexLine);

    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'pick-remove';
    removeBtn.setAttribute('aria-label', 'Remove pick');
    removeBtn.innerHTML = '&times;';
    removeBtn.addEventListener('click', () => remove(pick.hex));

    card.append(swatch, meta, removeBtn);
    return card;
  }

  global.Picks = { load, save, add, remove, clear, createCard, pushHistory, renameHistory };
})(window);
