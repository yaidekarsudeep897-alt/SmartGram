# SmartGram — rebuilt Flask project

SmartGram is a student project for village services and complaint tracking. This is a clean standalone rebuild rather than a patch over older conflicting files.

## Main features

- Reference-inspired responsive homepage with green, white and saffron accents.
- Citizen registration and login, with required district/Gram Panchayat selection.
- Separate official login; each officer account belongs to one Gram Panchayat.
- Admin dashboard to review complaints, create official accounts, assign complaints and publish announcements/projects.
- Complaint ticket IDs, image evidence upload, rule-based category/priority suggestions, status updates and citizen feedback.
- Panchayat directory with district filtering, text search and pagination.
- Project and government scheme information pages.
- SQLite database created automatically on first launch; passwords are hashed.
- The bundled normalized directory CSV has 5,949 distinct local-body codes derived from the uploaded village-to-Gram-Panchayat mapping file. Verify the directory against the latest official LGD data before operational use.

## Windows setup (VS Code)

1. Extract the ZIP into a new folder such as `D:\SmartGram_Rebuilt`. Do not merge it into your old project until the new version works.
2. Open that folder in VS Code: **File → Open Folder**.
3. In Terminal, run:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

4. Open `http://127.0.0.1:5000` in Chrome.

If PowerShell blocks activation, use `python -m pip install -r requirements.txt` and `python app.py` without activating the environment.

## Demo administrator

- Email: `admin@smartgram.local`
- Password: `admin12345`

## Demo Gram Panchayat officer

- Email: `officer@smartgram.local`
- Password: `officer12345`
- Assigned GP in the bundled directory: `Adagal` (Badami taluk, Bagalkote district). Select that exact Panchayat on the Official tab.

Create additional officers from **Admin → Official accounts** and link each one to the appropriate GP.

## Directory import

The normalized CSV is imported automatically into an empty database at startup. To import/update again:

```powershell
python import_gram_panchayats.py data\karnataka_gram_panchayats.csv
```

Expected CSV headers: `lgd_code,name,district,taluk`.

## Notes

- Complaint classification is transparent keyword/rule-based logic, not a trained machine-learning model. It is a demo suggestion and should be reviewed by officials.
- Demo credentials and the development secret key are not suitable for production. Set `SMARTGRAM_SECRET_KEY` to a long random value before deployment.
- This is a local student-project foundation, not a verified government service. Do not store sensitive identity numbers or real citizens' private information in a public demo.
- If you want a clean reset, stop Flask and remove `database/smartgram.db`, then restart `python app.py`. This deletes local test accounts and complaint data.


## Community engagement upgrades
- **Village Pulse** (`/village-pulse`): public board of complaints citizens explicitly opt to share. It only shows the title, category, priority, status, location, Panchayat and tracking ID; private descriptions, citizen names and photos are not exposed.
- **Community support votes**: signed-in citizens can support another citizen's shared issue once. A citizen cannot vote for their own complaint.
- **In-app notifications**: citizens receive updates when an admin or assigned official changes a complaint status. The Notifications link shows an unread count.
- Existing databases are migrated on startup to add the public-sharing flag and the new tables.

These are demonstration features. Do not put sensitive complaints on the public board; citizens should only opt in when the issue is appropriate for public display.

## Added modules (October 2026)

### Government Scheme Eligibility Checker
- Open **Scheme Checker** from the top navigation after signing in.
- Enter basic details and choose a category to see potentially relevant schemes.
- Scheme records are stored in the existing `schemes` table; past checks are recorded in `scheme_checks`.
- The matching is a simple category/keyword filter for a student project, not an official eligibility determination. Verify scheme details and eligibility on official government portals.

### Development Work Quality Inspection
- Open **Quality Inspections** from the top navigation.
- Gram Panchayat officers can record inspections only for projects assigned to their Gram Panchayat. Admin can record inspections for all projects.
- Record the result, findings, corrective action, follow-up date, and optional image. Citizens can view published reports.
- The app creates the `inspections` and `scheme_checks` tables automatically at startup. Existing project data is preserved.
- Uploaded inspection photos are stored in `uploads/`; only JPG, JPEG, PNG, and WEBP are accepted, with the app's 5 MB upload limit.

### Run on Windows
1. Extract this ZIP.
2. Open Command Prompt in the `SmartGram_final` folder.
3. Run `python -m pip install -r requirements.txt`.
4. Run `python app.py`.
5. Open `http://127.0.0.1:5000` in Chrome.


## School Development Module (added)

New routes: `/schools` (public directory; authorized officials can add schools), `/school-issues` (citizens can submit and track their own school issues; officers/admins can update status), and `/school-funds` (public fund transparency; authorized officers/admins can add records). School records reference the existing `gram_panchayats` table, so each school is tied to an existing Gram Panchayat. Tables are created automatically at startup: `schools`, `school_issues`, `school_funds`, and `school_feedback`.

To deploy on Render, set the Root Directory to the folder that directly contains `app.py` and `requirements.txt` (normally `SmartGram_final` if this ZIP is uploaded with its top-level folder). Build command: `pip install -r requirements.txt`. If using Gunicorn as the start command, add `gunicorn` to `requirements.txt` and use `gunicorn app:app`.

Note: the school directory starts empty because no verified school dataset was supplied. Add school records through the official/officer account. Funding values are public transparency entries and should be checked against official records before publication.

## Citizen dashboard: Village, School and Health
The citizen dashboard now highlights three primary services: Village Problem, School Problem, and Health Problem. Health problems are saved as Healthcare complaints and use the existing complaint tracking workflow.

## Community health camps
Administrators can open **Health Camps** to publish a camp with date, start/end time, Gram Panchayat, village venue, available doctors, medical services, and maximum patient registrations. Signed-in citizens can register a patient once per camp. The application checks the configured capacity before accepting registrations. Administrators can view the registration list from the camp page. Health camp registrations contain personal information and are restricted to administrators.
