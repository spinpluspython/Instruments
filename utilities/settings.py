# -*- coding: utf-8 -*-
"""

@author: Steinn Ymir Agustsson
"""
import ast
import os
from configparser import ConfigParser

def make_settings():
    settings_dict = {'paths':{'h5_data':'D:\data',
                              },
                     'general':{'verbose':'True',
                                },
                     'launcher':{'mode':'cmd',
                                 'recompile':'False',
                                 }
                     }

    settings = ConfigParser()
    for section_name, section in settings_dict.items():
        settings.add_section(section_name)
        for key, val in section.items():
            settings.set(section_name, key, str(val))

    with open('SETTINGS.ini', 'w') as configfile:
        settings.write(configfile)


def set_default_settings():
    default_settings = ConfigParser()
    default_settings.read('utilities/defaultSETTINGS.ini')

    with open('SETTINGS.ini', 'w') as configfile:
        default_settings.write(configfile)


def parse_category(category, settings_file='default'):
    """ parse setting file and return desired value

    Args:
        category (str): title of the category
        setting_file (str): path to setting file. If set to 'default' it takes
            a file called SETTINGS.ini in the main folder of the repo.

    Returns:
        dictionary containing name and value of all entries present in this
        category.
    """
    settings = ConfigParser()
    if settings_file == 'default':
        current_path = os.path.dirname(__file__)
        while not os.path.isfile(os.path.join(current_path, 'SETTINGS.ini')):
            current_path = os.path.split(current_path)[0]

        settings_file = os.path.join(current_path, 'SETTINGS.ini')
    settings.read(settings_file)
    try:
        cat_dict = {}
        for k,v in settings[category].items():
            try:
                cat_dict[k] = ast.literal_eval(v)
            except ValueError:
                cat_dict[k] = v
        return cat_dict
    except KeyError:
        print('No category "{}" found in SETTINGS.ini'.format(category))


def parse_setting(category, name, settings_file='default'):
    """ parse setting file and return desired value

    Args:
        category (str): title of the category
        name (str): name of the parameter
        setting_file (str): path to setting file. If set to 'default' it takes
            a file called SETTINGS.ini in the main folder of the repo.

    Returns:
        value of the parameter, None if parameter cannot be found.
    """
    settings = ConfigParser()
    if settings_file == 'default':
        current_path = os.path.dirname(__file__)
        while not os.path.isfile(os.path.join(current_path, 'SETTINGS.ini')):
            current_path = os.path.split(current_path)[0]

        settings_file = os.path.join(current_path, 'SETTINGS.ini')
    settings.read(settings_file)

    try:
        value = settings[category][name]
        return ast.literal_eval(value)
    except KeyError:
        print('No entry "{}" in category "{}" found in SETTINGS.ini'.format(name, category))
        return None
    except ValueError:
        return settings[category][name]
    except SyntaxError:
        return settings[category][name]

def write_setting(value, category, name, settings_file='default'):
    """ Write enrty in the settings file

    Args:
        category (str): title of the category
        name (str): name of the parameter
        setting_file (str): path to setting file. If set to 'default' it takes
            a file called SETTINGS.ini in the main folder of the repo.

    Returns:
        value of the parameter, None if parameter cannot be found.
    """
    settings = ConfigParser()
    if settings_file == 'default':
        current_path = os.path.dirname(__file__)
        while not os.path.isfile(os.path.join(current_path, 'SETTINGS.ini')):
            current_path = os.path.split(current_path)[0]

        settings_file = os.path.join(current_path, 'SETTINGS.ini')
    settings.read(settings_file)

    settings[category][name] = str(value)

    with open(settings_file, 'w') as configfile:
        settings.write(configfile)


if __name__ == '__main__':

    import time
    t0 = time.time()

    s = parse_setting('fastscan','shaker_position_step')
    print('{} as {} in {:.3f}ms'.format(s,type(s),(time.time()-t0)*1000))




