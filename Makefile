# make install     install xutil for the current user (~/.local)
# make run         run from this folder without installing (window)
# make uninstall   remove it
# make onefile     build dist/xutil.py (single self-contained file)
PREFIX ?= $(HOME)/.local
PY ?= python3

.PHONY: install uninstall run check onefile icons
install:
	./install.sh --prefix $(PREFIX)
uninstall:
	./install.sh --uninstall --prefix $(PREFIX)
run:
	$(PY) xutil.py --gui
check:
	$(PY) xutil.py --check
onefile:
	$(PY) build-onefile.py dist/xutil.py
# needs rsvg-convert and `npm pack simple-icons` (see tools/make_icons.py)
icons:
	$(PY) tools/make_icons.py $(NEW_ICONS) $(OLD_ICONS)
