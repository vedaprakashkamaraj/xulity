"""Entry point for the packaged GUI app (PyInstaller). Opens the window directly."""
import sys

if "--gui" not in sys.argv:
    sys.argv.insert(1, "--gui")
import xutil

xutil.main()
