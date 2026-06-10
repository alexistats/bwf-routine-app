document.addEventListener('DOMContentLoaded', function () {
    'use strict';

    // ── Constants ──────────────────────────────────────────────────
    const LBS_PER_KG = 2.20462;

    // ── Unit state ─────────────────────────────────────────────────
    let currentUnit = localStorage.getItem('weightUnit') || 'lbs';

    // ── Timer state ────────────────────────────────────────────────
    let timerSeconds = 0;
    let timerInterval = null;
    let timerRunning = false;
    let timerRestPeriod = 90;

    // ── Card accordion ─────────────────────────────────────────────
    let openCardId = null;

    document.addEventListener('click', function (e) {
        const header = e.target.closest('.exercise-card-header');
        if (!header) return;
        if (header.dataset.card) {
            toggleCard(header.dataset.card);
        } else if (header.dataset.href) {
            window.location.href = header.dataset.href;
        }
    });

    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        const header = e.target.closest('.exercise-card-header');
        if (!header) return;
        e.preventDefault();
        if (header.dataset.card) {
            toggleCard(header.dataset.card);
        } else if (header.dataset.href) {
            window.location.href = header.dataset.href;
        }
    });

    function toggleCard(cardId) {
        const panel = document.getElementById('panel-' + cardId);
        if (!panel) return;

        if (openCardId && openCardId !== cardId) {
            collapseCard(openCardId);
        }

        if (!panel.hidden) {
            collapseCard(cardId);
        } else {
            expandCard(cardId);
        }
    }

    function expandCard(cardId) {
        const panel = document.getElementById('panel-' + cardId);
        if (!panel) return;
        panel.hidden = false;
        openCardId = cardId;
        setExpandIcon(cardId, true);
        syncUnitInPanel(panel);
    }

    function collapseCard(cardId) {
        const panel = document.getElementById('panel-' + cardId);
        if (panel) panel.hidden = true;
        if (openCardId === cardId) openCardId = null;
        setExpandIcon(cardId, false);
    }

    function setExpandIcon(cardId, isOpen) {
        const header = document.querySelector('.exercise-card-header[data-card="' + cardId + '"]');
        if (!header) return;
        const icon = header.querySelector('.expand-icon');
        if (icon) icon.classList.toggle('open', isOpen);
    }

    // ── AJAX form submit ───────────────────────────────────────────
    document.addEventListener('submit', function (e) {
        const form = e.target;
        if (!form.classList.contains('exercise-log-form')) return;
        e.preventDefault();

        const btn = form.querySelector('[type="submit"]');
        if (btn) btn.disabled = true;

        const errDiv = form.querySelector('.form-error');
        if (errDiv) errDiv.textContent = '';

        fetch(form.action, {
            method: 'POST',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            body: new FormData(form),
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (btn) btn.disabled = false;
                if (data.status === 'ok') {
                    const cardId = form.dataset.cardId;
                    markCardDone(cardId, data.sets_completed);
                    collapseCard(cardId);
                    startTimer(data.rest_period, data.exercise_name);
                    if (data.advanced && data.new_progression) {
                        showAdvancementBanner(data.new_progression);
                    }
                } else {
                    if (errDiv) errDiv.textContent = data.message || 'Error logging exercise.';
                }
            })
            .catch(function () {
                if (btn) btn.disabled = false;
                form.submit();
            });
    });

    function markCardDone(cardId, setsCompleted) {
        const header = document.querySelector('.exercise-card-header[data-card="' + cardId + '"]');
        if (!header) return;
        let badge = header.querySelector('.logged-badge');
        if (!badge) {
            badge = document.createElement('span');
            badge.className = 'logged-badge';
            header.appendChild(badge);
        }
        badge.textContent = '✓ ' + setsCompleted + (setsCompleted === 1 ? ' set' : ' sets');
    }

    function showAdvancementBanner(newProgression) {
        const banner = document.createElement('div');
        banner.className = 'advancement-banner';
        banner.textContent = 'Advanced to: ' + newProgression;
        const main = document.querySelector('main');
        if (main) main.insertAdjacentElement('afterbegin', banner);
        setTimeout(function () { banner.remove(); }, 5000);
    }

    // ── Timer ──────────────────────────────────────────────────────
    function startTimer(restPeriod, exerciseName) {
        timerRestPeriod = restPeriod || 90;
        timerSeconds = timerRestPeriod;
        clearInterval(timerInterval);
        timerRunning = true;

        const bar = document.getElementById('timer-bar');
        if (bar) bar.hidden = false;
        document.body.classList.add('timer-visible');

        const label = document.getElementById('timer-exercise');
        if (label) label.textContent = exerciseName || '';

        const toggleBtn = document.getElementById('timer-bar-toggle');
        if (toggleBtn) toggleBtn.textContent = '⏸';

        updateTimerDisplay();
        timerInterval = setInterval(timerTick, 1000);
    }

    function timerTick() {
        if (timerSeconds > 0) {
            timerSeconds--;
            updateTimerDisplay();
        } else {
            clearInterval(timerInterval);
            timerRunning = false;
            const disp = document.getElementById('timer-bar-display');
            if (disp) disp.textContent = 'REST ✓';
            const btn = document.getElementById('timer-bar-toggle');
            if (btn) btn.textContent = '▶';
            if (navigator.vibrate) navigator.vibrate([200, 100, 200]);
        }
    }

    function updateTimerDisplay() {
        const m = Math.floor(timerSeconds / 60);
        const s = timerSeconds % 60;
        const disp = document.getElementById('timer-bar-display');
        if (disp) disp.textContent = pad2(m) + ':' + pad2(s);
    }

    function pad2(n) { return String(n).padStart(2, '0'); }

    window.timerToggle = function () {
        if (timerRunning) {
            clearInterval(timerInterval);
            timerRunning = false;
            const btn = document.getElementById('timer-bar-toggle');
            if (btn) btn.textContent = '▶';
        } else {
            timerRunning = true;
            const btn = document.getElementById('timer-bar-toggle');
            if (btn) btn.textContent = '⏸';
            timerInterval = setInterval(timerTick, 1000);
        }
    };

    window.timerAdjust = function (delta) {
        timerSeconds = Math.max(0, timerSeconds + delta);
        updateTimerDisplay();
    };

    window.timerReset = function () {
        clearInterval(timerInterval);
        timerRunning = false;
        timerSeconds = timerRestPeriod;
        updateTimerDisplay();
        const btn = document.getElementById('timer-bar-toggle');
        if (btn) btn.textContent = '▶';
    };

    // ── Unit conversion ────────────────────────────────────────────
    function convertWeight(value, from, to) {
        if (from === to) return value;
        return from === 'lbs' ? value / LBS_PER_KG : value * LBS_PER_KG;
    }

    function roundWeight(v) { return Math.round(v * 2) / 2; }

    window.setUnit = function (unit) {
        if (unit === currentUnit) return;
        document.querySelectorAll('.weight-input').forEach(function (input) {
            const v = parseFloat(input.value);
            if (!isNaN(v) && v > 0) {
                input.value = roundWeight(convertWeight(v, currentUnit, unit));
            }
        });
        currentUnit = unit;
        localStorage.setItem('weightUnit', currentUnit);
        applyUnitUI(document);
    };

    function applyUnitUI(root) {
        root = root || document;
        root.querySelectorAll('.weight-unit-input').forEach(function (el) {
            el.value = currentUnit;
        });
        root.querySelectorAll('.unit-display').forEach(function (el) {
            el.textContent = currentUnit;
        });
        document.querySelectorAll('.unit-toggle-btn').forEach(function (btn) {
            btn.classList.toggle('active', btn.dataset.unit === currentUnit);
        });
        root.querySelectorAll('.last-set-badge').forEach(function (badge) {
            const weightDisplay = badge.querySelector('.last-weight-display');
            const unitLabel = badge.querySelector('.last-unit-label');
            if (!weightDisplay || !unitLabel) return;
            const rawValue = parseFloat(badge.dataset.lbsValue);
            const storedUnit = badge.dataset.storedUnit || 'lbs';
            if (isNaN(rawValue)) return;
            weightDisplay.textContent = roundWeight(convertWeight(rawValue, storedUnit, currentUnit));
            unitLabel.textContent = currentUnit;
        });
    }

    function syncUnitInPanel(panel) {
        panel.querySelectorAll('.weight-unit-input').forEach(function (el) {
            el.value = currentUnit;
        });
        panel.querySelectorAll('.unit-display').forEach(function (el) {
            el.textContent = currentUnit;
        });
    }

    // Convert pre-filled weight inputs from stored unit to current preference
    document.querySelectorAll('.weight-input').forEach(function (input) {
        const storedValue = parseFloat(input.dataset.storedValue);
        const storedUnit = input.dataset.storedUnit || 'lbs';
        if (!isNaN(storedValue) && storedValue > 0) {
            input.value = roundWeight(convertWeight(storedValue, storedUnit, currentUnit));
        }
    });

    applyUnitUI(document);
});
