# Tests deterministas del agente (sin LLM ni red).
# Ejecutar desde python_agent/ con el venv activo:
#     python -m unittest discover -s tests
import os
import sys
import unittest

# Permite importar clinical_agent (vive un nivel arriba de tests/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import clinical_agent as ca  # noqa: E402


class TestNormalizeToolArgs(unittest.TestCase):
    def test_filter_dict_field_op_value_se_envuelve_en_lista(self):
        out = ca._normalize_tool_args({"filters": {"field": "persona.nombre", "op": "eq", "value": "Ana"}})
        self.assertEqual(out["filters"], [{"field": "persona.nombre", "op": "eq", "value": "Ana"}])

    def test_filter_dict_anidado_campo_op_valor(self):
        out = ca._normalize_tool_args({"filters": {"persona.nombre": {"contains": "M"}}})
        self.assertEqual(out["filters"], [{"field": "persona.nombre", "op": "contains", "value": "M"}])

    def test_filter_dict_plano_se_asume_eq(self):
        out = ca._normalize_tool_args({"filters": {"estado": False}})
        self.assertEqual(out["filters"], [{"field": "estado", "op": "eq", "value": False}])

    def test_field_op_value_top_level(self):
        out = ca._normalize_tool_args({"field": "id", "op": "eq", "value": 5})
        self.assertEqual(out["filters"], [{"field": "id", "op": "eq", "value": 5}])
        self.assertNotIn("field", out)

    def test_alias_de_operador_startswith(self):
        out = ca._normalize_tool_args({"filters": [{"field": "persona.nombre", "op": "starts_with", "value": "M"}]})
        self.assertEqual(out["filters"][0]["op"], "startsWith")

    def test_mapea_tiene_seguro_a_campo_interno(self):
        out = ca._normalize_tool_args({"filters": [{"field": "tiene_seguro", "op": "eq", "value": False}]})
        self.assertEqual(out["filters"][0]["field"], "__has_seguro")

    def test_mapea_tiene_telefono_y_corrige_op_contains(self):
        out = ca._normalize_tool_args({"filters": [{"field": "persona.tiene_telefono", "op": "contains", "value": True}]})
        self.assertEqual(out["filters"][0]["field"], "__has_phone")
        self.assertEqual(out["filters"][0]["op"], "eq")

    def test_normaliza_sinonimos_de_sexo(self):
        out = ca._normalize_tool_args({"filters": [{"field": "persona.sexo", "op": "neq", "value": "varones"}]})
        self.assertEqual(out["filters"][0]["value"], "Masculino")
        out = ca._normalize_tool_args({"filters": [{"field": "sexo", "op": "eq", "value": "Mujer"}]})
        self.assertEqual(out["filters"][0]["value"], "Femenino")

    def test_normaliza_sexo_en_lista_in(self):
        out = ca._normalize_tool_args({"filters": [{"field": "persona.sexo", "op": "in", "value": ["varon", "mujer"]}]})
        self.assertEqual(out["filters"][0]["value"], ["Masculino", "Femenino"])

    def test_pregunta_de_prefijo_convierte_contains_en_startswith(self):
        out = ca._normalize_tool_args(
            {"filters": [{"field": "persona.nombre", "op": "contains", "value": "M"}]},
            question="pacientes que empiecen con la letra M",
        )
        self.assertEqual(out["filters"][0]["op"], "startsWith")

    def test_args_no_dict_devuelve_dict_vacio(self):
        self.assertEqual(ca._normalize_tool_args(None), {})
        self.assertEqual(ca._normalize_tool_args("texto"), {})


class TestExtractores(unittest.TestCase):
    def test_extract_cita_id(self):
        self.assertEqual(ca._extract_cita_id_query("de quien es la cita 52"), "52")
        self.assertEqual(ca._extract_cita_id_query("cita con id 7"), "7")
        self.assertIsNone(ca._extract_cita_id_query("cuantos pacientes hay"))

    def test_looks_like_odontograma(self):
        self.assertTrue(ca._looks_like_odontograma_query("odontogramas de Juan"))
        self.assertTrue(ca._looks_like_odontograma_query("que molar trataron"))
        self.assertFalse(ca._looks_like_odontograma_query("pacientes sin seguro"))

    def test_strip_accents_lc(self):
        self.assertEqual(ca._strip_accents_lc("Pabellón Médico"), "pabellon medico")

    def test_is_count_question(self):
        self.assertTrue(ca._is_count_question("cuantos pacientes masculinos tengo?"))
        self.assertTrue(ca._is_count_question("¿Cuántas citas hay?"))
        self.assertTrue(ca._is_count_question("dame la cantidad de pagos"))
        self.assertFalse(ca._is_count_question("dame los pacientes masculinos"))
        self.assertFalse(ca._is_count_question("de quien es la cita 52"))


class TestEdad(unittest.TestCase):
    def test_fecha_vacia_o_futura(self):
        self.assertEqual(ca._age_details_from_birthdate(""), (None, None, None))
        self.assertEqual(ca._age_details_from_birthdate("2099-01-01"), (None, None, None))

    def test_adulto_devuelve_anios(self):
        years, months, text = ca._age_details_from_birthdate("1990-05-10")
        self.assertIsInstance(years, int)
        self.assertGreater(years, 0)
        self.assertTrue(text.endswith("año") or text.endswith("años"))


class TestDominiosNuevos(unittest.TestCase):
    # --- Detección de dominio (órdenes/recetas/atención) ---
    def test_looks_like_receta(self):
        self.assertTrue(ca._looks_like_receta_query("cuántas recetas se emitieron en abril"))
        self.assertTrue(ca._looks_like_receta_query("qué medicamentos le recetaron a Juan"))
        self.assertTrue(ca._looks_like_receta_query("prescripciones de paracetamol"))
        self.assertFalse(ca._looks_like_receta_query("pacientes sin seguro"))

    def test_looks_like_estudio(self):
        self.assertTrue(ca._looks_like_estudio_query("órdenes de laboratorio de abril"))
        self.assertTrue(ca._looks_like_estudio_query("cuántos estudios de gabinete hay"))
        self.assertTrue(ca._looks_like_estudio_query("ordenes médicas"))
        self.assertTrue(ca._looks_like_estudio_query("ecocardiogramas de mayo"))
        # "ordenar/ordename/en orden" (sort) NO debe activar el dominio
        self.assertFalse(ca._looks_like_estudio_query("ordename los pacientes por edad"))
        self.assertFalse(ca._looks_like_estudio_query("pacientes en orden alfabético"))
        self.assertFalse(ca._looks_like_estudio_query("cuántos pacientes hay"))

    def test_looks_like_visita(self):
        self.assertTrue(ca._looks_like_visita_query("cuántas visitas hubo en abril"))
        self.assertTrue(ca._looks_like_visita_query("atenciones del mes"))
        self.assertTrue(ca._looks_like_visita_query("pacientes atendidos hoy"))
        self.assertFalse(ca._looks_like_visita_query("cuántos pagos hay"))

    def test_looks_like_agenda(self):
        # "atender" en presente/futuro y "agenda" → agenda (citas)
        self.assertTrue(ca._looks_like_agenda_query("cuales pacientes atendere la siguiente semana"))
        self.assertTrue(ca._looks_like_agenda_query("dame la agenda de hoy"))
        self.assertTrue(ca._looks_like_agenda_query("a quien atiendo manana"))
        # "atendidos/atención" es pasado → NO agenda (eso es visitas)
        self.assertFalse(ca._looks_like_agenda_query("pacientes atendidos el mes pasado"))
        self.assertFalse(ca._looks_like_agenda_query("cuantos pacientes hay"))

    def test_relative_date_siguiente_semana(self):
        # ambas formas: "semana siguiente" y "siguiente semana"
        a = ca._extract_relative_date_filter("citas de la semana que viene", field="fecha")
        b = ca._extract_relative_date_filter("citas de la siguiente semana", field="fecha")
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        self.assertEqual([f["op"] for f in b], ["gte", "lte"])

    def test_extract_estudio_tipo(self):
        self.assertEqual(ca._extract_estudio_tipo("órdenes de laboratorio"), "Laboratorio")
        self.assertEqual(ca._extract_estudio_tipo("estudios de gabinete"), "Analisis de Gabinete")
        self.assertEqual(ca._extract_estudio_tipo("ecocardiograma de Ana"), "Gabinete Cardiologico")
        self.assertIsNone(ca._extract_estudio_tipo("cuántas órdenes hay"))

    def test_extract_receta_medicamento(self):
        self.assertEqual(ca._extract_receta_medicamento("recetas de paracetamol"), "paracetamol")
        self.assertEqual(ca._extract_receta_medicamento("dame las recetas de ibuprofeno"), "ibuprofeno")
        # "del paciente X" NO es medicamento (va por patient_id)
        self.assertIsNone(ca._extract_receta_medicamento("recetas del paciente luis"))
        # mes/fecha no es medicamento
        self.assertIsNone(ca._extract_receta_medicamento("recetas de abril"))
        self.assertIsNone(ca._extract_receta_medicamento("cuántas recetas hay"))

    def test_extract_patient_name_after_keyword(self):
        self.assertEqual(ca._extract_patient_name_after_keyword("estudios del paciente Luis"), "Luis")
        self.assertEqual(ca._extract_patient_name_after_keyword("recetas del paciente Juan Perez"), "Juan Perez")
        # "pacientes masculinos" no es un nombre
        self.assertIsNone(ca._extract_patient_name_after_keyword("cuántos pacientes masculinos hay"))
        self.assertIsNone(ca._extract_patient_name_after_keyword("cuántas órdenes hay"))
        # "pacienteS con X" (plural=filtro) NO es nombre de paciente
        self.assertIsNone(ca._extract_patient_name_after_keyword("dame listado de pacientes con recetas"))
        self.assertIsNone(ca._extract_patient_name_after_keyword("pacientes que tengan recetas"))
        self.assertIsNone(ca._extract_patient_name_after_keyword("pacientes con sangre"))
        self.assertIsNone(ca._extract_patient_name_after_keyword("cuantos pacientes con otitis media en abril"))
        self.assertIsNone(ca._extract_patient_name_after_keyword("lista de pacientes con diagnostico atendidos"))

    def test_extract_sort_spec_pacientes_por_edad(self):
        # "por edad" en pacientes → ordena por fecha_nacimiento (invertido)
        s = ca._extract_sort_spec("ordename los pacientes por edad", "patient_filter")
        self.assertEqual(s["field"], "persona.fecha_nacimiento")
        # default (sin dirección) = edad ascendente = fecha desc (más joven primero)
        self.assertEqual(s["direction"], "desc")
        # "de mayor a menor" edad → mayores primero = fecha asc
        s2 = ca._extract_sort_spec("ordename los pacientes por edad de mayor a menor", "patient_filter")
        self.assertEqual(s2["direction"], "asc")

    def test_extract_sort_spec_none_si_no_pide_orden(self):
        self.assertIsNone(ca._extract_sort_spec("cuántos pacientes hay", "patient_filter"))

    def test_report_spec_ignora_ordenar(self):
        # "ordename por edad" NO es reporte (es sort)
        self.assertIsNone(ca._extract_report_spec("ordename los pacientes por edad"))
        # pero "por edad" sin verbo de orden sí es group_by
        self.assertEqual(ca._extract_report_spec("pacientes por edad")["type"], "group_by")

    def test_compact_rows_citas(self):
        rows = [{
            "id": 1659, "patient_nombre": "Hernan Prueba",
            "fecha": "2026-06-12T06:29:10Z", "hora_inicio": "2026-06-12T10:00:00Z",
            "estado": "pendiente", "motivo": "Control", "comentarios": "x", "patient_id": 5,
        }]
        out = ca._compact_rows(rows, "citas_filter")
        self.assertEqual(set(out[0].keys()), {"paciente", "fecha", "hora", "estado", "motivo"})
        self.assertEqual(out[0]["paciente"], "Hernan Prueba")
        self.assertEqual(out[0]["hora"], "10:00")  # formateado a HH:MM

    def test_compact_rows_entidad_desconocida_no_cambia(self):
        rows = [{"a": 1, "b": 2}]
        self.assertEqual(ca._compact_rows(rows, "notas_by_cita"), rows)

    def test_extract_diagnostico_or(self):
        self.assertEqual(ca._extract_diagnostico_or("cuantos pacientes con bronquitis o con diarrea"), ["bronquitis", "diarrea"])
        self.assertEqual(ca._extract_diagnostico_or("pacientes con gripe o resfrio"), ["gripe", "resfrio"])
        # filtros conocidos NO son diagnósticos
        self.assertIsNone(ca._extract_diagnostico_or("pacientes con seguro o con telefono"))
        self.assertIsNone(ca._extract_diagnostico_or("pacientes con sangre o positivo"))

    def test_bare_list_followup(self):
        self.assertTrue(ca._is_bare_list_followup("dame la lista"))
        self.assertTrue(ca._is_bare_list_followup("muestralos"))
        self.assertTrue(ca._is_bare_list_followup("quiero la lista"))
        # consulta completa (trae criterio) NO es follow-up
        self.assertFalse(ca._is_bare_list_followup("dame la lista de pacientes con bronquitis"))
        self.assertFalse(ca._is_bare_list_followup("cuantos pacientes hay"))

    def test_to_list_form(self):
        self.assertEqual(
            ca._to_list_form("cuantos pacientes con bronquitis o diarrea"),
            "dame la lista de pacientes con bronquitis o diarrea",
        )

    def test_has_patient_reference(self):
        self.assertTrue(ca._has_patient_reference("todas las citas con ella"))
        self.assertTrue(ca._has_patient_reference("quiero ver todos sus antecedentes"))
        self.assertTrue(ca._has_patient_reference("la ultima cita de ese paciente"))
        self.assertFalse(ca._has_patient_reference("cuantos pacientes hay"))
        self.assertFalse(ca._has_patient_reference("citas de abril"))
        # "su/sus" en una LISTA de pacientes NO es referencia (bug Rotavirus)
        self.assertFalse(ca._has_patient_reference("pacientes que tienen su vacuna de rotavirus"))
        self.assertFalse(ca._has_patient_reference("pacientes con sus recetas"))

    def test_passes_age(self):
        # "mayores a 30" → fecha_nacimiento < corte (lt)
        flt = [{"field": "persona.fecha_nacimiento", "op": "lt", "value": "1994-06-13"}]
        self.assertTrue(ca._passes_age("1980-01-01", flt))   # nació antes → mayor
        self.assertFalse(ca._passes_age("2010-01-01", flt))  # nació después → menor
        self.assertFalse(ca._passes_age("", flt))            # sin fecha → no pasa

    def test_wants_latest(self):
        self.assertTrue(ca._wants_latest("diagnostico de la ultima visita de Hernan"))
        self.assertTrue(ca._wants_latest("la cita mas reciente"))
        self.assertFalse(ca._wants_latest("todas las visitas"))

    def test_extract_sangre(self):
        self.assertEqual(ca._extract_sangre("pacientes con sangre O+"), "O+")
        self.assertEqual(ca._extract_sangre("tipo de sangre A-"), "A-")
        self.assertEqual(ca._extract_sangre("grupo sanguineo AB positivo"), "AB+")
        self.assertIsNone(ca._extract_sangre("cuantos pacientes hay"))

    def test_extract_antecedent_patient_filters(self):
        self.assertEqual(ca._extract_antecedent_patient_filters("pacientes con sangre O+"), {"sangre": "O+"})
        self.assertEqual(ca._extract_antecedent_patient_filters("pacientes con alergias"), {"alergias": True})
        self.assertEqual(
            ca._extract_antecedent_patient_filters("pacientes con peso entre 1 y 2"),
            {"peso_min": 1.0, "peso_max": 2.0},
        )
        self.assertIsNone(ca._extract_antecedent_patient_filters("pacientes mujeres"))

    def test_clinical_single_patient(self):
        # Pregunta de UN paciente nombrado → devuelve el nombre (antecedents_get).
        self.assertEqual(ca._extract_clinical_single_patient("Isabella tiene alergias?"), "Isabella")
        self.assertEqual(
            ca._extract_clinical_single_patient("quiero los antecedentes de Hernan Olaechea"),
            "Hernan Olaechea",
        )
        self.assertEqual(
            ca._extract_clinical_single_patient(
                "quiero saber el tipo de sangre y alergias que tiene Alessandra"
            ),
            "Alessandra",
        )
        # Consultas de LISTA / conteo → None (van a antecedents_filter).
        self.assertIsNone(ca._extract_clinical_single_patient("pacientes con alergias"))
        self.assertIsNone(ca._extract_clinical_single_patient("cuantos pacientes con alergias hay"))
        self.assertIsNone(
            ca._extract_clinical_single_patient("listado de pacientes tipo de sangre O+ mayores a 30")
        )
        self.assertIsNone(ca._extract_clinical_single_patient("quiero ver todos sus antecedentes"))
        # Sin término clínico → None.
        self.assertIsNone(ca._extract_clinical_single_patient("Isabella tiene citas"))

    def test_is_vacuna_query(self):
        self.assertTrue(ca._is_vacuna_query("pacientes con vacuna de Rotavirus"))
        self.assertTrue(ca._is_vacuna_query("qué vacunas tiene Isabella"))
        self.assertTrue(ca._is_vacuna_query("pacientes con vacunas vencidas"))
        self.assertFalse(ca._is_vacuna_query("pacientes con alergias"))

    def test_extract_vacuna_name(self):
        self.assertEqual(ca._extract_vacuna_name("pacientes con vacuna de Rotavirus"), "rotavirus")
        self.assertEqual(
            ca._extract_vacuna_name("quiero listado de pacientes que tienen su vacuna de Rotavirus"),
            "rotavirus",
        )
        self.assertEqual(ca._extract_vacuna_name("quién tiene la vacuna contra la influenza"), "influenza")
        self.assertEqual(ca._extract_vacuna_name("vacuna de hepatitis b"), "hepatitis b")
        # Sin vacuna puntual → None.
        self.assertIsNone(ca._extract_vacuna_name("cuántos pacientes tienen vacuna"))

    def test_flatten_payment_row(self):
        row = {"monto": 100, "saldo": 50, "metodo": "QR",
               "patient": {"persona": {"nombre": "Ana", "apellidos": "Lopez", "telf1": "777"}}}
        out = ca._flatten_payment_row(row)
        self.assertEqual(out["patient_nombre"], "Ana Lopez")
        self.assertEqual(out["telefono"], "777")
        self.assertEqual(out["saldo"], 50)
        self.assertNotIn("patient", out)

    def test_flatten_antecedent_row(self):
        row = {"sangre": "O+", "peso": 70, "alergias_description": "Polen",
               "patient": {"persona": {"nombre": "Ana", "apellidos": "Lopez"}}}
        out = ca._flatten_antecedent_row(row)
        self.assertEqual(out["patient_nombre"], "Ana Lopez")
        self.assertEqual(out["sangre"], "O+")
        self.assertNotIn("patient", out)

    def test_antecedent_display_fields(self):
        # sin alergias → "No" (no se omite); con descripción → la descripción
        r1 = ca._antecedent_display_fields({"alergias": False, "medicacion": True,
                                            "medicacion_description": "Losartán", "quirurgicos": False})
        self.assertEqual(r1["alergias"], "No")
        self.assertEqual(r1["medicacion"], "Losartán")
        self.assertEqual(r1["quirurgicos"], "No")
        r2 = ca._antecedent_display_fields({"alergias": True, "alergias_description": ""})
        self.assertEqual(r2["alergias"], "Sí")  # flag true sin descripción

    def test_merge_antecedentes(self):
        row = {"nombre": "Jose Araque", "sangre": None}
        ant = {"sangre": "A+", "peso": 70, "altura": 1.75,
               "alergias": True, "alergias_description": "Penicilina",
               "medicacion": False, "quirurgicos": True, "quirurgicos_description": "Apendicectomía"}
        ca._merge_antecedentes(row, ant)
        self.assertEqual(row["sangre"], "A+")
        self.assertEqual(row["peso"], 70)
        self.assertEqual(row["alergias"], "Penicilina")        # usa la descripción
        self.assertIsNone(row["medicacion"])                   # flag false → None
        self.assertEqual(row["quirurgicos"], "Apendicectomía")

    def test_full_rows_antecedentes(self):
        # flujo real: primero se computan los campos sí/no, luego se proyecta
        row = ca._antecedent_display_fields({
            "sangre": "A+", "peso": 70, "altura": 1.7,
            "alergias": True, "alergias_description": "Penicilina", "id": 3, "patient_id": 5,
        })
        out = ca._full_rows([row], "antecedents_get")[0]
        self.assertEqual(out["sangre"], "A+")
        self.assertEqual(out["alergias"], "Penicilina")
        self.assertNotIn("id", out)

    def test_full_rows_pagos(self):
        rows = [{"monto": 100, "saldo": 0, "metodo": "Efectivo", "motivo": "Consulta",
                 "observaciones": "ok", "created_at": "2025-04-01 03:25:47", "id": 9, "patient_id": 5}]
        out = ca._full_rows(rows, "payments_filter")[0]
        self.assertEqual(out["fecha"], "01/04/2025")
        self.assertEqual(out["monto"], 100)
        self.assertIn("observaciones", out)

    def test_full_rows_entidad_generica(self):
        # entidad sin _FULL_COLS → vista genérica: todos los escalares menos ruido
        rows = [{"id": 1, "created_at": "x", "nota": "control", "tipo": "general",
                 "cita": {"obj": 1}}]
        out = ca._full_rows(rows, "notas_by_cita")[0]
        self.assertNotIn("id", out)
        self.assertNotIn("created_at", out)
        self.assertNotIn("cita", out)  # objeto anidado se omite
        self.assertEqual(out["nota"], "control")
        self.assertEqual(out["tipo"], "general")

    def test_full_rows_paciente_trae_todos_los_campos(self):
        rows = [{
            "nombre": "Alessandra Giorgio", "ci": "00030", "sexo": "Femenino",
            "edad_texto": "15 años", "telefono": "60883730", "email": "a@x.com",
            "direccion": "Calle 1", "sangre": "O+", "ocupacion": "Estudiante",
            "empresa_seg": None, "num_seguro": None, "estado": True,
        }]
        out = ca._full_rows(rows, "patient_filter")[0]
        # incluye campos que la vista compacta NO muestra
        for k in ("email", "direccion", "sangre", "ocupacion"):
            self.assertIn(k, out)
        self.assertEqual(out["nombre"], "Alessandra Giorgio")

    def test_field_selection_todos(self):
        self.assertEqual(ca._extract_field_selection("dame las citas con todos los campos", "citas_filter"), "all")
        self.assertEqual(ca._extract_field_selection("citas con todas las columnas", "citas_filter"), "all")
        # "datos completos" / "detalle completo" / "ficha completa" → todos los campos
        self.assertEqual(ca._extract_field_selection("dame los datos completos de jose araque", "patient_filter"), "all")
        self.assertEqual(ca._extract_field_selection("quiero el detalle completo de alessandra", "patient_filter"), "all")
        self.assertEqual(ca._extract_field_selection("ficha completa del paciente X", "patient_filter"), "all")
        self.assertEqual(ca._extract_field_selection("toda la info del paciente", "patient_filter"), "all")

    def test_field_selection_especifica(self):
        sel = ca._extract_field_selection("dame la agenda con solo los campos nombre y motivo", "citas_filter")
        self.assertIn(("patient_nombre", "paciente"), sel)
        self.assertIn(("motivo", "motivo"), sel)
        self.assertNotIn(("fecha", "fecha"), sel)

    def test_field_selection_none_sin_palabra_campos(self):
        # "con teléfono" es un FILTRO, no selección de columnas → None
        self.assertIsNone(ca._extract_field_selection("pacientes con telefono", "patient_filter"))
        self.assertIsNone(ca._extract_field_selection("dame la agenda de hoy", "citas_filter"))

    def test_explicit_format(self):
        self.assertEqual(ca._explicit_format("dame las citas de hoy en texto plano"), "text")
        self.assertEqual(ca._explicit_format("dame los pacientes en texto"), "text")
        self.assertEqual(ca._explicit_format("muestrame las citas sin tabla"), "text")
        self.assertEqual(ca._explicit_format("dame los pacientes en tabla"), "table")
        self.assertEqual(ca._explicit_format("citas de hoy como tabla"), "table")
        self.assertEqual(ca._explicit_format("dame la tabla de las citas del paciente hernan"), "table")
        self.assertEqual(ca._explicit_format("dame una tabla de pacientes"), "table")
        # "dame la lista de pacientes" NO es "en lista" → no fuerza nada
        self.assertIsNone(ca._explicit_format("dame la lista de pacientes"))
        self.assertIsNone(ca._explicit_format("cuántos pacientes hay"))

    def test_fmt_cell_fecha_y_hora(self):
        # fecha ISO → DD/MM/YYYY ; hora ISO → HH:MM
        self.assertEqual(ca._fmt_cell("fecha", "2026-06-12T06:29:10.000000Z"), "12/06/2026")
        self.assertEqual(ca._fmt_cell("hora", "2026-06-12T02:29:10.000000Z"), "02:29")
        self.assertEqual(ca._fmt_cell("nacimiento", "1990-05-10"), "10/05/1990")
        # otras columnas quedan igual
        self.assertEqual(ca._fmt_cell("estado", "en curso"), "en curso")
        self.assertEqual(ca._fmt_cell("fecha", None), None)

    def test_compact_rows_formatea_fecha_hora(self):
        rows = [{
            "patient_nombre": "David Lozano", "fecha": "2026-06-12T06:29:10.000000Z",
            "hora_inicio": "2026-06-12T02:29:10.000000Z", "estado": "en curso", "motivo": "asdf",
        }]
        out = ca._compact_rows(rows, "citas_filter")[0]
        self.assertEqual(out["fecha"], "12/06/2026")
        self.assertEqual(out["hora"], "02:29")

    def test_format_rows_as_text(self):
        rows = [{"paciente": "Ana Lopez", "fecha": "2026-04-01", "motivo": "Control"}]
        txt = ca._format_rows_as_text(rows, "citas", 1)
        self.assertIn("Encontré 1 citas", txt)
        self.assertIn("Ana Lopez", txt)
        self.assertIn("Motivo: Control", txt)

    def test_format_rows_as_text_saltea_vacios(self):
        # paciente y hora vacíos → no se muestran; el título es el primer no-vacío (fecha)
        rows = [{"paciente": None, "fecha": "10/04/2026", "hora": None,
                 "estado": "cerrada", "motivo": "prueba"}]
        txt = ca._format_rows_as_text(rows, "citas", 1)
        self.assertNotIn("—", txt)
        self.assertNotIn("Hora:", txt)
        self.assertIn("• 10/04/2026", txt)
        self.assertIn("Estado: cerrada", txt)

    def test_wants_sin_genero(self):
        self.assertTrue(ca._wants_sin_genero("pacientes sin género"))
        self.assertTrue(ca._wants_sin_genero("pacientes que no tengan genero"))
        self.assertTrue(ca._wants_sin_genero("pacientes que no tienen sexo"))
        self.assertFalse(ca._wants_sin_genero("pacientes de género masculino"))
        self.assertFalse(ca._wants_sin_genero("cuántos pacientes hay"))

    def test_sexo_filters_otro_es_neq_masc_y_fem(self):
        # "sin género" / "Otro" = ni Masculino ni Femenino (no eq "Otro")
        fs = ca._sexo_filters("persona.sexo", "Otro")
        self.assertEqual(
            fs,
            [
                {"field": "persona.sexo", "op": "neq", "value": "Masculino"},
                {"field": "persona.sexo", "op": "neq", "value": "Femenino"},
            ],
        )

    def test_patient_lookup_no_captura_conteo(self):
        # "¿cuántos pacientes hay?" NO debe tomarse como búsqueda del paciente "hay"
        self.assertIsNone(ca._extract_patient_name_lookup("¿cuántos pacientes hay?"))
        self.assertIsNone(ca._extract_patient_name_lookup("cuantos pacientes tengo"))
        # "datos del paciente Juan Perez" sí es una búsqueda por nombre
        self.assertEqual(
            ca._extract_patient_name_lookup("datos del paciente Juan Perez"),
            "juan perez",
        )

    # --- Flatteners (suben fecha/paciente al nivel raíz) ---
    def test_flatten_estudio_row(self):
        row = {
            "id": 1, "tipo": "Laboratorio",
            "cita": {"fecha": "2026-04-15T00:00:00.000000Z",
                     "patient": {"persona": {"nombre": "Ana", "apellidos": "Lopez"}}},
        }
        out = ca._flatten_estudio_row(row)
        self.assertNotIn("cita", out)
        self.assertEqual(out["tipo"], "Laboratorio")
        self.assertEqual(out["fecha"], "2026-04-15T00:00:00.000000Z")
        self.assertEqual(out["patient_nombre"], "Ana Lopez")

    def test_flatten_receta_row(self):
        row = {
            "id": 9, "nombre": "Paracetamol", "presentacion": "Jarabe",
            "visita": {"cita": {"fecha": "2026-05-02T00:00:00.000000Z"},
                       "patient": {"persona": {"nombre": "Juan", "apellidos": "Perez"}}},
        }
        out = ca._flatten_receta_row(row)
        self.assertNotIn("visita", out)
        self.assertEqual(out["nombre"], "Paracetamol")
        self.assertEqual(out["fecha"], "2026-05-02T00:00:00.000000Z")
        self.assertEqual(out["patient_nombre"], "Juan Perez")

    def test_flatten_visita_row(self):
        row = {
            "id": 3, "motivo": "Control",
            "cita": {"fecha": "2026-06-01T00:00:00.000000Z"},
            "patient": {"persona": {"nombre": "Eva", "apellidos": "Diaz", "sexo": "Femenino"}},
        }
        out = ca._flatten_visita_row(row)
        self.assertNotIn("patient", out)
        self.assertNotIn("cita", out)
        self.assertEqual(out["fecha"], "2026-06-01T00:00:00.000000Z")
        self.assertEqual(out["patient_nombre"], "Eva Diaz")
        self.assertEqual(out["patient_sexo"], "Femenino")

    # --- Reportes sobre los dominios nuevos ---
    def test_report_group_estudios_por_tipo(self):
        rows = [{"tipo": "Laboratorio"}, {"tipo": "Laboratorio"}, {"tipo": "Analisis de Gabinete"}]
        texto, desglose = ca._build_report({"type": "group_by", "dim": "tipo"}, rows, "estudios_filter")
        self.assertIn("Órdenes por tipo", texto)
        grupos = {d["grupo"]: d["cantidad"] for d in desglose}
        self.assertEqual(grupos["Laboratorio"], 2)
        self.assertEqual(grupos["Analisis de Gabinete"], 1)

    def test_report_group_recetas_por_mes(self):
        rows = [{"fecha": "2026-04-01"}, {"fecha": "2026-04-20"}, {"fecha": "2026-05-03"}]
        texto, desglose = ca._build_report({"type": "group_by", "dim": "mes"}, rows, "recetas_filter")
        grupos = {d["grupo"]: d["cantidad"] for d in desglose}
        self.assertEqual(grupos["2026-04"], 2)
        self.assertEqual(grupos["2026-05"], 1)


class TestEnsureResultLimit(unittest.TestCase):
    def test_inyecta_limit_si_no_hay_paginacion(self):
        out = ca._ensure_result_limit({"filters": []}, default_limit=5000)
        self.assertEqual(out["limit"], 5000)

    def test_respeta_limit_existente(self):
        out = ca._ensure_result_limit({"limit": 10}, default_limit=5000)
        self.assertEqual(out["limit"], 10)

    def test_respeta_pageSize_o_page_existente(self):
        self.assertNotIn("limit", ca._ensure_result_limit({"pageSize": 20}))
        self.assertNotIn("limit", ca._ensure_result_limit({"page": 2}))


class TestSexoExclusions(unittest.TestCase):
    def _vals(self, fs):
        return sorted(f["value"] for f in fs)

    def test_no_sean_varones_o_mujeres(self):
        fs = ca._extract_sexo_exclusions("dame la cantidad de pacientes que no sean varones o mujeres")
        self.assertEqual(self._vals(fs), ["Femenino", "Masculino"])
        self.assertTrue(all(f["op"] == "neq" for f in fs))

    def test_no_sean_ninos_ni_ninas(self):
        fs = ca._extract_sexo_exclusions("pacientes que no sean niños ni niñas")
        self.assertEqual(self._vals(fs), ["Femenino", "Masculino"])

    def test_no_sean_femeninos_ni_masculinos(self):
        fs = ca._extract_sexo_exclusions("pacientes que no sean femeninos ni masculinos")
        self.assertEqual(self._vals(fs), ["Femenino", "Masculino"])

    def test_excluir_solo_uno(self):
        fs = ca._extract_sexo_exclusions("pacientes que no sean hombres")
        self.assertEqual(self._vals(fs), ["Masculino"])

    def test_sin_negacion_devuelve_none(self):
        self.assertIsNone(ca._extract_sexo_exclusions("dame los pacientes masculinos"))

    def test_negacion_sin_sexo_devuelve_none(self):
        self.assertIsNone(ca._extract_sexo_exclusions("pacientes que no tengan telefono"))


class TestPatientNameLookup(unittest.TestCase):
    def test_apellido_solo(self):
        self.assertEqual(ca._extract_patient_name_lookup("quiero los datos del paciente olaechea"), "olaechea")

    def test_con_apellido_explicito(self):
        self.assertEqual(ca._extract_patient_name_lookup("dame los datos del paciente con apellido olaechea"), "olaechea")

    def test_nombre_completo(self):
        self.assertEqual(ca._extract_patient_name_lookup("datos del paciente hernan olaechea"), "hernan olaechea")

    def test_tres_tokens_con_enie(self):
        # conserva la ñ y captura los 3 tokens
        self.assertEqual(ca._extract_patient_name_lookup("dame los datos del paciente Javier Soliz Añez").lower(), "javier soliz añez")

    def test_no_aplica_a_citas(self):
        self.assertIsNone(ca._extract_patient_name_lookup("dame las citas del paciente olaechea"))

    def test_no_captura_palabras_de_filtro(self):
        self.assertIsNone(ca._extract_patient_name_lookup("dame los pacientes masculinos"))
        self.assertIsNone(ca._extract_patient_name_lookup("pacientes solteros"))
        self.assertIsNone(ca._extract_patient_name_lookup("pacientes con seguro alianza"))

    def test_datos_de_nombre_sin_palabra_paciente(self):
        # "datos/ficha de <nombre>" también es búsqueda por nombre (sin "paciente").
        self.assertEqual(ca._extract_patient_name_lookup("dame los datos de isabella"), "isabella")
        self.assertEqual(ca._extract_patient_name_lookup("ficha de hernan olaechea"), "hernan olaechea")
        # Si menciona otra entidad (citas/pagos), no es búsqueda por nombre.
        self.assertIsNone(ca._extract_patient_name_lookup("datos de las citas de isabella"))


class TestBareListFollowup(unittest.TestCase):
    def test_followups_reales(self):
        self.assertTrue(ca._is_bare_list_followup("dame la lista"))
        self.assertTrue(ca._is_bare_list_followup("dámelos"))
        self.assertTrue(ca._is_bare_list_followup("muéstralos"))
        self.assertTrue(ca._is_bare_list_followup("dame los nombres"))

    def test_consulta_completa_no_es_followup(self):
        # "dame los datos de isabella" NO es follow-up (nombra un paciente) → no
        # debe re-ejecutar la consulta anterior.
        self.assertFalse(ca._is_bare_list_followup("dame los datos de isabella"))
        self.assertFalse(ca._is_bare_list_followup("dame la lista de pacientes con vacuna de rotavirus"))
        self.assertFalse(ca._is_bare_list_followup("muéstrame las citas"))


class TestBroadenNameFilter(unittest.TestCase):
    def test_nombre_pasa_a_search_ambos_campos(self):
        out = ca._broaden_name_filter({"filters": [{"field": "persona.nombre", "op": "contains", "value": "olaechea"}]})
        self.assertEqual(out["search"]["fields"], ["persona.nombre", "persona.apellidos"])
        self.assertEqual(out["search"]["text"], "olaechea")
        self.assertEqual(out["filters"], [])

    def test_conserva_otros_filtros(self):
        out = ca._broaden_name_filter({"filters": [
            {"field": "persona.sexo", "op": "eq", "value": "Masculino"},
            {"field": "persona.nombre", "op": "contains", "value": "juan"},
        ]})
        self.assertEqual(out["search"]["text"], "juan")
        self.assertEqual(out["filters"], [{"field": "persona.sexo", "op": "eq", "value": "Masculino"}])

    def test_no_toca_startswith(self):
        args = {"filters": [{"field": "persona.nombre", "op": "startsWith", "value": "M"}]}
        out = ca._broaden_name_filter(args)
        self.assertNotIn("search", out)
        self.assertEqual(out["filters"][0]["op"], "startsWith")

    def test_respeta_apellido_explicito(self):
        args = {"filters": [
            {"field": "persona.nombre", "op": "contains", "value": "juan"},
            {"field": "persona.apellidos", "op": "contains", "value": "perez"},
        ]}
        out = ca._broaden_name_filter(args)
        self.assertNotIn("search", out)  # si hay apellido explícito, no toca


class TestPresenceFilters(unittest.TestCase):
    def test_sin_seguro(self):
        fs = ca._extract_presence_filters("cuantos pacientes masculinos sin seguro")
        self.assertEqual(fs, [{"field": "__has_seguro", "op": "eq", "value": False}])

    def test_con_seguro_y_telefono(self):
        fs = ca._extract_presence_filters("pacientes asegurados con telefono")
        campos = {f["field"]: f["value"] for f in fs}
        self.assertEqual(campos["__has_seguro"], True)
        self.assertEqual(campos["__has_phone"], True)

    def test_sin_telefono(self):
        fs = ca._extract_presence_filters("pacientes sin telefono")
        self.assertEqual(fs, [{"field": "__has_phone", "op": "eq", "value": False}])

    def test_sin_mencion_devuelve_none(self):
        self.assertIsNone(ca._extract_presence_filters("dame los pacientes masculinos"))


class TestEstadoCivil(unittest.TestCase):
    def test_soltero_a_la_barra(self):
        self.assertEqual(ca._canonical_estado_civil("soltero"), "Soltero/a")
        self.assertEqual(ca._canonical_estado_civil("Solteras"), "Soltero/a")

    def test_normalize_canoniza_estado_civil(self):
        out = ca._normalize_tool_args({"filters": [{"field": "persona.estado_civil", "op": "eq", "value": "casado"}]})
        self.assertEqual(out["filters"][0]["value"], "Casado/a")


class TestMultiFiltro(unittest.TestCase):
    """Hito: consultas multi-filtro sobre pacientes + citas (cantidades/listas)."""

    def test_citas_sexo_edad_mes_se_combinan(self):
        q = "dame las citas de varones mayores a 30 años en abril"
        self.assertEqual(ca._extract_sexo_positive(q), "Masculino")
        age = ca._extract_age_filters(q)
        self.assertTrue(age and age[0]["op"] == "lt")
        mes = ca._extract_month_filter(q, field="fecha")
        self.assertTrue(mes and mes[0]["op"] == "contains")
        self.assertTrue(ca._is_list_request(q))

    def test_pacientes_normalize_preserva_filtros_y_canoniza_sexo(self):
        args = {"filters": [
            {"field": "persona.sexo", "op": "eq", "value": "varones"},
            {"field": "persona.estado_civil", "op": "eq", "value": "Soltero"},
        ]}
        out = ca._normalize_tool_args(args)
        self.assertEqual(len(out["filters"]), 2)               # no pierde filtros
        self.assertEqual(out["filters"][0]["value"], "Masculino")    # canoniza sexo
        self.assertEqual(out["filters"][1]["value"], "Soltero/a")    # canoniza estado civil

    def test_pacientes_conteo_con_edad(self):
        q = "cuantos pacientes mayores a 65 años hay"
        self.assertTrue(ca._is_count_question(q))
        age = ca._extract_age_filters(q)
        self.assertTrue(age and age[0]["field"] == "persona.fecha_nacimiento")


class TestListRequest(unittest.TestCase):
    def test_pide_registros(self):
        self.assertTrue(ca._is_list_request("dame las citas del mes de abril"))
        self.assertTrue(ca._is_list_request("muestrame los pacientes"))
        self.assertTrue(ca._is_list_request("listame los pagos de abril"))

    def test_excluye_agregaciones(self):
        self.assertFalse(ca._is_list_request("dame el promedio de pagos"))
        self.assertFalse(ca._is_list_request("dame la suma de montos"))

    def test_no_es_pedido_de_lista(self):
        self.assertFalse(ca._is_list_request("de quien es la cita 52"))


class TestMonthFilter(unittest.TestCase):
    def test_mes_usa_contains_y_anio_actual(self):
        from datetime import datetime
        fs = ca._extract_month_filter("dame citas en el mes de abril")
        self.assertEqual(fs, [{"field": "fecha", "op": "contains", "value": f"{datetime.now().year}-04"}])

    def test_mes_con_anio_explicito(self):
        fs = ca._extract_month_filter("citas de diciembre 2025")
        self.assertEqual(fs[0]["value"], "2025-12")

    def test_rango_de_dias(self):
        from datetime import datetime
        y = datetime.now().year
        fs = ca._extract_month_filter("cuantas citas de varones entre el 15 y 25 de abril")
        self.assertEqual(len(fs), 2)
        self.assertEqual(fs[0], {"field": "fecha", "op": "gte", "value": f"{y}-04-15"})
        self.assertEqual(fs[1], {"field": "fecha", "op": "lte", "value": f"{y}-04-25T23:59:59"})

    def test_dia_puntual(self):
        from datetime import datetime
        y = datetime.now().year
        fs = ca._extract_month_filter("citas el 15 de abril")
        self.assertEqual(fs, [{"field": "fecha", "op": "contains", "value": f"{y}-04-15"}])

    def test_sin_mes_devuelve_none(self):
        self.assertIsNone(ca._extract_month_filter("dame citas con varones"))


class TestRelativeDate(unittest.TestCase):
    def test_esta_semana_es_rango_lun_dom(self):
        from datetime import datetime, timedelta
        fs = ca._extract_relative_date_filter("dame las citas de esta semana")
        self.assertEqual(len(fs), 2)
        self.assertEqual(fs[0]["op"], "gte")
        self.assertEqual(fs[1]["op"], "lte")
        hoy = datetime.now().date()
        lunes = hoy - timedelta(days=hoy.weekday())
        self.assertEqual(fs[0]["value"], lunes.strftime("%Y-%m-%d"))

    def test_hoy_es_contains_del_dia(self):
        from datetime import datetime
        fs = ca._extract_relative_date_filter("citas de hoy")
        self.assertEqual(fs, [{"field": "fecha", "op": "contains", "value": datetime.now().strftime("%Y-%m-%d")}])

    def test_este_mes(self):
        from datetime import datetime
        fs = ca._extract_relative_date_filter("citas de este mes")
        self.assertEqual(fs[0]["value"], datetime.now().strftime("%Y-%m"))

    def test_sin_fecha_relativa(self):
        self.assertIsNone(ca._extract_relative_date_filter("dame las citas de varones"))


class TestSexoFilters(unittest.TestCase):
    def test_otro_es_ni_masculino_ni_femenino(self):
        fs = ca._sexo_filters("persona.sexo", "Otro")
        self.assertEqual(fs, [
            {"field": "persona.sexo", "op": "neq", "value": "Masculino"},
            {"field": "persona.sexo", "op": "neq", "value": "Femenino"},
        ])

    def test_sin_genero_detecta_otro(self):
        self.assertEqual(ca._extract_sexo_positive("dame los pacientes sin genero"), "Otro")

    def test_masculino_es_eq(self):
        self.assertEqual(ca._sexo_filters("persona.sexo", "Masculino"),
                         [{"field": "persona.sexo", "op": "eq", "value": "Masculino"}])


class TestSexoPositive(unittest.TestCase):
    def test_un_sexo_afirmativo(self):
        self.assertEqual(ca._extract_sexo_positive("dame citas con varones en abril"), "Masculino")
        self.assertEqual(ca._extract_sexo_positive("citas del genero masculino"), "Masculino")
        self.assertEqual(ca._extract_sexo_positive("citas con mujeres"), "Femenino")

    def test_negacion_no_es_positivo(self):
        self.assertIsNone(ca._extract_sexo_positive("citas que no sean de varones"))

    def test_sin_sexo_o_ambiguo(self):
        self.assertIsNone(ca._extract_sexo_positive("dame citas en abril"))
        self.assertIsNone(ca._extract_sexo_positive("citas de varones y mujeres"))


class TestAgeFilters(unittest.TestCase):
    def test_cutoff_resta_anios(self):
        from datetime import datetime
        anio_actual = datetime.now().year
        self.assertTrue(ca._birthdate_cutoff(10).startswith(str(anio_actual - 10)))

    def test_sin_edad_devuelve_none(self):
        self.assertIsNone(ca._extract_age_filters("dame los pacientes masculinos"))
        self.assertIsNone(ca._extract_age_filters("de quien es la cita 52"))

    def test_mayores_a_n_usa_lt(self):
        fs = ca._extract_age_filters("pacientes varones mayores a 10 años")
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0]["field"], "persona.fecha_nacimiento")
        self.assertEqual(fs[0]["op"], "lt")

    def test_menores_o_igual_usa_gte(self):
        fs = ca._extract_age_filters("pacientes menores o igual a 10 años")
        self.assertEqual(fs[0]["op"], "gte")

    def test_mayores_y_menores_son_complementarios(self):
        # mismo corte, ops complementarios (lt vs gte) → particionan sin solaparse
        mayores = ca._extract_age_filters("varones mayores a 10 años")[0]
        menores = ca._extract_age_filters("varones menores o igual a 10 años")[0]
        self.assertEqual(mayores["value"], menores["value"])
        self.assertEqual({mayores["op"], menores["op"]}, {"lt", "gte"})

    def test_menores_a_n_usa_gt(self):
        fs = ca._extract_age_filters("pacientes menores a 18 años")
        self.assertEqual(fs[0]["op"], "gt")

    def test_rango_entre_n_y_m(self):
        fs = ca._extract_age_filters("pacientes entre 10 y 20 años")
        ops = sorted(f["op"] for f in fs)
        self.assertEqual(ops, ["gte", "lte"])

    def test_edad_exacta_con_n_anios(self):
        fs = ca._extract_age_filters("pacientes varones con 10 años")
        ops = sorted(f["op"] for f in fs)
        self.assertEqual(ops, ["gt", "lte"])  # rango de ~1 año = edad exacta

    def test_edad_exacta_de_n_anios(self):
        fs = ca._extract_age_filters("pacientes de 5 años")
        self.assertEqual(len(fs), 2)


class TestReportes(unittest.TestCase):
    def test_detecta_group_by(self):
        self.assertEqual(ca._extract_report_spec("dame los pacientes por sexo"), {"type": "group_by", "dim": "sexo"})
        self.assertEqual(ca._extract_report_spec("citas por mes"), {"type": "group_by", "dim": "mes"})
        self.assertEqual(ca._extract_report_spec("pacientes por estado civil"), {"type": "group_by", "dim": "estado_civil"})

    def test_detecta_promedio_y_resumen(self):
        self.assertEqual(ca._extract_report_spec("promedio de edad de los pacientes")["type"], "avg_age")
        self.assertEqual(ca._extract_report_spec("dame el promedio por edad de todos los pacientes")["type"], "avg_age")
        self.assertEqual(ca._extract_report_spec("edad promedio")["type"], "avg_age")
        self.assertEqual(ca._extract_report_spec("dame un resumen de pacientes")["type"], "summary")

    def test_group_by_edad_bucketiza(self):
        self.assertEqual(ca._extract_report_spec("pacientes por edad"), {"type": "group_by", "dim": "edad"})
        rows = [{"edad": 5}, {"edad": 25}, {"edad": 70}, {"edad": None}]
        _, d = ca._build_report({"type": "group_by", "dim": "edad"}, rows, "patient_filter")
        grupos = {x["grupo"] for x in d}
        self.assertIn("menores de 18", grupos)
        self.assertIn("60+", grupos)
        self.assertIn("(sin dato)", grupos)

    def test_no_es_reporte(self):
        self.assertIsNone(ca._extract_report_spec("dame los pacientes masculinos"))
        self.assertIsNone(ca._extract_report_spec("citas de abril"))

    def test_group_by_sexo_cuenta_bien(self):
        rows = [{"sexo": "Masculino"}, {"sexo": "Femenino"}, {"sexo": "Masculino"}, {"sexo": None}]
        texto, desglose = ca._build_report({"type": "group_by", "dim": "sexo"}, rows, "patient_filter")
        d = {x["grupo"]: x["cantidad"] for x in desglose}
        self.assertEqual(d["Masculino"], 2)
        self.assertEqual(d["Femenino"], 1)
        self.assertEqual(d["(sin dato)"], 1)
        self.assertIn("total 4", texto)

    def test_avg_age(self):
        rows = [{"edad": 10}, {"edad": 20}, {"edad": None}]
        texto, _ = ca._build_report({"type": "avg_age"}, rows, "patient_filter")
        self.assertIn("15.0", texto)

    def test_group_by_citas_mes(self):
        rows = [{"fecha": "2026-04-01T00:00:00"}, {"fecha": "2026-04-15T00:00:00"}, {"fecha": "2026-03-02T00:00:00"}]
        _, desglose = ca._build_report({"type": "group_by", "dim": "mes"}, rows, "citas_filter")
        d = {x["grupo"]: x["cantidad"] for x in desglose}
        self.assertEqual(d["2026-04"], 2)
        self.assertEqual(d["2026-03"], 1)


class TestWantsExcel(unittest.TestCase):
    def test_pide_excel(self):
        self.assertTrue(ca._wants_excel("dame el excel de los pacientes masculinos"))
        self.assertTrue(ca._wants_excel("quiero descargar la lista"))
        self.assertTrue(ca._wants_excel("exportar las citas de abril"))

    def test_no_pide_excel(self):
        self.assertFalse(ca._wants_excel("cuantos pacientes masculinos hay"))
        self.assertFalse(ca._wants_excel("dame los pacientes masculinos"))


class TestSingleRowText(unittest.TestCase):
    def test_cita_en_texto(self):
        row = {"fecha": "2026-04-10T18:09:00", "tipo_evento": "Consulta", "estado": "cerrada",
               "motivo": "control", "patient_nombre": "Hernan Olaechea"}
        txt = ca._single_row_text("citas_filter", row)
        self.assertIn("Fecha: 10/04/2026", txt)
        self.assertIn("Tipo: Consulta", txt)
        self.assertIn("Paciente: Hernan Olaechea", txt)
        self.assertNotIn("18:09", txt)  # solo la fecha, sin hora

    def test_paciente_en_texto(self):
        row = {"nombre": "Hernan Olaechea", "ci": "234234", "sexo": "Masculino",
               "edad_texto": "30 años", "telefono": None, "empresa_seg": "ALIANZA"}
        txt = ca._single_row_text("patient_filter", row)
        self.assertTrue(txt.startswith("• Hernan Olaechea"))
        self.assertIn("CI: 234234", txt)
        self.assertIn("Seguro: ALIANZA", txt)
        self.assertNotIn("Teléfono", txt)  # omite campos vacíos

    def test_paciente_sin_seguro(self):
        txt = ca._single_row_text("patient_filter", {"nombre": "Ana", "ci": "1", "tiene_seguro": False})
        self.assertIn("Seguro: sin seguro", txt)


class TestFlattenCitaRow(unittest.TestCase):
    def test_sube_sexo_nombre_al_nivel_raiz(self):
        cita = {
            "id": 1, "fecha": "2026-04-02", "estado": "cerrada",
            "patient": {"id": 9, "persona": {"nombre": "Ana", "apellidos": "Lopez", "sexo": "Femenino"}},
        }
        out = ca._flatten_cita_row(cita)
        self.assertEqual(out["patient_sexo"], "Femenino")
        self.assertEqual(out["patient_nombre"], "Ana Lopez")
        self.assertEqual(out["id"], 1)          # conserva campos de la cita
        self.assertNotIn("patient", out)        # suelta el objeto pesado

    def test_sin_patient_no_rompe(self):
        out = ca._flatten_cita_row({"id": 1, "fecha": "2026-04-02"})
        self.assertIsNone(out["patient_sexo"])


class TestDescribeExc(unittest.TestCase):
    def test_excepcion_simple(self):
        self.assertEqual(ca._describe_exc(ValueError("boom")), "ValueError: boom")

    def test_desenrolla_exception_group(self):
        eg = ExceptionGroup("grupo", [RuntimeError("HTTP 429 rate limit")])
        self.assertEqual(ca._describe_exc(eg), "RuntimeError: HTTP 429 rate limit")


class TestUnwrapRows(unittest.TestCase):
    def test_lista_directa(self):
        self.assertEqual(ca._unwrap_rows([{"a": 1}]), [{"a": 1}])

    def test_envuelto_en_items_rows_data(self):
        self.assertEqual(ca._unwrap_rows({"items": [{"a": 1}]}), [{"a": 1}])
        self.assertEqual(ca._unwrap_rows({"data": [{"b": 2}]}), [{"b": 2}])

    def test_sin_lista_devuelve_vacio(self):
        self.assertEqual(ca._unwrap_rows({"x": 1}), [])


if __name__ == "__main__":
    unittest.main()
