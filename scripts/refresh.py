"""Public-source refresh for API Competitor Research. Runs on GitHub Actions."""
import io, json, re, time, sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlsplit, urlunsplit, quote
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
from pypdf import PdfReader
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
TODAY = datetime.now(ZoneInfo("Asia/Manila")).date().isoformat()
STAMP = datetime.now(ZoneInfo("Asia/Manila")).isoformat(timespec="seconds")
START = "2026-06-01"
DATA = ROOT / "research-data.json"
AGENT = "APICompetitorResearch/1.0 (+https://github.com/Franje-smats/api-competitor-research)"
db = json.loads(DATA.read_text(encoding="utf-8-sig"))
rows = db["records"]
statuses = []
def canonical(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc.removeprefix("www."), p.path.rstrip("/"), "", ""))
index = {(r["competitor"], r["type"], canonical(r["url"])): r for r in rows}
new_count = 0
def fetch(url):
    time.sleep(0.35)
    last = None
    for attempt in range(2):
        try:
            with urlopen(Request(url, headers={"User-Agent": AGENT}), timeout=25) as response:
                body = response.read(6_000_001)
                if len(body) > 6_000_000:
                    raise ValueError("Source exceeds 6 MB limit")
                return body
        except Exception as exc:
            last = exc
            if attempt == 0:
                time.sleep(2)
    raise last
def page(url):
    return BeautifulSoup(fetch(url), "html.parser")
def date_value(text):
    if not text:
        return None
    text = re.sub(r"\s+", " ", text.strip().replace(",", ""))
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%B %d %Y", "%b %d %Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return None
def add(brand, title, url, date=None, kind="Article", basis="Publisher archive", category="", source="Owned", summary=""):
    global new_count
    if not title or not url or urlsplit(url).scheme not in ("https", "http"):
        return
    if date and not START <= date <= TODAY:
        return
    key = (brand, kind, canonical(url))
    if key in index:
        old = index[key]
        if date:
            old.update(date=date, dateBasis=basis, dateStatus="Verified")
        old.update(title=title.strip(), checked=TODAY)
        return
    item = dict(competitor=brand, type=kind, title=title.strip(), url=url, date=date,
                dateStatus="Verified" if date else "Unverified", dateBasis=basis,
                category=category, sourceType=source, summary=summary, opportunity="",
                reviewStatus="Metadata only", checked=TODAY)
    rows.append(item)
    index[key] = item
    new_count += 1
def known(brand, url, kind="Article"):
    return (brand, kind, canonical(url)) in index
def run(brand, fn):
    before = new_count
    try:
        observed = fn()
        if not observed:
            raise ValueError("No dated source entries found; layout may have changed")
        statuses.append(dict(source=brand, status="ok", observed=observed, added=new_count-before))
    except Exception as exc:
        # Keep previous records when a source fails; never treat a failed request as an empty archive.
        statuses.append(dict(source=brand, status="error", error=str(exc)[:220], added=new_count-before))
def spi():
    observed = 0
    for n in (0, 10, 20):
        url = "https://www.smartpropertyinvestment.com.au/news" + (f"?start={n}" if n else "")
        soup = page(url)
        for a in soup.select("#articles-container > a"):
            title = a.get("aria-label", "")
            m = re.search(r"\b\d{1,2}\s+[A-Z]{3}\s+\d{4}\b", a.get_text(" ", strip=True))
            d = date_value(m[0]) if m else None
            if d:
                observed += 1
                add("Smart Property Investment", title, urljoin(url, a["href"]), d)
    return observed
def yip():
    observed, candidates = 0, {}
    for n in (1, 2):
        url = "https://www.yourinvestmentpropertymag.com.au/news/" + (f"?p={n}" if n > 1 else "")
        for a in page(url).select("a.article-list-item, a.highlighted-article-list-item"):
            title = a.find(["h2", "h3"])
            if title:
                candidates[urljoin(url, a["href"])] = title.get_text(" ", strip=True)
    if candidates:
        observed = len(candidates)
    failures = 0
    for url, title in candidates.items():
        if known("Your Investment Property", url):
            continue
        try:
            text = page(url).get_text(" ", strip=True)
            m = re.search(r"Published\s+(\d{1,2}\s+[A-Za-z]+,?\s+\d{4})", text)
            add("Your Investment Property", title, url, date_value(m[1]) if m else None, basis="Publisher article")
        except Exception:
            failures += 1
    if failures:
        raise RuntimeError(f"{failures} new article pages could not be verified; previous data retained")
    return observed
def property_update():
    observed = 0
    for section in ("news-and-features", "property-investment", "personal-finance", "property-development"):
        for n in (1, 2):
            url = f"https://propertyupdate.com.au/category/{section}/" + (f"page/{n}/" if n > 1 else "")
            soup = page(url)
            for article in soup.select('article[id^="post-"]'):
                a, t = article.select_one(".podcast-top-title a"), article.find("time")
                if a and t:
                    d = date_value(t.get("datetime", "")[:10] or t.get_text(" ", strip=True))
                    if d:
                        observed += 1
                        add("Property Update", a.get_text(" ", strip=True), a["href"], d,
                            category=section.replace("-", " "))
    return observed
def domain():
    observed = 0
    soup = page("https://www.domain.com.au/research/")
    for card in soup.select('[data-testid="article-card-content"]'):
        heading, t = card.find("h3"), card.find("time")
        if heading and t and heading.find_parent("a"):
            d = date_value(t.get_text(" ", strip=True))
            if d:
                observed += 1
                add("Domain", heading.get_text(" ", strip=True), heading.find_parent("a")["href"], d, category="Research")
    return observed
def rea():
    candidates = {}
    for n in (1, 2):
        url = "https://www.realestate.com.au/insights/" + (f"page/{n}/" if n > 1 else "")
        for a in page(url).select("a[title][href]"):
            link = urljoin(url, a["href"])
            if re.search(r"/(?:insights|news)/[^/]+/$", link):
                candidates[link] = a["title"].removeprefix("Read about ")
    failures = 0
    for url, title in candidates.items():
        if known("realestate.com.au", url):
            continue
        try:
            text = page(url).get_text(" ", strip=True)
            m = re.search(r"First published\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})", text, re.I)
            add("realestate.com.au", title, url, date_value(m[1]) if m else None, basis="Publisher article", category="Insights")
        except Exception:
            failures += 1
    if failures:
        raise RuntimeError(f"{failures} article pages unavailable; previous data retained")
    return len(candidates)
def sqm():
    observed = 0
    url = "https://sqmresearch.com.au/property/newsletter-archive"
    for heading in page(url).find_all("h6"):
        container = heading.parent.parent
        a, span = container.find("a"), heading.parent.find("span")
        if a and span:
            d = date_value(span.get_text(" ", strip=True))
            if d and START <= d <= TODAY:
                observed += 1
                add("SQM Research", heading.get_text(" ", strip=True), urljoin(url, a["href"]), d,
                    kind="Activity", basis="Publisher newsletter archive", category="Newsletter", source="Owned · Newsletter")
    url = "https://sqmresearch.com.au/media"
    soup = page(url)
    year = next((h for h in soup.find_all("h4") if h.get_text(strip=True) == TODAY[:4]), None)
    if year:
        for node in year.find_all_next(["h4", "a"]):
            if node.name == "h4":
                break
            link = urljoin(url, node.get("href", ""))
            match = re.search(r"/uploads/(\d{2}-\d{2}-\d{2})-", link)
            if not match or known("SQM Research", link):
                continue
            candidate = datetime.strptime(match[1], "%d-%m-%y").date().isoformat()
            if not START <= candidate <= TODAY:
                continue
            try:
                reader = PdfReader(io.BytesIO(fetch(link)))
                text = reader.pages[0].extract_text() or ""
                m = re.search(r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b", text)
                d = date_value(m[0]) if m else None
                # Conflicting printed and filename dates remain outside the verified timeline.
                if d != candidate:
                    d = None
                add("SQM Research", node.get_text(" ", strip=True), link, d,
                    basis="Publisher PDF release date" if d else "PDF date conflicts with filename or could not be verified",
                    category="Research release")
            except Exception:
                add("SQM Research", node.get_text(" ", strip=True), link, None,
                    basis="Release linked in publisher media archive; PDF date unavailable", category="Research release")
    return observed
def public_mentions():
    observed = 0
    for brand in ("Smart Property Investment", "Your Investment Property", "Property Update", "Domain", "realestate.com.au", "SQM Research"):
        term = brand if brand not in ("Domain", "Property Update") else brand + " property Australia"
        query = quote('"' + term + '" when:7d')
        url = "https://news.google.com/rss/search?q=" + query + "&hl=en-AU&gl=AU&ceid=AU:en"
        root = ET.fromstring(fetch(url))
        for item in root.findall(".//item"):
            title, link = item.findtext("title", ""), item.findtext("link", "")
            description = BeautifulSoup(item.findtext("description", ""), "html.parser").get_text(" ", strip=True)
            if brand.casefold() not in (title + " " + description).casefold():
                continue
            try:
                d = parsedate_to_datetime(item.findtext("pubDate", "")).date().isoformat()
            except Exception:
                d = None
            observed += 1
            add(brand, title, link, d, kind="Mention", basis="News index timestamp; original page date not verified",
                source="Indexed news · Needs review",
                summary="Public news-index discovery. Relevance and original publication date require review; this is not a verified independent mention.")
            # An index timestamp is not an original publication date.
            entry = index.get((brand, "Mention", canonical(link)))
            if entry:
                entry["indexDate"] = d
                entry["date"] = None
                entry["dateStatus"] = "Unverified"
    return observed or 1
for brand, fn in [("Smart Property Investment", spi), ("Your Investment Property", yip),
                  ("Property Update", property_update), ("Domain", domain),
                  ("realestate.com.au", rea), ("SQM Research", sqm), ("Public news discovery", public_mentions)]:
    run(brand, fn)
rows.sort(key=lambda r: r.get("date") or "", reverse=True)
for n, r in enumerate(rows, 1):
    r["id"] = n
verified = [r for r in rows if r["type"] != "Opportunity" and r.get("dateStatus") == "Verified" and r.get("date") and START <= r["date"] <= TODAY]
months = []
cursor = datetime.strptime(START, "%Y-%m-%d").date().replace(day=1)
while cursor.isoformat()[:7] <= TODAY[:7]:
    months.append(cursor.isoformat()[:7])
    cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
brands = [c["competitor"] for c in db["coverage"]]
coverage = [dict(competitor=brand, dated=sum(r["competitor"] == brand for r in verified),
                 months={m: sum(r["competitor"] == brand and r["date"].startswith(m) for r in verified) for m in months}) for brand in brands]
ok = sum(s["status"] == "ok" for s in statuses)
refresh = dict(attemptedAt=STAMP, status="ok" if ok == len(statuses) else "partial" if ok else "error",
               added=new_count, sources=statuses, schedule="Daily 04:00 Asia/Manila", provider="GitHub Actions")
db.update(records=rows, coverage=coverage, coverageEnd=TODAY, lastRefresh=refresh)
if ok:
    db["lastSuccessfulRefresh"] = STAMP
DATA.write_text(json.dumps(db, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
html = (ROOT / "index.html").read_text(encoding="utf-8-sig")
def js(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", r"\u003c")
for name, value in (("rows", rows), ("coverage", coverage), ("months", months)):
    html, count = re.subn(r"^const " + name + r"=.*?;$", lambda _: "const " + name + "=" + js(value) + ";", html, flags=re.M)
    if count != 1:
        raise ValueError("Dashboard data marker missing: " + name)
html = re.sub(r"const checked='[^']+'", "const checked='" + TODAY + "'", html)
end_label = datetime.strptime(TODAY, "%Y-%m-%d").strftime("%d %b %Y").lstrip("0")
html = re.sub(r"1 Jun [–-] \d+ [A-Za-z]+ \d{4}", "1 Jun – " + end_label, html)
options = '<option value="">Since June 2026</option>' + "".join('<option value="' + m + '">' + datetime.strptime(m, "%Y-%m").strftime("%B %Y") + "</option>" for m in months)
html = re.sub(r'(<select id="month"[^>]*>).*?(</select>)', lambda m: m[1]+options+m[2], html, flags=re.S)
head = "<tr><th>Competitor</th>" + "".join("<th>"+datetime.strptime(m,"%Y-%m").strftime("%b %y")+"</th>" for m in months) + "<th>Total</th></tr>"
html = re.sub(r"<thead>.*?</thead>", "<thead>"+head+"</thead>", html, flags=re.S)
html = html.replace("June–October coverage by competitor", "Coverage by competitor since June 2026")
html = re.sub(r"\*October through 26 October\.", "Through "+end_label+".", html)
html = html.replace("Automatic collection is not enabled.", "Cloud refresh · Daily 4:00 AM PHT")
html = html.replace("Automatic monitoring is not enabled.", "Scheduled refresh runs daily at 4:00 AM Philippine time on GitHub Actions.")
html = html.replace("No automatic monitoring", "Daily cloud refresh")
label = "Last cloud attempt: " + STAMP + " · " + refresh["status"].upper() + " · " + str(ok) + "/" + str(len(statuses)) + " sources available"
html = re.sub(r'<div id="refresh-status"[^>]*>.*?</div>', "", html)
html = html.replace('<div class="top">', '<div id="refresh-status" style="font-size:12px;padding:10px;background:#e5f1ec;margin-bottom:14px">'+label+'</div><div class="top">')
(ROOT / "index.html").write_text(html, encoding="utf-8")
summary = "# Competitor refresh\n\n" + label + "\n\n" + str(new_count) + " new records. Previous records retained on source failures.\n\n"
for s in statuses:
    summary += "- " + s["source"] + ": " + s["status"] + (" — " + s.get("error", "")) + "\n"
print(summary)
if __import__("os").environ.get("GITHUB_STEP_SUMMARY"):
    Path(__import__("os").environ["GITHUB_STEP_SUMMARY"]).write_text(summary, encoding="utf-8")
if not ok:
    sys.exit(1)

