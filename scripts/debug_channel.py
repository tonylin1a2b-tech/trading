import requests, re
r = requests.get(
    'https://www.youtube.com/@macromicrom2843',
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
    timeout=15
)
patterns = [
    r'"channelId":"(UC[^"]+)"',
    r'"externalId":"(UC[^"]+)"',
    r'channel_id=(UC[^&"]+)',
]
for pat in patterns:
    m = re.search(pat, r.text)
    if m:
        print('Found:', m.group(1))
        break
else:
    print('Not found, status:', r.status_code)
    idx = r.text.find('"UC')
    if idx > 0:
        print('Sample:', r.text[idx:idx+50])
