(function () {
  'use strict';

  // ── Quiz answer selection ─────────────────────────────────
  // Instant green/red feedback on selection.
  // NEXT only enables when every question has the correct answer chosen.

  const quizForm = document.getElementById('quiz-form');
  const nextBtn  = document.getElementById('nav-next');

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

          // Mark selected and apply correct/incorrect
          radio.checked = true;
          if (selectedIdx === correctIdx) {
            label.classList.add('correct');
          } else {
            label.classList.add('incorrect');
          }

          maybeEnableNext();
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
