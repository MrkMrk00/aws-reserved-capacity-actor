#!/usr/bin/env python

import subprocess
import sys

PROJECT_DIR = 'src/'


def main():
    commands = [
        (sys.executable, '-m', 'flake8', PROJECT_DIR),
        (sys.executable, '-m', 'mypy', '--config-file', 'pyproject.toml', PROJECT_DIR),
        (sys.executable, '-m', 'isort', '--check', PROJECT_DIR),
    ]

    procs = [(subprocess.Popen(cmd), cmd) for cmd in commands]

    failed = []

    for proc, cmd in procs:
        status = proc.wait()

        if status != 0:
            failed.append((status, cmd))

    if len(failed) > 0:
        for status_code, cmd in failed:
            sys.stderr.write(
                f'command "{' '.join(cmd)}" failed with exit code {status_code}\n')

        sys.exit(1)


if __name__ == '__main__':
    main()
