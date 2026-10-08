"""Process-level paths. Environment overrides are operator configuration, not tools.

No credentials or participant state are read when this module is imported.
"""
import os
import json
from pathlib import Path
import shutil

REPO = Path(__file__).resolve().parents[6]


RUNTIME_ROOT = Path(os.environ.get('BF_RUNTIME_ROOT', str(Path.home() / '.local/share/bf-agent-runtime'))).expanduser().absolute()
CONFIG_PATH = Path(os.environ.get('BF_RUNTIME_CONFIG', str(RUNTIME_ROOT / 'runtime.json'))).expanduser()
# A single local operator file applies to service, CLI, tests and child solvers.
# Explicit BF_* environment overrides retain precedence for isolated tests.
_CONFIG = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.is_file() else {}
if _CONFIG and _CONFIG.get('schema_version') != 'bf-runtime-layout-v1':
    raise ValueError('RUNTIME_CONFIG_SCHEMA_INVALID')


def configured(name, default):
    value = os.environ.get('BF_' + name) or _CONFIG.get('paths', {}).get(name)
    return Path(value).expanduser().absolute() if value else Path(default).expanduser().absolute()


HOME_ROOT = configured('HOME', RUNTIME_ROOT / 'workbench')
PI = configured('PI_ROOT', RUNTIME_ROOT / 'pi-bf-aiot')
NODE = configured('NODE', shutil.which('node') or '/opt/homebrew/bin/node')
KEY_PATH = configured('PROVIDER_KEY_FILE', HOME_ROOT / 'secrets/deepseek.key')
CAD = configured('CAD_PYTHON', RUNTIME_ROOT / 'product-cad/bin/python')
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
