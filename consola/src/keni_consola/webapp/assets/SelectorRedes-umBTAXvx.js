import{p as d,w as a}from"./index-BgW0WhgF.js";import{i as m,C as x}from"./checkbox-Bo7rbbNV.js";import{L as o}from"./dialog-Pj8i91bB.js";/**
 * @license lucide-react v0.475.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const h=[["path",{d:"M15 3h6v6",key:"1q9fwt"}],["path",{d:"M10 14 21 3",key:"gplh6r"}],["path",{d:"M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6",key:"a6xqqp"}]],j=d("ExternalLink",h);function p(s){return`red-${s}`}function g({opciones:s,seleccionadas:t,onCambio:c,disabled:r}){return a.jsxs("div",{className:"space-y-1.5",children:[a.jsx(o,{children:"Redes"}),a.jsx("div",{className:"flex flex-wrap gap-x-5 gap-y-2.5",children:s.map(e=>{const i=m(e.id),n=p(e.id);return a.jsxs("div",{className:"flex items-center gap-2",children:[a.jsx(x,{id:n,checked:t.has(e.id),onCheckedChange:l=>c(e.id,l),disabled:r,"aria-label":e.nombre}),a.jsxs(o,{htmlFor:n,className:"flex cursor-pointer items-center gap-1.5 font-normal",children:[a.jsx(i,{className:"h-4 w-4 text-muted-foreground"}),e.nombre]})]},e.id)})})]})}export{j as E,g as S};
