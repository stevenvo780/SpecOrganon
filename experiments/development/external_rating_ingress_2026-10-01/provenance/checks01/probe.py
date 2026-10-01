import importlib.util, pathlib, tempfile, json
spec=importlib.util.spec_from_file_location("d124_archive_control",'/workspace/SpecOrganon/experiments/development/external_rating_ingress_2026-10-01/archive_originals.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
root=pathlib.Path(tempfile.mkdtemp(prefix="specorganon-D124-originals-probe-"));src=root/"source";src.mkdir();(src/"original").write_bytes(b"synthetic finite original")
output=root/"original.tar.gz";inventory=root/"inventory.json"
receipt=module.archive_originals(src,output,inventory);assert receipt["original_unchanged"] and not receipt["restore_authority"]
assert module.verify_originals(output,inventory)["verified_entries"]==1
before={p.name:p.read_bytes() for p in (output,inventory)}
try:module.archive_originals(src,output,inventory)
except module.ArchiveOriginalsError:pass
else:raise AssertionError("existing outputs accepted")
assert before=={p.name:p.read_bytes() for p in (output,inventory)}
(src/"link").symlink_to(src/"original")
try:module.archive_originals(src,root/"bad.tar.gz",root/"bad.json")
except module.ArchiveOriginalsError:pass
else:raise AssertionError("symlink accepted")
assert not (root/"bad.tar.gz").exists() and not (root/"bad.json").exists()
(src/"link").unlink()
changed=json.loads(inventory.read_bytes());changed["entries"][0]["sha256"]="0"*64;bad=root/"tampered.json";bad.write_text(json.dumps(changed))
try:module.verify_originals(output,bad)
except module.ArchiveOriginalsError:pass
else:raise AssertionError("hash tampering accepted")
print(json.dumps({"control_checks":5,"runtime_root":str(root),"source_bytes_unchanged":(src/"original").read_bytes()==b"synthetic finite original","archive_not_extracted":True}))
