"""
Example take-home pay model.

Gross pay alone misleads: a published salary says nothing about what is left
after tax, and a digest that prints only the gross number quietly overstates
every listing. This module turns gross into an estimated net figure.

It ships with a MADE-UP example rate schedule: a W-2 salary with no federal
income tax, a local progressive schedule whose 32% top bracket starts at
$48,000, plus US FICA (Social Security and Medicare).
Replace INCOME_TAX_BRACKETS and PERSONAL_EXEMPTION with your own schedule.

The model, and its limits:

  - Federal income tax is modelled as zero for this example jurisdiction, so
    the local 32% is not softened by anything.
  - FICA is always charged. It is the one payroll tax that applies wherever
    a US W-2 employee works.
  - Regular rates only. No alternate minimum tax, no high-income recapture,
    no dependents, no itemised deductions, no special incentive regimes.
  - Single filer, standard personal exemption.

So this is a planning figure, deliberately on the conservative side of exact.
It is labelled "est." everywhere it prints, and it is not tax advice.
"""

# EXAMPLE schedule, made up for illustration (not any real jurisdiction), single filer. (threshold, base tax at threshold, marginal)
INCOME_TAX_BRACKETS = (
    (0,      0,     0.00),
    (8_000,  0,     0.06),
    (24_000, 960,   0.16),
    (48_000, 4_800, 0.32),
)

PERSONAL_EXEMPTION = 3_000

SOCIAL_SECURITY_RATE = 0.062
SOCIAL_SECURITY_WAGE_BASE = 176_100
MEDICARE_RATE = 0.0145
ADDITIONAL_MEDICARE_RATE = 0.009
ADDITIONAL_MEDICARE_THRESHOLD = 200_000


def income_tax(gross):
    """Income tax on a W-2 salary under the example schedule, single filer."""
    taxable = max(0.0, gross - PERSONAL_EXEMPTION)
    threshold, base, rate = INCOME_TAX_BRACKETS[0]
    for t, b, r in INCOME_TAX_BRACKETS:
        if taxable > t:
            threshold, base, rate = t, b, r
        else:
            break
    return base + (taxable - threshold) * rate


def fica(gross):
    """
    Social Security and Medicare. Charged on US W-2 wages regardless of where
    the employee lives, so it is never zeroed.
    """
    ss = min(gross, SOCIAL_SECURITY_WAGE_BASE) * SOCIAL_SECURITY_RATE
    medicare = gross * MEDICARE_RATE
    if gross > ADDITIONAL_MEDICARE_THRESHOLD:
        medicare += (gross - ADDITIONAL_MEDICARE_THRESHOLD) * ADDITIONAL_MEDICARE_RATE
    return ss + medicare


def net_annual(gross):
    """Estimated annual take-home for a W-2 employee under the example schedule."""
    if not gross or gross <= 0:
        return None
    return gross - income_tax(gross) - fica(gross)


def net_monthly(gross):
    """Estimated monthly take-home — the unit most people budget in."""
    net = net_annual(gross)
    return None if net is None else net / 12


def effective_rate(gross):
    """Share of gross lost to income tax plus FICA."""
    net = net_annual(gross)
    return None if not net else 1 - (net / gross)


def summary(gross):
    """
    One short line for the digest, or None when there is nothing to say.

    Deliberately reports the monthly figure as well as the annual: budgets are
    monthly, and "$5,800/mo" lands where "$69,400" does not.
    """
    net = net_annual(gross)
    if net is None:
        return None
    return (
        f"≈ ${net:,.0f}/yr net · ${net / 12:,.0f}/mo "
        f"(example tax model, est. {effective_rate(gross):.0%} to tax)"
    )
