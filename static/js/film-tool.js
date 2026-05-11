/**
 * Film Tool — Liberty Basketball
 * Main application logic for the film tagging tool.
 *
 * All DOM IDs must match the HTML template exactly.
 */

// ── Issue Reporter (console capture) ────────────────────────
(function initLibertyIssueReporter() {
    if (window.LibertyIssueReporter) return;

    const entries = [];
    const maxEntries = 80;
    const maxChunkLength = 600;

    function serialize(value) {
        if (value == null) return String(value);
        if (value instanceof Error) return value.stack || value.message || String(value);
        if (typeof value === 'string') return value;
        if (typeof value === 'number' || typeof value === 'boolean') return String(value);
        try { return JSON.stringify(value); } catch (_err) { return String(value); }
    }

    function record(level, args) {
        const text = args.map(arg => serialize(arg).slice(0, maxChunkLength)).join(' ');
        entries.push({ at: new Date().toISOString(), level, text });
        if (entries.length > maxEntries) entries.splice(0, entries.length - maxEntries);
    }

    ['log', 'info', 'warn', 'error', 'debug'].forEach(level => {
        const original = console[level] ? console[level].bind(console) : null;
        console[level] = (...args) => { record(level, args); if (original) original(...args); };
    });

    window.addEventListener('error', (event) => {
        record('error', [event.message, event.filename ? `${event.filename}:${event.lineno || 0}:${event.colno || 0}` : '', event.error && event.error.stack ? event.error.stack : '']);
    });

    window.addEventListener('unhandledrejection', (event) => {
        record('error', ['Unhandled promise rejection', event.reason]);
    });

    window.LibertyIssueReporter = {
        getConsoleText() { return entries.map(e => `[${e.at}] ${e.level.toUpperCase()} ${e.text}`).join('\n'); },
        getCurrentPagePath() { return `${window.location.pathname}${window.location.search}${window.location.hash}`; },
    };
})();

// ── Constants ───────────────────────────────────────────────
const VOCAB_STORAGE_KEY = 'filmToolVocabularyV20260423final';
const ROSTER_STORAGE_KEY = 'filmToolRostersV20260423final';
const GAMES_STORAGE_KEY = 'filmToolSavedGamesV20260423final';
const LAST_GAME_KEY = 'filmToolLastGameIdV20260423final';
const CURRENT_AUTOSAVE_KEY = 'filmToolCurrentAutosaveV20260423final';

// ── Vocabulary (tagging terms) ──────────────────────────────
const vocabulary = {
    quarter: ['Q1', 'Q2', 'Q3', 'Q4', 'OT'],
    team: ['Our Team', 'Opponent', 'Home', 'Away'],
    side: ['Offense', 'Defense', 'Neutral'],
    category: ['ATO', 'Defense', 'Offense', 'Substitution', 'Transition', 'BLOB', 'SLOB', 'Quarter'],
    eventtype: ['2PT', '3PT', 'Assist', 'BLOB', 'Block', 'DefRebound', 'EndQTR', 'FT', 'Foul', 'JumpBall', 'OB', 'OffRebound', 'SLOB', 'StartQTR', 'Steal', 'SubOut', 'SubIn', 'TimeOut', 'Tip', 'Turnover', 'Violation'],
    result: ['Make', 'Miss', 'NA'],
    player: []
};
const lockedFields = ['quarter', 'team', 'side', 'category', 'eventtype', 'result'];

// ── Event Definitions (tag buttons) ─────────────────────────
const eventDefs = [
    { id: 'and1', label: 'And-1', hotkey: '', group: 'offense', teamMode: 'team-player', eventtype: '2PT', result: 'Make', side: 'Offense', category: 'Offense' },
    { id: 'assist', label: 'Assist', hotkey: 'A', group: 'offense', teamMode: 'team-player', eventtype: 'Assist', result: 'NA', side: 'Offense', category: 'Offense' },
    { id: 'blob', label: 'BLOB', hotkey: 'B', group: 'flow', teamMode: 'team-only', eventtype: 'BLOB', result: 'NA', side: 'Offense', category: 'BLOB' },
    { id: 'block', label: 'Block', hotkey: 'K', group: 'defense', teamMode: 'team-player', eventtype: 'Block', result: 'NA', side: 'Defense', category: 'Defense' },
    { id: 'defreb', label: 'Def Reb', hotkey: 'D', group: 'defense', teamMode: 'team-player', eventtype: 'DefRebound', result: 'NA', side: 'Defense', category: 'Defense' },
    { id: 'endqtr', label: 'End QTR', hotkey: 'E', group: 'flow', teamMode: 'event-only', eventtype: 'EndQTR', result: 'NA', side: 'Neutral', category: 'Quarter' },
    { id: 'foul', label: 'Foul', hotkey: 'F', group: 'defense', teamMode: 'team-player', eventtype: 'Foul', result: 'NA', side: 'Defense', category: 'Defense' },
    { id: 'ftmake', label: 'FT Make', hotkey: '', group: 'offense', teamMode: 'team-player', eventtype: 'FT', result: 'Make', side: 'Offense', category: 'Offense' },
    { id: 'ftmiss', label: 'FT Miss', hotkey: '', group: 'offense', teamMode: 'team-player', eventtype: 'FT', result: 'Miss', side: 'Offense', category: 'Offense' },
    { id: 'jumpball', label: 'Jump Ball', hotkey: 'J', group: 'flow', teamMode: 'event-only', eventtype: 'JumpBall', result: 'NA', side: 'Neutral', category: 'Quarter' },
    { id: 'ob', label: 'OB', hotkey: 'O', group: 'defense', teamMode: 'team-only', eventtype: 'OB', result: 'NA', side: 'Defense', category: 'Defense' },
    { id: 'offreb', label: 'Off Reb', hotkey: 'R', group: 'offense', teamMode: 'team-player', eventtype: 'OffRebound', result: 'NA', side: 'Offense', category: 'Offense' },
    { id: 'slob', label: 'SLOB', hotkey: '', group: 'flow', teamMode: 'team-only', eventtype: 'SLOB', result: 'NA', side: 'Offense', category: 'SLOB' },
    { id: 'startqtr', label: 'Start QTR', hotkey: 'Q', group: 'flow', teamMode: 'event-only', eventtype: 'StartQTR', result: 'NA', side: 'Neutral', category: 'Quarter' },
    { id: 'steal', label: 'Steal', hotkey: 'S', group: 'defense', teamMode: 'special-steal', eventtype: 'Steal', result: 'NA', side: 'Defense', category: 'Defense' },
    { id: 'timeout', label: 'Time Out', hotkey: 'T', group: 'flow', teamMode: 'team-only', eventtype: 'TimeOut', result: 'NA', side: 'Neutral', category: 'Quarter' },
    { id: 'tip', label: 'Tip', hotkey: 'P', group: 'flow', teamMode: 'team-only', eventtype: 'Tip', result: 'NA', side: 'Neutral', category: 'Quarter' },
    { id: 'turnover', label: 'Turnover', hotkey: '', group: 'offense', teamMode: 'team-player', eventtype: 'Turnover', result: 'NA', side: 'Offense', category: 'Offense' },
    { id: 'twoptmake', label: '2PT Make', hotkey: '2', group: 'offense', teamMode: 'team-player', eventtype: '2PT', result: 'Make', side: 'Offense', category: 'Offense' },
    { id: 'twoptmiss', label: '2PT Miss', hotkey: '', group: 'offense', teamMode: 'team-player', eventtype: '2PT', result: 'Miss', side: 'Offense', category: 'Offense' },
    { id: 'threeptmake', label: '3PT Make', hotkey: '3', group: 'offense', teamMode: 'team-player', eventtype: '3PT', result: 'Make', side: 'Offense', category: 'Offense' },
    { id: 'threeptmiss', label: '3PT Miss', hotkey: '', group: 'offense', teamMode: 'team-player', eventtype: '3PT', result: 'Miss', side: 'Offense', category: 'Offense' },
    { id: 'violation', label: 'Violation', hotkey: 'V', group: 'defense', teamMode: 'team-only', eventtype: 'Violation', result: 'NA', side: 'Defense', category: 'Defense' }
].sort((a, b) => a.label.localeCompare(b.label));

// ── Default Rosters ─────────────────────────────────────────
const defaultRosters = {};
['jrhigh', 'jv', 'varsity'].forEach(level => {
    ['boys', 'girls', 'coed'].forEach(gender => {
        ['our', 'opp', 'home', 'away'].forEach(side => {
            defaultRosters[`${level}|${gender}|${side}`] = [];
        });
    });
});

// ── State ───────────────────────────────────────────────────
let rosters = { ...defaultRosters };
let savedGames;
let currentRosterSide = 'our';
let selectedGameId = null;
let autosavePaused = false;
let currentStarters = null;
let currentLineups = { liberty: new Set(), opponent: new Set() };
let startersMode = 'initial';
let aiEventsCache = [];
let activeAiEventId = null;

// ── DOM References ──────────────────────────────────────────
let rowsBody, statusText, video, timeDisplay, lastTaggedTime, videoField, videoShell, videoFileInput;
let gameTypeSelect, competitionTypeSelect, gameDateInput, ourTeamNameInput, opponentInput, gameResultSelect;
let homeTeamNameInput, awayTeamNameInput, outputDirInput;
let leftScoreName, rightScoreName, leftScoreValue, rightScoreValue;
let reportScope, reportType, reportTitle, reportSummary, reportHeadRow, reportTableBody, reportKpiGrid;
let myGamesList, scoutGamesList;
let aiEventsList, aiEventsScroller, aiEventsCount, aiCurrentEventLabel;
let termDialog, termFieldSelect, termList, newTermInput;
let rosterDialog, playerList, rosterCsvInput;
let playerDialog, playerPosInput, playerNumInput, playerNameInput, playerGradeInput;
let quickTagDialog, quickDialogTitle, quickTagLabel, quickTagBody, focusExitBtn;
let startersDialog, libertyStartersList, opponentStartersList, startersHelp;
let uploadedVideoUrl = '';
let uploadedVideoName = '';

// ── Helpers ─────────────────────────────────────────────────
const setStatus = t => { if (statusText) statusText.textContent = t; };
const normalize = v => String(v || '').trim().replace(/\s+/g, ' ');
const safeSlug = v => String(v || '').trim().replace(/[^a-z0-9]+/gi, '-').replace(/^-+|-+$/g, '').toLowerCase();
const loadJson = (k, f) => { try { const r = localStorage.getItem(k); return r ? JSON.parse(r) : f; } catch (e) { return f; } };
const saveJson = (k, v) => localStorage.setItem(k, JSON.stringify(v));

function formatTime(t) {
    if (!isFinite(t)) return '0:00.0';
    const m = Math.floor(t / 60);
    const s = (t % 60).toFixed(1).padStart(4, '0');
    return `${m}:${s}`;
}

function timeToSeconds(str) {
    const s = String(str || '').trim();
    if (!s) return 0;
    const parts = s.split(':');
    if (parts.length === 1) return parseFloat(parts[0]) || 0;
    return (parseInt(parts[0], 10) || 0) * 60 + (parseFloat(parts[1]) || 0);
}

function formatSecondsToMMSS(sec) {
    if (!isFinite(sec) || sec <= 0) return '0:00';
    const total = Math.round(sec);
    return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

function escapeCsv(v) { return `"${String(v ?? '').replaceAll('"', '""')}"`; }

function getSelectedLevel() { return document.querySelector('input[name="level"]:checked')?.value || 'jrhigh'; }
function getSelectedGender() { return document.querySelector('input[name="gender"]:checked')?.value || 'boys'; }
function getRosterKey(side = currentRosterSide) { return `${getSelectedLevel()}|${getSelectedGender()}|${side}`; }

function parsePlayerText(text) {
    const value = normalize(text);
    if (!value) return { num: NaN, base: '' };
    const m = value.match(/^(\d+)\s*-\s*(.+)$/);
    if (m) return { num: parseInt(m[1], 10), base: `${m[1]} - ${m[2].trim()}` };
    if (/^\d+$/.test(value)) return { num: parseInt(value, 10), base: value };
    return { num: NaN, base: value };
}

function sortPlayers(list) {
    return [...new Set(list.map(normalize).filter(Boolean))]
        .map(parsePlayerText)
        .sort((a, b) => {
            if (Number.isNaN(a.num) && Number.isNaN(b.num)) return a.base.localeCompare(b.base);
            if (Number.isNaN(a.num)) return 1;
            if (Number.isNaN(b.num)) return -1;
            if (a.num !== b.num) return a.num - b.num;
            return a.base.localeCompare(b.base);
        })
        .map(x => x.base);
}

function getTeamChoices() {
    if (gameTypeSelect.value === 'my') {
        return [ourTeamNameInput.value.trim() || 'Our Team', opponentInput.value.trim() || 'Opponent'];
    }
    return [homeTeamNameInput.value.trim() || 'Home', awayTeamNameInput.value.trim() || 'Away'];
}

function mapTeamToRosterKey(team) {
    if (gameTypeSelect.value === 'my') {
        const our = ourTeamNameInput.value.trim() || 'Our Team';
        return (team === our) ? getRosterKey('our') : getRosterKey('opp');
    }
    const home = homeTeamNameInput.value.trim() || 'Home';
    return (team === home) ? getRosterKey('home') : getRosterKey('away');
}

function rosterForTeam(team) {
    return sortPlayers(rosters[mapTeamToRosterKey(team)] || []);
}

// ── Persistence ─────────────────────────────────────────────
function loadStores() {
    const vv = loadJson(VOCAB_STORAGE_KEY, null);
    if (vv) Object.keys(vocabulary).forEach(k => { if (Array.isArray(vv[k])) vocabulary[k] = vv[k]; });
    rosters = { ...defaultRosters, ...loadJson(ROSTER_STORAGE_KEY, {}) };
    savedGames = loadJson(GAMES_STORAGE_KEY, []);
}
function persistVocab() { saveJson(VOCAB_STORAGE_KEY, vocabulary); }
function persistRosters() { saveJson(ROSTER_STORAGE_KEY, rosters); }
function persistGames() { saveJson(GAMES_STORAGE_KEY, savedGames); }

// ── Row Management (tagged events table) ────────────────────
function createSelect(field, selected) {
    const select = document.createElement('select');
    select.dataset.field = field;
    const blank = document.createElement('option');
    blank.value = ''; blank.textContent = 'Select';
    select.appendChild(blank);
    (vocabulary[field] || []).forEach(term => {
        const opt = document.createElement('option');
        opt.value = term; opt.textContent = term;
        if (term === selected) opt.selected = true;
        select.appendChild(opt);
    });
    select.addEventListener('change', handleRowsChanged);
    return select;
}

function createInput(type, value, placeholder = '') {
    const input = document.createElement(type === 'textarea' ? 'textarea' : 'input');
    if (type !== 'textarea') input.type = type;
    input.value = value || '';
    if (placeholder) input.placeholder = placeholder;
    input.addEventListener('input', handleRowsChanged);
    return input;
}

function getRowData(row) {
    const data = {};
    row.querySelectorAll('[data-key]').forEach(el => { data[el.dataset.key] = String(el.value || '').trim(); });
    return data;
}

function getAllRows() {
    return [...rowsBody.querySelectorAll('tr')].map(getRowData);
}

function reindexRows() {
    [...rowsBody.querySelectorAll('tr')].forEach((row, index) => {
        row.dataset.index = index + 1;
        row.querySelector('.row-number').textContent = index + 1;
    });
}

function updateEventCount() {
    const el = document.getElementById('eventCountText');
    if (el) el.textContent = `Events tagged ${rowsBody.querySelectorAll('tr').length}`;
}

function addRow(data = {}) {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td class="row-number"></td>';
    const defs = [
        { kind: 'input', type: 'text', key: 'label' },
        { kind: 'input', type: 'text', key: 'player' },
        { kind: 'select', key: 'quarter' },
        { kind: 'select', key: 'team' },
        { kind: 'select', key: 'side' },
        { kind: 'select', key: 'category' },
        { kind: 'select', key: 'eventtype' },
        { kind: 'select', key: 'result' },
        { kind: 'input', type: 'text', key: 'start' },
        { kind: 'input', type: 'text', key: 'duration' },
        { kind: 'textarea', key: 'notes' }
    ];
    defs.forEach(def => {
        const td = document.createElement('td');
        let control;
        if (def.kind === 'select') control = createSelect(def.key, data[def.key]);
        else if (def.kind === 'textarea') control = createInput('textarea', data[def.key]);
        else control = createInput(def.type, data[def.key]);
        control.dataset.key = def.key;
        td.appendChild(control);
        tr.appendChild(td);
    });
    const actionTd = document.createElement('td');
    const wrap = document.createElement('div');
    wrap.className = 'row-actions';
    const cloneBtn = document.createElement('button');
    cloneBtn.type = 'button'; cloneBtn.className = 'btn btn-ghost'; cloneBtn.textContent = 'Clone';
    cloneBtn.addEventListener('click', () => { addRow(getRowData(tr)); handleRowsChanged(); });
    const delBtn = document.createElement('button');
    delBtn.type = 'button'; delBtn.className = 'btn btn-ghost btn-danger'; delBtn.textContent = 'Delete';
    delBtn.addEventListener('click', () => { tr.remove(); handleRowsChanged(); });
    wrap.append(cloneBtn, delBtn);
    actionTd.appendChild(wrap);
    tr.appendChild(actionTd);
    rowsBody.appendChild(tr);
    reindexRows();
    updateEventCount();
    return tr;
}

// ── Score ───────────────────────────────────────────────────
function updateScoreLabels() {
    if (gameTypeSelect.value === 'my') {
        leftScoreName.textContent = ourTeamNameInput.value.trim() || 'Our Team';
        rightScoreName.textContent = opponentInput.value.trim() || 'Opponent';
    } else {
        leftScoreName.textContent = homeTeamNameInput.value.trim() || 'Home';
        rightScoreName.textContent = awayTeamNameInput.value.trim() || 'Away';
    }
}

function getScoreState() {
    let left = 0, right = 0;
    getAllRows().forEach(r => {
        const p = (r.eventtype === '3PT' && r.result === 'Make') ? 3 : (r.eventtype === '2PT' && r.result === 'Make') ? 2 : (r.eventtype === 'FT' && r.result === 'Make') ? 1 : 0;
        if (!p) return;
        const team = r.team;
        const leftTeam = leftScoreName.textContent;
        const rightTeam = rightScoreName.textContent;
        if (team === leftTeam || team === 'Our Team') left += p;
        else if (team === rightTeam || team === 'Opponent') right += p;
        else if (gameTypeSelect.value === 'scout' && team === 'Home') left += p;
        else if (gameTypeSelect.value === 'scout' && team === 'Away') right += p;
    });
    return { left, right };
}

function renderScore() {
    updateScoreLabels();
    const s = getScoreState();
    leftScoreValue.textContent = s.left;
    rightScoreValue.textContent = s.right;
}

function currentQuarter() {
    const rows = getAllRows().filter(r => r.quarter);
    return rows.length ? rows[rows.length - 1].quarter : 'Q1';
}

// ── Event Buttons ───────────────────────────────────────────
function renderEventButtons() {
    const groupMap = { groupFlow: 'flow', groupOffense: 'offense', groupDefense: 'defense' };
    Object.entries(groupMap).forEach(([id, group]) => {
        const box = document.getElementById(id);
        if (!box) return;
        box.innerHTML = '';
                eventDefs.filter(x => x.group === group).forEach(def => {
                    const btn = document.createElement('button');
                    btn.className = 'btn';
                    btn.type = 'button';
                    btn.innerHTML = `<span>${def.label}</span>${def.hotkey ? `<span class="ft-hotkey">${def.hotkey}</span>` : ''}`;
                    btn.addEventListener('click', () => openQuickTag(def));
                    box.appendChild(btn);
                });
            });
    }

// ── Quick Tag Dialog ────────────────────────────────────────
function commitTag(def, { team = '', player = '' }) {
    addRow({
        label: def.label, player, quarter: currentQuarter(), team,
        side: def.side, category: def.category, eventtype: def.eventtype, result: def.result,
        start: formatTime(video.currentTime || 0), duration: '0:05.0', notes: ''
    });
    quickTagDialog.close();
    lastTaggedTime.textContent = formatTime(video.currentTime || 0);
    handleRowsChanged();
    setStatus(`Tagged ${def.label}.`);
}

function commitStealPair(def, p) {
    commitTag(def, { team: p.stealTeam, player: p.stealer });
    addRow({
        label: 'Turnover', player: p.turnoverPlayer, quarter: currentQuarter(),
        team: p.turnoverTeam, side: 'Offense', category: 'Offense', eventtype: 'Turnover', result: 'NA',
        start: formatTime(video.currentTime || 0), duration: '0:05.0',
        notes: `Linked to steal by ${p.stealer || p.stealTeam}`
    });
    quickTagDialog.close();
    lastTaggedTime.textContent = formatTime(video.currentTime || 0);
    handleRowsChanged();
    setStatus('Tagged steal and turnover.');
}

function openQuickTag(def) {
    if (!video.paused) video.pause();
    quickDialogTitle.textContent = def.label;
    quickTagLabel.textContent = `Video paused at ${formatTime(video.currentTime || 0)}.`;
    quickTagBody.innerHTML = '';

    if (def.teamMode === 'event-only') {
        const btn = document.createElement('button');
        btn.type = 'button'; btn.className = 'btn btn-primary'; btn.textContent = 'Tag event';
        btn.addEventListener('click', () => commitTag(def, { team: '', player: '' }));
        quickTagBody.appendChild(btn);
        quickTagDialog.showModal();
        return;
    }

    if (def.teamMode === 'team-only') {
        const wrap = document.createElement('div');
        wrap.className = 'pill-buttons';
        getTeamChoices().forEach(team => {
            const btn = document.createElement('button');
            btn.type = 'button'; btn.className = 'btn'; btn.textContent = team;
            btn.addEventListener('click', () => commitTag(def, { team, player: '' }));
            wrap.appendChild(btn);
        });
        quickTagBody.appendChild(wrap);
        quickTagDialog.showModal();
        return;
    }

    const title = document.createElement('div');
    title.className = 'tiny'; title.textContent = 'Select team';
    quickTagBody.appendChild(title);
    const wrap = document.createElement('div');
    wrap.className = 'pill-buttons';
    getTeamChoices().forEach(team => {
        const btn = document.createElement('button');
        btn.type = 'button'; btn.className = 'btn'; btn.textContent = team;
        btn.addEventListener('click', () => {
            if (def.teamMode === 'special-steal') showStealPlayers(def, team);
            else showPlayerSelection(def, team);
        });
        wrap.appendChild(btn);
    });
    quickTagBody.appendChild(wrap);
    quickTagDialog.showModal();
}

function showPlayerSelection(def, team) {
    quickTagBody.querySelector('[data-step="players"]')?.remove();
    const sec = document.createElement('div');
    sec.dataset.step = 'players'; sec.style.marginTop = '.8rem';
    const title = document.createElement('div');
    title.className = 'tiny'; title.textContent = `Select player for ${team}`;
    sec.appendChild(title);
    const wrap = document.createElement('div');
    wrap.className = 'pill-buttons';
    rosterForTeam(team).forEach(player => {
        const btn = document.createElement('button');
        btn.type = 'button'; btn.className = 'btn'; btn.textContent = player;
        btn.addEventListener('click', () => commitTag(def, { team, player }));
        wrap.appendChild(btn);
    });
    const addBtn = document.createElement('button');
    addBtn.type = 'button'; addBtn.className = 'btn btn-ghost'; addBtn.textContent = 'Add new player';
    addBtn.addEventListener('click', () => {
        const name = prompt('New player name/number (e.g. 24 - Smith):', '');
        if (!name) return;
        const key = mapTeamToRosterKey(team);
        rosters[key] = sortPlayers([...(rosters[key] || []), name]);
        persistRosters();
        showPlayerSelection(def, team);
    });
    const unknown = document.createElement('button');
    unknown.type = 'button'; unknown.className = 'btn btn-ghost'; unknown.textContent = 'Unknown / team only';
    unknown.addEventListener('click', () => commitTag(def, { team, player: '' }));
    wrap.append(addBtn, unknown);
    sec.appendChild(wrap);
    quickTagBody.appendChild(sec);
}

function showStealPlayers(def, stealTeam) {
    quickTagBody.querySelector('[data-step="players"]')?.remove();
    const sec = document.createElement('div');
    sec.dataset.step = 'players'; sec.style.marginTop = '.8rem';
    sec.innerHTML = `<div class="tiny">Who got the steal for ${stealTeam}?</div>`;
    const wrap = document.createElement('div');
    wrap.className = 'pill-buttons';
    rosterForTeam(stealTeam).forEach(player => {
        const btn = document.createElement('button');
        btn.type = 'button'; btn.className = 'btn'; btn.textContent = player;
        btn.addEventListener('click', () => showTurnoverChooser(def, stealTeam, player));
        wrap.appendChild(btn);
    });
    const addBtn = document.createElement('button');
    addBtn.type = 'button'; addBtn.className = 'btn btn-ghost'; addBtn.textContent = 'Add new player';
    addBtn.addEventListener('click', () => {
        const name = prompt('New player name/number (e.g. 24 - Smith):', '');
        if (!name) return;
        const key = mapTeamToRosterKey(stealTeam);
        rosters[key] = sortPlayers([...(rosters[key] || []), name]);
        persistRosters();
        showStealPlayers(def, stealTeam);
    });
    const unknown = document.createElement('button');
    unknown.type = 'button'; unknown.className = 'btn btn-ghost'; unknown.textContent = 'Unknown stealer';
    unknown.addEventListener('click', () => showTurnoverChooser(def, stealTeam, ''));
    wrap.append(addBtn, unknown);
    sec.appendChild(wrap);
    quickTagBody.appendChild(sec);
}

function showTurnoverChooser(def, stealTeam, stealer) {
    quickTagBody.querySelector('[data-step="turnover"]')?.remove();
    const sec = document.createElement('div');
    sec.dataset.step = 'turnover'; sec.style.marginTop = '.8rem';
    const oppTeams = getTeamChoices().filter(t => t !== stealTeam);
    const turnoverTeam = oppTeams[0] || stealTeam;
    sec.innerHTML = `<div class="tiny">Who turned it over for ${turnoverTeam}?</div>`;
    const wrap = document.createElement('div');
    wrap.className = 'pill-buttons';
    rosterForTeam(turnoverTeam).forEach(player => {
        const btn = document.createElement('button');
        btn.type = 'button'; btn.className = 'btn'; btn.textContent = player;
        btn.addEventListener('click', () => commitStealPair(def, { stealTeam, stealer, turnoverTeam, turnoverPlayer: player }));
        wrap.appendChild(btn);
    });
    const addBtn = document.createElement('button');
    addBtn.type = 'button'; addBtn.className = 'btn btn-ghost'; addBtn.textContent = 'Add new player';
    addBtn.addEventListener('click', () => {
        const name = prompt('New player name/number (e.g. 24 - Smith):', '');
        if (!name) return;
        const key = mapTeamToRosterKey(turnoverTeam);
        rosters[key] = sortPlayers([...(rosters[key] || []), name]);
        persistRosters();
        showTurnoverChooser(def, stealTeam, stealer);
    });
    const unknown = document.createElement('button');
    unknown.type = 'button'; unknown.className = 'btn btn-ghost'; unknown.textContent = 'Unknown turnover';
    unknown.addEventListener('click', () => commitStealPair(def, { stealTeam, stealer, turnoverTeam, turnoverPlayer: '' }));
    wrap.append(addBtn, unknown);
    sec.appendChild(wrap);
    quickTagBody.appendChild(sec);
}

// ── Row Change Handler ──────────────────────────────────────
function handleRowsChanged() {
    reindexRows();
    updateEventCount();
    renderScore();
    autosaveCurrentGame();
}

function clearAllRows() {
    rowsBody.innerHTML = '';
    updateEventCount();
    handleRowsChanged();
}

// ── Export ──────────────────────────────────────────────────
function downloadJson(filename, data) {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
}

function downloadCsv(filename, rows) {
    const header = ['Label', 'Player', 'Quarter', 'Team', 'Side', 'Category', 'EventType', 'Result', 'Start', 'Duration', 'Notes'];
    const lines = [header.map(escapeCsv).join(',')];
    rows.forEach(r => { lines.push([r.label, r.player, r.quarter, r.team, r.side, r.category, r.eventtype, r.result, r.start, r.duration, r.notes].map(escapeCsv).join(',')); });
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
}

function computePossessionsForEvents(events) {
    let possTeam = null, possIndex = 0;
    function flipTeamName(team) {
        const our = ourTeamNameInput.value.trim() || 'Our Team';
        const opp = opponentInput.value.trim() || 'Opponent';
        const home = homeTeamNameInput.value.trim() || 'Home';
        const away = awayTeamNameInput.value.trim() || 'Away';
        if (team === our) return opp; if (team === opp) return our;
        if (team === home) return away; if (team === away) return home;
        return team;
    }
    function changePossession(nextTeam) {
        if (nextTeam) possTeam = nextTeam; else if (possTeam) possTeam = flipTeamName(possTeam);
        possIndex += 1;
    }
    for (let i = 0; i < events.length; i++) {
        const ev = events[i];
        const type = (ev.eventtype || '').toUpperCase();
        const res = (ev.result || '').toUpperCase();
        const team = ev.team;
        if (type === 'TIP') { if (team) possTeam = team; else possTeam = ourTeamNameInput.value.trim() || 'Our Team'; possIndex = 1; }
        else if (type === 'STARTQTR') { if (possTeam == null) { possTeam = team || ourTeamNameInput.value.trim() || 'Our Team'; possIndex = 1; } }
        else if (type === 'JUMPBALL') { if (team) changePossession(team); }
        else if ((type === '2PT' || type === '3PT' || type === 'FT') && res === 'MAKE') { changePossession(flipTeamName(team || possTeam)); }
        else if (type === 'DEFREBOUND') { changePossession(team || possTeam); }
        else if (type === 'TURNOVER') { changePossession(flipTeamName(team || possTeam)); }
        else if (type === 'VIOLATION' || type === 'OB') { changePossession(flipTeamName(team || possTeam)); }
        else if (type === 'ENDQTR') { possIndex += 1; }
        if (!possTeam) { possTeam = team || ourTeamNameInput.value.trim() || 'Our Team'; if (possIndex === 0) possIndex = 1; }
        ev.possTeam = possTeam; ev.possIndex = possIndex;
    }
}

function exportGameData() {
    const outputDir = outputDirInput.value.trim();
    const opponent = opponentInput.value.trim();
    const gameDate = gameDateInput.value.trim();
    const ourTeamName = ourTeamNameInput.value.trim() || 'Our Team';
    const gameType = gameTypeSelect.value;
    const rows = getAllRows();
    if (!rows.length) { alert('No rows to export.'); return; }
    for (let i = 0; i < rows.length; i++) {
        const r = rows[i];
        if (!r.label || !r.start || !r.duration) { alert(`Row ${i + 1} must have label, start, and duration.`); return; }
    }
    const eventsOut = rows.map((r, idx) => {
        const startSeconds = timeToSeconds(r.start);
        const durationSeconds = timeToSeconds(r.duration);
        return {
            id: String(idx + 1).padStart(3, '0'), label: r.label, player: r.player, quarter: r.quarter,
            team: r.team, side: r.side, category: r.category, eventtype: r.eventtype, result: r.result,
            start: startSeconds, duration: durationSeconds, notes: r.notes,
            clipStart: Math.max(0, startSeconds - 3), clipEnd: startSeconds + 5, possTeam: null, possIndex: null
        };
    });
    computePossessionsForEvents(eventsOut);
    const eventsJson = { mode: gameType, gametype: gameType, video: 'G.mp4', outputdir: outputDir, events: eventsOut };
    const score = getScoreState();
    const summaryJson = { opponent: opponent || null, ourTeam: ourTeamName, ourScore: score.left, theirScore: score.right, date: gameDate || null, notes: 'Auto-generated from Basketball Film Tagger' };
    const baseId = `${gameDate || 'game'}_vs_${opponent || 'opponent'}`;
    const safeId = baseId.replace(/[^a-z0-9-]/gi, '_').slice(0, 60);
    downloadJson(`events_${safeId}.json`, eventsJson);
    downloadJson(`summary_${safeId}.json`, summaryJson);
    downloadCsv(`events_${safeId}.csv`, rows);
    setStatus(`Exported events_${safeId}.json, summary_${safeId}.json, and events_${safeId}.csv.`);
}

// ── Game Save / Load / Autosave ─────────────────────────────
function getGameMeta() {
    const score = getScoreState();
    return {
        id: selectedGameId || `game-${Date.now()}`, gameType: gameTypeSelect.value,
        competitionType: competitionTypeSelect.value, date: gameDateInput.value.trim(),
        ourTeam: ourTeamNameInput.value.trim() || 'Our Team', opponent: opponentInput.value.trim(),
        gameResult: gameResultSelect.value, homeTeam: homeTeamNameInput.value.trim(),
        awayTeam: awayTeamNameInput.value.trim(), outputDir: outputDirInput.value.trim(),
        lastTaggedTime: lastTaggedTime.textContent, score, updatedAt: new Date().toISOString()
    };
}

function serializeCurrentGame() {
    return { ...getGameMeta(), rows: getAllRows() };
}

function loadGameIntoUI(game) {
    autosavePaused = true;
    selectedGameId = game.id;
    gameTypeSelect.value = game.gameType || 'my';
    competitionTypeSelect.value = game.competitionType || 'non-conference';
    gameDateInput.value = game.date || '';
    ourTeamNameInput.value = game.ourTeam || 'Our Team';
    opponentInput.value = game.opponent || '';
    gameResultSelect.value = game.gameResult || '';
    homeTeamNameInput.value = game.homeTeam || '';
    awayTeamNameInput.value = game.awayTeam || '';
    outputDirInput.value = game.outputDir || '';
    lastTaggedTime.textContent = game.lastTaggedTime || '—';
    rowsBody.innerHTML = '';
    (game.rows || []).forEach(addRow);
    autosavePaused = false;
    handleRowsChanged();
    renderGames();
    setStatus(`Loaded ${game.date || 'saved game'} vs ${game.opponent || game.awayTeam || ''}. Reload video to continue tagging.`);
}

function autosaveCurrentGame() {
    if (autosavePaused) return;
    const game = serializeCurrentGame();
    localStorage.setItem(CURRENT_AUTOSAVE_KEY, JSON.stringify(game));
    localStorage.setItem(LAST_GAME_KEY, game.id);
    selectedGameId = game.id;
}

let autosaveTimeout = null;
function queueAutosave() { clearTimeout(autosaveTimeout); autosaveTimeout = setTimeout(() => autosaveCurrentGame(), 800); }

function saveCurrentGameToLibrary() {
    const game = serializeCurrentGame();
    selectedGameId = game.id;
    const idx = savedGames.findIndex(g => g.id === game.id);
    if (idx >= 0) savedGames[idx] = game; else savedGames.unshift(game);
    persistGames();
    localStorage.setItem(LAST_GAME_KEY, game.id);
    renderGames();
    setStatus('Game saved.');
}

function resumeLastGame() {
    const autosave = loadJson(CURRENT_AUTOSAVE_KEY, null);
    const lastId = localStorage.getItem(LAST_GAME_KEY);
    if (autosave && (!lastId || autosave.id === lastId)) { loadGameIntoUI(autosave); return; }
    const match = savedGames.find(g => g.id === lastId);
    if (match) { loadGameIntoUI(match); return; }
    setStatus('No saved game to resume yet.');
}

function newGame() {
    if (selectedGameId && !confirm('Start a new game? Save current work first if needed.')) return;
    autosavePaused = true;
    selectedGameId = `game-${Date.now()}`;
    rowsBody.innerHTML = '';
    gameTypeSelect.value = 'my';
    competitionTypeSelect.value = 'non-conference';
    gameDateInput.value = '';
    ourTeamNameInput.value = 'Liberty';
    opponentInput.value = '';
    gameResultSelect.value = '';
    homeTeamNameInput.value = '';
    awayTeamNameInput.value = '';
    outputDirInput.value = '';
    lastTaggedTime.textContent = '—';
    autosavePaused = false;
    handleRowsChanged();
    setStatus('Started new game.');
}

function resetGameMetadata() {
    gameTypeSelect.value = 'my';
    competitionTypeSelect.value = 'non-conference';
    gameDateInput.value = '';
    ourTeamNameInput.value = 'Liberty';
    opponentInput.value = '';
    gameResultSelect.value = '';
    homeTeamNameInput.value = '';
    awayTeamNameInput.value = '';
    outputDirInput.value = '';
    lastTaggedTime.textContent = '—';
}

// ── Games List ──────────────────────────────────────────────
function gameCardHtml(game) {
    const left = game.gameType === 'my' ? (game.ourTeam || 'Our Team') : (game.homeTeam || 'Home');
    const right = game.gameType === 'my' ? (game.opponent || 'Opponent') : (game.awayTeam || 'Away');
    const updated = new Date(game.updatedAt || Date.now()).toLocaleString();
    const rowsCount = (game.rows || []).length;
    const scoreLeft = game.score?.left ?? 0;
    const scoreRight = game.score?.right ?? 0;
    return `
<div class="game-card ${selectedGameId === game.id ? 'active' : ''}" data-game-id="${game.id}">
  <div class="inline-actions" style="justify-content:space-between;align-items:flex-start">
    <strong>${game.date || 'No date'}</strong>
    <span class="badge">${game.competitionType || 'game'}</span>
  </div>
  <div style="margin-top:.45rem">${left} vs ${right}</div>
  <div class="tiny" style="margin-top:.35rem">${rowsCount} tagged events · updated ${updated}</div>
  <div class="tiny" style="margin-top:.35rem">Score ${scoreLeft} - ${scoreRight}</div>
  <div class="inline-actions no-print" style="margin-top:.65rem">
    <button class="btn btn-ghost load-game-btn" type="button" data-id="${game.id}">Open</button>
    <button class="btn btn-ghost view-report-btn" type="button" data-id="${game.id}">Reports</button>
  </div>
</div>`;
}

function renderGames() {
    const my = savedGames.filter(g => g.gameType === 'my');
    const scout = savedGames.filter(g => g.gameType === 'scout');
    myGamesList.innerHTML = my.length ? my.map(gameCardHtml).join('') : '<div class="empty-state">No My Games saved yet.</div>';
    scoutGamesList.innerHTML = scout.length ? scout.map(gameCardHtml).join('') : '<div class="empty-state">No Scout Games saved yet.</div>';
    document.querySelectorAll('.load-game-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const g = savedGames.find(x => x.id === btn.dataset.id);
            if (g) { loadGameIntoUI(g); setActiveTab('taggerView'); }
        });
    });
    document.querySelectorAll('.view-report-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            selectedGameId = btn.dataset.id;
            renderGames();
            setActiveTab('reportsView');
            reportScope.value = 'selected';
            generateReport();
        });
    });
}

// ── Reports ─────────────────────────────────────────────────
function gatherGamesForScope(scope) {
    if (scope === 'selected') { const g = savedGames.find(g => g.id === selectedGameId) || serializeCurrentGame(); return [g]; }
    if (scope === 'my-season') return savedGames.filter(g => g.gameType === 'my');
    if (scope === 'scout-season') return savedGames.filter(g => g.gameType === 'scout');
    return savedGames.slice();
}

function statAccumulator(rows) {
    const byTeam = {}, byPlayer = {};
    rows.forEach(r => {
        const team = r.team || 'Unknown', player = r.player || 'Unknown', key = `${team}__${player}`;
        if (!byTeam[team]) byTeam[team] = { Points: 0, FGM: 0, FGA: 0, '3PM': 0, '3PA': 0, FTM: 0, FTA: 0, OReb: 0, DReb: 0, Reb: 0, Assists: 0, Steals: 0, Blocks: 0, Turnovers: 0, Fouls: 0 };
        if (!byPlayer[key]) byPlayer[key] = { Team: team, Player: player, Points: 0, FGM: 0, FGA: 0, '3PM': 0, '3PA': 0, FTM: 0, FTA: 0, OReb: 0, DReb: 0, Reb: 0, Assists: 0, Steals: 0, Blocks: 0, Turnovers: 0, Fouls: 0, Seconds: 0 };
        const t = byTeam[team], p = byPlayer[key];
        if (r.eventtype === '2PT') { t.FGA++; p.FGA++; if (r.result === 'Make') { t.FGM++; p.FGM++; t.Points += 2; p.Points += 2; } }
        if (r.eventtype === '3PT') { t.FGA++; t['3PA']++; p.FGA++; p['3PA']++; if (r.result === 'Make') { t.FGM++; t['3PM']++; p.FGM++; p['3PM']++; t.Points += 3; p.Points += 3; } }
        if (r.eventtype === 'FT') { t.FTA++; p.FTA++; if (r.result === 'Make') { t.FTM++; p.FTM++; t.Points += 1; p.Points += 1; } }
        if (r.eventtype === 'Assist') { t.Assists++; p.Assists++; }
        if (r.eventtype === 'OffRebound') { t.OReb++; t.Reb++; p.OReb++; p.Reb++; }
        if (r.eventtype === 'DefRebound') { t.DReb++; t.Reb++; p.DReb++; p.Reb++; }
        if (r.eventtype === 'Steal') { t.Steals++; p.Steals++; }
        if (r.eventtype === 'Block') { t.Blocks++; p.Blocks++; }
        if (r.eventtype === 'Turnover') { t.Turnovers++; p.Turnovers++; }
        if (r.eventtype === 'Foul') { t.Fouls++; p.Fouls++; }
    });
    return { byTeam, byPlayer };
}

function teamRecordSummary(games) {
    const my = games.filter(g => g.gameType === 'my');
    let ow = 0, ol = 0, cw = 0, cl = 0, nw = 0, nl = 0;
    my.forEach(g => {
        if (g.gameResult === 'win') { ow++; if (g.competitionType === 'conference') cw++; else nw++; }
        if (g.gameResult === 'loss') { ol++; if (g.competitionType === 'conference') cl++; else nl++; }
    });
    return [{ Category: 'Overall', Record: `${ow}-${ol}` }, { Category: 'Conference', Record: `${cw}-${cl}` }, { Category: 'Non-Conference / Other', Record: `${nw}-${nl}` }];
}

function drawReportTable(columns, rows) {
    reportHeadRow.innerHTML = '';
    reportTableBody.innerHTML = '';
    columns.forEach(c => { const th = document.createElement('th'); th.textContent = c; reportHeadRow.appendChild(th); });
    rows.forEach(row => {
        const tr = document.createElement('tr');
        columns.forEach(col => { const td = document.createElement('td'); td.textContent = row[col] ?? ''; tr.appendChild(td); });
        reportTableBody.appendChild(tr);
    });
    if (!rows.length) {
        const tr = document.createElement('tr');
        const td = document.createElement('td'); td.colSpan = columns.length || 1; td.textContent = 'No data for this report.';
        tr.appendChild(td); reportTableBody.appendChild(tr);
    }
}

function drawKpis(items) {
    reportKpiGrid.innerHTML = '';
    items.forEach(([label, value]) => {
        const box = document.createElement('div'); box.className = 'kpi';
        box.innerHTML = `<div class="label">${label}</div><div class="value">${value}</div>`;
        reportKpiGrid.appendChild(box);
    });
}

function addMinutesToStatAccumulator(rows, byPlayer) {
    const liberty = ourTeamNameInput.value.trim() || 'Our Team';
    const sorted = rows.map((r, i) => ({ ...r, _index: i })).sort((a, b) => timeToSeconds(a.start) - timeToSeconds(b.start));
    const onCourtLiberty = new Set(), onCourtOpp = new Set();
    function handleSub(row) {
        const team = row.team, player = row.player;
        if (!player) return;
        const isOur = (team === liberty || team === 'Our Team');
        const set = isOur ? onCourtLiberty : onCourtOpp;
        if (row.eventtype === 'SubOut') { if (set.has(player)) set.delete(player); }
        else if (row.eventtype === 'SubIn') { set.add(player); }
    }
    sorted.forEach(row => {
        const t = timeToSeconds(row.start);
        if (row.eventtype === 'SubIn' || row.eventtype === 'SubOut') handleSub(row);
        row._time = t;
    });
    const totalTime = sorted.length ? timeToSeconds(sorted[sorted.length - 1].start) + timeToSeconds(sorted[sorted.length - 1].duration) : 0;
    sorted.forEach((row, idx) => {
        const tStart = row._time;
        const tEnd = (idx < sorted.length - 1) ? sorted[idx + 1]._time : totalTime;
        const dt = Math.max(0, tEnd - tStart);
        if (dt <= 0) return;
        [...onCourtLiberty].forEach(player => { const key = `${liberty}__${player || 'Unknown'}`; if (byPlayer[key]) byPlayer[key].Seconds += dt; });
        if (row.eventtype === 'SubIn' || row.eventtype === 'SubOut') handleSub(row);
    });
}

function generateReport() {
    const scope = reportScope.value, type = reportType.value;
    const games = gatherGamesForScope(scope);
    const rows = scope === 'selected' ? getAllRows() : games.flatMap(g => g.rows || []);
    reportHeadRow.innerHTML = ''; reportTableBody.innerHTML = ''; reportKpiGrid.innerHTML = '';
    const titleParts = [];
    if (scope === 'selected') titleParts.push('Selected Game');
    else if (scope === 'my-season') titleParts.push('My Games Season to Date');
    else if (scope === 'scout-season') titleParts.push('Scout Games Season to Date');
    else titleParts.push('All Saved Games');
    if (type === 'team-totals') titleParts.push('Team Totals');
    else if (type === 'player-totals') titleParts.push('Individual Totals');
    else if (type === 'opponent-totals') titleParts.push('Opponent Totals');
    else if (type === 'record-summary') titleParts.push('Team Record');
    else if (type === 'box-score') titleParts.push('Box Score');
    else titleParts.push('Raw Data');
    reportTitle.textContent = titleParts.join(' • ');
    if (!rows.length && type !== 'record-summary') { reportSummary.value = 'No events tagged yet.'; return; }
    if (type === 'raw-data') {
        const headers = ['#', 'Label', 'Player', 'Quarter', 'Team', 'Side', 'Category', 'Event Type', 'Result', 'Start', 'Duration', 'Notes'];
        drawReportTable(headers, rows.map((r, i) => ({ '#': i + 1, Label: r.label, Player: r.player, Quarter: r.quarter, Team: r.team, Side: r.side, Category: r.category, 'Event Type': r.eventtype, Result: r.result, Start: r.start, Duration: r.duration, Notes: r.notes })));
        drawKpis([['Events', rows.length]]); reportSummary.value = 'Raw data for tagged events.'; return;
    }
    const acc = statAccumulator(rows);
    addMinutesToStatAccumulator(rows, acc.byPlayer);
    if (type === 'team-totals') {
        const teams = Object.entries(acc.byTeam).map(([team, s]) => ({ Team: team, PTS: s.Points, FGM: s.FGM, FGA: s.FGA, FG: `${s.FGA ? s.FGM + '/' + s.FGA : '0/0'}`, '3PM': s['3PM'], '3PA': s['3PA'], '3P': `${s['3PA'] ? s['3PM'] + '/' + s['3PA'] : '0/0'}`, FTM: s.FTM, FTA: s.FTA, FT: `${s.FTA ? s.FTM + '/' + s.FTA : '0/0'}`, OReb: s.OReb, DReb: s.DReb, Reb: s.Reb, Ast: s.Assists, Stl: s.Steals, Blk: s.Blocks, TO: s.Turnovers, PF: s.Fouls }));
        drawReportTable(['Team', 'PTS', 'FGM', 'FGA', 'FG', '3PM', '3PA', '3P', 'FTM', 'FTA', 'FT', 'OReb', 'DReb', 'Reb', 'Ast', 'Stl', 'Blk', 'TO', 'PF'], teams);
        const totalPts = teams.reduce((n, t) => n + (t.PTS || 0), 0);
        drawKpis([['Games', games.length || 1], ['Total PTS', totalPts], ['Events', rows.length]]);
        reportSummary.value = 'Team totals across selected scope.'; return;
    }
    if (type === 'player-totals' || type === 'opponent-totals' || type === 'box-score') {
        const liberty = ourTeamNameInput.value.trim() || 'Our Team';
        const rowsPlayers = Object.values(acc.byPlayer).filter(p => {
            if (type === 'player-totals' || type === 'box-score') return p.Team === liberty || p.Team === 'Our Team';
            return p.Team !== liberty && p.Team !== 'Our Team';
        }).map(p => ({ Team: p.Team, Player: p.Player, Min: formatSecondsToMMSS(p.Seconds), PTS: p.Points, FGM: p.FGM, FGA: p.FGA, FG: `${p.FGA ? p.FGM + '/' + p.FGA : '0/0'}`, '3PM': p['3PM'], '3PA': p['3PA'], '3P': `${p['3PA'] ? p['3PM'] + '/' + p['3PA'] : '0/0'}`, FTM: p.FTM, FTA: p.FTA, FT: `${p.FTA ? p.FTM + '/' + p.FTA : '0/0'}`, OReb: p.OReb, DReb: p.DReb, Reb: p.Reb, Ast: p.Assists, Stl: p.Steals, Blk: p.Blocks, TO: p.Turnovers, PF: p.Fouls }));
        const cols = (type === 'box-score' ? ['Player', 'Min', 'PTS', 'FGM', 'FGA', 'FG', '3PM', '3PA', '3P', 'FTM', 'FTA', 'FT', 'OReb', 'DReb', 'Reb', 'Ast', 'Stl', 'Blk', 'TO', 'PF'] : ['Team', 'Player', 'Min', 'PTS', 'FGM', 'FGA', 'FG', '3PM', '3PA', '3P', 'FTM', 'FTA', 'FT', 'OReb', 'DReb', 'Reb', 'Ast', 'Stl', 'Blk', 'TO', 'PF']);
        drawReportTable(cols, rowsPlayers);
        const pts = rowsPlayers.reduce((n, r) => n + (r.PTS || 0), 0);
        drawKpis([['Games', games.length || 1], ['Players', rowsPlayers.length], ['Total PTS', pts]]);
        reportSummary.value = (type === 'box-score' ? 'Box score for Liberty in the selected game/scope.' : (type === 'player-totals' ? 'Liberty player totals across selected scope.' : 'Opponent player totals across selected scope.'));
        return;
    }
    if (type === 'record-summary') {
        const summary = teamRecordSummary(games);
        drawReportTable(['Category', 'Record'], summary);
        drawKpis([['Games', games.length]]);
        reportSummary.value = 'Record summary based on saved results.'; return;
    }
}

// ── Vocabulary Management ───────────────────────────────────
function loadVocabulary() {
    const selectFields = ['quarter', 'team', 'side', 'category', 'eventtype', 'result'];
    termFieldSelect.innerHTML = '';
    selectFields.forEach(f => { const opt = document.createElement('option'); opt.value = f; opt.textContent = f; termFieldSelect.appendChild(opt); });
    renderTermList();
}

function renderTermList() {
    termList.innerHTML = '';
    const field = termFieldSelect.value;
    const terms = vocabulary[field] || [];
    terms.forEach((term, index) => {
        const row = document.createElement('div'); row.className = 'term-item';
        const label = document.createElement('div'); label.textContent = term; row.appendChild(label);
        const up = document.createElement('button'); up.type = 'button'; up.textContent = 'Up';
        up.addEventListener('click', function () { if (index === 0) return; const tmp = terms[index - 1]; terms[index - 1] = terms[index]; terms[index] = tmp; vocabulary[field] = terms; persistVocab(); renderTermList(); });
        const down = document.createElement('button'); down.type = 'button'; down.textContent = 'Down';
        down.addEventListener('click', function () { if (index === terms.length - 1) return; const tmp = terms[index + 1]; terms[index + 1] = terms[index]; terms[index] = tmp; vocabulary[field] = terms; persistVocab(); renderTermList(); });
        const del = document.createElement('button'); del.type = 'button'; del.textContent = 'Remove';
        del.addEventListener('click', function () { vocabulary[field] = terms.filter(function (_, i) { return i !== index; }); persistVocab(); renderTermList(); });
        row.appendChild(up); row.appendChild(down);
        if (!lockedFields.includes(field)) row.appendChild(del);
        termList.appendChild(row);
    });
}

function addTerm() {
    const field = termFieldSelect.value;
    const value = normalize(newTermInput.value);
    if (!value) return;
    if (lockedFields.includes(field)) { alert('This field is locked.'); return; }
    if (!vocabulary[field].includes(value)) { vocabulary[field].push(value); vocabulary[field].sort((a, b) => a.localeCompare(b)); persistVocab(); renderTermList(); }
    newTermInput.value = '';
}

// ── Roster Management ───────────────────────────────────────
function showRoster() {
    const key = getRosterKey();
    const list = sortPlayers(rosters[key] || []);
    playerList.innerHTML = '';
    if (!list.length) { playerList.innerHTML = '<div class="empty-state tiny">No players yet for this roster.</div>'; return; }
    list.forEach(player => {
        const row = document.createElement('div'); row.className = 'term-item';
        const label = document.createElement('div'); label.textContent = player;
        const del = document.createElement('button'); del.type = 'button'; del.textContent = 'Remove';
        del.addEventListener('click', () => { rosters[key] = (rosters[key] || []).filter(p => p !== player); persistRosters(); showRoster(); });
        row.appendChild(label); row.appendChild(del); playerList.appendChild(row);
    });
}

function importRosterCsv(file) {
    const reader = new FileReader();
    reader.onload = e => {
        const text = e.target.result;
        const lines = text.split(/\r?\n/);
        const key = getRosterKey();
        const players = rosters[key] || [];
        const headerWords = ['pos', 'position', '#', 'num', 'number', 'name', 'grade', 'class', 'yr'];
        lines.forEach(line => {
            const raw = line.trim(); if (!raw) return;
            const parts = raw.split(',').map(x => x.trim()).filter(Boolean);
            if (parts.length === 0) return;
            const lower = parts.map(p => p.toLowerCase());
            if (lower.some(p => headerWords.includes(p))) return;
            let numPart = null, namePart = null;
            parts.forEach(p => { if (/^\d+$/.test(p)) { if (numPart === null) numPart = p; } else if (!headerWords.includes(p.toLowerCase())) { if (!namePart || p.length > namePart.length) namePart = p; } });
            if (!namePart) return;
            players.push(numPart ? `${numPart} - ${namePart}` : namePart);
        });
        rosters[key] = sortPlayers(players);
        persistRosters(); showRoster(); setStatus('Imported roster from CSV.');
    };
    reader.readAsText(file);
}

function openAddPlayerDialog() {
    playerPosInput.value = ''; playerNumInput.value = ''; playerNameInput.value = ''; playerGradeInput.value = '';
    playerDialog.showModal();
}

function savePlayerFromDialog() {
    const pos = normalize(playerPosInput.value), num = normalize(playerNumInput.value), name = normalize(playerNameInput.value), grade = normalize(playerGradeInput.value);
    if (!num && !name) { alert('At least a jersey number or a name is required.'); return; }
    let label = ''; if (num && name) label = `${num} - ${name}`; else if (num) label = num; else label = name;
    if (grade) label += `, ${grade}`;
    const key = getRosterKey();
    rosters[key] = sortPlayers([...(rosters[key] || []), label]);
    persistRosters(); showRoster(); playerDialog.close();
}

// ── Starters / Lineup ───────────────────────────────────────
function renderStarterChoices(listEl, team, selectedSet) {
    listEl.innerHTML = '';
    const roster = rosterForTeam(team);
    if (!roster.length) { listEl.innerHTML = '<div class="empty-state tiny">No players yet for this team.</div>'; return; }
    roster.forEach(player => {
        const row = document.createElement('div'); row.className = 'term-item';
        const label = document.createElement('div'); label.textContent = player;
        const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = selectedSet.has(player);
        checkbox.addEventListener('change', () => {
            if (checkbox.checked) { if (selectedSet.size >= 5) { checkbox.checked = false; alert('Only 5 starters allowed for this team.'); return; } selectedSet.add(player); }
            else selectedSet.delete(player);
        });
        row.appendChild(label); row.appendChild(checkbox); listEl.appendChild(row);
    });
    const addRowEl = document.createElement('div'); addRowEl.className = 'term-item';
    const addLabel = document.createElement('div'); addLabel.textContent = 'Add new player';
    const addBtn = document.createElement('button'); addBtn.type = 'button'; addBtn.textContent = 'Add';
    addBtn.addEventListener('click', () => {
        const name = prompt('New player name/number e.g. 24 - Smith'); if (!name) return;
        const key = mapTeamToRosterKey(team); rosters[key] = sortPlayers([...(rosters[key] || []), name]); persistRosters();
        renderStarterChoices(listEl, team, selectedSet);
    });
    addRowEl.appendChild(addLabel); addRowEl.appendChild(addBtn); listEl.appendChild(addRowEl);
}

function openStartersDialog(mode = 'initial') {
    startersMode = mode;
    if (!video.paused) video.pause();
    const liberty = ourTeamNameInput.value.trim() || 'Our Team';
    const opp = opponentInput.value.trim() || 'Opponent';
    startersHelp.textContent = mode === 'initial' ? `Choose the five ${liberty} starters before tip. Opponent is optional.` : `Update who is currently on the floor for ${liberty} and ${opp}. Max 5 each.`;
    const libertySelected = mode === 'initial' ? new Set(currentStarters?.liberty || []) : new Set(currentLineups.liberty);
    const opponentSelected = mode === 'initial' ? new Set(currentStarters?.opponent || []) : new Set(currentLineups.opponent);
    renderStarterChoices(libertyStartersList, liberty, libertySelected);
    renderStarterChoices(opponentStartersList, opp, opponentSelected);
    startersDialog.returnValue = '';
    startersDialog.showModal();
    document.getElementById('startersSaveBtn').onclick = () => {
        if (libertySelected.size !== 5) { alert(`Please pick exactly 5 starters for ${liberty}.`); return; }
        const libertyArr = Array.from(libertySelected), oppArr = Array.from(opponentSelected);
        if (mode === 'initial') {
            currentStarters = { libertyTeam: liberty, opponentTeam: opp, liberty: libertyArr, opponent: oppArr };
            currentLineups.liberty = new Set(libertyArr); currentLineups.opponent = new Set(oppArr);
        } else {
            tagLineupChanges(liberty, new Set(currentLineups.liberty), libertySelected);
            tagLineupChanges(opp, new Set(currentLineups.opponent), opponentSelected);
            currentLineups.liberty = new Set(libertyArr); currentLineups.opponent = new Set(oppArr);
        }
        startersDialog.close();
        setStatus(mode === 'initial' ? 'Starters recorded.' : 'Lineups updated from SUB dialog.');
    };
}

function tagLineupChanges(teamName, prevSet, newSet) {
    const team = teamName;
    prevSet.forEach(player => {
        if (!newSet.has(player)) addRow({ label: 'Sub Out', player, quarter: currentQuarter(), team, side: 'Neutral', category: 'Substitution', eventtype: 'SubOut', result: 'NA', start: formatTime(video.currentTime || 0), duration: '0:00.0', notes: '' });
    });
    newSet.forEach(player => {
        if (!prevSet.has(player)) addRow({ label: 'Sub In', player, quarter: currentQuarter(), team, side: 'Neutral', category: 'Substitution', eventtype: 'SubIn', result: 'NA', start: formatTime(video.currentTime || 0), duration: '0:00.0', notes: '' });
    });
    handleRowsChanged();
}

function tagSubstitution() { openStartersDialog('adjust'); }

// ── Theme ───────────────────────────────────────────────────
function loadTheme() {
    const stored = localStorage.getItem('filmToolThemeV1');
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.dataset.theme = stored || (prefersDark ? 'dark' : 'light');
}
function toggleTheme() {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    localStorage.setItem('filmToolThemeV1', next);
}

// ── Report Save / Print ─────────────────────────────────────
function saveReportAsFile() {
    const title = reportTitle.textContent || 'report';
    const safeTitle = safeSlug(title) || 'report';
    const content = `${title}\n\n${reportSummary.value}\n\n${reportTableBody.innerText}`;
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = `${safeTitle}.txt`; a.click();
    URL.revokeObjectURL(url);
}

function printReport() {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.getElementById('reportsView').classList.add('active', 'print-target');
    window.print();
    document.getElementById('reportsView').classList.remove('print-target');
}

// ── Tab Navigation ──────────────────────────────────────────
function setActiveTab(id) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    const btn = document.querySelector(`.tab-btn[data-tab="${id}"]`);
    if (btn) btn.classList.add('active');
    document.getElementById(id).classList.add('active');
}

// ── Focus Mode ──────────────────────────────────────────────
function toggleGameInfo() {
    const container = document.getElementById('gameInfoFields');
    const btn = document.getElementById('toggleInfoBtn');
    if (container.style.display === 'none') {
        container.style.display = ''; document.body.classList.remove('tagger-focus');
        focusExitBtn.classList.add('hidden'); btn.textContent = 'Hide game info';
    } else {
        container.style.display = 'none'; document.body.classList.add('tagger-focus');
        focusExitBtn.classList.remove('hidden'); btn.textContent = 'Show game info';
    }
}

function exitFocusMode() {
    const container = document.getElementById('gameInfoFields');
    const btn = document.getElementById('toggleInfoBtn');
    container.style.display = ''; document.body.classList.remove('tagger-focus');
    focusExitBtn.classList.add('hidden'); btn.textContent = 'Hide game info';
}

// ── AI Events ───────────────────────────────────────────────
function parseAiEventDetails(raw) { if (!raw) return {}; try { return JSON.parse(raw); } catch (_err) { return {}; } }

function summarizeAiEvent(event) {
    const details = parseAiEventDetails(event.details_json);
    const parts = [];
    if (event.shot_result) parts.push(`result: ${event.shot_result}`);
    if (details.from_player && details.to_player) parts.push(`${details.from_player} -> ${details.to_player}`);
    if (details.from_player && !details.to_player) parts.push(`from ${details.from_player}`);
    if (details.next_possessor) parts.push(`to ${details.next_possessor}`);
    if (details.shot_player) parts.push(`shot by ${details.shot_player}`);
    if (details.scorer) parts.push(`scorer ${details.scorer}`);
    if (details.gap_frames != null) parts.push(`gap ${details.gap_frames} frames`);
    if (details.ball_rise != null) parts.push(`rise ${details.ball_rise}`);
    if (details.note) parts.push(details.note);
    if (event.confidence != null) parts.push(`conf ${(Number(event.confidence) * 100).toFixed(0)}%`);
    return parts.length ? parts.join(' · ') : 'Click to jump video playback to this event.';
}

function updateAiEventsSummary() {
    if (aiEventsCount) aiEventsCount.textContent = `${aiEventsCache.length} event${aiEventsCache.length === 1 ? '' : 's'}`;
    if (!aiCurrentEventLabel) return;
    const active = aiEventsCache.find(event => String(event.id) === String(activeAiEventId));
    aiCurrentEventLabel.textContent = active ? `Active event: ${active.event_type} at ${formatTime(active.timestamp_ms / 1000)}` : 'No active event at the current playback position.';
}

function setActiveAiEvent(eventId, shouldScroll = false) {
    activeAiEventId = eventId == null ? null : String(eventId);
    if (!aiEventsList) return;
    aiEventsList.querySelectorAll('[data-ai-event-id]').forEach(item => {
        const isActive = activeAiEventId && item.dataset.aiEventId === activeAiEventId;
        item.classList.toggle('active', Boolean(isActive));
        if (isActive && shouldScroll) item.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    });
    updateAiEventsSummary();
}

function syncAiEventsToPlayback() {
    if (!video || !aiEventsCache.length) { setActiveAiEvent(null); return; }
    const currentMs = Math.round((video.currentTime || 0) * 1000);
    let nearest = null, nearestDistance = Infinity;
    aiEventsCache.forEach(event => { const distance = Math.abs(Number(event.timestamp_ms || 0) - currentMs); if (distance < nearestDistance) { nearestDistance = distance; nearest = event; } });
    if (!nearest || nearestDistance > 5000) { setActiveAiEvent(null); return; }
    setActiveAiEvent(nearest.id, String(nearest.id) !== String(activeAiEventId));
}

function renderAiEvents(events) {
    if (!aiEventsList) return;
    aiEventsCache = events.filter(event => event.event_type !== 'bookmark');
    if (!aiEventsCache.length) { aiEventsList.innerHTML = '<div class="empty-state">No AI events found for this game.</div>'; setActiveAiEvent(null); return; }
    aiEventsList.innerHTML = aiEventsCache.map(event => `
        <div class="ai-event-item" data-ai-event-id="${event.id}" data-ai-event-ts="${event.timestamp_ms}" tabindex="0" role="button" aria-label="Jump to ${event.event_type} at ${formatTime(event.timestamp_ms / 1000)}">
            <div class="ai-event-row"><strong>${event.event_type}</strong><span class="ai-event-time">${formatTime(event.timestamp_ms / 1000)}</span></div>
            <div class="tiny">${event.player || 'AI detected event'}</div>
            <div class="ai-event-details">${summarizeAiEvent(event)}</div>
        </div>`).join('');
    aiEventsList.querySelectorAll('[data-ai-event-id]').forEach(item => {
        const seekToEvent = () => { const ms = Number(item.dataset.aiEventTs || '0'); video.currentTime = ms / 1000; setActiveAiEvent(item.dataset.aiEventId, true); setStatus(`Jumped to AI event at ${(ms / 1000).toFixed(1)}s.`); };
        item.addEventListener('click', seekToEvent);
        item.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); seekToEvent(); } });
    });
    syncAiEventsToPlayback();
}

async function fetchAndRenderAIEvents(gameId) {
    if (!gameId || !aiEventsList) return;
    aiEventsList.innerHTML = '<div class="empty-state">Loading AI events...</div>';
    try {
        const response = await fetch(`/api/events/${gameId}`);
        if (!response.ok) { aiEventsList.innerHTML = '<div class="empty-state">Could not load AI events.</div>'; aiEventsCache = []; updateAiEventsSummary(); return; }
        const events = await response.json();
        renderAiEvents(events);
    } catch (_err) { aiEventsList.innerHTML = '<div class="empty-state">Error loading AI events.</div>'; aiEventsCache = []; updateAiEventsSummary(); }
}

// ── Video ───────────────────────────────────────────────────
function loadHostedVideo(url, name) {
    if (!url) return;
    video.src = url; video.load();
    setStatus(`Loaded uploaded video: ${name || 'server video'}`);
}

function handleVideoFile(e) {
    const file = e.target.files[0]; if (!file) return;
    video.src = URL.createObjectURL(file); video.load();
    setStatus(`Loaded video: ${file.name}`);
}

function handleDirectoryPick() {
    if (!window.showDirectoryPicker) { alert('Directory picker not supported in this browser. Type the folder path manually.'); return; }
    window.showDirectoryPicker().then(handle => { outputDirInput.value = handle.name; setStatus(`Output folder: ${handle.name} (browser-limited name only)`); }).catch(() => { });
}

// ── Undo / Clear ────────────────────────────────────────────
function undoLastRow() {
    const rows = [...rowsBody.querySelectorAll('tr')]; if (!rows.length) return;
    rows[rows.length - 1].remove(); handleRowsChanged(); updateEventCount(); setStatus('Undid last tagged event.');
}

// ── Analysis Status Polling ─────────────────────────────────
function initAnalysisStatus() {
    const gameId = uploadedVideoName ? '' : ''; // placeholder, actual game_id set inline
    const autoStatsEnabled = typeof ENABLE_AUTO_STATS_M1 !== 'undefined' ? ENABLE_AUTO_STATS_M1 : false;
    const statusTextEl = document.getElementById('ai-status-text');
    const statusDetailEl = document.getElementById('ai-status-detail');

    function updateStatusText(status) { if (statusTextEl) statusTextEl.textContent = status; }
    function updateStatusDetail(detail) { if (statusDetailEl) statusDetailEl.textContent = detail; }

    async function fetchAnalysisStatus() {
        if (!gameId) { updateStatusText('no game selected'); updateStatusDetail('Upload a video or open a film link with a game_id.'); return; }
        try {
            const response = await fetch(`/api/analysis_status/${encodeURIComponent(gameId)}`);
            if (!response.ok) { updateStatusText('unknown'); updateStatusDetail('Could not load analysis details.'); return; }
            const data = await response.json();
            updateStatusText(data.status || 'unknown');
            updateStatusDetail(`${data.detection_count ?? 0} detections · ${data.event_count ?? 0} events · ${data.event_generation_summary || ''}`);
            if (data.status === 'running' || data.status === 'pending') setTimeout(fetchAnalysisStatus, 5000);
            else if (data.status === 'completed') fetchAndRenderAIEvents(gameId);
        } catch (err) { console.error('Error fetching analysis status:', err); updateStatusText('error'); updateStatusDetail('Analysis polling failed.'); }
    }

    window.addEventListener('load', () => {
        if (!autoStatsEnabled) return;
        if (gameId) { updateStatusText('checking...'); updateStatusDetail('Loading detections and event counts…'); fetchAnalysisStatus(); }
        else { updateStatusText('no game selected'); updateStatusDetail('Upload a video or open a film link with a game_id.'); }
    });
}

// ── Manual Bookmarks ────────────────────────────────────────
function initBookmarks() {
    const bookmarkGameIdInput = document.getElementById('bookmarkGameId');
    const bookmarkLabelInput = document.getElementById('bookmarkLabel');
    const bookmarkNoteInput = document.getElementById('bookmarkNote');
    const bookmarkStatus = document.getElementById('bookmarkStatus');
    const manualBookmarksList = document.getElementById('manualBookmarksList');

    function getBookmarkGameId() { return (bookmarkGameIdInput?.value || '').trim(); }
    function setBookmarkStatus(message) { if (bookmarkStatus) bookmarkStatus.textContent = message; }
    function parseBookmarkDetails(raw) { if (!raw) return {}; try { return JSON.parse(raw); } catch (_err) { return {}; } }

    function renderBookmarks(events) {
        if (!manualBookmarksList) return;
        if (!events.length) { manualBookmarksList.innerHTML = '<div class="empty-state">No bookmarks saved for this game yet.</div>'; setBookmarkStatus('No bookmarks found.'); return; }
        manualBookmarksList.innerHTML = events.map(event => {
            const details = parseBookmarkDetails(event.details_json);
            const label = event.player || details.label || 'Bookmark';
            const note = details.note ? `<div class="tiny">${details.note}</div>` : '';
            const seconds = (event.timestamp_ms / 1000).toFixed(1);
            return `<div class="term-item"><div><strong>${label}</strong><div class="tiny">${seconds}s</div>${note}</div><button type="button" data-bookmark-seek="${event.timestamp_ms}">Jump</button><button type="button" data-bookmark-delete="${event.id}">Delete</button></div>`;
        }).join('');
        manualBookmarksList.querySelectorAll('[data-bookmark-seek]').forEach(btn => { btn.addEventListener('click', () => { const ms = Number(btn.dataset.bookmarkSeek || '0'); video.currentTime = ms / 1000; if (typeof setStatus === 'function') setStatus(`Jumped to bookmark at ${(ms / 1000).toFixed(1)}s.`); }); });
        manualBookmarksList.querySelectorAll('[data-bookmark-delete]').forEach(btn => { btn.addEventListener('click', async () => { await fetch(`/api/events/${btn.dataset.bookmarkDelete}`, { method: 'DELETE' }); await loadManualBookmarks(); }); });
        setBookmarkStatus(`Loaded ${events.length} bookmark${events.length === 1 ? '' : 's'}.`);
    }

    async function loadManualBookmarks() {
        const bookmarkGameId = getBookmarkGameId();
        if (!bookmarkGameId) { renderBookmarks([]); if (manualBookmarksList) manualBookmarksList.innerHTML = '<div class="empty-state">Enter a game ID to load bookmarks.</div>'; setBookmarkStatus('Missing game ID.'); return; }
        try {
            const response = await fetch(`/api/events/${encodeURIComponent(bookmarkGameId)}?event_type=bookmark`);
            if (!response.ok) { setBookmarkStatus('Failed to load bookmarks.'); return; }
            const events = await response.json(); renderBookmarks(events);
        } catch (err) { console.error('Error loading manual bookmarks:', err); setBookmarkStatus('Error loading bookmarks.'); }
    }

    async function saveManualBookmark() {
        const bookmarkGameId = getBookmarkGameId();
        if (!bookmarkGameId) { setBookmarkStatus('Enter a game ID before saving.'); return; }
        const label = (bookmarkLabelInput?.value || '').trim() || 'Bookmark';
        const note = (bookmarkNoteInput?.value || '').trim();
        const payload = { game_id: bookmarkGameId, player: label, event_type: 'bookmark', timestamp_ms: Math.round(video.currentTime * 1000), details_json: JSON.stringify({ label, note }), source_video: uploadedVideoName || '', human_verified: true };
        const response = await fetch('/api/save_event', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        if (!response.ok) { setBookmarkStatus('Failed to save bookmark.'); return; }
        if (bookmarkLabelInput) bookmarkLabelInput.value = '';
        if (bookmarkNoteInput) bookmarkNoteInput.value = '';
        setBookmarkStatus('Bookmark saved.'); await loadManualBookmarks();
    }

    document.getElementById('saveBookmarkBtn')?.addEventListener('click', saveManualBookmark);
    document.getElementById('refreshBookmarksBtn')?.addEventListener('click', loadManualBookmarks);
    bookmarkGameIdInput?.addEventListener('change', loadManualBookmarks);
    window.addEventListener('load', () => { if (getBookmarkGameId()) loadManualBookmarks(); });
}

// ── Resource Status Monitor ──────────────────────────────────
function initResourceMonitor() {
    function setResourceValue(key, value) { const el = document.querySelector(`[data-resource="${key}"]`); if (el) el.textContent = value; }
    function formatPercent(value) { return value == null ? '--' : `${Number(value).toFixed(0)}%`; }
    function formatMb(value) { return value == null ? '--' : `${Number(value).toFixed(0)} MB`; }
    function formatWatts(value) { return value == null ? null : `${Number(value).toFixed(1)} W`; }
    function formatPowerSummary(power) {
        if (!power) return '--';
        const parts = [];
        if (power.cpu_watts != null) parts.push(`CPU ${formatWatts(power.cpu_watts)}`);
        if (power.gpu_watts != null) parts.push(`GPU ${formatWatts(power.gpu_watts)}`);
        if (power.total_watts != null && parts.length > 1) parts.push(`Total ${formatWatts(power.total_watts)}`);
        return parts.length ? parts.join(' · ') : '--';
    }
    function escapeHtml(value) { return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
    function renderGpuProcesses(processes) {
        const el = document.getElementById('gpu-process-details'); if (!el) return;
        if (!processes || !processes.length) { el.textContent = 'GPU processes: none detected'; return; }
        el.innerHTML = processes.map(p => `<span class="resource-pill"><strong>${escapeHtml((p.name || `PID ${p.pid}`) + (p.is_self_project ? '(self)' : ''))}</strong> GPU ${formatMb(p.gpu_memory_mb)} · CPU ${formatPercent(p.cpu_percent)} · RAM ${formatMb(p.memory_mb)}</span>`).join('');
    }
    async function refreshResourceStatus() {
        try {
            const response = await fetch('/api/resource-status'); if (!response.ok) return;
            const data = await response.json();
            setResourceValue('cpu-system', formatPercent(data.cpu?.system_percent));
            setResourceValue('cpu-process', formatPercent(data.application?.cpu_percent ?? data.cpu?.process_percent));
            setResourceValue('memory-system', data.memory?.used_gb == null ? '--' : `${data.memory.used_gb}/${data.memory.total_gb} GB (${formatPercent(data.memory.system_percent)})`);
            setResourceValue('memory-process', data.application?.memory_mb == null ? '--' : formatMb(data.application.memory_mb));
            setResourceValue('power-live', formatPowerSummary(data.power));
            setResourceValue('gpu-util', data.gpu?.available ? `${data.gpu.name} ${formatPercent(data.gpu.utilization_percent)}` : 'Unavailable');
            setResourceValue('gpu-memory', data.gpu?.available ? `${Number(data.gpu.memory_used_mb).toFixed(0)}/${Number(data.gpu.memory_total_mb).toFixed(0)} MB` : 'Unavailable');
            renderGpuProcesses(data.gpu?.processes);
        } catch (_err) { setResourceValue('power-live', '--'); setResourceValue('gpu-util', 'Unavailable'); renderGpuProcesses([]); }
    }
    refreshResourceStatus();
    setInterval(refreshResourceStatus, 2000);
}

// ── Report Drawer ───────────────────────────────────────────
function initReportDrawer() {
    const drawer = document.getElementById('report-drawer');
    const backdrop = document.getElementById('report-drawer-backdrop');
    const form = document.getElementById('report-drawer-form');
    const message = document.getElementById('report-drawer-message');
    const closeButton = document.getElementById('report-drawer-close');
    const cancelButton = document.getElementById('report-drawer-cancel');
    const submitButton = document.getElementById('report-drawer-submit');
    const sourceInput = document.getElementById('report-source-path');
    const returnToInput = document.getElementById('report-return-to');
    const consoleInput = document.getElementById('report-browser-console');
    const detailsInput = document.getElementById('report-details');
    if (!drawer || !backdrop || !form || !sourceInput || !returnToInput || !consoleInput) return;

    function setReportMessage(kind, text) {
        if (!message) return;
        if (!text) { message.style.display = 'none'; message.textContent = ''; message.style.color = ''; return; }
        message.style.display = 'block'; message.textContent = text;
        message.style.color = kind === 'error' ? 'var(--color-error)' : 'var(--color-success)';
    }
    function syncReportContext() {
        sourceInput.value = window.LibertyIssueReporter?.getCurrentPagePath?.() || `${window.location.pathname}${window.location.search}${window.location.hash}`;
        returnToInput.value = sourceInput.value;
        consoleInput.value = window.LibertyIssueReporter?.getConsoleText?.() || '';
    }
    function openDrawer() { syncReportContext(); setReportMessage(null, ''); drawer.classList.add('open'); drawer.setAttribute('aria-hidden', 'false'); backdrop.classList.add('open'); document.body.classList.add('report-drawer-open'); window.setTimeout(() => detailsInput?.focus(), 0); }
    function closeDrawer() { drawer.classList.remove('open'); drawer.setAttribute('aria-hidden', 'true'); backdrop.classList.remove('open'); document.body.classList.remove('report-drawer-open'); }

    document.querySelectorAll('[data-open-report-overlay]').forEach(trigger => { trigger.addEventListener('click', (event) => { event.preventDefault(); openDrawer(); }); });
    [backdrop, closeButton, cancelButton].forEach(el => { el?.addEventListener('click', closeDrawer); });
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && drawer.classList.contains('open')) closeDrawer(); });

    form.addEventListener('submit', async (event) => {
        event.preventDefault(); syncReportContext(); setReportMessage(null, '');
        submitButton.disabled = true; submitButton.textContent = 'Saving…';
        try {
            const response = await fetch(form.action, { method: 'POST', body: new FormData(form), headers: { 'X-Requested-With': 'XMLHttpRequest' } });
            const result = await response.json();
            if (!response.ok || result.status !== 'ok') throw new Error(result.message || 'Unable to save report.');
            setReportMessage('success', result.message || 'Report saved.'); form.reset();
            document.getElementById('report-entry-type').value = 'issue'; syncReportContext();
            window.setTimeout(closeDrawer, 700);
        } catch (error) { setReportMessage('error', error.message || 'Unable to save report.'); }
        finally { submitButton.disabled = false; submitButton.textContent = 'Save Report'; }
    });
}

// ── AI Upload Form ──────────────────────────────────────────
function initAiUpload() {
    const aiUploadForm = document.getElementById('aiUploadForm');
    const uploadProgressShell = document.getElementById('uploadProgressShell');
    const uploadProgressBar = document.getElementById('uploadProgressBar');
    const uploadProgressText = document.getElementById('uploadProgressText');
    if (!aiUploadForm) return;

    aiUploadForm.addEventListener('submit', (event) => {
        event.preventDefault();
        const formData = new FormData(aiUploadForm);
        const xhr = new XMLHttpRequest();
        xhr.open('POST', aiUploadForm.action);
        xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
        uploadProgressShell?.classList.add('active');
        if (uploadProgressBar) uploadProgressBar.style.width = '0%';
        if (uploadProgressText) uploadProgressText.textContent = 'Starting upload…';
        xhr.upload.addEventListener('progress', (progressEvent) => {
            if (!progressEvent.lengthComputable) return;
            const percent = Math.round((progressEvent.loaded / progressEvent.total) * 100);
            if (uploadProgressBar) uploadProgressBar.style.width = `${percent}%`;
            if (uploadProgressText) uploadProgressText.textContent = `Uploading video… ${percent}%`;
        });
        xhr.addEventListener('load', () => {
            if (xhr.status < 200 || xhr.status >= 300) { if (uploadProgressText) uploadProgressText.textContent = 'Upload failed.'; return; }
            const payload = JSON.parse(xhr.responseText);
            if (uploadProgressBar) uploadProgressBar.style.width = '100%';
            if (uploadProgressText) uploadProgressText.textContent = 'Upload complete. Redirecting to film tool…';
            window.location.href = payload.redirect_url;
        });
        xhr.addEventListener('error', () => { if (uploadProgressText) uploadProgressText.textContent = 'Upload failed.'; });
        xhr.send(formData);
    });
}

// ── Event Handlers ──────────────────────────────────────────
function attachEventHandlers() {
    document.querySelectorAll('.tab-btn').forEach(btn => { btn.addEventListener('click', () => setActiveTab(btn.dataset.tab)); });
    const themeToggle = document.querySelector('[data-theme-toggle]');
    if (themeToggle) themeToggle.addEventListener('click', toggleTheme);

    document.getElementById('manageTermsBtn')?.addEventListener('click', () => { loadVocabulary(); termDialog.showModal(); });
    document.getElementById('saveNewTermBtn')?.addEventListener('click', addTerm);
    termFieldSelect?.addEventListener('change', renderTermList);

    document.getElementById('manageRostersBtn')?.addEventListener('click', () => { showRoster(); rosterDialog.showModal(); });
    document.querySelectorAll('.roster-side-btn').forEach(btn => { btn.addEventListener('click', () => { document.querySelectorAll('.roster-side-btn').forEach(b => b.classList.remove('active')); btn.classList.add('active'); currentRosterSide = btn.dataset.side; showRoster(); }); });
    document.querySelectorAll('input[name="level"]').forEach(r => { r.addEventListener('change', () => showRoster()); });
    document.querySelectorAll('input[name="gender"]').forEach(r => { r.addEventListener('change', () => showRoster()); });
    rosterCsvInput?.addEventListener('change', e => { const file = e.target.files[0]; if (file) importRosterCsv(file); });
    document.getElementById('addPlayerBtn')?.addEventListener('click', openAddPlayerDialog);
    document.getElementById('playerCancelBtn')?.addEventListener('click', () => playerDialog.close());
    document.getElementById('playerSaveBtn')?.addEventListener('click', savePlayerFromDialog);
    document.getElementById('chooseOutputBtn')?.addEventListener('click', handleDirectoryPick);
    videoFileInput?.addEventListener('change', handleVideoFile);

    document.getElementById('undoBtn')?.addEventListener('click', undoLastRow);
    document.getElementById('clearAllBtn')?.addEventListener('click', () => { if (confirm('Clear all tagged events in this game?')) clearAllRows(); });
    document.getElementById('subBtn')?.addEventListener('click', tagSubstitution);
    document.getElementById('startersBtn')?.addEventListener('click', () => openStartersDialog('initial'));

    document.getElementById('newGameBtn')?.addEventListener('click', () => {
        if (!confirm('Start a new game? This clears current tagged rows.')) return;
        clearAllRows(); resetGameMetadata();
    });
    document.getElementById('saveGameBtn')?.addEventListener('click', saveCurrentGameToLibrary);
    document.getElementById('resumeLastBtn')?.addEventListener('click', resumeLastGame);
    document.getElementById('generateReportBtn')?.addEventListener('click', generateReport);
    document.getElementById('printReportBtn')?.addEventListener('click', () => window.print());
    document.getElementById('saveReportBtn')?.addEventListener('click', saveReportAsFile);
    document.getElementById('exportBtn')?.addEventListener('click', exportGameData);
    document.getElementById('toggleInfoBtn')?.addEventListener('click', toggleGameInfo);
    focusExitBtn?.addEventListener('click', exitFocusMode);
    document.getElementById('quickTagCancelBtn')?.addEventListener('click', () => quickTagDialog.close());

    document.querySelectorAll('.video-controls [data-skip]').forEach(btn => { btn.addEventListener('click', () => { video.currentTime = Math.max(0, Math.min(video.duration || 0, video.currentTime + parseFloat(btn.dataset.skip || '0'))); }); });
    document.getElementById('vidPlayPauseBtn')?.addEventListener('click', () => { if (video.paused) video.play(); else video.pause(); });
    document.getElementById('vidToStartBtn')?.addEventListener('click', () => { video.currentTime = 0; });
    document.getElementById('vidToEndBtn')?.addEventListener('click', () => { video.currentTime = video.duration || 0; });
    document.getElementById('vidSlow5x')?.addEventListener('click', () => { video.playbackRate = 0.5; });
    document.getElementById('vidSlow25x')?.addEventListener('click', () => { video.playbackRate = 0.25; });
    document.getElementById('vidNormalBtn')?.addEventListener('click', () => { video.playbackRate = 1; });
    document.getElementById('vidFast25x')?.addEventListener('click', () => { video.playbackRate = 2.5; });
    document.getElementById('vidFast5x')?.addEventListener('click', () => { video.playbackRate = 5; });

    video.addEventListener('timeupdate', () => { timeDisplay.textContent = formatTime(video.currentTime || 0); syncAiEventsToPlayback(); });
    video.addEventListener('seeked', syncAiEventsToPlayback);
    video.addEventListener('loadedmetadata', () => { timeDisplay.textContent = formatTime(video.currentTime || 0); syncAiEventsToPlayback(); });
}

// ── Autosave Restore ────────────────────────────────────────
function initFromAutosave() {
    const autosave = loadJson(CURRENT_AUTOSAVE_KEY, null);
    if (!autosave) return;
    if (!confirm('Restore autosaved game from last session?')) return;
    loadGameIntoUI(autosave);
}

// ── Init ────────────────────────────────────────────────────
function init() {
    try {
    // Cache DOM references
    rowsBody = document.getElementById('rowsBody');
    statusText = document.getElementById('statusText');
    video = document.getElementById('video');
    timeDisplay = document.getElementById('timeDisplay');
    lastTaggedTime = document.getElementById('lastTaggedTime');
    videoField = document.getElementById('videoField');
    videoShell = document.getElementById('videoShell');
    videoFileInput = document.getElementById('videoFileInput');
    gameTypeSelect = document.getElementById('gameType');
    competitionTypeSelect = document.getElementById('competitionType');
    gameDateInput = document.getElementById('gameDate');
    ourTeamNameInput = document.getElementById('ourTeamName');
    opponentInput = document.getElementById('opponent');
    gameResultSelect = document.getElementById('gameResult');
    homeTeamNameInput = document.getElementById('homeTeamName');
    awayTeamNameInput = document.getElementById('awayTeamName');
    outputDirInput = document.getElementById('outputDir');
    leftScoreName = document.getElementById('leftScoreName');
    rightScoreName = document.getElementById('rightScoreName');
    leftScoreValue = document.getElementById('leftScoreValue');
    rightScoreValue = document.getElementById('rightScoreValue');
    reportScope = document.getElementById('reportScope');
    reportType = document.getElementById('reportType');
    reportTitle = document.getElementById('reportTitle');
    reportSummary = document.getElementById('reportSummary');
    reportHeadRow = document.getElementById('reportHeadRow');
    reportTableBody = document.getElementById('reportTableBody');
    reportKpiGrid = document.getElementById('reportKpiGrid');
    myGamesList = document.getElementById('myGamesList');
    scoutGamesList = document.getElementById('scoutGamesList');
    aiEventsList = document.getElementById('aiEventsList');
    aiEventsScroller = document.getElementById('aiEventsScroller');
    aiEventsCount = document.getElementById('aiEventsCount');
    aiCurrentEventLabel = document.getElementById('aiCurrentEventLabel');
    termDialog = document.getElementById('termDialog');
    termFieldSelect = document.getElementById('termFieldSelect');
    termList = document.getElementById('termList');
    newTermInput = document.getElementById('newTermInput');
    rosterDialog = document.getElementById('rosterDialog');
    playerList = document.getElementById('playerList');
    rosterCsvInput = document.getElementById('rosterCsvInput');
    playerDialog = document.getElementById('playerDialog');
    playerPosInput = document.getElementById('playerPosInput');
    playerNumInput = document.getElementById('playerNumInput');
    playerNameInput = document.getElementById('playerNameInput');
    playerGradeInput = document.getElementById('playerGradeInput');
    quickTagDialog = document.getElementById('quickTagDialog');
    quickDialogTitle = document.getElementById('quickDialogTitle');
    quickTagLabel = document.getElementById('quickTagLabel');
    quickTagBody = document.getElementById('quickTagBody');
    focusExitBtn = document.getElementById('focusExitBtn');
    startersDialog = document.getElementById('startersDialog');
    libertyStartersList = document.getElementById('libertyStartersList');
    opponentStartersList = document.getElementById('opponentStartersList');
    startersHelp = document.getElementById('startersHelp');

    uploadedVideoUrl = window.FILM_TOOL_UPLOADED_VIDEO_URL || '';
    uploadedVideoName = window.FILM_TOOL_UPLOADED_VIDEO_NAME || '';

    loadTheme();
    loadStores();
    renderEventButtons();
    renderGames();
    attachEventHandlers();
    updateScoreLabels();
    renderScore();
    initFromAutosave();

    if (uploadedVideoUrl) loadHostedVideo(uploadedVideoUrl, uploadedVideoName);

    // Collapsible sections
    document.getElementById('ftAiUploadToggle')?.addEventListener('click', function() {
      this.classList.toggle('open');
      document.getElementById('ftAiUploadBody').classList.toggle('open');
    });
    document.getElementById('ftGameInfoToggle')?.addEventListener('click', function() {
      this.classList.toggle('open');
      document.getElementById('ftGameInfoBody').classList.toggle('open');
    });

    const urlParams = new URLSearchParams(window.location.search);
    const gameIdFromUrl = urlParams.get('game_id');
    const activeGameId = gameIdFromUrl || window.FILM_TOOL_GAME_ID || '';
    if (activeGameId) fetchAndRenderAIEvents(activeGameId);
    updateAiEventsSummary();
    timeDisplay.textContent = formatTime(video.currentTime || 0);
    setStatus('Ready.');

    // Initialize sub-modules
    initBookmarks();
    initResourceMonitor();
    initReportDrawer();
    initAiUpload();
    } catch (err) { console.error('Film tool init error:', err); }
}

document.addEventListener('DOMContentLoaded', init);
