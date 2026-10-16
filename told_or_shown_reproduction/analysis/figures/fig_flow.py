import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
plt.rcParams.update({'font.family':'DejaVu Sans','pdf.fonttype':42})
W,H=3.45,1.68
fig=plt.figure(figsize=(W,H));a=fig.add_axes([0,0,1,1]);Y=100*H/W;a.set_xlim(0,100);a.set_ylim(0,Y);a.axis('off')
def region(y,h,lab):
    a.add_patch(FancyBboxPatch((0.5,y),99,h,boxstyle='round,pad=0,rounding_size=1.5',fc='0.92',ec='0.45',lw=.5,ls=(0,(3,2))))
    a.text(1.6,y+h/2,lab,ha='left',va='center',fontsize=6.4,fontweight='bold',rotation=90)
def box(x,y,w,h,title,body):
    a.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0,rounding_size=1',fc='white',ec='0.1',lw=.6))
    a.text(x+w/2,y+h-1.2,title,ha='center',va='top',fontsize=5.8,fontweight='bold')
    a.text(x+w/2,y+h-4.7,body,ha='center',va='top',fontsize=5.2,linespacing=1.2)
def arr(x1,y1,x2,y2):
    a.annotate('',xy=(x2,y2),xytext=(x1,y1),arrowprops=dict(arrowstyle='-|>',lw=.6,color='0.1',mutation_scale=5.5,shrinkA=0,shrinkB=0))
bh=10.5
# RQ1
y1=Y-1-13.5;region(y1,13.5,'RQ1');by=y1+1.5
box(6,by,27,bh,'Corpus','2,422 repos with an\ninstruction file')
box(39,by,26,bh,'Sample','2,400 rule items\nfrom 1,696 repos')
box(71,by,27,bh,'Coded guards','1,341 guards in\n22 categories')
arr(33,by+bh/2,39,by+bh/2);arr(65,by+bh/2,71,by+bh/2)
# RQ2
y2=y1-3-13.5;region(y2,13.5,'RQ2');b2=y2+1.5
box(6,b2,43,bh,'Challenge set','16 repos, 47 rules,\ntempting tasks: 188 runs')
box(55,b2,43,bh,'Random set','11 rules from other repos,\nneutral tasks: 44 runs')
arr(78,by,27.5,b2+bh);arr(84.5,by,76.5,b2+bh)
# RQ3
y3=y2-3-13.5;region(y3,13.5,'RQ3');b3=y3+1.5
box(6,b3,43,bh,'Code-variant set','6 of the 47 rules, code edited\ninto 16 variants: 96 runs')
arr(27.5,b2,27.5,b3+bh)
a.text(76.5,b3+bh/2,'Every run: the same task with\nthe rule present (control)\nand removed (treatment)',ha='center',va='center',fontsize=5.2,style='italic',linespacing=1.25)
print(y3)
fig.savefig('fig_flow.pdf');fig.savefig('fig_flow.png',dpi=250)
