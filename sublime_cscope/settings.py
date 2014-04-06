
import sublime

from ..SublimeCscope import PACKAGE_NAME

SETTING_DEFAULTS = {
                        'index_file_extensions': [
                                                    ".c",
                                                    ".cc",
                                                    ".cpp",
                                                    ".h",
                                                    ".hpp",
                                                    ".l",
                                                    ".y",
                                                    ".py",
                                                    ".rb",
                                                    ".java"
                                                ],
                        'cscope_path': None,
                        'search_std_include_folders': False,
                        'extra_include_folders': [],
                        'tmp_folder': [],
                        'maximum_results': 1000
                   }

def load_settings():
    return sublime.load_settings(PACKAGE_NAME + '.sublime-settings')

def get(key, view_or_window):
    default = SETTING_DEFAULTS.get(key, None)

    #first lookup the setting in project if it exists
    #(prefixed by 'sublimecscope_')
    win = view_or_window
    if hasattr(view_or_window, 'window'):
        win = view_or_window.window()

    proj_settings = win.project_data().get('settings', None) if win else None
    proj_settings_key = 'sublimecscope_' + key
    if proj_settings and proj_settings_key in proj_settings:
        return proj_settings[proj_settings_key]

    #Otherwise look in our own settings
    return load_settings().get(key, default)




