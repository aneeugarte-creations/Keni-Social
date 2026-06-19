import { Newspaper, Rss, Sparkles, TrendingUp } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { PestanasSeccion, type PestanaSeccion } from "@/components/layout/encabezado";
import Algoritmos from "@/pages/Algoritmos";
import Cobertura from "@/pages/Cobertura";
import PublicacionesHub from "@/pages/PublicacionesHub";
import Fuentes from "@/pages/Fuentes";

/**
 * Cockpit OPERATIVO de INVESTIGACIÓN (`/maquina/investigacion`): el pool de noticias que el equipo
 * revisa a diario. Sub-secciones planas (`?seccion=`), cada una REUTILIZANDO una superficie existente:
 *   · NOTICIAS (`Cobertura`): el pool segmentado por líneas con usar/descartar — lo que el humano
 *     revisa. Es la sección por defecto. (La ruta vieja `/datos/investigacion` redirige aquí.)
 *   · FUENTES (`Fuentes`): los canales que alimentan el pool.
 *   · ALGORITMOS (`Algoritmos`): inteligencia de plataforma + trends.
 *   · CONTENIDOS (`PublicacionesHub`): el banco EVERGREEN —piezas que no caducan—.
 *
 * La subnav vive en el TOPBAR (vía `<PestanasSeccion/>`), igual que un hub por ruta (Métricas):
 * sin una tira propia bajo el título.
 *
 * El PIPELINE (recolectar → verificar) ya NO vive aquí: se enciende y se vigila en «Contexto»
 * (Máquina), donde cada fase trae su prompt, su contexto y sus logs. Los ajustes del motor también
 * viven en «Contexto» (esta página es solo operativa, sin «⋮» propio).
 */

/** Sub-secciones del cockpit (clave `?seccion=`). Noticias (el pool) es la primera y la por defecto. */
type Seccion = "mesa" | "fuentes" | "algoritmos" | "contenidos";
const SECCIONES: readonly Seccion[] = ["mesa", "fuentes", "algoritmos", "contenidos"];
const PESTANAS: PestanaSeccion[] = [
  { valor: "mesa", etiqueta: "Noticias", icono: Newspaper },
  { valor: "fuentes", etiqueta: "Fuentes", icono: Rss },
  { valor: "algoritmos", etiqueta: "Algoritmos", icono: TrendingUp },
  { valor: "contenidos", etiqueta: "Publicaciones", icono: Sparkles },
];

export default function CockpitInvestigacion() {
  const [searchParams, setSearchParams] = useSearchParams();

  const seccionParam = searchParams.get("seccion");
  const seccion: Seccion = SECCIONES.includes(seccionParam as Seccion)
    ? (seccionParam as Seccion)
    : "mesa";
  const cambiarSeccion = (valor: string) => {
    setSearchParams(
      (prev) => {
        prev.set("seccion", valor);
        return prev;
      },
      { replace: true },
    );
  };

  return (
    <>
      <PestanasSeccion pestanas={PESTANAS} activo={seccion} onSelect={cambiarSeccion} />

      {/* NOTICIAS: el pool con usar/descartar (Cobertura) — la sección por defecto. */}
      {seccion === "mesa" && <Cobertura />}
      {/* FUENTES: los canales que alimentan el pool. */}
      {seccion === "fuentes" && <Fuentes />}
      {/* ALGORITMOS: inteligencia de plataforma + trends. */}
      {seccion === "algoritmos" && <Algoritmos />}
      {/* CONTENIDOS: el banco EVERGREEN (PublicacionesHub). */}
      {seccion === "contenidos" && <PublicacionesHub />}
    </>
  );
}
