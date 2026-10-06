from pathlib import Path
p=Path("/output/count.txt")
p.write_text(str(int(p.read_text())+1) if p.exists() else "1")
print("counter="+p.read_text())
