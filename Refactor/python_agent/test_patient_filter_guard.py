import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import SQL_Server_AI_Agent_AUV as agent


class PatientFilterGuardTests(unittest.TestCase):
    def test_explicit_all_patients_is_allowed(self):
        self.assertTrue(agent._is_explicit_all_patients_request("muestrame todos los pacientes"))

    def test_unfiltered_patient_filter_is_blocked(self):
        self.assertFalse(agent._has_patient_filter_criteria({"limit": 1000}))

    def test_preset_patient_filter_is_allowed(self):
        self.assertTrue(agent._has_patient_filter_criteria({"preset": {"tiene_seguro": False}}))

    def test_sin_seguro_override(self):
        tool, args = agent._apply_preset_overrides("muestrame pacientes sin seguro", "patient_filter", {})
        self.assertEqual(tool, "patient_filter")
        self.assertEqual(args["preset"], {"tiene_seguro": False})

    def test_con_seguro_override(self):
        tool, args = agent._apply_preset_overrides("muestrame pacientes con seguro", "patient_filter", {})
        self.assertEqual(tool, "patient_filter")
        self.assertEqual(args["preset"], {"tiene_seguro": True})

    def test_con_estado_civil_casado_override(self):
        tool, args = agent._apply_preset_overrides("muestrame pacientes con estado civil casado", "patient_filter", {})
        self.assertEqual(tool, "patient_filter")
        self.assertEqual(args["preset"], {"estado_civil": "Casado/a"})

    def test_pacientes_casados_override(self):
        tool, args = agent._apply_preset_overrides("muestrame pacientes casados", "patient_filter", {})
        self.assertEqual(tool, "patient_filter")
        self.assertEqual(args["preset"], {"estado_civil": "Casado/a"})

    def test_search_patient_filter_is_allowed(self):
        self.assertTrue(
            agent._has_patient_filter_criteria(
                {"search": {"text": "Ana", "fields": ["persona.nombre"]}}
            )
        )


if __name__ == "__main__":
    unittest.main()
