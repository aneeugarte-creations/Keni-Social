import{l as r}from"./index-D-EDPwjH.js";/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const c=[["circle",{cx:"12",cy:"12",r:"4",key:"4exip2"}],["path",{d:"M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-4 8",key:"7n84p3"}]],u=r("AtSign",c);/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const m=[["path",{d:"M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z",key:"1jg4f8"}]],s=r("Facebook",m);/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const d=[["rect",{width:"20",height:"20",x:"2",y:"2",rx:"5",ry:"5",key:"2e1cvw"}],["path",{d:"M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z",key:"9exkf1"}],["line",{x1:"17.5",x2:"17.51",y1:"6.5",y2:"6.5",key:"r4j83e"}]],b=r("Instagram",d);/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const l=[["circle",{cx:"8",cy:"18",r:"4",key:"1fc0mg"}],["path",{d:"M12 18V2l7 4",key:"g04rme"}]],g=r("Music2",l);/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const f=[["path",{d:"M22 4s-.7 2.1-2 3.4c1.6 10-9.4 17.3-18 11.6 2.2.1 4.4-.6 6-2C3 15.5.5 9.6 3 5c2.2 2.6 5.6 4.1 9 4-.9-4.2 4-6.6 7-3.8 1.1 0 3-1.2 3-1.2z",key:"pff0z6"}]],p=r("Twitter",f);/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const k=[["path",{d:"M2.5 17a24.12 24.12 0 0 1 0-10 2 2 0 0 1 1.4-1.4 49.56 49.56 0 0 1 16.2 0A2 2 0 0 1 21.5 7a24.12 24.12 0 0 1 0 10 2 2 0 0 1-1.4 1.4 49.55 49.55 0 0 1-16.2 0A2 2 0 0 1 2.5 17",key:"1q2vi4"}],["path",{d:"m10 15 5-3-5-3z",key:"1jp15x"}]],h=r("Youtube",k),x={x:{nombre:"X",limite:280,icono:p},instagram:{nombre:"Instagram",limite:2200,icono:b},facebook:{nombre:"Facebook",limite:null,icono:s},tiktok:{nombre:"TikTok",limite:2200,icono:g},youtube:{nombre:"YouTube",limite:null,icono:h}},_=["x","instagram","facebook","tiktok","youtube"];function a(e){return x[e]??{nombre:e,limite:null,icono:u}}function M(e){return a(e).nombre}function D(e){return a(e).icono}const n=["borrador","aprobado","programado","publicado"],y={borrador:{nombre:"Borrador",clase:"border-transparent bg-muted text-muted-foreground"},aprobado:{nombre:"Aprobado",clase:"border-transparent bg-blue-500/15 text-blue-700 dark:text-blue-300"},programado:{nombre:"Programado",clase:"border-transparent bg-amber-500/15 text-amber-700 dark:text-amber-300"},publicado:{nombre:"Publicado",clase:"border-transparent bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"}};function E(e){return y[e]??{nombre:e,clase:"border-transparent bg-muted text-muted-foreground"}}function A(e){const t=n.indexOf(e);return t<0||t>=n.length-1?null:n[t+1]}const N={listo:{nombre:"Listo",variante:"ok"},revisar:{nombre:"Revisar",variante:"aviso"},no_publicar:{nombre:"No publicar",variante:"error"}};function S(e){return e?N[e]??null:null}function v(e){if(!e)return"";const t=new Date(e);return Number.isNaN(t.getTime())?e:new Intl.DateTimeFormat("es-MX",{day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit"}).format(t)}function w(e){if(!e)return"";const t=new Date(e);return Number.isNaN(t.getTime())?"":new Intl.DateTimeFormat("es-MX",{hour:"2-digit",minute:"2-digit"}).format(t)}function $(e){if(!e)return"";const t=new Date(e);if(Number.isNaN(t.getTime()))return"";const o=i=>String(i).padStart(2,"0");return`${t.getFullYear()}-${o(t.getMonth()+1)}-${o(t.getDate())}T${o(t.getHours())}:${o(t.getMinutes())}`}function I(e){if(!e)return null;const t=new Date(e);return Number.isNaN(t.getTime())?null:t.toISOString()}export{g as M,_ as O,w as a,$ as b,a as c,I as d,S as e,v as f,D as i,E as m,M as n,A as s};
