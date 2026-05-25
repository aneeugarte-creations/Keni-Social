import{o as n,z as s}from"./index-BQW9uDvJ.js";/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const b=[["circle",{cx:"12",cy:"12",r:"4",key:"4exip2"}],["path",{d:"M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-4 8",key:"7n84p3"}]],f=n("AtSign",b);/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const g=[["path",{d:"M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z",key:"1jg4f8"}]],h=n("Facebook",g);/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const p=[["rect",{width:"20",height:"20",x:"2",y:"2",rx:"5",ry:"5",key:"2e1cvw"}],["path",{d:"M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z",key:"9exkf1"}],["line",{x1:"17.5",x2:"17.51",y1:"6.5",y2:"6.5",key:"r4j83e"}]],k=n("Instagram",p);/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const y=[["circle",{cx:"8",cy:"18",r:"4",key:"1fc0mg"}],["path",{d:"M12 18V2l7 4",key:"g04rme"}]],x=n("Music2",y);/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const N=[["path",{d:"M2.5 17a24.12 24.12 0 0 1 0-10 2 2 0 0 1 1.4-1.4 49.56 49.56 0 0 1 16.2 0A2 2 0 0 1 21.5 7a24.12 24.12 0 0 1 0 10 2 2 0 0 1-1.4 1.4 49.55 49.55 0 0 1-16.2 0A2 2 0 0 1 2.5 17",key:"1q2vi4"}],["path",{d:"m10 15 5-3-5-3z",key:"1jp15x"}]],M=n("Youtube",N);function T({className:e,...t}){return s.jsx("svg",{viewBox:"0 0 24 24",fill:"currentColor",className:e,"aria-hidden":"true",...t,children:s.jsx("path",{d:"M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"})})}const v={x:{nombre:"X",limite:280,icono:T},instagram:{nombre:"Instagram",limite:2200,icono:k},facebook:{nombre:"Facebook",limite:null,icono:h},tiktok:{nombre:"TikTok",limite:2200,icono:x},youtube:{nombre:"YouTube",limite:null,icono:M}},w=["x","instagram","facebook","tiktok","youtube"];function m(e){return v[e]??{nombre:e,limite:null,icono:f}}function A(e){return m(e).nombre}function S(e){return m(e).icono}const a=["borrador","aprobado","programado","publicado"],D={borrador:{nombre:"Borrador",clase:"border-transparent bg-muted text-muted-foreground"},aprobado:{nombre:"Aprobado",clase:"border-transparent bg-blue-500/15 text-blue-700 dark:text-blue-300"},programado:{nombre:"Programado",clase:"border-transparent bg-amber-500/15 text-amber-700 dark:text-amber-300"},publicado:{nombre:"Publicado",clase:"border-transparent bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"}};function I(e){return D[e]??{nombre:e,clase:"border-transparent bg-muted text-muted-foreground"}}function R(e){const t=a.indexOf(e);return t<0||t>=a.length-1?null:a[t+1]}const E={listo:{nombre:"Listo",variante:"ok"},revisar:{nombre:"Revisar",variante:"aviso"},no_publicar:{nombre:"No publicar",variante:"error"}};function $(e){return e?E[e]??null:null}function F(e){if(!e)return"";const t=new Date(e);return Number.isNaN(t.getTime())?e:new Intl.DateTimeFormat("es-MX",{day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit"}).format(t)}function H(e){if(!e)return"";const t=new Date(e);return Number.isNaN(t.getTime())?"":new Intl.DateTimeFormat("es-MX",{hour:"2-digit",minute:"2-digit"}).format(t)}function O(e){if(!e)return"";const t=new Date(e);if(Number.isNaN(t.getTime()))return"";const r=Math.round((t.getTime()-Date.now())/1e3),o=Math.abs(r),i=new Intl.RelativeTimeFormat("es-MX",{numeric:"auto"}),d=[[60,"second"],[3600,"minute"],[86400,"hour"],[604800,"day"],[2629800,"week"],[31557600,"month"],[1/0,"year"]],u={second:1,minute:60,hour:3600,day:86400,week:604800,month:2629800,year:31557600};for(const[l,c]of d)if(o<l)return i.format(Math.round(r/u[c]),c);return i.format(Math.round(r/u.year),"year")}function L(e){if(!e)return"";const t=new Date(e);if(Number.isNaN(t.getTime()))return"";const r=o=>String(o).padStart(2,"0");return`${t.getFullYear()}-${r(t.getMonth()+1)}-${r(t.getDate())}T${r(t.getHours())}:${r(t.getMinutes())}`}function j(e){if(!e)return null;const t=new Date(e);return Number.isNaN(t.getTime())?null:t.toISOString()}export{x as M,w as O,H as a,L as b,m as c,j as d,$ as e,F as f,S as i,I as m,A as n,R as s,O as t};
