#! /usr/bin/env python
# Copyright (c) 2012 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Set up and invoke telemetry tests."""

import json
import optparse
import os
import sys

from common import chromium_utils


SCRIPT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def _GetPythonTestCommand(py_script, target, build_dir, arg_list=None,
                         wrapper_args=None, fp=None):
  """Synthesizes a command line to run runtest.py."""
  cmd = [sys.executable,
         os.path.join(SCRIPT_DIR, 'slave', 'runtest.py'),
         '--run-python-script',
         '--target', target,
         '--build-dir', build_dir,
         '--no-xvfb'] #  telemetry.py should be run by a 'master' runtest.py
                      #  which starts xvfb on linux.
  if fp:
    cmd.extend(["--factory-properties=%s" % json.dumps(fp)])
  if wrapper_args is not None:
    cmd.extend(wrapper_args)
  cmd.append(py_script)

  if arg_list is not None:
    cmd.extend(arg_list)
  return cmd


def _GetReferenceBuildPath(target_os, target_platform):
  ref_dir = os.path.join('src', 'chrome', 'tools', 'test', 'reference_build')
  if target_os == 'android':
    # TODO(tonyg): Check in a reference android content shell.
    return None
  elif target_platform == 'win32':
    return os.path.join(ref_dir, 'chrome_win', 'chrome.exe')
  elif target_platform == 'darwin':
    return os.path.join(ref_dir, 'chrome_mac', 'Chromium.app', 'Contents',
        'MacOS', 'Chromium')
  elif target_platform.startswith('linux'):
    return os.path.join(ref_dir, 'chrome_linux', 'chrome')
  return None


def _GenerateTelemetryCommandSequence(fp):
  """Given a test name, page set, and target, generate a telemetry test seq."""

  test_name = fp.get('test_name')
  page_set = fp.get('page_set')
  target = fp.get('target')
  target_os = fp.get('target_os')
  target_platform = fp.get('target_platform')
  build_dir = fp.get('build_dir')

  script = os.path.join('src', 'tools', 'perf', 'run_multipage_benchmarks')
  page_set = os.path.join('src', 'tools', 'perf', 'page_sets', page_set)

  env = os.environ

  # On android, telemetry needs to use the adb command and needs to be in
  # root mode. Run it in bash since envsetup.sh doesn't work in sh.
  if target_os == 'android':
    env['PATH'] = os.pathsep.join(['/b/build_internal/scripts/slave/android',
                                   env['PATH']])
    commands = [['adb', 'root'], ['adb', 'wait-for-device']]
  else:
    commands = []

  # Run the test against the target chrome build.
  browser = 'release'
  if target_os == 'android':
    browser = 'android-content-shell'
  test_args = ['-v', '--browser=%s' % browser, test_name, page_set]
  test_cmd = _GetPythonTestCommand(script, target, build_dir, test_args, fp=fp)
  commands.append(test_cmd)

  # Run the test against the reference build on platforms where it exists.
  ref_build = _GetReferenceBuildPath(target_os, target_platform)
  if ref_build:
    ref_args = ['-v', '--browser=exact',
                '--browser-executable=%s' % ref_build,
                test_name, page_set]
    ref_cmd = _GetPythonTestCommand(script, target, build_dir, ref_args, fp=fp)
    commands.append(ref_cmd)

  return commands, env


def main(argv):
  prog_desc = 'Invoke telemetry performance tests.'
  parser = optparse.OptionParser(usage=('%prog [options]' + '\n\n' + prog_desc))
  parser.add_option('--print-cmd', action='store_true',
                    help='only print command instead of running it')
  parser.add_option('--factory-properties', action='callback',
                    callback=chromium_utils.convert_json, type='string',
                    nargs=1, default={},
                    help='factory properties in JSON format')

  options, _ = parser.parse_args(argv[1:])
  fp = options.factory_properties
  if not fp:
    print 'This program requires a factory properties to run.'
    return 1

  commands, env = _GenerateTelemetryCommandSequence(fp)

  retval = 0
  for command in commands:
    if options.print_cmd:
      print ' '.join("'%s'" % c for c in command)
      continue

    retval = chromium_utils.RunCommand(command, env=env)
    if retval != 0:
      break
  return retval


if '__main__' == __name__:
  sys.exit(main(sys.argv))
