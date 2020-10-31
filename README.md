# pkg-testing-tool

Package testing tool for arch stabilizations, regular bumps of packages and testing of masked packages.

## Motivation

Currently there's hardy any tool that beside arch testing can also do regular testing of packages specified by atoms. The only real alternative is `tatt`, which however is not really suitable for unattended testing, as it lacks some proper machine readable output formats and have limited quality of life features. I wanted a tool that can be both unattended and flexible enough to allow end-user to exclude some USE flags from scope, like systemd or libressl, if neither of those are currently used on the system, with configurable switch to control how many combinations of USE flags one want to test. With optional machine-readable JSON format of reports, this tool can be integrated into CI machintery with limited effort.

## Scope

The tool is limited to single runtime environment, lacks any network features like remote parallel testing and bugzilla integration -- all of those are supposed to be supported by another tool, while leaving pkg-testing-tool as a single tool for single job.

## Prerequisites

One need to have `env` and `package.*` under /etc/portage as directories in order for the tool to work.

```
install -m 0750 -o portage -g portage -d /etc/portage/env /etc/portage/package.{accept_keywords,env,unmask,use}
```

## How to use

It's highly recommend to use `pkg-testing-tool` along with `binpkgs`, `ccache` and parallel `emerge` jobs, especially when using a clean environment like chroot or virtual machine with shared binary packages. Unless `make.conf` already have all of those enabled, one can use something like the code below to switch those features on, although it should be tweaked depending on one's capacity:

```
export PKGDIR="/var/cache/binpkgs"
export CCACHE_DIR="/var/cache/ccache"
export CCACHE_SIZE="4G"
export MAKEOPTS="--quiet -j$(nproc) -l$(nproc)"
install -m 0750 -o portage -g portage -d "${PKGDIR}"
install -m 0750 -o portage -g portage -d "${CCACHE_DIR}"

```


Rather paranoid run of `git` without libressl, with json report saved to file, with FEATURES=test enabled on every run
```
pkg-testing-tool \
    --binpkg --ccache \
    --package-atom  '=dev-vcs/git-2.23.0-r1' \
    --append-required-use '!libressl' \
    --report /tmp/test-git-2.23.0-r1.json \
    --test-feature-scope always
```


Local to package atom flags are sometimes not desired, especially when one flag on package we test requires the same flag on it's dependencies. For this, one should switch to global flags, that work as if someone set the `$USE` environmental variable with them.
```
pkg-testing-tool --use-flags-scope global --package-atom '=dev-libs/boost-1.71.0'
