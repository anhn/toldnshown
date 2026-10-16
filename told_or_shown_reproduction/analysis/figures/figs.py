import os
DATA=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','data')
import json,collections as C,numpy as np,matplotlib
matplotlib.use('Agg');import matplotlib.pyplot as plt
plt.rcParams.update({'font.size':7,'font.family':'DejaVu Sans','axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.6,'pdf.fonttype':42,'hatch.linewidth':.5})
BL,OR,GR,YE,PK,DG='#2a78d6','#eb6834','#1baf7a','#eda100','#e87ba4','#008300'
P=json.load(open(os.path.join(DATA,'challenge_set','pilot_results.json')));runs=P['runs'];J=P['judge'];D={e['id']:e for e in json.load(open(os.path.join(DATA,'challenge_set','designs_all.json')))}
V=lambda r: J[r['rid']]['verdict']=='VIOLATED'
cells=['shown','silent','misleading'];lab=['Code shows\nthe practice','Code is silent\nor mixed','Code\nmisleads']
def rate(f):
    x=[r for r in runs if f(r)];return sum(V(r) for r in x),len(x)
# Fig 1
fig,ax=plt.subplots(1,2,figsize=(7.16,2.1),gridspec_kw={'width_ratios':[1,1.25]})
a=ax[0];x=np.arange(3);w=.36
for k,(arm,col,h,nm) in enumerate((('without',OR,'////','Rule removed'),('with',BL,'','Rule present'))):
    v=[rate(lambda r,c=c:r['cell']==c and r['arm']==arm) for c in cells]
    b=a.bar(x+(k-.5)*w,[100*p/n for p,n in v],w,color=col,hatch=h,edgecolor='white',linewidth=.3,label=nm)
    for xi,(p,n) in zip(x,v): a.text(xi+(k-.5)*w,100*p/n+2,'%d/%d'%(p,n),ha='center',fontsize=5.8)
a.set_xticks(x);a.set_xticklabels(lab);a.set_ylim(0,100);a.set_ylabel('runs violating the rule (%)');a.legend(frameon=False,fontsize=6,loc='upper left');a.set_title('(a) Both models',loc='left',fontsize=7)
a=ax[1];x=np.arange(3);w=.2
for k,(m,arm,col,h,nm) in enumerate((('opus','without',OR,'////','larger model, rule removed'),('haiku','without',YE,'....','smaller model, rule removed'),('opus','with',BL,'','larger model, rule present'),('haiku','with',GR,'xxxx','smaller model, rule present'))):
    v=[rate(lambda r,c=c:r['cell']==c and r['arm']==arm and r['model']==m) for c in cells]
    a.bar(x+(k-1.5)*w,[100*p/n for p,n in v],w,color=col,hatch=h,edgecolor='white',linewidth=.3,label=nm)
    for xi,(p,n) in zip(x,v): a.text(xi+(k-1.5)*w,100*p/n+2,'%d'%p,ha='center',fontsize=5.6)
a.set_xticks(x);a.set_xticklabels(lab);a.set_ylim(0,100);a.legend(frameon=False,fontsize=5.6,loc='upper left',labelspacing=.25);a.set_title('(b) By model (number of violating runs above each bar; n = 19, 11, 17 per bar)',loc='left',fontsize=7)
fig.tight_layout(w_pad=1.2);fig.savefig('fig_cells.pdf',bbox_inches='tight',pad_inches=.03);fig.savefig('fig_cells.png',dpi=160,bbox_inches='tight')
# Fig 2: grid
order=[e for c in cells for e in sorted(D,key=lambda e:(D[e]['kind'],e)) if D[e]['cell']==c]
order=[]
for c in cells:
    es=[e for e in D if D[e]['cell']==c]
    es.sort(key=lambda e:(-sum(V(r) for r in runs if r['exp']==e and r['arm']=='without'),-sum(V(r) for r in runs if r['exp']==e),D[e]['kind'],e));order+=es
rowsdef=[('without','opus','rule removed, larger model'),('without','haiku','rule removed, smaller model'),('with','opus','rule present, larger model'),('with','haiku','rule present, smaller model')]
fig,a=plt.subplots(figsize=(7.16,1.55))
for j,e in enumerate(order):
    for i,(arm,m,_) in enumerate(rowsdef):
        r=[r for r in runs if r['exp']==e and r['arm']==arm and r['model']==m][0];v=V(r)
        a.add_patch(plt.Rectangle((j+.08,3-i+.1),.84,.8,facecolor=(OR if arm=='without' else BL) if v else 'white',edgecolor='0.55',linewidth=.4,hatch='////' if (v and arm=='without') else ''))
    a.text(j+.5,-.25,'F' if D[e]['kind']=='fence' else 'C',ha='center',va='top',fontsize=5.2,color='0.25')
pos=0
for c,l in zip(cells,('Code shows the practice (19 rules)','Silent or mixed (11)','Code misleads (17)')):
    n=sum(D[e]['cell']==c for e in D);a.text(pos+n/2,4.25,l,ha='center',fontsize=6.5)
    if pos: a.plot([pos,pos],[-.9,4.9],color='0.2',lw=.8)
    pos+=n
for i,(_,_,l) in enumerate(rowsdef): a.text(-.4,3-i+.5,l,ha='right',va='center',fontsize=6)
a.text(-.4,-.25,'F = intentional oddity, C = convention',ha='right',va='top',fontsize=5.6,color='0.25')
a.set_xlim(-.1,47.1);a.set_ylim(-1,4.9);a.axis('off')
fig.savefig('fig_grid.pdf',bbox_inches='tight',pad_inches=.03);fig.savefig('fig_grid.png',dpi=160,bbox_inches='tight')
# Fig 3: taxonomy
res=json.load(open(os.path.join(DATA,'rq1_guards','labels.json')))['res']
names={'A1':'Acts on version control or release','A2':'Scope creep','A3':'Adds a dependency','A4':'Edits a protected file','A5':'Destructive operation','B1':'Wrong tool or command','B2':'Breaks an architecture boundary','B3':'Ignores a code convention','B4':'Undoes something intentional','B5':'Falls into a local trap','C1':'Guesses or fabricates','C2':'Claims done without evidence','C3':'Hides a failure','D1':'Over-engineers','D2':'Noisy prose or comments','D3':'Bad tests','D4':'Lets docs drift','E1':'Security or privacy lapse','F1':'Wasteful run','F2':'Stops short','G1':'Product-persona conduct','G2':'Other'}
tcol={'A':OR,'B':BL,'C':GR,'D':YE,'E':PK,'F':DG,'G':'0.6'};thatch={'A':'////','B':'','C':'....','D':'\\\\\\\\','E':'xxxx','F':'++','G':''}
tname={'A':'Oversteps its mandate','B':'Applies defaults instead of local knowledge','C':'Unreliable about what is true','D':'Low-quality output habits','E':'Exposure','F':'Process','G':'Other'}
ks=sorted(res,key=lambda k:(k[0],-res[k]['pct']))
fig,ax=plt.subplots(1,2,figsize=(7.16,2.2),gridspec_kw={'width_ratios':[1.5,1]})
a=ax[0];y=np.arange(len(ks))[::-1]
a.barh(y,[res[k]['pct'] for k in ks],color=[tcol[k[0]] for k in ks],hatch=None,edgecolor='white',linewidth=.3,height=.74)
for yi,k in zip(y,ks):
    a.plot([res[k]['lo'],res[k]['hi']],[yi,yi],color='0.15',lw=.6);a.text(res[k]['hi']+.3,yi,'%.1f%%'%res[k]['pct'],va='center',fontsize=5.6)
a.set_yticks(y);a.set_yticklabels([names[k] for k in ks],fontsize=5.3);a.set_xlabel('% of guards (n = 1,341), with 95% interval');a.set_xlim(0,16.5);a.set_ylim(-.7,len(ks)-.3);a.set_title('(a) Agent behaviour that a rule guards against',loc='left',fontsize=7)
a=ax[1];ths=['B','A','D','C','E','F','G'];tot={t:sum(res[k]['n'] for k in res if k[0]==t) for t in ths};N=sum(tot.values())
proj={t:sum(res[k]['n']*res[k]['project']/100 for k in res if k[0]==t) for t in ths};y=np.arange(len(ths))[::-1]
a.barh(y,[100*proj[t]/N for t in ths],color=[tcol[t] for t in ths],edgecolor='white',linewidth=.3,height=.7,label='project-specific')
a.barh(y,[100*(tot[t]-proj[t])/N for t in ths],left=[100*proj[t]/N for t in ths],color=[tcol[t] for t in ths],alpha=.35,edgecolor='white',linewidth=.3,height=.7,hatch='////',label='generic')
for yi,t in zip(y,ths): a.text(100*tot[t]/N+.6,yi,'%.0f%%'%(100*tot[t]/N),va='center',fontsize=5.8)
a.set_yticks(y);a.set_yticklabels([tname[t].replace(' instead of ',' instead\nof ').replace(' about ',' about\n') for t in ths],fontsize=6);a.set_xlim(0,52);a.set_xlabel('% of guards');a.set_title('(b) Themes (solid: project-specific; hatched: generic)',loc='left',fontsize=7)
fig.tight_layout(w_pad=1.0);fig.savefig('fig_tax.pdf',bbox_inches='tight',pad_inches=.03);fig.savefig('fig_tax.png',dpi=160,bbox_inches='tight')
print({t:(tot[t],round(100*tot[t]/N,1),round(100*proj[t]/tot[t])) for t in ths})
