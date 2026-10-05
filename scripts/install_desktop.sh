#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_ID="fill-redmine-gui"
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/$APP_ID.desktop"

if ! python3 -c "import tkinter" >/dev/null 2>&1; then
    echo "tkinter не найден. Установите: sudo pacman -S tk"
    exit 1
fi

chmod +x "$PROJECT_DIR/run_gui.sh"
mkdir -p "$DESKTOP_DIR"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Fill Redmine
Comment=Импорт временных записей из YouTrack в Redmine
Exec="$PROJECT_DIR/run_gui.sh"
Path=$PROJECT_DIR
Icon=$PROJECT_DIR/assets/fill_redmine.svg
Terminal=false
Categories=Utility;Office;
StartupNotify=true
EOF

chmod +x "$DESKTOP_FILE"
update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true

if ! command -v qdbus6 >/dev/null 2>&1; then
    echo "Ярлык установлен. qdbus6 не найден: закрепите вручную (ПКМ → Закрепить на панели)."
    exit 0
fi

JS="$(cat <<'JSEOF'
var allPanels = panels();
var pinned = false;
for (var i = 0; i < allPanels.length; i++) {
    var widgets = allPanels[i].widgets();
    for (var j = 0; j < widgets.length; j++) {
        var w = widgets[j];
        if (w.type === "org.kde.plasma.icontasks" || w.type === "org.kde.plasma.taskmanager") {
            w.currentConfigGroup = ["General"];
            var raw = w.readConfig("launchers", "");
            var items = raw.length > 0 ? raw.split(",") : [];
            var entry = "applications:fill-redmine-gui.desktop";
            if (items.indexOf(entry) === -1) {
                items.push(entry);
                w.writeConfig("launchers", items.join(","));
                w.reloadConfig();
            }
            pinned = true;
        }
    }
}
print(pinned ? "pinned" : "no-taskmanager");
JSEOF
)"

RESULT="$(qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "$JS" 2>/dev/null || true)"

if [[ "$RESULT" == *pinned* ]]; then
    echo "Ярлык установлен и закреплён на панели."
else
    echo "Ярлык установлен. Автопин не удался: закрепите вручную (ПКМ → Закрепить на панели)."
fi
