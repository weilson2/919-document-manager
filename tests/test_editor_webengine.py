import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE = Path(__file__).with_name("editor_webengine_probe.py")


def run_checked(*args: str, cwd: Path, env: dict | None = None) -> str:
    result = subprocess.run(
        [sys.executable, "-X", "faulthandler", *args],
        check=False, cwd=cwd, env=env, capture_output=True, encoding="utf-8", errors="replace", timeout=90,
    )
    assert result.returncode == 0, f"{result.args!r} exited with {result.returncode}\n{result.stdout}\n{result.stderr}"
    return result.stdout


def run_offline_probe(workspace, installed=None):
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        '--disable-gpu --disable-background-networking --host-resolver-rules="MAP * ~NOTFOUND" '
        '--proxy-server=http://127.0.0.1:9 --proxy-bypass-list="<-loopback>"'
    )
    env["PATH"] = os.pathsep.join(
        path for path in env.get("PATH", "").split(os.pathsep)
        if path and not any((Path(path) / name).is_file() for name in ("node", "node.exe", "npm.cmd"))
    )
    args = [str(PROBE), str(workspace)]
    if installed is not None:
        env["PYTHONPATH"] = str(installed)
        args.append(str(installed))
    output = run_checked(*args, cwd=workspace, env=env)
    assert "Offline renderer startup, WebChannel JSON round trip" in output


def test_embedded_editor_round_trip(tmp_path):
    run_offline_probe(tmp_path)


def test_installed_wheel_loads_editor_assets_offline(tmp_path):
    run_checked("-m", "build", "--no-isolation", "--wheel", "--outdir", str(tmp_path), cwd=ROOT)
    wheel, = tmp_path.glob("document_manager_919-*.whl")
    installed = tmp_path / "installed"
    run_checked(
        "-m", "pip", "install", "--no-index", "--no-deps", "--target", str(installed), str(wheel), cwd=tmp_path,
    )
    run_offline_probe(tmp_path, installed)
