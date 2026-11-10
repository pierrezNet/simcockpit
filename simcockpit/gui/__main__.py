import sys

from ..devmode import run, take_flag

if take_flag(sys.argv):
    sys.exit(run("simcockpit.gui", sys.argv[1:]))

from .app import main  # noqa: E402

sys.exit(main())
