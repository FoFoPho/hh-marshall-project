(function () {
  'use strict';

  // ── Voice-over clips ──────────────────────────────────────
  // Recorded clips (static/audio/…, found by filename convention in app.py)
  // are passed in as data-audio URLs; no clip → no audio. Browsers (Safari
  // especially) may refuse to play sound before the user has clicked on the
  // page; if that happens, the speaker button pulses and the first
  // click/tap/keypress anywhere starts the clip.

  const READ_DELAY_MS = 1000;

  const Narration = (function () {
    const audio = new Audio();
    audio.preload = 'auto';
    let activeEl = null;      // element showing the .speaking pulse
    let pendingRetry = null;  // [src, el] to replay on first user gesture if blocked

    function setActive(el) {
      if (activeEl) activeEl.classList.remove('speaking');
      activeEl = el || null;
      if (activeEl) activeEl.classList.add('speaking');
    }

    function clearBlocked() {
      document.querySelectorAll('.audio-blocked').forEach(function (el) {
        el.classList.remove('audio-blocked');
      });
    }

    audio.addEventListener('ended', function () { setActive(null); });
    window.addEventListener('pagehide', function () { stop(); });

    function stop() {
      pendingRetry = null;
      audio.pause();
      setActive(null);
    }

    function armRetry(src, el) {
      pendingRetry = [src, el];
      if (el) el.classList.add('audio-blocked');
      function retry(e) {
        document.removeEventListener('pointerdown', retry, true);
        document.removeEventListener('keydown', retry, true);
        clearBlocked();
        // Clicks on answers / speaker buttons / checkboxes start their own audio
        if (e && e.target && e.target.closest &&
            e.target.closest('.quiz-option, .read-aloud-btn, .practical-confirm')) {
          pendingRetry = null;
          return;
        }
        if (pendingRetry) {
          const args = pendingRetry;
          pendingRetry = null;
          play(args[0], args[1]);
        }
      }
      document.addEventListener('pointerdown', retry, true);
      document.addEventListener('keydown', retry, true);
    }

    function play(src, el) {
      if (!src) return;
      stop();
      clearBlocked();
      audio.src = src;
      setActive(el);
      const p = audio.play();
      if (p && p.catch) {
        p.catch(function (err) {
          if (audio.src.indexOf(src) === -1) return;   // superseded by a newer clip
          setActive(null);
          if (err && err.name === 'NotAllowedError') armRetry(src, el);
        });
      }
    }

    return { play: play, stop: stop };
  })();

  // ── Video autoplay ────────────────────────────────────────
  // Embeds carry autoplay=1, but browsers (Safari especially) block
  // autoplay *with sound* until the user has clicked on the page. If the
  // video hasn't started shortly after loading, fall back to muted
  // autoplay (always allowed) and show a "Tap for sound" button.

  const AUTOPLAY_CHECK_MS = 1500;
  const videoFrames = document.querySelectorAll('iframe.video-embed');

  if (videoFrames.length) {
    const prevReady = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = function () {
      if (prevReady) prevReady();
      videoFrames.forEach(setupAutoplay);
    };
    const tag = document.createElement('script');
    tag.src = 'https://www.youtube.com/iframe_api';
    document.head.appendChild(tag);
  }

  function setupAutoplay(iframe) {
    const wrapper  = iframe.closest('.video-wrapper');
    const soundBtn = wrapper && wrapper.querySelector('.video-sound-btn');
    let mutedPoll = null;

    const player = new YT.Player(iframe, {
      events: {
        onReady: function () {
          player.playVideo();
          setTimeout(function () {
            const state = player.getPlayerState();
            if (state === YT.PlayerState.PLAYING || state === YT.PlayerState.BUFFERING) {
              if (player.isMuted()) showSoundBtn();   // browser auto-muted it
              return;
            }
            player.mute();
            player.playVideo();
            showSoundBtn();
          }, AUTOPLAY_CHECK_MS);
        },
      },
    });

    function hideSoundBtn() {
      if (soundBtn) soundBtn.hidden = true;
      if (mutedPoll) { clearInterval(mutedPoll); mutedPoll = null; }
    }

    function showSoundBtn() {
      if (!soundBtn) return;
      soundBtn.hidden = false;
      // Hide it again if they unmute with YouTube's own controls instead
      mutedPoll = setInterval(function () {
        if (!player.isMuted()) hideSoundBtn();
      }, 1000);
    }

    if (soundBtn) {
      soundBtn.addEventListener('click', function () {
        player.unMute();
        player.setVolume(100);
        if (player.getPlayerState() !== YT.PlayerState.PLAYING) player.playVideo();
        hideSoundBtn();
      });
    }
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

    function readQuestion(qEl) {
      if (qEl) Narration.play(qEl.getAttribute('data-audio'), qEl);
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
          Narration.stop();

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
      Narration.play(practicalForm.getAttribute('data-audio'), practicalForm);
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
