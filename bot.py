import os, json, sqlite3, logging, requests
from datetime import datetime, timezone

TOKEN = os.getenv('BOT_TOKEN','').strip()
ADMIN_CHAT_IDS = [x.strip() for x in os.getenv('ADMIN_CHAT_IDS','').split(',') if x.strip()]
DB_PATH = os.getenv('DB_PATH','pulse.db')
if not TOKEN:
    raise SystemExit('BOT_TOKEN is missing. Set it in the environment before running.')
API=f'https://api.telegram.org/bot{TOKEN}'
logging.basicConfig(level=logging.INFO)

QUESTIONS=[
('grade','پایه‌ات رو انتخاب کن:', ['دهم','یازدهم','دوازدهم','فارغ‌التحصیل']),
('field','رشته‌ات چیه؟', ['تجربی','ریاضی','انسانی','فنی‌وحرفه‌ای','سایر']),
('exam_year','برای کدوم کنکور آماده می‌شی؟', ['کنکور ۱۴۰۶','کنکور ۱۴۰۷','کنکور ۱۴۰۸','هنوز مشخص نیست']),
('goal','هدف اصلیت چیه؟', ['رتبه خیلی خوب','قبولی رشته/دانشگاه خاص','قبولی در رشته موردنظر','هنوز دقیق مشخص نیست']),
('study_hours','الان میانگین مطالعه‌ات در روز چقدره؟', ['کمتر از ۲ ساعت','۲ تا ۴ ساعت','۴ تا ۶ ساعت','۶ تا ۸ ساعت','بیشتر از ۸ ساعت']),
('discipline','وضعیت نظم مطالعاتی‌ات چطوره؟', ['منظمم','گاهی منظمم','بی‌نظمم','تقریباً شروع نکردم']),
('main_need','بیشتر از همه در چه چیزی مشکل داری؟', ['برنامه‌ریزی','آموزش','تست‌زنی','مرور','تمرکز و پیگیری','تقریباً همه موارد']),
('classes','الان کلاس آموزشی یا مشاور داری؟', ['بله، کلاس دارم','بله، مشاور دارم','هر دو را دارم','هیچ‌کدام']),
('budget','برای انتخاب مسیر، کدوم حالت به شرایطت نزدیک‌تره؟', ['اقتصادی‌تر','متعادل','کامل‌ترین مسیر برایم مهم‌تر است','فعلاً مطمئن نیستم']),
]
PACKAGES={
'PLUS': {'desc':'مسیر اقتصادی‌تر برای شروع با خدمات اصلی.','features':['برنامه‌ریزی پایه','پشتیبانی و پیگیری اصلی','ارزیابی اولیه']},
'PRO': {'desc':'مسیر متعادل برای دانش‌آموزی که آموزش، برنامه‌ریزی و پیگیری جدی‌تری می‌خواهد.','features':['برنامه‌ریزی شخصی‌سازی‌شده','پیگیری مستمر','خدمات آموزشی','ارزیابی و تحلیل']},
'360': {'desc':'مسیر کامل و یکپارچه برای مدیریت بخش‌های اصلی مسیر کنکور.','features':['آموزش','مشاوره و برنامه‌ریزی','آزمون و تحلیل','پیگیری یکپارچه']}}

state={}
def db():
    c=sqlite3.connect(DB_PATH)
    c.execute('''CREATE TABLE IF NOT EXISTS students(
      chat_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, phone TEXT,
      data_json TEXT, recommendation TEXT, created_at TEXT)''')
    c.commit(); return c

def tg(method,payload):
    r=requests.post(f'{API}/{method}',json=payload,timeout=35); r.raise_for_status(); return r.json()
def send(cid,text,markup=None):
    p={'chat_id':cid,'text':text}
    if markup: p['reply_markup']=markup
    return tg('sendMessage',p)
def kb(opts): return {'keyboard':[[{'text':x} for x in opts[i:i+2]] for i in range(0,len(opts),2)],'resize_keyboard':True,'one_time_keyboard':True}
def rm(): return {'remove_keyboard':True}
def contact_kb(): return {'keyboard':[[{'text':'📞 ارسال شماره تماس','request_contact':True}]],'resize_keyboard':True,'one_time_keyboard':True}
def fullname(msg):
    u=msg.get('from',{}); return (' '.join(x for x in [u.get('first_name',''),u.get('last_name','')] if x)).strip()

def recommend(d):
    s={'PLUS':0,'PRO':0,'360':0}
    if d.get('budget')=='اقتصادی‌تر': s['PLUS']+=4
    elif d.get('budget')=='کامل‌ترین مسیر برایم مهم‌تر است': s['360']+=4
    else: s['PRO']+=2
    if d.get('main_need') in ['آموزش','تست‌زنی','تقریباً همه موارد']: s['PRO']+=2; s['360']+=2
    if d.get('main_need') in ['برنامه‌ریزی','تمرکز و پیگیری','مرور']: s['PRO']+=2; s['360']+=1
    if d.get('discipline') in ['بی‌نظمم','تقریباً شروع نکردم']: s['PRO']+=2; s['360']+=2
    if d.get('classes')=='هیچ‌کدام': s['PRO']+=1; s['360']+=2
    if d.get('goal') in ['رتبه خیلی خوب','قبولی رشته/دانشگاه خاص']: s['PRO']+=1; s['360']+=1
    if d.get('study_hours') in ['۶ تا ۸ ساعت','بیشتر از ۸ ساعت']: s['360']+=1
    best=max(s,key=s.get); return best,s

def save(cid,msg,phone,d,rec):
    c=db(); c.execute('''INSERT INTO students VALUES(?,?,?,?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET username=excluded.username,full_name=excluded.full_name,phone=excluded.phone,data_json=excluded.data_json,recommendation=excluded.recommendation''',
      (cid,msg.get('from',{}).get('username',''),fullname(msg),phone,json.dumps(d,ensure_ascii=False),rec,datetime.now(timezone.utc).isoformat())); c.commit(); c.close()

def summary(msg,phone,d,rec):
    u=msg.get('from',{}).get('username',''); lines=['🔔 لید جدید PULSE','',f'👤 {fullname(msg) or "بدون نام"}',f'📱 {phone}',f'🔗 @{u}' if u else '🔗 username: ندارد']
    labels={k:q.replace('؟','') for k,q,_ in QUESTIONS}
    lines += [f'• {labels[k]}: {v}' for k,v in d.items()]; lines += ['',f'🎯 پیشنهاد سیستم: {rec}']; return '\n'.join(lines)

def handle(msg):
    cid=msg['chat']['id']; text=msg.get('text','')
    if text=='/id': send(cid,str(cid)); return
    if text=='/start':
        state[cid]={'i':-1,'d':{},'phone':'','rec':''}
        send(cid,'به PULSE خوش اومدی 👋\n\nچند سؤال کوتاه ازت می‌پرسیم تا بر اساس شرایط و هدفت، مناسب‌ترین مسیر آموزشی رو پیشنهاد بدیم.\n\n⏱️ چند دقیقه بیشتر زمان نمی‌بره.',kb(['شروع کنیم 🚀'])); return
    s=state.get(cid)
    if not s: send(cid,'برای شروع /start رو بزن.'); return
    if msg.get('contact'):
        c=msg['contact']; uid=msg.get('from',{}).get('id')
        if c.get('user_id') and c['user_id']!=uid: send(cid,'لطفاً شماره خودت رو با دکمه ارسال کن.'); return
        s['phone']=c.get('phone_number',''); s['rec'],_=recommend(s['d']); save(cid,msg,s['phone'],s['d'],s['rec'])
        p=PACKAGES[s['rec']]
        send(cid,f'🎯 بررسی اولیه PULSE آماده‌ست.\n\nپیشنهاد اولیه ما برای تو:\n🟣 {s["rec"]}\n\n{p["desc"]}\n\n'+'\n'.join('✓ '+x for x in p['features'])+'\n\nاین پیشنهاد بر اساس اطلاعاتی که وارد کردی تهیه شده و تیم PULSE می‌تونه قبل از ثبت‌نام نهایی، شرایطت رو دقیق‌تر بررسی کنه.',kb(['📦 جزئیات پکیج','📞 درخواست تماس','🔄 شروع دوباره']))
        for aid in ADMIN_CHAT_IDS:
            try: send(aid,summary(msg,s['phone'],s['d'],s['rec']))
            except Exception: logging.exception('admin notification failed')
        return
    if s['i']==-1:
        if text=='شروع کنیم 🚀': s['i']=0
        else: return
    if 0<=s['i']<len(QUESTIONS):
        key,q,opts=QUESTIONS[s['i']]
        if text not in opts: send(cid,'لطفاً یکی از گزینه‌های نمایش‌داده‌شده رو انتخاب کن.',kb(opts)); return
        s['d'][key]=text; s['i']+=1
        if s['i']<len(QUESTIONS):
            _,q2,o2=QUESTIONS[s['i']]; send(cid,q2,kb(o2))
        else: send(cid,'خیلی خوب. فقط یک مرحله دیگه مونده 👇\n\nبرای اینکه تیم PULSE بتونه نتیجه بررسی رو باهات در میون بذاره، شماره تماست رو ارسال کن.',contact_kb())
        return
    if text=='📦 جزئیات پکیج':
        p=PACKAGES[s['rec']]; send(cid,f'🟣 {s["rec"]}\n\n{p["desc"]}\n\n'+'\n'.join('✓ '+x for x in p['features'])); return
    if text=='📞 درخواست تماس':
        send(cid,'درخواستت ثبت شد. تیم PULSE باهات ارتباط می‌گیره.',rm())
        for aid in ADMIN_CHAT_IDS:
            try: send(aid,f'📞 درخواست تماس\n👤 {fullname(msg)}\n📱 {s["phone"]}\n🎯 پکیج: {s["rec"]}')
            except Exception: pass
        return
    if text=='🔄 شروع دوباره': state.pop(cid,None); send(cid,'حتماً. /start رو بزن.'); return

def main():
    offset=None; db(); logging.info('PULSE Bot V1 running')
    while True:
        try:
            p={'timeout':30,'allowed_updates':['message']};
            if offset is not None: p['offset']=offset
            res=tg('getUpdates',p)
            for u in res.get('result',[]): offset=u['update_id']+1; handle(u.get('message',{}))
        except KeyboardInterrupt: break
        except Exception: logging.exception('polling error')
if __name__=='__main__': main()
