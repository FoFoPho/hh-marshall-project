"""Print the voice-over script for a module: every clip file name and exactly
what it should say, in English and Spanish, generated from modules.json and
ui_strings.json so the recordings always match the on-screen text.

    python3 tools/voiceover_scripts.py 7 > "Modules/Audio/Module 7 - Voice-Over Scripts.md"

Re-run after any wording change (e.g. Spanish corrections) — any clip whose
text changed needs re-recording. Finished clips go in
static/audio/m<module>/ under the file names listed (see app.py audio_url()).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LETTERS = 'ABCDE'
LANG_NAMES = {'en': 'English', 'es': 'Spanish'}
PRACTICAL_INTRO = {'en': 'Practical exercise.', 'es': 'Ejercicio práctico.'}
# AI voice-over pause tag: between every line, plus one at the end so the
# clip doesn't cut off abruptly.
PAUSE = '[pause 0.5s]'


def load(name):
    with open(os.path.join(ROOT, 'content', name), encoding='utf-8') as f:
        return json.load(f)


def field(obj, key, lang):
    return obj.get(f'{key}_es', obj[key]) if lang == 'es' else obj[key]


def clips_for(module, ui):
    """Yield (filename, lang, label, lines) for every clip in the module."""
    for s_num, section in enumerate(module.get('sections', []), start=1):
        for lang in ('en', 'es'):
            for q_num, q in enumerate(section['quiz']['questions'], start=1):
                lines = [field(q, 'text', lang)]
                lines += [f'{LETTERS[i]}. {opt}' for i, opt in enumerate(field(q, 'options', lang))]
                yield (f's{s_num}-q{q_num}-{lang}.mp3', lang,
                       f'{field(section, "title", lang)} — Question {q_num}', lines)
            if section.get('practical'):
                lines = [PRACTICAL_INTRO[lang],
                         field(section['practical'], 'text', lang),
                         ui['practical_instructor'][lang]]
                yield (f's{s_num}-practical-{lang}.mp3', lang,
                       f'{field(section, "title", lang)} — Practical Exercise', lines)


def main():
    module_id = int(sys.argv[1])
    module = next(m for m in load('modules.json')['modules'] if m['id'] == module_id)
    ui = load('ui_strings.json')
    clips = list(clips_for(module, ui))

    print(f'# {module["title"]} — Voice-Over Scripts\n')
    print(f'{len(clips)} clips. Record each one exactly as written, then save it '
          f'with the file name shown (MP3 preferred; M4A or WAV also work).\n')
    print(f'Each script is ready to paste into the AI voice generator as-is, '
          f'including the {PAUSE} tags.\n')
    for lang in ('en', 'es'):
        print(f'\n## {LANG_NAMES[lang]}\n')
        for filename, clip_lang, label, lines in clips:
            if clip_lang != lang:
                continue
            print(f'### `{filename}`\n*{label}*\n')
            print(f'  {PAUSE}  '.join(lines) + f'  {PAUSE}\n')


if __name__ == '__main__':
    main()
