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
    routine_type = db.Column(db.String(20), default='bwf')
    exercises = db.relationship('ExerciseLog', backref='workout', lazy='dynamic')

    def formatted_date(self):
        return self.date.strftime('%Y-%m-%d %H:%M')


class ExerciseLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exercise_name = db.Column(db.String(100))
    sets_completed = db.Column(db.Integer)
    reps_per_set = db.Column(db.String(100))  # comma-separated
    weight_per_set = db.Column(db.String(200), nullable=True)  # comma-separated, gym only
    weight_unit = db.Column(db.String(5), nullable=True)  # 'lbs' or 'kg'
    progression_level = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.Text)
    workout_id = db.Column(db.Integer, db.ForeignKey('workout.id'))

    def get_reps_list(self):
        if not self.reps_per_set:
            return []
        return [int(r) for r in self.reps_per_set.split(',') if r]

    def get_weights_list(self):
        if not self.weight_per_set:
            return []
        return [float(w) for w in self.weight_per_set.split(',') if w]


class UserProgression(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    exercise_category = db.Column(db.String(100))  # e.g., "Pull-up", "Squat"
    current_progression = db.Column(db.Integer)  # Index of current progression
    current_reps = db.Column(db.Integer, default=5)  # Current target reps
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
