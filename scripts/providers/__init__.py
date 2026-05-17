"""Source providers for Memory Tree Pipeline."""
from providers.obsidian import ObsidianProvider
from providers.wiki import WikiProvider
from providers.thebrain import TheBrainProvider
from providers.apple_notes import AppleNotesProvider
from providers.chat import ChatProvider
from providers.journal import JournalProvider
from providers.spotify import SpotifyProvider

ALL_PROVIDERS = [
    ObsidianProvider,
    WikiProvider,
    TheBrainProvider,
    AppleNotesProvider,
    ChatProvider,
    JournalProvider,
    SpotifyProvider,
]

__all__ = [
    "ObsidianProvider", "WikiProvider", "TheBrainProvider",
    "AppleNotesProvider", "ChatProvider", "JournalProvider",
    "SpotifyProvider", "ALL_PROVIDERS"
]
