import unittest

from econbiz.guidance import collect_brief


class GuidanceTests(unittest.TestCase):
    def test_unknown_goal_and_field_are_preserved(self):
        answers = iter(['0', '0'])
        messages = []
        b = collect_brief('研究方向', ['x', 'y'], lambda prompt: next(answers), messages.append)
        self.assertEqual(b['goal'], 'undecided')
        self.assertIsNone(b['focus'])
        self.assertTrue(messages)

    def test_description_collects_plain_language_metadata(self):
        answers = iter(['1', '2', '经营风险', '风险指标原值', '比例', '会计年度', '教学数据',
                        '空白为未披露', '只是代理指标', '是'])
        b = collect_brief('研究方向', ['x', 'y'], lambda prompt: next(answers), lambda _: None)
        self.assertEqual(b['focus']['field'], 'y')
        self.assertTrue(b['focus']['confirmed'])
        self.assertIsNone(b['explanatory'])

    def test_unknown_metadata_cannot_be_confirmed(self):
        answers = iter(['1', '1', '经营风险', '', '', '', '', '', '', '是'])
        b = collect_brief('研究方向', ['y'], lambda prompt: next(answers), lambda _: None)
        self.assertFalse(b['focus']['confirmed'])

    def test_invalid_choice_reprompted(self):
        answers = iter(['bad', '9', '1', '99', '0'])
        b = collect_brief('研究方向', ['y'], lambda prompt: next(answers), lambda _: None)
        self.assertEqual(b['goal'], 'description')
        self.assertIsNone(b['focus'])
