(function () {
  'use strict';

  // ── Read aloud ────────────────────────────────────────────
  // Browser built-in voice (Web Speech API) — no audio files, so edits to
  // modules.json are picked up automatically. Browsers (Safari especially)
  // may refuse to start speech before the user has clicked on the page;
  // if that happens, the first click/tap/keypress anywhere retries it, and
  // the speaker buttons always work since they're a click themselves.

  const READ_DELAY_MS = 1000;

  const ReadAloud = (function () {
    const synth = window.speechSynthesis;
    const supported = !!(synth && window.SpeechSynthesisUtterance);
    let voice = null;
    let token = 0;            // bumps on every speak/cancel so stale callbacks are ignored
    let activeEl = null;      // element showing the .speaking pulse
    let pendingRetry = null;  // speak() args to replay on first user gesture if blocked

    function pickVoice() {
      const voices = synth.getVoices();
      voice =
        voices.find(function (v) { return v.default && /^en/i.test(v.lang); }) ||
        voices.find(function (v) { return /^en[-_]US/i.test(v.lang); }) ||
        voices.find(function (v) { return /^en/i.test(v.lang); }) ||
        null;
    }

    if (supported) {
      pickVoice();
      // Safari/Chrome load the voice list asynchronously
      synth.addEventListener && synth.addEventListener('voiceschanged', pickVoice);
      window.addEventListener('pagehide', function () { cancel(); });
    }

    function setActive(el) {
      if (activeEl) activeEl.classList.remove('speaking');
      activeEl = el || null;
      if (activeEl) activeEl.classList.add('speaking');
    }

    function cancel() {
      if (!supported) return;
      token++;
      pendingRetry = null;
      synth.cancel();
      setActive(null);
    }

    function armRetry(parts, el) {
      pendingRetry = [parts, el];
      function retry(e) {
        document.removeEventListener('pointerdown', retry, true);
        document.removeEventListener('keydown', retry, true);
        // Clicks on answers / speaker buttons / checkboxes start their own speech
        if (e && e.target && e.target.closest &&
            e.target.closest('.quiz-option, .read-aloud-btn, .practical-confirm')) {
          pendingRetry = null;
          return;
        }
        if (pendingRetry) {
          const args = pendingRetry;
          pendingRetry = null;
          speak(args[0], args[1]);
        }
      }
      document.addEventListener('pointerdown', retry, true);
      document.addEventListener('keydown', retry, true);
    }

    // parts: array of strings, each spoken as its own utterance (natural pauses)
    // el:    element to pulse while speaking
    function speak(parts, el) {
      if (!supported || !parts.length) return;
      cancel();
      const myToken = token;
      let blocked = false;

      parts.forEach(function (text, i) {
        const u = new SpeechSynthesisUtterance(text);
        if (voice) u.voice = voice;
        u.lang = voice ? voice.lang : 'en-US';
        u.rate = 0.95;
        if (i === 0) {
          u.onstart = function () { if (token === myToken) setActive(el); };
        }
        if (i === parts.length - 1) {
          u.onend = function () { if (token === myToken) setActive(null); };
        }
        u.onerror = function (e) {
          if (token !== myToken) return;
          setActive(null);
          if (e.error === 'not-allowed' && !blocked) {
            blocked = true;
            armRetry(parts, el);
          }
        };
        synth.speak(u);
      });

      // Some browsers silently drop speech instead of raising not-allowed
      setTimeout(function () {
        if (token === myToken && !blocked && !synth.speaking && !synth.pending) {
          blocked = true;
          armRetry(parts, el);
        }
      }, 300);
    }

    return { supported: supported, speak: speak, cancel: cancel };
  })();

  if (!ReadAloud.supported) {
    document.querySelectorAll('.read-aloud-btn').forEach(function (b) {
      b.style.display = 'none';
    });
  }

  function textOf(root, selector) {
    const el = root.querySelector(selector);
    return el ? el.textContent.trim() : '';
  }

  // ── Quiz answer selection ─────────────────────────────────
  // Instant green/red feedback on selection.
  // Correct answer → NEXT enables.
  // Wrong answer → option turns red, failure banner appears,
  //   PREVIOUS swaps to REVIEW & RETRY, entire quiz locks.
  //   User must click REVIEW & RETRY to restudy before retrying.

  const quizForm    = document.getElementById('quiz-form');
  const nextBtn     = document.getElementById('nav-next');
  const banner      = document.getElementById('failure-banner');
  const prevWrap    = document.getElementById('nav-previous-wrap');
  const restudyWrap = document.getElementById('nav-restudy-wrap');

  if (quizForm) {
    const questionLists = quizForm.querySelectorAll('.quiz-options');
    const questionEls   = Array.from(quizForm.querySelectorAll('.quiz-q'));

    // "Question 1 of 2. <text>" then "A: <option>" per option
    function questionScript(qEl) {
      const n = parseInt(qEl.getAttribute('data-q'), 10) + 1;
      const total = qEl.getAttribute('data-total');
      const parts = ['Question ' + n + ' of ' + total + '. ' + textOf(qEl, '.quiz-question')];
      qEl.querySelectorAll('.quiz-option').forEach(function (label) {
        const letter = textOf(label, '.option-letter').replace(/\.$/, '');
        parts.push(letter + ': ' + textOf(label, '.option-text'));
      });
      return parts;
    }

    function readQuestion(qEl) {
      if (qEl) ReadAloud.speak(questionScript(qEl), qEl);
    }

    function nextUnanswered() {
      return questionEls.find(function (qEl) {
        return !qEl.querySelector('input[type="radio"]:checked');
      });
    }

    questionEls.forEach(function (qEl) {
      const btn = qEl.querySelector('.read-aloud-btn');
      if (btn) btn.addEventListener('click', function () { readQuestion(qEl); });
    });

    setTimeout(function () { readQuestion(nextUnanswered()); }, READ_DELAY_MS);

    questionLists.forEach(function (ul) {
      const correctIdx = parseInt(ul.getAttribute('data-correct'), 10);
      const labels = ul.querySelectorAll('.quiz-option');

      labels.forEach(function (label) {
        label.addEventListener('click', function () {
          const radio = label.querySelector('input[type="radio"]');
          const selectedIdx = parseInt(radio.value, 10);

          radio.checked = true;
          ReadAloud.cancel();

          if (selectedIdx === correctIdx) {
            label.classList.add('correct');
            maybeEnableNext();
            readQuestion(nextUnanswered());
          } else {
            label.classList.add('incorrect');
            lockQuiz();
          }
        });
      });
    });

    function allCorrect() {
      return Array.from(questionLists).every(function (ul) {
        const correctIdx = parseInt(ul.getAttribute('data-correct'), 10);
        const checked = ul.querySelector('input[type="radio"]:checked');
        return checked && parseInt(checked.value, 10) === correctIdx;
      });
    }

    function lockQuiz() {
      // Disable all option clicks so user cannot change their answer
      quizForm.querySelectorAll('.quiz-option').forEach(function (l) {
        l.style.pointerEvents = 'none';
        l.style.cursor = 'default';
      });
      // Show failure banner
      if (banner) banner.style.display = '';
      // Swap PREVIOUS → REVIEW & RETRY
      if (prevWrap)    prevWrap.style.display    = 'none';
      if (restudyWrap) restudyWrap.style.display = '';

      // NEXT never becomes submittable once a wrong answer is picked, so the
      // server never sees this failure unless we tell it separately here.
      // sendBeacon (not fetch) because the student may click REVIEW & RETRY
      // and navigate away before an ordinary request would finish.
      if (navigator.sendBeacon) {
        navigator.sendBeacon(quizForm.action, new FormData(quizForm));
      }
    }

    function maybeEnableNext() {
      if (!nextBtn) return;
      if (allCorrect()) {
        nextBtn.classList.remove('inactive');
        nextBtn.classList.add('active');
        nextBtn.setAttribute('type', 'submit');
      }
    }

    // Belt-and-suspenders: block submission if not all correct
    if (nextBtn) {
      nextBtn.addEventListener('click', function (e) {
        if (!allCorrect()) {
          e.preventDefault();
          e.stopPropagation();
        }
      });
    }
  }

  // ── Practical exercise ────────────────────────────────────
  // Read the exercise + instructor instruction aloud; NEXT unlocks only
  // once the student confirms they did it with their instructor.

  const practicalForm = document.getElementById('practical-form');

  if (practicalForm) {
    const confirmBox = document.getElementById('practical-confirmed');
    const practicalNext = document.getElementById('practical-next');

    function readPractical() {
      ReadAloud.speak([
        'Practical exercise.',
        textOf(practicalForm, '.practical-text'),
        textOf(practicalForm, '.practical-instructor-text'),
      ], practicalForm);
    }

    const btn = practicalForm.querySelector('.read-aloud-btn');
    if (btn) btn.addEventListener('click', readPractical);
    setTimeout(readPractical, READ_DELAY_MS);

    function syncNext() {
      practicalNext.classList.toggle('active', confirmBox.checked);
      practicalNext.classList.toggle('inactive', !confirmBox.checked);
    }
    confirmBox.addEventListener('change', syncNext);
    syncNext();

    // Belt-and-suspenders: block submission if not confirmed
    practicalForm.addEventListener('submit', function (e) {
      if (!confirmBox.checked) e.preventDefault();
    });
  }

})();
