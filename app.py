import os
import io
import json
from datetime import datetime
from urllib.parse import urlparse, parse_qs

from flask import (
    Flask, session, render_template, redirect,
    url_for, request, send_file
)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-prod')


# ---------------------------------------------------------------------------
# Content helpers
# ---------------------------------------------------------------------------

def load_modules():
    path = os.path.join(os.path.dirname(__file__), 'content', 'modules.json')
    with open(path) as f:
        return json.load(f)['modules']


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
    """Convert a YouTube watch URL to a nocookie embed URL."""
    if not url:
        return ''
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    video_id = params.get('v', [''])[0]
    start = params.get('t', ['0'])[0].rstrip('s')
    return f"https://www.youtube-nocookie.com/embed/{video_id}?start={start}&rel=0&modestbranding=1"


app.jinja_env.globals['youtube_embed'] = youtube_embed_url


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return render_template('module_select.html', modules=load_modules())


@app.route('/module/<int:module_id>')
def start_module(module_id):
    module = get_module(module_id)
    if not module:
        return redirect(url_for('index'))
    session.clear()
    session['module_id'] = module_id
    session['current_step'] = 0   # 0 = no steps unlocked yet (welcome not counted)
    session['completed_sections'] = []
    session['quiz_failed_section'] = None
    return render_template('welcome.html', module=module)


@app.route('/module/<int:module_id>/start', methods=['POST'])
def module_start(module_id):
    module = get_module(module_id)
    if not module or session.get('module_id') != module_id:
        return redirect(url_for('index'))

    first_name = request.form.get('first_name', '').strip()
    last_name  = request.form.get('last_name', '').strip()
    job_title  = request.form.get('job_title', '').strip()
    email      = request.form.get('email', '').strip()

    if not first_name or not last_name:
        return render_template('welcome.html', module=module,
                               error="Please enter your first and last name before continuing.")

    session['user'] = {
        'first_name': first_name,
        'last_name':  last_name,
        'job_title':  job_title,
        'email':      email,
    }

    steps = build_steps(module)
    if not steps:
        # Module has no sections — go straight to complete
        return redirect(url_for('complete', module_id=module_id))

    session['current_step'] = 1   # step 1 is the first lesson
    return redirect(url_for('step', module_id=module_id, step_num=1))


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

    # Next URL (may be blocked on failed quiz)
    if step_num == len(steps):
        next_url = url_for('complete', module_id=module_id)
    else:
        next_url = url_for('step', module_id=module_id, step_num=step_num + 1)

    quiz_failed = (session.get('quiz_failed_section') == step_data.get('section_id'))

    if step_data['type'] == 'lesson':
        # Viewing a lesson unlocks the next step (the quiz).
        # This lets the user click NEXT from lesson → quiz without being gated.
        if step_num >= current:
            session['current_step'] = step_num + 1

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
            return redirect(url_for('complete', module_id=module_id))

        session['current_step'] = next_step
        return redirect(url_for('step', module_id=module_id, step_num=next_step))
    else:
        session['quiz_failed_section'] = section_id
        # Ensure current_step is at least at the quiz step
        if current < quiz_step_num:
            session['current_step'] = quiz_step_num
        return redirect(url_for('step', module_id=module_id, step_num=quiz_step_num))


@app.route('/module/<int:module_id>/restudy/<section_id>')
def restudy(module_id, section_id):
    module = get_module(module_id)
    if not module or session.get('module_id') != module_id:
        return redirect(url_for('index'))

    session['quiz_failed_section'] = None

    steps = build_steps(module)
    for i, s in enumerate(steps):
        if s.get('section_id') == section_id and s['type'] == 'lesson':
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


if __name__ == '__main__':
    app.run(debug=True)
