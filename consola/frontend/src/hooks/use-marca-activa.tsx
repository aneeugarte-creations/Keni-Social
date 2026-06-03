import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { useSesion } from "@/hooks/sesion-contexto";
import { api } from "@/lib/api";
import type { MarcaDisponible } from "@/types";

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
 * nombres legibles desde el catálogo canónico (`/api/publicaciones/opciones`,
 * que entrega `{id, nombre}` con ids canónicos para todo editor).
 *
 * Se monta DEBAJO de la puerta de sesión, así que normalmente hay usuario; aun
 * así es defensivo (si no hay sesión, expone una vista agregada neutra).
 */
export function MarcaActivaProvider({ children }: { children: React.ReactNode }) {
  const { usuario } = useSesion();
  const usuarioId = usuario?.id ?? "";
  const esAdmin = usuario?.rol === "admin";
  // Marcas del perfil (organigrama AMX), en id canónico. Vacío = no cubre ninguna.
  const marcasUsuario = React.useMemo(() => usuario?.marcas ?? [], [usuario?.marcas]);
  const marcaPrimaria = marcasUsuario[0] ?? null;

  // Catálogo canónico de marcas (id → nombre). Se cachea indefinidamente: es el
  // mismo que ya consumen Estudio/Publicaciones, así que no añade carga.
  const catalogoQuery = useQuery({
    queryKey: ["marcas-catalogo"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
    staleTime: Infinity,
  });
  const catalogo = React.useMemo<MarcaDisponible[]>(
    () => catalogoQuery.data?.marcas ?? [],
    [catalogoQuery.data],
  );

  /** ¿`marca` es una elección permitida para este usuario? (admin = cualquiera). */
  const permitida = React.useCallback(
    (marca: string | null): boolean => {
      if (marca === null) return esAdmin; // "Todas" solo para admin.
      if (esAdmin) return true;
      return marcasUsuario.includes(marca);
    },
    [esAdmin, marcasUsuario],
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

  // Opciones del switch: admin → catálogo completo; editor → solo sus marcas.
  // Si el catálogo aún no cargó, se arman desde los ids del perfil (nombre = id)
  // para no esconder el switch durante la carga.
  const marcasParaSwitch = React.useMemo<MarcaDisponible[]>(() => {
    if (esAdmin) return catalogo;
    if (catalogo.length) return catalogo.filter((m) => marcasUsuario.includes(m.id));
    return marcasUsuario.map((id) => ({ id, nombre: id }));
  }, [esAdmin, catalogo, marcasUsuario]);

  const nombreActiva = React.useMemo<string | null>(() => {
    if (marcaActiva === null) return null;
    return catalogo.find((m) => m.id === marcaActiva)?.nombre ?? marcaActiva;
  }, [marcaActiva, catalogo]);

  const valor = React.useMemo<ValorMarcaActiva>(() => {
    const enMarcaPrimaria = marcaActiva === (marcaPrimaria ?? null);
    const esMultiMarca = marcasParaSwitch.length > 1 || (esAdmin && marcasParaSwitch.length >= 1);
    return {
      marcaActiva,
      marcaPrimaria,
      enMarcaPrimaria,
      esMultiMarca,
      puedeTodas: esAdmin,
      marcasParaSwitch,
      nombreActiva,
      cambiarMarca,
      volverAPrimaria,
    };
  }, [
    marcaActiva,
    marcaPrimaria,
    marcasParaSwitch,
    esAdmin,
    nombreActiva,
    cambiarMarca,
    volverAPrimaria,
  ]);

  return <MarcaActivaContexto.Provider value={valor}>{children}</MarcaActivaContexto.Provider>;
}
