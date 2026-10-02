# LibreNMS SAML2 fork maintenance

This fork is designed so LibreNMS upstream synchronization cannot silently
replace the SAML2 customization.

## Fork-owned files

Only these files are fork-specific:

- `Dockerfile.saml2`
- `README-SAML2.md`
- `.github/workflows/build-saml2.yml`
- `.github/workflows/sync-upstream.yml`

Everything else belongs to `librenms/docker` upstream and should remain
unmodified in this fork.

## Build and publish

No local Docker build is required. GitHub Actions builds and publishes:

`jogaltanon/librenms-saml2:latest`

The workflow uses the existing repository credentials:

- Repository variable: `DOCKER_USERNAME`
- Repository secret: `DOCKER_PASSWORD`

The image extends `librenms/librenms:latest` and installs
`socialiteproviders/saml2:^4.8`.

## Synchronize with LibreNMS upstream

Do not use `git reset --hard upstream/master` on the customized branch.

Use the GitHub workflow instead:

1. Open **Actions** in `jogalt/librenmsDocker-saml2`.
2. Select **sync-upstream**.
3. Select **Run workflow**.

The workflow:

1. Fetches `https://github.com/librenms/docker.git` branch `master`.
2. Merges it into this repository's `master` branch.
3. Verifies all four fork-owned files are byte-for-byte unchanged.
4. Verifies the fork differs from current upstream only by those four files.
5. Pushes the synchronized `master` only if all checks pass.
6. Calls `build-saml2` to publish a refreshed `jogaltanon/librenms-saml2:latest`.

If upstream ever creates one of the same custom filenames, changes result in a
merge conflict, or another fork-only file is introduced, the synchronization
fails before pushing rather than overwriting anything.

## Manual Git synchronization

If GitHub Actions cannot push because of branch protection, the equivalent safe
Git-only operation is:

```bash
git switch master
git fetch origin --prune
git reset --hard origin/master
git remote add upstream https://github.com/librenms/docker.git 2>/dev/null || \
  git remote set-url upstream https://github.com/librenms/docker.git
git fetch upstream --prune
git merge --no-edit upstream/master
git push origin master
```

This is a Git synchronization only. There is no local Docker build. A normal
human push that changes `Dockerfile.saml2` triggers the GitHub build workflow.
