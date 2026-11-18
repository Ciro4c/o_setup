"""Điểm vào để đóng gói thành osetup.exe (PyInstaller)."""
import sys

from osetup.cli import main

if __name__ == "__main__":
    sys.exit(main())
