import sys

from serifu_kuji.app import main as gui_main
from serifu_kuji.web import main as web_main

if __name__ == "__main__":
    if "--web" in sys.argv:
        web_main()
    else:
        gui_main()
