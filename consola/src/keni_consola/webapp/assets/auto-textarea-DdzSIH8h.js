import{ab as p,an as i,_ as b,b as f,av as h,a6 as k}from"./index-BMb7F9Ug.js";/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const j=[["path",{d:"M6 12h9a4 4 0 0 1 0 8H7a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h7a4 4 0 0 1 0 8",key:"mg9rjx"}]],m=p("Bold",j);/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const g=[["line",{x1:"19",x2:"10",y1:"4",y2:"4",key:"15jd3p"}],["line",{x1:"14",x2:"5",y1:"20",y2:"20",key:"bu0au3"}],["line",{x1:"15",x2:"9",y1:"4",y2:"20",key:"uljnxc"}]],v=p("Italic",g);/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const $=[["path",{d:"M9 17H7A5 5 0 0 1 7 7h2",key:"8i5ue5"}],["path",{d:"M15 7h2a5 5 0 1 1 0 10h-2",key:"1b9ql8"}],["line",{x1:"8",x2:"16",y1:"12",y2:"12",key:"1jonct"}]],w=p("Link2",$);/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const N=[["path",{d:"M3 12h.01",key:"nlz23k"}],["path",{d:"M3 18h.01",key:"1tta3j"}],["path",{d:"M3 6h.01",key:"1rqtza"}],["path",{d:"M8 12h13",key:"1za7za"}],["path",{d:"M8 18h13",key:"1lx6n3"}],["path",{d:"M8 6h13",key:"ik3vkj"}]],M=p("List",N);/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const _=[["path",{d:"M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8",key:"1357e3"}],["path",{d:"M3 3v5h5",key:"1xhq8a"}]],F=p("RotateCcw",_);function I(d,o,n,r){const u=o.slice(n,r),c=o.slice(0,n),s=o.slice(r);switch(d){case"negrita":{const t=u||"texto en negrita";return{texto:`${c}**${t}**${s}`,selInicio:n+2,selFin:n+2+t.length}}case"cursiva":{const t=u||"texto en cursiva";return{texto:`${c}*${t}*${s}`,selInicio:n+1,selFin:n+1+t.length}}case"lista":{const a=(u||"Elemento").split(`
`).map(y=>`- ${y}`),l=(n>0&&!c.endsWith(`
`)?`
`:"")+a.join(`
`);return{texto:`${c}${l}${s}`,selInicio:n+l.length,selFin:n+l.length}}case"enlace":{const t=u||"texto del enlace",a=`${c}[${t}](https://)${s}`,e=n+1+t.length+2;return{texto:a,selInicio:e,selFin:e+8}}}}function z({refArea:d,valor:o,onContenido:n,className:r}){function u(s){const t=d.current,a=(t==null?void 0:t.selectionStart)??o.length,e=(t==null?void 0:t.selectionEnd)??o.length,l=I(s,o,a,e);n(l.texto),window.requestAnimationFrame(()=>{const x=d.current;x&&(x.focus(),x.setSelectionRange(l.selInicio,l.selFin))})}const c=[{accion:"negrita",label:"Negrita",icono:i.jsx(m,{className:"h-3.5 w-3.5"})},{accion:"cursiva",label:"Cursiva",icono:i.jsx(v,{className:"h-3.5 w-3.5"})},{accion:"lista",label:"Lista",icono:i.jsx(M,{className:"h-3.5 w-3.5"})},{accion:"enlace",label:"Enlace",icono:i.jsx(w,{className:"h-3.5 w-3.5"})}];return i.jsx("div",{className:r,children:i.jsx("div",{className:"inline-flex items-center gap-0.5 rounded-md border border-border p-0.5",children:c.map(s=>i.jsx(b,{label:s.label,children:i.jsx(f,{type:"button",variant:"ghost",size:"icon",className:"h-7 w-7",onClick:()=>u(s.accion),"aria-label":s.label,children:s.icono})},s.accion))})})}const L=h.forwardRef(({className:d,maxHeight:o,value:n,onChange:r,...u},c)=>{const s=h.useRef(null),t=h.useCallback(e=>{s.current=e,typeof c=="function"?c(e):c&&(c.current=e)},[c]),a=h.useCallback(()=>{const e=s.current;if(!e)return;e.style.height="auto";const l=o?Math.min(e.scrollHeight,o):e.scrollHeight;e.style.height=`${l}px`,e.style.overflowY=o&&e.scrollHeight>o?"auto":"hidden"},[o]);return h.useLayoutEffect(()=>{a()},[a,n]),i.jsx("textarea",{ref:t,value:n,onChange:e=>{r==null||r(e),a()},rows:1,className:k("flex min-h-[80px] w-full resize-none rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",d),...u})});L.displayName="AutoTextarea";export{L as A,z as B,w as L,F as R};
