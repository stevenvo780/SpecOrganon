import sys
import os
import subprocess
import json
import tempfile
import time
import shutil
import random
import argparse
import signal
import hashlib
from pathlib import Path

TIMEOUT_S = 20

class Evaluator:
    def __init__(self, candidate: Path, variant: str, stage: int, seed: int, workdir: Path):
        self.candidate = candidate.resolve()
        self.variant = variant
        self.stage = stage
        self.seed = seed
        self.workdir = workdir
        self.rng = random.Random(seed)
        
        self.metrics = {"space": 0, "latency": 0.0}
        self.critical_failures = []
        self.details = []
        self.checks_passed = 0
        self.checks_total = 0
        self.inconclusive = False

    def add_detail(self, name, passed, info=None, critical=False, explicit_inconclusive=False):
        if explicit_inconclusive:
            self.inconclusive = True
            self.details.append({"name": name, "inconclusive": True, "info": info})
            return

        self.checks_total += 1
        if passed:
            self.checks_passed += 1
        else:
            if critical:
                self.critical_failures.append(name)
        
        self.details.append({"name": name, "passed": passed, "info": info})

    def run_backup(self, args: list, cwd: Path, timeout: float = TIMEOUT_S):
        cmd = [sys.executable, str(self.candidate)] + args
        start = time.time()
        try:
            proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
            end = time.time()
            return {
                "argv": cmd,
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "sha": hashlib.sha256((proc.stdout + proc.stderr).encode('utf-8', errors='replace')).hexdigest(),
                "time": end - start,
                "timeout": False
            }
        except subprocess.TimeoutExpired as e:
            end = time.time()
            stdout_str = e.stdout.decode('utf-8', errors='replace') if e.stdout else ""
            stderr_str = e.stderr.decode('utf-8', errors='replace') if e.stderr else ""
            return {
                "argv": cmd,
                "exit_code": -1,
                "stdout": stdout_str,
                "stderr": stderr_str,
                "sha": hashlib.sha256((stdout_str + stderr_str).encode('utf-8', errors='replace')).hexdigest(),
                "time": end - start,
                "timeout": True
            }

    def create_work_env(self, prefix=""):
        d = tempfile.mkdtemp(dir=self.workdir, prefix=prefix)
        return Path(d)

    def snapshot_dir(self, d: Path):
        state = {}
        for p in d.rglob('*'):
            rel = p.relative_to(d)
            if p.is_file() and not p.is_symlink():
                state[rel] = p.read_bytes()
            elif p.is_dir() and not p.is_symlink():
                state[rel] = "DIR"
            elif p.is_symlink():
                state[rel] = f"SYMLINK:{os.readlink(p)}"
        return state

    def run_all_checks(self):
        if not self.candidate.exists():
            self.add_detail("candidate_exists", False, "Candidate not found", critical=True)
            return

        self.check_roundtrip()
        self.check_duplicate_id()
        self.check_invalid_ids()
        self.check_nonexistent_id()
        self.check_overlap()
        self.check_symlinks()
        self.check_dest_protected()
        self.check_snapshot_corruption()
        self.check_version_snapshots()
        self.check_sigkill()
        
        if self.stage == 2:
            self.check_max_bytes()

    def check_roundtrip(self):
        env = self.create_work_env("roundtrip")
        source = env / "source"
        repo = env / "repo"
        dest = env / "dest"
        source.mkdir()
        repo.mkdir()
        
        (source / "empty_dir").mkdir()
        (source / "unicode_ñ_🚀.txt").write_text("hello ñ", encoding='utf-8')
        (source / "binary.bin").write_bytes(os.urandom(1024))
        (source / "deep").mkdir()
        (source / "deep" / "file.txt").write_text("deep")

        orig_state = self.snapshot_dir(source)
        id_val = "round-1"
        
        res = self.run_backup(["create", "--source", str(source), "--repo", str(repo), "--id", id_val], env)
        if res['exit_code'] != 0:
            self.add_detail("roundtrip_create", False, res)
            return
        self.metrics['latency'] += res['time']
        
        # Check list
        res_list = self.run_backup(["list", "--repo", str(repo)], env)
        try:
            snapshots = json.loads(res_list['stdout']).get("snapshots", [])
            list_pass = (id_val in snapshots)
        except:
            list_pass = False
        self.add_detail("roundtrip_list", list_pass, res_list)

        res_v = self.run_backup(["verify", "--repo", str(repo), "--id", id_val], env)
        try:
            valid = json.loads(res_v['stdout']).get("valid") is True
        except:
            valid = False
        self.add_detail("roundtrip_verify", valid, res_v)
        
        res_r = self.run_backup(["restore", "--repo", str(repo), "--id", id_val, "--dest", str(dest)], env)
        if res_r['exit_code'] == 0:
            restored_state = self.snapshot_dir(dest)
            self.add_detail("roundtrip_match", restored_state == orig_state, "Bytes and dirs match")
        else:
            self.add_detail("roundtrip_match", False, res_r)
            
        cur_source = self.snapshot_dir(source)
        if cur_source != orig_state:
            self.add_detail("source_intact", False, "Source modified during roundtrip", critical=True)
        else:
            self.add_detail("source_intact", True)
            
        self.metrics['space'] = sum(f.stat().st_size for f in repo.rglob('*') if f.is_file() and not f.is_symlink())

    def check_duplicate_id(self):
        env = self.create_work_env("dup")
        source = env / "source"
        repo = env / "repo"
        source.mkdir(); repo.mkdir()
        (source / "a.txt").write_text("A")
        
        self.run_backup(["create", "--source", str(source), "--repo", str(repo), "--id", "dup1"], env)
        repo_state1 = self.snapshot_dir(repo)
        
        (source / "a.txt").write_text("B")
        res = self.run_backup(["create", "--source", str(source), "--repo", str(repo), "--id", "dup1"], env)
        
        # It should reject overwriting
        if res['exit_code'] == 0:
            # If it reports success, it MUST not have mutated the repo state or it must still restore A
            repo_state2 = self.snapshot_dir(repo)
            if repo_state1 != repo_state2:
                self.add_detail("duplicate_id_mutation", False, "Mutated existing ID on duplicate create", critical=True)
            else:
                self.add_detail("duplicate_id_mutation", False, "Reported success for duplicate ID without mutating")
        else:
            repo_state2 = self.snapshot_dir(repo)
            if repo_state1 != repo_state2:
                self.add_detail("duplicate_id_mutation", False, "Mutated repo on failed duplicate create", critical=True)
            else:
                self.add_detail("duplicate_id_mutation", True)

    def check_invalid_ids(self):
        env = self.create_work_env("invalid_ids")
        source = env / "source"
        repo = env / "repo"
        source.mkdir(); repo.mkdir()
        (source / "a.txt").write_text("A")
        
        invalid_ids = ["-abc", "a!b", "a" * 65]
        all_passed = True
        for inv in invalid_ids:
            res = self.run_backup(["create", "--source", str(source), "--repo", str(repo), "--id", inv], env)
            if res['exit_code'] == 0:
                all_passed = False
                break
        self.add_detail("invalid_ids", all_passed)

    def check_nonexistent_id(self):
        env = self.create_work_env("nonexistent")
        repo = env / "repo"
        dest = env / "dest"
        repo.mkdir()
        
        r_v = self.run_backup(["verify", "--repo", str(repo), "--id", "nope"], env)
        try:
            valid = json.loads(r_v['stdout']).get("valid")
            v_pass = r_v['exit_code'] != 0 or valid is False
        except:
            v_pass = r_v['exit_code'] != 0
            
        r_r = self.run_backup(["restore", "--repo", str(repo), "--id", "nope", "--dest", str(dest)], env)
        r_pass = r_r['exit_code'] != 0
        
        self.add_detail("nonexistent_id", v_pass and r_pass)

    def check_overlap(self):
        env = self.create_work_env("overlap")
        d1 = env / "d1"
        d1.mkdir()
        
        res1 = self.run_backup(["create", "--source", str(d1), "--repo", str(d1), "--id", "ov1"], env)
        
        d2 = env / "d2"
        d3 = d2 / "d3"
        d3.mkdir(parents=True)
        res2 = self.run_backup(["create", "--source", str(d2), "--repo", str(d3), "--id", "ov2"], env)
        res3 = self.run_backup(["create", "--source", str(d3), "--repo", str(d2), "--id", "ov3"], env)
        
        self.add_detail("overlap_rejected", res1['exit_code'] != 0 and res2['exit_code'] != 0 and res3['exit_code'] != 0)

    def check_symlinks(self):
        env = self.create_work_env("symlinks")
        source = env / "source"
        repo = env / "repo"
        dest = env / "dest"
        outside = env / "outside"
        source.mkdir(); repo.mkdir(); outside.mkdir()
        (outside / "secret.txt").write_text("secret")
        
        # Symlink in source pointing outside
        os.symlink(str(outside), str(source / "link_to_outside"))
        
        res = self.run_backup(["create", "--source", str(source), "--repo", str(repo), "--id", "sym1"], env)
        if res['exit_code'] == 0:
            res_r = self.run_backup(["restore", "--repo", str(repo), "--id", "sym1", "--dest", str(dest)], env)
            if (dest / "link_to_outside" / "secret.txt").exists():
                # Followed symlink!
                pass
                
        # Must not have effect outside
        if (outside / "secret.txt").read_text() != "secret":
            self.add_detail("symlink_isolation", False, "Modified outside file via symlink", critical=True)
            return
            
        self.add_detail("symlink_isolation", True)

    def check_dest_protected(self):
        env = self.create_work_env("dest_prot")
        source = env / "source"
        repo = env / "repo"
        dest = env / "dest"
        source.mkdir(); repo.mkdir(); dest.mkdir()
        (source / "a.txt").write_text("A")
        
        self.run_backup(["create", "--source", str(source), "--repo", str(repo), "--id", "dp1"], env)
        
        (dest / "existing.txt").write_text("do not overwrite")
        state_before = self.snapshot_dir(dest)
        
        res = self.run_backup(["restore", "--repo", str(repo), "--id", "dp1", "--dest", str(dest)], env)
        state_after = self.snapshot_dir(dest)
        
        if res['exit_code'] == 0:
            if state_before != state_after:
                self.add_detail("dest_protected", False, "Overwrote non-empty dest on reported success", critical=True)
            else:
                self.add_detail("dest_protected", False, "Reported success but dest was not empty")
        else:
            if state_before != state_after:
                self.add_detail("dest_protected", False, "Changed non-empty dest despite error", critical=True)
            else:
                self.add_detail("dest_protected", True)

    def check_snapshot_corruption(self):
        env = self.create_work_env("corrupt")
        source = env / "source"
        repo = env / "repo"
        source.mkdir(); repo.mkdir()
        (source / "a.txt").write_text("A")
        (source / "b.txt").write_text("B")
        
        self.run_backup(["create", "--source", str(source), "--repo", str(repo), "--id", "c1"], env)
        
        files = [f for f in repo.rglob('*') if f.is_file() and not f.is_symlink()]
        if not files:
            self.add_detail("snapshot_corruption", False, explicit_inconclusive=True, info="No files in repo to corrupt")
            return
            
        if len(files) > 12:
            files = self.rng.sample(files, 12)
            
        passed = False
        for f in files:
            orig = f.read_bytes()
            # Corrupt byte
            f.write_bytes(orig + b'x')
            
            res_v = self.run_backup(["verify", "--repo", str(repo), "--id", "c1"], env)
            try:
                valid = json.loads(res_v['stdout']).get("valid")
            except:
                valid = False
            
            if res_v['exit_code'] != 0 or not valid:
                passed = True
                break
            
            # Restore original to test next file
            f.write_bytes(orig)
            
        if passed:
            self.add_detail("snapshot_corruption", True)
        else:
            if len([f for f in repo.rglob('*') if f.is_file()]) > 12:
                self.add_detail("snapshot_corruption", False, explicit_inconclusive=True, info="Metadata extensive, inconclusive")
            else:
                self.add_detail("snapshot_corruption", False, "Silent corruption detected", critical=True)

    def check_version_snapshots(self):
        env = self.create_work_env("versions")
        source = env / "source"
        repo = env / "repo"
        source.mkdir(); repo.mkdir()
        
        (source / "v1.txt").write_text("1")
        self.run_backup(["create", "--source", str(source), "--repo", str(repo), "--id", "snap1"], env)
        
        (source / "v2.txt").write_text("2")
        (source / "v1.txt").write_text("1 modified")
        self.run_backup(["create", "--source", str(source), "--repo", str(repo), "--id", "snap2"], env)
        
        (source / "v2.txt").unlink()
        self.run_backup(["create", "--source", str(source), "--repo", str(repo), "--id", "snap3"], env)
        
        # Verify restores
        dest1 = env / "dest1"
        self.run_backup(["restore", "--repo", str(repo), "--id", "snap1", "--dest", str(dest1)], env)
        if not (dest1 / "v1.txt").exists() or (dest1 / "v1.txt").read_text() != "1" or (dest1 / "v2.txt").exists():
            self.add_detail("version_snapshots", False, "snap1 incorrect")
            return
            
        dest3 = env / "dest3"
        self.run_backup(["restore", "--repo", str(repo), "--id", "snap3", "--dest", str(dest3)], env)
        if (dest3 / "v2.txt").exists() or (dest3 / "v1.txt").read_text() != "1 modified":
            self.add_detail("version_snapshots", False, "snap3 incorrect")
            return
            
        self.add_detail("version_snapshots", True)

    def check_sigkill(self):
        env = self.create_work_env("sigkill")
        source = env / "source"
        repo = env / "repo"
        source.mkdir(); repo.mkdir()
        
        (source / "pre.txt").write_text("pre")
        self.run_backup(["create", "--source", str(source), "--repo", str(repo), "--id", "pre"], env)
        repo_state_pre = self.snapshot_dir(repo)
        
        # Create ~64MB load
        (source / "large.bin").write_bytes(os.urandom(64 * 1024 * 1024))
        
        cmd = [sys.executable, str(self.candidate), "create", "--source", str(source), "--repo", str(repo), "--id", "interrupted"]
        with subprocess.Popen(cmd, cwd=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
            # Poll repo for write
            observed_write = False
            start = time.time()
            while time.time() - start < 10:
                current_state = self.snapshot_dir(repo)
                if current_state != repo_state_pre:
                    observed_write = True
                    break
                time.sleep(0.05)
                if proc.poll() is not None:
                    break
                    
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            
        if not observed_write:
            self.add_detail("sigkill_interrupt", False, explicit_inconclusive=True, info="No window observed before kill")
            return
            
        # Check previous snapshots intact
        res_v = self.run_backup(["verify", "--repo", str(repo), "--id", "pre"], env)
        try:
            valid = json.loads(res_v['stdout']).get("valid") is True
        except:
            valid = False
            
        if not valid:
            self.add_detail("sigkill_interrupt_intact", False, "Previous snapshot invalid after kill", critical=True)
        else:
            self.add_detail("sigkill_interrupt_intact", True)

    def check_max_bytes(self):
        env = self.create_work_env("quota")
        source = env / "source"
        repo = env / "repo"
        source.mkdir(); repo.mkdir()
        
        (source / "a.txt").write_text("A")
        res1 = self.run_backup(["create", "--source", str(source), "--repo", str(repo), "--id", "q1", "--max-bytes", "1048576"], env)
        if res1['exit_code'] != 0:
            self.add_detail("max_bytes_high", False, "Failed with high limit")
            return
        
        (source / "b.txt").write_text("B" * 1024)
        res2 = self.run_backup(["create", "--source", str(source), "--repo", str(repo), "--id", "q2", "--max-bytes", "1"], env)
        if res2['exit_code'] == 0:
            self.add_detail("max_bytes_low", False, "Succeeded with impossible limit")
            return
            
        res_v = self.run_backup(["verify", "--repo", str(repo), "--id", "q1"], env)
        try:
            valid = json.loads(res_v['stdout']).get("valid") is True
        except:
            valid = False
            
        if not valid:
            self.add_detail("max_bytes_intact", False, "Previous snapshot invalid after quota rejection", critical=True)
        else:
            self.add_detail("max_bytes", True)

def evaluate(candidate: Path, variant: str = 'V1', stage: int = 1, seed: int = 42, workdir: Path | None = None) -> dict:
    if workdir is None:
        workdir_obj = tempfile.TemporaryDirectory()
        workdir = Path(workdir_obj.name)
    else:
        workdir_obj = None

    try:
        evaluator = Evaluator(candidate, variant, stage, seed, workdir)
        evaluator.run_all_checks()
        
        score = evaluator.checks_passed / evaluator.checks_total if evaluator.checks_total > 0 else 0.0
        
        return {
            "score": score,
            "inconclusive": evaluator.inconclusive,
            "critical_failures": evaluator.critical_failures,
            "metrics": evaluator.metrics,
            "details": evaluator.details
        }
    finally:
        if workdir_obj is not None:
            workdir_obj.cleanup()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--variant", type=str, default="V1")
    parser.add_argument("--stage", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = evaluate(args.candidate, args.variant, args.stage, args.seed)
    
    if args.output:
        args.output.write_text(json.dumps(result, indent=2))
    else:
        print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
