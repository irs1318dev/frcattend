"""Widgets for selecting student status."""

from typing import Optional

from textual import widgets

from frcattend import model


class StatusSelector(widgets.SelectionList[model.Stage]):
    """Selection list of student stages."""

    def __init__(
        self,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
        disabled: bool = False,
    ) -> None:
        """Populate options from the Stage enum.

        MEMBER and PROSPECT stages are checked by default.
        """
        checked_stages = (model.Stage.MEMBER, model.Stage.PROSPECT)
        super().__init__(
            *[
                (stage.value.title(), stage, stage in checked_stages)
                for stage in model.Stage
            ],
            name=name,
            id=id,
            classes=classes,
            disabled=disabled,
        )
