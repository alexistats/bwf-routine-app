from flask import Blueprint, render_template, current_app, redirect, url_for, request, flash
from flask_login import login_required, current_user, login_user, logout_user
from app.models import User, Workout, ExerciseLog
from app import db

main = Blueprint('main', __name__)

@main.route('/')
def home():
    routine_data = current_app.config['ROUTINE_DATA']
    return render_template('home.html', routine=routine_data)

@main.route('/exercise/<section>/<int:index>')
def exercise(section, index):
    routine_data = current_app.config['ROUTINE_DATA']
    exercise = routine_data[section][index]
    return render_template('exercise.html', exercise=exercise, section=section)

# Additional routes for user authentication and workout tracking can be added here
