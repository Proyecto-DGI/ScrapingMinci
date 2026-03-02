import requests
from bs4 import BeautifulSoup, Tag
from collections import Counter

url = "https://scienti.minciencias.gov.co/gruplac/jsp/visualiza/visualizagr.jsp"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}

# GIA - COL0005529
resp = requests.get(url, params={"nro": "00000000005529"}, headers=headers, timeout=30)
resp.encoding = resp.apparent_encoding or "latin-1"
soup = BeautifulSoup(resp.text, "html.parser")

# 1. All unique TD classes in the page
all_classes = Counter()
for td in soup.find_all("td"):
    for cls in (td.get("class") or [""]):
        all_classes[cls] += 1
print("=== All TD classes ===")
for cls, cnt in all_classes.most_common():
    print(f"  {cls!r:40} {cnt}")

# 2. Tables with >1 row
print("\n=== Tables with >1 row ===")
body = soup.body
children = [c for c in body.children if isinstance(c, Tag)]
for i, c in enumerate(children):
    if c.name != "table":
        continue
    rows = c.find_all("tr")
    if len(rows) <= 1:
        continue
    print(f"\nTable idx={i}, rows={len(rows)}")
    for j, r in enumerate(rows[:8]):
        cells = r.find_all("td")
        cs = [x.get("class", [""])[0] for x in cells]
        imgs = [img.get("src","")[-18:] for img in r.find_all("img")]
        print(f"  row {j}: cls={cs} imgs={imgs}: {repr(r.get_text(' ',strip=True)[:120])}")
    if len(rows) > 8:
        print(f"  ... {len(rows)-8} more rows")





