#!/usr/bin/env python
# Copyright 2012 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests all master.cfgs to make sure they load properly."""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'scripts'))

import masters_util

from common import chromium_utils
from common import master_cfg_utils


# Masters which do not currently load from the default configuration. These need
# to be fixed and removed from the list!
BLACKLIST = ['chromium.swarm',
             'chromium.chromebot',
             'chromiumos.tryserver',
             'client.nacl.chrome']


def TestMaster(mastername):

  cmd = [sys.executable,
         os.path.join(BASE_DIR, 'scripts', 'slave', 'runbuild.py'),
         mastername,
         '--test-config']
  env = os.environ.copy()
  buildpaths = ['scripts', 'third_party', 'site_config']
  thirdpartypaths = ['buildbot_8_4p1', 'buildbot_slave_8_4', 'jinja2',
                     'mock-1.0.1', 'twisted_10_2']

  pythonpaths = [os.path.join(BASE_DIR, p) for p in buildpaths]
  pythonpaths.extend(os.path.join(BASE_DIR, 'third_party', p)
                     for p in thirdpartypaths)
  if env.get('PYTHONPATH'):
    pythonpaths.append(env.get('PYTHONPATH'))

  env['PYTHONPATH'] = os.pathsep.join(pythonpaths)
  return chromium_utils.RunCommand(cmd, print_cmd=False, env=env)


def main():
  masters = master_cfg_utils.GetMasters(include_internal=False)
  failures = []
  bot_pwd_path = os.path.join(BASE_DIR, 'site_config', '.bot_password')
  with masters_util.temporary_password(bot_pwd_path):
    for mastername, path in masters:
      if mastername in BLACKLIST:
        print 'Skipping %s, fix and enable in masters_cfg_test.py!' % mastername
        continue

      print 'Parsing', mastername

      apply_issue_pwd_path = os.path.join(path, '.apply_issue_password')
      with masters_util.temporary_password(apply_issue_pwd_path):
        if TestMaster(mastername):
          failures.append((mastername, path))

  if failures:
    print 'The following master.cfgs did not load:'
    for mastername, path in failures:
      print '  %s: %s' % (mastername, path)
    return 1

  print 'All master.cfg files parsed successfully!'
  return 0


if __name__ == '__main__':
  sys.exit(main())
