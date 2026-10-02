#!/usr/bin/env python3
"""Inject the SAML2 Composer provider into the upstream LibreNMS Dockerfile.

This runs only in the GitHub Actions workspace.  The tracked upstream Dockerfile
is never committed with local modifications, which keeps upstream sync clean.
"""
from pathlib import Path
import sys

path = Path("Dockerfile")
text = path.read_text()

marker = 'socialiteproviders/saml2'
if marker in text:
    sys.exit(
        "Refusing to patch: Dockerfile already contains socialiteproviders/saml2. "
        "Review upstream before continuing."
    )

needle = (
    '  && su librenms -s /bin/sh -c '
    '"COMPOSER_CACHE_DIR=/tmp composer install --no-dev --no-interaction --no-ansi" \\\n'
)

if text.count(needle) != 1:
    sys.exit(
        "Refusing to patch: expected exactly one upstream Composer install line, "
        f"found {text.count(needle)}. Upstream Dockerfile changed; review the SAML injector."
    )

injected = needle + (
    '  && su librenms -s /bin/sh -c '
    '"COMPOSER_CACHE_DIR=/tmp composer require socialiteproviders/saml2:^4.8 '
    '--no-interaction --no-ansi --no-scripts --no-progress" \\\n'
    '  && su librenms -s /bin/sh -c '
    '"COMPOSER_CACHE_DIR=/tmp composer dump-autoload -o --no-interaction --no-ansi" \\\n'
)

path.write_text(text.replace(needle, injected, 1))
print("Injected SocialiteProviders SAML2 into upstream Dockerfile.")
