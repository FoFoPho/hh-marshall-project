(function () {
  'use strict';

  // ── Quiz answer selection ─────────────────────────────────
  // Instant green/red feedback on selection.
  // Wrong answer → shows failure banner + START SECTION OVER button.
  // NEXT only enables when every question has the correct answer chosen.

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

          // Clear state on all options in this question
          labels.forEach(function (l) {
            l.classList.remove('correct', 'incorrect', 'selected');
          });

          // Mark correct or incorrect
          radio.checked = true;
          label.classList.add(selectedIdx === correctIdx ? 'correct' : 'incorrect');

          // Update banner + nav buttons based on whether any wrong answer exists
          setWrongState(hasAnyWrong());
          maybeEnableNext();
        });
      });
    });

    function hasAnyWrong() {
      return Array.from(questionLists).some(function (ul) {
        const correctIdx = parseInt(ul.getAttribute('data-correct'), 10);
        const checked = ul.querySelector('input[type="radio"]:checked');
        return checked && parseInt(checked.value, 10) !== correctIdx;
      });
    }

    function allCorrect() {
      return Array.from(questionLists).every(function (ul) {
        const correctIdx = parseInt(ul.getAttribute('data-correct'), 10);
        const checked = ul.querySelector('input[type="radio"]:checked');
        return checked && parseInt(checked.value, 10) === correctIdx;
      });
    }

    function setWrongState(wrong) {
      if (banner)      wrong ? banner.removeAttribute('hidden')      : banner.setAttribute('hidden', '');
      if (prevWrap)    wrong ? prevWrap.setAttribute('hidden', '')    : prevWrap.removeAttribute('hidden');
      if (restudyWrap) wrong ? restudyWrap.removeAttribute('hidden') : restudyWrap.setAttribute('hidden', '');
    }

    function maybeEnableNext() {
      if (!nextBtn) return;
      if (allCorrect()) {
        nextBtn.classList.remove('inactive');
        nextBtn.classList.add('active');
        nextBtn.setAttribute('type', 'submit');
      } else {
        nextBtn.classList.remove('active');
        nextBtn.classList.add('inactive');
        nextBtn.setAttribute('type', 'button');
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
