import os, sqlite3, uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE=os.path.dirname(os.path.abspath(__file__))
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "database")

os.makedirs(DB_DIR, exist_ok=True)

DB = os.path.join(DB_DIR, "smartgram.db")
UPLOAD=os.path.join(BASE,'uploads')
os.makedirs(UPLOAD,exist_ok=True)
app=Flask(__name__)
app.secret_key='smartgram-change-this-key'
app.config['MAX_CONTENT_LENGTH']=5*1024*1024
def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = db()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,email TEXT UNIQUE,phone TEXT,password TEXT,role TEXT DEFAULT 'citizen',village TEXT,department TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS complaints(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,title TEXT,description TEXT,category TEXT,priority TEXT,location TEXT,image TEXT,status TEXT DEFAULT 'Pending',assigned_to INTEGER,note TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,description TEXT,location TEXT,budget REAL,start_date TEXT,end_date TEXT,progress INTEGER,status TEXT);
    CREATE TABLE IF NOT EXISTS schemes(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,description TEXT,eligibility TEXT,benefits TEXT,documents TEXT,link TEXT);
    CREATE TABLE IF NOT EXISTS announcements(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,content TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,complaint_id INTEGER,rating INTEGER,comment TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS emergency(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,department TEXT,phone TEXT,location TEXT);
    CREATE TABLE IF NOT EXISTS village_profile(id INTEGER PRIMARY KEY CHECK(id=1),village_name TEXT,gram_panchayat TEXT,taluk TEXT,district TEXT,state TEXT,pincode TEXT,population INTEGER,households INTEGER,contact TEXT,email TEXT,about TEXT);
    CREATE TABLE IF NOT EXISTS wards(id INTEGER PRIMARY KEY AUTOINCREMENT,ward_no TEXT UNIQUE,name TEXT,representative TEXT,population INTEGER,issues TEXT);
    CREATE TABLE IF NOT EXISTS officer_reports(id INTEGER PRIMARY KEY AUTOINCREMENT,officer_id INTEGER,title TEXT,report_date TEXT,location TEXT,details TEXT,status TEXT DEFAULT 'Submitted',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS meetings(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,meeting_date TEXT,location TEXT,agenda TEXT,minutes TEXT,status TEXT DEFAULT 'Scheduled');
    CREATE TABLE IF NOT EXISTS budgets(id INTEGER PRIMARY KEY AUTOINCREMENT,financial_year TEXT,category TEXT,allocated REAL,spent REAL,source TEXT,notes TEXT);
    CREATE TABLE IF NOT EXISTS village_assets(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,asset_type TEXT,location TEXT,condition_status TEXT,assigned_officer INTEGER,notes TEXT);
    ''')
    if not c.execute("select id from users where email=?",('admin@smartgram.local',)).fetchone():
        c.execute("insert into users(name,email,phone,password,role,village) values(?,?,?,?,?,?)",('SmartGram Admin','admin@smartgram.local','9999999999',generate_password_hash('admin123'),'admin','Demo Village'))
    if not c.execute("select id from users where email=?",('officer@smartgram.local',)).fetchone():
        c.execute("insert into users(name,email,phone,password,role,village,department) values(?,?,?,?,?,?,?)",('Village Officer','officer@smartgram.local','8888888888',generate_password_hash('officer123'),'officer','Demo Village','Village Development'))
    if c.execute('select count(*) n from projects').fetchone()['n']==0:
        c.executemany('insert into projects(name,description,location,budget,start_date,end_date,progress,status) values(?,?,?,?,?,?,?,?)',[
        ('Main Road Improvement','Repair damaged road sections and drainage.','Main Road',850000,'2026-01-10','2026-06-30',72,'In Progress'),('Clean Drinking Water','Pipeline extension and water points.','North Ward',1200000,'2026-02-01','2026-10-31',48,'In Progress'),('Solar Street Lights','Solar lights on important village streets.','Village Streets',450000,'2026-03-01','2026-08-15',100,'Completed')])
    if c.execute('select count(*) n from schemes').fetchone()['n']==0:
        c.executemany('insert into schemes(name,description,eligibility,benefits,documents) values(?,?,?,?,?)',[
        ('PM-KISAN','Information for eligible farmers.','Eligible farmer families','Financial assistance','Aadhaar and bank details'),('Ayushman Bharat','Information about health coverage.','Eligible families','Health coverage','Identity and eligibility proof'),('PMAY-G','Rural housing assistance information.','Eligible rural households','Housing support','Identity and residence proof')])
    if c.execute('select count(*) n from emergency').fetchone()['n']==0:
        c.executemany('insert into emergency(name,department,phone,location) values(?,?,?,?)',[('Police','Police Department','100','Nearby Police Station'),('Ambulance','Health Emergency','108','District Hospital'),('Fire & Rescue','Fire Department','101','Taluk Fire Station'),('Women Helpline','Women Safety','181','State Helpline')])
    if c.execute('select count(*) n from announcements').fetchone()['n']==0:
        c.execute('insert into announcements(title,content) values(?,?)',('Welcome to SmartGram','Report village problems, track progress and explore development information.'))
    if c.execute('select count(*) n from village_profile').fetchone()['n']==0:
        c.execute('insert into village_profile(id,village_name,gram_panchayat,taluk,district,state,pincode,population,households,contact,email,about) values(1,?,?,?,?,?,?,?,?,?,?,?)',('Demo Village','Demo Gram Panchayat','Mangaluru','Dakshina Kannada','Karnataka','575000',5200,1280,'0824-0000000','office@smartgram.local','A digital village development platform for transparent services, complaints, projects and citizen participation.'))
    if c.execute('select count(*) n from wards').fetchone()['n']==0:
        c.executemany('insert into wards(ward_no,name,representative,population,issues) values(?,?,?,?,?)',[
        ('01','North Ward','Smt. Anitha',820,'Road repair, street lights'),('02','Central Ward','Sri. Ramesh',1050,'Drainage, waste collection'),('03','South Ward','Smt. Kavya',760,'Water supply, bus shelter')])
    if c.execute('select count(*) n from budgets').fetchone()['n']==0:
        c.executemany('insert into budgets(financial_year,category,allocated,spent,source,notes) values(?,?,?,?,?,?)',[
        ('2026-27','Roads & Drainage',2500000,1125000,'Gram Panchayat','Main road and drainage improvement'),('2026-27','Water Supply',1800000,650000,'Rural Development','Pipeline extension'),('2026-27','Sanitation',900000,320000,'State Scheme','Waste and sanitation services')])
    if c.execute('select count(*) n from meetings').fetchone()['n']==0:
        c.executemany('insert into meetings(title,meeting_date,location,agenda,status) values(?,?,?,?,?)',[
        ('Gram Sabha Meeting','2026-10-15','Panchayat Hall','Village development priorities and citizen issues','Scheduled'),('Development Review','2026-10-25','Panchayat Office','Review ongoing projects and budgets','Scheduled')])
    c.commit(); c.close()

KEYWORDS={'Water':['water','tap','pipeline','drinking','tank','leak'],'Roads':['road','pothole','street','bridge'],'Electricity':['electricity','power','current','transformer','light'],'Sanitation':['drainage','sewage','toilet','sanitation'],'Waste':['garbage','waste','dustbin','plastic'],'Healthcare':['hospital','health','medicine','clinic','doctor'],'Education':['school','teacher','student','classroom'],'Agriculture':['farmer','crop','agriculture','irrigation','fertilizer']}
def category(text):
    s={k:sum(w in text.lower() for w in v) for k,v in KEYWORDS.items()}; best=max(s,key=s.get); return best if s[best] else 'Other'
def citizen(): return session.get('role')=='citizen'
def admin(): return session.get('role')=='admin'
def officer(): return session.get('role')=='officer'

@app.context_processor
def common(): return {'logged_in':bool(session.get('user_id')),'current_user':session.get('name'),'role':session.get('role')}
@app.route('/')
def home(): return render_template('index.html')
@app.route('/register',methods=['GET','POST'])
def register():
    if request.method=='POST':
        name=request.form['name'].strip(); email=request.form['email'].strip().lower(); password=request.form['password']
        if len(password)<6: flash('Password must have at least 6 characters.','danger'); return redirect(url_for('register'))
        c=db()
        try:
            c.execute('insert into users(name,email,phone,password,role,village) values(?,?,?,?,?,?)',(name,email,request.form.get('phone',''),generate_password_hash(password),'citizen',request.form.get('village',''))); c.commit(); flash('Account created. Please login.','success'); return redirect(url_for('login'))
        except sqlite3.IntegrityError: flash('Email is already registered.','danger')
        finally: c.close()
    return render_template('register.html')
@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        c=db(); u=c.execute('select * from users where email=?',(request.form['email'].strip().lower(),)).fetchone(); c.close()
        if u and check_password_hash(u['password'],request.form['password']):
            session.clear(); session.update(user_id=u['id'],name=u['name'],role=u['role'])
            return redirect(url_for('admin_dashboard' if u['role']=='admin' else 'officer_dashboard' if u['role']=='officer' else 'citizen_dashboard'))
        flash('Invalid email or password.','danger')
    return render_template('login.html')
@app.route('/logout')
def logout(): session.clear(); flash('Logged out successfully.','success'); return redirect(url_for('home'))

@app.route('/citizen')
def citizen_dashboard():
    if not citizen(): return redirect(url_for('login'))
    c=db(); uid=session['user_id']; total=c.execute('select count(*) n from complaints where user_id=?',(uid,)).fetchone()['n']; open_n=c.execute("select count(*) n from complaints where user_id=? and status not in ('Completed','Rejected')",(uid,)).fetchone()['n']; done=c.execute("select count(*) n from complaints where user_id=? and status='Completed'",(uid,)).fetchone()['n']; recent=c.execute('select * from complaints where user_id=? order by id desc limit 5',(uid,)).fetchall(); ann=c.execute('select * from announcements order by id desc limit 4').fetchall(); c.close(); return render_template('citizen.html',total=total,open_n=open_n,done=done,recent=recent,ann=ann)
@app.route('/report',methods=['GET','POST'])
def report():
    if not citizen(): return redirect(url_for('login'))
    if request.method=='POST':
        title=request.form['title'].strip(); desc=request.form['description'].strip(); cat=request.form.get('category','Auto'); cat=category(title+' '+desc) if cat=='Auto' else cat; img=request.files.get('image'); fname=None
        if img and img.filename:
            ext=img.filename.rsplit('.',1)[-1].lower()
            if ext not in {'jpg','jpeg','png','webp'}: flash('Only JPG, JPEG, PNG and WEBP images are allowed.','danger'); return redirect(url_for('report'))
            fname=secure_filename(uuid.uuid4().hex+'.'+ext); img.save(os.path.join(UPLOAD,fname))
        c=db(); c.execute('insert into complaints(user_id,title,description,category,priority,location,image) values(?,?,?,?,?,?,?)',(session['user_id'],title,desc,cat,request.form.get('priority','Medium'),request.form.get('location',''),fname)); c.commit(); c.close(); flash('Complaint submitted successfully.','success'); return redirect(url_for('citizen_dashboard'))
    return render_template('report.html',categories=list(KEYWORDS)+['Other'])
@app.route('/complaints')
def complaints():
    if not citizen(): return redirect(url_for('login'))
    c=db(); rows=c.execute('select * from complaints where user_id=? order by id desc',(session['user_id'],)).fetchall(); c.close(); return render_template('complaints.html',rows=rows)
@app.route('/complaint/<int:i>')
def complaint(i):
    if not session.get('user_id'): return redirect(url_for('login'))
    c=db(); row=c.execute('select c.*,u.name citizen,o.name officer_name from complaints c join users u on u.id=c.user_id left join users o on o.id=c.assigned_to where c.id=?',(i,)).fetchone(); c.close()
    if not row or (citizen() and row['user_id']!=session['user_id']): flash('Access denied.','danger'); return redirect(url_for('citizen_dashboard'))
    return render_template('complaint.html',x=row)
@app.route('/complaint/<int:i>/feedback',methods=['POST'])
def feedback(i):
    if not citizen(): return redirect(url_for('login'))
    c=db(); c.execute('insert into feedback(user_id,complaint_id,rating,comment) values(?,?,?,?,?)',(session['user_id'],i,int(request.form['rating']),request.form.get('comment',''))); c.commit(); c.close(); flash('Thanks for your feedback.','success'); return redirect(url_for('complaint',i=i))
@app.route('/projects')
def projects():
    c=db(); rows=c.execute('select * from projects order by id desc').fetchall(); c.close(); return render_template('projects.html',rows=rows)
@app.route('/schemes')
def schemes():
    c=db(); rows=c.execute('select * from schemes order by id desc').fetchall(); c.close(); return render_template('schemes.html',rows=rows)
@app.route('/emergency')
def emergency():
    c=db(); rows=c.execute('select * from emergency').fetchall(); c.close(); return render_template('emergency.html',rows=rows)

@app.route('/admin')
def admin_dashboard():
    if not admin(): return redirect(url_for('login'))
    c=db(); stats=[c.execute("select count(*) n from users where role='citizen'").fetchone()['n'],c.execute("select count(*) n from users where role='officer'").fetchone()['n'],c.execute('select count(*) n from complaints').fetchone()['n'],c.execute("select count(*) n from complaints where status not in ('Completed','Rejected')").fetchone()['n'],c.execute("select count(*) n from complaints where status='Completed'").fetchone()['n'],c.execute('select count(*) n from projects').fetchone()['n']]; recent=c.execute('select c.*,u.name citizen from complaints c join users u on u.id=c.user_id order by c.id desc limit 10').fetchall(); c.close(); return render_template('admin.html',stats=stats,recent=recent)
@app.route('/admin/complaints',methods=['GET','POST'])
def admin_complaints():
    if not admin(): return redirect(url_for('login'))
    c=db()
    if request.method=='POST':
        c.execute('update complaints set status=?,assigned_to=?,note=?,updated_at=CURRENT_TIMESTAMP where id=?',(request.form['status'],request.form.get('assigned_to') or None,request.form.get('note',''),request.form['id'])); c.commit(); flash('Complaint updated.','success')
    rows=c.execute('select c.*,u.name citizen,o.name officer_name from complaints c join users u on u.id=c.user_id left join users o on o.id=c.assigned_to order by c.id desc').fetchall(); officers=c.execute("select * from users where role='officer'").fetchall(); c.close(); return render_template('admin_complaints.html',rows=rows,officers=officers)
@app.route('/admin/users')
def users():
    if not admin(): return redirect(url_for('login'))
    c=db(); rows=c.execute("select * from users where role!='admin' order by id desc").fetchall(); c.close(); return render_template('users.html',rows=rows)
@app.route('/admin/projects',methods=['GET','POST'])
def admin_projects():
    if not admin(): return redirect(url_for('login'))
    c=db()
    if request.method=='POST':
        c.execute('insert into projects(name,description,location,budget,start_date,end_date,progress,status) values(?,?,?,?,?,?,?,?)',(request.form['name'],request.form.get('description',''),request.form.get('location',''),float(request.form.get('budget') or 0),request.form.get('start_date',''),request.form.get('end_date',''),int(request.form.get('progress',0)),request.form.get('status','Planned'))); c.commit(); flash('Project added.','success')
    rows=c.execute('select * from projects order by id desc').fetchall(); c.close(); return render_template('admin_projects.html',rows=rows)
@app.route('/admin/schemes',methods=['GET','POST'])
def admin_schemes():
    if not admin(): return redirect(url_for('login'))
    c=db()
    if request.method=='POST': c.execute('insert into schemes(name,description,eligibility,benefits,documents,link) values(?,?,?,?,?,?)',(request.form['name'],request.form.get('description',''),request.form.get('eligibility',''),request.form.get('benefits',''),request.form.get('documents',''),request.form.get('link',''))); c.commit(); flash('Scheme added.','success')
    rows=c.execute('select * from schemes order by id desc').fetchall(); c.close(); return render_template('admin_schemes.html',rows=rows)
@app.route('/admin/announcements',methods=['GET','POST'])
def announcements():
    if not admin(): return redirect(url_for('login'))
    c=db()
    if request.method=='POST': c.execute('insert into announcements(title,content) values(?,?)',(request.form['title'],request.form['content'])); c.commit(); flash('Announcement published.','success')
    rows=c.execute('select * from announcements order by id desc').fetchall(); c.close(); return render_template('announcements.html',rows=rows)

@app.route('/officer')
def officer_dashboard():
    if not officer(): return redirect(url_for('login'))
    c=db(); rows=c.execute('select c.*,u.name citizen from complaints c join users u on u.id=c.user_id where c.assigned_to=? order by c.id desc',(session['user_id'],)).fetchall(); c.close(); return render_template('officer.html',rows=rows)
@app.route('/officer/update',methods=['POST'])
def officer_update():
    if not officer(): return redirect(url_for('login'))
    c=db(); c.execute('update complaints set status=?,note=?,updated_at=CURRENT_TIMESTAMP where id=? and assigned_to=?',(request.form['status'],request.form.get('note',''),request.form['id'],session['user_id'])); c.commit(); c.close(); flash('Status updated.','success'); return redirect(url_for('officer_dashboard'))


@app.route('/administration')
def administration():
    if not admin(): return redirect(url_for('login'))
    c=db()
    profile=c.execute('select * from village_profile where id=1').fetchone()
    wards=c.execute('select * from wards order by ward_no').fetchall()
    budgets=c.execute('select * from budgets order by id desc').fetchall()
    meetings=c.execute('select * from meetings order by meeting_date').fetchall()
    officers=c.execute("select * from users where role='officer' order by name").fetchall()
    assets=c.execute('select a.*,u.name officer_name from village_assets a left join users u on u.id=a.assigned_officer order by a.id desc').fetchall()
    total_alloc=c.execute('select coalesce(sum(allocated),0) n from budgets').fetchone()['n']
    total_spent=c.execute('select coalesce(sum(spent),0) n from budgets').fetchone()['n']
    c.close()
    return render_template('administration.html',profile=profile,wards=wards,budgets=budgets,meetings=meetings,officers=officers,assets=assets,total_alloc=total_alloc,total_spent=total_spent)

@app.route('/administration/profile', methods=['POST'])
def administration_profile():
    if not admin(): return redirect(url_for('login'))
    c=db(); c.execute('update village_profile set village_name=?,gram_panchayat=?,taluk=?,district=?,state=?,pincode=?,population=?,households=?,contact=?,email=?,about=? where id=1',(
        request.form['village_name'],request.form['gram_panchayat'],request.form['taluk'],request.form['district'],request.form['state'],request.form['pincode'],int(request.form.get('population') or 0),int(request.form.get('households') or 0),request.form.get('contact',''),request.form.get('email',''),request.form.get('about',''))); c.commit(); c.close(); flash('Village profile updated.','success'); return redirect(url_for('administration'))

@app.route('/administration/wards', methods=['GET','POST'])
def administration_wards():
    if not admin(): return redirect(url_for('login'))
    c=db()
    if request.method=='POST':
        try:
            c.execute('insert into wards(ward_no,name,representative,population,issues) values(?,?,?,?,?)',(request.form['ward_no'],request.form['name'],request.form.get('representative',''),int(request.form.get('population') or 0),request.form.get('issues',''))); c.commit(); flash('Ward added.','success')
        except sqlite3.IntegrityError: flash('Ward number already exists.','danger')
    rows=c.execute('select * from wards order by ward_no').fetchall(); c.close(); return render_template('wards.html',rows=rows)

@app.route('/administration/budgets', methods=['GET','POST'])
def administration_budgets():
    if not admin(): return redirect(url_for('login'))
    c=db()
    if request.method=='POST':
        c.execute('insert into budgets(financial_year,category,allocated,spent,source,notes) values(?,?,?,?,?,?)',(request.form['financial_year'],request.form['category'],float(request.form.get('allocated') or 0),float(request.form.get('spent') or 0),request.form.get('source',''),request.form.get('notes',''))); c.commit(); flash('Budget entry added.','success')
    rows=c.execute('select * from budgets order by id desc').fetchall(); c.close(); return render_template('budgets.html',rows=rows)

@app.route('/administration/meetings', methods=['GET','POST'])
def administration_meetings():
    if not admin(): return redirect(url_for('login'))
    c=db()
    if request.method=='POST':
        c.execute('insert into meetings(title,meeting_date,location,agenda,status) values(?,?,?,?,?)',(request.form['title'],request.form['meeting_date'],request.form.get('location',''),request.form.get('agenda',''),'Scheduled')); c.commit(); flash('Meeting scheduled.','success')
    rows=c.execute('select * from meetings order by meeting_date').fetchall(); c.close(); return render_template('meetings.html',rows=rows)

@app.route('/administration/assets', methods=['GET','POST'])
def administration_assets():
    if not admin(): return redirect(url_for('login'))
    c=db()
    if request.method=='POST':
        c.execute('insert into village_assets(name,asset_type,location,condition_status,assigned_officer,notes) values(?,?,?,?,?,?)',(request.form['name'],request.form.get('asset_type',''),request.form.get('location',''),request.form.get('condition_status','Good'),request.form.get('assigned_officer') or None,request.form.get('notes',''))); c.commit(); flash('Village asset added.','success')
    rows=c.execute('select a.*,u.name officer_name from village_assets a left join users u on u.id=a.assigned_officer order by a.id desc').fetchall(); officers=c.execute("select * from users where role='officer'").fetchall(); c.close(); return render_template('assets.html',rows=rows,officers=officers)

@app.route('/officer/profile')
def officer_profile():
    if not officer(): return redirect(url_for('login'))
    c=db(); u=c.execute('select * from users where id=?',(session['user_id'],)).fetchone(); c.close(); return render_template('officer_profile.html',u=u)

@app.route('/officer/reports', methods=['GET','POST'])
def officer_reports():
    if not officer(): return redirect(url_for('login'))
    c=db()
    if request.method=='POST':
        c.execute('insert into officer_reports(officer_id,title,report_date,location,details,status) values(?,?,?,?,?,?)',(session['user_id'],request.form['title'],request.form['report_date'],request.form.get('location',''),request.form.get('details',''),'Submitted')); c.commit(); flash('Field report submitted to administration.','success')
    rows=c.execute('select * from officer_reports where officer_id=? order by id desc',(session['user_id'],)).fetchall(); c.close(); return render_template('officer_reports.html',rows=rows)

@app.route('/officer/projects')
def officer_projects():
    if not officer(): return redirect(url_for('login'))
    c=db(); rows=c.execute('select * from projects order by id desc').fetchall(); c.close(); return render_template('officer_projects.html',rows=rows)

@app.route('/officer/meetings')
def officer_meetings():
    if not officer(): return redirect(url_for('login'))
    c=db(); rows=c.execute('select * from meetings order by meeting_date').fetchall(); c.close(); return render_template('officer_meetings.html',rows=rows)


@app.route("/citizen-login", methods=["GET", "POST"])
def citizen_login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        c = db()
        user = c.execute(
            "SELECT * FROM users WHERE email=? AND role='citizen'",
            (email,)
        ).fetchone()
        c.close()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session.update(
                user_id=user["id"],
                name=user["name"],
                role="citizen"
            )
            flash("Welcome back!", "success")
            return redirect(url_for("citizen_dashboard"))

        flash("Invalid citizen email or password.", "danger")

    return render_template("citizen_login.html")


@app.route("/official-login", methods=["GET", "POST"])
def official_login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        c = db()
        user = c.execute(
            "SELECT * FROM users WHERE email=? AND role IN ('officer','admin')",
            (email,)
        ).fetchone()
        c.close()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session.update(
                user_id=user["id"],
                name=user["name"],
                role=user["role"]
            )

            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))

            return redirect(url_for("officer_dashboard"))

        flash("Invalid official email or password.", "danger")

    return render_template("official_login.html")

init_db()
if __name__=='__main__': app.run(debug=True)
