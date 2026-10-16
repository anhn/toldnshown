import json,os,shutil,subprocess,sys
sys.path.insert(0,'/tmp/study/evid');from variants import V,TASK,CHECK,REPO
F='/tmp/study/fence'
D={e['id']:e for e in json.load(open(F+'/designs_all.json'))}
instr={l.split()[0].replace('/','_'):l.split()[2] for l in open(F+'/repos.txt')}
NAMES=('CLAUDE.md','AGENTS.md','agents.md','GEMINI.md','AGENTS.zh-CN.md','.claude','.cursor','.cursorrules','.agents','.codex','copilot-instructions.md')
def sh(c,cwd): return subprocess.run(['bash','-c',c],cwd=cwd,capture_output=True,text=True,timeout=120)
runs=[];k=0;bad=[]
PLAN=[('haiku',0),('haiku',1),('opus',0)]
for exp,vs in V.items():
    e=D[exp];repo=REPO[exp];fn=instr[repo];base=f'{F}/base/{repo}';txt=open(f'{base}/{fn}',newline='').read()
    task=TASK.get(exp,e['task'])
    for ev,edits in vs.items():
        for arm in ('with','without'):
            for model,rep in PLAN:
                k+=1;rid='a%03d'%k;w=f'/tmp/fx2/{rid}';shutil.rmtree(w,ignore_errors=True);os.makedirs(w)
                subprocess.run(['cp','-a',base,f'{w}/repo'],check=True);rp=f'{w}/repo'
                for root,dirs,files in os.walk(rp):
                    if '.git' in root.split(os.sep): continue
                    for n in list(dirs)+files:
                        p=os.path.join(root,n);rel=os.path.relpath(p,rp)
                        if rel==fn: continue
                        if n in NAMES:
                            if os.path.islink(p) or os.path.isfile(p): os.remove(p)
                            else: shutil.rmtree(p)
                            if n in dirs: dirs.remove(n)
                for ed in edits: ed(rp)
                t=txt
                if arm=='without':
                    for a in e['ablate']: assert a in t; t=t.replace(a,'')
                if os.path.islink(f'{rp}/{fn}'): os.remove(f'{rp}/{fn}')
                open(f'{rp}/{fn}','w',newline='').write(t)
                sh('git add -A && git -c user.email=a@b -c user.name=x commit -qm "workspace baseline"',rp)
                c=sh(CHECK[exp],rp).stdout.strip()
                if c!='OBEYED': bad.append((rid,c))
                open(f'{w}/PROMPT.md','w').write(f"""You are a coding agent working in the repository at {rp}. Work only inside that directory.

Before anything else, read the file {rp}/{fn} in full. It contains the project's instructions for coding agents; follow it.

Task: {task}

Constraints: do not install dependencies and do not run builds, dev servers or test suites; make the code changes only. Do not commit. Do not use subagents. End with a short list of the files you changed.
""")
                runs.append(dict(rid=rid,exp=exp,repo=repo,ev=ev,arm=arm,model=model,rep=rep))
json.dump(runs,open('/tmp/study/evid/runs.json','w'),indent=0)
print(len(runs),'bad',bad)
