"""Teena Link Checker.

Read-only: never runs scripts, never saves files, never opens the link in your browser.
It only downloads page TEXT (max 200 KB) and never talks to your local network (SSRF guard).
"""
import datetime
import ipaddress
import os
import re
import socket
import ssl
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

ALLOW_PRIVATE = False          # keep False (only the tests turn it on)
UA = "Mozilla/5.0 (compatible; TeenaLinkChecker/1.0)"
CACHE = Path(__file__).resolve().parent / "cache"
MAX_BODY = 200_000
MAX_HOPS = 8

SHORTENERS = {"bit.ly", "tinyurl.com", "t.co", "cutt.ly", "rb.gy", "is.gd", "goo.gl",
              "ow.ly", "shorturl.at", "tiny.cc", "rebrand.ly"}
RISKY_TLDS = {"top", "xyz", "click", "icu", "live", "shop", "site", "online", "support", "zip",
              "mov", "cfd", "sbs", "rest", "buzz", "cyou", "monster", "quest", "work", "loan",
              "gq", "tk", "ml", "ga", "cf", "vip", "fit", "bond"}
KEYWORDS = ["kyc", "verify", "update", "refund", "reward", "prize", "lottery", "gift", "claim",
            "otp", "suspend", "blocked", "bonus", "cashback", "winner", "urgent"]
SECOND_LEVEL = {"co", "com", "org", "gov", "ac", "net", "nic", "edu", "res"}

# brand token -> official registered domains
BRANDS = {
    "sbi": {"sbi.co.in", "onlinesbi.sbi", "sbi.bank.in", "sbicard.com", "sbilife.co.in"},
    "onlinesbi": {"onlinesbi.sbi", "onlinesbi.com"},
    "hdfc": {"hdfcbank.com", "hdfc.com", "hdfclife.com", "hdfcsec.com"},
    "hdfcbank": {"hdfcbank.com"},
    "icici": {"icicibank.com", "icicidirect.com", "iciciprulife.com"},
    "icicibank": {"icicibank.com"},
    "axisbank": {"axisbank.com"},
    "paytm": {"paytm.com", "paytmbank.com"},
    "phonepe": {"phonepe.com"},
    "amazon": {"amazon.in", "amazon.com", "amazon.co.uk", "amazonaws.com"},
    "flipkart": {"flipkart.com"},
    "netflix": {"netflix.com"},
    "whatsapp": {"whatsapp.com", "whatsapp.net", "wa.me"},
    "instagram": {"instagram.com"},
    "facebook": {"facebook.com", "fb.com"},
    "google": {"google.com", "google.co.in", "googleapis.com", "goo.gl", "gstatic.com", "withgoogle.com"},
    "irctc": {"irctc.co.in"},
    "incometax": {"incometax.gov.in", "incometaxindia.gov.in"},
    "jio": {"jio.com", "ril.com"},
    "airtel": {"airtel.in", "airtel.com"},
    "uidai": {"uidai.gov.in"},
}


# ---------------------------------------------------------------- helpers
def extract_urls(text):
    found = re.findall(r"(?:https?://|www\.)[^\s<>\"']+", text, flags=re.I)
    short = "|".join(re.escape(s) for s in SHORTENERS)
    found += re.findall(r"(?<![\w/.@-])(?:%s)/[^\s<>\"']+" % short, text, flags=re.I)
    out = []
    for u in found:
        u = u.rstrip(".,;:!?)]}>")
        if not re.match(r"^https?://", u, flags=re.I):
            u = "http://" + u
        if u not in out:
            out.append(u)
    return out


def reg_domain(host):
    labels = host.lower().strip(".").split(".")
    if len(labels) >= 3 and labels[-2] in SECOND_LEVEL and len(labels[-1]) == 2:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def is_ip(host):
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def host_status(host):
    """'ok' | 'private' | 'nodns'. Blocks loopback / LAN / link-local targets."""
    if not host:
        return "nodns"
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return "nodns"
    if ALLOW_PRIVATE:
        return "ok"
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        ip = getattr(ip, "ipv4_mapped", None) or ip
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            return "private"
    return "ok"


# ---------------------------------------------------------------- network pieces
def follow(url):
    """Follow redirects by hand (every hop is safety-checked). Returns hops, html, info."""
    hops, html, info = [], "", {}
    cur = url
    with httpx.Client(follow_redirects=False, timeout=8, headers={"User-Agent": UA}) as client:
        for _ in range(MAX_HOPS + 1):
            p = urlparse(cur)
            if p.scheme not in ("http", "https"):
                hops.append((cur, "blocked-scheme"))
                info["blocked"] = "scheme"
                break
            st = host_status(p.hostname)
            if st != "ok":
                hops.append((cur, st))
                info["blocked" if st == "private" else "nodns"] = True
                break
            try:
                with client.stream("GET", cur) as r:
                    hops.append((cur, r.status_code))
                    loc = r.headers.get("location")
                    if 300 <= r.status_code < 400 and loc:
                        cur = urljoin(cur, loc)
                        continue
                    ctype = r.headers.get("content-type", "").lower()
                    disp = r.headers.get("content-disposition", "").lower()
                    path = p.path.lower()
                    info["ctype"] = ctype
                    info["status"] = r.status_code
                    info["download"] = ("attachment" in disp or path.endswith((".apk", ".exe", ".msi", ".scr", ".bat", ".zip"))
                                        or (ctype != "" and not ctype.startswith(("text/", "application/xhtml"))))
                    if not info["download"]:
                        data = b""
                        for chunk in r.iter_bytes():
                            data += chunk
                            if len(data) > MAX_BODY:
                                break
                        html = data.decode(r.encoding or "utf-8", "replace")
                    break
            except Exception as e:
                info["error"] = type(e).__name__
                break
        else:
            info["too_many_hops"] = True
    return hops, html, info


def tls_info(host):
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, 443), timeout=5) as s:
            with ctx.wrap_socket(s, server_hostname=host) as ss:
                cert = ss.getpeercert()
        nb = ssl.cert_time_to_seconds(cert["notBefore"])
        na = ssl.cert_time_to_seconds(cert["notAfter"])
        issuer = dict(x[0] for x in cert["issuer"]).get("organizationName", "?")
        now = time.time()
        return {"valid": True, "issuer": issuer,
                "age_days": int((now - nb) / 86400), "expires_days": int((na - now) / 86400)}
    except ssl.SSLCertVerificationError as e:
        return {"valid": False, "error": e.verify_message}
    except Exception as e:
        return {"valid": None, "error": type(e).__name__}


def domain_age_days(domain):
    try:
        r = httpx.get(f"https://rdap.org/domain/{domain}", timeout=8, follow_redirects=True,
                      headers={"User-Agent": UA})
        if r.status_code != 200:
            return None
        for ev in r.json().get("events", []):
            if ev.get("eventAction") == "registration":
                d = datetime.datetime.fromisoformat(ev["eventDate"].replace("Z", "+00:00"))
                return (datetime.datetime.now(datetime.timezone.utc) - d).days
    except Exception:
        return None
    return None


def _feed(name, url):
    f = CACHE / name
    try:
        CACHE.mkdir(exist_ok=True)
        if f.exists() and time.time() - f.stat().st_mtime < 6 * 3600:
            return f.read_text("utf-8").splitlines()
        r = httpx.get(url, timeout=15, follow_redirects=True, headers={"User-Agent": UA})
        r.raise_for_status()
        f.write_text(r.text, "utf-8")
        return r.text.splitlines()
    except Exception:
        try:
            return f.read_text("utf-8").splitlines() if f.exists() else None
        except Exception:
            return None


def _norm(u):
    return u.strip().lower().rstrip("/")


def blocklist_check(urls):
    """Returns (status, detail). status: 'exact' | 'host' | 'clean' | None (feeds unreachable)."""
    feeds = [_feed("openphish.txt", "https://openphish.com/feed.txt"),
             _feed("urlhaus.txt", "https://urlhaus.abuse.ch/downloads/text_online/")]
    feeds = [f for f in feeds if f]
    if not feeds:
        return None, "feed download aagala"
    exact, hosts = set(), set()
    for f in feeds:
        for line in f:
            line = line.strip()
            if line.startswith("http"):
                exact.add(_norm(line))
                hosts.add((urlparse(line).hostname or "").lower())
    for u in urls:
        if _norm(u) in exact:
            return "exact", u
    for u in urls:
        h = (urlparse(u).hostname or "").lower()
        if h and h in hosts:
            return "host", h
    return "clean", f"{len(exact)} bad links-oda compare panni paathen"


def safe_browsing(urls):
    key = os.environ.get("GSB_API_KEY")
    if not key:
        return None
    try:
        body = {"client": {"clientId": "teena", "clientVersion": "1.0"},
                "threatInfo": {"threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE"],
                               "platformTypes": ["ANY_PLATFORM"], "threatEntryTypes": ["URL"],
                               "threatEntries": [{"url": u} for u in urls]}}
        r = httpx.post("https://safebrowsing.googleapis.com/v4/threatMatches:find",
                       params={"key": key}, json=body, timeout=8)
        return bool(r.json().get("matches"))
    except Exception:
        return None


# ---------------------------------------------------------------- analysis
def analyze_html(html):
    low = html.lower()
    title = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.S | re.I)
    sensitive = sorted({k for k in ("otp", "pin", "cvv", "card", "aadhaar", "aadhar", "mpin", "upi", "pan")
                        if re.search(r'name=["\'][^"\']*%s' % k, low) or re.search(r'placeholder=["\'][^"\']*%s' % k, low)})
    text = re.sub(r"<[^>]+>", " ", low)[:20000]
    return {
        "title": re.sub(r"\s+", " ", title.group(1)).strip()[:80] if title else "",
        "password": bool(re.search(r'type=["\']?password', low)),
        "sensitive": sensitive,
        "meta_refresh": bool(re.search(r'http-equiv=["\']?refresh', low)),
        "js_redirect": bool(re.search(r"(window\.|document\.)?location(\.href)?\s*=", low)),
        "obfuscated": bool(re.search(r"\batob\(|\beval\(|unescape\(", low)),
        "brands": sorted({b for b in BRANDS if re.search(r"\b%s\b" % re.escape(b), text)}),
    }


def check_one(url):
    sig, done, skipped = [], [], []
    hops, html, info = follow(url)
    chain = [h[0] for h in hops]
    hosts = []
    for u in chain:
        h = (urlparse(u).hostname or "").lower()
        if h and h not in hosts:
            hosts.append(h)
    final_host = hosts[-1] if hosts else ""
    path_txt = " -> ".join(hosts) if hosts else url
    if len(chain) > 1:
        path_txt += f"  ({len(chain) - 1} redirect)"

    if info.get("blocked"):
        return {"verdict": "BLOCKED", "score": 0, "url": url, "path": path_txt,
                "findings": ["Idhu un laptop / local network address. Safety-ku Teena check pannala."],
                "done": [], "skipped": ["ellaam"]}

    p0 = urlparse(chain[0] if chain else url)
    host0 = (p0.hostname or "").lower()

    # ---- static checks on every hop
    for u in chain:
        p = urlparse(u)
        h = (p.hostname or "").lower()
        reg = reg_domain(h)
        tld = h.rsplit(".", 1)[-1]
        if is_ip(h):
            sig.append((30, f"Domain peru illa, IP address ({h}) vechi link irukku"))
        if "@" in p.netloc:
            sig.append((35, "Link-la '@' irukku, ethaiyo maraikka trick"))
        if "xn--" in h:
            sig.append((30, f"Look-alike (punycode) domain: {h}"))
        if len(h.split(".")) - len(reg.split(".")) >= 3:
            sig.append((15, f"Romba subdomains: {h}"))
        if tld in RISKY_TLDS:
            sig.append((15, f".{tld} maathiri risky ending, scam sites adhikama use pannum"))
        for brand, officials in BRANDS.items():
            labels = re.split(r"[.-]", h)
            if (brand in labels or (len(brand) >= 5 and brand in h)) and reg not in officials:
                sig.append((45, f"'{brand}' maathiri nadikkudhu, aana official domain illa ({reg})"))
                break
    if any(h in SHORTENERS for h in hosts):
        sig.append((5, "Short link (unmaiyaana site-a maraikkum)"))
    if len(chain) > 3:
        sig.append((10, f"{len(chain)} thadavai redirect aagudhu"))
    if info.get("too_many_hops"):
        sig.append((15, "Redirect loop maathiri irukku"))
    if len(url) > 120:
        sig.append((5, "Romba neenda link"))
    kw = sorted({k for k in KEYWORDS if k in " ".join(chain or [url]).lower()})
    if kw:
        sig.append((min(24, 8 * len(kw)), "Link-la sandhega words: " + ", ".join(kw)))
    if chain and urlparse(chain[-1]).scheme == "http":
        sig.append((10, "https illa (http), data safe illa"))
    done.append("link pattern")

    # ---- site not reachable
    if info.get("nodns"):
        sig.append((0, "Indha domain internet-la illa / open aagala. Dead link-a irukkalaam."))
        skipped.append("page paarkkala")
    elif info.get("error"):
        skipped.append(f"page paarkkala ({info['error']})")

    # ---- page
    page = None
    if html:
        page = analyze_html(html)
        done.append("page text")
        if page["password"]:
            sig.append((15, "Page-la password kekkudhu"))
        if page["sensitive"]:
            sig.append((20, "Page-la sensitive details kekkudhu: " + ", ".join(page["sensitive"])))
        if page["obfuscated"]:
            sig.append((10, "Page-la maraicha (obfuscated) code irukku"))
        if page["meta_refresh"] or page["js_redirect"]:
            sig.append((10, "Page thaanaave veroru idathuku anuppum"))
        offbrand = [b for b in page["brands"] if reg_domain(final_host) not in BRANDS[b]]
        if offbrand and (page["password"] or page["sensitive"]):
            sig.append((25, f"Page-la {', '.join(offbrand)} peru irukku, login kekkudhu, aana domain avanga illa"))
    if info.get("download"):
        sig.append((40, "Link file-a download panna sollum (APK / exe / zip). Open pannaadheenga"))
        done.append("file type")

    # ---- certificate
    tls = None
    if final_host and not is_ip(final_host) and chain and urlparse(chain[-1]).scheme == "https" and not info.get("nodns"):
        tls = tls_info(final_host)
        if tls["valid"] is True:
            done.append("ssl certificate")
            if tls["age_days"] < 7:
                sig.append((10, f"SSL certificate {tls['age_days']} naal-lathaan vaangiyirukku"))
        elif tls["valid"] is False:
            done.append("ssl certificate")
            sig.append((40, f"SSL certificate sari illa: {tls['error']}"))
        else:
            skipped.append("ssl (check aagala)")

    # ---- domain age
    ages = []
    for h in hosts[:3]:
        if h not in SHORTENERS and not is_ip(h) and "." in h and not info.get("nodns"):
            a = domain_age_days(reg_domain(h))
            if a is not None:
                ages.append(a)
    age = min(ages) if ages else None
    if age is None:
        skipped.append("domain age (theriyala)")
    else:
        done.append("domain age")
        if age < 7:
            sig.append((45, f"Domain {age} naal-lathaan create aagirukku"))
        elif age < 30:
            sig.append((35, f"Domain {age} naal pazhasu, romba pudhusu"))
        elif age < 180:
            sig.append((15, f"Domain {age} naal pazhasu (6 maasathukku kammi)"))

    # ---- blocklists
    bl, detail = blocklist_check(chain or [url])
    if bl == "exact":
        sig.append((70, "Phishing / malware blocklist-la indha link irukku"))
        done.append("blocklist")
    elif bl == "host":
        sig.append((50, f"Blocklist-la indha site ({detail}) irukku"))
        done.append("blocklist")
    elif bl == "clean":
        done.append("blocklist (listed illa)")
    else:
        skipped.append("blocklist (internet / feed illa)")
    gsb = safe_browsing(chain or [url])
    if gsb is True:
        sig.append((80, "Google Safe Browsing: aabathaana site nu sollirukku"))
        done.append("Google Safe Browsing")
    elif gsb is False:
        done.append("Google Safe Browsing (listed illa)")

    seen, uniq = set(), []
    for p, m in sig:
        if m not in seen:
            seen.add(m)
            uniq.append((p, m))
    sig = uniq
    score = min(100, sum(p for p, _ in sig))
    strong_good = (tls and tls.get("valid") is True and age is not None and age >= 365 and score < 15)
    if score >= 60:
        verdict = "DANGEROUS"
    elif score >= 30:
        verdict = "SUSPICIOUS"
    elif strong_good:
        verdict = "LOW RISK"
    else:
        verdict = "UNKNOWN"
    return {"verdict": verdict, "score": score, "url": url, "path": path_txt,
            "title": page["title"] if page else "",
            "findings": [m for _, m in sorted(sig, key=lambda x: -x[0]) if m],
            "done": done, "skipped": skipped}


def format_report(r):
    lines = ["=== LINK CHECK ===",
             f"Link    : {r['url'][:150]}",
             f"Verdict : {r['verdict']}" + (f" (risk {r['score']}/100)" if r["verdict"] != "BLOCKED" else ""),
             f"Path    : {r['path']}"]
    if r.get("title"):
        lines.append(f"Page    : {r['title']}")
    lines.append("Findings:")
    lines += [f"  - {m}" for m in r["findings"]] or ["  - Edhuvum sandhegam kidaikkala"]
    lines.append("Checked : " + (", ".join(r["done"]) or "-"))
    if r["skipped"]:
        lines.append("Not checked: " + ", ".join(r["skipped"]))
    lines.append("Note: 100% guarantee illa. Pudhu scam sites blocklist-la innum irukkaadhu. Sandhegam na click pannaadheenga.")
    return "\n".join(lines)


def check_text(text, limit=3):
    urls = extract_urls(text)
    if not urls:
        return "Link edhuvum kidaikkala. http:// or www. oda full link paste pannunga."
    return "\n\n".join(format_report(check_one(u)) for u in urls[:limit])
