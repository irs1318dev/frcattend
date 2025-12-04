"""A switch that toggles inactive students on and off."""

from textual import app, containers, widget, widgets


class InactiveStudentToggle(widget.Widget):
    """A custom widget for toggling the view of inactive students on and off."""

    def compose(self) -> app.ComposeResult:
        """Assemble the label and switch."""
        with containers.Horizontal(classes="toggle-inactive-students"):
            yield widgets.Label("Include Inactive Students:")
            yield widgets.Switch(False, classes="toggle-inactive-students-switch")

    @property
    def value(self) -> bool:
        """Value of the switch."""
        return self.query_one(".toggle-inactive-students-switch", widgets.Switch).value
