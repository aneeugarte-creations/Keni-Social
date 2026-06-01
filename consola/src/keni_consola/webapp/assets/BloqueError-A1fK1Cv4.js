import{ab as c,an as e,c as i,d as l,b as o,N as x,a6 as d}from"./index-B5dt7KLI.js";/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const m=[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["line",{x1:"12",x2:"12",y1:"8",y2:"12",key:"1pkeuh"}],["line",{x1:"12",x2:"12.01",y1:"16",y2:"16",key:"4dfq90"}]],u=c("CircleAlert",m);function h({titulo:t,mensaje:a,onReintentar:n,cargando:s=!1,className:r}){return e.jsx(i,{className:r,children:e.jsxs(l,{className:"flex flex-col items-center gap-4 py-12 text-center",children:[e.jsx(u,{className:"h-6 w-6 text-destructive","aria-hidden":"true"}),e.jsxs("div",{className:"space-y-1",children:[e.jsx("p",{className:"text-sm font-medium text-foreground",children:t}),e.jsx("p",{className:"max-w-md text-sm text-muted-foreground",children:a??"Ocurrió un problema inesperado. Vuelve a intentarlo en un momento."})]}),e.jsxs(o,{variant:"outline",onClick:n,disabled:s,children:[e.jsx(x,{className:d("h-4 w-4",s&&"animate-spin")}),"Reintentar"]})]})})}export{h as B,u as C};
