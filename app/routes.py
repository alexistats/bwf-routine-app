from flask import Blueprint, render_template, current_app, redirect, url_for, request, flash, session
from flask_login import login_required, current_user, login_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from app.models import User, Workout, ExerciseLog, UserProgression
from app import db
from datetime import datetime

main = Blueprint('main', __name__)


@main.route('/')
def home():
    routine_data = current_app.config['ROUTINE_DATA']
    return render_template('home.html', routine=routine_data)


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

        # Initialize user progressions
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
    routine_data = current_app.config['ROUTINE_DATA']
    exercise = routine_data[section][index]

    # Determine rest period based on section
    rest_period = 90  # Default for paired exercises
    if section == "Core Triplet":
        rest_period = 60

    # Get progression data if applicable
    progression_data = None
    if exercise['name'].endswith('Progression'):
        category = exercise['name']
        progression_data = current_app.config['PROGRESSION_DATA'].get(category, [])

    # Get user's current progression if logged in
    user_progression = None
    if current_user.is_authenticated and progression_data:
        user_progression = UserProgression.query.filter_by(
            user_id=current_user.id,
            exercise_category=exercise['name']
        ).first()

    return render_template(
        'exercise.html',
        exercise=exercise,
        section=section,
        rest_period=rest_period,
        progression_data=progression_data,
        user_progression=user_progression
    )


@main.route('/start_workout')
@login_required
def start_workout():
    # Create a new workout
    workout = Workout(user_id=current_user.id)
    db.session.add(workout)
    db.session.commit()

    # Store workout ID in session
    session['current_workout_id'] = workout.id

    flash('Workout started!')
    return redirect(url_for('main.home'))


@main.route('/end_workout')
@login_required
def end_workout():
    if 'current_workout_id' in session:
        workout_id = session.pop('current_workout_id')
        workout = Workout.query.get(workout_id)

        # If no exercises were logged, delete the workout
        if workout and workout.exercises.count() == 0:
            db.session.delete(workout)
            db.session.commit()
            flash('Workout cancelled.')
        else:
            flash('Workout completed!')

    return redirect(url_for('main.home'))


@main.route('/log_exercise/<exercise_name>', methods=['POST'])
@login_required
def log_exercise(exercise_name):
    if 'current_workout_id' not in session:
        flash('No active workout. Please start a workout first.')
        return redirect(url_for('main.home'))

    workout_id = session['current_workout_id']
    progression_level = request.form.get('progression_level', type=int)
    sets_completed = request.form.get('sets_completed', type=int)

    # Get reps for each set
    reps_list = []
    for i in range(1, sets_completed + 1):
        reps = request.form.get(f'reps_set_{i}', type=int)
        if reps:
            reps_list.append(str(reps))

    reps_per_set = ','.join(reps_list)
    notes = request.form.get('notes', '')

    # Log the exercise
    exercise_log = ExerciseLog(
        exercise_name=exercise_name,
        sets_completed=sets_completed,
        reps_per_set=reps_per_set,
        progression_level=progression_level,
        notes=notes,
        workout_id=workout_id
    )
    db.session.add(exercise_log)

    # Update user progression if all sets reached 8 reps
    if exercise_name.endswith('Progression') and all(int(rep) >= 8 for rep in reps_list) and len(reps_list) >= 3:
        user_progression = UserProgression.query.filter_by(
            user_id=current_user.id,
            exercise_category=exercise_name
        ).first()

        if user_progression:
            # Get max progression level
            progression_data = current_app.config['PROGRESSION_DATA'].get(exercise_name, [])
            max_level = len(progression_data)

            # If not at max level, advance to next progression
            if user_progression.current_progression < max_level:
                user_progression.current_progression += 1
                user_progression.current_reps = 5  # Reset to 5 reps
                user_progression.last_updated = datetime.utcnow()
                flash(
                    f'Congratulations! You have advanced to the next progression: {progression_data[user_progression.current_progression - 1]["name"]}')

    db.session.commit()
    flash('Exercise logged successfully!')

    return redirect(url_for('main.exercise', section=request.form.get('section'), index=request.form.get('index')))


@main.route('/progress')
@login_required
def progress():
    # Get user's progression data
    user_progressions = UserProgression.query.filter_by(user_id=current_user.id).all()
    progression_data = current_app.config['PROGRESSION_DATA']

    # Get recent workouts
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

    # Ensure the workout belongs to the current user
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
