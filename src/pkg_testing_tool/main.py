import argparse
import datetime
import json
import os
import subprocess
import sys
from contextlib import ExitStack
from tempfile import NamedTemporaryFile
import shlex

import portage

from .use import get_package_flags, get_use_combinations


def get_etc_portage_tmp_file(directory_name):
    target_location = os.path.join('/etc/portage', directory_name)

    if not os.path.isdir(target_location):
        edie("The location {} needs to exist and be a directory".format(target_location))

    handler = NamedTemporaryFile(
        mode='w',
        prefix='zzz_pkg_testing_tool_',
        dir=target_location
    )

    umask = os.umask(0)
    os.umask(umask)
    os.chmod(handler.name, 0o644 & ~umask)

    return handler


def process_args():
    parser = argparse.ArgumentParser()

    required = parser.add_argument_group('Required')
    required.add_argument(
        '-p', '--package-atom', action='append', required=True,
        help="Valid Portage package atom, like '=app-category/foo-1.2.3'. Can be specified multiple times to unmask/keyword all of them and test them one by one."
    )

    optional = parser.add_argument_group('Optional')

    optional.add_argument(
        '--ask', action='store_true', required=False,
        help="Ask for confirmation before executing actual tests."
    )

    optional.add_argument(
        '--binpkg', action='store_true', required=False,
        help="Append --usepkg to emerge command and add buildpkg to FEATURES."
    )

    optional.add_argument(
        '--ccache', action='store_true', required=False,
        help="Add ccache to FEATURES."
    )

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

    optional.add_argument(
        '--extra-env-file', action='append', type=str, required=False,
        help="Extra /etc/portage/env/ file name, to be used while testing packages. Can be passed multile times."
    )

    optional.add_argument(
        '--append-emerge', action='store', type=str, required=False,
        help="Append flags or parameters to the actual emerge call."
    )

    args, extra_args = parser.parse_known_args()
    if extra_args:
        if extra_args[0] != '--':
            parser.error("Custom arguments that are meant to be passed to pkg-testing-tool are to be palced after '--'.")
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


def get_package_metadata(atom):
    cpv = portage.dep.dep_getcpv(atom)

    cp, version, revision = portage.versions.pkgsplit(cpv)

    iuse, ruse = get_package_flags(cpv)

    phases = portage.portdb.aux_get(cpv, ['DEFINED_PHASES'])[0].split()

    return {
        'atom': atom,
        'cp': cp,
        'cpv': cpv,
        'version': version,
        'revision': revision,
        'has_tests': ('test' in phases),
        'iuse': iuse,
        'ruse': ruse
    }


def run_testing(job, args):
    global_features = []

    time_started = datetime.datetime.now().replace(microsecond=0).isoformat()

    emerge_cmdline = [
        'emerge',
        '--verbose', 'y',
        '--usepkg-exclude', job['cp'],
        '--deep', '--backtrack', '300',
    ]
    if args.append_emerge:
        emerge_cmdline += shlex.split(args.append_emerge)

    if args.binpkg:
        emerge_cmdline.append('--usepkg')
        global_features.append('buildpkg')

    if args.ccache:
        if not portage.settings.get('CCACHE_DIR') or not portage.settings.get('CCACHE_SIZE'):
            eerror("The CCACHE_DIR and/or CCACHE_SIZE is not set!")
            sys.exit(1)
            
        global_features.append('ccache')

    emerge_cmdline.append(job['cpv'])

    with ExitStack() as stack:
        tmp_files = {}

        for directory in ['env', 'package.env', 'package.use']:
            tmp_files[directory] = stack.enter_context(get_etc_portage_tmp_file(directory))

        tested_cpv_features = ['qa-unresolved-soname-deps', 'multilib-strict']

        if job['test_feature_toggle']:
            tested_cpv_features.append('test')

        if tested_cpv_features:
            tmp_files['env'].write('FEATURES="{}"\n'.format(" ".join(tested_cpv_features)))

        env_files = [os.path.basename(tmp_files['env'].name)]

        if job['extra_env_files']:
            env_files.append(job['extra_env_files'])

        tmp_files['package.env'].write(
            "{cp} {env_files}\n".format(
                cp=job['cp'],
                env_files=" ".join(env_files)
            )
        )

        if job['use_flags']:
            tmp_files['package.use'].write(
                '{prefix} {flags}\n'.format(
                    prefix=('*/*' if job['use_flags_scope'] == 'global' else job['cpv']),
                    flags=" ".join(job['use_flags'])
                )
            )

        for handler in tmp_files:
            tmp_files[handler].flush()

        env = os.environ.copy()

        if global_features:
            if 'FEATURES' in env:
                env['FEATURES'] = "{} {}".format(env['FEATURES'], " ".join(global_features))
            else:
                env['FEATURES'] = " ".join(global_features)

        emerge_result = subprocess.run(emerge_cmdline, env=env)
        print('')

    return {
        'use_flags': " ".join(job['use_flags']),
        'exit_code': emerge_result.returncode,
        'features': portage.settings.get('FEATURES'),
        'emerge_default_opts': portage.settings.get('EMERGE_DEFAULT_OPTS'),
        'emerge_cmdline': " ".join(emerge_cmdline),
        'test_feature_toggle': job['test_feature_toggle'],
        'atom': job['cpv'],
        'time': {
            'started': time_started,
            'finished': datetime.datetime.now().replace(microsecond=0).isoformat(),
        }
    }


def define_jobs(atom, args):
    jobs = []

    package_metadata = get_package_metadata(atom)

    common = {
        'cpv': atom,
        'cp': package_metadata['cp'],
        'extra_env_files': ( " ".join(args.extra_env_file) if args.extra_env_file else [] )
    }

    if args.append_required_use:
        package_metadata['ruse'].append(args.append_required_use)

    if package_metadata['iuse']:
        use_combinations = get_use_combinations(package_metadata['iuse'], package_metadata['ruse'], args.max_use_combinations)
    else:
        use_combinations = None

    if use_combinations:
        if package_metadata['has_tests'] and args.test_feature_scope == 'always':
            test_feature_toggle = True
        else:
            test_feature_toggle = False

        for flags_set in use_combinations:
            job = {}
            job.update(common)
            job.update(
                {
                    'test_feature_toggle': test_feature_toggle,
                    'use_flags': flags_set,
                    'use_flags_scope': args.use_flags_scope
                }
            )
            jobs.append(job)

        if package_metadata['has_tests'] and args.test_feature_scope == 'once':
            job = {}
            job.update(common)
            job.update(
                {
                    'test_feature_toggle': True,
                    'use_flags': [],
                    'use_flags_scope': args.use_flags_scope
                }
            )
            jobs.append(job)
    else:
        if not package_metadata['has_tests'] or args.test_feature_scope == 'never':
            job = {}
            job.update(common)
            job.update(
                {
                    'test_feature_toggle': False,
                    'use_flags': [],
                    'use_flags_scope': args.use_flags_scope
                }
            )
            jobs.append(job)
        else:
            job = {}
            job.update(common)
            job.update(
                {
                    'test_feature_toggle': False,
                    'use_flags': []
                }
            )
            jobs.append(job)

            job = {}
            job.update(common)
            job.update(
                {
                    'test_feature_toggle': True,
                    'use_flags': []
                }
            )
            jobs.append(job)

    return jobs


def yes_no(question):
    reply = input(question).lower()

    if reply == 'y':
        return True

    return False


def pkg_testing_tool(args, extra_args):
    results = []

    # Unconditionally unmask and keyword packages selected by atom.
    # No much of a reason to check what arch we're running or if package is masked in first place.
    with ExitStack() as stack:
        tmp_files = {}

        for directory in ['package.accept_keywords', 'package.unmask']:
            tmp_files[directory] = stack.enter_context(get_etc_portage_tmp_file(directory))

        jobs = []

        for atom in args.package_atom:
            # Unmask and keyword all the packages prior to testing them.
            tmp_files['package.accept_keywords'].write("{atom} **\n".format(atom=atom))
            tmp_files['package.unmask'].write("{atom}\n".format(atom=atom))

            for new_job in define_jobs(atom, args):
                jobs.append(new_job)

        for handler in tmp_files:
            tmp_files[handler].flush()

        padding = max(len(i['cpv']) for i in jobs) + 3

        einfo("Following testing jobs will be executed:")
        for job in jobs:
            print(
                "{cpv:<{padding}} USE: {use_flags}{test_feature}".format(
                    cpv=job['cpv'],
                    use_flags=("<default flags>" if not job['use_flags'] else " ".join(job['use_flags'])),
                    test_feature=(", FEATURES: test" if job['test_feature_toggle'] else ""),
                    padding=padding,
                )
            )

        if args.ask:
            if not yes_no('>>> Do you want to continue? [y/N]: '):
                sys.exit(1)

        i = 0
        for job in jobs:
            i += 1
            einfo(
                "Running ({i} of {max_i}) {cpv} with USE: {use_flags}{test_feature}".format(
                    i=i,
                    max_i=len(jobs),
                    cpv=job['cpv'],
                    use_flags=("<default flags>" if not job['use_flags'] else " ".join(job['use_flags'])),
                    test_feature=(", FEATURES: test" if job['test_feature_toggle'] else ""),
                )
            )
            results.append(
                run_testing(job, args)
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
