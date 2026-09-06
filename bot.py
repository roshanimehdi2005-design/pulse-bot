import os, json, sqlite3, logging, requests
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone

TOKEN = os.getenv('BOT_TOKEN', '').strip()
ADMIN_CHAT_IDS = [x.strip() for x in os.getenv('ADMIN_CHAT_IDS', '').split(',') if x.strip()]
DB_PATH = os.getenv('DB_PATH', 'pulse.db')
if not TOKEN:
    raise SystemExit('BOT_TOKEN is missing. Set it in the environment before running.')
API = f'https://api.telegram.org/bot{TOKEN}'
logging.basicConfig(level=logging.INFO)

QUESTIONS = [
    ('grade', 'پایه‌ات کدومه؟', ['دهم', 'یازدهم', 'دوازدهم', 'فارغ‌التحصیل / پشت‌کنکوری']),
    ('goal', 'اگه قرار باشه امسال فقط یک موفقیت برات مهم باشه، کدوم رو انتخاب می‌کنی؟ 🎯', [
        'موفقیت در مدرسه و امتحانات نهایی عالی',
        'آمادگی جدی برای کنکور و رسیدن به رتبه و دانشگاه خوب',
        'هنوز دقیق نمی‌دونم؛ می‌خوام ببینم کدوم مسیر برای من مناسب‌تره'
    ]),
    ('study_style', 'سبک درس خوندنت بیشتر به کدوم حالت نزدیکه؟ 📚', [
        'بیشتر تشریحی و مدرسه‌ای', 'ترکیبی؛ هم تشریحی، هم تستی',
        'بیشتر تستی و کنکوری', 'کاملاً کنکوری و آزمون‌محور', 'هنوز سبک مشخصی ندارم'
    ]),
    ('study_hours', 'توی یک روز معمولی، واقعاً چند ساعت مفید درس می‌خونی؟ ⏱️', [
        'کمتر از ۲ ساعت', '۲ تا ۴ ساعت', '۴ تا ۶ ساعت', '۶ تا ۸ ساعت', 'بیشتر از ۸ ساعت', 'دقیق نمی‌تونم بگم'
    ]),
    ('execution', 'برنامه‌ای که برای خودت می‌چینی رو چقدر می‌تونی اجرا کنی؟ 🎯', [
        'تقریباً همیشه', 'بیشتر مواقع', 'نصفه‌نیمه', 'معمولاً از برنامه عقب می‌مونم', 'عملاً برنامه ثابتی ندارم'
    ]),
    ('challenge', 'چالشت بیشتر با کدوم بخش مسیره؟ 🧩', [
        'آموزش و یادگیری', 'برنامه‌ریزی و شروع کردن', 'نظم و استمرار', 'تست زدن',
        'آزمون و تحلیل', 'تمرکز و مطالعه مفید', 'هنوز دقیق نمی‌دونم'
    ]),
    ('learning_model', 'وقتی پای یادگیری وسطه، کدوم مدل بیشتر به کارت میاد؟ 🎓', [
        'ترجیح می‌دم با کلاس و آموزش منظم جلو برم.',
        'بیشتر خودم مطالعه می‌کنم و فقط گاهی به رفع اشکال نیاز دارم.',
        'آموزش، کلاس و رفع اشکال رو یکجا می‌خوام.',
        'هنوز مطمئن نیستم؛ می‌خوام بر اساس شرایط خودم پیشنهاد بگیرم.'
    ]),
    ('support_style', 'دوست داری مسیر درست درس خوندنت چطور پیش بره؟ 🚀', [
        'مسیر مشخصی داشته باشم و خودم اجراش کنم.',
        'در طول مسیر مرتب بررسی بشم تا بدونم دارم درست پیش می‌رم.',
        'عملکردم بررسی بشه و مسیرم متناسب با شرایط تنظیم بشه.',
        'هنوز نمی‌دونم؛ می‌خوام پیشنهاد بگیرم.'
    ]),
    ('resources', 'تا امروز برای مسیر تحصیلیت از چه امکاناتی استفاده کردی؟ 📌', [
        'فعلاً هیچ‌کدوم', 'کلاس آموزشی', 'مشاور', 'آزمون آزمایشی',
        'کلاس + مشاور', 'چند مورد از این‌ها', 'قبلاً استفاده کردم ولی الان ندارم'
    ]),
    ('final_need', 'اگه PULSE قرار باشه فقط یک بخش از مسیرت رو برات بهتر کنه، دوست داری کدوم باشه؟ 🚀', [
        'یادگیری بهتر', 'نظم و استمرار', 'برنامه‌ریزی', 'تست و آزمون',
        'تحلیل و رفع ضعف', 'مدیریت کامل مسیر', 'هنوز نمی‌دونم'
    ]),
]

SCORES = {
    'grade': {
        'دهم': (3, 1, 1), 'یازدهم': (3, 2, 2), 'دوازدهم': (2, 3, 3), 'فارغ‌التحصیل / پشت‌کنکوری': (0, 4, 4)
    },
    'goal': {
        'موفقیت در مدرسه و امتحانات نهایی عالی': (7, 1, 1),
        'آمادگی جدی برای کنکور و رسیدن به رتبه و دانشگاه خوب': (1, 7, 6),
        'هنوز دقیق نمی‌دونم؛ می‌خوام ببینم کدوم مسیر برای من مناسب‌تره': (1, 1, 1)
    },
    'study_style': {
        'بیشتر تشریحی و مدرسه‌ای': (5, 0, 0), 'ترکیبی؛ هم تشریحی، هم تستی': (2, 3, 3),
        'بیشتر تستی و کنکوری': (0, 5, 4), 'کاملاً کنکوری و آزمون‌محور': (0, 5, 6), 'هنوز سبک مشخصی ندارم': (1, 1, 1)
    },
    'study_hours': {
        'کمتر از ۲ ساعت': (1, 1, 3), '۲ تا ۴ ساعت': (1, 2, 3), '۴ تا ۶ ساعت': (1, 2, 2),
        '۶ تا ۸ ساعت': (1, 2, 1), 'بیشتر از ۸ ساعت': (1, 2, 1), 'دقیق نمی‌تونم بگم': (1, 1, 2)
    },
    'execution': {
        'تقریباً همیشه': (2, 2, 1), 'بیشتر مواقع': (2, 2, 2), 'نصفه‌نیمه': (1, 3, 4),
        'معمولاً از برنامه عقب می‌مونم': (0, 2, 5), 'عملاً برنامه ثابتی ندارم': (1, 1, 5)
    },
    'challenge': {
        'آموزش و یادگیری': (3, 3, 4), 'برنامه‌ریزی و شروع کردن': (2, 4, 5), 'نظم و استمرار': (2, 3, 5),
        'تست زدن': (0, 4, 4), 'آزمون و تحلیل': (0, 5, 5), 'تمرکز و مطالعه مفید': (2, 3, 4), 'هنوز دقیق نمی‌دونم': (1, 1, 2)
    },
    'learning_model': {
        'ترجیح می‌دم با کلاس و آموزش منظم جلو برم.': (4, 4, 4),
        'بیشتر خودم مطالعه می‌کنم و فقط گاهی به رفع اشکال نیاز دارم.': (4, 2, 1),
        'آموزش، کلاس و رفع اشکال رو یکجا می‌خوام.': (2, 4, 6),
        'هنوز مطمئن نیستم؛ می‌خوام بر اساس شرایط خودم پیشنهاد بگیرم.': (1, 1, 2)
    },
    'support_style': {
        'مسیر مشخصی داشته باشم و خودم اجراش کنم.': (2, 6, 2),
        'در طول مسیر مرتب بررسی بشم تا بدونم دارم درست پیش می‌رم.': (1, 4, 6),
        'عملکردم بررسی بشه و مسیرم متناسب با شرایط تنظیم بشه.': (0, 3, 7),
        'هنوز نمی‌دونم؛ می‌خوام پیشنهاد بگیرم.': (1, 1, 2)
    },
    'resources': {
        'فعلاً هیچ‌کدوم': (1, 2, 3), 'کلاس آموزشی': (1, 2, 2), 'مشاور': (1, 2, 2), 'آزمون آزمایشی': (1, 2, 2),
        'کلاس + مشاور': (1, 2, 3), 'چند مورد از این‌ها': (1, 2, 3), 'قبلاً استفاده کردم ولی الان ندارم': (1, 2, 3)
    },
    'final_need': {
        'یادگیری بهتر': (5, 3, 3), 'نظم و استمرار': (2, 4, 6), 'برنامه‌ریزی': (2, 5, 6),
        'تست و آزمون': (0, 5, 5), 'تحلیل و رفع ضعف': (0, 4, 6), 'مدیریت کامل مسیر': (0, 2, 8), 'هنوز نمی‌دونم': (1, 1, 2)
    },
}

MISSING_SCORES = {
    'آموزش': (3, 3, 4), 'برنامه‌ریزی': (2, 4, 5), 'نظم و پیگیری': (1, 3, 6),
    'تست و آزمون': (0, 4, 5), 'تحلیل و رفع ضعف': (0, 4, 6), 'هماهنگی و مدیریت کل مسیر': (0, 2, 7), 'هنوز نمی‌دونم': (1, 1, 2)
}

PACKAGES = {
    'PLUS': {
        'title': '🟢 PLUS — مسیر یادگیری و مطالعه حرفه‌ای',
        'desc': 'برای کسی که تمرکز اصلی‌اش روی درست درس خواندن، مدرسه، امتحانات نهایی و ساختن پایه قوی است.',
        'features': ['روتین و برنامه مطالعه', 'تقویت یادگیری و فهم عمیق درس', 'تمرکز روی عملکرد مدرسه و امتحانات نهایی', 'پشتیبانی در مسیر مطالعه']
    },
    'PRO': {
        'title': '🟣 PRO — مسیر هدایت حرفه‌ای کنکور',
        'desc': 'برای کسی که هدف اصلی‌اش کنکور است و می‌خواهد مسیر مشخص، برنامه، آزمون و تحلیل داشته باشد؛ اما اجرای روزانه مسیر را خودش انجام می‌دهد.',
        'features': ['برنامه‌ریزی شخصی‌سازی‌شده', 'هدایت و پیگیری مسیر', 'آزمون و تحلیل عملکرد', 'کلاس و آموزش متناسب با مسیر', 'مشاوره و اصلاح مسیر']
    },
    '360': {
        'title': '🔵 360 — مدیریت کامل مسیر کنکور',
        'desc': 'برای کسی که فقط برنامه نمی‌خواهد؛ یک سیستم یکپارچه برای آموزش، برنامه‌ریزی، آزمون، تحلیل، رفع اشکال، پیگیری و اصلاح مداوم مسیر می‌خواهد.',
        'features': ['آموزش تخصصی از پایه تا تسلط', 'برنامه‌ریزی و چک روزانه/شبانه', 'آزمون‌های روزانه، هفتگی و دوره‌ای', 'تحلیل، رفع اشکال و اصلاح مستمر', 'مدیریت یکپارچه کل مسیر کنکور']
    }
}

state = {}

def db():
    c = sqlite3.connect(DB_PATH)
    c.execute('''CREATE TABLE IF NOT EXISTS students(
      chat_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, phone TEXT,
      data_json TEXT, recommendation TEXT, created_at TEXT)''')
    # Backward-compatible extension for the new diagnostic engine.
    for col, typ in [('score_json', 'TEXT'), ('reason_json', 'TEXT'), ('profile_json', 'TEXT')]:
        try:
            c.execute(f'ALTER TABLE students ADD COLUMN {col} {typ}')
        except sqlite3.OperationalError:
            pass
    c.commit()
    return c

def tg(method, payload):
    r = requests.post(f'{API}/{method}', json=payload, timeout=35)
    r.raise_for_status()
    return r.json()

def send(cid, text, markup=None):
    p = {'chat_id': cid, 'text': text}
    if markup:
        p['reply_markup'] = markup
    return tg('sendMessage', p)

def kb(opts):
    return {'keyboard': [[{'text': x} for x in opts[i:i+2]] for i in range(0, len(opts), 2)], 'resize_keyboard': True, 'one_time_keyboard': True}

def rm():
    return {'remove_keyboard': True}

def contact_kb():
    return {'keyboard': [[{'text': '📞 ارسال شماره تماس', 'request_contact': True}]], 'resize_keyboard': True, 'one_time_keyboard': True}

def fullname(msg):
    u = msg.get('from', {})
    return (' '.join(x for x in [u.get('first_name', ''), u.get('last_name', '')] if x)).strip()

def recommend(d):
    s = {'PLUS': 0, 'PRO': 0, '360': 0}
    reasons = []
    for key, _, _ in QUESTIONS:
        if key in d and d[key] in SCORES.get(key, {}):
            a, b, c = SCORES[key][d[key]]
            s['PLUS'] += a; s['PRO'] += b; s['360'] += c

    # Hard rules / direction gates.
    if d.get('goal') == 'موفقیت در مدرسه و امتحانات نهایی عالی' and d.get('study_style') == 'بیشتر تشریحی و مدرسه‌ای':
        s['PLUS'] += 5
        reasons.append('GOAL_SCHOOL_FINAL')
    if d.get('goal') == 'آمادگی جدی برای کنکور و رسیدن به رتبه و دانشگاه خوب' and d.get('support_style') == 'مسیر مشخصی داشته باشم و خودم اجراش کنم.':
        s['PRO'] += 5
        reasons.append('GUIDED_EXECUTION')
    if d.get('goal') == 'آمادگی جدی برای کنکور و رسیدن به رتبه و دانشگاه خوب' and d.get('support_style') in [
        'در طول مسیر مرتب بررسی بشم تا بدونم دارم درست پیش می‌رم.',
        'عملکردم بررسی بشه و مسیرم متناسب با شرایط تنظیم بشه.'
    ]:
        s['360'] += 7
        reasons.append('FULL_MANAGEMENT_SIGNAL')

    # Conditional follow-up for current resources.
    if d.get('resources') in ['کلاس آموزشی', 'مشاور', 'آزمون آزمایشی', 'کلاس + مشاور', 'چند مورد از این‌ها', 'قبلاً استفاده کردم ولی الان ندارم']:
        need = d.get('missing_need')
        if need in MISSING_SCORES:
            a, b, c = MISSING_SCORES[need]
            s['PLUS'] += a; s['PRO'] += b; s['360'] += c
            if need in ['نظم و پیگیری', 'هماهنگی و مدیریت کل مسیر']:
                reasons.append('NEEDS_MANAGEMENT')
            elif need in ['تحلیل و رفع ضعف', 'تست و آزمون']:
                reasons.append('NEEDS_EXAM_ANALYSIS')
            elif need == 'آموزش':
                reasons.append('NEEDS_EDUCATION')

    # School/final direction gate: exam-management signals should not overturn a clearly school-focused profile.
    school_goal = d.get('goal') == 'موفقیت در مدرسه و امتحانات نهایی عالی'
    school_style = d.get('study_style') == 'بیشتر تشریحی و مدرسه‌ای'
    if school_goal and school_style:
        if s['PLUS'] >= s['PRO']:
            s['PRO'] = min(s['PRO'], s['PLUS'] - 1 if s['PLUS'] > 0 else 0)
            s['360'] = min(s['360'], s['PLUS'] - 1 if s['PLUS'] > 0 else 0)

    ordered = sorted(s.items(), key=lambda x: (-x[1], x[0]))
    primary, secondary = ordered[0], ordered[1]
    gap_pct = ((primary[1] - secondary[1]) / primary[1] * 100) if primary[1] else 0
    confidence = 'HIGH' if gap_pct >= 20 else ('MEDIUM' if gap_pct >= 10 else 'CLOSE')
    selected = [primary[0], secondary[0]] if gap_pct < 10 else [primary[0]]

    if d.get('goal') == 'آمادگی جدی برای کنکور و رسیدن به رتبه و دانشگاه خوب':
        reasons.append('GOAL_KONKOUR')
    if d.get('study_hours') in ['کمتر از ۲ ساعت', '۲ تا ۴ ساعت']:
        reasons.append('LOW_STUDY_TIME')
    if d.get('execution') in ['نصفه‌نیمه', 'معمولاً از برنامه عقب می‌مونم', 'عملاً برنامه ثابتی ندارم']:
        reasons.append('WEAK_PLAN_EXECUTION')
    if d.get('support_style') in [
        'در طول مسیر مرتب بررسی بشم تا بدونم دارم درست پیش می‌رم.',
        'عملکردم بررسی بشه و مسیرم متناسب با شرایط تنظیم بشه.'
    ]:
        reasons.append('NEEDS_REGULAR_MONITORING')
    if d.get('learning_model') == 'آموزش، کلاس و رفع اشکال رو یکجا می‌خوام.':
        reasons.append('NEEDS_FULL_EDUCATION')
    if d.get('final_need') == 'مدیریت کامل مسیر':
        reasons.append('WANTS_FULL_MANAGEMENT')

    reasons = list(dict.fromkeys(reasons))
    tags = []
    if d.get('goal') == 'آمادگی جدی برای کنکور و رسیدن به رتبه و دانشگاه خوب': tags.append('🎯 هدف‌محور')
    if d.get('execution') in ['نصفه‌نیمه', 'معمولاً از برنامه عقب می‌مونم', 'عملاً برنامه ثابتی ندارم']: tags.append('🔄 نیازمند اصلاح مسیر')
    if d.get('support_style') in ['در طول مسیر مرتب بررسی بشم تا بدونم دارم درست پیش می‌رم.', 'عملکردم بررسی بشه و مسیرم متناسب با شرایط تنظیم بشه.']: tags.append('📈 پیگیری‌پذیر')
    if d.get('learning_model') == 'آموزش، کلاس و رفع اشکال رو یکجا می‌خوام.': tags.append('🎓 آموزش‌محور')
    if d.get('final_need') == 'مدیریت کامل مسیر': tags.append('🧭 مدیریت‌محور')
    if not tags: tags.append('🚀 آماده ساختن مسیر بهتر')

    return selected, s, reasons, tags, confidence

def save(cid, msg, phone, d, recs, scores, reasons, tags):
    c = db()
    rec = recs[0]
    payload = dict(d)
    c.execute('''INSERT INTO students(chat_id,username,full_name,phone,data_json,recommendation,created_at,score_json,reason_json,profile_json)
      VALUES(?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(chat_id) DO UPDATE SET username=excluded.username,full_name=excluded.full_name,phone=excluded.phone,
      data_json=excluded.data_json,recommendation=excluded.recommendation,created_at=excluded.created_at,
      score_json=excluded.score_json,reason_json=excluded.reason_json,profile_json=excluded.profile_json''',
      (cid, msg.get('from', {}).get('username', ''), fullname(msg), phone, json.dumps(payload, ensure_ascii=False),
       rec, datetime.now(timezone.utc).isoformat(), json.dumps(scores, ensure_ascii=False),
       json.dumps(reasons, ensure_ascii=False), json.dumps(tags, ensure_ascii=False)))
    c.commit(); c.close()

def profile_text(d):
    goal = d.get('goal', '')
    hours = d.get('study_hours', '')
    execution = d.get('execution', '')
    if 'مدرسه' in goal:
        return 'تمرکز اصلیت روی مدرسه و امتحانات نهایی است و دنبال یک مسیر منظم برای بهتر درس خواندن و نتیجه گرفتن هستی.'
    parts = ['هدفت کنکوری و جدی است']
    if hours in ['کمتر از ۲ ساعت', '۲ تا ۴ ساعت']:
        parts.append('اما فعلاً زمان مطالعه مفیدت جای رشد دارد')
    if execution in ['نصفه‌نیمه', 'معمولاً از برنامه عقب می‌مونم', 'عملاً برنامه ثابتی ندارم']:
        parts.append('و اجرای برنامه هم نیاز به تقویت دارد')
    if d.get('support_style') in ['در طول مسیر مرتب بررسی بشم تا بدونم دارم درست پیش می‌رم.', 'عملکردم بررسی بشه و مسیرم متناسب با شرایط تنظیم بشه.']:
        parts.append('پس صرفاً یک برنامه خام برایت کافی نیست')
    return '، '.join(parts) + '.'

def result_message(d, recs, scores, reasons, tags, confidence):
    primary = recs[0]
    p = PACKAGES[primary]
    text = f'🎯 خب! بررسی PULSE تموم شد.\n\n🧠 تصویری که PULSE از مسیرت ساخته:\n{profile_text(d)}\n\n{p["title"]}\n\n{p["desc"]}\n\n✨ چرا این مسیر برای تو؟'
    reason_map = {
        'GOAL_SCHOOL_FINAL': '🎯 هدفت فعلاً بیشتر مدرسه و امتحانات نهایی است.',
        'GOAL_KONKOUR': '🏁 هدف اصلیت کنکور و رسیدن به نتیجه جدی است.',
        'GUIDED_EXECUTION': '🗺️ مسیر مشخص می‌خواهی و اجرای آن را خودت بر عهده می‌گیری.',
        'FULL_MANAGEMENT_SIGNAL': '🔄 می‌خواهی عملکردت بررسی شود و مسیر متناسب با شرایطت تغییر کند.',
        'NEEDS_MANAGEMENT': '📊 مسئله اصلی فقط برنامه نیست؛ پیگیری و مدیریت مستمر هم برایت مهم است.',
        'NEEDS_EXAM_ANALYSIS': '📝 آزمون، تحلیل و اصلاح ضعف‌ها بخش مهمی از نیازت است.',
        'NEEDS_EDUCATION': '🎓 آموزش و یادگیری ساختاریافته برایت اهمیت بالایی دارد.',
        'LOW_STUDY_TIME': '⏱️ زمان مطالعه مفید فعلی‌ات یکی از نقاط قابل بهبود است.',
        'WEAK_PLAN_EXECUTION': '🔄 اجرای برنامه یکی از نقاطی است که باید روی آن کار شود.',
        'NEEDS_REGULAR_MONITORING': '📈 از بررسی منظم عملکردت بیشترین استفاده را می‌بری.',
        'NEEDS_FULL_EDUCATION': '🎓 آموزش، کلاس و رفع اشکال یکجا برایت ارزشمند است.',
        'WANTS_FULL_MANAGEMENT': '🧭 خودت هم مدیریت کامل مسیر را به‌عنوان نیاز اصلی انتخاب کردی.'
    }
    used = []
    for code in reasons:
        if code in reason_map and reason_map[code] not in used:
            used.append(reason_map[code])
    if not used:
        used = ['🧩 پیشنهاد بر اساس ترکیب کامل پاسخ‌هایت ساخته شده، نه یک سؤال منفرد.']
    text += '\n' + '\n'.join('• ' + x for x in used[:3])
    text += '\n\n🏷️ پروفایل تو:\n' + '  '.join(tags[:4])
    if len(recs) > 1:
        text += f'\n\n🔎 نتیجه نزدیک بود: {PACKAGES[recs[1]]["title"]} هم به شرایطت نزدیک است؛ برای انتخاب نهایی، بررسی انسانی PULSE بهتر است.'
    text += '\n\n🚀 قدم بعدی: اگر می‌خواهی مسیرت دقیق‌تر بررسی شود، درخواست بررسی مسیر را بزن.'
    return text

def summary(msg, phone, d, recs, scores, reasons, tags, confidence):
    u = msg.get('from', {}).get('username', '')
    lines = ['🔔 لید جدید PULSE', '', f'👤 {fullname(msg) or "بدون نام"}', f'📱 {phone}', f'🔗 @{u}' if u else '🔗 username: ندارد']
    labels = {k: q.replace('؟', '') for k, q, _ in QUESTIONS}
    for k, v in d.items():
        lines.append(f'• {labels.get(k, k)}: {v}')
    lines += ['', f'🎯 پیشنهاد اصلی: {recs[0]}', f'📊 امتیازها: PLUS={scores["PLUS"]} | PRO={scores["PRO"]} | 360={scores["360"]}', f'📌 اطمینان: {confidence}', f'🏷️ تگ‌ها: {" | ".join(tags)}']
    return '\n'.join(lines)

def handle(msg):
    cid = msg['chat']['id']; text = msg.get('text', '')
    if text == '/id': send(cid, str(cid)); return
    if text == '/start':
        state[cid] = {'i': -1, 'd': {}, 'phone': '', 'telegram_username': msg.get('from', {}).get('username', ''), 'telegram_id': cid, 'recs': [], 'scores': {}, 'reasons': [], 'tags': [], 'confidence': '', 'lead_requested': False}
        send(cid, 'درود! 👋🔥\n\nبه گروه آموزشی PULSE خوش اومدی.\nاینجا چند سؤال کوتاه ازت می‌پرسیم تا بفهمیم کدوم مسیر واقعاً بیشتر به شرایط و هدفت می‌خوره.\n\nنه آزمون عجیب داریم، نه فرم طولانی! 😎\nبزن بریم؟ 🚀', kb(['بزن بریم 🚀'])); return
    s = state.get(cid)
    if not s:
        send(cid, 'برای شروع /start رو بزن.'); return

    # Lead CTA must be handled before question routing. This prevents the final
    # keyboard button from being swallowed when the questionnaire index is complete.
    if text.strip() == '🚀 درخواست بررسی مسیر' and s.get('recs'):
        s['lead_requested'] = True
        s['telegram_username'] = msg.get('from', {}).get('username', s.get('telegram_username', ''))
        s['telegram_id'] = cid
        save(cid, msg, s.get('phone', ''), s['d'], s['recs'], s['scores'], s['reasons'], s['tags'])
        username_line = f'🔗 @{s["telegram_username"]}' if s.get('telegram_username') else '🔗 username: ندارد'
        admin_text = summary(msg, s.get('phone', ''), s['d'], s['recs'], s['scores'], s['reasons'], s['tags'], s['confidence'])
        admin_text += f'\n\n📥 درخواست بررسی مسیر: بله\n🆔 Telegram ID: {s["telegram_id"]}\n{username_line}'
        send(cid, '✅ درخواستت ثبت شد.\n\nاطلاعاتت به تیم PULSE رسید و مسیرت برای بررسی دقیق‌تر در نظر گرفته می‌شه.\n\n📞 شماره تماس و آیدی تلگرامت هم برای ارتباط با تیم ثبت شد.\n\n🚀 به‌زودی باهات ارتباط می‌گیریم.', rm())
        for aid in ADMIN_CHAT_IDS:
            try:
                send(aid, admin_text)
            except Exception:
                logging.exception('lead request admin notification failed')
        return
    if msg.get('contact'):
        c = msg['contact']; uid = msg.get('from', {}).get('id')
        if c.get('user_id') and c['user_id'] != uid:
            send(cid, 'لطفاً شماره خودت رو با دکمه ارسال کن.'); return
        s['phone'] = c.get('phone_number', '')
        s['recs'], s['scores'], s['reasons'], s['tags'], s['confidence'] = recommend(s['d'])
        s['telegram_username'] = msg.get('from', {}).get('username', s.get('telegram_username', ''))
        s['telegram_id'] = cid
        save(cid, msg, s['phone'], s['d'], s['recs'], s['scores'], s['reasons'], s['tags'])
        send(cid, result_message(s['d'], s['recs'], s['scores'], s['reasons'], s['tags'], s['confidence']), kb(['🚀 درخواست بررسی مسیر', '🔎 جزئیات مسیر', '🔄 شروع دوباره']))
        return
    if s['i'] == -1:
        if text == 'بزن بریم 🚀': s['i'] = 0
        else: return
    # Handle the conditional missing-need question before normal question routing.
    if s['d'].get('_waiting_missing_need'):
        if text not in MISSING_SCORES:
            send(cid, 'لطفاً یکی از گزینه‌های نمایش‌داده‌شده رو انتخاب کن. 👇', kb(list(MISSING_SCORES.keys())))
            return
        s['d']['missing_need'] = text
        s['d'].pop('_waiting_missing_need', None)
        if s['i'] < len(QUESTIONS):
            _, q2, o2 = QUESTIONS[s['i']]; send(cid, q2, kb(o2))
        return
    if 0 <= s['i'] < len(QUESTIONS):
        key, q, opts = QUESTIONS[s['i']]
        if text not in opts:
            send(cid, 'لطفاً یکی از گزینه‌های نمایش‌داده‌شده رو انتخاب کن. 👇', kb(opts)); return
        s['d'][key] = text; s['i'] += 1
        # Conditional follow-up after existing resources are known.
        if key == 'resources' and text in ['کلاس آموزشی', 'مشاور', 'آزمون آزمایشی', 'کلاس + مشاور', 'چند مورد از این‌ها', 'قبلاً استفاده کردم ولی الان ندارم']:
            s['d']['_waiting_missing_need'] = True
            send(cid, 'از چیزهایی که تا الان داشتی، فکر می‌کنی بیشتر از همه جای چه چیزی خالیه؟ 🧩', kb(list(MISSING_SCORES.keys())))
            return
        if s['d'].pop('_waiting_missing_need', False):
            pass
        if s['i'] < len(QUESTIONS):
            _, q2, o2 = QUESTIONS[s['i']]; send(cid, q2, kb(o2))
        else:
            send(cid, 'خیلی خوب! 🔥\n\nفقط یک قدم مونده تا نتیجه بررسی PULSE رو ببینی.\nبرای اینکه تیم PULSE بتونه نتیجه و مسیر پیشنهادی رو باهات در میون بذاره، شماره تماست رو ارسال کن. 📞', contact_kb())
        return
    # Handle the conditional missing-need answer after the normal question handler.
    if s['d'].get('_waiting_missing_need') and text in MISSING_SCORES:
        s['d']['missing_need'] = text
        s['d'].pop('_waiting_missing_need', None)
        if s['i'] < len(QUESTIONS):
            _, q2, o2 = QUESTIONS[s['i']]; send(cid, q2, kb(o2))
        return
    if text == '🔎 جزئیات مسیر' and s['recs']:
        p = PACKAGES[s['recs'][0]]
        send(cid, f'{p["title"]}\n\n{p["desc"]}\n\n' + '\n'.join('✓ ' + x for x in p['features']) + '\n\n💡 قیمت و شرایط نهایی ثابت نیست و بعد از بررسی شرایطت باهات هماهنگ می‌شه.')
        return
    if text == '🔄 شروع دوباره':
        state.pop(cid, None); send(cid, 'حتماً. /start رو بزن. 👋'); return

WEBHOOK_PATH = '/telegram-webhook'

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ('/', '/health'):
            body = b'PULSE Bot is running'
            self.send_response(200); self.send_header('Content-Type', 'text/plain; charset=utf-8'); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        if self.path != WEBHOOK_PATH:
            self.send_response(404); self.end_headers(); return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            raw = self.rfile.read(length); update = json.loads(raw.decode('utf-8')); msg = update.get('message')
            if msg: handle(msg)
            self.send_response(200); self.end_headers(); self.wfile.write(b'ok')
        except Exception:
            logging.exception('webhook error'); self.send_response(500); self.end_headers()

    def log_message(self, format, *args):
        return

def main():
    db(); port = int(os.getenv('PORT', '10000')); server = ThreadingHTTPServer(('0.0.0.0', port), HealthHandler)
    public_url = os.getenv('RENDER_EXTERNAL_URL', '').strip().rstrip('/')
    if public_url:
        webhook_url = public_url + WEBHOOK_PATH
        try:
            result = tg('setWebhook', {'url': webhook_url, 'allowed_updates': ['message']})
            logging.info('Telegram webhook configured: %s', result)
        except Exception:
            logging.exception('failed to configure Telegram webhook')
    logging.info('PULSE Bot V2 diagnostic running on port %s', port)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__ == '__main__': main()
