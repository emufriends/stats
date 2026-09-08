// Shared card identity helpers for the reusable card-details route.
// The catalog is loaded from the existing card metadata CSV so every card
// already represented by the Cards page resolves to one canonical slug.

const CARD_ATTRIBUTES_URL = 'cards_attributes.csv';
let catalogPromise = null;

export function cardSlug(cardName) {
  return String(cardName || '')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

export function cardDetailsHref(cardName) {
  return `#/card-details/${encodeURIComponent(cardSlug(cardName))}`;
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = '';
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quoted) {
      if (char === '"' && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        field += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ',') {
      row.push(field);
      field = '';
    } else if (char === '\n') {
      row.push(field.replace(/\r$/, ''));
      rows.push(row);
      row = [];
      field = '';
    } else {
      field += char;
    }
  }
  if (field || row.length) {
    row.push(field.replace(/\r$/, ''));
    rows.push(row);
  }
  return rows;
}

export async function loadCardCatalog() {
  if (!catalogPromise) {
    catalogPromise = fetch(CARD_ATTRIBUTES_URL, { cache: 'no-cache' })
      .then(response => {
        if (!response.ok) throw new Error(`Could not load ${CARD_ATTRIBUTES_URL}`);
        return response.text();
      })
      .then(text => {
        const rows = parseCsv(text);
        const headers = rows.shift() || [];
        const nameIndex = headers.indexOf('Name');
        const typeIndex = headers.indexOf('Type');
        if (nameIndex < 0 || typeIndex < 0) throw new Error('Card catalog is missing Name or Type');
        return rows
          .map(row => ({ name: String(row[nameIndex] || '').trim(), type: String(row[typeIndex] || '').trim() }))
          .filter(card => card.name)
          .map(card => ({ ...card, slug: cardSlug(card.name) }));
      });
  }
  return catalogPromise;
}

export function cardSlugFromCurrentRoute() {
  const parts = window.location.hash.replace(/^#\/?/, '').split('/');
  if (parts[0] !== 'card-details' || !parts[1]) return '';
  try {
    return decodeURIComponent(parts[1]);
  } catch (_) {
    return parts[1];
  }
}

export function cardForSlug(catalog, slug) {
  return (catalog || []).find(card => card.slug === slug) || null;
}
