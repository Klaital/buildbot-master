import os
from buildbot.plugins import util, steps, schedulers

import helpers
from buildbot.changes.gitpoller import GitPoller

config = helpers.load_yaml('config.yaml')

def _is_deploy_branch(step):
    return step.getProperty('branch') in list(config['branch_to_namespace_mapping'])

def 

def _make_factory():
    f = util.BuildFactory()

    # Sync git
    f.addStep(steps.Git(
        repourl="https://github.com/klaital/wwdice",
        method='clobber',
        mode='full',
        shallow=True,
        haltOnFailure=True,
        name='git sync'
    ))

    version_specifier = util.Interpolate('VERSION=%(prop:branch)s-%(prop:buildnumber)s')

    # Build binary
    f.addStep(steps.ShellCommand(
        command=['make', 'wwdicebot', version_specifier],
        env={'GOOS': 'linux'},
        haltOnFailure=true,
    ))

    # Run tests
    f.addStep(steps.ShellCommand(
        name='run tests'
        command=['make', 'test'],
        haltOnFailure=true,
    ))

    # TODO: Run linters

    # Build Docker image
    f.addStep(steps.ShellCommand(
        name='build and push docker image'
        command=['make', 'wwdicebot-push'],
        haltOnFailure=true,
    ))

    # Update k8s deployment
    f.addStep(steps.ShellCommand(
        name='push to home cluster'
        command=['kubectl', '--kubeconfig', 'wwdicebot_kubeconfig', 'apply', '-f', 'cmd/wwdicebot/k8s.yaml'],
        haltOnFailure=true,
        doStepIf=_is_deploy_branch
    ))

    # TODO: add liveness check to see if the new version is actually deployed and reachable

    return f

def add_changesources(cfg):
    cfg['change_source'].append(gitpoller.GitPoller(
        repourl="https://github.com/klaital/wwdice",
        branches=True,
        buildPushesWithNoCommits=True,
        pollInterval=3600,
        pollAtLaunch=True,
        workdir='/tmp/gitpoller-workdir-wwdice',
        project='wwdice'
    ))

def add_builders(b):
    for branch in config['branch_to_namespace_mapping']:
        realm = config['branch_to_namespace_mapping'][branch]
        buildername = f"wwdicebot-{realm}"
        b['builders'].append(util.BuilderConfig(name=buildername,
            workernames=["wwdicebot-worker"],
            factory=_make_factory(),
            tags=['wwdicebot', 'home', 'discord', 'bots']
        ))

def add_schedulers(cfg):
    for branch in config['branch_to_namespace_mapping']:
        realm = config['branch_to_namespace_mapping'][branch]
        buildername = 'wwdicebot-' + realm
        cfg['schedulers'].append(
            schedulers.ForceScheduler(
                name=f"force-wwdicebot-{realm}",
                codebases=[
                    util.CodebaseParameter(
                        "",
                        label="Repository",
                        branch=util.FixedParameter(name="branch", default=branch),
                        revision=util.StringParameter(name="revision", default=""),
                        repository=util.FixedParameter(name="repository", default="https://github.com/klaital/wwdice"),
                        project=util.FixedParameter(name="project", default='wwdicebot'),
                    )
                ]
            )
        )

        # TODO: add automatic scheduler