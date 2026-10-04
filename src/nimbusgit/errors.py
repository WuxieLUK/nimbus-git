"""Domain-specific exceptions for nimbus-git."""


class NimbusGitError(Exception):
    """Base class for all user-facing nimbus-git errors."""


class NotARepositoryError(NimbusGitError):
    """Raised when a command is executed outside a repository."""


class InvalidObjectError(NimbusGitError):
    """Raised when an object cannot be parsed or is missing."""


class RefNotFoundError(NimbusGitError):
    """Raised when a branch, tag, or revision cannot be resolved."""


class IndexError(NimbusGitError):
    """Raised when the Git index cannot be read or written."""


class DirtyWorktreeError(NimbusGitError):
    """Raised when an operation would overwrite uncommitted changes."""
