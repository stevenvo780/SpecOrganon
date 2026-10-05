#!/usr/bin/env python3
"""Explicit external Docker controller. Original provider profiles stay in place."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from specorganon import engine
from specorganon.docker_roles import DockerRoles, DockerRoleError
from specorganon.report import case_report
from specorganon.role_jobs import JobError, _read, _write
from specorganon.software_controller import Controller, ControllerError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True, help='Existing local case; never recreated on resume')
    parser.add_argument('--run-root', required=True, help='Private persistent host directory, outside provider mounts')
    parser.add_argument('--contract', required=True, help='Public delivery contract saved before generation')
    parser.add_argument('--mandate', required=True, help='Existing owner mandate; no new consent is inferred')
    parser.add_argument('--native-image', required=True, help='Inspected immutable sha256 image ID')
    parser.add_argument('--test-image', required=True, help='Inspected immutable sha256 image ID')
    parser.add_argument('--public-catalog', required=True, help='Public pinned CLI model metadata; not profile data')
    parser.add_argument('--source-root', default=str(Path(__file__).absolute().parents[1]))
    parser.add_argument('--author-provider', choices=('codex', 'gemini'), default='codex')
    parser.add_argument('--author-model', default='gpt-6.1-sol')
    parser.add_argument('--reviewer-provider', choices=('codex', 'gemini'), default='gemini')
    parser.add_argument('--reviewer-model', default='gemini-3.1-pro-high')
    parser.add_argument('--codex-volume', default='specorganon-lab_codex-home')
    parser.add_argument('--gemini-profile', default='/home/stev/.gemini')
    parser.add_argument('--gemini-executable', default='/home/stev/.local/bin/agy')
    parser.add_argument('--seccomp')
    parser.add_argument('--codex-reasoning-effort', choices=('low', 'medium', 'high', 'xhigh'),
                        default='low', help='Bounded explicit native Codex reasoning effort')
    parser.add_argument('--steps', type=int, default=1, help='Explicit bounded dispatch count, maximum80')
    args = parser.parse_args()
    if not 1 <= args.steps <= 80: parser.error('--steps must be 1..80')
    if args.author_provider == args.reviewer_provider:
        parser.error('this experiment requires genuinely separate provider roles')
    root = Path(args.run_root).absolute()
    try:
        state = engine.get_state(args.case)
        if state['project']['approval_policy'] != 'local': raise ControllerError('existing explicit local case required')
        # Read report and current task before any dispatch; bounded sources remain public.
        initial_report = case_report(args.case)
        transport = DockerRoles(root / 'transport', native_image=args.native_image,
            test_image=args.test_image, source_root=args.source_root, public_catalog=args.public_catalog,
            author_provider=args.author_provider, author_model=args.author_model,
            reviewer_provider=args.reviewer_provider, reviewer_model=args.reviewer_model,
            codex_volume=args.codex_volume, gemini_profile=args.gemini_profile,
            gemini_executable=args.gemini_executable, seccomp=args.seccomp,
            codex_reasoning_effort=args.codex_reasoning_effort)
        controller = Controller(args.case, root / 'controller', transport,
            contract=_read(args.contract, 64_000).decode(), mandate=_read(args.mandate, 16_000).decode(), executor=transport)
        _write(root / 'last-initial-report.json', initial_report)
        for _ in range(args.steps):
            result = controller.step()
            print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
            if result['action'] == 'complete':
                # This is a reviewable gate record, not implicit publication or comparative acceptance.
                _write(root / 'delivery-verdict.json', {'schema': 1, 'package_allowed': result['package_allowed'],
                    'state': engine.get_state(args.case), 'report': case_report(args.case),
                    'delivery_directory': str(controller.delivery), 'comparative_verdict': 'not evaluated'})
                return 0
        return 0
    except (ControllerError, DockerRoleError, JobError, OSError, ValueError) as exc:
        print(json.dumps({'status': 'stopped', 'reason': str(exc), 'run_root': str(root),
                          'approval': False, 'automatic_replacement': False}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__': raise SystemExit(main())
