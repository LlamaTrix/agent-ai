// Tests del motor de filtros client-side.
// Corren contra el JS compilado (dist/), así que requieren `npm run build` antes.
// Ejecutar:  npm test     (hace build + node --test)
import test from "node:test";
import assert from "node:assert/strict";

import {
  applyFilterPipeline,
  stripInternalFields,
  compareOp,
  getByPath,
} from "../dist/src/filters/pipeline.js";

// ---- dataset de pacientes de ejemplo --------------------------------------
const patients = () => [
  {
    id: 1,
    estado: true,
    persona: {
      nombre: "Ana", apellidos: "Lopez", ci: "111",
      num_seguro: "S-123", telf1: "70000001",
      estado_civil: "Soltera", fecha_nacimiento: "1990-05-10",
    },
  },
  {
    id: 2,
    estado: false,
    persona: {
      nombre: "Beto", apellidos: "Mora", ci: "222",
      num_seguro: "", telf1: "",
      estado_civil: null, fecha_nacimiento: "0000-00-00",
    },
  },
  {
    id: 3,
    estado: true,
    persona: {
      nombre: "Carla", apellidos: "Nieva", ci: "333",
      empresa_seg: "ACME", tel_referencia: "70000003",
      fecha_nacimiento: "2099-01-01", // futuro → no significativa
    },
  },
];

const ids = (res) => res.items.map((r) => r.id);

// ---- operadores básicos ---------------------------------------------------
test("eq de string es case-insensitive", () => {
  const res = applyFilterPipeline({
    input: patients(),
    filters: [{ field: "persona.nombre", op: "eq", value: "ana" }],
  });
  assert.deepEqual(ids(res), [1]);
});

test("contains / startsWith / endsWith", () => {
  assert.deepEqual(
    ids(applyFilterPipeline({ input: patients(), filters: [{ field: "persona.nombre", op: "contains", value: "ar" }] })),
    [3],
  );
  assert.deepEqual(
    ids(applyFilterPipeline({ input: patients(), filters: [{ field: "persona.nombre", op: "startsWith", value: "b" }] })),
    [2],
  );
  assert.deepEqual(
    ids(applyFilterPipeline({ input: patients(), filters: [{ field: "persona.apellidos", op: "endsWith", value: "eva" }] })),
    [3],
  );
});

test("in y neq", () => {
  assert.deepEqual(
    ids(applyFilterPipeline({ input: patients(), filters: [{ field: "id", op: "in", value: [1, 3] }] })),
    [1, 3],
  );
  assert.deepEqual(
    ids(applyFilterPipeline({ input: patients(), filters: [{ field: "estado", op: "neq", value: true }] })),
    [2],
  );
});

// ---- campos derivados -----------------------------------------------------
test("__has_seguro distingue con y sin seguro", () => {
  assert.deepEqual(
    ids(applyFilterPipeline({ input: patients(), filters: [{ field: "__has_seguro", op: "eq", value: true }] })),
    [1, 3],
  );
  assert.deepEqual(
    ids(applyFilterPipeline({ input: patients(), filters: [{ field: "__has_seguro", op: "eq", value: false }] })),
    [2],
  );
});

test("__has_phone detecta telf1 y tel_referencia", () => {
  assert.deepEqual(
    ids(applyFilterPipeline({ input: patients(), filters: [{ field: "__has_phone", op: "eq", value: false }] })),
    [2],
  );
});

test("fecha_nacimiento exists/not_exists usa __has_birthdate (ignora 0000-00-00 y futuros)", () => {
  assert.deepEqual(
    ids(applyFilterPipeline({ input: patients(), filters: [{ field: "persona.fecha_nacimiento", op: "exists" }] })),
    [1],
  );
  assert.deepEqual(
    ids(applyFilterPipeline({ input: patients(), filters: [{ field: "persona.fecha_nacimiento", op: "not_exists" }] })),
    [2, 3],
  );
});

// ---- limpieza de salida ---------------------------------------------------
test("stripInternalFields elimina los campos __ derivados de la salida", () => {
  const res = applyFilterPipeline({
    input: patients(),
    filters: [{ field: "__has_seguro", op: "eq", value: true }],
  });
  for (const row of res.items) {
    assert.equal("__has_seguro" in row, false);
    assert.equal("__has_phone" in row, false);
    assert.equal("__has_birthdate" in row, false);
    // num_seguro está en INTERNAL_FIELDS → también se quita del nivel raíz
  }
});

// ---- sort / paginación / limit / select -----------------------------------
test("sort desc por id", () => {
  const res = applyFilterPipeline({ input: patients(), sort: { field: "id", direction: "desc" } });
  assert.deepEqual(ids(res), [3, 2, 1]);
});

test("paginación devuelve total real y la página pedida", () => {
  const res = applyFilterPipeline({ input: patients(), page: 2, pageSize: 1, sort: { field: "id", direction: "asc" } });
  assert.equal(res.total, 3);
  assert.deepEqual(ids(res), [2]);
});

test("limit corta resultados pero total refleja el universo", () => {
  const res = applyFilterPipeline({ input: patients(), limit: 2, sort: { field: "id", direction: "asc" } });
  assert.equal(res.total, 3);
  assert.equal(res.returned, 2);
});

test("select proyecta solo los campos pedidos", () => {
  const res = applyFilterPipeline({ input: patients(), select: ["id", "persona.nombre"], limit: 1, sort: { field: "id" } });
  assert.deepEqual(Object.keys(res.items[0]).sort(), ["id", "persona.nombre"]);
});

// ---- search ---------------------------------------------------------------
test("search busca en varios campos", () => {
  const res = applyFilterPipeline({
    input: patients(),
    search: { text: "nieva", fields: ["persona.nombre", "persona.apellidos"] },
  });
  assert.deepEqual(ids(res), [3]);
});

// ---- helpers --------------------------------------------------------------
test("compareOp eq numérico vía toComparable", () => {
  assert.equal(compareOp("10", "gt", "9"), true);
  assert.equal(compareOp("2026-01-01", "lt", "2026-02-01"), true);
});

test("getByPath navega rutas anidadas", () => {
  assert.equal(getByPath({ a: { b: { c: 5 } } }, "a.b.c"), 5);
  assert.equal(getByPath({ a: {} }, "a.b.c"), undefined);
});

test("stripInternalFields es recursivo y respeta arrays", () => {
  const out = stripInternalFields({ keep: 1, created_at: "x", persona: { nombre: "z", updated_at: "y" } });
  assert.deepEqual(out, { keep: 1, persona: { nombre: "z" } });
});
