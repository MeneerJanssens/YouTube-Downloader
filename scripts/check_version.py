"""CI check: the pushed tag must match APP_VERSION in ytd.py.

Fails (exit 1) if they differ, so a release can never ship an exe that
reports an older version than its own release tag (which would also break
the in-app update check).
"""
import os
import re
import sys

src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ytd.py")
with open(src_path, encoding="utf-8") as f:
    src = f.read()

m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)', src)
if not m:
    print("APP_VERSION not found in ytd.py")
    sys.exit(1)

app_version = m.group(1)
tag = os.environ.get("TAG", "").lstrip("v")

if tag != app_version:
    print(f"Tag '{tag}' does not match APP_VERSION '{app_version}' — bump APP_VERSION in ytd.py")
    sys.exit(1)

print(f"OK: tag v{tag} == APP_VERSION {app_version}")
