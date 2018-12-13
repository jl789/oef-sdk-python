# -*- coding: utf-8 -*-

# ------------------------------------------------------------------------------
#
#   Copyright 2018 Fetch.AI Limited
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ------------------------------------------------------------------------------


import inspect
import os
import subprocess
import time

import pytest

ROOT_DIR = ".."
OUR_DIRECTORY = os.path.dirname(inspect.getfile(inspect.currentframe()))
FULL_PATH = [OUR_DIRECTORY, ROOT_DIR, "oef-core", "build", "apps", "node", "Node"]
PATH_TO_NODE_EXEC = os.path.join(*FULL_PATH)


@pytest.fixture(scope="session")
def oef_network_node():
    """Set up an instance of the OEF Node.
    It assumes that the OEFCore repository has been cloned in the root folder of the project."""
    FNULL = open(os.devnull, 'w')
    p = subprocess.Popen(PATH_TO_NODE_EXEC, stdout=FNULL, stderr=subprocess.STDOUT)
    time.sleep(0.01)
    yield
    p.kill()
