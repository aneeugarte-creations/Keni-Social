import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { useSesion } from "@/hooks/sesion-contexto";
import { api } from "@/lib/api";
import type { MarcaDisponible, MarcaOpcion } from "@/types";

import {
  claveMarcaActiva,
  MARCA_ACTIVA_TODAS,
  MarcaActivaContexto,
  type ValorMarcaActiva,
} from "./marca-activa-contexto";

/** Lee la marca persistida de este usuario (o `undefined` si no hay / falla). */
function leerPersistida(usuarioId: string): string | undefined {
  try {
    return localStorage.getItem(claveMarcaActiva(usuarioId)) ?? undefined;
  } catch {
    return undefined;
  }
}

/** Persiste la marca activa de este usuario (centinela para "Todas"). */
function guardarPersistida(usuarioId: string, marca: string | null): void {
  try {
    localStorage.setItem(claveMarcaActiva(usuarioId), marca ?? MARCA_ACTIVA_TODAS);
  } catch {
    // localStorage no disponible (modo privado): la marca vive solo en memoria.
  }
}

/**
 * Provider de la marca activa. Deriva el estado inicial del perfil de la sesión
 * (`usuario.marcas`) y de la preferencia persistida por usuario, y resuelve los
 * nombres legibles desde el catálogo canónico (`/api/piezas/opciones`,
 * que entrega `{id, nombre}` con ids canónicos para todo editor).
 *
 * Se monta DEBAJO de la puerta de sesión, así que normalmente hay usuario; aun
 * así es defensivo (si no hay sesión, expone una vista agregada neutra).
 */
export function MarcaActivaProvider({ children }: { children: React.ReactNode }) {
  const { usuario } = useSesion();
  const usuarioId = usuario?.id ?? "";
  // Solo el SUPERADMIN (el "admin de la app") ve la vista agregada "Todas". Un admin normal es
  // autoridad sobre SUS marcas asignadas, no sobre todas.
  const esSuperadmin = usuario?.es_superadmin === true;
  // Marcas del perfil (organigrama del cliente), en id canónico. Vacío = no cubre ninguna.
  const marcasUsuario = React.useMemo(() => usuario?.marcas ?? [], [usuario?.marcas]);
  const marcaPrimaria = marcasUsuario[0] ?? null;

  // Catálogo canónico de marcas (id → nombre). Mismo endpoint y queryKey que las páginas de
  // Piezas/Estudio (`["piezas","opciones"]`): comparten caché y se resuelve una sola vez.
  const catalogoQuery = useQuery({
    queryKey: ["piezas", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
    staleTime: Infinity,
  });
  const catalogo = React.useMemo<MarcaOpcion[]>(
    () => catalogoQuery.data?.marcas ?? [],
    [catalogoQuery.data],
  );

  /** ¿`marca` es una elección permitida? Foco, no restricción: cualquiera enfoca cualquier
   *  marca; solo "Todas" (la vista agregada, `null`) queda reservada al superadmin. */
  const permitida = React.useCallback(
    (marca: string | null): boolean => {
      if (marca === null) return esSuperadmin; // "Todas" solo para superadmin.
      return true; // cualquier marca concreta es enfocable por cualquiera.
    },
    [esSuperadmin],
  );

  // Estado inicial: preferencia persistida válida → marca de casa → "Todas".
  const inicial = React.useCallback((): string | null => {
    const guardada = usuarioId ? leerPersistida(usuarioId) : undefined;
    if (guardada !== undefined) {
      const marca = guardada === MARCA_ACTIVA_TODAS ? null : guardada;
      if (permitida(marca)) return marca;
    }
    if (marcaPrimaria) return marcaPrimaria;
    return null; // sin marca asignada (p. ej. admin): vista agregada.
  }, [usuarioId, permitida, marcaPrimaria]);

  const [marcaActiva, setMarcaActiva] = React.useState<string | null>(inicial);

  // Re-inicializa al cambiar de usuario (login distinto): cada quien arranca en
  // SU marca de casa, no heredando la del usuario anterior.
  const refUsuario = React.useRef(usuarioId);
  React.useEffect(() => {
    if (refUsuario.current !== usuarioId) {
      refUsuario.current = usuarioId;
      setMarcaActiva(inicial());
    }
  }, [usuarioId, inicial]);

  const cambiarMarca = React.useCallback(
    (id: string | null) => {
      if (!permitida(id)) return; // ignora marcas fuera del alcance del perfil.
      setMarcaActiva(id);
      if (usuarioId) guardarPersistida(usuarioId, id);
    },
    [permitida, usuarioId],
  );

  const volverAPrimaria = React.useCallback(() => {
    cambiarMarca(marcaPrimaria);
  }, [cambiarMarca, marcaPrimaria]);

  // Opciones del switch: el catálogo COMPLETO para todos (foco, no restricción: cualquiera puede
  // enfocar cualquier marca; lo que separa a admin/editor de superadmin es la vista "Todas", no
  // qué marcas ven). Si el catálogo aún no cargó, se arman desde los ids del perfil (nombre = id)
  // para no esconder el switch durante la carga.
  const marcasParaSwitch = React.useMemo<MarcaDisponible[]>(() => {
    if (catalogo.length) return catalogo;
    return marcasUsuario.map((id) => ({ id, nombre: id }));
  }, [catalogo, marcasUsuario]);

  const nombreActiva = React.useMemo<string | null>(() => {
    if (marcaActiva === null) return null;
    return catalogo.find((m) => m.id === marcaActiva)?.nombre ?? marcaActiva;
  }, [marcaActiva, catalogo]);

  // ¿La marca activa es de NOTICIAS? Solo se oculta el panel de Noticias cuando el catálogo
  // marca la activa como 'propio' (contenido propio); "Todas" (null) y los casos sin dato → sí.
  const marcaActivaEsNoticias = React.useMemo<boolean>(() => {
    if (marcaActiva === null) return true;
    return catalogo.find((m) => m.id === marcaActiva)?.tipo !== "propio";
  }, [marcaActiva, catalogo]);

  // Nombre del panel de investigación de la marca activa (p.ej. "Curiosidades"); "Noticias" por defecto.
  const etiquetaInvestigacion = React.useMemo<string>(() => {
    if (marcaActiva === null) return "Noticias";
    return catalogo.find((m) => m.id === marcaActiva)?.etiqueta_investigacion || "Noticias";
  }, [marcaActiva, catalogo]);

  const valor = React.useMemo<ValorMarcaActiva>(() => {
    const enMarcaPrimaria = marcaActiva === (marcaPrimaria ?? null);
    // "Fuera de casa" SOLO si enfocas una marca que NO es tuya (no está entre tus asignadas):
    // un admin con varias marcas asignadas que cambia entre ellas sigue "en casa" (todas son
    // suyas) y no ve el aviso "Volver a tu marca". "Todas" (null) tampoco es fuera de casa.
    const fueraDeCasa =
      marcaActiva !== null &&
      marcaPrimaria !== null &&
      !marcasUsuario.includes(marcaActiva);
    const esMultiMarca = marcasParaSwitch.length > 1 || esSuperadmin;
    return {
      marcaActiva,
      marcaPrimaria,
      enMarcaPrimaria,
      fueraDeCasa,
      esMultiMarca,
      puedeTodas: esSuperadmin,
      marcaActivaEsNoticias,
      etiquetaInvestigacion,
      marcasParaSwitch,
      nombreActiva,
      cambiarMarca,
      volverAPrimaria,
    };
  }, [
    marcaActiva,
    marcaPrimaria,
    marcasUsuario,
    marcasParaSwitch,
    esSuperadmin,
    marcaActivaEsNoticias,
    etiquetaInvestigacion,
    nombreActiva,
    cambiarMarca,
    volverAPrimaria,
  ]);

  return <MarcaActivaContexto.Provider value={valor}>{children}</MarcaActivaContexto.Provider>;
}
