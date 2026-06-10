from flask import Blueprint, render_template, current_app, redirect, url_for, request, flash, session
from flask_login import login_required, current_user, login_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from app.models import User, Workout, ExerciseLog, UserProgression
from app import db
from datetime import datetime

main = Blueprint('main', __name__)


@main.route('/')
def home():
    routine = request.args.get('routine', 'bwf')
    session['current_routine_view'] = routine

    if routine == 'gym':
        routine_data = current_app.config['GYM_ROUTINE_DATA']
    else:
        routine_data = current_app.config['ROUTINE_DATA']

    return render_template('home.html', routine=routine_data, routine_type=routine)


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
            progression = UserProgression(
                user_id=user.id,
                exercise_category=category,
                current_progression=1,
                current_reps=5
            )
            db.session.add(progression)
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
        routine_data = current_app.config['GYM_ROUTINE_DATA']
        exercise_obj = routine_data[section][index]

        last_log = None
        if current_user.is_authenticated:
            last_log = (
                ExerciseLog.query
                .join(Workout)
                .filter(
                    Workout.user_id == current_user.id,
                    ExerciseLog.exercise_name == exercise_obj['name']
                )
                .order_by(ExerciseLog.id.desc())
                .first()
            )

        return render_template(
            'exercise.html',
            exercise=exercise_obj,
            section=section,
            routine=routine,
            rest_period=120,
            last_log=last_log,
            progression_data=None,
            user_progression=None
        )

    # BWF
    routine_data = current_app.config['ROUTINE_DATA']
    exercise_obj = routine_data[section][index]

    rest_period = 90
    if section == 'Core Triplet':
        rest_period = 60

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
        routine=routine,
        rest_period=rest_period,
        last_log=None,
        progression_data=progression_data,
        user_progression=user_progression
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
        workout = Workout.query.get(workout_id)

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
        flash('No active workout. Please start a workout first.')
        return redirect(url_for('main.home'))

    workout_id = session['current_workout_id']
    routine = request.form.get('routine', 'bwf')
    section = request.form.get('section')
    index = request.form.get('index')

    if routine == 'gym':
        weight_unit = request.form.get('weight_unit', 'lbs')
        sets_completed = 0
        weights_list = []
        reps_list = []

        for i in range(1, 4):
            reps_str = request.form.get(f'reps_set_{i}', '').strip()
            weight_str = request.form.get(f'weight_set_{i}', '').strip()
            if reps_str:
                sets_completed += 1
                reps_list.append(reps_str)
                weights_list.append(weight_str if weight_str else '0')

        if sets_completed == 0:
            flash('Please fill in at least one set.')
            return redirect(url_for('main.exercise', section=section, index=index, routine=routine))

        has_weights = any(w not in ('', '0') for w in weights_list)

        exercise_log = ExerciseLog(
            exercise_name=exercise_name,
            sets_completed=sets_completed,
            reps_per_set=','.join(reps_list),
            weight_per_set=','.join(weights_list) if has_weights else None,
            weight_unit=weight_unit if has_weights else None,
            progression_level=None,
            notes=request.form.get('notes', ''),
            workout_id=workout_id
        )
        db.session.add(exercise_log)
        db.session.commit()
        flash('Exercise logged!')

    else:
        # BWF
        progression_level = request.form.get('progression_level', type=int)
        sets_completed = request.form.get('sets_completed', type=int)

        reps_list = []
        for i in range(1, sets_completed + 1):
            reps = request.form.get(f'reps_set_{i}', type=int)
            if reps:
                reps_list.append(str(reps))

        exercise_log = ExerciseLog(
            exercise_name=exercise_name,
            sets_completed=sets_completed,
            reps_per_set=','.join(reps_list),
            progression_level=progression_level,
            notes=request.form.get('notes', ''),
            workout_id=workout_id
        )
        db.session.add(exercise_log)

        if exercise_name.endswith('Progression') and all(int(r) >= 8 for r in reps_list) and len(reps_list) >= 3:
            user_progression = UserProgression.query.filter_by(
                user_id=current_user.id,
                exercise_category=exercise_name
            ).first()

            if user_progression:
                progression_data = current_app.config['PROGRESSION_DATA'].get(exercise_name, [])
                max_level = len(progression_data)

                if user_progression.current_progression < max_level:
                    user_progression.current_progression += 1
                    user_progression.current_reps = 5
                    user_progression.last_updated = datetime.utcnow()
                    flash(f'Congratulations! You advanced to: {progression_data[user_progression.current_progression - 1]["name"]}')

        db.session.commit()
        flash('Exercise logged successfully!')

    return redirect(url_for('main.exercise', section=section, index=index, routine=routine))


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
        recent_workouts=recent_workouts
    )


@main.route('/workout/<int:workout_id>')
@login_required
def view_workout(workout_id):
    workout = Workout.query.get_or_404(workout_id)

    if workout.user_id != current_user.id:
        flash('You do not have permission to view this workout.')
        return redirect(url_for('main.progress'))

    exercise_logs = ExerciseLog.query.filter_by(workout_id=workout_id).all()
    progression_data = current_app.config['PROGRESSION_DATA']

    return render_template(
        'workout_detail.html',
        workout=workout,
        exercise_logs=exercise_logs,
        progression_data=progression_data
    )
