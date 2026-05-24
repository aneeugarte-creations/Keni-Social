// Feature Configuración — JS vanilla. Solo fetch al endpoint local de guardado.
// Reutiliza los helpers GLOBALES de consola.js (postJSON, fijarEstado,
// marcarCargando): no se redefinen aquí. Sin librerías ni red externa.
"use strict";

function configRecogerFuente(form) {
  const sel = form.querySelector("input[name=fuente]:checked");
  return sel ? sel.value : "";
}

function configRecogerMarcas(form) {
  const marcas = [];
  form.querySelectorAll("input[name=marca]:checked").forEach(function (el) {
    marcas.push(el.value);
  });
  return marcas;
}

async function guardarConfig(form) {
  const estado = form.querySelector(".estado");
  const boton = form.querySelector("button[type=submit]");
  marcarCargando(boton, true);
  fijarEstado(estado, "Guardando...", "");
  try {
    const { ok, datos } = await postJSON("/api/config/guardar", {
      fuente: configRecogerFuente(form),
      marcas: configRecogerMarcas(form),
    });
    if (ok) {
      fijarEstado(estado, datos.mensaje || "Configuración guardada.", "ok");
    } else {
      fijarEstado(estado, datos.error || "No se pudo guardar.", "error");
    }
  } finally {
    marcarCargando(boton, false);
  }
}

document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("form-config");
  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      guardarConfig(form);
    });
  }
});
