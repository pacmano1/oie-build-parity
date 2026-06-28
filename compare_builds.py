#!/usr/bin/env python3
"""Compare the Ant-built setup tree with the Gradle-built one.

Archive metadata (entry order, entry timestamps, permissions) is treated
as normalization difference and only summarized. Manifests are compared
as attribute maps ignoring Ant-Version/Created-By. version.properties is
compared ignoring comment/blank lines. Everything else must be
byte-identical, including every class file and resource inside every
jar/zip.
"""
import sys, os, zipfile

# --ignore-signatures: for comparing a signed distribution against an
# unsigned build. Signature files are skipped and the JWS attributes the
# signing flow adds to manifests are ignored (signatures embed fresh
# RFC 3161 timestamps, so they can never be byte-stable between builds).
IGNORE_SIGNATURES = False
SIG_SUFFIXES = ('.SF', '.RSA', '.DSA', '.EC')

def is_signature(name):
    return name.startswith('META-INF/') and name.upper().endswith(SIG_SUFFIXES)

def walk(root):
    out = {}
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            p = os.path.join(dirpath, f)
            out[os.path.relpath(p, root)] = p
    return out

def is_zip(path):
    return path.endswith(('.jar', '.zip', '.war'))

def manifest_attrs(data):
    # join continuation lines, parse main section only
    text = data.decode('utf-8', 'replace').replace('\r\n', '\n').replace('\r', '\n')
    main = text.split('\n\n')[0]
    lines, out = [], {}
    for line in main.split('\n'):
        if line.startswith(' '):
            if lines:
                lines[-1] += line[1:]
        elif line:
            lines.append(line)
    for line in lines:
        if ':' in line:
            k, v = line.split(':', 1)
            out[k.strip()] = v.strip()
    out.pop('Ant-Version', None)
    out.pop('Created-By', None)
    if IGNORE_SIGNATURES:
        for k in ('Permissions', 'Codebase', 'Application-Name'):
            out.pop(k, None)
    return out

def props_lines(data):
    lines = [l for l in data.replace(b'\r\n', b'\n').split(b'\n')
             if l.strip() and not l.startswith(b'#')]
    if IGNORE_SIGNATURES:
        # release-vs-rebuild: the build date legitimately differs
        lines = [l for l in lines if not l.startswith(b'mirth.date=')]
    return lines

def entry_equal(name, a, b, report, ctx):
    if a == b:
        return True
    base = name.rsplit('/', 1)[-1]
    if base == 'MANIFEST.MF':
        if manifest_attrs(a) == manifest_attrs(b):
            report['manifest'] += 1
            return True
        report['real'].append(f'{ctx}!{name}: manifest attributes differ:\n    ant={manifest_attrs(a)}\n    gradle={manifest_attrs(b)}')
        return False
    if base == 'version.properties':
        if props_lines(a) == props_lines(b):
            report['versionprops'] += 1
            return True
    report['real'].append(f'{ctx}!{name}: content differs ({len(a)} vs {len(b)} bytes)')
    return False

def compare_zip(rel, pa, pb, report):
    za, zb = zipfile.ZipFile(pa), zipfile.ZipFile(pb)
    files_a = {n for n in za.namelist() if not n.endswith('/')}
    files_b = {n for n in zb.namelist() if not n.endswith('/')}
    if IGNORE_SIGNATURES:
        files_a = {n for n in files_a if not is_signature(n)}
        files_b = {n for n in files_b if not is_signature(n)}
    dirs_a = {n for n in za.namelist() if n.endswith('/')}
    dirs_b = {n for n in zb.namelist() if n.endswith('/')}
    if files_a != files_b:
        only_a, only_b = sorted(files_a - files_b), sorted(files_b - files_a)
        report['real'].append(f'{rel}: file entry sets differ (ant-only={only_a[:8]} gradle-only={only_b[:8]})')
        return
    if dirs_a != dirs_b:
        report['direntries'].append(f'{rel}: dir entries ant-only={sorted(dirs_a - dirs_b)[:4]} gradle-only={sorted(dirs_b - dirs_a)[:4]}')
    ok = True
    for n in sorted(files_a):
        if not entry_equal(n, za.read(n), zb.read(n), report, rel):
            ok = False
    if ok:
        report['zip_content_ok'] += 1

def main(ant_root, gradle_root):
    a, b = walk(ant_root), walk(gradle_root)
    report = {'real': [], 'direntries': [], 'manifest': 0, 'versionprops': 0,
              'identical': 0, 'zip_content_ok': 0}
    for m in sorted(set(a) - set(b)):
        report['real'].append(f'missing from gradle build: {m}')
    for m in sorted(set(b) - set(a)):
        report['real'].append(f'extra in gradle build: {m}')
    common = sorted(set(a) & set(b))
    n_zips = sum(1 for r in common if is_zip(r))
    for rel in common:
        da = open(a[rel], 'rb').read()
        db = open(b[rel], 'rb').read()
        if da == db:
            report['identical'] += 1
            if is_zip(rel):
                report['zip_content_ok'] += 1
            continue
        if is_zip(rel):
            compare_zip(rel, a[rel], b[rel], report)
        else:
            if rel.rsplit('/', 1)[-1] == 'version.properties' and props_lines(da) == props_lines(db):
                report['versionprops'] += 1
                continue
            report['real'].append(f'{rel}: plain file content differs')

    print(f'Common files: {len(common)} ({n_zips} jars/zips)')
    print(f'Byte-identical files: {report["identical"]}')
    print(f'Jars/zips with fully identical entry contents: {report["zip_content_ok"]} / {n_zips}')
    print(f'Manifests differing only in Ant-Version/Created-By: {report["manifest"]}')
    print(f'version.properties differing only in timestamp comment: {report["versionprops"]}')
    if report['direntries']:
        print(f'\nDirectory-entry-only differences ({len(report["direntries"])}):')
        for x in report['direntries'][:10]:
            print(f'  {x}')
    print(f'\nREAL differences ({len(report["real"])}):')
    for x in report['real']:
        print(f'  {x}')
    sys.exit(1 if report['real'] else 0)

if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a != '--ignore-signatures']
    IGNORE_SIGNATURES = '--ignore-signatures' in sys.argv[1:]
    if len(args) != 2 or args[0].startswith('-'):
        print('usage: compare_builds.py [--ignore-signatures] <baseline-setup-dir> <candidate-setup-dir>')
        sys.exit(2)
    main(args[0], args[1])
