import os
from buildbot.plugins import util, steps, schedulers

from . import helpers
from buildbot.changes.gitpoller import GitPoller

config = helpers.load_yaml('vitasa/config.yaml')

def _is_ssh_branch(step):
    return config['branch_deployment_configs'][step.getProperty('branch')]['host'] is not ''

def _is_k8s_branch(step):
    return config['branch_deployment_configs'][step.getProperty('branch')]['kubeconfig'] is not None

def _make_factory(branch_cfg):
    f = util.BuildFactory()

    # Sync git
    f.addStep(steps.Git(
        repourl="https://github.com/klaital/vitasa-web",
        method='clobber',
        mode='full',
        shallow=True,
        haltOnFailure=True,
        name='git sync'
    ))

    branch_specifier = util.Interpolate('%(prop:branch)s')
    version_specifier = util.Interpolate('VERSION=%(prop:branch)s-%(prop:buildnumber)s')

    # Update bundler
    f.addStep(steps.ShellCommand(
        name='update bundle',
        command=['bundle', 'install', '--path', 'vendor/bundle'],
        env={'RAILS_ENV': 'test'},
        haltOnFailure=True,
    ))
    # Migrate test db
    f.addStep(steps.ShellCommand(
        name='migrate test db',
        command=['bundle', 'exec', 'rails', 'db:migrate'],
        env={'RAILS_ENV': 'test'},
        haltOnFailure=True,
    ))

    # Run tests
    f.addStep(steps.ShellCommand(
        name='run tests',
        command=['bundle', 'exec', 'rails', 'test'],
        env={'RAILS_ENV': 'test'},
        haltOnFailure=True,
        usePTY=True,
    ))

    # TODO: Run linters

    #
    # Docker/Kubernetes deployment
    # 

    # Build Docker image
    f.addStep(steps.ShellCommand(
        name='build docker image',
        command=['bundle', 'exec', 'rails', 'docker:build', util.Property('branch')],
        doStepIf=_is_k8s_branch,
        haltOnFailure=True,
    ))
    # Push Docker image
    f.addStep(steps.ShellCommand(
        name='push docker image to Docker Hub',
        command=['bundle', 'exec', 'rails', 'docker:push', util.Property('branch')],
        doStepIf=_is_k8s_branch,
        haltOnFailure=True,
    ))

    # Update k8s deployment
    f.addStep(steps.ShellCommand(
        name='push to k8s cluster',
        command=['kubectl', '--kubeconfig', branch_cfg['kubeconfig'], 'apply', '-f', branch_cfg['k8s_deployment']],
        haltOnFailure=True,
        doStepIf=_is_k8s_branch,
    ))

    # 
    # Alternate deployment via direct SSH commands
    #
    f.addStep(steps.ShellCommand(
        name='update code on remote host',
        command=['ssh', '-i', branch_cfg['sshkey'], branch_cfg['username'] + '@' + branch_cfg['host'], '-c', 'cd /var/www/vitasa-web/code && git pull'],
        haltOnFailure=True,
        doStepIf=_is_ssh_branch,
    ))
    f.addStep(steps.ShellCommand(
        name='restart service on remote host',
        command=['ssh', '-i', branch_cfg['sshkey'], branch_cfg['username'] + '@' + branch_cfg['host'], '-c', 'passenger-config restart-app /var/www/vitasa-web/code' ],
        haltOnFailure=True,
        doStepIf=_is_ssh_branch,
    ))
    # TODO: add liveness check to see if the new version is actually deployed and reachable

    return f

def add_changesources(cfg):
    cfg['change_source'].append(GitPoller(
        repourl="https://github.com/klaital/vitasa-web",
        branches=True,
        buildPushesWithNoCommits=True,
        pollInterval=3600,
        pollAtLaunch=True,
        workdir='/tmp/gitpoller-workdir-vitasa-web',
        project='vitasa-web'
    ))

def add_builders(b):
    for branch in config['branch_deployment_configs']:
        realm = config['branch_deployment_configs'][branch]['namespace']
        buildername = "vitasa-" + realm
        tags = ['vita', config['branch_deployment_configs'][branch]['namespace']]
        if config['branch_deployment_configs'][branch]['kubeconfig'] == config['home_kubeconfig']:
            tags.append('home')

        b['builders'].append(util.BuilderConfig(name=buildername,
            workernames=["vitasa-worker"],
            factory=_make_factory(config['branch_deployment_configs'][branch]),
            tags=tags
        ))

def add_schedulers(cfg):
    for branch in config['branch_deployment_configs']:
        realm = config['branch_deployment_configs'][branch]['namespace']
        buildername = 'vitasa-' + realm
        cfg['schedulers'].append(
            schedulers.ForceScheduler(
                name="force-vita" + realm,
                codebases=[
                    util.CodebaseParameter(
                        "",
                        label="Repository",
                        branch=util.FixedParameter(name="branch", default=branch),
                        revision=util.StringParameter(name="revision", default=""),
                        repository=util.FixedParameter(name="repository", default="https://github.com/klaital/vitasa-web"),
                        project=util.FixedParameter(name="project", default='vitasa-web'),
                    )
                ],
                builderNames=[buildername]
            )
        )

        # TODO: add automatic scheduler
