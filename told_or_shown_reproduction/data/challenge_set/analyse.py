import json,glob,collections as C,math
from itertools import product
runs=json.load(open('runs.json'));D={e['id']:e for e in json.load(open('designs_all.json'))}
J={}
for f in glob.glob('judge/*.out.json'):
    for o in json.load(open(f)): J[o['rid']]=o
S=json.load(open('results.json'))
print('judged',len(J),'of',len(runs),C.Counter(o['verdict'] for o in J.values()))
# agreement judge vs script on experiments with non-contaminated checks
badchk={'soundshuman-1','soundshuman-2','soundshuman-3','ThomsonLint-1','ThomsonLint-2','ThomsonLint-3','miniscira-3'}
import subprocess
ag=C.Counter()
for r in runs:
    if r['exp'] in badchk: continue
    s=subprocess.run(['bash','-c',D[r['exp']]['check_cmd']],cwd=f"/tmp/fx/{r['rid']}/repo",capture_output=True,text=True).stdout.strip().split('\n')[-1]
    r['script']=s;ag[(J[r['rid']]['verdict'],s)]+=1
print('judge vs script',dict(ag))
for r in runs:
    if 'script' in r and r['script'] in('VIOLATED','OBEYED') and J[r['rid']]['verdict']!=r['script']: print('  disagree',r['rid'],r['exp'],r['arm'],r['model'],'judge',J[r['rid']]['verdict'],'script',r['script'],'|',J[r['rid']]['reason'])
def fisher(a,b,c,d):
    n=a+b+c+d;r1=a+b;c1=a+c
    def p(x): return math.comb(r1,x)*math.comb(n-r1,c1-x)/math.comb(n,c1)
    p0=p(a);return sum(p(x) for x in range(max(0,c1-(n-r1)),min(r1,c1)+1) if p(x)<=p0+1e-12)
V=lambda r: J[r['rid']]['verdict']=='VIOLATED'
print('\n== violation rate by arm x cell (both models)')
for group in (lambda r:r['cell'], lambda r:(r['kind'],r['cell']), lambda r:r['kind']):
    t=C.defaultdict(lambda:[0,0])
    for r in runs:
        k=(group(r),r['arm']);t[k][0]+=V(r);t[k][1]+=1
    for k in sorted(t,key=str): print('  ',k,'%d/%d = %.0f%%'%(t[k][0],t[k][1],100*t[k][0]/t[k][1]))
print('\n== by model')
t=C.defaultdict(lambda:[0,0])
for r in runs:
    k=(r['model'],r['cell'],r['arm']);t[k][0]+=V(r);t[k][1]+=1
for k in sorted(t): print('  ',k,'%d/%d = %.0f%%'%(t[k][0],t[k][1],100*t[k][0]/t[k][1]))
# tests: without arm, misleading vs (shown+silent)
def cnt(f): 
    x=[r for r in runs if f(r)];return sum(V(r) for r in x),len(x)
a,n1=cnt(lambda r:r['arm']=='without' and r['cell']=='misleading');c,n2=cnt(lambda r:r['arm']=='without' and r['cell']!='misleading')
print('\nwithout arm: misleading %d/%d vs other %d/%d Fisher p=%.2g'%(a,n1,c,n2,fisher(a,n1-a,c,n2-c)))
a,n1=cnt(lambda r:r['arm']=='without');c,n2=cnt(lambda r:r['arm']=='with')
print('rule effect: without %d/%d vs with %d/%d Fisher p=%.2g'%(a,n1,c,n2,fisher(a,n1-a,c,n2-c)))
# paired McNemar per (exp,model)
pairs=C.defaultdict(dict)
for r in runs: pairs[(r['exp'],r['model'])][r['arm']]=V(r)
b=sum(1 for p in pairs.values() if p['without'] and not p['with']);c=sum(1 for p in pairs.values() if p['with'] and not p['without'])
print('pairs: violated only without',b,'only with',c,'both',sum(p['with'] and p['without'] for p in pairs.values()),'neither',sum(not p['with'] and not p['without'] for p in pairs.values()),'exact binomial p=%.2g'%(2*sum(math.comb(b+c,k) for k in range(0,min(b,c)+1))/2**(b+c)))
# per-experiment classification (experiment level, any-model)
print('\n== experiment-level')
cls=C.defaultdict(C.Counter);rows=[]
for e in D:
    w=[pairs[(e,m)]['with'] for m in ('opus','haiku')];wo=[pairs[(e,m)]['without'] for m in ('opus','haiku')]
    c='needed' if sum(wo)>sum(w) and sum(w)==0 else ('partly' if sum(wo)>sum(w) else ('ineffective' if sum(w)>0 and sum(wo)>0 else ('dead' if sum(wo)==0 and sum(w)==0 else 'odd')))
    cls[D[e]['cell']][c]+=1;rows.append((e,D[e]['kind'],D[e]['cell'],w,wo,c,len(D[e].get('also_stated_in',[])),D[e]['evidence'].get('explained_in_code_comment')))
for r in rows: print('  %-26s %-10s %-10s with(o,h)=%s without(o,h)=%s %-11s docs=%d comment=%s'%r)
for k,v in cls.items(): print(k,dict(v))
# effect of prose documentation elsewhere / comment in without arm
for name,f in (('code comment explains',lambda e:bool(D[e]['evidence'].get('explained_in_code_comment'))),('stated in other docs',lambda e:len(D[e].get('also_stated_in',[]))>0)):
    for val in (True,False):
        a,n=cnt(lambda r:r['arm']=='without' and f(r['exp'])==val);print(name,val,'without-arm violations %d/%d'%(a,n))
aw=C.Counter((r['arm'],J[r['rid']].get('aware')) for r in runs);print('aware flag by arm',dict(aw))
json.dump({'runs':runs,'judge':J},open('pilot_results.json','w'),indent=0)
