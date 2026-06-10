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

    // ── Plate picker (barbell exercises) ───────────────────────────
    const PLATE_DENOMS = {
        lbs: [45, 35, 25, 10, 5, 2.5],
        kg: [20, 15, 10, 5, 2.5, 1.25],
    };
    const BAR_WEIGHT = { lbs: 45, kg: 20 };
    // Roughly the IPF colour convention, applied by size rank in both units
    const PLATE_COLORS = ['#c0392b', '#2962a8', '#f1c40f', '#27ae60', '#7f8c8d', '#bdc3c7'];

    function initPlatePickers() {
        document.querySelectorAll('.plate-picker').forEach(function (picker) {
            picker._plates = []; // weights loaded per side, in tap order
            renderPlateButtons(picker);
            renderBarbell(picker);
        });
    }

    function resetPlatePickers() {
        document.querySelectorAll('.plate-picker').forEach(function (picker) {
            picker._plates = [];
            renderPlateButtons(picker);
            renderBarbell(picker);
        });
    }

    function renderPlateButtons(picker) {
        const container = picker.querySelector('.plate-buttons');
        if (!container) return;
        container.innerHTML = '';
        PLATE_DENOMS[currentUnit].forEach(function (w, rank) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'plate-add-btn';
            btn.dataset.weight = w;
            btn.textContent = formatWeight(w);
            btn.style.borderColor = PLATE_COLORS[rank];
            container.appendChild(btn);
        });
    }

    function renderBarbell(picker) {
        const visual = picker.querySelector('.barbell-visual');
        if (!visual) return;
        visual.innerHTML = '';

        const plates = picker._plates;
        const denoms = PLATE_DENOMS[currentUnit];
        const maxW = denoms[0];
        // Heaviest plates sit closest to the centre of the bar
        const sorted = plates
            .map(function (w, i) { return { w: w, i: i }; })
            .sort(function (a, b) { return b.w - a.w; });

        function makePlate(entry) {
            const el = document.createElement('button');
            el.type = 'button';
            el.className = 'bv-plate';
            el.dataset.idx = entry.i;
            el.title = 'Remove ' + formatWeight(entry.w) + ' ' + currentUnit + ' pair';
            const ratio = entry.w / maxW;
            el.style.height = Math.round(26 + 44 * ratio) + 'px';
            el.style.width = Math.max(7, Math.round(14 * ratio)) + 'px';
            el.style.backgroundColor = PLATE_COLORS[denoms.indexOf(entry.w)] || '#7f8c8d';
            return el;
        }

        const left = document.createElement('div');
        left.className = 'bv-side bv-left';
        const right = document.createElement('div');
        right.className = 'bv-side bv-right';
        // Mirror: outermost (lightest) plate first on the left side
        sorted.slice().reverse().forEach(function (e) { left.appendChild(makePlate(e)); });
        sorted.forEach(function (e) { right.appendChild(makePlate(e)); });

        const bar = document.createElement('div');
        bar.className = 'bv-bar';

        visual.appendChild(left);
        visual.appendChild(bar);
        visual.appendChild(right);

        if (plates.length === 0) {
            const hint = document.createElement('div');
            hint.className = 'bv-hint';
            hint.textContent = 'Tap a plate below to load the bar — tap a loaded plate to remove it';
            visual.appendChild(hint);
        }

        const totalEl = picker.querySelector('.plate-total-value');
        if (totalEl) totalEl.textContent = formatWeight(plateTotal(picker));
    }

    function plateTotal(picker) {
        const perSide = picker._plates.reduce(function (sum, w) { return sum + w; }, 0);
        return BAR_WEIGHT[currentUnit] + 2 * perSide;
    }

    function formatWeight(w) {
        return (Math.round(w * 100) / 100).toString();
    }

    document.addEventListener('click', function (e) {
        const picker = e.target.closest('.plate-picker');
        if (!picker) return;

        const addBtn = e.target.closest('.plate-add-btn');
        if (addBtn) {
            picker._plates.push(parseFloat(addBtn.dataset.weight));
            renderBarbell(picker);
            return;
        }

        const plateEl = e.target.closest('.bv-plate');
        if (plateEl) {
            picker._plates.splice(parseInt(plateEl.dataset.idx, 10), 1);
            renderBarbell(picker);
            return;
        }

        const applyBtn = e.target.closest('.plate-apply-btn');
        if (applyBtn) {
            const panel = picker.closest('.exercise-panel');
            const input = panel && panel.querySelector('input[name="weight_set_' + applyBtn.dataset.set + '"]');
            if (input) {
                input.value = plateTotal(picker);
                applyBtn.classList.add('applied');
                setTimeout(function () { applyBtn.classList.remove('applied'); }, 600);
            }
            return;
        }

        if (e.target.closest('.plate-clear-btn')) {
            picker._plates = [];
            renderBarbell(picker);
        }
    });

    initPlatePickers();

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
        resetPlatePickers(); // plate denominations are physical — swap sets, don't convert
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
