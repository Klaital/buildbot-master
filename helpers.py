from buildbot.plugins import *
import yaml
import standardservices
from buildbot.process.results import SKIPPED

WORKER_LOCK = util.WorkerLock('klaital_worker_lock', maxCount=1)

def load_yaml(file):
    with open(file, 'r') as f:
        try:
            data = yaml.safe_load(f)
            return data

        except yaml.YAMLError as e:
            print(e)

@util.renderer
def _get_helm_command(props):
    branch = props.getProperty('branch')
    container_tag = props.getProperty('container_tag')
    script = '/home/chris/devel/buildbot-master/build_branch.sh'
    setopts = "-s containerTag={}".format(container_tag)
    cluster = "klaital.com"
    namespace = standardservices.BRANCH_TO_REALM_MAPPING[branch]
    chart_name = props.getProperty('project_name')
    values_file = branch[len('deploy-'):]
    return ['bash', script, setopts, cluster, namespace, chart_name, values_file]

