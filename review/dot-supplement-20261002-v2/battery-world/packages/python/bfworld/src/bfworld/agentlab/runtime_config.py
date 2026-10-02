"""Process-level paths. Environment overrides are operator configuration, not tools.

No credentials or participant state are read when this module is imported.
"""
import os
from pathlib import Path
import shutil

REPO = Path(__file__).resolve().parents[6]


def configured(name, default):
    value = os.environ.get('BF_' + name)
    return Path(value).expanduser().absolute() if value else Path(default).expanduser().absolute()


HOME_ROOT = configured('HOME', Path.home() / 'Documents/bf-agent-workbench')
PI = configured('PI_ROOT', REPO.parent / 'pi-bf-aiot')
NODE = configured('NODE', shutil.which('node') or '/opt/homebrew/bin/node')
KEY_PATH = configured('PROVIDER_KEY_FILE', HOME_ROOT / 'secrets/deepseek.key')
CAD = configured('CAD_PYTHON', HOME_ROOT / 'toolchains/product-cad/bin/python')
BLENDER = configured('BLENDER', '/Applications/Blender.app/Contents/MacOS/Blender')
COMSOL = configured('COMSOL', '/Applications/COMSOL62/Multiphysics/bin/comsol')
SPICE = configured('NGSPICE', shutil.which('ngspice') or '/opt/homebrew/bin/ngspice')
GCC = configured('ARM_GCC', shutil.which('arm-none-eabi-gcc') or '/opt/ST/STM32CubeCLT_1.19.0/GNU-tools-for-STM32/bin/arm-none-eabi-gcc')
CMSIS = configured('CMSIS', HOME_ROOT / 'toolchains/stm32l031')


def public_paths():
    """Operator diagnostics omit secret paths and values."""
    return {k: {'path': str(v), 'exists': v.exists()} for k, v in
            [('home', HOME_ROOT), ('pi', PI), ('node', NODE), ('cad', CAD),
             ('blender', BLENDER), ('comsol', COMSOL), ('ngspice', SPICE),
             ('arm_gcc', GCC), ('cmsis', CMSIS)]}
