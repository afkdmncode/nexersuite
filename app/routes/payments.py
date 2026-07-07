import os
import stripe
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, current_app
from flask_login import login_required, current_user
from app import db
from app.models import User, Payment, Subscription
from app.services.logger import log_user_action, log_error

payments_bp = Blueprint('payments', __name__)

stripe.api_key = os.getenv('STRIPE_SECRET_KEY', '')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', '')

PLANS = {
    'monthly': {
        'name': 'Pro Monthly',
        'price_id': os.getenv('STRIPE_MONTHLY_PRICE_ID', 'price_monthly'),
        'amount': 999,
        'currency': 'usd',
    },
    'yearly': {
        'name': 'Pro Yearly',
        'price_id': os.getenv('STRIPE_YEARLY_PRICE_ID', 'price_yearly'),
        'amount': 7999,
        'currency': 'usd',
    },
}


def is_stripe_configured():
    return bool(stripe.api_key)


@payments_bp.route('/checkout/<plan>')
@login_required
def checkout(plan):
    if not is_stripe_configured():
        return render_template('payments/error.html',
                               message='Stripe is not configured. Set STRIPE_SECRET_KEY in .env')

    if plan not in PLANS:
        return render_template('payments/error.html', message='Invalid plan')

    try:
        checkout_session = stripe.checkout.Session.create(
            client_reference_id=str(current_user.id),
            customer_email=current_user.email,
            payment_method_types=['card'],
            line_items=[{
                'price': PLANS[plan]['price_id'],
                'quantity': 1,
            }],
            mode='subscription',
            success_url=url_for('payments.success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('auth.profile', _external=True),
            metadata={'user_id': str(current_user.id)},
        )

        payment = Payment(
            user_id=current_user.id,
            amount=PLANS[plan]['amount'] / 100,
            stripe_session_id=checkout_session.id,
            status='pending',
        )
        db.session.add(payment)
        db.session.commit()

        log_user_action(request.remote_addr, 'checkout_started', '/payments/checkout',
                        f'Plan: {plan}, Session: {checkout_session.id}')

        return redirect(checkout_session.url, code=303)
    except Exception as e:
        log_error(f'Stripe checkout failed: {e}', user_id=current_user.id, plan=plan)
        return render_template('payments/error.html', message=str(e))


@payments_bp.route('/success')
@login_required
def success():
    session_id = request.args.get('session_id', '')
    if session_id:
        payment = Payment.query.filter_by(stripe_session_id=session_id).first()
        if payment:
            payment.status = 'completed'
            db.session.commit()

    return render_template('payments/success.html')


@payments_bp.route('/cancel')
@login_required
def cancel():
    return redirect(url_for('auth.profile'))


@payments_bp.route('/webhook', methods=['POST'])
def webhook():
    if not is_stripe_configured():
        return jsonify({'error': 'Stripe not configured'}), 400

    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature', '')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        log_error(f'Stripe webhook error: {e}')
        return jsonify({'error': 'Invalid signature'}), 400

    event_type = event.get('type')
    data = event.get('data', {}).get('object', {})

    if event_type == 'checkout.session.completed':
        session_id = data.get('id')
        customer_id = data.get('customer')
        subscription_id = data.get('subscription')
        user_id = data.get('metadata', {}).get('user_id')

        payment = Payment.query.filter_by(stripe_session_id=session_id).first()
        if payment:
            payment.status = 'completed'
            payment.stripe_subscription_id = subscription_id

        if user_id:
            user = db.session.get(User, int(user_id))
            if user:
                user.is_paid = True
                user.subscription_tier = 'pro'
                user.stripe_customer_id = customer_id

                sub = Subscription(
                    user_id=user.id,
                    stripe_subscription_id=subscription_id,
                    plan_id='pro',
                    status='active',
                    current_period_start=datetime.utcnow(),
                    current_period_end=datetime.utcnow() + timedelta(days=30),
                )
                db.session.add(sub)

        db.session.commit()

    elif event_type == 'customer.subscription.updated':
        subscription_id = data.get('id')
        status = data.get('status')
        sub = Subscription.query.filter_by(stripe_subscription_id=subscription_id).first()
        if sub:
            sub.status = status
            if status == 'active':
                sub.current_period_start = datetime.fromtimestamp(data.get('current_period_start', 0))
                sub.current_period_end = datetime.fromtimestamp(data.get('current_period_end', 0))
            db.session.commit()

    elif event_type == 'customer.subscription.deleted':
        subscription_id = data.get('id')
        sub = Subscription.query.filter_by(stripe_subscription_id=subscription_id).first()
        if sub:
            sub.status = 'canceled'
            user = db.session.get(User, sub.user_id)
            if user:
                user.is_paid = False
                user.subscription_tier = 'free'
            db.session.commit()

    elif event_type == 'invoice.payment_failed':
        subscription_id = data.get('subscription')
        sub = Subscription.query.filter_by(stripe_subscription_id=subscription_id).first()
        if sub:
            sub.status = 'past_due'
            db.session.commit()

    return jsonify({'status': 'ok'})
