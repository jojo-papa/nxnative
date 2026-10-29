"""Filesystem paths shared by dependency and SDK archive installers."""
import os
from pathlib import Path
import shutil


def filesystem_path(path):
    path = Path(path).resolve()
    # SDK framework paths can exceed MAX_PATH in a deeply nested checkout.
    if os.name == 'nt' and not str(path).startswith('\\\\?\\'):
        text = str(path)
        path = Path('\\\\?\\UNC\\' + text[2:] if text.startswith('\\\\') else '\\\\?\\' + text)
    return path



def remove_stage(stage, root):
    stage, root = Path(stage).resolve(), Path(root).resolve()
    if stage == root or not stage.is_relative_to(root):
        raise ValueError('Refusing to remove a staging directory outside the tools folder')
    shutil.rmtree(filesystem_path(stage), ignore_errors=True)

