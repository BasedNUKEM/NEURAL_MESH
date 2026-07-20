import re, json, os

raw = open('/opt/data/cache/web/raw.githubusercontent.com-3c5233ba0c.md', encoding='utf-8').read()
# The cached markdown has double-escaped quotes (\\" and \\\\). Convert to valid JSON text.
unescaped = raw.replace('\\\\"', '"').replace('\\\\\\\\', '\\')
start = unescaped.find('"session_1_summary"')
end = unescaped.find('"sample_id"')
block = unescaped[start:end]
summaries = re.findall(r'"(session_\d+_summary)":\s*"([^"]*)"', block)
print('session summaries found:', len(summaries))
os.makedirs('/opt/data/NEURAL_MESH/bench/fixtures', exist_ok=True)
with open('/opt/data/NEURAL_MESH/bench/fixtures/locomo_conv50_summaries.json', 'w') as fh:
    json.dump([{"session": k, "summary": v} for k, v in summaries], fh, indent=2)
print('wrote', len(summaries), 'summaries')
for k, v in summaries[:6]:
    print(k, '->', v[:80])
