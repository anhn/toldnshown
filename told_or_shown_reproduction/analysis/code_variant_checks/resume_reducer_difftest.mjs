import fs from 'fs';
const res={};
for (const v of ['orig','var']){
  const red=(await import(`./${v}/store/reducer/index.js`)).default;
  const acts=fs.readdirSync(`./${v}/store/actions`).filter(f=>f.endsWith('.js'));
  for(const a of acts){
    const cr=(await import(`./${v}/store/actions/${a}`)).default;
    const s0={toggleableJsonResume:{basics:{name:'x'},enableSourceDataDownload:false},other:1};
    const args=[{basics:{name:'y'},work:[1]},true,'z'];
    const s1=red(s0,cr(...args));
    (res[a]??={})[v]=JSON.stringify(s1);
  }
}
let same=0,diff=0;for(const[a,r] of Object.entries(res)){ if(r.orig===r.var) same++; else {diff++;console.log('DIFF',a)} }
console.log(`actions: ${same} identical reducer results, ${diff} different`);
