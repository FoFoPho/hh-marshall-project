import csv
import os
import io
import json
from datetime import datetime
from functools import wraps
from urllib.parse import urlparse, parse_qs

from flask import (
    Flask, session, render_template, redirect,
    url_for, request, send_file, Response
)

import db

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-prod')
db.init_db()


# ---------------------------------------------------------------------------
# Content helpers
# ---------------------------------------------------------------------------

def load_content():
    path = os.path.join(os.path.dirname(__file__), 'content', 'modules.json')
    with open(path) as f:
        return json.load(f)


def load_modules():
    return load_content()['modules']


def get_module(module_id):
    for m in load_modules():
        if m['id'] == module_id:
            return m
    return None


def build_steps(module):
    """Flat ordered list of lesson/quiz steps (excludes welcome and complete)."""
    steps = []
    for section in module.get('sections', []):
        for page in section.get('pages', []):
            steps.append({
                'type': 'lesson',
                'section_id': section['id'],
                'section_title': section['title'].upper(),
                'page': page,
                'section': section,
            })
        steps.append({
            'type': 'quiz',
            'section_id': section['id'],
            'section_title': section['title'].upper(),
            'section': section,
            'quiz': section['quiz'],
        })
    return steps


def youtube_embed_url(url):
    """Convert a YouTube watch/short URL to a nocookie embed URL."""
    if not url:
        return ''
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    if parsed.netloc.endswith('youtu.be'):
        video_id = parsed.path.lstrip('/')
    else:
        video_id = params.get('v', [''])[0]
    start = params.get('t', ['0'])[0].rstrip('s')
    return f"https://www.youtube-nocookie.com/embed/{video_id}?start={start}&rel=0&modestbranding=1"


app.jinja_env.globals['youtube_embed'] = youtube_embed_url


def sync_progress():
    """Push the current session's progress on the active module to the DB."""
    user = session.get('user')
    module_id = session.get('module_id')
    if not user or not user.get('email') or module_id is None:
        return
    db.save_progress(
        email=user['email'],
        module_id=module_id,
        first_name=user.get('first_name', ''),
        last_name=user.get('last_name', ''),
        job_title=user.get('job_title', ''),
        current_step=session.get('current_step', 1),
        completed_sections=session.get('completed_sections', []),
        quiz_failed_section=session.get('quiz_failed_section'),
        cert_number=session.get('cert_number'),
        completed_at=session.get('completed_at'),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    welcome_video = load_content().get('welcome_video', '')
    return render_template('welcome.html', welcome_video=welcome_video)


@app.route('/start', methods=['POST'])
def welcome_start():
    first_name = request.form.get('first_name', '').strip()
    last_name  = request.form.get('last_name', '').strip()
    job_title  = request.form.get('job_title', '').strip()
    email      = db.normalize_email(request.form.get('email', ''))

    if not first_name or not last_name or not email:
        welcome_video = load_content().get('welcome_video', '')
        return render_template('welcome.html', welcome_video=welcome_video,
                               error="Please enter your first name, last name, and email before continuing.")

    session['user'] = {
        'first_name': first_name,
        'last_name':  last_name,
        'job_title':  job_title,
        'email':      email,
    }
    return redirect(url_for('modules'))


@app.route('/modules')
def modules():
    user = session.get('user')
    if not user:
        return redirect(url_for('index'))
    progress_by_module = {
        p['module_id']: p for p in db.get_progress_for_email(user['email'])
    }
    return render_template('module_select.html', modules=load_modules(),
                           progress_by_module=progress_by_module)


@app.route('/module/<int:module_id>')
def start_module(module_id):
    module = get_module(module_id)
    user = session.get('user')
    if not module or not user:
        return redirect(url_for('index'))

    # Reset module state while preserving user info
    session.clear()
    session['user'] = user
    session['module_id'] = module_id

    steps = build_steps(module)
    if not steps:
        return redirect(url_for('complete', module_id=module_id))

    existing = db.get_progress(user['email'], module_id)
    if existing:
        # Resume in-progress or already-completed work on this module.
        session['current_step']        = existing['current_step']
        session['completed_sections']  = existing['completed_sections']
        session['quiz_failed_section'] = existing['quiz_failed_section']
        if existing['cert_number']:
            session['cert_number']  = existing['cert_number']
            session['completed_at'] = existing['completed_at']
            return redirect(url_for('complete', module_id=module_id))
        return redirect(url_for('step', module_id=module_id, step_num=existing['current_step']))

    session['completed_sections'] = []
    session['quiz_failed_section'] = None
    session['current_step'] = 1
    sync_progress()
    return redirect(url_for('step', module_id=module_id, step_num=1))


@app.route('/module/<int:module_id>/reset')
def reset_module(module_id):
    module = get_module(module_id)
    user = session.get('user')
    if not module or not user:
        return redirect(url_for('index'))

    db.delete_progress(user['email'], module_id)
    return redirect(url_for('start_module', module_id=module_id))


@app.route('/module/<int:module_id>/step/<int:step_num>')
def step(module_id, step_num):
    module = get_module(module_id)
    if not module or session.get('module_id') != module_id:
        return redirect(url_for('index'))

    steps = build_steps(module)
    current = session.get('current_step', 0)

    # Gating: can't jump ahead of unlocked progress
    if step_num > current:
        if current == 0:
            return redirect(url_for('start_module', module_id=module_id))
        return redirect(url_for('step', module_id=module_id, step_num=current))

    if step_num < 1 or step_num > len(steps):
        return redirect(url_for('index'))

    step_data = steps[step_num - 1]   # steps list is 0-indexed; URLs are 1-indexed

    total_display_steps = len(steps) + 2   # welcome(01) + steps + complete(last)
    display_num = f"{step_num + 1:02d}"    # welcome=01, step1=02, step2=03 …

    # Prev URL
    if step_num == 1:
        prev_url = url_for('start_module', module_id=module_id)
    else:
        prev_url = url_for('step', module_id=module_id, step_num=step_num - 1)

    # Next URL (may be blocked on failed quiz). Skip forward over any quiz
    # step whose section is already passed — happens when restudying an
    # earlier section after a later quiz failure.
    completed_sections = session.get('completed_sections', [])
    next_step_num = step_num + 1
    while (next_step_num <= len(steps)
           and steps[next_step_num - 1]['type'] == 'quiz'
           and steps[next_step_num - 1]['section_id'] in completed_sections):
        next_step_num += 1

    if next_step_num > len(steps):
        next_url = url_for('complete', module_id=module_id)
    else:
        next_url = url_for('step', module_id=module_id, step_num=next_step_num)

    quiz_failed = (session.get('quiz_failed_section') == step_data.get('section_id'))

    if step_data['type'] == 'lesson':
        # Viewing a lesson unlocks the next step (the quiz).
        # This lets the user click NEXT from lesson → quiz without being gated.
        if step_num >= current:
            session['current_step'] = step_num + 1
            sync_progress()

        return render_template('lesson.html',
            module=module,
            step=step_data,
            step_num=step_num,
            display_num=display_num,
            prev_url=prev_url,
            next_url=next_url,
        )
    elif step_data['type'] == 'quiz':
        restudy_url = url_for('restudy', module_id=module_id, section_id=step_data['section_id'])
        return render_template('quiz.html',
            module=module,
            step=step_data,
            step_num=step_num,
            display_num=display_num,
            prev_url=prev_url,
            next_url=next_url,
            quiz_failed=quiz_failed,
            restudy_url=restudy_url,
        )

    return redirect(url_for('index'))


@app.route('/module/<int:module_id>/quiz/<section_id>', methods=['POST'])
def submit_quiz(module_id, section_id):
    module = get_module(module_id)
    if not module or session.get('module_id') != module_id:
        return redirect(url_for('index'))

    steps = build_steps(module)

    # Find the quiz step for this section
    quiz_step_num = None
    quiz_step = None
    for i, s in enumerate(steps):
        if s['type'] == 'quiz' and s['section_id'] == section_id:
            quiz_step_num = i + 1   # 1-indexed
            quiz_step = s
            break

    if quiz_step is None:
        return redirect(url_for('index'))

    # Gating: must have reached this step
    current = session.get('current_step', 0)
    if quiz_step_num > current:
        return redirect(url_for('step', module_id=module_id, step_num=current))

    # Grade every question — all must be correct
    questions = quiz_step['quiz']['questions']
    all_correct = True
    for i, q in enumerate(questions):
        answer = request.form.get(f'q{i}')
        if answer is None or int(answer) != q['correct']:
            all_correct = False
            break

    if all_correct:
        session['quiz_failed_section'] = None
        completed = list(session.get('completed_sections', []))
        if section_id not in completed:
            completed.append(section_id)
        session['completed_sections'] = completed

        next_step = quiz_step_num + 1
        if next_step > len(steps):
            session['current_step'] = next_step
            sync_progress()
            return redirect(url_for('complete', module_id=module_id))

        session['current_step'] = next_step
        sync_progress()
        return redirect(url_for('step', module_id=module_id, step_num=next_step))
    else:
        session['quiz_failed_section'] = section_id
        # Ensure current_step is at least at the quiz step
        if current < quiz_step_num:
            session['current_step'] = quiz_step_num
        sync_progress()
        return redirect(url_for('step', module_id=module_id, step_num=quiz_step_num))


@app.route('/module/<int:module_id>/restudy/<section_id>')
def restudy(module_id, section_id):
    module = get_module(module_id)
    if not module or session.get('module_id') != module_id:
        return redirect(url_for('index'))

    # Note: quiz_failed_section is intentionally left set here — it's what
    # marks the student as "Restudy" on the supervisor dashboard, and should
    # stay true for the whole remediation period. submit_quiz() clears it on
    # a passing retry (or re-sets it on another failure), not this route.

    # Send the student back one section further, so they review the
    # previous section before retrying — unless this is already the
    # first section, in which case there's nothing earlier to review.
    sections = module.get('sections', [])
    idx = next((i for i, s in enumerate(sections) if s['id'] == section_id), None)
    if idx is None:
        return redirect(url_for('index'))
    target_section_id = sections[idx - 1]['id'] if idx > 0 else section_id

    steps = build_steps(module)
    for i, s in enumerate(steps):
        if s.get('section_id') == target_section_id and s['type'] == 'lesson':
            lesson_step_num = i + 1
            return redirect(url_for('step', module_id=module_id, step_num=lesson_step_num))

    return redirect(url_for('index'))


@app.route('/module/<int:module_id>/complete')
def complete(module_id):
    module = get_module(module_id)
    if not module or session.get('module_id') != module_id:
        return redirect(url_for('index'))

    # Verify all sections have been passed
    sections = module.get('sections', [])
    completed = session.get('completed_sections', [])
    if any(s['id'] not in completed for s in sections):
        current = session.get('current_step', 0)
        if current == 0:
            return redirect(url_for('start_module', module_id=module_id))
        return redirect(url_for('step', module_id=module_id, step_num=current))

    # Generate cert number once  (format: M1_FC_090126_01)
    if 'cert_number' not in session:
        user = session.get('user', {})
        initials = (
            user.get('first_name', 'X')[0].upper() +
            user.get('last_name',  'X')[0].upper()
        )
        now = datetime.now()
        date_code = now.strftime('%m%d%y')   # MMDDYY
        session['cert_number'] = f"M{module_id}_{initials}_{date_code}_01"
        session['completed_at'] = now.strftime('%Y-%m-%d')
        sync_progress()

    steps = build_steps(module)
    display_num = f"{len(steps) + 2:02d}"

    return render_template('complete.html',
        module=module,
        user=session.get('user', {}),
        cert_number=session.get('cert_number'),
        completed_at=session.get('completed_at'),
        display_num=display_num,
    )


@app.route('/module/<int:module_id>/certificate')
def download_certificate(module_id):
    module = get_module(module_id)
    if not module or session.get('module_id') != module_id or 'cert_number' not in session:
        return redirect(url_for('index'))

    from certificate import generate_certificate
    user = session.get('user', {})
    pdf_bytes = generate_certificate(
        first_name   = user.get('first_name', ''),
        last_name    = user.get('last_name', ''),
        module_title = module.get('title', f'Module {module_id}'),
        cert_number  = session.get('cert_number', ''),
        completed_at = session.get('completed_at', ''),
    )

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"marshall-project-module-{module_id}-certificate.pdf",
    )


# ---------------------------------------------------------------------------
# Supervisor Dashboard
# ---------------------------------------------------------------------------

DEV_SUPERVISOR_PASSWORD = 'dev-supervisor-password-change-in-prod'


def get_supervisor_passwords():
    """Any env var prefixed SUPERVISOR_PASSWORD is a valid password — lets
    new ones be added on Railway anytime with no code change."""
    passwords = {v for k, v in os.environ.items() if k.startswith('SUPERVISOR_PASSWORD') and v}
    return passwords or {DEV_SUPERVISOR_PASSWORD}


def supervisor_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('is_supervisor'):
            return redirect(url_for('supervisor_login'))
        return view(*args, **kwargs)
    return wrapped


def section_title_by_id(module, section_id):
    for s in module.get('sections', []) if module else []:
        if s['id'] == section_id:
            return s['title']
    return section_id


def section_index_by_id(module, section_id):
    """1-indexed position of a section within its module, or None if not found."""
    for i, s in enumerate(module.get('sections', []) if module else []):
        if s['id'] == section_id:
            return i + 1
    return None


def build_dashboard_rows():
    rows = []
    for p in db.get_all_progress():
        module = get_module(p['module_id'])
        module_title = module['title'] if module else f"Module {p['module_id']}"
        total_sections = len(module['sections']) if module else None
        current_section_num = None

        if p['cert_number']:
            status, status_class, section_label = 'Completed', 'completed', '—'
            current_section_num = total_sections
        elif p['quiz_failed_section']:
            failed_title = section_title_by_id(module, p['quiz_failed_section'])
            status = 'Restudy'
            status_class = 'restudying'
            section_label = failed_title
            current_section_num = section_index_by_id(module, p['quiz_failed_section'])
        else:
            status, status_class = 'In Progress', 'in_progress'
            section_label = '—'
            if module:
                steps = build_steps(module)
                idx = p['current_step'] - 1
                if 0 <= idx < len(steps):
                    section_label = steps[idx]['section']['title']
                    current_section_num = section_index_by_id(module, steps[idx]['section']['id'])
                elif idx >= len(steps):
                    # Passed every quiz but hasn't loaded /complete yet.
                    current_section_num = total_sections

        try:
            updated_at = datetime.fromisoformat(p['updated_at']).strftime('%Y-%m-%d %I:%M %p UTC')
        except (TypeError, ValueError):
            updated_at = p['updated_at'] or ''

        if total_sections:
            progress = f"{current_section_num or 1}/{total_sections}"
        else:
            progress = '?/?'

        rows.append({
            'first_name': p['first_name'],
            'last_name': p['last_name'],
            'email': p['email'],
            'module_id': p['module_id'],
            'module_title': module_title,
            'progress': progress,
            'section': section_label,
            'status': status,
            'status_class': status_class,
            'cert_number': p['cert_number'] or '',
            'updated_at': updated_at,
        })
    return rows


@app.route('/supervisor/login', methods=['GET', 'POST'])
def supervisor_login():
    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password and password in get_supervisor_passwords():
            session['is_supervisor'] = True
            return redirect(url_for('supervisor_dashboard'))
        error = 'Incorrect password.'
    return render_template('supervisor_login.html', error=error)


@app.route('/supervisor/logout')
def supervisor_logout():
    session.pop('is_supervisor', None)
    return redirect(url_for('supervisor_login'))


@app.route('/supervisor')
@supervisor_required
def supervisor_dashboard():
    return render_template('supervisor_dashboard.html', rows=build_dashboard_rows())


@app.route('/supervisor/data.json')
@supervisor_required
def supervisor_data():
    return {'rows': build_dashboard_rows()}


@app.route('/supervisor/export.csv')
@supervisor_required
def supervisor_export_csv():
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['First Name', 'Last Name', 'Email', 'Module', 'Progress', 'Current Section',
                      'Status', 'Cert Number', 'Last Updated'])
    for r in build_dashboard_rows():
        writer.writerow([r['first_name'], r['last_name'], r['email'], r['module_title'],
                          r['progress'], r['section'], r['status'], r['cert_number'], r['updated_at']])

    return Response(
        buf.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=marshall-project-progress.csv'},
    )


@app.route('/supervisor/reset', methods=['POST'])
@supervisor_required
def supervisor_reset():
    db.reset_all_progress()
    return redirect(url_for('supervisor_dashboard'))


@app.route('/supervisor/edit/<email>', methods=['GET', 'POST'])
@supervisor_required
def supervisor_edit(email):
    records = db.get_progress_for_email(email)
    if not records:
        return redirect(url_for('supervisor_dashboard'))
    current = records[0]

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        new_email = request.form.get('email', '').strip()

        if not first_name or not last_name or not new_email:
            return render_template('supervisor_edit.html', record=current,
                                   error='First name, last name, and email are all required.')

        if not db.rename_student(email, first_name, last_name, new_email):
            return render_template('supervisor_edit.html', record=current,
                                   error='That email is already used by another student in one of this student\'s modules.')

        return redirect(url_for('supervisor_dashboard'))

    return render_template('supervisor_edit.html', record=current)


@app.route('/supervisor/delete/<email>/<int:module_id>', methods=['POST'])
@supervisor_required
def supervisor_delete(email, module_id):
    db.delete_progress(email, module_id)
    return redirect(url_for('supervisor_dashboard'))


if __name__ == '__main__':
    app.run(debug=True)
