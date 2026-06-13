// Barrel de las piezas del calendario de la rota (celdas, chips, diálogos y helpers).
// La librería de componentes se troceó por familias bajo ./calendario/ en un refactor de
// PURA reubicación; este barrel preserva la superficie de import histórica
// (`import { ... } from "./CalendarioPiezas"`) re-exportando todo desde los nuevos módulos.
export * from "./calendario/utils";
export * from "./calendario/chips";
export * from "./calendario/celdas";
export * from "./calendario/dialogs";
