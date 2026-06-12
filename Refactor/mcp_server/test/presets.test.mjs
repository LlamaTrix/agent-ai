// Tests de los presets de los dominios nuevos (órdenes/estudios y recetas).
// Corren contra el JS compilado (dist/). Ejecutar:  npm test
import test from "node:test";
import assert from "node:assert/strict";

import { buildEstudiosPresetFilters } from "../dist/src/presets/estudios.js";
import { buildRecetasPresetFilters } from "../dist/src/presets/recetas.js";
import { applyFilterPipeline } from "../dist/src/filters/pipeline.js";

// --- estudios / órdenes ----------------------------------------------------
test("estudios preset: tipo → filtro eq sobre tipo", () => {
  const { filters } = buildEstudiosPresetFilters({ tipo: "Laboratorio" });
  assert.deepEqual(filters, [{ field: "tipo", op: "eq", value: "Laboratorio" }]);
});

test("estudios preset: mes → contains sobre cita.fecha", () => {
  const { filters } = buildEstudiosPresetFilters({ mes: "2026-04" });
  assert.deepEqual(filters, [{ field: "cita.fecha", op: "contains", value: "2026-04" }]);
});

test("estudios filter end-to-end: filtra por tipo y mes de la cita", () => {
  const data = [
    { id: 1, tipo: "Laboratorio", cita: { fecha: "2026-04-10T00:00:00Z" } },
    { id: 2, tipo: "Laboratorio", cita: { fecha: "2026-05-01T00:00:00Z" } },
    { id: 3, tipo: "Analisis de Gabinete", cita: { fecha: "2026-04-20T00:00:00Z" } },
  ];
  const { filters } = buildEstudiosPresetFilters({ tipo: "Laboratorio", mes: "2026-04" });
  const res = applyFilterPipeline({ input: data, filters });
  assert.equal(res.total, 1);
  assert.equal(res.items[0].id, 1);
});

// --- recetas ---------------------------------------------------------------
test("recetas preset: nombre → contains sobre nombre del medicamento", () => {
  const { filters } = buildRecetasPresetFilters({ nombre: "paracetamol" });
  assert.deepEqual(filters, [{ field: "nombre", op: "contains", value: "paracetamol" }]);
});

test("recetas preset: mes → contains sobre visita.cita.fecha", () => {
  const { filters } = buildRecetasPresetFilters({ mes: "2026-05" });
  assert.deepEqual(filters, [{ field: "visita.cita.fecha", op: "contains", value: "2026-05" }]);
});

test("recetas filter end-to-end: filtra por medicamento y mes", () => {
  const data = [
    { id: 1, nombre: "Paracetamol", visita: { cita: { fecha: "2026-05-02T00:00:00Z" } } },
    { id: 2, nombre: "Ibuprofeno", visita: { cita: { fecha: "2026-05-09T00:00:00Z" } } },
    { id: 3, nombre: "Paracetamol", visita: { cita: { fecha: "2026-04-01T00:00:00Z" } } },
  ];
  const { filters } = buildRecetasPresetFilters({ nombre: "Paracetamol", mes: "2026-05" });
  const res = applyFilterPipeline({ input: data, filters });
  assert.equal(res.total, 1);
  assert.equal(res.items[0].id, 1);
});
