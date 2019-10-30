# pkg-testing-tool

Package testing tool for arch stabilizations, regular bumps of packages and testing of masked packages.

## Motivation

Currently there's hardy any tool that beside arch testing can also do regular testing of packages specified by atoms. The only real alternative is `tatt`, which however is not really suitable for unattended testing, as it lacks some proper machine readable output formats and have limited quality of life features I've decided to write a tool that can be both unattended and flexible enough to allow end-user to exclude some USE flags from scope, like systemd or libressl, if neither of those are currently used on the system, with configurable switch to control how many combinations of USE flags one want to test. With optional machine-readable JSON format of reports, this tool be integrated into CI machintery with limited effort.

## Scope

The tool is limited to single runtime environment, lacks any network features like remote parallel testing and bugzilla integration -- all of those are supposed to be supported by another tool, while leaving pkg-testing-tool as a single tool for single job.

## Example usage

```
export FEATURES='buildpkg' 
export PKGDIR='/mnt/storage/binpkgs'
export EMERGE_DEFAULT_OPTS='--usepkg'

pkg-testing-tool \
    --package '=dev-vcs/git-2.23.0-r1' \
    --append-required-use '!libressl' \
    --report /tmp/test-git-2.23.0-r1.json \
    --test-feature-scope always
```

## Switches

```
usage: pkg-testing-tool [-h] --package PACKAGE
                        [--append-required-use APPEND_REQUIRED_USE]
                        [--max-use-combinations MAX_USE_COMBINATIONS]
                        [--use-flags-scope {local,global}]
                        [--test-feature-scope {once,always,never}]
                        [--report REPORT]

optional arguments:
  -h, --help            show this help message and exit

Required:
  --package PACKAGE     Valid Portage package atom, like '=app-
                        category/foo-1.2.3'.

Optional:
  --append-required-use APPEND_REQUIRED_USE
                        Append REQUIRED_USE entries, useful for blacklisting
                        flags, like '!systemd !libressl' on systems that runs
                        neither. The more complex REQUIRED_USE, the longer it
                        take to get USE flags combinations.
  --max-use-combinations MAX_USE_COMBINATIONS
                        Generate up to N combinations of USE flags, the
                        combinations are random out of those which pass check
                        for REQUIRED_USE. Default: 16.
  --use-flags-scope {local,global}
                        Local sets USE flags for package specified by atom,
                        global sets flags for */*.
  --test-feature-scope {once,always,never}
                        Enables FEATURES='test' once, for default use flags,
                        always, for every run or never. Default: once.
  --report REPORT       Save report in JSON format under specified path.

```