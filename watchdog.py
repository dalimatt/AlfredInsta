import time
import sys
from os import kill
from signal import SIGINT
from dependencies.workflow import Workflow

pid_str = sys.argv[1]
timeout_str = sys.argv[2]


def main(wf):
    
    # Parse arguments into integers
    try:
        timeout = int(timeout_str)
    except ValueError as err:
        wf.logger.critical('timeout not string: ' + err.message)
        sys.exit(1)
    try:
        pid = int(pid_str)
    except ValueError as err:
        wf.logger.critical('pid not string: ' + err.message)
        sys.exit(1)
    
    """Wait for a process to finish, or raise exception after timeout"""
    start = time.time()
    end = start + timeout
    interval = min(timeout / 1000.0, .25)

    try: 
        while True:
            exists = poll(pid)
            if not exists:
                wf.logger.debug('Process:{0} does not exist'.format(pid))
                return
            else:
                if time.time() >= end:
                    raise RuntimeError("Process timed out")
                time.sleep(interval)
    except RuntimeError as err:
        kill(pid, SIGINT)

def poll(pid):
    """ Check For the existence of a unix pid. """
    try:
        kill(pid, 0)
    except OSError:
        return False
    else:
        return True
            
if __name__ == '__main__':
    wf = Workflow()
    wf.run(main)
    sys.exit(0)
    
