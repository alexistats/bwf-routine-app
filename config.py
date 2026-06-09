import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here'

    _db_uri = os.environ.get('DATABASE_URL') or 'sqlite:///bwf_routine.db'
    # SQLAlchemy 2.x requires 'postgresql://' — Render/Neon provide 'postgres://'
    if _db_uri.startswith('postgres://'):
        _db_uri = _db_uri.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = _db_uri

    SQLALCHEMY_TRACK_MODIFICATIONS = False
