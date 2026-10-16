import asyncio
import math
import unittest
from unittest.mock import patch

import app
from market.candles import CandleStore
from trading.trade_manager import TradeManager


class AppFlowTests(unittest.TestCase):
    def test_timeframe_analysis_excludes_active_candle_and_waits_on_stale_feed(self):
        store = CandleStore()
        store.load_candles('1m', [
            {'epoch': index * 60, 'open': 100 + index, 'high': 101 + index, 'low': 99 + index, 'close': 100.5 + index}
            for index in range(31)
        ])
        last_tick = 31 * 60 + 10
        store.add_tick(last_tick, 132.0)

        live_analysis = app.build_timeframe_analysis(store, last_tick, True)
        stale_analysis = app.build_timeframe_analysis(store, last_tick, False)

        self.assertEqual(live_analysis['1m']['candles'], 31)
        self.assertEqual(live_analysis['1m']['timestamp'], 30 * 60)
        self.assertEqual(stale_analysis['1m']['action'], 'WAIT')
        self.assertEqual(stale_analysis['1m']['bias'], 'UNCLEAR')
        self.assertEqual(live_analysis['1m']['confluence']['total_layers'], 5)
        self.assertEqual(stale_analysis['1m']['confluence']['action'], 'WAIT')

    def test_timeframe_analysis_waits_for_long_trend_before_showing_sell(self):
        store = CandleStore()
        closes = [100 + index * 0.1 for index in range(300)]
        closes.extend(
            130 - index * 0.1 + math.sin(index * math.pi / 3) * 0.35
            for index in range(1, 61)
        )
        store.load_candles('1m', [
            {
                'epoch': index * 60,
                'open': close,
                'high': close + 0.25,
                'low': close - 0.25,
                'close': close,
            }
            for index, close in enumerate(closes)
        ])
        last_tick = len(closes) * 60 + 1
        store.add_tick(last_tick, closes[-1])

        result = app.build_timeframe_analysis(store, last_tick, True)['1m']
        from analysis.indicators import indicators
        latest = indicators(store.dataframe('1m').iloc[:-1]).iloc[-1]

        self.assertEqual(result['action'], 'WAIT')
        self.assertNotEqual(result['bias'], 'BEARISH')
        self.assertEqual(result['ema_alignment'], 'MIXED')
        self.assertGreater(latest.close, latest.ema_200)
        self.assertLess(result['confluence']['bearish_votes'], 3)
        self.assertEqual(result['confluence']['action'], 'WAIT')

    def test_timeframe_analysis_does_not_show_buy_during_recent_decline(self):
        store = CandleStore()
        closes = [100 + index * 0.08 for index in range(300)]
        closes.extend(124 + index * 0.08 for index in range(20))
        closes.extend(125.52 - index * 0.05 for index in range(1, 9))
        store.load_candles('1m', [
            {
                'epoch': index * 60,
                'open': close,
                'high': close + 0.08,
                'low': close - 0.08,
                'close': close,
            }
            for index, close in enumerate(closes)
        ])
        last_tick = len(closes) * 60 + 1
        store.add_tick(last_tick, closes[-1])

        result = app.build_timeframe_analysis(store, last_tick, True)['1m']

        self.assertNotEqual(result['action'], 'BUY')
        self.assertEqual(result['action'], 'WAIT')
        self.assertNotEqual(result['bias'], 'BULLISH')
        self.assertLess(result['confluence']['bullish_votes'], 3)
        self.assertEqual(result['confluence']['action'], 'WAIT')

    def test_chart_includes_candle_pattern_and_resolved_backtest_markers(self):
        store = CandleStore()
        candles = []
        for index in range(260):
            close = 100 + index * 0.01 + math.sin(index * 2 * math.pi / 11) * 0.6 + math.sin(index * math.pi / 11) * 0.11
            candles.append({
                'epoch': index * 60,
                'open': close - 0.1,
                'high': close + 0.13 + (index % 3) * 0.01,
                'low': close - 0.14 - (index % 4) * 0.01,
                'close': close,
            })
        candles[-2] = {'epoch': 258 * 60, 'open': 101, 'high': 101.2, 'low': 99.8, 'close': 100}
        candles[-1] = {'epoch': 259 * 60, 'open': 99.7, 'high': 101.6, 'low': 99.5, 'close': 101.4}
        store.load_candles('1m', candles)
        last_tick = 260 * 60 + 1
        store.add_tick(last_tick, 101.5)
        backtest = {
            'trade_markers': [{
                'timestamp': 255 * 60,
                'direction': 'SELL',
                'entry': candles[255]['close'],
                'result': 'WIN',
            }],
        }

        with patch.object(app, 'store', store), patch.dict(app.state, {
            'last_tick': last_tick,
            'connection': 'LIVE',
            'market_id': 'step_index',
            'market_name': 'Step Index',
            'symbol': 'stpRNG',
            'signal': {
                'status': 'ENTRY CONFIRMED',
                'direction': 'BUY',
                'entry': 101.0,
                'stop_loss': 100.0,
                'tp1': 103.0,
                'tp2': 104.0,
            },
            'scalp_signal': {'status': 'NO SCALP SIGNAL'},
            'backtest': backtest,
            'timeframe_analysis': {'1m': {'action': 'SELL'}},
        }):
            chart = asyncio.run(app.api_chart('1m'))

        trace_names = {trace['name'] for trace in chart['data']}
        self.assertIn('Short trend line (20 candles)', trace_names)
        self.assertIn('BUY candle patterns', trace_names)
        self.assertIn('Resolved backtest entries', trace_names)
        self.assertTrue(any('swing' in name.lower() for name in trace_names))
        shape_types = [shape['type'] for shape in chart['layout']['shapes']]
        self.assertIn('rect', shape_types)
        self.assertIn('line', shape_types)
        self.assertEqual(chart['market_id'], 'step_index')
        self.assertEqual(chart['symbol'], 'stpRNG')
        self.assertEqual(chart['timeframe'], '1m')
        self.assertIn('Step Index · 1 MINUTE', chart['layout']['title']['text'])
        annotations = [annotation.get('text', '') for annotation in chart['layout']['annotations']]
        self.assertTrue(any('ENTRY · 101.00' in label for label in annotations))
        self.assertTrue(any('STOP · CLOSE IF WRONG · 100.00' in label for label in annotations))
        self.assertTrue(any('TARGET 1 · 103.00' in label for label in annotations))
        self.assertTrue(any('TARGET 2 · 104.00' in label for label in annotations))

    def test_all_chart_timeframes_hide_old_candles_while_market_switches(self):
        store = CandleStore()
        for timeframe, granularity in app.TIMEFRAMES.items():
            store.load_candles(timeframe, [
                {'epoch': index * granularity, 'open': 100, 'high': 101, 'low': 99, 'close': 100}
                for index in range(3)
            ])

        with patch.object(app, 'store', store), patch.dict(app.state, {
            'connection': 'SWITCHING MARKET',
            'market_id': 'gold',
            'market_name': 'Gold',
            'symbol': 'frxXAUUSD',
        }):
            charts = [asyncio.run(app.api_chart(timeframe)) for timeframe in app.TIMEFRAMES]

        for timeframe, chart in zip(app.TIMEFRAMES, charts):
            with self.subTest(timeframe=timeframe):
                self.assertEqual(chart['data'], [])
                self.assertEqual(chart['market_id'], 'gold')
                self.assertEqual(chart['symbol'], 'frxXAUUSD')
                self.assertEqual(chart['timeframe'], timeframe)
                self.assertIn('Gold · ', chart['layout']['title'])

    def test_backtest_gate_requires_enough_profitable_closed_trades(self):
        self.assertEqual(
            app.backtest_gate_status({'status': 'COMPLETE', 'trades': 0}),
            'BLOCKED · 0/10 TRADES',
        )
        self.assertEqual(
            app.backtest_gate_status({'status': 'COMPLETE', 'trades': 10, 'profit_factor': 1.2, 'net_result': 1, 'validation_trades': 5, 'validation_profit_factor': 1.1, 'validation_net_result': 1}),
            'PASS',
        )
        self.assertEqual(
            app.backtest_gate_status({'status': 'COMPLETE', 'trades': 10, 'profit_factor': 1.2, 'net_result': 1, 'validation_trades': 2, 'validation_profit_factor': 2, 'validation_net_result': 1}),
            'BLOCKED · 2/5 HOLDOUT TRADES',
        )
        self.assertEqual(
            app.backtest_gate_status({'status': 'COMPLETE', 'trades': 10, 'profit_factor': 0.9, 'net_result': -1, 'validation_trades': 5, 'validation_profit_factor': 0.9, 'validation_net_result': -1}),
            'BLOCKED · EXPECTANCY NOT POSITIVE',
        )

    def test_market_switch_is_rejected_while_a_trade_is_active(self):
        from fastapi import HTTPException
        from app import MarketSelection, select_market

        class Feed:
            markets = {'boom_500': {'symbol': 'BOOM500'}}

            @staticmethod
            def request_market(market_id):
                raise AssertionError('Market switching should be blocked')

        with patch.object(app, 'feed', Feed()), patch.object(app.manager, 'active', {'direction': 'BUY'}):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(select_market(MarketSelection(market_id='boom_500')))

        self.assertEqual(error.exception.status_code, 409)

    def test_market_switch_requests_only_an_available_market(self):
        from app import MarketSelection, select_market

        requested = []

        class Feed:
            markets = {'boom_500': {'symbol': 'BOOM500'}}

            @staticmethod
            def request_market(market_id):
                requested.append(market_id)

        with patch.object(app, 'feed', Feed()), \
            patch.object(app, 'store', CandleStore()), \
            patch.object(app.engine, 'symbol', 'stpRNG'), \
            patch.object(app, 'last_saved_signal', None), \
            patch.object(app, 'last_backtest_candle', None), \
            patch.object(app, 'last_saved_candles', {}), \
            patch.object(app.journal, 'entries', []), \
            patch.object(app.manager, 'active', None), \
            patch.dict(app.state, {'symbol': 'stpRNG', 'market_id': 'step_index'}):
            result = asyncio.run(select_market(MarketSelection(market_id='boom_500')))

        self.assertEqual(result['status'], 'SWITCHING')
        self.assertEqual(requested, ['boom_500'])

    def test_market_switch_updates_signal_instrument(self):
        store = CandleStore()
        store.load_candles('1m', [
            {'epoch': 0, 'open': 100, 'high': 101, 'low': 99, 'close': 100},
        ])
        with patch.object(app, 'store', store), \
                patch.object(app.engine, 'symbol', 'stpRNG'), \
                patch.object(app, 'last_saved_signal', None), \
                patch.object(app, 'last_backtest_candle', None), \
                patch.object(app, 'last_saved_candles', {}), \
                patch.object(app.journal, 'entries', []), \
                patch.object(app.manager, 'active', None), \
                patch.dict(app.state, {'symbol': 'stpRNG'}):
            asyncio.run(app.on_symbol('gold', 'frxXAUUSD', 'Gold/USD'))

            self.assertEqual(app.engine.symbol, 'frxXAUUSD')
            self.assertEqual(app.state['symbol'], 'frxXAUUSD')
            self.assertTrue(app.store.dataframe('1m').empty)
            self.assertIsNone(app.store.last_tick)

    def test_backtest_uses_closed_bars_and_recomputes_on_new_bar(self):
        store = CandleStore()
        store.load_candles('5m', [
            {'epoch': index * 300, 'open': 100, 'high': 101, 'low': 99, 'close': 100}
            for index in range(250)
        ])
        store.load_candles('4h', [
            {'epoch': index * 14_400, 'open': 100, 'high': 101, 'low': 99, 'close': 100}
            for index in range(6)
        ])
        backtest_lengths = []
        no_signal = {'status': 'NO TRADE'}

        def record_backtest(*candles, **kwargs):
            backtest_lengths.append((*tuple(len(frame) for frame in candles), len(kwargs['four_hour'])))
            return {'status': 'INSUFFICIENT HISTORICAL DATA', 'trades': 0}

        with patch.object(app, 'store', store), \
                patch.object(app, 'last_backtest_candle', None), \
                patch.object(app, 'last_saved_candles', {}), \
                patch.dict(app.state, {'connection': 'LIVE', 'backtest': {'status': 'WAITING FOR DATA'}}), \
                patch.object(app.engine, 'evaluate', return_value=no_signal), \
                patch.object(app.engine, 'evaluate_scalp') as evaluate_scalp, \
                patch.object(app, 'run_backtest', side_effect=record_backtest), \
                patch.object(app.database, 'save_candles'), \
                patch.object(app.database, 'save_signal'), \
                patch.object(app.manager, 'update', return_value='WAITING'):
            asyncio.run(app.on_tick(249 * 300 + 10, 100.0))
            asyncio.run(app.on_tick(249 * 300 + 11, 100.0))
            self.assertEqual(backtest_lengths, [(0, 249, 0, 0, 5)])

            store.add_tick(250 * 300 + 10, 100.0)
            asyncio.run(app.on_tick(250 * 300 + 10, 100.0))
            self.assertEqual(backtest_lengths, [(0, 249, 0, 0, 5), (0, 250, 0, 0, 5)])
            evaluate_scalp.assert_not_called()

    def test_scalping_is_disabled_in_live_tick_flow(self):
        store = CandleStore()
        candle = {'epoch': 0, 'open': 100, 'high': 101, 'low': 99, 'close': 100}
        store.load_candles('1m', [candle, {**candle, 'epoch': 60}])
        store.load_candles('5m', [candle, {**candle, 'epoch': 300}])

        with patch.object(app, 'store', store), \
                patch.object(app, 'last_backtest_candle', None), \
                patch.object(app, 'last_saved_candles', {}), \
                patch.dict(app.state, {
                    'connection': 'LIVE',
                    'backtest': {'status': 'INSUFFICIENT HISTORICAL DATA', 'trades': 0},
                    'scalp_backtest': {'status': 'DISABLED'},
                }), \
                patch.object(app.engine, 'evaluate', return_value={'status': 'NO TRADE'}), \
                patch.object(app.engine, 'evaluate_scalp') as evaluate_scalp, \
                patch.object(app, 'run_backtest', return_value={'status': 'INSUFFICIENT HISTORICAL DATA', 'trades': 0}), \
                patch.object(app.journal, 'record') as record_signal, \
                patch.object(app.database, 'save_candles'), \
                patch.object(app.database, 'save_signal') as save_signal, \
                patch.object(app.manager, 'update', return_value='WAITING'):
            asyncio.run(app.on_tick(3600, 100.0))

            self.assertEqual(app.state['scalp_signal']['status'], 'SCALPING DISABLED — USE MAIN SIGNAL')
            self.assertIsNone(app.state['scalp_signal']['direction'])
            self.assertEqual(app.state['scalp_backtest']['status'], 'DISABLED')
            evaluate_scalp.assert_not_called()
            record_signal.assert_called_once_with({'status': 'NO TRADE'})
            save_signal.assert_not_called()

    def test_live_entry_is_withheld_without_matching_tradingview_confirmation(self):
        signal = {
            'id': 'entry-test',
            'status': 'ENTRY CONFIRMED',
            'direction': 'BUY',
            'score': 80,
            'setup_timestamp': 1_000,
            'entry': 100.0,
            'stop_loss': 99.0,
            'tp1': 102.0,
            'tp2': 103.0,
            'risk_reward': 2.0,
            'reasons': [],
        }
        manager_signals = []

        with patch.object(app, 'store', CandleStore()), \
                patch.object(app, 'latest_tradingview_alert', None), \
                patch.object(app, 'last_backtest_candle', None), \
                patch.object(app, 'last_saved_candles', {}), \
                patch.dict(app.state, {
                    'connection': 'LIVE',
                    'symbol': 'stpRNG',
                    'backtest': {'status': 'COMPLETE'},
                }), \
                patch.object(app, 'backtest_passes', return_value=True), \
                patch.object(app.engine, 'evaluate', return_value=signal), \
                patch.object(app.journal, 'record') as record_signal, \
                patch.object(app.database, 'save_candles'), \
                patch.object(app.database, 'save_signal'), \
                patch.object(
                    app.manager,
                    'update',
                    side_effect=lambda candidate, _price: manager_signals.append(candidate.copy()) or 'WAITING',
                ):
            asyncio.run(app.on_tick(1_001, 100.0))

        self.assertEqual(manager_signals[0]['status'], 'WAIT — TRADINGVIEW CONFIRMATION REQUIRED')
        self.assertIsNone(manager_signals[0]['direction'])
        self.assertNotIn('entry', manager_signals[0])
        self.assertNotIn('id', manager_signals[0])
        record_signal.assert_called_once_with(manager_signals[0])

    def test_exit_alert_latches_after_trade_manager_resets_and_can_be_acknowledged(self):
        manager = TradeManager()
        manager.active = {
            'id': 'trade-exit-test',
            'direction': 'BUY',
            'entry': 100,
            'stop_loss': 90,
            'tp1': 110,
            'tp2': 120,
        }

        with patch.object(app, 'store', CandleStore()), \
                patch.object(app, 'manager', manager), \
                patch.dict(app.state, {'connection': 'LIVE', 'exit_alert': None}), \
                patch.object(app.engine, 'evaluate', return_value={'status': 'NO TRADE'}), \
                patch.object(app.engine, 'evaluate_scalp') as evaluate_scalp:
            asyncio.run(app.on_tick(2_000, 111))
            evaluate_scalp.assert_not_called()
            alert = app.state['exit_alert'].copy()
            self.assertEqual(alert['status'], 'TARGET 1 HIT')

            asyncio.run(app.on_tick(2_001, 111))
            self.assertEqual(app.state['trade_status'], 'WAITING')
            self.assertEqual(app.state['exit_alert'], alert)

            acknowledged = asyncio.run(app.acknowledge_exit_alert(
                app.ExitAlertAcknowledgement(id=alert['id'])
            ))
            self.assertTrue(acknowledged['acknowledged'])
            self.assertIsNone(app.state['exit_alert'])


if __name__ == '__main__':
    unittest.main()