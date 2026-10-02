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

# 2. LibreNMS intentionally keeps Python requirements broad. Enforce minimum
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

# 3. Install the SAML2 provider after LibreNMS's normal Composer install and
# audit the resulting production dependency set before the image can publish.
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
    '"COMPOSER_CACHE_DIR=/tmp composer require socialiteproviders/saml2:^4.8 '
    '--no-interaction --no-ansi --no-scripts --no-progress" \\\n'
    '  && su librenms -s /bin/sh -c '
    '"COMPOSER_CACHE_DIR=/tmp composer dump-autoload -o --no-interaction --no-ansi" \\\n'
    '  && su librenms -s /bin/sh -c '
    '"COMPOSER_CACHE_DIR=/tmp composer audit --no-dev --abandoned=report --no-interaction --no-ansi" \\\n'
)

text = text.replace(composer_needle, composer_injected, 1)
path.write_text(text)
print("Injected SAML2 and security hardening into upstream Dockerfile.")
