import re
LEAD = re.compile(r'^\**\s*([A-Z][A-Z-]+)')
CLOSED = {'DONE', 'CLOSED', 'RULED'}
txt = open('docs/project/tasks-harness2.md').read()
for sec in re.split(r'\n## ', txt):
    rows = [l for l in sec.split('\n') if l.startswith('| TASK-')]
    if not rows:
        continue
    def lead(l):
        m = LEAD.match(l.split('|')[3].strip())
        return m.group(1) if m else '?'
    c = sum(1 for l in rows if lead(l) in CLOSED)
    print(f"{sec.split(chr(10))[0][:40]:42} rows={len(rows):3} closed={c:3} live={len(rows)-c:3}")
