#!/usr/bin/env python3
"""Write one SHA-256 line per file of a distribution tree, sorted.

The lightweight half of the build-logic change-safety protocol (the
heavier, archive-entry-level tool is compare_builds.py). Snapshot the
distribution before a build-logic change and after, then diff the two
snapshots; only the files you intended to change should appear.

    python3 snapshot_distribution.py <engine>/server/setup > before.txt
    # ... make your build-logic change, rebuild ...
    python3 snapshot_distribution.py <engine>/server/setup > after.txt
    diff before.txt after.txt

Output format matches `sha256sum`-style lines ("<hex>  <relpath>"),
sorted by path, so plain `diff` is meaningful. This replaces the
in-build snapshotDistribution task that previously lived in build.gradle.
"""
import sys, os, hashlib

def snapshot(root):
    lines = []
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            p = os.path.join(dirpath, f)
            h = hashlib.sha256()
            with open(p, 'rb') as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b''):
                    h.update(chunk)
            rel = os.path.relpath(p, root)
            lines.append(f'{h.hexdigest()}  {rel}')
    return sorted(lines)

def main(root):
    if not os.path.isdir(root):
        sys.stderr.write(f'not a directory: {root}\n'
                         '(build the distribution first, e.g. ./gradlew build)\n')
        sys.exit(2)
    out = snapshot(root)
    print('\n'.join(out))
    sys.stderr.write(f'{len(out)} files hashed under {root}\n')

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('usage: snapshot_distribution.py <setup-dir>')
        sys.exit(2)
    main(sys.argv[1])
