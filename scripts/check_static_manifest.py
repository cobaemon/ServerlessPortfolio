import json
import sys
from pathlib import Path

# Load static paths from templates
from django.conf import settings

BASE_DIR = Path(__file__).resolve().parent.parent

manifest_path = BASE_DIR / 'staticfiles' / 'staticfiles.json'
templates_dir = BASE_DIR / 'templates'

# Load manifest
with open(manifest_path, 'r') as f:
    manifest = json.load(f)['paths']

missing = []

# Extract static paths from templates
import re
pattern = re.compile(r"\{\% static '(.*?)' \%\}")

for template_file in templates_dir.rglob('*.html'):
    with open(template_file, 'r') as f:
        for match in pattern.findall(f.read()):
            if match not in manifest:
                missing.append((template_file, match))

if missing:
    print('Missing manifest entries:')
    for tpl, path in missing:
        print(f"{tpl}: {path}")
    sys.exit(1)
print('All static file references are valid.')
