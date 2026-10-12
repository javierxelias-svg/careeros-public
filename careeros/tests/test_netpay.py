#!/usr/bin/env python3
"""
Take-home estimates under netpay.py's example tax schedule.

The anchor is a figure worked out by hand from the published schedule:
$150k gross nets roughly $100,900. Any model that disagrees with that by much
is wrong.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import netpay  # noqa: E402


def main():
    failures = []

    print("=== the anchor: $150k nets ~$100,900 ===")
    net = netpay.net_annual(150_000)
    ok = 99_000 <= net <= 104_000
    print(f"  [{'PASS' if ok else 'FAIL'}] $150,000 -> ${net:,.0f} (want 99k-104k)")
    if not ok:
        failures.append(f"$150k netted {net:,.0f}, outside the established band")

    # Each of these drives a real decision: a pay floor, and the two scoring
    # marks in prefilter.py. If the net is wrong, every budget built on it is.
    print("\n=== the numbers decisions are made on ===")
    cases = [
        (70_000,  52_000,  57_000, "a low example floor"),
        (95_000,  67_000,  72_000, "prefilter.STRONG_PAY"),
        (120_000, 82_000,  87_000, "prefilter.GREAT_PAY"),
        (150_000, 99_000, 104_000, "the hand-checked anchor"),
    ]
    for gross, lo, hi, why in cases:
        net = netpay.net_annual(gross)
        rate = netpay.effective_rate(gross)
        ok = lo <= net <= hi
        print(f"  [{'PASS' if ok else 'FAIL'}] ${gross:>7,} -> ${net:>8,.0f} "
              f"({rate:.0%} to tax)  {why}")
        if not ok:
            failures.append(f"${gross:,} netted {net:,.0f}, wanted {lo:,}-{hi:,}")

    print("\n=== monotonic: more gross always means more net ===")
    nets = [netpay.net_annual(g) for g in range(20_000, 300_000, 5_000)]
    ok = all(b > a for a, b in zip(nets, nets[1:]))
    print(f"  [{'PASS' if ok else 'FAIL'}] net rises across $20k-$300k")
    if not ok:
        failures.append("net pay is not monotonic in gross — bracket bug")

    print("\n=== effective rate never exceeds the top marginal rate ===")
    worst = max(netpay.effective_rate(g) for g in range(20_000, 400_000, 10_000))
    ok = worst < 0.41   # 32% top bracket + 7.65% FICA, before the additional Medicare
    print(f"  [{'PASS' if ok else 'FAIL'}] peak effective rate {worst:.1%}")
    if not ok:
        failures.append(f"effective rate hit {worst:.1%}, implausible")

    print("\n=== FICA is charged on every dollar Medicare touches ===")
    # The example model zeroes federal income tax, never FICA. A model that zeroed FICA
    # would overstate every take-home figure by about eight percent.
    ok = netpay.fica(100_000) > 7_000
    print(f"  [{'PASS' if ok else 'FAIL'}] FICA on $100k = ${netpay.fica(100_000):,.0f}")
    if not ok:
        failures.append("FICA looks unapplied")

    # Social Security stops at the wage base; Medicare does not.
    below = netpay.fica(netpay.SOCIAL_SECURITY_WAGE_BASE)
    above = netpay.fica(netpay.SOCIAL_SECURITY_WAGE_BASE + 50_000)
    marginal = (above - below) / 50_000
    ok = 0.014 <= marginal <= 0.024
    print(f"  [{'PASS' if ok else 'FAIL'}] above the SS wage base, marginal "
          f"FICA falls to {marginal:.2%}")
    if not ok:
        failures.append(f"SS wage base cap not applied: marginal {marginal:.2%}")

    print("\n=== guards ===")
    for bad in (None, 0, -5_000):
        ok = netpay.net_annual(bad) is None and netpay.summary(bad) is None
        print(f"  [{'PASS' if ok else 'FAIL'}] {bad!r} -> None, not a crash")
        if not ok:
            failures.append(f"net_annual({bad!r}) did not return None")

    print("\n=== the line the digest prints ===")
    print(f"  $95,000  ->  {netpay.summary(95_000)}")
    print(f"  $120,000 ->  {netpay.summary(120_000)}")

    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED {len(failures)}")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL NETPAY TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
