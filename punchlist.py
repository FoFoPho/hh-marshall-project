"""MP IA Punch List (Marshall Project Issue Authority Punch List): reviewers flag a moment in a published video and
describe the fix; supervisors triage and track every report to closure.

Separate SQLite file (punchlist.db) and upload folder next to progress.db, so the
student app's data is never touched. Reports are append-only: changes are
recorded as events, never as edits."""
import hmac
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (Blueprint, abort, jsonify, redirect, render_template,
                   request, send_file, session, url_for)

import db as student_db

bp = Blueprint('punchlist', __name__, url_prefix='/punchlist')

CATEGORIES = [
    ('safety', 'Safety (unsafe or wrong behavior shown)'),
    ('continuity', 'Continuity (character, outfit, prop changes)'),
    ('look', 'Look / animation glitch (hands, faces, morphing)'),
    ('spanish_text', 'Spanish on-screen text'),
    ('spanish_vo', 'Spanish narration wording'),
    ('english_text', 'English on-screen text'),
    ('english_vo', 'English narration wording or pronunciation'),
    ('audio', 'Audio (levels, cutoffs, noise)'),
    ('timing', 'Timing (too fast, too slow, long text)'),
    ('quiz_wording', 'Quiz wording, answer key, or translation'),
    ('webapp_issue', 'Web app behavior or layout'),
    ('other', 'Something else'),
]
SEVERITIES = [
    ('blocks', 'Blocks release'),
    ('should', 'Should fix'),
    ('nice', 'Nice to have'),
]
TARGETS = [
    ('video', 'A moment in a video'),
    ('quiz', 'A quiz question or its answers'),
    ('practical', 'The practical exercise'),
    ('audio_clip', 'A voice-over or audio clip (not in the video)'),
    ('webapp', 'The web app (pages, buttons, layout, certificate)'),
    ('other', 'Something else about this module'),
]
ROLES = [
    ('ia', 'Issue Authority (safety)'),
    ('spanish', 'Spanish reviewer'),
    ('content', 'Content reviewer'),
    ('general', 'Reviewer'),
    ('owner', 'Owner / editor'),
]
OPEN_STATUSES = ('new', 'triaged', 'sent')
DECISIONS = [('approved', 'Approved'), ('conditions', 'Approved with conditions'), ('rejected', 'Not approved')]
STATUSES = ['new', 'triaged', 'sent', 'fixed', 'verified', 'closed', 'wontfix']
APPLIES = [('both', 'Both languages'), ('en', 'English only'), ('es', 'Spanish only')]

MAX_FILES = 5
MAX_BYTES = 6 * 1024 * 1024
IMAGE_MAGIC = {
    b'\x89PNG\r\n\x1a\n': 'png',
    b'\xff\xd8\xff': 'jpg',
    b'GIF8': 'gif',
    b'RIFF': 'webp',
}


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _base_dir():
    return os.path.dirname(student_db.get_db_path())


def _upload_dir():
    path = os.path.join(_base_dir(), 'punchlist_uploads')
    os.makedirs(path, exist_ok=True)
    return path


def conn():
    c = sqlite3.connect(os.path.join(_base_dir(), 'punchlist.db'))
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    return c


def init_punchlist_db():
    with conn() as c:
        c.executescript('''
            CREATE TABLE IF NOT EXISTS reviewers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                expires_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reviewer_id INTEGER NOT NULL,
                target TEXT NOT NULL DEFAULT 'video',
                module INTEGER,
                item_ref TEXT,
                item_text TEXT,
                video_id TEXT NOT NULL DEFAULT '',
                video_label TEXT NOT NULL,
                t_start REAL,
                t_end REAL,
                category TEXT NOT NULL,
                severity TEXT NOT NULL,
                applies_to TEXT NOT NULL,
                what_wrong TEXT NOT NULL,
                should_be TEXT,
                spanish_wording TEXT,
                status TEXT NOT NULL DEFAULT 'new',
                shot_id TEXT,
                fixed_in TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS signoffs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reviewer_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                video_id TEXT NOT NULL,
                decision TEXT NOT NULL,
                note TEXT,
                typed_name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                at TEXT NOT NULL,
                actor TEXT NOT NULL,
                kind TEXT NOT NULL,
                detail TEXT
            );
            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                original TEXT,
                created_at TEXT NOT NULL
            );
        ''')


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def log_event(c, report_id, actor, kind, detail=''):
    c.execute('INSERT INTO events (report_id, at, actor, kind, detail) VALUES (?,?,?,?,?)',
              (report_id, now(), actor, kind, detail))


def load_videos():
    path = os.path.join(os.path.dirname(__file__), 'content', 'punchlist_videos.json')
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def video_by_id(video_id):
    return next((v for v in load_videos() if v['id'] == video_id), None)


def load_modules():
    path = os.path.join(os.path.dirname(__file__), 'content', 'modules.json')
    with open(path, encoding='utf-8') as f:
        return json.load(f).get('modules', [])


def module_choices():
    return [(m['id'], f"Module {m['id']}") for m in load_modules()]


def quiz_question_text(module_id, ref):
    """Snapshot of the English question text for 'Q7' / '7' in this module."""
    digits = ''.join(ch for ch in (ref or '') if ch.isdigit())
    if not digits:
        return ''
    n = int(digits)
    for m in load_modules():
        if m['id'] != module_id:
            continue
        flat = [q for sec in m.get('sections', []) for q in sec.get('quiz', {}).get('questions', [])]
        if 1 <= n <= len(flat):
            q = flat[n - 1]
            return q.get('text', '') + ' | ' + ' / '.join(q.get('options', []))
    return ''


def fmt_time(seconds):
    if seconds is None:
        return ''
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f'{h}:{m:02d}:{sec:02d}' if h else f'{m}:{sec:02d}'


def parse_time(text):
    """Accepts 6:12, 1:06:12, or plain seconds. Returns seconds or None."""
    text = (text or '').strip()
    if not text:
        return None
    try:
        parts = [float(p) for p in text.split(':')]
    except ValueError:
        return None
    if len(parts) > 3 or any(p < 0 for p in parts):
        return None
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return total


def latest_signoff(c, video_id, role):
    return c.execute('SELECT s.*, v.name AS reviewer_name FROM signoffs s JOIN reviewers v ON v.id = s.reviewer_id '
                     'WHERE s.video_id = ? AND s.role = ? ORDER BY s.id DESC LIMIT 1',
                     (video_id, role)).fetchone()


def stale_blockers(c, video_id, since):
    """Open 'blocks release' reports filed after a sign-off was recorded."""
    marks = ','.join('?' * len(OPEN_STATUSES))
    return c.execute(f"SELECT COUNT(*) FROM reports WHERE video_id = ? AND severity = 'blocks' "
                     f"AND status IN ({marks}) AND created_at > ?",
                     [video_id, *OPEN_STATUSES, since]).fetchone()[0]


def signoff_state(c, video, role):
    """What this role may do for this video, and why 'Approved' might be locked."""
    marks = ','.join('?' * len(OPEN_STATUSES))
    sql = f"SELECT COUNT(*) FROM reports WHERE video_id = ? AND severity = 'blocks' AND status IN ({marks})"
    args = [video['id'], *OPEN_STATUSES]
    if role == 'spanish':
        sql += " AND (category LIKE 'spanish%' OR applies_to IN ('es'))"
    open_blocks = c.execute(sql, args).fetchone()[0]
    reasons = []
    if open_blocks:
        reasons.append(f'{open_blocks} open "blocks release" report(s) on this video must be fixed first.')
    if role == 'ia' and video.get('language') == 'es':
        sp = latest_signoff(c, video['id'], 'spanish')
        if not sp or sp['decision'] != 'approved':
            reasons.append('The Spanish reviewer has not approved this Spanish video yet.')
    current = latest_signoff(c, video['id'], role)
    stale = (stale_blockers(c, video['id'], current['created_at'])
             if current and current['decision'] != 'rejected' else 0)
    return {'can_approve': not reasons, 'reasons': reasons, 'stale': stale,
            'current': current,
            'spanish': latest_signoff(c, video['id'], 'spanish') if role == 'ia' else None}


def _labels(pairs):
    return dict(pairs)


@bp.app_template_filter('tc')
def tc_filter(seconds):
    return fmt_time(seconds)


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------

def supervisor_only(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('is_supervisor'):
            return redirect(url_for('supervisor_login'))
        return view(*args, **kwargs)
    return wrapped


def get_reviewer(token):
    with conn() as c:
        row = c.execute('SELECT * FROM reviewers WHERE token = ?', (token,)).fetchone()
    if not row or not row['active']:
        abort(404)
    if row['expires_at'] and row['expires_at'] < now():
        abort(410)
    return row


# ---------------------------------------------------------------------------
# Reviewer pages
# ---------------------------------------------------------------------------

@bp.route('/r/<token>')
def reviewer_page(token):
    reviewer = get_reviewer(token)
    videos = load_videos()
    with conn() as c:
        mine = c.execute('SELECT * FROM reports WHERE reviewer_id = ? ORDER BY id DESC',
                         (reviewer['id'],)).fetchall()
    signoffs = []
    if reviewer['role'] in ('ia', 'spanish'):
        with conn() as c:
            for v in videos:
                if reviewer['role'] == 'spanish' and v.get('language') != 'es':
                    continue
                signoffs.append((v, signoff_state(c, v, reviewer['role'])))
    return render_template('punchlist_reviewer.html', reviewer=reviewer, videos=videos,
                           signoffs=signoffs, decisions=DECISIONS, decision_labels=_labels(DECISIONS),
                           targets=TARGETS, modules=module_choices(),
                           categories=CATEGORIES, severities=SEVERITIES, applies=APPLIES,
                           reports=mine, cat_labels=_labels(CATEGORIES),
                           sev_labels=_labels(SEVERITIES),
                           role_label=_labels(ROLES).get(reviewer['role'], reviewer['role']),
                           sent=request.args.get('sent'))


def _save_images(c, report_id):
    saved = 0
    for f in request.files.getlist('images')[:MAX_FILES]:
        if not f or not f.filename:
            continue
        data = f.read(MAX_BYTES + 1)
        if not data or len(data) > MAX_BYTES:
            continue
        ext = next((e for magic, e in IMAGE_MAGIC.items() if data.startswith(magic)), None)
        if not ext:
            continue
        name = f'{report_id}-{secrets.token_hex(8)}.{ext}'
        with open(os.path.join(_upload_dir(), name), 'wb') as out:
            out.write(data)
        c.execute('INSERT INTO attachments (report_id, filename, original, created_at) VALUES (?,?,?,?)',
                  (report_id, name, (f.filename or '')[:120], now()))
        saved += 1
    return saved


@bp.route('/r/<token>/submit', methods=['POST'])
def submit_report(token):
    reviewer = get_reviewer(token)
    form = request.form
    target = form.get('target', 'video')
    what_wrong = (form.get('what_wrong') or '').strip()
    bad = (target not in _labels(TARGETS) or not what_wrong
           or form.get('category') not in _labels(CATEGORIES)
           or form.get('severity') not in _labels(SEVERITIES)
           or form.get('applies_to') not in _labels(APPLIES))
    video = t_start = t_end = module = None
    item_ref = (form.get('item_ref') or '').strip()[:200]
    item_text = ''
    label = ''
    if not bad and target == 'video':
        video = video_by_id(form.get('video_id', ''))
        t_start = parse_time(form.get('t_start'))
        t_end = parse_time(form.get('t_end'))
        bad = video is None or t_start is None
        if not bad:
            module = video.get('module')
            label = video['label']
    elif not bad:
        try:
            module = int(form.get('module', ''))
        except ValueError:
            bad = True
        if module not in {mid for mid, _ in module_choices()}:
            bad = True
        if target == 'quiz' and not item_ref:
            bad = True
        if not bad:
            item_text = quiz_question_text(module, item_ref) if target == 'quiz' else ''
            label = f"Module {module} - {_labels(TARGETS)[target]}" + (f" - {item_ref}" if item_ref else '')
    if bad:
        return redirect(url_for('punchlist.reviewer_page', token=token, sent='error'))
    # An Issue Authority safety flag always blocks release.
    severity = 'blocks' if (reviewer['role'] == 'ia' and form['category'] == 'safety') else form['severity']
    with conn() as c:
        cur = c.execute(
            '''INSERT INTO reports (reviewer_id, target, module, item_ref, item_text, video_id,
               video_label, t_start, t_end, category, severity, applies_to, what_wrong, should_be,
               spanish_wording, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (reviewer['id'], target, module, item_ref, item_text, video['id'] if video else '',
             label, t_start, t_end, form['category'], severity, form['applies_to'], what_wrong[:4000],
             (form.get('should_be') or '').strip()[:4000],
             (form.get('spanish_wording') or '').strip()[:4000], now()))
        report_id = cur.lastrowid
        n = _save_images(c, report_id)
        log_event(c, report_id, reviewer['name'], 'created', f'{n} screenshot(s) attached')
    return redirect(url_for('punchlist.reviewer_page', token=token, sent='ok'))


@bp.route('/r/<token>/signoff', methods=['POST'])
def submit_signoff(token):
    reviewer = get_reviewer(token)
    video = video_by_id(request.form.get('video_id', ''))
    decision = request.form.get('decision')
    note = (request.form.get('note') or '').strip()[:2000]
    typed = (request.form.get('typed_name') or '').strip()
    role = reviewer['role']
    ok = (video and role in ('ia', 'spanish') and decision in _labels(DECISIONS)
          and not (role == 'spanish' and video.get('language') != 'es')
          and typed.lower() == reviewer['name'].strip().lower()
          and (decision == 'approved' or note))
    if ok:
        with conn() as c:
            if decision == 'approved' and not signoff_state(c, video, role)['can_approve']:
                ok = False
            else:
                c.execute('INSERT INTO signoffs (reviewer_id, role, video_id, decision, note, typed_name, created_at) '
                          'VALUES (?,?,?,?,?,?,?)', (reviewer['id'], role, video['id'], decision, note, typed, now()))
    return redirect(url_for('punchlist.reviewer_page', token=token, sent='signed' if ok else 'signerror') + '#signoff')


@bp.route('/file/<int:attachment_id>')
def attachment(attachment_id):
    token = request.args.get('t', '')
    with conn() as c:
        row = c.execute('SELECT a.*, r.reviewer_id FROM attachments a JOIN reports r '
                        'ON r.id = a.report_id WHERE a.id = ?', (attachment_id,)).fetchone()
        owner = c.execute('SELECT token FROM reviewers WHERE id = ?',
                          (row['reviewer_id'],)).fetchone() if row else None
    if not row:
        abort(404)
    allowed = session.get('is_supervisor') or (
        owner and token and hmac.compare_digest(owner['token'], token))
    if not allowed:
        abort(403)
    return send_file(os.path.join(_upload_dir(), row['filename']))


# ---------------------------------------------------------------------------
# Supervisor pages
# ---------------------------------------------------------------------------

def _report_rows(filters):
    sql = ('SELECT r.*, v.name AS reviewer_name, v.role AS reviewer_role '
           'FROM reports r JOIN reviewers v ON v.id = r.reviewer_id WHERE 1=1')
    args = []
    for key in ('status', 'severity', 'category', 'video_id', 'target'):
        if filters.get(key):
            sql += f' AND r.{key} = ?'
            args.append(filters[key])
    sql += (" ORDER BY CASE r.severity WHEN 'blocks' THEN 0 WHEN 'should' THEN 1 ELSE 2 END,"
            ' r.video_id, r.t_start')
    with conn() as c:
        return c.execute(sql, args).fetchall()


@bp.route('/admin')
@supervisor_only
def admin():
    filters = {k: request.args.get(k, '') for k in ('status', 'severity', 'category', 'video_id', 'target')}
    if 'status' not in request.args:
        filters['status'] = ''
    rows = _report_rows(filters)
    with conn() as c:
        counts = {r['status']: r['n'] for r in c.execute(
            'SELECT status, COUNT(*) AS n FROM reports GROUP BY status')}
    with conn() as c:
        panel = []
        for v in load_videos():
            ia, sp = latest_signoff(c, v['id'], 'ia'), latest_signoff(c, v['id'], 'spanish')
            panel.append((v, ia, sp,
                          stale_blockers(c, v['id'], ia['created_at']) if ia and ia['decision'] != 'rejected' else 0,
                          stale_blockers(c, v['id'], sp['created_at']) if sp and sp['decision'] != 'rejected' else 0))
    return render_template('punchlist_admin.html', rows=rows, filters=filters, counts=counts,
                           panel=panel, decision_labels=_labels(DECISIONS),
                           targets=TARGETS, target_labels=_labels(TARGETS),
                           statuses=STATUSES, categories=CATEGORIES, severities=SEVERITIES,
                           videos=load_videos(), cat_labels=_labels(CATEGORIES),
                           sev_labels=_labels(SEVERITIES), role_labels=_labels(ROLES))


@bp.route('/admin/report/<int:report_id>', methods=['GET', 'POST'])
@supervisor_only
def admin_report(report_id):
    with conn() as c:
        if request.method == 'POST':
            status = request.form.get('status')
            note = (request.form.get('note') or '').strip()
            shot_id = (request.form.get('shot_id') or '').strip()
            fixed_in = (request.form.get('fixed_in') or '').strip()
            if status in STATUSES:
                c.execute('UPDATE reports SET status = ?, shot_id = ?, fixed_in = ? WHERE id = ?',
                          (status, shot_id or None, fixed_in or None, report_id))
                log_event(c, report_id, 'HUB', f'status:{status}',
                          ' | '.join(x for x in (note, f'shot {shot_id}' if shot_id else '',
                                                 f'fixed in {fixed_in}' if fixed_in else '') if x))
            elif note:
                log_event(c, report_id, 'HUB', 'note', note)
            return redirect(url_for('punchlist.admin_report', report_id=report_id))
        report = c.execute('SELECT r.*, v.name AS reviewer_name, v.role AS reviewer_role '
                           'FROM reports r JOIN reviewers v ON v.id = r.reviewer_id WHERE r.id = ?',
                           (report_id,)).fetchone()
        if not report:
            abort(404)
        events = c.execute('SELECT * FROM events WHERE report_id = ? ORDER BY id', (report_id,)).fetchall()
        files = c.execute('SELECT * FROM attachments WHERE report_id = ?', (report_id,)).fetchall()
    return render_template('punchlist_report.html', r=report, events=events, files=files,
                           target_labels=_labels(TARGETS),
                           statuses=STATUSES, cat_labels=_labels(CATEGORIES),
                           sev_labels=_labels(SEVERITIES), role_labels=_labels(ROLES),
                           app_labels=_labels(APPLIES), video=video_by_id(report['video_id']))


@bp.route('/admin/reviewers', methods=['GET', 'POST'])
@supervisor_only
def admin_reviewers():
    with conn() as c:
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'add' and request.form.get('name', '').strip():
                days = int(request.form.get('days') or 30)
                role = request.form.get('role') if request.form.get('role') in _labels(ROLES) else 'content'
                c.execute('INSERT INTO reviewers (token, name, role, expires_at, created_at) VALUES (?,?,?,?,?)',
                          (secrets.token_urlsafe(24), request.form['name'].strip()[:80], role,
                           (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec='seconds'),
                           now()))
            elif action == 'extend':
                c.execute('UPDATE reviewers SET expires_at = ?, active = 1 WHERE id = ?',
                          ((datetime.now(timezone.utc) + timedelta(days=30)).isoformat(timespec='seconds'),
                           int(request.form['id'])))
            elif action == 'toggle':
                c.execute('UPDATE reviewers SET active = 1 - active WHERE id = ?',
                          (int(request.form['id']),))
            return redirect(url_for('punchlist.admin_reviewers'))
        rows = c.execute('SELECT * FROM reviewers ORDER BY id DESC').fetchall()
    return render_template('punchlist_reviewers.html', rows=rows, roles=ROLES,
                           role_labels=_labels(ROLES), base=request.url_root.rstrip('/'))


# ---------------------------------------------------------------------------
# Export (pulled into the Review Log in Dropbox)
# ---------------------------------------------------------------------------

def _export_allowed():
    if session.get('is_supervisor'):
        return True
    expected = os.environ.get('PUNCHLIST_EXPORT_TOKEN', '')
    given = request.headers.get('X-Punchlist-Token', '')
    return bool(expected) and hmac.compare_digest(expected, given)


@bp.route('/export.json')
def export_json():
    if not _export_allowed():
        abort(403)
    with conn() as c:
        reports = [dict(r) for r in c.execute(
            'SELECT r.*, v.name AS reviewer_name, v.role AS reviewer_role FROM reports r '
            'JOIN reviewers v ON v.id = r.reviewer_id ORDER BY r.id')]
        events = [dict(e) for e in c.execute('SELECT * FROM events ORDER BY id')]
        files = [dict(a) for a in c.execute('SELECT * FROM attachments ORDER BY id')]
        signoffs = [dict(x) for x in c.execute('SELECT s.*, v.name AS reviewer_name FROM signoffs s '
                                               'JOIN reviewers v ON v.id = s.reviewer_id ORDER BY s.id')]
    for r in reports:
        r['timecode'] = (fmt_time(r['t_start']) + (f" - {fmt_time(r['t_end'])}" if r['t_end'] else '')
                         if r['t_start'] is not None else '')
        r['video'] = video_by_id(r['video_id'])
        r['events'] = [e for e in events if e['report_id'] == r['id']]
        r['attachments'] = [a for a in files if a['report_id'] == r['id']]
    return jsonify({'reports': reports, 'signoffs': signoffs})


@bp.route('/export/file/<int:attachment_id>')
def export_file(attachment_id):
    if not _export_allowed():
        abort(403)
    with conn() as c:
        row = c.execute('SELECT * FROM attachments WHERE id = ?', (attachment_id,)).fetchone()
    if not row:
        abort(404)
    return send_file(os.path.join(_upload_dir(), row['filename']))
