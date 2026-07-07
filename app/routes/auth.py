import secrets
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session, g, flash
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User, PasswordReset
from app.services.logger import log_user_action, log_error

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if not email or not username or not password:
            return render_template('auth/register.html', error='All fields are required')

        if password != confirm:
            return render_template('auth/register.html', error='Passwords do not match')

        if len(password) < 6:
            return render_template('auth/register.html', error='Password must be at least 6 characters')

        if User.query.filter_by(email=email).first():
            return render_template('auth/register.html', error='Email already registered')

        if User.query.filter_by(username=username).first():
            return render_template('auth/register.html', error='Username already taken')

        user = User(email=email, username=username)
        user.set_password(password)
        user.api_key = 'uk_' + secrets.token_hex(32)
        db.session.add(user)
        db.session.commit()

        log_user_action(request.remote_addr, 'register', '/auth/register', f'User {username} registered')
        login_user(user)
        return redirect(url_for('auth.profile'))

    return render_template('auth/register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            return render_template('auth/login.html', error='Invalid email or password')

        login_user(user)
        log_user_action(request.remote_addr, 'login', '/auth/login', f'User {user.username} logged in')

        next_page = request.args.get('next', url_for('auth.profile'))
        return redirect(next_page)

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    log_user_action(request.remote_addr, 'logout', '/auth/logout', f'User {current_user.username} logged out')
    logout_user()
    return redirect(url_for('landing.index'))


@auth_bp.route('/profile')
@login_required
def profile():
    from app.models import Payment, Subscription, ApiKey
    payments = Payment.query.filter_by(user_id=current_user.id).order_by(Payment.created_at.desc()).limit(10).all()
    subscription = Subscription.query.filter_by(user_id=current_user.id, status='active').first()
    api_keys = ApiKey.query.filter_by(user_id=current_user.id).all()
    return render_template('auth/profile.html',
                           payments=payments, subscription=subscription, api_keys=api_keys)


@auth_bp.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    email = request.form.get('email', '').strip()
    username = request.form.get('username', '').strip()

    if email and email != current_user.email:
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'Email already in use'}), 400
        current_user.email = email

    if username and username != current_user.username:
        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'Username already taken'}), 400
        current_user.username = username

    db.session.commit()
    return jsonify({'success': True})


@auth_bp.route('/profile/api-key/regenerate', methods=['POST'])
@login_required
def regenerate_api_key():
    current_user.api_key = 'uk_' + secrets.token_hex(32)
    db.session.commit()
    return jsonify({'success': True, 'api_key': current_user.api_key})


@auth_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    current_pw = request.form.get('current_password', '')
    new_pw = request.form.get('new_password', '')

    if not current_user.check_password(current_pw):
        return jsonify({'error': 'Current password is incorrect'}), 400

    if len(new_pw) < 6:
        return jsonify({'error': 'New password must be at least 6 characters'}), 400

    current_user.set_password(new_pw)
    db.session.commit()
    return jsonify({'success': True})


@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user = User.query.filter_by(email=email).first()

        if not user:
            return render_template('auth/reset_password.html', error='Email not found')

        token = secrets.token_hex(48)
        reset = PasswordReset(email=email, token=token)
        db.session.add(reset)
        db.session.commit()

        log_user_action(request.remote_addr, 'password_reset_request', '/auth/reset-password',
                        f'Reset token generated for {email}')
        return render_template('auth/reset_password.html',
                               message='Password reset link sent. For demo, use the token below:',
                               demo_token=token)

    return render_template('auth/reset_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password_confirm(token):
    reset = PasswordReset.query.filter_by(token=token, used=False).first()
    if not reset:
        return render_template('auth/reset_password.html', error='Invalid or expired reset token')

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if password != confirm:
            return render_template('auth/reset_password_confirm.html', error='Passwords do not match', token=token)

        if len(password) < 6:
            return render_template('auth/reset_password_confirm.html', error='Password too short', token=token)

        user = User.query.filter_by(email=reset.email).first()
        if user:
            user.set_password(password)
            db.session.commit()

        reset.used = True
        db.session.commit()

        log_user_action(request.remote_addr, 'password_reset_complete', '/auth/reset-password',
                        f'Password reset for {reset.email}')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password_confirm.html', token=token)
