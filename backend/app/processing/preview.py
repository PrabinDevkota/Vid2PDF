from app.processing.types import SelectedPage


def attach_previews(pages: list[SelectedPage]) -> list[SelectedPage]:
    """Placeholder preview metadata assignment."""
    for page in pages:
        page.preview_url = None
    return pages
