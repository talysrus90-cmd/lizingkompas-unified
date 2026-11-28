from decimal import Decimal
from datetime import date
import unittest
from broker.payment_schedule import parse_schedule,schedule_total,format_schedule,import_schedule,present_value

class PaymentScheduleTests(unittest.TestCase):
    def test_dated_total_no_double_count(self):
        rows=parse_schedule("2027-01-01;advance;200000\n2027-03-01;lease;30000,50\n2027-04-01;lease;40000\n2027-05-01;buyout;1000")
        self.assertEqual(schedule_total(rows,Decimal("200000")),Decimal("271000.50"))
        self.assertEqual(parse_schedule(format_schedule(rows)),rows)
    def test_reject_bad_dates_amounts_and_duplicates(self):
        for row in ("2027-02-30;lease;1","2027-01-01;lease;-1","2027-01-01;lease;NaN","2027-01-01;lease;1.001","2027-01-01;lease;10%","2027-01-01;lease;0","2027-01-01;lease;1\n2027-01-01;lease;1"):
            with self.subTest(row=row),self.assertRaises(ValueError):
                parse_schedule(row)
    def test_require_advance_match_and_lease_payment(self):
        with self.assertRaises(ValueError):
            schedule_total(parse_schedule("2027-01-01;lease;100"),Decimal("1"))
        with self.assertRaises(ValueError):
            schedule_total(parse_schedule("2027-01-01;advance;100"),Decimal("100"))


    def test_spreadsheet_and_csv_import(self):
        tab="Дата\tВид\tСумма\n01.01.2027\tАванс\t200 000,00\n01.01.2028\tЛизинговый платёж\t110 000,50"
        csv="date;kind;amount\n2027-01-01;advance;200000\n2028-01-01;lease;110000.50"
        self.assertEqual(import_schedule(tab),import_schedule(csv))
        self.assertEqual(schedule_total(import_schedule(tab),Decimal("200000")),Decimal("310000.50"))

    def test_import_rejects_ambiguous_rows(self):
        for text in ("01/02/27;lease;100","2027-01-01;lease;10 00","2027-01-01;lease;=100+10","2027-01-01;unknown;100","2027-01-01;lease;100;extra"):
            with self.subTest(text=text),self.assertRaises(ValueError):
                import_schedule(text)

    def test_present_value_known_one_year_case(self):
        rows=parse_schedule("2027-01-01;advance;200000\n2028-01-01;lease;110000")
        self.assertEqual(present_value(rows,date(2027,1,1),Decimal("10")),Decimal("300000.00"))
        self.assertEqual(present_value(rows,date(2027,1,1),Decimal("0")),Decimal("310000.00"))
        with self.assertRaises(ValueError):
            present_value(rows,date(2027,1,2),Decimal("10"))
        for rate in (Decimal("-1"),Decimal("101"),Decimal("NaN")):
            with self.assertRaises(ValueError):
                present_value(rows,date(2027,1,1),rate)
