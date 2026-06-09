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


class TestMultiFiltro(unittest.TestCase):
    """Hito: consultas multi-filtro sobre pacientes + citas (cantidades/listas)."""

    def test_citas_sexo_edad_mes_se_combinan(self):
        q = "dame las citas de varones mayores a 30 años en abril"
        self.assertEqual(ca._extract_sexo_positive(q), "Masculino")
        age = ca._extract_age_filters(q)
        self.assertTrue(age and age[0]["op"] == "lt")
        mes = ca._extract_month_filter(q, field="fecha")
        self.assertTrue(mes and mes["op"] == "contains")
        self.assertTrue(ca._is_list_request(q))

    def test_pacientes_normalize_preserva_filtros_y_canoniza_sexo(self):
        args = {"filters": [
            {"field": "persona.sexo", "op": "eq", "value": "varones"},
            {"field": "persona.estado_civil", "op": "eq", "value": "Soltero"},
        ]}
        out = ca._normalize_tool_args(args)
        self.assertEqual(len(out["filters"]), 2)               # no pierde filtros
        self.assertEqual(out["filters"][0]["value"], "Masculino")  # canoniza sexo
        self.assertEqual(out["filters"][1]["value"], "Soltero")    # respeta el resto

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
        f = ca._extract_month_filter("dame citas en el mes de abril")
        self.assertEqual(f["op"], "contains")
        self.assertEqual(f["value"], f"{datetime.now().year}-04")

    def test_mes_con_anio_explicito(self):
        f = ca._extract_month_filter("citas de diciembre 2025")
        self.assertEqual(f["value"], "2025-12")

    def test_sin_mes_devuelve_none(self):
        self.assertIsNone(ca._extract_month_filter("dame citas con varones"))


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
