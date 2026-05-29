/**
 * Lógica de SCOPE por app del launcher (cajón de apps · ADR 0005).
 *
 * El catálogo (`GET /api/catalogo`) declara las apps ACTIVAS, cada una con su
 * `nav` y sus `rutas_frontend`. Aquí derivamos, DATA-DRIVEN:
 *   - la ruta PRIMARIA de una app (a dónde lleva su tarjeta del launcher),
 *   - qué app corresponde a un path (para que el sidebar se reduzca a esa app),
 *   - los grupos de nav de UNA app (para el sidebar con scope).
 *
 * Nada está hardcodeado: activar/añadir una app en el backend la hace aparecer
 * sola; desactivarla la quita del launcher y deja de matchear sus rutas.
 */
import type { LucideIcon } from "lucide-react";

import type { AppCatalogo } from "@/types";

import { subPestanasDe } from "./hub-tabs";
import { iconoDe } from "./navegacion";
import type { GrupoNav, ItemNav } from "./navegacion";

/**
 * Una HOJA de navegación de una app: la entrada terminal que el sidebar pinta
 * como nivel 2 (no hay nivel-hub intermedio). Se deriva aplanando la nav de la
 * app: cada entrada que sea un hub (tiene sub-pestañas en `hub-tabs`) aporta SUS
 * sub-pestañas como hojas; el resto aporta la propia entrada.
 */
export interface HojaApp {
  ruta: string;
  etiqueta: string;
  icono: LucideIcon;
  /** Tooltip/accesibilidad (solo lo traen las entradas de nav, no las pestañas). */
  descripcion?: string;
  /** Marca activo solo en match exacto (pestaña "raíz" de un hub, p.ej. /agentes). */
  end?: boolean;
}

/**
 * Hojas PLANAS de una app (nivel 2 del sidebar), respetando el orden de la nav.
 * Aplana los hubs: por cada entrada de nav, si es un hub (`subPestanasDe(ruta)`
 * existe) emite sus sub-pestañas; si no, emite la propia entrada. Resultado: una
 * lista de páginas-hoja sin cabeceras de sección ni nivel-hub.
 */
export function hojasDeApp(app: AppCatalogo): HojaApp[] {
  const hojas: HojaApp[] = [];
  for (const item of app.nav) {
    const subPestanas = subPestanasDe(item.ruta);
    if (subPestanas) {
      for (const tab of subPestanas) {
        hojas.push({
          ruta: tab.ruta,
          etiqueta: tab.etiqueta,
          icono: tab.icono,
          end: tab.end,
        });
      }
    } else {
      hojas.push({
        ruta: item.ruta,
        etiqueta: item.etiqueta,
        icono: iconoDe(item.icono),
        descripcion: item.descripcion,
      });
    }
  }
  return hojas;
}

/**
 * Ruta primaria de una app: su PRIMERA HOJA (nivel 2 ya aplanado). Si la primera
 * entrada de nav es un hub (p.ej. Métricas → Analíticas), resuelve a su primera
 * sub-pestaña (`/analiticas/metricas`), no a la ruta-hub. Si no tuviera hojas,
 * cae a la primera de sus `rutas_frontend`, y en último caso a "/".
 */
export function rutaPrimaria(app: AppCatalogo): string {
  return hojasDeApp(app)[0]?.ruta ?? app.rutas_frontend[0] ?? "/";
}

/**
 * Determina a qué app pertenece un path. Para cada app reúne sus rutas conocidas
 * (las de `nav` + `rutas_frontend`) y se queda con el PREFIJO MÁS LARGO que
 * matchee el path; gana la app dueña de ese prefijo. Así `/parrilla/calendario`
 * cae en Operación aunque otra app tuviera una ruta más corta que también
 * prefijara. Devuelve `undefined` en el launcher o en rutas del shell.
 */
export function appDeRuta(
  apps: AppCatalogo[],
  pathname: string,
): AppCatalogo | undefined {
  let mejor: AppCatalogo | undefined;
  let mejorLargo = -1;
  for (const app of apps) {
    const rutas = new Set<string>([
      ...app.nav.map((n) => n.ruta),
      ...app.rutas_frontend,
    ]);
    for (const ruta of rutas) {
      // Match por segmento: `/parrilla` matchea `/parrilla` y `/parrilla/x`,
      // pero NO `/parrillaX`. La raíz "/" nunca se considera dueña de una app.
      if (ruta === "/" || ruta === "") continue;
      if (pathname === ruta || pathname.startsWith(`${ruta}/`)) {
        if (ruta.length > mejorLargo) {
          mejorLargo = ruta.length;
          mejor = app;
        }
      }
    }
  }
  return mejor;
}

/**
 * Grupos de nav del sidebar para UNA app, resolviendo cada icono-string a su
 * componente. Respeta los bloques visuales (`grupo`/`grupo_orden`) declarados en
 * los manifests, igual que el sidebar plano de hoy, pero acotados a esta app.
 */
export function gruposDeApp(app: AppCatalogo): GrupoNav[] {
  // Agrupa por bloque visual conservando el orden que ya trae el catálogo.
  const bloques = new Map<string, { orden: number; items: ItemNav[] }>();
  for (const item of app.nav) {
    const clave = item.grupo ?? "";
    if (!bloques.has(clave)) {
      bloques.set(clave, { orden: item.grupo_orden ?? 0, items: [] });
    }
    bloques.get(clave)!.items.push({
      ruta: item.ruta,
      etiqueta: item.etiqueta,
      icono: iconoDe(item.icono),
      descripcion: item.descripcion,
    });
  }
  return [...bloques.entries()]
    .sort((a, b) => a[1].orden - b[1].orden || a[0].localeCompare(b[0]))
    .map(([, { items }]) => ({
      // Como hoy: los bloques van sin encabezado (separador discreto).
      etiqueta: "",
      items,
    }));
}
