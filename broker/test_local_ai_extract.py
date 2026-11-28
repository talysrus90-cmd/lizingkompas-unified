import unittest
from broker.local_ai_extract import validate_candidates, number

class LocalExtractionTests(unittest.TestCase):
    def test_normalise_currency_and_literal_page(self):
        text="Аванс: 200 000,00 руб. Срок: 36 месяцев."
        result=validate_candidates(text,{"candidates":[
            {"field":"advance","value":"200000 RUB","evidence":"Аванс: 200 000,00 руб."},
            {"field":"term_months","value":"36","evidence":"Срок: 36 месяцев."},
        ]},7)
        self.assertEqual([x["value"] for x in result["candidates"]],["200000.00","36"])
        self.assertEqual(result["candidates"][0]["page"],7)
        self.assertTrue(result["requires_human_review"])
        self.assertIn("monthly_payment",result["missing_fields"])
    def test_no_invented_evidence_or_values(self):
        text="Аванс 200000 руб. Скидка 10 %. Корректировка -300."
        rows=[
            {"field":"advance","value":"100000","evidence":"Аванс 100000 руб."},
            {"field":"advance","value":"100000","evidence":"Аванс 200000 руб."},
            {"field":"buyout","value":"10","evidence":"Скидка 10 %."},
            {"field":"other_costs","value":"300","evidence":"Корректировка -300."},
        ]
        out=validate_candidates(text,{"candidates":rows},1)
        self.assertEqual(out["candidates"],[])
        self.assertEqual(out["rejected_candidates"],4)
    def test_grouped_percent_and_signed_amounts_not_reinterpreted(self):
        text="Скидка 10 000 %. Корректировка -200 000. Итог + 300 000."
        rows=[
            {"field":"advance","value":"10000","evidence":"Скидка 10 000 %."},
            {"field":"advance","value":"10","evidence":"Скидка 10 000 %."},
            {"field":"advance","value":"200000","evidence":"Корректировка -200 000."},
            {"field":"advance","value":"0","evidence":"Корректировка -200 000."},
            {"field":"advance","value":"300000","evidence":"Итог + 300 000."},
        ]
        self.assertEqual(validate_candidates(text,{"candidates":rows},1)["candidates"],[])

    def test_conflicting_candidates_removed(self):
        out=validate_candidates("Аванс 200000. Аванс 300000.",{"candidates":[
            {"field":"advance","value":"200000","evidence":"Аванс 200000"},
            {"field":"advance","value":"300000","evidence":"Аванс 300000"},
        ]},1)
        self.assertEqual(out["conflicting_fields"],["advance"])
        self.assertEqual(out["candidates"],[])
    def test_invalid_numeric_values(self):
        for value in ("NaN","1e6","-1","100.001","100%","0.0001","1 USD"):
            with self.subTest(value=value),self.assertRaises(ValueError):
                number(value,"advance")
        with self.assertRaises(ValueError):
            number("8","term_months")
    def test_shape_and_limits(self):
        with self.assertRaises(ValueError): validate_candidates("x",{"other":[]},1)
        with self.assertRaises(ValueError): validate_candidates("x",{"candidates":[]},0)
        with self.assertRaises(ValueError): validate_candidates("x"*12001,{"candidates":[]},1)

if __name__=="__main__":
    unittest.main()
