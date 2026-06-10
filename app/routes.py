from flask import (Blueprint, render_template, current_app, redirect, url_for,
                   request, flash, session, jsonify, get_flashed_messages)
from flask_login import login_required, current_user, login_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func
from app.models import User, Workout, ExerciseLog, UserProgression
from app import db
from datetime import datetime, timezone

main = Blueprint('main', __name__)

MIN_PASSWORD_LENGTH = 8
MAX_GYM_SETS = 10


def _is_ajax():
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


@main.route('/')
def home():
    routine = request.args.get('routine', 'bwf')
    if current_user.is_authenticated:
        session['current_routine_view'] = routine

    if routine == 'gym':
        routine_data = current_app.config['GYM_ROUTINE_DATA']
    else:
        routine_data = current_app.config['ROUTINE_DATA']

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
        return _gym_exercise_view(section, index)
    return _bwf_exercise_view(section, index)


def _gym_exercise_view(section, index):
    routine_data = current_app.config['GYM_ROUTINE_DATA']
    exercise_obj = routine_data[section][index]
    return render_template(
        'exercise.html',
        exercise=exercise_obj,
        section=section,
        routine='gym',
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


@main.route('/start_workout')
@login_required
def start_workout():
    routine_type = request.args.get('routine_type', session.get('current_routine_view', 'bwf'))
    workout = Workout(user_id=current_user.id, routine_type=routine_type)
    db.session.add(workout)
    db.session.commit()

    session['current_workout_id'] = workout.id
    session['current_routine_type'] = routine_type

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

    if routine == 'gym':
        result = _log_gym_exercise(exercise_name, workout_id)
    else:
        result = _log_bwf_exercise(exercise_name, workout_id)

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
