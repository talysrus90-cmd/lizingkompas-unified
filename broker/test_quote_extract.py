import unittest
from broker.quote_extract import extract_quote
from broker.document_import import extract_document

class QuoteExtractionTests(unittest.TestCase):
    def test_explicit_russian_terms_and_source(self):
        doc=extract_document("Стоимость имущества: 1 000 000 руб.\nАванс: 200 000,50 ₽\nСрок лизинга: 36 месяцев\nРазовая комиссия: 0 RUB".encode(),".txt")
        r=extract_quote(doc)
        by={x["field"]:x for x in r["candidates"]}
        self.assertEqual(by["asset_price"]["value"],"1000000.00")
        self.assertEqual(by["advance"]["value"],"200000.50")
        self.assertEqual(by["advance"]["location"],{"line":2})
        self.assertEqual(by["advance"]["evidence"],"Аванс: 200 000,50 ₽")
        self.assertEqual(by["term_months"]["value"],"36")
        self.assertEqual(by["upfront_fee"]["value"],"0.00")
        self.assertIn("insurance_total",r["missing_fields"])
        self.assertTrue(r["requires_human_review"])
    def test_ambiguous_values_are_not_guessed(self):
        doc=extract_document("Аванс: 20 %\nВыкупной платеж: 1 USD\nСрок лизинга: 3 года\nЕжемесячный платеж: 30 000–40 000 руб.\nРазовая комиссия: -100 руб.".encode(),".txt")
        self.assertEqual(extract_quote(doc)["candidates"],[])
    def test_conflicts_and_hidden_cells(self):
        doc=extract_document("Аванс: 100 RUB\nАванс: 200 RUB".encode(),".txt")
        doc["blocks"].append({"location":{"sheet":"x","row":1,"column":1},"text":"Выкупная стоимость: 5 RUB","sheet_hidden":True})
        r=extract_quote(doc)
        self.assertEqual(r["candidates"],[])
        self.assertEqual(r["conflicting_fields"],["advance"])
