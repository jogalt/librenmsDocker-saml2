# LibreNMS SAML2 Docker image

This fork publishes `jogaltanon/librenms-saml2:latest` with
`socialiteproviders/saml2:^4.8` installed in LibreNMS.

## Design

The repository keeps LibreNMS upstream-owned files unchanged in Git. In
particular, `Dockerfile`, `docker-bake.hcl`, `rootfs/`, `examples/`, and `test/`
are allowed to sync directly from `librenms/docker:master`.

Fork-specific behavior is limited to:

- `.saml2/prepare-dockerfile.py`
- `.github/workflows/build-saml2.yml`
- `.github/workflows/sync-upstream.yml`
- `README-SAML2.md`

During a GitHub Actions build, `prepare-dockerfile.py` modifies the checked-out
upstream `Dockerfile` **only in the runner workspace** by inserting the SAML2
Composer dependency immediately after LibreNMS's normal Composer install.
Nothing writes that modified Dockerfile back to the repository.

The build then runs upstream's `image-all` Bake target. Therefore the SAML2
image follows the platform list defined by the current upstream
`docker-bake.hcl`; no architecture list is duplicated in this fork.

## Update LibreNMS

Run the `sync-upstream` workflow against `master`.

It fetches and merges `librenms/docker:master`, verifies the four custom files
are unchanged, verifies there are no unexpected fork-only files, pushes the
updated `master`, and invokes `build-saml2` if upstream changed.

## Build manually in GitHub

Run the `build-saml2` workflow against `master`. No local Docker build is
required.

## Safety behavior

If upstream changes the Composer-install portion of its Dockerfile enough that
the injector can no longer identify it unambiguously, the build fails instead
of guessing or silently publishing an image without SAML support.

## Security hardening and promotion gate

The runner-only Dockerfile injector also performs conservative remediation that
can be applied without changing LibreNMS source files:

- upgrades packages available within the selected Alpine release (`apk upgrade`);
- requires `urllib3>=2.8.0,<3`;
- requires `setuptools>=78.1.1`;
- requires `jaraco.context>=6.1.0,<7`;
- runs `pip check` after the Python dependency update;
- runs `composer audit --no-dev --abandoned=report` after installing SAML2.

The GitHub build no longer writes directly to `:latest`. It first publishes an
immutable `sha-<commit>` candidate, scans every platform from upstream's
`image-all` target, and promotes that exact manifest to `:latest` only when all
platforms pass the blocking scan.

Promotion is blocked for fixable Critical/High vulnerabilities in Alpine (`apk`)
and Python (`pypi`) packages. Go findings are still reported, but are not used as
a generic blocking gate because the upstream `gosu` project requires Go CVEs to
be evaluated for reachable vulnerable code with `govulncheck` rather than by Go
stdlib version alone.

`sync-upstream` runs hourly at minute 17 and still supports manual dispatch. If
upstream has not changed, it does not invoke a new image build.

## Composer security remediation

The build starts with the Composer lock shipped by the selected LibreNMS release,
then performs a targeted minimal-change update of `laravel/framework`,
`league/commonmark`, `league/flysystem`, and `phpseclib/phpseclib`. This avoids a
blanket dependency refresh while allowing published security fixes to move ahead
of the release lock when needed. All production Composer advisories are reported;
remaining High/Critical advisories block publication, while Low/Medium findings
remain visible for review.
