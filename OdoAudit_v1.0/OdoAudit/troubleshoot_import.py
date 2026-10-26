import sys, os
from pathlib import Path

print("=== python core info ===")
print("executable", sys.executable)
print("prefix", sys.prefix)
print("base_prefix", getattr(sys, "base_prefix", None))
print("exec_prefix", getattr(sys, "exec_prefix", None))
print("path0", sys.path[0])
print("path_count", len(sys.path))
for i, p in enumerate(sys.path[:12]):
    print(f"path[{i}]", p)
print("PYTHONHOME", os.environ.get("PYTHONHOME"))
print("PYTHONPATH", os.environ.get("PYTHONPATH"))
print("sys.flags", sys.flags)
print("sys.warnoptions", sys.warnoptions)

# confirm where python actually resolves the stdlib/site-packages from
print("\n=== stdlib/site-packages resolution ===")
for name in ("os", "json", "typing", "datetime", "collections"):
    m = __import__(name)
    print(f"{name}: {getattr(m,'__file__','(builtin)')}")

import site
print("site.PREFIXES", site.PREFIXES)
print("site.getsitepackages()", site.getsitepackages())
print("site.getusersitepackages()", site.getusersitepackages())

print("\n=== venv layout ===")
root = Path(__file__).resolve().parent if "__file__" in globals() else Path(sys.prefix)
for rel in (".", ".venv", ".venv/Scripts/python.exe", ".venv/Lib/site-packages", ".venv/Lib/site-packages/pandas", ".venv/Lib/site-packages/uvicorn", ".venv/Lib/site-packages/fastapi"):
    p = root / rel
    print(rel, "EXISTS" if p.exists() else "MISSING", repr(p))

def show(label, value):
    print(label, repr(value))

show("executable", sys.executable)
show("prefix", sys.prefix)
show("base_prefix", getattr(sys, "base_prefix", None))
show("path0", sys.path[0])
show("path_count", len(sys.path))
for i, p in enumerate(sys.path[:12]):
    show(f"path[{i}]", p)
show("PYTHONHOME", os.environ.get("PYTHONHOME"))
show("PYTHONPATH", os.environ.get("PYTHONPATH"))
show("sys.flags", sys.flags)
show("sys.warnoptions", sys.warnoptions)

try:
    import importlib.util as iu
    spec = iu.find_spec("pandas")
    show("pandas_spec", spec)
    show("pandas_spec.origin", getattr(spec, "origin", None))
    show("pandas_spec.submodule_search_locations", getattr(spec, "submodule_search_locations", None))
except Exception as e:
    print("pandas_spec error", repr(e))

try:
    # --- simulate what a stray PYTHONHOME does to venv site-packages ---
    import os as _os
    _saved_pythonhome = _os.environ.get("PYTHONHOME")
    _saved_path = list(sys.path)

    # --- show what a stray PYTHONHOME does to this venv ---
    import os as _os
    from pathlib import Path
    import subprocess, textwrap, tempfile

    _saved_pythonhome = _os.environ.get("PYTHONHOME")
    _saved_path = list(sys.path)

    _probe_lines = []
    _probe_lines.append("import os, sys")
    _probe_lines.append('print("PYTHONHOME", os.environ.get("PYTHONHOME"))')
    _probe_lines.append('print("sys.prefix", sys.prefix)')
    _probe_lines.append('print("sys.executable", sys.executable)')
    _probe_lines.append("print('sys.path', sys.path)")
    for pkg in ("pandas", "odo_audit", "fastapi", "uvicorn"):
        _probe_lines.append(f"""
    try:
        import {pkg}
        print(f"IMPORT_OK: {{pkg}} -> {{getattr({pkg},'__file__',{pkg})}}")
    except Exception as e:
        print(f"IMPORT_ERR: {{pkg}} -> {{type(e).__name__}}: {{e}}")
""")
    _probe = Path(tempfile.mkdtemp(prefix="odoaudit_ph_probe_")) / "probe.py"
    _probe.write_text("\n".join(_probe_lines) + "\n")

    _tr = _probe.parent
    _empty = _tr / "empty_home"
    _empty.mkdir(parents=True, exist_ok=True)

    def _run(label, pythonhome):
        env = dict(os.environ)
        env["PYTHONHOME"] = pythonhome if pythonhome is not None else ""
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        r = subprocess.run([sys.executable, str(_probe)], env=env, capture_output=True, text=True, cwd=str(_tr))
        print(f"\n=== {label} (rc={r.returncode}) ===")
        print(r.stdout)
        if r.stderr:
            print(r.stderr)

    print("\n=== subprocess probe: no PYTHONHOME (empty string) ===")
    _run("empty PYTHONHOME", "")
    print("\n=== subprocess probe: PYTHONHOME=<venv itself> ===")
    _run("PYTHONHOME=<venv>", str(Path(sys.prefix).resolve()))
    print("\n=== subprocess probe: PYTHONHOME=<empty dir, no Lib/site-packages> ===")
    _run("PYTHONHOME=<empty dir>", str(_empty))

    # Restore
    if _saved_pythonhome is None:
        _os.environ.pop("PYTHONHOME", None)
    else:
        _os.environ["PYTHONHOME"] = _saved_pythonhome
    sys.path[:] = _saved_path

    import pandas as pd
    show("pandas_version", pd.__version__)
    show("pandas_file", pd.__file__)
except Exception as e:
    print("pandas import error", repr(e))

try:
    import pyarrow
    show("pyarrow_version", pyarrow.__version__)
except Exception as e:
    print("pyarrow import error", repr(e))

try:
    import openpyxl
    show("openpyxl_version", openpyxl.__version__)
except Exception as e:
    print("openpyxl import error", repr(e))
