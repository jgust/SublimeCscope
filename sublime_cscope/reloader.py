
import sys

import sublime

from imp import reload

from ..SublimeCscope import PACKAGE_NAME, DEBUG

# Heavily influenced by wbond's package control
reload_mods = []
for mod in sys.modules:
    if mod.startswith(PACKAGE_NAME) and sys.modules[mod] != None:
        if DEBUG: print("Found mod: %s to reload" % mod)
        reload_mods.append(mod)

mod_prefix = PACKAGE_NAME + '.sublime_cscope'

mods_load_order = ['']
mods_load_order.append('.settings')
mods_load_order.append('.event_listener')
mods_load_order.append('.indexer')
mods_load_order.append('.cscope_runner')
mods_load_order.append('.cscope_results')
mods_load_order.append('.commands')
mods_load_order.append('.commands.query')
mods_load_order.append('.commands.index')

if DEBUG:
    reloaded_mods = []
    mods_load_order.append('.tests')
    mods_load_order.append('.tests.test_indexer')
    mods_load_order.append('.tests.test_event_listener')
    mods_load_order.append('.tests.test_cscope_results')
    mods_load_order.append('.debug_commands')
    mods_load_order.append('.debug_commands.run_tests_command')


for suffix in mods_load_order:
    mod = mod_prefix + suffix
    if mod in reload_mods:
        if DEBUG: print("Reloading: %s" % mod)
        try:
            reload(sys.modules[mod])
            if DEBUG: reloaded_mods.append(mod)
        except ImportError as e:
            print("Could not reload %s from path %s" % (mod, e.path))
    elif DEBUG:
        print("Module %s was not found in list of modules that are possible to reload. Typo?" % mod)

if DEBUG:
    reload_mods.remove(PACKAGE_NAME)
    reload_mods.remove(PACKAGE_NAME + '.' + PACKAGE_NAME)
    reload_mods.remove(__name__)
    forgotten_mods = set(reload_mods) - set(reloaded_mods)
    for mod in forgotten_mods:
        print("Module %s was not explicitly reloaded. Did you forget to add it?" % mod)

