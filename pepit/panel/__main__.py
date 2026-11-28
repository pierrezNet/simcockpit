import sys

from ..devmode import run, take_flag

if take_flag(sys.argv):
    # le panneau est aussi relancé quand un fichier de configuration YAML change
    sys.exit(run("pepit.panel", sys.argv[1:], watch=("pepit/**/*.py", "config/**/*.yaml", "*.yaml")))

from .app import main  # noqa: E402

sys.exit(main())
