import os, json, uuid, smtplib, bcrypt, jwt
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from functools import wraps

app = Flask(__name__, static_folder='public', static_url_path='')
CORS(app)

# ── CONFIG ────────────────────────────────────
JWT_SECRET   = os.environ.get('JWT_SECRET', 'change_this_secret_please')
SMTP_HOST    = os.environ.get('SMTP_HOST', '')
SMTP_PORT    = int(os.environ.get('SMTP_PORT', 587))
SMTP_USER    = os.environ.get('SMTP_USER', '')
SMTP_PASS    = os.environ.get('SMTP_PASS', '')
MAIL_FROM    = os.environ.get('MAIL_FROM', 'XSQHost <noreply@xsqhost.de>')
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:5000')
SFTP_HOST    = os.environ.get('SFTP_HOST', 'sftp.xsqhost.de')

DB_FILE = 'data/database.json'
os.makedirs('data', exist_ok=True)

PLANS = {
    'free':    {'maxServers': 1, 'ram': '2GB',  'cores': 2, 'storage': '2GB',  'slots': 32},
    'starter': {'maxServers': 3, 'ram': '4GB',  'cores': 4, 'storage': '10GB', 'slots': 64},
    'pro':     {'maxServers': 5, 'ram': '8GB',  'cores': 6, 'storage': '25GB', 'slots': 128},
}

# ── DATABASE ──────────────────────────────────
def db_load():
    if not os.path.exists(DB_FILE):
        data = {'users': [], 'servers': []}
        db_save(data)
        return data
    with open(DB_FILE, 'r') as f:
        return json.load(f)

def db_save(data):
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def get_user_by_email(email):
    return next((u for u in db_load()['users'] if u['email'].lower() == email.lower()), None)

def get_user_by_id(uid):
    return next((u for u in db_load()['users'] if u['id'] == uid), None)

def get_user_by_token(token):
    return next((u for u in db_load()['users'] if u.get('emailToken') == token), None)

# ── EMAIL ─────────────────────────────────────
def base_email(content):
    return f"""
<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
body{{margin:0;padding:0;background:#080B12;font-family:'Courier New',monospace}}
.wrap{{max-width:560px;margin:0 auto;padding:32px 16px}}
.header{{background:#0D1120;border:1px solid #1E2A42;padding:24px 32px;border-bottom:2px solid #00E5FF}}
.logo{{color:#00E5FF;font-size:22px;letter-spacing:3px;font-weight:bold}}
.logo span{{color:#FF4D00}}
.body{{background:#0D1120;border:1px solid #1E2A42;padding:32px}}
h1{{color:#D8E4F0;font-size:22px;margin:0 0 8px}}
p{{color:#5A6A8A;font-size:14px;line-height:1.7;margin:12px 0}}
.btn{{display:inline-block;background:#00E5FF;color:#080B12;font-family:'Courier New',monospace;font-size:14px;font-weight:bold;padding:13px 32px;text-decoration:none;letter-spacing:2px;margin:16px 0}}
.code-box{{background:#050709;border:1px solid #1E2A42;padding:20px 24px;margin:16px 0;font-size:13px}}
.code-row{{margin:6px 0}}
.ck{{color:#5A6A8A}}.cv{{color:#00E5FF;font-weight:bold}}.cg{{color:#00FF88}}.cy{{color:#FFD700}}
.divider{{height:1px;background:#1E2A42;margin:20px 0}}
.footer{{background:#0D1120;border:1px solid #1E2A42;padding:16px 32px;text-align:center}}
.footer p{{color:#3A3F58;font-size:11px;margin:0}}
</style></head><body>
<div class="wrap">
  <div class="header"><div class="logo">◈ XSQ<span>HOST</span></div></div>
  <div class="body">{content}</div>
  <div class="footer"><p>© 2025 XSQHost · FiveM Server Hosting · Deutschland</p></div>
</div></body></html>"""

def send_email(to, subject, html):
    if not SMTP_HOST or not SMTP_USER:
        print(f"[MAIL SKIP] No SMTP configured. To: {to}, Subject: {subject}")
        return
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = MAIL_FROM
        msg['To']      = to
        msg.attach(MIMEText(html, 'html'))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_USER, to, msg.as_string())
        print(f"[MAIL OK] Sent to {to}")
    except Exception as e:
        print(f"[MAIL ERROR] {e}")

def mail_verify(to, username, token):
    url = f"{FRONTEND_URL}/verify?token={token}"
    html = base_email(f"""
        <h1>Willkommen, {username}!</h1>
        <p>Dein XSQHost Account wurde erstellt. Bitte bestätige deine E-Mail-Adresse.</p>
        <div class="divider"></div>
        <a href="{url}" class="btn">E-MAIL BESTÄTIGEN →</a>
        <p style="font-size:12px">Link: <span style="color:#00E5FF">{url}</span></p>
        <div class="divider"></div>
        <p style="font-size:12px">Falls du dich nicht registriert hast, ignoriere diese E-Mail.</p>
    """)
    send_email(to, '◈ XSQHost – E-Mail bestätigen', html)

def mail_server_created(to, username, srv):
    plan_names = {'free':'FREE (2GB RAM, 2 Kerne)', 'starter':'STARTER (4GB RAM)', 'pro':'PRO (8GB RAM)'}
    html = base_email(f"""
        <h1>Dein Server ist bereit! 🎮</h1>
        <p>Hey {username}, dein FiveM Server wurde erfolgreich erstellt!</p>
        <div class="divider"></div>
        <p style="color:#00E5FF;font-size:12px;letter-spacing:2px">SERVER INFO</p>
        <div class="code-box">
          <div class="code-row"><span class="ck">Name:      </span><span class="cg">{srv['name']}</span></div>
          <div class="code-row"><span class="ck">Plan:      </span><span class="cy">{plan_names.get(srv['plan'], srv['plan'])}</span></div>
          <div class="code-row"><span class="ck">Framework: </span><span class="cv">{srv['framework']}</span></div>
          <div class="code-row"><span class="ck">Status:    </span><span class="cg">● ONLINE</span></div>
        </div>
        <p style="color:#00E5FF;font-size:12px;letter-spacing:2px;margin-top:20px">WINSCP / SFTP ZUGANGSDATEN</p>
        <div class="code-box">
          <div class="code-row"><span class="ck">Host:      </span><span class="cv">{SFTP_HOST}</span></div>
          <div class="code-row"><span class="ck">Port:      </span><span class="cv">{srv['sftpPort']}</span></div>
          <div class="code-row"><span class="ck">Benutzer:  </span><span class="cg">{srv['sftpUser']}</span></div>
          <div class="code-row"><span class="ck">Passwort:  </span><span class="cy">{srv['sftpPass']}</span></div>
          <div class="code-row"><span class="ck">Protokoll: </span><span class="cv">SFTP</span></div>
        </div>
        <p style="color:#00E5FF;font-size:12px;letter-spacing:2px;margin-top:20px">MYSQL DATENBANK</p>
        <div class="code-box">
          <div class="code-row"><span class="ck">Host:      </span><span class="cv">db.xsqhost.de</span></div>
          <div class="code-row"><span class="ck">Datenbank: </span><span class="cg">{srv['dbName']}</span></div>
          <div class="code-row"><span class="ck">Benutzer:  </span><span class="cg">{srv['dbUser']}</span></div>
          <div class="code-row"><span class="ck">Passwort:  </span><span class="cy">{srv['dbPass']}</span></div>
        </div>
        <div class="divider"></div>
        <p style="font-size:11px;color:#3A3F58">Bewahre diese Zugangsdaten sicher auf!</p>
    """)
    send_email(to, f'◈ XSQHost – Server "{srv["name"]}" ist online!', html)

def mail_reset(to, username, token):
    url = f"{FRONTEND_URL}/reset-password?token={token}"
    html = base_email(f"""
        <h1>Passwort zurücksetzen</h1>
        <p>Hey {username}, du hast ein Passwort-Reset angefordert.</p>
        <div class="divider"></div>
        <a href="{url}" class="btn">PASSWORT ZURÜCKSETZEN →</a>
        <p style="font-size:12px">Dieser Link ist 1 Stunde gültig.</p>
    """)
    send_email(to, '◈ XSQHost – Passwort zurücksetzen', html)

# ── AUTH MIDDLEWARE ───────────────────────────
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        header = request.headers.get('Authorization', '')
        if not header.startswith('Bearer '):
            return jsonify({'error': 'Nicht angemeldet'}), 401
        try:
            payload = jwt.decode(header[7:], JWT_SECRET, algorithms=['HS256'])
            request.user = payload
        except Exception:
            return jsonify({'error': 'Token ungültig oder abgelaufen'}), 401
        return f(*args, **kwargs)
    return decorated

# ── HELPERS ───────────────────────────────────
def gen_sftp(username):
    rand = str(uuid.uuid4()).replace('-','')[:6].upper()
    clean = ''.join(c for c in username.lower() if c.isalnum())
    return {
        'sftpUser': f'srv_{clean}_{rand}',
        'sftpPass': str(uuid.uuid4()).replace('-','')[:16],
        'sftpPort': 22,
    }

def gen_db(username):
    rand = str(uuid.uuid4()).replace('-','')[:4]
    clean = ''.join(c for c in username.lower() if c.isalnum())
    return {
        'dbName': f'xsq_{clean}_{rand}',
        'dbUser': f'u_{rand}',
        'dbPass': str(uuid.uuid4()).replace('-','')[:14],
    }

# ══════════════════════════════════════════════
#  ROUTES
# ══════════════════════════════════════════════

# ── Frontend ──────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

@app.route('/verify')
def verify_page():
    return send_from_directory('public', 'index.html')

# ── POST /api/register ────────────────────────
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json or {}
    email    = data.get('email','').strip()
    password = data.get('password','')
    username = data.get('username','').strip()

    if not email or not password or not username:
        return jsonify({'error': 'Alle Felder sind pflicht'}), 400
    if len(password) < 8:
        return jsonify({'error': 'Passwort muss mindestens 8 Zeichen haben'}), 400
    if get_user_by_email(email):
        return jsonify({'error': 'E-Mail bereits registriert'}), 409

    pw_hash     = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    email_token = str(uuid.uuid4())
    uid         = str(uuid.uuid4())

    db = db_load()
    db['users'].append({
        'id': uid, 'email': email, 'passwordHash': pw_hash,
        'username': username, 'plan': 'free',
        'emailToken': email_token, 'emailVerified': False,
        'createdAt': datetime.now(timezone.utc).isoformat(),
    })
    db_save(db)

    mail_verify(email, username, email_token)
    return jsonify({'message': 'Registrierung erfolgreich! Bitte E-Mail bestätigen.', 'userId': uid}), 201

# ── GET /api/verify ───────────────────────────
@app.route('/api/verify')
def verify_email():
    token = request.args.get('token','')
    if not token:
        return jsonify({'error': 'Token fehlt'}), 400
    user = get_user_by_token(token)
    if not user:
        return jsonify({'error': 'Token ungültig oder bereits verwendet'}), 404
    db = db_load()
    for u in db['users']:
        if u['id'] == user['id']:
            u['emailVerified'] = True
            u['emailToken']    = None
    db_save(db)
    return jsonify({'message': 'E-Mail bestätigt! Du kannst dich jetzt einloggen.'})

# ── POST /api/login ───────────────────────────
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    email    = data.get('email','').strip()
    password = data.get('password','')

    if not email or not password:
        return jsonify({'error': 'E-Mail und Passwort pflicht'}), 400

    user = get_user_by_email(email)
    if not user:
        return jsonify({'error': 'E-Mail oder Passwort falsch'}), 401
    if not user.get('emailVerified'):
        return jsonify({'error': 'E-Mail noch nicht bestätigt. Bitte E-Mail prüfen.'}), 403
    if not bcrypt.checkpw(password.encode(), user['passwordHash'].encode()):
        return jsonify({'error': 'E-Mail oder Passwort falsch'}), 401

    token = jwt.encode({
        'id': user['id'], 'email': user['email'],
        'username': user['username'], 'plan': user['plan'],
        'exp': datetime.now(timezone.utc) + timedelta(days=7),
    }, JWT_SECRET, algorithm='HS256')

    return jsonify({
        'token': token,
        'user': {'id': user['id'], 'username': user['username'], 'email': user['email'], 'plan': user['plan']},
    })

# ── GET /api/me ───────────────────────────────
@app.route('/api/me')
@require_auth
def me():
    user = get_user_by_id(request.user['id'])
    if not user:
        return jsonify({'error': 'User nicht gefunden'}), 404
    return jsonify({'id': user['id'], 'username': user['username'], 'email': user['email'], 'plan': user['plan']})

# ── GET /api/servers ──────────────────────────
@app.route('/api/servers')
@require_auth
def get_servers():
    db      = db_load()
    servers = [s for s in db['servers'] if s['userId'] == request.user['id']]
    result  = []
    for s in servers:
        result.append({
            'id': s['id'], 'name': s['name'], 'framework': s['framework'],
            'plan': s['plan'], 'status': s['status'],
            'sftp': {'host': SFTP_HOST, 'port': s['sftpPort'], 'user': s['sftpUser'], 'pass': s['sftpPass']},
            'db':   {'host': 'db.xsqhost.de', 'name': s['dbName'], 'user': s['dbUser'], 'pass': s['dbPass']},
            'resources': PLANS.get(s['plan'], PLANS['free']),
            'createdAt': s['createdAt'],
        })
    return jsonify(result)

# ── POST /api/servers ─────────────────────────
@app.route('/api/servers', methods=['POST'])
@require_auth
def create_server():
    data      = request.json or {}
    name      = data.get('name','').strip()
    framework = data.get('framework', 'ESX')

    if not name:
        return jsonify({'error': 'Servername pflicht'}), 400

    user = get_user_by_id(request.user['id'])
    plan = user['plan']
    plan_config = PLANS.get(plan, PLANS['free'])

    db = db_load()
    existing = sum(1 for s in db['servers'] if s['userId'] == user['id'])

    if existing >= plan_config['maxServers']:
        return jsonify({'error': f"Dein {plan.upper()} Plan erlaubt maximal {plan_config['maxServers']} Server."}), 403

    sftp = gen_sftp(user['username'])
    dbc  = gen_db(user['username'])
    sid  = str(uuid.uuid4())

    server = {
        'id': sid, 'userId': user['id'], 'name': name,
        'framework': framework, 'plan': plan,
        **sftp, **dbc,
        'status': 'online',
        'createdAt': datetime.now(timezone.utc).isoformat(),
    }
    db['servers'].append(server)
    db_save(db)

    mail_server_created(user['email'], user['username'], server)

    return jsonify({
        'message': 'Server erstellt! Zugangsdaten wurden per E-Mail gesendet.',
        'server': {
            'id': server['id'], 'name': server['name'],
            'framework': server['framework'], 'plan': server['plan'],
            'status': server['status'],
            'sftp': {'host': SFTP_HOST, 'port': server['sftpPort'], 'user': server['sftpUser'], 'pass': server['sftpPass']},
            'db':   {'host': 'db.xsqhost.de', 'name': server['dbName'], 'user': server['dbUser'], 'pass': server['dbPass']},
            'resources': plan_config,
        }
    }), 201

# ── PATCH /api/servers/<id>/status ───────────
@app.route('/api/servers/<sid>/status', methods=['PATCH'])
@require_auth
def update_status(sid):
    data   = request.json or {}
    status = data.get('status','')
    if status not in ('online','offline','restarting'):
        return jsonify({'error': 'Ungültiger Status'}), 400

    db = db_load()
    srv = next((s for s in db['servers'] if s['id'] == sid and s['userId'] == request.user['id']), None)
    if not srv:
        return jsonify({'error': 'Server nicht gefunden'}), 404

    srv['status'] = status
    db_save(db)
    return jsonify({'message': f'Status → {status}'})

# ── POST /api/forgot-password ─────────────────
@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    email = (request.json or {}).get('email','').strip()
    user  = get_user_by_email(email)
    if user:
        token = jwt.encode({
            'id': user['id'], 'purpose': 'reset',
            'exp': datetime.now(timezone.utc) + timedelta(hours=1),
        }, JWT_SECRET, algorithm='HS256')
        mail_reset(email, user['username'], token)
    return jsonify({'message': 'Falls die E-Mail existiert, wurde ein Reset-Link gesendet.'})

# ── GET /api/plans ────────────────────────────
@app.route('/api/plans')
def plans():
    return jsonify(PLANS)

# ── START ─────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"""
  ◈ XSQHost Python Backend
  ─────────────────────────────
  ● http://localhost:{port}
  ● Datenbank: ./data/database.json
  ─────────────────────────────
    """)
    app.run(host='0.0.0.0', port=port, debug=False)
