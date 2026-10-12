"""
Role-title fit scoring.

v1 had no concept of what job the operator wants. Tiering ran on pay, culture
keywords and geography alone, so an Associate General Counsel role at $240k
outranked every AI Engineer opening in the same digest. This module supplies
the missing axis.

Title only, never the description — the same discipline estimate.py uses. A
description mentions "solutions" and "customer success" for a hundred reasons;
the title is the one field that states what the job actually is.

Four lanes, checked in order:

  core      the operator's own target titles
  adjacent  same lane, different vocabulary
  stretch   unrecognised, or generic engineering without seniority
  off       roles the operator cannot get or does not want, named explicitly

`off` is a list, never a fallback. An unrecognised title lands in `stretch`,
because unknown must not be punished like known-bad — the operator is
explicitly open to roles that do not pattern-match their history.
"""

import re

LANE_CORE = "core"
LANE_ADJACENT = "adjacent"
LANE_STRETCH = "stretch"
LANE_OFF = "off"

# Deliberately unweighted integers, matching every other term in the prefilter
# score. Core outranks the +3 geo bonus so role fit cannot be outvoted by a
# single "work from anywhere" phrase.
LANE_SCORE = {
    LANE_CORE: 6,
    LANE_ADJACENT: 4,
    LANE_STRETCH: 1,
    LANE_OFF: -6,
}

# The operator's target titles, plus the spelling
# variants boards actually use. "Customer Engineer" is widely used and easy to
# miss, which is why it is listed explicitly rather than inferred.
CORE_PATTERNS = [
    # "engineering" as well as "engineer" throughout: boards write both, and
    # "Director of Solutions Engineering" is the same lane as "Solutions
    # Engineer" even though the noun changed.
    # Widened 2026-09-30 after the operator noticed no implementation roles in
    # the digest. Measured that day: 901 implementation-shaped roles
    # were live, 155 cleared the experience gate, and 7 had reached the digest in
    # twenty-one runs. The gate was not the bottleneck — these two patterns
    # were. Each required an exact noun immediately after, so "Implementation
    # Manager", "Implementation Lead", "Implementation Analyst" and "Customer
    # Onboarding Manager" all fell through to `stretch`, where earns_main_lane()
    # makes a role argue for its slot.
    (r"\bimplementation\b(?!\s+(?:technician|electrician))", "implementation"),

    # The title this lane is most often filed under, and it was absent entirely.
    # "Cloud Professional Services Manager" and "Professional Services -
    # Technical Architect" were both landing in stretch.
    (r"\bprofessional\s+services\b", "professional services"),

    # Onboarding needs a customer on the other end. Bare `onboarding` is a trap
    # with two live examples from the same audit: "KYC/B Onboarding Analyst" is
    # compliance, and "Sales Enablement & Onboarding Manager" is internal
    # training. Neither is the target work, and both would have walked into core.
    # `manager` and `lead` are deliberately NOT in the noun list: "Sales
    # Enablement & Onboarding Manager" matched it on the first cut, and that is
    # internal training, not customer implementation. Those two need a
    # customer-side word in front of "onboarding" to qualify.
    (r"\b(?:customer|client|user|merchant|partner|technical|smb|enterprise)\s+"
     r"onboarding\b|\bonboarding\s+(?:engineer|specialist|"
     r"consultant|architect|project\s+manager)\b", "onboarding"),

    # People-facing deployment only, since 2026-10-12; "Deployment Engineer"
    # (often database or platform infrastructure) moved to DEMOTED_PATTERNS.
    (r"\bdeployment\s+(?:strategist|specialist|consultant|manager|lead)\b",
     "deployment strategist"),

    # PREMIUM MEMBER EXPERIENCE (concierge, luxury travel, VIP member roles) was
    # core from 2026-09-30 and REMOVED 2026-10-08 by the operator, to focus the
    # search on newer industries. Premium-tier support AT SOFTWARE COMPANIES stays
    # (derived, below).
    (r"\btechnical\s+account\s+manager\b", "technical account manager"),
    (r"\bautomation\s+engineer(?:ing)?\b", "automation engineer"),
]

# Engineering-heavy titles, demoted from CORE to adjacent 2026-10-12 by the
# operator, to focus the main lane on the target roles. These screen for coding
# depth on paper.
# They are still tested BEFORE the off list, exactly where core used to test
# them, so "Senior Solutions Engineer" stays adjacent instead of falling to
# "senior pure engineering". Only the lane changes, never the exclusions.
DEMOTED_PATTERNS = [
    (r"\bdeployment\s+(?:engineer|architect)\b", "deployment engineer"),
    (r"\bsolutions?\s+(?:engineer(?:ing)?|architect)\b", "solutions engineer"),
    (r"\bforward[- ]deployed\b", "forward deployed engineer"),
    (r"\bcustomer\s+engineer(?:ing)?\b", "customer engineer"),
    (r"\b(?:technical\s+)?support\s+engineer(?:ing)?\b", "support engineer"),
    (r"\bai\s+engineer(?:ing)?\b|\bai/ml\s+engineer\b", "AI engineer"),
    (r"\bintegrations?\s+engineer(?:ing)?\b", "integrations engineer"),
]

# Same work, different words. Scored below core so the operator's own
# vocabulary wins when both match.
ADJACENT_PATTERNS = [
    (r"\b(?:sales|pre-?sales)\s+engineer\b", "sales engineer"),
    (r"\bsolutions?\s+consultant\b", "solutions consultant"),
    (r"\bdeveloper\s+(?:advocate|relations|experience)\b|\bdevrel\b", "developer advocate"),
    (r"\bapplied\s+ai\b|\bai\s+consultant\b|\bprompt\s+engineer\b", "applied AI"),
    (r"\bpartner\s+engineer\b|\bprofessional\s+services\s+engineer\b", "partner engineer"),
    (r"\bdeployment\s+engineer\b|\bfield\s+engineer\b", "deployment engineer"),
    (r"\bcustomer\s+success\b", "customer success"),
    (r"\btechnical\s+consultant\b", "technical consultant"),
]

# Adjacent roles that must be tested BEFORE the off-lane list, for exactly the
# reason core is: the senior pure-engineering gate matches "Senior <anything>
# Engineer", so "Senior Red Team Engineer" would be classified off-lane and
# never print.
#
# These are the lanes the operator opened on 2026-08-17. AI evals, red-teaming
# and model QA hire unusual backgrounds by design, and agent-design and evals
# work maps directly. Adjacent, not core: the primary target is elsewhere.
PROTECTED_ADJACENT_PATTERNS = [
    (r"\bred[- ]?team\w*\b", "red teaming"),
    (r"\b(?:model|ai|llm)\s+eval(?:uation)?s?\b|\bevals?\s+engineer\b", "AI evals"),
    (r"\bmodel\s+(?:qa|quality)\b|\bai\s+quality\b", "model QA"),
    (r"\balignment\s+(?:engineer|specialist|researcher)\b", "alignment"),
    (r"\bai\s+safety\b", "AI safety"),
]

# Lanes derived from the operator's prior work history, opened 2026-09-28.
# These encode one person's background; configure them for your own.
#
# Tested BEFORE the off-lane list for the same reason protected-adjacent is:
# several of these titles collide with an off pattern written for a different
# job. "Chief of Staff" hits the `chief` executive rule, "Technical Writer"
# hits `writer`, "AI Trainer" hits `trainer`. Each collision is a different
# job wearing the same word.
#
# Each group names the kind of experience it comes from, because the point is
# not to widen the net — it is to widen it along lines the operator can actually
# defend in an interview.
DERIVED_PATTERNS = [
    # --- From prior premium-service work ---
    # Anticipating needs, competing priorities under pressure, discretion with
    # sensitive situations. That is the job spec for a founder's right hand and
    # for the premium tier of support.
    (r"\bchief\s+of\s+staff\b", "chief of staff"),
    (r"\bexecutive\s+(?:business\s+)?partner\b|\bfounder'?s?\s+associate\b|"
     r"\bassociate\s+to\s+the\s+(?:ceo|founder)\b", "founder's right hand"),
    (r"\b(?:vip|premium|priority|white[- ]glove|dedicated|concierge|elite)\s+"
     r"(?:support|success|service|experience|account)\w*\b", "premium-tier support"),
    (r"\bclient\s+(?:partner|services?|advisor)\b", "client services"),

    # --- From prior regulated customer-support work ---
    # The support half, never the sales half. Translating high-stakes,
    # confusing, regulated information into plain terms, with real consequences
    # for getting it wrong. That is the core competence of trust & safety and
    # policy work, which hire unusual backgrounds by design and are fully remote.
    (r"\btrust\s*(?:&|and)\s*safety\b|\bt&s\b", "trust & safety"),
    (r"\b(?:content|platform|community|marketplace)\s+policy\b|"
     r"\bpolicy\s+(?:specialist|analyst|operations|ops|manager)\b", "content policy"),
    (r"\b(?:risk|fraud|abuse|integrity)\s+(?:operations|ops|specialist|analyst|investigator)\b",
     "risk & integrity ops"),
    (r"\b(?:member|patient|customer|user)\s+experience\s+"
     r"(?:specialist|manager|lead|associate)\b", "member experience"),

    # --- From a design education ---
    # Physical and brand design are ruled out; digital design is plausible.
    # This switches digital design on explicitly. The
    # off-lane brand/graphic/visual/motion/industrial/packaging rule is
    # untouched, so only product and interface work opens.
    (r"\b(?:product|ux|ui|interaction|experience)\s+designer\b|"
     r"\bproduct\s+design(?:er)?\b|\bdesign\s+engineer\b", "product/UX design"),
    (r"\bux\s+research(?:er)?\b|\buser\s+research(?:er)?\b", "UX research"),

    # --- From the self-taught AI practice ---
    # "AI Trainer" and "AI Tutor" at the labs and data companies are not
    # teaching jobs; they are model evaluation work that happens to borrow the
    # vocabulary of teaching. The off-lane `trainer|tutor` rule exists because
    # the operator does not want to deliver training to humans. This carve-out
    # is deliberately narrow: the AI prefix is required.
    (r"\bai\s+(?:trainer|tutor|specialist|analyst)\b|"
     r"\b(?:llm|model)\s+trainer\b", "AI training"),

    # --- Technical writing, carved out of the `writer` off-lane rule ---
    # That rule blocks editorial and copywriting, which crowd out the target lane.
    # Documentation at an AI company is a different job: it pays $90-140k,
    # is remote by default, and rewards the pairing of reading the code and
    # explaining it to someone who cannot. Developer *educator* is left
    # blocked; that is teaching delivery.
    (r"\btechnical\s+writer?\b|\btechnical\s+writing\b|"
     r"\bdocumentation\s+(?:engineer|specialist|lead|manager)\b|\bdocs\s+engineer\b",
     "technical writing"),

    # --- From being fully bilingual (English/Spanish), spoken and written ---
    # LATAM-facing roles pay a premium against less competition. Matched on the
    # title so it only fires
    # when the role is actually regional, not when a US posting merely mentions
    # Spanish as a nice-to-have.
    (r"\b(?:latam|latin america|hispanohablante|spanish[- ]speaking)\b",
     "LATAM / Spanish-speaking"),
    (r"\blocali[sz]ation\b|\binternationali[sz]ation\b|\bi18n\b", "localization"),

    # --- From a psychology background ---
    #
    # This does not open coaching roles. It opens the lane where psychology and
    # applied AI already overlap. Model behaviour and character work at the labs
    # is the study of why a system responds as it does and how to shape it —
    # the same question psychology asks about people, aimed at a model. These
    # roles hire for the combination rather than for years served.
    # Model behaviour, AI character and conversation design moved to
    # BUILDER_PATTERNS (core) on 2026-10-08; see the note there.
    # Bare "Character Designer/Lead" stays here (adjacent): on most boards it is
    # an illustration job in games, not AI character work.
    (r"\bcharacter\s+(?:designer|lead)\b", "AI character"),
    (r"\bhuman[- ](?:ai|computer|machine)\s+interaction\b|\bhci\b",
     "human-AI interaction"),
    (r"\bbehaviou?ral\s+(?:scien(?:ce|tist)|research(?:er)?|design(?:er)?)\b",
     "behavioural science"),

    # --- Outside software and AI entirely, opened 2026-09-28 ---
    #
    # Read off the operator's résumé rather than off job-board taxonomy:
    # stakeholder management, encoding judgment into a process, and building
    # things a non-technical person can own. Those describe operations,
    # partnership and community work as exactly as they describe engineering.
    # None of these lanes need coding, all are remote-normal, and most hire
    # generalists rather than years.

    # Operations. Encoding judgment into a process someone else can run is the
    # literal job. Scoped to prefixed forms: a bare "Operations Manager" pulls
    # in restaurant and warehouse floors, which the remote gate would catch but
    # only after they had crowded the pool.
    (r"\b(?:business|revenue|product|design|program|partner|strategy)\s+operations\b|"
     r"\brev\s?ops\b|\bbiz\s?ops\b", "business operations"),
    (r"\b(?:technical\s+)?(?:program|project)\s+manager\b|\bprogram\s+lead\b|"
     r"\bproject\s+coordinator\b|\btpm\b", "program management"),

    # Partnerships, post-sale only. "Partner Success" and "Alliances" are
    # relationship work; the off-lane quota rule still catches Account
    # Executive, Account Development and the rest of the closing titles, which
    # is the distinction that matters here.
    (r"\bpartner(?:ships?)?\s+(?:manager|success|lead|associate|operations)\b|"
     r"\balliances?\s+(?:manager|lead|director)\b", "partnerships"),

    # Community. Direct human contact plus permission to go beyond the script;
    # this is that job with a budget line.
    # Distinct from the marketing off-lane rule, which is about campaigns.
    (r"\bcommunity\s+(?:manager|lead|specialist|associate|builder|operations|advocate)\b|"
     r"\bcommunity\s+engagement\b", "community"),
    # Creator success, added 2026-10-08: post-sale relationship work with
    # creators on AI and creative tools (no quota; the off rule still catches
    # sales titles).
    (r"\bcreator\s+(?:success|partnerships?|experience|support)\b", "creator success"),

    # Quality. Preflight checks, crash handling and approval gates are the
    # operator's own working habits. QA hires on care and
    # thoroughness rather than years, and is one of the genuinely
    # entry-accessible remote lanes.
    (r"\b(?:qa|quality\s+assurance)\s+"
     r"(?:analyst|specialist|engineer|lead|associate|tester)\b|"
     r"\bsoftware\s+tester\b|\btest\s+engineer\b", "quality assurance"),

    # Global mobility and relocation. Employer-of-record companies are
    # structurally remote-first with LATAM operations that make Spanish a hiring
    # asset.
    (r"\bglobal\s+mobility\b|"
     r"\brelocation\s+(?:specialist|consultant|manager|advisor|coordinator)\b|"
     r"\bimmigration\s+(?:specialist|coordinator|analyst)\b", "global mobility"),

    # Concierge / member / guest services removed 2026-10-08 with the
    # hospitality lane (see the note in CORE_PATTERNS).

    # Patient advocacy and care navigation, from the same support background.
    # The clinical off-lane rule still blocks nurse, therapist and physician
    # roles, which need licences the operator does not have. Pay here is often
    # thin; the pay floor filters that without needing a rule.
    (r"\b(?:patient|care|member)\s+(?:advocate|navigator|guide)\b|"
     r"\bcare\s+(?:navigation|coordinator)\b", "patient advocacy"),
]

# Roles that are structurally not available to the operator, or that the
# operator has said they do not want. Each entry has a stated reason rather
# than general taste — see the comments.
OFF_PATTERNS = [
    # Never worked on an engineering team, which is exactly what senior pure-eng
    # postings screen for. Because core is tested first, this only catches
    # senior engineering titles OUTSIDE the target lane — "Senior Solutions Engineer"
    # stays core, "Tech Lead Full-Stack Rails Engineer" does not. Plain
    # "Software Engineer" is absent on purpose: no seniority marker, no gate.
    (r"\b(?:senior|sr\.?|staff|principal|lead)\b[^,]{0,50}\b(?:engineer|developer)\b",
     "senior pure engineering"),
    (r"\b(?:engineering|software)\s+manager\b", "engineering management"),
    # Senior product management. Plain "Product Manager" is left at stretch —
    # it is not the target, but it is not unreachable at a small company.
    (r"\bgroup\s+product\s+manager\b|"
     r"\b(?:senior|principal|staff|lead|head|director)\s+product\s+manager\b",
     "senior product management"),
    # Legal.
    (r"\b(?:counsel|attorney|lawyer|paralegal|legal)\b", "legal"),
    # Finance and accounting.
    # `accountant` alone missed "Accounting Specialist - LATAM @ cloudbeds",
    # which reached the 2026-09-29 digest: the noun is "accounting", the rule
    # only knew the person. Same adjacency class as the SDR and campaign-manager
    # misses of August — the words were right and the form was wrong.
    (r"\b(?:fp&a|finops|controller|account(?:ant|ing)|bookkeep|treasury|actuar)\w*\b",
     "finance/accounting"),
    (r"\b(?:finance|financial|tax)\s+(?:manager|director|analyst|lead)\b", "finance"),
    # "Manager - India Tax & Operations" printed on 2026-08-17. The pattern
    # above needs tax IMMEDIATELY before the seniority word; the real title
    # puts it after. No target role has "tax" in the title, so the bare
    # word is safe to block.
    (r"\btax\b", "tax"),
    # Analyst roles — reporting on a business rather than building for it.
    (r"\b(?:business intelligence|bi|data)\s+analyst\b", "analyst"),
    # Non-technical leadership. Checked after core, so "Director of Solutions
    # Engineering" is still core.
    (r"\b(?:chief|c[teofi]o|vp|vice president)\b", "executive"),
    # Director with a scope word in front of it is executive hiring, whatever
    # the function. "Senior Director, Data Platform and AI" and "Regional
    # Director of Customer Success" both printed on 2026-08-17 — the first
    # unrecognised, the second matched by the `customer success` adjacent rule.
    # Core is still tested first, so "Director of Solutions Engineering" — a
    # target lane — stays core.
    (r"\b(?:senior|sr\.?|regional|global|group|executive|managing)\s+director\b",
     "senior/regional director"),
    (r"\b(?:director|head)\s+of\s+[^,]{0,30}\b(?:product|design|marketing|"
     r"finance|people|operations|hr|talent|communications?)\b",
     "non-technical director"),

    # Occupational health and safety, added 2026-09-29. The program-management
    # lane opened the day before matches any "<X> Program Manager", and "Health
    # & Safety Program Manager @ okta" reached the digest through it. Safety
    # programme work is a licensed compliance discipline, not the stakeholder
    # management the target lanes are about. Blocked here rather than by narrowing
    # the program pattern, because the problem is the domain and not the noun.
    (r"\bhealth\s*(?:&|and)\s*safety\b|\behs\b|\boccupational\s+health\b|"
     r"\bsafety\s+(?:manager|specialist|officer|coordinator)\b", "health & safety"),
    # Physical and brand design. Digital design is plausible (derived lanes);
    # brand and graphic work is a different job.
    (r"\b(?:brand|graphic|visual|motion|industrial|packaging)\s+designer\b", "brand/graphic design"),
    # Design leadership, same judgement as the designer patterns above: design
    # leadership needs years of practice as a designer.
    # "Creative Director @ Coinbase" carried an ecosystem signal and so earned
    # a main-lane slot once stretch had to bring a reason — the signal was real,
    # the role was not.
    (r"\b(?:creative|art|design)\s+director\b", "creative/design leadership"),
    # Quota-carrying sales. A hard exclusion set by the operator.
    # "Sales Development Representative" reached the main lane on 2026-08-17:
    # the list held both "sales representative" and "sdr", but the real title
    # puts a word BETWEEN them, so neither fired. Same adjacency failure as
    # "Campaign Manager - SEO & AI Content" the day before.
    (r"\b(?:account executive|account development|"
     r"sales\s+(?:development\s+|solutions?\s+)?(?:rep|representative|manager|director)|"
     r"sdr|bdr|business development rep)\w*\b", "quota sales"),
    # Go-to-market leadership is quota sales with a newer name. Scoped to
    # leadership titles so a "GTM Engineer" — a genuinely technical role — is
    # left in stretch rather than blocked.
    (r"\b(?:gtm|go[- ]to[- ]market)\s+(?:lead|manager|director|head|leader)\b",
     "go-to-market leadership"),
    # Marketing.
    (r"\b(?:marketing|growth|seo|social media|content)\s+"
     r"(?:manager|lead|director|specialist|marketer)\b|"
     # "Campaign Manager - SEO & AI Content" reached the digest on 2026-08-16:
     # the words were all present but never adjacent.
     r"\bcampaign manager\b|\b(?:seo|sem|ppc|paid media|demand gen(?:eration)?)\b",
     "marketing"),
    # People functions. Four of these printed in the 2026-08-17 digest —
    # "Strategic People Partner" and "Regional HR & People Operations
    # Specialist" both landed in `stretch`, because the list knew "people ops"
    # but not "people operations", and knew "human resources" but not "HR".
    (r"\b(?:recruiter|recruiting|talent acquisition|human resources)\b|"
     r"\bhr\b|"
     r"\bpeople\s+(?:ops|operations|partner|team|experience|success)\b|"
     r"\b(?:people|hr)\s+business partner\b", "recruiting/HR"),
    # Teaching — excluded by the operator's preference.
    (r"\b(?:instructor|trainer|teacher|curriculum|tutor)\b|"
     r"\blearning and development\b|\bl&d\b", "teaching"),
    # Physical, retail and field work. These leak into remote feeds constantly
    # — RemoteOK surfaced a U-Haul "Detail Specialist" and three Australian
    # store-manager posts on 2026-08-15. Not remote, not the lane, not close.
    (r"\b(?:store|branch|restaurant|retail|shift)\s+manager\b|\bstore associate\b|"
     r"\b(?:shop|sales|retail|store)\s+assistant\b|\bshop floor\b",
     "retail"),
    (r"\b(?:detail specialist|technician|mechanic|driver|warehouse|"
     r"cashier|barista|server|cleaner|janitor|housekeep)\w*\b", "field/manual work"),
    (r"\b(?:nurse|nursing|caregiver|therapist|physician|pharmac)\w*\b", "clinical"),
    # Writing and editorial. Not the job being searched for, and these postings
    # crowd out the ones that are.
    (r"\b(?:freelance\s+)?(?:writer|copywriter|editor|journalist|"
     r"content creator)\b", "writing"),
]

_CORE = [(re.compile(p, re.I), label) for p, label in CORE_PATTERNS]
_DEMOTED = [(re.compile(p, re.I), label) for p, label in DEMOTED_PATTERNS]
_ADJACENT = [(re.compile(p, re.I), label) for p, label in ADJACENT_PATTERNS]
_PROTECTED_ADJACENT = [
    (re.compile(p, re.I), label) for p, label in PROTECTED_ADJACENT_PATTERNS
]
# Three of the derived patterns share a word with an off-lane rule written for
# a different job, and only these three. They are checked before the off list;
# everything else derived is checked AFTER it.
#
# Why the split, added 2026-09-28 after the whole derived group ran first and
# broke the most important filter in the file: "Channel Account Executive,
# LATAM @ Asana" reached the main digest. Account Executive is quota sales —
# a hard exclusion, on the off list since the beginning — and the
# LATAM pattern matched first, so classify() returned adjacent and never
# reached it. A pattern meant to surface Spanish-speaking roles was laundering
# every off-lane role that happened to mention the region.
#
# The rule this encodes: a lane may be widened, never at the cost of an
# exclusion. Same failure as the 2026-08-17 senior-engineering gate catching
# "Senior Red Team Engineer" — ordering IS the rule set, so every reordering
# has to be justified one pattern at a time, not in a block.
# Checked BEFORE everything, including core. A language requirement is not a
# lane question, it is a can-the-operator-do-the-job question, and those come first.
#
# Added 2026-09-29 after two roles reached the digest asking for a language the
# operator does not speak: "Amharic Language Specialist - Freelance AI Trainer Project @
# Invisible Technologies" and "Presales Engineer (German speaker) @ twilio".
# The first arrived through the AI-training carve-out and the second through
# the core sales-engineer rule - different doors, same miss - and putting the
# rule in OFF_PATTERNS fixed only the second, because COLLISION_PATTERNS and
# CORE_PATTERNS are both tested earlier.
#
# That is the third time in two days that ordering, not matching, was the bug.
# The lesson is now structural rather than a comment: eligibility outranks
# preference, so it gets its own list at the top of classify().
#
# The operator speaks Spanish and English. Both are deliberately absent below -
# those titles should rank HIGHEST, and prefilter.BILINGUAL_BONUS pays them.
# Edit this list for the languages you speak.
HARD_BLOCK_PATTERNS = [
    # A posting written in Portuguese, added 2026-09-29 after the guard built
    # an hour earlier failed on the listing that prompted it:
    #
    #   "Grupo QuintoAndar | Vaga afirmativa para PcD - Analista de Business
    #    Operations (Remoto)"
    #
    # The first attempt only withdrew the bilingual BONUS, and even that missed:
    # QuintoAndar operates in Mexico as well as Brazil, so the description named
    # Spanish-speaking countries and outvoted the Portuguese title. Treating it
    # as a scoring question was the mistake. The operator cannot read the posting, which
    # makes it the same kind of fact as a language requirement, so it belongs
    # here with them.
    #
    # Discriminating on characters and words Spanish does not have. "Analista"
    # and "Remoto" are shared by both languages and deliberately absent; ç, ã
    # and õ are Portuguese only, and "vaga", "PcD" and "desenvolvedor" are
    # Portuguese where Spanish says vacante, PcD is unused, and desarrollador.
    (r"[çãõ]|\bvaga\b|\bpcd\b|\bdesenvolvedor\b|\best[aá]gio\b|"
     r"\bpessoa com defici", "posting written in Portuguese"),
    (r"\b(?:amharic|hausa|swahili|yoruba|igbo|zulu|afrikaans|somali|"
     r"arabic|hebrew|farsi|persian|pashto|urdu|turkish|kurdish|"
     r"hindi|bengali|tamil|telugu|marathi|gujarati|punjabi|kannada|malayalam|"
     r"nepali|sinhala|burmese|khmer|lao|thai|vietnamese|tagalog|filipino|"
     r"indonesian|malay|mongolian|japanese|korean|mandarin|cantonese|chinese|"
     r"german|french|italian|dutch|flemish|portuguese|brazilian portuguese|"
     r"russian|ukrainian|polish|czech|slovak|hungarian|romanian|bulgarian|"
     r"serbian|croatian|greek|swedish|norwegian|danish|finnish|icelandic|"
     r"estonian|latvian|lithuanian)\b", "language the operator does not speak"),
]

COLLISION_PATTERNS = [
    (r"\bchief\s+of\s+staff\b", "chief of staff"),
    (r"\btechnical\s+writer?\b|\btechnical\s+writing\b|"
     r"\bdocumentation\s+(?:engineer|specialist|lead|manager)\b|\bdocs\s+engineer\b",
     "technical writing"),
    (r"\bai\s+(?:trainer|tutor)\b|\b(?:llm|model)\s+trainer\b", "AI training"),
    # 2026-10-08: writing an AI's character is not the editorial writing the
    # `writer` off rule blocks.
    (r"\b(?:ai|character|persona|personality|dialogue)\s+writer\b", "AI character"),
]

# Builder and creative-tech lanes, opened 2026-10-01: a problem handed over, the
# solution built by the operator. That is what the operator's portfolio already
# is, so these rank as core.
#
# Checked AFTER the off list, unlike the rest of core. "AI Automation Sales
# Representative" must stay quota sales, and "Senior AI Agent Engineer" must
# stay senior. A lane may be widened, never at the cost of an exclusion.
BUILDER_PATTERNS = [
    (r"\bai\s+(?:automation|builder|enablement|adoption|agents?)\b|"
     r"\b(?:automation|workflow|no-?code|low-?code)\s+"
     r"(?:specialist|developer|builder|consultant|architect|lead|engineer)\b|"
     r"\bagent\s+(?:builder|developer)\b|\binternal\s+tools?\b",
     "AI builder"),
    # AI Operations promoted from derived (adjacent) to core 2026-10-08: it is
    # one of the operator's three target families. The field is ~2 years old,
    # so nobody has 5 years of it and the portfolio is the credential. Business
    # Systems only counts with an AI or automation word in the title: bare
    # "Business Systems Analyst" is Salesforce/Workday admin, not the target work.
    (r"\bai\s+(?:operations|ops)\b|\bagent\s+(?:engineer|ops|operations)\b|"
     r"\b(?:ai|automation)\b.*\bbusiness\s+systems\b|"
     r"\bbusiness\s+systems\b.*\b(?:ai|automation)\b",
     "AI operations"),
    # AI customer-service operations, opened 2026-10-08. Support teams are
    # swapping queues for AI agents and someone has to design, tune and run
    # them: prior support work plus agent-building.
    # Contact-centre and workforce-management titles are deliberately absent:
    # those are staffing a phone floor, not building the system.
    (r"\b(?:support|cx|customer\s+(?:support|experience|service))\s+"
     r"(?:operations|ops|systems|automation|tooling|engineer(?:ing)?)\b|"
     r"\bconversational\s+(?:ai|design(?:er)?|experience)\b|\bchat\s?bot\b|"
     r"\bai\s+(?:support|cx|customer\s+(?:support|experience|service))\b|"
     r"\bknowledge\s+(?:base|management)\s+(?:specialist|manager|lead|engineer)\b",
     "AI customer-service ops"),
    # Human-AI design, promoted from derived (adjacent) to core 2026-10-08.
    # Shaping how an AI talks, what it notices and how it handles a hard moment
    # is people-reading aimed at a model, and it is a new field that hires for
    # the mix of people skills and writing.
    (r"\bmodel\s+behaviou?r\b|\bai\s+behaviou?r\b", "model behaviour"),
    (r"\bai\s+(?:character|persona(?:lity)?)\b|\bpersonality\s+designer\b",
     "AI character"),
    (r"\bconversation(?:al)?\s+(?:design(?:er)?|architect)\b|"
     r"\bprompt\s+design(?:er)?\b|\bai\s+content\s+design(?:er)?\b",
     "conversation design"),
    # Knowledge and context engineering: building knowledge bases with a
    # routing layer for an AI assistant. And AI change / transformation:
    # the adoption half of AI enablement, people-first.
    (r"\b(?:knowledge|context|ontology)\s+engineer(?:ing)?\b|"
     r"\bknowledge\s+(?:manager|management)\b",
     "knowledge / context engineering"),
    (r"\bai\s+(?:change|transformation|champion|literacy|fluency)\b|"
     r"\bchange\s+management\b.*\bai\b|\bai\b.*\bchange\s+management\b",
     "AI adoption"),
    (r"\bcreative\s+(?:technologist|technology|engineer|developer)\b|"
     r"\b(?:ai|generative|genai)\s+(?:creative|artist|designer|video|filmmaker|"
     r"art\s+director|content\s+producer)\b|\bprototyper\b",
     "creative technologist"),
]

_HARD_BLOCK = [(re.compile(p, re.I), label) for p, label in HARD_BLOCK_PATTERNS]
_BUILDER = [(re.compile(p, re.I), label) for p, label in BUILDER_PATTERNS]
_COLLISION = [(re.compile(p, re.I), label) for p, label in COLLISION_PATTERNS]
_DERIVED = [(re.compile(p, re.I), label) for p, label in DERIVED_PATTERNS]
_OFF = [(re.compile(p, re.I), label) for p, label in OFF_PATTERNS]


# Seniority, added 2026-09-28. A digest arrived where six of eighteen roles
# were Senior, Sr. or Staff, for an operator who is early in a new career.
#
# The cause was a deliberate exemption: classify() tests core
# before off precisely so that "Senior Solutions Engineer" stays in the lane
# rather than being thrown out with "Senior Software Engineer". That exemption
# protected the lane and lost the level.
#
# A separate axis fixes it without undoing that. Lane answers "is this the
# right kind of work"; this answers "can the operator get it this year". Kept as a
# penalty rather than a gate because the word means different things at
# different companies: Senior Solutions Engineer at a fifteen-person startup
# is a real shot, Sr. Forward Deployed Engineer at Databricks is not. Company
# shape decides that, and company.py already scores company shape.
SENIORITY_PENALTY = -4
ENTRY_BONUS = 3

_SENIOR_RE = re.compile(
    r"\b(?:senior|sr\.?|staff|principal|distinguished|lead)\b", re.I
)
# "Lead Generation Specialist" is not a senior role. Nor is a "Technical Lead
# Generation" anything. Guard the one common false positive rather than drop
# `lead`, which really does mark seniority in "Lead Solutions Engineer".
_LEAD_FALSE_POSITIVE = re.compile(r"\blead\s+gen(?:eration)?\b", re.I)

# The other half, and the more useful one: titles that say out loud they will
# take someone without the years. The operator is explicitly open to roles
# requiring no prior experience, and nothing in the scorer acted on that until
# now.
_ENTRY_RE = re.compile(
    r"\b(?:junior|jr\.?|entry[- ]level|associate|apprentice|trainee|"
    r"new\s+grad(?:uate)?|graduate|early\s+career|no\s+experience)\b",
    re.I,
)


def seniority(title):
    """
    Return (points, tag) for the level named in the title.

    tag is None when the title says nothing about level, which is the common
    and desirable case — an unmarked "Solutions Engineer" is exactly the rung
    the operator is aiming at.
    """
    text = (title or "").strip()
    if not text:
        return 0, None
    if _ENTRY_RE.search(text):
        return ENTRY_BONUS, "entry-friendly"
    if _SENIOR_RE.search(text) and not _LEAD_FALSE_POSITIVE.search(text):
        return SENIORITY_PENALTY, "senior-titled"
    return 0, None


def classify(title):
    """
    Return (lane, label).

    Order is the rule set. Core is tested before off so that a senior or
    director-level role inside the operator's own lane stays core — "Senior
    Solutions Engineer" is a target job, "Senior Software Engineer" is not.
    """
    text = (title or "").strip()
    if not text:
        return LANE_STRETCH, "no title"

    # Eligibility before preference: a job needing a language the operator
    # cannot speak is out, whatever the title otherwise says.
    for pattern, label in _HARD_BLOCK:
        if pattern.search(text):
            return LANE_OFF, label

    for pattern, label in _CORE:
        if pattern.search(text):
            return LANE_CORE, label

    for pattern, label in _DEMOTED:
        if pattern.search(text):
            return LANE_ADJACENT, label

    for pattern, label in _PROTECTED_ADJACENT:
        if pattern.search(text):
            return LANE_ADJACENT, label

    # Only the three genuine collisions run before off: "Chief of Staff" with
    # `chief`, "Technical Writer" with `writer`, "AI Trainer" with `trainer`.
    # Each is a different job wearing the same word.
    for pattern, label in _COLLISION:
        if pattern.search(text):
            return LANE_ADJACENT, label

    # Off comes next, and nothing derived may jump it. It holds the exclusions
    # that exist for reasons other than taste — quota sales above all.
    for pattern, label in _OFF:
        if pattern.search(text):
            return LANE_OFF, label

    for pattern, label in _BUILDER:
        if pattern.search(text):
            return LANE_CORE, label

    # The rest of the derived lanes, now safely after the exclusions. A
    # Spanish-speaking quota-sales role is a quota-sales role.
    for pattern, label in _DERIVED:
        if pattern.search(text):
            return LANE_ADJACENT, label

    for pattern, label in _ADJACENT:
        if pattern.search(text):
            return LANE_ADJACENT, label

    return LANE_STRETCH, "unrecognised role"


# Words that make a title recognisably a job. Used only to keep non-jobs out of
# the main lane: RemoteOK carries product-directory rows from "AI Supermarket"
# whose titles are just product names ("Jenni AI", "Typefully"), and those took
# three main-lane slots on 2026-08-15.
ROLE_NOUNS = re.compile(
    r"\b(?:engineer|engineering|developer|architect|manager|specialist|analyst|"
    r"designer|consultant|coordinator|associate|representative|writer|scientist|"
    r"administrator|technician|officer|advocate|strategist|marketer|recruiter|"
    r"accountant|counsel|assistant|intern|lead|director|head|chief|president|"
    r"support|success|operations|ops|sales|marketing|product|programmer|"
    r"advisor|agent|partner|staff|contractor|freelancer|copywriter|editor|"
    r"researcher|trainer|teacher|nurse|driver|clerk|steward|host|guide)\b",
    re.I,
)


# Work the operator could plausibly do, read off the TITLE. Used only to decide whether an
# unrecognised (`stretch`) title has earned a main-lane slot.
#
# The ecosystem and training signals are matched against the whole posting, so
# they describe the EMPLOYER, not the job: "GRC Analyst @ Vercel" and "Manager,
# Account Development @ Justworks" both earned slots on 2026-08-17 because their
# descriptions mention AI. That is the same mistake as scoring a role by its
# company category — an AI company hiring a compliance analyst is still hiring a
# compliance analyst.
#
# Same discipline as classify(): title only. Deliberately narrow, because this
# is the gate for roles the system could not identify at all.
RELEVANT_WORK = re.compile(
    r"\b(?:ai|a\.i\.|ml|llm|genai|agent|agentic|automation|autonomous|"
    r"technical|engineer|engineering|developer|platform|integration|"
    r"solutions?|implementation|deployment|data|prompt|api|infrastructure|"
    r"support|success|onboarding)\b",
    re.I,
)


def title_shows_relevant_work(title):
    """True when the title itself names work in or near the target lane."""
    return bool(RELEVANT_WORK.search(title or ""))


def looks_like_a_role(title):
    """
    True when the title names a job rather than a product or a location.

    Deliberately generous — this is a floor, not a filter. Anything that trips
    it is a listing we cannot even confirm is a job, and those do not belong in
    the lane the operator reads first.
    """
    return bool(ROLE_NOUNS.search(title or ""))


def score(title):
    """
    Return (points, lane, label) for the prefilter score sum.

    Points carry both axes: which lane the work is in, and whether the title
    names a level the operator can realistically reach this year. Off-lane is
    left alone — an unwanted role is not made more wanted by being junior.
    """
    lane, label = classify(title)
    points = LANE_SCORE[lane]
    if lane != LANE_OFF:
        level_points, _ = seniority(title)
        points += level_points
    return points, lane, label


def is_off_lane(lane):
    """Roles that must never reach the main digest, whatever they pay."""
    return lane == LANE_OFF
