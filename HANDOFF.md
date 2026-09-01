# The Marshall Project — Handoff Document

This document is updated every session. Check the date at the top to confirm you have the latest version before starting work.

**Last updated:** 2026-09-01 (Session 2)  
**Last session:** Certificate PDF redesign

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
| Session     | Flask signed cookies (no database) |

---

## File Structure

```
HH Marshall Project - 2026/
├── app.py              # All Flask routes and logic
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

## Railway Deployment

1. Push repo to GitHub
2. New project on Railway → connect GitHub repo
3. Set environment variable: `SECRET_KEY` = any long random string
4. Railway auto-detects Python + runs `gunicorn app:app` from Procfile
5. No database needed — all state is session-based

**Railway URL:** (not yet deployed)

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

- [ ] Fill in Modules 2, 3, and 4 content in `modules.json`
- [ ] Add real Marshall Project logo image to the web UI header (currently text-based)
- [ ] Deploy to Railway and record URL here
- [ ] Consider adding a logo bar / splash screen

---

## Session Log

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
