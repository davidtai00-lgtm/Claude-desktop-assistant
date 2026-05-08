# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['Main.py'],
    pathex=[],
    binaries=[],
    datas=[('logo_ys.png', '.'), ('config.json', '.')],
    hiddenimports=[
        'pyqtgraph',
        'pyqtgraph.graphicsItems.ViewBox.ViewBoxMenu',
        'pyqtgraph.graphicsItems.PlotItem.PlotItem',
        'pyqtgraph.graphicsItems.LegendItem',
        'pyqtgraph.graphicsItems.TextItem',
        'pyqtgraph.graphicsItems.InfiniteLine',
        'pyqtgraph.graphicsItems.SignalProxy',
        'pyqtgraph.Qt',
        'numpy',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch', 'scipy', 'pandas', 'PIL', 'numba', 'llvmlite',
        'pyarrow', 'sklearn', 'matplotlib', 'tensorflow',
        'onnxruntime', 'sympy', 'IPython', 'jupyter',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='YS_Assistant',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='logo_ys.png',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='YS_Assistant',
)
