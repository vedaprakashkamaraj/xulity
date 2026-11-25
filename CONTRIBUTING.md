# Contributing to X Utility

Thanks for helping improve X Utility. Contributions of all sizes are welcome — docs, catalog entries, bug fixes and platform testing all matter.

## Before you start

- Search existing issues and pull requests first.
- For large changes, open an issue to discuss the approach.
- Be respectful and constructive.

## Development setup

```sh
git clone https://github.com/vedaprakashkamaraj/xulity.git
cd xulity
python3 -m venv .venv
. .venv/bin/activate
python3 xutil.py --check
python3 xutil.py --gui
```

The engine uses only the Python standard library. The GUI additionally needs `tkinter`.

## Adding a task

1. Add an entry to the relevant `tabs/<tab>/tab_data.toml`.
2. Put the script next to the tab data file (`.sh` or `.ps1`).
3. Add preconditions so the task only appears where it works.
4. Run `python3 xutil.py --check`.
5. Test with `--dry-run` before asking others to run it.

Keep scripts readable, ask before making system changes, and never download or execute unreviewed remote code without telling the user.

## Website changes

The official site lives in `site/` and uses Next.js, TypeScript and Tailwind CSS.

```sh
cd site
npm install
npm run dev
npm run typecheck
npm run build
```

Release information comes from the GitHub Releases API. Do not add fake download links or version numbers.

## Pull requests

- Keep each PR focused on one thing.
- Describe what changed and how you tested it.
- Include screenshots for visible UI changes.
- Update documentation when behaviour changes.

## License

By contributing, you agree that your work is licensed under the MIT License.
