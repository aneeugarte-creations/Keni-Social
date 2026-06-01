import{a6 as i,ai as e,a as c,b as l,B as o,y as x,a1 as d}from"./index-gEBWfa9q.js";/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const m=[["circle",{cx:"12",cy:"12",r:"10",key:"1mglay"}],["line",{x1:"12",x2:"12",y1:"8",y2:"12",key:"1pkeuh"}],["line",{x1:"12",x2:"12.01",y1:"16",y2:"16",key:"4dfq90"}]],u=i("CircleAlert",m);function y({titulo:a,mensaje:t,onReintentar:r,cargando:s=!1,className:n}){return e.jsx(c,{className:n,children:e.jsxs(l,{className:"flex flex-col items-center gap-4 py-12 text-center",children:[e.jsx(u,{className:"h-6 w-6 text-destructive","aria-hidden":"true"}),e.jsxs("div",{className:"space-y-1",children:[e.jsx("p",{className:"text-sm font-medium text-foreground",children:a}),e.jsx("p",{className:"max-w-md text-sm text-muted-foreground",children:t??"Ocurrió un problema inesperado. Vuelve a intentarlo en un momento."})]}),e.jsxs(o,{variant:"outline",onClick:r,disabled:s,children:[e.jsx(x,{className:d("h-4 w-4",s&&"animate-spin")}),"Reintentar"]})]})})}export{y as B,u as C};
