import unittest
from unittest.mock import patch

import app
from analysis.signal_journal import SignalJournal


class SignalHistoryTests(unittest.TestCase):
    def test_history_contains_only_recent_explicitly_confirmed_entries(self):
        now = 2_000_000_000

        def entry(identifier, timestamp, status, direction='BUY', price=100.0):
            return {
                'id': identifier,
                'timestamp': timestamp,
                'symbol': '1HZ100V',
                'direction': direction,
                'entry': price,
                'outcome': status,
                'confidence': 90,
                'reason': '[]',
            }

        journal_entries = [
            entry('main-new', now - 60, 'ENTRY CONFIRMED'),
            entry('old', now - app.HISTORY_MAX_AGE_SECONDS - 1, 'ENTRY CONFIRMED'),
            entry('provisional', now - 30, 'SETUP FORMING'),
            entry('future', now + 1, 'ENTRY CONFIRMED'),
        ]
        database_entries = [
            entry('scalp-new', now - 120, 'SCALP ENTRY CONFIRMED', direction='SELL'),
            entry('legacy-unconfirmed', now - 90, None),
        ]

        with patch.object(app.time, 'time', return_value=now), \
                patch.object(app.journal, 'recent', return_value=journal_entries), \
                patch.object(app.database, 'recent_signals', return_value=database_entries) as recent_signals:
            result = app.build_history()

        self.assertEqual({item['id'] for item in result}, {'main-new'})
        self.assertTrue(all(item['confirmed'] for item in result))
        recent_signals.assert_called_once_with(limit=20, since=now - app.HISTORY_MAX_AGE_SECONDS)

    def test_journal_rejects_nonconfirmed_entries(self):
        self.assertFalse(SignalJournal.is_signal({
            'status': 'SETUP FORMING',
            'direction': 'BUY',
            'entry': 100,
        }))
        self.assertTrue(SignalJournal.is_signal({
            'status': 'SCALP ENTRY CONFIRMED',
            'direction': 'SELL',
            'entry': 100,
        }))

    def test_hourly_view_can_load_all_retained_history(self):
        now = 2_000_000_000
        with patch.object(app.time, 'time', return_value=now), \
                patch.object(app.journal, 'recent', return_value=[]), \
                patch.object(app.database, 'recent_signals', return_value=[]) as recent_signals:
            self.assertEqual(app.build_history(limit=app.HISTORY_DETAIL_LIMIT), [])

        recent_signals.assert_called_once_with(
            limit=app.HISTORY_DETAIL_LIMIT,
            since=now - app.HISTORY_MAX_AGE_SECONDS,
        )

    def test_history_is_filtered_to_selected_instrument(self):
        now = 2_000_000_000
        step_entry = {
            'id': 'step-signal', 'timestamp': now - 60, 'symbol': 'stpRNG',
            'direction': 'BUY', 'entry': 100, 'outcome': 'ENTRY CONFIRMED',
        }
        boom_entry = {
            'id': 'boom-signal', 'timestamp': now - 30, 'symbol': 'BOOM500',
            'direction': 'SELL', 'entry': 200, 'outcome': 'ENTRY CONFIRMED',
        }

        with patch.object(app.time, 'time', return_value=now), \
                patch.object(app.journal, 'recent', return_value=[]), \
                patch.object(app.database, 'recent_signals', return_value=[step_entry, boom_entry]):
            result = app.build_history(symbol='BOOM500')

        self.assertEqual([entry['id'] for entry in result], ['boom-signal'])


if __name__ == '__main__':
    unittest.main()