#!/usr/bin/env python3
"""Fail-closed preflight for E2E-owned endpoint allocation (never a product limit).

Call with actual, current public-CLI-derived counts immediately before a
namespaced E2E allocation batch. All lanes sharing the same test Server must be
accounted for. This preflight does not perform allocations or prove a PASS.
"""
from __future__ import annotations

import argparse
import json

E2E_MAX_SIMULTANEOUS_ALLOCATED_PORTS = 30


def nonnegative(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected an integer") from exc
    if number < 0:
        raise argparse.ArgumentTypeError("counts must be nonnegative")
    return number


def evaluate(
    *,
    active_owned: int,
    other_e2e_owned: int,
    planned_new: int,
    expect_full_pool: bool,
    pool_capacity: int | None,
    pool_active_after_plan: int | None,
) -> dict[str, int | str | bool]:
    if min(active_owned, other_e2e_owned, planned_new) < 0:
        raise ValueError("negative allocation counts are invalid")
    total = active_owned + other_e2e_owned + planned_new
    reasons: list[str] = []
    if total > E2E_MAX_SIMULTANEOUS_ALLOCATED_PORTS:
        reasons.append("AGGREGATE_E2E_PORT_BUDGET_EXCEEDED")
    if expect_full_pool:
        if pool_capacity is None or pool_active_after_plan is None:
            reasons.append("POOL_EXHAUSTION_PRECONDITION_UNVERIFIED")
        elif not 1 <= pool_capacity <= E2E_MAX_SIMULTANEOUS_ALLOCATED_PORTS:
            reasons.append("NATIVE_POOL_TOO_LARGE_FOR_BOUNDED_EXHAUSTION")
        elif pool_active_after_plan > total:
            reasons.append("POOL_CAPACITY_NOT_OWNED_BY_E2E_LANES")
        elif pool_active_after_plan != pool_capacity:
            reasons.append("ISOLATED_POOL_NOT_AT_CONFIGURED_CAPACITY")
    return {
        "status": "DENY" if reasons else "ALLOW",
        "reason": ",".join(reasons) if reasons else "BUDGET_WITHIN_LIMIT",
        "budget": E2E_MAX_SIMULTANEOUS_ALLOCATED_PORTS,
        "observed_active_owned": active_owned,
        "observed_other_e2e_owned": other_e2e_owned,
        "planned_new": planned_new,
        "projected_total": total,
        "expect_full_pool": expect_full_pool,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--active-owned", type=nonnegative, required=True,
                        help="observed current test-run reservations, including pending")
    parser.add_argument("--other-e2e-owned", type=nonnegative, required=True,
                        help="observed reservations from other E2E lanes on the same Server")
    parser.add_argument("--planned-new", type=nonnegative, required=True,
                        help="all additional expected live endpoint allocations in this batch")
    parser.add_argument("--expect-full-pool", action="store_true",
                        help="require genuinely full isolated pool with capacity at most 30")
    parser.add_argument("--pool-capacity", type=nonnegative)
    parser.add_argument("--pool-active-after-plan", type=nonnegative)
    args = parser.parse_args()
    result = evaluate(
        active_owned=args.active_owned,
        other_e2e_owned=args.other_e2e_owned,
        planned_new=args.planned_new,
        expect_full_pool=args.expect_full_pool,
        pool_capacity=args.pool_capacity,
        pool_active_after_plan=args.pool_active_after_plan,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "ALLOW" else 2


if __name__ == "__main__":
    raise SystemExit(main())
