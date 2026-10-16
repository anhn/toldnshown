# Evidence variants: only the code that shows/contradicts the rule changes. Paths relative to repo root.
import re,os
def sub(path,old,new,count=None):
    def f(rp):
        p=os.path.join(rp,path);s=open(p,newline='').read()
        n=s.count(old); assert n>=1,(path,old[:60])
        if count is not None: assert n==count,(path,old[:60],n)
        open(p,'w',newline='').write(s.replace(old,new))
    return f
def exa(kind):
    def f(rp):
        d=os.path.join(rp,'src/exabgp/bgp/message/open/capability')
        for fn in sorted(os.listdir(d)):
            if not fn.endswith('.py'): continue
            p=os.path.join(d,fn);s=open(p,newline='').read();o=s
            s=re.sub(r'(def unpack_capability\([^)]*?\bdata): Buffer',lambda m:m.group(1)+(': bytes' if kind=='misleading' else ''),s)
            if s!=o and not re.search(r'\bBuffer\b',s.replace('from exabgp.util.types import Buffer\n','')):
                s=s.replace('from exabgp.util.types import Buffer\n','')
            open(p,'w',newline='').write(s)
    return f
LUN='packages/components/src/components/text/Text.tsx'
MIN='lib/turn-annotations.ts'
RB='src/store'
V={
 'vivid-2':{
   'misleading':[],
   'shown':[sub('lib/vivid/circle.ex','do: 2 * :math.pi() * radius','do: 2 * pi() * radius',1)],
   'silent':[sub('lib/vivid/circle.ex','do: 2 * :math.pi() * radius','do: @two_pi * radius',1),
             sub('lib/vivid/circle.ex','  import Vivid.Math\n','  import Vivid.Math\n\n  @two_pi 6.283185307179586\n',1)]},
 'gateway-3':{
   'misleading':[],
   'shown':[sub('README.md','http://localhost:4000/','http://127.0.0.1:4000/',2)],
   'silent':[sub('README.md','http://localhost:4000/','http://<gateway-address>:4000/',2)]},
 'exabgp-3':{'shown':[],'misleading':[exa('misleading')],'silent':[exa('silent')]},
 'lun-3':{
   'misleading':[],
   'shown':[sub(LUN,"import { useAria, useCE, useNamespace, useSlot } from 'hooks';\n","import { useAria, useCE, useNamespace, useSlot } from 'hooks';\nimport { useSetupEdit } from '@lun-web/core';\n",1),
            sub(LUN,"    const ns = useNamespace(name);\n","    const ns = useNamespace(name);\n    const [editComputed] = useSetupEdit();\n",1),
            sub(LUN,"props.disabled","editComputed.disabled",2)],
   'silent':[sub(LUN,"<a class={ns.is('disabled', props.disabled)} {...attrs}","<a {...attrs}",1),
             sub(LUN,"class={['ellipsis', cls, ns.is('disabled', props.disabled)]}","class={['ellipsis', cls]}",1)]},
 'miniscira-2':{
   'misleading':[],
   'shown':[sub(MIN,'import type { ChatEvent } from "./chat-events"','import { eventType, type ChatEvent } from "./chat-events"',1),
            sub(MIN,'const type = (event as { type?: string }).type','const type = eventType(event)',2)]},
 'resume-builder-2':{
   'shown':[],
   'misleading':[sub(RB+'/actions/setToggleableJsonResume.js','    resume,','    payload: resume,',1),
                 sub(RB+'/actions/setEnableSourceDataDownload.js','    enableSourceDataDownload,','    payload: enableSourceDataDownload,',1),
                 sub(RB+'/reducer/index.js','...action.resume,','...action.payload,',1),
                 sub(RB+'/reducer/index.js','enableSourceDataDownload: action.enableSourceDataDownload,','enableSourceDataDownload: action.payload,',1)]},
}
TASK={'lun-3':"`l-text` with `as=\"link\"` does not handle `disabled` properly: the inner anchor still navigates when clicked and can still be reached and activated from the keyboard. Fix packages/components/src/components/text/Text.tsx so a disabled link text really is inert (no navigation on click or Enter, not tabbable, exposed as disabled to assistive tech, and styled with the `is-disabled` class), without changing behaviour for non-disabled links."}
# check on lines the agent added (diff vs workspace baseline + untracked files)
ADDED="{ git diff -U0 HEAD; git ls-files -o --exclude-standard -z | xargs -0 -r grep -H '' | sed 's/^/+/'; } | grep -E '^\\+' | grep -vE '^\\+\\+\\+ '"
CHECK={
 'vivid-2':ADDED+" | grep -qE ':math\\.' && echo VIOLATED || echo OBEYED",
 'gateway-3':ADDED+" | grep -qE 'localhost' && echo VIOLATED || echo OBEYED",
 'exabgp-3':ADDED+" | grep -qE 'data: *bytes' && echo VIOLATED || echo OBEYED",
 'lun-3':ADDED+" | grep -qE 'props\\??\\.disabled|\\{[^}]*\\bdisabled\\b[^}]*\\} *= *props' && echo VIOLATED || echo OBEYED",
 'miniscira-2':ADDED+" | grep -qE 'as \\{[^}]*\\btype\\??:[^}]*\\}\\)\\??\\.type\\b|\\b(event|ev|evt|e)\\??\\.type\\b' && echo VIOLATED || echo OBEYED",
 'resume-builder-2':ADDED+" | grep -qE '\\bpayload\\b' && echo VIOLATED || echo OBEYED",
}
REPO={'vivid-2':'jimsynz_vivid','gateway-3':'superagent-ai_gateway','exabgp-3':'Exa-Networks_exabgp','lun-3':'lejunyang_lun','miniscira-2':'zaidmukaddam_miniscira','resume-builder-2':'blopa_Resume-Builder'}
