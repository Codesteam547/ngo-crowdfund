import hashlib
import uuid
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'crowdfund-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///crowdfund.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- DATABASE MODELS ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='donor')  # 'donor' or 'admin'

class NGO(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    reputation_score = db.Column(db.Integer, default=100)

class Vendor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    balance = db.Column(db.Float, default=0.0)

class Campaign(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ngo_id = db.Column(db.Integer, db.ForeignKey('ngo.id'))
    title = db.Column(db.String(150), nullable=False)
    target_amount = db.Column(db.Float, nullable=False)
    escrow_balance = db.Column(db.Float, default=0.0)
    milestones = db.relationship('Milestone', backref='campaign', cascade="all, delete-orphan")
    donations = db.relationship('Donation', backref='campaign', cascade="all, delete-orphan")

class Milestone(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaign.id'))
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendor.id'))
    title = db.Column(db.String(150), nullable=False)
    target_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default="LOCKED")
    proof_url = db.Column(db.String(255), nullable=True)

class Donation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaign.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    receipt_no = db.Column(db.String(20), unique=True, nullable=True)
    txn_hash = db.Column(db.String(64), unique=True, nullable=True)
    timestamp = db.Column(db.String(50), nullable=False)

def seed_database():
    with app.app_context():
        db.create_all()
        # Seed default Admin and Donor users
        if not User.query.first():
            admin_user = User(
                username="admin", 
                password_hash=generate_password_hash("admin123"), 
                role="admin"
            )
            donor_user = User(
                username="donor", 
                password_hash=generate_password_hash("donor123"), 
                role="donor"
            )
            ngo = NGO(id=1, name="Clean Water Initiative", reputation_score=100)
            vendor = Vendor(id=10, name="Aqua Pipe Supplies Co.", balance=0.0)
            campaign = Campaign(id=101, ngo_id=1, title="Village Well Construction", target_amount=15000.0, escrow_balance=0.0)
            milestone = Milestone(id=501, campaign_id=101, vendor_id=10, title="Phase 1: Purchase Pipes & Drilling Gear", target_amount=5000.0, status="LOCKED")
            
            db.session.add_all([admin_user, donor_user, ngo, vendor, campaign, milestone])
            db.session.commit()

# --- PAGE ROUTES ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/signup')
def signup_page():
    return render_template('signup.html')

@app.route('/create')
def create_page():
    if session.get('role') != 'admin':
        return redirect(url_for('login_page'))
    return render_template('create.html')

@app.route('/receipt/<string:txn_hash>')
def view_receipt(txn_hash):
    donation = Donation.query.filter_by(txn_hash=txn_hash).first_or_404()
    campaign = Campaign.query.get(donation.campaign_id)
    ngo = NGO.query.get(campaign.ngo_id) if campaign else None
    return render_template('receipt.html', donation=donation, campaign=campaign, ngo=ngo)

# --- AUTH API ENDPOINTS ---
@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role = data.get('role', 'donor')

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already taken"}), 400

    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        role=role if role in ['donor', 'admin'] else 'donor'
    )
    db.session.add(user)
    db.session.commit()

    session['user_id'] = user.id
    session['username'] = user.username
    session['role'] = user.role

    return jsonify({"message": f"Account created as {user.role.capitalize()}!", "role": user.role})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    user = User.query.filter_by(username=username).first()

    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid username or password"}), 401

    session['user_id'] = user.id
    session['username'] = user.username
    session['role'] = user.role

    return jsonify({"message": f"Welcome back, {user.username}!", "role": user.role})

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"message": "Logged out successfully."})

@app.route('/api/me', methods=['GET'])
def get_current_user():
    if 'user_id' in session:
        return jsonify({"logged_in": True, "username": session['username'], "role": session['role']})
    return jsonify({"logged_in": False})

# --- DATA API ENDPOINTS ---
@app.route('/api/campaigns', methods=['GET'])
def get_campaigns():
    campaigns = Campaign.query.all()
    results = []
    for c in campaigns:
        ngo = NGO.query.get(c.ngo_id)
        ms_list = []
        for ms in c.milestones:
            vendor = Vendor.query.get(ms.vendor_id) if ms.vendor_id else None
            ms_list.append({
                "id": ms.id,
                "title": ms.title,
                "target_amount": ms.target_amount,
                "status": ms.status,
                "proof_url": ms.proof_url,
                "vendor_name": vendor.name if vendor else "N/A",
                "vendor_balance": vendor.balance if vendor else 0.0
            })
        results.append({
            "campaign_id": c.id,
            "title": c.title,
            "target_amount": c.target_amount,
            "escrow_balance": c.escrow_balance,
            "ngo_name": ngo.name if ngo else "Unknown NGO",
            "ngo_reputation": ngo.reputation_score if ngo else 100,
            "milestones": ms_list
        })
    return jsonify(results)

@app.route('/api/create-campaign', methods=['POST'])
def create_campaign():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized. Only Admins can create campaigns."}), 403

    data = request.get_json()
    ngo = NGO(name=data.get('ngo_name'), reputation_score=100)
    db.session.add(ngo)
    db.session.flush()

    vendor = Vendor(name=data.get('vendor_name'), balance=0.0)
    db.session.add(vendor)
    db.session.flush()

    campaign = Campaign(ngo_id=ngo.id, title=data.get('title'), target_amount=float(data.get('target_amount')), escrow_balance=0.0)
    db.session.add(campaign)
    db.session.flush()

    milestone = Milestone(campaign_id=campaign.id, vendor_id=vendor.id, title=data.get('milestone_title'), target_amount=float(data.get('milestone_target')), status="LOCKED")
    db.session.add(milestone)
    db.session.commit()
    return jsonify({"message": f"Campaign '{campaign.title}' created!"})

@app.route('/api/delete-campaign/<int:campaign_id>', methods=['DELETE'])
def delete_campaign(campaign_id):
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized. Only Admins can delete campaigns."}), 403

    campaign = Campaign.query.get(campaign_id)
    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404

    title = campaign.title
    db.session.delete(campaign)
    db.session.commit()
    return jsonify({"message": f"Campaign '{title}' deleted."})

@app.route('/api/donate', methods=['POST'])
def donate():
    if 'user_id' not in session:
        return jsonify({"error": "Please log in to make a donation."}), 401

    data = request.get_json()
    campaign_id = data.get('campaign_id')
    amount = float(data.get('amount', 0))

    if amount <= 0:
        return jsonify({"error": "Enter a valid donation amount."}), 400

    campaign = Campaign.query.get(campaign_id)
    if not campaign:
        return jsonify({"error": "Campaign not found."}), 404

    ngo = NGO.query.get(campaign.ngo_id)
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    
    receipt_no = f"REC-{uuid.uuid4().hex[:8].upper()}"
    raw_hash_data = f"{campaign_id}-{amount}-{receipt_no}-{now_str}-{uuid.uuid4()}"
    txn_hash = "0x" + hashlib.sha256(raw_hash_data.encode('utf-8')).hexdigest()

    campaign.escrow_balance += amount
    donation = Donation(
        campaign_id=campaign.id,
        user_id=session.get('user_id'),
        amount=amount,
        receipt_no=receipt_no,
        txn_hash=txn_hash,
        timestamp=now_str
    )
    db.session.add(donation)
    db.session.commit()

    return jsonify({
        "status": "Payment Submitted",
        "receipt_no": receipt_no,
        "txn_hash": txn_hash,
        "amount": amount,
        "timestamp": now_str,
        "campaign_title": campaign.title,
        "ngo_name": ngo.name if ngo else "N/A"
    })

@app.route('/api/donations', methods=['GET'])
def get_donations():
    donations = Donation.query.order_by(Donation.id.desc()).all()
    results = []
    for d in donations:
        campaign = Campaign.query.get(d.campaign_id)
        user = User.query.get(d.user_id) if d.user_id else None
        results.append({
            "id": d.id,
            "donor_name": user.username if user else "Anonymous",
            "campaign_title": campaign.title if campaign else "Archived Campaign",
            "amount": d.amount,
            "receipt_no": d.receipt_no or "N/A",
            "txn_hash": d.txn_hash or "N/A",
            "timestamp": d.timestamp
        })
    return jsonify(results)

@app.route('/api/submit-proof', methods=['POST'])
def submit_proof():
    data = request.get_json()
    milestone = Milestone.query.get(data.get('milestone_id'))
    if not milestone:
        return jsonify({"error": "Milestone not found"}), 404

    milestone.proof_url = data.get('proof_url')
    milestone.status = "PROOF_SUBMITTED"
    db.session.commit()
    return jsonify({"message": "Proof of work submitted."})

@app.route('/api/release-funds', methods=['POST'])
def release_funds():
    if session.get('role') != 'admin':
        return jsonify({"error": "Unauthorized. Only Admins can approve & release funds."}), 403

    data = request.get_json()
    milestone = Milestone.query.get(data.get('milestone_id'))
    if not milestone:
        return jsonify({"error": "Milestone not found"}), 404

    campaign = Campaign.query.get(milestone.campaign_id)
    ngo = NGO.query.get(campaign.ngo_id) if campaign else None
    vendor = Vendor.query.get(milestone.vendor_id) if milestone.vendor_id else None

    if milestone.status != "PROOF_SUBMITTED":
        return jsonify({"error": "Proof of work must be submitted first."}), 400

    if campaign and campaign.escrow_balance < milestone.target_amount:
        return jsonify({"error": f"Insufficient Escrow balance. Needs: ${milestone.target_amount:,.2f}."}), 400

    if campaign:
        campaign.escrow_balance -= milestone.target_amount
    if vendor:
        vendor.balance += milestone.target_amount
    if ngo:
        ngo.reputation_score += 15

    milestone.status = "RELEASED"
    db.session.commit()
    return jsonify({"message": f"${milestone.target_amount:,.2f} released to vendor!"})

if __name__ == '__main__':
    seed_database()
    app.run(debug=True)