"""
The terms gate: the second filter. Reads a posting's full text and returns
every written term it breaks, with the sentence that breaks it.

Why it exists. On 2026-10-30 an audit re-read past shortlisted roles against
the operator's written terms. Most of the misses had the same cause: the role
OWNED revenue (renewal, expansion, NRR, "accountable for retention", OTE pay)
and was scored "ask on the first call" instead of no. So a second, stricter
filter was added.

The first filter (prefilter.py) finds and ranks. It prints several hard terms
as warnings (on-call, after-hours, quota) and never checked revenue ownership
or presenting at all. This module removes. A FAIL here is a written no; only
the operator's own "send anyway" overrides it, never the machine.

Operator rules from 2026-10-30: the pay range TOP must reach PAY_TOP_FLOOR
(the bottom may be lower); presenting, training or business reviews as a
RECURRING duty fail, explaining one's own work now and then does not.

    python3 careeros/terms_gate.py <url or text file>
"""

import re
import sys

# EXAMPLE operator setting — set your own floor for the top of a published range.
PAY_TOP_FLOOR = 85_000

# A sentence is the unit of evidence: the quote the operator reads is the sentence.
_SPLIT = re.compile(r"(?<=[.!?])\s+|\s*[\n•·▪●]\s*|\s+-\s+(?=[A-Z])")
# "No on-call", "we don't have quotas": the term is promised, not broken.
_NEGATION = re.compile(
    r"(?:❌|\b(?:no|not|never|without|zero|none|isn'?t|aren'?t|won'?t|don'?t|doesn'?t|"
    r"free (?:of|from))\b)[^.;:]{0,40}$", re.I)
# Somebody else owns it: "Sales owns renewals", "AEs handle expansion".
_OTHER_OWNER = re.compile(
    r"\b(?:sales|account executives?|AEs?|account managers?|the AM team|"
    r"our (?:sales|revenue) team)\s+(?:team\s+)?(?:owns?|handles?|drives?|manages?|"
    r"leads?|is responsible for|are responsible for)\b[^.;]{0,25}$", re.I)
# ...or the sentence's subject is sales and the match starts at its verb.
_SALES_SUBJECT = re.compile(r"\b(?:sales|AEs?|account executives?|account managers?)"
                            r"(?:\s+team)?\s*$", re.I)
_PAST_EXPERIENCE = re.compile(r"\byears? of experience\b|\bexperience (?:in|as|with)\b|"
                               r"\bexperience\s*$|\btrack record\b|\bcontributions to\b", re.I)
_NICE_TO_HAVE = re.compile(r"\b(?:preferred|nice to have|a plus|bonus|"
                           r"is helpful|would be great)\b", re.I)
_OCCASIONAL = re.compile(r"\b(?:occasional(?:ly)?|from time to time|as needed|"
                         r"when needed|sometimes|now and then|opportunit(?:y|ies) (?:for you )?to)\b", re.I)

# (rule, label, pattern, guard). guard: "neg" skips negated matches, "owner"
# also skips matches whose subject is the sales team, "occasional" turns a
# match into a flag when the sentence says it happens only now and then.
FAIL_RULES = [
    # F1 remote
    ("F1", "not fully remote",
     r"\bhybrid (?:schedule|work(?:ing)? model|arrangement)\b|"
     r"\bhybrid (?:role|position) (?:based|in|at|out of)\b|"
     r"\b(?:\d|one|two|three|four)\s+days?\s+(?:a|per|each)\s+week\s+in\b|"
     r"\bin[- ]office\s+(?:\d|one|two|three|four)\s+days\b|"
     r"\b(?:\d|one|two|three|four|five)\s+days?\s+(?:a week\s+|per week\s+)?in[- ](?:the[- ])?office\b|"
     r"\b(?:must|need to|required to)\s+(?:live|reside|be based|be located)\s+"
     r"(?:in|within|near)\s+(?:commuting distance|the (?:sf|bay|nyc|new york)|"
     r"san francisco|new york|nyc|the bay area|seattle|austin|boston)\b|"
     r"\brelocation (?:to [A-Z][a-z]+ )?(?:is )?required\b|\breturn[- ]to[- ]office\b|"
     r"\brequires? (?:candidates|you|applicants) to (?:be based|live|reside) in\b|"
     r"\bonsite (?:engagement|placement|presence)\b|\bcustomer onsite\b|"
     r"\bbased out of (?!(?:the )?(?:u\.?s\.?\b|usa\b|united states|anywhere))[A-Z]|"
     r"\b(?:must|required to) be (?:based|located) in (?!(?:the )?(?:u\.?s\.?\b|usa\b|united states|"
     r"north america|americas|puerto rico|latam|latin america))(?:the )?[A-Z]",
     "neg"),
    # F3 nothing follows you home
    ("F3", "work follows you home",
     r"\bon[- ]call\b(?! (?:rotation )?experience)|\bpager(?:duty)?\b|\bweekend (?:shifts?|coverage|rotations?|work|"
     r"availability|support)\b|\b(?:nights?|evenings?) and weekends\b(?! back)|"
     r"\bafter[- ]hours (?:support|coverage|availability|work|escalations?)\b|"
     r"\b(?:outside|beyond) (?:of )?(?:normal |regular |standard )?business hours\b|"
     r"\bovertime\b|\bfollow[- ]the[- ]sun\b|\bworking late\b|"
     r"\bwork (?:evenings|nights),? weekends\b|"
     r"\bshift(?:s|\(s\))?\b[^.]{0,60}?(?:\b(?:satur|sun)day\s*[-–]|[-–]\s*(?:satur|sun)day\b)|"
     r"^(?:(?:satur|sun)day\s*[-–]\s*\w+day|\w+day\s*[-–]\s*(?:satur|sun)day)\s+\d{1,2}(?::\d\d)?\s*[ap]m",
     "neg"),
    # F4 intensity culture (written no since 2026-10-13)
    ("F4", "intensity culture",
     r"\bhigh[- ]intensity\b|\blow[- ]intensity\b|\bhardcore\b|\bintense (?:pace|environment|"
     r"culture|hours)\b|\bdemanding (?:job|role|environment|pace)\b|\bhustles?\b|\bgrind\b|"
     r"\bwork hard,? play hard\b|\bextreme (?:speed|pace|urgency)\b|\blong hours\b|"
     r"\b(?:over|more than|at least)\s+(?:40|forty|50|fifty)\s+hours\b|\b(?:50|60)\+?\s*hours?\s+"
     r"(?:a|per)\s+week\b|\balways-on\b|\balways on (?:call|culture|availability)\b|"
     r"\bnot a 9[- ]to[- ]5\b",
     "neg"),
    # F6 all base, no quota, no sell-more: pay that is part commission
    ("F6", "commission / OTE pay",
     r"\bOTE\b|\bon[- ]target earnings\b|\b\d{2}\s*/\s*\d{2}\s*(?:split|OTE|base)|"
     r"\b(?:base|salary)\s*(?:\+|plus|and)\s*(?:variable|commission)\b|"
     r"\binclusive of variable\b|\buncapped commission\b|\bcommission[- ]based\b|"
     r"(?<!headroom, )(?<!storage )(?<!resource )(?<!API )\bquota\b(?![- ]carrying reps|"
     r",? (?:and )?(?:reservations?|limits?|usage)\b)|\b(?:hit|hitting|exceed|exceeding|meet)\s*(?:/\s*exceed\w*\s*)?"
     r"(?:your |customer |the )?(?:quota|revenue|retention|sales) targets?\b",
     "owner"),
    # F6: the role OWNS revenue (the 12-of-15 audit cause)
    ("F6", "owns revenue (renewal / expansion / NRR)",
     r"\b(?:measured|judged|evaluated|compensated) (?:on|by)\b[^.;]{0,80}?\b(?:pipeline|revenue|bookings|quota)\b|"
     r"\b(?:own|owns|owning|drive|drives|driving|accountable for|responsible for|"
     r"lead|leading|manage|managing|find|identify|surface|facilitate|support|grow|growing)"
     r"\b[^.;]{0,70}?\b(?:renewals?|upsells?|upselling|cross[- ]sell\w*|"
     r"net revenue retention|revenue retention|account growth|retention targets?|"
     r"book of business)\b|"
     r"\b(?:own|owns|owning|accountable for)\b[^.;]{0,40}?\b(?:customer |logo )?retention\b|"
     r"\bNRR\b|\bnet revenue retention\b|\bexpansion (?:revenue|opportunit\w+|targets?|"
     r"pipeline)\b|\breferral expansion\b|\baccount expansions?\b|"
     r"\bgrow(?:ing)? (?:usage|revenue|spend) against\b|\bnext expansion\b|"
     r"\brevenue retention\b|\baccount growth\b|\brenewal\w*[^.;]{0,30}\band expansion\b|"
     r"\boutreach against expansion\b|\bdriv\w* revenue\b|\btechnical seller\b|"
     r"\bclos(?:e|ing) (?:deals|business|new logos)\b",
     "owner"),
    # F7 years: a required minimum of 4+ (since 2026-10-14; "3-5 years" = 3).
    ("F7", "asks 4+ years",
     r"(?<!\d[-–])(?<!\d [-–] )(?<!\d[-–] )(?<!\d to )(?<!\d)\b(?:[4-9]|1\d)\s*(?:\+|plus)?\s*"
     r"(?:(?:-|–|to)\s*\d+\s*)?\+?\s*years?\b"
     r"(?=[^.;]{0,60}\bexperience\b|\s+(?:in|as|at|working|building|leading|supporting|"
     r"shipping|doing|designing|delivering|managing|selling|owning)\b|\s+of\s+(?!runway|history|age\b|growth|operation|existence)\w)|"
     r"\b(?:at least|minimum of|minimum)\s+(?:[4-9]|1\d|four|five|six|seven|eight|ten)\s+years\b",
     "years"),
    # F10 values (an operator-configured exclusion)
    ("F10", "gender-affirming care",
     r"\bgender[- ]affirming\b(?! (?:benefits?|coverage|health benefits))", None),
    # F11 presenting / training as a recurring duty (since 2026-10-29)
    ("F11", "presenting / training as a duty",
     r"\b(?:host|hosts|hosting|run|runs|running|lead|leads|leading|deliver|delivers|"
     r"delivering|conduct|conducting|facilitate|facilitating|prepare and deliver|own)"
     r"\b[^.;]{0,50}?\b(?:webinars?|workshops?|training sessions?|trainings?"
     r"(?!,? (?:and )?(?:simulation|inference|data|runs?|jobs?|pipelines?|clusters?|"
     r"workloads?|compute|and inference))|"
     r"enablement (?:sessions?|programs?)|office hours|QBRs?|quarterly business reviews?|"
     r"(?:executive )?business reviews?|performance reviews for (?:your )?(?:key )?accounts|"
     r"briefings and presentations|customer training|demo streams?|livestreams?|"
     r"live (?:demos?|sessions?|streams?))\b|\blive audience\b|"
     r"\b(?:speak|speaking|present|presenting|talks?) at (?:conferences|events|meetups)\b|"
     r"\brepresent [A-Z][\w.]* at [^.;]{0,30}?\b(?:events|conferences|meetups)\b|"
     r"\bconference talks?\b|(?<!hands-)\bon (?:camera|stage)\b|\bteach (?:each |the )?"
     r"(?:customers?|users|teams?|others|each customer)\b|\btrain and upskill\b|"
     r"\btrain (?:customers|users|others)\b|\bguidance and training to\b|"
     r"\b(?:create|record|produce|film)\w* (?:technical |educational |tutorial |demo |youtube )?"
     r"(?:video content|videos?,? (?:and|or) (?:blog|tutorials?|livestreams?|streams)|"
     r"livestreams?|tutorial videos|youtube videos)\b|"
     r"\bincluding:? [^.;]{0,60}\bQBRs\b|"
     r"\blead\w* (?:clients|customers|users)\b[^.;]{0,90}\btraining\b|"
     r"\brecurring enablement\b|\benablement programs?\b|\bdeliver\w* (?:internal )?enablement\b|"
     r"\beducation (?:initiatives|programs)\b|\blead (?:in[- ]person |live )?sessions\b|"
     r"\btrain (?:internal |our |the )?(?:teams?|customers|users|others|clients)\b|"
     r"\bevangelism\b|\btalks,? (?:and )?demos\b|\bdemos,? talks\b|\b(?:make|making) videos?\b|"
     r"\battend\w* conferences\b|\bvideos,? and conferences\b|\bat a conference\b|"
     r"\brun\w* [^.;]{0,20}hackathons\b",
     "occasional"),
    # F16 contractor in the full-time lane (since 2026-10-26)
    ("F16", "contract, not employee",
     # The 1099 tax form alone is not a contract (Block builds 1099 systems);
     # "W2 or a 1099, to be determined" is an ask, flagged below.
     r"(?<!or a )(?<!or )\b1099[- ](?:independent )?contract\w*|(?<!or )\ba 1099\b|"
     r"\b(?:on|as) a 1099\b|\b1099 (?:role|position|engagement|opportunity|basis)\b|"
     r"\bcontract(?:ing|or)? (?:role|position)\b|\bthis is a contract\b",
     "neg"),
]

FLAG_RULES = [
    ("F3", "24/7 mentioned", r"\b24/?7\b|\baround the clock\b"),
    ("F16", "W2 or 1099 not decided", r"\bW-?2\b[^.;]{0,40}\bor (?:a )?1099\b"),
    ("F4", "effort language", r"\bwork hard\b|\bextra mile\b|\bnot for everyone\b|"
     r"\bfast[- ]paced\b|\bscrappy\b"),
    ("F6", "works with sales", r"\b(?:partner|work|collaborate)\w* (?:closely )?with "
     r"(?:sales|account executives|AEs|the sales team)\b"),
    ("F13", "travel / offsites", r"\b\d{1,2}\s*%\s*(?:of the time )?travel|"
     r"travel[^.;]{0,30}\b\d{1,2}\s*%|\boffsites?\b|\bin[- ]person (?:meetups?|"
     r"gatherings?|weeks?)\b"),
    ("F7", "years asked", r"\b3\s*\+?\s*(?:(?:-|–|to)\s*\d+\s*)?\+?\s*years?\b|"
     r"\b(?:[4-9]|1\d)\s*\+?\s*years?\b[^.;]{0,40}\b(?:preferred|a plus|nice to have)\b"),
    ("F10", "gender-affirming employee benefit", r"\bgender[- ]affirming (?:benefits?|coverage)"),
    ("F9", "pharma customers", r"\bpharma(?:ceutical)?s?\b|\bbiopharma\b|\blife sciences\b"),
]

TITLE_FAILS = [
    ("F8", "senior title", r"\b(?:senior|sr\.?|staff|principal|lead|head of|director|"
     r"vp|vice president)\b"),
    ("F8", "manages people", r"^manager\b|\bengineering manager\b|\bmanager of\b|"
     r"\bsupport engineering manager\b|\bmanager,\s"),
    ("F3", "weekend shift", r"\b(?:sat|sun)(?:urday|day)?\s*[-–]\s*\w+\s+shift\b|\bweekend shift\b"),
    ("F11", "presenting job by title", r"\bdeveloper (?:advocate|relations)\b|\bdevrel\b|"
     # "Silicon Enablement" is hardware work; only sales/customer enablement teaches.
     r"\bevangelist\b|\b(?:sales|gtm|go[- ]to[- ]market|customer|partner|field|revenue|"
     r"learning|product) enablement\b|\benablement (?:manager|specialist|lead|partner|"
     r"program|director|associate)\b|^enablement\b|\btrainer\b|\beducator\b|\binstructor\b"),
    ("F12", "design role", r"\bdesigner\b|\bdesign engineer\b|\bux\b|\bui/ux\b|\bdrafter\b|"
     r"\bdraftsperson\b"),
]

BRIDGE_FAILS = [
    ("B4", "exclusivity / non-compete", r"\bexclusivity (?:agreement|clause|requirement)\b|(?<!non-)\bexclusive "
     r"(?:contract|agreement|engagement|basis|relationship)\b|\bwork exclusively\b|\bnon[- ]compete\b|"
     r"\bminimum (?:term|commitment) of\b"),
    ("B5", "too many hours", r"(?<![-–])(?<![-–] )(?<!to )\b(?:3\d|40)\+?\s*(?:hours|hrs)\s*(?:/|a|per)\s*week\b|"
     r"\bfull[- ]time hours\b"),
]

_COMPILED = [(r, l, re.compile(p, re.I), g) for r, l, p, g in FAIL_RULES]
_FLAGS = [(r, l, re.compile(p, re.I)) for r, l, p in FLAG_RULES]
_TITLE = [(r, l, re.compile(p, re.I)) for r, l, p in TITLE_FAILS]
_BRIDGE = [(r, l, re.compile(p, re.I)) for r, l, p in BRIDGE_FAILS]
# Boilerplate some companies print on every posting, about other roles.
_BOILERPLATE = re.compile(
    r"(?:\+|plus|and)?\s*commission\s*\((?:for )?quota[- ]based roles\)|"
    r"\((?:for )?quota[- ]based roles\)|commission if applicable|"
    r"commission for (?:sales|eligible) roles|where applicable|"
    r"[^.]{0,400}variable comp\w* where (?:appropriate|applicable)[^.]{0,400}|"
    r"for sales roles,[^.]{0,400}|[^.]{0,400}\bnon-commission(?:able|[- ]based)? roles[^.]{0,400}|employment or an? (?:independent )?contractor (?:role|position)|[^.]{0,400}office-based team members[^.]{0,400}", re.I)


# Companies whose customers are mainly big pharma, an operator exclusion since
# 2026-10-14. Matched on the company name.
PHARMA_VENDORS = re.compile(r"^(?:veeva(?: systems)?|iqvia|medidata|certara|"
                            r"model n|indegene)$", re.I)


class Verdict:
    __slots__ = ("fails", "flags", "read")

    def __init__(self, read=True):
        self.fails = []   # (rule, label, sentence)
        self.flags = []
        self.read = read

    @property
    def passed(self):
        return self.read and not self.fails

    def summary(self):
        if not self.read:
            return "not readable"
        return "; ".join(f"{r} {l}" for r, l, _ in self.fails) or "pass"


def sentences(text):
    return [s.strip() for s in _SPLIT.split(text or "") if len(s.strip()) > 3]


def _blocked(sentence, start, guard, end=None):
    # ATS text often arrives with its line breaks collapsed, so one "sentence"
    # can be a whole posting. Guards look only at the words around the match.
    before = sentence[max(0, start - 100):start]
    end = start if end is None else end
    around = sentence[max(0, start - 60):end + 40]
    if guard in ("neg", "owner", "occasional") and _NEGATION.search(before):
        return True
    if guard == "owner" and (_OTHER_OWNER.search(before) or _SALES_SUBJECT.search(before)):
        return True
    # "2 years of experience in a ... quota-carrying role" asks about the applicant's past.
    if guard in ("owner", "occasional") and _PAST_EXPERIENCE.search(before):
        return True
    if guard == "years" and _NICE_TO_HAVE.search(around):
        return True
    return False


def check(text, title="", pay_top=None, pay_published=False, bridge=False,
          min_chars=400, company=""):
    """Return a Verdict. A posting shorter than min_chars was not really read."""
    text = (text or "").replace("\xa0", " ")
    # Unfilled pay template lines ("OTE (all other U.S. states): $X - $X", Affirm
    # 2026-10-31) say nothing about this role.
    text = re.sub(r"[^\n]{0,400}\$X\s*-\s*\$X[^\n]{0,400}", " ", text)
    # "Tuesday - Saturday" is a day range, not a list bullet; keep it whole.
    text = re.sub(r"(day)\s+-\s+(?=(?:mon|tues|wednes|thurs|fri|satur|sun)day)", r"\1–",
                  text, flags=re.I)
    v = Verdict(read=len(text) >= min_chars)
    seen = set()

    def add(bucket, rule, label, sent, m=None):
        key = (bucket is v.fails, rule, label)
        if key not in seen:
            seen.add(key)
            quote = sent if m is None else sent[max(0, m.start() - 120):m.end() + 120]
            bucket.append((rule, label, quote.strip()[:300]))

    if company and PHARMA_VENDORS.search(company.strip()):
        add(v.fails, "F9", "sells to big pharma", f"company: {company}")
    for rule, label, pat in _TITLE:
        if not bridge and pat.search(title or ""):
            add(v.fails, rule, label, f"title: {title}")
    if (not bridge and pay_published and pay_top is not None
            and pay_top < PAY_TOP_FLOOR):
        add(v.fails, "F5", f"pay top under ${PAY_TOP_FLOOR // 1000}k",
            f"published top ${pay_top:,.0f}")

    for sent in sentences(text):
        clean = _BOILERPLATE.sub(" ", sent)
        for rule, label, pat, guard in _COMPILED:
            if bridge and rule in ("F16", "F11"):
                continue
            for m in pat.finditer(clean):
                if _blocked(clean, m.start(), guard, m.end()):
                    continue
                near = clean[max(0, m.start() - 80):m.end() + 80]
                bucket = v.flags if (guard == "occasional"
                                     and _OCCASIONAL.search(near)) else v.fails
                add(bucket, rule, label, clean, m)
                break
        for rule, label, pat in _FLAGS:
            m = pat.search(clean)
            if m and not _NEGATION.search(clean[:m.start()]):
                add(v.flags, rule, label, clean, m)
        if bridge:
            for rule, label, pat in _BRIDGE:
                m = pat.search(clean)
                if m and not _NEGATION.search(clean[:m.start()]):
                    add(v.fails, rule, label, clean, m)
    return v


def check_scored(item, page=None):
    """Gate a prefilter.Scored on its listing description plus any page text."""
    listing = item.listing
    text = " \n".join(t for t in (listing.description, page) if t)
    sal = getattr(item, "salary", None)
    published = bool(sal is not None and getattr(sal, "confidence", "") == "published")
    v = check(text, listing.title, getattr(sal, "top", None), published,
              bridge=bool(getattr(item, "bridge", False)), company=listing.company)
    # Pay read from the ATS compensation field, outside the posting text
    # (Snyk, 2026-10-30: "assumed 80/20 of $132,000-$166,000 OTE").
    shown = sal.display() if sal is not None and hasattr(sal, "display") else ""
    if re.search(r"\bOTE\b", shown) and not any(r == "F6" for r, _, _ in v.fails):
        v.fails.append(("F6", "commission / OTE pay", f"pay: {shown}"))
    return v


# ---- CLI: run this on a posting before recommending a role or applying.

def _fetch(url):
    import html
    import json
    import urllib.request

    def get(u):
        req = urllib.request.Request(u, headers={"User-Agent": "CareerOS terms gate"})
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.read().decode("utf-8", "ignore")

    def strip(t):
        t = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>|</div>", "\n", t)
        return html.unescape(re.sub(r"<[^>]+>", " ", t))

    m = re.search(r"jobs\.ashbyhq\.com/([^/]+)/([0-9a-f-]{36})", url)
    if m:
        board = json.loads(get("https://api.ashbyhq.com/posting-api/job-board/"
                               f"{m[1]}?includeCompensation=true"))
        for j in board.get("jobs", []):
            if j.get("id") == m[2]:
                comp = (j.get("compensation") or {}).get("compensationTierSummary", "")
                return j.get("title", ""), f"{comp}\n{j.get('descriptionPlain', '')}"
        raise SystemExit("posting not on the board any more (closed)")
    m = re.search(r"greenhouse\.io/([^/]+)/jobs/(\d+)", url)
    if m:
        j = json.loads(get(f"https://boards-api.greenhouse.io/v1/boards/{m[1]}/jobs/{m[2]}"))
        return j.get("title", ""), strip(html.unescape(j.get("content", "")))
    m = re.search(r"jobs\.lever\.co/([^/]+)/([0-9a-f-]{36})", url)
    if m:
        j = json.loads(get(f"https://api.lever.co/v0/postings/{m[1]}/{m[2]}"))
        lists = "\n".join(x.get("text", "") + "\n" + strip(x.get("content", ""))
                          for x in j.get("lists", []))
        desc = j.get("descriptionPlain") or strip(j.get("description", ""))
        extra = j.get("additionalPlain") or strip(j.get("additional", ""))
        return j.get("text", ""), f"{desc}\n{lists}\n{extra}"
    return "", strip(get(url))


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    src = argv[1]
    if src.startswith("http"):
        title, text = _fetch(src)
    else:
        title, text = "", open(src, encoding="utf-8").read()
    pay = re.findall(r"\$\s?(\d{2,3})(?:,(\d{3})|k|K)", text)
    tops = [int(a) * 1000 for a, _ in pay]
    v = check(text, title or (argv[2] if len(argv) > 2 else ""),
              max(tops) if tops else None, bool(tops))
    print(f"TERMS GATE: {'PASS' if v.passed else 'FAIL'}  ({title})")
    if not v.read:
        print("  NOT READABLE: under 400 characters of posting text")
    for r, l, s in v.fails:
        print(f"  FAIL {r} {l}: \"{s}\"")
    for r, l, s in v.flags:
        print(f"  flag {r} {l}: \"{s}\"")
    return 0 if v.passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
