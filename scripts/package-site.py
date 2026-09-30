import json,tarfile,shutil
from pathlib import Path
p=Path('artifacts/site');p.mkdir(parents=True,exist_ok=True)
shutil.copytree('dist',p/'dist',dirs_exist_ok=True)
(p/'.openai').mkdir(exist_ok=True);(p/'hosting').mkdir(exist_ok=True)
shutil.copy('.openai/hosting.json',p/'.openai/hosting.json');shutil.copy('hosting/worker.js',p/'hosting/worker.js')
with tarfile.open('artifacts/queryotter.tar.gz','w:gz') as t:
 for path in sorted(p.rglob('*')):
  if path.is_file():t.add(path,arcname=str(path.relative_to(p)).replace('\\','/'))
print('Deployment archive built without environment files or database data.')
