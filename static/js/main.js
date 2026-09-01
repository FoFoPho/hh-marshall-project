(function () {
  'use strict';

  // ── Quiz answer selection ─────────────────────────────────
  // Highlight the selected option row and enable the NEXT button
  // when an answer is chosen (only runs on quiz pages).

  const quizForm   = document.getElementById('quiz-form');
  const nextBtn    = document.getElementById('nav-next');

  if (quizForm) {
    const options = quizForm.querySelectorAll('.quiz-option');

    options.forEach(function (label) {
      label.addEventListener('click', function () {
        // Clear all selections within the same question group
        const name = label.querySelector('input[type="radio"]').name;
        quizForm.querySelectorAll(`input[name="${name}"]`).forEach(function (radio) {
          radio.closest('.quiz-option').classList.remove('selected');
        });

        // Mark this one selected
        label.classList.add('selected');
        label.querySelector('input[type="radio"]').checked = true;

        // Enable NEXT if all questions have an answer selected
        maybeEnableNext();
      });
    });

    function allAnswered() {
      const groups = {};
      quizForm.querySelectorAll('input[type="radio"]').forEach(function (r) {
        if (!groups[r.name]) groups[r.name] = false;
        if (r.checked) groups[r.name] = true;
      });
      return Object.values(groups).every(Boolean);
    }

    function maybeEnableNext() {
      if (!nextBtn) return;
      if (allAnswered()) {
        nextBtn.classList.remove('inactive');
        nextBtn.classList.add('active');
        nextBtn.setAttribute('type', 'submit');
      }
    }

    // Prevent NEXT from submitting if no answer chosen (belt + suspenders)
    if (nextBtn) {
      nextBtn.addEventListener('click', function (e) {
        if (!allAnswered()) {
          e.preventDefault();
          e.stopPropagation();
        }
      });
    }
  }

  // ── Welcome form NEXT guard ───────────────────────────────
  // The NEXT button on the welcome page submits the form.
  // It's always enabled (server validates), so nothing extra needed.

})();
