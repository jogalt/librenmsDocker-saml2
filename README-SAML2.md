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
