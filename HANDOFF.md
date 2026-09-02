# The Marshall Project — Handoff Document

This document is updated every session. Check the date at the top to confirm you have the latest version before starting work.

**Last updated:** 2026-09-02 (Session 5)  
**Last session:** Real header logo + Module 1 content from script docx

---

## Project Overview

A web-based safety training course platform for Hammer Haag employees. Users select a training module, enter their name, watch safety videos, complete section quizzes (must score 100% to advance), and download a completion certificate.

---

## Tech Stack

| Layer       | Choice                  |
|-------------|-------------------------|
| Language    | Python 3.11             |
| Framework   | Flask 3.0               |
| Templates   | Jinja2 (server-rendered)|
| PDF         | ReportLab               |
| Server      | Gunicorn                |
| Hosting     | Railway                 |
| Session     | Flask signed cookies (per-browser state) |
| Persistence | SQLite (`db.py`), keyed by email + module — enables cross-device resume |

---

## File Structure

```
HH Marshall Project - 2026/
├── app.py              # All Flask routes and logic
├── db.py               # SQLite progress persistence (resume across devices)
├── certificate.py      # ReportLab PDF generation
├── requirements.txt    # flask, reportlab, gunicorn
├── Procfile            # web: gunicorn app:app
├── .python-version     # 3.11
├── .gitignore
├── content/
│   └── modules.json    # ← EDIT THIS to add/update content
├── static/
│   ├── css/style.css   # Design system (colors, layout, components)
│   ├── js/main.js      # Quiz answer selection + NEXT guard
│   └── assets/         # Logo and other static images (empty for now)
├── templates/
│   ├── base.html           # Header shell
│   ├── module_select.html  # Module grid page
│   ├── welcome.html        # Welcome video + user info form
│   ├── lesson.html         # Lesson page (video + brief)
│   ├── quiz.html           # Quiz page with gating
│   └── complete.html       # Completion + certificate download
└── HANDOFF.md          # ← This file
```

---

## How to Run Locally

```bash
cd "HH Marshall Project - 2026"
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
flask run
```

Open: http://localhost:5000

---

## How to Add/Update Content

**All course content lives in `content/modules.json`.** No code changes needed.

### Add a new section to an existing module:
```json
{
  "id": "my-section-id",       // URL-safe slug, no spaces
  "title": "Section Title",
  "pages": [
    {
      "type": "lesson",
      "video_url": "https://www.youtube.com/watch?v=VIDEO_ID",
      "video_label": "SECTION VIDEO",
      "brief_label": "SAFETY BRIEF",
      "brief_text": "Text blurb goes here."
    }
  ],
  "quiz": {
    "questions": [
      {
        "text": "Question text?",
        "options": ["Option A", "Option B", "Option C", "Option D"],
        "correct": 0   // 0-indexed (0 = first option)
      }
    ]
  }
}
```

### Add a new lesson page within a section:
Just add another object to the `pages` array. Each page gets its own lesson step.

### Multiple quiz questions:
Add more objects to the `questions` array. All questions are shown on one quiz page; all must be correct to pass.

### Add a new module:
Add a new object to the top-level `modules` array. Use the next number (5, 6, etc.) and set the icon to one of: `hardhat`, `stairs`, `crosshair`, `forklift` (or add a new SVG in `module_select.html`).

---

## User Flow (per session)

1. `/` → Module selection grid
2. `/module/<id>` → Welcome page (clears session, fresh start)
3. User fills in name/email → POST to `/module/<id>/start`
4. `/module/<id>/step/1` → First lesson
5. `/module/<id>/step/2` → Quiz for section 1
   - **Correct**: advance to step 3 (next section lesson or complete)
   - **Wrong**: stay on quiz, failure banner shown, NEXT locked
   - User clicks "START SECTION OVER" → `/module/<id>/restudy/<section_id>` → back to step 1
6. After all sections passed → `/module/<id>/complete`
7. Certificate PDF download → `/module/<id>/certificate`

---

## Gating Rules

- Users **cannot skip ahead** past their current progress (server-side redirect enforces this)
- NEXT is **disabled client-side** until a quiz answer is selected
- After a wrong answer, NEXT is **disabled both client and server-side**
- "START SECTION OVER" is the only way out of a failed quiz

---

## Resume / Cross-Device Progress

Progress is persisted server-side in SQLite (`db.py`), keyed by `(email, module_id)`, in addition to the session cookie. Session cookies still drive gating during an active visit; the DB is what makes progress survive a closed tab or a different device.

- `GET /module/<id>` looks up existing progress for the logged-in email before resetting anything. If found and not yet certified, it hydrates the session and redirects straight to the saved step. If found and already certified, it redirects to the completion page (cert re-downloadable from any device).
- Every point that mutates `current_step`, `completed_sections`, or `quiz_failed_section` also writes through to the DB via the `sync_progress()` helper in `app.py`.
- `GET /module/<id>/reset` deletes the DB row for that email/module and restarts from step 1 — this is the explicit "Start Over" escape hatch, surfaced on the module select cards.
- Identity is **email only** (normalized to lowercase/trimmed) — first/last name and job title are stored for display and certificate generation but aren't part of the lookup key. There's no verification step (e.g. a confirmation email), so this trusts self-reported email the same way the app already trusted self-reported names.

---

## Railway Deployment

1. Push repo to GitHub
2. New project on Railway → connect GitHub repo
3. Set environment variable: `SECRET_KEY` = any long random string
4. Railway auto-detects Python + runs `gunicorn app:app` from Procfile
5. **Required for resume to survive redeploys:** attach a Railway Volume to the service (e.g. mounted at `/data`) and set `DATABASE_PATH=/data/progress.db`. Without this, `progress.db` lives on the container's ephemeral filesystem and is wiped on every redeploy/restart — resume would silently stop working after each deploy.

**Railway URL:** (already deployed — update this line with the live URL)

---

## Design System

| Token         | Value     |
|---------------|-----------|
| Primary blue  | `#1B4FBF` |
| Black         | `#111111` |
| Background    | `#F2F3F5` |
| Card bg       | `#FFFFFF` |
| Correct green | `#28A745` |
| Error red     | `#DC3545` |

Font: Barlow Condensed (headings) + Barlow (body) via Google Fonts.

---

## Session State Keys

| Key                   | Type       | Notes                              |
|-----------------------|------------|------------------------------------|
| `module_id`           | int        | Which module is active             |
| `current_step`        | int        | Highest unlocked step number (1-indexed) |
| `completed_sections`  | list[str]  | Section IDs that passed quiz       |
| `quiz_failed_section` | str / None | Section ID of last failed quiz     |
| `user`                | dict       | first_name, last_name, job_title, email |
| `cert_number`         | str        | Generated on module completion     |
| `completed_at`        | str        | ISO date string                    |

---

## Certificate PDF

The certificate uses `static/assets/MP Cert Template.png` as a full-page background. Four text fields are overlaid at calibrated positions in `certificate.py`:

| Field | Color | Position constants |
|---|---|---|
| Name | Blue `#1B4FBF` | `page_w*0.500, page_h*0.530` |
| Module title | Black `#111111` | `page_w*0.500, page_h*0.385` |
| Date | Black | `page_w*0.710, page_h*0.183` |
| Cert number | Black | `page_w*0.195, page_h*0.068` |

**Cert number format:** `M{module_id}_{initials}_{MMDDYY}_01`  
Example: `M1_FC_090126_01` (Module 1, Forrest Conner, Sep 01 2026)

To adjust text positions, edit the float constants in `certificate.py`. Page is landscape letter (792×612 pts). Larger y = higher on page.

---

## Pending / Next Steps

- [ ] Fill in Modules 2, 3, and 4 content — user is dropping script docs into `Modules/` (see "Module Script Docs" below) one at a time for conversion into `modules.json`
- [ ] Record the live Railway URL above
- [ ] Consider adding a logo bar / splash screen

---

## Module Script Docs

The user drops a `.docx` script per module into `Modules/` (untracked in git — source files, not app code) for conversion into `content/modules.json`. Confirmed format (validated against Module 1's script):

```
Section – <Section Title>
Video: <youtube.com/watch?v=... or youtu.be/... link>
Text:
<lesson blurb — becomes brief_text>

Quiz –
  • <question text>
    A. <option> B. <option> C. <option> D. <option>
  • ...
Answer Key
  • <letter per question, in order>
```

Notes for processing the next one:
- `.docx` isn't readable directly — convert first: `textutil -convert txt -stdout "Modules/<file>.docx"`.
- Video links may be `youtu.be/ID` short links — `youtube_embed_url()` in `app.py` now handles both that and `youtube.com/watch?v=ID`, so either format works as-is. Normalize to `https://www.youtube.com/watch?v=ID` when writing to `modules.json` for consistency (strip `?si=`/playlist/index tracking params).
- If a section's answer key is missing (happened for Module 1's first section), infer likely answers from the lesson text but **confirm with the user before finalizing** — don't guess silently on quiz content that gates certification.
- Section title vs. content mismatches happen (Module 1's "Bolt Testing" section was actually about reading a tape measure) — flag and confirm rather than transcribing blindly.
- `video_label` per section (e.g. "BASIC SAFETY TRAINING VIDEO"), `brief_label` standardized to `"SAFETY BRIEF"` across all sections.

---

## Session Log

### 2026-09-02 (Session 5) — Module 1 Real Content + youtu.be Embed Fix

**What changed:**
- `content/modules.json` — replaced Module 1's placeholder "Pinch Point Safety" section with 3 real sections transcribed from `Modules/Module 1 - Test Script.docx`: Basic Safety Training (5 quiz questions), Intro to Fabrication Drawings | The Basics (4 questions), Reading a Tape Measure (1 question, retitled from "Bolt Testing" in the script to match its actual content)
- `app.py` — `youtube_embed_url()` now handles `youtu.be/ID` short links in addition to `youtube.com/watch?v=ID` (two of the three script videos were short links, which previously embedded blank)

**Decisions made:**
- Basic Safety Training's answer key was missing from the script — inferred from the lesson text (1-A, 2-C, 3-C, 4-C, 5-C) and confirmed with the user before writing it in, rather than guessing silently on a compliance quiz
- This script's format is confirmed as the template for Modules 2-4 too — see "Module Script Docs" above for the processing checklist

**Verification:** ran the full module end-to-end via the Flask test client — all 3 videos embed with valid IDs, all 10 quiz questions grade correctly, a wrong answer still blocks progress, and the module reaches `complete` only after all sections pass.

### 2026-09-02 (Session 4) — Real Header Logo

**What changed:**
- `templates/base.html` / `static/css/style.css` — replaced the CSS-built text logo (`.logo-the`/`.logo-main`/`.logo-sub`) with the official logo image (`static/assets/Project Marshall Logo.png`); header grew from 72px → 110px and the logo renders at 90px tall so the full stacked lockup (including the "A Hammer Haag Initiative" tagline) has room to read clearly
- Railway Volume (`web-volume`, mounted at `/data`) attached to the `web` service with `DATABASE_PATH=/data/progress.db` set, so the Session 3 resume feature now survives redeploys in production

### 2026-09-02 (Session 3) — Cross-Device Resume

**What changed:**
- New `db.py` — stdlib `sqlite3` persistence layer, one `progress` row per `(email, module_id)`, storing step/section/cert progress alongside the session
- `templates/welcome.html` — re-added the Email field (removed in Session 1's `32dfa99`), now required alongside first/last name; added red-asterisk required markers and a grey helper note explaining email is used to resume progress later
- `app.py` — `welcome_start` now requires + normalizes email; `start_module` looks up existing progress before resetting (resumes in-progress or completed modules instead of always restarting); added `sync_progress()` write-through called from `step`, `submit_quiz`, `restudy`, and `complete`; new `GET /module/<id>/reset` route to explicitly clear progress and start over
- `templates/module_select.html` — softened the "cannot be resumed later / two uninterrupted hours" copy to reflect that progress now saves automatically; added "In Progress" / "Completed" badges and a "Start Over" link per module card, driven by `progress_by_module` passed from the `modules` route
- `static/css/style.css` — `.required-mark`, `.form-hint`, `.module-progress-badge` (+ `.in-progress`/`.completed` variants), `.module-card-footer a` link styling

**Decisions made:**
- Reversed the Session 1 "session-only, no database" decision — SQLite was the lightest option that still supports cross-device resume, since a cookie alone can't do that
- Identity for resume = normalized email (not a separate resume code) — reuses a field students already recognize, at the cost of trusting self-reported email the same way names were already trusted
- Kept the "sit down with enough time" framing in `module_select.html` rather than removing it entirely — resume is a safety net for interruptions, not an invitation to split training across days

**Known gap:** Railway's filesystem is ephemeral — `progress.db` needs a Railway Volume + `DATABASE_PATH` env var (see Railway Deployment section) or progress will be lost on every redeploy. Not yet done as of this session.

### 2026-09-01 (Session 2) — Certificate Redesign

**What changed:**
- `certificate.py` fully rewritten — replaced ReportLab-drawn layout with PNG template background (`MP Cert Template.png`) + text overlays
- Cert number format changed to `M{n}_{initials}_{MMDDYY}_01`
- `app.py` updated to pass `module_title` (not `module_id`) to the certificate generator
- Text positions dialed in iteratively; name in blue, module/date/cert number in black

### 2026-09-01 — Initial Build

**What was built:**
- Full project structure created at `HH Marshall Project - 2026/`
- Flask app with all routes: module select, welcome, lesson, quiz, restudy, complete, certificate download
- Content-driven architecture: all course content in `modules.json`
- Module 1 wired up with one section (Pinch Point Safety) and one quiz question
- Modules 2–4 are stubs (show in grid, no content yet)
- CSS design system matching mockups (Barlow Condensed font, blue/white/gray palette)
- YouTube embed support (nocookie domain, start time preserved)
- Quiz gating: NEXT disabled until answered, stays disabled on failure
- Failure banner + "START SECTION OVER" flow
- ReportLab PDF certificate with name, module, date, cert number
- HANDOFF.md created

**Decisions made:**
- Session-only (no database) for now — cert numbers are not persisted
- Cert number format: `TMP-M{module_id}-{YYYYMMDD}-{initials}-001`
- Separate git repo from the PDF engine project
- YouTube embed via `youtube-nocookie.com`

**Instructions given:**
- Videos embedded from YouTube
- Sample video: `https://www.youtube.com/watch?v=nzK2bL_Kkok&t=10s`
- Must pass 100% to advance; failure requires restudying section
- Certificate should auto-fill name, date, cert number
- Should be easily updatable via JSON
- Handoff doc must be updated each session
