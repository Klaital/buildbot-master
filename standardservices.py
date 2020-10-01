import os
from buildbot.plugins import util, steps, schedulers

import helpers
import gitpoller

config = helpers.load_yaml('services_config.yaml')

# Increment this if you wipe the DB to prevent reusing build version numbers.
DATABASE_VERSION = 1

SOURCE_GIT_URL = 'https://github.com'
POLL_INTERVAL_SECONDS = 600

# Deploy any branches that have any associated realm
BRANCH_TO_REALM_MAPPING = config['branch_to_realm_mapping']
DEPLOY_BRANCHES = list(BRANCH_TO_REALM_MAPPING)

# The Docker Hub registry doesn't need a hostname
REGISTRY = 'klaital'

# List of workers that can concurrently build
WORKERNAMES = [
        "klaital-standardservice-worker",
]

SERVICES = config['services']

for ms in SERVICES:
    SERVICES[ms]['poll_branches'] = DEPLOY_BRANCHES


def _is_deploy_branch(step):
    return step.getProperty('branch') in DEPLOY_BRANCHES or step.getProperty('branch') == ""

def _make_factory(name, ms):
    f = util.BuildFactory()

    # Sync Git
    f.addStep(steps.Git(
        repourl=ms['giturl'],
        method='clobber',
        mode='full',
        shallow=False,
        haltOnFailure=True,
        name='git sync'))

    # TODO: login to dockerhub

    f.addStep(steps.SetPropertyFromCommand(
        name="set property from make version",
        command=["make", "version", "--always-make"],
        property="project_version",
        haltOnFailure=True))


    version_specific_str = '%(prop:project_version)s-$(prop:branch)s-%(prop:buildnumber)s-' + str(DATABASE_VERSION)
    version_specifier = util.Interpolate('VERSION=' + version_specific_str)
    commit_hash_specifier = util.Interpolate('COMMIT_HASH=' + '%(prop:got_revision)s')

    # Compile
    f.addStep(steps.ShellCommand(
        name="compile",
        command=["make", "build", version_specifier, commit_hash_specifier],
        haltOnFailure=True,
    ))

    # Run tests
    f.addStep(steps.ShellCommand(
        name="run tests",
        command=["make", "test", version_specifier, commit_hash_specifier],
        warnOnFailure=not ms['fail_on_tests'],
        haltOnFailure=ms['fail_on_tests'],
        doStepIf=ms['run_tests'],
    ))

    # Build image and push to Docker registry
    f.addStep(steps.ShellCommand(
        name="push docker image to registry",
        haltOnFailure=True,
        command=["make", "push", version_specifier, commit_hash_specifier],
        doStepIf=_is_deploy_branch,
        ))

    f.addStep(steps.SetProperties(
        name="set container properties",
        properties={
            'container_name': REGISTRY + r'\/' + name,
            'container_tag': util.Interpolate(version_specific_str),
            'project_name': name,
        }
    ))

    # TODO: add actual k8s deployment step

    # TODO: add liveness check step

    return f

def add_all_changesources(cfg):
    for s_name in SERVICES:
        s = SERVICES[s_name]
        gp = gitpoller.KGitPoller(
                repourl=s['giturl'],
                branches=True,
                buildPushesWithNoCommits=True,
                pollInterval=POLL_INTERVAL_SECONDS,
                pollAtLaunch=True,
                workdir="/tmp/gitpoller-workdir-"+s_name,
                project=s_name)
        cfg['change_source'].append(gp)


def add_all_builders(b):
    for s_name in SERVICES:
        factory = _make_factory(s_name, SERVICES[s_name])
        for branch in get_all_possible_branch_names():
            realm = branch[len('deploy-'):]
            b.append(util.BuilderConfig(name=f"{s_name}_{realm}",
                workernames=WORKERNAMES,
                factory=factory,
                locks=[helpers.WORKER_LOCK.access('exclusive')],
                tags=[s_name, realm]))

def add_all_schedulers(cfg):
    for s_name in SERVICES:
        for branch in get_all_possible_branch_names():
            realm = BRANCH_TO_REALM_MAPPING[branch]
            buildername = f"{s_name}_{realm}"
            cfg['schedulers'].append(
                schedulers.ForceScheduler(
                    name=f"force-{s_name}-{realm}",
                    codebases=[
                        util.CodebaseParameter(
                            "",
                            label="Repository",
                            branch=util.FixedParameter(name="branch", default=branch),
                            revision=util.StringParameter(name="revision", default=""),
                            repository=util.FixedParameter(name="repository", default=SERVICES[s_name]['giturl']),
                            project=util.FixedParameter(name="project", default=s_name),
                        )
                    ],
                    builderNames=[buildername],
                )
            )
            
            cfg['schedulers'].append(
                schedulers.SingleBranchScheduler(
                    name=f"commit-{s_name}-{realm}",
                    builderNames=[buildername],
                    treeStableTimer=0,
                    change_filter=util.ChangeFilter(branch=branch, project=s_name),
                )
            )


def get_all_possible_branch_names():
    branch_hash = {}
    for s_name in SERVICES:
        for branch_name in SERVICES[s_name]['poll_branches']:
            branch_hash[branch_name] = 1

    return sorted(list(branch_hash.keys()))


