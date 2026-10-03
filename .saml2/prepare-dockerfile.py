#!/usr/bin/env python3
"""Apply fork-only SAML2 and security hardening to upstream LibreNMS Dockerfile.

This runs only in the GitHub Actions workspace. The tracked upstream Dockerfile
is never committed with local modifications, which keeps upstream sync clean.
"""
from pathlib import Path
import sys

path = Path("Dockerfile")
text = path.read_text()

# 1. Refresh Alpine packages in the final image before installing LibreNMS's
# package set. This picks up patched packages available in the same Alpine
# release without changing the upstream base-release selection.
apk_anchor = "COPY --from=gosu /gosu /usr/local/bin/\n"
apk_upgrade = "\nRUN apk --update --no-cache upgrade\n"

if apk_upgrade not in text:
    if text.count(apk_anchor) != 1:
        sys.exit(
            "Refusing to patch: expected exactly one gosu COPY anchor, "
            f"found {text.count(apk_anchor)}. Upstream Dockerfile changed; review the hardening injector."
        )
    text = text.replace(apk_anchor, apk_anchor + apk_upgrade, 1)

# 2. Keep Alpine's package-managed pip for the build instead of upgrading pip
# in-place with pip itself. pip 26.x vendors its own urllib3/msgpack/setuptools
# copies; self-upgrading Alpine's py3-pip can leave untracked vendor files behind
# after `apk del py3-pip`, which vulnerability scanners continue to see.
pip_upgrade_cmd = "pip3 install --upgrade --break-system-packages pip"

if pip_upgrade_cmd in text:
    if text.count(pip_upgrade_cmd) != 1:
        sys.exit(
            "Refusing to patch: expected exactly one upstream pip self-upgrade command, "
            f"found {text.count(pip_upgrade_cmd)}. Upstream Dockerfile changed; review the hardening injector."
        )
    text = text.replace(pip_upgrade_cmd, "pip3 --version", 1)

# 3. LibreNMS intentionally keeps Python requirements broad. Enforce minimum
# patched versions for currently known fixable high-severity findings while
# leaving upstream's requirements.txt untouched.
python_needle = (
    "  && pip3 install --ignore-installed -r requirements.txt --upgrade --break-system-packages \\\n"
)
python_marker = '"urllib3>=2.8.0,<3"'

if python_marker not in text:
    if text.count(python_needle) != 1:
        sys.exit(
            "Refusing to patch: expected exactly one upstream Python requirements install line, "
            f"found {text.count(python_needle)}. Upstream Dockerfile changed; review the hardening injector."
        )
    python_injected = python_needle + (
        '  && pip3 install --upgrade --break-system-packages '
        '"urllib3>=2.8.0,<3" "setuptools>=78.1.1" "jaraco.context>=6.1.0,<7" \\\n'
        '  && pip3 check \\\n'
    )
    text = text.replace(python_needle, python_injected, 1)

# 4. Start from LibreNMS's release lock, selectively move known vulnerable
# Composer packages to compatible fixed releases, add SAML2, report the complete
# audit, and block publication only when High/Critical advisories remain.
saml_marker = "socialiteproviders/saml2"
composer_needle = (
    '  && su librenms -s /bin/sh -c '
    '"COMPOSER_CACHE_DIR=/tmp composer install --no-dev --no-interaction --no-ansi" \\\n'
)

if saml_marker in text:
    sys.exit(
        "Refusing to patch: Dockerfile already contains socialiteproviders/saml2. "
        "Review upstream before continuing."
    )

if text.count(composer_needle) != 1:
    sys.exit(
        "Refusing to patch: expected exactly one upstream Composer install line, "
        f"found {text.count(composer_needle)}. Upstream Dockerfile changed; review the SAML injector."
    )

composer_injected = composer_needle + (
    '  && su librenms -s /bin/sh -c '
    '"FORCE=1 COMPOSER_CACHE_DIR=/tmp composer update '
    'laravel/framework league/commonmark league/flysystem phpseclib/phpseclib '
    '--with-all-dependencies --minimal-changes --no-dev '
    '--no-interaction --no-ansi --no-progress" \\\n'
    '  && su librenms -s /bin/sh -c '
    '"COMPOSER_CACHE_DIR=/tmp composer require socialiteproviders/saml2:^4.8 '
    '--no-interaction --no-ansi --no-scripts --no-progress" \\\n'
    '  && su librenms -s /bin/sh -c '
    '"COMPOSER_CACHE_DIR=/tmp composer dump-autoload -o --no-interaction --no-ansi" \\\n'
    # Report all production advisories. Do not make Low/Medium findings abort
    # the build; the second audit below is the release gate.
    '  && su librenms -s /bin/sh -c '
    '"COMPOSER_CACHE_DIR=/tmp composer audit --no-dev --abandoned=report '
    '--no-interaction --no-ansi || true" \\\n'
    # Fail if any High/Critical production Composer advisory remains.
    '  && su librenms -s /bin/sh -c '
    '"COMPOSER_CACHE_DIR=/tmp composer audit --no-dev --abandoned=report '
    '--ignore-severity=low --ignore-severity=medium --no-interaction --no-ansi" \\\n'
    # LibreNMS Docker disables in-container code updates and is upgraded by
    # replacing the image. pip is therefore build-time tooling here. Remove it
    # from the runtime image after all Python dependencies have been installed.
    # This also removes pip's vendored dependency copies/SBOM, which otherwise
    # surface as urllib3/msgpack/setuptools CVEs even when the runtime copies
    # have already been upgraded.
    '  && python3 -c "import pymysql, dotenv, redis, setuptools, psutil, command_runner; '
    'print(\'LibreNMS Python runtime dependencies import successfully\')" \\\n'
    '  && apk del py3-pip \\\n'
    # Defensive cleanup for both Python installation prefixes. If an older
    # image ever self-upgraded pip over Alpine's package, added vendor files may
    # not have been tracked by apk and can otherwise survive package removal.
    '  && rm -rf /usr/lib/python*/site-packages/pip '
    '/usr/lib/python*/site-packages/pip-*.dist-info '
    '/usr/local/lib/python*/site-packages/pip '
    '/usr/local/lib/python*/site-packages/pip-*.dist-info '
    '/root/.cache/pip \\\n'
    '  && rm -f /usr/bin/pip /usr/bin/pip3 /usr/bin/pip3.* '
    '/usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.* \\\n'
)

text = text.replace(composer_needle, composer_injected, 1)

# 5. Upstream uses gosu in both CLI wrappers: /usr/local/bin/artisan and
# /usr/bin/lnms. The same image already uses s6-setuidgid throughout its service
# scripts. Replace both wrappers with the equivalent s6 helper before removing
# the gosu stage/copy so no startup or operator CLI path still depends on gosu.
wrapper_replacements = [
    (
        Path("rootfs/usr/local/bin/artisan"),
        'gosu librenms:librenms php artisan "$@"',
        'exec s6-setuidgid librenms php artisan "$@"',
    ),
    (
        Path("rootfs/usr/bin/lnms"),
        'gosu librenms:librenms php -f /opt/librenms/lnms "$@"',
        'exec s6-setuidgid librenms php -f /opt/librenms/lnms "$@"',
    ),
]

for wrapper_path, gosu_command, s6_command in wrapper_replacements:
    wrapper_text = wrapper_path.read_text()
    if s6_command not in wrapper_text:
        if wrapper_text.count(gosu_command) != 1:
            sys.exit(
                f"Refusing to patch: expected exactly one gosu invocation in {wrapper_path}. "
                "Upstream wrapper changed; review before removing gosu."
            )
        wrapper_text = wrapper_text.replace(gosu_command, s6_command, 1)
        wrapper_path.write_text(wrapper_text)

# Refuse to remove gosu if upstream adds another runtime reference. This makes
# an upstream change fail visibly instead of publishing an image that starts but
# later breaks on an unpatched helper script.
remaining_gosu_refs = []
for candidate in Path("rootfs").rglob("*"):
    if not candidate.is_file():
        continue
    try:
        candidate_text = candidate.read_text()
    except UnicodeDecodeError:
        continue
    for lineno, line in enumerate(candidate_text.splitlines(), 1):
        if "gosu" in line:
            remaining_gosu_refs.append(f"{candidate}:{lineno}: {line.strip()}")

if remaining_gosu_refs:
    sys.exit(
        "Refusing to remove gosu: runtime references remain after wrapper replacement:\n"
        + "\n".join(remaining_gosu_refs)
    )

gosu_stage = "FROM tianon/gosu:latest AS gosu\n\n"
gosu_copy = "COPY --from=gosu /gosu /usr/local/bin/\n"

if text.count(gosu_stage) != 1 or text.count(gosu_copy) != 1:
    sys.exit(
        "Refusing to patch: expected one upstream gosu stage and one gosu COPY. "
        "Upstream Dockerfile changed; review before removing gosu."
    )

text = text.replace(gosu_stage, "", 1)
text = text.replace(gosu_copy, "", 1)

path.write_text(text)
print("Injected SAML2/security hardening, replaced gosu CLI wrappers, and removed gosu.")
