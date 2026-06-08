/** Columna por la que se ordena la lista de objetos, con su dirección. */
export type ClaveOrden = "nombre" | "tamano" | "modificado";

export interface OrdenS3 {
  clave: ClaveOrden;
  dir: "asc" | "desc";
}
