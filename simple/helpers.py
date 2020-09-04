import yaml

WORKER_LOCK = util.WorkerLock('wannet_worker_lock',
                              maxCount=2)

def load_yaml(file):
    with open(file, 'r') as f:
        try:
            data = yaml.safe_load(f)
            return data

        except yaml.YAMLError as e:
            print(e)