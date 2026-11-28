from decimal import Decimal
import unittest
from broker.payment_schedule import parse_schedule,schedule_total,format_schedule

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
