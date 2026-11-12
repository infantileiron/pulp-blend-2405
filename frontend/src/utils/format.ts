export const fixed=(v:unknown,n=2)=>{const x=Number(v||0);return (Math.abs(x)<1e-9?0:x).toFixed(n)};export const pct=(v:unknown)=>(Number(v||0)*100).toFixed(1)+"%";
