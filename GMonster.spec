# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import copy_metadata, collect_data_files
import certifi
import os

_spec_file = globals().get('__file__')
spec_dir = os.path.abspath(os.path.dirname(_spec_file)) if _spec_file else os.path.abspath(os.getcwd())

icons_path = os.path.join(spec_dir, 'icons')
gmaps_scraper_assets_path = os.path.join(
    spec_dir, 'data', 'tools', 'google_maps_scraper'
)
starter_data_path = os.path.join(spec_dir, 'starter-data')
config_template_path = os.path.join(spec_dir, 'config.example.json')
certificate_path = certifi.where()


def _safe_copy_metadata(package_name, recursive=False):
    try:
        return copy_metadata(package_name, recursive=recursive)
    except Exception:
        return []


def _safe_collect_data_files(package_name):
    try:
        return collect_data_files(package_name)
    except Exception:
        return []

datas = []
datas += _safe_copy_metadata('apscheduler', recursive=True)
datas += _safe_collect_data_files('textblob.en')
datas += _safe_collect_data_files('tzdata')
datas += _safe_collect_data_files('qtawesome')
if os.path.isfile(config_template_path):
    datas += [(config_template_path, 'default-data')]
if os.path.isfile(certificate_path):
    datas += [(certificate_path, 'default-data')]

block_cipher = None


a = Analysis(['var.py'],
             pathex=[spec_dir],
             binaries=[],
             datas=datas,
             hiddenimports=['qtawesome'],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)

if os.path.isdir(icons_path):
    a.datas += Tree(icons_path, prefix='icons')
if os.path.isdir(gmaps_scraper_assets_path):
    a.datas += Tree(
        gmaps_scraper_assets_path,
        prefix='data/tools/google_maps_scraper'
    )
if os.path.isdir(starter_data_path):
    a.datas += Tree(starter_data_path, prefix='starter-data')
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

icon_path = os.path.join(spec_dir, 'icons', 'icon.ico')
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
          console=os.environ.get("GMONSTER_CONSOLE_BUILD") == "1",
          icon=icon_path if os.path.isfile(icon_path) else None)
