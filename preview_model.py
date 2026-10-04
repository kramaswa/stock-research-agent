"""
Local preview of _compute_10yr_model output — no LLM, no cost.
Usage: python preview_model.py CRWD V AAPL
"""
import sys, os, importlib

for path in ['backend/.env', '.env']:
    try:
        for line in open(path):
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        pass

sys.path.insert(0, 'backend')
import agents.hold_check_agent as hca
importlib.reload(hca)
from tools.market_tools import get_all_stock_data


def preview(ticker: str, treasury: float = 5.25):
    raw = get_all_stock_data(ticker)
    r = hca._compute_10yr_model(raw, treasury_yield=treasury, sp_fwd_pe=None)
    p = raw.get('current_price')
    if r is None:
        print(f'\n=== {ticker} @ ${p} ===')
        print('  model returned None — LLM generates all numbers (check eps_growth_5y, revenue_growth_3y, pfcf_share_ttm)')
        return
    d = r.get('dilution_10yr', 1.0)
    print(f'\n=== {ticker} @ ${p} ===')
    print(f'  EPS source : {r.get("eps_source", "?")}')
    print(f'  Anchor     : {r["eps_g5y"]}%  ({r.get("anchor_label","")[:60]})')
    print(f'  revenue_b  : ${r["revenue_b"]}B  dp={r["discount_pp"]}pp  waived={r["disc_waived"]}  capped={r["growth_capped"]}')
    print(f'  Dilution   : {d:.2f}x over 10yr  |  S&P baseline {r["sp_10yr_mult"]}x')
    print()
    print(f'  {"":6} {"Growth":>7}  {"Yr10 EPS":>9}  {"ExitPE":>7}  {"PriceTgt":>9}  {"AdjRet":>8}')
    for label, g, y10eps, xpe in [
        ('Bear', r['bear_g'],  r['yr10_bear'], r.get('exit_pe_bear') or 18),
        ('Base', r['base_g'],  r['yr10_base'], r.get('exit_pe_base') or 30),
        ('Bull', r['bull_g'],  r['yr10_bull'], r.get('exit_pe_bull') or 45),
    ]:
        pt = round(y10eps * xpe, 2)
        ret = round(pt / p * d, 2) if p else '?'
        src = '*' if not r.get(f'exit_pe_{label.lower()}') else ''
        print(f'  {label:<6} {str(g)+"%":>7}  {"$"+str(round(y10eps,2)):>9}  {str(xpe)+"x"+src:>7}  {"$"+str(pt):>9}  {"~"+str(ret)+"x":>8}')
    print('  (* exit P/E = LLM estimate, may vary)')


tickers = sys.argv[1:] if len(sys.argv) > 1 else ['V', 'CRWD']
for t in tickers:
    try:
        preview(t.upper())
    except Exception as e:
        print(f'\n=== {t} === ERROR: {e}')
