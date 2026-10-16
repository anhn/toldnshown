import json,gzip,re,random,collections as C,sys
sys.argv=['x'];src=open('prep.py').read();ns={}
exec(src[src.index('def real'):src.index('rng=random.Random')],{'re':re},ns);segment=ns['segment'];real=ns['real']
R=[json.loads(l) for l in gzip.open('corpus.jsonl.gz','rt')]
NEG=re.compile(r"\b(never|do not|don't|dont|must not|mustn't|should not|shouldn't|avoid|forbidden|prohibited|not allowed|no longer|instead of|rather than|unless explicitly|without (asking|permission|approval)|stop and ask|refrain)\b|\bNO\b|\bNOT\b|\bNEVER\b|🚫|❌|⚠",re.I)
EMPH=re.compile(r"\b(IMPORTANT|CRITICAL|MUST|ALWAYS|WARNING|MANDATORY|NON-NEGOTIABLE)\b")
INC=re.compile(r"\b(previously|in the past|used to|has (broken|caused)|this (broke|caused)|we had|learned|lesson|incident|regress|keeps? (doing|adding|trying)|tends? to|repeatedly|hallucinat|common mistake|common pitfall|past mistake|agents? (often|sometimes|frequently|have|has))\b",re.I)
allit=[];per=[]
for r in R:
    fn='AGENTS.md' if real(r['files'].get('AGENTS.md')) else ('CLAUDE.md' if real(r['files'].get('CLAUDE.md')) else None)
    if not fn: continue
    its=[i for i in segment(r['files'][fn].replace('\r\n','\n')) if i['kind']!='code']
    n=0
    for k,i in enumerate(its):
        t=i['text'].strip()
        if len(t)<25: continue
        neg=bool(NEG.search(t));em=bool(EMPH.search(t));inc=bool(INC.search(t))
        allit.append(dict(repo=r['repo'],file=fn,head=i['head'],text=t,neg=neg,emph=em,inc=inc,stars=r['stars'],lang=r['lang'],agent=(r['commits100']['agent']/max(1,r['commits100']['n']))))
        n+=neg
    per.append((r['repo'],len(its),n))
N=len(allit);neg=[i for i in allit if i['neg']]
print('files',len(per),'prose items',N,'neg',len(neg),round(100*len(neg)/N,1),'emph',sum(i['emph'] for i in allit),'inc',sum(i['inc'] for i in allit),'neg&inc',sum(i['inc'] for i in neg))
print('files with >=1 neg',sum(p[2]>0 for p in per),'median neg per file',sorted(p[2] for p in per)[len(per)//2],'p90',sorted(p[2] for p in per)[int(.9*len(per))])
rng=random.Random(7)
# sample: at most 2 per repo, short enough
byr=C.defaultdict(list)
for i in neg:
    if len(i['text'])<=700: byr[i['repo']].append(i)
pool=[]
for repo,v in byr.items(): pool+=rng.sample(v,min(2,len(v)))
rng.shuffle(pool);samp=pool[:2400]
for k,i in enumerate(samp): i['id']='s%04d'%k
print('pool',len(pool),'sample',len(samp),'repos',len({i['repo'] for i in samp}))
json.dump(allit,open('/tmp/study/scar/all_items.json','w'));json.dump(samp,open('/tmp/study/scar/sample.json','w'))
for j in range(0,2400,200):
    json.dump([{'id':i['id'],'section':i['head'][-80:],'text':i['text']} for i in samp[j:j+200]],open('/tmp/study/scar/in_%02d.json'%(j//200),'w'),indent=0,ensure_ascii=False)
for i in samp[:12]: print('-',i['text'][:160].replace('\n',' '))
