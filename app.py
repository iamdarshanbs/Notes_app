import json
import uuid
import re
import os
import base64
from datetime import datetime, timedelta
from collections import Counter
from flask import Flask, jsonify, render_template_string, request, make_response, send_from_directory

app = Flask(__name__)
NOTES_FILE = 'notes.json'
AUDIO_DIR = 'audio_uploads'
os.makedirs(AUDIO_DIR, exist_ok=True)

# ── Optional: fpdf2 for PDF export ──────────────────────────
try:
    from fpdf import FPDF
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# ── Stop words for keyword extraction ───────────────────────
STOP_WORDS = {
    'a','an','the','and','or','but','in','on','at','to','for','of','with',
    'by','from','is','it','its','this','that','was','are','be','been','has',
    'have','had','do','does','did','will','would','could','should','may',
    'might','shall','can','i','you','he','she','we','they','my','your',
    'his','her','our','their','as','if','not','no','so','up','out','about',
    'into','than','then','there','also','just','more','like','very'
}

def load_notes():
    try:
        with open(NOTES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_notes(notes):
    with open(NOTES_FILE, 'w', encoding='utf-8') as f:
        json.dump(notes, f, indent=2, ensure_ascii=False)

def extract_keywords(text, top_n=3):
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    filtered = [w for w in words if w not in STOP_WORDS]
    common = Counter(filtered).most_common(top_n)
    return [w for w, _ in common]

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/notes', methods=['GET'])
def get_notes():
    return jsonify(load_notes())

@app.route('/api/notes', methods=['POST'])
def add_note():
    notes = load_notes()
    data = request.json
    content = data.get('content', '')
    auto_tags = extract_keywords(content) if content.strip() else []
    manual_tags = [t.strip() for t in data.get('tags', '').split(',') if t.strip()]
    new_note = {
        "id": str(uuid.uuid4()),
        "title": data['title'],
        "content": content,
        "tags": manual_tags,
        "auto_tags": auto_tags,
        "color": data.get('color', '#7c6aff'),
        "pinned": False,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    
    audio_data = data.get('audio_data')
    if audio_data:
        try:
            audio_bytes = base64.b64decode(audio_data)
            audio_filename = f"{new_note['id']}.webm"
            with open(os.path.join(AUDIO_DIR, audio_filename), 'wb') as f:
                f.write(audio_bytes)
            new_note['audio_file'] = audio_filename
        except Exception as e:
            print("Error saving audio:", e)
            
    notes.append(new_note)
    save_notes(notes)
    return jsonify(new_note), 201

@app.route('/api/notes/<id>', methods=['PUT'])
def update_note(id):
    notes = load_notes()
    data = request.json
    for note in notes:
        if note['id'] == id:
            content = data.get('content', '')
            note['title'] = data['title']
            note['content'] = content
            note['tags'] = [t.strip() for t in data.get('tags', '').split(',') if t.strip()]
            note['auto_tags'] = extract_keywords(content) if content.strip() else []
            note['color'] = data.get('color', note.get('color', '#7c6aff'))
            note['updated'] = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            audio_data = data.get('audio_data')
            if audio_data:
                try:
                    audio_bytes = base64.b64decode(audio_data)
                    audio_filename = f"{id}.webm"
                    with open(os.path.join(AUDIO_DIR, audio_filename), 'wb') as f:
                        f.write(audio_bytes)
                    note['audio_file'] = audio_filename
                except Exception as e:
                    print("Error saving audio:", e)
            elif data.get('remove_audio'):
                note.pop('audio_file', None)
                try:
                    os.remove(os.path.join(AUDIO_DIR, f"{id}.webm"))
                except OSError:
                    pass
                    
            save_notes(notes)
            return jsonify(note)
    return jsonify({"error": "Not found"}), 404

@app.route('/api/notes/<id>/pin', methods=['PATCH'])
def toggle_pin(id):
    notes = load_notes()
    for note in notes:
        if note['id'] == id:
            note['pinned'] = not note.get('pinned', False)
            save_notes(notes)
            return jsonify(note)
    return jsonify({"error": "Not found"}), 404

@app.route('/api/notes/<id>', methods=['DELETE'])
def delete_note(id):
    notes = load_notes()
    for note in notes:
        if note['id'] == id:
            note['deleted'] = True
            note['updated'] = datetime.now().strftime("%Y-%m-%d %H:%M")
            save_notes(notes)
            return jsonify({"success": True})
    return jsonify({"error": "Not found"}), 404

@app.route('/api/notes/<id>/hard', methods=['DELETE'])
def hard_delete_note(id):
    notes = load_notes()
    notes = [n for n in notes if n['id'] != id]
    save_notes(notes)
    return jsonify({"success": True})

@app.route('/api/notes/<id>/restore', methods=['PATCH'])
def restore_note(id):
    notes = load_notes()
    for note in notes:
        if note['id'] == id:
            note['deleted'] = False
            note['updated'] = datetime.now().strftime("%Y-%m-%d %H:%M")
            save_notes(notes)
            return jsonify(note)
    return jsonify({"error": "Not found"}), 404

@app.route('/api/audio/<filename>', methods=['GET'])
def get_audio(filename):
    return send_from_directory(AUDIO_DIR, filename)

@app.route('/api/notes/<id>/pdf', methods=['GET'])
def export_pdf(id):
    if not PDF_AVAILABLE:
        return jsonify({"error": "fpdf2 not installed. Run: pip install fpdf2"}), 500
    notes = load_notes()
    note = next((n for n in notes if n['id'] == id), None)
    if not note:
        return jsonify({"error": "Not found"}), 404

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Title
    pdf.set_font("Helvetica", 'B', 22)
    pdf.set_text_color(30, 20, 80)
    pdf.multi_cell(0, 12, note['title'], align='L')
    pdf.ln(2)

    # Meta line
    pdf.set_font("Helvetica", 'I', 10)
    pdf.set_text_color(120, 110, 150)
    all_tags = note.get('tags', []) + ['[auto] ' + t for t in note.get('auto_tags', [])]
    pdf.cell(0, 8, f"Created: {note['created']}  |  Tags: {', '.join(all_tags) or 'None'}", ln=True)
    pdf.ln(3)

    # Divider
    pdf.set_draw_color(180, 170, 220)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(6)

    # Content (strip markdown for PDF)
    clean = re.sub(r'[#*`_~>]', '', note['content'])
    pdf.set_font("Helvetica", size=12)
    pdf.set_text_color(40, 40, 60)
    pdf.multi_cell(0, 7, clean)

    response = make_response(bytes(pdf.output()))
    safe_title = re.sub(r'[^\w\-]', '_', note['title'])[:40]
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename="{safe_title}.pdf"'
    return response

@app.route('/api/stats', methods=['GET'])
def get_stats():
    notes = load_notes()
    active_notes = [n for n in notes if not n.get('deleted')]
    # Tags distribution
    all_tags = []
    for n in active_notes:
        all_tags.extend(n.get('tags', []))
        all_tags.extend(['[' + t + ']' for t in n.get('auto_tags', [])])
    tag_counts = dict(Counter(all_tags).most_common(10))

    # Notes per day for last 7 days
    today = datetime.now().date()
    day_labels = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
    day_counts = {d: 0 for d in day_labels}
    for n in active_notes:
        try:
            d = n['created'].split(' ')[0]
            if d in day_counts:
                day_counts[d] += 1
        except Exception:
            pass

    return jsonify({
        "total": len(active_notes),
        "pinned": sum(1 for n in active_notes if n.get('pinned')),
        "tag_distribution": tag_counts,
        "notes_per_day": {"labels": day_labels, "values": [day_counts[d] for d in day_labels]}
    })

# ════════════════════════════════════════════════════════════
#  HTML TEMPLATE
# ════════════════════════════════════════════════════════════
HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>QuickNotes — Illuminate Your Thoughts</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:ital,wght@0,300;0,400;1,300&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
/*═══════════════════════════════════════════════════════════
  RESET & ROOT
═══════════════════════════════════════════════════════════*/
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --primary: #7c6aff;
  --primary-glow: rgba(124,106,255,0.35);
  --bg: #080810;
  --card: rgba(18,18,30,0.75);
  --border: rgba(255,255,255,0.07);
  --text: #e8e8f0;
  --muted: rgba(200,200,220,0.45);
  --danger: #ff4d6d;
  --success: #00e5a0;
  --warn: #ffb347;
  --info: #3db8ff;
}
body {
  font-family: 'Syne', sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  overflow-x: hidden;
  cursor: none;
}

/*═══════════════════════════════════════════════════════════
  CANVAS / CURSOR
═══════════════════════════════════════════════════════════*/
#bg-canvas { position: fixed; inset: 0; z-index: 0; pointer-events: none; }
.cursor-light {
  position: fixed; width: 500px; height: 500px; border-radius: 50%;
  pointer-events: none; z-index: 1; transform: translate(-50%,-50%);
  background: radial-gradient(circle, rgba(124,106,255,0.12) 0%, rgba(80,60,200,0.06) 35%, transparent 70%);
  mix-blend-mode: screen; transition: background 0.4s;
}
.custom-cursor {
  position: fixed; width: 10px; height: 10px; background: var(--primary);
  border-radius: 50%; pointer-events: none; z-index: 9999;
  transform: translate(-50%,-50%);
  transition: width 0.2s, height 0.2s, background 0.2s;
  box-shadow: 0 0 14px var(--primary), 0 0 28px var(--primary-glow);
}
.custom-cursor.hover { width: 18px; height: 18px; background: transparent; border: 2px solid var(--primary); }
.cursor-ring {
  position: fixed; width: 36px; height: 36px;
  border: 1.5px solid rgba(124,106,255,0.45); border-radius: 50%;
  pointer-events: none; z-index: 9998; transform: translate(-50%,-50%);
  transition: width 0.25s, height 0.25s, border-color 0.2s;
}
.cursor-ring.hover { width: 48px; height: 48px; border-color: var(--primary); }

/*═══════════════════════════════════════════════════════════
  LAYOUT
═══════════════════════════════════════════════════════════*/
.app-wrapper { position: relative; z-index: 2; max-width: 1140px; margin: 0 auto; padding: 40px 24px 100px; }

/*═══════════════════════════════════════════════════════════
  HEADER
═══════════════════════════════════════════════════════════*/
.header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 32px;
  animation: slideDown 0.7s cubic-bezier(0.22,1,0.36,1) both;
}
.logo-area h1 {
  font-size: 2rem; font-weight: 800; letter-spacing: -0.03em;
  background: linear-gradient(135deg, #fff 25%, var(--primary) 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.logo-area span {
  font-family: 'DM Mono', monospace; font-size: 0.68rem;
  color: var(--muted); letter-spacing: 0.14em; text-transform: uppercase;
}
.header-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }

/*═══════════════════════════════════════════════════════════
  STATS BAR
═══════════════════════════════════════════════════════════*/
.stats-bar {
  display: flex; gap: 28px; margin-bottom: 28px;
  animation: slideDown 0.7s 0.05s cubic-bezier(0.22,1,0.36,1) both;
}
.stat-item { display: flex; flex-direction: column; gap: 1px; }
.stat-value {
  font-size: 1.45rem; font-weight: 800;
  background: linear-gradient(135deg, #fff 30%, var(--primary) 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.stat-label {
  font-family: 'DM Mono', monospace; font-size: 0.62rem;
  color: var(--muted); letter-spacing: 0.1em; text-transform: uppercase;
}

/*═══════════════════════════════════════════════════════════
  SEARCH
═══════════════════════════════════════════════════════════*/
.search-wrap {
  position: relative; margin-bottom: 20px;
  animation: slideDown 0.7s 0.1s cubic-bezier(0.22,1,0.36,1) both;
}
.search-wrap input {
  width: 100%; padding: 13px 56px 13px 46px;
  background: var(--card); border: 1px solid var(--border);
  border-radius: 13px; color: var(--text);
  font-family: 'DM Mono', monospace; font-size: 0.88rem;
  outline: none; backdrop-filter: blur(20px);
  transition: border-color 0.3s, box-shadow 0.3s;
}
.search-wrap input:focus {
  border-color: rgba(124,106,255,0.5);
  box-shadow: 0 0 0 3px rgba(124,106,255,0.1), 0 0 30px rgba(124,106,255,0.07);
}
.search-icon { position: absolute; left: 15px; top: 50%; transform: translateY(-50%); color: var(--muted); pointer-events: none; }
.search-count { position: absolute; right: 14px; top: 50%; transform: translateY(-50%); font-family: 'DM Mono', monospace; font-size: 0.7rem; color: var(--muted); }

/*═══════════════════════════════════════════════════════════
  FILTER CHIPS
═══════════════════════════════════════════════════════════*/
.filter-row {
  display: flex; gap: 7px; flex-wrap: wrap; margin-bottom: 26px;
  animation: slideDown 0.7s 0.12s cubic-bezier(0.22,1,0.36,1) both;
}
.filter-chip {
  padding: 5px 13px; border-radius: 99px;
  background: rgba(255,255,255,0.03); border: 1px solid var(--border);
  color: var(--muted); font-size: 0.75rem;
  font-family: 'DM Mono', monospace;
  cursor: pointer; transition: all 0.2s; letter-spacing: 0.04em;
}
.filter-chip.active, .filter-chip:hover {
  background: var(--primary-glow); border-color: var(--primary); color: #fff;
}

/*═══════════════════════════════════════════════════════════
  GRID
═══════════════════════════════════════════════════════════*/
.notes-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 18px;
}
.notes-empty {
  grid-column: 1/-1; text-align: center; padding: 80px 20px;
  color: var(--muted); font-family: 'DM Mono', monospace; font-size: 0.83rem;
}
.notes-empty .empty-icon { font-size: 2.8rem; margin-bottom: 10px; opacity: 0.35; }

/*═══════════════════════════════════════════════════════════
  NOTE CARD
═══════════════════════════════════════════════════════════*/
.note-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 16px; padding: 20px; position: relative;
  backdrop-filter: blur(20px); overflow: hidden;
  transition: transform 0.35s cubic-bezier(0.22,1,0.36,1), box-shadow 0.35s, border-color 0.3s;
  animation: cardIn 0.5s cubic-bezier(0.22,1,0.36,1) both;
  transform-style: preserve-3d;
}
.note-card::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: var(--note-color, var(--primary)); border-radius: 16px 16px 0 0;
}
.note-card::after {
  content: ''; position: absolute; inset: 0; border-radius: 16px;
  background: radial-gradient(circle at var(--mx,50%) var(--my,50%), rgba(255,255,255,0.035) 0%, transparent 58%);
  pointer-events: none; opacity: 0; transition: opacity 0.3s;
}
.note-card:hover::after { opacity: 1; }
.note-card:hover {
  box-shadow: 0 22px 60px rgba(0,0,0,0.45), 0 0 0 1px rgba(124,106,255,0.18), 0 0 40px rgba(124,106,255,0.05);
  border-color: rgba(124,106,255,0.22);
}
.note-card.pinned { border-color: rgba(255,210,50,0.28); }
.note-card.pinned::before { background: #ffd232; }
.note-card.deleting { animation: cardOut 0.38s cubic-bezier(0.4,0,1,1) forwards !important; pointer-events: none; }

.card-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px; gap: 8px; }
.note-title { font-size: 0.98rem; font-weight: 700; line-height: 1.3; flex: 1; }
.card-actions { display: flex; gap: 5px; opacity: 0; transition: opacity 0.2s; flex-shrink: 0; }
.note-card:hover .card-actions { opacity: 1; }

/* Markdown rendered content */
.note-content {
  font-size: 0.83rem; color: rgba(220,220,235,0.68);
  line-height: 1.65; margin-bottom: 12px;
  display: -webkit-box; -webkit-line-clamp: 5; -webkit-box-orient: vertical; overflow: hidden;
}
.note-content h1, .note-content h2, .note-content h3 {
  font-family: 'Syne', sans-serif; font-weight: 700;
  color: rgba(240,240,255,0.85); margin: 4px 0 2px;
  font-size: 0.92rem;
}
.note-content strong { color: rgba(255,255,255,0.9); }
.note-content em { color: rgba(200,185,255,0.9); font-style: italic; }
.note-content code {
  font-family: 'DM Mono', monospace; font-size: 0.75rem;
  background: rgba(124,106,255,0.15); border: 1px solid rgba(124,106,255,0.2);
  padding: 1px 5px; border-radius: 4px; color: rgba(180,170,255,0.95);
}
.note-content pre {
  background: rgba(10,10,20,0.8); border: 1px solid rgba(124,106,255,0.15);
  border-radius: 8px; padding: 10px 12px; margin: 6px 0; overflow: auto;
}
.note-content pre code { background: none; border: none; padding: 0; font-size: 0.73rem; }
.note-content ul, .note-content ol { padding-left: 16px; }
.note-content blockquote {
  border-left: 3px solid var(--primary); padding-left: 10px;
  color: rgba(200,190,255,0.7); font-style: italic; margin: 4px 0;
}
.note-content a { color: var(--primary); text-decoration: underline; }

.tags-row { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 12px; }
.tag-chip {
  padding: 2px 9px; border-radius: 99px;
  background: rgba(124,106,255,0.1); border: 1px solid rgba(124,106,255,0.18);
  font-size: 0.68rem; font-family: 'DM Mono', monospace;
  color: rgba(175,165,255,0.9); letter-spacing: 0.03em;
}
.auto-tag-chip {
  padding: 2px 9px; border-radius: 99px;
  background: rgba(0,229,160,0.08); border: 1px solid rgba(0,229,160,0.2);
  font-size: 0.65rem; font-family: 'DM Mono', monospace;
  color: rgba(0,229,160,0.85); letter-spacing: 0.03em;
}
.auto-tag-chip::before { content: '⚡'; margin-right: 3px; font-size: 0.6rem; }

.card-footer {
  display: flex; justify-content: space-between; align-items: center;
  border-top: 1px solid var(--border); padding-top: 10px;
}
.card-date { font-family: 'DM Mono', monospace; font-size: 0.65rem; color: var(--muted); }
.pin-badge { font-size: 0.63rem; font-family: 'DM Mono', monospace; color: #ffd232; text-transform: uppercase; letter-spacing: 0.06em; }

/*═══════════════════════════════════════════════════════════
  ICON BUTTONS
═══════════════════════════════════════════════════════════*/
.icon-btn {
  width: 28px; height: 28px; border-radius: 7px;
  border: 1px solid var(--border); background: rgba(255,255,255,0.04);
  color: var(--muted); cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.82rem; transition: all 0.2s;
}
.icon-btn:hover { background: rgba(255,255,255,0.09); color: #fff; border-color: rgba(255,255,255,0.18); }
.icon-btn.pin-active { color: #ffd232; border-color: rgba(255,210,50,0.35); }
.icon-btn.del:hover { background: rgba(255,77,109,0.13); color: var(--danger); border-color: rgba(255,77,109,0.35); }
.icon-btn.dl:hover { background: rgba(61,184,255,0.12); color: var(--info); border-color: rgba(61,184,255,0.35); }

/*═══════════════════════════════════════════════════════════
  BUTTONS
═══════════════════════════════════════════════════════════*/
.btn {
  padding: 9px 18px; border-radius: 10px; cursor: pointer; border: none;
  font-family: 'Syne', sans-serif; font-weight: 600; font-size: 0.83rem;
  transition: all 0.25s cubic-bezier(0.22,1,0.36,1); letter-spacing: 0.02em;
  white-space: nowrap;
}
.btn-primary { background: var(--primary); color: white; box-shadow: 0 4px 18px rgba(124,106,255,0.32); }
.btn-primary:hover { transform: translateY(-2px); box-shadow: 0 8px 28px rgba(124,106,255,0.48); }
.btn-ghost { background: rgba(255,255,255,0.05); color: var(--muted); border: 1px solid var(--border); }
.btn-ghost:hover { background: rgba(255,255,255,0.09); color: #fff; }
.btn-teal { background: rgba(0,229,160,0.12); color: var(--success); border: 1px solid rgba(0,229,160,0.25); }
.btn-teal:hover { background: rgba(0,229,160,0.2); transform: translateY(-1px); }
.btn-icon { background: rgba(255,255,255,0.04); color: var(--muted); border: 1px solid var(--border); padding: 9px 12px; }
.btn-icon:hover { background: rgba(255,255,255,0.09); color: #fff; }

.view-toggle { display: flex; gap: 3px; background: rgba(255,255,255,0.03); padding: 3px; border-radius: 9px; border: 1px solid var(--border); }
.view-btn { width: 30px; height: 26px; border: none; background: transparent; color: var(--muted); cursor: pointer; border-radius: 6px; display: flex; align-items: center; justify-content: center; font-size: 0.82rem; transition: all 0.2s; }
.view-btn.active { background: var(--primary); color: #fff; }

/* List view */
.notes-grid.list-view { grid-template-columns: 1fr; }
.notes-grid.list-view .note-card { display: flex; gap: 16px; }
.notes-grid.list-view .note-content { -webkit-line-clamp: 2; flex: 1; margin-bottom: 0; }
.notes-grid.list-view .card-top { flex-direction: column; flex: none; width: 170px; min-width: 170px; }
.notes-grid.list-view .tags-row, .notes-grid.list-view .card-footer { display: none; }
.notes-grid.list-view .note-card::before { width: 2px; height: auto; top: 0; left: 0; right: auto; bottom: 0; border-radius: 16px 0 0 16px; }

/*═══════════════════════════════════════════════════════════
  MODAL
═══════════════════════════════════════════════════════════*/
.modal-overlay {
  position: fixed; inset: 0; background: rgba(4,4,12,0.88);
  display: none; justify-content: center; align-items: center;
  z-index: 1000; backdrop-filter: blur(10px);
}
.modal-overlay.open { display: flex; }
.modal {
  background: rgba(13,13,24,0.97); border: 1px solid rgba(255,255,255,0.09);
  padding: 30px; border-radius: 20px; width: 500px; max-width: calc(100vw - 32px);
  max-height: 92vh; overflow-y: auto;
  box-shadow: 0 40px 120px rgba(0,0,0,0.85), 0 0 0 1px rgba(124,106,255,0.08);
  animation: modalIn 0.4s cubic-bezier(0.22,1,0.36,1) both; position: relative;
}
.modal::-webkit-scrollbar { width: 4px; }
.modal::-webkit-scrollbar-thumb { background: rgba(124,106,255,0.3); border-radius: 4px; }
.modal-title { font-size: 1.2rem; font-weight: 800; margin-bottom: 22px; letter-spacing: -0.02em; }
.modal-close {
  position: absolute; top: 18px; right: 18px; width: 30px; height: 30px;
  border-radius: 8px; border: 1px solid var(--border);
  background: rgba(255,255,255,0.04); color: var(--muted);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  font-size: 0.95rem; transition: all 0.2s;
}
.modal-close:hover { background: rgba(255,77,109,0.14); color: var(--danger); }

.form-group { margin-bottom: 15px; }
.form-label {
  display: block; font-family: 'DM Mono', monospace; font-size: 0.68rem;
  color: var(--muted); letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 6px;
}
.form-input {
  width: 100%; padding: 11px 13px;
  background: rgba(255,255,255,0.04); border: 1px solid var(--border);
  border-radius: 10px; color: var(--text); font-family: 'Syne', sans-serif;
  font-size: 0.88rem; outline: none;
  transition: border-color 0.3s, box-shadow 0.3s; resize: vertical;
}
.form-input:focus { border-color: rgba(124,106,255,0.55); box-shadow: 0 0 0 3px rgba(124,106,255,0.1); }
.char-counter {
  text-align: right; font-family: 'DM Mono', monospace; font-size: 0.66rem;
  color: var(--muted); margin-top: 4px; transition: color 0.2s;
}
.char-counter.warn { color: var(--warn); }
.char-counter.over { color: var(--danger); }

/* Voice button area */
.textarea-wrap { position: relative; }
.voice-btn {
  position: absolute; right: 10px; bottom: 10px;
  width: 32px; height: 32px; border-radius: 50%;
  border: 1px solid var(--border); background: rgba(124,106,255,0.12);
  color: var(--primary); cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.9rem; transition: all 0.2s;
  z-index: 2;
}
.voice-btn:hover { background: rgba(124,106,255,0.24); transform: scale(1.1); }
.voice-btn.recording {
  background: rgba(255,77,109,0.25); border-color: var(--danger); color: var(--danger);
  animation: pulse 1s ease-in-out infinite;
}
.voice-unsupported { opacity: 0.3; cursor: not-allowed; }
.voice-unsupported:hover { transform: none; }
.audio-btn { right: 50px; }

.color-row { display: flex; gap: 7px; align-items: center; flex-wrap: wrap; }
.color-swatch {
  width: 25px; height: 25px; border-radius: 7px; cursor: pointer;
  border: 2px solid transparent; transition: transform 0.2s, border-color 0.2s;
}
.color-swatch:hover { transform: scale(1.2); }
.color-swatch.selected { border-color: #fff; transform: scale(1.12); }

.modal-footer { display: flex; justify-content: flex-end; gap: 9px; margin-top: 22px; }

/*═══════════════════════════════════════════════════════════
  TOAST — completely redesigned
═══════════════════════════════════════════════════════════*/
.toast-container {
  position: fixed; bottom: 28px; right: 28px;
  z-index: 10001; display: flex; flex-direction: column;
  gap: 10px; pointer-events: none;
}
.toast {
  pointer-events: auto;
  display: flex; align-items: center; gap: 12px;
  min-width: 300px; max-width: 380px;
  padding: 0 18px 0 0;
  border-radius: 14px;
  background: rgba(16,16,28,0.97);
  backdrop-filter: blur(24px);
  border: 1px solid rgba(255,255,255,0.07);
  box-shadow: 0 12px 40px rgba(0,0,0,0.55), 0 0 0 1px rgba(255,255,255,0.03);
  overflow: hidden;
  animation: toastIn 0.42s cubic-bezier(0.22,1,0.36,1) both;
  font-family: 'DM Mono', monospace; font-size: 0.82rem; color: var(--text);
}
.toast-icon-wrap {
  width: 48px; height: 48px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 1.1rem;
}
.toast.success .toast-icon-wrap { background: rgba(0,229,160,0.1); }
.toast.error .toast-icon-wrap { background: rgba(255,77,109,0.1); }
.toast.info .toast-icon-wrap { background: rgba(61,184,255,0.1); }
.toast.warn .toast-icon-wrap { background: rgba(255,179,71,0.1); }
.toast-body { flex: 1; padding: 12px 0; display: flex; flex-direction: column; gap: 1px; }
.toast-title { font-weight: 600; font-size: 0.8rem; letter-spacing: 0.03em; }
.toast-msg { font-size: 0.74rem; color: var(--muted); }
.toast-close {
  background: none; border: none; cursor: pointer;
  color: var(--muted); font-size: 0.85rem; padding: 4px;
  transition: color 0.2s; flex-shrink: 0;
}
.toast-close:hover { color: var(--text); }
.toast-progress {
  position: absolute; bottom: 0; left: 0; right: 0; height: 2px;
  border-radius: 0 0 14px 14px;
}
.toast.success .toast-progress { background: var(--success); }
.toast.error .toast-progress { background: var(--danger); }
.toast.info .toast-progress { background: var(--info); }
.toast.warn .toast-progress { background: var(--warn); }
.toast-progress-bar {
  height: 100%; border-radius: inherit;
  animation: progressBar 3s linear forwards;
  background: inherit;
}
.toast.success { border-left: 3px solid var(--success); }
.toast.error { border-left: 3px solid var(--danger); }
.toast.info { border-left: 3px solid var(--info); }
.toast.warn { border-left: 3px solid var(--warn); }
.toast.fadeout { animation: toastOut 0.3s ease forwards; }

/*═══════════════════════════════════════════════════════════
  DASHBOARD PANEL
═══════════════════════════════════════════════════════════*/
.dashboard-panel {
  display: none; margin-bottom: 32px;
  background: var(--card); border: 1px solid var(--border);
  border-radius: 18px; padding: 28px; backdrop-filter: blur(20px);
  animation: slideDown 0.4s cubic-bezier(0.22,1,0.36,1) both;
}
.dashboard-panel.open { display: block; }
.dashboard-title {
  font-size: 1rem; font-weight: 700; margin-bottom: 20px;
  display: flex; align-items: center; gap: 8px;
  letter-spacing: -0.01em;
}
.dashboard-title::before { content: ''; display: inline-block; width: 8px; height: 8px; border-radius: 2px; background: var(--primary); }
.charts-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
@media (max-width: 640px) { .charts-grid { grid-template-columns: 1fr; } }
.chart-box {
  background: rgba(10,10,20,0.6); border: 1px solid var(--border);
  border-radius: 14px; padding: 18px;
}
.chart-label {
  font-family: 'DM Mono', monospace; font-size: 0.68rem;
  color: var(--muted); text-transform: uppercase; letter-spacing: 0.1em;
  margin-bottom: 12px;
}
.chart-canvas-wrap { position: relative; height: 200px; }

/*═══════════════════════════════════════════════════════════
  ANIMATIONS
═══════════════════════════════════════════════════════════*/
@keyframes slideDown {
  from { opacity: 0; transform: translateY(-18px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes cardIn {
  from { opacity: 0; transform: translateY(22px) scale(0.97); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes cardOut {
  to { opacity: 0; transform: scale(0.86) translateY(24px); filter: blur(10px); }
}
@keyframes modalIn {
  from { opacity: 0; transform: scale(0.93) translateY(18px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}
@keyframes toastIn {
  from { opacity: 0; transform: translateX(50px) scale(0.92); }
  to { opacity: 1; transform: translateX(0) scale(1); }
}
@keyframes toastOut {
  to { opacity: 0; transform: translateX(50px) scale(0.92); }
}
@keyframes progressBar {
  from { width: 100%; opacity: 1; }
  to { width: 0%; opacity: 0.5; }
}
@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(255,77,109,0.4); }
  50% { box-shadow: 0 0 0 8px rgba(255,77,109,0); }
}
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
</style>
</head>
<body>

<!-- Cursor -->
<div class="custom-cursor" id="cursor"></div>
<div class="cursor-ring" id="cursorRing"></div>
<div class="cursor-light" id="cursorLight"></div>
<!-- BG -->
<canvas id="bg-canvas"></canvas>
<!-- Toasts -->
<div class="toast-container" id="toastContainer"></div>

<div class="app-wrapper">

  <!-- Header -->
  <div class="header">
    <div class="logo-area">
      <h1>QuickNotes</h1>
      <span>Illuminate Your Thoughts</span>
    </div>
    <div class="header-actions">
      <div class="view-toggle">
        <button class="view-btn active" id="gridViewBtn" title="Grid" onclick="setView('grid')">⊞</button>
        <button class="view-btn" id="listViewBtn" title="List" onclick="setView('list')">☰</button>
      </div>
      <button class="btn btn-ghost" id="historyBtn" onclick="toggleHistoryView()">🕰️ History</button>
      <button class="btn btn-teal btn-icon" title="Dashboard" onclick="toggleDashboard()">📊</button>
      <button class="btn btn-primary" onclick="openModal()">+ New Note</button>
    </div>
  </div>

  <!-- Stats -->
  <div class="stats-bar">
    <div class="stat-item"><div class="stat-value" id="statTotal">0</div><div class="stat-label">Total</div></div>
    <div class="stat-item"><div class="stat-value" id="statPinned">0</div><div class="stat-label">Pinned</div></div>
    <div class="stat-item"><div class="stat-value" id="statTags">0</div><div class="stat-label">Tags</div></div>
  </div>

  <!-- Dashboard -->
  <div class="dashboard-panel" id="dashboardPanel">
    <div class="dashboard-title">Visual Insights</div>
    <div class="charts-grid">
      <div class="chart-box">
        <div class="chart-label">Notes by Tag</div>
        <div class="chart-canvas-wrap"><canvas id="tagChart"></canvas></div>
      </div>
      <div class="chart-box">
        <div class="chart-label">Created — Last 7 Days</div>
        <div class="chart-canvas-wrap"><canvas id="dayChart"></canvas></div>
      </div>
    </div>
  </div>

  <!-- Search -->
  <div class="search-wrap">
    <span class="search-icon">🔍</span>
    <input type="text" id="searchInput" placeholder="Search by title, content or tag…" oninput="filterNotes()">
    <span class="search-count" id="searchCount"></span>
  </div>

  <!-- Filters -->
  <div class="filter-row" id="filterRow">
    <span class="filter-chip active" data-filter="all" onclick="setFilter('all',this)">All</span>
    <span class="filter-chip" data-filter="pinned" onclick="setFilter('pinned',this)">📌 Pinned</span>
  </div>

  <!-- Notes -->
  <div class="notes-grid" id="notesGrid"></div>
</div>

<!-- Modal -->
<div class="modal-overlay" id="modalOverlay">
  <div class="modal">
    <div class="modal-title" id="modalTitle">New Note</div>
    <button class="modal-close" onclick="closeModal()">✕</button>
    <input type="hidden" id="noteId">

    <div class="form-group">
      <label class="form-label">Title</label>
      <input type="text" class="form-input" id="titleInput" placeholder="Give it a name…" maxlength="80">
    </div>

    <div class="form-group">
      <label class="form-label">Content <span style="color:var(--muted);font-size:0.6rem;font-family:'DM Mono',monospace;text-transform:none;letter-spacing:0">— Markdown supported</span></label>
      <div class="textarea-wrap">
        <textarea class="form-input" id="contentInput" rows="7"
          placeholder="Write with **bold**, # headers, \`code\`…"
          maxlength="2000" oninput="updateCharCount()"></textarea>
        <button class="voice-btn audio-btn" id="audioRecordBtn" title="Record Voice Note" onclick="toggleAudioRecording()">🎙️</button>
        <button class="voice-btn" id="voiceBtn" title="Voice to text" onclick="toggleVoice()">🎤</button>
      </div>
      <div class="char-counter" id="charCounter">0 / 2000</div>
      
      <div id="audioPreviewContainer" style="display:none; margin-top:10px; background: rgba(255,255,255,0.03); padding: 10px; border-radius: 10px; border: 1px solid var(--border);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-size: 0.8rem; color: var(--muted);"><span style="color:var(--primary)">🎙️</span> Audio Note</span>
          <button class="icon-btn del" title="Remove Audio" onclick="removeAudio()" style="width:24px; height:24px; font-size:0.7rem;">✕</button>
        </div>
        <audio id="audioPreview" controls style="width: 100%; height: 35px; border-radius: 8px;"></audio>
      </div>
    </div>

    <div class="form-group">
      <label class="form-label">Tags <span style="color:var(--muted);font-size:0.6rem;font-family:'DM Mono',monospace;text-transform:none;letter-spacing:0">comma separated</span></label>
      <input type="text" class="form-input" id="tagsInput" placeholder="work, ideas, personal">
    </div>

    <div class="form-group">
      <label class="form-label">Card Color</label>
      <div class="color-row" id="colorRow"></div>
    </div>

    <div class="modal-footer">
      <button class="btn btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn btn-primary" onclick="saveNote()">Save Note</button>
    </div>
  </div>
</div>

<!-- Confirm Modal -->
<div class="modal-overlay" id="confirmModalOverlay">
  <div class="modal" style="width: 400px; text-align: center; padding: 40px 30px;">
    <div style="font-size: 3.5rem; margin-bottom: 15px; opacity: 0.9;">⚠️</div>
    <div class="modal-title" id="confirmModalTitle" style="font-size: 1.4rem; margin-bottom: 12px; font-weight: 800;">Are you sure?</div>
    <div id="confirmModalMessage" style="color: var(--muted); margin-bottom: 30px; font-size: 0.9rem; line-height: 1.5;">This action cannot be undone.</div>
    <div class="modal-footer" style="justify-content: center; gap: 12px; margin-top: 0;">
      <button class="btn btn-ghost" onclick="closeConfirmModal()" style="padding: 10px 24px;">Cancel</button>
      <button class="btn btn-primary" id="confirmModalBtn" style="background: var(--danger); box-shadow: 0 4px 18px rgba(255,77,109,0.32); padding: 10px 24px;">Delete</button>
    </div>
  </div>
</div>

<script>
/* ──────────────────────────────────────────
   3D BG CANVAS
────────────────────────────────────────── */
const bgCanvas = document.getElementById('bg-canvas');
const bgCtx = bgCanvas.getContext('2d');
let BW, BH, bParticles = [];
let bMouse = { x: -1000, y: -1000 };

function bgResize() { BW = bgCanvas.width = innerWidth; BH = bgCanvas.height = innerHeight; }
bgResize();
window.addEventListener('resize', bgResize);

const PC = 85;
const BCOLS = ['rgba(124,106,255,','rgba(80,200,255,','rgba(200,130,255,'];
function initBParticles() {
  bParticles = [];
  for (let i = 0; i < PC; i++) bParticles.push({
    x: Math.random()*BW, y: Math.random()*BH,
    z: Math.random()*1.8+0.3,
    vx: (Math.random()-0.5)*0.22, vy: (Math.random()-0.5)*0.22,
    r: Math.random()*1.8+0.4,
    color: BCOLS[Math.floor(Math.random()*BCOLS.length)],
    phase: Math.random()*Math.PI*2
  });
}
initBParticles();

let bT = 0;
function drawBg() {
  bgCtx.clearRect(0, 0, BW, BH);
  bT += 0.007;
  // grid
  bgCtx.strokeStyle = 'rgba(124,106,255,0.035)';
  bgCtx.lineWidth = 1;
  for (let x = 0; x < BW; x += 80) { bgCtx.beginPath(); bgCtx.moveTo(x,0); bgCtx.lineTo(x,BH); bgCtx.stroke(); }
  for (let y = 0; y < BH; y += 80) { bgCtx.beginPath(); bgCtx.moveTo(0,y); bgCtx.lineTo(BW,y); bgCtx.stroke(); }
  // nebula
  [[BW*.2,BH*.3,280,'rgba(124,106,255,0.04)'],[BW*.8,BH*.7,240,'rgba(80,200,255,0.03)'],[BW*.55,BH*.45,320,'rgba(200,80,255,0.025)']].forEach(([x,y,r,c])=>{
    const g = bgCtx.createRadialGradient(x,y,0,x,y,r);
    g.addColorStop(0,c); g.addColorStop(1,'transparent');
    bgCtx.fillStyle=g; bgCtx.beginPath(); bgCtx.arc(x,y,r,0,Math.PI*2); bgCtx.fill();
  });
  // mouse glow
  const mg = bgCtx.createRadialGradient(bMouse.x,bMouse.y,0,bMouse.x,bMouse.y,260);
  mg.addColorStop(0,'rgba(124,106,255,0.065)'); mg.addColorStop(1,'transparent');
  bgCtx.fillStyle=mg; bgCtx.beginPath(); bgCtx.arc(bMouse.x,bMouse.y,260,0,Math.PI*2); bgCtx.fill();
  // particles
  bParticles.forEach(p => {
    const dx=bMouse.x-p.x, dy=bMouse.y-p.y, dd=Math.sqrt(dx*dx+dy*dy);
    if(dd<150){ p.vx+=dx/dd*0.004; p.vy+=dy/dd*0.004; }
    p.vx*=0.99; p.vy*=0.99; p.x+=p.vx; p.y+=p.vy;
    if(p.x<0)p.x=BW; if(p.x>BW)p.x=0; if(p.y<0)p.y=BH; if(p.y>BH)p.y=0;
    const alpha=(0.28+0.38*Math.sin(bT+p.phase))*p.z*0.6;
    bgCtx.beginPath(); bgCtx.arc(p.x,p.y,p.r*p.z,0,Math.PI*2);
    bgCtx.fillStyle=p.color+alpha+')'; bgCtx.fill();
  });
  // lines
  bgCtx.lineWidth=0.35;
  for(let i=0;i<bParticles.length;i++) for(let j=i+1;j<bParticles.length;j++){
    const dx=bParticles[i].x-bParticles[j].x, dy=bParticles[i].y-bParticles[j].y;
    const d=Math.sqrt(dx*dx+dy*dy);
    if(d<95){ bgCtx.strokeStyle=`rgba(124,106,255,${(1-d/95)*0.11})`; bgCtx.beginPath(); bgCtx.moveTo(bParticles[i].x,bParticles[i].y); bgCtx.lineTo(bParticles[j].x,bParticles[j].y); bgCtx.stroke(); }
  }
  requestAnimationFrame(drawBg);
}
drawBg();

/* ──────────────────────────────────────────
   CUSTOM CURSOR
────────────────────────────────────────── */
const curEl = document.getElementById('cursor');
const ringEl = document.getElementById('cursorRing');
const lightEl = document.getElementById('cursorLight');
let cx=0, cy=0, rx=0, ry=0;

document.addEventListener('mousemove', e => {
  cx=e.clientX; cy=e.clientY;
  bMouse.x=cx; bMouse.y=cy;
  curEl.style.left=cx+'px'; curEl.style.top=cy+'px';
  lightEl.style.left=cx+'px'; lightEl.style.top=cy+'px';
});
(function animRing() {
  rx+=(cx-rx)*0.12; ry+=(cy-ry)*0.12;
  ringEl.style.left=rx+'px'; ringEl.style.top=ry+'px';
  requestAnimationFrame(animRing);
})();
document.addEventListener('mouseover', e => {
  if(e.target.matches('button,a,.note-card,.filter-chip,.color-swatch,.icon-btn,input,textarea,.view-btn')) {
    curEl.classList.add('hover'); ringEl.classList.add('hover');
  }
});
document.addEventListener('mouseout', e => {
  if(e.target.matches('button,a,.note-card,.filter-chip,.color-swatch,.icon-btn,input,textarea,.view-btn')) {
    curEl.classList.remove('hover'); ringEl.classList.remove('hover');
  }
});

// 3D card tilt
document.addEventListener('mousemove', e => {
  document.querySelectorAll('.note-card:not(.deleting)').forEach(card => {
    const r = card.getBoundingClientRect();
    const mx = ((e.clientX-r.left)/r.width)*100;
    const my = ((e.clientY-r.top)/r.height)*100;
    card.style.setProperty('--mx', mx+'%');
    card.style.setProperty('--my', my+'%');
    if(e.clientX>r.left && e.clientX<r.right && e.clientY>r.top && e.clientY<r.bottom) {
      card.style.transform=`translateY(-5px) scale(1.01) rotateX(${(my-50)*0.11}deg) rotateY(${-(mx-50)*0.11}deg)`;
    }
  });
});
document.addEventListener('mouseleave', () => {
  document.querySelectorAll('.note-card:not(.deleting)').forEach(c => { c.style.transform=''; });
});

/* ──────────────────────────────────────────
   APP STATE
────────────────────────────────────────── */
let allNotes = [];
let currentFilter = 'all';
let currentView = 'grid';
let selectedColor = '#7c6aff';
let isDashOpen = false;
let isHistoryView = false;
let tagChartInst = null;
let dayChartInst = null;

let audioRecorder = null;
let audioChunks = [];
let audioBlob = null;
let isAudioRecording = false;
let removeAudioFlag = false;

const NOTE_COLORS = ['#7c6aff','#ff4d6d','#00e5a0','#ffd232','#3db8ff','#ff8c42','#c084fc','#f472b6'];

/* ──────────────────────────────────────────
   LOAD & RENDER
────────────────────────────────────────── */
async function loadNotes() {
  const res = await fetch('/api/notes');
  allNotes = await res.json();
  updateStats();
  renderTagFilters();
  render();
  if(isDashOpen) loadDashboard();
}

function toggleHistoryView() {
  isHistoryView = !isHistoryView;
  const histBtn = document.getElementById('historyBtn');
  if (isHistoryView) {
    histBtn.classList.add('btn-primary');
    histBtn.classList.remove('btn-ghost');
    histBtn.textContent = '🔙 Back to Notes';
    document.getElementById('filterRow').style.display = 'none';
  } else {
    histBtn.classList.remove('btn-primary');
    histBtn.classList.add('btn-ghost');
    histBtn.textContent = '🕰️ History';
    document.getElementById('filterRow').style.display = 'flex';
  }
  render();
}

function updateStats() {
  const activeNotes = allNotes.filter(n => !n.deleted);
  document.getElementById('statTotal').textContent = activeNotes.length;
  document.getElementById('statPinned').textContent = activeNotes.filter(n=>n.pinned).length;
  const tags = new Set(activeNotes.flatMap(n=>[...(n.tags||[]), ...(n.auto_tags||[])]));
  document.getElementById('statTags').textContent = tags.size;
}

function renderTagFilters() {
  const row = document.getElementById('filterRow');
  row.querySelectorAll('[data-filter]:not([data-filter="all"]):not([data-filter="pinned"])').forEach(e=>e.remove());
  const activeNotes = allNotes.filter(n => !n.deleted);
  const tags = [...new Set(activeNotes.flatMap(n=>n.tags||[]))].filter(Boolean).slice(0,10);
  tags.forEach(tag => {
    const chip = document.createElement('span');
    chip.className='filter-chip'; chip.dataset.filter='tag:'+tag;
    chip.textContent='#'+tag;
    chip.onclick=()=>setFilter('tag:'+tag,chip);
    row.appendChild(chip);
  });
}

function getFilteredNotes() {
  const q = document.getElementById('searchInput').value.toLowerCase();
  let notes = [...allNotes];
  
  if (isHistoryView) {
    notes = notes.filter(n => n.deleted);
  } else {
    notes = notes.filter(n => !n.deleted);
    if(currentFilter==='pinned') notes=notes.filter(n=>n.pinned);
    else if(currentFilter.startsWith('tag:')) { const t=currentFilter.slice(4); notes=notes.filter(n=>(n.tags||[]).includes(t)); }
  }
  
  if(q) notes=notes.filter(n=>
    n.title.toLowerCase().includes(q)||
    n.content.toLowerCase().includes(q)||
    (n.tags||[]).some(t=>t.toLowerCase().includes(q))||
    (n.auto_tags||[]).some(t=>t.toLowerCase().includes(q))
  );
  return [...notes.filter(n=>n.pinned), ...notes.filter(n=>!n.pinned)];
}

function render() {
  const grid = document.getElementById('notesGrid');
  const notes = getFilteredNotes();
  document.getElementById('searchCount').textContent = notes.length ? `${notes.length} note${notes.length>1?'s':''}` : '';
  if(!notes.length) {
    grid.innerHTML=`<div class="notes-empty"><div class="empty-icon">📝</div>${isHistoryView ? 'No deleted notes.' : 'No notes here.<br>Create one to get started!'}</div>`;
    return;
  }
  grid.innerHTML = notes.map((n,i)=>`
    <div class="note-card${n.pinned?' pinned':''}"
         style="--note-color:${n.color||'#7c6aff'}; animation-delay:${i*0.045}s"
         id="card-${n.id}">
      <div class="card-top">
        <div class="note-title">${escHtml(n.title)}</div>
        <div class="card-actions">
          ${n.deleted ? `
            <button class="icon-btn" title="Restore" onclick="restoreNote('${n.id}')">↩️</button>
            <button class="icon-btn del" title="Permanently Delete" onclick="hardDeleteNote('${n.id}')">🗑</button>
          ` : `
            <button class="icon-btn${n.pinned?' pin-active':''}" title="${n.pinned?'Unpin':'Pin'}" onclick="togglePin('${n.id}')">📌</button>
            <button class="icon-btn" title="Edit" onclick="openModal('${n.id}')">✏️</button>
            <button class="icon-btn dl" title="Download PDF" onclick="downloadPDF('${n.id}')">⬇</button>
            <button class="icon-btn del" title="Delete" onclick="deleteNote('${n.id}')">🗑</button>
          `}
        </div>
      </div>
      <div class="note-content">${marked.parse(n.content||'')}</div>
      ${n.audio_file ? `<div style="margin-bottom: 12px;"><audio controls src="/api/audio/${n.audio_file}" style="width:100%; height:32px; border-radius:8px; opacity:0.85; transition:opacity 0.2s;" onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=0.85"></audio></div>` : ''}
      ${(n.tags&&n.tags.length)||(n.auto_tags&&n.auto_tags.length) ? `
        <div class="tags-row">
          ${(n.tags||[]).map(t=>`<span class="tag-chip">#${escHtml(t)}</span>`).join('')}
          ${(n.auto_tags||[]).map(t=>`<span class="auto-tag-chip">${escHtml(t)}</span>`).join('')}
        </div>` : ''}
      <div class="card-footer">
        <span class="card-date">${n.updated?'↻ '+n.updated:n.created}</span>
        ${n.pinned?'<span class="pin-badge">📌 pinned</span>':''}
      </div>
    </div>
  `).join('');
}

/* ──────────────────────────────────────────
   MODAL
────────────────────────────────────────── */
function buildColorPicker() {
  document.getElementById('colorRow').innerHTML = NOTE_COLORS.map(c=>`
    <div class="color-swatch${c===selectedColor?' selected':''}"
         style="background:${c}" data-color="${c}"
         onclick="pickColor('${c}')"></div>
  `).join('');
}
function pickColor(c) {
  selectedColor=c;
  document.querySelectorAll('.color-swatch').forEach(s=>s.classList.toggle('selected',s.dataset.color===c));
}

function openModal(id=null) {
  stopVoice();
  if(isAudioRecording) toggleAudioRecording();
  audioBlob = null;
  removeAudioFlag = false;
  document.getElementById('audioPreviewContainer').style.display = 'none';
  document.getElementById('audioPreview').src = '';
  
  buildColorPicker();
  if(id) {
    const n=allNotes.find(n=>n.id===id);
    document.getElementById('modalTitle').textContent='Edit Note';
    document.getElementById('noteId').value=n.id;
    document.getElementById('titleInput').value=n.title;
    document.getElementById('contentInput').value=n.content;  // raw markdown
    document.getElementById('tagsInput').value=(n.tags||[]).join(', ');
    selectedColor=n.color||'#7c6aff';
    buildColorPicker();
    
    if (n.audio_file) {
      document.getElementById('audioPreviewContainer').style.display = 'block';
      document.getElementById('audioPreview').src = '/api/audio/' + n.audio_file;
    }
  } else {
    document.getElementById('modalTitle').textContent='New Note';
    ['noteId','titleInput','contentInput','tagsInput'].forEach(id=>document.getElementById(id).value='');
    selectedColor='#7c6aff'; buildColorPicker();
  }
  updateCharCount();
  document.getElementById('modalOverlay').classList.add('open');
  setTimeout(()=>document.getElementById('titleInput').focus(),80);
}
function closeModal() {
  stopVoice();
  document.getElementById('modalOverlay').classList.remove('open');
}
document.getElementById('modalOverlay').addEventListener('click', e=>{ if(e.target===e.currentTarget) closeModal(); });
document.addEventListener('keydown', e=>{
  if(e.key==='Escape') closeModal();
  if((e.ctrlKey||e.metaKey)&&e.key==='Enter'&&document.getElementById('modalOverlay').classList.contains('open')) saveNote();
});
function updateCharCount() {
  const v=document.getElementById('contentInput').value.length;
  const el=document.getElementById('charCounter');
  el.textContent=`${v} / 2000`;
  el.className='char-counter'+(v>1800?' over':v>1400?' warn':'');
}

/* ──────────────────────────────────────────
   CONFIRM MODAL
────────────────────────────────────────── */
let confirmActionCallback = null;
function showConfirmModal(title, msg, btnText, callback) {
  document.getElementById('confirmModalTitle').textContent = title;
  document.getElementById('confirmModalMessage').textContent = msg;
  document.getElementById('confirmModalBtn').textContent = btnText;
  confirmActionCallback = callback;
  document.getElementById('confirmModalOverlay').classList.add('open');
}
function closeConfirmModal() {
  document.getElementById('confirmModalOverlay').classList.remove('open');
  confirmActionCallback = null;
}
document.getElementById('confirmModalBtn').addEventListener('click', () => {
  if(confirmActionCallback) confirmActionCallback();
  closeConfirmModal();
});
document.getElementById('confirmModalOverlay').addEventListener('click', e => {
  if(e.target===e.currentTarget) closeConfirmModal();
});
document.addEventListener('keydown', e => {
  if(e.key === 'Escape' && document.getElementById('confirmModalOverlay').classList.contains('open')) {
    closeConfirmModal();
  }
});

/* ──────────────────────────────────────────
   AUDIO RECORDING
────────────────────────────────────────── */
async function toggleAudioRecording() {
  const btn = document.getElementById('audioRecordBtn');
  if (isAudioRecording) {
    audioRecorder.stop();
    isAudioRecording = false;
    btn.classList.remove('recording');
    btn.title = 'Record Voice Note';
  } else {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioRecorder = new MediaRecorder(stream);
      audioChunks = [];
      audioRecorder.ondataavailable = e => audioChunks.push(e.data);
      audioRecorder.onstop = () => {
        audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
        showToast('Audio recorded!', 'success');
        document.getElementById('audioPreview').src = URL.createObjectURL(audioBlob);
        document.getElementById('audioPreviewContainer').style.display = 'block';
        removeAudioFlag = false;
        stream.getTracks().forEach(t => t.stop());
      };
      audioRecorder.start();
      isAudioRecording = true;
      btn.classList.add('recording');
      btn.title = 'Stop Recording';
      showToast('Recording voice note...', 'info');
    } catch (err) {
      console.error(err);
      showToast('Microphone access denied or unavailable', 'error');
    }
  }
}

function removeAudio() {
  audioBlob = null;
  removeAudioFlag = true;
  document.getElementById('audioPreviewContainer').style.display = 'none';
  document.getElementById('audioPreview').src = '';
  if (isAudioRecording) toggleAudioRecording();
}

/* ──────────────────────────────────────────
   VOICE TO TEXT
────────────────────────────────────────── */
let recognition=null, isRecording=false;
(function initVoice() {
  const SpeechRecognition=window.SpeechRecognition||window.webkitSpeechRecognition;
  const btn=document.getElementById('voiceBtn');
  if(!SpeechRecognition) {
    btn.title='Voice not supported in this browser'; btn.classList.add('voice-unsupported');
    return;
  }
  recognition=new SpeechRecognition();
  recognition.continuous=true; recognition.interimResults=true; recognition.lang='en-US';
  recognition.onresult=e=>{
    let interim='', final='';
    for(let i=e.resultIndex;i<e.results.length;i++) {
      if(e.results[i].isFinal) final+=e.results[i][0].transcript;
      else interim+=e.results[i][0].transcript;
    }
    if(final) {
      const ta=document.getElementById('contentInput');
      ta.value+=(ta.value&&!ta.value.endsWith(' ')?' ':'')+final.trim()+' ';
      updateCharCount();
    }
  };
  recognition.onerror=e=>{ showToast('Voice error: '+e.error,'error'); stopVoice(); };
  recognition.onend=()=>{ if(isRecording) stopVoice(); };
})();

function toggleVoice() {
  const btn=document.getElementById('voiceBtn');
  if(btn.classList.contains('voice-unsupported')) { showToast('Speech recognition not supported in this browser','error'); return; }
  if(!recognition) return;
  if(isRecording) stopVoice();
  else { isRecording=true; btn.classList.add('recording'); btn.title='Click to stop'; recognition.start(); showToast('Listening…','info'); }
}
function stopVoice() {
  if(!recognition) return;
  isRecording=false;
  document.getElementById('voiceBtn').classList.remove('recording');
  document.getElementById('voiceBtn').title='Voice to text';
  try { recognition.stop(); } catch(e){}
}

/* ──────────────────────────────────────────
   CRUD
────────────────────────────────────────── */
async function saveNote() {
  const id=document.getElementById('noteId').value;
  const title=document.getElementById('titleInput').value.trim();
  if(!title){ showToast('A title is required','error'); document.getElementById('titleInput').focus(); return; }
  
  let audio_data = null;
  if (audioBlob) {
    const reader = new FileReader();
    reader.readAsDataURL(audioBlob);
    await new Promise(r => reader.onloadend = r);
    audio_data = reader.result.split(',')[1];
  }
  
  const data={
    title, content: document.getElementById('contentInput').value.trim(),
    tags: document.getElementById('tagsInput').value, color: selectedColor,
    audio_data: audio_data, remove_audio: removeAudioFlag
  };
  const res=await fetch(id?`/api/notes/${id}`:'/api/notes',{
    method: id?'PUT':'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)
  });
  if(res.ok) { closeModal(); await loadNotes(); showToast(id?'Note updated':'Note saved','success'); }
  else showToast('Failed to save','error');
}

async function deleteNote(id) {
  showConfirmModal('Move to History?', 'This note will be moved to history. You can restore it later.', 'Move to History', async () => {
    const card=document.getElementById('card-'+id);
    if(card) card.classList.add('deleting');
    setTimeout(async()=>{
      const res=await fetch(`/api/notes/${id}`,{method:'DELETE'});
      if(res.ok) { await loadNotes(); showToast('Note moved to history','info'); }
      else showToast('Delete failed','error');
    }, 380);
  });
}

async function hardDeleteNote(id) {
  showConfirmModal('Permanently Delete?', 'This note will be permanently deleted. This action cannot be undone.', 'Delete Permanently', async () => {
    const card=document.getElementById('card-'+id);
    if(card) card.classList.add('deleting');
    setTimeout(async()=>{
      const res=await fetch(`/api/notes/${id}/hard`,{method:'DELETE'});
      if(res.ok) { await loadNotes(); showToast('Note permanently deleted','success'); }
      else showToast('Delete failed','error');
    }, 380);
  });
}

async function restoreNote(id) {
  const res=await fetch(`/api/notes/${id}/restore`,{method:'PATCH'});
  if(res.ok) { await loadNotes(); showToast('Note restored','success'); }
  else showToast('Restore failed','error');
}

async function togglePin(id) {
  await fetch(`/api/notes/${id}/pin`,{method:'PATCH'});
  await loadNotes();
  const n=allNotes.find(n=>n.id===id);
  showToast(n&&n.pinned?'Note pinned 📌':'Note unpinned','info');
}

function downloadPDF(id) {
  showToast('Generating PDF…','info');
  const a = document.createElement('a');
  a.href = `/api/notes/${id}/pdf`;
  a.download = '';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

/* ──────────────────────────────────────────
   DASHBOARD
────────────────────────────────────────── */
async function toggleDashboard() {
  isDashOpen=!isDashOpen;
  document.getElementById('dashboardPanel').classList.toggle('open', isDashOpen);
  if(isDashOpen) await loadDashboard();
}

async function loadDashboard() {
  const res=await fetch('/api/stats');
  const data=await res.json();
  renderTagChart(data.tag_distribution);
  renderDayChart(data.notes_per_day);
}

function chartDefaults() {
  return {
    color: 'rgba(200,200,220,0.6)',
    plugins:{ legend:{ labels:{ color:'rgba(200,200,220,0.7)', font:{family:'DM Mono',size:10}, boxWidth:12, padding:10 }}},
    scales: undefined
  };
}

function renderTagChart(tagData) {
  const labels=Object.keys(tagData);
  const vals=Object.values(tagData);
  const palette=['#7c6aff','#ff4d6d','#00e5a0','#ffd232','#3db8ff','#ff8c42','#c084fc','#f472b6','#a78bfa','#34d399'];
  if(tagChartInst) tagChartInst.destroy();
  const ctx2=document.getElementById('tagChart').getContext('2d');
  tagChartInst=new Chart(ctx2,{
    type:'doughnut',
    data:{ labels: labels.length?labels:['No tags yet'], datasets:[{
      data: vals.length?vals:[1],
      backgroundColor: labels.length?palette.slice(0,labels.length):['rgba(124,106,255,0.2)'],
      borderColor:'transparent', hoverOffset:6
    }]},
    options:{ responsive:true, maintainAspectRatio:false, cutout:'65%',
      plugins:{ legend:{ position:'right', labels:{ color:'rgba(200,200,220,0.75)', font:{family:'DM Mono',size:10}, boxWidth:10, padding:8 }}}
    }
  });
}

function renderDayChart(dayData) {
  if(dayChartInst) dayChartInst.destroy();
  const ctx2=document.getElementById('dayChart').getContext('2d');
  const gradient=ctx2.createLinearGradient(0,0,0,180);
  gradient.addColorStop(0,'rgba(124,106,255,0.4)'); gradient.addColorStop(1,'rgba(124,106,255,0.0)');
  dayChartInst=new Chart(ctx2,{
    type:'line',
    data:{
      labels: dayData.labels.map(d=>d.slice(5)), // MM-DD
      datasets:[{ label:'Notes', data:dayData.values,
        borderColor:'#7c6aff', backgroundColor:gradient,
        borderWidth:2, pointBackgroundColor:'#7c6aff',
        pointRadius:4, pointHoverRadius:6, tension:0.4, fill:true
      }]
    },
    options:{ responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{ display:false }},
      scales:{
        x:{ ticks:{ color:'rgba(200,200,220,0.5)', font:{family:'DM Mono',size:9}}, grid:{ color:'rgba(255,255,255,0.04)'}},
        y:{ ticks:{ color:'rgba(200,200,220,0.5)', font:{family:'DM Mono',size:9}, stepSize:1, precision:0}, grid:{ color:'rgba(255,255,255,0.04)'}}
      }
    }
  });
}

/* ──────────────────────────────────────────
   FILTERS & VIEW
────────────────────────────────────────── */
function setFilter(f,el) {
  currentFilter=f;
  document.querySelectorAll('.filter-chip').forEach(c=>c.classList.remove('active'));
  el.classList.add('active');
  render();
}
function filterNotes(){ render(); }
function setView(v) {
  currentView=v;
  document.getElementById('notesGrid').classList.toggle('list-view',v==='list');
  document.getElementById('gridViewBtn').classList.toggle('active',v==='grid');
  document.getElementById('listViewBtn').classList.toggle('active',v==='list');
}

/* ──────────────────────────────────────────
   TOAST — redesigned
────────────────────────────────────────── */
const TOAST_CONFIG = {
  success:{ icon:'✅', title:'Success' },
  error:  { icon:'❌', title:'Error' },
  info:   { icon:'💡', title:'Info' },
  warn:   { icon:'⚠️', title:'Warning' }
};

function showToast(msg, type='success') {
  const tc=document.getElementById('toastContainer');
  const cfg=TOAST_CONFIG[type]||TOAST_CONFIG.info;
  const t=document.createElement('div');
  t.className=`toast ${type}`;
  t.style.position='relative';
  t.innerHTML=`
    <div class="toast-icon-wrap">${cfg.icon}</div>
    <div class="toast-body">
      <div class="toast-title">${cfg.title}</div>
      <div class="toast-msg">${msg}</div>
    </div>
    <button class="toast-close" onclick="this.closest('.toast').remove()">✕</button>
    <div class="toast-progress"><div class="toast-progress-bar"></div></div>
  `;
  tc.appendChild(t);
  setTimeout(()=>{ t.classList.add('fadeout'); setTimeout(()=>t.remove(),300); }, 3200);
}

/* ──────────────────────────────────────────
   UTIL
────────────────────────────────────────── */
function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

window.onload=loadNotes;
</script>
</body>
</html>
"""

if __name__ == '__main__':
    app.run(debug=True)