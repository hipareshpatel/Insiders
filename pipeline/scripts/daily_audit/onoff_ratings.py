"""F111 on/off: stored rating cards whose before/after comparison the same-agency rule keeps or drops (no AI).
Run: python -I onoff_ratings.py <feed1.json> [feed2.json ...]  (also reads the live first page and /api/companies/<scrip>)."""
import json,subprocess,sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'src'))
from bse_intel.card_context import _same_agency, agency_of
cs={}
for f in sys.argv[1:]:  # cached /api/feed exports (JSON with a cards list)
    d=json.load(open(f)); d=d['cards'] if isinstance(d,dict) else d
    for c in d: cs[c['news_id']]=c
f=json.loads(subprocess.check_output(['curl','-s','https://insiders.reply-bd3.workers.dev/api/feed?range=7d&limit=40']))
for c in f['cards']: cs[c['news_id']]=c
rows=[];mem={}
for c in cs.values():
    cj=c['card_json']; cj=json.loads(cj) if isinstance(cj,str) else cj
    rc=cj.get('rating_change')
    if not rc or rc.get('before') is None or not rc.get('as_of_before'): continue
    s=c['scrip_code']
    if s not in mem: mem[s]=json.loads(subprocess.check_output(['curl','-s',f'https://insiders.reply-bd3.workers.dev/api/companies/{s}']))['dossier'].get('balance_sheet',[])
    bs=mem[s]
    now=next((x for x in bs if x.get('source_news_id')==c['news_id']),None)
    prev=next((x for x in bs if (x.get('as_of') or '')[:10]==rc['as_of_before'] and x.get('credit_rating')),None)
    if not now or not prev: rows.append((c['symbol'],c['news_id'],'unmatched',rc)); continue
    keep=_same_agency(prev,now,agency_of(now))
    rows.append((c['symbol'],c['news_id'],'kept' if keep else 'DROPPED',rc['before'],rc['after'],rc['notches'],prev.get('rating_agency'),prev.get('credit_rating'),now.get('rating_agency'),now.get('credit_rating')))
from collections import Counter
print(Counter(r[2] for r in rows))
for r in rows:
    if r[2]!='kept': print(r)
