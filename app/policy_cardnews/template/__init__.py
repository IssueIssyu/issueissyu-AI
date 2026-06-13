# JSON·Pillow 고정 템플릿

from app.policy_cardnews.template.dispatch import (
    LAYOUT_COVER,
    LAYOUT_CTA,
    LAYOUT_GRID,
    LAYOUT_NUMBERED,
    LAYOUT_THREE_COL,
    MASCOT_LAYOUTS,
    TemplateContext,
    apply_deck_template_theme,
    build_template_context,
    load_custom_palettes,
    normalize_to_template_slide,
    render_template_slide,
    resolve_template_palette,
    template_palette_names,
)

__all__ = [
    "LAYOUT_COVER",
    "LAYOUT_CTA",
    "LAYOUT_GRID",
    "LAYOUT_NUMBERED",
    "LAYOUT_THREE_COL",
    "MASCOT_LAYOUTS",
    "TemplateContext",
    "apply_deck_template_theme",
    "build_template_context",
    "load_custom_palettes",
    "normalize_to_template_slide",
    "render_template_slide",
    "resolve_template_palette",
    "template_palette_names",
]
