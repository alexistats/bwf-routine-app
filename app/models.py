from app import db, login_manager
from flask_login import UserMixin
from datetime import datetime


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, index=True)
    email = db.Column(db.String(120), unique=True, index=True)
    password_hash = db.Column(db.String(128))
    workouts = db.relationship('Workout', backref='user', lazy='dynamic')
    progressions = db.relationship('UserProgression', backref='user', lazy='dynamic')


class Workout(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    exercises = db.relationship('ExerciseLog', backref='workout', lazy='dynamic')

    def formatted_date(self):
        return self.date.strftime('%Y-%m-%d %H:%M')


class ExerciseLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exercise_name = db.Column(db.String(100))
    sets_completed = db.Column(db.Integer)
    reps_per_set = db.Column(db.String(50))  # Store as comma-separated values
    progression_level = db.Column(db.Integer)
    notes = db.Column(db.Text)
    workout_id = db.Column(db.Integer, db.ForeignKey('workout.id'))

    def get_reps_list(self):
        return [int(rep) for rep in self.reps_per_set.split(',')]


class UserProgression(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    exercise_category = db.Column(db.String(100))  # e.g., "Pull-up", "Squat"
    current_progression = db.Column(db.Integer)  # Index of current progression
    current_reps = db.Column(db.Integer, default=5)  # Current target reps
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
