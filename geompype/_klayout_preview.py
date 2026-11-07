"""Reload a GDS preview in KLayout Desktop without blocking its event loop.

``Project.show()`` launches this macro inside KLayout Desktop. It is not
imported by the geometry package; Desktop supplies the required ``pya`` API.
The producer replaces the GDS atomically; this script never writes the file.
Closing the preview tab stops watching. Closing KLayout also destroys the timer.

Desktop API references:
https://www.klayout.de/doc/code/class_QTimer.html
https://www.klayout.de/doc/code/class_MainWindow.html
https://www.klayout.de/doc/code/class_LayoutView.html
"""

import os
import sys

import pya  # Desktop's embedded Python exposes both the Qt and layout APIs.


class GdsPreview:
    """Watch one file and update its original tab every 200 milliseconds."""

    def __init__(self, filename):
        self.filename = os.path.abspath(filename)
        self.window = pya.Application.instance().main_window()
        if self.window is None:
            raise RuntimeError("GDS preview requires KLayout Desktop in GUI mode.")
        self.view = None
        self.cellview_index = None
        self.signature = None
        self.read_failures = 0
        self.timer = pya.QTimer(self.window)
        self.timer.timeout = self.poll
        self.timer.start(200)

    def poll(self):
        """Stop on unexpected errors so a broken callback cannot repeat forever."""
        try:
            self.reload_if_changed()
        except Exception:
            self.timer.stop()
            raise

    def reload_if_changed(self):
        if self.view is not None and self.view._destroyed():
            self.timer.stop()
            return

        try:
            stat = os.stat(self.filename)
        except FileNotFoundError:
            # The initial export may not exist yet, or replacement is in flight.
            return
        signature = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino)
        if signature == self.signature:
            return

        first_load = self.view is None
        try:
            if first_load:
                cellview = self.window.load_layout(self.filename, 1)
            else:
                self.view.reload_layout(self.cellview_index)
        except (OSError, RuntimeError) as error:
            # KLayout reports reader errors as RuntimeError. Retry only these
            # I/O calls, at most three times; a persistent error stays visible.
            self.read_failures += 1
            if self.read_failures >= 3:
                raise
            print("GDS preview: retrying read: {}".format(error), file=sys.stderr)
            return

        self.read_failures = 0
        if first_load:
            self.view = self.window.current_view()
            self.cellview_index = cellview.index()
        self.view.add_missing_layers()
        self.view.show_all_cells()
        self.view.zoom_fit()
        self.signature = signature


_filename = globals().get("gds_file", "")
if not _filename:
    raise ValueError("Pass the GDS path with -rd gds_file=/path/design.gds.")

# Keep a Python reference after the startup macro returns to the GUI event loop.
_preview = GdsPreview(str(_filename))
