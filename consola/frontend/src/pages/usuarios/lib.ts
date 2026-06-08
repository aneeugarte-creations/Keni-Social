import { formatearFecha as fmtFechaCdmx } from "@/lib/fecha";

// Fecha en CDMX (instantes UTC del backend); ver `@/lib/fecha`.
export const formatearFecha = (iso: string | null): string =>
  fmtFechaCdmx(iso) || "—";
