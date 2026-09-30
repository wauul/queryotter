import json, tarfile
from pathlib import Path

source = json.loads(Path(".openai/hosting.json").read_text(encoding="utf8"))
built = json.loads(Path("dist/.openai/hosting.json").read_text(encoding="utf8"))
assert source == built, "Rebuild after changing hosting configuration."
assert Path("dist/server/index.js").is_file(), "Run npm run build first."
Path("artifacts").mkdir(exist_ok=True)
with tarfile.open("artifacts/queryotter.tar.gz", "w:gz") as t:
    t.add("dist", arcname="dist")
print("Deployment archive built without environment files or database data.")
