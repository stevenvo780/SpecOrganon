# Reference check for a native coding harness

SpecOrganon already separates the external agent/executor from its artifact
ledger. `run`, `put`, `advance` and MCP do not execute application code. This
check connects the existing CLI, synthetic workflow and local receipt contract
to a tiny real code fixture, with retained evidence suitable for review.
It adds acceptance coverage, not another runner or engine feature.

## Run without installing anything

From a checkout with the repository dependencies already available:

```sh
python scripts/check_native_harness_acceptance.py --output /tmp/specorganon-reference-01
python -m unittest discover -s tests -p test_native_harness_acceptance.py -v
```

Use a new output directory each time. Nothing is overwritten. The reference
uses the current Python interpreter and source checkout; it is not a wheel or
release-installation test. It does not call a model API, install dependencies,
publish anything, alter trust registries, or connect to production MCP services.

Exit codes:

- `0`: CLI and actual MCP reference mechanics completed
- `1`: an execution/assertion failed; retain the output for investigation
- `2`: CLI mechanics completed, but actual MCP execution is blocked

The pinned MCP dependency is `mcp==2.2.0`. A different or missing installed
version is reported as blocked, never silently replaced or treated as a pass.
With the correct dependency, two fresh local MCP stdio servers read the same
case and must match the actual CLI state. A server failure is also blocked.
The existing `scripts/clean_smoke.py` and `tests/test_local_interfaces.py` remain
the broader installed-package and transport checks.

## What runs and what the artifacts mean

1. Copy `tests/fixtures/native_harness/` into retained working and deliberately
   regressed source directories. Run the real stdlib unit test command in each.
   The working tally passes; the controlled sum-to-length regression must fail.
   The source, exact argv/cwd, return code, timeout and raw streams are preserved.
2. Reuse `workflows/synthetic_full.json` in `mechanics-case/` with **fixture
   policy**. Its nine review labels and two owner decisions are invented
   deterministic test inputs. Replaying through fresh CLI processes must append
   no events and leave the ledger byte-identical.
3. Revise the synthetic evidence premise. Previously accepted dependent phases
   must lose acceptance and dependent requirements/tests become stale. Replaying
   the outdated manifest must fail without overwriting either evidence version.
4. Write the same labeled draft graph into a separate **local-policy** case.
   Replay must preserve its checkpoint. Register the actual failed test with its
   corresponding implementation source version. Its receipt must be rejected by
   the local test gate, and an attempted build advance must fail without a write.
   Restore the measured good implementation/test as third versions: the original
   pass, real failure and repair all remain in the ledger.
5. Leave that local case awaiting genuine review. Read it through fresh MCP
   servers when available, compare state, and emit an evidence inventory.

The local case has **no approval, phase-review or phase-advance events**. Its
`human:acceptance-operator` is an unverified owner label, not a recorded human
decision. Earlier unreviewed phases also block its build: this check establishes
the specific failed-receipt blocker, not withdrawal of previously accepted
local reviews. That accepted-state invalidation is demonstrated in the separate
synthetic fixture; existing local-policy unit tests cover its local mechanics.

`summary.json` separately reports CLI, MCP, synthetic mechanics and actual
agent/human review status. Even exit `0` proves only deterministic reference
mechanics. It never proves that a model solved a new application, that an
independent agent reviewed it, or that a human approved its norms. Genuine
native-harness acceptance needs a real task, actual owner decisions and a
separate reviewer reading the source, observations and phase artifacts.

## Evidence to inspect

- `working/` and `regression/`: exact source snapshots, raw test streams,
  process metadata and local-test receipts
- `cli/`: ordered real CLI invocations with the same process receipts
- `fixture-workflow.json` and `local-drafts.json`: replay inputs
- Both case directories: complete hash-chained ledgers and historical versions
- `mechanics-completed.json`, `mechanics-invalidated.json`,
  `local-failed-test.json`, `local-final.json`: before/after state snapshots
- `local-report.json` and `summary.json`: limits and next pending action
- `mcp-restart-*`: actual MCP streams when that stage could run
- `sha256.json`: all evidence-file digests, excluding itself

The recorded `source_identity` binds the test report to retained source bytes
and the corresponding implementation version for inspection. The engine's
`result_sha256` checks its defined receipt fields; it does **not** authenticate
source identity or independently execute the command. These local declarations
and hashes do not provide signed custody or protection from a dishonest runner.

The direct unit tests use only `unittest` plus the existing runtime dependencies.
They verify receipts, source/version links, preserved failure history, synthetic
invalidation, replay, missing-MCP status, refusal to overwrite and timeout logs.
Passing those tests is not a full pytest-suite or MCP pass.
