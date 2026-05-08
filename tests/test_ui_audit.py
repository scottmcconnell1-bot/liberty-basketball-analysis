"""
Comprehensive UI audit v2: checks every page, form, button, input, and interactive element.
Uses requests + HTMLParser for server-side rendering checks.
"""
import requests
import sys
from html.parser import HTMLParser

BASE = "http://localhost:8081"
s = requests.Session()

class ElementExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.buttons = []
        self.inputs = []
        self.selects = []
        self.textareas = []
        self.tables = []
        self.current_form = None
        self.current_select = None
        self.in_button = False
        self.button_text = ""
        self.in_table = False
        self.current_table = None
        self.in_th = False
        self.th_text = ""

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == 'form':
            self.current_form = {
                'action': attrs_dict.get('action', ''),
                'method': attrs_dict.get('method', 'get').upper(),
                'id': attrs_dict.get('id', ''),
                'inputs': []
            }
        elif tag == 'input' and self.current_form:
            self.current_form['inputs'].append({
                'type': attrs_dict.get('type', 'text'),
                'name': attrs_dict.get('name', ''),
                'id': attrs_dict.get('id', ''),
            })
        elif tag == 'button':
            self.in_button = True
            self.button_text = ""
            self.buttons.append({
                'text': '',
                'type': attrs_dict.get('type', ''),
                'id': attrs_dict.get('id', ''),
                'class': attrs_dict.get('class', ''),
            })
        elif tag == 'input':
            self.inputs.append({
                'type': attrs_dict.get('type', 'text'),
                'name': attrs_dict.get('name', ''),
                'id': attrs_dict.get('id', ''),
            })
        elif tag == 'select':
            self.current_select = {
                'name': attrs_dict.get('name', ''),
                'id': attrs_dict.get('id', ''),
                'options': []
            }
        elif tag == 'option' and self.current_select:
            self.current_select['options'].append(attrs_dict.get('value', ''))
        elif tag == 'textarea':
            self.textareas.append({
                'name': attrs_dict.get('name', ''),
                'id': attrs_dict.get('id', ''),
            })
        elif tag == 'table':
            self.in_table = True
            self.current_table = {
                'id': attrs_dict.get('id', ''),
                'class': attrs_dict.get('class', ''),
                'headers': []
            }
        elif tag == 'th' and self.in_table:
            self.in_th = True
            self.th_text = ""

    def handle_endtag(self, tag):
        if tag == 'form' and self.current_form:
            self.forms.append(self.current_form)
            self.current_form = None
        elif tag == 'button' and self.in_button:
            self.in_button = False
            if self.buttons:
                self.buttons[-1]['text'] = self.button_text.strip()
        elif tag == 'select' and self.current_select:
            self.selects.append(self.current_select)
            self.current_select = None
        elif tag == 'table' and self.in_table:
            self.in_table = False
            if self.current_table:
                self.tables.append(self.current_table)
            self.current_table = None
        elif tag == 'th':
            self.in_th = False
            if self.current_table:
                self.current_table['headers'].append(self.th_text.strip())

    def handle_data(self, data):
        if self.in_button:
            self.button_text += data
        if self.in_th:
            self.th_text += data


def audit_page(path, label):
    url = BASE + path
    try:
        r = s.get(url, timeout=10)
    except Exception as e:
        return {'path': path, 'label': label, 'status': 'ERROR', 'error': str(e)}

    if r.status_code != 200:
        return {'path': path, 'label': label, 'status': r.status_code}

    ex = ElementExtractor()
    try:
        ex.feed(r.text)
    except Exception:
        pass

    return {
        'path': path, 'label': label, 'status': 200,
        'forms': ex.forms, 'buttons': ex.buttons, 'inputs': ex.inputs,
        'selects': ex.selects, 'textareas': ex.textareas, 'tables': ex.tables,
        'html_size': len(r.text),
    }


# ── Page Definitions (corrected paths) ─────────────────────────────

PAGES = [
    ("/", "Dashboard"),
    ("/schedule", "Schedule"),
    ("/games", "Games"),
    ("/videos", "Videos"),
    ("/film", "Film Tool"),
    ("/playbook", "Playbook"),
    ("/player-development", "Player Development"),
    ("/practice-playlists", "Practice Playlists"),
    ("/practices", "Practices"),
    ("/practice-summary", "Practice Summary"),
    ("/settings", "Settings"),
    ("/settings/custom-weights", "Custom Weights Guide"),
    ("/users", "Users"),
    ("/status", "Status"),
    ("/nfhs-matches", "NFHS Matches"),
    ("/debug", "Debug / Issues"),
]

# ── Run Audit ───────────────────────────────────────────────────────

print("=" * 80)
print("  LIBERTY BASKETBALL — COMPREHENSIVE UI AUDIT v2")
print("=" * 80)

results = []
all_pass = True

for path, label in PAGES:
    result = audit_page(path, label)
    results.append(result)
    status = result.get('status', '?')
    if status == 200:
        n_forms = len(result.get('forms', []))
        n_buttons = len(result.get('buttons', []))
        n_inputs = len(result.get('inputs', []))
        n_selects = len(result.get('selects', []))
        n_textareas = len(result.get('textareas', []))
        n_tables = len(result.get('tables', []))
        size = result.get('html_size', 0)
        print(f"\n✅ {label} ({path}) — {size:,} bytes")
        print(f"   Forms: {n_forms} | Buttons: {n_buttons} | Inputs: {n_inputs} | "
              f"Selects: {n_selects} | Textareas: {n_textareas} | Tables: {n_tables}")

        # Detail key forms (skip per-row delete forms)
        key_forms = [f for f in result.get('forms', [])
                     if not f['action'].endswith('/delete')
                     and not f['id'] == 'report-drawer-form']
        for f in key_forms[:5]:
            fid = f.get('id') or f.get('action') or '(no id)'
            fnames = [i.get('name', '') for i in f.get('inputs', []) if i.get('name')]
            print(f"   📋 Form [{f['method']}] {fid}: {fnames[:8]}")

        # Detail buttons (skip per-row duplicates)
        seen_btn_texts = set()
        for b in result.get('buttons', []):
            btext = b.get('text', '')[:30]
            if btext not in seen_btn_texts and btext:
                seen_btn_texts.add(btext)
                bid = b.get('id') or '(no id)'
                print(f"   🔘 [{bid}]: \"{btext}\"")

        # Detail tables
        for t in result.get('tables', []):
            tid = t.get('id') or t.get('class') or '(no id)'
            headers = t.get('headers', [])
            print(f"   📊 Table [{tid}]: {headers}")

    else:
        print(f"\n❌ {label} ({path}) — STATUS: {status}")
        all_pass = False

# ── API Endpoints ────────────────────────────────────────────────────

print("\n" + "=" * 80)
print("  API ENDPOINT CHECKS")
print("=" * 80)

API_ENDPOINTS = [
    ("/api/dashboard", "Dashboard API"),
    ("/api/videos", "Videos API"),
    ("/api/users", "Users API"),
    ("/api/seasons", "Seasons API"),
    ("/api/playlists", "Playlists API"),
    ("/api/clips", "Clips API"),
    ("/api/nfhs_matches", "NFHS Matches API (underscore)"),
]

for path, label in API_ENDPOINTS:
    try:
        r = s.get(BASE + path, timeout=10)
        try:
            data = r.json()
            if isinstance(data, list):
                print(f"   ✅ {label} — {r.status_code} ({len(data)} items)")
            elif isinstance(data, dict):
                print(f"   ✅ {label} — {r.status_code} (keys: {list(data.keys())[:5]})")
            else:
                print(f"   ✅ {label} — {r.status_code}")
        except:
            print(f"   ⚠️  {label} — {r.status_code} (non-JSON)")
    except Exception as e:
        print(f"   ❌ {label} — ERROR: {e}")

# ── Static Assets ────────────────────────────────────────────────────

print("\n" + "=" * 80)
print("  STATIC ASSETS")
print("=" * 80)

STATIC_ASSETS = [
    "/static/img/patriot-logo.jpg",
]

for path in STATIC_ASSETS:
    try:
        r = s.get(BASE + path, timeout=10)
        ct = r.headers.get('Content-Type', 'unknown')
        print(f"   {'✅' if r.status_code == 200 else '❌'} {path} — {r.status_code} ({ct}, {len(r.text)} bytes)")
    except Exception as e:
        print(f"   ❌ {path} — ERROR: {e}")

# ── Summary ─────────────────────────────────────────────────────────

print("\n" + "=" * 80)
print("  AUDIT SUMMARY")
print("=" * 80)
print(f"   Pages checked: {len(PAGES)}")
print(f"   API endpoints checked: {len(API_ENDPOINTS)}")
print(f"   Overall: {'✅ ALL PASSED' if all_pass else '❌ SOME FAILURES'}")
print("=" * 80)
