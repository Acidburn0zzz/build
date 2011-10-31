# Copyright (c) 2011 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from master import master_config
from master.factory import chromium_factory

defaults = {}

helper = master_config.Helper(defaults)
B = helper.Builder
F = helper.Factory
S = helper.Scheduler
T = helper.Triggerable

def win(): return chromium_factory.ChromiumFactory('src/build', 'win32')
def linux(): return chromium_factory.ChromiumFactory('src/build', 'linux2')

defaults['category'] = '7win latest'

################################################################################
## Release
################################################################################

# Archive location
rel_archive = master_config.GetArchiveUrl('ChromiumWebkit',
                                          'Win Builder',
                                          'win-latest-rel', 'win32')

#
# Main release scheduler for webkit
#
S('s7_webkit_builder_rel', branch='trunk', treeStableTimer=60)
S('s7_webkit_rel', branch='trunk', treeStableTimer=60)

# Create the triggerable scheduler for the reliability tests.
T('reliability')

# Triggerable scheduler for testers
T('s7_webkit_builder_rel_trigger')


#
# Win Rel Builders
#
B('Win Builder', 'f_win_rel', scheduler='s7_webkit_builder_rel',
  builddir='win-latest-rel')
F('f_win_rel', win().ChromiumWebkitLatestFactory(
    slave_type='Builder',
    project='all.sln;chromium_builder',
    factory_properties={
        'trigger': 's7_webkit_builder_rel_trigger',
        'gclient_env': { 'GYP_DEFINES': 'fastbuild=1' },
    }))

B('Win Reliability Builder', 'f_win_reliability_rel', scheduler='s7_webkit_rel',
  builddir='Win_Webkit_Latest')
F('f_win_reliability_rel', win().ChromiumWebkitLatestFactory(
    clobber=True,
    tests=[],
    project='all.sln',
    factory_properties={'archive_build': True,
                        'trigger': 'reliability',
                        'use_build_number': True}))

#
# Win Rel testers+builders
#
# TODO: Switch back to trigger, http://crbug.com/102331
B('Vista Perf', 'f_win_rel_perf', scheduler='s7_webkit_builder_rel',
  auto_reboot=True)
F('f_win_rel_perf', win().ChromiumWebkitLatestFactory(
    # TODO: undo, http://crbug.com/102331
    #slave_type='Tester',
    #build_url=rel_archive,
    project='all.sln;chromium_builder_perf',
    tests=['dom_perf', 'page_cycler_moz', 'page_cycler_morejs',
           'page_cycler_intl1', 'page_cycler_intl2', 'page_cycler_dhtml',
           'page_cycler_database', 'page_cycler_indexeddb', 'sunspider'],
    factory_properties={'perf_id': 'chromium-rel-vista-webkit',
                        'show_perf_results': True,
                        'start_crash_handler': True,
                        # TODO: Remove, http://crbug.com/102331
                        'gclient_env': {'GYP_DEFINES': 'fastbuild=1'},
                        }))

B('Vista Tests', 'f_win_rel_tests', scheduler='s7_webkit_builder_rel_trigger',
  auto_reboot=True)
F('f_win_rel_tests', win().ChromiumWebkitLatestFactory(
    slave_type='Tester',
    build_url=rel_archive,
    tests=['installer', 'unit', 'ui'],
    factory_properties={'perf_id': 'chromium-rel-vista-webkit',
                        'show_perf_results': True,
                        'start_crash_handler': True,
                        'test_results_server': 'test-results.appspot.com',
                        }))

B('Win Reliability', 'win_reliability', scheduler='reliability')
# The Windows reliability bot runs on Linux because it only needs to transfer
# the build from one part of the network to another, and it is easier on Linux.
F('win_reliability', linux().ReliabilityTestsFactory('win_webkit_canary'))

################################################################################
## Debug
################################################################################

#
# Main debug scheduler for webkit
#
S('s7_webkit_builder_dbg', branch='trunk', treeStableTimer=60)
S('s7_webkit_dbg', branch='trunk', treeStableTimer=60)

#
# Win Dbg Builder
#
B('Win (dbg)', 'f_win_dbg', scheduler='s7_webkit_builder_dbg',
  builddir='win-latest-dbg')
F('f_win_dbg', win().ChromiumWebkitLatestFactory(
    target='Debug',
    project='all.sln;chromium_builder',
    tests=['browser_tests', 'interactive_ui', 'unit', 'ui'],
    factory_properties={
        'start_crash_handler': True,
        'generate_gtest_json': True,
        'gclient_env': {'GYP_DEFINES': 'fastbuild=1'}}))


B('Win Shared Builder (dbg)', 'f_win_shared_dbg', scheduler='s7_webkit_dbg')
F('f_win_shared_dbg', win().ChromiumWebkitLatestFactory(
    project='all.sln',
    compile_timeout=2400,
    factory_properties={
        'gclient_env': {'GYP_DEFINES':
                            'component=shared_library fastbuild=1'}}))


def Update(config, active_master, c):
  return helper.Update(c)
