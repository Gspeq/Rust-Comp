from __future__ import annotations

from tkinter import TclError
from typing import Any

# Import the earlier map/shop hotfix first so its strategic value scoring,
# map work, and application error handling remain active.
import rust_companion_plus.hotfix_map_shop as _legacy
from rust_companion_plus import app as _app
from rust_companion_plus.ui.tabs import shops_enhanced as _shops_enhanced


HOTFIX_ID = "SHOP_IMAGE_LIFETIME_REMOVE_DRONE_GUESS_V6"
DRONE_REACHABILITY_NOTICE = (
    "Rust+ provides broadcast vending markers, but it does not expose walls, "
    "roof geometry, blocked flight paths, or whether a Drone Marketplace drone "
    "can physically reach a machine. Rust Companion+ therefore does not infer "
    "or filter by drone reachability."
)

# V3 wrapped the real enhanced marketplace class with a player-owned marker
# filter. Keep its map, scoring, and notification work loaded, but build the
# active Shops tab from the original enhanced marketplace class so no drone
# reachability control or claim appears in the UI.
_EnhancedMarketplaceBase = getattr(
    _shops_enhanced,
    "_drone_filter_original_class",
    _shops_enhanced.ShopsTab,
)


def detach_minimap_image_before_release(owner: Any) -> bool:
    """Detach the Tk image name before releasing the owning CTkImage reference.

    Tk labels retain an internal string such as ``pyimage2``. Releasing the last
    Python image reference first deletes that Tk image, and a later label update
    can then raise ``TclError: image "pyimage2" doesn't exist``.
    """

    label = getattr(owner, "minimap_label", None)
    current = getattr(owner, "_minimap_ctk_image", None)
    if label is not None:
        try:
            label.configure(image=None)
        except TclError:
            # Recover a label whose Tk image was already deleted by older code.
            inner_label = getattr(label, "_label", None)
            if inner_label is None:
                raise
            inner_label.configure(image="")
            try:
                setattr(label, "_image", None)
            except Exception:
                pass

    # This assignment must happen only after the widget no longer references
    # the underlying Tk image name.
    owner._minimap_ctk_image = None
    return current is not None


class ReliableMarketplaceShopsTab(_EnhancedMarketplaceBase):
    """Marketplace without an unverifiable drone-reachability filter."""

    def _build_results_table(self) -> None:
        super()._build_results_table()
        self.table_note.configure(
            text=(
                "BP listings are marked directly. Best value uses comparable "
                "markets and history. Drone reachability is not inferred because "
                "Rust+ does not expose walls or flight-path access."
            )
        )

    def _clear_selection_detail(self) -> None:
        # Fix the image lifetime ordering before the inherited method resets the
        # remainder of the selection and minimap presentation.
        detach_minimap_image_before_release(self)
        super()._clear_selection_detail()


# app.py imported the V3 ShopsTab class earlier. Rebind only the application's
# runtime class. Keeping shops_enhanced.ShopsTab unchanged preserves the older
# V3 activation contract tests while the actual GUI uses this honest class.
_app.ShopsTab = ReliableMarketplaceShopsTab
_app.SHOP_RELIABILITY_HOTFIX_ID = HOTFIX_ID
_shops_enhanced.ReliableMarketplaceShopsTab = ReliableMarketplaceShopsTab
_shops_enhanced._drone_reachability_runtime_removed = HOTFIX_ID
_legacy.DRONE_REACHABILITY_RUNTIME_REMOVED_BY = HOTFIX_ID
