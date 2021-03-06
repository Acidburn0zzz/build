#!/usr/bin/env python
# Copyright (c) 2012 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
# get_swarm_results.py: Retrieves and output swarm test results for a given
# test request name.

"""Takes in a test name and retrives all the output that the swarm server
has produced for tests with that name. This is expected to be called as a
build step."""

import json
import math
import optparse
import random
import re
import socket
import sys
import time
import urllib
import urllib2

from common import find_depot_tools  # pylint: disable=W0611
from common import gtest_utils

# From the depot tools
import fix_encoding


MAX_RETRY_ATTEMPTS = 20


def TestRunOutput(output):
  """Go through the given output and only return the output from the Test Run
     Step. This removes all the swarm specific output.
  """
  test_run_output = []

  in_step = False
  step_name = ''
  for line in output.splitlines(True):
    if in_step:
      if ('[       OK ] ' + step_name in line or
          '[  FAILED  ] ' + step_name in line):
        break
      else:
        test_run_output.append(line)
    elif '[ RUN      ] ' in line and 'Run Test' in line:
      in_step = True
      i = len('[ RUN      ] ')
      step_name = line[i:].strip()

  return ''.join(test_run_output)


def ConnectToSwarmServer(url, data=None, max_retries=MAX_RETRY_ATTEMPTS):
  """Try multiple times to connect to the swarm server and return the response,
     or None if unable to connect.
  """
  for attempt in range(MAX_RETRY_ATTEMPTS):
    try:
      if data:
        return urllib2.urlopen(url, data=data).read()
      else:
        return urllib2.urlopen(url).read()
    except (socket.error, urllib2.URLError) as e:
      print 'Error: Calling %s threw %s' % (url, e)

      if attempt != MAX_RETRY_ATTEMPTS - 1:
        wait_duration = random.random() * 3 + math.pow(1.3, (attempt + 1))
        wait_duration = min(5, max(0.1, wait_duration))
        time.sleep(wait_duration)

  # We were unable to connect to the url.
  print ('Unable to connect to the given url, %s, after %d attempts. Aborting.'
         % (url, MAX_RETRY_ATTEMPTS))
  return None


def GetTestKeys(swarm_base_url, test_name):
  key_data = urllib.urlencode([('name', test_name)])
  test_keys_url = '%s/get_matching_test_cases?%s' % (swarm_base_url.rstrip('/'),
                                                     key_data)

  result = ConnectToSwarmServer(test_keys_url)
  if result is None:
    return []

  if 'No matching' in result:
    print ('Error: Unable to find any tests with the name, %s, on swarm server'
           % test_name)
    return []

  return json.loads(result)


class ShardWatcher(object):
  """A simple class that monitors the gtest output from all the shards and
     ensure all the required shards run and that there are no duplicates.
  """

  def __init__(self, shard_count):
    # We add 1 to the shard indices because they will start at 1, not 0.
    self.remaining_shards = map(str, range(1, shard_count + 1))
    self.shard_line = re.compile(
        r'Note: This is test shard ([0-9]+) of ([0-9]+)')
    self.errors = False

  def ProcessLine(self, line):
    """Examine the line to see if it tells us which shard we are."""
    match = self.shard_line.match(line)
    if match:
      shard_num = match.group(1)
      if shard_num in self.remaining_shards:
        self.remaining_shards.remove(shard_num)
      else:
        self.errors = True

  def MissingShards(self):
    return self.remaining_shards

  def ShardsCompleted(self):
    return not self.errors and not self.remaining_shards


def GetSwarmResults(swarm_base_url, test_keys):
  if not test_keys:
    print 'Error: No test keys to get results with'
    return 1

  gtest_parser = gtest_utils.GTestLogParser()
  machine_ids = ['unknown'] * len(test_keys)
  machine_tags = ['unknown'] * len(test_keys)
  exit_codes = [1] * len(test_keys)
  shard_watcher = ShardWatcher(len(test_keys))
  for index in range(len(test_keys)):
    test_key_encoded = urllib.urlencode([('r', test_keys[index])])
    result_url = '%s/get_result?%s' % (swarm_base_url.rstrip('/'),
                                       test_key_encoded)
    while True:
      output = ConnectToSwarmServer(result_url)
      if output is None:
        break

      try:
        test_outputs = json.loads(output)
      except (ValueError, TypeError), e:
        print 'Unable to get results for shard  %d' % index
        print e
        break

      if test_outputs['output']:
        if test_outputs['exit_codes']:
          test_exit_codes = test_outputs['exit_codes'].split(',')
          exit_codes[index] = max(map(int, test_exit_codes))
        machine_ids[index] = test_outputs['machine_id']
        machine_tags[index] = test_outputs.get('machine_tag', 'unknown')

        print
        print '================================================================'
        print 'Begin output from shard index %s (machine tag: %s, id: %s)' % (
            index, machine_tags[index], machine_ids[index])
        print '================================================================'
        print

        cleaned_output = TestRunOutput(test_outputs['output'])
        if cleaned_output:
          for line in cleaned_output.splitlines():
            gtest_parser.ProcessLine(line)
            shard_watcher.ProcessLine(line)
          print cleaned_output
        else:
          # We failed to get any test output which is an error, so we should
          # show the swarm output since that is probably where the error is.
          print 'No output produced by the test, it may have failed to run.'
          print 'Showing all the output, including swarm specific output.'
          print
          print test_outputs['output']

          # Ensure that we mark this as a failure, since we should always have
          # output from the tests.
          if not exit_codes[index]:
            exit_codes[index] = 1

        print '================================================================'
        print ('End output from shard index %s (machine tag: %s, id: %s). '
               'Return %d' % (index, machine_tags[index], machine_ids[index],
                              exit_codes[index]))
        print '================================================================'
        print

        if exit_codes[index] == 0:
          # If the test passed, delete the key since it is no longer needed.
          remove_key_url = '%s/cleanup_results' % swarm_base_url.rstrip('/')
          # The data parameter must be used so that the the request will be a
          # POST and not a GET.
          ConnectToSwarmServer(remove_key_url, data=test_key_encoded,
                               max_retries=1)
        break
      else:
        # Test is not yet done, wait a bit before checking again.
        time.sleep(0.5)

  print 'Summary for all the shards:'

  failed_tests = gtest_parser.FailedTests()
  if len(failed_tests) > 0:
    plural = 's' if len(failed_tests) > 1 else ''
    print '%d test%s failed, listed below:' % (len(failed_tests), plural)
    print '\n'.join('  ' + test for test in failed_tests)
  else:
    print 'All tests passed.'

  if len(test_keys) > 1 and shard_watcher.MissingShards():
    print 'Not all shards were executed.'
    print 'The following gtest shards weren\'t run:'
    print '\n'.join('  ' + shard_id for shard_id in
                    shard_watcher.MissingShards())
    return 1


  return max(exit_codes)


def main():
  """Retrieve the given swarm test results from the swarm server and print it
  to stdout.

  Args:
    test_name: The name of the test to retrieve output for.
  """
  # Parses arguments
  parser = optparse.OptionParser(usage='%prog [options] test_name',
                                 description=sys.modules[__name__].__doc__)
  parser.add_option('-u', '--url', default='http://localhost:8080',
                    help='Specify the url of the Swarm server. '
                    'Defaults to %default')
  parser.add_option('-v', '--verbose', action='store_true',
                    help='Print verbose logging')
  (options, args) = parser.parse_args()
  if not args:
    parser.error('Must specify one test name.')
  elif len(args) > 1:
    parser.error('Must specify only one test name.')
  test_name = args[0]

  test_keys = GetTestKeys(options.url, test_name)

  return GetSwarmResults(options.url, test_keys)


if __name__ == '__main__':
  fix_encoding.fix_encoding()
  sys.exit(main())
