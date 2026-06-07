import unittest
from datetime import date

from src.intent_parser import parse_research_task


class IntentParserTests(unittest.TestCase):
    def test_parses_companies_and_three_month_range(self):
        task = parse_research_task("比较英伟达、阿里巴巴和英特尔最近三个月", date(2026, 6, 7))
        self.assertEqual([company.symbol for company in task.companies], ["NVDA", "BABA", "INTC"])
        self.assertEqual(task.time_range.start_date.isoformat(), "2026-03-09")
        self.assertEqual(task.time_range.source, "user_explicit")

    def test_defaults_to_thirty_days(self):
        task = parse_research_task("看看阿里巴巴最近怎么样", date(2026, 6, 7))
        self.assertEqual(task.time_range.start_date.isoformat(), "2026-05-08")
        self.assertTrue(task.defaults_applied)


if __name__ == "__main__":
    unittest.main()
