from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from .models import User
from app import db, login_manager

auth = Blueprint('auth', __name__)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@auth.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        session.pop('_flashes', None)
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return render_template('auth/signup.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'error')
            return render_template('auth/signup.html')
        
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Account created successfully! Please login.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/signup.html')



from flask_wtf.csrf import generate_csrf

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('detection.dashboard'))
        flash('Invalid username or password', 'error')

    csrf_token = generate_csrf() 
    return render_template('auth/login.html', csrf_token=csrf_token)


@auth.route('/logout')
@login_required
def logout():
    session.pop('_flashes', None)
    logout_user()
    return redirect(url_for('auth.login'))