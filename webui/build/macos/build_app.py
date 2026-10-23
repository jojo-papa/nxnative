"""Rebuild the native executable of an already assembled macOS game bundle."""
import argparse
import os
from pathlib import Path
import platform
import shlex
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", required=True, help="Base game title ID")
    parser.add_argument("--app", required=True, type=Path, help="Existing .app with matching game resources")
    args = parser.parse_args()
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        parser.error("Build on an Apple Silicon Mac with the Metal 4 SDK.")
    app = args.app.resolve()
    resources = app / "Contents/Resources"
    for name in ("romfs", "patched", "shaders", "profile"):
        if not (resources / name).is_dir():
            parser.error(f"Missing bundle resource directory: {resources / name}")
    repo = Path(__file__).resolve().parents[3]
    host = repo / "dm/host"
    subprocess.run(["make", f"GAME={args.game}", "game_profile", "gen/vpx/libvpx.a"], cwd=host, check=True)
    dry = subprocess.check_output(["make", "-n", "-B", f"GAME={args.game}", "dmhost"], cwd=host, text=True)
    output = app / "Contents/MacOS/Launch"
    temporary = output.with_name("Launch.building")
    for line in dry.splitlines():
        command = shlex.split(line)
        if command and command[0] == "clang" and "-o" in command and command[command.index("-o") + 1] == "dmhost":
            command[command.index("-o") + 1] = str(temporary)
            command += ["-Dmain=dm_main", str(Path(__file__).with_name("main.m").resolve())]
            subprocess.run(command, cwd=host, check=True)
            os.replace(temporary, output)
            print(f"Built {output}")
            return
    raise RuntimeError("Could not find the host compiler invocation")


if __name__ == "__main__":
    main()
