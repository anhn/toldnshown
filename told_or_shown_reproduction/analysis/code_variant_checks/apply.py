# Usage: run from a directory containing base/<owner_repo> (repositories at the pinned commits,
# e.g. from code/: python -m rab setup, then link repos/ as base/). Writes var/<rule>/<state>/.
import sys,shutil,subprocess,os
sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),'../../data/code_variant_set')); import variants as v
out={}
for exp,states in v.V.items():
    repo=v.REPO[exp]
    for st,fs in states.items():
        d=f'{os.getcwd()}/var/{exp}/{st}'
        if os.path.exists(d): shutil.rmtree(d)
        shutil.copytree(f'base/{repo}',d,symlinks=True)
        for f in fs: f(d)
        df=subprocess.run(['git','diff','--stat'],cwd=d,capture_output=True,text=True).stdout.strip().splitlines()
        print(exp,st,df[-1] if df else 'no change (original code)')
