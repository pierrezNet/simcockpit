import sys

from ..devmode import run, take_flag

if take_flag(sys.argv):
    # relancé à chaque modification du code ou d'un fichier de configuration YAML
    sys.exit(run("pepit.app", sys.argv[1:], watch=("pepit/**/*.py", "config/**/*.yaml", "*.yaml")))

from .main import main  # noqa: E402

sys.exit(main())
