(function () {
  'use strict';

  // ── Quiz answer selection ─────────────────────────────────
  // Instant green/red feedback on selection.
  // Correct answer → NEXT enables.
  // Wrong answer → option turns red, failure banner appears,
  //   PREVIOUS swaps to START SECTION OVER, entire quiz locks.
  //   User must click START SECTION OVER to restudy before retrying.

  const quizForm    = document.getElementById('quiz-form');
  const nextBtn     = document.getElementById('nav-next');
  const banner      = document.getElementById('failure-banner');
  const prevWrap    = document.getElementById('nav-previous-wrap');
  const restudyWrap = document.getElementById('nav-restudy-wrap');

  if (quizForm) {
    const questionLists = quizForm.querySelectorAll('.quiz-options');

    questionLists.forEach(function (ul) {
      const correctIdx = parseInt(ul.getAttribute('data-correct'), 10);
      const labels = ul.querySelectorAll('.quiz-option');

      labels.forEach(function (label) {
        label.addEventListener('click', function () {
          const radio = label.querySelector('input[type="radio"]');
          const selectedIdx = parseInt(radio.value, 10);

          radio.checked = true;

          if (selectedIdx === correctIdx) {
            label.classList.add('correct');
            maybeEnableNext();
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
      // Swap PREVIOUS → START SECTION OVER
      if (prevWrap)    prevWrap.style.display    = 'none';
      if (restudyWrap) restudyWrap.style.display = '';
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

})();
