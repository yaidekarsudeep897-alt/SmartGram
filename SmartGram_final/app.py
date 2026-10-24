import csv
import io
import os
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, abort, flash, g, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DATABASE_DIR = BASE_DIR / 'database'
DATABASE_PATH = DATABASE_DIR / 'smartgram.db'
UPLOAD_DIR = BASE_DIR / 'uploads'
DATA_PATH = BASE_DIR / 'data' / 'karnataka_gram_panchayats.csv'
DATABASE_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SMARTGRAM_SECRET_KEY', 'dev-only-change-this-secret-key')
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = str(UPLOAD_DIR)
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}

CATEGORIES = ['Water Supply', 'Roads', 'Electricity', 'Sanitation', 'Waste Management', 'Healthcare', 'Education', 'Agriculture', 'Public Safety', 'Other']
STATUSES = ['Pending', 'Under Review', 'Assigned', 'In Progress', 'Resolved', 'Rejected']
KEYWORDS = {
    'Water Supply': ['water', 'tap', 'pipeline', 'drinking', 'tank', 'leak', 'borewell'],
    'Roads': ['road', 'pothole', 'street', 'bridge', 'footpath'],
    'Electricity': ['electricity', 'power', 'current', 'transformer', 'streetlight', 'street light'],
    'Sanitation': ['drainage', 'sewage', 'toilet', 'sanitation', 'overflow'],
    'Waste Management': ['garbage', 'waste', 'dustbin', 'plastic', 'rubbish', 'collection'],
    'Healthcare': ['hospital', 'health', 'medicine', 'clinic', 'doctor', 'phc'],
    'Education': ['school', 'teacher', 'student', 'classroom', 'college'],
    'Agriculture': ['farmer', 'crop', 'agriculture', 'irrigation', 'fertilizer'],
    'Public Safety': ['unsafe', 'danger', 'animal', 'open manhole', 'accident', 'harassment'],
}

def db():
    con = sqlite3.connect(DATABASE_PATH)
    con.row_factory = sqlite3.Row
    return con
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE_PATH, timeout=20)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    connection = g.pop('db', None)
    if connection is not None:
        connection.close()


def classify_complaint(title, description):
    """Transparent keyword-based classification suitable for a student demo, not a trained AI model."""
    text = f'{title} {description}'.lower()
    scores = {category: sum(1 for keyword in words if keyword in text) for category, words in KEYWORDS.items()}
    category = max(scores, key=scores.get) if scores else 'Other'
    if not scores or scores[category] == 0:
        category = 'Other'
    urgent_terms = ['emergency', 'danger', 'urgent', 'accident', 'open manhole', 'live wire', 'contamination', 'unsafe']
    priority = 'High' if any(term in text for term in urgent_terms) else ('Medium' if category != 'Other' else 'Low')
    return category, priority


def init_db():
    con = sqlite3.connect(DATABASE_PATH)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys = ON')
    con.executescript('''
    CREATE TABLE IF NOT EXISTS gram_panchayats (
      id INTEGER PRIMARY KEY AUTOINCREMENT, lgd_code TEXT NOT NULL UNIQUE,
      name TEXT NOT NULL, district TEXT NOT NULL, taluk TEXT NOT NULL,
      state TEXT NOT NULL DEFAULT 'Karnataka', active INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
      phone TEXT DEFAULT '', password TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'citizen',
      department TEXT DEFAULT '', gp_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(gp_id) REFERENCES gram_panchayats(id)
    );
    CREATE TABLE IF NOT EXISTS complaints (
      id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_no TEXT NOT NULL UNIQUE,
      user_id INTEGER NOT NULL, gp_id INTEGER NOT NULL, title TEXT NOT NULL,
      description TEXT NOT NULL, category TEXT NOT NULL, priority TEXT NOT NULL DEFAULT 'Medium',
      location TEXT DEFAULT '', image TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'Pending',
      assigned_to INTEGER, officer_note TEXT DEFAULT '', admin_note TEXT DEFAULT '', public_visible INTEGER NOT NULL DEFAULT 0,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(user_id) REFERENCES users(id), FOREIGN KEY(gp_id) REFERENCES gram_panchayats(id),
      FOREIGN KEY(assigned_to) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS feedback (
      id INTEGER PRIMARY KEY AUTOINCREMENT, complaint_id INTEGER NOT NULL UNIQUE,
      user_id INTEGER NOT NULL, rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
      comment TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(complaint_id) REFERENCES complaints(id), FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS projects (
      id INTEGER PRIMARY KEY AUTOINCREMENT, gp_id INTEGER, name TEXT NOT NULL,
      description TEXT DEFAULT '', location TEXT DEFAULT '', budget REAL DEFAULT 0,
      start_date TEXT DEFAULT '', end_date TEXT DEFAULT '', progress INTEGER DEFAULT 0,
      status TEXT DEFAULT 'Planned', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(gp_id) REFERENCES gram_panchayats(id)
    );
    CREATE TABLE IF NOT EXISTS schemes (
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT DEFAULT '',
      eligibility TEXT DEFAULT '', benefits TEXT DEFAULT '', documents TEXT DEFAULT '', link TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS announcements (
      id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, content TEXT NOT NULL,
      gp_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(gp_id) REFERENCES gram_panchayats(id)
    );
    CREATE TABLE IF NOT EXISTS budgets (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      gp_id INTEGER,
      financial_year TEXT NOT NULL DEFAULT '',
      category TEXT NOT NULL,
      source TEXT DEFAULT '',
      allocated REAL NOT NULL DEFAULT 0,
      spent REAL NOT NULL DEFAULT 0,
      notes TEXT DEFAULT '',
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(gp_id) REFERENCES gram_panchayats(id)
    );
    CREATE TABLE IF NOT EXISTS wards (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      gp_id INTEGER,
      name TEXT NOT NULL,
      issues TEXT DEFAULT '',
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(gp_id) REFERENCES gram_panchayats(id)
    );
    CREATE INDEX IF NOT EXISTS idx_complaints_gp ON complaints(gp_id, status);
    CREATE INDEX IF NOT EXISTS idx_complaints_user ON complaints(user_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_users_gp_role ON users(gp_id, role);
    CREATE TABLE IF NOT EXISTS support_votes (
      id INTEGER PRIMARY KEY AUTOINCREMENT, complaint_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(complaint_id,user_id),
      FOREIGN KEY(complaint_id) REFERENCES complaints(id) ON DELETE CASCADE,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS notifications (
      id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, complaint_id INTEGER,
      title TEXT NOT NULL, message TEXT NOT NULL, read_at TEXT DEFAULT NULL,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY(complaint_id) REFERENCES complaints(id) ON DELETE SET NULL
    );
    CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id,read_at,created_at);
    CREATE TABLE IF NOT EXISTS schools (
      id INTEGER PRIMARY KEY AUTOINCREMENT, gp_id INTEGER NOT NULL, name TEXT NOT NULL,
      school_type TEXT NOT NULL DEFAULT 'Government', address TEXT DEFAULT '',
      facilities TEXT DEFAULT '', contact TEXT DEFAULT '', active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(gp_id) REFERENCES gram_panchayats(id)
    );
    CREATE TABLE IF NOT EXISTS school_issues (
      id INTEGER PRIMARY KEY AUTOINCREMENT, school_id INTEGER NOT NULL, gp_id INTEGER NOT NULL,
      user_id INTEGER NOT NULL, category TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL,
      image TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'Pending', officer_note TEXT DEFAULT '',
      created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(school_id) REFERENCES schools(id), FOREIGN KEY(gp_id) REFERENCES gram_panchayats(id),
      FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS school_funds (
      id INTEGER PRIMARY KEY AUTOINCREMENT, school_id INTEGER NOT NULL, gp_id INTEGER NOT NULL,
      project_title TEXT NOT NULL, financial_year TEXT NOT NULL, source TEXT DEFAULT '',
      allocated REAL NOT NULL DEFAULT 0, spent REAL NOT NULL DEFAULT 0, status TEXT DEFAULT 'Planned',
      notes TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(school_id) REFERENCES schools(id), FOREIGN KEY(gp_id) REFERENCES gram_panchayats(id)
    );
    CREATE TABLE IF NOT EXISTS school_feedback (
      id INTEGER PRIMARY KEY AUTOINCREMENT, issue_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
      rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5), comment TEXT DEFAULT '',
      created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(issue_id,user_id),
      FOREIGN KEY(issue_id) REFERENCES school_issues(id), FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE INDEX IF NOT EXISTS idx_school_issues_gp ON school_issues(gp_id,status);

    CREATE INDEX IF NOT EXISTS idx_support_votes_complaint ON support_votes(complaint_id);
    ''')
    # Safe migrations from earlier SmartGram versions.
    user_cols = {r['name'] for r in con.execute('PRAGMA table_info(users)').fetchall()}
    if 'department' not in user_cols:
        con.execute("ALTER TABLE users ADD COLUMN department TEXT DEFAULT ''")
    if 'gp_id' not in user_cols:
        con.execute('ALTER TABLE users ADD COLUMN gp_id INTEGER')
    complaint_cols = {r['name'] for r in con.execute('PRAGMA table_info(complaints)').fetchall()}
    # Existing older schemas are preserved, but this fresh rebuild is designed to create the new schema.
    for col, definition in [('ticket_no', "TEXT NOT NULL DEFAULT ''"), ('gp_id', 'INTEGER'), ('officer_note', "TEXT DEFAULT ''"), ('admin_note', "TEXT DEFAULT ''"), ('public_visible', 'INTEGER NOT NULL DEFAULT 0')]:
        if col not in complaint_cols:
            con.execute(f'ALTER TABLE complaints ADD COLUMN {col} {definition}')
    con.commit()

    gp_count = con.execute('SELECT COUNT(*) AS n FROM gram_panchayats').fetchone()['n']
    if gp_count == 0 and DATA_PATH.exists():
        with DATA_PATH.open('r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            rows = []
            for row in reader:
                code = (row.get('lgd_code') or '').strip()
                name = (row.get('name') or '').strip()
                district = (row.get('district') or '').strip()
                taluk = (row.get('taluk') or '').strip()
                if code and name and district and taluk:
                    rows.append((code, name, district, taluk))
            con.executemany('INSERT OR IGNORE INTO gram_panchayats(lgd_code,name,district,taluk) VALUES(?,?,?,?)', rows)
    if con.execute('SELECT COUNT(*) AS n FROM gram_panchayats').fetchone()['n'] == 0:
        con.execute("INSERT INTO gram_panchayats(lgd_code,name,district,taluk) VALUES('DEMO-001','Demo Gram Panchayat','Dakshina Kannada','Mangaluru')")

    # Seed safe-to-reset demo data only when absent. These accounts are for local demo use.
    if not con.execute("SELECT 1 FROM users WHERE email='admin@smartgram.local'").fetchone():
        con.execute('INSERT INTO users(name,email,phone,password,role) VALUES(?,?,?,?,?)', ('SmartGram Administrator', 'admin@smartgram.local', '', generate_password_hash('admin12345'), 'admin'))
    # Seed a local demo officer against the first directory entry so Official login can be tested immediately.
    demo_gp = con.execute('SELECT id,name,district,taluk FROM gram_panchayats WHERE active=1 ORDER BY district,taluk,name LIMIT 1').fetchone()
    if demo_gp and not con.execute("SELECT 1 FROM users WHERE email='officer@smartgram.local'").fetchone():
        con.execute('INSERT INTO users(name,email,phone,password,role,department,gp_id) VALUES(?,?,?,?,?,?,?)', ('Demo GP Officer', 'officer@smartgram.local', '', generate_password_hash('officer12345'), 'officer', 'Village Development', demo_gp['id']))
    if con.execute('SELECT COUNT(*) AS n FROM schemes').fetchone()['n'] == 0:
        con.executemany('INSERT INTO schemes(name,description,eligibility,benefits,documents) VALUES(?,?,?,?,?)', [
            ('PM-KISAN', 'Financial support scheme information for eligible farmer families.', 'Eligible farmer families; confirm current official rules.', 'Income support as defined by the scheme.', 'Aadhaar and bank details, subject to official requirements.'),
            ('PMAY-G', 'Rural housing assistance information.', 'Eligible rural households under current selection rules.', 'Housing assistance as per scheme rules.', 'Identity and residence proof as required by authorities.'),
            ('Ayushman Bharat', 'Health coverage information for eligible beneficiaries.', 'Eligibility depends on the applicable beneficiary list.', 'Health coverage according to current scheme rules.', 'Check the official portal for current requirements.')])
    if con.execute('SELECT COUNT(*) AS n FROM announcements').fetchone()['n'] == 0:
        con.execute('INSERT INTO announcements(title,content) VALUES(?,?)', ('Welcome to SmartGram', 'Use this portal to submit village issues and follow their progress.'))

    # Add optional GPS columns for the Village Problem Map.
    complaint_cols = {r['name'] for r in con.execute('PRAGMA table_info(complaints)').fetchall()}
    if 'latitude' not in complaint_cols:
        con.execute('ALTER TABLE complaints ADD COLUMN latitude REAL')
    if 'longitude' not in complaint_cols:
        con.execute('ALTER TABLE complaints ADD COLUMN longitude REAL')
    # New modules: scheme eligibility checks and development quality inspections.
    con.executescript('''
    CREATE TABLE IF NOT EXISTS scheme_checks (
      id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
      age INTEGER, occupation TEXT NOT NULL, income_range TEXT NOT NULL,
      category TEXT NOT NULL, results TEXT NOT NULL DEFAULT '',
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS inspections (
      id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
      gp_id INTEGER, officer_id INTEGER NOT NULL, inspection_date TEXT NOT NULL,
      result TEXT NOT NULL, findings TEXT NOT NULL, corrective_action TEXT DEFAULT '',
      followup_date TEXT DEFAULT '', photo_filename TEXT DEFAULT '',
      public_visible INTEGER NOT NULL DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
      FOREIGN KEY(gp_id) REFERENCES gram_panchayats(id),
      FOREIGN KEY(officer_id) REFERENCES users(id)
    );
    CREATE INDEX IF NOT EXISTS idx_inspections_project ON inspections(project_id, inspection_date);
    ''')
    con.commit()
    con.close()


def login_required(*roles):
    if not session.get('user_id'):
        return False
    return not roles or session.get('role') in roles


def current_gp_id():
    return session.get('gp_id')


def notify_user(user_id, title, message, complaint_id=None):
    """Add an in-app notification; callers decide when a real event occurs."""
    get_db().execute('INSERT INTO notifications(user_id,complaint_id,title,message) VALUES(?,?,?,?)',
                     (user_id, complaint_id, title, message))


def allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


@app.context_processor
def inject_globals():
    unread_count = 0
    if session.get('user_id'):
        unread_count = get_db().execute('SELECT COUNT(*) n FROM notifications WHERE user_id=? AND read_at IS NULL', (session['user_id'],)).fetchone()['n']
    return {'current_user': session.get('name'), 'current_role': session.get('role'), 'is_logged_in': bool(session.get('user_id')), 'unread_count': unread_count}


@app.route('/')
def home():
    con = get_db()
    districts = [r['district'] for r in con.execute('SELECT DISTINCT district FROM gram_panchayats WHERE active=1 ORDER BY district')]
    gps = [dict(r) for r in con.execute('SELECT id,name,district,taluk FROM gram_panchayats WHERE active=1 ORDER BY district,taluk,name LIMIT 10000')]
    return render_template('index.html', districts=districts, gram_panchayats=gps)


@app.route('/login', methods=['POST'])
def login():
    role = request.form.get('role', 'citizen')
    if role not in ('citizen', 'officer'):
        flash('Choose Citizen or Official login.', 'error')
        return redirect(url_for('home'))
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    gp_id = request.form.get('gp_id', '').strip()
    if not gp_id:
        flash('Please select your district and Gram Panchayat first.', 'error')
        return redirect(url_for('home'))
    con = get_db()
    gp = con.execute('SELECT id,district FROM gram_panchayats WHERE id=? AND active=1', (gp_id,)).fetchone()
    user = con.execute('SELECT * FROM users WHERE email=? AND role=?', (email, role)).fetchone()
    if not gp or not user or not check_password_hash(user['password'], password):
        flash('Email or password is incorrect for the selected login type.', 'error')
        return redirect(url_for('home'))
    if role == 'officer' and str(user['gp_id'] or '') != str(gp_id):
        flash('This official account is not assigned to the selected Gram Panchayat.', 'error')
        return redirect(url_for('home'))
    if role == 'citizen' and user['gp_id'] and str(user['gp_id']) != str(gp_id):
        flash('Choose the Gram Panchayat linked to your citizen account.', 'error')
        return redirect(url_for('home'))
    session.clear()
    session.update(user_id=user['id'], name=user['name'], role=user['role'], gp_id=user['gp_id'], email=user['email'])
    if role == 'officer':
        return redirect(url_for('officer_dashboard'))
    return redirect(url_for('citizen_dashboard'))


@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        con = get_db()
        user = con.execute("SELECT * FROM users WHERE email=? AND role='admin'", (email,)).fetchone()
        if user and check_password_hash(user['password'], request.form.get('password', '')):
            session.clear(); session.update(user_id=user['id'], name=user['name'], role='admin', email=user['email'])
            return redirect(url_for('admin_dashboard'))
        flash('Invalid administrator credentials.', 'error')
    return render_template('admin_login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    con = get_db()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        gp_id = request.form.get('gp_id', '').strip()
        if not name or not email or len(password) < 8 or not gp_id:
            flash('Complete all required fields and use a password of at least 8 characters.', 'error')
        elif not con.execute('SELECT id FROM gram_panchayats WHERE id=? AND active=1', (gp_id,)).fetchone():
            flash('Please select a valid Gram Panchayat.', 'error')
        else:
            try:
                con.execute("INSERT INTO users(name,email,phone,password,role,gp_id) VALUES(?,?,?,?, 'citizen',?)", (name, email, phone, generate_password_hash(password), gp_id))
                con.commit(); flash('Account created. You can now sign in.', 'success'); return redirect(url_for('home'))
            except sqlite3.IntegrityError:
                flash('That email address is already registered.', 'error')
    districts = [r['district'] for r in con.execute('SELECT DISTINCT district FROM gram_panchayats WHERE active=1 ORDER BY district')]
    gps = [dict(r) for r in con.execute('SELECT id,name,district,taluk FROM gram_panchayats WHERE active=1 ORDER BY district,taluk,name')]
    return render_template('register.html', districts=districts, gram_panchayats=gps)


@app.route('/logout')
def logout():
    session.clear(); flash('You have been signed out.', 'success'); return redirect(url_for('home'))


@app.route('/citizen')
def citizen_dashboard():
    if not login_required('citizen'):
        return redirect(url_for('home'))
    con = get_db(); uid = session['user_id']; gp_id = current_gp_id()
    stats = {
        'total': con.execute('SELECT COUNT(*) n FROM complaints WHERE user_id=?', (uid,)).fetchone()['n'],
        'open': con.execute("SELECT COUNT(*) n FROM complaints WHERE user_id=? AND status NOT IN ('Resolved','Rejected')", (uid,)).fetchone()['n'],
        'resolved': con.execute("SELECT COUNT(*) n FROM complaints WHERE user_id=? AND status='Resolved'", (uid,)).fetchone()['n'],
    }
    recent = con.execute('SELECT c.*,g.name gp_name FROM complaints c JOIN gram_panchayats g ON g.id=c.gp_id WHERE c.user_id=? ORDER BY c.id DESC LIMIT 5', (uid,)).fetchall()
    announcements = con.execute('SELECT a.*,g.name gp_name FROM announcements a LEFT JOIN gram_panchayats g ON g.id=a.gp_id WHERE a.gp_id IS NULL OR a.gp_id=? ORDER BY a.id DESC LIMIT 4', (gp_id,)).fetchall()
    projects = con.execute('SELECT * FROM projects WHERE gp_id IS NULL OR gp_id=? ORDER BY id DESC LIMIT 3', (gp_id,)).fetchall()
    return render_template('citizen_dashboard.html', stats=stats, recent=recent, announcements=announcements, projects=projects)


@app.route('/report', methods=['GET', 'POST'])
def report_complaint():
    if not login_required('citizen'):
        return redirect(url_for('home'))
    con = get_db()
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        location = request.form.get('location', '').strip()
        gp_id = request.form.get('gp_id', '').strip()
        image = request.files.get('image')
        if not title or not description or not gp_id:
            flash('Title, description and Gram Panchayat are required.', 'error')
        elif not con.execute('SELECT id FROM gram_panchayats WHERE id=? AND active=1', (gp_id,)).fetchone():
            flash('Please choose a valid Gram Panchayat.', 'error')
        elif image and image.filename and not allowed_image(image.filename):
            flash('Upload a JPG, PNG or WEBP image only.', 'error')
        else:
            category, priority = classify_complaint(title, description)
            filename = ''
            if image and image.filename:
                ext = image.filename.rsplit('.', 1)[1].lower()
                filename = f'{uuid.uuid4().hex}.{ext}'
                image.save(UPLOAD_DIR / secure_filename(filename))
            # Keep the citizen profile linked to the GP explicitly selected for this complaint.
            con.execute('UPDATE users SET gp_id=? WHERE id=?', (gp_id, session['user_id']))
            ticket = 'SG-' + datetime.now().strftime('%y%m%d') + '-' + uuid.uuid4().hex[:6].upper()
            public_visible = 1 if request.form.get('public_visible') == 'yes' else 0

            cur = con.execute(
                '''INSERT INTO complaints
                   (ticket_no, user_id, gp_id, title, description, category,
                    priority, location, image, status, public_visible, latitude, longitude)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?, ?, ?)''',
                (
                    ticket, session['user_id'], gp_id, title, description,
                    category, priority, location, filename, public_visible,
                    request.form.get('latitude') or None,
                    request.form.get('longitude') or None
                )
            )
            notify_user(
                session['user_id'], 'Complaint received',
                f'Your complaint {ticket} has been registered. Suggested category: {category}.',
                cur.lastrowid
            )
            con.commit()
            flash(f'Complaint submitted successfully. Your tracking number is {ticket}. Category: {category}; priority: {priority}.', 'success')
            return redirect(url_for('my_complaints'))
    gps = con.execute('SELECT id,name,district,taluk FROM gram_panchayats WHERE active=1 ORDER BY district,taluk,name').fetchall()
    return render_template('report.html', gram_panchayats=gps, categories=CATEGORIES)


@app.route('/my-complaints')
def my_complaints():
    if not login_required('citizen'):
        return redirect(url_for('home'))
    rows = get_db().execute('SELECT c.*,g.name gp_name FROM complaints c JOIN gram_panchayats g ON g.id=c.gp_id WHERE c.user_id=? ORDER BY c.id DESC', (session['user_id'],)).fetchall()
    return render_template('my_complaints.html', complaints=rows)


@app.route('/complaint/<int:complaint_id>', methods=['GET', 'POST'])
def complaint_detail(complaint_id):
    if not session.get('user_id'):
        return redirect(url_for('home'))
    con = get_db()
    row = con.execute('SELECT c.*,g.name gp_name,g.district,g.taluk,u.name citizen_name,o.name officer_name FROM complaints c JOIN gram_panchayats g ON g.id=c.gp_id JOIN users u ON u.id=c.user_id LEFT JOIN users o ON o.id=c.assigned_to WHERE c.id=?', (complaint_id,)).fetchone()
    if not row:
        abort(404)
    if session['role'] == 'citizen' and row['user_id'] != session['user_id']:
        abort(403)
    if session['role'] == 'officer' and (row['assigned_to'] != session['user_id'] or row['gp_id'] != session.get('gp_id')):
        abort(403)
    if request.method == 'POST':
        if session['role'] != 'citizen' or row['status'] != 'Resolved':
            abort(403)
        rating = request.form.get('rating', '5')
        try: rating = int(rating)
        except ValueError: rating = 0
        if rating not in range(1, 6):
            flash('Choose a rating from 1 to 5.', 'error')
        else:
            try:
                con.execute('INSERT INTO feedback(complaint_id,user_id,rating,comment) VALUES(?,?,?,?)', (complaint_id, session['user_id'], rating, request.form.get('comment', '').strip()))
                con.commit(); flash('Thank you for your feedback.', 'success')
            except sqlite3.IntegrityError:
                flash('Feedback has already been submitted for this complaint.', 'error')
        return redirect(url_for('complaint_detail', complaint_id=complaint_id))
    feedback = con.execute('SELECT * FROM feedback WHERE complaint_id=?', (complaint_id,)).fetchone()
    return render_template('complaint_detail.html', complaint=row, feedback=feedback)


@app.route('/officer')
def officer_dashboard():
    if not login_required('officer'):
        return redirect(url_for('home'))
    con = get_db(); gp_id = current_gp_id(); uid = session['user_id']
    stats = {
        'assigned': con.execute('SELECT COUNT(*) n FROM complaints WHERE gp_id=? AND assigned_to=?', (gp_id, uid)).fetchone()['n'],
        'pending': con.execute("SELECT COUNT(*) n FROM complaints WHERE gp_id=? AND assigned_to=? AND status IN ('Pending','Under Review','Assigned')", (gp_id, uid)).fetchone()['n'],
        'resolved': con.execute("SELECT COUNT(*) n FROM complaints WHERE gp_id=? AND assigned_to=? AND status='Resolved'", (gp_id, uid)).fetchone()['n'],
    }
    rows = con.execute('SELECT c.*,u.name citizen_name FROM complaints c JOIN users u ON u.id=c.user_id WHERE c.gp_id=? AND c.assigned_to=? ORDER BY CASE c.priority WHEN \'High\' THEN 0 WHEN \'Medium\' THEN 1 ELSE 2 END,c.id DESC', (gp_id, uid)).fetchall()
    gp = con.execute('SELECT * FROM gram_panchayats WHERE id=?', (gp_id,)).fetchone()
    return render_template('officer_dashboard.html', stats=stats, complaints=rows, gp=gp)


@app.route('/officer/complaint/<int:complaint_id>', methods=['POST'])
def officer_update_complaint(complaint_id):
    if not login_required('officer'):
        return redirect(url_for('home'))
    status = request.form.get('status', '')
    if status not in STATUSES:
        flash('Invalid status selected.', 'error'); return redirect(url_for('officer_dashboard'))
    con = get_db()
    before = con.execute('SELECT status,user_id,ticket_no FROM complaints WHERE id=? AND gp_id=? AND assigned_to=?', (complaint_id, current_gp_id(), session['user_id'])).fetchone()
    result = con.execute('UPDATE complaints SET status=?,officer_note=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND gp_id=? AND assigned_to=?',
                         (status, request.form.get('officer_note', '').strip(), complaint_id, current_gp_id(), session['user_id']))
    if result.rowcount and before and before['status'] != status:
        notify_user(before['user_id'], 'Complaint status updated', f'{before["ticket_no"]} is now marked: {status}.', complaint_id)
    con.commit()
    if result.rowcount:
        flash('Complaint status updated.', 'success')
    else:
        flash('This complaint is not assigned to your account.', 'error')
    return redirect(url_for('officer_dashboard'))


@app.route('/admin')
def admin_dashboard():
    if not login_required('admin'):
        return redirect(url_for('admin_login'))
    con = get_db()
    stats = {
        'citizens': con.execute("SELECT COUNT(*) n FROM users WHERE role='citizen'").fetchone()['n'],
        'officers': con.execute("SELECT COUNT(*) n FROM users WHERE role='officer'").fetchone()['n'],
        'complaints': con.execute('SELECT COUNT(*) n FROM complaints').fetchone()['n'],
        'open': con.execute("SELECT COUNT(*) n FROM complaints WHERE status NOT IN ('Resolved','Rejected')").fetchone()['n'],
        'resolved': con.execute("SELECT COUNT(*) n FROM complaints WHERE status='Resolved'").fetchone()['n'],
        'gps': con.execute('SELECT COUNT(*) n FROM gram_panchayats WHERE active=1').fetchone()['n'],
    }
    recent = con.execute('SELECT c.*,u.name citizen_name,g.name gp_name,o.name officer_name FROM complaints c JOIN users u ON u.id=c.user_id JOIN gram_panchayats g ON g.id=c.gp_id LEFT JOIN users o ON o.id=c.assigned_to ORDER BY c.id DESC LIMIT 12').fetchall()
    return render_template('admin_dashboard.html', stats=stats, complaints=recent)


@app.route('/admin/complaints', methods=['GET', 'POST'])
def admin_complaints():
    if not login_required('admin'):
        return redirect(url_for('admin_login'))
    con = get_db()
    if request.method == 'POST':
        complaint_id = request.form.get('complaint_id', '')
        status = request.form.get('status', '')
        assigned_to = request.form.get('assigned_to', '').strip() or None
        if status not in STATUSES:
            flash('Choose a valid complaint status.', 'error')
        else:
            complaint = con.execute('SELECT gp_id FROM complaints WHERE id=?', (complaint_id,)).fetchone()
            officer = con.execute("SELECT id,gp_id FROM users WHERE id=? AND role='officer'", (assigned_to,)).fetchone() if assigned_to else None
            if not complaint:
                flash('Complaint not found.', 'error')
            elif assigned_to and (not officer or officer['gp_id'] != complaint['gp_id']):
                flash('Assign this complaint only to an officer from the same Gram Panchayat.', 'error')
            else:
                before = con.execute('SELECT status,user_id,ticket_no FROM complaints WHERE id=?', (complaint_id,)).fetchone()
                con.execute('UPDATE complaints SET status=?,assigned_to=?,admin_note=?,updated_at=CURRENT_TIMESTAMP WHERE id=?', (status, assigned_to, request.form.get('admin_note', '').strip(), complaint_id))
                if before and before['status'] != status:
                    notify_user(before['user_id'], 'Complaint status updated', f'{before["ticket_no"]} is now marked: {status}.', int(complaint_id))
                con.commit(); flash('Complaint record updated.', 'success')
    district_filter = request.args.get('district', '').strip()
    gp_filter = request.args.get('gp_id', '').strip()
    status_filter = request.args.get('status', '').strip()
    clauses, params = [], []
    if district_filter:
        clauses.append('g.district=?'); params.append(district_filter)
    if gp_filter:
        clauses.append('c.gp_id=?'); params.append(gp_filter)
    if status_filter in STATUSES:
        clauses.append('c.status=?'); params.append(status_filter)
    where_sql = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
    rows = con.execute('SELECT c.*,u.name citizen_name,g.name gp_name,g.district,o.name officer_name FROM complaints c JOIN users u ON u.id=c.user_id JOIN gram_panchayats g ON g.id=c.gp_id LEFT JOIN users o ON o.id=c.assigned_to' + where_sql + ' ORDER BY c.id DESC', params).fetchall()
    officers = con.execute("SELECT u.id,u.name,u.email,u.gp_id,g.name gp_name FROM users u LEFT JOIN gram_panchayats g ON g.id=u.gp_id WHERE u.role='officer' ORDER BY g.district,g.name,u.name").fetchall()
    districts = con.execute('SELECT DISTINCT district FROM gram_panchayats WHERE active=1 ORDER BY district').fetchall()
    gps = con.execute('SELECT id,name,district FROM gram_panchayats WHERE active=1 ORDER BY district,name').fetchall()
    return render_template('admin_complaints.html', complaints=rows, officers=officers, statuses=STATUSES, districts=districts, gram_panchayats=gps, selected_district=district_filter, selected_gp=gp_filter, selected_status=status_filter)


@app.route('/admin/export/complaints.csv')
def export_complaints():
    if not login_required('admin'):
        return redirect(url_for('admin_login'))
    con = get_db()
    rows = con.execute('SELECT c.ticket_no,c.title,c.description,c.category,c.priority,c.status,c.location,c.created_at,c.updated_at,u.name citizen,u.email citizen_email,g.name gram_panchayat,g.taluk,g.district,o.name assigned_officer,c.admin_note,c.officer_note FROM complaints c JOIN users u ON u.id=c.user_id JOIN gram_panchayats g ON g.id=c.gp_id LEFT JOIN users o ON o.id=c.assigned_to ORDER BY c.id DESC').fetchall()
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['Tracking ID','Title','Description','Category','Priority','Status','Location','Created At','Updated At','Citizen Name','Citizen Email','Gram Panchayat','Taluk','District','Assigned Officer','Admin Note','Officer Note'])
    for row in rows:
        writer.writerow([row[key] for key in row.keys()])
    return Response('﻿' + output.getvalue(), mimetype='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename=smartgram_complaints.csv'})


@app.route('/admin/users')
def admin_users():
    if not login_required('admin'):
        flash('Please sign in as an administrator to view registered users.', 'error')
        return redirect(url_for('admin_login'))
    con = get_db()
    users = con.execute('''
        SELECT u.id, u.name, u.email, u.phone, u.role, u.department,
               u.created_at, g.name AS gp_name, g.taluk, g.district
        FROM users u LEFT JOIN gram_panchayats g ON g.id=u.gp_id
        ORDER BY CASE u.role WHEN 'admin' THEN 0 WHEN 'officer' THEN 1 ELSE 2 END, u.name
    ''').fetchall()
    return render_template('admin_users.html', users=users)


@app.route('/admin/officers', methods=['GET', 'POST'])
def admin_officers():
    if not login_required('admin'):
        return redirect(url_for('admin_login'))
    con = get_db()
    if request.method == 'POST':
        name = request.form.get('name', '').strip(); email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', ''); gp_id = request.form.get('gp_id', '').strip()
        department = request.form.get('department', 'Village Administration').strip()
        gp = con.execute('SELECT id FROM gram_panchayats WHERE id=? AND active=1', (gp_id,)).fetchone()
        if not name or not email or len(password) < 8 or not gp:
            flash('Enter name, email, valid Gram Panchayat and password of at least 8 characters.', 'error')
        else:
            try:
                con.execute("INSERT INTO users(name,email,phone,password,role,department,gp_id) VALUES(?,?,?,?,'officer',?,?)", (name, email, request.form.get('phone', '').strip(), generate_password_hash(password), department, gp_id))
                con.commit(); flash('Official account created and linked to its Gram Panchayat.', 'success')
            except sqlite3.IntegrityError:
                flash('This email is already registered.', 'error')
    gps = con.execute('SELECT id,name,district,taluk,lgd_code FROM gram_panchayats WHERE active=1 ORDER BY district,taluk,name').fetchall()
    officers = con.execute("SELECT u.*,g.name gp_name,g.district,g.taluk FROM users u LEFT JOIN gram_panchayats g ON g.id=u.gp_id WHERE u.role='officer' ORDER BY g.district,g.name,u.name").fetchall()
    return render_template('admin_officers.html', gram_panchayats=gps, officers=officers)


@app.route('/admin/projects', methods=['GET', 'POST'])
def admin_projects():
    if not login_required('admin'):
        return redirect(url_for('admin_login'))
    con = get_db()
    if request.method == 'POST':
        try:
            progress = max(0, min(100, int(request.form.get('progress', '0'))))
            budget = max(0, float(request.form.get('budget', '0') or 0))
        except ValueError:
            flash('Enter valid budget and progress values.', 'error')
        else:
            con.execute('INSERT INTO projects(gp_id,name,description,location,budget,start_date,end_date,progress,status) VALUES(?,?,?,?,?,?,?,?,?)',
                        (request.form.get('gp_id') or None, request.form.get('name', '').strip(), request.form.get('description', '').strip(), request.form.get('location', '').strip(), budget, request.form.get('start_date', ''), request.form.get('end_date', ''), progress, request.form.get('status', 'Planned')))
            con.commit(); flash('Development project added.', 'success')
    gps = con.execute('SELECT id,name,district FROM gram_panchayats WHERE active=1 ORDER BY district,name').fetchall()
    projects = con.execute('SELECT p.*,g.name gp_name FROM projects p LEFT JOIN gram_panchayats g ON g.id=p.gp_id ORDER BY p.id DESC').fetchall()
    return render_template('admin_projects.html', projects=projects, gram_panchayats=gps)


@app.route('/projects')
def projects():
    con = get_db()
    gp_id = current_gp_id() if session.get('role') == 'citizen' else None
    rows = con.execute('SELECT p.*,g.name gp_name FROM projects p LEFT JOIN gram_panchayats g ON g.id=p.gp_id WHERE p.gp_id IS NULL OR p.gp_id=? ORDER BY p.id DESC', (gp_id,)).fetchall()
    return render_template('projects.html', projects=rows)


@app.route('/schemes')
def schemes():
    rows = get_db().execute('SELECT * FROM schemes ORDER BY name').fetchall()
    return render_template('schemes.html', schemes=rows)


@app.route('/admin/announcements', methods=['GET', 'POST'])
def admin_announcements():
    if not login_required('admin'):
        return redirect(url_for('admin_login'))
    con = get_db()
    if request.method == 'POST':
        title = request.form.get('title', '').strip(); content = request.form.get('content', '').strip()
        if title and content:
            con.execute('INSERT INTO announcements(title,content,gp_id) VALUES(?,?,?)', (title, content, request.form.get('gp_id') or None)); con.commit(); flash('Announcement published.', 'success')
        else:
            flash('Title and announcement content are required.', 'error')
    gps = con.execute('SELECT id,name,district FROM gram_panchayats WHERE active=1 ORDER BY district,name').fetchall()
    announcements = con.execute('SELECT a.*,g.name gp_name FROM announcements a LEFT JOIN gram_panchayats g ON g.id=a.gp_id ORDER BY a.id DESC').fetchall()
    return render_template('admin_announcements.html', gram_panchayats=gps, announcements=announcements)


@app.route('/village-pulse')
def village_pulse():
    # Public, privacy-conscious view of issues citizens opted to share.
    con = get_db()
    district = request.args.get('district', '').strip()
    gp_id = request.args.get('gp_id', '').strip()
    gps = con.execute('SELECT id,name,district,taluk FROM gram_panchayats WHERE active=1 ORDER BY district,taluk,name').fetchall()
    clauses = ['c.public_visible=1']
    params = []
    if district:
        clauses.append('g.district=?'); params.append(district)
    if gp_id:
        clauses.append('c.gp_id=?'); params.append(gp_id)
    where = ' AND '.join(clauses)
    issues = con.execute(f'''SELECT c.id,c.user_id,c.ticket_no,c.title,c.category,c.priority,c.status,c.location,c.created_at,
      g.name gp_name,g.district,g.taluk,COUNT(DISTINCT v.id) support_count
      FROM complaints c JOIN gram_panchayats g ON g.id=c.gp_id
      LEFT JOIN support_votes v ON v.complaint_id=c.id
      WHERE {where} GROUP BY c.id ORDER BY support_count DESC,c.id DESC LIMIT 100''', params).fetchall()
    stats_where = ' WHERE ' + ' AND '.join(clauses)
    stats = {
      'shared': con.execute('SELECT COUNT(*) n FROM complaints c JOIN gram_panchayats g ON g.id=c.gp_id' + stats_where, params).fetchone()['n'],
      'open': con.execute("SELECT COUNT(*) n FROM complaints c JOIN gram_panchayats g ON g.id=c.gp_id" + stats_where + " AND c.status NOT IN ('Resolved','Rejected')", params).fetchone()['n'],
      'resolved': con.execute("SELECT COUNT(*) n FROM complaints c JOIN gram_panchayats g ON g.id=c.gp_id" + stats_where + " AND c.status='Resolved'", params).fetchone()['n'],
    }
    voted = set()
    if session.get('role') == 'citizen':
        voted = {r['complaint_id'] for r in con.execute('SELECT complaint_id FROM support_votes WHERE user_id=?', (session['user_id'],)).fetchall()}
    districts = con.execute('SELECT DISTINCT district FROM gram_panchayats WHERE active=1 ORDER BY district').fetchall()
    return render_template('village_pulse.html', issues=issues, stats=stats, gps=gps, districts=districts,
                           selected_district=district, selected_gp=gp_id, voted=voted)


@app.route('/village-pulse/<int:complaint_id>/support', methods=['POST'])
def support_issue(complaint_id):
    if not login_required('citizen'):
        flash('Sign in as a citizen to support a community issue.', 'error')
        return redirect(url_for('home'))
    con = get_db()
    issue = con.execute('SELECT id,user_id,public_visible FROM complaints WHERE id=?', (complaint_id,)).fetchone()
    if not issue or not issue['public_visible']:
        abort(404)
    if issue['user_id'] == session['user_id']:
        flash('You cannot support your own complaint.', 'error')
    else:
        try:
            con.execute('INSERT INTO support_votes(complaint_id,user_id) VALUES(?,?)', (complaint_id, session['user_id']))
            con.commit(); flash('Your support was added. Community support helps officials see shared concerns.', 'success')
        except sqlite3.IntegrityError:
            flash('You have already supported this issue.', 'error')
    return redirect(url_for('village_pulse'))


@app.route('/notifications')
def notifications():
    if not session.get('user_id'):
        return redirect(url_for('home'))
    con = get_db()
    rows = con.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC,id DESC LIMIT 100', (session['user_id'],)).fetchall()
    con.execute('UPDATE notifications SET read_at=CURRENT_TIMESTAMP WHERE user_id=? AND read_at IS NULL', (session['user_id'],))
    con.commit()
    return render_template('notifications.html', notifications=rows)


@app.route('/directory')
def directory():
    con = get_db()
    district = request.args.get('district', '').strip()
    query = request.args.get('q', '').strip()
    page = max(1, int(request.args.get('page', 1) or 1))
    page_size = 50
    where, params = ['active=1'], []
    if district:
        where.append('district=?'); params.append(district)
    if query:
        where.append('(name LIKE ? OR taluk LIKE ? OR lgd_code LIKE ?)'); params.extend([f'%{query}%'] * 3)
    condition = ' AND '.join(where)
    total = con.execute(f'SELECT COUNT(*) n FROM gram_panchayats WHERE {condition}', params).fetchone()['n']
    rows = con.execute(f'SELECT * FROM gram_panchayats WHERE {condition} ORDER BY district,taluk,name LIMIT ? OFFSET ?', params + [page_size, (page - 1) * page_size]).fetchall()
    districts = con.execute('SELECT DISTINCT district FROM gram_panchayats WHERE active=1 ORDER BY district').fetchall()
    return render_template('directory.html', gram_panchayats=rows, districts=districts, selected_district=district, query=query, page=page, pages=max(1, (total + page_size - 1) // page_size), total=total)


@app.route('/scheme-checker', methods=['GET', 'POST'])
def scheme_checker():
    # Public visitors can check likely scheme matches; only signed-in users have checks saved.
    con = get_db()
    results = []
    if request.method == 'POST':
        try:
            age = int(request.form.get('age', '0'))
        except ValueError:
            age = 0
        occupation = request.form.get('occupation', '').strip()
        income_range = request.form.get('income_range', '').strip()
        category = request.form.get('category', '').strip()
        if not (1 <= age <= 120) or not occupation or not income_range or not category:
            flash('Please enter valid details in all required fields.', 'error')
        else:
            schemes = con.execute('SELECT * FROM schemes ORDER BY name').fetchall()
            terms = {
                'Agriculture': ('farm', 'agri', 'kisan', 'crop'),
                'Housing': ('housing', 'house', 'awas', 'home'),
                'Health': ('health', 'medical', 'ayushman'),
                'Education': ('education', 'student', 'scholarship'),
                'Employment': ('employment', 'job', 'work', 'skill'),
                'Pension and social support': ('pension', 'senior', 'widow', 'disability', 'social')
            }
            wanted = terms.get(category, ())
            for scheme in schemes:
                haystack = ' '.join([scheme['name'], scheme['description'], scheme['eligibility'], scheme['benefits']]).lower()
                if not wanted or any(term in haystack for term in wanted):
                    results.append(dict(scheme))
            if session.get('user_id'):
                con.execute('INSERT INTO scheme_checks(user_id,age,occupation,income_range,category,results) VALUES(?,?,?,?,?,?)',
                            (session['user_id'], age, occupation, income_range, category, ','.join(str(s['id']) for s in results)))
                con.commit()
            if not results:
                flash('No category match found. Browse all schemes or ask your Gram Panchayat office.', 'info')
    all_schemes = con.execute('SELECT * FROM schemes ORDER BY name').fetchall()
    return render_template('scheme_checker.html', results=results, all_schemes=all_schemes)


@app.route('/quality-inspections', methods=['GET', 'POST'])
def quality_inspections():
    # Published inspection reports are public. Recording a new report still requires an officer/admin login.
    if request.method == 'POST' and not login_required('officer', 'admin'):
        flash('Please sign in as an officer or administrator to record an inspection.', 'error')
        return redirect(url_for('admin_login') if session.get('role') != 'officer' else url_for('home'))
    con = get_db()
    if request.method == 'POST':
        if not login_required('officer', 'admin'):
            abort(403)
        project_id = request.form.get('project_id', type=int)
        inspection_date = request.form.get('inspection_date', '').strip()
        result = request.form.get('result', '').strip()
        findings = request.form.get('findings', '').strip()
        corrective_action = request.form.get('corrective_action', '').strip()
        followup_date = request.form.get('followup_date', '').strip()
        photo = request.files.get('photo')
        project = con.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone() if project_id else None
        if not project or not inspection_date or result not in ('Passed', 'Needs improvement', 'Failed') or not findings:
            flash('Select a project and complete the required inspection fields.', 'error')
        elif session.get('role') == 'officer' and project['gp_id'] != session.get('gp_id'):
            abort(403)
        else:
            filename = ''
            if photo and photo.filename:
                if not allowed_image(photo.filename):
                    flash('Upload a JPG, JPEG, PNG, or WEBP image only.', 'error')
                    return redirect(url_for('quality_inspections'))
                filename = f"inspection_{uuid.uuid4().hex}.{secure_filename(photo.filename).rsplit('.',1)[-1].lower()}"
                photo.save(UPLOAD_DIR / filename)
            gp_id = project['gp_id'] if project['gp_id'] else current_gp_id()
            con.execute("INSERT INTO inspections(project_id,gp_id,officer_id,inspection_date,result,findings, corrective_action,followup_date,photo_filename,public_visible) VALUES(?,?,?,?,?,?,?,?,?,1)",
                        (project['id'], gp_id, session['user_id'], inspection_date, result, findings,
                         corrective_action, followup_date, filename))
            con.commit()
            flash('Inspection report saved.', 'success')
            return redirect(url_for('quality_inspections'))
    if session.get('role') == 'officer':
        projects = con.execute('SELECT * FROM projects WHERE gp_id=? ORDER BY created_at DESC', (current_gp_id(),)).fetchall()
        inspections = con.execute("SELECT i.*,p.name project_name,g.name gp_name,u.name inspector_name FROM inspections i JOIN projects p ON p.id=i.project_id LEFT JOIN gram_panchayats g ON g.id=i.gp_id JOIN users u ON u.id=i.officer_id WHERE i.gp_id=? ORDER BY i.created_at DESC", (current_gp_id(),)).fetchall()
    elif session.get('role') == 'admin':
        projects = con.execute('SELECT * FROM projects ORDER BY created_at DESC').fetchall()
        inspections = con.execute("SELECT i.*,p.name project_name,g.name gp_name,u.name inspector_name FROM inspections i JOIN projects p ON p.id=i.project_id LEFT JOIN gram_panchayats g ON g.id=i.gp_id JOIN users u ON u.id=i.officer_id ORDER BY i.created_at DESC").fetchall()
    else:
        projects = []
        inspections = con.execute("SELECT i.*,p.name project_name,g.name gp_name,u.name inspector_name FROM inspections i JOIN projects p ON p.id=i.project_id LEFT JOIN gram_panchayats g ON g.id=i.gp_id JOIN users u ON u.id=i.officer_id WHERE i.public_visible=1 ORDER BY i.created_at DESC").fetchall()
    return render_template('quality_inspections.html', projects=projects, inspections=inspections)


@app.route('/schools', methods=['GET', 'POST'])
def school_directory():
    con = get_db()
    if request.method == 'POST':
        if not login_required('admin','officer'): abort(403)
        gp_id_new=request.form.get('gp_id',type=int); name=request.form.get('name','').strip()
        gp=con.execute('SELECT id FROM gram_panchayats WHERE id=? AND active=1',(gp_id_new,)).fetchone() if gp_id_new else None
        if not gp or not name: flash('Select a Gram Panchayat and enter a school name.','error')
        else:
            if session.get('role')=='officer' and gp_id_new != current_gp_id(): abort(403)
            con.execute('INSERT INTO schools(gp_id,name,school_type,address,facilities,contact) VALUES(?,?,?,?,?,?)',(gp_id_new,name,request.form.get('school_type','Government'),request.form.get('address','').strip(),request.form.get('facilities','').strip(),request.form.get('contact','').strip())); con.commit()
            flash('School added to the directory.','success'); return redirect(url_for('school_directory'))
    gp_id = request.args.get('gp_id', type=int)
    gps = con.execute('SELECT id,name,district,taluk FROM gram_panchayats WHERE active=1 ORDER BY district,taluk,name').fetchall()
    query = "SELECT s.*,g.name gp_name,g.district,g.taluk FROM schools s JOIN gram_panchayats g ON g.id=s.gp_id WHERE s.active=1"
    args = []
    if gp_id:
        query += ' AND s.gp_id=?'; args.append(gp_id)
    query += ' ORDER BY g.district,g.taluk,s.name'
    schools = con.execute(query, args).fetchall()
    return render_template('schools.html', schools=schools, gps=gps, selected_gp=gp_id)


@app.route('/school-issues', methods=['GET', 'POST'])
def school_issues():
    con = get_db()
    if request.method == 'POST':
        if not login_required('citizen'):
            flash('Please sign in with a citizen account to report a school issue.', 'error')
            return redirect(url_for('home'))
        school_id = request.form.get('school_id', type=int)
        category = request.form.get('category','').strip()
        title = request.form.get('title','').strip()
        description = request.form.get('description','').strip()
        school = con.execute('SELECT * FROM schools WHERE id=? AND active=1', (school_id,)).fetchone() if school_id else None
        allowed = {'Building/Classroom','Toilet/Sanitation','Drinking Water','Midday Meal','Furniture/Equipment','Electricity','Other'}
        if not school or category not in allowed or not title or not description:
            flash('Select a school and complete all required fields.', 'error')
        else:
            filename=''
            photo=request.files.get('photo')
            if photo and photo.filename:
                if not allowed_image(photo.filename):
                    flash('Photo must be JPG, JPEG, PNG, or WEBP.', 'error')
                    return redirect(url_for('school_issues'))
                filename=f"school_{uuid.uuid4().hex}.{secure_filename(photo.filename).rsplit('.',1)[-1].lower()}"
                photo.save(UPLOAD_DIR / filename)
            con.execute('INSERT INTO school_issues(school_id,gp_id,user_id,category,title,description,image) VALUES(?,?,?,?,?,?,?)',
                        (school['id'],school['gp_id'],session['user_id'],category,title,description,filename))
            con.commit(); flash('School issue submitted. You can track it below after signing in.', 'success')
            return redirect(url_for('school_issues'))
    gps = con.execute('SELECT id,name,district,taluk FROM gram_panchayats WHERE active=1 ORDER BY district,taluk,name').fetchall()
    schools = con.execute('SELECT s.id,s.name,s.gp_id,g.name gp_name FROM schools s JOIN gram_panchayats g ON g.id=s.gp_id WHERE s.active=1 ORDER BY g.name,s.name').fetchall()
    if session.get('role') == 'admin':
        issues = con.execute('SELECT i.*,s.name school_name,g.name gp_name,u.name reporter FROM school_issues i JOIN schools s ON s.id=i.school_id JOIN gram_panchayats g ON g.id=i.gp_id JOIN users u ON u.id=i.user_id ORDER BY i.created_at DESC').fetchall()
    elif session.get('role') == 'officer':
        issues = con.execute('SELECT i.*,s.name school_name,g.name gp_name,u.name reporter FROM school_issues i JOIN schools s ON s.id=i.school_id JOIN gram_panchayats g ON g.id=i.gp_id JOIN users u ON u.id=i.user_id WHERE i.gp_id=? ORDER BY i.created_at DESC', (current_gp_id(),)).fetchall()
    elif session.get('role') == 'citizen':
        issues = con.execute('SELECT i.*,s.name school_name,g.name gp_name,u.name reporter FROM school_issues i JOIN schools s ON s.id=i.school_id JOIN gram_panchayats g ON g.id=i.gp_id JOIN users u ON u.id=i.user_id WHERE i.user_id=? ORDER BY i.created_at DESC', (session['user_id'],)).fetchall()
    else:
        issues = con.execute("SELECT i.*,s.name school_name,g.name gp_name,u.name reporter FROM school_issues i JOIN schools s ON s.id=i.school_id JOIN gram_panchayats g ON g.id=i.gp_id JOIN users u ON u.id=i.user_id WHERE i.status='Resolved' ORDER BY i.created_at DESC LIMIT 50").fetchall()
    return render_template('school_issues.html', schools=schools, gps=gps, issues=issues)


@app.route('/school-issues/<int:issue_id>/update', methods=['POST'])
def update_school_issue(issue_id):
    if not login_required('officer','admin'):
        abort(403)
    con=get_db(); issue=con.execute('SELECT * FROM school_issues WHERE id=?',(issue_id,)).fetchone()
    if not issue: abort(404)
    if session.get('role') == 'officer' and issue['gp_id'] != current_gp_id(): abort(403)
    status=request.form.get('status','')
    note=request.form.get('officer_note','').strip()
    if status not in ('Pending','Under Review','In Progress','Resolved','Rejected'):
        flash('Invalid issue status.','error')
    else:
        con.execute('UPDATE school_issues SET status=?,officer_note=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(status,note,issue_id)); con.commit()
        flash('School issue status updated.','success')
    return redirect(url_for('school_issues'))


@app.route('/school-issues/<int:issue_id>/feedback', methods=['POST'])
def school_issue_feedback(issue_id):
    if not login_required('citizen'):
        flash('Please sign in to send feedback.','error'); return redirect(url_for('home'))
    con=get_db(); issue=con.execute("SELECT * FROM school_issues WHERE id=? AND user_id=? AND status='Resolved'",(issue_id,session['user_id'])).fetchone()
    if not issue: abort(403)
    rating=request.form.get('rating',type=int); comment=request.form.get('comment','').strip()
    if rating not in (1,2,3,4,5): flash('Choose a rating from 1 to 5.','error')
    else:
        con.execute('INSERT INTO school_feedback(issue_id,user_id,rating,comment) VALUES(?,?,?,?) ON CONFLICT(issue_id,user_id) DO UPDATE SET rating=excluded.rating,comment=excluded.comment',(issue_id,session['user_id'],rating,comment)); con.commit()
        flash('Thank you for your feedback.','success')
    return redirect(url_for('school_issues'))


@app.route('/school-funds', methods=['GET', 'POST'])
def school_funds():
    con=get_db()
    rows=con.execute('SELECT f.*,s.name school_name,g.name gp_name FROM school_funds f JOIN schools s ON s.id=f.school_id JOIN gram_panchayats g ON g.id=f.gp_id ORDER BY f.financial_year DESC,f.created_at DESC').fetchall()
    totals=con.execute('SELECT COALESCE(SUM(allocated),0) allocated,COALESCE(SUM(spent),0) spent FROM school_funds').fetchone()
    schools=con.execute('SELECT s.id,s.name,s.gp_id,g.name gp_name FROM schools s JOIN gram_panchayats g ON g.id=s.gp_id WHERE s.active=1 ORDER BY g.name,s.name').fetchall()
    if request.method == 'POST':
        if not login_required('admin','officer'): abort(403)
        school_id=request.form.get('school_id',type=int); title=request.form.get('project_title','').strip(); year=request.form.get('financial_year','').strip()
        try: allocated=float(request.form.get('allocated','0')); spent=float(request.form.get('spent','0'))
        except ValueError: allocated=-1; spent=-1
        school=con.execute('SELECT * FROM schools WHERE id=?',(school_id,)).fetchone() if school_id else None
        if not school or not title or not year or allocated < 0 or spent < 0 or spent > allocated:
            flash('Enter valid fund details; spending cannot exceed allocation.','error')
        elif session.get('role')=='officer' and school['gp_id'] != current_gp_id(): abort(403)
        else:
            con.execute('INSERT INTO school_funds(school_id,gp_id,project_title,financial_year,source,allocated,spent,status,notes) VALUES(?,?,?,?,?,?,?,?,?)',(school_id,school['gp_id'],title,year,request.form.get('source','').strip(),allocated,spent,request.form.get('status','Planned'),request.form.get('notes','').strip())); con.commit()
            flash('School development fund entry added.','success')
            return redirect(url_for('school_funds'))
    return render_template('school_funds.html',rows=rows,totals=totals,schools=schools)


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    # Uploads are only complaint evidence; use generated filenames, never user-provided paths.
    if not re.fullmatch(r'(?:[a-f0-9]{32}|school_[a-f0-9]{32}|inspection_[a-f0-9]{32})\.(jpg|jpeg|png|webp)', filename.lower()):
        abort(404)
    return send_from_directory(UPLOAD_DIR, filename)


@app.errorhandler(403)
def forbidden(_error):
    return render_template('error.html', code=403, message='You do not have permission to view this page.'), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template('error.html', code=404, message='The page you requested could not be found.'), 404


# 2. VILLAGE PROBLEM MAP
@app.route("/village-map")
def village_map():
    c = db()
    complaints = c.execute("""
        SELECT complaints.*, gram_panchayats.name AS gp_name
        FROM complaints
        LEFT JOIN gram_panchayats
          ON gram_panchayats.id = complaints.gp_id
        WHERE complaints.latitude IS NOT NULL
          AND complaints.longitude IS NOT NULL
        ORDER BY complaints.id DESC
    """).fetchall()
    c.close()
    return render_template(
        "village_map.html",
        complaints=complaints
    )


# 4. PUBLIC BUDGET TRANSPARENCY
@app.route("/public-budget")
def public_budget():
    c = db()
    rows = c.execute("""
        SELECT * FROM budgets
        ORDER BY financial_year DESC, category
    """).fetchall()

    totals = c.execute("""
        SELECT
            COALESCE(SUM(allocated), 0) AS allocated,
            COALESCE(SUM(spent), 0) AS spent
        FROM budgets
    """).fetchone()
    c.close()

    remaining = max(
        float(totals["allocated"] or 0)
        - float(totals["spent"] or 0),
        0
    )

    return render_template(
        "public_budget.html",
        rows=rows,
        totals=totals,
        remaining=remaining
    )


# 5. ADMIN-ONLY DEVELOPMENT SUGGESTIONS
@app.route("/admin/development-suggestions")
def development_suggestions():
    if not login_required('admin'):
        return redirect(url_for('admin_login'))

    c = db()

    categories = c.execute("""
        SELECT category,
               COUNT(*) AS total,
               SUM(
                   CASE
                       WHEN status NOT IN ('Resolved', 'Rejected')
                       THEN 1 ELSE 0
                   END
               ) AS open_count
        FROM complaints
        GROUP BY category
        ORDER BY open_count DESC, total DESC
    """).fetchall()

    pending = c.execute("""
        SELECT COUNT(*) AS n
        FROM complaints
        WHERE status NOT IN ('Resolved', 'Rejected')
    """).fetchone()["n"]

    unlocated = c.execute("""
        SELECT COUNT(*) AS n
        FROM complaints
        WHERE latitude IS NULL OR longitude IS NULL
    """).fetchone()["n"]

    wards = c.execute("""
        SELECT name, issues
        FROM wards
        WHERE COALESCE(issues, '') != ''
    """).fetchall()

    budgets = c.execute("""
        SELECT * FROM budgets
        WHERE allocated > 0
        ORDER BY financial_year DESC
    """).fetchall()

    projects = c.execute("""
        SELECT name, progress, status, budget
        FROM projects
        WHERE status != 'Resolved'
        ORDER BY progress ASC
    """).fetchall()

    c.close()

    suggestions = []

    for item in categories:
        if item["open_count"]:
            suggestions.append({
                "title": "Prioritise " + (item["category"] or "Other") + " issues",
                "reason": (
                    str(item["open_count"])
                    + " unresolved complaint(s) out of "
                    + str(item["total"])
                    + " recorded complaints."
                ),
                "action": (
                    "Review complaints, assign the responsible department "
                    "and publish an expected completion timeline."
                )
            })

    for ward in wards:
        suggestions.append({
            "title": "Review needs in " + ward["name"],
            "reason": "Recorded ward issues: " + ward["issues"],
            "action": (
                "Arrange a ward inspection and consider approved work "
                "in the development plan."
            )
        })

    for budget in budgets:
        allocated = float(budget["allocated"] or 0)
        spent = float(budget["spent"] or 0)

        if allocated > 0 and spent / allocated < 0.35:
            suggestions.append({
                "title": "Review " + budget["category"] + " budget",
                "reason": (
                    "Recorded expenditure is "
                    + str(round(spent / allocated * 100))
                    + "% for financial year "
                    + str(budget["financial_year"])
                    + "."
                ),
                "action": (
                    "Verify the actual work and expenditure records "
                    "before deciding whether the budget needs attention."
                )
            })

    for project in projects[:3]:
        suggestions.append({
            "title": "Review project: " + project["name"],
            "reason": (
                "Recorded progress: "
                + str(project["progress"] or 0)
                + "%; status: "
                + str(project["status"])
            ),
            "action": (
                "Ask the responsible officer for an updated milestone "
                "and expected completion date."
            )
        })

    if not suggestions:
        suggestions.append({
            "title": "Collect more village data",
            "reason": "There is not enough recorded data to rank priorities.",
            "action": (
                "Keep complaint, ward, project and budget records updated."
            )
        })

    return render_template(
        "development_suggestions.html",
        suggestions=suggestions,
        pending=pending,
        unlocated=unlocated,
        categories=categories
    )
init_db()

if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG', '0') == '1')
