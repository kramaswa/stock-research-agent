"""Sync the structured data chips to the card header.

Each card keeps a second copy of its NTM EPS / forward P/E / revenue inside an
info chip, and those copies drift from the header as the card is revised. ORCL
displayed "fwd P/E: 17.5x · Revenue: $90.0B" against a header of 16.81x and a
live revenue of $71.78B.

Targets only chips containing "dp=", which is the signature of the structured
data chip. Prose chips are left alone deliberately: PAYP's "IPO'd at $16.00",
DDOG's "beat $0.58 consensus" and CRWD's text already marked superseded are
legitimate historical statements, not stale current values.
"""
import re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
DRY = '--apply' not in sys.argv
P = r'C:\Users\kisho\projects\stock-research-agent\ranking.html'
h = open(P, encoding='utf-8', newline='').read()
CARD = re.compile(r'\r?\n<!--\s*(\w+)\s*-->\r?\n')
TAG = re.compile(r'<[^>]+>'); WS = re.compile(r'\s+')

# live TTM revenue in $B, where verified today
REV = {'ORCL':71.78,'FICO':2.39,'SMCI':39.06,'AMKR':7.46,'SMTC':1.17,'ALAB':1.20,'DDOG':3.97,
       'NVDA':302.97,'TSM':139.57,'AVGO':145.0,'MU':133.19,'INTU':21.45,'CRM':43.94,'ADBE':25.97,
       'UBER':55.23,'NFLX':48.37,'LYFT':6.77,'VEEV':3.46,'MRVL':9.45,'DLO':1.36,'MKSI':4.35,
       'HPE':41.87,'STX':12.20,'WDC':12.92,'LRCX':23.23,'DELL':151.20,'JBL':35.95,'ADI':13.88,
       'ARW':35.92,'AVT':27.63,'SNX':75.67,'CLS':15.59,'TTMI':3.38,'KLIC':0.95,'SIMO':1.31,
       'IMOS':0.848,'ASX':22.35,'APH':29.01,'FIS':12.20,'TER':4.46,'CIEN':6.02,'DOCN':1.01,
       'NET':2.51,'PLTR':6.16,'SNOW':5.43,'CRWD':5.40,'P':4.26,'PAY':1.36,'DSP':0.3885,
       'BLSH':0.3007,'FN':4.64,'FORM':0.902,'NTAP':7.39,'KEYS':6.58,'PENG':1.73,'VICR':0.474,
       'LIF':0.573,'FLYW':0.714,'DASH':15.89,'NOW':14.73,'NU':8.44,'MELI':35.18,'ISRG':11.03}

st = [(m.group(1), m.start()) for m in CARD.finditer(h)]
edits, report = [], []
for n, (tk, i) in enumerate(st):
    if tk in ('VOO', 'SCHG'):
        continue
    j = st[n+1][1] if n+1 < len(st) else len(h)
    c = h[i:j]
    sm = re.search(r'<div class="price-sub">(.*?)</div>', c, re.S)
    if not sm:
        continue
    sub = sm.group(1)
    pem = re.search(r'fwd P/E\s*~?([\d.]+)×', sub)
    epm = re.search(r'NTM EPS\s*~?\$([\d.,]+)', sub)
    entry = float(pem.group(1)) if pem else None
    heps = float(epm.group(1).replace(',', '')) if epm else None
    bstart = c.find('<div class="chips">')
    if bstart == -1:
        continue
    head, body = c[:bstart], c[bstart:]
    changes = []

    def fix_chip(mo):
        inner = mo.group(2)
        if 'dp=' not in WS.sub(' ', TAG.sub('', inner)):
            return mo.group(0)
        new = inner
        if heps:
            def e(m2):
                old = float(m2.group(2).replace(',', ''))
                if abs(old - heps) / heps <= 0.01:
                    return m2.group(0)
                changes.append("EPS $%s→$%.2f" % (m2.group(2), heps))
                return "%s%.2f" % (m2.group(1), heps)
            new = re.sub(r'(NTM EPS[:\s]*~?\$)([\d.,]+)', e, new)
        if entry:
            def p(m2):
                old = float(m2.group(2))
                if abs(old - entry) / entry <= 0.01:
                    return m2.group(0)
                changes.append("P/E %s→%.2f" % (m2.group(2), entry))
                return "%s%.2f%s" % (m2.group(1), entry, m2.group(3))
            new = re.sub(r'(fwd P/E[:\s]*~?)([\d.]+)(×|x)', p, new)
        if tk in REV:
            def r(m2):
                old = float(m2.group(2).replace(',', ''))
                if abs(old - REV[tk]) / max(REV[tk], 1e-9) <= 0.02:
                    return m2.group(0)
                changes.append("rev $%sB→$%gB" % (m2.group(2), REV[tk]))
                return "%s%g%s" % (m2.group(1), REV[tk], m2.group(3))
            new = re.sub(r'(Revenue[:\s]*~?\$)([\d.,]+)(B)', r, new)
        return mo.group(1) + new + mo.group(3)

    body2 = re.sub(r'(<span class="(?:chip|warn)"[^>]*>)(.*?)(</span>)', fix_chip, body, flags=re.S)
    if changes:
        report.append((tk, changes))
        edits.append((i, j, head + body2))

print("%-6s  %s" % ("TKR", "data-chip figures resynced to the header"))
print("-" * 78)
for tk, ch in report:
    print("%-6s  %s" % (tk, ", ".join(ch[:5])))
print("\n%d cards" % len(report))
if not DRY:
    for i, j, nc in sorted(edits, reverse=True):
        h = h[:i] + nc + h[j:]
    open(P, 'w', encoding='utf-8', newline='').write(h)
    print("APPLIED")
else:
    print("DRY RUN")
