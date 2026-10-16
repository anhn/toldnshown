import os
import json,collections as C,itertools,random,statistics as st
r=json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'../../data/code_variant_set/runs.json')))
c=C.defaultdict(lambda:[0,0])
for x in r:
    for m in (x['model'],'all'):
        k=(x['exp'],x['ev'],x['arm'],m); c[k][0]+=x['verdict']=='VIOLATED'; c[k][1]+=1
rules=sorted({x['exp'] for x in r}); E=['shown','silent','misleading']
def rate(e,s,a,m='all'): v,n=c[(e,s,a,m)]; return v/n if n else None
def need(e,s,m='all'):
    a,b=rate(e,s,'without',m),rate(e,s,'with',m); return None if a is None else a-b
# balanced: average over the two models
def needB(e,s): 
    x=[need(e,s,m) for m in ('opus','haiku')]; return None if x[0] is None else sum(x)/2
print('rule | shown wo/w | silent wo/w | misleading wo/w | need sh si mi | diff mi-sh (pooled, balanced)')
D=[];DB=[]
for e in rules:
    row=[]
    for s in E:
        v=c[(e,s,'without','all')];w=c[(e,s,'with','all')]
        row.append(f"{v[0]}/{v[1]} {w[0]}/{w[1]}" if v[1] else '--')
    ns=[need(e,s) for s in E]
    d=need(e,'misleading')-need(e,'shown'); db=needB(e,'misleading')-needB(e,'shown'); D.append(d);DB.append(db)
    print(e,'|',' | '.join(row),'|',[None if x is None else round(x,2) for x in ns],'|',round(d,2),round(db,2))
for name,X in (('pooled',D),('model-balanced',DB)):
    m=st.mean(X)
    # exact sign-flip (randomisation) test over rules, one-sided
    fl=[sum(s*x for s,x in zip(sg,X))/len(X) for sg in itertools.product([1,-1],repeat=len(X))]
    p=sum(f>=m-1e-12 for f in fl)/len(fl)
    # cluster bootstrap over rules
    random.seed(1);bs=sorted(st.mean(random.choices(X,k=len(X))) for _ in range(20000))
    # t interval
    se=st.stdev(X)/len(X)**.5; t=2.571
    print(f"{name}: mean diff {m:.2f}; rule-bootstrap 95% [{bs[500]:.2f},{bs[19499]:.2f}]; t-interval [{m-t*se:.2f},{m+t*se:.2f}]; sign-flip one-sided p={p:.3f}; min {min(X):.2f}")
# per-rule need in misleading alone, and silent
for s in ('silent','misleading'):
    X=[need(e,s) for e in rules if need(e,s) is not None]
    random.seed(2);bs=sorted(st.mean(random.choices(X,k=len(X))) for _ in range(20000))
    print(s,'need per rule',[round(x,2) for x in X],'mean',round(st.mean(X),2),'boot',round(bs[500],2),round(bs[19499],2))
# by model
for m in ('opus','haiku'):
    for s in E:
        a=sum(c[(e,s,'without',m)][0] for e in rules);n=sum(c[(e,s,'without',m)][1] for e in rules)
        b=sum(c[(e,s,'with',m)][0] for e in rules)
        print(m,s,f'{a}/{n} -> {b}/{n}')
