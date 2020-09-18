import os
from buildbot.plugins import util, steps, schedulers

from . import helpers
from buildbot.changes.gitpoller import GitPoller

config = helpers.load_yaml('volunteersavvybackend/config.yaml')

def _is_k8s_branch(step):
    return config['branch_deployment_configs'][step.getProperty('branch')]['kubeconfig'] is not None

def _make_factory(branch_cfg):
    f = util.BuildFactory()
    branch_specifier = util.Interpolate('%(prop:branch)s')
    
    # Sync git
    f.addStep(steps.Git(
        repourl="https://github.com/klaital/volunteer-savvy-backend",
        method='clobber',
        mode='full',
        shallow=True,
        haltOnFailure=True,
        branch=branch_specifier,
        name='git sync',
    ))

    version_specifier = util.Interpolate('VERSION=%(prop:branch)s-%(prop:buildnumber)s')

    # Build
    f.addStep(steps.ShellCommand(
        name='compile',
        command=['make', 'build'],
        haltOnFailure=True,
    ))
    # Run tests
    f.addStep(steps.ShellCommand(
        name='run tests',
        command=['make', 'test'],
        haltOnFailure=True,
    ))

    # TODO: Run linters

    #
    # Docker/Kubernetes deployment
    # 

    # Build Docker image
    f.addStep(steps.ShellCommand(
        name='build docker image',
        command=['make', 'image'],
        doStepIf=_is_k8s_branch,
        haltOnFailure=True,
    ))
    # Push Docker image
    f.addStep(steps.ShellCommand(
        name='push docker image to Docker Hub',
        command=['make', 'push'],
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

    # TODO: add liveness check to see if the new version is actually deployed and reachable

    return f

def add_changesources(cfg):
    cfg['change_source'].append(GitPoller(
        repourl="https://github.com/klaital/volunteer-savvy-backend",
        branches=True,
        buildPushesWithNoCommits=True,
        pollInterval=3600,
        pollAtLaunch=True,
        workdir='/tmp/gitpoller-workdir-vs-backend',
        project='volunteer-savvy-backend'
    ))

def add_builders(b):
    for branch in config['branch_deployment_configs']:
        realm = config['branch_deployment_configs'][branch]['namespace']
        buildername = "vs-" + realm
        tags = ['vs', config['branch_deployment_configs'][branch]['namespace']]
        if config['branch_deployment_configs'][branch]['kubeconfig'] == config['home_kubeconfig']:
            tags.append('home')

        b['builders'].append(util.BuilderConfig(name=buildername,
            workernames=["klaital-worker"],
            factory=_make_factory(config['branch_deployment_configs'][branch]),
            tags=tags
        ))

def add_schedulers(cfg):
    for branch in config['branch_deployment_configs']:
        realm = config['branch_deployment_configs'][branch]['namespace']
        buildername = 'vs-' + realm
        cfg['schedulers'].append(
            schedulers.ForceScheduler(
                name="force-vs" + realm,
                codebases=[
                    util.CodebaseParameter(
                        "",
                        label="Repository",
                        branch=util.FixedParameter(name="branch", default=branch),
                        revision=util.StringParameter(name="revision", default=""),
                        repository=util.FixedParameter(name="repository", default="https://github.com/klaital/volunteer-savvy-backend"),
                        project=util.FixedParameter(name="project", default='volunteer-savvy-backend'),
                    )
                ],
                builderNames=[buildername]
            )
        )

        # TODO: add automatic scheduler
