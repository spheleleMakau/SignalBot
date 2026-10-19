import tempfile
import unittest
import asyncio
from pathlib import Path
from unittest.mock import patch

import app
from data.database import Database
from learning.course import (
    LESSONS,
    build_exercise,
    build_review,
    explain_signal,
    public_curriculum,
)


def historical_candles(count=250):
    candles = []
    for index in range(count):
        close = 100 + index * 0.02
        candles.append({
            'timestamp': index * 60,
            'open': close - 0.01,
            'high': close + 0.04,
            'low': close - 0.04,
            'close': close,
            'volume': 0,
        })
    return candles


class LearningCourseTests(unittest.TestCase):
    def test_course_has_short_rule_linked_lessons_and_searchable_glossary_terms(self):
        course = public_curriculum({})

        self.assertGreaterEqual(len(course['lessons']), 6)
        self.assertTrue(all(lesson['rule'] for lesson in course['lessons']))
        self.assertTrue(any(term['term'] == 'RSI' for term in course['glossary']))
        self.assertTrue(any(term['term'] == 'Expiry' for term in course['glossary']))

    def test_exercise_only_returns_candles_available_at_decision_point(self):
        candles = historical_candles(250)

        exercise = build_exercise('one-minute-trigger', candles, 1, 'stpRNG')

        self.assertIsNotNone(exercise)
        self.assertLess(exercise['observed_candles'][-1]['timestamp'], exercise['decision_timestamp'])
        self.assertEqual(exercise['observed_candles'][-1]['timestamp'] + 60, exercise['decision_timestamp'])
        self.assertEqual(len(exercise['observed_candles']), 90)
        self.assertIn('ema_200', exercise['features']['indicators'])
        self.assertTrue(all(
            candle['timestamp'] < exercise['decision_timestamp']
            for candle in exercise['observed_candles']
        ))

    def test_exercise_is_unavailable_without_indicator_warmup_and_future_bar(self):
        self.assertIsNone(build_exercise('read-structure', historical_candles(221), 1, 'stpRNG'))
        with self.assertRaisesRegex(ValueError, 'Unknown lesson'):
            build_exercise('not-a-lesson', historical_candles(), 1, 'stpRNG')

    def test_review_reveals_later_candles_but_never_fabricates_contract_settlement(self):
        exercise = build_exercise('contract-expiry', historical_candles(), 1, 'stpRNG')
        future = [{
            'timestamp': exercise['decision_timestamp'],
            'open': 105.0,
            'high': 105.2,
            'low': 104.8,
            'close': 105.1,
        }]

        review = build_review(exercise, 'LONG', future)

        self.assertEqual(review['subsequent_candles'], future)
        self.assertEqual(review['directional_candle_context'], 'UP')
        self.assertEqual(review['contract_result']['outcome'], 'INCOMPLETE')
        self.assertIsNone(review['contract_result']['entry_quote'])
        self.assertIsNone(review['contract_result']['expiry_quote'])
        with self.assertRaisesRegex(ValueError, 'Decision must'):
            build_review(exercise, 'BUY', future)

    def test_signal_explanation_uses_only_recorded_evidence_and_bias(self):
        result = explain_signal({
            'status': 'WAIT — TIMEFRAMES NOT ALIGNED',
            'direction': None,
            'reasons': ['Current readings: 4H BEARISH · 1M BULLISH.'],
            'timeframes': {
                '4h': {'available': True, 'bias': 'BEARISH'},
                '1m': {'available': True, 'bias': 'BULLISH'},
            },
            'indicators': {'rsi_14': 58.0},
        })

        self.assertEqual(result['evidence'], ['Current readings: 4H BEARISH · 1M BULLISH.'])
        self.assertFalse(result['contradictions'])
        self.assertTrue(any('required completed-timeframe' in item for item in result['waiting_for']))
        self.assertEqual(result['indicators'], {'rsi_14': 58.0})
        self.assertNotIn('probability', result)

    def test_progress_and_attempt_review_are_persisted_once(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(str(Path(directory) / 'learning.db'))
            exercise = build_exercise('read-structure', historical_candles(), 1, 'stpRNG')
            database.create_learning_attempt(
                'attempt-1',
                'read-structure',
                'stpRNG',
                exercise['decision_timestamp'],
                exercise,
                100,
            )
            saved = database.learning_attempt('attempt-1')
            review = build_review(exercise, 'WAIT', [])

            self.assertTrue(database.complete_learning_attempt('attempt-1', 'WAIT', review, 101))
            self.assertFalse(database.complete_learning_attempt('attempt-1', 'LONG', review, 102))
            progress = database.learning_progress()
            completed = database.learning_attempt('attempt-1')

        self.assertEqual(progress['read-structure']['completion_count'], 1)
        self.assertEqual(completed['decision'], 'WAIT')
        self.assertEqual(completed['review']['contract_result']['outcome'], 'INCOMPLETE')
        self.assertEqual(saved['snapshot']['lesson']['id'], 'read-structure')

    def test_database_returns_learning_candles_in_time_order(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(str(Path(directory) / 'learning.db'))
            rows = historical_candles(4)
            database.save_candles('stpRNG', '1m', rows[::-1])

            saved = database.learning_candles('stpRNG', '1m', limit=3)

        self.assertEqual([row['timestamp'] for row in saved], [60, 120, 180])
        self.assertEqual(len(LESSONS), public_curriculum({})['total_lessons'])

    def test_learning_api_hides_future_until_answer_and_persists_review(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(str(Path(directory) / 'learning.db'))
            database.save_candles('stpRNG', '1m', historical_candles(250))
            with patch.object(app, 'database', database), patch.dict(app.state, {
                'market_id': 'step_index',
                'symbol': 'stpRNG',
            }):
                exercise = asyncio.run(app.start_learning_attempt(
                    app.LearningExerciseRequest(lesson_id='contract-expiry')
                ))
                self.assertNotIn('subsequent_candles', exercise)
                self.assertLess(
                    exercise['observed_candles'][-1]['timestamp'],
                    exercise['decision_timestamp'],
                )
                answer = app.LearningAnswerRequest(
                    attempt_id=exercise['attempt_id'],
                    decision='WAIT',
                )
                first_review = asyncio.run(app.submit_learning_answer(answer))
                repeated_review = asyncio.run(app.submit_learning_answer(answer))
                progress = asyncio.run(app.learning_course())

        self.assertEqual(first_review, repeated_review)
        self.assertEqual(first_review['review']['contract_result']['outcome'], 'INCOMPLETE')
        self.assertEqual(progress['completed_lessons'], 1)

    def test_learning_exercise_requires_step_index_market(self):
        with patch.dict(app.state, {'market_id': 'gold', 'symbol': 'frxXAUUSD'}):
            with self.assertRaises(app.HTTPException) as error:
                asyncio.run(app.start_learning_attempt(
                    app.LearningExerciseRequest(lesson_id='read-structure')
                ))

        self.assertEqual(error.exception.status_code, 409)


if __name__ == '__main__':
    unittest.main()
