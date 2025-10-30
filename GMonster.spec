# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import copy_metadata, collect_data_files
import os

cwd = os.getcwd()

icons_path = os.path.join(cwd, 'icons')

datas = []
datas += copy_metadata('apscheduler', recursive=True)
datas += collect_data_files('textblob.en') # Collecting data for sentiment analysis
datas += collect_data_files('tzdata')

block_cipher = None


a = Analysis(['var.py'],
             pathex=[cwd],
             binaries=[],
             datas=datas,
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)

a.datas += Tree(icons_path, prefix='icons\\')

pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
          name='GMonster',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=False, icon='icons\\icon.ico')
