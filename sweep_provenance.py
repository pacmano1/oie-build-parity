#!/usr/bin/env python3
"""Re-verify and classify the vendored-jar provenance record.

Modes:
  --verify-exact   re-check every 'exact' entry: download the .jar.sha1 for
                   the recorded coordinate from repo1.maven.org and compare
                   to the recorded SHA-1 (catches tampering and typos).
  --classify-none  probe Maven Central for each 'none' entry by artifact
                   name and record evidence of WHY it stays vendored:
                   version never published, or published bytes differ.

Lesson encoded here (June 2026 migration): Maven Central's search index
lacks checksum documents for some artifacts, so a "no SHA match" from the
search API is only trustworthy after a direct repo1 probe.
"""
import hashlib, json, os, re, subprocess, sys, time, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PROV = os.path.join(HERE, 'jar-provenance.json')

def curl(url):
    r = subprocess.run(['curl', '-sL', '--max-time', '20', '-w', '\\n%{http_code}', url],
                       capture_output=True, text=True)
    body, _, code = r.stdout.rpartition('\n')
    return code, body

def repo1_sha1(g, a, v, classifier=None):
    path = f"{g.replace('.', '/')}/{a}/{v}/{a}-{v}{'-' + classifier if classifier else ''}.jar.sha1"
    code, body = curl(f'https://repo1.maven.org/maven2/{path}')
    # legacy .sha1 files contain "hash  original/build/path"; the hash is the first token
    return body.split()[0] if code == '200' and body.strip() else None

def search_versions(artifact):
    q = urllib.parse.quote(f'a:"{artifact}"')
    code, body = curl(f'https://search.maven.org/solrsearch/select?q={q}&core=gav&rows=50&wt=json')
    if code != '200':
        return []
    try:
        docs = json.loads(body)['response']['docs']
        return [(d['g'], d['a'], d['v']) for d in docs]
    except Exception:
        return []

def split_name(filename):
    base = filename[:-4]
    m = re.match(r'^(.*?)[-_](\d[\w.\-]*)$', base)
    return (m.group(1), m.group(2)) if m else (base, None)

def main():
    prov = json.load(open(PROV))
    changed = False
    if '--verify-exact' in sys.argv:
        bad = 0
        for e in prov:
            if e['status'] != 'exact':
                continue
            m = e['matches'][0]
            classifier = None
            if 'netty-transport-native-epoll' in e['path']:
                classifier = 'linux-x86_64'
            actual = repo1_sha1(m['g'], m['a'], m['v'], classifier)
            if actual != e['sha1']:
                bad += 1
                print(f"MISMATCH {e['path']}: repo1={actual} recorded={e['sha1']}")
            time.sleep(0.1)
        print(f'verify-exact: {bad} mismatches')
        sys.exit(1 if bad else 0)
    if '--classify-none' in sys.argv:
        for e in prov:
            if e['status'] != 'none' or e.get('reason'):
                continue
            name = e['path'].rsplit('/', 1)[-1]
            artifact, version = split_name(name)
            gavs = search_versions(artifact)
            same_version = [(g, a, v) for (g, a, v) in gavs if v == version]
            if same_version:
                g, a, v = same_version[0]
                actual = repo1_sha1(g, a, v)
                if actual == e['sha1']:
                    e['reason'] = f'MATCHES {g}:{a}:{v} on repo1; reclassify as exact'
                else:
                    e['reason'] = (f'bytes differ from Central {g}:{a}:{v} '
                                   f'(repo1 sha1 {actual}); kept vendored')
            elif gavs:
                vs = sorted({v for (_, _, v) in gavs})[-5:]
                e['reason'] = (f'version {version} never published to Central '
                               f'(artifact exists; recent versions: {", ".join(vs)})')
            else:
                e['reason'] = 'no artifact of this name on Maven Central'
            print(f"{e['path']}: {e['reason']}")
            changed = True
            time.sleep(0.2)
    if changed:
        json.dump(prov, open(PROV, 'w'), indent=1)
        print('jar-provenance.json updated')

main()
