"""Replay January-August with a rolling twelve-calendar-month price context."""
import argparse
import calendar
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
from historical_price_service import fetch_price_history_for_range
from stock_walkforward_validator import run_stock_validation


def summarize(output):
    report = json.loads(Path(output).read_text(encoding='utf-8'))
    rows = report['runs']
    lines = [f"# January-August {report['year']} stock prediction backtest", '',
             'Each prediction receives the previous 12 calendar months of daily prices. '
             'Returns run from the preceding month-end close to the target month-end close, '
             'using the last trading day on or before each date. Returns exclude costs and dividends.', '',
             'These are retrospective predictions using the current model and current code. '
             'Price inputs are time-filtered, but this does not establish that the model and its '
             'training or development history were free of knowledge of these outcomes.', '',
             '| Stock | Month | Predicted return | Actual return | Direction correct |',
             '|---|---|---:|---:|:---:|']
    for row in rows:
        if row['status'] != 'SUCCESS':
            lines.append(f"| {row['symbol']} | {row['month']} | No usable forecast | — | — |")
            continue
        predicted = row['prediction']['predicted_return_pct']
        actual = row['validation']['actual_return_pct']
        match = (predicted > 0) == (actual > 0) if predicted and actual else predicted == actual
        lines.append(f"| {row['symbol']} | {row['month']} | {predicted:+.2f}% | {actual:+.2f}% | {'Yes' if match else 'No'} |")
    lines += ['', '| Stock | Successful runs | Direction accuracy | Mean absolute return error | Decision agreement |',
              '|---|---:|---:|---:|---:|']
    for symbol in sorted({r['symbol'] for r in rows}) + ['ALL']:
        valid = [r for r in rows if r['status'] == 'SUCCESS' and (symbol == 'ALL' or r['symbol'] == symbol)]
        n = len(valid)
        if not n:
            continue
        correct = sum((r['prediction']['predicted_return_pct'] > 0) == (r['validation']['actual_return_pct'] > 0)
                      if r['prediction']['predicted_return_pct'] and r['validation']['actual_return_pct']
                      else r['prediction']['predicted_return_pct'] == r['validation']['actual_return_pct'] for r in valid)
        error = sum(abs(r['prediction']['predicted_return_pct'] - r['validation']['actual_return_pct']) for r in valid) / n
        decisions = sum(r['prediction']['decision'] == r['validation']['actual_decision'] for r in valid)
        lines.append(f'| {symbol} | {n} | {correct}/{n} ({correct/n:.1%}) | {error:.2f} percentage points | {decisions}/{n} ({decisions/n:.1%}) |')
    lines += ['', 'Direction accuracy compares the sign of returns. Decision agreement compares the '
              "project's BUY/HOLD/SELL labels. The small sample does not establish future predictive performance.", '']
    for row in rows:
        if row['status'] != 'SUCCESS':
            reason = row.get('error') or row.get('prediction', {}).get('error') or row.get('validation', {}).get('error')
            lines.append(f"- {row['symbol']} {row['month']}: {reason}")
    destination = Path(output).with_suffix('.md')
    destination.write_text('\n'.join(lines), encoding='utf-8')
    return destination


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--year', type=int, default=2026)
    parser.add_argument('--symbols', default='SPY,TSLA')
    args = parser.parse_args()
    use_gemini = os.getenv('AI_PROVIDER', 'gemini').lower() == 'gemini' and bool(
        os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY'))
    if use_gemini:
        from gemini_stock_prediction_agent import run_gemini_stock_prediction as predict
    else:
        from stock_prediction_agent import run_stock_prediction as predict
    output = ROOT / 'data' / f'calendar_backtest_{args.year}_jan_aug.json'
    report = {'year': args.year, 'provider': 'gemini' if use_gemini else 'baseline',
              'method': 'Previous 12 calendar months; forecast prior month close to target month close.',
              'runs': []}
    for symbol in args.symbols.upper().split(','):
        symbol = symbol.strip()
        print(f'Fetching {symbol} history', flush=True)
        history, error, coverage = fetch_price_history_for_range(
            symbol, f'{args.year-1}-01-01', f'{args.year}-08-31')
        for month in range(1, 9):
            start = date(args.year - 1, month, 1)
            origin = date(args.year, month, 1) - timedelta(days=1)
            target = date(args.year, month, calendar.monthrange(args.year, month)[1])
            row = {'symbol': symbol, 'month': f'{args.year}-{month:02}',
                   'context_start': str(start), 'origin': str(origin), 'target': str(target),
                   'coverage': coverage}
            try:
                if target >= date.today():
                    raise ValueError('Target month is not yet complete')
                context = [b for b in history if str(start) <= b['date'] <= str(origin)]
                actual = [b for b in history if b['date'] <= str(target)]
                if not context:
                    raise ValueError(error or 'No context data')
                if (date.fromisoformat(context[0]['date']) - start).days > 7:
                    raise ValueError('Incomplete twelve-month context')
                if len(context) < 230:
                    raise ValueError('Too few daily bars for twelve-month context')
                if (origin - date.fromisoformat(context[-1]['date'])).days > 5:
                    raise ValueError('Missing origin data')
                if not actual or (target - date.fromisoformat(actual[-1]['date'])).days > 5:
                    raise ValueError('Missing target data')
                spi = {'symbol': symbol, 'historical_context_start_date': str(start),
                       'prediction_origin_date': str(origin), 'target_date': str(target),
                       'decision_horizon_days': (target-origin).days, 'initial_capital': 50000,
                       'benchmark': 'SPY', 'validation_mode': 'horizon_days', 'price_basis': 'close'}
                row.update(bars=len(context), first_bar=context[0]['date'], last_bar=context[-1]['date'])
                print(f"Predicting {symbol} {row['month']} ({len(context)} context bars)", flush=True)
                prediction = predict(spi, context)
                row['prediction'] = prediction
                validation = run_stock_validation(spi, prediction, actual)
                row['validation'] = validation
                row['status'] = validation['status']
                print(f"{row['status']}: predicted={prediction.get('predicted_return_pct')} actual={validation.get('actual_return_pct')}", flush=True)
            except Exception as exc:
                row.update(status='FAILED', error=str(exc))
                print(f"FAILED {symbol} {row['month']}: {exc}", flush=True)
            report['runs'].append(row)
            output.write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
    print(f'Results: {output}', flush=True)
    print(f'Summary: {summarize(output)}', flush=True)


if __name__ == '__main__':
    main()
