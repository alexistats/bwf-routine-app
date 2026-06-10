// Shared front-end behaviour. Each block guards on its root element so this
// file can load safely on every page.

document.addEventListener('DOMContentLoaded', function() {

    // ── Rest Timer ──────────────────────────────────────────────
    const timerSection = document.querySelector('.timer-section');
    if (timerSection) {
        const timerDisplay = timerSection.querySelector('.timer-display');
        const startBtn = document.getElementById('timer-start');
        const resetBtn = document.getElementById('timer-reset');
        const defaultTime = parseInt(timerSection.dataset.restPeriod, 10) || 90;

        let countdown;
        let timeLeft = defaultTime;
        let isRunning = false;

        function updateTimerDisplay() {
            const m = Math.floor(timeLeft / 60);
            const s = timeLeft % 60;
            timerDisplay.textContent = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
        }

        function startTimer() {
            if (isRunning) return;
            isRunning = true;
            startBtn.textContent = 'Pause';
            countdown = setInterval(() => {
                timeLeft--;
                updateTimerDisplay();
                if (timeLeft <= 0) {
                    clearInterval(countdown);
                    timerDisplay.textContent = 'DONE!';
                    startBtn.textContent = 'Start';
                    isRunning = false;
                    if ('vibrate' in navigator) navigator.vibrate([200, 100, 200]);
                }
            }, 1000);
        }

        startBtn.addEventListener('click', function() {
            if (isRunning) {
                clearInterval(countdown);
                isRunning = false;
                startBtn.textContent = 'Resume';
            } else {
                startTimer();
            }
        });

        resetBtn.addEventListener('click', function() {
            clearInterval(countdown);
            isRunning = false;
            startBtn.textContent = 'Start';
            timeLeft = defaultTime;
            updateTimerDisplay();
        });

        [['timer-60', 60], ['timer-90', 90], ['timer-120', 120]].forEach(function([id, secs]) {
            const btn = document.getElementById(id);
            if (btn) btn.addEventListener('click', () => { timeLeft = secs; updateTimerDisplay(); });
        });

        updateTimerDisplay();
    }

    // ── BWF dynamic rep inputs ───────────────────────────────────
    window.updateRepInputs = function(sets) {
        const container = document.getElementById('rep-inputs');
        if (!container) return;
        const defaultReps = container.dataset.defaultReps || '5';
        container.innerHTML = '';
        for (let i = 1; i <= sets; i++) {
            container.innerHTML += `
                <div class="form-group">
                    <label for="reps_set_${i}">Reps (Set ${i})</label>
                    <input type="number" id="reps_set_${i}" name="reps_set_${i}" min="1" max="20" value="${defaultReps}">
                </div>`;
        }
    };

    // ── Gym kg/lbs unit toggle ───────────────────────────────────
    const unitInput = document.getElementById('weight-unit-input');
    if (!unitInput) return; // not a weighted gym exercise page

    const LBS_PER_KG = 2.20462;
    let currentUnit = localStorage.getItem('weightUnit') || 'lbs';

    function convertWeight(value, from, to) {
        if (from === to) return value;
        return from === 'lbs' ? value / LBS_PER_KG : value * LBS_PER_KG;
    }

    function roundWeight(value) {
        return Math.round(value * 2) / 2; // nearest 0.5
    }

    window.setUnit = function(unit) {
        if (unit === currentUnit) return;

        document.querySelectorAll('.weight-input').forEach(function(input) {
            const v = parseFloat(input.value);
            if (!isNaN(v) && v > 0) {
                input.value = roundWeight(convertWeight(v, currentUnit, unit));
            }
        });

        currentUnit = unit;
        localStorage.setItem('weightUnit', currentUnit);
        applyUnitUI();
    };

    function applyUnitUI() {
        unitInput.value = currentUnit;

        document.querySelectorAll('.unit-display').forEach(el => el.textContent = currentUnit);

        const btnLbs = document.getElementById('btn-lbs');
        const btnKg = document.getElementById('btn-kg');
        if (btnLbs) btnLbs.classList.toggle('active', currentUnit === 'lbs');
        if (btnKg) btnKg.classList.toggle('active', currentUnit === 'kg');

        document.querySelectorAll('.last-set-badge').forEach(function(badge) {
            const storedUnit = badge.dataset.storedUnit || 'lbs';
            const weightDisplay = badge.querySelector('.last-weight-display');
            const unitLabel = badge.querySelector('.last-unit-label');
            if (!weightDisplay || !unitLabel) return;
            const rawValue = parseFloat(badge.dataset.lbsValue);
            if (isNaN(rawValue)) return;
            weightDisplay.textContent = roundWeight(convertWeight(rawValue, storedUnit, currentUnit));
            unitLabel.textContent = currentUnit;
        });
    }

    // Convert pre-filled weights to the saved unit preference on load
    document.querySelectorAll('.weight-input').forEach(function(input) {
        const storedValue = parseFloat(input.dataset.storedValue);
        const storedUnit = input.dataset.storedUnit || 'lbs';
        if (!isNaN(storedValue) && storedValue > 0) {
            input.value = roundWeight(convertWeight(storedValue, storedUnit, currentUnit));
        }
    });

    applyUnitUI();
});
