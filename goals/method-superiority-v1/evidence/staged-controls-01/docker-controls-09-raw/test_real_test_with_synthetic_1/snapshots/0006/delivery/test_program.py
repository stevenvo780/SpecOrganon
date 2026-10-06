from pathlib import Path
import runpy
assert runpy.run_path(str(Path(__file__).with_name("program.py")))["result"]()==7
print("guard control passed")

p=Path("/output/own-runs.txt");p.write_text(str(int(p.read_text())+1) if p.exists() else "1")
