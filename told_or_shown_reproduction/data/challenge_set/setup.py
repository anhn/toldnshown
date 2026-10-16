import json,glob,os,subprocess,shutil,random,sys
D=[];instr={}
for l in open('repos.txt'):
    r,sha,fn=l.split();instr[r.replace('/','_')]=fn
for f in sorted(glob.glob('design/*.json')):
    repo=os.path.basename(f)[:-5]
    for e in json.load(open(f)):
        if 'task' not in e: continue
        e['repo']=repo;D.append(e)
print('experiments',len(D))
OTHER=['CLAUDE.md','AGENTS.md','agents.md','GEMINI.md','AGENTS.zh-CN.md','.claude','.cursor','.cursorrules','.github/copilot-instructions.md','.agents','.codex']
def sh(cmd,cwd): return subprocess.run(['bash','-c',cmd],cwd=cwd,capture_output=True,text=True,timeout=120)
runs=[];bad=[];k=0
rng=random.Random(11)
for e in D:
    base=f'base/{e["repo"]}';fn=instr[e['repo']];txt=open(f'{base}/{fn}').read()
    miss=[a for a in e['ablate'] if a not in txt]
    if miss: bad.append((e['id'],'ablate missing',miss[0][:60]));continue
    ok=True;made=[]
    for arm in ('with','without'):
        for model in ('opus','haiku'):
            k+=1;rid='r%03d'%k;w=f'/tmp/fx/{rid}';shutil.rmtree(w,ignore_errors=True);os.makedirs(w)
            subprocess.run(['cp','-a',base,f'{w}/repo'],check=True);rp=f'{w}/repo'
            # remove other agent-instruction files (both arms), incl. nested ones
            for root,dirs,files in os.walk(rp):
                if '.git' in root.split(os.sep): continue
                for n in list(dirs)+files:
                    p=os.path.join(root,n);rel=os.path.relpath(p,rp)
                    if rel==fn: continue
                    if n in ('CLAUDE.md','AGENTS.md','agents.md','GEMINI.md','AGENTS.zh-CN.md','.claude','.cursor','.cursorrules','.agents','.codex','copilot-instructions.md'):
                        if os.path.islink(p) or os.path.isfile(p): os.remove(p)
                        else: shutil.rmtree(p)
                        if n in dirs: dirs.remove(n)
            t=txt
            if arm=='without':
                for a in e['ablate']: t=t.replace(a,'')
            if os.path.islink(f'{rp}/{fn}'): os.remove(f'{rp}/{fn}')
            open(f'{rp}/{fn}','w').write(t)
            sh('git add -A && git -c user.email=a@b -c user.name=x commit -qm "workspace baseline"',rp)
            c=sh(e['check_cmd'],rp).stdout.strip().split('\n')[-1] if True else ''
            if c!='OBEYED': ok=False;bad.append((e['id'],arm,'precheck '+c[:40]))
            sh('git reset -q && git status --short | head -1',rp)
            open(f'{w}/PROMPT.md','w').write(f"""You are a coding agent working in the repository at {rp}. Work only inside that directory.

Before anything else, read the file {rp}/{fn} in full. It contains the project's instructions for coding agents; follow it.

Task: {e['task']}

Constraints: do not install dependencies and do not run builds, dev servers or test suites; make the code changes only. Do not commit. Do not use subagents. End with a short list of the files you changed.
""")
            made.append(dict(rid=rid,exp=e['id'],repo=e['repo'],arm=arm,model=model,kind=e['kind'],cell=e['cell']))
    if ok: runs+=made
    else:
        for m in made: shutil.rmtree('/tmp/fx/'+m['rid'],ignore_errors=True)
json.dump(runs,open('runs.json','w'),indent=0);json.dump(D,open('designs_all.json','w'),indent=0)
print('runs',len(runs),'experiments ok',len(runs)//4);print('bad',bad)
import collections as C;print(C.Counter((r['kind'],r['cell']) for r in runs if r['arm']=='with' and r['model']=='opus'))
