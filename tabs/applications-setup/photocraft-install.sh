#!/bin/sh -e
# Installs PhotoCraft (AppImage) from the official GitHub release into ~/.local, no root needed.
# Verifies the SHA-256 checksum from the release's SHA256SUMS.txt before installing.
. ../common-script.sh

for c in curl sha256sum; do
    command_exists "$c" || { printf "%b\n" "${RED}$c is required${RC}"; exit 1; }
done
[ "$(uname -s)" = "Linux" ] || { printf "%b\n" "${RED}Linux only${RC}"; exit 1; }
case "$(uname -m)" in
    x86_64 | amd64) arch=x86_64 ;;
    aarch64 | arm64) arch=aarch64 ;;
    *) printf "%b\n" "${RED}Unsupported CPU: $(uname -m)${RC}"; exit 1 ;;
esac

API="${PHOTOCRAFT_API:-https://api.github.com/repos/storytold/photocraft/releases/latest}"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

printf "%b\n" "${CYAN}Looking up the latest PhotoCraft release...${RC}"
curl -fsSL "$API" -o "$tmp/release.json"
urls=$(grep -o '"browser_download_url": *"[^"]*"' "$tmp/release.json" | sed 's/.*"\(http[^"]*\)"$/\1/')
app_url=$(printf '%s\n' "$urls" | grep "linux-${arch}\.AppImage\$" | head -n 1)
sum_url=$(printf '%s\n' "$urls" | grep 'SHA256SUMS\.txt$' | head -n 1)
if [ -z "$app_url" ] || [ -z "$sum_url" ]; then
    printf "%b\n" "${RED}Could not find the AppImage or SHA256SUMS.txt in the latest release.${RC}"; exit 1
fi

file=$(basename "$app_url")
printf "%b\n" "${YELLOW}Downloading ${file}${RC}"
curl -fL --progress-bar "$app_url" -o "$tmp/$file"
curl -fsSL "$sum_url" -o "$tmp/SHA256SUMS.txt"

expected=$(awk -v f="$file" '{n=$2; sub(/^\*/,"",n); if (n==f) print $1}' "$tmp/SHA256SUMS.txt" | head -n 1)
actual=$(sha256sum "$tmp/$file" | awk '{print $1}')
if [ -z "$expected" ] || [ "$expected" != "$actual" ]; then
    printf "%b\n" "${RED}Checksum verification FAILED. Nothing was installed.${RC}"; exit 1
fi
printf "%b\n" "${GREEN}Checksum OK${RC}"

dest="$HOME/.local/share/photocraft"
bin="$HOME/.local/bin"
mkdir -p "$dest" "$bin"
install -m 755 "$tmp/$file" "$dest/photocraft.AppImage"
cat > "$bin/photocraft" <<'WRAP'
#!/bin/sh
# Use extract-and-run when libfuse2 is missing (common on new Fedora/Ubuntu installs).
if ! ldconfig -p 2>/dev/null | grep -q 'libfuse\.so\.2'; then export APPIMAGE_EXTRACT_AND_RUN=1; fi
exec "$HOME/.local/share/photocraft/photocraft.AppImage" "$@"
WRAP
chmod 755 "$bin/photocraft"

printf "%b\n" "${GREEN}Installed. Start it with: photocraft${RC}"
case ":$PATH:" in
    *":$bin:"*) ;;
    *) printf "%b\n" "${YELLOW}Add $bin to your PATH, or run it as $bin/photocraft${RC}" ;;
esac
printf "%b\n" "${YELLOW}Note: PhotoCraft is early alpha software. Keep backups of your originals.${RC}"
