# Copyright (c) 2012 The Chromium Authors. All rights reserved.
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

def win():
  return chromium_factory.ChromiumFactory('src/build', 'win32')
def win_out():
  return chromium_factory.ChromiumFactory('src/out', 'win32')
def win_tester():
  return chromium_factory.ChromiumFactory(
      'src/build', 'win32', nohooks_on_update=True)

# Tests that are single-machine shard-safe. For now we only use the sharding
# supervisor for long tests (more than 30 seconds) that are known to be stable.
sharded_tests = [
  'base_unittests',
  'browser_tests',
  'content_browsertests',
  'cc_unittests',
  'media_unittests',
  'webkit_compositor_bindings_unittests',
]

################################################################################
## Release
################################################################################

defaults['category'] = '2windows'

# Archive location
rel_archive = master_config.GetArchiveUrl('ChromiumWin', 'Win Builder',
                                          'cr-win-rel', 'win32')

#
# Main debug scheduler for src/
#
S('win_rel', branch='src', treeStableTimer=60)

#
# Triggerable scheduler for the rel builder
#
T('win_rel_trigger')

#
# Win Rel Builder
#
B('Win Builder', 'rel', 'compile|windows', 'win_rel', builddir='cr-win-rel',
  auto_reboot=False, notify_on_missing=True)
F('rel', win().ChromiumFactory(
    slave_type='Builder',
    project='all.sln;chromium_builder_tests',
    factory_properties={'trigger': 'win_rel_trigger',
                        'gclient_env': {'GYP_DEFINES': 'fastbuild=1'}}))

#
# Win Rel testers
#
B('XP Tests (1)', 'rel_unit_1', 'testers|windows', 'win_rel_trigger',
  notify_on_missing=True)
F('rel_unit_1', win_tester().ChromiumFactory(
    slave_type='Tester',
    build_url=rel_archive,
    tests=[
      'browser_tests',
      'cacheinvalidation',
      'cc_unittests',
      'chromedriver2_unittests',
      'content_browsertests',
      'courgette',
      'crypto',
      'googleurl',
      'gpu',
      'installer',
      'interactive_ui_tests',
      'jingle',
      'media',
      'ppapi_unittests',
      'printing',
      'remoting',
      'sandbox',
      'webkit_compositor_bindings_unittests',
    ],
    factory_properties={'process_dumps': True,
                        'sharded_tests': sharded_tests,
                        'browser_total_shards': 3, 'browser_shard_index': 1,
                        'start_crash_handler': True,
                        'generate_gtest_json': True}))

B('XP Tests (2)', 'rel_unit_2', 'testers|windows', 'win_rel_trigger',
  notify_on_missing=True)
F('rel_unit_2', win_tester().ChromiumFactory(
    slave_type='Tester',
    build_url=rel_archive,
    tests=[
      'base_unittests',
      'browser_tests',
      'net',
    ],
    factory_properties={'process_dumps': True,
                        'sharded_tests': sharded_tests,
                        'browser_total_shards': 3, 'browser_shard_index': 2,
                        'start_crash_handler': True,
                        'generate_gtest_json': True}))

B('XP Tests (3)', 'rel_unit_3', 'testers|windows', 'win_rel_trigger',
  notify_on_missing=True)
F('rel_unit_3', win_tester().ChromiumFactory(
    slave_type='Tester',
    build_url=rel_archive,
    tests=[
      'browser_tests',
      'components_unittests',
      'unit',
    ],
    factory_properties={'process_dumps': True,
                        'sharded_tests': sharded_tests,
                        'browser_total_shards': 3, 'browser_shard_index': 3,
                        'start_crash_handler': True,
                        'generate_gtest_json': True}))

B('Vista Tests (1)', 'rel_unit_1', 'testers|windows', 'win_rel_trigger',
  notify_on_missing=True)
B('Vista Tests (2)', 'rel_unit_2', 'testers|windows', 'win_rel_trigger',
  notify_on_missing=True)
B('Vista Tests (3)', 'rel_unit_3', 'testers|windows', 'win_rel_trigger',
  notify_on_missing=True)
B('Win7 Tests (1)', 'rel_unit_1', 'testers|windows', 'win_rel_trigger',
  notify_on_missing=True)
B('Win7 Tests (2)', 'rel_unit_2', 'testers|windows', 'win_rel_trigger',
  notify_on_missing=True)
B('Win7 Tests (3)', 'rel_unit_3', 'testers|windows', 'win_rel_trigger',
  notify_on_missing=True)

B('Win7 Sync', 'rel_sync', 'testers|windows', 'win_rel_trigger',
  notify_on_missing=True)
F('rel_sync', win_tester().ChromiumFactory(
    slave_type='Tester',
    build_url=rel_archive,
    tests=['sync_integration'],
    factory_properties={'process_dumps': True,
                        'start_crash_handler': True,
                        'generate_gtest_json': True}))

B('NaCl Tests (x86-32)', 'rel_nacl', 'testers|windows', 'win_rel_trigger',
  notify_on_missing=True)
F('rel_nacl', win_tester().ChromiumFactory(
    slave_type='Tester',
    build_url=rel_archive,
    tests=['nacl_integration'],
    factory_properties={'process_dumps': True,
                        'start_crash_handler': True,}))

B('NaCl Tests (x86-64)', 'rel_nacl', 'testers|windows', 'win_rel_trigger',
  notify_on_missing=True)

B('Chrome Frame Tests (ie6)', 'rel_cf', 'testers|windows', 'win_rel_trigger',
  notify_on_missing=True)
F('rel_cf', win_tester().ChromiumFactory(
    slave_type='Tester',
    build_url=rel_archive,
    tests=[
      'chrome_frame_tests',
      'chrome_frame_net_tests',
      'chrome_frame_unittests',
    ],
    factory_properties={'process_dumps': True,
                        'generate_gtest_json': True,
                        'start_crash_handler': True,}))

B('Chrome Frame Tests (ie7)', 'rel_cf', 'testers|windows', 'win_rel_trigger',
  notify_on_missing=True)
B('Chrome Frame Tests (ie8)', 'rel_cf', 'testers|windows|chrome_frame',
  'win_rel_trigger', notify_on_missing=True)
B('Chrome Frame Tests (ie9)', 'rel_cf', 'testers|windows', 'win_rel_trigger',
  notify_on_missing=True)

################################################################################
## Debug
################################################################################

dbg_archive = master_config.GetArchiveUrl('ChromiumWin', 'Win Builder (dbg)',
                                          'cr-win-dbg', 'win32')
dbg_aura_archive = master_config.GetArchiveUrl('ChromiumWin',
                                               'Win Aura Builder',
                                               'Win_Aura_Builder', 'win32')

#
# Main debug scheduler for src/
#
S('win_dbg', branch='src', treeStableTimer=60)

#
# Triggerable scheduler for the dbg builder
#
T('win_dbg_trigger')
T('win_dbg_aura_trigger')

#
# Win Dbg Builder
#
B('Win Builder (dbg)', 'dbg', 'compile|windows', 'win_dbg',
  builddir='cr-win-dbg', auto_reboot=False, notify_on_missing=True)
F('dbg', win().ChromiumFactory(
    target='Debug',
    slave_type='Builder',
    project='all.sln;chromium_builder_tests',
    factory_properties={'gclient_env': {'GYP_DEFINES': 'fastbuild=1'},
                        'trigger': 'win_dbg_trigger'}))

#
# Win Dbg Unit testers
#
B('XP Tests (dbg)(1)', 'dbg_unit_1', 'testers|windows', 'win_dbg_trigger',
  notify_on_missing=True)
F('dbg_unit_1', win_tester().ChromiumFactory(
    target='Debug',
    slave_type='Tester',
    build_url=dbg_archive,
    tests=[
      'base_unittests',
      'cacheinvalidation',
      'cc_unittests',
      'chromedriver2_unittests',
      'check_deps',
      'components_unittests',
      'courgette',
      'crypto',
      'googleurl',
      'gpu',
      'installer',
      'jingle',
      'media',
      'ppapi_unittests',
      'printing',
      'remoting',
      'unit',
      'webkit_compositor_bindings_unittests',
    ],
    factory_properties={'process_dumps': True,
                        'sharded_tests': sharded_tests,
                        'start_crash_handler': True,
                        'generate_gtest_json': True}))


B('XP Tests (dbg)(2)', 'dbg_unit_2', 'testers|windows', 'win_dbg_trigger',
  notify_on_missing=True)
F('dbg_unit_2', win_tester().ChromiumFactory(
    target='Debug',
    slave_type='Tester',
    build_url=dbg_archive,
    tests=[
      'browser_tests',
      'content_browsertests',
      'net',
    ],
    factory_properties={'sharded_tests': sharded_tests,
                        'browser_total_shards': 5, 'browser_shard_index': 1,
                        'process_dumps': True,
                        'start_crash_handler': True,
                        'generate_gtest_json': True}))

B('XP Tests (dbg)(3)', 'dbg_unit_3', 'testers|windows', 'win_dbg_trigger',
  notify_on_missing=True)
F('dbg_unit_3', win_tester().ChromiumFactory(
    target='Debug',
    slave_type='Tester',
    build_url=dbg_archive,
    tests=[
      'browser_tests',
      'sandbox',
    ],
    factory_properties={'sharded_tests': sharded_tests,
                        'browser_total_shards': 5, 'browser_shard_index': 2,
                        'process_dumps': True,
                        'start_crash_handler': True,
                        'generate_gtest_json': True}))

B('XP Tests (dbg)(4)', 'dbg_unit_4', 'testers|windows', 'win_dbg_trigger',
  notify_on_missing=True)
F('dbg_unit_4', win_tester().ChromiumFactory(
    target='Debug',
    slave_type='Tester',
    build_url=dbg_archive,
    tests=['browser_tests'],
    factory_properties={'sharded_tests': sharded_tests,
                        'browser_total_shards': 5, 'browser_shard_index': 3,
                        'process_dumps': True,
                        'start_crash_handler': True,
                        'generate_gtest_json': True}))

B('XP Tests (dbg)(5)', 'dbg_unit_5', 'testers|windows', 'win_dbg_trigger',
  notify_on_missing=True)
F('dbg_unit_5', win_tester().ChromiumFactory(
    target='Debug',
    slave_type='Tester',
    build_url=dbg_archive,
    tests=['browser_tests'],
    factory_properties={'sharded_tests': sharded_tests,
                        'browser_total_shards': 5, 'browser_shard_index': 4,
                        'process_dumps': True,
                        'start_crash_handler': True,
                        'generate_gtest_json': True}))

B('XP Tests (dbg)(6)', 'dbg_unit_6', 'testers|windows', 'win_dbg_trigger',
  notify_on_missing=True)
F('dbg_unit_6', win_tester().ChromiumFactory(
    target='Debug',
    slave_type='Tester',
    build_url=dbg_archive,
    tests=['browser_tests'],
    factory_properties={'sharded_tests': sharded_tests,
                        'browser_total_shards': 5, 'browser_shard_index': 5,
                        'process_dumps': True,
                        'start_crash_handler': True,
                        'generate_gtest_json': True}))

B('Win7 Tests (dbg)(1)', 'dbg_unit_1', 'testers|windows', 'win_dbg_trigger',
  notify_on_missing=True)
B('Win7 Tests (dbg)(2)', 'dbg_unit_2', 'testers|windows', 'win_dbg_trigger',
  notify_on_missing=True)
B('Win7 Tests (dbg)(3)', 'dbg_unit_3', 'testers|windows', 'win_dbg_trigger',
  notify_on_missing=True)
B('Win7 Tests (dbg)(4)', 'dbg_unit_4', 'testers|windows', 'win_dbg_trigger',
  notify_on_missing=True)
B('Win7 Tests (dbg)(5)', 'dbg_unit_5', 'testers|windows', 'win_dbg_trigger',
  notify_on_missing=True)
B('Win7 Tests (dbg)(6)', 'dbg_unit_6', 'testers|windows', 'win_dbg_trigger',
  notify_on_missing=True)

#
# Win Dbg Interactive Tests
#
B('Interactive Tests (dbg)', 'dbg_int', 'testers|windows', 'win_dbg_trigger',
  notify_on_missing=True)
F('dbg_int', win_tester().ChromiumFactory(
    target='Debug',
    slave_type='Tester',
    build_url=dbg_archive,
    tests=['interactive_ui_tests'],
    factory_properties={'process_dumps': True,
                        'start_crash_handler': True,
                        'generate_gtest_json': True}))

#
# Dbg Aura builder
#

aura_gyp_defines = 'use_aura=1 fastbuild=1 chromium_win_pch=0'

B('Win Aura Builder', 'dbg_aura', 'compile|windows', 'win_dbg',
  auto_reboot=False, notify_on_missing=True)
F('dbg_aura', win_out().ChromiumFactory(
    target='Debug',
    options=['--build-tool=ninja', '--compiler=goma', '--', 'aura_builder'],
    slave_type='Builder',
    factory_properties={'gclient_env': {'GYP_DEFINES': aura_gyp_defines},
                        'trigger': 'win_dbg_aura_trigger'}))

#
# Dbg Aura Testers
#

B('Win Aura Tests (1)', 'dbg_aura_test_1', 'testers|windows',
  'win_dbg_aura_trigger', notify_on_missing=True)
F('dbg_aura_test_1', win_tester().ChromiumFactory(
    target='Debug',
    slave_type='Tester',
    build_url=dbg_aura_archive,
    tests=['ash_unittests',
           'aura',
           'browser_tests',
           'content_browsertests',
          ],
    factory_properties={'process_dumps': True,
                        'sharded_tests': sharded_tests,
                        'browser_total_shards': 3, 'browser_shard_index': 1,
                        'start_crash_handler': True,
                        'generate_gtest_json': True}))

B('Win Aura Tests (2)', 'dbg_aura_test_2', 'testers|windows',
  'win_dbg_aura_trigger', notify_on_missing=True)
F('dbg_aura_test_2', win_tester().ChromiumFactory(
    target='Debug',
    slave_type='Tester',
    build_url=dbg_aura_archive,
    tests=['browser_tests',
           'compositor',
           'content_unittests',
           'unit_tests',
           'views_unittests',
          ],
    factory_properties={'process_dumps': True,
                        'sharded_tests': sharded_tests,
                        'browser_total_shards': 3, 'browser_shard_index': 2,
                        'start_crash_handler': True,
                        'generate_gtest_json': True}))

B('Win Aura Tests (3)', 'dbg_aura_test_3', 'testers|windows',
  'win_dbg_aura_trigger', notify_on_missing=True)
F('dbg_aura_test_3', win_tester().ChromiumFactory(
    target='Debug',
    slave_type='Tester',
    build_url=dbg_aura_archive,
    tests=['browser_tests',
           'interactive_ui_tests',
          ],
    factory_properties={'process_dumps': True,
                        'sharded_tests': sharded_tests,
                        'browser_total_shards': 3, 'browser_shard_index': 3,
                        'start_crash_handler': True,
                        'generate_gtest_json': True}))

B('Win8 Aura', 'dbg_aura_win8', 'windows',
  'win_dbg_aura_trigger', notify_on_missing=True)
F('dbg_aura_win8', win_tester().ChromiumFactory(
    target='Debug',
    slave_type='Tester',
    build_url=dbg_aura_archive,
    tests=['ash_unittests',
           'aura',
           'compositor',
           'views_unittests',
          ],
    factory_properties={'process_dumps': True,
                        'start_crash_handler': True,
                        'generate_gtest_json': True}))

def Update(config, active_master, c):
  return helper.Update(c)
