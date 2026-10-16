import json,os,shutil,subprocess,glob
B='/tmp/study/extB'
NAMES=('CLAUDE.md','AGENTS.md','agents.md','GEMINI.md','AGENTS.zh-CN.md','.claude','.cursor','.cursorrules','.agents','.codex','copilot-instructions.md','.windsurfrules','.clinerules')
def sh(c,cwd): return subprocess.run(['bash','-c',c],cwd=cwd,capture_output=True,text=True,timeout=300)
runs=[];k=0;bad=[];D=[]
for f in sorted(glob.glob(B+'/design/[A-E][0-9].json')):
    e=json.load(open(f))
    if not e.get('id'): continue
    D.append(e);repo=e['repo'].replace('/','_');base=f'{B}/base/{repo}';fn=e['instruction_file']
    txt=open(f'{base}/{fn}',newline='').read()
    for a in e['ablate']:
        if a not in txt: bad.append((e['id'],'ablate missing',a[:60]))
    for arm in ('with','without'):
        for model in ('haiku','opus'):
            k+=1;rid='b%03d'%k;w=f'/tmp/fx3/{rid}';shutil.rmtree(w,ignore_errors=True);os.makedirs(w)
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
            t=txt
            if arm=='without':
                for a in e['ablate']: t=t.replace(a,'')
            if os.path.islink(f'{rp}/{fn}'): os.remove(f'{rp}/{fn}')
            open(f'{rp}/{fn}','w',newline='').write(t)
            sh('git add -A && git -c user.email=a@b -c user.name=x commit -qm "workspace baseline"',rp)
            c=sh(e['check_cmd'],rp).stdout.strip().split('\n')[-1]
            if c!='OBEYED': bad.append((rid,e['id'],'precheck',c[:50]))
            open(f'{w}/PROMPT.md','w').write(f"""You are a coding agent working in the repository at {rp}. Work only inside that directory.

Before anything else, read the file {rp}/{fn} in full. It contains the project's instructions for coding agents; follow it.

Task: {e['task']}

Constraints: do not install dependencies and do not run builds, dev servers or test suites; make the code changes only. Do not commit. Do not use subagents. End with a short list of the files you changed.
""")
            runs.append(dict(rid=rid,exp=e['id'],arm=arm,model=model,cell=e['cell']))
json.dump(runs,open(B+'/runs.json','w'),indent=0);json.dump(D,open(B+'/designs.json','w'),indent=1)
print(len(runs),'bad',bad)
