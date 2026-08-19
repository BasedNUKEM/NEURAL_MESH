import json, httpx, sys, time
sys.path.insert(0, '.')
import bench.longmemeval_harness as H

key, base = H._nous_credentials()
url = base.rstrip('/') + '/chat/completions'

d = json.load(open('data/longmemeval_oracle.json'))
cases = d if isinstance(d, list) else d.get('data') or d.get('cases') or []
c = cases[0]
q = c.get('question', '')
gold = c.get('gold_answer') or c.get('answer', '')
ctx = (gold + ' ') * 10
prompt = (f'Based on the following conversation history, answer the question.\n\n'
          f'CONVERSATION:\n{ctx}\n\nQUESTION: {q}\n\nAnswer concisely in 1-2 sentences.')

for mt in (300, 512):
    empty = 0
    for i in range(6):
        body = {'model': 'deepseek/deepseek-v4-pro-0813',
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': mt, 'temperature': 0}
        r = httpx.post(url, json=body,
                       headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                       timeout=60)
        msg = r.json()['choices'][0]['message']
        content = msg.get('content') or ''
        if not content.strip():
            empty += 1
        time.sleep(1)
    print(f'max_tokens={mt}: {empty}/6 empty')
