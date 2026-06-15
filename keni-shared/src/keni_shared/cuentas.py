"""Cuentas hermanas de las marcas — fuente UNICA del monorepo.

Se cargan del paquete de cliente declarativo (`clientes/<cliente>.toml`, seccion `[cuentas]`),
externalizado a configuracion (#135). Anadir un cliente nuevo = anadir/seleccionar un `.toml`.

Sin estado: solo datos, materializados una vez al importar (desde el cliente activo).
"""

from __future__ import annotations

from .cliente import cargar_cliente

_cliente = cargar_cliente()

# Cuenta principal del reporte de deportes (su `id_metricas`). Coincide con
# `marcas.id_metricas_de("claro-sports")` en el cliente por defecto.
CUENTA_DEPORTES_PRINCIPAL: str = _cliente.deportes_principal

# Cuentas hermanas de Claro Sports (canal de TV + sub-vertical de golf). NO son
# marcas del catalogo: el guard de `muestra` verifica que no se solapan con el.
CUENTAS_DEPORTES_HERMANAS: tuple[str, ...] = _cliente.deportes_hermanas
