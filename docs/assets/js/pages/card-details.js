import {
  cardDetailsHref,
  cardForSlug,
  cardSlugFromCurrentRoute,
  loadCardCatalog,
} from '../card-catalog.js?v=20260908-card-details1';

export const id = 'card-details';
export const title = 'Card details';
export const navLabel = null;

export const mainHtml = `
  <div class="main-header card-details-main-header">
    <div class="table-meta">Card details</div>
  </div>
  <section class="card-details-shell" aria-labelledby="cardDetailsTitle">
    <div class="card-details-picker">
      <label for="cardDetailsSelect">Card</label>
      <select id="cardDetailsSelect" onchange="setCardDetailsSelection(this.value)">
        <option value="">Select a card</option>
      </select>
    </div>
    <div class="card-details-placeholder" id="cardDetailsPlaceholder">
      <h1 id="cardDetailsTitle">Card details</h1>
      <p>Card-specific statistics and information will be added here.</p>
    </div>
  </section>`;

export const sidebarHtml = `
  <div class="sidebar-header">
    <span class="sidebar-title">Filters</span>
    <button class="sidebar-close-btn" onclick="toggleSidebar()" title="Close filters">x</button>
  </div>
  <hr class="divider" />
  <div class="card-details-sidebar-placeholder">
    Card-specific filters will be added here.
  </div>`;

let mounted = false;
let catalog = [];
let loadToken = 0;

export function mount() {
  mounted = true;
  window.setCardDetailsSelection = slug => {
    const card = cardForSlug(catalog, slug);
    window.location.hash = card ? cardDetailsHref(card.name) : '#/card-details';
  };
  const token = ++loadToken;
  renderCardDetails();
  loadCardCatalog()
    .then(cards => {
      if (!mounted || token !== loadToken) return;
      catalog = cards;
      renderCardDetails();
    })
    .catch(error => {
      if (!mounted || token !== loadToken) return;
      const placeholder = document.getElementById('cardDetailsPlaceholder');
      if (placeholder) placeholder.innerHTML = `<h1 id="cardDetailsTitle">Card details</h1><p>Could not load the card catalog: ${escapeHtml(error.message || error)}</p>`;
    });
}

export function unmount() {
  mounted = false;
  loadToken += 1;
  delete window.setCardDetailsSelection;
}

function renderCardDetails() {
  const select = document.getElementById('cardDetailsSelect');
  const placeholder = document.getElementById('cardDetailsPlaceholder');
  if (!select || !placeholder) return;
  const slug = cardSlugFromCurrentRoute();
  const selected = cardForSlug(catalog, slug);
  select.innerHTML = `<option value="">Select a card</option>${catalog.map(card => `<option value="${escapeAttr(card.slug)}">${escapeHtml(card.name)}</option>`).join('')}`;
  select.value = selected?.slug || '';
  if (!selected) {
    placeholder.innerHTML = '<h1 id="cardDetailsTitle">Card details</h1><p>Select a card to open its detail page.</p>';
    return;
  }
  placeholder.innerHTML = `<div class="card-details-type">${escapeHtml(selected.type)}</div><h1 id="cardDetailsTitle">${escapeHtml(selected.name)}</h1><p>Card-specific statistics and information will be added here.</p>`;
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
  }[char]));
}

function escapeAttr(value) {
  return escapeHtml(value);
}
