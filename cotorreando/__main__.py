import sys

if "--self-test" in sys.argv:  # before the app module: nothing of the GUI, tray or audio starts
    from cotorreando.selftest import run

    sys.exit(run(sys.argv))

from cotorreando.app import main

sys.exit(main())
