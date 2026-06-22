import { PanelAjustes } from "@/pages/configuracion/SeccionFuncionalidad";

// Grupos del catálogo que gobiernan la publicación (global + por marca).
const GRUPOS_PIEZA = ["pieza", "publicacion_marca"] as const;
import { CalendarDays } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";

import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { MenuAcciones } from "@/components/layout/MenuAcciones";
import { Button } from "@/components/ui/button";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { PanelPlan } from "@/pages/piezas/GestionPlan";
import { GestionPiezas } from "@/pages/piezas/GestionPiezas";

/**
 * Página "Programación" (`/operacion/programacion`): la rejilla mensual de piezas
 * programadas (`GestionPiezas` en modo calendario), por marca activa del workspace.
 * Es una página plana del sidebar (su hermana es "Turnos"). Desde la cabecera se gestionan los HORARIOS de
 * publicación (las franjas/huecos que alimentan este calendario). Un enlace `?horarios=1` abre
 * los horarios directamente (lo usa el aviso "sin franjas" de la lista de contenido).
 */
export default function CalendarioPublicacion() {
  const { marcaActiva } = useMarcaActiva();
  const [searchParams, setSearchParams] = useSearchParams();
  // Deep-link `?horarios=1` (lo usa el aviso «sin franjas» de la lista de contenido): abre el
  // panel de ajustes con la sección "Plan y horarios" ya desplegada. Se congela en el PRIMER
  // render (el panel y la sección capturan su estado inicial); el efecto de abajo limpia luego
  // el parámetro.
  const [horariosDeepLink] = React.useState(() => searchParams.get("horarios") === "1");
  // «Plan y horarios» es una SUBPÁGINA (no un panel lateral ni pop-up): se abre a pantalla
  // completa con su flecha «← volver». `?horarios=1` la abre directamente.
  const [mostrarPlan, setMostrarPlan] = React.useState(horariosDeepLink);

  // Si se llega con ?horarios=1, limpia el parámetro de la URL (la subpágina ya abrió por
  // `horariosDeepLink`, congelado en el primer render).
  React.useEffect(() => {
    if (searchParams.get("horarios") === "1") {
      const next = new URLSearchParams(searchParams);
      next.delete("horarios");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  // SUBPÁGINA «Plan y horarios»: a pantalla completa, con «← volver». El editor es POR MARCA
  // (key por marca: remontar al cambiar evita arrastrar el plan de la marca anterior).
  if (mostrarPlan && marcaActiva) {
    return (
      <>
        <TituloPagina
          titulo="Plan y horarios"
          icono={CalendarDays}
          onAtras={() => setMostrarPlan(false)}
        />
        <PanelPlan key={marcaActiva} marca={marcaActiva} />
      </>
    );
  }

  return (
    <>
      <TituloPagina titulo="Programación" icono={CalendarDays} />
      <AccionesPagina>
        {/* «Plan y horarios» abre su SUBPÁGINA (no pop-up). El "⋮" queda para los ajustes de
            publicación real. */}
        <Button
          variant="outline"
          size="sm"
          disabled={!marcaActiva}
          onClick={() => setMostrarPlan(true)}
        >
          Plan y horarios
        </Button>
        <MenuAcciones
          ajustesTitulo="Ajustes de programación"
          ajustes={
            <PanelAjustes
              grupos={GRUPOS_PIEZA}
              titulo="Ajustes de publicación"
              acento="amber"
              descripcion="Habilita/deshabilita publicación automática en redes, con excepciones por marca."
            />
          }
        />
      </AccionesPagina>

      <GestionPiezas modo="calendario" />
    </>
  );
}
