#!/usr/bin/env python3
"""Command line for the Front Office planner and sealed dispatch seam.

Planning remains static by default.  ``launch`` may dispatch only an explicitly
ready campaign/profile pair, and delegates child-process creation to the small
direct-argv adapter.  This command never owns the GPU, port 8199, or cleanup.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

import front_office
import front_office_dispatch


def _emit(value: object, as_json: bool) -> None:
    if as_json:
        print(front_office.format_json(value), end="")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            print(f"{key}: {item}")
        return
    print(value)


def _cell_reference(value: str) -> tuple[str, str]:
    if value.count("/") != 1:
        raise front_office.CampaignValidationError(
            "CELL must be exactly campaign-id/cell-id"
        )
    campaign_id, cell_id = value.split("/", 1)
    return campaign_id, cell_id


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Static-only Runner Front Office; it never starts a GPU or server."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    profiles = subparsers.add_parser("profiles", help="list enrolled profile IDs")
    profiles.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    validate = subparsers.add_parser("validate-profile", help="validate one enrolled profile")
    validate.add_argument("profile_id", help="enrolled profile ID")
    validate.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    plan = subparsers.add_parser("plan", help="build a static sealed launch plan")
    plan.add_argument("cell", metavar="CELL", help="campaign-id/cell-id")
    plan.add_argument("--profile", required=True, dest="profile_id", help="enrolled profile ID")
    plan.add_argument(
        "--write-spec",
        action="store_true",
        help="atomically write the validated static plan under .runtime/; does not launch it",
    )
    plan.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    r0 = subparsers.add_parser("r0", help="run the offline static census")
    r0.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    receipt_status = subparsers.add_parser(
        "receipt-status", help="display stale/current classifications without touching receipt bytes"
    )
    receipt_status.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    launch = subparsers.add_parser(
        "launch", help="seal and dispatch one explicitly ready campaign cell"
    )
    launch.add_argument("cell", metavar="CELL", help="campaign-id/cell-id")
    launch.add_argument("--profile", required=True, dest="profile_id", help="enrolled profile ID")
    launch.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    try:
        if args.command == "profiles":
            profiles = front_office.list_enrolled_profiles()
            _emit({"profiles": profiles, "direct_launch": "SEALED_DIRECT_DISPATCH_AVAILABLE"}, args.json)
            return 0
        if args.command == "validate-profile":
            profile = front_office.load_enrolled_profile(args.profile_id)
            _emit(
                {
                    "profile_id": profile["id"],
                    "profile_sha256": front_office.canonical_sha256(profile),
                    "status": "VALID_STATIC_ENROLLMENT",
                },
                args.json,
            )
            return 0
        if args.command == "plan":
            campaign_id, cell_id = _cell_reference(args.cell)
            spec = front_office.build_launch_spec(campaign_id, cell_id, args.profile_id)
            if args.write_spec:
                destination = front_office.write_launch_spec(spec)
                payload = {"launch_spec": spec, "written_path": str(destination)}
            else:
                payload = spec
            _emit(payload, args.json)
            return 0
        if args.command == "r0":
            _emit(front_office.r0_static_census(), args.json)
            return 0
        if args.command == "receipt-status":
            _emit(front_office.receipt_status_report(), args.json)
            return 0
        if args.command == "launch":
            campaign_id, cell_id = _cell_reference(args.cell)
            spec = front_office.build_execution_spec(campaign_id, cell_id, args.profile_id)
            destination = front_office.write_execution_spec(spec)
            child_code = front_office_dispatch.dispatch_execution_spec(destination)
            payload = {
                "status": "DISPATCHED",
                "written_path": str(destination),
                "launch_spec_sha256": spec["launch_spec_sha256"],
                "child_returncode": child_code,
            }
            _emit(payload, args.json)
            return child_code
        parser.error("unknown command")
    except front_office.FrontOfficeError as exc:
        print(f"[FRONT OFFICE ABORT] {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
