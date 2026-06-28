# oie-build-parity

Byte-level build-parity verification tooling for the
[Open Integration Engine](https://github.com/OpenIntegrationEngine/engine)
Ant-to-Gradle migration ([engine PR #326](https://github.com/OpenIntegrationEngine/engine/pull/326)).

These are the manual, human-run scripts that prove the new Gradle build
produces the same distribution as the old Ant build, archive by archive,
entry by entry. They are not part of the engine build or its CI; nothing
automated depends on them. They live here so anyone can reproduce the
byte-identical result independently rather than taking it on trust.

The comparison is still reproducible after the migration merges: the
Ant build is deleted by the migration commit, but its direct parent
`8c1111ba3` remains in the engine's history forever, so the old Ant tree
can be checked out and built at any time.

## Quick start

All paths below are absolute, so it does not matter which directory you run
from. Set the two variables once and paste the rest.

```bash
# 1. This tooling
git clone https://github.com/pacmano1/oie-build-parity
PARITY="$(cd oie-build-parity && pwd)"

# 2. The engine (skip the clone if you already have it; just point ENGINE at it)
git clone https://github.com/OpenIntegrationEngine/engine
ENGINE="$(cd engine && pwd)"

# 3. Ant baseline at the migration's parent commit, in a throwaway worktree
git -C "$ENGINE" worktree add /tmp/oie-ant 8c1111ba3
(cd /tmp/oie-ant/server && ant -f mirth-build.xml -DdisableSigning=true -DdisableTests=true build)

# 4. Gradle build of the migration branch (use the SAME JDK build for both,
#    and the SAME calendar day: version.properties embeds the build date).
#    Gradle build flags are project properties (-P); the Ant baseline above
#    uses Ant's own -D syntax.
(cd "$ENGINE" && ./gradlew clean build dist -PdisableSigning=true)

# 5. Compare every archive, entry by entry (absolute paths; cwd-independent)
python3 "$PARITY/compare_builds.py" /tmp/oie-ant/server/setup "$ENGINE/server/setup"

# 6. Cleanup
git -C "$ENGINE" worktree remove --force /tmp/oie-ant
```

Expected result: `REAL differences (0)`. The Ant baseline builds in
seconds (that is normal, not a short-circuit); the Gradle build takes a
few minutes and runs the full test suite. The worktree costs about a
gigabyte of disk until removed.

## compare_builds.py

Compares two distribution trees (e.g. two `server/setup` snapshots) at the
archive-entry level:

```bash
python3 compare_builds.py <baseline-setup> <candidate-setup>
```

Both arguments are directory paths. A relative path is resolved from your
current directory, so a wrong cwd shows up as every file "missing from" one
side; pass absolute paths (or run from a known directory) to avoid that.

Every file is byte-compared. Jars and zips that differ are compared entry
by entry. Differences that are pure tool metadata are classified and
reported separately:

- manifest `Ant-Version` / `Created-By` attributes
- zip entry timestamps and ordering
- the `version.properties` timestamp comment (differs between any two
  builds of the old Ant system as well)
- empty `package-info.class` markers present only in the Ant baseline:
  Ant's javac emitted an inert, empty `package-info.class` for every
  annotation-free `package-info.java`; the Gradle build does not
  reproduce these (a documented, zero-runtime-effect difference), so
  ant-only markers of that shape are classified as expected, not real

Anything else is a real difference and fails the run. The Gradle
migration was accepted with all archives' entry contents identical
against an Ant baseline built on the same machine, modulo the classified
metadata above.

`compare_builds.py` is also useful beyond the migration: it diffs any two
`server/setup` trees, so it answers "did this build-logic change alter the
product?" for two Gradle builds, with no Ant involved.

## snapshot_distribution.py

The lightweight half of the build-logic change-safety protocol. It writes
one `sha256sum`-style line per file of a `server/setup` tree, sorted, so a
plain `diff` of two snapshots shows exactly which distribution files a
build-logic change touched:

```bash
python3 snapshot_distribution.py <engine>/server/setup > before.txt
# ... make your build-logic change, rebuild ...
python3 snapshot_distribution.py <engine>/server/setup > after.txt
diff before.txt after.txt
```

Only the files you intended to change should appear. For archive-entry-level
analysis of any file that does differ, use `compare_builds.py`. This
replaces the in-build `snapshotDistribution` task that previously lived in
the engine's `build.gradle`.

## jar-provenance.json

The result of SHA-1 matching every vendored jar against Maven Central
(June 2026): 374 of 419 jars were byte-identical to published artifacts
and were replaced by version-catalog dependencies
(`gradle/libs.versions.toml`, placement map in
`gradle/vendored-layout.json`). Caveat learned the hard way: the Central
*search index* lacks checksum documents for some artifacts, so a
"no match" from the search API must be confirmed against
`repo1.maven.org/.../<artifact>.jar.sha1` before being believed
(that is how postgresql, jsch, and snakeyaml were rescued from the
unmatched list).

The 45 unmatched jars remain vendored in the module `lib/` directories.
Notable cases, worth auditing before ever upgrading them blindly:

- HAPI 2.3 jars (`server/lib/hapi/` and `client/lib/`): long believed
  to be Mirth-patched, but entry-level comparison proves they are
  content-identical to Central's HAPI 2.3, only repackaged. Kept
  vendored under the file-level SHA-exact policy.
- `mirth-vocab.jar` (generated in-house by the `generator` module)
- dcm4che 2.x (never published to Maven Central)
- `wsdl4j-1.6.2-fixed.jar` (locally patched, per its own name)
- `jtds-1.3.1` and `sqlite-jdbc-3.43.2.1`: content identical to
  Central, repackaged containers only. Kept vendored.
- Genuinely locally modified (verified class-level differences):
  `javaparser-1.0.8` (114 classes), `zip4j_1.3.3` (60),
  `not-going-to-be-commons-ssl-0.3.18` (2). Treat these as forks.

Resolved dependencies are pinned non-transitively so the runtime artifact
set is exactly the audited vendored set, and every resolution is
checksum-enforced by the engine's `gradle/verification-metadata.xml`.

`sweep_provenance.py --verify-exact` re-downloads each matched jar's
checksum from Maven Central and confirms it still matches; expect
`0 mismatches`. It reads `jar-provenance.json` for the coordinates.

## The acceptance baseline

The migration was accepted against an Ant build of commit `8c1111ba3`
(the migration commit's direct parent), built with Ant 1.10.14 on Zulu
JDK 17.0.17+10, hashed with the
[oie-release-verifier](https://github.com/OpenIntegrationEngine/release-verifier)
toolkit: every jar expanded, version/javadoc noise normalized, one SHA
line per file.

The hash file itself is NOT committed (5MB of generated data); its
SHA-256 is pinned here and the file is published as a release asset on
the engine fork, linked from the migration pull request:

```
e54cb2ef8c30ea887fb6752fc83a4dbf9fd818de3267177d29d6d2a1eaf3f6e4  ant-baseline-hashes.txt
```

The hashes embed one specific javac's output, so they are not portable
across JDK builds. The reproducible procedure is the dual build shown in
Quick start, on any machine.

Known metadata-only deltas, classified automatically by the comparator:
manifest `Ant-Version`/`Created-By` attributes, zip entry
timestamps/ordering, the `version.properties` comment line, and two
directory-only entries.

### Running the verifier route itself

Requires `bash` and `unzip`; `verify.sh` also calls `sha256sum`, so on
macOS install coreutils or substitute `shasum -a 256`:

```bash
git clone https://github.com/OpenIntegrationEngine/release-verifier
cd release-verifier            # required: verify.sh calls ./hash.sh etc.
./verify.sh /tmp/oie-ant/server/setup /tmp/ant-hashes.txt
./verify.sh <engine>/server/setup /tmp/gradle-hashes.txt
wc -l /tmp/ant-hashes.txt /tmp/gradle-hashes.txt   # sanity: both non-empty
diff /tmp/ant-hashes.txt /tmp/gradle-hashes.txt
```

Pitfall, learned by hitting it: `verify.sh` must run from inside its
checkout because it invokes its sibling scripts by relative path. Run
from anywhere else it prints an error but still exits 0 and writes an
EMPTY hash file, and two empty files diff as identical, a false pass.
The script prints the output file's SHA-256 when it finishes;
`e3b0c442...` is the hash of empty input and means the run produced
nothing. Hence the `wc -l` sanity line.

Expected: changed lines only for the per-archive `MANIFEST.MF` (the
`Ant-Version` attribute the comparator also classifies) and the
`version.properties` copies (they embed the full build timestamp, so any
two runs differ).

## Signed-build check

Signing is on by default in the engine build (the committed development
keystore; `-PdisableSigning=true` skips it). The 216 jars that ship
signed are the client-lib and extension jars:

```bash
cd engine
./gradlew clean build dist
find server/setup/client-lib server/setup/extensions -name '*.jar' \
  -exec jarsigner -verify -strict {} \;
```

Expected: all 216 verify; `-strict` additionally warns that the
certificate chain is self-signed, which is a property of the
development keystore, not the build. The old build's output warns
identically.

## Entry-level check of a vendored holdout

Each vendored jar's grouping (content-identical vs genuinely modified) is
re-checkable per jar against the coordinate recorded in its
`jar-provenance.json` reason:

```bash
curl -sLO https://repo1.maven.org/maven2/<g-as-path>/<a>/<v>/<a>-<v>.jar
mkdir ours theirs
(cd ours && unzip -q ../<vendored>.jar); (cd theirs && unzip -q ../<a>-<v>.jar)
diff -r ours theirs
```

Expected: zero differing entries for the thirteen repackaged-identical
jars; exactly 114, 60, and 2 differing `.class` files for
`javaparser-1.0.8`, `zip4j_1.3.3`, and
`not-going-to-be-commons-ssl-0.3.18` respectively.

## Cross-check against the published v4.6.0-rc1 release

`compare_builds.py --ignore-signatures` was also run between the
published `oie_unix_4_6_0-rc1.tar.gz` (signed, CI-built from
`cd1110e30`) and a local unsigned Ant build of the same commit:
473 of 490 archives byte-identical in content. The remaining deltas are
all properties of the release pipeline, not the build: signature files
and JWS manifest attributes (tolerated by the flag), `module-info.class`
rewrites in 16 third-party modular jars (the signing flow's `jar umf`
step rewrites the archive and the jar tool recomputes module
attributes; the signed Gradle path runs the identical step), and the
install4j launcher files that the installer packaging adds after the
build.

To reproduce:

```bash
curl -sLO https://github.com/OpenIntegrationEngine/engine/releases/download/v4.6.0-rc1/oie_unix_4_6_0-rc1.tar.gz
shasum -a 256 oie_unix_4_6_0-rc1.tar.gz
# expect 5fd22916ebe347bb52c935df7e121eea4d4f089541dfe44c799cb4f817854c77
# (the release also publishes an md5sums asset)
tar xzf oie_unix_4_6_0-rc1.tar.gz                # extracts to oie/
git worktree add /tmp/oie-rc1-src cd1110e30
(cd /tmp/oie-rc1-src/server && ant -f mirth-build.xml -DdisableSigning=true -DdisableTests=true build)
python3 compare_builds.py --ignore-signatures oie /tmp/oie-rc1-src/server/setup
git worktree remove --force /tmp/oie-rc1-src     # cleanup
```

## License

[MPL-2.0](./LICENSE). Developed with the moral support of Finnegan the dog.
