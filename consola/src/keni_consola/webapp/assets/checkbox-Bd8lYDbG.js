import{l as o,D as l,w as m,i as f}from"./index-BPsW_OCZ.js";import{C as g}from"./check-eqAiafhd.js";/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const p=[["circle",{cx:"12",cy:"12",r:"4",key:"4exip2"}],["path",{d:"M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-4 8",key:"7n84p3"}]],h=o("AtSign",p);/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const k=[["path",{d:"M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z",key:"1jg4f8"}]],y=o("Facebook",k);/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const x=[["rect",{width:"20",height:"20",x:"2",y:"2",rx:"5",ry:"5",key:"2e1cvw"}],["path",{d:"M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z",key:"9exkf1"}],["line",{x1:"17.5",x2:"17.51",y1:"6.5",y2:"6.5",key:"r4j83e"}]],N=o("Instagram",x);/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const M=[["circle",{cx:"8",cy:"18",r:"4",key:"1fc0mg"}],["path",{d:"M12 18V2l7 4",key:"g04rme"}]],v=o("Music2",M);/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const T=[["path",{d:"M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z",key:"1a8usu"}],["path",{d:"m15 5 4 4",key:"1mk7zo"}]],F=o("Pencil",T);/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const w=[["path",{d:"M22 4s-.7 2.1-2 3.4c1.6 10-9.4 17.3-18 11.6 2.2.1 4.4-.6 6-2C3 15.5.5 9.6 3 5c2.2 2.6 5.6 4.1 9 4-.9-4.2 4-6.6 7-3.8 1.1 0 3-1.2 3-1.2z",key:"pff0z6"}]],_=o("Twitter",w);/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const D=[["path",{d:"M2.5 17a24.12 24.12 0 0 1 0-10 2 2 0 0 1 1.4-1.4 49.56 49.56 0 0 1 16.2 0A2 2 0 0 1 21.5 7a24.12 24.12 0 0 1 0 10 2 2 0 0 1-1.4 1.4 49.55 49.55 0 0 1-16.2 0A2 2 0 0 1 2.5 17",key:"1q2vi4"}],["path",{d:"m10 15 5-3-5-3z",key:"1jp15x"}]],E=o("Youtube",D),A={x:{nombre:"X",limite:280,icono:_},instagram:{nombre:"Instagram",limite:2200,icono:N},facebook:{nombre:"Facebook",limite:null,icono:y},tiktok:{nombre:"TikTok",limite:2200,icono:v},youtube:{nombre:"YouTube",limite:null,icono:E}},O=["x","instagram","facebook","tiktok","youtube"];function d(e){return A[e]??{nombre:e,limite:null,icono:h}}function j(e){return d(e).nombre}function z(e){return d(e).icono}const c=["borrador","aprobado","programado","publicado"],R={borrador:{nombre:"Borrador",clase:"border-transparent bg-muted text-muted-foreground"},aprobado:{nombre:"Aprobado",clase:"border-transparent bg-blue-500/15 text-blue-700 dark:text-blue-300"},programado:{nombre:"Programado",clase:"border-transparent bg-amber-500/15 text-amber-700 dark:text-amber-300"},publicado:{nombre:"Publicado",clase:"border-transparent bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"}};function L(e){return R[e]??{nombre:e,clase:"border-transparent bg-muted text-muted-foreground"}}function P(e){const t=c.indexOf(e);return t<0||t>=c.length-1?null:c[t+1]}const S={listo:{nombre:"Listo",variante:"ok"},revisar:{nombre:"Revisar",variante:"aviso"},no_publicar:{nombre:"No publicar",variante:"error"}};function H(e){return e?S[e]??null:null}function V(e){if(!e)return"";const t=new Date(e);return Number.isNaN(t.getTime())?e:new Intl.DateTimeFormat("es-MX",{day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit"}).format(t)}function X(e){if(!e)return"";const t=new Date(e);return Number.isNaN(t.getTime())?"":new Intl.DateTimeFormat("es-MX",{hour:"2-digit",minute:"2-digit"}).format(t)}function Y(e){if(!e)return"";const t=new Date(e);if(Number.isNaN(t.getTime()))return"";const r=Math.round((t.getTime()-Date.now())/1e3),n=Math.abs(r),a=new Intl.RelativeTimeFormat("es-MX",{numeric:"auto"}),s=[[60,"second"],[3600,"minute"],[86400,"hour"],[604800,"day"],[2629800,"week"],[31557600,"month"],[1/0,"year"]],i={second:1,minute:60,hour:3600,day:86400,week:604800,month:2629800,year:31557600};for(const[b,u]of s)if(n<b)return a.format(Math.round(r/i[u]),u);return a.format(Math.round(r/i.year),"year")}function q(e){if(!e)return"";const t=new Date(e);if(Number.isNaN(t.getTime()))return"";const r=n=>String(n).padStart(2,"0");return`${t.getFullYear()}-${r(t.getMonth()+1)}-${r(t.getDate())}T${r(t.getHours())}:${r(t.getMinutes())}`}function B(e){if(!e)return null;const t=new Date(e);return Number.isNaN(t.getTime())?null:t.toISOString()}const I=l.forwardRef(({checked:e,onCheckedChange:t,id:r,disabled:n,className:a,...s},i)=>m.jsx("button",{ref:i,type:"button",role:"checkbox",id:r,"aria-checked":e,disabled:n,onClick:()=>t(!e),className:f("flex h-5 w-5 shrink-0 items-center justify-center rounded border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50",e?"border-primary bg-primary text-primary-foreground":"border-input hover:bg-accent",a),...s,children:e&&m.jsx(g,{className:"h-3.5 w-3.5"})}));I.displayName="Checkbox";export{I as C,v as M,O,F as P,X as a,q as b,d as c,B as d,H as e,V as f,z as i,L as m,j as n,P as s,Y as t};
