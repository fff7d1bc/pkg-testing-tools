import argparse
import datetime
import sys
import os
import subprocess
import json
import portage
from tempfile import NamedTemporaryFile
from .use import get_package_flags, get_use_combinations


def temporary_package_file(directory_name):
    target_location = os.path.join('/etc/portage', directory_name)

    if not os.path.isdir(target_location):
        edie("The location {} needs to exist and be a directory".format(target_location))

    fd = NamedTemporaryFile(
        mode='w',
        prefix='zzz_pkg_testing_tool_',
        dir=target_location
    )
    umask = os.umask(0)
    os.umask(umask)
    os.chmod(fd.name, 0o644 & ~umask)
    return fd


def process_args():
    parser = argparse.ArgumentParser()

    required = parser.add_argument_group('Required')
    required.add_argument(
        '-p', '--package-atom', action='append', required=True,
        help="Valid Portage package atom, like '=app-category/foo-1.2.3'. Can be specified multiple times to unmask/keyword all of them and test them one by one."
    )

    optional = parser.add_argument_group('Optional')

    optional.add_argument(
        '--append-required-use', action='store', type=str, required=False,
        help="Append REQUIRED_USE entries, useful for blacklisting flags, like '!systemd !libressl' on systems that runs neither. The more complex REQUIRED_USE, the longer it take to get USE flags combinations."
    )

    optional.add_argument(
        '--max-use-combinations', action='store', type=int, required=False, default=16,
        help="Generate up to N combinations of USE flags, the combinations are random out of those which pass check for REQUIRED_USE. Default: 16."
    )

    optional.add_argument(
        '--use-flags-scope', action='store', type=str, required=False, default='local', choices=['local', 'global'],
        help="Local sets USE flags for package specified by atom, global sets flags for */*."
    )

    optional.add_argument(
        '--test-feature-scope', action='store', type=str, required=False, default='once', choices=['once', 'always', 'never'],
        help="Enables FEATURES='test' once, for default use flags, always, for every run or never. Default: once."
    )

    optional.add_argument(
        '--report', action='store', type=str, required=False,
        help="Save report in JSON format under specified path."
    )

    args, extra_args = parser.parse_known_args()
    if extra_args:
        if extra_args[0] != '--':
            parser.error(f"Custom arguments that are meant to be passed to mksquashfs are to be palced after '--'.")
        extra_args.remove('--')

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    return args, extra_args


def eerror(msg):
    print("[ERROR] >>> {}".format(msg))


def einfo(msg):
    print("[INFO] >>> {}".format(msg))


def edie(msg):
    eerror(msg)
    sys.exit(1)


def run_testing(package, use_flags_scope, flags_set, test_feature_toggle):
    time_started = datetime.datetime.now().replace(microsecond=0).isoformat()

    cpv = portage.dep.dep_getcpv(package)
    cp = portage.versions.pkgsplit(cpv)[0]

    emerge_cmdline = [
        'emerge',
        '--verbose', 'y',
        '--autounmask', 'n',
        '--usepkg-exclude', cp,
        package
    ]

    env = os.environ.copy()

    features = 'multilib-strict collision-protect sandbox userpriv usersandbox'

    if test_feature_toggle:
        features = '{} {}'.format(features, 'test')

    if 'FEATURES' in env:
        env['FEATURES'] = "{} {}".format(env['FEATURES'], features)
    else:
        env['FEATURES'] = features

    with temporary_package_file('package.use') as tmp_package_use:
        if flags_set:
            tmp_package_use.write(
                '{prefix} {flags}\n'.format(
                    prefix=('*/*' if use_flags_scope == 'global' else package),
                    flags=" ".join(flags_set)
                )
            )
            tmp_package_use.flush()
        emerge_result = subprocess.run(emerge_cmdline, env=env)
        print('')

        return {
            'use_flags': " ".join(flags_set),
            'exit_code': emerge_result.returncode,
            'features': portage.settings.get('FEATURES'),
            'emerge_default_opts': portage.settings.get('EMERGE_DEFAULT_OPTS'),
            'emerge_cmdline': " ".join(emerge_cmdline),
            'atom': package,
            'time': {
                'started': time_started,
                'finished': datetime.datetime.now().replace(microsecond=0).isoformat(),
            }
        }


def test_package(atom, args):
    results = []

    iuse, ruse = get_package_flags(atom)

    if args.append_required_use:
        ruse.append(args.append_required_use)

    if iuse:
        use_combinations = get_use_combinations(iuse, ruse, args.max_use_combinations)
    else:
        use_combinations = None

    if use_combinations:
        if args.test_feature_scope == 'always':
            test_feature_toggle = True
        else:
            test_feature_toggle = False

        use_combinations_pass = 0
        for flags_set in use_combinations:
            use_combinations_pass += 1
            einfo(
                "Running {pass_num} of {total} build for '{package}' with '{flags}' USE flags ...".format(
                    pass_num=use_combinations_pass,
                    total=len(use_combinations),
                    package=atom,
                    flags=" ".join(flags_set)
                )
            )

            results.append(
                run_testing(atom, args.use_flags_scope, flags_set, test_feature_toggle)
            )

    if args.test_feature_scope in ['once', 'always']:
        test_feature_toggle = True
    else:
        test_feature_toggle = False

    if not use_combinations or args.test_feature_scope == 'once':
        if use_combinations and args.test_feature_scope == 'once':
            einfo("Additional run for '{package}' with FEATURES=test and default USE flags since test-feature-scope is set to 'once'.".format(package=atom))
        elif args.test_feature_scope == 'never':
            einfo("Running build for '{package}' with default USE flags ...".format(package=atom))
        else:
            einfo("Running build for '{package}' with default USE flags and FEATURES=test ...".format(package=atom))

        results.append(
            run_testing(atom, args.use_flags_scope, [], test_feature_toggle)
        )

    return results


def pkg_testing_tool(args, extra_args):
    results = []

    # Unconditionally unmask and keyword packages selected by atom.
    # No much of a reason to check what arch we're running or if package is masked in first place.
    with \
        temporary_package_file('package.accept_keywords') as tmp_package_accept_keywords, \
        temporary_package_file('package.unmask') as tmp_package_unmask:

            # Unmask and keyword all the packages prior to testing them.
            for atom in args.package_atom:
                tmp_package_accept_keywords.write("{atom} **\n".format(atom=atom))
                tmp_package_unmask.write("{atom}\n".format(atom=atom))

            tmp_package_accept_keywords.flush()
            tmp_package_unmask.flush()

            for atom in args.package_atom:
                results.extend(
                    test_package(atom, args)
                )

    failures = []
    for item in results:
        if item['exit_code'] != 0:
            failures.append(item)

    if args.report:
        with open(args.report, 'w') as report:
            report.write(json.dumps(results, indent=4, sort_keys=True))

    if len(failures) > 0:
        eerror('Not all runs were successful.')
        for entry in failures:
            print(
                "atom: {atom}, USE flags: '{use_flags}'".format(
                    atom=entry['atom'],
                    use_flags=entry['use_flags']
                )
            )
        sys.exit(1)
    else:
        einfo('All good.')


def main():
    args, extra_args = process_args()
    pkg_testing_tool(args, extra_args)
