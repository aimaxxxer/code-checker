#!/usr/bin/env python3
"""End-to-end check of the pipeline in whatever mode credentials allow."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from product_scout.pipeline import Scout  # noqa: E402


def main() -> int:
    scout = Scout()

    print("=" * 70)
    print("PROVIDER STATUS")
    print("=" * 70)
    status = scout.status()
    for name, info in status["providers"].items():
        mark = "live" if info["configured"] else "not configured"
        print(f"  {name:22s} {mark:16s} covers: {', '.join(info['covers'])}")
    print(f"\n  live supplier data: {status['live_data_available']}")
    print(f"  retail benchmark:   {status['benchmark_available']}")

    query = sys.argv[1] if len(sys.argv) > 1 else "neck massager"
    marketplace = sys.argv[2] if len(sys.argv) > 2 else "aliexpress"

    print("\n" + "=" * 70)
    print(f"PIPELINE: {query!r} on {marketplace}")
    print("=" * 70)
    report = scout.find_winners(query, marketplace=marketplace, limit=5, candidates=20)

    print(f"  provider: {report['provider']} — {report['provider_note']}")
    bench = report.get("retail_benchmark") or {}
    print(f"  retail benchmark: median {bench.get('median_price')} "
          f"from {bench.get('sample_size')} results, {bench.get('seller_count')} sellers")
    trend = report.get("trend") or {}
    print(f"  trend: {trend.get('direction')} ({trend.get('slope_pct')}%)")
    print(f"  screened {report['candidates_screened']} candidates\n")

    for rank, row in enumerate(report["results"], 1):
        offer, score, econ = row["offer"], row["score"], row.get("economics") or {}
        print(f"  {rank}. rank={row['rank_score']:5.1f} score={score['total']:5.1f} {score['verdict']:9s} {offer['title'][:52]}")
        print(f"      cost {offer.get('price')} -> sell {row.get('suggested_sell_price')} ({row.get('pricing_basis')}) | "
              f"margin {econ.get('gross_margin_pct')}% | breakeven ROAS {econ.get('breakeven_roas')}")
        print(f"      components: " + "  ".join(f"{k}={v}" for k, v in score["components"].items()))
        print(f"      confidence: {score['confidence']}")
        if score["penalties"]:
            print(f"      PENALTY: {score['penalties'][0]}")
        risk = row.get("risk") or {}
        if risk.get("severity") not in (None, "none"):
            print(f"      RISK [{risk['severity']}]: "
                  f"{(risk.get('ip_risk') or risk.get('regulatory') or ['-'])[0][:70]}")
        print()

    if "--json" in sys.argv:
        print(json.dumps(report, indent=2, default=str)[:4000])

    assert report["results"], "pipeline returned no results"
    print("OK — pipeline ran end to end.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
