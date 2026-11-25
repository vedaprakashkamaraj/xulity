const apps = [
  { name: "7-Zip", cat: "Utilities", icon: "7Z", desc: "Free file archiver with high compression and strong AES-256 encryption.", url: "https://www.7-zip.org/download.html" },
  { name: "Firefox", cat: "Browsers", icon: "FF", desc: "Private, open-source web browser from Mozilla.", url: "https://www.mozilla.org/firefox/new/" },
  { name: "Google Chrome", cat: "Browsers", icon: "CH", desc: "Fast Chromium-based browser with Google account sync.", url: "https://www.google.com/chrome/" },
  { name: "VLC", cat: "Media", icon: "VL", desc: "Plays almost any video or audio format, plus discs and streams.", url: "https://www.videolan.org/vlc/download-windows.html" },
  { name: "Visual Studio Code", cat: "Development", icon: "VS", desc: "Lightweight code editor with extensions, Git and debugging built in.", url: "https://code.visualstudio.com/Download" },
  { name: "Git for Windows", cat: "Development", icon: "GT", desc: "Git command line plus Bash and Git GUI for Windows.", url: "https://gitforwindows.org/" },
  { name: "Python", cat: "Development", icon: "PY", desc: "Python interpreter for Windows with pip and the standard library.", url: "https://www.python.org/downloads/windows/" },
  { name: "Node.js", cat: "Development", icon: "JS", desc: "JavaScript runtime and npm for Windows development.", url: "https://nodejs.org/en/download" },
  { name: "Notepad++", cat: "Development", icon: "NP", desc: "Fast source-code and text editor with syntax highlighting.", url: "https://notepad-plus-plus.org/downloads/" },
  { name: "PuTTY", cat: "Networking", icon: "PT", desc: "SSH, Telnet and serial client for remote access.", url: "https://www.chiark.greenend.org.uk/~sgtatham/putty/latest.html" },
  { name: "FileZilla", cat: "Networking", icon: "FZ", desc: "FTP, SFTP and FTPS client for transferring files.", url: "https://filezilla-project.org/download.php?type=client" },
  { name: "WinSCP", cat: "Networking", icon: "WS", desc: "Graphical SFTP, SCP and FTP client with scripting.", url: "https://winscp.net/eng/downloads.php" },
  { name: "Docker Desktop", cat: "Development", icon: "DK", desc: "Run containers locally with Docker and Kubernetes tooling.", url: "https://www.docker.com/products/docker-desktop/" },
  { name: "LibreOffice", cat: "Office", icon: "LO", desc: "Free office suite: Writer, Calc, Impress, Draw and more.", url: "https://www.libreoffice.org/download/download/" },
  { name: "GIMP", cat: "Graphics", icon: "GM", desc: "Free image editor for retouching, compositing and design.", url: "https://www.gimp.org/downloads/" },
  { name: "Audacity", cat: "Media", icon: "AU", desc: "Free audio editor and recorder for podcasts and music.", url: "https://www.audacityteam.org/download/" },
  { name: "OBS Studio", cat: "Media", icon: "OB", desc: "Free screen recording and live streaming software.", url: "https://obsproject.com/download" },
  { name: "Telegram Desktop", cat: "Communication", icon: "TG", desc: "Fast cloud-based messaging desktop app.", url: "https://desktop.telegram.org/" },
  { name: "Discord", cat: "Communication", icon: "DC", desc: "Voice, video and text chat for communities.", url: "https://discord.com/download" },
  { name: "Spotify", cat: "Media", icon: "SP", desc: "Music and podcast streaming desktop client.", url: "https://www.spotify.com/download/windows/" },
  { name: "Zoom", cat: "Communication", icon: "ZM", desc: "Video meetings, webinars and screen sharing.", url: "https://zoom.us/download" },
  { name: "Thunderbird", cat: "Communication", icon: "TB", desc: "Free email, calendar and news client from Mozilla.", url: "https://www.thunderbird.net/en-US/download/" },
  { name: "SumatraPDF", cat: "Utilities", icon: "SM", desc: "Small, fast PDF, EPUB and comic book reader.", url: "https://www.sumatrapdfreader.org/download-free-pdf-viewer.html" },
  { name: "Everything", cat: "Utilities", icon: "EV", desc: "Instant filename search across your whole drive.", url: "https://www.voidtools.com/downloads/" },
];

const grid = document.getElementById("grid");
const chips = document.getElementById("chips");
const q = document.getElementById("q");
const empty = document.getElementById("empty");
const count = document.getElementById("count");

let active = "All";

function categories() {
  return ["All", ...new Set(apps.map(a => a.cat))];
}

function render() {
  const term = q.value.trim().toLowerCase();
  const shown = apps.filter(a => {
    const matchesCat = active === "All" || a.cat === active;
    const matchesTerm = !term || [a.name, a.desc, a.cat].join(" ").toLowerCase().includes(term);
    return matchesCat && matchesTerm;
  });

  count.textContent = `${shown.length} of ${apps.length} apps`;
  empty.hidden = shown.length > 0;

  grid.innerHTML = shown.map(a => `
    <article class="card">
      <div class="card-top">
        <div class="icon">${a.icon}</div>
        <div><h3>${a.name}</h3><div class="cat">${a.cat}</div></div>
      </div>
      <p class="desc">${a.desc}</p>
      <a href="${a.url}" target="_blank" rel="noopener">Download ↗</a>
    </article>`).join("");
}

function renderChips() {
  chips.innerHTML = categories().map(c =>
    `<button class="chip ${c === active ? "active" : ""}" data-cat="${c}">${c}</button>`
  ).join("");
  chips.querySelectorAll(".chip").forEach(btn => {
    btn.addEventListener("click", () => {
      active = btn.dataset.cat;
      renderChips();
      render();
    });
  });
}

q.addEventListener("input", render);
renderChips();
render();
