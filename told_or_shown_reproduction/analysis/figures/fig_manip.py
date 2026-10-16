import os
DATA=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','data')
import json,collections,matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams.update({'font.size':6.2,'font.family':'DejaVu Sans','axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.6,'pdf.fonttype':42,'hatch.linewidth':.5})
runs=json.load(open(os.path.join(DATA,'code_variant_set','runs.json')))
T=collections.defaultdict(lambda:[0,0])
for r in runs: T[(r['ev'],r['arm'])][0]+=r['verdict']=='VIOLATED';T[(r['ev'],r['arm'])][1]+=1
evs=['shown','silent','misleading'];w=.36
fig,a=plt.subplots(figsize=(3.45,1.32))
for k,(arm,fc,h,nm) in enumerate([('without','white','//////','rule removed'),('with','0.35','','rule present')]):
    v=[T[(e,arm)] for e in evs]
    a.bar([i+(k-.5)*w for i in range(3)],[100*p/n for p,n in v],w,color=fc,hatch=h,edgecolor='0.1',linewidth=.5,label=nm)
    for i,(p,n) in enumerate(v): a.text(i+(k-.5)*w,100*p/n+3,'%d/%d'%(p,n),ha='center',fontsize=5.6)
a.set_xticks(range(3));a.set_xticklabels(['code shows the practice','code silent (4 rules)','code misleads']);a.set_ylim(0,112);a.set_yticks([0,50,100])
a.set_ylabel('runs violating (%)');a.legend(frameon=False,fontsize=5.8,loc='upper left')
plt.tight_layout(pad=.25);plt.savefig('fig_manip.pdf');plt.savefig('fig_manip.png',dpi=220)
