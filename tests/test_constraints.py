from __future__ import annotations

import unittest

from factory.tracka.intent import REAGENT_FAMILY, constraint_violations, parse_intent


def tags(intent):
    return {c["tag"] for c in intent.constraints}

class TestParseConstraints(unittest.TestCase):
    def test_all_four_dictionary_constraints(self):
        it = parse_intent("снизить потери никеля без нового оборудования, "
                          "без новых реагентов, не снижая качество концентрата "
                          "и без снижения производительности")
        self.assertEqual(tags(it), {"без нового оборудования", "без новых реагентов",
                                    "сохранить качество концентрата",
                                    "без снижения производительности"})
        self.assertTrue(it.no_new_equipment)

    def test_no_constraints(self):
        self.assertEqual(parse_intent("повысить извлечение меди").constraints, [])

    def test_named_reagent(self):
        it = parse_intent("повысить извлечение Ni без реагента Finfix 300")
        named = [c for c in it.constraints if c.get("name")]
        self.assertEqual(len(named), 1)
        self.assertEqual(named[0]["name"], "finfix 300")
        self.assertEqual(named[0]["kind"], "reagent")

    def test_named_reagent_verb_form(self):
        it = parse_intent("снизить потери, не использовать реагент кмц, без остановки")
        self.assertIn("кмц", [c.get("name") for c in it.constraints])

class TestViolations(unittest.TestCase):
    def test_equipment(self):
        it = parse_intent("снизить потери никеля без нового оборудования")
        self.assertEqual(constraint_violations(it, "раскрытие / измельчение", True),
                         ["без нового оборудования"])
        self.assertEqual(constraint_violations(it, "доизвлечение флотацией", False), [])

    def test_reagent_family(self):
        it = parse_intent("снизить потери без новых реагентов")
        self.assertEqual(constraint_violations(it, REAGENT_FAMILY, False),
                         ["без новых реагентов"])
        self.assertEqual(constraint_violations(it, "грохочение", False), [])

    def test_named_reagent_matches_text_only(self):
        it = parse_intent("повысить извлечение без реагента кмц")

        self.assertEqual(
            constraint_violations(it, "реагенты", False,
                                  text="Дозировка КМЦ как депрессора породы"),
            ["без реагента кмц"])

        self.assertEqual(
            constraint_violations(it, REAGENT_FAMILY, False,
                                  text="Подбор собирателя (ксантогенат)"), [])

    def test_quality_not_penalized(self):
        it = parse_intent("снизить потери, сохранить качество концентрата")
        self.assertEqual(it.constraints[0]["kind"], "quality")
        self.assertEqual(constraint_violations(it, REAGENT_FAMILY, True), [])

class TestGeneratorPenalty(unittest.TestCase):
    def test_priority_penalty_and_marking(self):
        from factory.tracka.generator import HypothesisGenerator
        from factory.tracka.reader import ClassLoss, FormLoss, TailingsProfile

        cl = ClassLoss(size_class="-71+45", tonnes={"Ni": 100.0, "Cu": 40.0},
                       cells={"Ni": "E7", "Cu": "G7"})
        cl.forms = [FormLoss("Закрытый Pnt/Cp", "Ni", 90.0, 90.0, True, "E30"),
                    FormLoss("Раскрытый Pnt/Cp", "Ni", 10.0, 10.0, True, "E31")]
        prof = TailingsProfile(fabric="Тест", classes=[cl])

        base = HypothesisGenerator().generate(prof, kpi="снизить потери никеля")
        capped = HypothesisGenerator().generate(
            prof, kpi="снизить потери никеля без нового оборудования")
        h0, h1 = base[0], capped[0]
        self.assertEqual(h0.violates_constraints, [])
        self.assertEqual(h1.violates_constraints, ["без нового оборудования"])
        self.assertAlmostEqual(h1.metrics["priority"],
                               round(h0.metrics["priority"] * 0.1, 5), places=5)

if __name__ == "__main__":
    unittest.main()
