// Paneles del editor: barra de herramientas, lista de capas (z-order) e inspector de propiedades.
// Todos operan sobre el store del documento via contexto.
//
// Barrel: el contenido vive ahora en `editor/paneles/`. Se mantiene este módulo para preservar la
// superficie de imports de los consumidores (`Inspector`, `PanelCapas`).

export { Inspector } from "./paneles/Inspector";
export { PanelCapas } from "./paneles/PanelCapas";
