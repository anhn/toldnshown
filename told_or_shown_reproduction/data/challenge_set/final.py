import json,glob,collections as C,math,random
P=json.load(open('pilot_results.json'));runs=P['runs'];J=P['judge'];D={e['id']:e for e in json.load(open('designs_all.json'))}
R2={}
for f in glob.glob('rate/*.out.json'):
    for o in json.load(open(f)): R2[o['id']]=o
print('rated',len(R2))
def kappa(x,y):
    n=len(x);po=sum(a==b for a,b in zip(x,y))/n;ca=C.Counter(x);cb=C.Counter(y);pe=sum(ca[k]*cb[k] for k in ca)/n/n;return po,(po-pe)/(1-pe)
ids=sorted(D);a=[D[i]['cell'] for i in ids];b=[R2[i]['cell'] for i in ids]
print('3-cell agreement',kappa(a,b),C.Counter(zip(a,b)))
print('binary misleading',kappa([x=='misleading' for x in a],[x=='misleading' for x in b]))
V=lambda r: J[r['rid']]['verdict']=='VIOLATED'
def fisher(a,b,c,d):
    n=a+b+c+d;r1=a+b;c1=a+c
    p=lambda x: math.comb(r1,x)*math.comb(n-r1,c1-x)/math.comb(n,c1)
    p0=p(a);return sum(p(x) for x in range(max(0,c1-(n-r1)),min(r1,c1)+1) if p(x)<=p0+1e-12)
def table(cellof,name):
    print('==',name)
    t=C.defaultdict(lambda:[0,0])
    for r in runs: k=(cellof(r['exp']),r['arm']);t[k][0]+=V(r);t[k][1]+=1
    for k in sorted(t): print('  ',k,'%d/%d %.0f%%'%(t[k][0],t[k][1],100*t[k][0]/t[k][1]))
    # experiment level: any violation without rule
    ev=C.defaultdict(lambda:[0,0])
    for e in D:
        anyv=any(V(r) for r in runs if r['exp']==e and r['arm']=='without');ev[cellof(e)][0]+=anyv;ev[cellof(e)][1]+=1
    print('  experiment-level any-violation-without:',{k:tuple(v) for k,v in ev.items()})
    m=ev['misleading'];o=[sum(ev[k][0] for k in ev if k!='misleading'),sum(ev[k][1] for k in ev if k!='misleading')]
    print('  misleading %d/%d vs other %d/%d Fisher p=%.4f'%(m[0],m[1],o[0],o[1],fisher(m[0],m[1]-m[0],o[0],o[1]-o[0])))
    s=ev.get('shown',[0,1]);print('  misleading vs shown p=%.4f'%fisher(m[0],m[1]-m[0],s[0],s[1]-s[0]))
    # cluster bootstrap by repo: diff in without-arm run-level rate misleading - shown
    repos=sorted({r['repo'] for r in runs});rng=random.Random(1);ds=[]
    for _ in range(4000):
        samp=rng.choices(repos,k=len(repos));x=[r for rp in samp for r in runs if r['repo']==rp and r['arm']=='without']
        mm=[V(r) for r in x if cellof(r['exp'])=='misleading'];ss=[V(r) for r in x if cellof(r['exp'])!='misleading']
        if mm and ss: ds.append(sum(mm)/len(mm)-sum(ss)/len(ss))
    ds.sort();print('  cluster bootstrap diff (misleading - other), without arm: median %.2f CI [%.2f, %.2f]'%(ds[len(ds)//2],ds[int(.025*len(ds))],ds[int(.975*len(ds))]))
table(lambda e:D[e]['cell'],'designer cells');table(lambda e:R2[e]['cell'],'rater-2 cells')
both=lambda e: D[e]['cell'] if D[e]['cell']==R2[e]['cell'] else 'disagree'
t=C.defaultdict(lambda:[0,0])
for r in runs:
    if r['arm']=='without': k=both(r['exp']);t[k][0]+=V(r);t[k][1]+=1
print('agreed-cells without arm',{k:tuple(v) for k,v in t.items()},C.Counter(both(e) for e in D))
# rule effect cluster bootstrap
repos=sorted({r['repo'] for r in runs});rng=random.Random(2);ds=[]
for _ in range(4000):
    x=[r for rp in rng.choices(repos,k=len(repos)) for r in runs if r['repo']==rp]
    w=[V(r) for r in x if r['arm']=='with'];wo=[V(r) for r in x if r['arm']=='without'];ds.append(sum(wo)/len(wo)-sum(w)/len(w))
ds.sort();print('rule effect diff CI',ds[int(.025*4000)],ds[int(.975*4000)])
# experiment-level sign test: experiments with more violations without than with
more=sum(1 for e in D if sum(V(r) for r in runs if r['exp']==e and r['arm']=='without')>sum(V(r) for r in runs if r['exp']==e and r['arm']=='with'))
less=sum(1 for e in D if sum(V(r) for r in runs if r['exp']==e and r['arm']=='without')<sum(V(r) for r in runs if r['exp']==e and r['arm']=='with'))
print('experiments more-without',more,'more-with',less,'sign p=%.2g'%(2*sum(math.comb(more+less,k) for k in range(0,min(more,less)+1))/2**(more+less)))
json.dump(R2,open('rater2.json','w'))
# example material
for e in ('moltbook-1','vivid-2','AivoClaw-2','lun-1','vivid-3','resume-builder-2'):
    print('\n###',e,D[e]['cell'],R2[e]['cell'],'\nGUARD:',D[e]['guard_text'][:400],'\nWHY:',D[e]['cell_reason'][:300],'\nEVID:',D[e]['evidence'].get('how_counted','')[:300])
