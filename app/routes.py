from flask import (Blueprint, render_template, current_app, redirect, url_for,
                   request, flash, session, jsonify, get_flashed_messages)
from flask_login import login_required, current_user, login_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func
from app.models import (User, Workout, ExerciseLog, UserProgression,
                         CustomExercise, HiddenExercise, GeneratedProgram,
                         UserApiKey)
from app import db
from app import ai_generator
from datetime import datetime, timezone
import json

main = Blueprint('main', __name__)

MIN_PASSWORD_LENGTH = 8
MAX_GYM_SETS = 10
ALLOWED_EQUIPMENT = ('barbell', 'dumbbell', 'machine', 'bodyweight')

# What the generation form lets users tick — free-form context for the model,
# not the same thing as the per-exercise equipment enum above.
EQUIPMENT_CHOICES = (
    'full gym membership', 'barbell and plates', 'dumbbells', 'kettlebells',
    'pull-up bar', 'resistance bands', 'cardio machines', 'bodyweight only',
)
EXPERIENCE_LEVELS = ('beginner', 'intermediate', 'advanced')


def _is_ajax():
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def _routine_with_overlays(base, routine_key):
    """A routine with the user's removals and additions applied."""
    if not current_user.is_authenticated:
        return base

    hidden = {
        h.exercise_name
        for h in HiddenExercise.query.filter_by(
            user_id=current_user.id, routine_type=routine_key)
    }
    customs = CustomExercise.query.filter_by(
        user_id=current_user.id, routine_type=routine_key).all()

    routine = {
        section: [ex for ex in exercises if ex['name'] not in hidden]
        for section, exercises in base.items()
    }
    for custom in customs:
        routine.setdefault(custom.section, []).append(custom.to_dict())
    return routine


def _gym_routine_for_user():
    """Built-in gym routine with the user's removals and additions applied."""
    return _routine_with_overlays(current_app.config['GYM_ROUTINE_DATA'], 'gym')


def _ai_program_for_key(routine_key, include_draft=False):
    """Resolve an 'ai-<id>' routine key to the current user's program, or None."""
    if (not routine_key or not routine_key.startswith('ai-')
            or not current_user.is_authenticated):
        return None
    try:
        program_id = int(routine_key[3:])
    except ValueError:
        return None
    program = db.session.get(GeneratedProgram, program_id)
    if program is None or program.user_id != current_user.id:
        return None
    if program.is_draft and not include_draft:
        return None
    return program


def _valid_routine_key(routine_key):
    if routine_key in ('bwf', 'gym'):
        return True
    return _ai_program_for_key(routine_key) is not None


def _editable_base_routine(routine_key):
    """Base routine data for keys that support add/remove customization."""
    if routine_key == 'gym':
        return current_app.config['GYM_ROUTINE_DATA']
    program = _ai_program_for_key(routine_key)
    return program.routine_data() if program else None


def _default_routine_view():
    """Last routine the user interacted with, falling back to bwf."""
    if not current_user.is_authenticated:
        return 'bwf'
    view = session.get('current_routine_view')
    if view and _valid_routine_key(view):
        return view
    last_workout = (Workout.query.filter_by(user_id=current_user.id)
                    .order_by(Workout.id.desc()).first())
    if last_workout and _valid_routine_key(last_workout.routine_type):
        return last_workout.routine_type
    return 'bwf'


@main.route('/')
def home():
    routine = request.args.get('routine')
    if not routine or not _valid_routine_key(routine):
        routine = _default_routine_view()
    if current_user.is_authenticated:
        session['current_routine_view'] = routine

    hidden_count = 0
    ai_program = None
    if routine == 'bwf':
        routine_data = current_app.config['ROUTINE_DATA']
    else:
        if routine == 'gym':
            base = current_app.config['GYM_ROUTINE_DATA']
        else:
            ai_program = _ai_program_for_key(routine)
            base = ai_program.routine_data()
        routine_data = _routine_with_overlays(base, routine)
        if current_user.is_authenticated:
            hidden_count = HiddenExercise.query.filter_by(
                user_id=current_user.id, routine_type=routine).count()

    ai_programs = []
    if current_user.is_authenticated:
        ai_programs = (GeneratedProgram.query
                       .filter_by(user_id=current_user.id, is_draft=False)
                       .order_by(GeneratedProgram.created_at).all())

    last_logs = {}
    user_progressions = {}
    progression_data = {}

    if current_user.is_authenticated:
        all_names = [ex['name'] for exs in routine_data.values() for ex in exs]
        subq = (
            db.session.query(
                ExerciseLog.exercise_name,
                func.max(ExerciseLog.id).label('max_id')
            )
            .join(Workout)
            .filter(
                Workout.user_id == current_user.id,
                ExerciseLog.exercise_name.in_(all_names)
            )
            .group_by(ExerciseLog.exercise_name)
            .subquery()
        )
        last_logs = {
            log.exercise_name: log
            for log in ExerciseLog.query.join(subq, ExerciseLog.id == subq.c.max_id).all()
        }

        if routine == 'bwf':
            progression_data = current_app.config['PROGRESSION_DATA']
            user_progressions = {
                p.exercise_category: p
                for p in UserProgression.query.filter_by(user_id=current_user.id).all()
            }

    return render_template(
        'home.html',
        routine=routine_data,
        routine_type=routine,
        last_logs=last_logs,
        user_progressions=user_progressions,
        progression_data=progression_data,
        hidden_count=hidden_count,
        ai_program=ai_program,
        ai_programs=ai_programs,
    )


@main.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.home'))
        else:
            flash('Invalid username or password')

    return render_template('login.html')


@main.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        if not password or len(password) < MIN_PASSWORD_LENGTH:
            flash(f'Password must be at least {MIN_PASSWORD_LENGTH} characters.')
            return redirect(url_for('main.register'))

        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('main.register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('main.register'))

        user = User(username=username, email=email, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()

        progression_data = current_app.config['PROGRESSION_DATA']
        for category in progression_data:
            db.session.add(UserProgression(
                user_id=user.id,
                exercise_category=category,
                current_progression=1,
                current_reps=5,
            ))
        db.session.commit()

        flash('Registration successful! Please log in.')
        return redirect(url_for('main.login'))

    return render_template('register.html')


@main.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.home'))


@main.route('/exercise/<section>/<int:index>')
def exercise(section, index):
    routine = request.args.get('routine', 'bwf')
    if routine == 'gym':
        return _gym_style_exercise_view(section, index, _gym_routine_for_user(), 'gym')
    program = _ai_program_for_key(routine)
    if program is not None:
        routine_data = _routine_with_overlays(program.routine_data(), routine)
        return _gym_style_exercise_view(section, index, routine_data, routine)
    return _bwf_exercise_view(section, index)


def _gym_style_exercise_view(section, index, routine_data, routine_key):
    exercises = routine_data.get(section, [])
    if index >= len(exercises):
        flash('Exercise not found.')
        return redirect(url_for('main.home', routine=routine_key))
    exercise_obj = exercises[index]
    return render_template(
        'exercise.html',
        exercise=exercise_obj,
        section=section,
        routine=routine_key,
        progression_data=None,
        user_progression=None,
    )


def _bwf_exercise_view(section, index):
    routine_data = current_app.config['ROUTINE_DATA']
    exercise_obj = routine_data[section][index]

    progression_data = None
    if exercise_obj['name'].endswith('Progression'):
        progression_data = current_app.config['PROGRESSION_DATA'].get(exercise_obj['name'], [])

    user_progression = None
    if current_user.is_authenticated and progression_data:
        user_progression = UserProgression.query.filter_by(
            user_id=current_user.id,
            exercise_category=exercise_obj['name']
        ).first()

    return render_template(
        'exercise.html',
        exercise=exercise_obj,
        section=section,
        routine='bwf',
        progression_data=progression_data,
        user_progression=user_progression,
    )


def _form_routine_key():
    """Customization target from the form: 'gym' or a valid 'ai-<id>' key."""
    routine_key = request.form.get('routine', 'gym')
    if routine_key != 'gym' and _ai_program_for_key(routine_key) is None:
        return 'gym'
    return routine_key


@main.route('/routine/add_exercise', methods=['POST'])
@login_required
def add_exercise():
    routine_key = _form_routine_key()
    section = request.form.get('section', '').strip()
    name = request.form.get('name', '').strip()

    base = _editable_base_routine(routine_key)
    if not name or base is None or section not in base:
        flash('Exercise name and a valid section are required.')
        return redirect(url_for('main.home', routine=routine_key))

    visible_names = {
        ex['name'].lower()
        for exercises in _routine_with_overlays(base, routine_key).values()
        for ex in exercises
    }
    if name.lower() in visible_names:
        flash(f'"{name}" is already in your routine.')
        return redirect(url_for('main.home', routine=routine_key))

    sets = request.form.get('sets', type=int) or 3
    sets = max(1, min(sets, MAX_GYM_SETS))
    reps = request.form.get('reps', '').strip() or '8-12'
    equipment = request.form.get('equipment', 'machine')
    if equipment not in ALLOWED_EQUIPMENT:
        equipment = 'machine'

    db.session.add(CustomExercise(
        user_id=current_user.id,
        routine_type=routine_key,
        section=section,
        name=name,
        sets=sets,
        reps=reps[:20],
        weighted=(equipment != 'bodyweight'),
        equipment=equipment,
        description=request.form.get('description', '').strip(),
    ))
    db.session.commit()
    flash(f'Added "{name}" to {section}.')
    return redirect(url_for('main.home', routine=routine_key))


@main.route('/routine/remove_exercise', methods=['POST'])
@login_required
def remove_exercise():
    routine_key = _form_routine_key()
    name = request.form.get('name', '').strip()
    if not name:
        return redirect(url_for('main.home', routine=routine_key))

    custom = CustomExercise.query.filter_by(
        user_id=current_user.id, routine_type=routine_key, name=name).first()
    if custom:
        db.session.delete(custom)
    else:
        already_hidden = HiddenExercise.query.filter_by(
            user_id=current_user.id, routine_type=routine_key,
            exercise_name=name).first()
        if not already_hidden:
            db.session.add(HiddenExercise(
                user_id=current_user.id,
                routine_type=routine_key,
                exercise_name=name,
            ))
    db.session.commit()
    flash(f'Removed "{name}" from your routine.')
    return redirect(url_for('main.home', routine=routine_key))


@main.route('/routine/restore_exercises', methods=['POST'])
@login_required
def restore_exercises():
    routine_key = _form_routine_key()
    HiddenExercise.query.filter_by(
        user_id=current_user.id, routine_type=routine_key).delete()
    db.session.commit()
    flash('Removed exercises restored.')
    return redirect(url_for('main.home', routine=routine_key))


@main.route('/start_workout')
@login_required
def start_workout():
    routine_type = request.args.get('routine_type', session.get('current_routine_view', 'bwf'))
    if not _valid_routine_key(routine_type):
        routine_type = 'bwf'
    workout = Workout(user_id=current_user.id, routine_type=routine_type)
    db.session.add(workout)
    db.session.commit()

    session['current_workout_id'] = workout.id
    session['current_routine_type'] = routine_type
    session['current_routine_view'] = routine_type

    flash('Workout started!')
    return redirect(url_for('main.home', routine=routine_type))


@main.route('/end_workout')
@login_required
def end_workout():
    if 'current_workout_id' in session:
        workout_id = session.pop('current_workout_id')
        routine_type = session.pop('current_routine_type', 'bwf')
        workout = db.session.get(Workout, workout_id)

        if workout and workout.exercises.count() == 0:
            db.session.delete(workout)
            db.session.commit()
            flash('Workout cancelled.')
        else:
            flash('Workout completed!')

        return redirect(url_for('main.home', routine=routine_type))

    return redirect(url_for('main.home'))


@main.route('/log_exercise/<exercise_name>', methods=['POST'])
@login_required
def log_exercise(exercise_name):
    if 'current_workout_id' not in session:
        if _is_ajax():
            return jsonify({'status': 'error', 'message': 'No active workout'}), 400
        flash('No active workout. Please start a workout first.')
        return redirect(url_for('main.home'))

    workout_id = session['current_workout_id']
    routine = request.form.get('routine', 'bwf')
    section = request.form.get('section', '')
    index = request.form.get('index')
    rest_period = 60 if 'Core' in section else 90

    # AI-generated programs use the gym exercise schema, so they log the same way
    if routine == 'bwf':
        result = _log_bwf_exercise(exercise_name, workout_id)
    else:
        result = _log_gym_exercise(exercise_name, workout_id)

    if _is_ajax():
        get_flashed_messages()  # discard — flash queue unused for AJAX responses
        return jsonify({
            'status': 'ok' if result.get('ok') else 'error',
            'message': result.get('message', ''),
            'exercise_name': exercise_name,
            'sets_completed': result.get('sets_completed', 0),
            'rest_period': rest_period,
            'advanced': result.get('advanced', False),
            'new_progression': result.get('new_progression'),
        })

    return redirect(url_for('main.exercise', section=section, index=index, routine=routine))


def parse_gym_sets(form):
    """Return (weights, reps) lists from numbered form fields.
    A set counts when reps are present; weight is optional."""
    weights, reps = [], []
    for i in range(1, MAX_GYM_SETS + 1):
        reps_str = form.get(f'reps_set_{i}', '').strip()
        weight_str = form.get(f'weight_set_{i}', '').strip()
        if reps_str:
            reps.append(reps_str)
            weights.append(weight_str if weight_str else '0')
    return weights, reps


def _log_gym_exercise(exercise_name, workout_id):
    weights, reps = parse_gym_sets(request.form)
    if not reps:
        flash('Please fill in at least one set.')
        return {'ok': False, 'sets_completed': 0, 'message': 'Please fill in at least one set.'}

    has_weights = any(w not in ('', '0') for w in weights)
    weight_unit = request.form.get('weight_unit', 'lbs')

    db.session.add(ExerciseLog(
        exercise_name=exercise_name,
        sets_completed=len(reps),
        reps_per_set=','.join(reps),
        weight_per_set=','.join(weights) if has_weights else None,
        weight_unit=weight_unit if has_weights else None,
        progression_level=None,
        notes=request.form.get('notes', ''),
        workout_id=workout_id,
    ))
    db.session.commit()
    flash('Exercise logged!')
    return {'ok': True, 'sets_completed': len(reps), 'message': 'Exercise logged!'}


def _log_bwf_exercise(exercise_name, workout_id):
    progression_level = request.form.get('progression_level', type=int)

    reps_list = []
    for i in range(1, MAX_GYM_SETS + 1):
        reps_str = request.form.get(f'reps_set_{i}', '').strip()
        if reps_str:
            reps_list.append(reps_str)

    db.session.add(ExerciseLog(
        exercise_name=exercise_name,
        sets_completed=len(reps_list),
        reps_per_set=','.join(reps_list),
        progression_level=progression_level,
        notes=request.form.get('notes', ''),
        workout_id=workout_id,
    ))

    advanced, new_name = maybe_advance_progression(current_user, exercise_name, reps_list)
    db.session.commit()
    flash('Exercise logged successfully!')
    return {
        'ok': True,
        'sets_completed': len(reps_list),
        'message': 'Exercise logged!',
        'advanced': advanced,
        'new_progression': new_name,
    }


def maybe_advance_progression(user, exercise_name, reps_list):
    """Advance level after 3+ sets of 8+ reps. Returns (advanced, new_name)."""
    if not exercise_name.endswith('Progression'):
        return False, None
    if len(reps_list) < 3 or not all(int(r) >= 8 for r in reps_list):
        return False, None

    user_progression = UserProgression.query.filter_by(
        user_id=user.id,
        exercise_category=exercise_name
    ).first()
    if not user_progression:
        return False, None

    progression_data = current_app.config['PROGRESSION_DATA'].get(exercise_name, [])
    max_level = len(progression_data)

    if user_progression.current_progression < max_level:
        user_progression.current_progression += 1
        user_progression.current_reps = 5
        user_progression.last_updated = datetime.now(timezone.utc)
        next_name = progression_data[user_progression.current_progression - 1]['name']
        flash(f'Congratulations! You advanced to: {next_name}')
        return True, next_name

    return False, None


@main.route('/progress')
@login_required
def progress():
    user_progressions = UserProgression.query.filter_by(user_id=current_user.id).all()
    progression_data = current_app.config['PROGRESSION_DATA']
    recent_workouts = Workout.query.filter_by(user_id=current_user.id).order_by(Workout.date.desc()).limit(5).all()

    return render_template(
        'progress.html',
        user_progressions=user_progressions,
        progression_data=progression_data,
        recent_workouts=recent_workouts,
    )


@main.route('/workout/<int:workout_id>')
@login_required
def view_workout(workout_id):
    workout = db.session.get(Workout, workout_id)
    if workout is None:
        flash('Workout not found.')
        return redirect(url_for('main.progress'))

    if workout.user_id != current_user.id:
        flash('You do not have permission to view this workout.')
        return redirect(url_for('main.progress'))

    exercise_logs = ExerciseLog.query.filter_by(workout_id=workout_id).all()
    progression_data = current_app.config['PROGRESSION_DATA']

    return render_template(
        'workout_detail.html',
        workout=workout,
        exercise_logs=exercise_logs,
        progression_data=progression_data,
    )


# ── AI program generation ──────────────────────────────────────────────


def _owned_program_or_none(program_id):
    program = db.session.get(GeneratedProgram, program_id)
    if program is None or program.user_id != current_user.id:
        return None
    return program


def _generation_inputs_from_form(form):
    days = form.get('days_per_week', type=int) or 3
    minutes = form.get('session_length', type=int) or 60
    experience = form.get('experience', 'beginner')
    return {
        'goal': form.get('goal', '').strip()[:200],
        'equipment': [e for e in form.getlist('equipment') if e in EQUIPMENT_CHOICES],
        'days_per_week': max(1, min(days, 7)),
        'session_length': max(15, min(minutes, 180)),
        'experience': experience if experience in EXPERIENCE_LEVELS else 'beginner',
        'notes': form.get('notes', '').strip()[:500],
    }


@main.route('/generate', methods=['GET', 'POST'])
@login_required
def generate():
    api_key = ai_generator.resolve_api_key(current_user)

    if request.method == 'GET':
        return render_template(
            'generate.html',
            has_api_key=bool(api_key),
            equipment_choices=EQUIPMENT_CHOICES,
            experience_levels=EXPERIENCE_LEVELS,
        )

    if not api_key:
        flash('No Claude API key available. Add yours in Settings first.')
        return redirect(url_for('main.settings'))

    inputs = _generation_inputs_from_form(request.form)
    if not inputs['goal']:
        flash('Tell the coach what you are training for.')
        return redirect(url_for('main.generate'))

    try:
        name, description, routine = ai_generator.generate_program(api_key, inputs)
    except ai_generator.GenerationError as exc:
        flash(str(exc))
        return redirect(url_for('main.generate'))

    # Abandoned drafts are dead weight — keep at most one per user
    GeneratedProgram.query.filter_by(
        user_id=current_user.id, is_draft=True).delete()
    program = GeneratedProgram(
        user_id=current_user.id,
        name=name,
        goal=inputs['goal'],
        description=description,
        program_json=json.dumps(routine),
        inputs_json=json.dumps(inputs),
        is_draft=True,
    )
    db.session.add(program)
    db.session.commit()
    return redirect(url_for('main.preview_program', program_id=program.id))


@main.route('/generate/preview/<int:program_id>')
@login_required
def preview_program(program_id):
    program = _owned_program_or_none(program_id)
    if program is None:
        flash('Program not found.')
        return redirect(url_for('main.home'))
    return render_template(
        'preview_program.html',
        program=program,
        routine=program.routine_data(),
    )


@main.route('/generate/accept/<int:program_id>', methods=['POST'])
@login_required
def accept_program(program_id):
    program = _owned_program_or_none(program_id)
    if program is None:
        flash('Program not found.')
        return redirect(url_for('main.home'))
    program.is_draft = False
    db.session.commit()
    flash(f'"{program.name}" saved — time to train!')
    return redirect(url_for('main.home', routine=program.routine_key))


@main.route('/generate/retry/<int:program_id>', methods=['POST'])
@login_required
def retry_program(program_id):
    program = _owned_program_or_none(program_id)
    if program is None:
        flash('Program not found.')
        return redirect(url_for('main.home'))

    feedback = request.form.get('feedback', '').strip()[:500]
    if not feedback:
        flash('Tell the coach what to change.')
        return redirect(url_for('main.preview_program', program_id=program.id))

    api_key = ai_generator.resolve_api_key(current_user)
    if not api_key:
        flash('No Claude API key available. Add yours in Settings first.')
        return redirect(url_for('main.settings'))

    try:
        name, description, routine = ai_generator.generate_program(
            api_key, program.inputs(),
            previous_program=program.routine_data(), feedback=feedback)
    except ai_generator.GenerationError as exc:
        flash(str(exc))
        return redirect(url_for('main.preview_program', program_id=program.id))

    program.name = name
    program.description = description
    program.program_json = json.dumps(routine)
    db.session.commit()
    flash('Program updated with your feedback.')
    return redirect(url_for('main.preview_program', program_id=program.id))


@main.route('/program/delete/<int:program_id>', methods=['POST'])
@login_required
def delete_program(program_id):
    program = _owned_program_or_none(program_id)
    if program is None:
        flash('Program not found.')
        return redirect(url_for('main.home'))

    routine_key = program.routine_key
    CustomExercise.query.filter_by(
        user_id=current_user.id, routine_type=routine_key).delete()
    HiddenExercise.query.filter_by(
        user_id=current_user.id, routine_type=routine_key).delete()
    db.session.delete(program)
    db.session.commit()
    if session.get('current_routine_view') == routine_key:
        session.pop('current_routine_view')
    flash(f'Deleted "{program.name}". Workout history is kept.')
    return redirect(url_for('main.home'))


@main.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    record = UserApiKey.query.filter_by(
        user_id=current_user.id, provider='anthropic').first()

    if request.method == 'POST':
        if request.form.get('action') == 'clear':
            if record:
                db.session.delete(record)
                db.session.commit()
            flash('Your API key was removed.')
        else:
            raw = request.form.get('api_key', '').strip()
            if not raw:
                flash('Enter an API key to save.')
            else:
                if record is None:
                    record = UserApiKey(user_id=current_user.id,
                                        provider='anthropic')
                    db.session.add(record)
                record.set_key(raw)
                db.session.commit()
                flash('API key saved.')
        return redirect(url_for('main.settings'))

    return render_template(
        'settings.html',
        key_hint=record.key_hint() if record else None,
        server_key_available=bool(current_app.config.get('ANTHROPIC_API_KEY')),
    )
