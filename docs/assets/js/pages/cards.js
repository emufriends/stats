export const id = 'cards';
import {
  cappedNumericRange,
  deltaRangeColor,
  numericRange,
  playrateColor,
  relativeEloColor,
} from '../color-scales.js?v=20260704-9';

export const title = 'Cards';
export const navLabel = 'Cards';
export const mainHtml = "<!--\n      Main table controls.\n      Desktop/tablet: meta left, Minimum plays + Rows controls right.\n      Phone: compact single row. Card search lives inside the Card table header.\n    -->\n    <div class=\"main-header\">\n      <div class=\"table-meta\" id=\"tableMeta\"></div>\n      <div class=\"main-controls\">\n        <!-- Frontend-only Minimum plays filter.\n             Empty value = no minimum. It filters by n_played immediately via onMinPlaysInput().\n             The blank placeholder is intentional; CSS draws the centred dash. -->\n        <div class=\"min-plays-wrap\">\n          <label class=\"min-plays-label\" for=\"minPlayedInput\"><span class=\"min-plays-label-full\">Minimum plays</span><span class=\"min-plays-label-short\">Min plays</span></label>\n          <input class=\"min-plays-input\" type=\"number\" id=\"minPlayedInput\" placeholder=\" \" min=\"0\" inputmode=\"numeric\" oninput=\"onMinPlaysInput()\" />\n        </div>\n        <div class=\"rpp-wrap\">\n          Rows\n          <select class=\"rpp-select\" id=\"rppSelect\" onchange=\"onRppChange()\">\n            <option value=\"25\">25</option>\n            <option value=\"50\" selected>50</option>\n            <option value=\"100\">100</option>\n            <option value=\"9999\">All</option>\n          </select>\n        </div>\n      </div>\n    </div>\n\n    <!-- Attributes bar\n         Client-side-only card metadata filters (Species, Habitat, Strength,\n         Size, Reefer, Aviary, Abilities). Reads cards_attributes.csv, looked\n         up by card_name. Filtering is layered into applySearch() exactly like\n         the Type filter \u2014 no backend call, instant results.\n         Collapsible, collapsed by default.\n\n         Important maintenance notes:\n         - Conditions still exists in cards_attributes.csv, but is intentionally\n           NOT exposed in the UI and is not read by the frontend.\n         - Species and Habitat are separate filters, not a combined OR group.\n         - Rock/Water/Science are boolean \"only cards with this tag\" toggles.\n         - Strength/Science are Sponsor-only; Size/Reefer/Aviary/Abilities are\n           Animal-only. Availability is controlled in ATTR_RELEVANT_TYPES. -->\n    <div class=\"attributes-bar collapsed\" id=\"attributesBar\">\n      <div class=\"attributes-bar-header\" onclick=\"toggleAttributesBar()\">\n        <div class=\"attributes-bar-title\">\n          Attributes\n        </div>\n        <div class=\"attributes-bar-actions\">\n          <button class=\"attributes-reset-btn\" onclick=\"resetAttributesFromHeader(event)\">Reset</button>\n          <span class=\"attributes-bar-chevron\">&#9662;</span>\n        </div>\n      </div>\n      <div class=\"attributes-bar-body\" id=\"attributesBarBody\">\n\n        <!-- Species and Habitat are separate include-list filters.\n             Both are disabled and reset when Type is Project-only.\n             Do not merge these back into one Tags control unless Panda asks:\n             user testing specifically preferred them split. -->\n        <div class=\"attr-group\" id=\"attrGroupSpecies\" data-attr-group=\"species\">\n          <span class=\"attr-group-label\">Species</span>\n          <button class=\"attr-tags-btn\" id=\"speciesBtn\" onclick=\"toggleTagPopup('species', event)\">\n            <span id=\"speciesBtnLabel\">All</span>\n            <span class=\"attr-tags-indicator\" id=\"speciesBtnIndicator\"></span>\n          </button>\n        </div>\n\n        <div class=\"attr-group\" id=\"attrGroupContinent\" data-attr-group=\"continent\">\n          <span class=\"attr-group-label\">Habitat</span>\n          <button class=\"attr-tags-btn\" id=\"continentBtn\" onclick=\"toggleTagPopup('continent', event)\">\n            <span id=\"continentBtnLabel\">All</span>\n            <span class=\"attr-tags-indicator\" id=\"continentBtnIndicator\"></span>\n          </button>\n        </div>\n\n        <div class=\"attr-separator\" aria-hidden=\"true\"></div>\n\n        <!-- Rock / Water / Science: simple yes/no toggles, default OFF (no filtering).\n             Switching ON narrows to \"only cards that have this tag\".\n             Rock/Water appear on Animal and Sponsor; Science only on Sponsor. -->\n        <div class=\"attr-group\" id=\"attrGroupRock\" data-attr-group=\"rock\">\n          <span class=\"attr-group-label\">Rock</span>\n          <div class=\"attr-toggle-row\">\n            <label class=\"toggle\">\n              <input type=\"checkbox\" id=\"rockToggle\" onchange=\"onBoolTagToggle('rock')\" />\n              <span class=\"toggle-track\"></span>\n            </label>\n          </div>\n        </div>\n\n        <div class=\"attr-group\" id=\"attrGroupWater\" data-attr-group=\"water\">\n          <span class=\"attr-group-label\">Water</span>\n          <div class=\"attr-toggle-row\">\n            <label class=\"toggle\">\n              <input type=\"checkbox\" id=\"waterToggle\" onchange=\"onBoolTagToggle('water')\" />\n              <span class=\"toggle-track\"></span>\n            </label>\n          </div>\n        </div>\n\n        <div class=\"attr-separator\" aria-hidden=\"true\"></div>\n\n        <div class=\"attr-group\" id=\"attrGroupScience\" data-attr-group=\"science\">\n          <span class=\"attr-group-label\">Science</span>\n          <div class=\"attr-toggle-row\">\n            <label class=\"toggle\">\n              <input type=\"checkbox\" id=\"scienceToggle\" onchange=\"onBoolTagToggle('science')\" />\n              <span class=\"toggle-track\"></span>\n            </label>\n          </div>\n        </div>\n\n        <div class=\"attr-separator\" aria-hidden=\"true\"></div>\n\n        <!-- Strength: 3/4/5/6 chips. Sponsor-only attribute.\n             Disabled unless Sponsor is active in the Type filter.\n             Narrowing this (away from all-selected) forces Type to Sponsor-only. -->\n        <div class=\"attr-group\" id=\"attrGroupStrength\" data-attr-group=\"strength\">\n          <div class=\"attr-group-heading\">\n            <span class=\"attr-group-label\">Strength</span>\n            <span class=\"attr-group-actions\">\n              (<span class=\"map-toggle-link\" onclick=\"selectAllAttributeValues('strength')\">all</span> / <span class=\"map-toggle-link\" onclick=\"selectNoneAttributeValues('strength')\">none</span>)\n            </span>\n          </div>\n          <div class=\"attr-chip-row\" id=\"strengthChips\"></div>\n        </div>\n\n        <div class=\"attr-separator\" aria-hidden=\"true\"></div>\n\n        <!-- Size: 1/2/3/4/5 chips. Animal-only attribute.\n             Disabled unless Animal is active in the Type filter.\n             Narrowing this forces Type to Animal-only. -->\n        <div class=\"attr-group\" id=\"attrGroupSize\" data-attr-group=\"size\">\n          <div class=\"attr-group-heading\">\n            <span class=\"attr-group-label\">Size</span>\n            <span class=\"attr-group-actions\">\n              (<span class=\"map-toggle-link\" onclick=\"selectAllAttributeValues('size')\">all</span> / <span class=\"map-toggle-link\" onclick=\"selectNoneAttributeValues('size')\">none</span>)\n            </span>\n          </div>\n          <div class=\"attr-chip-row\" id=\"sizeChips\"></div>\n        </div>\n\n        <div class=\"attr-separator\" aria-hidden=\"true\"></div>\n\n        <!-- Reefer: yes/no toggle, default No (off, not filtering).\n             Animal-only attribute. Disabled unless Animal is active in Type.\n             Turning ON forces Type to Animal-only, remembering whatever Type\n             selection was active immediately before (shared with Aviary).\n             Turning OFF restores that remembered Type \u2014 unless Aviary is still\n             ON, in which case Type stays Animal-only until both are off. -->\n        <div class=\"attr-group\" id=\"attrGroupReefer\" data-attr-group=\"reefer\">\n          <span class=\"attr-group-label\">Reefer</span>\n          <div class=\"attr-toggle-row\">\n            <label class=\"toggle\">\n              <input type=\"checkbox\" id=\"reeferToggle\" onchange=\"onReeferAviaryToggle('reefer')\" />\n              <span class=\"toggle-track\"></span>\n            </label>\n          </div>\n        </div>\n\n        <!-- Aviary: same pattern as Reefer, sharing the same remembered-Type slot. -->\n        <div class=\"attr-group\" id=\"attrGroupAviary\" data-attr-group=\"aviary\">\n          <span class=\"attr-group-label\">Aviary</span>\n          <div class=\"attr-toggle-row\">\n            <label class=\"toggle\">\n              <input type=\"checkbox\" id=\"aviaryToggle\" onchange=\"onReeferAviaryToggle('aviary')\" />\n              <span class=\"toggle-track\"></span>\n            </label>\n          </div>\n        </div>\n\n        <div class=\"attr-separator\" aria-hidden=\"true\"></div>\n\n        <!-- Abilities: searchable multi-select checklist, alphabetical, OR logic.\n             Animal-only attribute. Disabled unless Animal is active in Type. -->\n        <div class=\"attr-group\" id=\"attrGroupAbilities\" data-attr-group=\"abilities\">\n          <span class=\"attr-group-label\">Abilities</span>\n          <div class=\"abilities-dropdown\">\n            <button class=\"abilities-dropdown-btn\" id=\"abilitiesBtn\" onclick=\"toggleAbilitiesPanel(event)\">\n              <span id=\"abilitiesBtnLabel\">All</span>\n              <span class=\"attr-tags-indicator\" id=\"abilitiesBtnIndicator\"></span>\n            </button>\n            <div class=\"abilities-panel\" id=\"abilitiesPanel\" onclick=\"event.stopPropagation()\">\n              <input class=\"abilities-search-input\" type=\"text\" id=\"abilitiesSearchInput\"\n                     placeholder=\"Search abilities...\" oninput=\"renderAbilitiesList()\" />\n              <div class=\"abilities-actions\">\n                <span class=\"map-toggle-link\" onclick=\"selectAllAbilities()\">all</span> /\n                <span class=\"map-toggle-link\" onclick=\"selectNoneAbilities()\">none</span>\n              </div>\n              <div class=\"abilities-list\" id=\"abilitiesList\"></div>\n            </div>\n          </div>\n        </div>\n\n      </div>\n    </div>\n\n    <!-- Tag popup overlay: reused by Species and Habitat.\n         The popup content is generated from currentTagPopupKind, so there is\n         only one modal in the DOM for both controls. -->\n    <div class=\"tags-popup-overlay\" id=\"tagPopupOverlay\" onclick=\"closeTagPopupOnOverlay(event)\">\n      <div class=\"tags-popup\" onclick=\"event.stopPropagation()\">\n        <div class=\"tags-popup-header\">\n          <span class=\"tags-popup-title\" id=\"tagPopupTitle\">Species</span>\n          <div class=\"tags-popup-actions\">\n            <span class=\"map-toggle-link\" onclick=\"selectAllCurrentTagPopup()\">all</span> /\n            <span class=\"map-toggle-link\" onclick=\"selectNoneCurrentTagPopup()\">none</span>\n          </div>\n        </div>\n\n        <div class=\"tags-popup-section\">\n          <div class=\"tags-popup-chips\" id=\"tagPopupChips\"></div>\n        </div>\n\n        <button class=\"tags-popup-close-btn\" onclick=\"closeTagPopup()\">Done</button>\n      </div>\n    </div>\n\n    <div class=\"table-wrap\">\n      <div class=\"table-scroll\">\n      <table id=\"statsTable\">\n        <thead>\n          <tr>\n            <th style=\"width:5%;text-align:center;cursor:default;\">#</th>\n            <th class=\"card-search-header\" onclick=\"sortBy('card_name')\" style=\"width:20%;text-align:center\">\n              <div class=\"card-header-content\" id=\"cardHeaderContent\">\n                <button class=\"card-search-btn\" id=\"cardSearchBtn\" onclick=\"openCardSearch(event)\" title=\"Search cards\" aria-label=\"Search cards\">&#128269;</button>\n                <span class=\"card-header-title\">Card</span>\n                <span class=\"sort-arrow\" id=\"sort-card_name\">&#8597;</span>\n              </div>\n              <div class=\"card-header-search\" id=\"cardHeaderSearch\" onclick=\"event.stopPropagation()\">\n                <span class=\"card-header-search-icon\">&#128269;</span>\n                <input class=\"card-header-search-input\" type=\"text\" id=\"searchInput\" placeholder=\"Search...\" oninput=\"onSearch()\" />\n                <button class=\"card-search-close\" onclick=\"closeCardSearch(event)\" title=\"Clear search\" aria-label=\"Clear search\">x</button>\n              </div>\n            </th>\n            <th onclick=\"sortBy('delta_played')\" style=\"width:12%;text-align:center\">&Delta; (Played)<span class=\"col-tip\" data-tip=\"average elo gain when played\">?</span><span class=\"sort-arrow\" id=\"sort-delta_played\">&#8597;</span></th>\n            <th onclick=\"sortBy('delta_in_hand')\" style=\"width:12%;text-align:center\">&Delta; (In Hand)<span class=\"col-tip\" data-tip=\"average elo gain when in hand\">?</span><span class=\"sort-arrow\" id=\"sort-delta_in_hand\">&#8597;</span></th>\n            <th onclick=\"sortBy('avg_elo')\" style=\"width:8%;text-align:center\">Elo<span class=\"col-tip\" data-tip=\"average player elo when played\">?</span><span class=\"sort-arrow\" id=\"sort-avg_elo\">&#8597;</span></th>\n            <th onclick=\"sortBy('playrate_pct')\" style=\"width:13%;text-align:center\">Playrate <span class=\"col-tip\" data-tip-fraction>?</span><span class=\"sort-arrow\" id=\"sort-playrate_pct\">&#8597;</span></th>\n            <th onclick=\"sortBy('n_played')\" style=\"width:10%;text-align:center\">Played<span class=\"col-tip\" data-tip-played>?</span><span class=\"sort-arrow\" id=\"sort-n_played\">&#8597;</span></th>\n            <th onclick=\"sortBy('n_seen')\" style=\"width:10%;text-align:center\">Seen<span class=\"col-tip\" data-tip-seen>?</span><span class=\"sort-arrow\" id=\"sort-n_seen\">&#8597;</span></th>\n            <th class=\"type-filter-header\" id=\"typeFilterHeader\" style=\"width:10%;text-align:center;cursor:pointer;\" onclick=\"toggleTypeFilterPopup(event)\">\n              <span class=\"type-filter-label\">Type <span class=\"type-filter-indicator type-filter-icon\" id=\"typeFilterIndicator\"></span></span>\n              <div class=\"type-filter-popup\" id=\"typeFilterPopup\">\n                <button class=\"chip active\" data-value=\"animal\" onclick=\"toggleTypeChip(this)\">Animal</button>\n                <button class=\"chip active\" data-value=\"sponsor\" onclick=\"toggleTypeChip(this)\">Sponsor</button>\n                <button class=\"chip active\" data-value=\"project\" onclick=\"toggleTypeChip(this)\">Project</button>\n              </div>\n            </th>\n          </tr>\n        </thead>\n        <tbody id=\"tableBody\">\n          <tr><td colspan=\"9\">\n            <div class=\"state-overlay\">\n              <div class=\"spinner\"></div>\n              <div class=\"state-title\">Preparing data...</div>\n              <div class=\"state-sub\">Loading the latest available card statistics.</div>\n            </div>\n          </td></tr>\n        </tbody>\n      </table>\n      </div>\n      <div class=\"pagination\" id=\"pagination\" style=\"display:none;\"></div>\n    </div>";
export const sidebarHtml = "\u003cdiv class=\"sidebar-header\"\u003e\n      \u003cspan class=\"sidebar-title\"\u003eFilters\u003c/span\u003e\n      \u003cdiv style=\"display:flex;align-items:center;gap:6px;\"\u003e\n        \u003cbutton class=\"reset-btn\" onclick=\"resetFilters()\"\u003eReset\u003c/button\u003e\n        \u003cbutton class=\"sidebar-close-btn\" onclick=\"toggleSidebar()\" title=\"Close filters\"\u003ex\u003c/button\u003e\n      \u003c/div\u003e\n    \u003c/div\u003e\n\n    \u003chr class=\"divider\" /\u003e\n\n    \u003c!-- Player ELO --\u003e\n    \u003cdiv class=\"filter-group\"\u003e\n      \u003cspan class=\"filter-label\"\u003ePlayer ELO\u003c/span\u003e\n      \u003cdiv class=\"range-row\"\u003e\n        \u003cinput class=\"range-input\" type=\"number\" id=\"playerEloMin\" placeholder=\"Min\" value=\"300\" min=\"0\" /\u003e\n        \u003cinput class=\"range-input\" type=\"number\" id=\"playerEloMax\" placeholder=\"Max\" min=\"0\" /\u003e\n      \u003c/div\u003e\n    \u003c/div\u003e\n\n    \u003c!-- Opponent ELO --\u003e\n    \u003cdiv class=\"filter-group\"\u003e\n      \u003cspan class=\"filter-label\"\u003eOpponent ELO\u003c/span\u003e\n      \u003cdiv class=\"range-row\"\u003e\n        \u003cinput class=\"range-input\" type=\"number\" id=\"opponentEloMin\" placeholder=\"Min\" value=\"300\" min=\"0\" /\u003e\n        \u003cinput class=\"range-input\" type=\"number\" id=\"opponentEloMax\" placeholder=\"Max\" min=\"0\" /\u003e\n      \u003c/div\u003e\n    \u003c/div\u003e\n\n    \u003chr class=\"divider\" /\u003e\n\n    \u003c!-- Maps --\u003e\n    \u003cdiv class=\"filter-group\"\u003e\n      \u003cdiv style=\"display:flex;align-items:baseline;gap:6px;margin-bottom:8px;\"\u003e\n        \u003cspan class=\"filter-label\" style=\"margin-bottom:0\"\u003eMaps\u003c/span\u003e\n        \u003cspan class=\"map-select-all-none\"\u003e\n          (\u003cspan class=\"map-toggle-link\" onclick=\"selectAllMaps()\"\u003eall\u003c/span\u003e / \u003cspan class=\"map-toggle-link\" onclick=\"selectNoneMaps()\"\u003enone\u003c/span\u003e)\n        \u003c/span\u003e\n      \u003c/div\u003e\n      \u003cdiv class=\"chip-grid\" id=\"mapChips\"\u003e\u003c/div\u003e\n    \u003c/div\u003e\n\n    \u003chr class=\"divider\" /\u003e\n\n    \u003c!-- Round filter\n         All six chips active = default/no round filter.\n         Selecting only some chips re-queries the backend for cards played in those rounds.\n         Selecting no chips is allowed; applyFilters() catches that locally and renders an\n         empty table without calling the backend. This mirrors Maps none behaviour. --\u003e\n    \u003cdiv class=\"filter-group\"\u003e\n      \u003cdiv style=\"display:flex;align-items:baseline;gap:6px;margin-bottom:8px;\"\u003e\n        \u003cspan class=\"filter-label\" style=\"margin-bottom:0\"\u003eRound\u003c/span\u003e\n        \u003cspan class=\"map-select-all-none\"\u003e\n          (\u003cspan class=\"map-toggle-link\" onclick=\"selectAllRounds()\"\u003eall\u003c/span\u003e / \u003cspan class=\"map-toggle-link\" onclick=\"selectNoneRounds()\"\u003enone\u003c/span\u003e)\n        \u003c/span\u003e\n      \u003c/div\u003e\n      \u003cdiv class=\"chip-grid\" id=\"roundChips\"\u003e\u003c/div\u003e\n    \u003c/div\u003e\n\n    \u003chr class=\"divider\" /\u003e\n\n    \u003c!-- Date range --\u003e\n    \u003cdiv class=\"filter-group\"\u003e\n      \u003cspan class=\"filter-label\"\u003eDate Range\u003c/span\u003e\n      \u003cinput class=\"date-input\" type=\"text\" inputmode=\"numeric\" pattern=\"\\d{4}-\\d{2}-\\d{2}\" placeholder=\"yyyy-mm-dd\" id=\"dateFrom\" value=\"2025-01-01\" /\u003e\n      \u003cinput class=\"date-input\" type=\"text\" inputmode=\"numeric\" pattern=\"\\d{4}-\\d{2}-\\d{2}\" placeholder=\"yyyy-mm-dd\" id=\"dateTo\" /\u003e\n    \u003c/div\u003e\n\n    \u003chr class=\"divider\" /\u003e\n\n    \u003c!-- End game triggered --\u003e\n    \u003cdiv class=\"filter-group\"\u003e\n      \u003cdiv class=\"toggle-row\"\u003e\n        \u003cspan class=\"toggle-label\"\u003eCompleted games only\u003c/span\u003e\n        \u003clabel class=\"toggle\"\u003e\n          \u003cinput type=\"checkbox\" id=\"endGameToggle\" onchange=\"onEndGameChange()\" /\u003e\n          \u003cspan class=\"toggle-track\"\u003e\u003c/span\u003e\n        \u003c/label\u003e\n      \u003c/div\u003e\n    \u003c/div\u003e\n\n    \u003chr class=\"divider\" /\u003e\n\n    \u003cdiv class=\"filter-action-stack\"\u003e\n      \u003cbutton class=\"apply-btn\" id=\"applyBtn\" onclick=\"applyFiltersFromSidebar()\"\u003eApply filters\u003c/button\u003e\n    \u003c/div\u003e";

// Config
// API_URL points to the deployed Google Cloud Function. The frontend sends POST JSON
// with filters; the backend queries BigQuery and returns already-aggregated card stats.
const API_URL = 'https://europe-west1-ark-nova-stats-dashboard.cloudfunctions.net/get-card-stats';
// Daily default snapshots are static Cloud Storage JSON files, refreshed by
// Cloud Scheduler. Default MW/Base loads use these directly; advanced Filter
// bar requests still call API_URL because those aggregations are more specific.
const DEFAULT_SNAPSHOT_URLS = {
  1: 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/default-mw.json',
  0: 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/default-base.json',
};
// Alias CSV is optional. If it fails to load, the catch block keeps normal search working.
const CARD_ALIASES_URL = 'cards_altnames.csv';
// Attributes CSV holds static card metadata (species, strength, abilities, etc.).
// Optional in the same spirit as the alias CSV: if it fails to load, the Attributes
// bar still renders but every group is effectively a no-op since there's no data to filter on.
const CARD_ATTRIBUTES_URL = 'cards_attributes.csv';

// Attribute definitions
// Each attribute group declares which card Types it can possibly apply to.
// A group is disabled (and reset to its default/non-filtering state) whenever
// none of its relevantTypes are active in the Type filter \u2014 e.g. Strength only
// ever appears on Sponsor cards, so it's meaningless (and disabled) otherwise.
const TAG_NONE_VALUE = '0';
const SPECIES_TAGS = ['Bear', 'Bird', 'Herbivore', 'Petting Zoo', 'Predator', 'Primate', 'Reptile', 'Sea Animal'];
const CONTINENT_TAGS = ['Africa', 'America', 'Asia', 'Australia', 'Europe'];

const STRENGTH_VALUES = ['3', '4', '5', '6'];
const SIZE_VALUES = ['1', '2', '3', '4', '5'];

const ATTR_RELEVANT_TYPES = {
  species: ['animal', 'sponsor'],
  continent: ['animal', 'sponsor'],
  strength: ['sponsor'],
  size: ['animal'],
  water: ['animal', 'sponsor'],
  rock: ['animal', 'sponsor'],
  science: ['sponsor'],
  reefer: ['animal'],
  aviary: ['animal'],
  abilities: ['animal'],
};

// Keep this list in sync with the actual UI groups above.
// refreshAttributeAvailability() uses it as the single source of truth for:
// - disabling impossible attribute groups when Type excludes their card type,
// - resetting disabled groups back to default,
// - preventing hidden stale selections from continuing to filter rows.


// These are the map choices exposed to users in the sidebar.
 // Backend also validates maps, so frontend map edits alone are not enough for new backend data.
const VALID_MAPS = [
  { code: '1a',  full: 'Map 1a: Observation Tower' },
  { code: '2a',  full: 'Map 2a: Outdoor Areas' },
  { code: '3a',  full: 'Map 3a: Silver Lake' },
  { code: '4a',  full: 'Map 4a: Commercial Harbor' },
  { code: '5a',  full: 'Map 5a: Park Restaurant' },
  { code: '6a',  full: 'Map 6a: Research Institute' },
  { code: '7a',  full: 'Map 7a: Ice Cream Parlors' },
  { code: '8a',  full: 'Map 8a: Hollywood Hills' },
  { code: '9',   full: 'Map 9: Geographical Zoo' },
  { code: '10',  full: 'Map 10: Rescue Station' },
  { code: '11',  full: 'Map 11: Caves' },
  { code: '12',  full: 'Map 12: Artificial Intelligence' },
  { code: '13',  full: 'Map 13: Drawing Board' },
  { code: '14',  full: 'Map 14: Lagoon' },
  { code: 'T1',  full: 'Map T1: Tournament 1' },
];

// Round filter choices. The backend treats "6+" as round >= 6.
// All six active means the default/no-filter state.
const ROUND_FILTERS = [
  { label: '1',  value: '1' },
  { label: '2',  value: '2' },
  { label: '3',  value: '3' },
  { label: '4',  value: '4' },
  { label: '5',  value: '5' },
  { label: '6+', value: '6+' },
];

// State
let allData = [];      // Full API result for current backend filters.
let filteredData = []; // allData after client-side search + Type chip filtering.
// Default opening sort: highest delta (In Hand) first.
let currentSort = { col: 'delta_in_hand', dir: 'desc' };
let currentPage = 1;
let rowsPerPage = 50;
let searchQuery = '';
let cardAliases = new Map();
let isMW = 1;
let roundFilterActive = false; // Last loaded backend state: true when fewer than all round chips are selected.
let minPlayedThreshold = null; // Client-side minimum n_played filter. Null/blank means no minimum.
// In-memory browser cache for the two default backend snapshots. This complements
// the server-side Cloud Storage cache: once MW/Base has loaded in this page view,
// switching back to that default tab can render immediately without another fetch.
const defaultSnapshotCache = { 0: null, 1: null };
let apiWarmupInFlight = false;
let apiWarmupLastAt = 0;
const API_WARMUP_COOLDOWN_MS = 5 * 60 * 1000;
let isPageMounted = false;
let mountToken = 0;

function isCurrentMount(token) {
  return isPageMounted && token === mountToken;
}

// Attributes bar state
// cardAttributes maps normalized card name -> parsed attribute object from cards_attributes.csv.
let cardAttributes = new Map();
let cardAttributesLoaded = false;

// Selection sets for each group. Defaults are "all selected" (no filtering) for
// Species/Habitat/Strength/Size/Abilities, and "off" (no filtering) for
// Water/Rock/Science/Reefer/Aviary toggles.
let selectedSpeciesTags = new Set(SPECIES_TAGS);
let selectedContinentTags = new Set(CONTINENT_TAGS);
let selectedStrengths = new Set(STRENGTH_VALUES);
let selectedSizes = new Set(SIZE_VALUES);
let selectedAbilities = new Set(); // populated once abilities are known from the CSV
let allAbilities = []; // alphabetically sorted list of every unique ability string
let currentTagPopupKind = 'species';
let waterOn = false;
let rockOn = false;
let scienceOn = false;
let reeferOn = false;
let aviaryOn = false;
// Remembered Type-filter selection captured right before Reefer or Aviary first
// switches Type to Animal-only, so it can be restored once both are off again.
let typeBeforeReeferAviary = null;
let typeBeforeSharedAnimalSponsor = null;
let typeBeforeSponsorOnly = null;
let typeBeforeSizeOnly = null;

// Init
export function mount({ dataset = 1 } = {}) {
  bindWindowHandlers();
  isPageMounted = true;
  const activeMountToken = ++mountToken;
  document.getElementById('statsTable')?.classList.add('cards-stats-table');
  // The router recreates this page's DOM on every visit, while ES module state
  // persists. Reset DOM-backed state here so controls and data start aligned.
  resetCardsPageState(dataset);

  // Build dynamic map/round chips, fetch default stats immediately, then let
  // optional CSV metadata load in parallel without blocking the first table.
  buildMapChips();
  buildRoundChips();
  updateTypeFilterIndicator();
  buildAttributeChips();
  const searchInput = document.getElementById('searchInput');
  if (searchInput) searchInput.addEventListener('input', onSearch);
  applyFilters(activeMountToken); // auto-load on page open with defaults
  warmApiInBackground();

  loadCardAliases().then(() => {
    if (!isCurrentMount(activeMountToken)) return;
    if (allData.length) applySearch();
  });

  loadCardAttributes().then(() => {
    if (!isCurrentMount(activeMountToken)) return;
    refreshAttributeAvailability();
    if (allData.length) applySearch();
  });
}


function resetCardsPageState(dataset) {
  allData = [];
  filteredData = [];
  currentSort = { col: 'delta_in_hand', dir: 'desc' };
  currentPage = 1;
  rowsPerPage = 50;
  searchQuery = '';
  isMW = Number(dataset) === 0 ? 0 : 1;
  roundFilterActive = false;
  minPlayedThreshold = null;
  selectedSpeciesTags = new Set(SPECIES_TAGS);
  selectedContinentTags = new Set(CONTINENT_TAGS);
  selectedStrengths = new Set(STRENGTH_VALUES);
  selectedSizes = new Set(SIZE_VALUES);
  selectedAbilities = new Set(allAbilities);
  currentTagPopupKind = 'species';
  waterOn = false;
  rockOn = false;
  scienceOn = false;
  reeferOn = false;
  aviaryOn = false;
  typeBeforeReeferAviary = null;
  typeBeforeSharedAnimalSponsor = null;
  typeBeforeSponsorOnly = null;
  typeBeforeSizeOnly = null;
}
// Map chips
function buildMapChips() {
  const container = document.getElementById('mapChips');
  VALID_MAPS.forEach(map => {
    const btn = document.createElement('button');
    btn.className = 'chip active';
    btn.dataset.value = map.full;
    btn.dataset.tooltip = map.full;
    btn.textContent = map.code;
    btn.onclick = () => toggleChip(btn, 'map');
    container.appendChild(btn);
  });
}

// Round chips
function buildRoundChips() {
  const container = document.getElementById('roundChips');
  ROUND_FILTERS.forEach(round => {
    const btn = document.createElement('button');
    btn.className = 'chip active';
    btn.dataset.value = round.value;
    btn.textContent = round.label;
    btn.onclick = () => toggleRoundChip(btn);
    container.appendChild(btn);
  });
}

function toggleRoundChip(btn) {
  // Unlike the Type popup, the round filter intentionally allows zero selected
  // chips because the sidebar offers a "none" shortcut just like Maps. If the
  // user loads with no rounds selected, the frontend renders an empty table locally
  // and does not call the backend API.
  btn.classList.toggle('active');
}

function selectAllRounds() {
  document.querySelectorAll('#roundChips .chip').forEach(c => c.classList.add('active'));
}

function selectNoneRounds() {
  document.querySelectorAll('#roundChips .chip').forEach(c => c.classList.remove('active'));
}

function getSelectedRoundTokens() {
  return [...document.querySelectorAll('#roundChips .chip.active')]
    .map(c => c.dataset.value);
}

function isRoundFilterActiveFromChips() {
  const selectedRounds = getSelectedRoundTokens();
  return selectedRounds.length < ROUND_FILTERS.length;
}

function isRoundUnavailableColumn(col) {
  return ['delta_in_hand', 'playrate_pct', 'n_seen'].includes(col);
}

// Smart tooltip (avoids viewport clipping)
const _tooltip = document.getElementById('map-tooltip');

document.addEventListener('mouseover', e => {
  if (!isPageMounted) return;
  const chip = e.target.closest('[data-tooltip]');
  if (!chip) return;
  _tooltip.textContent = chip.dataset.tooltip;
  _tooltip.style.display = 'block';
  positionTooltip(e);
});

document.addEventListener('mousemove', e => {
  if (!isPageMounted) return;
  if (_tooltip.style.display === 'none') return;
  if (!e.target.closest('[data-tooltip]')) { _tooltip.style.display = 'none'; return; }
  positionTooltip(e);
});

document.addEventListener('mouseout', e => {
  if (!isPageMounted) return;
  if (!e.target.closest('[data-tooltip]')) _tooltip.style.display = 'none';
});

function positionTooltip(e) {
  const tw = _tooltip.offsetWidth;
  const th = _tooltip.offsetHeight;
  const margin = 8;
  let x = e.clientX - tw / 2;
  let y = e.clientY - th - 10;
  // Clamp horizontally
  x = Math.max(margin, Math.min(x, window.innerWidth - tw - margin));
  // Flip below cursor if too close to top
  if (y < margin) y = e.clientY + 18;
  _tooltip.style.left = x + 'px';
  _tooltip.style.top = y + 'px';
}

function selectAllMaps() {
  document.querySelectorAll('#mapChips .chip').forEach(c => c.classList.add('active'));
}

function selectNoneMaps() {
  document.querySelectorAll('#mapChips .chip').forEach(c => c.classList.remove('active'));
}

// Toggle chip
function toggleChip(btn, group) {
  btn.classList.toggle('active');
}

// MW / Base tab
function setTab(value, btn) {
  isMW = value;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  applyFilters(mountToken);
}

// end_game toggle
function onEndGameChange() {
  // nothing extra needed \u2014 value read on apply
}

// Reset
function resetFilters() {
  document.getElementById('playerEloMin').value = '300';
  document.getElementById('playerEloMax').value = '';
  document.getElementById('opponentEloMin').value = '300';
  document.getElementById('opponentEloMax').value = '';
  document.getElementById('dateFrom').value = '2025-01-01';
  document.getElementById('dateTo').value = '';
  document.getElementById('endGameToggle').checked = false;

  document.querySelectorAll('#mapChips .chip').forEach(c => c.classList.add('active'));
  document.querySelectorAll('#roundChips .chip').forEach(c => c.classList.add('active'));
  const minPlayedInput = document.getElementById('minPlayedInput');
  if (minPlayedInput) minPlayedInput.value = '';
  minPlayedThreshold = null;

  // Reset type filter chips
  document.querySelectorAll('#typeFilterPopup .chip').forEach(c => c.classList.add('active'));
  updateTypeFilterIndicator();

  // Reset Attributes bar to its full default state.
  resetAllAttributeFilters();
  refreshAttributeAvailability();

  applyFilters(mountToken);
}

// Collect filter params
function getParams() {
  // Collect backend filters here. Search text and Type chips are intentionally not sent;
  // they are applied client-side after data has loaded. The Round chips are sent because
  // round filtering changes the BigQuery aggregation itself.
  const selectedMaps = [...document.querySelectorAll('#mapChips .chip.active')]
    .map(c => c.dataset.value);
  const selectedRounds = getSelectedRoundTokens();

  const params = {
    is_mw: isMW,
    maps: selectedMaps,
    end_game_triggered: document.getElementById('endGameToggle').checked ? true : null,
  };

  if (selectedRounds.length < ROUND_FILTERS.length) {
    params.rounds = selectedRounds;
  }

  const pMin = document.getElementById('playerEloMin').value;
  const pMax = document.getElementById('playerEloMax').value;
  const oMin = document.getElementById('opponentEloMin').value;
  const oMax = document.getElementById('opponentEloMax').value;
  const dFrom = document.getElementById('dateFrom').value;
  const dTo = document.getElementById('dateTo').value;

  if (pMin) params.player_elo_min = parseInt(pMin);
  if (pMax) params.player_elo_max = parseInt(pMax);
  if (oMin) params.opponent_elo_min = parseInt(oMin);
  if (oMax) params.opponent_elo_max = parseInt(oMax);
  if (dFrom) params.date_from = dFrom;
  if (dTo) params.date_to = dTo;

  // card_types now handled client-side \u2014 not sent to API

  return params;
}

function getDefaultSnapshotKey(params) {
  // Mirrors the backend's cacheable-default definition. Only these two cases
  // are safe to reuse without a fetch: default Marine Worlds and default Base.
  const selectedMaps = params.maps || [];
  const allMapNames = VALID_MAPS.map(m => m.full);
  const allMapsSelected =
    selectedMaps.length === allMapNames.length &&
    allMapNames.every(mapName => selectedMaps.includes(mapName));

  const playerMinDefault = params.player_elo_min === undefined || Number(params.player_elo_min) === 300;
  const opponentMinDefault = params.opponent_elo_min === undefined || Number(params.opponent_elo_min) === 300;

  const isDefault =
    (params.is_mw === 0 || params.is_mw === 1) &&
    allMapsSelected &&
    playerMinDefault &&
    params.player_elo_max === undefined &&
    opponentMinDefault &&
    params.opponent_elo_max === undefined &&
    (params.date_from === undefined || params.date_from === '2025-01-01') &&
    params.date_to === undefined &&
    params.end_game_triggered === null &&
    params.rounds === undefined;

  return isDefault ? params.is_mw : null;
}

function closeSidebarIfOpen() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  if (!sidebar || !sidebar.classList.contains('open')) return;
  sidebar.classList.remove('open');
  if (overlay) overlay.classList.remove('active');
}

async function applyFiltersFromSidebar() {
  const activeMountToken = mountToken;
  const params = getParams();
  const defaultSnapshotKey = getDefaultSnapshotKey(params);
  if (defaultSnapshotKey !== null) {
    const cachedDefaultSnapshot = defaultSnapshotCache[defaultSnapshotKey];
    if (!isCurrentMount(activeMountToken)) return;
    if (cachedDefaultSnapshot) {
      roundFilterActive = Boolean(cachedDefaultSnapshot.round_filter_active);
      allData = cachedDefaultSnapshot.data;
      searchQuery = normalizeSearchText(document.getElementById('searchInput').value);
      updateCardSearchIndicator();
      applySearch();
    }
    closeSidebarIfOpen();
    return;
  }

  closeSidebarIfOpen();
  await applyFilters(activeMountToken);
}

function warmApiInBackground() {
  const now = Date.now();
  if (apiWarmupInFlight || now - apiWarmupLastAt < API_WARMUP_COOLDOWN_MS) return;

  apiWarmupInFlight = true;
  fetch(API_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ warmup: true }),
    cache: 'no-store',
    keepalive: true,
  }).catch(() => {
    // Warmup is opportunistic; visible filter requests still handle errors normally.
  }).finally(() => {
    apiWarmupInFlight = false;
    apiWarmupLastAt = Date.now();
  });
}

// Apply filters (fetch from API)
async function applyFilters(activeMountToken = mountToken) {
  // This is the only frontend function that calls the backend API.
  // It runs on page load, MW/Base tab change, Reset, and Apply filters.
  // If no Maps or no Rounds are selected, there is nothing to query: the frontend
  // renders an empty result immediately and skips the Cloud Function call entirely.
  if (!isCurrentMount(activeMountToken)) return;
  const params = getParams();
  const selectedMaps = params.maps || [];
  const selectedRounds = getSelectedRoundTokens();

  if (!selectedMaps.length || !selectedRounds.length) {
    roundFilterActive = selectedRounds.length < ROUND_FILTERS.length;

    // In round-filter mode, these columns are intentionally unavailable. If the
    // table was previously sorted by one of them, switch to delta (Played), which
    // remains meaningful for played-round analysis.
    if (roundFilterActive && isRoundUnavailableColumn(currentSort.col)) {
      currentSort = { col: 'delta_played', dir: 'desc' };
    }

    allData = [];
    filteredData = [];
    searchQuery = normalizeSearchText(document.getElementById('searchInput').value);
    updateCardSearchIndicator();
    applySearch();
    return;
  }

  const defaultSnapshotKey = getDefaultSnapshotKey(params);
  const cachedDefaultSnapshot = defaultSnapshotKey === null ? null : defaultSnapshotCache[defaultSnapshotKey];
  if (cachedDefaultSnapshot) {
    roundFilterActive = Boolean(cachedDefaultSnapshot.round_filter_active);
    allData = cachedDefaultSnapshot.data;
    searchQuery = normalizeSearchText(document.getElementById('searchInput').value);
    updateCardSearchIndicator();
    applySearch();
    return;
  }

  const btn = document.getElementById('applyBtn');
  if (btn) btn.disabled = true;
  showLoading(defaultSnapshotKey === null ? 'query' : 'saved');

  try {
    let json;

    if (defaultSnapshotKey !== null) {
      try {
        const snapshotRes = await fetch(DEFAULT_SNAPSHOT_URLS[defaultSnapshotKey], { cache: 'no-cache' });
        if (!snapshotRes.ok) throw new Error(`Snapshot HTTP ${snapshotRes.status}`);
        json = await snapshotRes.json();
      } catch (snapshotErr) {
        if (!isCurrentMount(activeMountToken)) return;
        const fallbackRes = await fetch(API_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(params),
        });
        json = await fallbackRes.json();
      }
    } else {
      const res = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
      });
      json = await res.json();
    }

    if (!isCurrentMount(activeMountToken)) return;
    if (json.status !== 'ok') throw new Error(json.message || 'Unknown error');

    roundFilterActive = Boolean(json.round_filter_active && (params.rounds !== undefined));

    // In round-filter mode, these columns are intentionally unavailable. If the
    // table was previously sorted by one of them, switch to delta (Played), which
    // remains meaningful for played-round analysis.
    if (roundFilterActive && isRoundUnavailableColumn(currentSort.col)) {
      currentSort = { col: 'delta_played', dir: 'desc' };
    }

    allData = json.data;
    if (defaultSnapshotKey !== null) {
      defaultSnapshotCache[defaultSnapshotKey] = {
        data: json.data,
        round_filter_active: Boolean(json.round_filter_active),
        cache_status: json.cache_status || 'unknown',
      };
    }
    searchQuery = normalizeSearchText(document.getElementById('searchInput').value);
    updateCardSearchIndicator();
    applySearch();

  } catch (err) {
    if (isCurrentMount(activeMountToken)) showError(err.message);
  } finally {
    if (isCurrentMount(activeMountToken) && btn) {
      btn.disabled = false;
      btn.textContent = 'Apply filters';
    }
  }
}


// Card aliases / nicknames for search
function normalizeSearchText(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();
}

async function loadCardAliases() {
  // Expected CSV format:
  // card_name,aliases
  // Sun Bear,sunny;sunbear;bear
  // Matching is accent-insensitive and lowercase-normalized via normalizeSearchText().
  try {
    const res = await fetch(CARD_ALIASES_URL, { cache: 'no-cache' });
    if (!res.ok) throw new Error(`Could not load ${CARD_ALIASES_URL}`);

    const csv = await res.text();
    const rows = parseCsv(csv);
    const aliases = new Map();

    rows.slice(1).forEach(row => {
      const cardName = (row[0] || '').trim();
      const aliasText = (row[1] || '').trim();
      if (!cardName || !aliasText) return;

      const aliasList = aliasText
        .split(';')
        .map(a => normalizeSearchText(a))
        .filter(Boolean);

      if (aliasList.length) aliases.set(normalizeSearchText(cardName), aliasList);
    });

    cardAliases = aliases;
  } catch (err) {
    console.warn('Card aliases were not loaded. Search will use card names only.', err);
    cardAliases = new Map();
  }
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = '';
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    const next = text[i + 1];

    if (char === '"') {
      if (inQuotes && next === '"') {
        field += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === ',' && !inQuotes) {
      row.push(field);
      field = '';
    } else if ((char === '\n' || char === '\r') && !inQuotes) {
      if (char === '\r' && next === '\n') i++;
      row.push(field);
      if (row.some(cell => cell.trim() !== '')) rows.push(row);
      row = [];
      field = '';
    } else {
      field += char;
    }
  }

  row.push(field);
  if (row.some(cell => cell.trim() !== '')) rows.push(row);

  // Remove possible BOM from the first header cell.
  if (rows.length && rows[0].length) rows[0][0] = rows[0][0].replace(/^\uFEFF/, '');
  return rows;
}

function aliasesForCard(cardName) {
  return cardAliases.get(normalizeSearchText(cardName)) || [];
}

// Search
// Invoked on search query update.
function onSearch() {
  searchQuery = normalizeSearchText(document.getElementById('searchInput').value);
  updateCardSearchIndicator();
  applySearch();
}

function openCardSearch(event) {
  if (event) event.stopPropagation();
  const searchBox = document.getElementById('cardHeaderSearch');
  const input = document.getElementById('searchInput');
  if (searchBox) searchBox.classList.add('open');
  if (input) input.focus();
}

function closeCardSearch(event) {
  if (event) event.stopPropagation();
  const searchBox = document.getElementById('cardHeaderSearch');
  const input = document.getElementById('searchInput');
  if (input) input.value = '';
  searchQuery = '';
  if (searchBox) searchBox.classList.remove('open');
  updateCardSearchIndicator();
  applySearch();
}

function updateCardSearchIndicator() {
  const btn = document.getElementById('cardSearchBtn');
  if (btn) btn.classList.toggle('search-active', Boolean(searchQuery));
}

function onMinPlaysInput() {
  // Minimum plays is deliberately client-side only. It uses n_played from the
  // current allData array, so typing here updates immediately and never calls fetch().
  const input = document.getElementById('minPlayedInput');
  const raw = input ? input.value.trim() : '';
  if (!raw) {
    minPlayedThreshold = null;
  } else {
    const parsed = parseInt(raw, 10);
    minPlayedThreshold = Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
  }
  applySearch();
}

function applySearch() {
  // Central client-side filtering pipeline. Keep all instant filters here; do not
  // accidentally move them into getParams(), because getParams() triggers backend work.
  // Client-side filters are applied here:
  // 1. Type popup (animal/sponsor/project),
  // 2. optional Minimum plays input using n_played,
  // 3. search over card name, card type, and aliases from cards_altnames.csv,
  // 4. Attributes bar (Species/Habitat/Strength/Size/Reefer/Aviary/Abilities)
  //    using cards_attributes.csv, looked up by card_name.
  // This preserves original backend names and only changes frontend display behaviour.
  const activeTypes = new Set(
    [...document.querySelectorAll('#typeFilterPopup .chip.active')].map(c => c.dataset.value)
  );

  const candidatesBeforeMinimum = allData.filter(row => {
    if (!activeTypes.has(row.card_type)) return false;
    if (!passesAttributeFilters(row)) return false;

    const cardName = normalizeSearchText(row.card_name);
    const cardType = normalizeSearchText(row.card_type);
    const aliases = aliasesForCard(row.card_name);

    return cardName.includes(searchQuery) ||
      cardType.includes(searchQuery) ||
      aliases.some(alias => alias.includes(searchQuery));
  });
  filteredData = minPlayedThreshold == null
    ? candidatesBeforeMinimum
    : candidatesBeforeMinimum.filter(row => Number(row.n_played || 0) >= minPlayedThreshold);
  window.setMinimumPlaysWarning?.(
    document.getElementById('minPlayedInput'),
    minPlayedThreshold > 0 && candidatesBeforeMinimum.length > 0 && filteredData.length === 0
  );

  currentPage = 1;
  applySortAndRender();
}

// Sort
function sortBy(col) {
  // Round-filtered data cannot meaningfully sort by stats that are hidden as unavailable.
  if (roundFilterActive && isRoundUnavailableColumn(col)) return;

  if (currentSort.col === col) {
    currentSort.dir = currentSort.dir === 'desc' ? 'asc' : 'desc';
  } else {
    currentSort.col = col;
    currentSort.dir = 'desc';
  }
  currentPage = 1;
  applySortAndRender();
}

function compareRowsForCurrentSort(a, b) {
  // Shared comparator used both for visible sorting and for global rank calculation.
  // Ties fall back to card_name, then card_type, so rank order is stable.
  const { col, dir } = currentSort;
  const av = a[col] ?? (col === 'card_name' ? '' : -Infinity);
  const bv = b[col] ?? (col === 'card_name' ? '' : -Infinity);

  let result;
  if (typeof av === 'string' || typeof bv === 'string') {
    result = String(av).localeCompare(String(bv));
  } else {
    result = av - bv;
  }

  if (result === 0) {
    result = String(a.card_name || '').localeCompare(String(b.card_name || ''));
  }
  if (result === 0) {
    result = String(a.card_type || '').localeCompare(String(b.card_type || ''));
  }

  return dir === 'asc' ? result : -result;
}

// Assigns globally sorted rank indices for stable, non-filtered indexing in standard lists.
function assignGlobalRanks() {
  // Global rank is assigned across cards that pass Minimum plays, but BEFORE
  // search/type/attribute filtering.
  // This is intentional: when searching "goat" or filtering to Sponsors, the # column
  // still shows the card's overall rank among all minimum-qualified cards.
  const rankingUniverse = minPlayedThreshold == null
    ? allData
    : allData.filter(row => Number(row.n_played || 0) >= minPlayedThreshold);
  const globallySorted = [...rankingUniverse].sort(compareRowsForCurrentSort);
  allData.forEach(row => { row.global_rank = null; });
  globallySorted.forEach((row, index) => {
    row.global_rank = index + 1;
  });
}

function applySortAndRender() {
  assignGlobalRanks();
  const table = document.getElementById('statsTable');
  if (table) table.classList.toggle('cards-round-filter-active', roundFilterActive);
  const { col, dir } = currentSort;
  const sorted = [...filteredData].sort(compareRowsForCurrentSort);

  // Update sort arrows
  document.querySelectorAll('.sort-arrow').forEach(el => el.textContent = '\u2195');
  document.querySelectorAll('th').forEach(th => th.classList.remove('sorted'));
  const arrow = document.getElementById(`sort-${col}`);
  if (arrow) {
    arrow.textContent = dir === 'asc' ? '\u2191' : '\u2193';
    arrow.closest('th').classList.add('sorted');
  }

  renderTable(sorted);
}

// Rows per page
function onRppChange() {
  rowsPerPage = parseInt(document.getElementById('rppSelect').value);
  currentPage = 1;
  applySortAndRender();
}

function appendCell(rowEl, className, text, color) {
  const cell = document.createElement('td');
  if (className) cell.className = className;
  if (color) cell.style.color = color;
  cell.textContent = text;
  rowEl.appendChild(cell);
  return cell;
}

function appendDeltaCiCell(rowEl, row, prefix, text, range) {
  const color = deltaRangeColor(row[prefix], range.min, range.max);
  const cell = appendCell(rowEl, 'delta delta-ci-cell', text, color);
  cell.dataset.ciLow = row[`${prefix}_ci95_low`] ?? '';
  cell.dataset.ciHigh = row[`${prefix}_ci95_high`] ?? '';
  cell.dataset.ciN = row[`${prefix}_ci95_n`] ?? '';
  cell.dataset.ciColorMin = range.min ?? '';
  cell.dataset.ciColorMax = range.max ?? '';
  return cell;
}

function appendUnavailableCell(rowEl) {
  appendCell(rowEl, 'unavailable-cell', '\u2014');
}

function appendPlayrateCell(rowEl, pr, prVal, barWidth, barColor) {
  const cell = document.createElement('td');
  const wrap = document.createElement('div');
  wrap.className = 'playrate-cell';

  const barWrap = document.createElement('div');
  barWrap.className = 'playrate-bar-wrap';

  const bar = document.createElement('div');
  bar.className = 'playrate-bar';
  bar.style.width = barWidth + '%';
  bar.style.background = barColor;

  const value = document.createElement('span');
  value.className = 'playrate-val';
  value.style.color = barColor;
  value.textContent = pr;

  barWrap.appendChild(bar);
  wrap.appendChild(barWrap);
  wrap.appendChild(value);
  cell.appendChild(wrap);
  rowEl.appendChild(cell);
}

function appendTypeCell(rowEl, rawType) {
  const typeText = rawType == null ? '' : String(rawType);
  const normalizedType = ['animal', 'sponsor', 'project'].includes(typeText) ? typeText : 'unknown';
  const cell = document.createElement('td');
  const badge = document.createElement('span');
  badge.className = `type-badge type-${normalizedType}`;
  badge.textContent = typeText ? typeText.charAt(0).toUpperCase() + typeText.slice(1) : 'Unknown';
  cell.appendChild(badge);
  rowEl.appendChild(cell);
}

// Render table
function renderTable(data) {
  // data is already filtered + sorted. This function only handles pagination,
  // colour formatting, and converting rows into table HTML.
  // In roundFilterActive mode, the backend returns NULL for delta_in_hand, n_seen,
  // and playrate_pct; this function renders those cells as a single long dash (\u2014).
  const tbody = document.getElementById('tableBody');
  const pagination = document.getElementById('pagination');
  const meta = document.getElementById('tableMeta');

  if (!data.length) {
    tbody.innerHTML = `<tr><td colspan="9">
      <div class="state-overlay">
        <div class="error-icon">&#128269;</div>
        <div class="state-title">No cards found</div>
        <div class="state-sub">Try adjusting your search or filters.</div>
      </div>
    </td></tr>`;
    pagination.style.display = 'none';
    meta.innerHTML = 'No results';
    return;
  }

  const rpp = rowsPerPage >= 9999 ? data.length : rowsPerPage;
  const totalPages = Math.ceil(data.length / rpp);
  if (currentPage > totalPages) currentPage = totalPages;

  const start = (currentPage - 1) * rpp;
  const pageData = data.slice(start, start + rpp);

  // Frontend-only search, Type, Attributes, and minimum-play filters do not
  // recolor survivors; ranges belong to the complete current backend payload.
  const colorUniverse = allData.length ? allData : data;
  const playrateRange = numericRange(colorUniverse, row => row.playrate_pct);
  const eloRange = numericRange(colorUniverse, row => row.avg_elo);
  const deltaPlayedRange = cappedNumericRange(colorUniverse, row => row.delta_played);
  const deltaInHandRange = cappedNumericRange(colorUniverse, row => row.delta_in_hand);

  tbody.replaceChildren();
  pageData.forEach(row => {
    const dp = fmtDelta(row.delta_played);
    const dh = fmtDelta(row.delta_in_hand);
    const pr = row.playrate_pct != null ? row.playrate_pct.toFixed(2) + '%' : '\u2014';
    const prVal = row.playrate_pct || 0;
    const barWidth = prVal; // absolute: playrate % = bar width %
    const barColor = prColor(prVal, playrateRange.min, playrateRange.max);
    const eloDisplay = row.avg_elo != null ? Math.round(row.avg_elo).toLocaleString('en-US') : '\u2014';
    const eloCol = eloColor(row.avg_elo, eloRange.min, eloRange.max);

    const tr = document.createElement('tr');
    appendCell(tr, 'rank-cell', row.global_rank ?? '\u2014');
    appendCell(tr, 'card-name', titleCase(row.card_name));
    appendDeltaCiCell(tr, row, 'delta_played', dp, deltaPlayedRange);
    if (roundFilterActive) appendUnavailableCell(tr);
    else appendDeltaCiCell(tr, row, 'delta_in_hand', dh, deltaInHandRange);
    appendCell(tr, 'n-cell', eloDisplay, eloCol);
    if (roundFilterActive) appendUnavailableCell(tr);
    else appendPlayrateCell(tr, pr, prVal, barWidth, barColor);
    appendCell(tr, 'n-cell', fmtN(row.n_played));
    if (roundFilterActive) appendUnavailableCell(tr);
    else appendCell(tr, 'n-cell', fmtN(row.n_seen));
    appendTypeCell(tr, row.card_type);
    tbody.appendChild(tr);
  });

  // Meta
  const from = start + 1;
  const to = Math.min(start + rpp, data.length);
  meta.innerHTML = `<span class="meta-prefix">Showing </span><strong>${from}-${to}</strong> of <strong>${data.length}</strong> cards`;

  // Pagination
  if (totalPages <= 1) {
    pagination.style.display = 'none';
  } else {
    pagination.style.display = 'flex';
    pagination.innerHTML = buildPagination(totalPages);
  }
}

function buildPagination(totalPages) {
  let html = `<button class="page-btn" onclick="goPage(${currentPage - 1})" ${currentPage === 1 ? 'disabled' : ''}>&lsaquo;</button>`;

  const pages = paginationRange(currentPage, totalPages);
  let prev = null;
  for (const p of pages) {
    if (prev !== null && p - prev > 1) html += `<span class="page-info">...</span>`;
    html += `<button class="page-btn ${p === currentPage ? 'active' : ''}" onclick="goPage(${p})">${p}</button>`;
    prev = p;
  }

  html += `<button class="page-btn" onclick="goPage(${currentPage + 1})" ${currentPage === totalPages ? 'disabled' : ''}>&rsaquo;</button>`;
  return html;
}

function paginationRange(current, total) {
  const delta = 2;
  const range = [];
  for (let i = Math.max(1, current - delta); i <= Math.min(total, current + delta); i++) range.push(i);
  if (!range.includes(1)) range.unshift(1);
  if (!range.includes(total)) range.push(total);
  return range;
}

function goPage(p) {
  const totalPages = Math.ceil(filteredData.length / (rowsPerPage >= 9999 ? filteredData.length : rowsPerPage));
  if (p < 1 || p > totalPages) return;
  currentPage = p;
  applySortAndRender();
  document.querySelector('.table-wrap').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// States
function showLoading(mode = 'query') {
  document.querySelectorAll('#statsTable th.sorted').forEach(th => th.classList.remove('sorted'));
  document.querySelectorAll('#statsTable .sort-arrow').forEach(arrow => { arrow.textContent = '\u2195'; });
  const isSavedSnapshot = mode === 'saved';
  const title = isSavedSnapshot ? 'Preparing data...' : 'Fetching data...';
  const sub = isSavedSnapshot
    ? '<div class="state-sub">Loading the latest available card statistics.</div>'
    : '<div class="state-sub">Querying BigQuery with your current filters.</div>';
  document.getElementById('tableBody').innerHTML = `<tr><td colspan="9">
    <div class="state-overlay">
      <div class="spinner"></div>
      <div class="state-title">${title}</div>
      ${sub}
    </div>
  </td></tr>`;
  document.getElementById('pagination').style.display = 'none';
  document.getElementById('tableMeta').innerHTML = '';
}

function showError(msg) {
  const tbody = document.getElementById('tableBody');
  const tr = document.createElement('tr');
  const td = document.createElement('td');
  const overlay = document.createElement('div');
  const icon = document.createElement('div');
  const title = document.createElement('div');
  const sub = document.createElement('div');

  td.colSpan = 9;
  overlay.className = 'state-overlay';
  icon.className = 'error-icon';
  title.className = 'state-title';
  sub.className = 'state-sub';

  icon.textContent = '!';
  title.textContent = 'Something went wrong';
  sub.textContent = msg;

  overlay.appendChild(icon);
  overlay.appendChild(title);
  overlay.appendChild(sub);
  td.appendChild(overlay);
  tr.appendChild(td);
  tbody.replaceChildren(tr);
}

// Helpers
function fmtDelta(val) {
  if (val == null) return '\u2014';
  const sign = val >= 0 ? '+' : '';
  return `${sign}${val.toFixed(3)}`;
}

// Formats big number digits nicely.
function fmtN(val) {
  if (val == null) return '\u2014';
  return val.toLocaleString('en-US');
}

function titleCase(str) {
  // Frontend display only. Do NOT send title-cased names back to backend/BigQuery,
  // because card names in the source data are case-sensitive.
  // Also handles "(domestic) Goat" -> "(Domestic) Goat".
  const lower = new Set(['on', 'in', 'of', 'the', 'a']);
  const displayName = str
    .split(' ')
    .map((word, i) => {
      const w = word.toLowerCase();
      // Always capitalise the first word; lowercase the small words otherwise
      if (i > 0 && lower.has(w)) return w;
      // Capitalise the first actual letter, so "(domestic)" becomes "(Domestic)".
      return w.replace(/[A-Za-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u00FF]/, ch => ch.toUpperCase());
    })
    .join(' ');

  return displayName
    .replace(/\bWaza\b/g, 'WAZA')
    .replace(/\bGalapagos\b/g, 'Gal\u00e1pagos');
}

const prColor = playrateColor;
const eloColor = relativeEloColor;

// Column header tooltips
const _colTip = document.getElementById('col-tooltip');

document.addEventListener('mouseover', e => {
  if (!isPageMounted) return;
  const th = e.target.closest('th');
  if (!th) return;
  const tipEl = th.querySelector('.col-tip');
  if (!tipEl) return;

  if (tipEl.hasAttribute('data-tip-fraction')) {
    _colTip.innerHTML = `<div class="tip-fraction">
      <span class="tip-num">played</span>
      <span class="tip-den">seen</span>
    </div>`;
  } else if (tipEl.hasAttribute('data-tip-played')) {
    _colTip.innerHTML = `<div class="tip-plain">n (played by either player)</div>`;
  } else if (tipEl.hasAttribute('data-tip-seen')) {
    _colTip.innerHTML = `<div class="tip-plain">n (on display or in hand of either player)</div>`;
  } else {
    _colTip.textContent = tipEl.dataset.tip;
  }

  _colTip.style.display = 'block';
  positionColTip(e);
});

document.addEventListener('mousemove', e => {
  if (!isPageMounted) return;
  if (_colTip.style.display === 'none') return;
  if (e.target.closest('.delta-ci-cell')) return;
  const th = e.target.closest('th');
  if (!th || !th.querySelector('.col-tip')) { _colTip.style.display = 'none'; return; }
  positionColTip(e);
});

document.addEventListener('mouseout', e => {
  if (!isPageMounted) return;
  if (e.target.closest('.delta-ci-cell') || e.relatedTarget?.closest('.delta-ci-cell')) return;
  const th = e.target.closest('th');
  if (!th || !e.relatedTarget?.closest('th') || e.relatedTarget.closest('th') !== th) {
    _colTip.style.display = 'none';
  }
});

function positionColTip(e) {
  const tw = _colTip.offsetWidth;
  const th = _colTip.offsetHeight;
  const margin = 8;
  let x = e.clientX - tw / 2;
  let y = e.clientY + 18; // show below cursor for header tooltips
  x = Math.max(margin, Math.min(x, window.innerWidth - tw - margin));
  if (y + th > window.innerHeight - margin) y = e.clientY - th - 10;
  _colTip.style.left = x + 'px';
  _colTip.style.top = y + 'px';
}

// Type column filter
function toggleTypeFilterPopup(e) {
  // Opens/closes the far-right Type column popup. The popup is position:fixed,
  // so it can escape the scroll/clipping context of the table wrapper.
  e.stopPropagation();
  if (e.target.closest('.type-filter-popup')) return;
  const popup = document.getElementById('typeFilterPopup');
  if (!popup) return;

  const willOpen = !popup.classList.contains('open');
  popup.classList.toggle('open', willOpen);
  if (willOpen) {
    positionTypeFilterPopup();
    requestAnimationFrame(positionTypeFilterPopup);
  }
}

function positionTypeFilterPopup() {
  if (!isPageMounted) return;
  const header = document.getElementById('typeFilterHeader');
  const popup = document.getElementById('typeFilterPopup');
  if (!header || !popup || !popup.classList.contains('open')) return;

  const margin = 8;
  const gap = 0;
  const headerRect = header.getBoundingClientRect();
  const popupRect = popup.getBoundingClientRect();
  const popupWidth = popupRect.width || 110;
  const popupHeight = popupRect.height || 120;
  const anchoredTop = headerRect.bottom + gap;
  if (anchoredTop + popupHeight <= 0 || anchoredTop >= window.innerHeight) {
    closeTypeFilterPopup();
    return;
  }

  let left = headerRect.left + (headerRect.width / 2) - (popupWidth / 2);
  left = Math.max(margin, Math.min(left, window.innerWidth - popupWidth - margin));

  let top = headerRect.bottom + gap;
  if (top + popupHeight > window.innerHeight - margin) {
    top = Math.max(margin, headerRect.top - popupHeight - gap);
  }

  popup.style.left = `${Math.round(left)}px`;
  popup.style.top = `${Math.round(top)}px`;
}

function closeTypeFilterPopup() {
  const popup = document.getElementById('typeFilterPopup');
  if (!popup) return;
  popup.classList.remove('open');
}
function updateTypeFilterIndicator() {
  // Visual reminder for the client-side Type filter after the popup is closed.
  // All three selected = default state with compact filter icon.
  // Two selected = two warm-green dots. One selected = one warm-green dot.
  const header = document.getElementById('typeFilterHeader');
  const indicator = document.getElementById('typeFilterIndicator');
  const allChips = [...document.querySelectorAll('#typeFilterPopup .chip')];
  if (!header || !indicator || !allChips.length) return;

  const activeCount = allChips.filter(c => c.classList.contains('active')).length;

  if (activeCount === allChips.length) {
    header.classList.remove('type-filter-active');
    indicator.classList.add('type-filter-icon');
    indicator.textContent = '';
  } else {
    header.classList.add('type-filter-active');
    indicator.classList.remove('type-filter-icon');
    indicator.textContent = activeCount === 1 ? '\u2022' : '\u2022\u2022';
  }
}

function toggleTypeChip(btn) {
  btn.classList.toggle('active');

  updateTypeFilterIndicator();
  // Type changed: some Attribute groups may now be impossible (e.g. Strength
  // if Sponsor was just deselected). Re-evaluate which groups are disabled,
  // which silently resets any now-irrelevant group back to its default.
  refreshAttributeAvailability();
  applySearch();
}

// Close Type popup when clicking outside its trigger or floating menu.
document.addEventListener('click', e => {
  if (!isPageMounted) return;
  const popup = document.getElementById('typeFilterPopup');
  if (!popup || !popup.classList.contains('open')) return;
  if (e.target.closest('#typeFilterPopup') || e.target.closest('#typeFilterHeader')
      || e.target.closest('#filterToggleBtn') || e.target.closest('.sidebar-close-btn')
      || e.target.closest('.attributes-bar-header')) return;
  closeTypeFilterPopup();
});

window.addEventListener('resize', positionTypeFilterPopup);
window.addEventListener('scroll', positionTypeFilterPopup, true);


// ==============================================================================
// Attributes bar
// Everything below is CLIENT-SIDE ONLY. It reads static card metadata from
// cards_attributes.csv (loaded once at startup) and layers extra filtering on
// top of the existing Type/Search/Min-plays pipeline inside applySearch().
// No part of this ever triggers a backend fetch.
// ==============================================================================

// Loading cards_attributes.csv
async function loadCardAttributes() {
  // Used columns: Type,Name,Species,Continent,Water,Rock,Science,Strength,
  // Size,Abilities,Reefer,Aviary. Species/Abilities can contain multiple
  // semicolon-separated values. Matching against backend card_name is done on a
  // normalized (accent/case-insensitive) basis, same approach as the alias CSV.
  try {
    const res = await fetch(CARD_ATTRIBUTES_URL, { cache: 'no-cache' });
    if (!res.ok) throw new Error(`Could not load ${CARD_ATTRIBUTES_URL}`);

    const csv = await res.text();
    const rows = parseCsv(csv);
    if (!rows.length) throw new Error('Empty attributes CSV');

    const header = rows[0].map(h => h.trim());
    const idx = name => header.indexOf(name);

    const iType = idx('Type'), iName = idx('Name'), iSpecies = idx('Species'),
          iContinent = idx('Continent'), iWater = idx('Water'), iRock = idx('Rock'),
          iScience = idx('Science'), iStrength = idx('Strength'), iSize = idx('Size'),
          iAbilities = idx('Abilities'), iReefer = idx('Reefer'), iAviary = idx('Aviary');

    const attrs = new Map();
    const abilitySet = new Set();

    rows.slice(1).forEach(cols => {
      const name = (cols[iName] || '').trim();
      if (!name) return;

      const species = (cols[iSpecies] || '').split(';').map(s => s.trim()).filter(Boolean);
      const abilities = (cols[iAbilities] || '').split(';').map(s => s.trim()).filter(Boolean);
      abilities.forEach(a => abilitySet.add(a));

      const record = {
        cardType: (cols[iType] || '').trim(),
        species,
        continent: (cols[iContinent] || '').trim(),
        water: Boolean((cols[iWater] || '').trim()),
        rock: Boolean((cols[iRock] || '').trim()),
        science: Boolean((cols[iScience] || '').trim()),
        strength: (cols[iStrength] || '').trim(), // '' if not a sponsor / no strength
        size: (cols[iSize] || '').trim(),         // '' if not an animal / no size
        abilities,
        reefer: Boolean((cols[iReefer] || '').trim()),
        aviary: Boolean((cols[iAviary] || '').trim()),
      };

      attrs.set(normalizeSearchText(name), record);
    });

    cardAttributes = attrs;
    cardAttributesLoaded = true;
    allAbilities = [...abilitySet].sort((a, b) => a.localeCompare(b));
    selectedAbilities = new Set(allAbilities); // default: all selected = no filtering
    buildAbilitiesList();
    setAttributesUnavailable(false);
  } catch (err) {
    console.warn('Card attributes were not loaded. The Attributes bar will have no effect.', err);
    cardAttributes = new Map();
    cardAttributesLoaded = false;
    allAbilities = [];
    selectedAbilities = new Set();
    setAttributesUnavailable(true);
  }
}

function attributesForCard(cardName) {
  return cardAttributes.get(normalizeSearchText(cardName)) || null;
}

function setAttributesUnavailable(unavailable) {
  const bar = document.getElementById('attributesBar');
  if (bar) bar.classList.toggle('attributes-unavailable', unavailable);
}

// Collapse / expand
function toggleAttributesBar() {
  document.getElementById('attributesBar').classList.toggle('collapsed');
  positionTypeFilterPopup();
  requestAnimationFrame(positionTypeFilterPopup);
}

function resetAttributesFromHeader(event) {
  if (event) event.stopPropagation();
  setActiveTypeTokens(['animal', 'sponsor', 'project']);
  resetAllAttributeFilters();
  refreshAttributeAvailability();
  applySearch();
}

// Building the static chip rows and tag popup
function buildAttributeChips() {
  buildChipGroup('strengthChips', STRENGTH_VALUES, selectedStrengths, 'strength');
  buildChipGroup('sizeChips', SIZE_VALUES, selectedSizes, 'size');
  renderCurrentTagPopup();
}

function buildChipGroup(containerId, values, selectedSet, kind) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = '';
  values.forEach(value => {
    const btn = document.createElement('button');
    btn.className = selectedSet.has(value) ? 'chip active' : 'chip';
    btn.dataset.value = value;
    btn.textContent = value;
    btn.onclick = () => toggleAttributeChip(btn, selectedSet, values, kind);
    container.appendChild(btn);
  });
}

// Shared independent toggle handler for Strength/Size/Species/Continent chips.
function toggleAttributeChip(btn, selectedSet, values, kind) {
  const value = btn.dataset.value;
  if (selectedSet.has(value)) {
    selectedSet.delete(value);
    btn.classList.remove('active');
  } else {
    selectedSet.add(value);
    btn.classList.add('active');
  }

  // Attribute narrowing forces the Type filter toward the card types that can
  // actually carry that attribute, so the Type header and popup reflect the
  // effective filtering users see in the table.
  const isDefault = selectedSet.size === values.length;
  if (kind === 'strength') {
    if (!isDefault) forceSponsorOnlyTypeFilter();
    else syncSponsorOnlyTypeFilter();
  }
  if (kind === 'size') {
    if (!isDefault) forceSizeOnlyTypeFilter();
    else syncAnimalOnlyTypeFilter();
  }
  if (kind === 'species' || kind === 'continent') {
    syncSharedAnimalSponsorTypeFilter();
    updateTagButtonLabels();
  }

  updateAttributesSummary();
  applySearch();
}

function selectAllAttributeValues(kind) {
  setAttributeValues(kind, true);
}

function selectNoneAttributeValues(kind) {
  setAttributeValues(kind, false);
}

function setAttributeValues(kind, selectAll) {
  if (kind === 'strength') {
    selectedStrengths = selectAll ? new Set(STRENGTH_VALUES) : new Set();
    buildChipGroup('strengthChips', STRENGTH_VALUES, selectedStrengths, 'strength');
    if (!selectAll) forceSponsorOnlyTypeFilter();
    else syncSponsorOnlyTypeFilter();
  } else if (kind === 'size') {
    selectedSizes = selectAll ? new Set(SIZE_VALUES) : new Set();
    buildChipGroup('sizeChips', SIZE_VALUES, selectedSizes, 'size');
    if (!selectAll) forceSizeOnlyTypeFilter();
    else syncAnimalOnlyTypeFilter();
  }

  updateAttributesSummary();
  applySearch();
}

// Species / Habitat popups
function toggleTagPopup(kind, event) {
  if (event) event.stopPropagation();
  const group = document.getElementById(kind === 'species' ? 'attrGroupSpecies' : 'attrGroupContinent');
  if (group.classList.contains('disabled')) return;

  currentTagPopupKind = kind;
  renderCurrentTagPopup();
  document.getElementById('tagPopupOverlay').classList.add('open');
}

function closeTagPopup() {
  document.getElementById('tagPopupOverlay').classList.remove('open');
  updateAttributesSummary();
  applySearch();
}

function closeTagPopupOnOverlay(event) {
  // Clicking the dark backdrop (not the popup itself) closes it, same affordance
  // as clicking outside the Type filter popup.
  closeTagPopup();
}

function renderCurrentTagPopup() {
  const title = document.getElementById('tagPopupTitle');
  const values = currentTagPopupKind === 'species' ? SPECIES_TAGS : CONTINENT_TAGS;
  const selectedSet = currentTagPopupKind === 'species' ? selectedSpeciesTags : selectedContinentTags;
  const kind = currentTagPopupKind === 'species' ? 'species' : 'continent';

  if (title) title.textContent = currentTagPopupKind === 'species' ? 'Species' : 'Habitat';
  buildChipGroup('tagPopupChips', values, selectedSet, kind);
}

function selectAllCurrentTagPopup() {
  if (currentTagPopupKind === 'species') {
    selectedSpeciesTags = new Set(SPECIES_TAGS);
  } else {
    selectedContinentTags = new Set(CONTINENT_TAGS);
  }
  syncSharedAnimalSponsorTypeFilter();
  renderCurrentTagPopup();
  updateTagButtonLabels();
}

function selectNoneCurrentTagPopup() {
  if (currentTagPopupKind === 'species') {
    selectedSpeciesTags = new Set();
  } else {
    selectedContinentTags = new Set();
  }
  syncSharedAnimalSponsorTypeFilter();
  renderCurrentTagPopup();
  updateTagButtonLabels();
}

function areSpeciesAtDefault() {
  return selectedSpeciesTags.size === SPECIES_TAGS.length;
}

function areContinentsAtDefault() {
  return selectedContinentTags.size === CONTINENT_TAGS.length;
}

function updateSingleTagButton(kind, selectedSet, values) {
  const btn = document.getElementById(kind === 'species' ? 'speciesBtn' : 'continentBtn');
  const label = document.getElementById(kind === 'species' ? 'speciesBtnLabel' : 'continentBtnLabel');
  const indicator = document.getElementById(kind === 'species' ? 'speciesBtnIndicator' : 'continentBtnIndicator');
  if (!btn || !label || !indicator) return;

  if (selectedSet.size === values.length) {
    btn.classList.remove('narrowed');
    label.textContent = 'All';
    indicator.textContent = '';
  } else {
    btn.classList.add('narrowed');
    label.textContent = '';
    indicator.textContent = `(${selectedSet.size}/${values.length})`;
  }
}

function updateTagButtonLabels() {
  updateSingleTagButton('species', selectedSpeciesTags, SPECIES_TAGS);
  updateSingleTagButton('continent', selectedContinentTags, CONTINENT_TAGS);
}

// Abilities dropdown
function buildAbilitiesList() {
  renderAbilitiesList();
}

function toggleAbilitiesPanel(event) {
  if (event) event.stopPropagation();
  const group = document.getElementById('attrGroupAbilities');
  if (group.classList.contains('disabled')) return;
  const panel = document.getElementById('abilitiesPanel');
  panel.classList.toggle('open');
  if (panel.classList.contains('open')) {
    const input = document.getElementById('abilitiesSearchInput');
    if (input) {
      try {
        input.focus({ preventScroll: true });
      } catch {
        input.focus();
      }
    }
    positionAbilitiesPanel();
    requestAnimationFrame(positionAbilitiesPanel);
  }
}

function positionAbilitiesPanel() {
  if (!isPageMounted) return;
  // The panel is fixed-positioned so a short filtered table cannot clip it.
  // Keep it visually anchored to the Abilities button and clamp it inside the viewport.
  const btn = document.getElementById('abilitiesBtn');
  const panel = document.getElementById('abilitiesPanel');
  if (!btn || !panel || !panel.classList.contains('open')) return;

  const margin = 16;
  const gap = 8;
  const rect = btn.getBoundingClientRect();
  const panelWidth = panel.offsetWidth || 260;
  const left = Math.max(margin, Math.min(rect.right - panelWidth, window.innerWidth - panelWidth - margin));
  const top = Math.max(margin, Math.min(rect.bottom + gap, window.innerHeight - panel.offsetHeight - margin));

  panel.style.left = left + 'px';
  panel.style.top = top + 'px';
}

function renderAbilitiesList() {
  const list = document.getElementById('abilitiesList');
  if (!list) return;
  const query = normalizeSearchText(document.getElementById('abilitiesSearchInput')?.value || '');

  const matches = allAbilities.filter(a => normalizeSearchText(a).includes(query));

  if (!matches.length) {
    list.innerHTML = '<div class="abilities-list-empty">No abilities match.</div>';
    return;
  }

  list.innerHTML = '';
  matches.forEach((ability, index) => {
    const safeId = 'ability-' + ability.replace(/[^a-zA-Z0-9]/g, '_') + '-' + index;
    const label = document.createElement('label');
    label.className = 'abilities-list-item';
    label.setAttribute('for', safeId);

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.id = safeId;
    checkbox.checked = selectedAbilities.has(ability);
    checkbox.addEventListener('change', () => toggleAbility(ability, checkbox));

    label.appendChild(checkbox);
    label.appendChild(document.createTextNode(` ${ability}`));
    list.appendChild(label);
  });
}

function toggleAbility(ability, checkbox) {
  if (selectedAbilities.size === allAbilities.length && !checkbox.checked) {
    // UX shortcut: from the default all-selected state, clicking one ability
    // means "only this ability". After that, ability checkboxes toggle normally.
    selectedAbilities = new Set([ability]);
    renderAbilitiesList();
  } else if (checkbox.checked) {
    selectedAbilities.add(ability);
  } else {
    selectedAbilities.delete(ability);
  }
  if (selectedAbilities.size === allAbilities.length) syncAnimalOnlyTypeFilter();
  else forceSizeOnlyTypeFilter();
  updateAbilitiesButtonLabel();
  updateAttributesSummary();
  applySearch();
}

function selectAllAbilities() {
  selectedAbilities = new Set(allAbilities);
  renderAbilitiesList();
  if (selectedAbilities.size === allAbilities.length) syncAnimalOnlyTypeFilter();
  else forceSizeOnlyTypeFilter();
  updateAbilitiesButtonLabel();
  updateAttributesSummary();
  applySearch();
}

function selectNoneAbilities() {
  selectedAbilities = new Set();
  renderAbilitiesList();
  if (selectedAbilities.size === allAbilities.length) syncAnimalOnlyTypeFilter();
  else forceSizeOnlyTypeFilter();
  updateAbilitiesButtonLabel();
  updateAttributesSummary();
  applySearch();
}

// Update the label on the abilities drop button.
function updateAbilitiesButtonLabel() {
  const btn = document.getElementById('abilitiesBtn');
  const label = document.getElementById('abilitiesBtnLabel');
  const indicator = document.getElementById('abilitiesBtnIndicator');
  if (!btn || !label || !indicator) return;

  if (selectedAbilities.size === allAbilities.length) {
    btn.classList.remove('narrowed');
    label.textContent = 'All';
    indicator.textContent = '';
  } else {
    btn.classList.add('narrowed');
    label.textContent = '';
    indicator.textContent = `(${selectedAbilities.size}/${allAbilities.length})`;
  }
}

// Close Abilities panel when clicking outside it.
document.addEventListener('click', e => {
  if (!isPageMounted) return;
  const panel = document.getElementById('abilitiesPanel');
  if (panel && panel.classList.contains('open') && !e.target.closest('.abilities-dropdown')) {
    panel.classList.remove('open');
  }
});

window.addEventListener('resize', positionAbilitiesPanel);

// Water / Rock / Science toggles
// Water and Rock apply to both Animal and Sponsor cards. Turning either on
// removes Project from Type while preserving Animal-only/Sponsor-only choices. Science
// is Sponsor-only, so turning it on follows Strength and forces Sponsor-only.
function onBoolTagToggle(which) {
  if (which === 'water') {
    waterOn = document.getElementById('waterToggle').checked;
    syncSharedAnimalSponsorTypeFilter();
  } else if (which === 'rock') {
    rockOn = document.getElementById('rockToggle').checked;
    syncSharedAnimalSponsorTypeFilter();
  } else if (which === 'science') {
    scienceOn = document.getElementById('scienceToggle').checked;
    if (scienceOn) forceSponsorOnlyTypeFilter();
    else syncSponsorOnlyTypeFilter();
  }
  updateAttributesSummary();
  applySearch();
}

// Reefer / Aviary toggles
function onReeferAviaryToggle(which) {
  const reeferCheckbox = document.getElementById('reeferToggle');
  const aviaryCheckbox = document.getElementById('aviaryToggle');
  const wasReeferOn = reeferOn;
  const wasAviaryOn = aviaryOn;

  reeferOn = reeferCheckbox.checked;
  aviaryOn = aviaryCheckbox.checked;

  const eitherOnNow = reeferOn || aviaryOn;
  const eitherOnBefore = wasReeferOn || wasAviaryOn;

  if (eitherOnNow && !eitherOnBefore) {
    // Neither was on before, now one just turned on: remember current Type
    // selection and force Type to Animal-only.
    typeBeforeReeferAviary = getActiveTypeTokens();
    forceTypeToOnly('animal');
  } else if (!eitherOnNow && eitherOnBefore) {
    // Both are now off: restore whatever Type selection was active right
    // before the first one of these was switched on.
    if (typeBeforeReeferAviary) {
      setActiveTypeTokens(typeBeforeReeferAviary);
    }
    typeBeforeReeferAviary = null;
  }
  // If one was already on and the other just joined it (both now on), Type
  // stays Animal-only \u2014 no change needed since it's already forced there.

  refreshAttributeAvailability();
  updateAttributesSummary();
  applySearch();
}

// Type filter helpers shared with Strength/Size/Reefer/Aviary
function getActiveTypeTokens() {
  return [...document.querySelectorAll('#typeFilterPopup .chip.active')].map(c => c.dataset.value);
}

function setActiveTypeTokens(tokens) {
  const tokenSet = new Set(tokens);
  document.querySelectorAll('#typeFilterPopup .chip').forEach(c => {
    c.classList.toggle('active', tokenSet.has(c.dataset.value));
  });
  updateTypeFilterIndicator();
}

// Forces Type to a single value for attribute groups that are meaningful for
// only one card type.
function forceTypeToOnly(typeValue) {
  setActiveTypeTokens([typeValue]);
  refreshAttributeAvailability();
}

function forceSponsorOnlyTypeFilter() {
  if (!typeBeforeSponsorOnly) typeBeforeSponsorOnly = getActiveTypeTokens();
  forceTypeToOnly('sponsor');
}

function forceSizeOnlyTypeFilter() {
  if (!typeBeforeSizeOnly) typeBeforeSizeOnly = getActiveTypeTokens();
  forceTypeToOnly('animal');
}

function syncSharedAnimalSponsorTypeFilter() {
  // Species, Habitat, Rock, and Water can only match Animal/Sponsor cards.
  // Narrowing one removes Project from the active Type set, but it preserves a
  // prior Animal-only or Sponsor-only choice instead of widening it.
  const allSharedAnimalSponsorFiltersDefault =
    areSpeciesAtDefault() &&
    areContinentsAtDefault() &&
    !waterOn &&
    !rockOn;
  const activeTypes = getActiveTypeTokens();
  const sharedTypes = activeTypes.filter(t => t === 'animal' || t === 'sponsor');

  if (!allSharedAnimalSponsorFiltersDefault) {
    if (!typeBeforeSharedAnimalSponsor) typeBeforeSharedAnimalSponsor = activeTypes;
    setActiveTypeTokens(sharedTypes.length ? sharedTypes : ['animal', 'sponsor']);
    refreshAttributeAvailability();
    return;
  }

  if (!typeBeforeSharedAnimalSponsor) return;

  const projectedBeforeShared = typeBeforeSharedAnimalSponsor.filter(t => t === 'animal' || t === 'sponsor');
  const expectedAutoTypes = projectedBeforeShared.length ? projectedBeforeShared : ['animal', 'sponsor'];
  const stillInAutoState =
    activeTypes.length === expectedAutoTypes.length &&
    expectedAutoTypes.every(t => activeTypes.includes(t));

  if (stillInAutoState) setActiveTypeTokens(typeBeforeSharedAnimalSponsor);
  typeBeforeSharedAnimalSponsor = null;
  refreshAttributeAvailability();
}

function syncSponsorOnlyTypeFilter() {
  // Science and narrowed Strength are Sponsor-only. When they return to
  // default, restore the Type selection from before they first forced Sponsor.
  const allSponsorOnlyFiltersDefault =
    !scienceOn &&
    selectedStrengths.size === STRENGTH_VALUES.length;
  const activeTypes = getActiveTypeTokens();

  if (!allSponsorOnlyFiltersDefault || !typeBeforeSponsorOnly) return;

  const stillInAutoState = activeTypes.length === 1 && activeTypes[0] === 'sponsor';
  if (stillInAutoState) setActiveTypeTokens(typeBeforeSponsorOnly);
  typeBeforeSponsorOnly = null;
  refreshAttributeAvailability();
}

function syncAnimalOnlyTypeFilter() {
  // Narrowed Size and narrowed Abilities are Animal-only. When both return to
  // default, restore the Type selection from before they first forced Animal.
  const allAnimalOnlyFiltersDefault =
    selectedSizes.size === SIZE_VALUES.length &&
    selectedAbilities.size === allAbilities.length;
  const activeTypes = getActiveTypeTokens();

  if (!allAnimalOnlyFiltersDefault || !typeBeforeSizeOnly) return;

  const stillInAutoState = activeTypes.length === 1 && activeTypes[0] === 'animal';
  if (stillInAutoState) setActiveTypeTokens(typeBeforeSizeOnly);
  typeBeforeSizeOnly = null;
  refreshAttributeAvailability();
}

// Disabling groups based on the active Type filter
// Central rule: a group is disabled whenever NONE of its relevantTypes are
// currently active in the Type filter. Disabling always resets that group's
// selection back to its default (all-selected for chip/ability groups, off
// for Reefer/Aviary) so re-enabling never restores a stale prior choice.
function refreshAttributeAvailability() {
  // Central "impossible by Type" rule. Example: if Sponsor is inactive,
  // Strength and Science are disabled and reset; if Animal is inactive,
  // Size/Reefer/Aviary/Abilities are disabled and reset.
  const activeTypes = new Set(getActiveTypeTokens());

  Object.keys(ATTR_RELEVANT_TYPES).forEach(groupKey => {
    const relevant = ATTR_RELEVANT_TYPES[groupKey];
    const isPossible = relevant.some(t => activeTypes.has(t));
    setGroupDisabled(groupKey, !isPossible);
  });

  if (!reeferOn && !aviaryOn) {
    typeBeforeReeferAviary = null;
  }

  updateAttributesSummary();
}

function setGroupDisabled(groupKey, disabled) {
  const groupIdMap = {
    species: 'attrGroupSpecies',
    continent: 'attrGroupContinent',
    strength: 'attrGroupStrength',
    size: 'attrGroupSize',
    water: 'attrGroupWater',
    rock: 'attrGroupRock',
    science: 'attrGroupScience',
    reefer: 'attrGroupReefer',
    aviary: 'attrGroupAviary',
    abilities: 'attrGroupAbilities',
  };
  const el = document.getElementById(groupIdMap[groupKey]);
  if (!el) return;

  const wasDisabled = el.classList.contains('disabled');
  el.classList.toggle('disabled', disabled);

  // Only reset state on the transition into disabled, not on every refresh call,
  // so we don't wipe a selection that was already at default anyway (harmless
  // either way, but avoids unnecessary DOM rebuilds).
  if (disabled && !wasDisabled) {
    resetAttributeGroup(groupKey);
  }
}

function resetAttributeGroup(groupKey) {
  switch (groupKey) {
    case 'species':
      selectedSpeciesTags = new Set(SPECIES_TAGS);
      updateTagButtonLabels();
      if (currentTagPopupKind === 'species') renderCurrentTagPopup();
      break;
    case 'continent':
      selectedContinentTags = new Set(CONTINENT_TAGS);
      updateTagButtonLabels();
      if (currentTagPopupKind === 'continent') renderCurrentTagPopup();
      break;
    case 'strength':
      selectedStrengths = new Set(STRENGTH_VALUES);
      buildChipGroup('strengthChips', STRENGTH_VALUES, selectedStrengths, 'strength');
      break;
    case 'size':
      selectedSizes = new Set(SIZE_VALUES);
      buildChipGroup('sizeChips', SIZE_VALUES, selectedSizes, 'size');
      break;
    case 'abilities':
      selectedAbilities = new Set(allAbilities);
      renderAbilitiesList();
      updateAbilitiesButtonLabel();
      break;
    case 'water':
      waterOn = false;
      document.getElementById('waterToggle').checked = false;
      break;
    case 'rock':
      rockOn = false;
      document.getElementById('rockToggle').checked = false;
      break;
    case 'science':
      scienceOn = false;
      document.getElementById('scienceToggle').checked = false;
      break;
    case 'reefer':
      reeferOn = false;
      document.getElementById('reeferToggle').checked = false;
      break;
    case 'aviary':
      aviaryOn = false;
      document.getElementById('aviaryToggle').checked = false;
      break;
  }
}

function resetAllAttributeFilters() {
  selectedSpeciesTags = new Set(SPECIES_TAGS);
  selectedContinentTags = new Set(CONTINENT_TAGS);
  selectedStrengths = new Set(STRENGTH_VALUES);
  selectedSizes = new Set(SIZE_VALUES);
  selectedAbilities = new Set(allAbilities);
  waterOn = false;
  rockOn = false;
  scienceOn = false;
  reeferOn = false;
  aviaryOn = false;
  typeBeforeReeferAviary = null;
  typeBeforeSharedAnimalSponsor = null;
  typeBeforeSponsorOnly = null;
  typeBeforeSizeOnly = null;

  buildAttributeChips();
  renderAbilitiesList();
  updateTagButtonLabels();
  updateAbilitiesButtonLabel();

  [['waterToggle', null], ['rockToggle', null],
   ['scienceToggle', null], ['reeferToggle', null],
   ['aviaryToggle', null]].forEach(([cbId, lblId]) => {
    const cb = document.getElementById(cbId);
    const lbl = lblId ? document.getElementById(lblId) : null;
    if (cb) cb.checked = false;
    if (lbl) lbl.textContent = 'No';
  });

  updateAttributesSummary();
}

// Summary text in the Attributes bar header.
function updateAttributesSummary() {
  if (!cardAttributesLoaded) {
    return;
  }

  updateTagButtonLabels();
  updateAbilitiesButtonLabel();
}

// The actual per-row filtering check
function passesAttributeFilters(row) {
  // If the attributes CSV failed to load, or this particular card has no entry
  // in it, do not filter the row out \u2014 fail open so the table still works.
  if (!cardAttributesLoaded) return true;
  const attrs = attributesForCard(row.card_name);
  if (!attrs) return true;

  // Species and Habitat are separate include-lists. Default all selected =
  // no filtering for that group. Once narrowed, a card must match at least one
  // selected value in the narrowed group. Selecting none means the explicit
  // no-tag value, matching Sponsor cards with no Species/Habitat tag.
  // Important: these are ANDed as groups. If Species and Habitat are both
  // narrowed, a card must satisfy both groups.
  if (!areSpeciesAtDefault()) {
    if (selectedSpeciesTags.size) {
      if (!attrs.species.some(s => selectedSpeciesTags.has(s))) return false;
    } else if (!attrs.species.includes(TAG_NONE_VALUE)) {
      return false;
    }
  }
  if (!areContinentsAtDefault()) {
    if (selectedContinentTags.size) {
      if (!attrs.continent || !selectedContinentTags.has(attrs.continent)) return false;
    } else if (attrs.continent !== TAG_NONE_VALUE) {
      return false;
    }
  }

  // Water/Rock/Science: simple boolean toggles, default OFF (no filtering).
  // Switching one ON narrows the table to only cards that have that tag.
  if (waterOn && !attrs.water) return false;
  if (rockOn && !attrs.rock) return false;
  if (scienceOn && !attrs.science) return false;

  // Strength: when narrowed, a card must have one of the selected strength values.
  if (selectedStrengths.size !== STRENGTH_VALUES.length) {
    if (!attrs.strength) return false;
    if (!selectedStrengths.has(attrs.strength)) return false;
  }

  // Size: when narrowed, a card must have one of the selected size values.
  if (selectedSizes.size !== SIZE_VALUES.length) {
    if (!attrs.size) return false;
    if (!selectedSizes.has(attrs.size)) return false;
  }

  // Reefer / Aviary: simple boolean toggles. When off (default), they don't filter.
  if (reeferOn && !attrs.reefer) return false;
  if (aviaryOn && !attrs.aviary) return false;

  // Abilities: OR logic \u2014 card passes if it has at least one selected ability.
  // selectedAbilities defaults to the full set, so this only narrows anything
  // once the user has deliberately deselected at least one ability.
  if (selectedAbilities.size !== allAbilities.length) {
    if (attrs.abilities.length === 0) {
      // A card with zero ability entries cannot match a narrowed ability
      // search, because "no abilities" is not itself a selectable option
      // (the literal ability string "None" is a separate, selectable value).
      return false;
    }
    if (!attrs.abilities.some(a => selectedAbilities.has(a))) return false;
  }

  return true;
}
export function setDataset(value) {
  isMW = Number(value) === 0 ? 0 : 1;
  if (!isPageMounted) return;
  applyFilters(mountToken);
}

export function unmount() {
  isPageMounted = false;
  mountToken += 1;
  const searchInput = document.getElementById('searchInput');
  if (searchInput) searchInput.removeEventListener('input', onSearch);
  const panel = document.getElementById('abilitiesPanel');
  if (panel) panel.classList.remove('open');
  closeTypeFilterPopup();
  const tagPopup = document.getElementById('tagPopupOverlay');
  if (tagPopup) tagPopup.classList.remove('open');
  if (_tooltip) _tooltip.style.display = 'none';
  if (_colTip) _colTip.style.display = 'none';
}

const PAGE_WINDOW_HANDLERS = {
  onMinPlaysInput,
  onRppChange,
  toggleAttributesBar,
  resetAttributesFromHeader,
  toggleTagPopup,
  onBoolTagToggle,
  selectAllAttributeValues,
  selectNoneAttributeValues,
  onReeferAviaryToggle,
  toggleAbilitiesPanel,
  renderAbilitiesList,
  selectAllAbilities,
  selectNoneAbilities,
  closeTagPopupOnOverlay,
  selectAllCurrentTagPopup,
  selectNoneCurrentTagPopup,
  closeTagPopup,
  sortBy,
  onSearch,
  openCardSearch,
  closeCardSearch,
  toggleTypeFilterPopup,
  toggleTypeChip,
  resetFilters,
  selectAllMaps,
  selectNoneMaps,
  selectAllRounds,
  selectNoneRounds,
  onEndGameChange,
  applyFiltersFromSidebar,
  goPage,
};

function bindWindowHandlers() {
  Object.assign(window, PAGE_WINDOW_HANDLERS);
}
