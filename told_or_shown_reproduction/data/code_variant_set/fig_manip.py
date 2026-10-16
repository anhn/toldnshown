import json,collections,matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
exec(open('figs.py').read().split('\n')[2])  # rcParams line
import re
src=open('figs.py').read()
BL,OR='#2a78d6','#eb6834'

runs=json.load(open('/tmp/study/evid/runs.json'))
names={'vivid-2':'Vivid.Math','gateway-3':'127.0.0.1','exabgp-3':'Buffer','lun-3':'editComputed','miniscira-2':'eventType()','resume-builder-2':'no payload'}
order=['miniscira-2','resume-builder-2','gateway-3','exabgp-3','vivid-2','lun-3']
evs=['shown','silent','misleading']
fig,axs=plt.subplots(1,2,figsize=(7.0,1.55),gridspec_kw={'width_ratios':[1,2.3]})
a=axs[0];T=collections.defaultdict(lambda:[0,0])
for r in runs: T[(r['ev'],r['arm'])][0]+=r['verdict']=='VIOLATED';T[(r['ev'],r['arm'])][1]+=1
w=.38
for k,(arm,col,h,nm) in enumerate([('without',OR,'////','rule removed'),('with',BL,'','rule present')]):
    v=[T[(e,arm)] for e in evs]
    a.bar([i+(k-.5)*w for i in range(3)],[100*p/n for p,n in v],w,color=col,hatch=h,edgecolor='white',linewidth=.3,label=nm)
    for i,(p,n) in enumerate(v): a.text(i+(k-.5)*w,100*p/n+2,'%d/%d'%(p,n),ha='center',fontsize=5.6)
a.set_xticks(range(3));a.set_xticklabels(['shown','silent','misleading']);a.set_ylim(0,110);a.set_ylabel('runs violating (%)');a.legend(frameon=False,fontsize=5.8,loc='upper left');a.set_title('(a) All six rules',loc='left',fontsize=7)
a=axs[1]
R=collections.defaultdict(lambda:collections.defaultdict(int))
for r in runs: R[r['exp']][(r['ev'],r['arm'])]+=r['verdict']=='VIOLATED'
x=0;ticks=[];labs=[];groups=[]
for exp in order:
    start=x
    for e in evs:
        if not any(rr['exp']==exp and rr['ev']==e for rr in runs): continue
        for k,(arm,col,h) in enumerate([('without',OR,'////'),('with',BL,'')]):
            v=R[exp][(e,arm)];a.bar(x+(k-.5)*.4,v,.4,color=col,hatch=h,edgecolor='white',linewidth=.3)
            if v==0: a.text(x+(k-.5)*.4,.05,'0',ha='center',fontsize=4.8,color=col)
        ticks.append(x);labs.append(e[:2]);x+=1
    groups.append((start,x-1,names[exp]));x+=.6
a.set_xticks(ticks);a.set_xticklabels(labs,fontsize=5.6);a.set_yticks([0,1,2,3]);a.set_ylim(0,3.9);a.set_ylabel('violating runs (of 3)')
for s,e,n in groups: a.text((s+e)/2,3.45,n,ha='center',fontsize=5.4)
a.set_title('(b) Per rule (sh = shown, si = silent, mi = misleading)',loc='left',fontsize=7)
plt.tight_layout(pad=.3,w_pad=1.2);plt.savefig('fig_manip.pdf');print('ok',OR,BL)
